"""Permission catalog — the single source of truth for every permission key.

Every authorization decision checks a key from this catalog; no decision
depends on a role's name. `test_permission_registry.py` fails when code
enforces a key that is not listed here, and when the seeded system roles drift
from `SYSTEM_ROLE_PERMISSIONS`.

Flags:
- dangerous:         destructive or security-sensitive; the UI asks to confirm
                     before granting it.
- privileged:        part of the MFA "privileged" scope; never a default role.
- api_key_grantable: may be granted to an API key's scopes.
- platform_only:     only effective in the platform organization
                     (`config.PLATFORM_ORG_SLUG`); a custom role of any other
                     organization can never hold it.

Effective permissions are additive: the union over all of a user's roles
(only roles that are global system roles or belong to the user's own org).
No role ever restricts another.

New keys and grants are registered here AND granted by one data migration
(`admin_guardrails_rbac` for the initial set). Feature migrations must not
`UPDATE roles`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    key: str
    group: str
    label: str
    description: str
    dangerous: bool = False
    privileged: bool = False
    api_key_grantable: bool = True
    platform_only: bool = False

    def to_dict(self) -> dict:
        return {
            'key': self.key,
            'group': self.group,
            'label': self.label,
            'description': self.description,
            'dangerous': self.dangerous,
            'privileged': self.privileged,
            'api_key_grantable': self.api_key_grantable,
            'platform_only': self.platform_only,
        }


# Ordered: the roles UI renders groups in this order.
GROUPS: dict[str, str] = {
    'incidents': 'Incidents',
    'timeline': 'Timeline',
    'hosts': 'Hosts',
    'accounts': 'Accounts',
    'network_iocs': 'Network IOCs',
    'host_iocs': 'Host IOCs',
    'malware': 'Malware & tools',
    'artifacts': 'Artifacts & evidence',
    'tasks': 'Tasks',
    'case_notes': 'Case notes',
    'attack_graph': 'Attack graph',
    'reports': 'Reports',
    'templates': 'Templates & playbooks',
    'decisions': 'Decision log',
    'response_actions': 'Response actions',
    'metrics': 'Metrics',
    'improvements': 'Improvements',
    'users': 'Users',
    'roles': 'Roles',
    'teams': 'Teams',
    'integrations': 'Integrations',
    'audit_logs': 'Audit logs',
    'organizations': 'Organization',
    'api_keys': 'API keys',
    'system': 'System',
    'knowledge_base': 'Knowledge base',
}

P = Permission

_CRUD_LABELS = {'create': 'Create', 'read': 'View', 'update': 'Edit', 'delete': 'Delete'}


def _crud(group: str, noun: str, *, delete_dangerous: bool = False) -> tuple[Permission, ...]:
    return tuple(
        P(f'{group}:{action}', group, f'{label} {noun}', f'{label} {noun} on incidents you can access.',
          dangerous=(action == 'delete' and delete_dangerous))
        for action, label in _CRUD_LABELS.items()
    )


PERMISSIONS: tuple[Permission, ...] = (
    # ── Incidents ──
    P('incidents:create', 'incidents', 'Create incidents', 'Open new incidents.'),
    P('incidents:read', 'incidents', 'View incidents',
      'Read incidents you can see. Alone it grants only directly assigned incidents; '
      'the read_all / read_team / read_tlp_white scopes widen visibility.'),
    P('incidents:update', 'incidents', 'Edit incidents', 'Edit incidents you can access, run playbooks, add notes.'),
    P('incidents:archive', 'incidents', 'Archive incidents', 'Archive and restore incidents and list archived ones.'),
    P('incidents:purge', 'incidents', 'Permanently delete incidents',
      'Irreversibly delete an archived incident and all of its data.', dangerous=True, privileged=True),
    P('incidents:read_all', 'incidents', 'See all incidents', 'Visibility scope: every incident in the organization.'),
    P('incidents:read_team', 'incidents', 'See team incidents',
      'Visibility scope: incidents of your teams and incidents not restricted to a team.'),
    P('incidents:read_tlp_white', 'incidents', 'See TLP:WHITE incidents',
      'Visibility scope: every TLP:WHITE incident in the organization.'),
    P('incidents:export', 'incidents', 'Export incident data',
      'Bulk exports: CSV/STIX, evidence register, custody bundles, decision-log export.', dangerous=True),
    # ── Investigation data ──
    *_crud('timeline', 'timeline events'),
    *_crud('hosts', 'compromised hosts'),
    *_crud('accounts', 'compromised accounts'),
    P('compromised_accounts:reveal', 'accounts', 'Reveal account passwords',
      'Reveal stored credentials of compromised accounts.', dangerous=True),
    *_crud('network_iocs', 'network IOCs'),
    *_crud('host_iocs', 'host-based IOCs'),
    *_crud('malware', 'malware & tools'),
    P('artifacts:upload', 'artifacts', 'Upload artifacts', 'Upload evidence files to incidents you can access.'),
    P('artifacts:read', 'artifacts', 'View artifacts', 'List artifacts, verify hashes and read chain of custody.'),
    P('artifacts:download', 'artifacts', 'Download artifacts', 'Download evidence files.'),
    P('artifacts:delete', 'artifacts', 'Delete artifacts', 'Delete evidence files.', dangerous=True),
    *_crud('tasks', 'tasks'),
    P('case_notes:delete', 'case_notes', 'Delete case notes', 'Delete case notes on incidents you can access.'),
    *_crud('attack_graph', 'attack graph nodes and edges'),
    P('reports:generate', 'reports', 'Generate reports', 'Generate incident reports.'),
    P('reports:read', 'reports', 'View reports', 'Read and download generated reports.'),
    P('templates:manage', 'templates', 'Manage templates & playbooks',
      'Create, edit and delete case templates and playbooks.'),
    # ── Decision log / response actions ──
    P('decisions:read', 'decisions', 'View decisions', 'Read the incident decision log.'),
    P('decisions:create', 'decisions', 'Record decisions', 'Record decisions in the decision log.'),
    P('decisions:update', 'decisions', 'Edit decisions', 'Revise decisions (every revision is kept).'),
    P('decisions:approve', 'decisions', 'Approve decisions', 'Approve or reject decisions.',
      api_key_grantable=False),
    P('decisions:read_privileged', 'decisions', 'View privileged decisions',
      'Read decisions marked privileged (legal / HR).', dangerous=True, api_key_grantable=False),
    P('response_actions:read', 'response_actions', 'View response actions', 'Read response actions.'),
    P('response_actions:create', 'response_actions', 'Create response actions', 'Plan response actions.'),
    P('response_actions:update', 'response_actions', 'Edit response actions',
      'Update response actions and their execution status.'),
    P('response_actions:authorize', 'response_actions', 'Authorize response actions',
      'Authorize response actions before execution.', api_key_grantable=False),
    # ── Post-incident ──
    P('metrics:read', 'metrics', 'View metrics', 'Read response metrics (dwell time, MTTD/MTTR).'),
    P('improvements:read', 'improvements', 'View improvements', 'Read after-action improvement items.'),
    P('improvements:create', 'improvements', 'Create improvements', 'Create after-action improvement items.'),
    P('improvements:update', 'improvements', 'Edit improvements', 'Update improvement items.'),
    P('improvements:delete', 'improvements', 'Delete improvements', 'Delete improvement items.'),
    # ── Administration ──
    P('users:create', 'users', 'Create users', 'Create user accounts.',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('users:read', 'users', 'View users', 'List users, roles and team members.'),
    P('users:update', 'users', 'Edit users', 'Edit user profiles.', api_key_grantable=False),
    P('users:delete', 'users', 'Delete users', 'Delete user accounts.',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('users:manage', 'users', 'Manage users', 'Disable accounts, reset passwords, sync identity providers.',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('roles:manage', 'roles', 'Manage roles', 'Create and edit custom roles and assign roles to users.',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('teams:create', 'teams', 'Create teams', 'Create teams.'),
    P('teams:read', 'teams', 'View teams', 'List teams.'),
    P('teams:update', 'teams', 'Edit teams', 'Rename teams and change membership.'),
    P('teams:delete', 'teams', 'Delete teams', 'Delete teams.'),
    P('integrations:create', 'integrations', 'Create integrations', 'Add integrations (they hold credentials).',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('integrations:read', 'integrations', 'View integrations', 'List integrations and their settings.'),
    P('integrations:update', 'integrations', 'Edit integrations', 'Change integrations and their credentials.',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('integrations:delete', 'integrations', 'Delete integrations', 'Remove integrations.',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('audit_logs:read', 'audit_logs', 'View audit logs', 'Read the audit log and admin activity.'),
    P('audit_logs:export', 'audit_logs', 'Export audit logs', 'Export the audit log.', dangerous=True),
    P('organizations:manage', 'organizations', 'Manage organization',
      'Change organization settings (registration, data egress, retention).',
      dangerous=True, privileged=True, api_key_grantable=False),
    P('api_keys:own', 'api_keys', 'Own API keys', 'Create and revoke your own API keys.',
      api_key_grantable=False),
    P('api_keys:manage', 'api_keys', 'Manage API keys', "Manage every API key in the organization.",
      dangerous=True, privileged=True, api_key_grantable=False),
    P('system:manage', 'system', 'Manage platform', 'Instance-wide settings (platform organization only).',
      dangerous=True, privileged=True, api_key_grantable=False, platform_only=True),
    P('admin:manage', 'knowledge_base', 'Manage MITRE detection patterns',
      'Create, edit and delete the MITRE detection patterns used for suggestions.',
      dangerous=True, privileged=True, api_key_grantable=False),
)

del P

PERMISSION_KEYS: frozenset[str] = frozenset(p.key for p in PERMISSIONS)
PERMISSIONS_BY_KEY: dict[str, Permission] = {p.key: p for p in PERMISSIONS}

# Holding both makes a user an administrator for the last-admin guard.
ADMIN_CORE: frozenset[str] = frozenset({'users:manage', 'roles:manage'})

PLATFORM_ONLY_KEYS: frozenset[str] = frozenset(p.key for p in PERMISSIONS if p.platform_only)


def _with_crud(*groups: str, actions=('create', 'read', 'update', 'delete')) -> list[str]:
    return [f'{g}:{a}' for g in groups for a in actions]


_EVIDENCE_GROUPS = ('timeline', 'hosts', 'accounts', 'network_iocs', 'host_iocs', 'malware')

# Canonical post-migration permission sets of the six global system roles.
# Must equal the database after `flask db upgrade` (test_system_roles_match_registry).
SYSTEM_ROLE_PERMISSIONS: dict[str, list[str]] = {
    'Administrator': sorted(PERMISSION_KEYS - {
        'incidents:read_team', 'incidents:read_tlp_white',  # read_all subsumes them
    }),
    'Incident Responder': sorted({
        'incidents:create', 'incidents:read', 'incidents:update', 'incidents:read_team', 'incidents:export',
        *_with_crud(*_EVIDENCE_GROUPS),
        'compromised_accounts:reveal',
        'artifacts:upload', 'artifacts:read', 'artifacts:download',
        'tasks:create', 'tasks:read', 'tasks:update',
        *_with_crud('attack_graph'),
        'reports:generate', 'reports:read',
        'templates:manage',
        'decisions:read', 'decisions:create', 'decisions:update', 'decisions:approve', 'decisions:read_privileged',
        'response_actions:read', 'response_actions:create', 'response_actions:update',
        'response_actions:authorize',
        'metrics:read', 'improvements:read', 'improvements:create', 'improvements:update',
        'users:read', 'teams:read', 'api_keys:own',
    }),
    'Analyst': sorted({
        'incidents:read', 'incidents:update', 'incidents:read_team',
        *_with_crud(*_EVIDENCE_GROUPS, actions=('create', 'read', 'update')),
        'artifacts:upload', 'artifacts:read', 'artifacts:download',
        'tasks:read', 'tasks:update',
        *_with_crud('attack_graph', actions=('create', 'read', 'update')),
        'decisions:read', 'decisions:create', 'decisions:update',
        'response_actions:read', 'response_actions:create', 'response_actions:update',
        'improvements:read', 'improvements:update',
        'users:read', 'teams:read', 'api_keys:own',
    }),
    'Manager': sorted({
        'incidents:read', 'incidents:read_all', 'incidents:export',
        *_with_crud(*_EVIDENCE_GROUPS, actions=('read',)),
        'artifacts:read', 'artifacts:download',
        'tasks:read', 'attack_graph:read',
        'reports:generate', 'reports:read',
        'decisions:read', 'decisions:approve', 'decisions:read_privileged',
        'response_actions:read', 'response_actions:authorize',
        'metrics:read', 'improvements:read', 'improvements:create', 'improvements:update',
        'users:read', 'teams:read', 'audit_logs:read', 'api_keys:own',
    }),
    'Operator': sorted({
        'incidents:read',
        *_with_crud(*_EVIDENCE_GROUPS, actions=('read',)),
        'timeline:create',
        'artifacts:read',
        'tasks:read', 'tasks:update', 'attack_graph:read',
        'decisions:read',
        'response_actions:read', 'response_actions:update',
        'improvements:read', 'improvements:update',
        'users:read', 'teams:read', 'api_keys:own',
    }),
    'Viewer': sorted({
        'incidents:read', 'incidents:read_tlp_white',
        *_with_crud(*_EVIDENCE_GROUPS, actions=('read',)),
        'tasks:read', 'attack_graph:read',
        'decisions:read', 'response_actions:read', 'improvements:read',
    }),
}

SYSTEM_ROLE_NAMES: frozenset[str] = frozenset(SYSTEM_ROLE_PERMISSIONS)


# A broader visibility scope covers the narrower ones for grant / hierarchy
# comparisons (the Administrator holds read_all, not read_team).
IMPLIED_PERMISSIONS: dict[str, frozenset[str]] = {
    'incidents:read_all': frozenset({'incidents:read_team', 'incidents:read_tlp_white'}),
}


def with_implied(perms) -> set[str]:
    """`perms` plus every permission they imply (for guard comparisons only)."""
    out = set(perms or ())
    for key in list(out):
        out |= IMPLIED_PERMISSIONS.get(key, frozenset())
    return out


def unknown_permissions(perms) -> list[str]:
    """Keys in `perms` that are not in the catalog (sorted, deduplicated)."""
    return sorted({p for p in (perms or []) if p not in PERMISSION_KEYS})


def is_privileged(perms) -> bool:
    """True when any of `perms` is in the privileged (MFA-scope) set."""
    return any(PERMISSIONS_BY_KEY[p].privileged for p in (perms or []) if p in PERMISSIONS_BY_KEY)


def api_key_grantable_keys() -> frozenset[str]:
    return frozenset(p.key for p in PERMISSIONS if p.api_key_grantable)
