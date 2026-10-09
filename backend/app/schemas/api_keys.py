"""Request schemas for API keys and service accounts (endpoints/api_keys.py).

Shape only: scope validation against the catalog and the owner's
permissions, lifetime caps and ownership rules live in
services/api_key_service.py.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

# A catalog key is `group:action`; the service checks membership.
MAX_SCOPES = 200


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


def _name(v):
    if v is None:
        return v
    if not 1 <= len(v) <= 100:
        raise ValueError('Name must be 1-100 characters')
    return v


class ApiKeyCreate(_Strict):
    name: StrictStr
    description: Optional[StrictStr] = Field(None, max_length=500)
    scopes: List[StrictStr] = Field(..., max_length=MAX_SCOPES)
    # Required by policy (1..365, capped by the org's api_key_max_lifetime_days);
    # the service applies the default (90) when omitted.
    expires_in_days: Optional[StrictInt] = None
    owner_id: Optional[UUID] = None

    @field_validator('name')
    @classmethod
    def _valid_name(cls, v):
        return _name(v)


class ApiKeyRotate(_Strict):
    expires_in_days: Optional[StrictInt] = None
    grace_minutes: StrictInt = Field(0, ge=0, le=1440)


class ApiKeyRevoke(_Strict):
    reason: Optional[StrictStr] = Field(None, max_length=200)


class ServiceAccountCreate(_Strict):
    name: StrictStr
    role_ids: List[UUID] = Field(default_factory=list, max_length=20)

    @field_validator('name')
    @classmethod
    def _valid_name(cls, v):
        return _name(v)


class ServiceAccountUpdate(_Strict):
    name: Optional[StrictStr] = None
    is_active: Optional[StrictBool] = None
    role_ids: Optional[List[UUID]] = Field(None, max_length=20)

    @field_validator('name')
    @classmethod
    def _valid_name(cls, v):
        return _name(v)


def validation_fields(exc) -> dict:
    """{dotted.loc: message} from a pydantic ValidationError."""
    return {'.'.join(str(p) for p in err['loc']) or 'body': err['msg'] for err in exc.errors()}


__all__ = ['ApiKeyCreate', 'ApiKeyRotate', 'ApiKeyRevoke', 'ServiceAccountCreate', 'ServiceAccountUpdate',
           'validation_fields', 'MAX_SCOPES']
