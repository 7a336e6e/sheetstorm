from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict, Any
from datetime import datetime
from .base import BaseSchema

class IncidentCreate(BaseSchema):
    title: str = Field(..., min_length=3, max_length=500)
    description: Optional[str] = None
    severity: str = Field('medium', pattern='^(low|medium|high|critical)$')
    classification: Optional[str] = None
    detected_at: Optional[datetime] = None
    lead_responder_id: Optional[UUID4] = None

class IncidentUpdate(BaseSchema):
    title: Optional[str] = Field(None, min_length=3, max_length=500)
    description: Optional[str] = None
    severity: Optional[str] = Field(None, pattern='^(low|medium|high|critical)$')
    classification: Optional[str] = None
    executive_summary: Optional[str] = None
    lessons_learned: Optional[str] = None
    lead_responder_id: Optional[UUID4] = None

class IncidentStatusUpdate(BaseSchema):
    status: Optional[str] = Field(None, pattern='^(open|investigating|contained|eradicated|recovered|closed)$')
    phase: Optional[int] = Field(None, ge=1, le=6)

class IncidentResponse(BaseSchema):
    id: UUID4
    incident_number: int
    title: str
    description: Optional[str]
    severity: str
    status: str
    classification: Optional[str]
    phase: int
    phase_name: str
    created_at: datetime
    updated_at: Optional[datetime]
    lead_responder: Optional[Dict[str, Any]]
    creator: Optional[Dict[str, Any]]
    counts: Optional[Dict[str, int]]
