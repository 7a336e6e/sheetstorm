"""Item 1: the Alembic chain is linear and works on a fresh install
(database/init SQL + full `flask db upgrade`), survives a downgrade to
a1b2c3d4e5f6 and re-upgrade, and is a no-op on a DB already at head."""
import glob
import os
import subprocess
import sys
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text

EXPECTED_HEAD = 'admin_guardrails_rbac'
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_single_head_in_script_directory():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config()
    cfg.set_main_option('script_location', os.path.join(BACKEND_DIR, 'migrations'))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == [EXPECTED_HEAD]


def test_session_database_is_at_head(app, db):
    rev = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar()
    assert rev == EXPECTED_HEAD


def test_admin_manage_granted_and_custody_column(app, db):
    perms = db.session.execute(text("SELECT permissions FROM roles WHERE name='Administrator'")).scalar()
    assert 'admin:manage' in perms
    cols = db.session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='chain_of_custody'"
    )).scalars().all()
    assert 'signature_key_id' in cols


@pytest.fixture
def scratch_db():
    """A brand-new database built only from database/init/*.sql."""
    init_dir = os.environ.get('DB_INIT_DIR')
    if not init_dir:
        pytest.skip('DB_INIT_DIR not set')
    base = urlparse(os.environ['TEST_DATABASE_URL'])
    name = base.path.lstrip('/') + '_mig'
    admin = create_engine(urlunparse(base), isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = urlunparse(base._replace(path='/' + name))
    eng = create_engine(url)
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for path in sorted(glob.glob(os.path.join(init_dir, '*.sql'))):
            with open(path, encoding='utf-8') as fh:
                cur.execute(fh.read())
        raw.commit()
    finally:
        raw.close()
        eng.dispose()
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _flask_db(url, *args):
    env = dict(os.environ, TEST_DATABASE_URL=url, FLASK_APP="app:create_app('testing')")
    return subprocess.run([sys.executable, '-m', 'flask', 'db', *args], cwd=BACKEND_DIR,
                          env=env, capture_output=True, text=True, timeout=300)


def _current(url):
    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            return conn.execute(text('SELECT version_num FROM alembic_version')).scalar()
    finally:
        eng.dispose()


def test_fresh_install_upgrade_downgrade_upgrade(scratch_db):
    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _current(scratch_db) == EXPECTED_HEAD

    # Already at head: upgrade again is a clean no-op.
    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]

    r = _flask_db(scratch_db, 'downgrade', 'a1b2c3d4e5f6')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _current(scratch_db) == 'a1b2c3d4e5f6'

    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _current(scratch_db) == EXPECTED_HEAD

    r = _flask_db(scratch_db, 'heads')
    assert r.returncode == 0
    assert [ln for ln in r.stdout.splitlines() if ln.strip()] == [f'{EXPECTED_HEAD} (head)']


# ── admin_guardrails_rbac ───────────────────────────────────────────

def test_roles_org_column_and_partial_unique_indexes(app, db):
    cols = db.session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='roles'")).scalars().all()
    assert 'organization_id' in cols
    idx = dict(db.session.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='roles'")).all())
    assert 'WHERE (organization_id IS NULL)' in idx['uq_roles_system_name']
    assert 'lower' in idx['uq_roles_org_name'] and 'WHERE (organization_id IS NOT NULL)' in idx['uq_roles_org_name']
    assert not db.session.execute(text(
        "SELECT 1 FROM pg_constraint WHERE conname='roles_name_key'")).first()


def test_guardrails_permission_backfill(app, db):
    perms = dict(db.session.execute(text(
        "SELECT name, permissions FROM roles WHERE is_system AND organization_id IS NULL")).all())
    assert {'incidents:archive', 'incidents:purge', 'incidents:read_all', 'case_notes:delete'} <= set(perms['Administrator'])
    assert 'incidents:read_tlp_white' in perms['Viewer']
    assert 'incidents:read_all' in perms['Manager']
    assert 'incidents:read_team' in perms['Analyst'] and 'incidents:read_team' in perms['Incident Responder']
    assert not any('incidents:delete' in p for p in perms.values())


def _seed_legacy_roles(url):
    """At custody_key_id_admin_perm: 3 orgs, global custom roles in use."""
    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            def q(sql, **kw):
                return conn.execute(text(sql), kw)
            orgs = {}
            for i, slug in enumerate(('default', 'org-x', 'org-y')):
                orgs[slug] = q("INSERT INTO organizations (name, slug, settings, created_at) "
                               "VALUES (:s, :s, '{}', now() + make_interval(secs => :i)) RETURNING id",
                               s=slug, i=i).scalar()
            users = {}
            for slug in ('org-x', 'org-y'):
                users[slug] = q("INSERT INTO users (organization_id, email, name) VALUES (:o, :e, 'u') RETURNING id",
                                o=orgs[slug], e=f'u@{slug}.test').scalar()
            roles = {}
            for name, perms in (
                ('Shared Hunters', '["incidents:read", "incidents:delete", "users:manage", "users:read",'
                                   ' "incidents:create", "reports:generate"]'),
                ('Lonely', '["tasks:read"]'),
                ('Only X', '["incidents:read"]'),
            ):
                roles[name] = q("INSERT INTO roles (name, permissions, is_system) "
                                "VALUES (:n, CAST(:p AS jsonb), false) RETURNING id", n=name, p=perms).scalar()
            for slug in ('org-x', 'org-y'):
                q("INSERT INTO user_roles (user_id, role_id, organization_id) VALUES (:u, :r, :o)",
                  u=users[slug], r=roles['Shared Hunters'], o=orgs[slug])
            q("INSERT INTO user_roles (user_id, role_id, organization_id) VALUES (:u, :r, :o)",
              u=users['org-x'], r=roles['Only X'], o=orgs['org-x'])
            before = dict(conn.execute(text("SELECT name, permissions FROM roles")).all())
        return orgs, users, before
    finally:
        eng.dispose()


def test_custom_roles_rehomed_split_and_access_preserved(scratch_db):
    r = _flask_db(scratch_db, 'upgrade', 'custody_key_id_admin_perm')
    assert r.returncode == 0, r.stderr[-3000:]
    orgs, users, before = _seed_legacy_roles(scratch_db)
    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]

    eng = create_engine(scratch_db)
    try:
        with eng.connect() as conn:
            by_name = {}
            for rid, name, org_id, perms in conn.execute(text(
                    "SELECT id, name, organization_id, permissions FROM roles")).all():
                by_name.setdefault(name, []).append((str(rid), org_id, set(perms)))
            # The shared role is split into one row per org and user_roles are repointed.
            shared = by_name['Shared Hunters']
            assert sorted(str(o) for _, o, _ in shared) == sorted(str(orgs[s]) for s in ('org-x', 'org-y'))
            owner = {rid: org for rid, org, _ in shared}
            for slug in ('org-x', 'org-y'):
                rid = conn.execute(text(
                    "SELECT ur.role_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                    "WHERE ur.user_id = :u AND r.name = 'Shared Hunters'"), {'u': users[slug]}).scalar()
                assert owner[str(rid)] == orgs[slug]
            assert by_name['Only X'][0][1] == orgs['org-x']
            assert by_name['Lonely'][0][1] == orgs['default']  # unused -> default org
            # Effective access preserved (only incidents:delete is dropped) + backfills.
            for name, old in before.items():
                for _, _, new in by_name[name]:
                    assert set(old) - {'incidents:delete'} <= new, name
                    assert 'incidents:delete' not in new
            hunters = shared[0][2]
            assert {'incidents:read_team', 'decisions:read', 'response_actions:read', 'improvements:read',
                    'users:create', 'users:delete', 'teams:create', 'teams:update', 'teams:delete',
                    'teams:read', 'templates:manage', 'incidents:export'} <= hunters
            assert 'incidents:archive' not in hunters and 'system:manage' not in hunters
            assert by_name['Lonely'][0][2] == {'tasks:read'}
            # The existing default org keeps registration open.
            settings = conn.execute(text("SELECT settings FROM organizations WHERE slug='default'")).scalar()
            assert settings['registration_enabled'] is True
    finally:
        eng.dispose()

    # Lossy but clean downgrade: global UNIQUE(name) restored over the split rows.
    r = _flask_db(scratch_db, 'downgrade', 'custody_key_id_admin_perm')
    assert r.returncode == 0, r.stderr[-3000:]
    eng = create_engine(scratch_db)
    try:
        with eng.connect() as conn:
            names = conn.execute(text("SELECT name FROM roles WHERE name LIKE 'Shared Hunters%'")).scalars().all()
            assert len(names) == 2 and len(set(names)) == 2
            admin = conn.execute(text("SELECT permissions FROM roles WHERE name='Administrator'")).scalar()
            assert 'incidents:delete' in admin and 'incidents:archive' not in admin
    finally:
        eng.dispose()
