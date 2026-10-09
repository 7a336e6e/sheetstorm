"""Audit governance fixtures: isolated audit chains, row writers and tamper
helpers (the append-only trigger must be disabled to tamper)."""
import uuid
from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import text


@pytest.fixture
def audit_org(app, db):
    """audit_org(**settings) -> a fresh Organization with its own audit chain.

    Its audit rows and chain head are removed after the test (with the purge
    GUC), so tampered or purged chains never leak into other tests.
    """
    from app.models import Organization
    created = []

    def make(**settings):
        org = Organization(name='audit test', slug=f'aud-{uuid.uuid4().hex[:10]}', settings=settings)
        db.session.add(org)
        db.session.commit()
        created.append(org.id)
        return org

    yield make
    db.session.rollback()
    for org_id in created:
        db.session.execute(text("SELECT set_config('sheetstorm.audit_purge', 'on', true)"))
        db.session.execute(text('DELETE FROM audit_logs WHERE organization_id = :o'), {'o': org_id})
        db.session.execute(text('DELETE FROM ledger_heads WHERE chain_key = :k'), {'k': f'audit:{org_id}'})
        db.session.commit()


@contextmanager
def _frozen_audit_clock(at):
    """Make _write_audit_row stamp ``at`` as created_at."""
    import app.middleware.audit as mw
    real = mw.datetime

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    mw.datetime = _Frozen
    try:
        yield
    finally:
        mw.datetime = real


@pytest.fixture
def write_audit_rows(app):
    """write_audit_rows(org, n=1, *, at=None, **fields) -> [AuditLog]

    Writes through the single writer (chained). ``at`` backdates created_at.
    Defaults: event_type system_event, action 'test_row', details {'i': n}.
    """
    def write(org, n=1, *, at=None, **fields):
        from app.middleware.audit import _write_audit_row
        rows = []
        fields.setdefault('event_type', 'system_event')
        fields.setdefault('action', 'test_row')
        ctx = _frozen_audit_clock(at) if at else _noop()
        with ctx:
            for i in range(n):
                row_fields = dict(fields)
                row_fields.setdefault('details', {'i': i})
                rows.append(_write_audit_row(organization_id=org.id if org is not None else None,
                                             **row_fields))
        return rows
    return write


@contextmanager
def _noop():
    yield


@pytest.fixture
def audit_tamper(db):
    """audit_tamper(sql, params) runs ``sql`` with the append-only row trigger
    disabled (as an attacker with table-owner rights could), in one
    transaction, then re-enables it."""
    def run(sql, params=None):
        db.session.rollback()
        db.session.execute(text("SET LOCAL lock_timeout = '10s'"))
        db.session.execute(text('ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only_row'))
        db.session.execute(text(sql), params or {})
        db.session.execute(text('ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_append_only_row'))
        db.session.commit()
    return run
