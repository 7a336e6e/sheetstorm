"""W0-FND: utils/hash_chain.py — golden vectors, strict/lenient canonical JSON,
linear-chain verification, advisory lock, stdlib-only guarantee."""
import ast
import hashlib
import os
import sys

import pytest

from app.utils import hash_chain as hc

HASH_CHAIN_PATH = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'hash_chain.py')

# Golden vectors: changing any of these breaks every existing chain and every
# exported custody bundle. Do not "fix" them; version the domain instead.
GOLDEN_PAYLOAD = {'b': 1, 'a': 'é', 'c': [None, True, 'x']}
GOLDEN_CANONICAL = '{"a":"é","b":1,"c":[null,true,"x"]}'.encode('utf-8')
GOLDEN_GENESIS = '985ebdcda3bff8c4481bbeda14a9753fbbd9ed4995f309c4193aaffc021a9f10'
GOLDEN_LINK = 'a20aed51bf10a2c34d858b900bd79bf27e0941c7bad95cab22fd49ed4fcc42c6'
GOLDEN_HMAC = '98755ce7a0d431b5d7b8ec8e343ada3bcaa4f6c44ca468cffcbaa9c273634dd7'


def test_golden_vectors():
    payload = hc.canonical_json(GOLDEN_PAYLOAD)
    assert payload == GOLDEN_CANONICAL
    assert hc.genesis_hash('custody-v3', 'incident', '00000000-0000-0000-0000-000000000001') == GOLDEN_GENESIS
    assert hc.link_hash('custody-v3', '0' * 64, payload) == GOLDEN_LINK
    assert hc.hmac_hex('k', 'data') == GOLDEN_HMAC


def test_golden_vectors_match_documented_formulas():
    payload = hc.canonical_json(GOLDEN_PAYLOAD)
    assert GOLDEN_GENESIS == hashlib.sha256(
        b'sheetstorm:custody-v3:genesis:incident:00000000-0000-0000-0000-000000000001').hexdigest()
    assert GOLDEN_LINK == hashlib.sha256(b'custody-v3\x00' + b'0' * 64 + b'\x00' + payload).hexdigest()
    assert hc.hmac_hex(b'k', b'data') == GOLDEN_HMAC


@pytest.mark.parametrize('bad', [{'x': 1.0}, {'x': float('nan')}, {1: 'x'}, {'x': object()},
                                 [1, {'y': [2.5]}]])
def test_strict_rejects_floats_nonstr_keys_and_unknown_types(bad):
    with pytest.raises(ValueError):
        hc.canonical_json(bad)


def test_lenient_mode_is_deterministic_and_never_raises():
    out = hc.canonical_json({'f': 1.5, 'n': float('nan'), 1: 'x', 'o': {'z': 1, 'a': 2}}, strict=False)
    assert out == b'{"1":"x","f":1.5,"n":"nan","o":{"a":2,"z":1}}'


def test_link_hash_requires_bytes():
    with pytest.raises(TypeError):
        hc.link_hash('audit-v1', 'x', 'not-bytes')


def _build_chain(n, domain='decision-v1'):
    genesis = hc.genesis_hash(domain, 'incident', 'i1')
    rows, prev = [], genesis
    for seq in range(1, n + 1):
        row = {'id': f'r{seq}', 'seq': seq, 'prev_hash': prev, 'data': f'v{seq}', 'created_at': seq}
        row['entry_hash'] = hc.link_hash(domain, prev, hc.canonical_json({'data': row['data'], 'seq': seq}))
        rows.append(row)
        prev = row['entry_hash']
    return genesis, rows


def _payload(row):
    return hc.canonical_json({'data': row['data'], 'seq': row['seq']})


def test_verify_linear_chain_ok():
    genesis, rows = _build_chain(5)
    assert hc.verify_linear_chain(rows, 'decision-v1', genesis, 'prev_hash', _payload, start_seq=1) == []


def test_verify_linear_chain_detects_edit_once():
    genesis, rows = _build_chain(5)
    rows[2]['data'] = 'tampered'
    failures = hc.verify_linear_chain(rows, 'decision-v1', genesis, 'prev_hash', _payload)
    assert failures == [{'seq': 3, 'id': 'r3', 'reason': 'entry_hash_mismatch'}]


def test_verify_linear_chain_detects_deletion_duplicate_and_regression():
    genesis, rows = _build_chain(5)
    del rows[2]
    reasons = {f['reason'] for f in hc.verify_linear_chain(rows, 'decision-v1', genesis, 'prev_hash', _payload)}
    assert {'seq_gap', 'prev_hash_mismatch'} <= reasons

    genesis, rows = _build_chain(3)
    rows.append(dict(rows[-1]))
    assert 'seq_duplicate' in {f['reason'] for f in hc.verify_linear_chain(
        rows, 'decision-v1', genesis, 'prev_hash', _payload)}

    genesis, rows = _build_chain(3)
    rows[2]['created_at'] = 0
    assert [f['reason'] for f in hc.verify_linear_chain(
        rows, 'decision-v1', genesis, 'prev_hash', _payload)] == ['timestamp_regression']


def test_verify_linear_chain_wrong_genesis_and_custom_hash_fn():
    genesis, rows = _build_chain(2)
    failures = hc.verify_linear_chain(rows, 'decision-v1', 'f' * 64, 'prev_hash', _payload)
    assert failures == [{'seq': 1, 'id': 'r1', 'reason': 'prev_hash_mismatch'}]
    keyed = lambda d, p, b: hc.hmac_hex('key', d.encode() + b'\x00' + p.encode() + b'\x00' + b)  # noqa: E731
    assert len(hc.verify_linear_chain(rows, 'decision-v1', genesis, 'prev_hash', _payload,
                                      hash_fn=keyed)) == 2


def test_hash_chain_is_stdlib_only():
    """The module ships inside custody bundles: stdlib imports only, except the
    lazy SQLAlchemy import inside advisory_xact_lock."""
    tree = ast.parse(open(HASH_CHAIN_PATH, encoding='utf-8').read())
    lazy_ok = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'advisory_xact_lock':
            lazy_ok = {id(n) for n in ast.walk(node)}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, 'no relative imports'
            names = [node.module or '']
        for name in names:
            top = name.split('.')[0]
            if id(node) in lazy_ok and top == 'sqlalchemy':
                continue
            assert top in sys.stdlib_module_names, f'non-stdlib import {name!r} in hash_chain.py'


def test_hash_chain_runs_standalone(tmp_path):
    """Importable without the app package (as in an exported bundle)."""
    import subprocess
    import shutil
    shutil.copy(HASH_CHAIN_PATH, tmp_path / 'hash_chain.py')
    out = subprocess.run([sys.executable, '-c',
                          'import hash_chain as h; print(h.genesis_hash("custody-v3","incident",'
                          '"00000000-0000-0000-0000-000000000001"))'],
                         cwd=tmp_path, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == GOLDEN_GENESIS


def test_advisory_xact_lock_executes(app, db):
    with app.app_context():
        hc.advisory_xact_lock(db.session, 'custody:test-lock')
        held = db.session.execute(db.text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()")).scalar()
        assert held >= 1
        db.session.rollback()
