"""Table-driven contract test: every registered tool hits the backend route,
HTTP method and payload that the backend (backend/app/api/v1/endpoints) expects."""

from __future__ import annotations

import asyncio
import importlib

import pytest
from conftest import PKG

I = "inc-1"  # noqa: E741

# tool name -> (kwargs, method, path, json subset | None, query-param subset | None)
CASES: dict[str, tuple] = {
    # auth
    "sheetstorm_get_current_user": ({}, "GET", "/auth/me", None, None),
    "sheetstorm_logout": ({}, "POST", "/auth/logout", None, None),
    # incidents
    "sheetstorm_list_incidents": ({"status": "open", "q": "x", "sort": "-severity", "per_page": 500}, "GET",
                                  "/incidents", None,
                                  {"status": "open", "q": "x", "sort": "-severity", "per_page": "200"}),
    "sheetstorm_get_incident": ({"incident_id": I}, "GET", f"/incidents/{I}", None, None),
    "sheetstorm_create_incident": ({"title": "T", "description": "D", "detected_at": "2026-01-01T00:00:00Z",
                                    "lead_responder_id": "u1"}, "POST", "/incidents",
                                   {"title": "T", "description": "D", "severity": "medium",
                                    "detected_at": "2026-01-01T00:00:00Z", "lead_responder_id": "u1"}, None),
    "sheetstorm_update_incident": ({"incident_id": I, "title": "N", "contained_at": "2026-01-02T00:00:00Z",
                                    "lead_responder_id": "u2", "expected_version": 3}, "PUT", f"/incidents/{I}",
                                   {"title": "N", "contained_at": "2026-01-02T00:00:00Z", "lead_responder_id": "u2",
                                    "expected_version": 3}, None),
    "sheetstorm_get_dashboard_stats": ({}, "GET", "/dashboard/stats", None, None),
    "sheetstorm_update_incident_status": ({"incident_id": I, "status": "contained"}, "PATCH",
                                          f"/incidents/{I}/status", {"status": "contained"}, None),
    "sheetstorm_archive_incident": ({"incident_id": I}, "POST", f"/incidents/{I}/archive", None, None),
    "sheetstorm_unarchive_incident": ({"incident_id": I}, "POST", f"/incidents/{I}/unarchive", None, None),
    "sheetstorm_list_archived_incidents": ({"search": "x", "sort": "title"}, "GET", "/incidents/archived", None,
                                           {"search": "x", "sort": "title"}),
    "sheetstorm_permanently_delete_incident": ({"incident_id": I, "confirmation": "DELETE PERMANENTLY"},
                                               "DELETE", f"/incidents/{I}/permanent", None, None),
    # assignments
    "sheetstorm_list_assignments": ({"incident_id": I}, "GET", f"/incidents/{I}/assignments", None, None),
    "sheetstorm_assign_user": ({"incident_id": I, "user_id": "u1", "role": "Analyst"}, "POST",
                               f"/incidents/{I}/assignments", {"user_id": "u1", "role": "Analyst"}, None),
    "sheetstorm_remove_assignment": ({"incident_id": I, "assignment_id": "a1"}, "DELETE",
                                     f"/incidents/{I}/assignments/a1", None, None),
    # timeline
    "sheetstorm_list_timeline_events": ({"incident_id": I, "phase": 2}, "GET", f"/incidents/{I}/timeline",
                                        None, {"phase": "2"}),
    "sheetstorm_create_timeline_event": (
        {"incident_id": I, "timestamp": "2026-01-01T00:00:00Z", "activity": "x",
         "detection_time": "2026-01-02T00:00:00Z", "confidence_level": "high"},
        "POST", f"/incidents/{I}/timeline",
        {"activity": "x", "detection_time": "2026-01-02T00:00:00Z", "confidence_level": "high"}, None),
    "sheetstorm_update_timeline_event": ({"incident_id": I, "event_id": "e1", "confidence_level": "low"},
                                         "PUT", f"/incidents/{I}/timeline/e1", {"confidence_level": "low"}, None),
    "sheetstorm_delete_timeline_event": ({"incident_id": I, "event_id": "e1"}, "DELETE",
                                         f"/incidents/{I}/timeline/e1", None, None),
    "sheetstorm_mark_timeline_event_as_ioc": ({"incident_id": I, "event_id": "e1", "artifact_type": "process"},
                                              "POST", f"/incidents/{I}/timeline/e1/mark-as-ioc",
                                              {"artifact_type": "process", "is_malicious": True}, None),
    "sheetstorm_list_timeline_mitre_tactics": ({}, "GET", "/mitre/tactics", None, None),
    "sheetstorm_list_timeline_mitre_techniques": ({"tactic": "execution"}, "GET", "/mitre/techniques",
                                                  None, {"tactic": "execution"}),
    # tasks
    "sheetstorm_list_tasks": ({"incident_id": I, "status": "pending", "task_type": "investigative_lead",
                               "lead_outcome": "open"}, "GET", f"/incidents/{I}/tasks",
                              None, {"status": "pending", "task_type": "investigative_lead", "lead_outcome": "open"}),
    "sheetstorm_list_leads": ({"incident_id": I}, "GET", f"/incidents/{I}/tasks", None,
                              {"task_type": "investigative_lead", "lead_outcome": "open", "lead_counts": "true",
                               "include_comments": "false"}),
    "sheetstorm_create_task": (
        {"incident_id": I, "title": "Lead", "task_type": "investigative_lead",
         "investigation_direction": "check RDP", "evidence_refs": '[{"evidence_type": "artifact", "evidence_id": "a1"}]'},
        "POST", f"/incidents/{I}/tasks",
        {"title": "Lead", "task_type": "investigative_lead", "investigation_direction": "check RDP",
         "evidence_refs": [{"evidence_type": "artifact", "evidence_id": "a1"}]}, None),
    "sheetstorm_update_task": ({"incident_id": I, "task_id": "t1", "lead_outcome": "false_positive"}, "PUT",
                               f"/incidents/{I}/tasks/t1", {"lead_outcome": "false_positive"}, None),
    "sheetstorm_delete_task": ({"incident_id": I, "task_id": "t1"}, "DELETE", f"/incidents/{I}/tasks/t1", None, None),
    "sheetstorm_add_task_comment": ({"incident_id": I, "task_id": "t1", "content": "c"}, "POST",
                                    f"/incidents/{I}/tasks/t1/comments", {"content": "c"}, None),
    "sheetstorm_list_task_comments": ({"incident_id": I, "task_id": "t1"}, "GET",
                                      f"/incidents/{I}/tasks/t1/comments", None, None),
    # hosts & accounts
    "sheetstorm_list_hosts": ({"incident_id": I, "triage_status": "suspicious", "acquisition": "!disk_imaged"},
                              "GET", f"/incidents/{I}/hosts", None,
                              {"triage_status": "suspicious", "acquisition": "!disk_imaged"}),
    "sheetstorm_bulk_update_hosts": ({"incident_id": I, "host_ids": ["h1", "h2"], "triage_status": "clean"},
                                     "PATCH", f"/incidents/{I}/hosts/bulk",
                                     {"host_ids": ["h1", "h2"], "triage_status": "clean"}, None),
    "sheetstorm_add_host": ({"incident_id": I, "hostname": "WS1", "triage_status": "suspicious",
                             "memory_captured": True}, "POST", f"/incidents/{I}/hosts",
                            {"hostname": "WS1", "triage_status": "suspicious",
                             "acquisition_status": {"memory_captured": True}}, None),
    "sheetstorm_update_host": ({"incident_id": I, "host_id": "h1", "triage_status": "clean"}, "PUT",
                               f"/incidents/{I}/hosts/h1", {"triage_status": "clean"}, None),
    "sheetstorm_delete_host": ({"incident_id": I, "host_id": "h1"}, "DELETE", f"/incidents/{I}/hosts/h1", None, None),
    "sheetstorm_list_accounts": ({"incident_id": I}, "GET", f"/incidents/{I}/accounts", None, None),
    "sheetstorm_add_account": ({"incident_id": I, "account_name": "bob"}, "POST", f"/incidents/{I}/accounts",
                               {"account_name": "bob"}, None),
    "sheetstorm_update_account": ({"incident_id": I, "account_id": "ac1", "status": "reset"}, "PUT",
                                  f"/incidents/{I}/accounts/ac1", {"status": "reset"}, None),
    "sheetstorm_delete_account": ({"incident_id": I, "account_id": "ac1"}, "DELETE",
                                  f"/incidents/{I}/accounts/ac1", None, None),
    "sheetstorm_reveal_account_password": ({"incident_id": I, "account_id": "ac1"}, "GET",
                                           f"/incidents/{I}/accounts/ac1", None, {"reveal": "true"}),
    # IOCs
    "sheetstorm_list_network_iocs": ({"incident_id": I}, "GET", f"/incidents/{I}/network-iocs", None, None),
    "sheetstorm_add_network_ioc": ({"incident_id": I, "dns_ip": "1.2.3.4"}, "POST", f"/incidents/{I}/network-iocs",
                                   {"dns_ip": "1.2.3.4"}, None),
    "sheetstorm_update_network_ioc": ({"incident_id": I, "ioc_id": "n1", "port": 443}, "PUT",
                                      f"/incidents/{I}/network-iocs/n1", {"port": 443}, None),
    "sheetstorm_delete_network_ioc": ({"incident_id": I, "ioc_id": "n1"}, "DELETE",
                                      f"/incidents/{I}/network-iocs/n1", None, None),
    "sheetstorm_list_host_iocs": ({"incident_id": I}, "GET", f"/incidents/{I}/host-iocs", None, None),
    "sheetstorm_add_host_ioc": ({"incident_id": I, "artifact_type": "file", "artifact_value": "x.exe"}, "POST",
                                f"/incidents/{I}/host-iocs", {"artifact_type": "file", "artifact_value": "x.exe"}, None),
    "sheetstorm_update_host_ioc": ({"incident_id": I, "ioc_id": "h1", "notes": "n"}, "PUT",
                                   f"/incidents/{I}/host-iocs/h1", {"notes": "n"}, None),
    "sheetstorm_delete_host_ioc": ({"incident_id": I, "ioc_id": "h1"}, "DELETE", f"/incidents/{I}/host-iocs/h1",
                                   None, None),
    "sheetstorm_list_malware": ({"incident_id": I}, "GET", f"/incidents/{I}/malware", None, None),
    "sheetstorm_add_malware": ({"incident_id": I, "file_name": "m.exe"}, "POST", f"/incidents/{I}/malware",
                               {"file_name": "m.exe"}, None),
    "sheetstorm_update_malware": ({"incident_id": I, "malware_id": "m1", "md5": "abc"}, "PUT",
                                  f"/incidents/{I}/malware/m1", {"md5": "abc"}, None),
    "sheetstorm_delete_malware": ({"incident_id": I, "malware_id": "m1"}, "DELETE", f"/incidents/{I}/malware/m1",
                                  None, None),
    # artifacts
    "sheetstorm_list_artifacts": ({"incident_id": I}, "GET", f"/incidents/{I}/artifacts", None, None),
    "sheetstorm_upload_artifact": ({"incident_id": I, "file_path": "@FILE@", "description": "mem"}, "POST",
                                   f"/incidents/{I}/artifacts", None, None),
    "sheetstorm_verify_artifact": ({"incident_id": I, "artifact_id": "a1"}, "POST",
                                   f"/incidents/{I}/artifacts/a1/verify", None, None),
    "sheetstorm_get_chain_of_custody": ({"incident_id": I, "artifact_id": "a1"}, "GET",
                                        f"/incidents/{I}/artifacts/a1/custody", None, None),
    "sheetstorm_set_legal_hold": ({"incident_id": I, "artifact_id": "a1", "reason": "lit"}, "POST",
                                  f"/incidents/{I}/artifacts/a1/legal-hold", {"hold": True, "reason": "lit"}, None),
    "sheetstorm_export_custody": ({"incident_id": I, "artifact_id": "a1"}, "GET",
                                  f"/incidents/{I}/artifacts/a1/custody/export", None, {"format": "json"}),
    "sheetstorm_download_artifact": ({"incident_id": I, "artifact_id": "a1"}, "GET",
                                     f"/incidents/{I}/artifacts/a1/download", None, None),
    # evidence register / custody ledger
    "sheetstorm_list_evidence": ({"incident_id": I, "custody_state": "checked_out", "search": "EV-0007",
                                  "per_page": 500}, "GET", f"/incidents/{I}/evidence", None,
                                 {"custody_state": "checked_out", "q": "EV-0007", "per_page": "200"}),
    "sheetstorm_get_evidence": ({"incident_id": I, "evidence_id": "e1"}, "GET", f"/incidents/{I}/evidence/e1",
                                None, None),
    "sheetstorm_register_evidence": (
        {"incident_id": I, "title": "SSD", "evidence_type": "disk_image", "seal_number": "S-1",
         "hashes_json": '[{"algorithm": "sha256", "value": "ab", "source": "tool_reported"}]'},
        "POST", f"/incidents/{I}/evidence",
        {"title": "SSD", "evidence_type": "disk_image", "seal_number": "S-1",
         "acquisition_hashes": [{"algorithm": "sha256", "value": "ab", "source": "tool_reported"}]}, None),
    "sheetstorm_transfer_evidence": (
        {"incident_id": I, "evidence_id": "e1", "mode": "transfer", "reason": "lab", "to_party_id": "p1",
         "transfer_method": "courier", "attested": True},
        "POST", f"/incidents/{I}/evidence/e1/custody/transfer",
        {"reason": "lab", "to_party_id": "p1", "transfer_method": "courier"}, None),
    "sheetstorm_verify_evidence_chain": ({"incident_id": I}, "GET", f"/incidents/{I}/evidence/custody/verify",
                                         None, None),
    # attack graph
    "sheetstorm_get_attack_graph": ({"incident_id": I}, "GET", f"/incidents/{I}/attack-graph", None, None),
    "sheetstorm_auto_generate_graph": ({"incident_id": I}, "POST", f"/incidents/{I}/attack-graph/auto-generate",
                                       None, None),
    "sheetstorm_add_graph_node": ({"incident_id": I, "label": "DC", "node_type": "domain_controller",
                                   "metadata": '{"k": 1}'}, "POST", f"/incidents/{I}/attack-graph/nodes",
                                  {"label": "DC", "node_type": "domain_controller", "extra_data": {"k": 1}}, None),
    "sheetstorm_update_graph_node": ({"incident_id": I, "node_id": "n1", "label": "X"}, "PUT",
                                     f"/incidents/{I}/attack-graph/nodes/n1", {"label": "X"}, None),
    "sheetstorm_delete_graph_node": ({"incident_id": I, "node_id": "n1"}, "DELETE",
                                     f"/incidents/{I}/attack-graph/nodes/n1", None, None),
    "sheetstorm_add_graph_edge": ({"incident_id": I, "source_node_id": "a", "target_node_id": "b",
                                   "edge_type": "lateral_movement", "mitre_technique": "T1021"}, "POST",
                                  f"/incidents/{I}/attack-graph/edges",
                                  {"source_node_id": "a", "edge_type": "lateral_movement",
                                   "mitre_technique": "T1021"}, None),
    "sheetstorm_update_graph_edge": ({"incident_id": I, "edge_id": "e1", "label": "RDP"}, "PUT",
                                     f"/incidents/{I}/attack-graph/edges/e1", {"label": "RDP"}, None),
    "sheetstorm_delete_graph_edge": ({"incident_id": I, "edge_id": "e1"}, "DELETE",
                                     f"/incidents/{I}/attack-graph/edges/e1", None, None),
    "sheetstorm_get_node_types": ({}, "GET", "/attack-graph/node-types", None, None),
    "sheetstorm_get_edge_types": ({}, "GET", "/attack-graph/edge-types", None, None),
    # case notes
    "sheetstorm_list_case_notes": ({"incident_id": I, "category": "finding"}, "GET",
                                   f"/incidents/{I}/case-notes", None, {"category": "finding"}),
    "sheetstorm_get_case_note": ({"incident_id": I, "note_id": "c1"}, "GET", f"/incidents/{I}/case-notes/c1",
                                 None, None),
    "sheetstorm_create_case_note": ({"incident_id": I, "title": "t", "content": "c", "category": "hypothesis"},
                                    "POST", f"/incidents/{I}/case-notes",
                                    {"title": "t", "content": "c", "category": "hypothesis"}, None),
    "sheetstorm_update_case_note": ({"incident_id": I, "note_id": "c1", "title": "t2"}, "PUT",
                                    f"/incidents/{I}/case-notes/c1", {"title": "t2"}, None),
    "sheetstorm_delete_case_note": ({"incident_id": I, "note_id": "c1"}, "DELETE",
                                    f"/incidents/{I}/case-notes/c1", None, None),
    # playbooks
    "sheetstorm_list_playbook_templates": ({}, "GET", "/playbooks", None, None),
    "sheetstorm_get_playbook_template": ({"playbook_id": "p1"}, "GET", "/playbooks/p1", None, None),
    "sheetstorm_activate_playbook": ({"incident_id": I, "playbook_id": "p1"}, "POST",
                                     f"/incidents/{I}/playbooks/p1/activate", None, None),
    "sheetstorm_get_incident_playbook": ({"incident_id": I}, "GET", f"/incidents/{I}/playbook", None, None),
    "sheetstorm_advance_playbook_phase": ({"incident_id": I}, "PUT", f"/incidents/{I}/playbook/advance", None, None),
    "sheetstorm_execute_playbook_action": ({"incident_id": I, "action_key": "a1"}, "POST",
                                           f"/incidents/{I}/playbook/execute", {"action_key": "a1"}, None),
    "sheetstorm_toggle_playbook_task": ({"incident_id": I, "task_key": "2:0", "done": False}, "PUT",
                                        f"/incidents/{I}/playbook/task", {"task_key": "2:0", "done": False}, None),
    # reports
    "sheetstorm_list_reports": ({"incident_id": I}, "GET", f"/incidents/{I}/reports", None, None),
    "sheetstorm_generate_pdf_report": ({"incident_id": I, "report_type": "ioc"}, "POST",
                                       f"/incidents/{I}/reports/generate-pdf", {"report_type": "ioc"}, None),
    "sheetstorm_generate_ai_report": ({"incident_id": I, "summary_type": "technical"}, "POST",
                                      f"/incidents/{I}/reports/ai-generate", {"summary_type": "technical"}, None),
    # admin
    "sheetstorm_list_users": ({"search": "ann", "status": "locked", "role": "admin"}, "GET", "/users", None,
                              {"q": "ann", "status": "locked", "role": "Administrator"}),
    "sheetstorm_create_user": ({"email": "a@b.c", "name": "A", "password": "pw", "role": "incident responder"},
                               "POST", "/users", {"roles": ["Incident Responder"]}, None),
    "sheetstorm_update_user": ({"user_id": "u1", "is_active": False}, "PUT", "/users/u1", {"is_active": False}, None),
    "sheetstorm_delete_user": ({"user_id": "u1"}, "DELETE", "/users/u1", None, None),
    "sheetstorm_invite_user": ({"email": "a@b.c", "expires_in_days": 3}, "POST", "/users/invites",
                               {"email": "a@b.c", "expires_in_days": 3}, None),
    "sheetstorm_list_invites": ({}, "GET", "/users/invites", None, {"status": "pending"}),
    "sheetstorm_revoke_invite": ({"invite_id": "i1"}, "DELETE", "/users/invites/i1", None, None),
    "sheetstorm_disable_user": ({"user_id": "u1", "reason": "r"}, "POST", "/users/u1/disable", {"reason": "r"},
                                None),
    "sheetstorm_enable_user": ({"user_id": "u1"}, "POST", "/users/u1/enable", None, None),
    "sheetstorm_force_logout_user": ({"user_id": "u1"}, "POST", "/users/u1/force-logout", None, None),
    "sheetstorm_unlock_user": ({"user_id": "u1"}, "POST", "/users/u1/unlock", None, None),
    "sheetstorm_get_user_activity": ({"user_id": "u1"}, "GET", "/users/u1/activity", None, {"scope": "all"}),
    "sheetstorm_list_roles": ({}, "GET", "/roles", None, None),
    "sheetstorm_list_permissions": ({}, "GET", "/permissions", None, None),
    "sheetstorm_list_notifications": ({"unread_only": True}, "GET", "/notifications", None, {"unread_only": "true"}),
    "sheetstorm_mark_notification_read": ({"notification_id": "n1"}, "POST", "/notifications/n1/read", None, None),
    "sheetstorm_mark_all_notifications_read": ({}, "POST", "/notifications/read-all", None, None),
    "sheetstorm_get_audit_logs": ({"action": "login", "event_type": "authentication", "status": "denied",
                                   "ip": "10.0.0.0/8", "sort": "-created_at", "per_page": 500},
                                  "GET", "/audit-logs", None,
                                  {"action_contains": "login", "event_type": "authentication", "status": "denied",
                                   "ip": "10.0.0.0/8", "sort": "-created_at", "per_page": "200"}),
    "sheetstorm_get_system_status": ({}, "GET", "/admin/system-status", None, None),
    "sheetstorm_get_security_policy": ({}, "GET", "/organization/security-policy", None, None),
    "sheetstorm_health_check": ({}, "GET", "/health", None, None),
    # threat intel
    "sheetstorm_virustotal_lookup": ({"lookup_type": "hash", "value": "abc"}, "POST",
                                     "/threat-intel/virustotal/lookup", {"type": "hash", "value": "abc"}, None),
    "sheetstorm_misp_push_iocs": ({"incident_id": I, "iocs": [{"type": "ip-dst", "value": "1.2.3.4"}]}, "POST",
                                  "/threat-intel/misp/push", {"incident_id": I}, None),
    "sheetstorm_cve_lookup": ({"cve_id": "CVE-2024-1"}, "POST", "/threat-intel/cve/lookup",
                              {"cve_id": "CVE-2024-1"}, None),
    "sheetstorm_ip_reputation": ({"ip": "1.2.3.4"}, "POST", "/threat-intel/ip/lookup", {"ip": "1.2.3.4"}, None),
    "sheetstorm_domain_reputation": ({"domain": "e.com"}, "POST", "/threat-intel/domain/lookup",
                                     {"domain": "e.com"}, None),
    "sheetstorm_email_reputation": ({"email": "a@e.com"}, "POST", "/threat-intel/email/lookup",
                                    {"email": "a@e.com"}, None),
    "sheetstorm_ransomware_lookup": ({"query": "lockbit"}, "POST", "/threat-intel/ransomware/lookup",
                                     {"query": "lockbit"}, None),
    # knowledge base
    "sheetstorm_kb_lolbas": ({"search": "certutil"}, "GET", "/knowledge-base/lolbas", None, {"search": "certutil"}),
    "sheetstorm_kb_event_ids": ({"search": "4624"}, "GET", "/knowledge-base/event-ids", None, {"search": "4624"}),
    "sheetstorm_kb_d3fend": ({"attack_id": "T1059"}, "GET", "/knowledge-base/d3fend", None, {"attack_id": "T1059"}),
    "sheetstorm_kb_d3fend_suggest": ({"attack_techniques": ["T1059"]}, "POST", "/knowledge-base/d3fend/suggest",
                                     {"attack_techniques": ["T1059"]}, None),
    "sheetstorm_get_mitre_tactics": ({}, "GET", "/knowledge-base/mitre-attack/tactics", None, None),
    "sheetstorm_get_mitre_techniques": ({"search": "rdp"}, "GET", "/knowledge-base/mitre-attack", None,
                                        {"search": "rdp"}),
    # advanced
    "sheetstorm_search": ({"query": "evil", "incident_id": I, "sort": "-timestamp", "since": "2026-01-01",
                           "per_page": 500}, "GET", "/search", None,
                          {"q": "evil", "incident_id": I, "sort": "-timestamp", "since": "2026-01-01",
                           "per_page": "50"}),
    "sheetstorm_correlate_iocs": ({"ioc_values": "1.2.3.4"}, "POST", "/correlate-iocs",
                                  {"ioc_values": ["1.2.3.4"]}, None),
    "sheetstorm_export_stix": ({"incident_id": I}, "GET", f"/incidents/{I}/export/stix", None, None),
    "sheetstorm_bulk_enrich": ({"ioc_values": "ip:1.2.3.4"}, "POST", "/bulk-enrich",
                               {"ioc_values": [{"type": "ip", "value": "1.2.3.4"}]}, None),
    # defang
    "sheetstorm_defang_iocs": ({"values": ["evil.com"]}, "POST", "/tools/defang", {"values": ["evil.com"]}, None),
    "sheetstorm_refang_iocs": ({"text": "evil[.]com"}, "POST", "/tools/refang", {"text": "evil[.]com"}, None),
}


def _registered_tools(pkg) -> set[str]:
    return {t.name for t in asyncio.run(pkg.mcp.list_tools())}


def test_every_registered_tool_has_a_contract_case(pkg):
    registered = _registered_tools(pkg)
    assert registered == set(CASES), (
        f"missing cases: {sorted(registered - set(CASES))}; stale cases: {sorted(set(CASES) - registered)}"
    )


def test_tool_names_are_unique(pkg):
    names = [t.name for t in asyncio.run(pkg.mcp.list_tools())]
    assert len(names) == len(set(names))


def _tool_fn(name: str):
    for mod in ("auth", "incidents", "assignments", "timeline", "tasks", "assets", "iocs", "artifacts",
                "attack_graph", "case_notes", "playbooks", "reports", "admin", "threat_intel",
                "knowledge_base", "advanced_analysis", "defang", "evidence"):
        m = importlib.import_module(f"{PKG}.tools.{mod}")
        if hasattr(m, name):
            return getattr(m, name)
    raise LookupError(name)


@pytest.mark.parametrize("name", sorted(CASES))
async def test_tool_contract(name, client, backend, tmp_path):
    kwargs, method, path, json_subset, params_subset = CASES[name]
    kwargs = dict(kwargs)
    if kwargs.get("file_path") == "@FILE@":
        f = tmp_path / "evidence.bin"
        f.write_bytes(b"evidence")
        kwargs["file_path"] = str(f)
    out = await _tool_fn(name)(**kwargs)
    assert isinstance(out, str)
    call = backend.find(method, path)
    assert call is not None, f"{name}: expected {method} {path}, got {[(c['method'], c['path']) for c in backend.calls]}"
    if json_subset:
        body = call["json"] or {}
        for k, v in json_subset.items():
            assert body.get(k) == v, f"{name}: body[{k!r}]={body.get(k)!r}, expected {v!r}"
    if params_subset:
        for k, v in params_subset.items():
            assert call["params"].get(k) == v, f"{name}: param {k}={call['params'].get(k)!r}, expected {v!r}"
    assert call["auth"] == "Bearer static-token"


async def test_every_prompt_renders_and_only_uses_known_routes(pkg, client, backend):
    backend.set("GET", f"/incidents/{I}", {"id": I, "title": "Ransomware", "status": "open", "severity": "high"})
    known = {f"/incidents/{I}", f"/incidents/{I}/timeline", f"/incidents/{I}/hosts", f"/incidents/{I}/accounts",
             f"/incidents/{I}/network-iocs", f"/incidents/{I}/host-iocs", f"/incidents/{I}/malware",
             f"/incidents/{I}/tasks", f"/incidents/{I}/case-notes", f"/incidents/{I}/artifacts"}
    prompts = await pkg.mcp.list_prompts()
    for p in prompts:
        result = await pkg.mcp.get_prompt(p.name, {"incident_id": I})
        assert result.messages, p.name
    used = {c["path"] for c in backend.calls}
    assert used <= known, used - known
