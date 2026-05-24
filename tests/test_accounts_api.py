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


def test_delete_account(client):
    acc_id = client.post('/api/accounts', json={'name': 'Bye'}).get_json()['account']['id']
    resp = client.delete(f'/api/accounts/{acc_id}')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert client.get('/api/accounts').get_json() == []


def test_delete_account_sets_characters_unassigned(client):
    from models import get_session, Character
    acc_id = client.post('/api/accounts', json={'name': 'Doomed'}).get_json()['account']['id']
    s = get_session()
    s.add(Character(id=789, name='Pilot', refresh_token='rt', account_id=acc_id))
    s.commit()
    s.close()

    client.delete(f'/api/accounts/{acc_id}')

    s = get_session()
    char = s.query(Character).filter_by(id=789).first()
    assert char is not None
    assert char.account_id is None
    s.close()


def test_delete_account_404(client):
    resp = client.delete('/api/accounts/999')
    assert resp.status_code == 404


def test_assign_character_to_account(client):
    from models import get_session, Character
    acc_id = client.post('/api/accounts', json={'name': 'Main'}).get_json()['account']['id']
    s = get_session()
    s.add(Character(id=100, name='C1', refresh_token='rt'))
    s.commit()
    s.close()

    resp = client.put('/api/characters/100/account', json={'account_id': acc_id})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    s = get_session()
    assert s.query(Character).filter_by(id=100).first().account_id == acc_id
    s.close()


def test_unassign_character_with_null(client):
    from models import get_session, Character
    acc_id = client.post('/api/accounts', json={'name': 'Main'}).get_json()['account']['id']
    s = get_session()
    s.add(Character(id=101, name='C2', refresh_token='rt', account_id=acc_id))
    s.commit()
    s.close()

    resp = client.put('/api/characters/101/account', json={'account_id': None})
    assert resp.status_code == 200

    s = get_session()
    assert s.query(Character).filter_by(id=101).first().account_id is None
    s.close()


def test_assign_character_404_character(client):
    acc_id = client.post('/api/accounts', json={'name': 'Main'}).get_json()['account']['id']
    resp = client.put('/api/characters/9999/account', json={'account_id': acc_id})
    assert resp.status_code == 404


def test_assign_character_404_account(client):
    from models import get_session, Character
    s = get_session()
    s.add(Character(id=102, name='C3', refresh_token='rt'))
    s.commit()
    s.close()

    resp = client.put('/api/characters/102/account', json={'account_id': 9999})
    assert resp.status_code == 404


def test_locations_includes_account_fields(client):
    from models import get_session, Character
    acc_id = client.post('/api/accounts', json={'name': 'Main', 'subscription': 'omega'}).get_json()['account']['id']
    s = get_session()
    s.add_all([
        Character(id=200, name='Assigned', refresh_token='rt', account_id=acc_id),
        Character(id=201, name='Unassigned', refresh_token='rt'),
    ])
    s.commit()
    s.close()

    data = client.get('/api/locations').get_json()
    by_name = {c['name']: c for c in data}
    assert by_name['Assigned']['account_id'] == acc_id
    assert by_name['Assigned']['account_name'] == 'Main'
    assert by_name['Assigned']['account_subscription'] == 'omega'
    assert by_name['Unassigned']['account_id'] is None
    assert by_name['Unassigned']['account_name'] is None
