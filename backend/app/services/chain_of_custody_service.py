"""Artifact-level chain-of-custody logging.

Thin adapter over ``CustodyLedger`` for the stored-file routes in
``artifacts.py``: every ``log_*`` method resolves the artifact's evidence item
and appends a v3 ledger entry (with ``artifact_id`` set). ``commit=True``
(default) commits like before; pass ``commit=False`` to keep the entry in the
caller's transaction (e.g. upload: item + artifact + entries in one commit).
Security events are written after a commit only.
"""
from datetime import datetime, timezone
from typing import Optional

from app import db
from app.middleware.audit import log_security_event
from app.models import Artifact, ChainOfCustody, User
from app.services.custody_ledger import CustodyLedger


def _actor(user_id):
    return db.session.get(User, user_id) if not isinstance(user_id, User) else user_id


def _hashes(artifact):
    return {'md5': artifact.md5, 'sha256': artifact.sha256, 'sha512': artifact.sha512}


class ChainOfCustodyService:
    """Service for managing chain of custody for artifacts."""

    @staticmethod
    def log_upload(artifact: Artifact, user_id, source: Optional[str] = None, *,
                   commit: bool = True) -> ChainOfCustody:
        """Log an artifact upload (``upload`` entry on its evidence item)."""
        entry = CustodyLedger.append(
            artifact.evidence_item, 'upload', performed_by=_actor(user_id), artifact=artifact,
            extra={
                'original_filename': artifact.original_filename,
                'file_size': artifact.file_size,
                'source': source,
                'purpose': artifact.purpose,
                'storage_type': artifact.storage_type,
                'hashes': _hashes(artifact),
            })
        if commit:
            db.session.commit()
            ChainOfCustodyService.audit_upload(artifact)
        return entry

    @staticmethod
    def audit_upload(artifact: Artifact) -> None:
        log_security_event(
            action='artifact_upload',
            resource_type='artifact',
            resource_id=artifact.id,
            incident_id=artifact.incident_id,
            details={'filename': artifact.original_filename,
                     'evidence_item_id': str(artifact.evidence_item_id)},
        )

    @staticmethod
    def log_view(artifact: Artifact, user_id) -> ChainOfCustody:
        """Log an artifact view."""
        entry = CustodyLedger.append(artifact.evidence_item, 'view', performed_by=_actor(user_id),
                                     artifact=artifact)
        db.session.commit()
        return entry

    @staticmethod
    def log_download(artifact: Artifact, user_id, purpose: Optional[str] = None,
                     verification_result: Optional[str] = None) -> ChainOfCustody:
        """Log an artifact download (with the on-the-fly hash check result)."""
        entry = CustodyLedger.append(
            artifact.evidence_item, 'download', performed_by=_actor(user_id), artifact=artifact,
            purpose=purpose, verification_result=verification_result,
            extra={'filename': artifact.original_filename, 'file_size': artifact.file_size})
        db.session.commit()
        log_security_event(
            action='artifact_download',
            resource_type='artifact',
            resource_id=artifact.id,
            incident_id=artifact.incident_id,
            details={
                'filename': artifact.original_filename,
                'purpose': purpose,
                'verification_result': verification_result,
            },
        )
        return entry

    @staticmethod
    def log_transfer(artifact: Artifact, from_user_id, to_user_id, reason: Optional[str] = None,
                     transfer_method: str = 'internal') -> ChainOfCustody:
        """Transfer the artifact's evidence item to another user (state machine
        applies: the item becomes ``transferred``)."""
        to_user = _actor(to_user_id)
        entry = CustodyLedger.transfer(artifact.evidence_item, actor=_actor(from_user_id), reason=reason,
                                       transfer_method=transfer_method, to_user=to_user,
                                       extra={'artifact_id': str(artifact.id)})
        db.session.commit()
        log_security_event(
            action='artifact_transfer',
            resource_type='artifact',
            resource_id=artifact.id,
            incident_id=artifact.incident_id,
            details={'from_user': str(getattr(from_user_id, 'id', from_user_id)),
                     'to_user': str(to_user.id) if to_user else None, 'reason': reason},
        )
        return entry

    @staticmethod
    def log_verification(artifact: Artifact, user_id, result: str, computed_hashes: dict) -> ChainOfCustody:
        """Log an artifact integrity verification (recomputed from stored bytes)."""
        entry = CustodyLedger.append(
            artifact.evidence_item, 'verify', performed_by=_actor(user_id), artifact=artifact,
            verification_result=result,
            extra={'computed_hashes': computed_hashes, 'stored_hashes': _hashes(artifact),
                   'method': 'recompute_stored_file'})
        now = datetime.now(timezone.utc)
        artifact.verification_status = 'verified' if result == 'match' else 'mismatch'
        artifact.last_verified_at = now
        artifact.is_verified = result == 'match'
        item = artifact.evidence_item
        item.last_verified_at = now
        item.last_verification_result = 'match' if result == 'match' else 'mismatch'
        db.session.commit()

        if result == 'mismatch':
            log_security_event(
                action='artifact_integrity_mismatch',
                resource_type='artifact',
                resource_id=artifact.id,
                incident_id=artifact.incident_id,
                details={
                    'filename': artifact.original_filename,
                    'computed_hashes': computed_hashes,
                    'stored_hashes': _hashes(artifact),
                },
            )
        return entry

    @staticmethod
    def log_legal_hold(artifact: Artifact, user_id, hold: bool, reason: Optional[str] = None) -> ChainOfCustody:
        """Log placement or release of a legal hold / preservation lock on an artifact."""
        entry = CustodyLedger.append(
            artifact.evidence_item, 'legal_hold', performed_by=_actor(user_id), artifact=artifact,
            purpose=reason,
            extra={'hold': bool(hold), 'scope': 'artifact',
                   'legal_hold_until': artifact.legal_hold_until.isoformat() if artifact.legal_hold_until else None})
        db.session.commit()
        log_security_event(
            action='artifact_legal_hold' if hold else 'artifact_legal_hold_released',
            resource_type='artifact',
            resource_id=artifact.id,
            incident_id=artifact.incident_id,
            details={'filename': artifact.original_filename, 'hold': bool(hold), 'reason': reason},
        )
        return entry

    @staticmethod
    def log_delete(artifact: Artifact, user_id, reason: Optional[str] = None, *,
                   commit: bool = True) -> ChainOfCustody:
        """Log an artifact tombstone (stored bytes purged, row and hashes kept)."""
        entry = CustodyLedger.append(
            artifact.evidence_item, 'delete', performed_by=_actor(user_id), artifact=artifact,
            purpose=reason,
            extra={'filename': artifact.original_filename, 'file_size': artifact.file_size,
                   'storage_type': artifact.storage_type, 'hashes': _hashes(artifact)})
        if commit:
            db.session.commit()
        return entry

    @staticmethod
    def get_custody_chain(artifact_id) -> list:
        """Ledger entries that reference one artifact, oldest first, each with
        its ``signature_status``."""
        from flask import current_app
        from app.models.artifact import custody_signing_key
        secret = custody_signing_key()
        legacy_secret = current_app.config.get('SECRET_KEY', '')
        entries = CustodyLedger.entries(artifact_id=artifact_id)
        result = []
        for entry in entries:
            d = entry.to_dict()
            d['signature_status'] = entry.signature_status(secret, legacy_secret=legacy_secret)
            result.append(d)
        return result

    @staticmethod
    def get_user_access_history(artifact_id, user_id) -> list:
        """Access history of one user for one artifact (newest first)."""
        entries = ChainOfCustody.query.filter_by(
            artifact_id=artifact_id,
            performed_by=user_id,
        ).order_by(ChainOfCustody.created_at.desc()).all()
        return [entry.to_dict() for entry in entries]
