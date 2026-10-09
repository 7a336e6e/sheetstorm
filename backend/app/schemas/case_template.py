"""Case-template definition schema (pydantic v2, ``extra='forbid'`` everywhere).

A template ``definition`` seeds a new (or existing) incident with key
questions, starter leads, a playbook, defaults and custom-field definitions.
The same models validate built-in YAML at load time and org templates written
through the API. Checks that need the question library or the database
(``ref`` resolution, ``playbook_id`` ownership) live in
``services/case_template_service.py``; this module is pure.
"""
from __future__ import annotations

import re
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import (BaseModel, ConfigDict, Field, StrictBool, field_validator,
                      model_validator)

TLP_LEVELS = ('white', 'green', 'amber', 'amber_strict', 'red')
SEVERITIES = ('low', 'medium', 'high', 'critical')
PRIORITIES = ('low', 'medium', 'high', 'critical')
TASK_TYPES = ('action_item', 'investigative_lead', 'verification', 'documentation', 'reporting')
CUSTOM_FIELD_TYPES = ('text', 'number', 'boolean', 'date', 'select')

MAX_QUESTIONS = 200
MAX_LEADS = 100
MAX_CUSTOM_FIELDS = 30
MAX_SELECT_OPTIONS = 50
MAX_BODY_BYTES = 256 * 1024

TEMPLATE_KEY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,63}$')
ENTRY_KEY_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
FIELD_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,62}$')
LIBRARY_REF_RE = re.compile(r'^(ss|dfiq):[A-Za-z0-9_-]{1,32}$')
BUILTIN_REF_RE = re.compile(r'^builtin:[a-z0-9][a-z0-9-]{1,63}$')


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Defaults(_Strict):
    severity: Optional[Literal['low', 'medium', 'high', 'critical']] = None
    tlp: Optional[Literal['white', 'green', 'amber', 'amber_strict', 'red']] = None
    classification: Optional[str] = Field(None, min_length=1, max_length=100)


class QuestionEntry(_Strict):
    """A library question (``ref``) or a template-local one (``key`` + ``question``)."""
    ref: Optional[str] = Field(None, max_length=40)
    key: Optional[str] = Field(None, max_length=64)
    question: Optional[str] = Field(None, min_length=3, max_length=1000)
    description: Optional[str] = Field(None, max_length=5000)
    facet: Optional[str] = Field(None, max_length=255)
    phase: Optional[int] = Field(None, ge=1, le=6)
    priority: Optional[Literal['low', 'medium', 'high', 'critical']] = None

    @field_validator('ref')
    @classmethod
    def _ref(cls, v):
        if v is not None and not LIBRARY_REF_RE.match(v):
            raise ValueError('ref must look like "ss:SSQ-001" or "dfiq:Q1058"')
        return v

    @field_validator('key')
    @classmethod
    def _key(cls, v):
        if v is not None and not ENTRY_KEY_RE.match(v):
            raise ValueError('key must match ^[a-z0-9][a-z0-9_-]{0,63}$')
        return v

    @model_validator(mode='after')
    def _one_form(self):
        if self.ref is not None:
            if self.key is not None or self.question is not None or self.description is not None:
                raise ValueError('a library question entry takes only ref, phase, priority and facet')
        elif self.key is None or self.question is None:
            raise ValueError('a question entry needs either ref, or key and question')
        return self

    @property
    def ident(self):
        return self.ref or self.key


class LeadEntry(_Strict):
    key: str = Field(..., max_length=64)
    title: str = Field(..., min_length=3, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    phase: Optional[int] = Field(None, ge=1, le=6)
    priority: Optional[Literal['low', 'medium', 'high', 'critical']] = None
    task_type: Literal['action_item', 'investigative_lead', 'verification',
                       'documentation', 'reporting'] = 'investigative_lead'
    investigation_direction: Optional[str] = Field(None, max_length=5000)
    answers: List[str] = Field(default_factory=list, max_length=MAX_QUESTIONS)

    @field_validator('key')
    @classmethod
    def _key(cls, v):
        if not ENTRY_KEY_RE.match(v):
            raise ValueError('key must match ^[a-z0-9][a-z0-9_-]{0,63}$')
        return v


class PlaybookRef(_Strict):
    builtin: Optional[str] = Field(None, max_length=64)
    playbook_id: Optional[UUID] = None

    @field_validator('builtin')
    @classmethod
    def _builtin(cls, v):
        if v is not None and not TEMPLATE_KEY_RE.match(v):
            raise ValueError('builtin must be a playbook key such as "ransomware"')
        return v

    @model_validator(mode='after')
    def _one(self):
        if (self.builtin is None) == (self.playbook_id is None):
            raise ValueError('playbook needs exactly one of builtin or playbook_id')
        return self


class CustomFieldDef(_Strict):
    key: str = Field(..., max_length=63)
    label: str = Field(..., min_length=1, max_length=100)
    type: Literal['text', 'number', 'boolean', 'date', 'select']
    options: Optional[List[str]] = Field(None, max_length=MAX_SELECT_OPTIONS)
    required: StrictBool = False

    @field_validator('key')
    @classmethod
    def _key(cls, v):
        if not FIELD_KEY_RE.match(v):
            raise ValueError('key must match ^[a-z][a-z0-9_]{0,62}$')
        return v

    @field_validator('options')
    @classmethod
    def _options(cls, v):
        if v is not None:
            if any((not isinstance(o, str)) or not o.strip() or len(o) > 100 for o in v):
                raise ValueError('options must be non-empty strings of at most 100 characters')
            if len(set(v)) != len(v):
                raise ValueError('options must be unique')
        return v

    @model_validator(mode='after')
    def _select_options(self):
        if self.type == 'select' and not self.options:
            raise ValueError('a select field needs options')
        if self.type != 'select' and self.options:
            raise ValueError('options are only allowed on select fields')
        return self


class CaseTemplateDefinition(_Strict):
    schema_version: Literal[1]
    defaults: Defaults = Field(default_factory=Defaults)
    questions: List[QuestionEntry] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    leads: List[LeadEntry] = Field(default_factory=list, max_length=MAX_LEADS)
    playbook: Optional[PlaybookRef] = None
    custom_fields: List[CustomFieldDef] = Field(default_factory=list, max_length=MAX_CUSTOM_FIELDS)
    report_template: Optional[str] = Field(None, max_length=200)  # reserved, stored, unused

    @model_validator(mode='after')
    def _cross_field(self):
        idents = [q.ident for q in self.questions]
        dupes = sorted({i for i in idents if idents.count(i) > 1})
        if dupes:
            raise ValueError(f'duplicate question ref/key: {dupes[0]}')
        lead_keys = [lead.key for lead in self.leads]
        dupes = sorted({k for k in lead_keys if lead_keys.count(k) > 1})
        if dupes:
            raise ValueError(f'duplicate lead key: {dupes[0]}')
        field_keys = [f.key for f in self.custom_fields]
        dupes = sorted({k for k in field_keys if field_keys.count(k) > 1})
        if dupes:
            raise ValueError(f'duplicate custom field key: {dupes[0]}')
        known = set(idents)
        for lead in self.leads:
            for target in lead.answers:
                if target not in known:
                    raise ValueError(f'lead {lead.key!r} answers {target!r}, which is not in questions')
        return self


class CaseTemplateWrite(_Strict):
    """Body of POST /case-templates (and, with every field optional, PUT)."""
    key: str = Field(..., max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    incident_type: Optional[str] = Field(None, max_length=100)
    is_active: StrictBool = True
    definition: CaseTemplateDefinition

    @field_validator('key')
    @classmethod
    def _key(cls, v):
        if not TEMPLATE_KEY_RE.match(v):
            raise ValueError('key must match ^[a-z0-9][a-z0-9-]{1,63}$')
        return v

    @field_validator('name')
    @classmethod
    def _name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('name must not be blank')
        return v


class CaseTemplateUpdate(_Strict):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    incident_type: Optional[str] = Field(None, max_length=100)
    is_active: Optional[StrictBool] = None
    definition: Optional[CaseTemplateDefinition] = None
    expected_version: Optional[int] = Field(None, ge=0)

    @field_validator('name')
    @classmethod
    def _name(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('name must not be blank')
        return v


class ApplyOptions(_Strict):
    apply_defaults: StrictBool = False
    dry_run: StrictBool = False
    run_auto_actions: StrictBool = False
    include: List[Literal['questions', 'leads', 'playbook', 'custom_fields']] = Field(
        default_factory=lambda: ['questions', 'leads', 'playbook', 'custom_fields'], max_length=4)
