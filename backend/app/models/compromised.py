"""Compromised assets models"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, BigInteger, LargeBinary, Integer
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

# Placeholder to_dict() emits instead of the real password. Before the W0-PR0
# fix, editing an account could store this literal as the "password"; a value
# that decrypts to it is treated as no stored password.
PASSWORD_MASK = '********'


class CompromisedHost(BaseModel):
    """Compromised host model."""
    __tablename__ = 'compromised_hosts'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(INET)
    mac_address = Column(String(17))
    system_type = Column(String(255))
    os_version = Column(String(255))
    evidence = Column(Text)  # Evidence of compromise from initial detection
    first_seen = Column(DateTime(timezone=True))
    last_seen = Column(DateTime(timezone=True))
    containment_status = Column(String(50), default='active')
    # Investigation triage — distinct from containment (a response action).
    # clean / compromised / under_analysis / suspicious
    triage_status = Column(String(50), nullable=False, default='under_analysis', server_default='under_analysis')
    # Forensic acquisition progress: {disk_imaged, memory_captured,
    # logs_collected, forensically_sound, acquired_at}
    acquisition_status = Column(JSONB, default=dict)
    notes = Column(Text)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    # Optimistic concurrency: bumped by SQLAlchemy on every UPDATE
    # (see app/utils/concurrency.py).
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    # Relationships
    incident = relationship('Incident', back_populates='compromised_hosts')
    creator = relationship('User')
    graph_nodes = relationship('AttackGraphNode', back_populates='compromised_host', lazy='dynamic')
    timeline_events = relationship('TimelineEvent', back_populates='host', lazy='dynamic',
                                   foreign_keys='TimelineEvent.host_id')
    compromised_accounts = relationship('CompromisedAccount', back_populates='host', lazy='dynamic')
    network_indicators = relationship('NetworkIndicator', back_populates='host', lazy='dynamic',
                                      foreign_keys='NetworkIndicator.host_id')
    malware_tools = relationship('MalwareTool', back_populates='host_ref', lazy='dynamic')
    host_indicators = relationship('HostBasedIndicator', back_populates='host_ref', lazy='dynamic')

    CONTAINMENT_STATUSES = ['active', 'compromised', 'isolated', 'contained', 'reimaged', 'cleaned', 'decommissioned']
    SYSTEM_TYPES = ['workstation', 'server', 'domain_controller', 'database', 'web_server',
                    'file_server', 'mail_server', 'laptop', 'virtual_machine', 'container', 'other']
    TRIAGE_STATUSES = ['clean', 'compromised', 'under_analysis', 'suspicious']

    def __repr__(self):
        return f'<CompromisedHost {self.hostname}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['ip_address'] = str(self.ip_address) if self.ip_address else None
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        return data


class CompromisedAccount(BaseModel):
    """Compromised account model with encrypted password storage."""
    __tablename__ = 'compromised_accounts'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    # Host correlation
    host_id = Column(UUID(as_uuid=True), ForeignKey('compromised_hosts.id', ondelete='SET NULL'), nullable=True)
    # Timeline correlation for timestamp
    timeline_event_id = Column(UUID(as_uuid=True), ForeignKey('timeline_events.id', ondelete='SET NULL'), nullable=True)
    datetime_seen = Column(DateTime(timezone=True), nullable=False)
    account_name = Column(String(255), nullable=False)
    password_encrypted = Column(LargeBinary)  # Fernet encrypted
    host_system = Column(String(255))  # Keep for backwards compatibility
    sid = Column(String(100))
    account_type = Column(String(50), nullable=False)
    domain = Column(String(255))
    is_privileged = Column(Boolean, default=False)
    status = Column(String(50), default='active')
    notes = Column(Text)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    # Optimistic concurrency: bumped by SQLAlchemy on every UPDATE
    # (see app/utils/concurrency.py).
    version = Column(Integer, nullable=False, default=1, server_default='1')
    __mapper_args__ = {'version_id_col': version}

    # Relationships
    incident = relationship('Incident', back_populates='compromised_accounts')
    host = relationship('CompromisedHost', back_populates='compromised_accounts')
    timeline_event = relationship('TimelineEvent')
    creator = relationship('User')
    graph_nodes = relationship('AttackGraphNode', back_populates='compromised_account', lazy='dynamic')

    ACCOUNT_TYPES = ['domain', 'local', 'ftp', 'service', 'application', 'admin', 'other']
    STATUSES = ['active', 'disabled', 'reset', 'deleted']

    def __repr__(self):
        return f'<CompromisedAccount {self.account_name}>'

    def to_dict(self, reveal_password=False, decrypted_password=None):
        """Convert to dictionary, optionally revealing password."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        data['host'] = self.host.to_dict() if self.host else None
        data['timeline_event'] = {'id': str(self.timeline_event.id), 'timestamp': self.timeline_event.timestamp.isoformat()} if self.timeline_event else None

        # Keep host_system for backwards compatibility
        if not data.get('host_system') and self.host:
            data['host_system'] = self.host.hostname

        # Handle password field. A revealed value equal to the mask is legacy
        # data (mask round-tripped by the old edit form): no real password.
        legacy_mask = reveal_password and decrypted_password == PASSWORD_MASK
        if self.password_encrypted and not legacy_mask:
            if reveal_password and decrypted_password:
                data['password'] = decrypted_password
            else:
                data['password'] = PASSWORD_MASK
            data['has_password'] = True
        else:
            data['password'] = None
            data['has_password'] = False

        # Remove encrypted binary from response
        data.pop('password_encrypted', None)

        return data
