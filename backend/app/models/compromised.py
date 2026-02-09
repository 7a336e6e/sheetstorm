"""Compromised assets models"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, BigInteger, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


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
    notes = Column(Text)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='compromised_hosts')
    creator = relationship('User')
    graph_nodes = relationship('AttackGraphNode', back_populates='compromised_host', lazy='dynamic')
    timeline_events = relationship('TimelineEvent', back_populates='host', lazy='dynamic',
                                   foreign_keys='TimelineEvent.host_id')
    compromised_accounts = relationship('CompromisedAccount', back_populates='host', lazy='dynamic')
    network_indicators = relationship('NetworkIndicator', back_populates='host', lazy='dynamic')
    malware_tools = relationship('MalwareTool', back_populates='host_ref', lazy='dynamic')
    host_indicators = relationship('HostBasedIndicator', back_populates='host_ref', lazy='dynamic')

    CONTAINMENT_STATUSES = ['active', 'isolated', 'reimaged', 'decommissioned']
    SYSTEM_TYPES = ['workstation', 'server', 'domain_controller', 'database', 'web_server', 
                    'file_server', 'mail_server', 'laptop', 'virtual_machine', 'container', 'other']

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

        # Handle password field
        if self.password_encrypted:
            if reveal_password and decrypted_password:
                data['password'] = decrypted_password
            else:
                data['password'] = '********'
            data['has_password'] = True
        else:
            data['password'] = None
            data['has_password'] = False

        # Remove encrypted binary from response
        data.pop('password_encrypted', None)

        return data
