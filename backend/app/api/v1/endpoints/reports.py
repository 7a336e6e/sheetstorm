"""Report generation endpoints — AI-powered Markdown→PDF pipeline."""
import io
import re
import html as html_module
from datetime import datetime, timezone
from flask import jsonify, request, g, send_file, current_app
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp
from app import db
from app.models import Report, Incident, TimelineEvent, CompromisedHost, CompromisedAccount
from app.models import NetworkIndicator, HostBasedIndicator, MalwareTool
from app.middleware.rbac import require_incident_access, get_current_user
from app.middleware.audit import audit_log
from app.services.ai_service import ai_service


# ── Report type definitions ─────────────────────────────────────────────
REPORT_TYPES = {
    'executive': {
        'title': 'Executive Summary',
        'sections': ['summary', 'recommendations'],
    },
    'metrics': {
        'title': 'Incident Metrics',
        'sections': ['summary', 'timeline', 'iocs'],
    },
    'ioc': {
        'title': 'IOC Analysis',
        'sections': ['iocs'],
    },
    'trends': {
        'title': 'Trend Report',
        'sections': ['summary', 'timeline', 'iocs', 'recommendations'],
    },
}


@api_bp.route('/incidents/<uuid:incident_id>/reports', methods=['GET'])
@jwt_required()
@require_incident_access('reports:read')
def list_reports(incident_id):
    """List generated reports for an incident."""
    incident = g.incident

    reports = Report.query.filter_by(incident_id=incident.id).order_by(Report.created_at.desc()).all()

    return jsonify({
        'items': [r.to_dict() for r in reports]
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/reports/generate-pdf', methods=['POST'])
@jwt_required()
@require_incident_access('reports:generate')
@audit_log('data_modification', 'generate', 'report')
def generate_pdf_report(incident_id):
    """Generate an AI-powered PDF report for an incident.

    The AI generates Markdown content using a report-type-specific system prompt.
    That Markdown is then converted to styled HTML and rendered to PDF via WeasyPrint.
    Falls back to a basic data-only report if AI is not configured.
    """
    user = get_current_user()
    incident = g.incident
    data = request.get_json() or {}

    report_type = data.get('report_type', 'executive')
    if report_type not in REPORT_TYPES:
        report_type = 'executive'

    provider = data.get('provider')
    sections = data.get('sections', REPORT_TYPES[report_type]['sections'])
    report_title = REPORT_TYPES[report_type]['title']

    # Collect all incident data
    timeline_events = TimelineEvent.query.filter_by(
        incident_id=incident.id
    ).order_by(TimelineEvent.timestamp.asc()).all()
    hosts = CompromisedHost.query.filter_by(incident_id=incident.id).all()
    accounts = CompromisedAccount.query.filter_by(incident_id=incident.id).all()
    network_iocs = NetworkIndicator.query.filter_by(incident_id=incident.id).all()
    host_iocs = HostBasedIndicator.query.filter_by(incident_id=incident.id).all()
    malware = MalwareTool.query.filter_by(incident_id=incident.id).all()

    incident_data = incident.to_dict()
    timeline_data = [e.to_dict() for e in timeline_events]
    assets_data = {
        'hosts': [h.to_dict() for h in hosts],
        'accounts': [a.to_dict() for a in accounts],
    }
    iocs_data = {
        'network': [i.to_dict() for i in network_iocs],
        'host': [i.to_dict() for i in host_iocs],
        'malware': [m.to_dict() for m in malware],
    }

    # ── Step 1: Generate AI content ──────────────────────────────────
    ai_markdown = None
    ai_provider_used = None

    if ai_service.is_configured():
        used_provider = provider
        if not used_provider:
            providers = ai_service.get_available_providers()
            used_provider = providers[0] if providers else None

        if used_provider:
            ai_provider_used = used_provider
            ai_markdown = ai_service.generate_report(
                report_type=report_type,
                incident_data=incident_data,
                timeline_events=timeline_data,
                compromised_assets=assets_data,
                iocs=iocs_data,
                provider=used_provider,
            )

    # ── Step 2: Convert to HTML ──────────────────────────────────────
    if ai_markdown:
        html_content = _markdown_to_report_html(
            markdown_content=ai_markdown,
            incident=incident,
            report_title=report_title,
        )
    else:
        # Fallback: build a basic data-only report
        html_content = _build_fallback_report_html(
            incident=incident,
            timeline_events=timeline_events,
            hosts=hosts,
            accounts=accounts,
            network_iocs=network_iocs,
            host_iocs=host_iocs,
            malware=malware,
            sections=sections,
            report_title=report_title,
        )

    # ── Step 3: HTML → PDF via WeasyPrint ────────────────────────────
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
    except Exception as e:
        current_app.logger.error(f"PDF generation failed: {e}")
        return jsonify({
            'error': 'server_error',
            'message': f'PDF generation failed: {str(e)}'
        }), 500

    # ── Step 4: Save report record ───────────────────────────────────
    report = Report(
        incident_id=incident.id,
        title=f'{report_title} - #{incident.incident_number}',
        report_type=report_type,
        format='pdf',
        ai_summary=ai_markdown,
        ai_provider=ai_provider_used,
        sections=sections,
        generated_by=user.id,
    )
    db.session.add(report)
    db.session.commit()

    # ── Step 5: Return PDF ───────────────────────────────────────────
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'incident_{incident.incident_number}_{report_type}_report.pdf',
    )


@api_bp.route('/incidents/<uuid:incident_id>/reports/ai-generate', methods=['POST'])
@jwt_required()
@require_incident_access('reports:generate')
def generate_ai_summary(incident_id):
    """Generate an AI summary for an incident (returns JSON text, not PDF)."""
    incident = g.incident
    data = request.get_json() or {}

    if not ai_service.is_configured():
        return jsonify({'error': 'not_configured', 'message': 'AI service not configured'}), 501

    provider = data.get('provider')
    summary_type = data.get('summary_type', 'executive')

    # Collect data
    timeline_events = TimelineEvent.query.filter_by(incident_id=incident.id).all()
    hosts = CompromisedHost.query.filter_by(incident_id=incident.id).all()
    accounts = CompromisedAccount.query.filter_by(incident_id=incident.id).all()
    network_iocs = NetworkIndicator.query.filter_by(incident_id=incident.id).all()
    host_iocs = HostBasedIndicator.query.filter_by(incident_id=incident.id).all()
    malware = MalwareTool.query.filter_by(incident_id=incident.id).all()

    summary = ai_service.generate_summary_sync(
        incident_data=incident.to_dict(),
        timeline_events=[e.to_dict() for e in timeline_events],
        compromised_assets={
            'hosts': [h.to_dict() for h in hosts],
            'accounts': [a.to_dict() for a in accounts]
        },
        iocs={
            'network': [i.to_dict() for i in network_iocs],
            'host': [i.to_dict() for i in host_iocs],
            'malware': [m.to_dict() for m in malware]
        },
        summary_type=summary_type,
        provider=provider
    )

    if not summary:
        return jsonify({'error': 'server_error', 'message': 'AI generation failed'}), 500

    return jsonify({
        'summary': summary,
        'summary_type': summary_type,
        'provider': provider or ai_service.get_available_providers()[0]
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/reports/types', methods=['GET'])
@jwt_required()
@require_incident_access('reports:read')
def list_report_types(incident_id):
    """List available report types and AI configuration status."""
    ai_configured = ai_service.is_configured()
    providers = ai_service.get_available_providers() if ai_configured else []

    types = []
    for key, val in REPORT_TYPES.items():
        types.append({
            'id': key,
            'title': val['title'],
            'sections': val['sections'],
        })

    return jsonify({
        'report_types': types,
        'ai_configured': ai_configured,
        'ai_providers': providers,
    }), 200


@api_bp.route('/incidents/<uuid:incident_id>/reports/<uuid:report_id>/download', methods=['GET'])
@jwt_required()
@require_incident_access('reports:read')
def download_report(incident_id, report_id):
    """Download (re-generate) a previously generated report as PDF.

    Re-renders the stored ai_summary Markdown to PDF. If no ai_summary
    exists, rebuilds a basic data-only report.
    """
    incident = g.incident
    report = Report.query.filter_by(id=report_id, incident_id=incident.id).first()
    if not report:
        return jsonify({'error': 'not_found', 'message': 'Report not found'}), 404

    report_title = report.title
    report_type = report.report_type
    sections = report.sections or ['summary']

    if report.ai_summary:
        html_content = _markdown_to_report_html(
            markdown_content=report.ai_summary,
            incident=incident,
            report_title=report_title,
        )
    else:
        timeline_events = TimelineEvent.query.filter_by(incident_id=incident.id).order_by(TimelineEvent.timestamp.asc()).all()
        hosts = CompromisedHost.query.filter_by(incident_id=incident.id).all()
        accounts = CompromisedAccount.query.filter_by(incident_id=incident.id).all()
        network_iocs = NetworkIndicator.query.filter_by(incident_id=incident.id).all()
        host_iocs = HostBasedIndicator.query.filter_by(incident_id=incident.id).all()
        malware = MalwareTool.query.filter_by(incident_id=incident.id).all()
        html_content = _build_fallback_report_html(
            incident=incident,
            timeline_events=timeline_events,
            hosts=hosts,
            accounts=accounts,
            network_iocs=network_iocs,
            host_iocs=host_iocs,
            malware=malware,
            sections=sections,
            report_title=report_title,
        )

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
    except Exception as e:
        current_app.logger.error(f"PDF re-generation failed: {e}")
        return jsonify({'error': 'server_error', 'message': f'PDF generation failed: {str(e)}'}), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'incident_{incident.incident_number}_{report_type}_report.pdf',
    )


@api_bp.route('/incidents/<uuid:incident_id>/reports/<uuid:report_id>', methods=['DELETE'])
@jwt_required()
@require_incident_access('reports:generate')
@audit_log('data_modification', 'delete', 'report')
def delete_report(incident_id, report_id):
    """Delete a report record."""
    incident = g.incident
    report = Report.query.filter_by(id=report_id, incident_id=incident.id).first()
    if not report:
        return jsonify({'error': 'not_found', 'message': 'Report not found'}), 404

    db.session.delete(report)
    db.session.commit()

    return jsonify({'message': 'Report deleted'}), 200


# ── Markdown → HTML conversion ──────────────────────────────────────────

def _markdown_to_report_html(markdown_content: str, incident, report_title: str) -> str:
    """Convert AI-generated Markdown to a styled HTML document for PDF rendering.

    Uses a simple regex-based Markdown→HTML converter to avoid adding a dependency.
    Handles: headings, bold, italic, tables, bullet lists, code blocks.
    """
    body_html = _simple_markdown_to_html(markdown_content)

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{_get_report_css()}
</style>
</head>
<body>
<div class="report-header">
    <div class="report-brand">SheetStorm</div>
    <h1>{html_module.escape(report_title)}</h1>
    <div class="report-meta">
        <span>Incident #{incident.incident_number} — {html_module.escape(incident.title)}</span>
        <span>Severity: <strong class="severity-{incident.severity}">{incident.severity.upper()}</strong></span>
        <span>Status: <strong>{html_module.escape(incident.status)}</strong></span>
        <span>Phase: {html_module.escape(incident.phase_name)}</span>
    </div>
    <div class="report-meta" style="margin-top: 4px;">
        <span>Generated: {now}</span>
    </div>
</div>
<div class="report-body">
{body_html}
</div>
<div class="report-footer">
    <p>Generated by SheetStorm Incident Response Platform — {now}</p>
    <p>Classification: {html_module.escape(incident.classification or 'UNCLASSIFIED')}</p>
</div>
</body>
</html>'''


def _simple_markdown_to_html(md: str) -> str:
    """Convert Markdown text to HTML using regex. Handles the subset of Markdown
    that the AI reports use: headings, bold, italic, tables, lists, code blocks."""
    lines = md.split('\n')
    html_lines = []
    in_table = False
    in_list = False
    in_code_block = False
    table_header_done = False

    for line in lines:
        stripped = line.strip()

        # Code blocks
        if stripped.startswith('```'):
            if in_code_block:
                html_lines.append('</code></pre>')
                in_code_block = False
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                if in_table:
                    html_lines.append('</tbody></table>')
                    in_table = False
                    table_header_done = False
                lang = stripped[3:].strip()
                html_lines.append(f'<pre><code class="language-{lang}">' if lang else '<pre><code>')
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(html_module.escape(line))
            continue

        # Empty line
        if not stripped:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            if in_table:
                html_lines.append('</tbody></table>')
                in_table = False
                table_header_done = False
            continue

        # Table separator (---|---|---)
        if re.match(r'^\|?\s*[-:]+\s*(\|\s*[-:]+\s*)+\|?\s*$', stripped):
            table_header_done = True
            continue

        # Table rows
        if '|' in stripped and (stripped.startswith('|') or in_table):
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            if not in_table:
                html_lines.append('<table><thead><tr>')
                for cell in cells:
                    html_lines.append(f'<th>{_inline_md(cell)}</th>')
                html_lines.append('</tr></thead><tbody>')
                in_table = True
                continue
            elif not table_header_done:
                html_lines.append(f'<tr>')
                for cell in cells:
                    html_lines.append(f'<th>{_inline_md(cell)}</th>')
                html_lines.append('</tr>')
                continue
            else:
                html_lines.append('<tr>')
                for cell in cells:
                    html_lines.append(f'<td>{_inline_md(cell)}</td>')
                html_lines.append('</tr>')
                continue

        # Close table if we hit a non-table line
        if in_table:
            html_lines.append('</tbody></table>')
            in_table = False
            table_header_done = False

        # Headings
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            level = len(heading_match.group(1))
            text = _inline_md(heading_match.group(2))
            html_lines.append(f'<h{level}>{text}</h{level}>')
            continue

        # Bullet lists
        list_match = re.match(r'^[-*+]\s+(.+)$', stripped)
        if list_match:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(f'<li>{_inline_md(list_match.group(1))}</li>')
            continue

        # Numbered lists
        num_match = re.match(r'^\d+\.\s+(.+)$', stripped)
        if num_match:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(f'<li>{_inline_md(num_match.group(1))}</li>')
            continue

        # Close list if non-list line
        if in_list:
            html_lines.append('</ul>')
            in_list = False

        # Horizontal rule
        if re.match(r'^[-*_]{3,}$', stripped):
            html_lines.append('<hr/>')
            continue

        # Regular paragraph
        html_lines.append(f'<p>{_inline_md(stripped)}</p>')

    # Close any open elements
    if in_list:
        html_lines.append('</ul>')
    if in_table:
        html_lines.append('</tbody></table>')
    if in_code_block:
        html_lines.append('</code></pre>')

    return '\n'.join(html_lines)


def _inline_md(text: str) -> str:
    """Convert inline Markdown formatting to HTML (bold, italic, code, links)."""
    # Code spans
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Bold + italic
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


def _get_report_css() -> str:
    """Professional CSS for PDF reports."""
    return '''
    @page {
        margin: 2cm;
        @bottom-center { content: counter(page) " / " counter(pages); font-size: 9pt; color: #94a3b8; }
    }
    body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; font-size: 11pt; }
    .report-header { border-bottom: 3px solid #0ea5e9; padding-bottom: 20px; margin-bottom: 30px; }
    .report-brand { font-size: 10pt; font-weight: 700; color: #0ea5e9; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px; }
    .report-header h1 { font-size: 22pt; color: #0f172a; margin: 0 0 12px 0; font-weight: 700; }
    .report-meta { display: flex; flex-wrap: wrap; font-size: 9pt; color: #64748b; }
    .report-meta span { white-space: nowrap; margin-right: 8px; }
    .report-meta span:not(:last-child)::after { content: "  ·"; margin-left: 8px; color: #cbd5e1; }
    .report-body { }
    h1 { font-size: 18pt; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; margin-top: 28px; }
    h2 { font-size: 15pt; color: #1e293b; margin-top: 24px; }
    h3 { font-size: 12pt; color: #334155; margin-top: 18px; }
    h4 { font-size: 11pt; color: #475569; margin-top: 14px; }
    p { margin: 6px 0; }
    ul { margin: 6px 0; padding-left: 24px; }
    li { margin: 3px 0; }
    table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 9.5pt; }
    th, td { border: 1px solid #e2e8f0; padding: 7px 10px; text-align: left; }
    th { background-color: #f1f5f9; font-weight: 600; color: #334155; }
    tr:nth-child(even) td { background-color: #f8fafc; }
    code { background-color: #f1f5f9; padding: 1px 4px; border-radius: 3px; font-size: 9pt; font-family: "SF Mono", Monaco, "Cascadia Code", monospace; }
    pre { background-color: #f1f5f9; padding: 12px; border-radius: 6px; overflow-x: auto; }
    pre code { background: none; padding: 0; }
    hr { border: none; border-top: 1px solid #e2e8f0; margin: 20px 0; }
    strong { font-weight: 600; }
    .severity-critical { color: #dc2626; }
    .severity-high { color: #ea580c; }
    .severity-medium { color: #ca8a04; }
    .severity-low { color: #16a34a; }
    .report-footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 8.5pt; color: #94a3b8; }
'''


# ── Fallback report (no AI) ─────────────────────────────────────────────

def _build_fallback_report_html(
    incident, timeline_events, hosts, accounts, network_iocs,
    host_iocs, malware, sections, report_title
):
    """Build a basic data-only HTML report when AI is not available."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{_get_report_css()}</style></head>
<body>
<div class="report-header">
    <div class="report-brand">SheetStorm</div>
    <h1>{html_module.escape(report_title)}</h1>
    <div class="report-meta">
        <span>Incident #{incident.incident_number} — {html_module.escape(incident.title)}</span>
        <span>Severity: <strong class="severity-{incident.severity}">{incident.severity.upper()}</strong></span>
        <span>Status: <strong>{html_module.escape(incident.status)}</strong></span>
        <span>Phase: {html_module.escape(incident.phase_name)}</span>
    </div>
    <div class="report-meta" style="margin-top: 4px;">
        <span>Generated: {now}</span>
    </div>
</div>
<div class="report-body">
    <p><em>Note: AI-powered analysis is not configured. This is a data-only report. Configure an OpenAI or Google AI API key in Settings → Integrations to enable AI-generated reports.</em></p>
'''

    if 'summary' in sections:
        html += f'''
    <h2>Incident Summary</h2>
    <p>{html_module.escape(incident.description or 'No description provided.')}</p>
    <table>
        <tr><th>Classification</th><td>{html_module.escape(incident.classification or 'N/A')}</td></tr>
        <tr><th>Total Hosts</th><td>{len(hosts)}</td></tr>
        <tr><th>Total Accounts</th><td>{len(accounts)}</td></tr>
        <tr><th>Timeline Events</th><td>{len(timeline_events)}</td></tr>
        <tr><th>Network IOCs</th><td>{len(network_iocs)}</td></tr>
        <tr><th>Host IOCs</th><td>{len(host_iocs)}</td></tr>
        <tr><th>Malware/Tools</th><td>{len(malware)}</td></tr>
    </table>
'''

    if 'timeline' in sections and timeline_events:
        html += '<h2>Timeline of Events</h2><table><thead><tr><th>Timestamp</th><th>Host</th><th>Activity</th><th>MITRE</th></tr></thead><tbody>'
        for event in timeline_events:
            mitre = f'{event.mitre_tactic} — {event.mitre_technique}' if event.mitre_technique else ''
            html += f'<tr><td>{event.timestamp}</td><td>{html_module.escape(event.hostname or "N/A")}</td><td>{html_module.escape(event.activity)}</td><td>{html_module.escape(mitre)}</td></tr>'
        html += '</tbody></table>'

    if 'iocs' in sections:
        if hosts:
            html += '<h2>Compromised Hosts</h2><table><thead><tr><th>Hostname</th><th>IP</th><th>Type</th><th>Containment</th></tr></thead><tbody>'
            for h in hosts:
                html += f'<tr><td>{html_module.escape(h.hostname)}</td><td>{html_module.escape(h.ip_address or "N/A")}</td><td>{html_module.escape(h.system_type or "N/A")}</td><td>{html_module.escape(h.containment_status)}</td></tr>'
            html += '</tbody></table>'

        if network_iocs:
            html += '<h2>Network Indicators</h2><table><thead><tr><th>DNS/IP</th><th>Protocol</th><th>Port</th><th>Description</th></tr></thead><tbody>'
            for ioc in network_iocs:
                html += f'<tr><td>{html_module.escape(ioc.dns_ip)}</td><td>{html_module.escape(ioc.protocol or "N/A")}</td><td>{ioc.port or "N/A"}</td><td>{html_module.escape(ioc.description or "N/A")}</td></tr>'
            html += '</tbody></table>'

        if malware:
            html += '<h2>Malware & Tools</h2><table><thead><tr><th>File</th><th>SHA256</th><th>Host</th><th>Description</th></tr></thead><tbody>'
            for m in malware:
                sha = html_module.escape((m.sha256 or '')[:16] + '...' if m.sha256 else 'N/A')
                html += f'<tr><td>{html_module.escape(m.file_name)}</td><td>{sha}</td><td>{html_module.escape(m.host or "N/A")}</td><td>{html_module.escape(m.description or "N/A")}</td></tr>'
            html += '</tbody></table>'

    if 'recommendations' in sections and incident.lessons_learned:
        html += f'<h2>Lessons Learned & Recommendations</h2><p>{html_module.escape(incident.lessons_learned)}</p>'

    html += f'''
</div>
<div class="report-footer">
    <p>Generated by SheetStorm Incident Response Platform — {now}</p>
    <p>Classification: {html_module.escape(incident.classification or 'UNCLASSIFIED')}</p>
</div>
</body></html>'''

    return html
