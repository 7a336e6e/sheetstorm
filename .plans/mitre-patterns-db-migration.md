# Plan: Migrate MITRE Patterns from YAML to Per-Org DB Table

ClickUp: https://app.clickup.com/t/86c9ng9k9

## Context
MITRE patterns live in `backend/app/data/mitre_patterns.yaml` — a single global file shared across all orgs. This breaks multi-tenancy, has no audit trail, and the `threading.Lock()` atomic-write workaround in `mitre_suggest_service.py` only works within a single Gunicorn worker (cross-process writes are still unsafe). Moving to a DB table fixes all three.

## Step 1 — Alembic migration

New migration file in `backend/migrations/versions/`, chained from the current head (`add_teams_and_org_roles`).

```sql
CREATE TABLE mitre_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    technique VARCHAR(20) NOT NULL,       -- e.g. T1059.001
    tactic VARCHAR(80) NOT NULL,          -- e.g. execution
    name VARCHAR(200) NOT NULL,
    keywords JSONB NOT NULL DEFAULT '[]',
    regex JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_mitre_patterns_org ON mitre_patterns(organization_id);
CREATE UNIQUE INDEX ix_mitre_patterns_org_technique ON mitre_patterns(organization_id, technique);
```

Alembic `upgrade`: create table + indexes.
Alembic `downgrade`: drop table.

## Step 2 — SQLAlchemy model

New file: `backend/app/models/mitre_pattern.py`

```python
from app.models.base import BaseModel
from app.extensions import db

class MitrePattern(BaseModel):
    __tablename__ = 'mitre_patterns'
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    technique = db.Column(db.String(20), nullable=False)
    tactic = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    keywords = db.Column(db.JSON, nullable=False, default=list)
    regex = db.Column(db.JSON, nullable=False, default=list)
```

Export from `backend/app/models/__init__.py`.

## Step 3 — Rewrite mitre_suggest_service.py

Replace `_load_patterns()`, `get_all_patterns()`, `save_patterns()`:

```python
def get_all_patterns(organization_id: str) -> List[Dict]:
    rows = MitrePattern.query.filter_by(organization_id=organization_id).all()
    return [r.to_dict() for r in rows]

def save_patterns(patterns_list: List[Dict], organization_id: str) -> None:
    # Delete all existing patterns for org, re-insert
    MitrePattern.query.filter_by(organization_id=organization_id).delete()
    for p in patterns_list:
        mp = MitrePattern(organization_id=organization_id, **{k: p[k] for k in ('technique','tactic','name','keywords','regex')})
        db.session.add(mp)
    db.session.commit()
```

Remove `_WRITE_LOCK`, `_PATTERNS`, `_PATTERNS_PATH`, `tempfile`, `threading` imports.

Keep `suggest_mitre_techniques()` working — it calls `get_all_patterns()`, just needs `organization_id` passed in from the request context.

## Step 4 — Update endpoints in knowledge_base.py

All three CRUD endpoints and `mitre_auto_suggest` need to extract `org_id` from JWT claims and pass it to the service:

```python
from flask_jwt_extended import get_jwt
org_id = get_jwt().get('organization_id')
patterns = get_all_patterns(org_id)
```

## Step 5 — Seed migration script

One-time script `backend/scripts/seed_mitre_patterns.py`:
- Load `mitre_patterns.yaml`
- For each org in the DB, insert the YAML patterns (deduplicated by `organization_id + technique`)
- Run once after deploy: `flask shell < scripts/seed_mitre_patterns.py`

## Step 6 — Verification

```bash
cd backend
flask db heads          # must show exactly 1 head
flask db upgrade        # apply migration
python -m pytest tests/ -x -q
```

Check that:
- Orgs see only their own patterns
- YAML file is no longer written at runtime (remove write path from service)
- Seed script inserts rows for all orgs

## Files to touch
- `backend/migrations/versions/<new>.py`
- `backend/app/models/mitre_pattern.py` (new)
- `backend/app/models/__init__.py`
- `backend/app/services/mitre_suggest_service.py`
- `backend/app/api/v1/endpoints/knowledge_base.py`
- `backend/scripts/seed_mitre_patterns.py` (new)
