"""admin guardrails: org-scoped roles + full permission catalog grants

- roles.organization_id (NULL = global system role), the global UNIQUE(name)
  is replaced by two partial unique indexes on lower(name).
- Existing custom roles are re-homed to the org(s) of their holders; a custom
  role used by several orgs is split into one copy per org.
- ALL permission grants of the catalog (app/permissions.py,
  `_integration.md` §3) happen here, once. Feature migrations must not
  UPDATE roles.
- `incidents:delete` is removed from every role (archive/purge now use
  `incidents:archive` / `incidents:purge`).
- The existing default org keeps registration open (the code default
  becomes closed).

The permission lists are frozen copies: never import app code here.

Revision ID: admin_guardrails_rbac
Revises: add_search_trgm_indexes
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'admin_guardrails_rbac'
down_revision = 'add_search_trgm_indexes'
branch_labels = None
depends_on = None

_SYSTEM = "is_system AND organization_id IS NULL AND name = :role"
_CUSTOM = "NOT coalesce(is_system, false)"

# Grants to the global system roles (§3).
SYSTEM_GRANTS = {
    'Administrator': [
        'incidents:archive', 'incidents:purge', 'incidents:read_all', 'incidents:export',
        'case_notes:delete', 'templates:manage',
        'api_keys:own', 'api_keys:manage', 'system:manage', 'audit_logs:export',
        'decisions:read', 'decisions:create', 'decisions:update', 'decisions:approve',
        'decisions:read_privileged',
        'response_actions:read', 'response_actions:create', 'response_actions:update',
        'response_actions:authorize',
        'metrics:read',
        'improvements:read', 'improvements:create', 'improvements:update', 'improvements:delete',
    ],
    'Incident Responder': [
        'incidents:read_team', 'incidents:export', 'templates:manage', 'api_keys:own',
        'decisions:read', 'decisions:create', 'decisions:update', 'decisions:approve',
        'decisions:read_privileged',
        'response_actions:read', 'response_actions:create', 'response_actions:update',
        'response_actions:authorize',
        'metrics:read', 'improvements:read', 'improvements:create', 'improvements:update',
    ],
    'Analyst': [
        'incidents:read_team', 'api_keys:own',
        'decisions:read', 'decisions:create', 'decisions:update',
        'response_actions:read', 'response_actions:create', 'response_actions:update',
        'improvements:read', 'improvements:update',
    ],
    'Manager': [
        'incidents:read_all', 'incidents:export', 'api_keys:own',
        'decisions:read', 'decisions:approve', 'decisions:read_privileged',
        'response_actions:read', 'response_actions:authorize',
        'metrics:read', 'improvements:read', 'improvements:create', 'improvements:update',
    ],
    'Operator': [
        'api_keys:own', 'decisions:read', 'response_actions:read', 'response_actions:update',
        'improvements:read', 'improvements:update',
    ],
    'Viewer': [
        'incidents:read_tlp_white', 'decisions:read', 'response_actions:read', 'improvements:read',
    ],
}

# Custom-role backfill: holders of the trigger key keep today's access.
CUSTOM_BACKFILL = [
    # Visibility was the "team" tier for custom roles; plus read-only views of
    # the new per-incident features.
    ('incidents:read', ['incidents:read_team', 'decisions:read', 'response_actions:read', 'improvements:read']),
    # POST/DELETE /users and team mutations used users:manage.
    ('users:manage', ['users:create', 'users:delete', 'teams:create', 'teams:update', 'teams:delete']),
    # GET /teams and GET /teams/<id> used users:read.
    ('users:read', ['teams:read']),
    # Playbook CRUD was gated by incidents:create (C22).
    ('incidents:create', ['templates:manage']),
    # CSV/STIX exports were reachable by report generators.
    ('reports:generate', ['incidents:export']),
]

# Keys unknown before this revision (removed again on downgrade).
NEW_KEYS = sorted({
    'incidents:archive', 'incidents:purge', 'incidents:read_all', 'incidents:read_team',
    'incidents:read_tlp_white', 'incidents:export', 'case_notes:delete', 'templates:manage',
    'api_keys:own', 'api_keys:manage', 'system:manage', 'audit_logs:export',
    'decisions:read', 'decisions:create', 'decisions:update', 'decisions:approve', 'decisions:read_privileged',
    'response_actions:read', 'response_actions:create', 'response_actions:update', 'response_actions:authorize',
    'metrics:read', 'improvements:read', 'improvements:create', 'improvements:update', 'improvements:delete',
})


def _column_exists(table, column):
    insp = sa.inspect(op.get_bind())
    return column in {c['name'] for c in insp.get_columns(table)}


def _grant(where, keys, **params):
    bind = op.get_bind()
    for key in keys:
        bind.execute(sa.text(
            f"UPDATE roles SET permissions = coalesce(permissions, '[]'::jsonb) || jsonb_build_array(CAST(:key AS text)) "
            f"WHERE ({where}) AND NOT coalesce(permissions, '[]'::jsonb) @> jsonb_build_array(CAST(:key AS text))"
        ), dict(params, key=key))


def _revoke(where, keys, **params):
    bind = op.get_bind()
    for key in keys:
        bind.execute(sa.text(
            f"UPDATE roles SET permissions = permissions - CAST(:key AS text) "
            f"WHERE ({where}) AND permissions @> jsonb_build_array(CAST(:key AS text))"
        ), dict(params, key=key))


def _rehome_custom_roles(bind):
    """Give every global custom role an owner org; split shared ones."""
    fallback_org = bind.execute(sa.text(
        "SELECT id FROM organizations ORDER BY (slug = 'default') DESC, created_at NULLS LAST, id LIMIT 1"
    )).scalar()
    roles = bind.execute(sa.text(
        f"SELECT id, name, description, permissions FROM roles WHERE {_CUSTOM} AND organization_id IS NULL"
    )).fetchall()
    for role_id, name, description, permissions in roles:
        org_ids = [r[0] for r in bind.execute(sa.text(
            "SELECT o.id FROM organizations o WHERE o.id IN ("
            "  SELECT DISTINCT u.organization_id FROM user_roles ur JOIN users u ON u.id = ur.user_id"
            "  WHERE ur.role_id = :rid AND u.organization_id IS NOT NULL)"
            " ORDER BY o.created_at NULLS LAST, o.id"
        ), {'rid': role_id})]
        if not org_ids:
            if fallback_org is not None:
                bind.execute(sa.text("UPDATE roles SET organization_id = :org WHERE id = :rid"),
                             {'org': fallback_org, 'rid': role_id})
            else:  # no org at all: invisible to every tenant, harmless
                bind.execute(sa.text("UPDATE roles SET is_system = false WHERE id = :rid"), {'rid': role_id})
            continue
        bind.execute(sa.text("UPDATE roles SET organization_id = :org, is_system = false WHERE id = :rid"),
                     {'org': org_ids[0], 'rid': role_id})
        for org_id in org_ids[1:]:
            new_id = bind.execute(sa.text(
                "INSERT INTO roles (id, name, description, permissions, is_system, organization_id, created_at) "
                "SELECT uuid_generate_v4(), name, description, permissions, false, :org, created_at "
                "FROM roles WHERE id = :rid RETURNING id"
            ), {'org': org_id, 'rid': role_id}).scalar()
            bind.execute(sa.text(
                "UPDATE user_roles SET role_id = :new WHERE role_id = :rid "
                "AND user_id IN (SELECT id FROM users WHERE organization_id = :org)"
            ), {'new': new_id, 'rid': role_id, 'org': org_id})


def _dedupe_names(bind):
    """Old UNIQUE(name) was case-sensitive; the new indexes are not."""
    dups = bind.execute(sa.text(
        "SELECT id, name, rn FROM ("
        "  SELECT id, name, row_number() OVER (PARTITION BY organization_id, lower(name)"
        "                                      ORDER BY is_system DESC, created_at NULLS LAST, id) AS rn"
        "  FROM roles WHERE organization_id IS NOT NULL) t WHERE rn > 1"
    )).fetchall()
    for role_id, name, rn in dups:
        bind.execute(sa.text("UPDATE roles SET name = :name WHERE id = :rid"),
                     {'name': f'{name[:90]} ({rn})', 'rid': role_id})


def upgrade():
    bind = op.get_bind()

    # 1. Org column.
    if not _column_exists('roles', 'organization_id'):
        op.add_column('roles', sa.Column(
            'organization_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='CASCADE', name='roles_organization_id_fkey'),
            nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS idx_roles_org ON roles (organization_id)")

    # 2-3. Re-home custom roles, then swap the global unique name constraint.
    op.execute("ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_name_key")
    _rehome_custom_roles(bind)
    _dedupe_names(bind)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_roles_system_name ON roles (lower(name)) "
               "WHERE organization_id IS NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_roles_org_name ON roles (organization_id, lower(name)) "
               "WHERE organization_id IS NOT NULL")

    # 4. Permission data (idempotent).
    for role, keys in SYSTEM_GRANTS.items():
        _grant(_SYSTEM, keys, role=role)
    for trigger, keys in CUSTOM_BACKFILL:
        _grant(f"{_CUSTOM} AND permissions @> jsonb_build_array(CAST(:trigger AS text))", keys, trigger=trigger)
    _revoke("true", ['incidents:delete'])

    # 5. Existing installs keep registration open; fresh installs (no default
    #    org yet) get the new closed-by-default behaviour.
    op.execute(
        "UPDATE organizations SET settings = coalesce(settings, '{}'::jsonb) || '{\"registration_enabled\": true}'::jsonb "
        "WHERE slug = 'default' AND NOT coalesce(settings, '{}'::jsonb) ? 'registration_enabled'"
    )


def downgrade():
    bind = op.get_bind()

    # Reverse step 4. Backfilled keys that existed before this revision
    # (users:create/delete, teams:*) stay; custom roles do not regain
    # incidents:delete (lossy, documented).
    _revoke("true", NEW_KEYS)
    _grant(_SYSTEM, ['incidents:delete'], role='Administrator')

    # Reverse steps 1-3: make names globally unique again, restore UNIQUE(name).
    op.execute("DROP INDEX IF EXISTS uq_roles_org_name")
    op.execute("DROP INDEX IF EXISTS uq_roles_system_name")
    if _column_exists('roles', 'organization_id'):
        dups = bind.execute(sa.text(
            "SELECT r.id, r.name, coalesce(o.slug, r.id::text) FROM roles r "
            "LEFT JOIN organizations o ON o.id = r.organization_id "
            "WHERE r.organization_id IS NOT NULL AND EXISTS ("
            "  SELECT 1 FROM roles r2 WHERE r2.name = r.name AND r2.id <> r.id"
            "  AND (r2.organization_id IS NULL OR r2.created_at < r.created_at"
            "       OR (r2.created_at = r.created_at AND r2.id < r.id)))"
        )).fetchall()
        for role_id, name, slug in dups:
            bind.execute(sa.text("UPDATE roles SET name = :name WHERE id = :rid"),
                         {'name': f'{name[:60]} ({slug[:36]})', 'rid': role_id})
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roles_name_key') THEN
                ALTER TABLE roles ADD CONSTRAINT roles_name_key UNIQUE (name);
            END IF;
        END $$;
    """)
    op.execute("DROP INDEX IF EXISTS idx_roles_org")
    if _column_exists('roles', 'organization_id'):
        op.drop_column('roles', 'organization_id')
