"""allow ollama + openai_compatible integration types

Revision ID: add_openai_compatible
Revises: add_custody_metadata
Create Date: 2026-06-28
"""
from alembic import op


revision = 'add_openai_compatible'
down_revision = 'add_custody_metadata'
branch_labels = None
depends_on = None

# Full allow-list, including the previously-missing 'ollama' and the new
# 'openai_compatible' (generic local OpenAI-compatible endpoints).
_TYPES = (
    's3', 'openai', 'google_ai', 'ollama', 'openai_compatible',
    'slack', 'email_smtp', 'webhook',
    'oauth_google', 'oauth_github', 'oauth_azure',
    'misp', 'virustotal', 'mitre_attack', 'abuseipdb', 'hibp', 'shodan',
    'velociraptor', 'thehive', 'cortex', 'jira', 'google_drive',
    'siem', 'splunk', 'elastic',
)

_OLD_TYPES = tuple(t for t in _TYPES if t not in ('ollama', 'openai_compatible'))


def _set_constraint(types):
    values = ', '.join(f"'{t}'" for t in types)
    op.execute("ALTER TABLE integrations DROP CONSTRAINT IF EXISTS integrations_type_check")
    op.execute(
        f"ALTER TABLE integrations ADD CONSTRAINT integrations_type_check "
        f"CHECK (type IN ({values}))"
    )


def upgrade():
    _set_constraint(_TYPES)


def downgrade():
    _set_constraint(_OLD_TYPES)
