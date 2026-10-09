"""Decision-log tools (W4-DEC): never approve/authorize/apply state, never
mark privileged, verification sends the current version, input guards."""

from __future__ import annotations

import asyncio
import importlib
import inspect

from conftest import PKG

decisions = importlib.import_module(f"{PKG}.tools.decisions")

I = "inc-1"  # noqa: E741


def test_no_approval_authorization_or_privileged_surface(pkg):
    names = {t.name for t in asyncio.run(pkg.mcp.list_tools())}
    assert not any(("approve" in n or "authorize" in n) for n in names)
    for fn in (decisions.sheetstorm_log_decision, decisions.sheetstorm_log_response_action):
        params = set(inspect.signature(fn).parameters)
        assert not params & {"is_privileged", "status", "approve", "apply_target_state", "target_state"}


async def test_verification_sends_the_current_version(client, backend):
    backend.set("GET", f"/incidents/{I}/response-actions/a1", {"id": "a1", "version": 4, "status": "executed"})
    backend.set("POST", f"/incidents/{I}/response-actions/a1/verify",
                {"id": "a1", "display_id": "A-001", "title": "Isolate", "status": "verified",
                 "verified_at": "2026-01-01T00:00:00Z", "verification_result": "success",
                 "verified_by_name": "SOC"})
    out = await decisions.sheetstorm_update_action_verification(
        incident_id=I, action_id="a1", result="success", method="EDR", verified_by_name="SOC")
    assert out.startswith("✓") and "SOC (recorded)" in out
    body = backend.find("POST", f"/incidents/{I}/response-actions/a1/verify")["json"]
    assert body["expected_version"] == 4 and body["verified_by_name"] == "SOC"


async def test_malformed_json_arguments_send_nothing(client, backend):
    out = await decisions.sheetstorm_log_decision(incident_id=I, title="t", decision="d", links="{not json")
    assert out.startswith("✗") and backend.find("POST", f"/incidents/{I}/decisions") is None
    out = await decisions.sheetstorm_log_response_action(incident_id=I, action_type="other", title="t",
                                                         links='{"a": 1}')
    assert out.startswith("✗") and backend.find("POST", f"/incidents/{I}/response-actions") is None


async def test_list_decisions_formats_attestations(client, backend):
    backend.set("GET", f"/incidents/{I}/decisions", {"total": 1, "items": [{
        "id": "d1", "display_id": "D-001", "title": "No ransom", "status": "approved", "category": "ransom_legal",
        "decided_at": "2026-01-01T10:00:00Z", "decision": "Do not pay", "approved_at": "2026-01-01T11:00:00Z",
        "approved_by_name": "General Counsel", "users": {"decided_by_user_id": {"name": "Jo"}}}]})
    out = await decisions.sheetstorm_list_decisions(incident_id=I)
    assert "D-001: No ransom" in out and "General Counsel (recorded)" in out and "by Jo" in out
