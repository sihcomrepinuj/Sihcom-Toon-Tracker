import os
import sys
from dotenv import load_dotenv

load_dotenv()

# When frozen by PyInstaller, resolve paths relative to the exe's directory.
# In dev, use the repo root (where this file lives).
_exe_dir = (
    os.path.dirname(sys.executable)
    if getattr(sys, 'frozen', False)
    else os.path.dirname(os.path.abspath(__file__))
)

class Config:
    """Application configuration loaded from environment variables."""

    # Flask settings
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

    # EVE SSO settings
    EVE_CLIENT_ID = os.getenv('EVE_CLIENT_ID')
    EVE_CLIENT_SECRET = os.getenv('EVE_CLIENT_SECRET')

    # Background service port — must match the EVE developer portal callback URL.
    SERVICE_PORT = int(os.getenv('SERVICE_PORT', '5000'))

    EVE_CALLBACK_URL = os.getenv(
        'EVE_CALLBACK_URL',
        f'http://localhost:{int(os.getenv("SERVICE_PORT", "5000"))}/callback',
    )

    # Database settings — absolute paths so they work from any working directory.
    DATABASE_PATH = os.getenv('DATABASE_PATH', os.path.join(_exe_dir, 'tracker.db'))
    SDE_DATABASE_PATH = os.getenv('SDE_DATABASE_PATH', os.path.join(_exe_dir, 'sde.sqlite.db'))
    # Database settings
    DATABASE_PATH = 'tracker.db'
    # SDE built from CCP's official YAML export via setup_sde.py
    # (tools/eve-sde-converter). Run `python setup_sde.py` to create it.
    SDE_DATABASE_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'data', 'sqlite-latest.sqlite'
    )

    # OAuth scopes required
    EVE_SCOPES = [
        'esi-location.read_location.v1',
        'esi-location.read_online.v1',
        'esi-location.read_ship_type.v1',
        'esi-skills.read_skills.v1'
    ]

    # Poller settings
    LOCATION_POLL_INTERVAL = 60  # seconds
    SKILLS_POLL_INTERVAL = 86400  # 24 hours in seconds

    @classmethod
    def validate(cls):
        """Validate that required configuration is present."""
        if not cls.EVE_CLIENT_ID:
            raise ValueError("EVE_CLIENT_ID not set in environment")
        if not cls.EVE_CLIENT_SECRET:
            raise ValueError("EVE_CLIENT_SECRET not set in environment")
