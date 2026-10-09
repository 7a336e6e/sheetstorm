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

EXPECTED_HEAD = 'evidence_register_ledger'
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


# ── audit_governance ────────────────────────────────────────────────

def test_audit_governance_schema_at_head(app, db):
    fks = db.session.execute(text(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'audit_logs'::regclass AND contype = 'f'")).all()
    assert fks == []
    triggers = set(db.session.execute(text(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit_logs'::regclass AND NOT tgisinternal")).scalars())
    assert {'audit_logs_append_only_row', 'audit_logs_append_only_truncate'} <= triggers
    cols = set(db.session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='audit_logs'")).scalars())
    assert {'chain_seq', 'prev_hash', 'row_hash', 'chain_key_id'} <= cols
    assert db.session.execute(text("SELECT to_regclass('ledger_heads')")).scalar() == 'ledger_heads'
    idx = set(db.session.execute(text("SELECT indexname FROM pg_indexes WHERE tablename='audit_logs'")).scalars())
    assert {'uq_audit_org_seq', 'idx_audit_org_created_id', 'idx_audit_org_user_created',
            'idx_audit_org_event_created'} <= idx
    icols = set(db.session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='integrations'")).scalars())
    assert {'last_tested_at', 'last_test_ok'} <= icols


def test_audit_governance_round_trip_with_data(scratch_db):
    r = _flask_db(scratch_db, 'upgrade', 'realtime_versions')
    assert r.returncode == 0, r.stderr[-3000:]
    eng = create_engine(scratch_db)
    try:
        with eng.begin() as conn:
            org = conn.execute(text("INSERT INTO organizations (name, slug, settings) "
                                    "VALUES ('o', 'o', '{}') RETURNING id")).scalar()
            conn.execute(text("INSERT INTO audit_logs (organization_id, event_type, action) "
                              "VALUES (:o, 'system_event', 'legacy')"), {'o': org})
    finally:
        eng.dispose()

    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    eng = create_engine(scratch_db)
    try:
        with eng.begin() as conn:
            # A chained-looking row with a dangling user id (no FK any more).
            conn.execute(text("INSERT INTO audit_logs (organization_id, user_id, event_type, action, chain_seq, "
                              "prev_hash, row_hash) VALUES (:o, :u, 'system_event', 'new', 1, 'p', 'h')"),
                         {'o': org, 'u': '00000000-0000-0000-0000-0000000000ff'})
        with eng.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM audit_logs WHERE chain_seq IS NULL")).scalar() == 1
    finally:
        eng.dispose()

    # Down: triggers dropped first, FKs come back NOT VALID despite the dangling id.
    r = _flask_db(scratch_db, 'downgrade', 'realtime_versions')
    assert r.returncode == 0, r.stderr[-3000:]
    eng = create_engine(scratch_db)
    try:
        with eng.connect() as conn:
            fks = dict(conn.execute(text(
                "SELECT conname, convalidated FROM pg_constraint "
                "WHERE conrelid = 'audit_logs'::regclass AND contype = 'f'")).all())
            assert set(fks) == {'audit_logs_organization_id_fkey', 'audit_logs_user_id_fkey',
                                'audit_logs_incident_id_fkey'}
            assert conn.execute(text("SELECT to_regclass('ledger_heads')")).scalar() is None
            assert conn.execute(text("SELECT count(*) FROM audit_logs")).scalar() == 2
    finally:
        eng.dispose()

    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _current(scratch_db) == EXPECTED_HEAD


# ── evidence_register_ledger (W1-EVD-CORE) ─────────────────────────────────

def _seed_legacy_evidence(url, key):
    """At realtime_versions: 2 incidents, 3 artifacts, v2-signed legacy custody rows."""
    import uuid
    from datetime import datetime, timedelta, timezone
    from app.models import ChainOfCustody
    from app.models.artifact import custody_key_id

    eng = create_engine(url)
    t0 = datetime(2026, 3, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
    try:
        with eng.begin() as conn:
            def q(sql, **kw):
                return conn.execute(text(sql), kw)
            org = q("INSERT INTO organizations (name, slug, settings) VALUES ('ev', 'ev-org', '{}') RETURNING id").scalar()
            user = q("INSERT INTO users (organization_id, email, name) VALUES (:o, 'ev@x.test', 'ev') RETURNING id",
                     o=org).scalar()
            incs = [q("INSERT INTO incidents (organization_id, title, severity, status, phase, created_by) "
                      "VALUES (:o, :t, 'high', 'open', 1, :u) RETURNING id", o=org, t=f'inc{i}', u=user).scalar()
                    for i in range(2)]
            arts = []
            # Inserted out of order: numbering must follow created_at, not insert order.
            for inc, offset, name in ((incs[0], 2, 'second.e01'), (incs[0], 1, 'first.raw'), (incs[1], 0, 'other.bin')):
                aid = q("INSERT INTO artifacts (incident_id, filename, original_filename, storage_path, storage_type, "
                        "file_size, md5, sha256, sha512, uploaded_by, created_at, source_host, acquisition_tool) "
                        "VALUES (:i, 'f', :n, 'p', 'local', 1, :md5, :sha256, :sha512, :u, :ts, 'WS-01', 'FTK') "
                        "RETURNING id", i=inc, n=name, md5='A' * 32, sha256='b' * 64, sha512='c' * 128, u=user,
                        ts=t0 + timedelta(minutes=offset)).scalar()
                arts.append((aid, inc, name))
            rows = []
            for n, (aid, inc, _) in enumerate(arts):
                for k, action in enumerate(('upload', 'download')):
                    ts = t0 + timedelta(hours=1, minutes=n * 10 + k)
                    row = ChainOfCustody(id=uuid.uuid4(), artifact_id=aid, action=action, performed_by=user,
                                         ip_address='10.0.0.5', user_agent='ua', purpose='p',
                                         verification_result=None, extra_data={'k': n}, created_at=ts)
                    sig = ChainOfCustody._hmac(key, row._payload_v2())
                    q("INSERT INTO chain_of_custody (id, artifact_id, action, performed_by, ip_address, user_agent, "
                      "purpose, extra_data, signature, signature_key_id, created_at) VALUES "
                      "(:id, :a, :act, :u, '10.0.0.5', 'ua', 'p', CAST(:ed AS jsonb), :s, :kid, :ts)",
                      id=row.id, a=aid, act=action, u=user, ed=f'{{"k": {n}}}', s=sig, kid=custody_key_id(key), ts=ts)
                    rows.append(row.id)
        return {'user': user, 'incidents': incs, 'artifacts': arts, 'custody_ids': rows}
    finally:
        eng.dispose()


def test_evidence_register_backfill_round_trip(app, scratch_db):
    import uuid
    from app.models import ChainOfCustody
    key = app.config['CUSTODY_SIGNING_KEY']

    r = _flask_db(scratch_db, 'upgrade', 'realtime_versions')
    assert r.returncode == 0, r.stderr[-3000:]
    seed = _seed_legacy_evidence(scratch_db, key)
    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]

    eng = create_engine(scratch_db)
    try:
        with eng.begin() as conn:
            items = conn.execute(text(
                "SELECT a.original_filename, e.sequence_number, e.incident_id, e.evidence_type, e.title, "
                "e.created_by, e.source_host_label, e.acquisition_tool, e.acquisition_hashes, e.organization_id "
                "FROM artifacts a JOIN evidence_items e ON e.id = a.evidence_item_id")).mappings().all()
            by_name = {i['original_filename']: i for i in items}
            assert len(items) == 3
            assert by_name['first.raw']['sequence_number'] == 1 and by_name['second.e01']['sequence_number'] == 2
            assert by_name['other.bin']['sequence_number'] == 1
            first = by_name['first.raw']
            assert first['evidence_type'] == 'digital_file' and first['title'] == 'first.raw'
            assert first['created_by'] == seed['user'] and first['source_host_label'] == 'WS-01'
            assert first['acquisition_tool'] == 'FTK'
            hashes = {h['algorithm']: h for h in first['acquisition_hashes']}
            assert hashes['md5']['value'] == 'a' * 32 and hashes['sha512']['source'] == 'computed_on_upload'

            custody = conn.execute(text(
                "SELECT c.*, a.evidence_item_id AS art_item, a.incident_id AS art_inc FROM chain_of_custody c "
                "JOIN artifacts a ON a.id = c.artifact_id")).mappings().all()
            assert len(custody) == 6
            for row in custody:
                assert row['evidence_item_id'] == row['art_item'] and row['incident_id'] == row['art_inc']
                assert row['chain_version'] is None
                cols = {c.name for c in ChainOfCustody.__table__.columns}
                legacy = ChainOfCustody(**{k: v for k, v in row.items() if k in cols})
                assert legacy.signature_status(key) == 'valid'  # legacy signatures survive the backfill

            triggers = conn.execute(text(
                "SELECT tgname FROM pg_trigger WHERE tgname IN "
                "('coc_append_only','coc_no_truncate','anchors_append_only','anchors_no_truncate')")).scalars().all()
            assert sorted(triggers) == ['anchors_append_only', 'anchors_no_truncate', 'coc_append_only',
                                        'coc_no_truncate']
            deltype = conn.execute(text(
                "SELECT confdeltype FROM pg_constraint WHERE conname = 'fk_custody_artifact'")).scalar()
            assert deltype == 'a'  # NO ACTION (was CASCADE)
            for table, col in (('artifacts', 'evidence_item_id'), ('chain_of_custody', 'evidence_item_id'),
                               ('chain_of_custody', 'incident_id')):
                nullable = conn.execute(text(
                    "SELECT is_nullable FROM information_schema.columns WHERE table_name=:t AND column_name=:c"),
                    {'t': table, 'c': col}).scalar()
                assert nullable == 'NO', (table, col)

            # Rows the downgrade must drop: one v3 entry and one tombstoned artifact.
            aid, inc, _ = seed['artifacts'][2]
            item = conn.execute(text('SELECT evidence_item_id FROM artifacts WHERE id=:a'), {'a': aid}).scalar()
            conn.execute(text(
                "INSERT INTO chain_of_custody (id, artifact_id, evidence_item_id, incident_id, action, performed_by, "
                "seq, incident_seq, prev_hash, incident_prev_hash, entry_hash, chain_version, created_at) VALUES "
                "(:id, NULL, :e, :i, 'register', :u, 1, 1, :h, :h, :h, 3, now())"),
                {'id': uuid.uuid4(), 'e': item, 'i': inc, 'u': seed['user'], 'h': '0' * 64})
            conn.execute(text('UPDATE artifacts SET deleted_at = now() WHERE id=:a'), {'a': aid})
    finally:
        eng.dispose()

    r = _flask_db(scratch_db, 'downgrade', 'realtime_versions')
    assert r.returncode == 0, r.stderr[-3000:]
    eng = create_engine(scratch_db)
    try:
        with eng.connect() as conn:
            assert not conn.execute(text("SELECT to_regclass('evidence_items')")).scalar()
            cols = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='chain_of_custody'")).scalars().all()
            assert 'chain_version' not in cols and 'evidence_item_id' not in cols
            # Lossy: the tombstoned artifact and its rows are gone; the v3 row is gone.
            assert conn.execute(text('SELECT count(*) FROM artifacts')).scalar() == 2
            assert conn.execute(text('SELECT count(*) FROM chain_of_custody')).scalar() == 4
            deltype = conn.execute(text(
                "SELECT confdeltype FROM pg_constraint WHERE conname = 'chain_of_custody_artifact_id_fkey'")).scalar()
            assert deltype == 'c'
    finally:
        eng.dispose()

    r = _flask_db(scratch_db, 'upgrade')
    assert r.returncode == 0, r.stderr[-3000:]
    assert _current(scratch_db) == EXPECTED_HEAD
