"""Organization settings schema — the single place to add org setting keys.

`PUT /organization` validates with `OrganizationUpdate` (extra='forbid') and
MERGES the validated keys over the stored settings, so keys owned by other
endpoints (e.g. audit retention / legal hold via /admin/audit-settings)
survive and cannot be written here.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

TLP_LEVELS = ('white', 'green', 'amber', 'amber_strict', 'red')
AI_POLICY_MODES = ('allow', 'local_only', 'block')
TlpLevel = Literal['white', 'green', 'amber', 'amber_strict', 'red']
AiPolicyMode = Literal['allow', 'local_only', 'block']

# Owner decision (_integration.md §1 #22b): red / amber_strict data only goes
# to local (internal, allowlisted) models by default.
AI_TLP_POLICY_DEFAULTS: dict[str, str] = {
    'white': 'allow', 'green': 'allow', 'amber': 'allow',
    'amber_strict': 'local_only', 'red': 'local_only',
}
# Higher = more permissive (a rise is a loosening).
AI_POLICY_RANK = {'block': 0, 'local_only': 1, 'allow': 2}


def effective_ai_tlp_policy(stored) -> dict[str, str]:
    """Stored per-level modes merged over the defaults (unknown values ignored)."""
    policy = dict(AI_TLP_POLICY_DEFAULTS)
    if isinstance(stored, dict):
        policy.update({k: v for k, v in stored.items() if k in policy and v in AI_POLICY_RANK})
    return policy


@lru_cache(maxsize=1)
def _timezones() -> frozenset[str]:
    import zoneinfo
    return frozenset(zoneinfo.available_timezones())


class OrgSettings(BaseModel):
    """Writable organization settings. Every field optional (partial update)."""
    model_config = ConfigDict(extra='forbid')

    timezone: Optional[str] = None
    auto_enrich_iocs: Optional[StrictBool] = None
    # Only meaningful for the default org (registration lands there); the
    # endpoint answers 400 not_applicable elsewhere. Moves to the security
    # policy in W3-SEC.
    registration_enabled: Optional[StrictBool] = None
    enrichment_allow_amber_strict: Optional[StrictBool] = None
    ai_tlp_policy: Optional[Dict[TlpLevel, AiPolicyMode]] = None

    @field_validator('timezone')
    @classmethod
    def _valid_timezone(cls, v):
        if v is not None and v not in _timezones():
            raise ValueError('Unknown IANA timezone')
        return v


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: Optional[str] = None
    settings: Optional[OrgSettings] = None

    @field_validator('name')
    @classmethod
    def _valid_name(cls, v):
        if v is not None and not 1 <= len(v) <= 255:
            raise ValueError('Name must be 1-255 characters')
        return v


# Keys returned by GET /organization (everything writable except
# registration_enabled, which is returned separately to managers only).
PUBLIC_SETTING_KEYS = ('timezone', 'auto_enrich_iocs', 'enrichment_allow_amber_strict')
