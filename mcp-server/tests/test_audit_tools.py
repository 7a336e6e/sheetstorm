"""Audit log search and system status tools (W1-AUD-BE)."""

from __future__ import annotations

import asyncio
import importlib

from conftest import PKG

admin = importlib.import_module(f"{PKG}.tools.admin")


async def test_audit_logs_show_actor_status_and_change_summary(client, backend):
    backend.set("GET", "/audit-logs", {"items": [{
        "created_at": "2026-10-01T10:00:00+00:00", "action": "update", "event_type": "admin_action",
        "user_email": "admin@x.test", "status_code": 200, "resource_type": "role", "resource_id": "r1",
        "details": {"changes": {"permissions": {"added": ["a", "b"], "removed": ["c"]},
                                "client_secret": {"changed": True},
                                "name": {"from": "Old", "to": "New"}}},
    }], "total": 1, "page": 1})
    out = await admin.sheetstorm_get_audit_logs(user_email="admin@x.test", start_date="2026-01-01")
    assert "by admin@x.test" in out and "→ 200" in out
    assert "permissions +2/-1" in out and "client_secret (changed, redacted)" in out
    assert "name: 'Old' → 'New'" in out
    params = backend.find("GET", "/audit-logs")["params"]
    assert params["user_email"] == "admin@x.test" and params["start_date"] == "2026-01-01"
    assert "action" not in params  # substring semantics go through action_contains


async def test_audit_logs_empty(client, backend):
    backend.set("GET", "/audit-logs", {"items": [], "total": 0})
    assert await admin.sheetstorm_get_audit_logs() == "No audit logs found."


async def test_system_status_org_admin_view(client, backend):
    backend.set("GET", "/admin/system-status", {
        "infra_visible": False, "storage": {"backend": "local"},
        "ai_providers": [{"provider": "ollama", "source": "integration"}],
        "integrations": [{"name": "MISP", "type": "misp", "is_enabled": True, "last_test_ok": False}],
        "counts": {"users": 3, "active_users": 2, "incidents": 5, "open_incidents": 1, "artifacts": 7},
        "audit": {"total_rows": 10, "retention_days": None, "legal_hold": True,
                  "chain": {"head_seq": 9, "head_hash": "ab" * 32, "last_verify_ok": True}},
    })
    out = await admin.sheetstorm_get_system_status()
    assert "Database" not in out and "Storage: local" in out
    assert "ollama (integration)" in out and "MISP [misp] enabled, last test FAILED" in out
    assert "retention forever, LEGAL HOLD" in out and "chain head 9:abababababababab" in out
    assert "last verification OK" in out


async def test_system_status_platform_view(client, backend):
    backend.set("GET", "/admin/system-status", {
        "infra_visible": True,
        "app": {"version": "1.2.3", "commit": "abc", "environment": "production"},
        "database": {"ok": True, "latency_ms": 1.2, "server_version": "16.4"},
        "alembic": {"ok": True, "current": ["audit_governance"], "head": ["audit_governance"], "up_to_date": True},
        "redis": {"ok": False, "error": "unavailable"},
        "rate_limiting": {"enabled": True, "storage": "redis", "default_limit": "600 per minute"},
        "storage": {"backend": "local", "disk": {"ok": True, "used_pct": 42.0}},
    })
    out = await admin.sheetstorm_get_system_status()
    assert "Version: 1.2.3 (abc)" in out and "Database: OK" in out and "up to date" in out
    assert "Redis: FAIL (unavailable)" in out and "42.0% used" in out


async def test_system_status_error(client, backend):
    backend.set("GET", "/admin/system-status", {"error": "forbidden", "message": "Permission denied"}, status=403)
    out = await admin.sheetstorm_get_system_status()
    assert out.startswith("✗ Error")


def test_no_audit_export_tool(pkg):
    names = {t.name for t in asyncio.run(pkg.mcp.list_tools())}
    assert "sheetstorm_get_system_status" in names
    assert not any("export" in n and "audit" in n for n in names)
