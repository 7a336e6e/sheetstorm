#!/usr/bin/env python3
"""Seed MITRE auto-suggest patterns for every organization."""
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import db, create_app
from app.models import Organization, MitrePattern

PATTERNS_PATH = BASE_DIR / 'app' / 'data' / 'mitre_patterns.yaml'


def load_patterns():
    """Load source MITRE patterns from YAML."""
    with PATTERNS_PATH.open('r') as f:
        data = yaml.safe_load(f) or {}
    return data.get('patterns', [])


def seed_mitre_patterns():
    """Seed MITRE patterns for all organizations."""
    try:
        from flask import current_app
        current_app._get_current_object()
        _run_seed()
    except RuntimeError:
        app = create_app()
        with app.app_context():
            _run_seed()


def _run_seed():
    """Internal seeding logic."""
    source_patterns = load_patterns()
    organizations = Organization.query.all()

    for org in organizations:
        existing = {
            row[0]
            for row in db.session.query(MitrePattern.technique)
            .filter_by(organization_id=org.id)
            .all()
        }
        seen = set(existing)
        seeded = 0

        for p in source_patterns:
            technique = p.get('technique')
            if not technique or technique in seen:
                continue
            if not p.get('tactic') or not p.get('name'):
                continue

            db.session.add(MitrePattern(
                organization_id=org.id,
                technique=technique,
                tactic=p['tactic'],
                name=p['name'],
                keywords=p.get('keywords', []) or [],
                regex=p.get('regex', []) or [],
            ))
            seen.add(technique)
            seeded += 1

        db.session.commit()
        print(f'Seeded {seeded} patterns for org {org.id}')


if __name__ == '__main__':
    seed_mitre_patterns()
