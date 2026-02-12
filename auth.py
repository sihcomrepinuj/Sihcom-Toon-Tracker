from preston import Preston
from config import Config
from datetime import datetime, timedelta
import logging
import base64
import json

logger = logging.getLogger(__name__)

# Initialize Preston with EVE SSO credentials
preston = None


def init_preston():
    """Initialize the Preston OAuth client."""
    global preston
    preston = Preston(
        client_id=Config.EVE_CLIENT_ID,
        client_secret=Config.EVE_CLIENT_SECRET,
        callback_url=Config.EVE_CALLBACK_URL,
        scope=' '.join(Config.EVE_SCOPES)
    )
    return preston


def decode_jwt_payload(token):
    """
    Decode JWT token payload without verification (for character info extraction).

    Args:
        token: JWT access token string

    Returns:
        dict: Decoded payload containing character info
    """
    try:
        # JWT tokens have 3 parts separated by dots: header.payload.signature
        # We only need the payload (middle part)
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT token format")

        # Decode the payload (add padding if needed)
        payload = parts[1]
        # Add padding if needed (JWT base64 may not be padded)
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"Failed to decode JWT token: {e}")
        return {}


def get_authorization_url():
    """Get the EVE SSO authorization URL for user login."""
    if preston is None:
        init_preston()
    return preston.get_authorize_url()


def authenticate(code):
    """
    Exchange authorization code for tokens and character info.

    Args:
        code: Authorization code from EVE SSO callback

    Returns:
        dict: Contains character_id, character_name, access_token, refresh_token, expires_in
    """
    if preston is None:
        init_preston()

    # Exchange code for tokens
    # Preston.authenticate() returns a new authenticated Preston instance
    auth_preston = preston.authenticate(code)

    # Get tokens from the Preston object attributes
    access_token = auth_preston.access_token
    refresh_token = auth_preston.refresh_token

    # Decode JWT token directly to get character info and expiry
    # Preston's whoami() can fail silently, so we decode the token ourselves
    token_payload = decode_jwt_payload(access_token)

    # Extract character info from JWT claims
    # EVE SSO JWT tokens use 'sub' for character ID (format: "CHARACTER:EVE:12345")
    # and 'name' for character name
    character_id = None
    character_name = None

    # Try to extract from 'sub' claim (standard EVE SSO format)
    if 'sub' in token_payload:
        # Format is "CHARACTER:EVE:12345" - extract the ID
        sub_parts = token_payload['sub'].split(':')
        if len(sub_parts) >= 3:
            character_id = int(sub_parts[2])

    # Try to get character name from various possible fields
    character_name = (
        token_payload.get('name') or
        token_payload.get('character_name') or
        token_payload.get('CharacterName')
    )

    if not character_id or not character_name:
        logger.error(f"Could not extract character info from JWT payload: {token_payload}")
        raise ValueError(f"Invalid JWT payload. Keys available: {list(token_payload.keys())}")

    # Get expiry from JWT token
    expires_in = token_payload.get('exp', 0) - int(datetime.utcnow().timestamp())
    token_expiry = datetime.fromtimestamp(token_payload.get('exp', 0)) if 'exp' in token_payload else datetime.utcnow() + timedelta(seconds=1200)

    return {
        'character_id': int(character_id) if isinstance(character_id, str) else character_id,
        'character_name': character_name,
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': max(expires_in, 0),
        'token_expiry': token_expiry
    }


def refresh_access_token(refresh_token):
    """
    Refresh an access token using a refresh token.

    Args:
        refresh_token: The refresh token to use

    Returns:
        dict: Contains new access_token, refresh_token, expires_in, token_expiry
    """
    if preston is None:
        init_preston()

    # Use Preston's authenticate_from_token to get a new authenticated instance
    auth_preston = preston.authenticate_from_token(refresh_token)

    # Get the new tokens from the authenticated Preston instance
    new_access_token = auth_preston.access_token
    new_refresh_token = auth_preston.refresh_token

    # Decode JWT to get expiry
    token_payload = decode_jwt_payload(new_access_token)
    expires_in = token_payload.get('exp', 0) - int(datetime.utcnow().timestamp())
    token_expiry = datetime.fromtimestamp(token_payload.get('exp', 0)) if 'exp' in token_payload else datetime.utcnow() + timedelta(seconds=1200)

    return {
        'access_token': new_access_token,
        'refresh_token': new_refresh_token if new_refresh_token else refresh_token,
        'expires_in': max(expires_in, 0),
        'token_expiry': token_expiry
    }


def get_authenticated_preston(access_token):
    """
    Get a Preston instance authenticated with an access token.

    Args:
        access_token: The access token to use

    Returns:
        Preston instance ready to make ESI calls
    """
    if preston is None:
        init_preston()

    auth_preston = Preston(
        client_id=Config.EVE_CLIENT_ID,
        client_secret=Config.EVE_CLIENT_SECRET,
        callback_url=Config.EVE_CALLBACK_URL,
        scope=' '.join(Config.EVE_SCOPES)
    )
    auth_preston.access_token = access_token
    return auth_preston
