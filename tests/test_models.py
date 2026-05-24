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
