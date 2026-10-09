"""One-click DFIQ import (services/dfiq_import.py, /questions/library/dfiq).

No network and no vendored DFIQ: archives are synthesized here, and the pinned
SHA-256 is patched to match them (its real value is a constant reviewed in
code). Upload and download paths, integrity refusal, path-traversal and
non-file members, storage, library visibility, removal and permissions.
"""
import hashlib
import io
import tarfile

import pytest

from app.services import dfiq_import, question_library

URL = '/api/v1/questions/library/dfiq'
TOP = 'dfiq-abc'


def _yaml(**fields):
    lines = []
    for k, v in fields.items():
        if isinstance(v, list):
            lines.append(f'{k}:')
            lines.extend(f'  - {x}' for x in v)
        else:
            lines.append(f'{k}: {v}')
    return ('\n'.join(lines) + '\n').encode()


def make_archive(extra=None):
    files = {
        f'{TOP}/LICENSE': b'Apache License 2.0\n',
        f'{TOP}/dfiq/data/scenarios/S1001.yaml': _yaml(id='S1001', name='Data exfiltration', dfiq_version='1.1.0'),
        f'{TOP}/dfiq/data/facets/F1001.yaml': _yaml(id='F1001', name='Initial access', dfiq_version='1.1.0',
                                                     parent_ids=['S1001']),
        f'{TOP}/dfiq/data/questions/Q1001.yaml': _yaml(id='Q1001', name='How did the attacker get in?',
                                                        dfiq_version='1.1.0', parent_ids=['F1001']),
        f'{TOP}/dfiq/data/questions/Q1002.yaml': _yaml(id='Q1002', name='Which accounts were used?',
                                                        dfiq_version='1.1.0', parent_ids=['F1001']),
        f'{TOP}/README.md': b'ignored',
    }
    files.update(extra or {})
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            if data is None:  # a symlink pointing outside
                info.type, info.linkname = tarfile.SYMTYPE, '/etc/passwd'
                tar.addfile(info)
                continue
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def pinned(monkeypatch):
    def pin(data):
        monkeypatch.setattr(dfiq_import, 'DFIQ_ARCHIVE_SHA256', hashlib.sha256(data).hexdigest())
        return data
    return pin


@pytest.fixture(autouse=True)
def _clean(app, db):
    from app.models.system_setting import SystemSetting
    SystemSetting.query.filter_by(key=question_library.DFIQ_SETTING_KEY).delete()
    db.session.commit()
    question_library.invalidate_db_cache()
    yield
    SystemSetting.query.filter_by(key=question_library.DFIQ_SETTING_KEY).delete()
    db.session.commit()
    question_library.invalidate_db_cache()


def test_parse_reads_only_dfiq_yaml_and_ignores_links_and_other_paths(pinned):
    data = pinned(make_archive({
        f'{TOP}/dfiq/data/questions/../../../evil.yaml': _yaml(id='Q9999', name='x', dfiq_version='1.0.0'),
        f'{TOP}/other/questions/Q1003.yaml': _yaml(id='Q1003', name='elsewhere', dfiq_version='1.0.0'),
        f'{TOP}/dfiq/data/questions/link.yaml': None,
    }))
    doc = dfiq_import.parse_archive(data)
    assert [q['id'] for q in doc['questions']] == ['Q1001', 'Q1002']
    assert doc['counts'] == {'scenarios': 1, 'facets': 1, 'questions': 2}
    assert doc['license'].startswith('Apache License')


def test_integrity_mismatch_is_refused(pinned):
    pinned(make_archive())
    with pytest.raises(dfiq_import.DfiqImportError) as exc:
        dfiq_import.verify_archive(make_archive({f'{TOP}/x': b'tampered'}))
    assert exc.value.code == 'integrity_mismatch'


def test_bad_yaml_and_bad_ids_are_refused(pinned):
    for extra in ({f'{TOP}/dfiq/data/questions/Q1003.yaml': b'id: [unclosed'},
                  {f'{TOP}/dfiq/data/questions/Q1003.yaml': _yaml(id='nope', name='x', dfiq_version='1.0.0')}):
        with pytest.raises(dfiq_import.DfiqImportError) as exc:
            dfiq_import.parse_archive(pinned(make_archive(extra)))
        assert exc.value.code == 'invalid_archive'


def test_platform_admin_imports_by_upload_and_library_shows_it(platform_admin, auth, pinned):
    from app.models import AuditLog
    data = pinned(make_archive())
    client = auth(platform_admin)
    assert client.get(URL).get_json()['imported'] is False
    resp = client.post(f'{URL}/import', data={'archive': (io.BytesIO(data), 'dfiq.tar.gz')},
                       content_type='multipart/form-data')
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['imported'] is True and body['method'] == 'upload' and body['counts']['questions'] == 2

    tree = client.get('/api/v1/questions/library').get_json()
    refs = {q['ref'] for g in tree['groups'] for f in g['facets'] for q in f['questions']}
    assert {'dfiq:Q1001', 'dfiq:Q1002'} <= refs
    assert any(s['key'] == 'dfiq' for s in tree['sources'])
    assert AuditLog.query.filter_by(action='dfiq_import').count() >= 1

    assert client.delete(URL).get_json()['imported'] is False
    question_library.invalidate_db_cache()
    tree = client.get('/api/v1/questions/library').get_json()
    assert not any(s['key'] == 'dfiq' for s in tree['sources'])


def test_download_path_uses_the_pinned_url(platform_admin, auth, pinned, monkeypatch):
    data = pinned(make_archive())
    seen = {}

    class Resp:
        status_code = 200

        def iter_content(self, chunk_size):
            yield data

        def close(self):
            pass

    def fake_get(url, **kw):
        seen.update(url=url, **kw)
        return Resp()

    monkeypatch.setattr(dfiq_import.requests, 'get', fake_get)
    monkeypatch.setattr(dfiq_import, 'validate_outbound_url', lambda url: (True, ''))  # no DNS in CI
    resp = auth(platform_admin).post(f'{URL}/import')
    assert resp.status_code == 200, resp.get_json()
    assert seen['url'] == dfiq_import.DFIQ_URL and seen['allow_redirects'] is False
    assert resp.get_json()['method'] == 'download'


def test_tampered_upload_is_refused(platform_admin, auth, pinned):
    pinned(make_archive())
    resp = auth(platform_admin).post(f'{URL}/import', data={'archive': (io.BytesIO(b'not the archive'), 'x.tar.gz')},
                                     content_type='multipart/form-data')
    assert resp.status_code == 400 and resp.get_json()['error'] == 'integrity_mismatch'


def test_permissions(users, auth):
    admin = auth(users['Administrator'])  # org A admin: templates:manage but not platform admin
    body = admin.get(URL).get_json()
    assert body['can_import'] is False and body['pinned_commit'] == dfiq_import.DFIQ_COMMIT
    assert admin.post(f'{URL}/import').status_code == 403
    assert admin.delete(URL).status_code == 403
    assert auth(users['Viewer']).get(URL).status_code == 403


def test_pinned_constants_look_sane():
    assert len(dfiq_import.DFIQ_COMMIT) == 40 and dfiq_import.DFIQ_COMMIT in dfiq_import.DFIQ_URL
    assert len(dfiq_import.DFIQ_ARCHIVE_SHA256) == 64
    assert dfiq_import.DFIQ_URL.startswith('https://codeload.github.com/google/dfiq/')
