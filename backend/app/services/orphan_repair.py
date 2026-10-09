"""Find and repair rows whose foreign keys point at missing parents.

On a healthy database this finds nothing: foreign keys prevent orphans. They
appear when parents were deleted while foreign-key enforcement was bypassed
(``session_replication_role = replica``, disabled triggers, manual SQL), and
then block migrations that rebuild those keys.

Detection comes from the database's own catalog (every single-column foreign
key in the ``public`` schema), so new tables are covered automatically.
Repair, in one transaction, follows what the schema itself says:

* nullable column → set it to NULL (the row is kept);
* NOT NULL with ``ON DELETE CASCADE`` → delete the row: the schema already
  says it cannot outlive its parent (a role assignment of a deleted user, a
  notification, a custody row of a deleted artifact). Deleted rows are returned
  verbatim (``row_to_json``) so the caller keeps a report;
* NOT NULL without cascade (authorship such as ``timeline_events.created_by``)
  → never deleted. Reassigned to ``reassign_to`` (a user id) when the parent
  is ``users``, otherwise left and reported as ``manual``.

Passes repeat until nothing is left (a deleted parent can orphan its children).
"""
from sqlalchemy import text

from app import db

MAX_PASSES = 5
# Never altered: dangling references are part of the design there (audit rows
# outlive the users and incidents they describe; audit_governance drops these
# foreign keys) and audit history is evidence.
KEEP_TABLES = frozenset({'audit_logs'})

_FK_SQL = text("""
SELECT con.conname AS name,
       cl.relname  AS child,
       att.attname AS column,
       NOT att.attnotnull AS nullable,
       con.confdeltype = 'c' AS cascade,
       pcl.relname AS parent,
       patt.attname AS parent_column
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
JOIN pg_class pcl ON pcl.oid = con.confrelid
JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
JOIN pg_attribute patt ON patt.attrelid = con.confrelid AND patt.attnum = con.confkey[1]
WHERE con.contype = 'f' AND n.nspname = 'public' AND array_length(con.conkey, 1) = 1
ORDER BY cl.relname, att.attname
""")


def _q(name):
    return db.engine.dialect.identifier_preparer.quote(name)


def _orphan_where(fk):
    return (f"c.{_q(fk['column'])} IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {_q(fk['parent'])} p WHERE p.{_q(fk['parent_column'])} = c.{_q(fk['column'])})")


def foreign_keys():
    return [dict(r._mapping) for r in db.session.execute(_FK_SQL)]


def _action(fk):
    if fk['child'] in KEEP_TABLES:
        return 'keep'
    if fk['nullable']:
        return 'set_null'
    if fk['cascade']:
        return 'delete'
    return 'reassign' if fk['parent'] == 'users' else 'manual'


def find_orphans():
    """[{constraint, table, column, parent, nullable, action, count}] with count > 0."""
    out = []
    for fk in foreign_keys():
        n = db.session.execute(text(
            f"SELECT count(*) FROM {_q(fk['child'])} c WHERE {_orphan_where(fk)}")).scalar()
        if n:
            out.append({'constraint': fk['name'], 'table': fk['child'], 'column': fk['column'],
                        'parent': f"{fk['parent']}.{fk['parent_column']}", 'nullable': fk['nullable'],
                        'action': _action(fk), 'count': n})
    return out


def repair(reassign_to=None):
    """Fix the orphans (caller commits). ``reassign_to``: user id that takes
    over NOT NULL references to deleted users. Returns {'passes', 'actions',
    'deleted_rows', 'skipped'}; skipped = orphans left for a manual decision."""
    actions, deleted_rows = [], []
    fks = {fk['name']: fk for fk in foreign_keys()}
    pass_no = 0
    for pass_no in range(1, MAX_PASSES + 1):
        todo = [o for o in find_orphans() if o['action'] not in ('manual', 'keep')
                and not (o['action'] == 'reassign' and reassign_to is None)]
        if not todo:
            break
        # Deletes first, alone in their pass: updating a row re-checks its other
        # foreign keys, which fails when that row is itself an orphan to delete.
        deletes = [o for o in todo if o['action'] == 'delete']
        for item in deletes or todo:
            fk = fks[item['constraint']]
            table, where = _q(fk['child']), _orphan_where(fk)
            if item['action'] == 'set_null':
                n = db.session.execute(text(
                    f"UPDATE {table} AS c SET {_q(fk['column'])} = NULL WHERE {where}")).rowcount
            elif item['action'] == 'delete':
                rows = db.session.execute(text(
                    f"DELETE FROM {table} AS c WHERE {where} RETURNING row_to_json(c)")).scalars().all()
                deleted_rows.extend({'table': fk['child'], 'row': r} for r in rows)
                n = len(rows)
            else:  # reassign
                n = db.session.execute(text(
                    f"UPDATE {table} AS c SET {_q(fk['column'])} = :to WHERE {where}"), {'to': reassign_to}).rowcount
            actions.append({**item, 'pass': pass_no, 'affected': n})
    skipped = find_orphans()
    return {'passes': pass_no, 'actions': actions, 'deleted_rows': deleted_rows, 'skipped': skipped}
