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

MAX_PHASE_TASKS = 50
MAX_PHASE_ACTIONS = 20
MAX_TASK_TITLE = 500
MAX_ACTION_NAME = 255

# Scopes an auto/manual playbook action may change (refetched via resync).
ACTION_SCOPES = {'enrich_iocs': ['network_iocs'], 'generate_summary': ['incident'],
                 'suggest_mitre': ['timeline'], 'create_task': ['tasks']}


def validate_create_task_config(config):
    """Error message for a ``create_task`` action config, or None when valid.

    Used at save time (400 instead of a failed run later) and at run time.
    """
    from app.models import Task
    if not isinstance(config, dict):
        return 'create_task requires a config object with a title'
    title = config.get('title')
    if not isinstance(title, str) or not title.strip():
        return 'create_task requires a title'
    priority = config.get('priority', 'medium')
    task_type = config.get('task_type', 'action_item')
    phase = config.get('phase')
    if priority not in Task.PRIORITIES or task_type not in Task.TASK_TYPES or (
            phase is not None and (isinstance(phase, bool) or not isinstance(phase, int) or not 1 <= phase <= 6)):
        return 'create_task has an invalid priority, task_type or phase'
    return None


def validate_definition(definition):
    """Structurally validate a playbook definition -> ``(ok, message)``.

    Shared by the playbook endpoints, case-template playbooks and the built-in
    YAML loader, so a bad definition is a 400 (or a load-time error) instead
    of a 500 later. Caps: unique phase numbers, at most 50 tasks and 20
    actions per phase, task titles required (<= 500 chars), unique action
    keys, ``create_task`` configs valid.
    """
    from app.models import Playbook
    if definition is None:
        return True, None
    if not isinstance(definition, dict):
        return False, 'definition must be an object'
    phases = definition.get('phases', [])
    if not isinstance(phases, list):
        return False, 'definition.phases must be a list'
    if len(phases) > 6:
        return False, 'definition.phases may have at most 6 phases'
    action_keys, phase_numbers = set(), set()
    for i, ph in enumerate(phases):
        if not isinstance(ph, dict):
            return False, f'definition.phases[{i}] must be an object'
        phase_no = ph.get('phase')
        if isinstance(phase_no, bool) or not isinstance(phase_no, int) or not 1 <= phase_no <= 6:
            return False, f'definition.phases[{i}].phase must be an integer 1-6'
        if phase_no in phase_numbers:
            return False, f'definition.phases[{i}].phase {phase_no} is duplicated'
        phase_numbers.add(phase_no)
        if ph.get('name') is not None and not isinstance(ph.get('name'), str):
            return False, f'definition.phases[{i}].name must be a string'
        tasks = ph.get('tasks') or []
        if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
            return False, f'definition.phases[{i}].tasks must be a list of objects'
        if len(tasks) > MAX_PHASE_TASKS:
            return False, f'definition.phases[{i}].tasks may have at most {MAX_PHASE_TASKS} tasks'
        for k, task in enumerate(tasks):
            title = task.get('title')
            if not isinstance(title, str) or not title.strip() or len(title) > MAX_TASK_TITLE:
                return False, f'definition.phases[{i}].tasks[{k}].title must be a non-empty string of at most {MAX_TASK_TITLE} characters'
            if task.get('owner_role') is not None and (
                    not isinstance(task['owner_role'], str) or len(task['owner_role']) > 100):
                return False, f'definition.phases[{i}].tasks[{k}].owner_role must be a string of at most 100 characters'
        actions = ph.get('actions') or []
        if not isinstance(actions, list):
            return False, f'definition.phases[{i}].actions must be a list'
        if len(actions) > MAX_PHASE_ACTIONS:
            return False, f'definition.phases[{i}].actions may have at most {MAX_PHASE_ACTIONS} actions'
        for j, act in enumerate(actions):
            where = f'definition.phases[{i}].actions[{j}]'
            if not isinstance(act, dict):
                return False, f'{where} must be an object'
            if act.get('type') not in Playbook.ACTION_TYPES:
                return False, f"{where}: invalid action type {act.get('type')!r}. Allowed: {Playbook.ACTION_TYPES}"
            key = act.get('key')
            if not isinstance(key, str) or not key.strip():
                return False, f'{where}.key must be a non-empty string'
            if key in action_keys:
                return False, f'{where}.key {key!r} is duplicated'
            action_keys.add(key)
            if act.get('name') is not None and (not isinstance(act['name'], str) or len(act['name']) > MAX_ACTION_NAME):
                return False, f'{where}.name must be a string of at most {MAX_ACTION_NAME} characters'
            if act.get('config') is not None and not isinstance(act['config'], dict):
                return False, f'{where}.config must be an object'
            if 'auto_run' in act and not isinstance(act['auto_run'], bool):
                return False, f'{where}.auto_run must be a boolean'
            if act['type'] == 'create_task':
                problem = validate_create_task_config(act.get('config'))
                if problem:
                    return False, f'{where}: {problem}'
    return True, None


class PlaybookService:

    # -- activation ---------------------------------------------------------

    @staticmethod
    def phase_actions(definition, phase):
        for ph in (definition or {}).get('phases', []):
            if ph.get('phase') == phase:
                return ph.get('actions') or []
        return []

    @staticmethod
    def record_run(inst, action, result):
        state = dict(inst.state or {})
        runs = list(state.get('action_runs', []))
        runs.append({
            'key': action.get('key'), 'type': action.get('type'), 'name': action.get('name'),
            'result': result, 'run_at': datetime.now(timezone.utc).isoformat(),
        })
        state['action_runs'] = runs
        inst.state = state

    @staticmethod
    def run_auto_actions(inst, incident, phase, user):
        """Run the phase's ``auto_run`` actions (one commit per action so a
        failing action, which rolls the session back, cannot discard earlier
        run records) and ask clients to refetch what they changed."""
        from app.services import realtime
        runs = []
        for act in PlaybookService.phase_actions(inst.definition, phase):
            if act.get('auto_run'):
                result = PlaybookService.execute_action(incident, act, user)
                PlaybookService.record_run(inst, act, result)
                db.session.commit()
                runs.append({'key': act.get('key'), 'type': act.get('type'), 'result': result})
        scopes = [s for r in runs for s in ACTION_SCOPES.get(r['type'], [])]
        if scopes:
            realtime.emit_resync(incident.id, scopes, 'playbook_action')
        return runs

    @staticmethod
    def build_instance(incident, *, name, definition, user, playbook_id=None, builtin_key=None):
        """Add (not commit) an IncidentPlaybook snapshotting ``definition``,
        starting at the incident's current phase."""
        from app.models import IncidentPlaybook
        inst = IncidentPlaybook(
            incident_id=incident.id,
            playbook_id=playbook_id,
            builtin_key=builtin_key,
            name=name,
            definition=definition or {},
            current_phase=incident.phase or 1,
            state={'tasks': {}, 'action_runs': []},
            activated_at=datetime.now(timezone.utc),
            created_by=user.id,
        )
        db.session.add(inst)
        return inst

    @staticmethod
    def activate(incident, *, name, definition, user, playbook_id=None, builtin_key=None, run_auto=True):
        """Activate a playbook on an incident: ``(instance, auto_runs)``.

        Commits. The caller emits the realtime ``playbook`` change.
        """
        inst = PlaybookService.build_instance(incident, name=name, definition=definition, user=user,
                                              playbook_id=playbook_id, builtin_key=builtin_key)
        db.session.commit()
        runs = PlaybookService.run_auto_actions(inst, incident, inst.current_phase, user) if run_auto else []
        return inst, runs

    # -- actions ------------------------------------------------------------

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
        from app.services.egress_policy import enrichment_allowed, filter_values_for_enrichment
        from app.models import NetworkIndicator
        if not enrichment_allowed(incident):
            return {'status': 'skipped', 'code': 'tlp_restricted',
                    'message': f'Enrichment is not allowed for TLP:{incident.tlp.upper()} incidents'}
        iocs = NetworkIndicator.query.filter_by(incident_id=incident.id).all()
        _, blocked = filter_values_for_enrichment(
            incident.organization_id, [(i.dns_ip or '').strip() for i in iocs])
        blocked = {b.lower() for b in blocked}
        enriched = 0
        for ioc in iocs:
            val = (ioc.dns_ip or '').strip()
            if not val or val.lower() in blocked:
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
        from app.services.ai_service import ai_service, AIBlockedByTLP
        from app.models import TimelineEvent, CompromisedHost, Report
        org_id = str(incident.organization_id)
        # Automatic path: only a provider the org's AI TLP policy allows; if
        # none is, skip (the refusal is recorded as a security event).
        try:
            provider = ai_service.select_provider(org_id, None, incident_tlp=incident.tlp,
                                                  feature='playbook_summary', incident_id=incident.id)
        except AIBlockedByTLP as e:
            return {'status': 'skipped', 'code': e.code, 'message': e.message}
        if not provider:
            return {'status': 'skipped', 'message': 'No AI provider configured'}
        report_type = config.get('report_type', 'executive')
        if report_type not in Report.REPORT_TYPES:
            report_type = 'executive'
        events = [e.to_dict() for e in TimelineEvent.query.filter_by(incident_id=incident.id).limit(100).all()]
        hosts = [h.to_dict() for h in CompromisedHost.query.filter_by(incident_id=incident.id).limit(50).all()]
        try:
            markdown = ai_service.generate_report(
                report_type,
                incident.to_dict(), events,
                {'hosts': hosts, 'accounts': []},
                {'network': [], 'host': [], 'malware': []},
                provider=provider,
                organization_id=org_id,
                incident_tlp=incident.tlp,
                incident_id=incident.id,
                feature='playbook_summary',
            )
        except AIBlockedByTLP as e:
            return {'status': 'skipped', 'code': e.code, 'message': e.message}
        if not markdown:
            return {'status': 'error', 'message': 'Summary generation returned nothing'}
        report = Report(
            incident_id=incident.id,
            title=f'Playbook {report_type} summary - #{incident.incident_number}',
            report_type=report_type,
            format='pdf',
            ai_summary=markdown,
            ai_provider=provider,
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
        problem = validate_create_task_config(config)
        if problem:
            return {'status': 'error', 'message': problem}
        title = config['title']
        task = Task(
            incident_id=incident.id,
            title=title.strip()[:500],
            description=config.get('description'),
            priority=config.get('priority', 'medium'),
            phase=config.get('phase'),
            task_type=config.get('task_type', 'action_item'),
            created_by=user.id,
        )
        db.session.add(task)
        db.session.commit()
        return {'status': 'success', 'message': f'Created task: {title}', 'task_id': str(task.id)}
