"""Team models"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Team(BaseModel):
    """Team model for organizing users."""
    __tablename__ = 'teams'
    __table_args__ = (
        UniqueConstraint('organization_id', 'name', name='uq_teams_org_name'),
    )

    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    organization = relationship('Organization', back_populates='teams')
    members = relationship('TeamMember', back_populates='team', cascade='all, delete-orphan', lazy='joined')

    def __repr__(self):
        return f'<Team {self.name}>'

    def to_dict(self, include_members=False):
        """Convert to dictionary."""
        data = {
            'id': str(self.id),
            'organization_id': str(self.organization_id),
            'name': self.name,
            'description': self.description,
            'member_count': len(self.members) if self.members else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_members:
            data['members'] = [m.to_dict() for m in self.members]
        return data


class TeamMember(BaseModel):
    """Team membership junction model."""
    __tablename__ = 'team_members'
    __table_args__ = (
        UniqueConstraint('team_id', 'user_id', name='uq_team_members_team_user'),
    )

    team_id = Column(UUID(as_uuid=True), ForeignKey('teams.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    team = relationship('Team', back_populates='members')
    user = relationship('User', back_populates='team_memberships')

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': str(self.id),
            'team_id': str(self.team_id),
            'user_id': str(self.user_id),
            'user': self.user.to_dict() if self.user else None,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
        }
