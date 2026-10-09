"""pg_trgm + trigram GIN indexes for global search

Enables the pg_trgm contrib extension (trusted, so the database owner can
create it) and adds one GIN expression index per searchable table on the
exact search-doc expression that services/search_service.py queries with
ILIKE '%q%' (tests/test_search.py asserts the SQL text is identical and that
the planner uses the index). Plain (non-CONCURRENT) builds: self-hosted
single-node databases, run once during `flask db upgrade`.

Downgrade drops the indexes but keeps the extension (other objects may
depend on it; it is harmless).

Revision ID: add_search_trgm_indexes
Revises: custody_key_id_admin_perm
Create Date: 2026-10-08
"""
from alembic import op

revision = 'add_search_trgm_indexes'
down_revision = 'custody_key_id_admin_perm'
branch_labels = None
depends_on = None

# table -> indexed expression. Must stay byte-identical to
# search_service.index_expression_sql() for the planner to match it.
INDEXES = {
    'incidents': (
        "coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || "
        "coalesce(executive_summary, '') || ' ' || coalesce(classification, '')"
    ),
    'timeline_events': (
        "coalesce(activity, '') || ' ' || coalesce(hostname, '') || ' ' || "
        "coalesce(mitre_tactic, '') || ' ' || coalesce(CAST(mitre_mappings AS TEXT), '')"
    ),
    'compromised_hosts': (
        "coalesce(hostname, '') || ' ' || coalesce(host(ip_address), '') || ' ' || "
        "coalesce(system_type, '') || ' ' || coalesce(notes, '')"
    ),
    'compromised_accounts': (
        "coalesce(account_name, '') || ' ' || coalesce(domain, '') || ' ' || coalesce(notes, '')"
    ),
    'network_indicators': (
        "coalesce(dns_ip, '') || ' ' || coalesce(source_host, '') || ' ' || "
        "coalesce(destination_host, '') || ' ' || coalesce(description, '')"
    ),
    'host_based_indicators': (
        "coalesce(artifact_value, '') || ' ' || coalesce(notes, '') || ' ' || coalesce(host, '')"
    ),
    'malware_tools': (
        "coalesce(file_name, '') || ' ' || coalesce(file_path, '') || ' ' || coalesce(md5, '') || ' ' || "
        "coalesce(sha256, '') || ' ' || coalesce(malware_family, '') || ' ' || coalesce(description, '')"
    ),
    'case_notes': "coalesce(title, '') || ' ' || coalesce(content, '')",
}


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    for table, expr in INDEXES.items():
        op.execute(
            f'CREATE INDEX IF NOT EXISTS ix_{table}_search_trgm '
            f'ON {table} USING gin (({expr}) gin_trgm_ops)'
        )


def downgrade():
    for table in INDEXES:
        op.execute(f'DROP INDEX IF EXISTS ix_{table}_search_trgm')
