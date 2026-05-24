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


def test_patch_account_name(client):
    create = client.post('/api/accounts', json={'name': 'Old'}).get_json()
    acc_id = create['account']['id']
    resp = client.patch(f'/api/accounts/{acc_id}', json={'name': 'New'})
    assert resp.status_code == 200
    assert resp.get_json()['account']['name'] == 'New'


def test_patch_account_subscription_and_notes(client):
    acc_id = client.post('/api/accounts', json={'name': 'Acc'}).get_json()['account']['id']
    resp = client.patch(f'/api/accounts/{acc_id}', json={'subscription': 'alpha', 'notes': 'cheap'})
    body = resp.get_json()
    assert body['account']['subscription'] == 'alpha'
    assert body['account']['notes'] == 'cheap'


def test_patch_account_404(client):
    resp = client.patch('/api/accounts/999', json={'name': 'Ghost'})
    assert resp.status_code == 404


def test_patch_account_rejects_duplicate_name(client):
    client.post('/api/accounts', json={'name': 'A'})
    b_id = client.post('/api/accounts', json={'name': 'B'}).get_json()['account']['id']
    resp = client.patch(f'/api/accounts/{b_id}', json={'name': 'A'})
    assert resp.status_code == 422
