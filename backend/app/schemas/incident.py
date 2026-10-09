from pydantic import BaseModel, Field, UUID4, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.utils.validation import as_utc
from .base import BaseSchema

TLP_PATTERN = '^(white|green|amber|amber_strict|red)$'

# IR milestone timestamps editable through PUT /incidents/<id>
# (see incidents.py::validate_milestones for the ordering rules).
MILESTONE_FIELDS = ('first_malicious_at', 'detected_at', 'responded_at', 'contained_at',
                    'eradicated_at', 'recovered_at', 'closed_at')

DESCRIPTION_MAX = 10000
NARRATIVE_MAX = 20000


class IncidentCreate(BaseSchema):
    title: str = Field(..., min_length=3, max_length=500)
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX)
    severity: str = Field('medium', pattern='^(low|medium|high|critical)$')
    classification: Optional[str] = Field(None, max_length=100)
    detected_at: Optional[datetime] = None
    lead_responder_id: Optional[UUID4] = None
    tlp: Optional[str] = Field('amber', pattern=TLP_PATTERN)
    team_id: Optional[UUID4] = None
    team_ids: Optional[List[UUID4]] = Field(None, max_length=50)
    # Start from a case template: "builtin:<key>" or an org template UUID.
    case_template: Optional[str] = Field(
        None, pattern=r'^(builtin:[a-z0-9][a-z0-9-]{1,63}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$')

    @field_validator('detected_at')
    @classmethod
    def detected_utc(cls, v):
        # Offset-less values are UTC (same rule as utils/validation.parse_datetime).
        return as_utc(v)


class IncidentUpdate(BaseSchema):
    title: Optional[str] = Field(None, min_length=3, max_length=500)
    description: Optional[str] = Field(None, max_length=DESCRIPTION_MAX)
    severity: Optional[str] = Field(None, pattern='^(low|medium|high|critical)$')
    classification: Optional[str] = Field(None, max_length=100)
    executive_summary: Optional[str] = Field(None, max_length=NARRATIVE_MAX)
    lessons_learned: Optional[str] = Field(None, max_length=NARRATIVE_MAX)
    lead_responder_id: Optional[UUID4] = None
    tlp: Optional[str] = Field(None, pattern=TLP_PATTERN)
    team_id: Optional[UUID4] = None
    # IR milestones (C20). null clears a milestone.
    first_malicious_at: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    contained_at: Optional[datetime] = None
    eradicated_at: Optional[datetime] = None
    recovered_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    @field_validator(*MILESTONE_FIELDS)
    @classmethod
    def milestones_utc(cls, v):
        return as_utc(v)


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
