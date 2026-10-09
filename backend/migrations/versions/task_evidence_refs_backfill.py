"""tasks: extra_data.linked_entities -> evidence_refs (data only)

Before W2-DFIR-A the web UI linked tasks to evidence by writing
``extra_data.linked_entities = [{type, id, label}]`` (client-supplied labels),
while the MCP wrote ``evidence_refs = [{evidence_type, evidence_id}]``. The
API now reads and validates ``evidence_refs`` only and resolves labels on the
server.

Upgrade: for every task whose ``evidence_refs`` is NULL or empty and whose
``extra_data.linked_entities`` is a non-empty list, write the mapped refs:
types normalised to the evidence_refs registry names (aliases
``host_indicator -> host_ioc``, ``network_indicator -> network_ioc``),
malformed entries / unknown types / non-UUID ids dropped, duplicates
removed, at most 50 refs. Labels are not copied. ``extra_data`` is left
untouched, so the downgrade (and older UI builds) still have the source.
The row ``version`` is bumped so clients holding the old row get a 409
instead of overwriting the backfill. Idempotent: a re-run only sees tasks
whose refs are still empty.

Downgrade: clears ``evidence_refs`` (to ``[]``) on tasks whose refs still
equal the mapping of their ``linked_entities``, i.e. the rows this upgrade
wrote and nobody changed since. Refs written by users or the MCP are kept.

Revision ID: task_evidence_refs_backfill
Revises: evidence_register_ledger
Create Date: 2026-10-09
"""
import json
import uuid

from alembic import op
import sqlalchemy as sa

revision = 'task_evidence_refs_backfill'
down_revision = 'evidence_register_ledger'
branch_labels = None
depends_on = None

# Frozen copy of the registry at this revision (migrations never import app
# code, whose registry may change later).
CANONICAL_TYPES = ('timeline_event', 'host', 'account', 'network_ioc', 'host_ioc', 'malware',
                   'artifact', 'case_note', 'task', 'evidence_item')
ALIASES = {'host_indicator': 'host_ioc', 'network_indicator': 'network_ioc'}
MAX_REFS = 50
BATCH = 500


def map_linked_entities(linked):
    """[{type, id, label}] -> canonical [{evidence_type, evidence_id}]."""
    if not isinstance(linked, list):
        return []
    out, seen = [], set()
    for entry in linked:
        if not isinstance(entry, dict):
            continue
        etype = entry.get('type')
        etype = ALIASES.get(etype, etype) if isinstance(etype, str) else None
        if etype not in CANONICAL_TYPES:
            continue
        try:
            eid = str(uuid.UUID(str(entry.get('id'))))
        except (ValueError, TypeError, AttributeError):
            continue
        if (etype, eid) in seen:
            continue
        seen.add((etype, eid))
        out.append({'evidence_type': etype, 'evidence_id': eid})
        if len(out) >= MAX_REFS:
            break
    return out


def _has_version(bind):
    return 'version' in {c['name'] for c in sa.inspect(bind).get_columns('tasks')}


def _candidates(bind):
    return bind.execute(sa.text(
        "SELECT id, evidence_refs, extra_data -> 'linked_entities' AS linked FROM tasks "
        "WHERE jsonb_typeof(extra_data -> 'linked_entities') = 'array' "
        "AND jsonb_array_length(extra_data -> 'linked_entities') > 0"
    )).mappings().all()


def _write(bind, rows):
    """rows: [(task_id, refs_list)]"""
    bump = ', version = version + 1' if _has_version(bind) else ''
    stmt = sa.text(f'UPDATE tasks SET evidence_refs = CAST(:refs AS jsonb){bump} WHERE id = :id')
    for i in range(0, len(rows), BATCH):
        bind.execute(stmt, [{'id': tid, 'refs': json.dumps(refs)} for tid, refs in rows[i:i + BATCH]])


def upgrade():
    bind = op.get_bind()
    rows = []
    for row in _candidates(bind):
        if row['evidence_refs']:  # already has refs (MCP / earlier run): keep them
            continue
        refs = map_linked_entities(row['linked'])
        if refs:
            rows.append((row['id'], refs))
    _write(bind, rows)


def downgrade():
    bind = op.get_bind()
    rows = []
    for row in _candidates(bind):
        refs = map_linked_entities(row['linked'])
        if refs and row['evidence_refs'] == refs:
            rows.append((row['id'], []))
    _write(bind, rows)
