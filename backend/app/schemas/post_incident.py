"""Request schemas for the after-action review and improvement actions."""
import re
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import UUID4, Field, field_validator

from app.models.post_incident import (
    ACTION_PRIORITIES, ACTION_STATUSES, CONTRIBUTING_CATEGORIES, CONTROL_FRAMEWORKS, DETECTION_SOURCES,
)
from app.utils.validation import as_utc
from .base import BaseSchema

TEXT_MAX = 20000
CSF_REF = re.compile(r'^[A-Z]{2}\.[A-Z]{2}(-\d{2})?$')
D3FEND_REF = re.compile(r'^D3-[A-Z]+$')

Category = Literal[CONTRIBUTING_CATEGORIES]  # type: ignore[valid-type]
DetectionSource = Literal[DETECTION_SOURCES]  # type: ignore[valid-type]
ActionStatus = Literal[ACTION_STATUSES]  # type: ignore[valid-type]
ActionPriority = Literal[ACTION_PRIORITIES]  # type: ignore[valid-type]
Framework = Literal[CONTROL_FRAMEWORKS]  # type: ignore[valid-type]


class ContributingFactor(BaseSchema):
    category: Category
    description: str = Field(..., min_length=1, max_length=2000)


class ReviewUpdate(BaseSchema):
    """PUT /incidents/<id>/review (upsert; only the sent fields change)."""
    what_went_well: Optional[str] = Field(None, max_length=TEXT_MAX)
    what_went_wrong: Optional[str] = Field(None, max_length=TEXT_MAX)
    root_cause: Optional[str] = Field(None, max_length=TEXT_MAX)
    contributing_factors: Optional[List[ContributingFactor]] = Field(None, max_length=50)
    detection_source: Optional[DetectionSource] = None
    review_date: Optional[date] = None
    participants: Optional[List[UUID4]] = Field(None, max_length=50)
    status: Optional[Literal['draft', 'final']] = None


class _ActionFields(BaseSchema):
    description: Optional[str] = Field(None, max_length=10000)
    owner_id: Optional[UUID4] = None
    team_id: Optional[UUID4] = None
    due_date: Optional[datetime] = None
    category: Optional[Category] = None
    control_framework: Optional[Framework] = None
    control_ref: Optional[str] = Field(None, max_length=100)
    review_id: Optional[UUID4] = None

    @field_validator('due_date')
    @classmethod
    def due_utc(cls, v):
        return as_utc(v)

    @field_validator('control_ref')
    @classmethod
    def strip_ref(cls, v):
        return v.strip() or None if isinstance(v, str) else v


class ImprovementActionCreate(_ActionFields):
    title: str = Field(..., min_length=1, max_length=500)
    status: ActionStatus = 'open'
    priority: ActionPriority = 'medium'


class ImprovementActionUpdate(_ActionFields):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[ActionStatus] = None
    priority: Optional[ActionPriority] = None


def validate_control(framework, ref):
    """Return an error message for an invalid control reference, else None.

    A reference needs a framework. ``d3fend`` refs must be a known D3FEND
    technique id, ``nist_csf`` refs a CSF 2.0 subcategory (``RS.MA-01``) or
    category (``ID.IM``); other frameworks accept free text (<= 100 chars).
    """
    if ref and not framework:
        return 'control_ref requires control_framework'
    if not framework or not ref:
        return None
    if framework == 'd3fend':
        if not D3FEND_REF.match(ref):
            return 'control_ref for d3fend must look like D3-MFA'
        from app.api.v1.endpoints.kb_data_d3fend import D3FEND_TECHNIQUES
        if ref not in {t['id'] for t in D3FEND_TECHNIQUES}:
            return f'{ref} is not a known D3FEND technique'
    elif framework == 'nist_csf' and not CSF_REF.match(ref):
        return 'control_ref for nist_csf must look like RS.MA-01 or ID.IM'
    return None


def first_error(exc):
    """A short client message from a pydantic ValidationError."""
    try:
        err = exc.errors()[0]
        loc = '.'.join(str(p) for p in err.get('loc', ()) if p != 'body')
        return f'{loc}: {err.get("msg")}' if loc else str(err.get('msg'))
    except Exception:
        return 'Invalid request body'
