---
name: Securing Data
description: Implement database security through encryption, Row-Level Security, connection hardening, backups, and audit logging.
---

## Goal

Protect data at rest and in transit by encrypting sensitive columns, isolating tenant data with Row-Level Security, enforcing secure connections, maintaining reliable backups, and logging all data changes for audit.

## When to Use

- Storing personally identifiable information (PII) such as email, phone, SSN
- Building a multi-tenant application that shares database tables across tenants
- Setting up database access for a new service or environment
- Defining a backup and disaster recovery strategy
- Adding audit trails for compliance requirements

## Instructions

## 1. Encrypt Sensitive Columns

Encrypt PII at the application level before writing to the database. Use a symmetric encryption library (e.g., `cryptography.fernet`) with keys managed through environment configuration, never stored in the database or source code.

```python
from cryptography.fernet import Fernet

# Key loaded from environment config
fernet = Fernet(settings.ENCRYPTION_KEY)


def encrypt_value(plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return fernet.decrypt(ciphertext.encode()).decode()
```

Store encrypted values in `TEXT` or `BYTEA` columns. Mark these columns clearly in the schema:

```sql
CREATE TABLE user_profiles (
    id             BIGSERIAL   PRIMARY KEY,
    user_id        BIGINT      NOT NULL REFERENCES users (id),
    ssn_encrypted  TEXT        NOT NULL,  -- AES-encrypted, app-level
    phone_encrypted TEXT,                 -- AES-encrypted, app-level
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 2. Implement Row-Level Security (RLS)

Use PostgreSQL RLS to enforce tenant isolation at the database level. This provides a safety net even if application code has bugs.

```sql
-- Enable RLS on the table
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- Create a policy that restricts access to the current tenant
CREATE POLICY tenant_isolation ON projects
    USING (tenant_id = current_setting('app.current_tenant_id')::BIGINT);

-- Force RLS even for table owners (important for testing)
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
```

Set the tenant context at the beginning of each request in your application:

```python
def set_tenant_context(session: Session, tenant_id: int) -> None:
    session.execute(
        text("SET LOCAL app.current_tenant_id = :tenant_id"),
        {"tenant_id": str(tenant_id)},
    )
```

The `SET LOCAL` command scopes the setting to the current transaction, ensuring it does not leak across requests.

## 3. Secure Database Connections

Require SSL for all connections and use least-privilege database users.

```sql
-- Create a limited application user
CREATE ROLE app_service WITH LOGIN PASSWORD 'strong-random-password';
GRANT CONNECT ON DATABASE mydb TO app_service;
GRANT USAGE ON SCHEMA public TO app_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_service;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_service;

-- Do NOT grant: CREATE, DROP, ALTER, TRUNCATE, SUPERUSER
```

Enforce SSL in the connection string:

```python
engine = create_engine(
    "postgresql://app_service:password@db-host/mydb",
    connect_args={"sslmode": "verify-full", "sslrootcert": "/path/to/ca.crt"},
)
```

Create separate database users for different services and for migrations:

| User             | Permissions                              |
|------------------|------------------------------------------|
| `app_service`    | SELECT, INSERT, UPDATE, DELETE           |
| `migration_user` | ALL on schema (for running migrations)   |
| `readonly_user`  | SELECT only (for reporting and analytics)|

## 4. Implement Backup Strategy

Use multiple backup approaches for defense in depth.

```bash
# Logical backup with pg_dump (full database)
pg_dump -Fc --no-owner --no-acl mydb > backup_$(date +%Y%m%d_%H%M%S).dump

# Restore from logical backup
pg_restore -d mydb --no-owner --no-acl backup_20250115_143000.dump

# Physical backup with pg_basebackup (for point-in-time recovery)
pg_basebackup -D /backups/base -Ft -z -P

# Enable WAL archiving in postgresql.conf for continuous archiving
# archive_mode = on
# archive_command = 'cp %p /archive/%f'
```

Test backup restoration on a regular schedule. A backup that has not been tested is not a backup.

## 5. Add Audit Logging

Track who changed what and when. Use a dedicated audit table and a trigger function.

```sql
CREATE TABLE audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    table_name  TEXT        NOT NULL,
    record_id   BIGINT      NOT NULL,
    action      TEXT        NOT NULL,  -- INSERT, UPDATE, DELETE
    old_values  JSONB,
    new_values  JSONB,
    changed_by  TEXT        NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION audit_trigger_func()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_by)
    VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        TG_OP,
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END,
        current_setting('app.current_user', true)
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Attach to any table that needs auditing
CREATE TRIGGER audit_users
    AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();
```

## Constraints

### ✅ Do
- Encrypt all PII columns at the application level before storage
- Use separate database users per service with least-privilege permissions
- Test backup restoration regularly, at minimum monthly
- Enable SSL for all database connections
- Use RLS for multi-tenant data isolation as a defense-in-depth measure
- Rotate encryption keys on a defined schedule
- Log all schema changes and privileged operations


### ❌ Don&#x27;t
- Store plaintext passwords; always hash with bcrypt or argon2
- Give the application user superuser or CREATEDB privileges
- Skip backup restoration testing; untested backups are unreliable
- Store encryption keys in the database, source code, or version control
- Rely solely on application-level checks for tenant isolation
- Disable SSL for convenience, even in development environments


## Output Format

Produce SQL scripts for RLS policies, role definitions, and audit triggers. Produce Python modules for encryption utilities. Include configuration snippets for connection security. Document the backup schedule and restoration procedure.

## Dependencies

- [Designing Schemas](../designing-schemas/SKILL.md) — schema must be defined before security policies are applied
- [Environment Config](../../shared/environment-config/SKILL.md) — encryption keys and database credentials are managed through environment configuration
