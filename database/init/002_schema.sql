-- SheetStorm Database Schema
-- Incident Response Platform with incident response lifecycle tracking

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Organizations (Multi-tenant support)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Roles
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    permissions JSONB NOT NULL DEFAULT '[]',
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    auth_provider VARCHAR(50) DEFAULT 'local',
    auth_provider_id VARCHAR(255),
    supabase_id VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    mfa_enabled BOOLEAN DEFAULT FALSE,
    mfa_secret VARCHAR(255),
    last_login TIMESTAMP WITH TIME ZONE,
    password_changed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_organization ON users(organization_id);
CREATE INDEX idx_users_auth_provider ON users(auth_provider, auth_provider_id);

-- User Roles (Many-to-Many)
CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    granted_by UUID REFERENCES users(id),
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role_id, organization_id)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role ON user_roles(role_id);

-- Password History (for preventing reuse)
CREATE TABLE password_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Sessions (for token management)
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    refresh_token_hash VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_token ON sessions(token_hash);

-- =============================================================================
-- INCIDENT MANAGEMENT
-- =============================================================================

-- Incidents
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    incident_number SERIAL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status VARCHAR(50) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'contained', 'eradicated', 'recovered', 'closed')),
    classification VARCHAR(100),
    phase INTEGER NOT NULL DEFAULT 1 CHECK (phase BETWEEN 1 AND 6),
    lead_responder_id UUID REFERENCES users(id),
    detected_at TIMESTAMP WITH TIME ZONE,
    contained_at TIMESTAMP WITH TIME ZONE,
    eradicated_at TIMESTAMP WITH TIME ZONE,
    recovered_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE,
    executive_summary TEXT,
    lessons_learned TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_incidents_org ON incidents(organization_id);
CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_severity ON incidents(severity);
CREATE INDEX idx_incidents_phase ON incidents(phase);
CREATE UNIQUE INDEX idx_incidents_number_org ON incidents(organization_id, incident_number);

-- Incident Assignments
CREATE TABLE incident_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(100),
    assigned_by UUID REFERENCES users(id),
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(incident_id, user_id)
);

CREATE INDEX idx_incident_assignments_incident ON incident_assignments(incident_id);
CREATE INDEX idx_incident_assignments_user ON incident_assignments(user_id);

-- =============================================================================
-- TIMELINE EVENTS
-- =============================================================================

CREATE TABLE timeline_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    hostname VARCHAR(255),
    activity TEXT NOT NULL,
    source VARCHAR(255),
    mitre_tactic VARCHAR(100),
    mitre_technique VARCHAR(20),
    phase INTEGER CHECK (phase BETWEEN 1 AND 6),
    is_key_event BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_timeline_incident ON timeline_events(incident_id);
CREATE INDEX idx_timeline_timestamp ON timeline_events(timestamp);
CREATE INDEX idx_timeline_hostname ON timeline_events(hostname);
CREATE INDEX idx_timeline_mitre ON timeline_events(mitre_tactic, mitre_technique);

-- =============================================================================
-- COMPROMISED ASSETS
-- =============================================================================

-- Compromised Hosts
CREATE TABLE compromised_hosts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    hostname VARCHAR(255) NOT NULL,
    ip_address INET,
    mac_address VARCHAR(17),
    system_type VARCHAR(255),
    os_version VARCHAR(255),
    evidence TEXT,
    first_seen TIMESTAMP WITH TIME ZONE,
    last_seen TIMESTAMP WITH TIME ZONE,
    containment_status VARCHAR(50) DEFAULT 'active' CHECK (containment_status IN ('active', 'isolated', 'reimaged', 'decommissioned')),
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_compromised_hosts_incident ON compromised_hosts(incident_id);
CREATE INDEX idx_compromised_hosts_hostname ON compromised_hosts(hostname);
CREATE INDEX idx_compromised_hosts_ip ON compromised_hosts(ip_address);

-- Compromised Accounts
CREATE TABLE compromised_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    datetime_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    password_encrypted BYTEA,
    host_system VARCHAR(255),
    sid VARCHAR(100),
    account_type VARCHAR(50) NOT NULL CHECK (account_type IN ('domain', 'local', 'ftp', 'service', 'application', 'other')),
    domain VARCHAR(255),
    is_privileged BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'reset', 'deleted')),
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_compromised_accounts_incident ON compromised_accounts(incident_id);
CREATE INDEX idx_compromised_accounts_name ON compromised_accounts(account_name);
CREATE INDEX idx_compromised_accounts_type ON compromised_accounts(account_type);

-- =============================================================================
-- INDICATORS OF COMPROMISE (IOCs)
-- =============================================================================

-- Network Indicators
CREATE TABLE network_indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE,
    protocol VARCHAR(20),
    port INTEGER,
    dns_ip VARCHAR(255) NOT NULL,
    source_host VARCHAR(255),
    destination_host VARCHAR(255),
    direction VARCHAR(20) CHECK (direction IN ('inbound', 'outbound', 'lateral')),
    description TEXT,
    is_malicious BOOLEAN DEFAULT TRUE,
    threat_intel_source VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_network_iocs_incident ON network_indicators(incident_id);
CREATE INDEX idx_network_iocs_dns_ip ON network_indicators(dns_ip);

-- Host-Based Indicators
CREATE TABLE host_based_indicators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    artifact_type VARCHAR(50) NOT NULL CHECK (artifact_type IN ('wmi_event', 'asep', 'registry', 'scheduled_task', 'service', 'file', 'process', 'other')),
    datetime TIMESTAMP WITH TIME ZONE,
    artifact_value TEXT NOT NULL,
    host VARCHAR(255),
    notes TEXT,
    is_malicious BOOLEAN DEFAULT TRUE,
    remediated BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_host_iocs_incident ON host_based_indicators(incident_id);
CREATE INDEX idx_host_iocs_type ON host_based_indicators(artifact_type);
CREATE INDEX idx_host_iocs_host ON host_based_indicators(host);

-- Malware and Tools
CREATE TABLE malware_tools (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT,
    md5 VARCHAR(32),
    sha256 VARCHAR(64),
    sha512 VARCHAR(128),
    file_size BIGINT,
    creation_time TIMESTAMP WITH TIME ZONE,
    modification_time TIMESTAMP WITH TIME ZONE,
    access_time TIMESTAMP WITH TIME ZONE,
    host VARCHAR(255),
    description TEXT,
    malware_family VARCHAR(255),
    threat_actor VARCHAR(255),
    is_tool BOOLEAN DEFAULT FALSE,
    sandbox_report_url TEXT,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_malware_incident ON malware_tools(incident_id);
CREATE INDEX idx_malware_md5 ON malware_tools(md5);
CREATE INDEX idx_malware_sha256 ON malware_tools(sha256);
CREATE INDEX idx_malware_host ON malware_tools(host);

-- =============================================================================
-- EVIDENCE & ARTIFACTS
-- =============================================================================

-- Artifacts (uploaded files)
CREATE TABLE artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    storage_path TEXT NOT NULL,
    storage_type VARCHAR(50) DEFAULT 'local' CHECK (storage_type IN ('local', 's3')),
    mime_type VARCHAR(255),
    file_size BIGINT NOT NULL,
    md5 VARCHAR(32) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    sha512 VARCHAR(128) NOT NULL,
    description TEXT,
    source VARCHAR(255),
    collected_at TIMESTAMP WITH TIME ZONE,
    is_verified BOOLEAN DEFAULT TRUE,
    verification_status VARCHAR(50) DEFAULT 'verified' CHECK (verification_status IN ('verified', 'mismatch', 'pending')),
    last_verified_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    uploaded_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_artifacts_incident ON artifacts(incident_id);
CREATE INDEX idx_artifacts_sha256 ON artifacts(sha256);
CREATE INDEX idx_artifacts_md5 ON artifacts(md5);

-- Chain of Custody
CREATE TABLE chain_of_custody (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL CHECK (action IN ('upload', 'view', 'download', 'transfer', 'verify', 'export')),
    performed_by UUID NOT NULL REFERENCES users(id),
    ip_address INET,
    user_agent TEXT,
    purpose TEXT,
    recipient_id UUID REFERENCES users(id),
    verification_result VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_custody_artifact ON chain_of_custody(artifact_id);
CREATE INDEX idx_custody_user ON chain_of_custody(performed_by);
CREATE INDEX idx_custody_action ON chain_of_custody(action);

-- =============================================================================
-- TASKS
-- =============================================================================

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'blocked', 'cancelled')),
    priority VARCHAR(20) DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    assignee_id UUID REFERENCES users(id),
    due_date TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    checklist JSONB DEFAULT '[]',
    phase INTEGER CHECK (phase BETWEEN 1 AND 6),
    parent_task_id UUID REFERENCES tasks(id),
    order_index INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_incident ON tasks(incident_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX idx_tasks_status ON tasks(status);

-- Task Comments
CREATE TABLE task_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    author_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_task_comments_task ON task_comments(task_id);

-- =============================================================================
-- ATTACK GRAPH VISUALIZATION
-- =============================================================================

-- Attack Graph Nodes
CREATE TABLE attack_graph_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    node_type VARCHAR(50) NOT NULL CHECK (node_type IN ('workstation', 'server', 'domain_controller', 'attacker', 'c2_server', 'cloud_resource', 'user', 'service_account', 'external', 'unknown')),
    label VARCHAR(255) NOT NULL,
    compromised_host_id UUID REFERENCES compromised_hosts(id),
    compromised_account_id UUID REFERENCES compromised_accounts(id),
    position_x FLOAT DEFAULT 0,
    position_y FLOAT DEFAULT 0,
    is_initial_access BOOLEAN DEFAULT FALSE,
    is_objective BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_graph_nodes_incident ON attack_graph_nodes(incident_id);
CREATE INDEX idx_graph_nodes_type ON attack_graph_nodes(node_type);

-- Attack Graph Edges
CREATE TABLE attack_graph_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    source_node_id UUID NOT NULL REFERENCES attack_graph_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES attack_graph_nodes(id) ON DELETE CASCADE,
    edge_type VARCHAR(50) NOT NULL CHECK (edge_type IN ('lateral_movement', 'credential_theft', 'data_exfiltration', 'command_control', 'initial_access', 'privilege_escalation', 'persistence', 'discovery', 'execution', 'defense_evasion', 'collection')),
    label VARCHAR(255),
    mitre_tactic VARCHAR(100),
    mitre_technique VARCHAR(20),
    timestamp TIMESTAMP WITH TIME ZONE,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_graph_edges_incident ON attack_graph_edges(incident_id);
CREATE INDEX idx_graph_edges_source ON attack_graph_edges(source_node_id);
CREATE INDEX idx_graph_edges_target ON attack_graph_edges(target_node_id);
CREATE INDEX idx_graph_edges_mitre ON attack_graph_edges(mitre_tactic, mitre_technique);

-- =============================================================================
-- INTEGRATIONS & NOTIFICATIONS
-- =============================================================================

-- Integrations
CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL CHECK (type IN ('s3', 'slack', 'openai', 'google_ai', 'oauth_google', 'oauth_github', 'oauth_azure', 'webhook', 'siem')),
    name VARCHAR(255) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}',
    credentials_encrypted BYTEA,
    last_used_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(organization_id, type, name)
);

CREATE INDEX idx_integrations_org ON integrations(organization_id);
CREATE INDEX idx_integrations_type ON integrations(type);

-- Notifications
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    action_url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_notifications_unread ON notifications(user_id, is_read) WHERE NOT is_read;

-- =============================================================================
-- AUDIT LOGS
-- =============================================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    user_email VARCHAR(255),
    event_type VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    ip_address INET,
    user_agent TEXT,
    request_method VARCHAR(10),
    request_path TEXT,
    status_code INTEGER,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_org ON audit_logs(organization_id);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_event ON audit_logs(event_type);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_incident ON audit_logs(incident_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

-- =============================================================================
-- REPORTS
-- =============================================================================

CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    report_type VARCHAR(50) DEFAULT 'full' CHECK (report_type IN ('full', 'executive', 'technical', 'timeline', 'ioc', 'metrics', 'trends')),
    format VARCHAR(20) DEFAULT 'pdf' CHECK (format IN ('pdf', 'html', 'json')),
    storage_path TEXT,
    ai_summary TEXT,
    ai_provider VARCHAR(50),
    sections JSONB DEFAULT '[]',
    generated_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reports_incident ON reports(incident_id);

-- =============================================================================
-- FUNCTIONS & TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at trigger to all relevant tables
CREATE TRIGGER update_organizations_updated_at BEFORE UPDATE ON organizations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON incidents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_timeline_events_updated_at BEFORE UPDATE ON timeline_events FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_compromised_hosts_updated_at BEFORE UPDATE ON compromised_hosts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_compromised_accounts_updated_at BEFORE UPDATE ON compromised_accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_network_indicators_updated_at BEFORE UPDATE ON network_indicators FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_host_based_indicators_updated_at BEFORE UPDATE ON host_based_indicators FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_malware_tools_updated_at BEFORE UPDATE ON malware_tools FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_task_comments_updated_at BEFORE UPDATE ON task_comments FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_attack_graph_nodes_updated_at BEFORE UPDATE ON attack_graph_nodes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_attack_graph_edges_updated_at BEFORE UPDATE ON attack_graph_edges FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_integrations_updated_at BEFORE UPDATE ON integrations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to auto-increment incident number per organization
CREATE OR REPLACE FUNCTION set_incident_number()
RETURNS TRIGGER AS $$
BEGIN
    NEW.incident_number := COALESCE(
        (SELECT MAX(incident_number) + 1 FROM incidents WHERE organization_id = NEW.organization_id),
        1
    );
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER set_incident_number_trigger
BEFORE INSERT ON incidents
FOR EACH ROW
WHEN (NEW.incident_number IS NULL)
EXECUTE FUNCTION set_incident_number();
