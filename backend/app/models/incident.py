"""Incident model"""
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Incident(BaseModel):
    """Incident model with IR lifecycle phases."""
    __tablename__ = 'incidents'
    __table_args__ = (
        Index('idx_incident_status_severity_created', 'status', 'severity', 'created_at'),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    incident_number = Column(Integer)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    severity = Column(String(20), nullable=False, default='medium')
    status = Column(String(50), nullable=False, default='open')
    classification = Column(String(100))
    phase = Column(Integer, nullable=False, default=1)
    lead_responder_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    detected_at = Column(DateTime(timezone=True))
    contained_at = Column(DateTime(timezone=True))
    eradicated_at = Column(DateTime(timezone=True))
    recovered_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    executive_summary = Column(Text)
    lessons_learned = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    organization = relationship('Organization', back_populates='incidents')
    lead_responder = relationship('User', foreign_keys=[lead_responder_id])
    creator = relationship('User', foreign_keys=[created_by])
    assignments = relationship('IncidentAssignment', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    timeline_events = relationship('TimelineEvent', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    compromised_hosts = relationship('CompromisedHost', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    compromised_accounts = relationship('CompromisedAccount', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    network_indicators = relationship('NetworkIndicator', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    host_indicators = relationship('HostBasedIndicator', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    malware_tools = relationship('MalwareTool', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    artifacts = relationship('Artifact', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    tasks = relationship('Task', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    attack_graph_nodes = relationship('AttackGraphNode', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    attack_graph_edges = relationship('AttackGraphEdge', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    reports = relationship('Report', back_populates='incident', lazy='dynamic', cascade='all, delete-orphan')
    incident_teams = relationship('IncidentTeam', back_populates='incident', cascade='all, delete-orphan', lazy='joined')

    # IR lifecycle phases
    PHASES = {
        1: 'Preparation',
        2: 'Identification',
        3: 'Containment',
        4: 'Eradication',
        5: 'Recovery',
        6: 'Lessons Learned'
    }

    def __repr__(self):
        return f'<Incident #{self.incident_number}: {self.title}>'

    @property
    def phase_name(self):
        """Get the human-readable phase name."""
        return self.PHASES.get(self.phase, 'Unknown')

    def to_dict(self, include_counts=False):
        """Convert to dictionary."""
        data = super().to_dict()
        data['phase_name'] = self.phase_name
        data['lead_responder'] = self.lead_responder.to_dict() if self.lead_responder else None
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        data['teams'] = [
            {'id': str(it.team_id), 'name': it.team.name if it.team else None}
            for it in (self.incident_teams or [])
        ]

        if include_counts:
            data['counts'] = {
                'timeline_events': self.timeline_events.count(),
                'compromised_hosts': self.compromised_hosts.count(),
                'compromised_accounts': self.compromised_accounts.count(),
                'artifacts': self.artifacts.count(),
                'tasks': self.tasks.count(),
            }

        return data


class IncidentAssignment(BaseModel):
    """Incident assignment model for personnel tracking."""
    __tablename__ = 'incident_assignments'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(100))
    assigned_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    assigned_at = Column(DateTime(timezone=True))
    removed_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='assignments')
    user = relationship('User', foreign_keys=[user_id])
    assigner = relationship('User', foreign_keys=[assigned_by])

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': str(self.id),
            'incident_id': str(self.incident_id),
            'user': self.user.to_dict() if self.user else None,
            'role': self.role,
            'assigned_by': str(self.assigned_by) if self.assigned_by else None,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
        }


class IncidentTeam(BaseModel):
    """Junction table linking incidents to teams for access control."""
    __tablename__ = 'incident_teams'
    __table_args__ = (
        UniqueConstraint('incident_id', 'team_id', name='uq_incident_teams'),
    )

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey('teams.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    incident = relationship('Incident', back_populates='incident_teams')
    team = relationship('Team')

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': str(self.id),
            'incident_id': str(self.incident_id),
            'team_id': str(self.team_id),
            'team': self.team.to_dict() if self.team else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
