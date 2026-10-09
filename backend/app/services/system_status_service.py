"""Admin system status (``GET /admin/system-status``).

``collect_system_status(org, include_infra=...)`` returns:

* organization sections (any ``organizations:manage`` holder): ``storage``
  (backend only), ``ai_providers``, ``integrations``, ``counts``, ``audit``;
* deployment-global infra sections, only when ``include_infra`` (the caller
  is a platform admin): ``app`` (version / commit / environment),
  ``database``, ``alembic``, ``redis``, ``rate_limiting`` and the storage
  details (disk usage / S3 bucket + endpoint host).

Every probe is isolated: a failing probe reports ``{'ok': False, 'error':
<short code>}`` and never fails the request. No secret, credential or URL
with credentials is ever included.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import current_app
from sqlalchemy import func, text

from app import db

logger = logging.getLogger(__name__)

LAST_ERROR_MAX = 200

# ai_service provider name -> integration type
_AI_INTEGRATION_TYPES = {
    'openai': 'openai', 'google': 'google_ai', 'ollama': 'ollama', 'openai_compatible': 'openai_compatible',
}


def _probe(name, fn):
    try:
        return fn()
    except Exception:
        logger.warning('system status probe %s failed', name, exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            pass
        return {'ok': False, 'error': 'unavailable'}


def _iso(value):
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Infra (platform admins only)
# ---------------------------------------------------------------------------

def _app_info():
    app = current_app
    env = 'testing' if app.testing else ('development' if app.debug else 'production')
    return {
        'version': app.config.get('APP_VERSION') or None,
        'commit': app.config.get('GIT_COMMIT') or None,
        'environment': env,
    }


def _database():
    start = time.monotonic()
    db.session.execute(text('SELECT 1'))
    latency = round((time.monotonic() - start) * 1000, 2)
    version = db.session.execute(text('SHOW server_version')).scalar()
    return {'ok': True, 'latency_ms': latency, 'server_version': version}


def _alembic():
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    config = current_app.extensions['migrate'].migrate.get_config()
    head = sorted(ScriptDirectory.from_config(config).get_heads())
    conn = db.session.connection()
    current = sorted(MigrationContext.configure(conn).get_current_heads())
    return {'ok': True, 'current': current, 'head': head, 'up_to_date': current == head}


def _redis():
    import app as app_pkg
    client = app_pkg.redis_client
    if client is None:
        return {'ok': False, 'error': 'not_configured'}
    start = time.monotonic()
    client.ping()
    return {'ok': True, 'latency_ms': round((time.monotonic() - start) * 1000, 2)}


def _rate_limiting():
    from app import limiter
    uri = getattr(limiter, '_storage_uri', None) or ''
    scheme = (urlparse(uri).scheme or uri.split(':', 1)[0] or 'memory').lower()
    return {
        'enabled': bool(getattr(limiter, 'enabled', True)),
        'storage': 'redis' if scheme.startswith('redis') else scheme,
        'default_limit': os.getenv('RATE_LIMIT_DEFAULT', '600 per minute'),
    }


def _storage_infra(backend):
    cfg = current_app.config
    if backend == 's3':
        endpoint = cfg.get('S3_ENDPOINT') or ''
        return {'bucket': cfg.get('S3_BUCKET'), 'endpoint_host': urlparse(endpoint).hostname}
    if backend == 'local':
        path = cfg.get('LOCAL_ARTIFACT_DIR', '/app/artifacts')
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return {'disk': {'ok': False, 'error': 'unavailable'}}
        return {'disk': {'ok': True, 'total_bytes': usage.total, 'free_bytes': usage.free,
                         'used_pct': round(100 * (usage.total - usage.free) / usage.total, 1)
                         if usage.total else None}}
    return {}


# ---------------------------------------------------------------------------
# Organization sections
# ---------------------------------------------------------------------------

def _org_integrations(org):
    from app.models import Integration
    return Integration.query.filter_by(organization_id=org.id).order_by(Integration.type, Integration.name).all()


def _storage_backend(org, integrations):
    from app.services.storage_service import storage_service
    if storage_service.is_s3_configured:
        return 's3'
    if any(i.type == 'google_drive' and i.is_enabled for i in integrations):
        return 'google_drive'
    return 'local'


def _ai_providers(org, integrations):
    from app.services.ai_service import ai_service
    by_type = {}
    for i in integrations:
        if i.is_enabled:
            by_type.setdefault(i.type, i)
    out = []
    for provider in ai_service.get_available_providers(str(org.id)):
        row = by_type.get(_AI_INTEGRATION_TYPES.get(provider))
        out.append({
            'provider': provider,
            'source': 'integration' if row else 'env',
            'last_tested_at': _iso(row.last_tested_at) if row else None,
            'last_test_ok': row.last_test_ok if row else None,
        })
    return out


def _integrations(integrations):
    return [{
        'id': str(i.id),
        'type': i.type,
        'name': i.name,
        'is_enabled': bool(i.is_enabled),
        'last_tested_at': _iso(i.last_tested_at),
        'last_test_ok': i.last_test_ok,
        'last_used_at': _iso(i.last_used_at),
        'last_error': (i.last_error or '')[:LAST_ERROR_MAX] or None,
    } for i in integrations]


def _counts(org):
    from app.models import Artifact, Incident, User
    users_total = User.query.filter_by(organization_id=org.id).count()
    users_active = User.query.filter_by(organization_id=org.id, is_active=True).count()
    incidents = Incident.query.filter(Incident.organization_id == org.id)
    incidents_total = incidents.count()
    incidents_open = incidents.filter(Incident.status != 'closed',
                                      Incident.is_archived.isnot(True)).count()
    artifacts, artifact_bytes = (db.session.query(func.count(Artifact.id), func.coalesce(func.sum(Artifact.file_size), 0))
                                 .join(Incident, Incident.id == Artifact.incident_id)
                                 .filter(Incident.organization_id == org.id).one())
    return {
        'users': users_total, 'active_users': users_active,
        'incidents': incidents_total, 'open_incidents': incidents_open,
        'artifacts': int(artifacts or 0), 'artifact_bytes': int(artifact_bytes or 0),
    }


def _audit(org):
    from app.models import AuditLog
    from app.services import audit_service
    settings = audit_service.get_audit_settings(org)
    total, oldest = (db.session.query(func.count(AuditLog.id), func.min(AuditLog.created_at))
                     .filter(AuditLog.organization_id == org.id).one())
    legacy = (db.session.query(func.count(AuditLog.id))
              .filter(AuditLog.organization_id == org.id, AuditLog.chain_seq.is_(None)).scalar())
    chain = audit_service.chain_status(org.id)
    chain['legacy_unchained'] = int(legacy or 0)
    return {
        'retention_days': settings['audit_retention_days'],
        'legal_hold': settings['legal_hold'],
        'total_rows': int(total or 0),
        'oldest_entry_at': _iso(oldest),
        'chain': chain,
    }


def collect_system_status(org, *, include_infra: bool = False) -> dict:
    """Status sections for ``org``; infra sections only with ``include_infra``."""
    integrations = _probe('integrations_rows', lambda: _org_integrations(org))
    if isinstance(integrations, dict):  # probe failed
        integrations = []

    backend = _probe('storage', lambda: _storage_backend(org, integrations))
    storage = {'backend': backend} if isinstance(backend, str) else backend

    status = {
        'infra_visible': bool(include_infra),
        'storage': storage,
        'ai_providers': _probe('ai_providers', lambda: _ai_providers(org, integrations)),
        'integrations': _probe('integrations', lambda: _integrations(integrations)),
        'counts': _probe('counts', lambda: _counts(org)),
        'audit': _probe('audit', lambda: _audit(org)),
    }
    if include_infra:
        status['app'] = _probe('app', _app_info)
        status['database'] = _probe('database', _database)
        status['alembic'] = _probe('alembic', _alembic)
        status['redis'] = _probe('redis', _redis)
        status['rate_limiting'] = _probe('rate_limiting', _rate_limiting)
        if isinstance(backend, str):
            storage.update(_probe('storage_infra', lambda: _storage_infra(backend)))
    status['generated_at'] = datetime.now(timezone.utc).isoformat()
    return status


__all__ = ['collect_system_status']
