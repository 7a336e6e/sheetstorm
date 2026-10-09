"""Permission catalog consistency (admin guardrails §6.1).

The catalog in app/permissions.py is the single source of truth: code may
only enforce catalog keys, never a role name, and the seeded system roles
must equal SYSTEM_ROLE_PERMISSIONS (_integration.md §3).
"""
import os
import re

import pytest
from sqlalchemy import text

from app.permissions import (
    ADMIN_CORE, PERMISSION_KEYS, PERMISSIONS_BY_KEY, SYSTEM_ROLE_PERMISSIONS, api_key_grantable_keys,
    is_privileged, unknown_permissions,
)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BACKEND_DIR, 'app')

_CHECK_CALL = re.compile(
    r'(?:require_permission|require_incident_access|require_any_permission|require_all_permissions|'
    r'has_permission|has_any_permission|has_all_permissions|check_permission|check_any_permission)'
    r'\(([^)]*)\)')
_KEY = re.compile(r"""['"]([a-z_]+:[a-z_]+)['"]""")
_ROLE_NAME_AUTHZ = re.compile(
    r"""has_role\(|require_role|incident_access_tier|"""
    r"""Role\.name\s*==\s*['"]|"""
    r"""==\s*['"](?:Administrator|Incident Responder|Analyst|Manager|Operator|Viewer)['"]""")


def _py_files(*dirs):
    for d in dirs:
        for root, _, files in os.walk(os.path.join(APP_DIR, d)):
            for name in files:
                if name.endswith('.py'):
                    path = os.path.join(root, name)
                    with open(path, encoding='utf-8') as fh:
                        yield path, fh.read()


def test_every_enforced_permission_is_in_catalog():
    enforced = {}
    for path, src in _py_files('.'):
        for call in _CHECK_CALL.finditer(src):
            for key in _KEY.findall(call.group(1)):
                enforced.setdefault(key, path)
    assert enforced, 'scanner found no permission checks'
    unknown = {k: v for k, v in enforced.items() if k not in PERMISSION_KEYS}
    assert not unknown, f'permissions enforced but missing from app/permissions.py: {unknown}'


def test_no_role_name_authorization():
    offenders = [f'{os.path.relpath(p, BACKEND_DIR)}: {m.group(0)}'
                 for p, src in _py_files('api', 'middleware', 'services')
                 for m in _ROLE_NAME_AUTHZ.finditer(src)]
    assert not offenders, offenders


def test_frontend_permission_strings_in_catalog():
    src_dir = os.path.join(os.path.dirname(BACKEND_DIR), 'frontend', 'src')
    if not os.path.isdir(src_dir):
        pytest.skip('frontend sources not present (backend-only test container)')
    pattern = re.compile(r"""(?:hasPermission|hasAnyPermission|usePermission|anyOf)\W{0,3}['"]([a-z_]+:[a-z_]+)['"]""")
    found = set()
    for root, _, files in os.walk(src_dir):
        for name in files:
            if name.endswith(('.ts', '.tsx')):
                with open(os.path.join(root, name), encoding='utf-8') as fh:
                    found.update(pattern.findall(fh.read()))
    assert not (found - PERMISSION_KEYS)


def test_system_roles_match_registry(app, db):
    rows = db.session.execute(text(
        "SELECT name, permissions FROM roles WHERE is_system AND organization_id IS NULL")).all()
    assert {name: sorted(perms) for name, perms in rows} == SYSTEM_ROLE_PERMISSIONS


def test_catalog_flags_match_integration_plan():
    flags = lambda k: PERMISSIONS_BY_KEY[k]  # noqa: E731
    assert flags('incidents:purge').dangerous and flags('incidents:purge').privileged
    assert flags('system:manage').platform_only and not flags('system:manage').api_key_grantable
    for key in ('decisions:approve', 'response_actions:authorize', 'decisions:read_privileged',
                'api_keys:own', 'api_keys:manage', 'users:create', 'users:delete', 'users:manage',
                'users:update', 'roles:manage', 'organizations:manage', 'admin:manage'):
        assert key not in api_key_grantable_keys(), key
    for key in ('artifacts:delete', 'compromised_accounts:reveal', 'incidents:export', 'audit_logs:export'):
        assert flags(key).dangerous, key
    assert 'incidents:delete' not in PERMISSION_KEYS
    assert ADMIN_CORE == {'users:manage', 'roles:manage'}
    assert unknown_permissions(['incidents:read', 'incidents:nuke', 'incidents:nuke']) == ['incidents:nuke']
    assert is_privileged(['roles:manage']) and not is_privileged(['incidents:read'])


def test_every_system_role_permission_is_catalogued():
    for name, perms in SYSTEM_ROLE_PERMISSIONS.items():
        assert not unknown_permissions(perms), name


def test_get_permissions_shape(app, users, auth):
    resp = auth(users['Viewer']).get('/api/v1/permissions')
    assert resp.status_code == 200
    body = resp.get_json()
    assert {g['key'] for g in body['groups']} >= {'incidents', 'users', 'knowledge_base'}
    items = {i['key']: i for i in body['items']}
    assert set(items) == PERMISSION_KEYS
    for item in items.values():
        assert {'key', 'group', 'label', 'description', 'dangerous'} <= set(item)
    assert items['roles:manage']['dangerous'] is True
    assert items['admin:manage']['group'] == 'knowledge_base'


def test_get_permissions_requires_auth(app):
    assert app.test_client().get('/api/v1/permissions').status_code == 401
