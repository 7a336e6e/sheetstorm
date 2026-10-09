"""evidence register + tamper-evident custody ledger (v3)

Upgrade (each step idempotent; triggers LAST):

1. Tables ``custody_parties``, ``evidence_items``, ``custody_anchors``.
2. Columns: ``artifacts.evidence_item_id / purpose / deleted_at / deleted_by /
   deletion_reason / content_purged``; ``chain_of_custody.evidence_item_id /
   incident_id / seq / incident_seq / prev_hash / incident_prev_hash /
   entry_hash / chain_version / external_party_id / transfer_method``; the
   custody action CHECK grows to the v3 action list.
3. Backfill (SQL only): one ``digital_file`` evidence item per existing
   artifact (``sequence_number`` = row_number per incident ordered by
   ``created_at, id``; title = original filename; md5/sha256/sha512 as
   ``computed_on_upload`` acquisition hashes; acquisition fields copied;
   ``source_host_label`` = ``source_host``; ``created_by`` = ``uploaded_by``;
   organization from the incident). Then ``artifacts.evidence_item_id`` and
   ``chain_of_custody.evidence_item_id / incident_id`` through the artifact.
   Existing custody rows stay legacy (``chain_version`` NULL, unchained);
   the first v3 entry of each item / incident seals them (legacy_seal).
4. NOT NULL on the backfilled columns; ``chain_of_custody.artifact_id``
   becomes NULLable and its FK changes from ON DELETE CASCADE to NO ACTION
   (an artifact delete can no longer destroy custody history).
5. ``custody_append_only()`` + BEFORE UPDATE/DELETE (row) and BEFORE
   TRUNCATE (statement) triggers on ``chain_of_custody`` and
   ``custody_anchors``. A DELETE is allowed only when the transaction-local
   GUC ``sheetstorm.custody_purge`` equals the row's incident id (the audited
   incident purge, services/incident_purge.py).

Downgrade (LOSSY, documented): triggers are dropped first; every v3 ledger
row (``chain_version`` NOT NULL) and every row without an artifact is
DELETED; tombstoned artifacts and their remaining custody rows are DELETED
(the pre-v3 behaviour was a hard delete); evidence items, custody parties
and anchors are DROPPED (metadata-only items, external parties, transfers,
acknowledgments and anchors are lost); the CASCADE FK, NOT NULL
``artifact_id`` and the pre-v3 action CHECK are restored. Export the custody
ledgers (bundles) before downgrading.

Revision ID: evidence_register_ledger
Revises: realtime_versions
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'evidence_register_ledger'
down_revision = 'realtime_versions'
branch_labels = None
depends_on = None

EVIDENCE_TYPES = ('disk_image', 'memory_capture', 'triage_package', 'logical_collection', 'mobile_device',
                  'storage_media', 'computer_system', 'network_capture', 'cloud_export', 'log_export',
                  'document', 'digital_file', 'other')
CUSTODY_STATES = ('in_storage', 'checked_out', 'transferred', 'disposed')
PARTY_ROLES = ('counsel', 'law_enforcement', 'third_party_lab', 'insurer', 'client', 'regulator',
               'courier', 'other')
TRANSFER_METHODS = ('hand_delivery', 'courier', 'registered_mail', 'secure_file_transfer', 'internal', 'other')
V3_ACTIONS = ('register', 'upload', 'view', 'download', 'transfer', 'check_out', 'check_in', 'acknowledge',
              'verify', 'update', 'add_hash', 'derive', 'export', 'delete', 'void', 'dispose', 'legal_hold')
LEGACY_ACTIONS = ('upload', 'view', 'download', 'transfer', 'verify', 'export', 'delete', 'legal_hold')

TRIGGERS = (
    ('coc_append_only', 'chain_of_custody', 'BEFORE UPDATE OR DELETE', 'ROW'),
    ('coc_no_truncate', 'chain_of_custody', 'BEFORE TRUNCATE', 'STATEMENT'),
    ('anchors_append_only', 'custody_anchors', 'BEFORE UPDATE OR DELETE', 'ROW'),
    ('anchors_no_truncate', 'custody_anchors', 'BEFORE TRUNCATE', 'STATEMENT'),
)

APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION custody_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_LEVEL = 'ROW' AND TG_OP = 'DELETE' THEN
    IF current_setting('sheetstorm.custody_purge', true) = OLD.incident_id::text THEN
      RETURN OLD;  -- only the audited incident purge path (services/incident_purge.py)
    END IF;
  END IF;
  RAISE EXCEPTION '% on % is forbidden: append-only custody ledger', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END $$;
"""


def _in(values):
    return ', '.join(f"'{v}'" for v in values)


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(table):
    return _insp().has_table(table)


def _column_exists(table, column):
    return column in {c['name'] for c in _insp().get_columns(table)}


def _index_exists(table, name):
    return name in {i['name'] for i in _insp().get_indexes(table)}


def _constraint_exists(name):
    return op.get_bind().execute(
        sa.text('SELECT 1 FROM pg_constraint WHERE conname = :n'), {'n': name}).first() is not None


def _fk_name(table, column, referred):
    for fk in _insp().get_foreign_keys(table):
        if fk['constrained_columns'] == [column] and fk['referred_table'] == referred:
            return fk['name']
    return None


def _add_column(table, column):
    if not _column_exists(table, column.name):
        op.add_column(table, column)


def _add_fk(name, table, referred, cols, ondelete=None):
    if not _constraint_exists(name):
        op.create_foreign_key(name, table, referred, cols, ['id'], ondelete=ondelete)


def _create_tables():
    if not _table_exists('custody_parties'):
        op.create_table(
            'custody_parties',
            sa.Column('id', pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('organization_id', pg.UUID(as_uuid=True),
                      sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('organization_name', sa.String(255)),
            sa.Column('role', sa.String(40), nullable=False, server_default='other'),
            sa.Column('email', sa.String(255)),
            sa.Column('phone', sa.String(60)),
            sa.Column('address', sa.Text()),
            sa.Column('notes', sa.Text()),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_by', pg.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.CheckConstraint(f'role IN ({_in(PARTY_ROLES)})', name='ck_custody_parties_role'),
        )
        op.create_index('idx_custody_parties_org', 'custody_parties', ['organization_id'])

    if not _table_exists('evidence_items'):
        op.create_table(
            'evidence_items',
            sa.Column('id', pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('organization_id', pg.UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('incident_id', pg.UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('sequence_number', sa.Integer(), nullable=False),
            sa.Column('evidence_type', sa.String(40), nullable=False, server_default='other'),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('condition_notes', sa.Text()),
            sa.Column('media_type', sa.String(120)),
            sa.Column('make', sa.String(120)),
            sa.Column('model', sa.String(120)),
            sa.Column('serial_number', sa.String(120)),
            sa.Column('capacity_bytes', sa.BigInteger()),
            sa.Column('seal_number', sa.String(120)),
            sa.Column('bag_number', sa.String(120)),
            sa.Column('storage_location', sa.String(500)),
            sa.Column('acquired_at', sa.DateTime(timezone=True)),
            sa.Column('acquired_by_user_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id')),
            sa.Column('acquired_by_name', sa.String(255)),
            sa.Column('acquired_from', sa.String(500)),
            sa.Column('acquisition_method', sa.String(100)),
            sa.Column('acquisition_tool', sa.String(150)),
            sa.Column('acquisition_tool_version', sa.String(60)),
            sa.Column('source_host_id', pg.UUID(as_uuid=True),
                      sa.ForeignKey('compromised_hosts.id', ondelete='SET NULL')),
            sa.Column('source_host_label', sa.String(255)),
            sa.Column('acquisition_hashes', pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column('parent_id', pg.UUID(as_uuid=True), sa.ForeignKey('evidence_items.id')),
            sa.Column('derivation_note', sa.Text()),
            sa.Column('custody_state', sa.String(20), nullable=False, server_default='in_storage'),
            sa.Column('current_holder_user_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id')),
            sa.Column('current_holder_party_id', pg.UUID(as_uuid=True), sa.ForeignKey('custody_parties.id')),
            sa.Column('expected_return_at', sa.DateTime(timezone=True)),
            sa.Column('last_verified_at', sa.DateTime(timezone=True)),
            sa.Column('last_verification_result', sa.String(20)),
            sa.Column('legal_hold_until', sa.DateTime(timezone=True)),
            sa.Column('is_locked', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('voided_at', sa.DateTime(timezone=True)),
            sa.Column('voided_by', pg.UUID(as_uuid=True), sa.ForeignKey('users.id')),
            sa.Column('void_reason', sa.Text()),
            sa.Column('created_by', pg.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
            sa.Column('extra_data', pg.JSONB(), server_default=sa.text("'{}'::jsonb")),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.UniqueConstraint('incident_id', 'sequence_number', name='uq_evidence_items_incident_seq'),
            sa.CheckConstraint(f'evidence_type IN ({_in(EVIDENCE_TYPES)})', name='ck_evidence_items_type'),
            sa.CheckConstraint(f'custody_state IN ({_in(CUSTODY_STATES)})',
                               name='ck_evidence_items_custody_state'),
            sa.CheckConstraint("last_verification_result IS NULL OR last_verification_result IN ('match', 'mismatch')",
                               name='ck_evidence_items_verification'),
        )
        op.create_index('idx_evidence_items_incident', 'evidence_items', ['incident_id'])
        op.create_index('idx_evidence_items_org', 'evidence_items', ['organization_id'])
        op.create_index('idx_evidence_items_parent', 'evidence_items', ['parent_id'])
        op.execute('CREATE INDEX IF NOT EXISTS idx_evidence_items_hashes ON evidence_items '
                   'USING gin (acquisition_hashes jsonb_path_ops)')

    if not _table_exists('custody_anchors'):
        op.create_table(
            'custody_anchors',
            sa.Column('id', pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('incident_id', pg.UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('incident_seq', sa.Integer(), nullable=False),
            sa.Column('head_hash', sa.String(64), nullable=False),
            sa.Column('anchor_type', sa.String(30), nullable=False),
            sa.Column('tsa_url', sa.Text()),
            sa.Column('nonce', sa.Numeric(20, 0)),
            sa.Column('token_der', sa.LargeBinary()),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('error', sa.Text()),
            sa.Column('created_by', pg.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint("anchor_type IN ('rfc3161', 'export_manifest')", name='ck_custody_anchors_type'),
            sa.CheckConstraint("status IN ('granted', 'failed')", name='ck_custody_anchors_status'),
        )
        op.create_index('idx_custody_anchors_incident', 'custody_anchors', ['incident_id'])


def _add_columns():
    # artifacts
    _add_column('artifacts', sa.Column('evidence_item_id', pg.UUID(as_uuid=True), nullable=True))
    _add_fk('fk_artifacts_evidence_item', 'artifacts', 'evidence_items', ['evidence_item_id'])
    _add_column('artifacts', sa.Column('purpose', sa.String(30), nullable=False, server_default='evidence'))
    if not _constraint_exists('ck_artifacts_purpose'):
        op.create_check_constraint('ck_artifacts_purpose', 'artifacts', "purpose IN ('evidence', 'custody_receipt')")
    _add_column('artifacts', sa.Column('deleted_at', sa.DateTime(timezone=True)))
    _add_column('artifacts', sa.Column('deleted_by', pg.UUID(as_uuid=True)))
    _add_fk('fk_artifacts_deleted_by', 'artifacts', 'users', ['deleted_by'])
    _add_column('artifacts', sa.Column('deletion_reason', sa.Text()))
    _add_column('artifacts', sa.Column('content_purged', sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _index_exists('artifacts', 'idx_artifacts_evidence_item'):
        op.create_index('idx_artifacts_evidence_item', 'artifacts', ['evidence_item_id'])

    # chain_of_custody (the ledger)
    _add_column('chain_of_custody', sa.Column('evidence_item_id', pg.UUID(as_uuid=True)))
    _add_fk('fk_custody_evidence_item', 'chain_of_custody', 'evidence_items', ['evidence_item_id'])
    _add_column('chain_of_custody', sa.Column('incident_id', pg.UUID(as_uuid=True)))
    _add_fk('fk_custody_incident', 'chain_of_custody', 'incidents', ['incident_id'], ondelete='CASCADE')
    _add_column('chain_of_custody', sa.Column('seq', sa.Integer()))
    _add_column('chain_of_custody', sa.Column('incident_seq', sa.Integer()))
    _add_column('chain_of_custody', sa.Column('prev_hash', sa.String(64)))
    _add_column('chain_of_custody', sa.Column('incident_prev_hash', sa.String(64)))
    _add_column('chain_of_custody', sa.Column('entry_hash', sa.String(64)))
    _add_column('chain_of_custody', sa.Column('chain_version', sa.SmallInteger()))
    _add_column('chain_of_custody', sa.Column('external_party_id', pg.UUID(as_uuid=True)))
    _add_fk('fk_custody_external_party', 'chain_of_custody', 'custody_parties', ['external_party_id'])
    _add_column('chain_of_custody', sa.Column('transfer_method', sa.String(40)))
    if not _constraint_exists('ck_custody_transfer_method'):
        op.create_check_constraint('ck_custody_transfer_method', 'chain_of_custody',
                                   f'transfer_method IS NULL OR transfer_method IN ({_in(TRANSFER_METHODS)})')
    op.execute('ALTER TABLE chain_of_custody DROP CONSTRAINT IF EXISTS chain_of_custody_action_check')
    op.execute('ALTER TABLE chain_of_custody ADD CONSTRAINT chain_of_custody_action_check '
               f'CHECK (action IN ({_in(V3_ACTIONS)}))')
    if not _constraint_exists('uq_custody_item_seq'):
        op.create_unique_constraint('uq_custody_item_seq', 'chain_of_custody', ['evidence_item_id', 'seq'])
    if not _constraint_exists('uq_custody_incident_seq'):
        op.create_unique_constraint('uq_custody_incident_seq', 'chain_of_custody', ['incident_id', 'incident_seq'])
    if not _index_exists('chain_of_custody', 'idx_custody_evidence_item'):
        op.create_index('idx_custody_evidence_item', 'chain_of_custody', ['evidence_item_id'])
    if not _index_exists('chain_of_custody', 'idx_custody_incident'):
        op.create_index('idx_custody_incident', 'chain_of_custody', ['incident_id'])


BACKFILL_ITEMS = """
WITH src AS MATERIALIZED (
    SELECT a.id AS artifact_id, gen_random_uuid() AS item_id, a.incident_id, i.organization_id,
           (COALESCE((SELECT max(e.sequence_number) FROM evidence_items e WHERE e.incident_id = a.incident_id), 0)
            + row_number() OVER (PARTITION BY a.incident_id ORDER BY a.created_at, a.id))::int AS seq,
           left(a.original_filename, 255) AS title, a.description,
           COALESCE(a.acquired_at, a.collected_at) AS acquired_at,
           a.acquisition_method, a.acquisition_tool, left(a.source_host, 255) AS source_host_label,
           jsonb_build_array(
             jsonb_build_object('algorithm', 'md5', 'value', lower(a.md5), 'source', 'computed_on_upload',
                                'recorded_at', to_char(a.created_at AT TIME ZONE 'UTC',
                                                       'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
                                'recorded_by', a.uploaded_by::text),
             jsonb_build_object('algorithm', 'sha256', 'value', lower(a.sha256), 'source', 'computed_on_upload',
                                'recorded_at', to_char(a.created_at AT TIME ZONE 'UTC',
                                                       'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
                                'recorded_by', a.uploaded_by::text),
             jsonb_build_object('algorithm', 'sha512', 'value', lower(a.sha512), 'source', 'computed_on_upload',
                                'recorded_at', to_char(a.created_at AT TIME ZONE 'UTC',
                                                       'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
                                'recorded_by', a.uploaded_by::text)
           ) AS hashes,
           a.uploaded_by, a.created_at, a.storage_type
    FROM artifacts a JOIN incidents i ON i.id = a.incident_id
    WHERE a.evidence_item_id IS NULL
),
ins AS (
    INSERT INTO evidence_items (id, organization_id, incident_id, sequence_number, evidence_type, title,
                                description, acquired_at, acquisition_method, acquisition_tool,
                                source_host_label, acquisition_hashes, storage_location, custody_state,
                                created_by, created_at, extra_data, version)
    SELECT item_id, organization_id, incident_id, seq, 'digital_file', title, description, acquired_at,
           acquisition_method, acquisition_tool, source_host_label, hashes,
           'SheetStorm (' || COALESCE(storage_type, 'local') || ')', 'in_storage',
           uploaded_by, created_at, jsonb_build_object('backfilled_from_artifact', artifact_id::text), 1
    FROM src
    RETURNING id
)
UPDATE artifacts a SET evidence_item_id = src.item_id
FROM src WHERE a.id = src.artifact_id
"""

BACKFILL_CUSTODY = """
UPDATE chain_of_custody c
SET evidence_item_id = a.evidence_item_id, incident_id = a.incident_id
FROM artifacts a
WHERE c.artifact_id = a.id AND (c.evidence_item_id IS NULL OR c.incident_id IS NULL)
"""


def _swap_fk(table, column, referred, new_name, ondelete):
    current = _fk_name(table, column, referred)
    if current == new_name:
        return
    if current:
        op.drop_constraint(current, table, type_='foreignkey')
    op.create_foreign_key(new_name, table, referred, [column], ['id'], ondelete=ondelete)


def upgrade():
    _create_tables()
    _add_columns()

    # Backfill (SQL only)
    op.execute(BACKFILL_ITEMS)
    op.execute(BACKFILL_CUSTODY)

    # NOT NULL + FK swap
    op.alter_column('artifacts', 'evidence_item_id', nullable=False)
    op.alter_column('chain_of_custody', 'evidence_item_id', nullable=False)
    op.alter_column('chain_of_custody', 'incident_id', nullable=False)
    op.alter_column('chain_of_custody', 'artifact_id', nullable=True)
    _swap_fk('chain_of_custody', 'artifact_id', 'artifacts', 'fk_custody_artifact', None)

    # Triggers LAST
    op.execute(APPEND_ONLY_FUNCTION)
    for name, table, timing, level in TRIGGERS:
        op.execute(f'DROP TRIGGER IF EXISTS {name} ON {table}')
        op.execute(f'CREATE TRIGGER {name} {timing} ON {table} FOR EACH {level} '
                   'EXECUTE FUNCTION custody_append_only()')


def downgrade():
    # Triggers FIRST
    for name, table, _timing, _level in TRIGGERS:
        if _table_exists(table):
            op.execute(f'DROP TRIGGER IF EXISTS {name} ON {table}')
    op.execute('DROP FUNCTION IF EXISTS custody_append_only()')

    # LOSSY: drop v3 ledger rows, rows without an artifact, and tombstones.
    if _column_exists('chain_of_custody', 'chain_version'):
        op.execute('DELETE FROM chain_of_custody WHERE chain_version IS NOT NULL OR artifact_id IS NULL')
    if _column_exists('artifacts', 'deleted_at'):
        op.execute('DELETE FROM chain_of_custody c USING artifacts a '
                   'WHERE c.artifact_id = a.id AND a.deleted_at IS NOT NULL')
        op.execute('DELETE FROM artifacts WHERE deleted_at IS NOT NULL')

    # Restore the pre-v3 custody table
    _swap_fk('chain_of_custody', 'artifact_id', 'artifacts', 'chain_of_custody_artifact_id_fkey', 'CASCADE')
    op.alter_column('chain_of_custody', 'artifact_id', nullable=False)
    op.execute('ALTER TABLE chain_of_custody DROP CONSTRAINT IF EXISTS chain_of_custody_action_check')
    op.execute('ALTER TABLE chain_of_custody ADD CONSTRAINT chain_of_custody_action_check '
               f'CHECK (action IN ({_in(LEGACY_ACTIONS)}))')
    for name in ('uq_custody_incident_seq', 'uq_custody_item_seq', 'ck_custody_transfer_method',
                 'fk_custody_external_party', 'fk_custody_incident', 'fk_custody_evidence_item'):
        op.execute(f'ALTER TABLE chain_of_custody DROP CONSTRAINT IF EXISTS {name}')
    op.execute('DROP INDEX IF EXISTS idx_custody_incident')
    op.execute('DROP INDEX IF EXISTS idx_custody_evidence_item')
    for col in ('transfer_method', 'external_party_id', 'chain_version', 'entry_hash', 'incident_prev_hash',
                'prev_hash', 'incident_seq', 'seq', 'incident_id', 'evidence_item_id'):
        if _column_exists('chain_of_custody', col):
            op.drop_column('chain_of_custody', col)

    # artifacts
    for name in ('ck_artifacts_purpose', 'fk_artifacts_deleted_by', 'fk_artifacts_evidence_item'):
        op.execute(f'ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS {name}')
    op.execute('DROP INDEX IF EXISTS idx_artifacts_evidence_item')
    for col in ('content_purged', 'deletion_reason', 'deleted_by', 'deleted_at', 'purpose', 'evidence_item_id'):
        if _column_exists('artifacts', col):
            op.drop_column('artifacts', col)

    for table in ('custody_anchors', 'evidence_items', 'custody_parties'):
        if _table_exists(table):
            op.drop_table(table)
