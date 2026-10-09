"""Response parsing for tools whose backend shapes changed, and client auth behaviour."""

from __future__ import annotations

import importlib

import pytest
from conftest import PKG

I = "inc-1"  # noqa: E741
artifacts = importlib.import_module(f"{PKG}.tools.artifacts")
reports = importlib.import_module(f"{PKG}.tools.reports")
assets = importlib.import_module(f"{PKG}.tools.assets")
incidents = importlib.import_module(f"{PKG}.tools.incidents")
admin = importlib.import_module(f"{PKG}.tools.admin")
defang = importlib.import_module(f"{PKG}.tools.defang")
kb = importlib.import_module(f"{PKG}.tools.knowledge_base")
client_mod = importlib.import_module(f"{PKG}.client")

HASHES = {"md5": "m", "sha256": "s", "sha512": "x"}


# -- artifacts ----------------------------------------------------------------

async def test_verify_artifact_match(client, backend):
    backend.set("POST", f"/incidents/{I}/artifacts/a1/verify", {
        "result": "match", "stored_hashes": HASHES, "computed_hashes": HASHES,
        "matches": {"md5": True, "sha256": True, "sha512": True}})
    out = await artifacts.sheetstorm_verify_artifact(I, "a1")
    assert out.startswith("**Integrity Check**: PASS")
    assert "stored:   s" in out and "computed: s" in out


async def test_verify_artifact_mismatch(client, backend):
    backend.set("POST", f"/incidents/{I}/artifacts/a1/verify", {
        "result": "mismatch", "stored_hashes": HASHES, "computed_hashes": {**HASHES, "sha256": "evil"},
        "matches": {"md5": True, "sha256": False, "sha512": True}})
    out = await artifacts.sheetstorm_verify_artifact(I, "a1")
    assert "FAIL" in out and "SHA256 ✗ MISMATCH" in out and "computed: evil" in out


async def test_chain_of_custody_reads_chain_of_custody_key(client, backend):
    backend.set("GET", f"/incidents/{I}/artifacts/a1/custody", {
        "artifact_id": "a1", "original_filename": "mem.raw", "chain_of_custody": [
            {"action": "upload", "created_at": "t1", "performer": {"name": "Ann"}, "purpose": "intake",
             "signature_status": "valid"},
            {"action": "verify", "created_at": "t2", "performer": {"name": "Bob"},
             "verification_result": "match", "signature_status": "unsigned_legacy"},
            {"action": "download", "created_at": "t3", "performer": {"name": "Eve"},
             "signature_status": "invalid"},
        ]})
    out = await artifacts.sheetstorm_get_chain_of_custody(I, "a1")
    assert "(3 events) — mem.raw" in out
    assert "**upload** by Ann" in out and "Purpose: intake" in out
    assert "Signature: valid" in out and "Signature: unsigned_legacy" in out and "Signature: invalid" in out
    assert "Verification: match" in out


async def test_export_custody_json(client, backend):
    backend.set("GET", f"/incidents/{I}/artifacts/a1/custody/export", {
        "artifact": {"id": "a1", "original_filename": "mem.raw"}, "chain_integrity": False,
        "chain_integrity_status": "compromised", "generated_at": "now", "custody_entries": [{"action": "upload", "signature_valid": False}]})
    out = await artifacts.sheetstorm_export_custody(I, "a1")
    assert "Chain integrity: COMPROMISED" in out and '"signature_valid": false' in out


async def test_upload_sends_description_and_acquisition_fields(client, backend, tmp_path):
    f = tmp_path / "disk.E01"
    f.write_bytes(b"EVF")
    await artifacts.sheetstorm_upload_artifact(
        I, str(f), description="disk image", acquisition_tool="FTK", source_host="WS1")
    body = backend.find("POST", f"/incidents/{I}/artifacts")["json"]
    assert b'name="description"' in body and b"disk image" in body
    assert b'name="acquisition_tool"' in body and b"FTK" in body
    assert b'name="source_host"' in body and b'filename="disk.E01"' in body


# -- reports --------------------------------------------------------------------

async def test_ai_report_uses_summary_type_and_reads_summary(client, backend):
    backend.set("POST", f"/incidents/{I}/reports/ai-generate",
                {"summary": "Attacker used RDP.", "summary_type": "technical", "provider": "openai"})
    out = await reports.sheetstorm_generate_ai_report(I, summary_type="technical")
    assert "Attacker used RDP." in out and "provider: openai" in out
    body = backend.find("POST", f"/incidents/{I}/reports/ai-generate")["json"]
    assert body == {"summary_type": "technical"}


# -- accounts -------------------------------------------------------------------

async def test_reveal_falls_back_to_name_filtered_list_and_returns_only_target(client, backend):
    backend.set("GET", f"/incidents/{I}/accounts/ac2", {"error": "method_not_allowed"}, status=405)
    listing = {"items": [{"id": "ac1", "account_name": "alice"}, {"id": "ac2", "account_name": "bob"}], "pages": 1}
    revealed = {"items": [{"id": "ac2", "account_name": "bob", "password": "S3cret!", "has_password": True},
                          {"id": "ac9", "account_name": "bobby", "password": "other", "has_password": True}]}

    backend.set("GET", f"/incidents/{I}/accounts",
                lambda req: (200, revealed if req.url.params.get("reveal") == "true" else listing))
    out = await assets.sheetstorm_reveal_account_password(I, "ac2")
    revealing = [c for c in backend.calls if c["params"].get("reveal") == "true" and c["path"].endswith("/accounts")]
    assert revealing and revealing[0]["params"].get("search") == "bob"
    assert "S3cret!" in out and "other" not in out


async def test_reveal_single_account_endpoint(client, backend):
    backend.set("GET", f"/incidents/{I}/accounts/ac1",
                {"id": "ac1", "account_name": "alice", "password": "pw1", "has_password": True})
    out = await assets.sheetstorm_reveal_account_password(I, "ac1")
    assert out == "Password for alice: pw1"
    assert all(c["path"] != f"/incidents/{I}/accounts" for c in backend.calls)


def test_reveal_description_warns_about_llm_context():
    assert "AI model's context" in assets.sheetstorm_reveal_account_password.__doc__


# -- guard rails -----------------------------------------------------------------

async def test_permanent_delete_requires_exact_confirmation(client, backend):
    out = await incidents.sheetstorm_permanently_delete_incident(I, confirmation="yes")
    assert out.startswith("✗ Aborted") and not backend.calls


@pytest.mark.parametrize("given,expected", [
    ("analyst", "Analyst"), ("ADMIN", "Administrator"), ("incident_responder", "Incident Responder"),
    ("Viewer", "Viewer"), ("admin", "Administrator"),
])
async def test_create_user_sends_canonical_role(client, backend, given, expected):
    await admin.sheetstorm_create_user("a@b.c", "A", "pw", role=given)
    assert backend.find("POST", "/users")["json"]["roles"] == [expected]


async def test_create_user_passes_custom_role_through(client, backend):
    await admin.sheetstorm_create_user("a@b.c", "A", "pw", role="Hunters")
    assert backend.find("POST", "/users")["json"]["roles"] == ["Hunters"]


async def test_list_permissions_flags_dangerous_and_filters_group(client, backend):
    backend.set("GET", "/permissions", {
        "groups": [{"key": "incidents", "label": "Incidents"}, {"key": "users", "label": "Users"}],
        "items": [
            {"key": "incidents:purge", "group": "incidents", "label": "Purge", "description": "d", "dangerous": True},
            {"key": "users:read", "group": "users", "label": "View users", "description": "d", "dangerous": False},
        ]})
    out = await admin.sheetstorm_list_permissions(group="incidents")
    assert "incidents:purge" in out and "dangerous" in out and "users:read" not in out


async def test_list_roles_tags_system_and_custom(client, backend):
    backend.set("GET", "/roles", {"items": [
        {"id": "r1", "name": "Analyst", "is_system": True, "permissions": ["a", "b"]},
        {"id": "r2", "name": "Hunters", "is_system": False, "permissions": ["a"]}]})
    out = await admin.sheetstorm_list_roles()
    assert "Analyst** [system]" in out and "Hunters** [custom]" in out


async def test_update_user_does_not_send_ignored_fields(client, backend):
    await admin.sheetstorm_update_user("u1", name="New")
    assert backend.find("PUT", "/users/u1")["json"] == {"name": "New"}


async def test_delete_user_409_shows_counts(client, backend):
    backend.set("DELETE", "/users/u1", {"error": "user_has_records", "message": "deactivate instead",
                                        "counts": {"incidents": 2, "timeline_events": 5}, "hint": "deactivate"},
                status=409)
    out = await admin.sheetstorm_delete_user("u1")
    assert out.startswith("✗") and "incidents: 2" in out and "timeline_events: 5" in out
    assert "sheetstorm_disable_user" in out


async def test_invite_user_resolves_role_and_builds_absolute_link(client, backend):
    backend.set("GET", "/roles", {"items": [{"id": "r-analyst", "name": "Analyst"}]})
    backend.set("POST", "/users/invites", {"id": "i1", "invite": {"id": "i1", "email": "a@b.c"},
                                           "token": "tok", "accept_path": "/auth/invite#token=tok"}, status=201)
    out = await admin.sheetstorm_invite_user("a@b.c", role="analyst", team_ids=["t1"])
    body = backend.find("POST", "/users/invites")["json"]
    assert body["role_ids"] == ["r-analyst"] and body["team_ids"] == ["t1"]
    assert "http://backend.test/auth/invite#token=tok" in out


async def test_invite_user_prefers_server_accept_url_and_rejects_unknown_role(client, backend):
    backend.set("POST", "/users/invites", {"invite": {"id": "i1"}, "accept_path": "/auth/invite#token=t",
                                           "accept_url": "https://ui.example/auth/invite#token=t"}, status=201)
    assert "https://ui.example/auth/invite#token=t" in await admin.sheetstorm_invite_user("a@b.c")
    out = await admin.sheetstorm_invite_user("a@b.c", role="nope")
    assert out.startswith("✗ Unknown role")


def test_reset_tools_not_exposed_over_mcp():
    assert not hasattr(admin, "sheetstorm_reset_user_password")
    assert not hasattr(admin, "sheetstorm_reset_user_mfa")
    doc = admin.sheetstorm_invite_user.__doc__ or ""
    assert "credential" in doc


async def test_list_users_lifecycle_flags_and_status_validation(client, backend):
    backend.set("GET", "/users", {"items": [{"id": "u1", "name": "A", "is_locked": True,
                                             "locked_until": "2026-10-09T10:00:00Z",
                                             "must_change_password": True}], "total": 1})
    out = await admin.sheetstorm_list_users(status="locked")
    assert "Locked until 2026-10-09T10:00:00Z" in out and "Must change password" in out
    assert (await admin.sheetstorm_list_users(status="weird")).startswith("✗")


# -- defang / d3fend --------------------------------------------------------------

async def test_defang_parses_items_and_text(client, backend):
    backend.set("POST", "/tools/defang", {"items": [{"original": "evil.com", "defanged": "evil[.]com"}]})
    assert "evil[.]com" in await defang.sheetstorm_defang_iocs(values=["evil.com"])
    backend.set("POST", "/tools/defang", {"original": "x", "defanged": "hxxp://evil[.]com"})
    assert "hxxp://evil[.]com" in await defang.sheetstorm_defang_iocs(text="http://evil.com")
    backend.set("POST", "/tools/refang", {"items": [{"defanged": "evil[.]com", "original": "evil.com"}]})
    assert "evil.com" in await defang.sheetstorm_refang_iocs(values=["evil[.]com"])


async def test_d3fend_suggest_payload(client, backend):
    backend.set("POST", "/knowledge-base/d3fend/suggest", {"items": [
        {"id": "D3-PSA", "name": "Process Spawn Analysis", "tactic": "Detect", "matched_techniques": ["T1059"]}]})
    out = await kb.sheetstorm_kb_d3fend_suggest(["T1059"])
    assert "D3-PSA" in out
    assert backend.find("POST", "/knowledge-base/d3fend/suggest")["json"] == {"attack_techniques": ["T1059"]}


# -- client --------------------------------------------------------------------------

async def test_refresh_stores_rotated_refresh_token(make_client, backend, monkeypatch):
    c = make_client("stdio", SHEETSTORM_API_TOKEN="", SHEETSTORM_USERNAME="u@x", SHEETSTORM_PASSWORD="pw")
    backend.set("POST", "/auth/login", {"access_token": "acc-1", "refresh_token": "ref-1"})
    backend.set("POST", "/auth/refresh", {"access_token": "acc-2", "refresh_token": "ref-2"})
    await c.ensure_authenticated()
    await c.refresh()
    assert c._access_token == "acc-2" and c._refresh_token == "ref-2"
    assert backend.find("POST", "/auth/refresh")["auth"] == "Bearer ref-1"
    backend.set("POST", "/auth/refresh", {"access_token": "acc-3", "refresh_token": "ref-3"})
    await c.refresh()
    refreshes = [x["auth"] for x in backend.calls if x["path"] == "/auth/refresh"]
    assert refreshes == ["Bearer ref-1", "Bearer ref-2"]


async def test_401_triggers_refresh_and_retry(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_TOKEN="", SHEETSTORM_USERNAME="u@x", SHEETSTORM_PASSWORD="pw")
    backend.set("POST", "/auth/login", {"access_token": "old", "refresh_token": "ref-1"})
    backend.set("POST", "/auth/refresh", {"access_token": "new", "refresh_token": "ref-2"})
    backend.set("GET", "/auth/me", lambda req: (
        (401, {"error": "token_expired"}) if req.headers["authorization"] == "Bearer old" else (200, {"name": "A"})))
    assert (await c.get("/auth/me"))["name"] == "A"
    assert c._refresh_token == "ref-2"
    me_calls = [x["auth"] for x in backend.calls if x["path"] == "/auth/me"]
    assert me_calls == ["Bearer old", "Bearer new"]


async def test_error_message_preferred_over_error_code(client, backend):
    backend.set("GET", f"/incidents/{I}", {"error": "forbidden", "message": "Only administrators can do that"},
                status=403)
    with pytest.raises(client_mod.AuthenticationError) as exc:
        await client.get(f"/incidents/{I}")
    assert str(exc.value) == "Only administrators can do that"


async def test_cookies_are_never_persisted_or_sent(client, backend):
    import httpx
    import respx

    respx.route(host="backend.test", path="/api/v1/set-cookie").mock(
        return_value=httpx.Response(200, json={}, headers={"set-cookie": "refresh_token_cookie=abc; Path=/"}))
    await client.get("/set-cookie")
    await client.get("/auth/me")
    assert len(client._http.cookies) == 0
    assert backend.find("GET", "/auth/me")["cookie"] is None


async def test_logout_revokes_refresh_token(make_client, backend):
    c = make_client("stdio", SHEETSTORM_API_TOKEN="", SHEETSTORM_USERNAME="u@x", SHEETSTORM_PASSWORD="pw")
    backend.set("POST", "/auth/login", {"access_token": "acc", "refresh_token": "ref"})
    await c.ensure_authenticated()
    await c.logout()
    call = backend.find("POST", "/auth/logout")
    assert call["auth"] == "Bearer acc" and call["json"] == {"refresh_token": "ref"}
    assert c._access_token is None and c._refresh_token is None


async def test_export_custody_falls_back_to_boolean_integrity(client, backend):
    backend.set("GET", f"/incidents/{I}/artifacts/a1/custody/export",
                {"artifact": {"id": "a1"}, "chain_integrity": True, "custody_entries": []})
    assert "Chain integrity: INTACT" in await artifacts.sheetstorm_export_custody(I, "a1")
