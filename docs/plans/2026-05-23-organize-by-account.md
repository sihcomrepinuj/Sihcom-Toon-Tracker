# Organize Characters by Account — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a first-class `Account` entity so the user can group their EVE characters by account, assign account-level properties (subscription type, notes), and toggle the dashboard between Grouped and Loose views.

**Architecture:** New `Account` SQLAlchemy model with `name`, `subscription` ('omega' | 'alpha' | 'unknown'), `notes`. Nullable FK `account_id` on `Character` with `ON DELETE SET NULL`. CRUD API mirrors the existing role endpoints. Settings page gains an Accounts section and a per-character dropdown. Dashboard gains a view toggle (Grouped headers vs Loose flat grid) and an account filter chip row.

**Tech Stack:** Flask 3.x, SQLAlchemy 2.x, SQLite, Jinja2, vanilla JS, pytest (newly introduced for this feature).

**Design doc:** `docs/plans/2026-05-23-organize-by-account-design.md`

**Working directory:** `C:\Users\Neeraj\Documents\Sihcom Toon Tracker`

---

## Task 1: Add pytest scaffolding

**Why:** Subsequent API tasks are TDD; we need a working test runner with an isolated SQLite database fixture so tests can't touch live `tracker.db`.

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

**Step 1: Add pytest to requirements**

Append to `requirements.txt`:
```
pytest
```

Run:
```powershell
pip install pytest
```

**Step 2: Create empty `tests/__init__.py`**

```
(empty file)
```

**Step 3: Create `tests/conftest.py`**

```python
import os
import tempfile
import pytest

from config import Config


@pytest.fixture
def temp_db(monkeypatch):
    """Point Config.DATABASE_PATH at a temp file for the duration of one test."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    monkeypatch.setattr(Config, 'DATABASE_PATH', path)
    # Initialize schema against the fresh DB
    from models import init_db
    init_db()
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def client(temp_db):
    """Flask test client with an isolated DB."""
    import app as app_module
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c
```

**Step 4: Verify pytest can collect tests**

Run:
```powershell
pytest tests/ --collect-only
```
Expected: `no tests ran` (no test files yet) with exit code 5 — that's fine, it means pytest is installed and can scan the folder.

**Step 5: Commit**

```powershell
git add requirements.txt tests/__init__.py tests/conftest.py
git commit -m "Add pytest scaffolding with isolated DB fixture"
```

---

## Task 2: Add Account model and Character FK

**Why:** Data model is the foundation. Everything else depends on it.

**Files:**
- Modify: `models.py`

**Step 1: Write the failing test** — `tests/test_models.py`

```python
from models import get_session, Character, Account


def test_create_account(temp_db):
    s = get_session()
    acc = Account(name='Main', subscription='omega', notes='primary')
    s.add(acc)
    s.commit()

    fetched = s.query(Account).filter_by(name='Main').first()
    assert fetched is not None
    assert fetched.subscription == 'omega'
    assert fetched.notes == 'primary'
    s.close()


def test_account_name_unique(temp_db):
    from sqlalchemy.exc import IntegrityError
    s = get_session()
    s.add(Account(name='Dup'))
    s.commit()
    s.add(Account(name='Dup'))
    try:
        s.commit()
        assert False, "expected IntegrityError"
    except IntegrityError:
        s.rollback()
    s.close()


def test_character_account_relationship(temp_db):
    s = get_session()
    acc = Account(name='Main', subscription='omega')
    char = Character(id=123, name='Pilot', refresh_token='rt', account=acc)
    s.add_all([acc, char])
    s.commit()

    fetched = s.query(Character).filter_by(id=123).first()
    assert fetched.account.name == 'Main'
    assert acc.characters[0].id == 123
    s.close()


def test_delete_account_sets_character_null(temp_db):
    s = get_session()
    acc = Account(name='Doomed')
    char = Character(id=456, name='Survivor', refresh_token='rt', account=acc)
    s.add_all([acc, char])
    s.commit()

    s.delete(acc)
    s.commit()

    fetched = s.query(Character).filter_by(id=456).first()
    assert fetched is not None
    assert fetched.account_id is None
    s.close()
```

**Step 2: Run tests to verify they fail**

Run:
```powershell
pytest tests/test_models.py -v
```
Expected: All four fail with `ImportError: cannot import name 'Account'`.

**Step 3: Implement Account model + FK in `models.py`**

After the `Role` class (around line 49), insert:

```python
class Account(Base):
    __tablename__ = 'accounts'

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String, nullable=False, unique=True)
    subscription = Column(String, nullable=False, default='unknown')  # 'omega' | 'alpha' | 'unknown'
    notes        = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    characters = relationship('Character', back_populates='account')

    def __repr__(self):
        return f"<Account(id={self.id}, name='{self.name}', subscription='{self.subscription}')>"
```

Inside the `Character` class (around line 27, after `added_at`), add:

```python
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True)
```

And inside `Character`'s relationships block (around line 32):

```python
    account = relationship('Account', back_populates='characters')
```

**Step 4: Enable FK enforcement in SQLite**

SQLite does not enforce foreign keys by default, so `ON DELETE SET NULL` is a no-op without this. Add an event listener at the bottom of `models.py` (just before `init_db`):

```python
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

**Step 5: Run tests to verify they pass**

Run:
```powershell
pytest tests/test_models.py -v
```
Expected: all four pass.

**Step 6: Commit**

```powershell
git add models.py tests/test_models.py
git commit -m "Add Account model and nullable FK on Character with SET NULL"
```

---

## Task 3: Migrate existing tracker.db

**Why:** `init_db()` uses `create_all`, which creates the `accounts` table but does NOT add `account_id` to the existing `characters` table. Without a migration, the live DB would fail on first query referencing the column.

**Files:**
- Modify: `models.py`

**Step 1: Write the failing test** — append to `tests/test_models.py`

```python
import sqlite3


def test_migration_adds_account_id_to_legacy_table(temp_db, monkeypatch):
    """Simulate a pre-feature DB: drop the column, then re-run init_db."""
    # Drop and recreate the characters table without account_id to simulate legacy
    conn = sqlite3.connect(temp_db)
    conn.execute("DROP TABLE characters")
    conn.execute("""
        CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            refresh_token VARCHAR NOT NULL,
            access_token VARCHAR,
            token_expiry DATETIME,
            corporation_id INTEGER,
            added_at DATETIME
        )
    """)
    conn.commit()
    conn.close()

    # Run migration
    from models import init_db
    init_db()

    # Verify account_id column now exists
    conn = sqlite3.connect(temp_db)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(characters)")]
    conn.close()
    assert 'account_id' in cols
```

**Step 2: Run to verify failure**

Run:
```powershell
pytest tests/test_models.py::test_migration_adds_account_id_to_legacy_table -v
```
Expected: FAIL — `account_id` not in cols.

**Step 3: Implement migration in `models.py`**

Replace the existing `init_db()` (around line 110) with:

```python
def init_db():
    """Initialize the application database, applying any needed migrations."""
    engine = create_engine(f'sqlite:///{Config.DATABASE_PATH}')
    Base.metadata.create_all(engine)
    _migrate_add_account_id(engine)
    return engine


def _migrate_add_account_id(engine):
    """Add characters.account_id if missing (idempotent)."""
    with engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text("PRAGMA table_info(characters)")).fetchall()
        cols = [row[1] for row in result]
        if 'account_id' not in cols:
            conn.execute(text(
                "ALTER TABLE characters ADD COLUMN account_id INTEGER "
                "REFERENCES accounts(id) ON DELETE SET NULL"
            ))
            conn.commit()
```

**Step 4: Run to verify pass + existing tests still pass**

Run:
```powershell
pytest tests/test_models.py -v
```
Expected: all five pass.

**Step 5: Commit**

```powershell
git add models.py tests/test_models.py
git commit -m "Add idempotent migration for characters.account_id"
```

---

## Task 4: API — GET /api/accounts

**Files:**
- Modify: `app.py`
- Create/append: `tests/test_accounts_api.py`

**Step 1: Write the failing test** — `tests/test_accounts_api.py`

```python
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
```

**Step 2: Run to verify failure**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: 404s — route not implemented.

**Step 3: Implement the route**

Add `Account` to the imports at the top of `app.py` (line 10):

```python
from models import init_db, get_session, Character, Role, LocationCache, SavedFit, CharacterSkill, Notepad, Account
```

After the existing role API section (after line 296), insert a new section header and route:

```python
# ============================================================================
# API ROUTES - Accounts
# ============================================================================

@app.route('/api/accounts', methods=['GET'])
def api_list_accounts():
    """List all accounts with character counts."""
    db_session = get_session()
    accounts = db_session.query(Account).all()
    data = [
        {
            'id': a.id,
            'name': a.name,
            'subscription': a.subscription,
            'notes': a.notes,
            'character_count': len(a.characters),
        }
        for a in accounts
    ]
    db_session.close()
    return jsonify(data)
```

**Step 4: Run to verify pass**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: both pass.

**Step 5: Commit**

```powershell
git add app.py tests/test_accounts_api.py
git commit -m "Add GET /api/accounts endpoint"
```

---

## Task 5: API — POST /api/accounts

**Files:**
- Modify: `app.py`
- Modify: `tests/test_accounts_api.py`

**Step 1: Append failing tests**

```python
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
```

**Step 2: Run to verify failure**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: 5 failures (the new tests).

**Step 3: Implement the route**

Append after `api_list_accounts`:

```python
_VALID_SUBSCRIPTIONS = {'omega', 'alpha', 'unknown'}


@app.route('/api/accounts', methods=['POST'])
def api_create_account():
    """Create a new account."""
    data = request.json or {}
    name = (data.get('name') or '').strip()
    subscription = data.get('subscription', 'unknown')
    notes = data.get('notes')

    if not name:
        return jsonify({'success': False, 'error': 'Account name is required'}), 422
    if subscription not in _VALID_SUBSCRIPTIONS:
        return jsonify({'success': False, 'error': 'Invalid subscription value'}), 422

    db_session = get_session()
    if db_session.query(Account).filter_by(name=name).first():
        db_session.close()
        return jsonify({'success': False, 'error': 'Account name already exists'}), 422

    account = Account(name=name, subscription=subscription, notes=notes)
    db_session.add(account)
    db_session.commit()
    result = {
        'id': account.id,
        'name': account.name,
        'subscription': account.subscription,
        'notes': account.notes,
        'character_count': 0,
    }
    db_session.close()
    return jsonify({'success': True, 'account': result})
```

**Step 4: Run to verify pass**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: all pass.

**Step 5: Commit**

```powershell
git add app.py tests/test_accounts_api.py
git commit -m "Add POST /api/accounts with validation"
```

---

## Task 6: API — PATCH /api/accounts/<id>

**Files:**
- Modify: `app.py`
- Modify: `tests/test_accounts_api.py`

**Step 1: Append failing tests**

```python
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
```

**Step 2: Run to verify failure**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: 4 failures.

**Step 3: Implement the route**

Append:

```python
@app.route('/api/accounts/<int:account_id>', methods=['PATCH'])
def api_patch_account(account_id):
    """Update an account's name / subscription / notes."""
    data = request.json or {}
    db_session = get_session()

    account = db_session.query(Account).filter_by(id=account_id).first()
    if not account:
        db_session.close()
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    if 'name' in data:
        new_name = (data['name'] or '').strip()
        if not new_name:
            db_session.close()
            return jsonify({'success': False, 'error': 'Account name is required'}), 422
        clash = db_session.query(Account).filter(
            Account.name == new_name, Account.id != account_id
        ).first()
        if clash:
            db_session.close()
            return jsonify({'success': False, 'error': 'Account name already exists'}), 422
        account.name = new_name

    if 'subscription' in data:
        if data['subscription'] not in _VALID_SUBSCRIPTIONS:
            db_session.close()
            return jsonify({'success': False, 'error': 'Invalid subscription value'}), 422
        account.subscription = data['subscription']

    if 'notes' in data:
        account.notes = data['notes']

    db_session.commit()
    result = {
        'id': account.id,
        'name': account.name,
        'subscription': account.subscription,
        'notes': account.notes,
        'character_count': len(account.characters),
    }
    db_session.close()
    return jsonify({'success': True, 'account': result})
```

**Step 4: Run to verify pass**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: all pass.

**Step 5: Commit**

```powershell
git add app.py tests/test_accounts_api.py
git commit -m "Add PATCH /api/accounts/<id> for inline edits"
```

---

## Task 7: API — DELETE /api/accounts/<id>

**Files:**
- Modify: `app.py`
- Modify: `tests/test_accounts_api.py`

**Step 1: Append failing tests**

```python
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
```

**Step 2: Run to verify failure**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: 3 failures.

**Step 3: Implement the route**

Append:

```python
@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def api_delete_account(account_id):
    """Delete an account; characters fall back to unassigned via ON DELETE SET NULL."""
    db_session = get_session()
    account = db_session.query(Account).filter_by(id=account_id).first()
    if not account:
        db_session.close()
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    db_session.delete(account)
    db_session.commit()
    db_session.close()
    return jsonify({'success': True})
```

**Step 4: Run to verify pass**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: all pass.

**Step 5: Commit**

```powershell
git add app.py tests/test_accounts_api.py
git commit -m "Add DELETE /api/accounts/<id>; characters fall back to unassigned"
```

---

## Task 8: API — PUT /api/characters/<id>/account

**Files:**
- Modify: `app.py`
- Modify: `tests/test_accounts_api.py`

**Step 1: Append failing tests**

```python
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
```

**Step 2: Run to verify failure**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: 4 failures.

**Step 3: Implement the route**

Append:

```python
@app.route('/api/characters/<int:character_id>/account', methods=['PUT'])
def api_assign_character_account(character_id):
    """Assign a character to an account (or null to unassign)."""
    data = request.json or {}
    account_id = data.get('account_id')

    db_session = get_session()
    character = db_session.query(Character).filter_by(id=character_id).first()
    if not character:
        db_session.close()
        return jsonify({'success': False, 'error': 'Character not found'}), 404

    if account_id is not None:
        account = db_session.query(Account).filter_by(id=account_id).first()
        if not account:
            db_session.close()
            return jsonify({'success': False, 'error': 'Account not found'}), 404
        character.account_id = account_id
    else:
        character.account_id = None

    db_session.commit()
    db_session.close()
    return jsonify({'success': True})
```

**Step 4: Run to verify pass**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: all pass.

**Step 5: Commit**

```powershell
git add app.py tests/test_accounts_api.py
git commit -m "Add PUT /api/characters/<id>/account for assignment"
```

---

## Task 9: Extend /api/locations + settings template context

**Why:** Dashboard JS and settings template need account data without a second fetch.

**Files:**
- Modify: `app.py`
- Modify: `tests/test_accounts_api.py`

**Step 1: Append failing test**

```python
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
```

**Step 2: Run to verify failure**

Run:
```powershell
pytest tests/test_accounts_api.py::test_locations_includes_account_fields -v
```
Expected: KeyError on `account_id`.

**Step 3: Extend `/api/locations`**

In `app.py`, modify `api_locations()` (line 159). Add `selectinload(Character.account)` to the query, then add three fields to each dict:

Replace:
```python
characters = db_session.query(Character).all()
```
with:
```python
characters = db_session.query(Character).options(selectinload(Character.account)).all()
```

Inside the `for char in characters:` loop, replace the `data.append({...})` block with:

```python
data.append({
    'id': char.id,
    'name': char.name,
    'system': location.solar_system_name if location else 'Unknown',
    'ship': location.ship_name if location else 'Unknown',
    'online': location.is_online if location else False,
    'roles': [role.name for role in char.roles],
    'portrait_url': f'https://images.evetech.net/characters/{char.id}/portrait?size=64',
    'last_updated': location.last_updated.isoformat() if location and location.last_updated else None,
    'corporation_id': char.corporation_id,
    'account_id': char.account_id,
    'account_name': char.account.name if char.account else None,
    'account_subscription': char.account.subscription if char.account else None,
})
```

**Step 4: Extend the settings route**

In `app.py`, modify `settings()` (line 59):

```python
@app.route('/settings')
def settings():
    """Settings page for character and role management."""
    db_session = get_session()
    characters = db_session.query(Character).options(
        selectinload(Character.roles),
        selectinload(Character.account),
    ).all()
    roles = db_session.query(Role).all()
    accounts = db_session.query(Account).all()
    db_session.close()
    return render_template(
        'settings.html',
        characters=characters,
        roles=roles,
        accounts=accounts,
        now=datetime.utcnow(),
    )
```

**Step 5: Run all API tests**

Run:
```powershell
pytest tests/test_accounts_api.py -v
```
Expected: all pass.

**Step 6: Commit**

```powershell
git add app.py tests/test_accounts_api.py
git commit -m "Surface account fields in /api/locations and settings context"
```

---

## Task 10: Settings UI — Accounts section

**Why:** User needs to create/edit/delete accounts before they can assign characters.

**Files:**
- Modify: `templates/settings.html`
- Modify: `static/style.css`

**Step 1: Add the Accounts section to `templates/settings.html`**

After the `<h2>Characters</h2>` section closes (after the existing `</section>` on line 42) and before the `<h2>Roles</h2>` section, insert:

```html
<section class="settings-section">
    <h2>Accounts</h2>
    <form id="createAccountForm" class="inline-form">
        <input type="text" id="newAccountName" placeholder="New account name" required>
        <select id="newAccountSubscription">
            <option value="unknown">Unknown</option>
            <option value="omega">Omega</option>
            <option value="alpha">Alpha</option>
        </select>
        <button type="submit" class="btn btn-secondary">Create Account</button>
    </form>

    {% if accounts %}
    <div class="accounts-list">
        {% for acc in accounts %}
        <div class="account-item" id="account-{{ acc.id }}" data-account-id="{{ acc.id }}">
            <div class="account-row">
                <input type="text"
                       class="account-name-input"
                       value="{{ acc.name }}"
                       data-original="{{ acc.name }}"
                       onchange="patchAccount({{ acc.id }}, 'name', this.value)">
                <select class="account-sub-select"
                        onchange="patchAccount({{ acc.id }}, 'subscription', this.value)">
                    <option value="unknown" {% if acc.subscription == 'unknown' %}selected{% endif %}>Unknown</option>
                    <option value="omega" {% if acc.subscription == 'omega' %}selected{% endif %}>Omega</option>
                    <option value="alpha" {% if acc.subscription == 'alpha' %}selected{% endif %}>Alpha</option>
                </select>
                <span class="account-char-count">{{ acc.characters|length }} char{{ '' if acc.characters|length == 1 else 's' }}</span>
                <button class="btn btn-danger btn-small" onclick="deleteAccount({{ acc.id }}, {{ acc.characters|length }})">Delete</button>
            </div>
            <textarea class="account-notes"
                      placeholder="Optional notes..."
                      onchange="patchAccount({{ acc.id }}, 'notes', this.value)">{{ acc.notes or '' }}</textarea>
        </div>
        {% endfor %}
    </div>
    {% endif %}
</section>
```

**Step 2: Add CSS for the accounts list**

Append to `static/style.css`:

```css
/* Accounts management */
.accounts-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 1rem;
}

.account-item {
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border-primary);
    border-radius: 6px;
    padding: 0.75rem;
}

.account-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.account-name-input {
    flex: 1;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border-input);
    border-radius: 4px;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
}

.account-sub-select {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border-input);
    border-radius: 4px;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
}

.account-char-count {
    font-size: 0.85rem;
    color: var(--color-text-secondary);
    white-space: nowrap;
}

.account-notes {
    width: 100%;
    margin-top: 0.5rem;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border-input);
    border-radius: 4px;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
    font-family: inherit;
    font-size: 0.85rem;
    min-height: 2rem;
    resize: vertical;
}
```

**Step 3: Smoke test**

Run:
```powershell
python app.py
```
Visit `http://localhost:5000/settings`. Expected:
- New "Accounts" section appears with a create form.
- Empty list (no accounts yet).
- No console errors.
- Ctrl+C to stop.

**Step 4: Commit**

```powershell
git add templates/settings.html static/style.css
git commit -m "Add Accounts section to settings page (HTML + CSS, no handlers yet)"
```

---

## Task 11: Settings UI — JS handlers + character account dropdown

**Files:**
- Modify: `templates/settings.html`

**Step 1: Add JS handlers**

Inside the existing `<script>` block in `templates/settings.html` (after `refreshSkills()` around line 243), append:

```javascript
// ---- Accounts CRUD ----
document.getElementById('createAccountForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('newAccountName').value.trim();
    const subscription = document.getElementById('newAccountSubscription').value;
    if (!name) return;
    try {
        const resp = await fetch('/api/accounts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, subscription })
        });
        const data = await resp.json();
        if (data.success) {
            location.reload();
        } else {
            alert(data.error || 'Error creating account');
        }
    } catch (err) {
        console.error(err);
        alert('Error creating account');
    }
});

async function patchAccount(accountId, field, value) {
    try {
        const resp = await fetch(`/api/accounts/${accountId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: value })
        });
        const data = await resp.json();
        if (!data.success) {
            alert(data.error || 'Error updating account');
            location.reload();
        }
    } catch (err) {
        console.error(err);
    }
}

async function deleteAccount(accountId, charCount) {
    const msg = charCount > 0
        ? `Move ${charCount} character${charCount === 1 ? '' : 's'} to Unassigned and delete this account?`
        : 'Delete this account?';
    if (!confirm(msg)) return;
    try {
        const resp = await fetch(`/api/accounts/${accountId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (data.success) location.reload();
        else alert(data.error || 'Error deleting account');
    } catch (err) {
        console.error(err);
    }
}

async function assignCharacterAccount(characterId, selectEl) {
    const value = selectEl.value;
    const payload = { account_id: value === '' ? null : parseInt(value, 10) };
    try {
        const resp = await fetch(`/api/characters/${characterId}/account`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!data.success) {
            alert(data.error || 'Error assigning account');
            location.reload();
        }
    } catch (err) {
        console.error(err);
    }
}
```

**Step 2: Add the per-character account dropdown to the character row**

In `templates/settings.html`, inside `character-manage-card` (around line 14), after the `character-manage-roles` div (line 34) and before `character-manage-actions` (line 35), insert:

```html
<div class="character-manage-account">
    <label class="account-label">Account:</label>
    <select onchange="assignCharacterAccount({{ char.id }}, this)">
        <option value="" {% if not char.account_id %}selected{% endif %}>— Unassigned —</option>
        {% for acc in accounts %}
            <option value="{{ acc.id }}" {% if char.account_id == acc.id %}selected{% endif %}>{{ acc.name }}</option>
        {% endfor %}
    </select>
</div>
```

**Step 3: Add CSS for the dropdown**

Append to `static/style.css`:

```css
.character-manage-account {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.25rem;
}

.character-manage-account .account-label {
    font-size: 0.85rem;
    color: var(--color-text-secondary);
}

.character-manage-account select {
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--color-border-input);
    border-radius: 4px;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
    font-size: 0.85rem;
}
```

**Step 4: Smoke test**

Run `python app.py`, visit `/settings`. Verify:
- Create account named "TestAcc" with subscription Omega → page reloads, account appears.
- Edit name inline → no error, refresh page, name persists.
- Change subscription dropdown → persists.
- Edit notes → persists.
- On a character row, change the Account dropdown → no error, refresh, value persists.
- Delete account with 0 chars → confirm dialog → account removed.
- Delete account with 1 char → confirm dialog wording says "Move 1 character to Unassigned and delete this account?" → char's dropdown reverts to Unassigned on next reload.

Ctrl+C to stop.

**Step 5: Commit**

```powershell
git add templates/settings.html static/style.css
git commit -m "Wire up account CRUD JS and per-character account dropdown in settings"
```

---

## Task 12: Dashboard — view toggle UI + CSS

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `static/style.css`

**Step 1: Add toggle markup to the dashboard header**

In `templates/dashboard.html`, after the `<div class="search-bar">` closing tag (line 18) and before `<div class="refresh-indicator">` (line 19), insert:

```html
<div class="view-toggle" id="viewToggle" role="group" aria-label="View mode">
    <button class="view-toggle-btn active" data-view="grouped" type="button">Grouped</button>
    <button class="view-toggle-btn" data-view="loose" type="button">Loose</button>
</div>
```

**Step 2: Add account filter row markup**

Immediately after the existing `<div class="role-filters">` block closes (around line 14), insert:

```html
<div class="account-filters" id="accountFilters">
    <button class="account-chip filter-chip active" data-account-filter="all" type="button">All</button>
    <button class="account-chip filter-chip" data-account-filter="unassigned" type="button">Unassigned</button>
    {# Account-specific chips are injected by JS once /api/locations is fetched #}
</div>
```

**Step 3: Add CSS for toggle, account chips, grouped headers, and per-card account chip**

Append to `static/style.css`:

```css
/* View toggle */
.view-toggle {
    display: inline-flex;
    border: 1px solid var(--color-border-primary);
    border-radius: 6px;
    overflow: hidden;
}
.view-toggle-btn {
    padding: 0.4rem 0.8rem;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
    border: 0;
    cursor: pointer;
    font-size: 0.85rem;
}
.view-toggle-btn.active {
    background: var(--color-btn-primary);
    color: white;
}

/* Account filter chips */
.account-filters {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}
.account-chip.filter-chip {
    padding: 0.3rem 0.7rem;
    border-radius: 12px;
    border: 1px solid var(--color-border-primary);
    background: var(--color-bg-chip);
    color: var(--color-text-primary);
    cursor: pointer;
    font-size: 0.8rem;
}
.account-chip.filter-chip.active {
    background: var(--color-btn-primary);
    color: white;
    border-color: var(--color-btn-primary);
}

/* Grouped view */
.account-group {
    margin-bottom: 1.5rem;
}
.account-group-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.4rem 0;
    margin-bottom: 0.5rem;
    border-bottom: 1px solid var(--color-border-primary);
    cursor: pointer;
    user-select: none;
}
.account-group-header h2 {
    margin: 0;
    font-size: 1.1rem;
    color: var(--color-text-heading);
}
.account-group-header .group-count {
    color: var(--color-text-secondary);
    font-size: 0.85rem;
}
.account-group-header .group-toggle-arrow {
    color: var(--color-text-secondary);
    transition: transform 0.15s ease;
}
.account-group.collapsed .group-toggle-arrow {
    transform: rotate(-90deg);
}
.account-group.collapsed .character-grid {
    display: none;
}

/* Subscription badge */
.sub-badge {
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
}
.sub-badge.omega {
    background: #f5c542;
    color: #5a4400;
}
.sub-badge.alpha {
    background: #d0d0d0;
    color: #444;
}

/* Per-card account chip */
.card-account {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.3rem;
    margin-top: 0.25rem;
    padding-top: 0.25rem;
    border-top: 1px dashed var(--color-border-divider);
    font-size: 0.75rem;
    color: var(--color-text-secondary);
}
```

**Step 4: Smoke test**

Run `python app.py`, visit `/`. Expected:
- Toggle buttons appear in the header.
- Account filter chips appear (only "All" and "Unassigned" visible until JS injects more in the next task).
- No layout breakage. Existing cards still render.
- Ctrl+C to stop.

**Step 5: Commit**

```powershell
git add templates/dashboard.html static/style.css
git commit -m "Add dashboard view toggle + account filter scaffolding (CSS + HTML)"
```

---

## Task 13: Dashboard — JS for grouped/loose render + filters

**Why:** Bring the dashboard live with view toggle, account filter, account chips on cards, and group-by-account rendering.

**Files:**
- Modify: `templates/dashboard.html`

**Step 1: Replace `updateCharacterDisplay()` and `applyFilters()` in the dashboard script**

Find `updateCharacterDisplay(characters)` (line 153). Replace from that function through the end of `applyFilters()` (line 275) with the block below. Also add helpers above and a `currentView` global beside the existing `searchTerm`.

Near the top of the script (after the `let searchTerm = '';` line, around line 118), insert:

```javascript
let currentView = localStorage.getItem('dashboardView') || 'grouped';
let activeAccountFilter = 'all';  // 'all' | 'unassigned' | <accountId as string>
let cachedCharacters = [];
```

Replace `updateCharacterDisplay` and `applyFilters` with:

```javascript
function renderCardHTML(char) {
    return `
        <div class="character-card"
             data-online="${char.online}"
             data-roles="${char.roles.join(',')}"
             data-name="${char.name}"
             data-system="${char.system}"
             data-ship="${char.ship}"
             data-account-id="${char.account_id ?? ''}"
             data-account-name="${char.account_name ?? ''}">
            <div class="card-header">
                <div class="character-portrait">
                    <img src="${char.portrait_url}" alt="${char.name}" class="portrait-img">
                    ${char.corporation_id ? `
                        <img src="https://images.evetech.net/corporations/${char.corporation_id}/logo?size=32"
                             alt="Corp" class="corp-logo">
                    ` : ''}
                    <div class="status-indicator ${char.online ? 'online' : 'offline'}"></div>
                </div>
                <h3 class="character-name">${char.name}</h3>
            </div>
            <div class="card-details">
                <div class="card-detail">
                    <span class="detail-label">Location</span>
                    <a href="https://evemaps.dotlan.net/system/${char.system}"
                       target="_blank" class="system-link">${char.system}</a>
                </div>
                <div class="card-detail">
                    <span class="detail-label">Ship</span>
                    <span>${char.ship}</span>
                </div>
            </div>
            ${char.roles.length ? `
                <div class="card-roles">
                    ${char.roles.map(r => `<span class="role-chip">${r}</span>`).join('')}
                </div>
            ` : ''}
            ${char.account_name ? `
                <div class="card-account">
                    📛 ${char.account_name}${char.account_subscription === 'omega' ? ' · Ω'
                                              : char.account_subscription === 'alpha' ? ' · α' : ''}
                </div>
            ` : ''}
            ${char.last_updated ? `
                <div class="card-timestamp" data-updated="${char.last_updated}">
                    Updated ${relativeTime(char.last_updated)}
                </div>
            ` : ''}
        </div>
    `;
}

function subBadgeHTML(sub) {
    if (sub === 'omega') return '<span class="sub-badge omega">Omega</span>';
    if (sub === 'alpha') return '<span class="sub-badge alpha">Alpha</span>';
    return '';
}

function groupByAccount(characters) {
    const groups = new Map();  // key: accountId-or-'unassigned' → { name, subscription, chars }
    for (const c of characters) {
        const key = c.account_id ?? 'unassigned';
        if (!groups.has(key)) {
            groups.set(key, {
                key: String(key),
                name: c.account_name || 'Unassigned',
                subscription: c.account_subscription || null,
                chars: [],
            });
        }
        groups.get(key).chars.push(c);
    }
    const ordered = [...groups.values()].sort((a, b) => {
        if (a.key === 'unassigned') return 1;
        if (b.key === 'unassigned') return -1;
        return a.name.localeCompare(b.name);
    });
    return ordered;
}

function renderGrouped(characters) {
    const groups = groupByAccount(characters);
    return groups.map(g => {
        const collapsedKey = `groupCollapsed:${g.key}`;
        const isCollapsed = localStorage.getItem(collapsedKey) === '1';
        return `
            <div class="account-group ${isCollapsed ? 'collapsed' : ''}" data-group-key="${g.key}">
                <div class="account-group-header">
                    <span class="group-toggle-arrow">▾</span>
                    <h2>${g.name}</h2>
                    ${subBadgeHTML(g.subscription)}
                    <span class="group-count">· ${g.chars.length} char${g.chars.length === 1 ? '' : 's'}</span>
                </div>
                <div class="character-grid">
                    ${g.chars.map(renderCardHTML).join('')}
                </div>
            </div>
        `;
    }).join('');
}

function renderLoose(characters) {
    return `<div class="character-grid">${characters.map(renderCardHTML).join('')}</div>`;
}

function rebuildAccountFilterChips(characters) {
    const seen = new Map();
    for (const c of characters) {
        if (c.account_id && !seen.has(c.account_id)) {
            seen.set(c.account_id, c.account_name);
        }
    }
    const container = document.getElementById('accountFilters');
    if (!container) return;
    // Keep "All" and "Unassigned"; rebuild the rest
    const fixed = container.querySelectorAll('[data-account-filter="all"], [data-account-filter="unassigned"]');
    container.innerHTML = '';
    fixed.forEach(b => container.appendChild(b));
    for (const [id, name] of seen) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'account-chip filter-chip';
        btn.dataset.accountFilter = String(id);
        btn.textContent = name;
        if (String(id) === activeAccountFilter) btn.classList.add('active');
        container.appendChild(btn);
    }
}

function updateCharacterDisplay(characters) {
    cachedCharacters = characters;
    characters.sort((a, b) => {
        if (a.online !== b.online) return b.online - a.online;
        return a.name.localeCompare(b.name);
    });

    const container = document.getElementById('characterList');
    if (characters.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>No characters added yet.</p>
                <p><a href="/settings">Add a character</a> to get started.</p>
            </div>
        `;
        return;
    }

    rebuildAccountFilterChips(characters);
    container.innerHTML = currentView === 'grouped' ? renderGrouped(characters) : renderLoose(characters);
    applyFilters();
}

function applyFilters() {
    const cards = document.querySelectorAll('.character-card');
    const term = searchTerm.toLowerCase();
    let visible = 0;
    const total = cards.length;
    const isFiltering = term || activeRoles.size > 0 || activeAccountFilter !== 'all';

    cards.forEach(card => {
        // Role filter
        let roleMatch = true;
        if (activeRoles.size > 0) {
            const cardRoles = card.dataset.roles.split(',').filter(r => r);
            roleMatch = cardRoles.some(r => activeRoles.has(r));
        }
        // Account filter
        let accountMatch = true;
        if (activeAccountFilter === 'unassigned') {
            accountMatch = !card.dataset.accountId;
        } else if (activeAccountFilter !== 'all') {
            accountMatch = card.dataset.accountId === activeAccountFilter;
        }
        // Search filter
        let searchMatch = true;
        if (term) {
            const name = (card.dataset.name || '').toLowerCase();
            const system = (card.dataset.system || '').toLowerCase();
            const ship = (card.dataset.ship || '').toLowerCase();
            const roles = (card.dataset.roles || '').toLowerCase();
            const account = (card.dataset.accountName || '').toLowerCase();
            searchMatch = name.includes(term) || system.includes(term) || ship.includes(term)
                       || roles.includes(term) || account.includes(term);
        }
        const show = roleMatch && accountMatch && searchMatch;
        card.style.display = show ? '' : 'none';
        if (show) visible++;
    });

    // In grouped view, hide empty groups
    document.querySelectorAll('.account-group').forEach(group => {
        const anyVisible = [...group.querySelectorAll('.character-card')]
            .some(c => c.style.display !== 'none');
        group.style.display = anyVisible ? '' : 'none';
    });

    const statusEl = document.getElementById('searchStatus');
    if (statusEl) statusEl.textContent = isFiltering ? `Showing ${visible} of ${total} characters` : '';

    const noResultsEl = document.getElementById('noResults');
    if (noResultsEl) noResultsEl.style.display = (isFiltering && visible === 0) ? '' : 'none';
}
```

**Step 2: Wire up the view toggle and account filter handlers**

Append (near the other click handlers, around line 327):

```javascript
// View toggle
document.getElementById('viewToggle')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.view-toggle-btn');
    if (!btn) return;
    currentView = btn.dataset.view;
    localStorage.setItem('dashboardView', currentView);
    document.querySelectorAll('.view-toggle-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.view === currentView);
    });
    if (cachedCharacters.length) updateCharacterDisplay(cachedCharacters);
});

// Account filter chips
document.getElementById('accountFilters')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.account-chip');
    if (!btn) return;
    activeAccountFilter = btn.dataset.accountFilter;
    document.querySelectorAll('#accountFilters .account-chip').forEach(b => {
        b.classList.toggle('active', b.dataset.accountFilter === activeAccountFilter);
    });
    applyFilters();
});

// Group header collapse
document.getElementById('characterList')?.addEventListener('click', (e) => {
    const header = e.target.closest('.account-group-header');
    if (!header) return;
    const group = header.parentElement;
    const key = group.dataset.groupKey;
    const nowCollapsed = !group.classList.contains('collapsed');
    group.classList.toggle('collapsed', nowCollapsed);
    localStorage.setItem(`groupCollapsed:${key}`, nowCollapsed ? '1' : '0');
});

// Sync initial toggle button state
document.querySelectorAll('.view-toggle-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.view === currentView);
});

// Trigger an immediate fetch so the initial render uses the chosen view
updateCharacters();
```

**Step 3: Smoke test**

Run `python app.py`, visit `/`. Verify:
- Page loads, shows characters either grouped or flat depending on `localStorage.dashboardView`.
- Click "Loose" → flat grid; account filter chips become useful.
- Click "Grouped" → headers appear with account names + subscription badges.
- Click an account chip → only those characters show.
- Search "Main" (your account name) → matches characters by account.
- Collapse a group header → grid hides; persists on reload.
- Existing role chips still work and combine AND-style with account filter and search.

Ctrl+C to stop.

**Step 4: Commit**

```powershell
git add templates/dashboard.html
git commit -m "Wire dashboard view toggle, account filter, grouped render, and chip on cards"
```

---

## Task 14: Update Jinja initial server-side render

**Why:** Currently the dashboard renders a static character list server-side. The new JS replaces the DOM on first `updateCharacters()` call (we added that to Task 13 step 2), so the server-side render is now mostly a flash-of-content. Keep it simple: the JS handles everything; the Jinja fallback only needs to render an empty state and let JS take over.

**Files:**
- Modify: `templates/dashboard.html`

**Step 1: Simplify the Jinja loop**

In `templates/dashboard.html`, replace the entire `<div class="character-grid" id="characterList">...</div>` block (lines 24-89) with:

```html
<div id="characterList">
    {% if not characters %}
    <div class="empty-state">
        <p>No characters added yet.</p>
        <p><a href="{{ url_for('settings') }}">Add a character</a> to get started.</p>
    </div>
    {% endif %}
</div>
```

**Step 2: Smoke test**

Run `python app.py`. Visit `/`. Expected:
- Brief empty area, then JS populates the grid/groups immediately.
- No regression in any feature.

Ctrl+C to stop.

**Step 3: Commit**

```powershell
git add templates/dashboard.html
git commit -m "Let JS own dashboard rendering; Jinja only renders empty state"
```

---

## Task 15: Backup live DB and verify migration on real data

**Why:** Tests prove the migration works on a synthetic legacy DB. We still need to verify it on the user's actual `tracker.db` before merging.

**Step 1: Back up the live DB**

```powershell
Copy-Item tracker.db tracker.db.bak-2026-05-23
```

**Step 2: Run the app to trigger migration**

```powershell
python app.py
```

Expected: no errors in console. Visit `http://localhost:5000/settings` and `http://localhost:5000/`.

**Step 3: Inspect the schema**

In a separate terminal:
```powershell
python -c "import sqlite3; c=sqlite3.connect('tracker.db'); print([r[1] for r in c.execute('PRAGMA table_info(characters)')]); print([r for r in c.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')])"
```

Expected output includes `'account_id'` in the characters columns and `'accounts'` in the table list.

**Step 4: Sanity check existing characters**

Verify all pre-existing characters still show on the dashboard (Unassigned group / no account chip). No data loss.

**Step 5: Commit (if any incidental fixes were needed)**

If the migration ran cleanly with no changes, nothing to commit here — proceed to Task 16. If anything broke and you had to patch, commit those fixes now.

---

## Task 16: Update CONTEXT.md feature backlog

**Files:**
- Modify: `CONTEXT.md`

**Step 1: Add an entry to the Feature Backlog**

Open `CONTEXT.md` and find the `## Feature Backlog` section. Add a new sub-section just after the "Completed Quick Wins" block:

```markdown
### Completed (Session 4 — 2026-05-23)
- ~~Organize characters by account (first-class `Account` entity, view toggle, account filter)~~ ✅
```

Also update the **Database Models** section to mention:
```markdown
- **Account**: First-class entity (name, subscription, notes). Nullable FK from Character (ON DELETE SET NULL).
```

And under **All Routes**, add the new rows:

| Route | Method | Purpose |
|---|---|---|
| `/api/accounts` | GET | List accounts |
| `/api/accounts` | POST | Create account |
| `/api/accounts/<id>` | PATCH | Update account |
| `/api/accounts/<id>` | DELETE | Delete account (chars become unassigned) |
| `/api/characters/<id>/account` | PUT | Assign character to account |

Update **Last Updated** at the bottom to `2026-05-23`.

**Step 2: Final smoke test (full flow)**

Run `python app.py` once more and walk the whole feature end-to-end:
1. Create 2 accounts ("Main" omega, "Alt" alpha).
2. Assign chars to each, leave one unassigned.
3. Dashboard: toggle Grouped → see groups; collapse one; refresh page → stays collapsed.
4. Dashboard: toggle Loose → see chips, click "Alt" → filters down.
5. Search by account name → matches.
6. Edit account name → reflects after next 60s poll (or hard refresh).
7. Delete an account with chars → confirm dialog correct → chars move to Unassigned.
8. `pytest tests/ -v` → all pass.

**Step 3: Commit**

```powershell
git add CONTEXT.md
git commit -m "Document Account feature in CONTEXT.md backlog and routes table"
```

**Step 4: Mark backlog task #1 done in TaskList; the next item ("Fix character deletion bug") is now the active backlog task.**

---

## Done. Summary of changes

- **Schema:** new `accounts` table; `characters.account_id` FK with `ON DELETE SET NULL`; SQLite FK enforcement enabled.
- **API:** 5 new endpoints + 1 modified (`/api/locations`) + settings route extended.
- **UI — Settings:** Accounts management section; per-character account dropdown.
- **UI — Dashboard:** Grouped/Loose view toggle (persisted); account filter chip row; per-card account chip; collapsible group headers (persisted); account name searchable.
- **Tests:** `tests/test_models.py`, `tests/test_accounts_api.py` covering models, migration, and full API surface.

## Notes for the executor

- **Commit cadence:** one commit per task (each labeled in the steps). Don't squash.
- **If a test fails unexpectedly:** stop and ask — don't paper over with a code change that "makes the test pass" unless you understand why it was wrong.
- **Smoke tests:** include manual click-throughs even when pytest is green — JS isn't covered by tests.
- **Working directory:** all commands assume the project root.
- **Electron testing:** changes only affect the Flask layer + templates/static. `npm start` should work identically once `python app.py` works.
