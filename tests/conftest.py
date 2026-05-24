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
