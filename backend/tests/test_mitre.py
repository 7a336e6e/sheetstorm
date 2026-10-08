"""Item 7: MITRE suggest/patterns resolve the organization from the current
user (no token claim needed), stay org-scoped, admin:manage is granted, and
timeline creation auto-suggests from the org's patterns."""


def test_suggest_works_with_plain_tokens(app, users, auth):
    resp = auth(users['Analyst']).post('/api/v1/mitre/suggest', json={'activity': 'ran powershell -enc'})
    assert resp.status_code == 200
    assert [s['technique'] for s in resp.get_json()['suggestions']] == ['T1059']


def test_suggest_is_org_scoped(app, users, auth):
    resp = auth(users['admin_b']).post('/api/v1/mitre/suggest', json={'activity': 'ran powershell then nmap'})
    assert [s['technique'] for s in resp.get_json()['suggestions']] == ['T1046']


def test_suggest_bad_limit_is_400(app, users, auth):
    assert auth(users['Analyst']).post('/api/v1/mitre/suggest',
                                       json={'activity': 'x', 'limit': 'many'}).status_code == 400


def test_patterns_list_scoped(app, users, auth):
    techs = {p['technique'] for p in auth(users['Viewer']).get('/api/v1/mitre/patterns').get_json()['patterns']}
    assert techs == {'T1059'}


def test_admin_can_manage_patterns(app, users, auth):
    admin = auth(users['admin_b'])
    resp = admin.post('/api/v1/mitre/patterns', json={'technique': 'T1003', 'tactic': 'credential-access',
                                                      'name': 'OS Credential Dumping', 'keywords': ['mimikatz']})
    assert resp.status_code == 201
    assert auth(users['Analyst']).post('/api/v1/mitre/patterns', json={
        'technique': 'T1', 'tactic': 'x', 'name': 'x'}).status_code == 403
    assert admin.delete('/api/v1/mitre/patterns/T1003').status_code == 200


def test_timeline_create_autosuggests(app, users, auth, make_incident):
    inc = make_incident()
    resp = auth(users['Analyst']).post(f'/api/v1/incidents/{inc.id}/timeline', json={
        'timestamp': '2026-01-01T10:00:00Z', 'activity': 'Attacker used powershell to download payload'})
    assert resp.status_code == 201
    assert resp.get_json()['mitre_mappings'][0]['technique'] == 'T1059'
