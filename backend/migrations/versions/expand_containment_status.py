"""Expand containment_status check constraint.

Add 'compromised' and 'contained' as valid statuses alongside
the existing set.  These are standard IR lifecycle states that
were missing from the original constraint.

Revision ID: expand_containment_01
Revises: (head)
"""
from alembic import op

revision = 'expand_containment_01'
down_revision = 'add_soft_delete_columns'
branch_labels = None
depends_on = None

# New valid set — superset of the original
VALID_STATUSES = (
    "'active'",
    "'compromised'",
    "'isolated'",
    "'contained'",
    "'reimaged'",
    "'cleaned'",
    "'decommissioned'",
)


def upgrade():
    op.drop_constraint(
        'compromised_hosts_containment_status_check',
        'compromised_hosts',
        type_='check',
    )
    values = ", ".join(VALID_STATUSES)
    op.create_check_constraint(
        'compromised_hosts_containment_status_check',
        'compromised_hosts',
        f"containment_status IN ({values})",
    )


def downgrade():
    op.drop_constraint(
        'compromised_hosts_containment_status_check',
        'compromised_hosts',
        type_='check',
    )
    op.create_check_constraint(
        'compromised_hosts_containment_status_check',
        'compromised_hosts',
        "containment_status IN ('active', 'isolated', 'reimaged', 'decommissioned')",
    )
