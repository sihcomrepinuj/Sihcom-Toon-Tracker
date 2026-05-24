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
