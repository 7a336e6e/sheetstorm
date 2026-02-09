"""Update report_type check constraint to include metrics and trends

Revision ID: update_report_type_check
Revises: add_mfa_backup_codes
Create Date: 2026-02-09

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'update_report_type_check'
down_revision = 'add_mfa_backup_codes'
branch_labels = None
depends_on = None


def upgrade():
    """Replace the reports_report_type_check constraint to allow all report types."""
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS reports_report_type_check")
    op.execute(
        "ALTER TABLE reports ADD CONSTRAINT reports_report_type_check "
        "CHECK (report_type IN ('full', 'executive', 'technical', 'timeline', 'ioc', 'metrics', 'trends'))"
    )


def downgrade():
    """Revert to original check constraint."""
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS reports_report_type_check")
    op.execute(
        "ALTER TABLE reports ADD CONSTRAINT reports_report_type_check "
        "CHECK (report_type IN ('full', 'executive', 'technical', 'timeline', 'ioc'))"
    )
