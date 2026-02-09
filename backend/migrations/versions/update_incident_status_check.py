"""Update incidents status check constraint to include investigating

Revision ID: update_incident_status_check
Revises: update_report_type_check
Create Date: 2026-02-09

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'update_incident_status_check'
down_revision = 'update_report_type_check'
branch_labels = None
depends_on = None


def upgrade():
    """Replace the incidents_status_check constraint to allow 'investigating' status."""
    op.execute("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS incidents_status_check")
    op.execute(
        "ALTER TABLE incidents ADD CONSTRAINT incidents_status_check "
        "CHECK (status IN ('open', 'investigating', 'contained', 'eradicated', 'recovered', 'closed'))"
    )


def downgrade():
    """Revert to original check constraint without 'investigating'."""
    op.execute("ALTER TABLE incidents DROP CONSTRAINT IF EXISTS incidents_status_check")
    op.execute(
        "ALTER TABLE incidents ADD CONSTRAINT incidents_status_check "
        "CHECK (status IN ('open', 'contained', 'eradicated', 'recovered', 'closed'))"
    )
