"""Built-in investigative question library (read-only, code-resident).

Sources, all loaded from files shipped in the image with ``yaml.safe_load``
(no network access, no user-supplied files, no path built from input):

* ``app/data/question_library/sheetstorm_core.yaml``: SheetStorm core
  questions, refs ``ss:SSQ-###`` (MIT).
* ``app/data/dfiq/{scenarios,facets,questions}/*.yaml``: an optional verbatim
  DFIQ subset (Apache-2.0), refs ``dfiq:Q####``. Absent until it is vendored
  (``backend/scripts/vendor_dfiq.py``); the library works without it.

``load_library()`` returns a validated, cached ``Library``. Library questions
are copied into an incident's own rows (``to_question_kwargs``), so later
upgrades of the library never change existing investigations.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CORE_FILE = os.path.join(DATA_DIR, 'question_library', 'sheetstorm_core.yaml')
DFIQ_DIR = os.path.join(DATA_DIR, 'dfiq')

MAX_FILE_BYTES = 512 * 1024
PRIORITIES = ('low', 'medium', 'high', 'critical')

CORE_ID_RE = re.compile(r'^SSQ-\d{3}$')
CORE_FACET_RE = re.compile(r'^SSF-\d{2}$')
DFIQ_ID_RE = re.compile(r'^[SFQ]\d{4}$')

CORE_SOURCE = {
    'key': 'core', 'name': 'SheetStorm core questions', 'license': 'MIT',
    'attribution': None, 'url': None,
}
DFIQ_SOURCE = {
    'key': 'dfiq', 'name': 'DFIQ', 'license': 'Apache-2.0',
    'attribution': 'Questions marked DFIQ are © 2024 Google LLC, Apache-2.0',
    'url': 'https://github.com/google/dfiq',
}


class LibraryError(ValueError):
    """A library file is malformed (raised at load time, never per request)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class _CoreFacet(_Strict):
    id: str
    name: str = Field(..., min_length=1, max_length=255)

    @field_validator('id')
    @classmethod
    def _id(cls, v):
        if not CORE_FACET_RE.match(v):
            raise ValueError('facet id must look like SSF-01')
        return v


class _CoreQuestion(_Strict):
    id: str
    facet: str
    question: str = Field(..., min_length=3, max_length=1000)
    description: Optional[str] = Field(None, max_length=5000)
    phase: Optional[int] = Field(None, ge=1, le=6)
    priority: str = 'medium'

    @field_validator('id')
    @classmethod
    def _id(cls, v):
        if not CORE_ID_RE.match(v):
            raise ValueError('question id must look like SSQ-001')
        return v

    @field_validator('priority')
    @classmethod
    def _priority(cls, v):
        if v not in PRIORITIES:
            raise ValueError(f'priority must be one of {PRIORITIES}')
        return v


class _CoreFile(_Strict):
    schema_: str = Field(..., alias='schema')
    version: int
    namespace: str
    name: str
    license: str
    facets: List[_CoreFacet]
    questions: List[_CoreQuestion]

    model_config = ConfigDict(extra='forbid', populate_by_name=True)


@dataclass
class QuestionDef:
    ref: str
    source: str            # 'core' | 'dfiq'
    question: str
    description: Optional[str] = None
    facet: Optional[str] = None       # facet display name
    facet_ref: Optional[str] = None
    group_ref: Optional[str] = None   # scenario / core group
    phase: Optional[int] = None
    priority: str = 'medium'
    tags: List[str] = field(default_factory=list)
    guidance: List[dict] = field(default_factory=list)

    def summary(self):
        return {'ref': self.ref, 'source': self.source, 'question': self.question, 'facet': self.facet,
                'phase': self.phase, 'priority': self.priority}

    def detail(self):
        data = self.summary()
        data.update(description=self.description, tags=list(self.tags), guidance=list(self.guidance),
                    facet_ref=self.facet_ref, group_ref=self.group_ref)
        return data


@dataclass
class Library:
    index: Dict[str, QuestionDef]
    groups: List[dict]
    sources: List[dict]

    def get(self, ref) -> Optional[QuestionDef]:
        return self.index.get(ref) if isinstance(ref, str) else None

    def tree(self):
        return {'groups': self.groups, 'sources': self.sources, 'total': len(self.index)}


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def _read_yaml(path):
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise LibraryError(f'{os.path.basename(path)}: file too large')
    with open(path, encoding='utf-8') as fh:
        try:
            return yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise LibraryError(f'{os.path.basename(path)}: invalid YAML ({exc})') from exc


def _load_core(path):
    raw = _read_yaml(path)
    try:
        doc = _CoreFile.model_validate(raw)
    except ValidationError as exc:
        raise LibraryError(f'{os.path.basename(path)}: {exc.errors()[0]["loc"]}: {exc.errors()[0]["msg"]}') from exc
    if doc.schema_ != 'sheetstorm-question-library' or doc.version != 1 or doc.namespace != 'ss':
        raise LibraryError(f'{os.path.basename(path)}: unsupported schema/version/namespace')
    facets = {}
    for f in doc.facets:
        if f.id in facets:
            raise LibraryError(f'duplicate facet {f.id}')
        facets[f.id] = f
    index, by_facet = {}, {}
    for q in doc.questions:
        if q.facet not in facets:
            raise LibraryError(f'{q.id}: unknown facet {q.facet}')
        ref = f'ss:{q.id}'
        if ref in index:
            raise LibraryError(f'duplicate question {ref}')
        index[ref] = QuestionDef(
            ref=ref, source='core', question=q.question.strip(), description=q.description,
            facet=facets[q.facet].name, facet_ref=f'ss:{q.facet}', group_ref='ss:core',
            phase=q.phase, priority=q.priority)
        by_facet.setdefault(q.facet, []).append(ref)
    group = {
        'ref': 'ss:core', 'kind': 'core', 'name': doc.name, 'source': 'core',
        'facets': [{'ref': f'ss:{fid}', 'name': f.name, 'questions': [index[r].summary() for r in by_facet.get(fid, [])]}
                   for fid, f in facets.items() if by_facet.get(fid)],
    }
    return index, [group]


def check_dfiq_doc(doc, label):
    """Validate one DFIQ document (any source); raises LibraryError."""
    if not isinstance(doc, dict) or not isinstance(doc.get('id'), str) or not DFIQ_ID_RE.match(doc['id']):
        raise LibraryError(f'{label}: missing or invalid id')
    version = str(doc.get('dfiq_version', ''))
    if version.split('.')[0] != '1':
        raise LibraryError(f'{label}: unsupported dfiq_version {version!r}')
    return doc


def _dfiq_docs(base, subdir):
    folder = os.path.join(base, subdir)
    if not os.path.isdir(folder):
        return []
    docs = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(('.yaml', '.yml')):
            continue
        docs.append(check_dfiq_doc(_read_yaml(os.path.join(folder, name)), f'dfiq/{subdir}/{name}'))
    return docs


def _guidance(approaches):
    out = []
    for a in approaches or []:
        if not isinstance(a, dict) or not a.get('name'):
            continue
        refs = [str(r)[:500] for r in (a.get('references') or []) if isinstance(r, (str, int))][:20]
        out.append({'name': str(a['name'])[:255], 'description': str(a.get('description') or '')[:5000],
                    'references': refs})
    return out[:20]


def _load_dfiq(base):
    """Parse a vendored DFIQ subset from files."""
    return dfiq_from_docs(*(_dfiq_docs(base, d) for d in ('scenarios', 'facets', 'questions')))


def dfiq_from_docs(scenarios, facets, questions):
    """Build the DFIQ part of the library from parsed documents (files or an
    import stored in the database); dangling parents are dropped."""
    if not questions:
        return {}, []
    key = lambda d: {d['id'], str(d.get('uuid') or '')}  # noqa: E731
    scen_by_id = {s['id']: s for s in scenarios}
    facet_by_id = {f['id']: f for f in facets}

    def parent_of(doc, pool):
        for pid in doc.get('parent_ids') or []:
            for pdoc in pool.values():
                if str(pid) in key(pdoc):
                    return pdoc
        return None

    index, groups = {}, {}
    for q in questions:
        facet = parent_of(q, facet_by_id)
        scenario = parent_of(facet, scen_by_id) if facet else None
        ref = f"dfiq:{q['id']}"
        text = str(q.get('name') or '').strip()
        if not text:
            raise LibraryError(f'{ref}: empty question name')
        index[ref] = QuestionDef(
            ref=ref, source='dfiq', question=text[:1000], description=(q.get('description') or None),
            facet=str(facet['name']) if facet else None, facet_ref=f"dfiq:{facet['id']}" if facet else None,
            group_ref=f"dfiq:{scenario['id']}" if scenario else None,
            tags=[str(t) for t in (q.get('tags') or [])][:20], guidance=_guidance(q.get('approaches')))
    for sid, s in scen_by_id.items():
        groups[sid] = {'ref': f'dfiq:{sid}', 'kind': 'scenario', 'name': str(s['name']), 'source': 'dfiq',
                       'facets': []}
    for fid, f in facet_by_id.items():
        qs = [d.summary() for r, d in index.items() if d.facet_ref == f'dfiq:{fid}']
        scenario = parent_of(f, scen_by_id)
        if qs and scenario:
            groups[scenario['id']]['facets'].append({'ref': f'dfiq:{fid}', 'name': str(f['name']), 'questions': qs})
    return index, [g for g in groups.values() if g['facets']]


# DFIQ imported at runtime (services/dfiq_import.py) lives in
# system_settings[DFIQ_SETTING_KEY] = {commit, sha256, ..., scenarios, facets,
# questions}. Each worker re-reads its version at most every DB_TTL seconds,
# so an import or removal reaches every worker without a restart.
DFIQ_SETTING_KEY = 'dfiq_library'
DB_TTL = 30.0
_db_cache = {'at': 0.0, 'version': 0, 'docs': None}


def _db_dfiq():
    """(version, docs|None) of the imported DFIQ library; (0, None) when none
    or unreadable (the library then works with core questions only)."""
    now = time.monotonic()
    if now - _db_cache['at'] < DB_TTL:
        return _db_cache['version'], _db_cache['docs']
    try:
        from app.models.system_setting import SystemSetting
        row = SystemSetting.query.filter_by(key=DFIQ_SETTING_KEY).first()
        version, docs = (row.version, row.value) if row is not None else (0, None)
    except Exception:  # no app context / DB down: keep what we had
        version, docs = _db_cache['version'], _db_cache['docs']
    _db_cache.update(at=now, version=version, docs=docs)
    return version, docs


def invalidate_db_cache():
    _db_cache.update(at=0.0)


def library() -> Library:
    """The library in force now (core + vendored or imported DFIQ)."""
    version, _ = _db_dfiq()
    return load_library(db_version=version)


@lru_cache(maxsize=4)
def load_library(core_file=CORE_FILE, dfiq_dir=DFIQ_DIR, db_version=0) -> Library:
    """The validated library (cached per imported-DFIQ version). The file
    arguments exist for tests only. Vendored files win over an import."""
    index, groups = _load_core(core_file)
    sources = [dict(CORE_SOURCE)]
    dfiq_index, dfiq_groups = _load_dfiq(dfiq_dir)
    if not dfiq_index and db_version:
        docs = _db_cache['docs'] or {}
        try:
            dfiq_index, dfiq_groups = dfiq_from_docs(docs.get('scenarios') or [], docs.get('facets') or [],
                                                     docs.get('questions') or [])
        except LibraryError:
            logger.exception('Ignoring an invalid imported DFIQ library')
            dfiq_index, dfiq_groups = {}, []
    if dfiq_index:
        overlap = set(index) & set(dfiq_index)
        if overlap:
            raise LibraryError(f'duplicate refs across sources: {sorted(overlap)[:3]}')
        index.update(dfiq_index)
        groups = groups + dfiq_groups
        sources.append(dict(DFIQ_SOURCE))
    return Library(index=index, groups=groups, sources=sources)


def reload_library():
    """Drop the cache (tests)."""
    load_library.cache_clear()
    return load_library()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get(ref) -> Optional[QuestionDef]:
    return library().get(ref)


def to_question_kwargs(ref, overrides=None) -> dict:
    """InvestigativeQuestion column values for a library ref.

    ``overrides`` may set phase, priority, facet, owner_id... (already
    validated by the caller); library text is never taken from the client.
    """
    qdef = get(ref)
    if qdef is None:
        raise KeyError(ref)
    data = {
        'question': qdef.question,
        'description': qdef.description,
        'facet': qdef.facet,
        'phase': qdef.phase,
        'priority': qdef.priority,
        'source': qdef.source,
        'source_ref': ref,
        'dedupe_key': ref,
        'guidance': list(qdef.guidance),
    }
    for k, v in (overrides or {}).items():
        if v is not None and k in ('phase', 'priority', 'facet', 'owner_id', 'order_index'):
            data[k] = v
    return data


def has_dfiq(refs) -> bool:
    return any(isinstance(r, str) and r.startswith('dfiq:') for r in refs)
