"""Update integrations_type_check to allow all integration types

Revision ID: update_integration_type_check
Revises: expand_containment_01
Create Date: 2026-03-10
"""
from alembic import op

revision = 'update_integration_type_check'
down_revision = 'expand_containment_01'
branch_labels = None
depends_on = None

# Must match Integration.INTEGRATION_TYPES in app/models/integration.py
ALL_TYPES = [
    's3',
    'openai', 'google_ai',
    'slack', 'email_smtp', 'webhook',
    'oauth_google', 'oauth_github', 'oauth_azure',
    'misp', 'virustotal', 'mitre_attack',
    'abuseipdb', 'hibp', 'shodan',
    'velociraptor', 'thehive', 'cortex',
    'jira',
    'google_drive',
    'siem', 'splunk', 'elastic',
]

OLD_TYPES = [
    's3', 'slack', 'openai', 'google_ai',
    'oauth_google', 'oauth_github', 'oauth_azure',
    'webhook', 'siem',
]


def upgrade():
    op.execute("ALTER TABLE integrations DROP CONSTRAINT IF EXISTS integrations_type_check")
    types_str = "', '".join(ALL_TYPES)
    op.execute(
        f"ALTER TABLE integrations ADD CONSTRAINT integrations_type_check "
        f"CHECK (type IN ('{types_str}'))"
    )


def downgrade():
    op.execute("ALTER TABLE integrations DROP CONSTRAINT IF EXISTS integrations_type_check")
    types_str = "', '".join(OLD_TYPES)
    op.execute(
        f"ALTER TABLE integrations ADD CONSTRAINT integrations_type_check "
        f"CHECK (type IN ('{types_str}'))"
    )
