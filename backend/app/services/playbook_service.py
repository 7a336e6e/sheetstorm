"""IR-aligned playbook action execution.

Executes investigation-augmenting actions only (enrich / summarize / suggest /
create-task). Synchronous and soft-failing — no background worker required for
an investigation-tracking tool. This is deliberately NOT a SOC alert-triage
engine: there is no alert ingestion, routing, or auto-escalation.
"""
from datetime import datetime, timezone
import re

from flask import current_app
from app import db


class PlaybookService:

    @staticmethod
    def execute_action(incident, action, user):
        """Execute a single playbook action; returns a result dict (never raises)."""
        atype = (action or {}).get('type')
        config = (action or {}).get('config') or {}
        try:
            if atype == 'enrich_iocs':
                return PlaybookService._enrich_iocs(incident, config)
            if atype == 'generate_summary':
                return PlaybookService._generate_summary(incident, config, user)
            if atype == 'suggest_mitre':
                return PlaybookService._suggest_mitre(incident, config)
            if atype == 'create_task':
                return PlaybookService._create_task(incident, config, user)
            return {'status': 'error', 'message': f'Unknown action type: {atype}'}
        except Exception:
            current_app.logger.exception('Playbook action failed')
            db.session.rollback()
            return {'status': 'error', 'message': 'action failed'}

    @staticmethod
    def _enrich_iocs(incident, config):
        from app.services.enrichment_service import EnrichmentService
        from app.models import NetworkIndicator
        iocs = NetworkIndicator.query.filter_by(incident_id=incident.id).all()
        enriched = 0
        for ioc in iocs:
            val = (ioc.dns_ip or '').strip()
            if not val:
                continue
            itype = 'ip-src' if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', val) else 'domain'
            result = EnrichmentService.auto_enrich_ioc(itype, val, str(incident.organization_id))
            if result:
                ed = dict(ioc.extra_data or {})
                ed['enrichment'] = result
                ioc.extra_data = ed
                enriched += 1
        db.session.commit()
        return {'status': 'success', 'message': f'Enriched {enriched}/{len(iocs)} network IOCs'}

    @staticmethod
    def _suggest_mitre(incident, config):
        from app.services.mitre_suggest_service import suggest
        from app.models import TimelineEvent
        events = TimelineEvent.query.filter_by(incident_id=incident.id).all()
        updated = 0
        for ev in events:
            if ev.mitre_mappings:
                continue
            sugg = suggest(ev.activity or '', limit=3, min_score=0.2,
                           organization_id=str(incident.organization_id))
            if sugg:
                ev.mitre_mappings = [
                    {'tactic': s.get('tactic'), 'technique': s.get('technique'),
                     'name': s.get('name'), 'score': s.get('score')} for s in sugg
                ]
                ev.mitre_tactic = ev.mitre_mappings[0].get('tactic')
                ev.mitre_technique = ev.mitre_mappings[0].get('technique')
                updated += 1
        db.session.commit()
        return {'status': 'success', 'message': f'Suggested MITRE mappings for {updated} events'}

    @staticmethod
    def _generate_summary(incident, config, user):
        """Generate an AI summary and persist it as a Report (downloadable /
        re-renderable from the Reports tab like any AI report)."""
        from app.services.ai_service import ai_service
        from app.models import TimelineEvent, CompromisedHost, Report
        org_id = str(incident.organization_id)
        providers = ai_service.get_available_providers(organization_id=org_id)
        if not providers:
            return {'status': 'skipped', 'message': 'No AI provider configured'}
        report_type = config.get('report_type', 'executive')
        if report_type not in Report.REPORT_TYPES:
            report_type = 'executive'
        events = [e.to_dict() for e in TimelineEvent.query.filter_by(incident_id=incident.id).limit(100).all()]
        hosts = [h.to_dict() for h in CompromisedHost.query.filter_by(incident_id=incident.id).limit(50).all()]
        markdown = ai_service.generate_report(
            report_type,
            incident.to_dict(), events,
            {'hosts': hosts, 'accounts': []},
            {'network': [], 'host': [], 'malware': []},
            provider=providers[0],
            organization_id=org_id,
        )
        if not markdown:
            return {'status': 'error', 'message': 'Summary generation returned nothing'}
        report = Report(
            incident_id=incident.id,
            title=f'Playbook {report_type} summary - #{incident.incident_number}',
            report_type=report_type,
            format='pdf',
            ai_summary=markdown,
            ai_provider=providers[0],
            sections=[],
            generated_by=user.id,
        )
        db.session.add(report)
        db.session.commit()
        return {'status': 'success', 'message': 'Summary generated and saved to Reports',
                'report_id': str(report.id), 'length': len(markdown)}

    @staticmethod
    def _create_task(incident, config, user):
        from app.models import Task
        if not user.has_permission('tasks:create'):
            return {'status': 'forbidden', 'message': 'tasks:create permission is required for this action'}
        title = config.get('title')
        if not isinstance(title, str) or not title.strip():
            return {'status': 'error', 'message': 'create_task requires a title'}
        priority = config.get('priority', 'medium')
        task_type = config.get('task_type', 'action_item')
        phase = config.get('phase')
        if priority not in Task.PRIORITIES or task_type not in Task.TASK_TYPES or (
                phase is not None and (isinstance(phase, bool) or not isinstance(phase, int) or not 1 <= phase <= 6)):
            return {'status': 'error', 'message': 'create_task has an invalid priority, task_type or phase'}
        task = Task(
            incident_id=incident.id,
            title=title.strip()[:500],
            description=config.get('description'),
            priority=priority,
            phase=phase,
            task_type=task_type,
            created_by=user.id,
        )
        db.session.add(task)
        db.session.commit()
        return {'status': 'success', 'message': f'Created task: {title}', 'task_id': str(task.id)}
