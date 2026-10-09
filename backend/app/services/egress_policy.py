"""TLP egress control for threat-intel enrichment (server-side, not UI-only).

Enrichment sends indicator values to third-party services (VirusTotal,
AbuseIPDB, HIBP, ...). Values that belong to restricted incidents must not
leave:

* ``red`` is ALWAYS blocked; no setting can unblock it;
* ``amber_strict`` is blocked unless the organization setting
  ``enrichment_allow_amber_strict`` is true (default false).

A value is blocked when it appears (case-insensitively) in any restricted
incident of the organization, whichever incident or endpoint asks for it.
Covered paths: IOC auto-enrichment on create, playbook ``enrich_iocs``,
``POST /bulk-enrich`` and the ``/threat-intel/*/lookup`` endpoints.

AI egress is governed separately (``ai_service`` + org ``ai_tlp_policy``).
"""
from sqlalchemy import func

ALWAYS_BLOCKED_TLPS = frozenset({'red'})


class EgressBlocked(Exception):
    """403 ``tlp_restricted``."""
    status = 403
    code = 'tlp_restricted'

    def __init__(self, tlp=None, message=None, blocked_count=None):
        self.tlp = tlp
        self.blocked_count = blocked_count
        self.message = message or (
            f'TLP:{str(tlp).upper()} data may not be sent to external enrichment services'
            if tlp else 'Restricted (TLP) data may not be sent to external enrichment services')
        super().__init__(self.message)

    def to_dict(self):
        body = {'error': self.code, 'message': self.message}
        if self.tlp:
            body['tlp'] = self.tlp
        if self.blocked_count is not None:
            body['blocked_count'] = self.blocked_count
        return body

    def to_response(self):
        from flask import jsonify
        return jsonify(self.to_dict()), self.status


def _org_settings(organization_id):
    import uuid
    from app import db
    from app.models import Organization
    if not organization_id:
        return {}
    org = db.session.get(Organization, uuid.UUID(str(organization_id)))
    return (org.settings if org else None) or {}


def blocked_tlps(organization_id) -> frozenset:
    """TLP levels whose data may not be enriched for this organization."""
    blocked = set(ALWAYS_BLOCKED_TLPS)
    if _org_settings(organization_id).get('enrichment_allow_amber_strict') is not True:
        blocked.add('amber_strict')
    return frozenset(blocked)


def enrichment_allowed(incident) -> bool:
    return incident is not None and incident.tlp not in blocked_tlps(incident.organization_id)


def assert_enrichment_allowed(incident):
    """Raise ``EgressBlocked`` when this incident's TLP forbids enrichment."""
    if incident is None:
        return
    if incident.tlp in blocked_tlps(incident.organization_id):
        raise EgressBlocked(incident.tlp)


def _norm(value) -> str:
    return str(value).strip().lower()


def _restricted_values(organization_id, lowered, tlps):
    """Subset of ``lowered`` values present in the org's incidents with ``tlps``."""
    from app.models import (Incident, NetworkIndicator, HostBasedIndicator, MalwareTool,
                            CompromisedHost, CompromisedAccount)
    from sqlalchemy import cast, String

    columns = [
        (NetworkIndicator, NetworkIndicator.dns_ip),
        (HostBasedIndicator, HostBasedIndicator.artifact_value),
        (MalwareTool, MalwareTool.md5),
        (MalwareTool, MalwareTool.sha256),
        (MalwareTool, MalwareTool.sha512),
        (MalwareTool, MalwareTool.file_name),
        (CompromisedHost, CompromisedHost.hostname),
        (CompromisedHost, func.host(CompromisedHost.ip_address)),
        (CompromisedAccount, CompromisedAccount.account_name),
    ]
    found = set()
    for model, col in columns:
        expr = func.lower(cast(col, String))
        rows = (model.query.with_entities(expr)
                .join(Incident, Incident.id == model.incident_id)
                .filter(Incident.organization_id == organization_id,
                        Incident.tlp.in_(list(tlps)),
                        expr.in_(list(lowered)))
                .distinct().all())
        found.update(r[0] for r in rows if r[0])
        if len(found) == len(lowered):
            break
    return found


def filter_values_for_enrichment(organization_id, values):
    """Split ``values`` into ``(allowed, blocked)`` (original order and spelling).

    A value is blocked if it appears in any incident of the organization whose
    TLP is restricted (see ``blocked_tlps``). Empty values are dropped.
    """
    values = [v for v in (values or []) if v is not None and str(v).strip()]
    if not values:
        return [], []
    lowered = {_norm(v) for v in values}
    restricted = _restricted_values(organization_id, lowered, blocked_tlps(organization_id))
    allowed = [v for v in values if _norm(v) not in restricted]
    blocked = [v for v in values if _norm(v) in restricted]
    return allowed, blocked


def assert_values_allowed(organization_id, values):
    """Raise ``EgressBlocked`` if any of ``values`` is restricted."""
    _, blocked = filter_values_for_enrichment(organization_id, values)
    if blocked:
        raise EgressBlocked(blocked_count=len(blocked))
