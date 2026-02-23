import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration loaded from environment variables."""

    # Flask settings
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

    # EVE SSO settings
    EVE_CLIENT_ID = os.getenv('EVE_CLIENT_ID')
    EVE_CLIENT_SECRET = os.getenv('EVE_CLIENT_SECRET')
    EVE_CALLBACK_URL = os.getenv('EVE_CALLBACK_URL', 'http://localhost:5000/callback')

    # Database settings
    DATABASE_PATH = 'tracker.db'
    SDE_DATABASE_PATH = 'sde.sqlite.db'

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
