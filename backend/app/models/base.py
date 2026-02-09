"""Base model with common functionality"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app import db


class BaseModel(db.Model):
    """Base model with common fields and methods."""
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """Convert model to dictionary."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif hasattr(value, 'hex'):  # UUID
                value = str(value)
            result[column.name] = value
        return result

    def save(self):
        """Save the model to the database."""
        db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Delete the model from the database."""
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def get_by_id(cls, id):
        """Get a record by ID."""
        return cls.query.get(id)
