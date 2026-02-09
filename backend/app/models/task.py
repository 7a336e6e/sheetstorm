"""Task model"""
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Task(BaseModel):
    """Task model for incident response tracking."""
    __tablename__ = 'tasks'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(50), default='pending')
    priority = Column(String(20), default='medium')
    assignee_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    due_date = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    checklist = Column(JSONB, default=list)
    phase = Column(Integer)
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id'))
    order_index = Column(Integer, default=0)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='tasks')
    assignee = relationship('User', foreign_keys=[assignee_id])
    creator = relationship('User', foreign_keys=[created_by])
    comments = relationship('TaskComment', back_populates='task', lazy='dynamic', cascade='all, delete-orphan')
    subtasks = relationship('Task', backref='parent_task', remote_side='Task.id')

    STATUSES = ['pending', 'in_progress', 'completed', 'blocked', 'cancelled']
    PRIORITIES = ['low', 'medium', 'high', 'critical']

    def __repr__(self):
        return f'<Task {self.title}>'

    def to_dict(self, include_comments=False):
        """Convert to dictionary."""
        data = super().to_dict()
        data['assignee'] = self.assignee.to_dict() if self.assignee else None
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None

        if include_comments:
            data['comments'] = [c.to_dict() for c in self.comments.order_by(TaskComment.created_at.desc()).limit(20)]

        # Calculate checklist progress
        if self.checklist:
            completed = sum(1 for item in self.checklist if item.get('completed', False))
            data['checklist_progress'] = {
                'completed': completed,
                'total': len(self.checklist),
                'percentage': round((completed / len(self.checklist)) * 100) if self.checklist else 0
            }

        return data


class TaskComment(BaseModel):
    """Task comment model."""
    __tablename__ = 'task_comments'

    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    task = relationship('Task', back_populates='comments')
    author = relationship('User')

    def __repr__(self):
        return f'<TaskComment by {self.author_id}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['author'] = {'id': str(self.author.id), 'name': self.author.name} if self.author else None
        return data
