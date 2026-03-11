"""Custom field option model for user-defined dropdown values."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class CustomFieldOption(BaseModel):
    """Stores custom dropdown values (system types, artifact types, protocols, etc.) per organization."""
    __tablename__ = 'custom_field_options'
    __table_args__ = (
        UniqueConstraint('organization_id', 'field_name', 'field_value', name='uq_custom_field_option'),
        Index('idx_custom_field_options_field', 'organization_id', 'field_name'),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    field_name = Column(String(100), nullable=False)  # e.g. 'system_type', 'artifact_type'
    field_value = Column(String(255), nullable=False)
    display_label = Column(String(255))
    is_default = Column(Boolean, default=False, server_default='false')
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Relationships
    organization = relationship('Organization')
    creator = relationship('User')

    # Predefined field names
    FIELD_NAMES = ['system_type', 'artifact_type', 'protocol', 'direction', 'containment_status']

    # Default options per field
    DEFAULTS = {
        'system_type': [
            ('workstation', 'Workstation'),
            ('server', 'Server'),
            ('domain_controller', 'Domain Controller'),
            ('database', 'Database Server'),
            ('web_server', 'Web Server'),
            ('file_server', 'File Server'),
            ('mail_server', 'Mail Server'),
            ('laptop', 'Laptop'),
            ('virtual_machine', 'Virtual Machine'),
            ('container', 'Container'),
            ('firewall', 'Firewall'),
            ('router', 'Router'),
            ('switch', 'Network Switch'),
            ('vpn_gateway', 'VPN Gateway'),
            ('load_balancer', 'Load Balancer'),
            ('nas', 'NAS Storage'),
            ('printer', 'Printer'),
            ('iot_device', 'IoT Device'),
            ('mobile_device', 'Mobile Device'),
            ('other', 'Other'),
        ],
        'artifact_type': [
            ('registry', 'Registry Key'),
            ('service', 'Service'),
            ('process', 'Process'),
            ('file', 'File'),
            ('scheduled_task', 'Scheduled Task'),
            ('wmi_event', 'WMI Event'),
            ('asep', 'ASEP'),
            ('driver', 'Driver'),
            ('dll', 'DLL'),
            ('named_pipe', 'Named Pipe'),
            ('mutex', 'Mutex'),
            ('startup_item', 'Startup Item'),
            ('browser_extension', 'Browser Extension'),
            ('cron_job', 'Cron Job'),
            ('user_account', 'User Account'),
            ('group_policy', 'Group Policy Object'),
            ('firewall_rule', 'Firewall Rule'),
            ('dns_record', 'DNS Record'),
            ('certificate', 'Certificate'),
            ('log_entry', 'Log Entry'),
            ('other', 'Other'),
        ],
    }

    def __repr__(self):
        return f'<CustomFieldOption {self.field_name}={self.field_value}>'

    def to_dict(self):
        return {
            'id': str(self.id),
            'field_name': self.field_name,
            'field_value': self.field_value,
            'display_label': self.display_label or self.field_value,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def seed_defaults(cls, organization_id, session):
        """Seed default options for an organization."""
        from uuid import uuid4
        for field_name, options in cls.DEFAULTS.items():
            for value, label in options:
                existing = session.query(cls).filter_by(
                    organization_id=organization_id,
                    field_name=field_name,
                    field_value=value
                ).first()
                if not existing:
                    opt = cls(
                        id=uuid4(),
                        organization_id=organization_id,
                        field_name=field_name,
                        field_value=value,
                        display_label=label,
                        is_default=True,
                    )
                    session.add(opt)
