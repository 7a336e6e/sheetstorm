"""MITRE ATT&CK Auto-Suggest Service.

Scores timeline-event activity descriptions against keyword / regex patterns
loaded from ``app/data/mitre_patterns.yaml`` and returns ranked technique
suggestions.
"""

import os
import re
from typing import List, Dict, Optional

import yaml

_PATTERNS: Optional[List[dict]] = None
_PATTERNS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mitre_patterns.yaml')


def _load_patterns() -> List[dict]:
    """Load and cache YAML detection patterns."""
    global _PATTERNS
    if _PATTERNS is not None:
        return _PATTERNS

    with open(_PATTERNS_PATH, 'r') as f:
        data = yaml.safe_load(f)

    raw = data.get('patterns', []) if data else []
    compiled: List[dict] = []
    for p in raw:
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

    _PATTERNS = compiled
    return _PATTERNS


def reload_patterns() -> None:
    """Force-reload patterns from disk (e.g. after CRUD edit)."""
    global _PATTERNS
    _PATTERNS = None
    _load_patterns()


def suggest(activity: str, limit: int = 5, min_score: float = 0.1) -> List[Dict]:
    """Return ranked MITRE technique suggestions for *activity*.

    Each result has: technique, tactic, name, score (0-1).
    """
    if not activity or not activity.strip():
        return []

    patterns = _load_patterns()
    text = activity.lower()
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


def get_all_patterns() -> List[Dict]:
    """Return the raw pattern list (for management endpoints)."""
    patterns = _load_patterns()
    result = []
    for p in patterns:
        result.append({
            'technique': p['technique'],
            'tactic': p['tactic'],
            'name': p['name'],
            'keywords': p['keywords'],
            'regex': [rx.pattern for rx in p['regex']],
            'weight': p['weight'],
        })
    return result


def save_patterns(patterns_list: List[Dict]) -> None:
    """Persist patterns list back to the YAML file."""
    entries = []
    for p in patterns_list:
        entry: dict = {
            'technique': p['technique'],
            'tactic': p['tactic'],
            'name': p['name'],
            'keywords': p['keywords'],
            'weight': p.get('weight', 0.8),
        }
        if p.get('regex'):
            entry['regex'] = p['regex']
        entries.append(entry)

    with open(_PATTERNS_PATH, 'w') as f:
        yaml.dump(
            {'patterns': entries},
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    reload_patterns()
