"""MITRE ATT&CK Auto-Suggest Service.

Scores timeline-event activity descriptions against keyword / regex patterns
loaded from per-organization database rows and returns ranked technique
suggestions.
"""

import re
from typing import Dict, List, Optional

from app import db
from app.models import MitrePattern


def get_all_patterns(organization_id: str) -> List[Dict]:
    """Return the raw pattern list (for management endpoints)."""
    patterns = MitrePattern.query.filter_by(
        organization_id=organization_id
    ).order_by(MitrePattern.technique.asc()).all()
    return [p.to_dict() for p in patterns]


def save_patterns(patterns_list: List[Dict], organization_id: str) -> None:
    """Persist patterns list for one organization."""
    db.session.query(MitrePattern).filter_by(
        organization_id=organization_id
    ).delete(synchronize_session=False)

    patterns = []
    for p in patterns_list:
        patterns.append(MitrePattern(
            organization_id=organization_id,
            technique=p['technique'],
            tactic=p['tactic'],
            name=p['name'],
            keywords=p.get('keywords', []) or [],
            regex=p.get('regex', []) or [],
        ))

    if patterns:
        db.session.add_all(patterns)
    db.session.commit()


def reload_patterns() -> None:
    """No-op retained for legacy callers; database reads are always fresh."""
    return None


def _compile_patterns(patterns: List[Dict]) -> List[dict]:
    """Compile regex patterns and normalize keywords for matching."""
    compiled: List[dict] = []
    for p in patterns:
        entry = {
            'technique': p['technique'],
            'tactic': p['tactic'],
            'name': p['name'],
            'keywords': [kw.lower() for kw in p.get('keywords', [])],
            'regex': [],
            'weight': float(p.get('weight', 0.8)),
        }
        for rx in p.get('regex', []):
            try:
                entry['regex'].append(re.compile(rx, re.IGNORECASE))
            except re.error:
                pass  # skip invalid patterns
        compiled.append(entry)
    return compiled


def suggest_mitre_techniques(
    text: str,
    organization_id: str,
    limit: int = 5,
    min_score: float = 0.1
) -> List[Dict]:
    """Return ranked MITRE technique suggestions for *text*.

    Each result has: technique, tactic, name, score (0-1).
    """
    if not text or not text.strip() or not organization_id:
        return []

    patterns = _compile_patterns(get_all_patterns(organization_id))
    text = text.lower()
    results: Dict[str, dict] = {}

    for p in patterns:
        score = 0.0
        matched_keywords = 0

        # Keyword matching
        for kw in p['keywords']:
            if kw in text:
                matched_keywords += 1

        if matched_keywords:
            # Proportion of keywords that matched, scaled by weight
            score = (matched_keywords / len(p['keywords'])) * p['weight']

        # Regex matching — each hit adds a bonus
        for rx in p['regex']:
            if rx.search(text):
                score += 0.15

        # Cap at 1.0
        score = min(score, 1.0)

        if score >= min_score:
            key = p['technique']
            if key not in results or results[key]['score'] < score:
                results[key] = {
                    'technique': p['technique'],
                    'tactic': p['tactic'],
                    'name': p['name'],
                    'score': round(score, 3),
                }

    ranked = sorted(results.values(), key=lambda r: r['score'], reverse=True)
    return ranked[:limit]


def suggest(
    activity: str,
    limit: int = 5,
    min_score: float = 0.1,
    organization_id: Optional[str] = None
) -> List[Dict]:
    """Backward-compatible wrapper around suggest_mitre_techniques."""
    return suggest_mitre_techniques(
        activity,
        organization_id,
        limit=limit,
        min_score=min_score
    )
