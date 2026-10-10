"""Request bodies of the SSO provider admin API (pydantic v2, extra='forbid').

Pure shape and format validation. Checks that need the database or the caller
(role visibility, grant ceilings, slug uniqueness) live in the endpoint.
``SsoProviderUpdate`` is the same model with every field optional: only the
fields sent are changed, and ``client_secret`` is write-only (``""`` clears
it, omitted keeps it).
"""
from __future__ import annotations

import re
from typing import List, Literal, Optional
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.models.sso import MFA_MODES, PRESETS, ROLE_SYNC_MODES, TOKEN_AUTH_METHODS

SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$')
CLAIM_RE = re.compile(r'^[A-Za-z0-9_:/.\-]{1,200}$')
SCOPE_RE = re.compile(r'^[\x21\x23-\x5B\x5D-\x7E]{1,100}$')  # RFC 6749 scope-token
DOMAIN_RE = re.compile(r'^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$')
MAX_LIST = 50


class RoleMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')

    group: str = Field(..., min_length=1, max_length=255)
    role_id: UUID

    @field_validator('group')
    @classmethod
    def _group(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('group is required')
        return v


def _string_list(values, *, lower=False, max_len=255):
    out = []
    for raw in values:
        if not isinstance(raw, str):
            raise ValueError('values must be strings')
        v = raw.strip()
        v = v.lower() if lower else v
        if not v or len(v) > max_len:
            raise ValueError(f'invalid value: {raw[:60]!r}')
        if v not in out:
            out.append(v)
    return out


def _check_slug(v):
    v = (v or '').strip().lower()
    if not SLUG_RE.match(v):
        raise ValueError('3-40 characters: lowercase letters, digits and dashes, '
                         'starting and ending with a letter or digit')
    return v


def _check_stripped(v):
    v = v.strip()
    if not v:
        raise ValueError('must not be blank')
    return v


def _check_issuer(v):
    v = v.strip()
    parsed = urlparse(v)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        raise ValueError('must be an absolute http(s) URL')
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('must not contain a query, fragment or credentials')
    return v


def _check_scopes(v):
    tokens = v.split()
    if 'openid' not in tokens:
        raise ValueError("must include 'openid'")
    if len(tokens) > 20 or not all(SCOPE_RE.match(t) for t in tokens):
        raise ValueError('invalid scope list')
    return ' '.join(dict.fromkeys(tokens))


def _check_claims(v):
    v = _string_list(v, max_len=200)
    if not all(CLAIM_RE.match(c) for c in v):
        raise ValueError('invalid claim name')
    return v


def _check_claim(v):
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not CLAIM_RE.match(v):
        raise ValueError('invalid claim name')
    return v


def _check_domains(v):
    v = list(dict.fromkeys(d.lstrip('@') for d in _string_list(v, lower=True)))
    bad = [d for d in v if not DOMAIN_RE.match(d)]
    if bad:
        raise ValueError(f'invalid domain: {bad[0][:60]!r}')
    return v


def _optional(check):
    return lambda v: None if v is None else check(v)


class SsoProviderWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')

    slug: str
    display_name: str = Field(..., min_length=1, max_length=80)
    preset: Literal[PRESETS] = 'generic'
    issuer: str = Field(..., min_length=8, max_length=500)
    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret: Optional[str] = Field(None, max_length=2000)
    token_auth_method: Literal[TOKEN_AUTH_METHODS] = 'client_secret_basic'
    scopes: str = Field('openid email profile', max_length=500)
    email_claims: List[str] = Field(default_factory=lambda: ['email'], min_length=1, max_length=5)
    name_claim: str = Field('name', max_length=100)
    groups_claim: Optional[str] = Field(None, max_length=200)
    role_mappings: List[RoleMapping] = Field(default_factory=list, max_length=MAX_LIST)
    default_role_id: Optional[UUID] = None
    allowed_groups: List[str] = Field(default_factory=list, max_length=MAX_LIST)
    allowed_domains: List[str] = Field(default_factory=list, max_length=MAX_LIST)
    is_enabled: StrictBool = True
    show_on_login: StrictBool = True
    auto_provision: StrictBool = False
    link_existing: StrictBool = False
    require_email_verified: StrictBool = True
    role_sync: Literal[ROLE_SYNC_MODES] = 'first_login'
    mfa_mode: Literal[MFA_MODES] = 'sheetstorm'

    _v_slug = field_validator('slug')(lambda v: _check_slug(v))
    _v_stripped = field_validator('display_name', 'client_id')(lambda v: _check_stripped(v))
    _v_issuer = field_validator('issuer')(lambda v: _check_issuer(v))
    _v_scopes = field_validator('scopes')(lambda v: _check_scopes(v))
    _v_email_claims = field_validator('email_claims')(lambda v: _check_claims(v))
    _v_claim = field_validator('name_claim', 'groups_claim')(lambda v: _check_claim(v))
    _v_groups = field_validator('allowed_groups')(lambda v: _string_list(v))
    _v_domains = field_validator('allowed_domains')(lambda v: _check_domains(v))


class SsoProviderUpdate(SsoProviderWrite):
    """Partial update: every field optional; only the fields sent change."""
    slug: Optional[str] = None
    display_name: Optional[str] = Field(None, min_length=1, max_length=80)
    preset: Optional[Literal[PRESETS]] = None
    issuer: Optional[str] = Field(None, min_length=8, max_length=500)
    client_id: Optional[str] = Field(None, min_length=1, max_length=255)
    token_auth_method: Optional[Literal[TOKEN_AUTH_METHODS]] = None
    scopes: Optional[str] = Field(None, max_length=500)
    email_claims: Optional[List[str]] = Field(None, min_length=1, max_length=5)
    name_claim: Optional[str] = Field(None, max_length=100)
    role_mappings: Optional[List[RoleMapping]] = Field(None, max_length=MAX_LIST)
    allowed_groups: Optional[List[str]] = Field(None, max_length=MAX_LIST)
    allowed_domains: Optional[List[str]] = Field(None, max_length=MAX_LIST)
    is_enabled: Optional[StrictBool] = None
    show_on_login: Optional[StrictBool] = None
    auto_provision: Optional[StrictBool] = None
    link_existing: Optional[StrictBool] = None
    require_email_verified: Optional[StrictBool] = None
    role_sync: Optional[Literal[ROLE_SYNC_MODES]] = None
    mfa_mode: Optional[Literal[MFA_MODES]] = None

    _v_slug = field_validator('slug')(lambda v: _optional(_check_slug)(v))
    _v_stripped = field_validator('display_name', 'client_id')(lambda v: _optional(_check_stripped)(v))
    _v_issuer = field_validator('issuer')(lambda v: _optional(_check_issuer)(v))
    _v_scopes = field_validator('scopes')(lambda v: _optional(_check_scopes)(v))
    _v_email_claims = field_validator('email_claims')(lambda v: _optional(_check_claims)(v))
    _v_groups = field_validator('allowed_groups')(lambda v: _optional(_string_list)(v))
    _v_domains = field_validator('allowed_domains')(lambda v: _optional(_check_domains)(v))
