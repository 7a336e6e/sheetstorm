-- Seed system roles with permissions

INSERT INTO roles (name, description, permissions, is_system) VALUES
(
    'Administrator',
    'Full system access including user management and system configuration',
    '[
        "incidents:create", "incidents:read", "incidents:update", "incidents:delete",
        "timeline:create", "timeline:read", "timeline:update", "timeline:delete",
        "hosts:create", "hosts:read", "hosts:update", "hosts:delete",
        "accounts:create", "accounts:read", "accounts:update", "accounts:delete",
        "compromised_accounts:reveal",
        "network_iocs:create", "network_iocs:read", "network_iocs:update", "network_iocs:delete",
        "host_iocs:create", "host_iocs:read", "host_iocs:update", "host_iocs:delete",
        "malware:create", "malware:read", "malware:update", "malware:delete",
        "artifacts:upload", "artifacts:read", "artifacts:download", "artifacts:delete",
        "tasks:create", "tasks:read", "tasks:update", "tasks:delete",
        "attack_graph:create", "attack_graph:read", "attack_graph:update", "attack_graph:delete",
        "reports:generate", "reports:read",
        "users:create", "users:read", "users:update", "users:delete", "users:manage",
        "roles:manage",
        "integrations:create", "integrations:read", "integrations:update", "integrations:delete",
        "audit_logs:read",
        "organizations:manage"
    ]'::jsonb,
    TRUE
),
(
    'Incident Responder',
    'Create and manage incidents, full evidence access, lead response efforts',
    '[
        "incidents:create", "incidents:read", "incidents:update",
        "timeline:create", "timeline:read", "timeline:update", "timeline:delete",
        "hosts:create", "hosts:read", "hosts:update", "hosts:delete",
        "accounts:create", "accounts:read", "accounts:update", "accounts:delete",
        "compromised_accounts:reveal",
        "network_iocs:create", "network_iocs:read", "network_iocs:update", "network_iocs:delete",
        "host_iocs:create", "host_iocs:read", "host_iocs:update", "host_iocs:delete",
        "malware:create", "malware:read", "malware:update", "malware:delete",
        "artifacts:upload", "artifacts:read", "artifacts:download",
        "tasks:create", "tasks:read", "tasks:update",
        "attack_graph:create", "attack_graph:read", "attack_graph:update", "attack_graph:delete",
        "reports:generate", "reports:read",
        "users:read"
    ]'::jsonb,
    TRUE
),
(
    'Analyst',
    'View incidents, add timeline events and IOCs, upload artifacts',
    '[
        "incidents:read", "incidents:update",
        "timeline:create", "timeline:read", "timeline:update",
        "hosts:create", "hosts:read", "hosts:update",
        "accounts:create", "accounts:read", "accounts:update",
        "network_iocs:create", "network_iocs:read", "network_iocs:update",
        "host_iocs:create", "host_iocs:read", "host_iocs:update",
        "malware:create", "malware:read", "malware:update",
        "artifacts:upload", "artifacts:read", "artifacts:download",
        "tasks:read", "tasks:update",
        "attack_graph:create", "attack_graph:read", "attack_graph:update",
        "users:read"
    ]'::jsonb,
    TRUE
),
(
    'Manager',
    'View all incidents, generate reports, review team activity',
    '[
        "incidents:read",
        "timeline:read",
        "hosts:read",
        "accounts:read",
        "network_iocs:read",
        "host_iocs:read",
        "malware:read",
        "artifacts:read", "artifacts:download",
        "tasks:read",
        "attack_graph:read",
        "reports:generate", "reports:read",
        "users:read",
        "audit_logs:read"
    ]'::jsonb,
    TRUE
),
(
    'Operator',
    'View assigned incidents, update tasks, add basic information',
    '[
        "incidents:read",
        "timeline:read", "timeline:create",
        "hosts:read",
        "accounts:read",
        "network_iocs:read",
        "host_iocs:read",
        "malware:read",
        "artifacts:read",
        "tasks:read", "tasks:update",
        "attack_graph:read",
        "users:read"
    ]'::jsonb,
    TRUE
),
(
    'Viewer',
    'Read-only access to incidents',
    '[
        "incidents:read",
        "timeline:read",
        "hosts:read",
        "accounts:read",
        "network_iocs:read",
        "host_iocs:read",
        "malware:read",
        "artifacts:read",
        "tasks:read",
        "attack_graph:read",
        "reports:read",
        "users:read"
    ]'::jsonb,
    TRUE
);
