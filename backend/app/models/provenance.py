"""Record provenance mixin (decision-log-provenance §3.2).

Applied to ``TimelineEvent``, ``NetworkIndicator``, ``HostBasedIndicator`` and
``MalwareTool``: where a fact came from (evidence item / artifact, the exact
record reference), the timestamp exactly as found, how the normalized UTC
value was derived, and who verified it. ``services/provenance_service.py`` is
the only writer of the server-controlled columns
(``timestamp_derivation``, ``clock_skew_applied_seconds``,
``provenance_verified_*``).
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, and_, case, or_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declared_attr, relationship

SOURCE_RECORD_TYPES = ('file_path', 'evtx_record', 'offset', 'log_line', 'url',
                       'registry_key', 'db_row', 'other')
# MACB + log semantics.
TIMESTAMP_TYPES = ('modified', 'accessed', 'changed', 'born', 'logged',
                   'first_seen', 'last_seen', 'observed', 'other')
TIMESTAMP_DERIVATIONS = ('manual', 'computed', 'imported')

# Columns a client may write (everything else on the mixin is server-set).
PROVENANCE_INPUT_FIELDS = (
    'source_artifact_id', 'source_evidence_id', 'source_record_type', 'source_record_ref',
    'raw_timestamp', 'source_timezone', 'timestamp_type',
    'extraction_tool', 'extraction_tool_version',
)
PROVENANCE_LEVELS = ('none', 'partial', 'full', 'verified')


class ProvenanceMixin:
    """Provenance columns + ``provenance_level`` for incident record models."""

    source_record_type = Column(String(30))
    source_record_ref = Column(String(1000))
    raw_timestamp = Column(String(100))
    source_timezone = Column(String(64))
    timestamp_type = Column(String(20))
    # NULL (legacy / no raw timestamp) is treated as 'manual'.
    timestamp_derivation = Column(String(20))
    clock_skew_applied_seconds = Column(Integer)
    extraction_tool = Column(String(150))
    extraction_tool_version = Column(String(50))
    provenance_verified_at = Column(DateTime(timezone=True))

    @declared_attr
    def source_artifact_id(cls):
        return Column(UUID(as_uuid=True), ForeignKey('artifacts.id', ondelete='SET NULL'), nullable=True)

    @declared_attr
    def source_evidence_id(cls):
        return Column(UUID(as_uuid=True), ForeignKey('evidence_items.id', ondelete='SET NULL'), nullable=True)

    @declared_attr
    def provenance_verified_by(cls):
        return Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    @declared_attr
    def provenance_verifier(cls):
        return relationship('User', foreign_keys=f'{cls.__name__}.provenance_verified_by', viewonly=True)

    # -- derived -----------------------------------------------------------

    @property
    def provenance_level(self):
        """``none | partial | full | verified`` (python mirror of
        :meth:`provenance_level_expr`)."""
        if self.provenance_verified_at is not None:
            return 'verified'
        link = self.source_evidence_id or self.source_artifact_id
        if link and self.source_record_ref and self.raw_timestamp and self.source_timezone:
            return 'full'
        if any((link, self.source_record_type, self.source_record_ref, self.raw_timestamp,
                self.source_timezone, self.timestamp_type, self.extraction_tool,
                self.extraction_tool_version)):
            return 'partial'
        return 'none'

    @classmethod
    def provenance_level_expr(cls):
        """SQL expression equal to :attr:`provenance_level` (list filtering)."""
        has_link = or_(cls.source_evidence_id.isnot(None), cls.source_artifact_id.isnot(None))
        any_field = or_(
            has_link, cls.source_record_type.isnot(None), cls.source_record_ref.isnot(None),
            cls.raw_timestamp.isnot(None), cls.source_timezone.isnot(None),
            cls.timestamp_type.isnot(None), cls.extraction_tool.isnot(None),
            cls.extraction_tool_version.isnot(None))
        full = and_(has_link, cls.source_record_ref.isnot(None), cls.raw_timestamp.isnot(None),
                    cls.source_timezone.isnot(None))
        return case(
            (cls.provenance_verified_at.isnot(None), 'verified'),
            (full, 'full'),
            (any_field, 'partial'),
            else_='none',
        )

    def provenance_to_dict(self):
        """Extra keys for ``to_dict()`` (the raw columns already flow through
        ``BaseModel.to_dict``)."""
        verifier = None
        if self.provenance_verified_by:
            user = self.provenance_verifier
            verifier = {'id': str(self.provenance_verified_by), 'name': user.name if user else None}
        return {'provenance_level': self.provenance_level, 'provenance_verifier': verifier}
