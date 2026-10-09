"""Built-in playbooks and case templates (read-only, code-resident).

Loaded from ``app/data/playbooks/*.yaml`` and ``app/data/case_templates/*.yaml``
with ``yaml.safe_load`` and validated at first use (a malformed shipped file
raises ``BuiltinError`` and is caught by ``test_question_library.py`` in CI).
They are addressed as ``builtin:<key>``; the key is matched by regex and looked
up in the loaded dict, never used to build a path. Built-ins upgrade with the
app; "clone" copies one into an org row.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.case_template import BUILTIN_REF_RE, TEMPLATE_KEY_RE, CaseTemplateDefinition
from app.services import question_library
from app.services.playbook_service import validate_definition

DATA_DIR = question_library.DATA_DIR
PLAYBOOK_DIR = os.path.join(DATA_DIR, 'playbooks')
TEMPLATE_DIR = os.path.join(DATA_DIR, 'case_templates')
MAX_FILE_BYTES = 256 * 1024


class BuiltinError(ValueError):
    """A shipped built-in file is invalid."""


class _PlaybookFile(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    schema_: str = Field(..., alias='schema')
    key: str
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    incident_type: Optional[str] = Field(None, max_length=100)
    metadata: Dict = Field(default_factory=dict)
    definition: Dict


class _TemplateFile(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    schema_: str = Field(..., alias='schema')
    key: str
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    incident_type: Optional[str] = Field(None, max_length=100)
    definition: Dict


def _yaml_files(folder):
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if n.endswith(('.yaml', '.yml'))]


def _read(path):
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise BuiltinError(f'{os.path.basename(path)}: file too large')
    with open(path, encoding='utf-8') as fh:
        try:
            return yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise BuiltinError(f'{os.path.basename(path)}: invalid YAML ({exc})') from exc


def _first_error(exc):
    err = exc.errors()[0]
    return f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"


def ref_for(key):
    return f'builtin:{key}'


def parse_builtin_ref(ref):
    """``'builtin:ransomware'`` -> ``'ransomware'``; None if not that shape."""
    if isinstance(ref, str) and BUILTIN_REF_RE.match(ref):
        return ref.split(':', 1)[1]
    return None


# ---------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2)
def load_playbooks(folder=PLAYBOOK_DIR) -> Dict[str, dict]:
    out = {}
    for path in _yaml_files(folder):
        name = os.path.basename(path)
        try:
            doc = _PlaybookFile.model_validate(_read(path))
        except ValidationError as exc:
            raise BuiltinError(f'{name}: {_first_error(exc)}') from exc
        if doc.schema_ != 'sheetstorm-playbook':
            raise BuiltinError(f'{name}: unsupported schema {doc.schema_!r}')
        if not TEMPLATE_KEY_RE.match(doc.key) or name.rsplit('.', 1)[0] != doc.key:
            raise BuiltinError(f'{name}: key must match the file name and ^[a-z0-9][a-z0-9-]{{1,63}}$')
        if doc.key in out:
            raise BuiltinError(f'{name}: duplicate key {doc.key}')
        ok, msg = validate_definition(doc.definition)
        if not ok:
            raise BuiltinError(f'{name}: {msg}')
        for ph in doc.definition.get('phases', []):
            for act in ph.get('actions') or []:
                if act.get('auto_run'):
                    # Built-ins never run actions (or send incident data to an
                    # AI provider) on their own.
                    raise BuiltinError(f'{name}: built-in playbooks must not set auto_run')
        out[doc.key] = {
            'id': ref_for(doc.key), 'builtin_key': doc.key, 'is_builtin': True,
            'name': doc.name, 'description': doc.description, 'incident_type': doc.incident_type,
            'definition': doc.definition, 'metadata': doc.metadata, 'is_template': True,
            'organization_id': None, 'cloned_from': None, 'creator': None,
            'created_at': None, 'updated_at': None,
        }
    return out


def get_playbook(key) -> Optional[dict]:
    return load_playbooks().get(key) if isinstance(key, str) else None


# ---------------------------------------------------------------------------
# Case templates
# ---------------------------------------------------------------------------

def check_library_refs(defn: CaseTemplateDefinition):
    """Problems (strings) in a definition that need the library / built-ins:
    unknown ``ref`` ids and an unknown built-in playbook."""
    problems = []
    for q in defn.questions:
        if q.ref and question_library.get(q.ref) is None:
            problems.append(f'unknown library question {q.ref!r}')
    if defn.playbook and defn.playbook.builtin and get_playbook(defn.playbook.builtin) is None:
        problems.append(f'unknown built-in playbook {defn.playbook.builtin!r}')
    return problems


@lru_cache(maxsize=2)
def load_case_templates(folder=TEMPLATE_DIR) -> Dict[str, dict]:
    out = {}
    for path in _yaml_files(folder):
        name = os.path.basename(path)
        try:
            doc = _TemplateFile.model_validate(_read(path))
            defn = CaseTemplateDefinition.model_validate(doc.definition)
        except ValidationError as exc:
            raise BuiltinError(f'{name}: {_first_error(exc)}') from exc
        if doc.schema_ != 'sheetstorm-case-template':
            raise BuiltinError(f'{name}: unsupported schema {doc.schema_!r}')
        if not TEMPLATE_KEY_RE.match(doc.key) or name.rsplit('.', 1)[0] != doc.key:
            raise BuiltinError(f'{name}: key must match the file name and ^[a-z0-9][a-z0-9-]{{1,63}}$')
        if doc.key in out:
            raise BuiltinError(f'{name}: duplicate key {doc.key}')
        problems = check_library_refs(defn)
        if problems:
            raise BuiltinError(f'{name}: {problems[0]}')
        out[doc.key] = {
            'id': ref_for(doc.key), 'builtin_key': doc.key, 'is_builtin': True, 'key': doc.key,
            'name': doc.name, 'description': doc.description, 'incident_type': doc.incident_type,
            'definition': defn.model_dump(mode='json', exclude_none=True), 'is_active': True,
            'version': 1, 'organization_id': None, 'cloned_from': None, 'creator': None,
            'created_at': None, 'updated_at': None,
        }
    return out


def get_case_template(key) -> Optional[dict]:
    return load_case_templates().get(key) if isinstance(key, str) else None


def reload_all():
    """Drop caches (tests)."""
    load_playbooks.cache_clear()
    load_case_templates.cache_clear()
    question_library.load_library.cache_clear()
