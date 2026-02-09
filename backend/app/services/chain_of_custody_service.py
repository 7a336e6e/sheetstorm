"""Chain of custody service for evidence tracking"""
from datetime import datetime, timezone
from typing import Optional
from flask import request, g
from app import db
from app.models import Artifact, ChainOfCustody
from app.middleware.audit import log_security_event


class ChainOfCustodyService:
    """Service for managing chain of custody for artifacts."""

    @staticmethod
    def log_upload(artifact: Artifact, user_id: str, source: Optional[str] = None) -> ChainOfCustody:
        """Log artifact upload to chain of custody.

        Args:
            artifact: The uploaded artifact
            user_id: ID of the uploading user
            source: Source of the artifact

        Returns:
            Created ChainOfCustody record
        """
        entry = ChainOfCustody(
            artifact_id=artifact.id,
            action='upload',
            performed_by=user_id,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
            metadata={
                'original_filename': artifact.original_filename,
                'file_size': artifact.file_size,
                'source': source,
                'hashes': {
                    'md5': artifact.md5,
                    'sha256': artifact.sha256,
                    'sha512': artifact.sha512
                }
            }
        )
        db.session.add(entry)
        db.session.commit()

        log_security_event(
            action='artifact_upload',
            resource_type='artifact',
            resource_id=artifact.id,
            incident_id=artifact.incident_id,
            details={'filename': artifact.original_filename}
        )

        return entry

    @staticmethod
    def log_view(artifact: Artifact, user_id: str) -> ChainOfCustody:
        """Log artifact view to chain of custody.

        Args:
            artifact: The viewed artifact
            user_id: ID of the viewing user

        Returns:
            Created ChainOfCustody record
        """
        entry = ChainOfCustody(
            artifact_id=artifact.id,
            action='view',
            performed_by=user_id,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    @staticmethod
    def log_download(
        artifact: Artifact,
        user_id: str,
        purpose: Optional[str] = None,
        verification_result: Optional[str] = None
    ) -> ChainOfCustody:
        """Log artifact download to chain of custody.

        Args:
            artifact: The downloaded artifact
            user_id: ID of the downloading user
            purpose: Reason for download
            verification_result: Hash verification result

        Returns:
            Created ChainOfCustody record
        """
        entry = ChainOfCustody(
            artifact_id=artifact.id,
            action='download',
            performed_by=user_id,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
            purpose=purpose,
            verification_result=verification_result,
            metadata={
                'filename': artifact.original_filename,
                'file_size': artifact.file_size,
            }
        )
        db.session.add(entry)
        db.session.commit()

        log_security_event(
            action='artifact_download',
            resource_type='artifact',
            resource_id=artifact.id,
            incident_id=artifact.incident_id,
            details={
                'filename': artifact.original_filename,
                'purpose': purpose,
                'verification_result': verification_result
            }
        )

        return entry

    @staticmethod
    def log_transfer(
        artifact: Artifact,
        from_user_id: str,
        to_user_id: str,
        reason: Optional[str] = None
    ) -> ChainOfCustody:
        """Log artifact transfer between users.

        Args:
            artifact: The transferred artifact
            from_user_id: ID of the transferring user
            to_user_id: ID of the receiving user
            reason: Reason for transfer

        Returns:
            Created ChainOfCustody record
        """
        entry = ChainOfCustody(
            artifact_id=artifact.id,
            action='transfer',
            performed_by=from_user_id,
            recipient_id=to_user_id,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
            purpose=reason,
        )
        db.session.add(entry)
        db.session.commit()

        log_security_event(
            action='artifact_transfer',
            resource_type='artifact',
            resource_id=artifact.id,
            incident_id=artifact.incident_id,
            details={
                'from_user': str(from_user_id),
                'to_user': str(to_user_id),
                'reason': reason
            }
        )

        return entry

    @staticmethod
    def log_verification(
        artifact: Artifact,
        user_id: str,
        result: str,
        computed_hashes: dict
    ) -> ChainOfCustody:
        """Log artifact integrity verification.

        Args:
            artifact: The verified artifact
            user_id: ID of the verifying user
            result: 'match' or 'mismatch'
            computed_hashes: Dictionary of computed hashes

        Returns:
            Created ChainOfCustody record
        """
        entry = ChainOfCustody(
            artifact_id=artifact.id,
            action='verify',
            performed_by=user_id,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
            verification_result=result,
            metadata={
                'computed_hashes': computed_hashes,
                'stored_hashes': {
                    'md5': artifact.md5,
                    'sha256': artifact.sha256,
                    'sha512': artifact.sha512
                }
            }
        )
        db.session.add(entry)

        # Update artifact verification status
        artifact.verification_status = 'verified' if result == 'match' else 'mismatch'
        artifact.last_verified_at = datetime.now(timezone.utc)
        artifact.is_verified = result == 'match'

        db.session.commit()

        # Log security event for mismatches
        if result == 'mismatch':
            log_security_event(
                action='artifact_integrity_mismatch',
                resource_type='artifact',
                resource_id=artifact.id,
                incident_id=artifact.incident_id,
                details={
                    'filename': artifact.original_filename,
                    'computed_hashes': computed_hashes,
                    'stored_hashes': {
                        'md5': artifact.md5,
                        'sha256': artifact.sha256,
                        'sha512': artifact.sha512
                    }
                }
            )

        return entry

    @staticmethod
    def get_custody_chain(artifact_id: str) -> list:
        """Get the complete chain of custody for an artifact.

        Args:
            artifact_id: ID of the artifact

        Returns:
            List of ChainOfCustody records
        """
        entries = ChainOfCustody.query.filter_by(
            artifact_id=artifact_id
        ).order_by(ChainOfCustody.created_at.asc()).all()

        return [entry.to_dict() for entry in entries]

    @staticmethod
    def get_user_access_history(artifact_id: str, user_id: str) -> list:
        """Get access history for a specific user and artifact.

        Args:
            artifact_id: ID of the artifact
            user_id: ID of the user

        Returns:
            List of ChainOfCustody records
        """
        entries = ChainOfCustody.query.filter_by(
            artifact_id=artifact_id,
            performed_by=user_id
        ).order_by(ChainOfCustody.created_at.desc()).all()

        return [entry.to_dict() for entry in entries]
