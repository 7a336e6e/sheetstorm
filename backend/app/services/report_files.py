"""Immutable report snapshots: storage, verification and purge
(surface-dfir §3.10; _integration C34).

A report is a snapshot of exactly what was issued: the PDF bytes are stored
once, under ``incidents/<incident_id>/reports/<report_id>.pdf``, with their
SHA-256 and size on the ``reports`` row. They are never regenerated in place;
downloads return the stored bytes after re-checking the hash.

Soft-deleting a report keeps its file. Files are removed only by the incident
purge: ``incident_purge`` step ``report_files`` collects every stored path
before the delete (``pre``) and removes the files after the commit
(``post_commit``), so a failed purge never loses a file.
"""
from __future__ import annotations

import hashlib
import io
import logging

from app.services.incident_purge import register_purge_step
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


class SnapshotError(Exception):
    """The snapshot could not be stored."""


class SnapshotIntegrityError(Exception):
    """The stored snapshot is missing or its SHA-256 no longer matches."""

    def __init__(self, reason, expected=None, actual=None):
        super().__init__(reason)
        self.reason, self.expected, self.actual = reason, expected, actual


def snapshot_path(incident_id, report_id) -> str:
    return f'incidents/{incident_id}/reports/{report_id}.pdf'


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_snapshot(report) -> bool:
    return bool(report.storage_path and report.sha256)


def store_snapshot(report, pdf_bytes: bytes) -> None:
    """Store ``pdf_bytes`` for ``report`` (already flushed, so it has an id)
    and fill ``storage_path`` / ``storage_type`` / ``sha256`` / ``size_bytes``.
    Raises ``SnapshotError``; the caller rolls back so no half-issued report
    row exists."""
    path = snapshot_path(report.incident_id, report.id)
    ok, storage_type = storage_service.store_file(io.BytesIO(pdf_bytes), path, 'application/pdf')
    if not ok:
        raise SnapshotError('report snapshot could not be stored')
    report.storage_path = path
    report.storage_type = storage_type
    report.sha256 = sha256_hex(pdf_bytes)
    report.size_bytes = len(pdf_bytes)


def load_snapshot(report) -> bytes:
    """The stored bytes, verified against ``report.sha256``
    (``SnapshotIntegrityError`` when missing or altered)."""
    handle = storage_service.retrieve_file(report.storage_path, report.storage_type or 'local')
    if handle is None:
        raise SnapshotIntegrityError('stored report file is missing', expected=report.sha256)
    try:
        data = handle.read()
    finally:
        try:
            handle.close()
        except Exception:
            pass
    actual = sha256_hex(data)
    if actual != report.sha256 or (report.size_bytes is not None and len(data) != report.size_bytes):
        raise SnapshotIntegrityError('stored report file does not match its SHA-256',
                                     expected=report.sha256, actual=actual)
    return data


# ── Incident purge steps ─────────────────────────────────────────────────────

def _collect_report_files(ctx) -> None:
    """pre: remember every stored report file of the incident."""
    from app import db
    from app.models import Report
    rows = (db.session.query(Report.storage_path, Report.storage_type)
            .filter(Report.incident_id == ctx.incident.id, Report.storage_path.isnot(None)).all())
    ctx.data['report_files'] = [(path, storage_type or 'local') for path, storage_type in rows]


def _delete_report_files(ctx) -> None:
    """post_commit: delete the collected files (a failure is logged; the
    purge itself is already committed)."""
    failed = 0
    for path, storage_type in ctx.data.get('report_files', []):
        try:
            if not storage_service.delete_file(path, storage_type):
                failed += 1
        except Exception:
            failed += 1
            logger.exception('report file delete failed during purge of incident %s', ctx.incident_id)
    if failed:
        logger.warning('incident %s purge: %d report file(s) could not be deleted', ctx.incident_id, failed)


register_purge_step('report_files_collect', _collect_report_files, phase='pre')
register_purge_step('report_files', _delete_report_files, phase='post_commit')
