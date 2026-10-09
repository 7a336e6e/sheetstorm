"""W3-QST-BE: built-in question library, case templates and playbooks.

The shipped YAML must load through the safe loaders, validate against the
schemas, and only reference things that exist. W4-QST-CONTENT extends this
file with the vendored DFIQ manifest checks.
"""
import ast
import os
import textwrap

import pytest

from app.schemas.case_template import CaseTemplateDefinition
from app.services import builtin_templates, question_library
from app.services.playbook_service import validate_definition

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app')


def test_core_library_loads_and_is_consistent():
    lib = question_library.load_library()
    core = [q for q in lib.index.values() if q.source == 'core']
    assert len(core) == 37
    assert lib.get('ss:SSQ-009').question.startswith('Is scoping complete')
    assert lib.get('ss:SSQ-009').priority == 'critical'
    assert lib.get('nope') is None and lib.get(None) is None
    assert {s['key'] for s in lib.sources} >= {'core'}
    # every core question sits under a facet of the tree, once
    in_tree = [q['ref'] for g in lib.groups for f in g['facets'] for q in f['questions']]
    assert sorted(in_tree) == sorted(q.ref for q in core)
    for q in core:
        assert 1 <= len(q.question) <= 1000 and q.phase in (None, 1, 2, 3, 4, 5, 6)


def test_to_question_kwargs_copies_and_overrides():
    kw = question_library.to_question_kwargs('ss:SSQ-001', {'priority': 'low', 'phase': 3, 'junk': 'x'})
    assert kw['source'] == 'core' and kw['source_ref'] == kw['dedupe_key'] == 'ss:SSQ-001'
    assert kw['priority'] == 'low' and kw['phase'] == 3 and 'junk' not in kw
    with pytest.raises(KeyError):
        question_library.to_question_kwargs('ss:SSQ-999')


def test_builtin_playbooks_and_templates_validate():
    playbooks = builtin_templates.load_playbooks()
    templates = builtin_templates.load_case_templates()
    assert {'picerl-generic', 'ransomware'} <= set(playbooks)
    assert {'generic-intrusion', 'ransomware'} <= set(templates)
    for key, pb in playbooks.items():
        ok, msg = validate_definition(pb['definition'])
        assert ok, (key, msg)
        assert [p['phase'] for p in pb['definition']['phases']] == [1, 2, 3, 4, 5, 6], key
        for ph in pb['definition']['phases']:
            assert 3 <= len(ph['tasks']) <= 8, (key, ph['phase'])
            for act in ph.get('actions') or []:
                assert not act.get('auto_run'), (key, act)  # built-ins never auto-run
    for key, tpl in templates.items():
        defn = CaseTemplateDefinition.model_validate(tpl['definition'])
        assert builtin_templates.check_library_refs(defn) == [], key
        assert defn.playbook and defn.playbook.builtin in playbooks, key
        assert 4 <= len(defn.leads) <= 8, key
        for lead in defn.leads:
            assert lead.task_type == 'investigative_lead' or lead.task_type == 'verification'


def test_ransomware_template_contents():
    tpl = builtin_templates.get_case_template('ransomware')
    defn = CaseTemplateDefinition.model_validate(tpl['definition'])
    assert defn.defaults.severity == 'critical' and defn.defaults.tlp == 'amber'
    assert defn.defaults.classification == 'ransomware'
    assert {f.key for f in defn.custom_fields} == {'ransomware_family', 'ransom_note_observed',
                                                   'backups_impacted', 'leak_site_listing'}
    refs = {q.ref for q in defn.questions}
    assert {'ss:SSQ-025', 'ss:SSQ-026', 'ss:SSQ-009'} <= refs


def test_builtin_keys_are_matched_not_used_as_paths():
    assert builtin_templates.parse_builtin_ref('builtin:ransomware') == 'ransomware'
    for bad in ('builtin:../../etc/passwd', 'builtin:Ransomware', 'ransomware', 'builtin:', None, 5):
        assert builtin_templates.parse_builtin_ref(bad) is None
    assert builtin_templates.get_case_template('../x') is None
    assert builtin_templates.get_playbook(None) is None


# ── loader robustness (synthetic files, never the shipped data) ───────────

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def test_core_loader_rejects_malformed_files(tmp_path):
    bad = tmp_path / 'core.yaml'
    _write(bad, """
        schema: sheetstorm-question-library
        version: 1
        namespace: ss
        name: x
        license: MIT
        facets: [{id: SSF-01, name: A}]
        questions: [{id: SSQ-001, facet: SSF-99, question: Why was this done?}]
    """)
    with pytest.raises(question_library.LibraryError):
        question_library.load_library(str(bad), str(tmp_path / 'none'))
    _write(bad, "questions: [unclosed")
    with pytest.raises(question_library.LibraryError):
        question_library.load_library(str(bad), str(tmp_path / 'none'))
    # python object tags are not constructed (safe_load)
    _write(bad, "x: !!python/object/apply:os.system ['true']")
    with pytest.raises(question_library.LibraryError):
        question_library.load_library(str(bad), str(tmp_path / 'none'))


def test_dfiq_loader_builds_tree_and_drops_dangling_parents(tmp_path):
    dfiq = tmp_path / 'dfiq'
    _write(dfiq / 'scenarios' / 'S1001.yaml', """
        id: S1001
        name: Data Exfiltration
        type: scenario
        uuid: aaaa
        dfiq_version: 1.1.0
    """)
    _write(dfiq / 'facets' / 'F1001.yaml', """
        id: F1001
        name: Cloud storage
        type: facet
        uuid: bbbb
        dfiq_version: 1.1.0
        parent_ids: [S1001, S9999]
    """)
    _write(dfiq / 'questions' / 'Q1001.yaml', """
        id: Q1001
        name: Was data uploaded to personal cloud storage?
        description: Check proxy logs.
        type: question
        dfiq_version: 1.1.0
        tags: [exfil]
        parent_ids: [F1001, F9999]
        approaches:
          - name: Proxy logs
            description: Search for uploads.
            references: [https://example.test/ref]
    """)
    _write(dfiq / 'questions' / 'Q1002.yaml', """
        id: Q1002
        name: Orphan question
        type: question
        dfiq_version: 1.1.0
        parent_ids: [F7777]
    """)
    lib = question_library.load_library(question_library.CORE_FILE, str(dfiq))
    q = lib.get('dfiq:Q1001')
    assert q.source == 'dfiq' and q.facet == 'Cloud storage' and q.group_ref == 'dfiq:S1001'
    assert q.guidance[0]['name'] == 'Proxy logs'
    assert lib.get('dfiq:Q1002').facet is None
    assert {s['key'] for s in lib.sources} == {'core', 'dfiq'}
    assert any(g['ref'] == 'dfiq:S1001' and g['facets'][0]['questions'] for g in lib.groups)

    _write(dfiq / 'questions' / 'Q1003.yaml', """
        id: Q1003
        name: Wrong major version
        dfiq_version: 2.0.0
    """)
    with pytest.raises(question_library.LibraryError):
        question_library.load_library(question_library.CORE_FILE, str(dfiq) + '/')


def test_playbook_loader_refuses_auto_run_and_bad_definitions(tmp_path):
    base = """
        schema: sheetstorm-playbook
        key: bad
        name: Bad
        definition:
          phases:
            - phase: 1
              tasks: [{title: "t"}]
              actions: [{key: a, type: enrich_iocs, auto_run: true}]
    """
    _write(tmp_path / 'bad.yaml', base)
    with pytest.raises(builtin_templates.BuiltinError, match='auto_run'):
        builtin_templates.load_playbooks(str(tmp_path))
    _write(tmp_path / 'bad.yaml', base.replace('auto_run: true', 'auto_run: false').replace('key: bad', 'key: other'))
    with pytest.raises(builtin_templates.BuiltinError, match='file name'):
        builtin_templates.load_playbooks(str(tmp_path) + '/')
    _write(tmp_path / 'bad.yaml', base.replace('true', 'false').replace('type: enrich_iocs', 'type: rm_rf'))
    with pytest.raises(builtin_templates.BuiltinError, match='invalid action type'):
        builtin_templates.load_playbooks(str(tmp_path) + '//')


def test_template_loader_rejects_unknown_refs(tmp_path):
    _write(tmp_path / 'tpl.yaml', """
        schema: sheetstorm-case-template
        key: tpl
        name: T
        definition:
          schema_version: 1
          questions: [{ref: "ss:SSQ-999"}]
    """)
    with pytest.raises(builtin_templates.BuiltinError, match='unknown library question'):
        builtin_templates.load_case_templates(str(tmp_path))


# ── no unsafe deserialisation in the code that reads data files ───────────

_FILES = ['services/question_library.py', 'services/builtin_templates.py', 'services/case_template_service.py',
          'services/question_service.py', 'services/playbook_service.py', 'api/v1/endpoints/questions.py',
          'api/v1/endpoints/case_templates.py', 'api/v1/endpoints/playbooks.py']


@pytest.mark.parametrize('rel', _FILES)
def test_no_unsafe_loaders(rel):
    tree = ast.parse(open(os.path.join(APP_DIR, rel), encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            assert name not in ('yaml.load', 'yaml.unsafe_load', 'yaml.full_load', 'pickle.load', 'pickle.loads',
                                'eval', 'exec'), f'{rel}: {name}'
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] + [getattr(node, 'module', None) or '']
            assert 'pickle' not in mods, rel
