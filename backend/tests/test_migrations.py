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

EXPECTED_HEAD = 'surface_dfir_prefs_reports'
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
