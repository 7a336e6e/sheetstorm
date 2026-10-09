"""Evidence register tools (W2-EVD-API): attestation guard, payload mapping, client header."""

from __future__ import annotations

import importlib

from conftest import PKG

I = "inc-1"  # noqa: E741
CLIENT_NAME = "mcp-server" if PKG == "sheetstorm_mcp" else "mcp-bridge"


def _tools():
    return importlib.import_module(f"{PKG}.tools.evidence")


async def test_transfer_without_attestation_never_reaches_the_backend(client, backend):
    out = await _tools().sheetstorm_transfer_evidence(
        incident_id=I, evidence_id="e1", mode="check_out", reason="imaging", to_user_id="u1")
    assert out.startswith("✗ Not recorded") and "attested=true" in out
    assert backend.calls == []


async def test_unknown_mode_is_refused_locally(client, backend):
    out = await _tools().sheetstorm_transfer_evidence(incident_id=I, evidence_id="e1", mode="teleport",
                                                      attested=True)
    assert out.startswith("✗ mode must be one of") and backend.calls == []


async def test_check_out_and_check_in_payloads(client, backend):
    t = _tools()
    await t.sheetstorm_transfer_evidence(incident_id=I, evidence_id="e1", mode="check_out", reason="imaging",
                                         to_user_id="u1", attested=True)
    call = backend.find("POST", f"/incidents/{I}/evidence/e1/custody/check-out")
    assert call["json"] == {"purpose": "imaging", "to_user_id": "u1"}
    await t.sheetstorm_transfer_evidence(incident_id=I, evidence_id="e1", mode="check_in", reason="scratched",
                                         storage_location="Safe 2", seal_intact=True, attested=True)
    call = backend.find("POST", f"/incidents/{I}/evidence/e1/custody/check-in")
    assert call["json"] == {"storage_location": "Safe 2", "seal_intact": True, "condition_notes": "scratched"}


async def test_item_chain_verification(client, backend):
    backend.set("GET", f"/incidents/{I}/evidence/e1/custody/verify",
                {"scope": "item", "status": "broken", "item_chain": {"length": 3, "head_seq": 3},
                 "signatures": {"valid": 3}, "breaks": [{"chain": "item", "seq": 2, "reason": "seq_gap"}]})
    out = await _tools().sheetstorm_verify_evidence_chain(incident_id=I, evidence_id="e1")
    assert "BROKEN" in out and "seq_gap" in out


async def test_register_rejects_bad_hashes_json_locally(client, backend):
    out = await _tools().sheetstorm_register_evidence(incident_id=I, title="x", evidence_type="other",
                                                      hashes_json="{not json")
    assert out.startswith("✗ hashes_json") and backend.calls == []


def test_client_identifies_itself(client):
    assert client._http.headers["X-SheetStorm-Client"] == CLIENT_NAME
