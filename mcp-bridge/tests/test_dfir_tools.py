"""DFIR task / host tools (W2-DFIR-A): server-side lead filters, resolved
evidence labels, bulk host triage, acquisition merge via `focus`."""

from __future__ import annotations

import importlib

from conftest import PKG

tasks = importlib.import_module(f"{PKG}.tools.tasks")
assets = importlib.import_module(f"{PKG}.tools.assets")

I = "inc-1"  # noqa: E741


async def test_list_leads_shows_counts_and_resolved_evidence(client, backend):
    backend.set("GET", f"/incidents/{I}/tasks", {
        "items": [{"id": "t1", "title": "RDP from jump host", "task_type": "investigative_lead",
                   "status": "in_progress", "priority": "high",
                   "evidence_refs": [{"evidence_type": "host", "evidence_id": "h1"}],
                   "evidence": [{"evidence_type": "host", "evidence_id": "h1", "label": "WS-01", "missing": False},
                                {"evidence_type": "artifact", "evidence_id": "a1", "label": None,
                                 "missing": False, "restricted": True},
                                {"evidence_type": "malware", "evidence_id": "m1", "label": None, "missing": True}]}],
        "total": 1, "lead_counts": {"open": 1, "false_positive": 2},
    })
    out = await tasks.sheetstorm_list_leads(incident_id=I)
    assert "open=1, false_positive=2" in out
    assert 'host "WS-01" (h1)' in out and "artifact:a1" in out and "malware:m1 (deleted)" in out
    params = backend.find("GET", f"/incidents/{I}/tasks")["params"]
    assert params["lead_outcome"] == "open" and params["task_type"] == "investigative_lead"


async def test_list_leads_all_outcomes_sends_no_outcome_filter(client, backend):
    await tasks.sheetstorm_list_leads(incident_id=I, outcome="all")
    assert "lead_outcome" not in backend.find("GET", f"/incidents/{I}/tasks")["params"]


async def test_list_tasks_filters_server_side(client, backend):
    backend.set("GET", f"/incidents/{I}/tasks", {"items": [
        {"id": "t1", "title": "Lead", "task_type": "investigative_lead"}], "total": 300})
    out = await tasks.sheetstorm_list_tasks(incident_id=I, task_type="investigative_lead")
    assert "300 total, showing 1" in out
    assert backend.find("GET", f"/incidents/{I}/tasks")["params"]["task_type"] == "investigative_lead"


async def test_bulk_update_hosts(client, backend):
    backend.set("PATCH", f"/incidents/{I}/hosts/bulk", {"updated": 2, "items": [
        {"id": "h1", "hostname": "WS-01"}, {"id": "h2", "hostname": "WS-02"}]})
    out = await assets.sheetstorm_bulk_update_hosts(incident_id=I, host_ids=["h1", "h2"],
                                                    containment_status="isolated")
    assert out.startswith("✓ 2 host(s) updated") and "WS-02" in out
    body = backend.find("PATCH", f"/incidents/{I}/hosts/bulk")["json"]
    assert body == {"host_ids": ["h1", "h2"], "containment_status": "isolated"}


async def test_bulk_update_hosts_requires_a_field(client, backend):
    out = await assets.sheetstorm_bulk_update_hosts(incident_id=I, host_ids=["h1"])
    assert out.startswith("Nothing to update")
    assert backend.calls == []


async def test_bulk_update_hosts_reports_backend_error(client, backend):
    backend.set("PATCH", f"/incidents/{I}/hosts/bulk",
                {"error": "invalid_host_ids", "message": "Some host_ids are not hosts of this incident",
                 "invalid": ["h9"]}, status=400)
    out = await assets.sheetstorm_bulk_update_hosts(incident_id=I, host_ids=["h9"], triage_status="clean")
    assert out.startswith("✗ Error")


async def test_update_host_merges_acquisition_from_focused_row(client, backend):
    backend.set("GET", f"/incidents/{I}/hosts", {"items": [
        {"id": "h1", "hostname": "WS-01", "acquisition_status": {"disk_imaged": True}}], "focus_found": True})
    backend.set("PUT", f"/incidents/{I}/hosts/h1", {"id": "h1", "hostname": "WS-01"})
    await assets.sheetstorm_update_host(incident_id=I, host_id="h1", memory_captured=True)
    params = backend.find("GET", f"/incidents/{I}/hosts")["params"]
    assert params == {"focus": "h1", "per_page": "1"}
    body = backend.find("PUT", f"/incidents/{I}/hosts/h1")["json"]
    assert body["acquisition_status"] == {"disk_imaged": True, "memory_captured": True}
