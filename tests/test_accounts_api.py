from models import get_session, Account


def test_list_accounts_empty(client):
    resp = client.get('/api/accounts')
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_accounts_with_data(client):
    s = get_session()
    s.add_all([
        Account(name='Main', subscription='omega'),
        Account(name='Alt', subscription='alpha', notes='hauler'),
    ])
    s.commit()
    s.close()

    resp = client.get('/api/accounts')
    assert resp.status_code == 200
    data = resp.get_json()
    names = sorted(a['name'] for a in data)
    assert names == ['Alt', 'Main']
    alt = next(a for a in data if a['name'] == 'Alt')
    assert alt['subscription'] == 'alpha'
    assert alt['notes'] == 'hauler'
    assert alt['character_count'] == 0
    assert 'id' in alt


def test_create_account(client):
    resp = client.post('/api/accounts', json={'name': 'Main', 'subscription': 'omega'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['account']['name'] == 'Main'
    assert body['account']['subscription'] == 'omega'


def test_create_account_defaults_to_unknown(client):
    resp = client.post('/api/accounts', json={'name': 'Plain'})
    assert resp.status_code == 200
    assert resp.get_json()['account']['subscription'] == 'unknown'


def test_create_account_requires_name(client):
    resp = client.post('/api/accounts', json={'name': '   '})
    assert resp.status_code == 422
    assert 'error' in resp.get_json()


def test_create_account_rejects_duplicate(client):
    client.post('/api/accounts', json={'name': 'Main'})
    resp = client.post('/api/accounts', json={'name': 'Main'})
    assert resp.status_code == 422


def test_create_account_rejects_invalid_subscription(client):
    resp = client.post('/api/accounts', json={'name': 'X', 'subscription': 'platinum'})
    assert resp.status_code == 422
