"""Metrics and improvement-action tools (W3-RT-POST): formatting of durations
and anomalies, only the set filters are sent, errors are reported."""

from __future__ import annotations

import importlib

from conftest import PKG

metrics = importlib.import_module(f"{PKG}.tools.metrics")

I = "inc-1"  # noqa: E741


def test_duration_formatting():
    d = metrics._duration
    assert d(None) == "-"
    assert d(45) == "45s"
    assert d(5 * 60 + 10) == "5m"
    assert d(2 * 3600 + 15 * 60) == "2h 15m"
    assert d(3 * 86400 + 4 * 3600 + 59) == "3d 4h"


async def test_incident_metrics_are_formatted_with_anomalies(client, backend):
    backend.set("GET", f"/incidents/{I}/metrics", {
        "incident_id": I,
        "durations": {"dwell_time": 36 * 3600, "time_to_respond": 900, "time_to_contain": None,
                      "total_open": 90000},
        "anomalies": [{"metric": "time_to_contain", "reason": "negative", "seconds": -3600}],
        "sources": {"first_malicious": "timeline"},
    })
    out = await metrics.sheetstorm_get_incident_metrics(incident_id=I)
    assert "Dwell time (first malicious -> detected): 1d 12h" in out
    assert "Time to respond (detected -> responded): 15m" in out
    assert "Time to contain (detected -> contained): -" in out
    assert "derived from the timeline" in out
    assert "Anomaly: time_to_contain is negative" in out


async def test_incident_metrics_error_is_reported(client, backend):
    backend.set("GET", f"/incidents/{I}/metrics", {"error": "forbidden", "message": "no"}, status=403)
    assert (await metrics.sheetstorm_get_incident_metrics(incident_id=I)).startswith("✗ Error loading metrics")


async def test_list_improvement_actions_sends_only_set_filters(client, backend):
    backend.set("GET", "/improvement-actions", {"items": [
        {"id": "a1", "title": "Enable MFA", "status": "open", "priority": "high",
         "owner": {"name": "Dana"}, "due_date": "2026-04-01T00:00:00+00:00", "incident_ref": "#7 Ransom",
         "control_framework": "d3fend", "control_ref": "D3-MFA"}], "total": 1})
    out = await metrics.sheetstorm_list_improvement_actions()
    params = backend.find("GET", "/improvement-actions")["params"]
    assert params == {"page": "1", "per_page": "50"}
    assert "Enable MFA" in out and "Owner: Dana" in out and "Due: 2026-04-01" in out
    assert "Control: d3fend D3-MFA" in out and "#7 Ransom" in out


async def test_list_improvement_actions_empty(client, backend):
    assert await metrics.sheetstorm_list_improvement_actions(status="done") == "No improvement actions found."


async def test_add_improvement_action_sends_only_given_fields(client, backend):
    backend.set("POST", f"/incidents/{I}/improvement-actions",
                {"id": "a1", "title": "Patch VPN", "status": "open", "priority": "medium"})
    out = await metrics.sheetstorm_add_improvement_action(incident_id=I, title="Patch VPN")
    assert backend.find("POST", f"/incidents/{I}/improvement-actions")["json"] == {
        "title": "Patch VPN", "priority": "medium"}
    assert out.startswith("✓ Improvement action added") and "Patch VPN" in out


async def test_add_improvement_action_validation_error_is_reported(client, backend):
    backend.set("POST", f"/incidents/{I}/improvement-actions",
                {"error": "invalid_control", "message": "control_ref requires control_framework"}, status=400)
    out = await metrics.sheetstorm_add_improvement_action(incident_id=I, title="x", control_ref="D3-MFA")
    assert out.startswith("✗ Error adding improvement action")
