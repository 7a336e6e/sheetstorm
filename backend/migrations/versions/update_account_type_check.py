"""Add 'admin' to compromised_accounts account_type check constraint

Revision ID: update_account_type_check
"""
from alembic import op

revision = 'update_account_type_check'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE compromised_accounts
        DROP CONSTRAINT IF EXISTS compromised_accounts_account_type_check;

        ALTER TABLE compromised_accounts
        ADD CONSTRAINT compromised_accounts_account_type_check
        CHECK (account_type IN ('domain', 'local', 'ftp', 'service', 'application', 'admin', 'other'));
    """)


def downgrade():
    op.execute("""
        ALTER TABLE compromised_accounts
        DROP CONSTRAINT IF EXISTS compromised_accounts_account_type_check;

        ALTER TABLE compromised_accounts
        ADD CONSTRAINT compromised_accounts_account_type_check
        CHECK (account_type IN ('domain', 'local', 'ftp', 'service', 'application', 'other'));
    """)
