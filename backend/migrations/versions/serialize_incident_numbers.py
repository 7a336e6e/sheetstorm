"""serialize per-organization incident numbers

``set_incident_number()`` (database/init/002_schema.sql) assigned
MAX(incident_number) + 1 without a lock, so two incidents created at the same
moment in one organization got the same number and the second insert failed
with a unique violation on idx_incidents_number_org (HTTP 500). The function
now takes a transaction-scoped advisory lock per organization first; the
second insert waits for the first to commit and then sees its number (a
VOLATILE plpgsql function takes a fresh snapshot per query under READ
COMMITTED).

Idempotent (CREATE OR REPLACE) and reversible.

Revision ID: serialize_incident_numbers
Revises: add_decision_log
Create Date: 2026-10-10
"""
from alembic import op

revision = 'serialize_incident_numbers'
down_revision = 'add_decision_log'
branch_labels = None
depends_on = None

LOCKED = """
CREATE OR REPLACE FUNCTION set_incident_number()
RETURNS TRIGGER AS $$
BEGIN
    -- One number allocation per organization at a time (released at commit).
    PERFORM pg_advisory_xact_lock(hashtext('sheetstorm.incident_number'), hashtext(NEW.organization_id::text));
    NEW.incident_number := COALESCE(
        (SELECT MAX(incident_number) + 1 FROM incidents WHERE organization_id = NEW.organization_id),
        1
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

ORIGINAL = """
CREATE OR REPLACE FUNCTION set_incident_number()
RETURNS TRIGGER AS $$
BEGIN
    NEW.incident_number := COALESCE(
        (SELECT MAX(incident_number) + 1 FROM incidents WHERE organization_id = NEW.organization_id),
        1
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade():
    op.execute(LOCKED)


def downgrade():
    op.execute(ORIGINAL)
