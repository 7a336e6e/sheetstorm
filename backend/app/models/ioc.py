"""Indicator of Compromise (IOC) models"""
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class NetworkIndicator(BaseModel):
    """Network-based indicator of compromise."""
    __tablename__ = 'network_indicators'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    # Host correlation
    host_id = Column(UUID(as_uuid=True), ForeignKey('compromised_hosts.id', ondelete='SET NULL'), nullable=True)
    # Timeline correlation
    timeline_event_id = Column(UUID(as_uuid=True), ForeignKey('timeline_events.id', ondelete='SET NULL'), nullable=True)
    timestamp = Column(DateTime(timezone=True))
    protocol = Column(String(20))
    port = Column(Integer)
    dns_ip = Column(String(255), nullable=False)
    source_host = Column(String(255))  # Keep for backwards compatibility
    destination_host = Column(String(255))
    direction = Column(String(20))
    description = Column(Text)
    is_malicious = Column(Boolean, default=True)
    threat_intel_source = Column(String(255))
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='network_indicators')
    host = relationship('CompromisedHost', back_populates='network_indicators')
    timeline_event = relationship('TimelineEvent')
    creator = relationship('User')

    DIRECTIONS = ['inbound', 'outbound', 'lateral']
    PROTOCOLS = ['TCP', 'UDP', 'ICMP', 'HTTP', 'HTTPS', 'DNS', 'SMTP', 'FTP', 'SSH', 'RDP', 'SMB']

    def __repr__(self):
        return f'<NetworkIndicator {self.dns_ip}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        data['host'] = self.host.to_dict() if self.host else None
        # Keep source_host for backwards compatibility
        if not data.get('source_host') and self.host:
            data['source_host'] = self.host.hostname
        return data


class HostBasedIndicator(BaseModel):
    """Host-based indicator of compromise."""
    __tablename__ = 'host_based_indicators'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    # Host correlation
    host_id = Column(UUID(as_uuid=True), ForeignKey('compromised_hosts.id', ondelete='SET NULL'), nullable=True)
    # Timeline event source (when marking event as IOC)
    timeline_event_id = Column(UUID(as_uuid=True), ForeignKey('timeline_events.id', ondelete='SET NULL'), nullable=True)
    artifact_type = Column(String(50), nullable=False)
    datetime = Column(DateTime(timezone=True))
    artifact_value = Column(Text, nullable=False)
    host = Column(String(255))  # Keep for backwards compatibility
    notes = Column(Text)
    is_malicious = Column(Boolean, default=True)
    remediated = Column(Boolean, default=False)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='host_indicators')
    host_ref = relationship('CompromisedHost', back_populates='host_indicators')
    source_event = relationship('TimelineEvent', back_populates='host_indicators')
    creator = relationship('User')

    ARTIFACT_TYPES = ['wmi_event', 'asep', 'registry', 'scheduled_task', 'service', 'file', 'process', 'other']

    def __repr__(self):
        return f'<HostBasedIndicator {self.artifact_type}: {self.artifact_value[:50]}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        data['host_ref'] = self.host_ref.to_dict() if self.host_ref else None
        data['source_event'] = self.source_event.to_dict() if self.source_event else None
        # Keep host for backwards compatibility
        if not data.get('host') and self.host_ref:
            data['host'] = self.host_ref.hostname
        return data


class MalwareTool(BaseModel):
    """Malware and tools discovered during incident."""
    __tablename__ = 'malware_tools'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    # Host correlation
    host_id = Column(UUID(as_uuid=True), ForeignKey('compromised_hosts.id', ondelete='SET NULL'), nullable=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text)
    md5 = Column(String(32))
    sha256 = Column(String(64))
    sha512 = Column(String(128))
    file_size = Column(BigInteger)
    creation_time = Column(DateTime(timezone=True))
    modification_time = Column(DateTime(timezone=True))
    access_time = Column(DateTime(timezone=True))
    host = Column(String(255))  # Keep for backwards compatibility
    description = Column(Text)
    malware_family = Column(String(255))
    threat_actor = Column(String(255))
    is_tool = Column(Boolean, default=False)
    sandbox_report_url = Column(Text)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='malware_tools')
    host_ref = relationship('CompromisedHost', back_populates='malware_tools')
    creator = relationship('User')

    def __repr__(self):
        return f'<MalwareTool {self.file_name}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        data['host_ref'] = self.host_ref.to_dict() if self.host_ref else None
        # Keep host for backwards compatibility
        if not data.get('host') and self.host_ref:
            data['host'] = self.host_ref.hostname
        return data
