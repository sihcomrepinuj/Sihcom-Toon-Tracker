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
