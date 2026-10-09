"""Incident detail, milestone and dashboard tools (W2-DFIR-B)."""

from __future__ import annotations

import importlib

from conftest import PKG

incidents = importlib.import_module(f"{PKG}.tools.incidents")
I = "inc-1"  # noqa: E741


async def test_update_incident_clears_milestones_with_explicit_nulls(client, backend):
    backend.set("PUT", f"/incidents/{I}", {"id": I, "title": "T"})
    out = await incidents.sheetstorm_update_incident(
        incident_id=I, recovered_at="2026-01-03T00:00:00Z", clear_milestones="closed_at, ")
    assert out.startswith("✓")
    body = backend.find("PUT", f"/incidents/{I}")["json"]
    assert body == {"recovered_at": "2026-01-03T00:00:00Z", "closed_at": None}


async def test_update_incident_rejects_unknown_or_conflicting_clears(client, backend):
    out = await incidents.sheetstorm_update_incident(incident_id=I, clear_milestones="title")
    assert out.startswith("✗ Unknown milestone")
    out = await incidents.sheetstorm_update_incident(incident_id=I, closed_at="2026-01-03T00:00:00Z",
                                                     clear_milestones="closed_at")
    assert "both set and cleared" in out
    assert backend.calls == []


async def test_update_incident_sets_and_clears_rt_post_milestones(client, backend):
    backend.set("PUT", f"/incidents/{I}", {"id": I, "title": "T"})
    out = await incidents.sheetstorm_update_incident(
        incident_id=I, first_malicious_at="2026-01-01T00:00:00Z", clear_milestones="responded_at")
    assert out.startswith("✓")
    body = backend.find("PUT", f"/incidents/{I}")["json"]
    assert body == {"first_malicious_at": "2026-01-01T00:00:00Z", "responded_at": None}


async def test_get_incident_shows_first_malicious_and_responded(client, backend):
    backend.set("GET", f"/incidents/{I}", {"id": I, "title": "T", "first_malicious_at": "2026-01-01T00:00:00+00:00",
                                          "responded_at": "2026-01-02T00:00:00+00:00"})
    out = await incidents.sheetstorm_get_incident(incident_id=I)
    assert "- First Malicious: 2026-01-01T00:00:00+00:00" in out
    assert "- Responded: 2026-01-02T00:00:00+00:00" in out


async def test_update_incident_reports_milestone_400(client, backend):
    backend.set("PUT", f"/incidents/{I}", {"error": "invalid_milestones", "code": "milestone_order",
                                          "message": "detected_at must not be after contained_at"}, status=400)
    out = await incidents.sheetstorm_update_incident(incident_id=I, contained_at="2020-01-01T00:00:00Z")
    assert out.startswith("✗") and "detected_at must not be after contained_at" in out


async def test_get_incident_shows_milestones_lead_and_summary(client, backend):
    backend.set("GET", f"/incidents/{I}", {
        "id": I, "title": "Ransomware", "status": "contained", "tlp": "red",
        "lead_responder": {"id": "u1", "name": "Dana"},
        "detected_at": "2026-01-01T10:00:00+00:00", "contained_at": "2026-01-02T10:00:00+00:00",
        "summary": {"first_event_at": "2025-12-30T08:00:00+00:00", "last_event_at": "2026-01-02T09:00:00+00:00",
                    "earliest_detection_at": None, "leads": {"total": 3, "open": 2, "by_outcome": {}},
                    "hosts_by_triage": {"under_analysis": 2, "clean": 1}, "acquisition": None},
    })
    out = await incidents.sheetstorm_get_incident(incident_id=I)
    assert "**Lead Responder**: Dana (u1)" in out
    assert "- Detected: 2026-01-01T10:00:00+00:00" in out and "- Contained: 2026-01-02T10:00:00+00:00" in out
    assert "First known activity: 2025-12-30T08:00:00+00:00" in out
    assert "Leads: 2 open of 3" in out
    assert "Hosts by triage: clean 1, under_analysis 2" in out


async def test_get_incident_tolerates_null_summary_parts(client, backend):
    backend.set("GET", f"/incidents/{I}", {"id": I, "title": "T", "summary": {
        "first_event_at": None, "leads": None, "hosts_by_triage": None}})
    out = await incidents.sheetstorm_get_incident(incident_id=I)
    assert "Leads:" not in out and "Hosts by triage" not in out


async def test_dashboard_stats_renders_counts(client, backend):
    backend.set("GET", "/dashboard/stats", {
        "incidents": {"total": 3, "active": 2, "closed": 1, "critical": 1, "created_7d": 2, "created_30d": 3,
                      "by_severity": {"critical": 1, "high": 1, "medium": 1, "low": 0},
                      "by_status": {"open": 1, "closed": 1, "investigating": 1},
                      "by_phase_open": {"1": 1, "2": 1}, "by_tlp": {"red": 1, "amber": 2}},
        "mitre": {"events_total": 4, "events_mapped": 3,
                  "tactics": [{"tactic": "execution", "count": 2, "techniques": {"T1059": 2}}]},
        "dfir": {"open_leads": 2, "hosts_by_triage": {"clean": 1}},
    })
    out = await incidents.sheetstorm_get_dashboard_stats()
    assert "3 total, 2 active, 1 closed, 1 critical" in out
    assert "**By TLP**: amber 2, red 1" in out
    assert "**Open leads**: 2" in out
    assert "(3/4 events mapped)" in out and "- execution: 2 (T1059 2)" in out


async def test_dashboard_stats_without_optional_sections(client, backend):
    backend.set("GET", "/dashboard/stats", {"incidents": {"total": 0}, "mitre": None,
                                            "dfir": {"open_leads": None, "hosts_by_triage": None}})
    out = await incidents.sheetstorm_get_dashboard_stats()
    assert "0 total" in out and "MITRE" not in out and "Open leads" not in out
