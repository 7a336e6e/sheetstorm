"""Supabase ↔ SheetStorm role synchronisation.

Stores the canonical list of SheetStorm role names in each Supabase user's
``app_metadata.sheetstorm_roles`` so that roles survive a full database
rebuild.  After a rebuild, the next Supabase login (or sync-supabase call)
reads those roles back and re-assigns them locally.
"""

from __future__ import annotations

import logging
from typing import Sequence

import requests as http_requests
from flask import current_app

from app import db
from app.models import Role, UserRole

logger = logging.getLogger(__name__)

_METADATA_KEY = "sheetstorm_roles"


# ── Push local → Supabase ──────────────────────────────────────────

def push_roles_to_supabase(user) -> bool:
    """Write the user's current local roles into Supabase ``app_metadata``.

    Returns ``True`` on success, ``False`` if the update failed or Supabase
    is not configured.  Failures are logged but never raised so that the
    local role change is not rolled back.
    """
    supabase_url = current_app.config.get("SUPABASE_URL")
    service_key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_key or not user.supabase_id:
        return False

    role_names = sorted(
        r.role.name for r in user.user_roles if r.role
    )

    try:
        resp = http_requests.put(
            f"{supabase_url}/auth/v1/admin/users/{user.supabase_id}",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "Content-Type": "application/json",
            },
            json={"app_metadata": {_METADATA_KEY: role_names}},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            logger.warning(
                "Supabase app_metadata update failed for %s: %s %s",
                user.email, resp.status_code, resp.text,
            )
            return False
        logger.info(
            "Pushed roles %s to Supabase for %s", role_names, user.email,
        )
        return True
    except Exception:
        logger.exception("Failed to push roles to Supabase for %s", user.email)
        return False


# ── Pull Supabase → local ──────────────────────────────────────────

def roles_from_supabase_metadata(sb_user: dict) -> list[str]:
    """Extract SheetStorm role names from a Supabase user dict.

    Returns an empty list when the key is absent or not a list.
    """
    app_meta = sb_user.get("app_metadata") or {}
    roles = app_meta.get(_METADATA_KEY)
    if isinstance(roles, list):
        return [r for r in roles if isinstance(r, str)]
    return []


def assign_roles_from_list(
    user,
    role_names: Sequence[str],
    organization_id,
    granted_by=None,
) -> int:
    """Assign the listed roles to *user*, skipping any already present.

    Returns the number of newly assigned roles.
    """
    existing = {ur.role.name for ur in user.user_roles if ur.role}
    assigned = 0

    for name in role_names:
        if name in existing:
            continue
        role = Role.query.filter_by(name=name).first()
        if not role:
            logger.warning("Role %r not found — skipping", name)
            continue
        ur = UserRole(
            user_id=user.id,
            role_id=role.id,
            organization_id=organization_id,
            granted_by=granted_by,
        )
        db.session.add(ur)
        assigned += 1

    return assigned


def sync_roles_for_user(user, sb_user: dict, granted_by=None) -> int:
    """Read roles from Supabase metadata and assign them locally.

    Intended for use during login or bulk sync.  Only *adds* roles — does
    not remove locally-assigned roles that are absent from Supabase metadata.

    Returns the number of new roles assigned.
    """
    role_names = roles_from_supabase_metadata(sb_user)
    if not role_names:
        return 0
    return assign_roles_from_list(
        user,
        role_names,
        organization_id=user.organization_id,
        granted_by=granted_by,
    )


# ── Bulk push for migration ────────────────────────────────────────

def push_all_roles_to_supabase() -> dict:
    """Push every Supabase-linked user's local roles to ``app_metadata``.

    Useful as a one-time migration after adding this feature.
    Returns ``{"success": N, "failed": N, "skipped": N}``.
    """
    from app.models import User

    stats = {"success": 0, "failed": 0, "skipped": 0}
    users = User.query.filter(User.supabase_id.isnot(None), User.supabase_id != "").all()

    for user in users:
        if not user.supabase_id:
            stats["skipped"] += 1
            continue
        ok = push_roles_to_supabase(user)
        stats["success" if ok else "failed"] += 1

    return stats
