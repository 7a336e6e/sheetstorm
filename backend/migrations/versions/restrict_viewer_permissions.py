"""Restrict Viewer role permissions — remove users:read, artifacts:read, reports:read

Revision ID: restrict_viewer_perms
Revises: expand_audit_fields
Create Date: 2026-03-12

"""
from alembic import op


revision = 'restrict_viewer_perms'
down_revision = 'expand_audit_fields'
branch_labels = None
depends_on = None

VIEWER_NEW_PERMISSIONS = [
    "incidents:read",
    "timeline:read",
    "hosts:read",
    "accounts:read",
    "network_iocs:read",
    "host_iocs:read",
    "malware:read",
    "tasks:read",
    "attack_graph:read",
]

VIEWER_OLD_PERMISSIONS = [
    "incidents:read",
    "timeline:read",
    "hosts:read",
    "accounts:read",
    "network_iocs:read",
    "host_iocs:read",
    "malware:read",
    "artifacts:read",
    "tasks:read",
    "attack_graph:read",
    "reports:read",
    "users:read",
]


def upgrade():
    import json
    op.execute(
        f"UPDATE roles SET permissions = '{json.dumps(VIEWER_NEW_PERMISSIONS)}'::jsonb "
        f"WHERE name = 'Viewer'"
    )


def downgrade():
    import json
    op.execute(
        f"UPDATE roles SET permissions = '{json.dumps(VIEWER_OLD_PERMISSIONS)}'::jsonb "
        f"WHERE name = 'Viewer'"
    )
