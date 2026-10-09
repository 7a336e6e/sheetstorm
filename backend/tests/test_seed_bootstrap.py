"""Seed bootstrap (owner decision, W1-LIFE-BE): no well-known admin password.

The generated password never leaves this process: the announce hook is
captured and nothing is printed (a failing assertion only shows booleans).
"""
import os
import uuid

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(BACKEND_DIR)


@pytest.fixture
def seed_env(app, db, monkeypatch):
    """Run app.seed._run_seed in a fresh org slug with a unique admin email."""
    from app import seed
    from app.models import Organization, User
    slug = f'seed-{uuid.uuid4().hex[:8]}'
    email = f'seed-admin-{uuid.uuid4().hex[:8]}@seed.test'
    monkeypatch.setenv('ADMIN_EMAIL', email)
    announced = []
    monkeypatch.setattr(seed, '_announce_generated_password', lambda e, p: announced.append((e, p)))
    printed = []
    monkeypatch.setattr('builtins.print', lambda *a, **k: printed.append(' '.join(str(x) for x in a)))
    yield seed, slug, email, announced, printed
    monkeypatch.undo()
    u = User.query.filter_by(email=email).first()
    if u:
        db.session.delete(u)  # cascades user_roles
    Organization.query.filter_by(slug=slug).delete()
    db.session.commit()


def test_seed_without_env_generates_password_and_forces_change(app, db, monkeypatch, seed_env):
    from app.api.v1.endpoints.auth import validate_password
    seed, slug, email, announced, printed = seed_env
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    admin = seed._run_seed(org_slug=slug)
    assert admin is not None and admin.must_change_password is True
    assert admin.role_names == ['Administrator']
    count, announced_email = len(announced), announced[0][0] if announced else None
    assert count == 1 and announced_email == email
    password = announced[0][1]
    checks = {
        'policy': validate_password(password)[0],
        'long': len(password) >= 20,
        'not_default': password != 'ChangeMe123!',
        'not_printed': not any(password in line for line in printed),
        'hashed': admin.check_password(password) and password not in (admin.password_hash or ''),
    }
    assert all(checks.values()), [k for k, v in checks.items() if not v]

    client = app.test_client()
    login = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert login.status_code == 200 and login.get_json()['user']['must_change_password'] is True
    resp = client.get('/api/v1/incidents', headers={'Authorization': f"Bearer {login.get_json()['access_token']}"})
    assert resp.status_code == 403 and resp.get_json()['error'] == 'password_change_required'


def test_seed_with_env_password_still_forces_change(app, monkeypatch, seed_env):
    seed, slug, email, announced, _ = seed_env
    monkeypatch.setenv('ADMIN_PASSWORD', 'Op3rator-Chosen-Pass!')
    admin = seed._run_seed(org_slug=slug)
    count = len(announced)
    assert admin.must_change_password is True and count == 0
    assert admin.check_password('Op3rator-Chosen-Pass!')


def test_seed_weak_env_password_is_replaced(app, monkeypatch, seed_env):
    seed, slug, email, announced, _ = seed_env
    monkeypatch.setenv('ADMIN_PASSWORD', 'changeme')
    admin = seed._run_seed(org_slug=slug)
    count, kept_weak = len(announced), admin.check_password('changeme')
    assert count == 1 and kept_weak is False


def test_seed_is_idempotent(app, monkeypatch, seed_env):
    seed, slug, _, announced, _ = seed_env
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    assert seed._run_seed(org_slug=slug) is not None
    assert seed._run_seed(org_slug=slug) is None
    count = len(announced)
    assert count == 1


def test_seed_rerun_never_touches_an_existing_admin(app, db, monkeypatch, seed_env):
    """start.sh re-runs the seed on every start: on an existing install it must
    leave the admin's password, flags and roles exactly as the operator set them."""
    from app.models import User
    seed, slug, email, announced, _ = seed_env
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    admin = seed._run_seed(org_slug=slug)
    admin_id = admin.id
    # The operator has since changed the password and cleared the flag.
    admin.set_password('Operat0r-Own-Pass!')
    admin.must_change_password = False
    db.session.commit()
    before = (admin.password_hash, admin.must_change_password, admin.is_active, sorted(admin.role_names))

    for env_password in (None, 'An0ther-Valid-Pass!'):
        if env_password:
            monkeypatch.setenv('ADMIN_PASSWORD', env_password)
        assert seed._run_seed(org_slug=slug) is None
        db.session.expire_all()
        u = db.session.get(User, admin_id)
        after = (u.password_hash, u.must_change_password, u.is_active, sorted(u.role_names))
        unchanged, own_password_works = after == before, u.check_password('Operat0r-Own-Pass!')
        assert unchanged and own_password_works  # booleans only: no hash in a failure message
    count = len(announced)
    assert count == 1  # only the first (creating) run generated a password
    assert User.query.filter_by(email=email).count() == 1


def test_no_literal_default_admin_password():
    with open(os.path.join(BACKEND_DIR, 'app', 'seed.py'), encoding='utf-8') as fh:
        source = fh.read()
    assert 'ChangeMe123!' not in source
    assert "Updating Administrator permissions" not in source  # system roles are immutable
    compose = os.path.join(REPO_DIR, 'docker-compose.yml')
    env_example = os.path.join(REPO_DIR, '.env.example')
    if not os.path.exists(compose):
        pytest.skip('repo root files not present (backend-only test container)')
    with open(compose, encoding='utf-8') as fh:
        assert 'ADMIN_PASSWORD: ${ADMIN_PASSWORD:-}' in fh.read()
    with open(env_example, encoding='utf-8') as fh:
        lines = [ln.strip() for ln in fh if ln.strip().startswith('ADMIN_PASSWORD=')]
    assert lines == ['ADMIN_PASSWORD=']
