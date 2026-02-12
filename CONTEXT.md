# EVE Character Tracker - Development Context

## Project Overview

This is a local Flask web application that tracks EVE Online characters in real-time. It shows character locations, ships, online status, and includes a fit checker to determine which characters can fly specific ship fittings.

**Tech Stack:**
- **Backend**: Python 3.13, Flask, SQLAlchemy
- **Authentication**: EVE Online SSO via Preston library
- **Database**: SQLite (local)
- **Frontend**: Jinja2 templates, vanilla JavaScript
- **EVE API**: ESI (EVE Swagger Interface) via Preston

## Recent Work Session (Feb 11, 2026)

### Initial Problem

The application was completely non-functional due to authentication failures. Users could not add characters, making the entire tracker unusable.

**Error**: `KeyError: 'CharacterID'` when attempting to authenticate with EVE Online SSO.

### Root Cause Analysis

The original code assumed Preston's `whoami()` method would return character information with keys like `CharacterID` and `CharacterName` (capitalized). However:

1. **Preston's `whoami()` was returning an empty dictionary `{}`** - The method was failing silently
2. **Preston API changes** - The library's authentication flow had changed:
   - `preston.authenticate(code)` returns a **Preston object**, not a dictionary
   - Access tokens are **object attributes**, not dictionary keys
   - The `use_refresh_token()` method doesn't exist anymore

### Solutions Implemented

#### 1. JWT Token Decoding ([auth.py](auth.py))

**Problem**: Preston's `whoami()` unreliable and returning empty data.

**Solution**: Implemented direct JWT token decoding:
```python
def decode_jwt_payload(token):
    """Decode JWT access token to extract character info."""
    # Decodes the middle part of JWT (header.payload.signature)
    # Returns dict with 'sub', 'name', 'exp', etc.
```

**Character Info Extraction**:
- `character_id`: Extracted from `sub` claim (format: `"CHARACTER:EVE:123456"`)
- `character_name`: Extracted from `name` claim
- `token_expiry`: Extracted from `exp` claim (Unix timestamp)

#### 2. Fixed Preston API Usage ([auth.py](auth.py))

**Updated `authenticate()` function**:
```python
# OLD (broken):
auth_result = preston.authenticate(code)
access_token = auth_result['access_token']  # TypeError!

# NEW (working):
auth_preston = preston.authenticate(code)
access_token = auth_preston.access_token  # Attribute access
refresh_token = auth_preston.refresh_token
```

**Updated `refresh_access_token()` function**:
```python
# OLD (broken):
preston.use_refresh_token(refresh_token)  # AttributeError!
auth_result = preston.refresh()

# NEW (working):
auth_preston = preston.authenticate_from_token(refresh_token)
new_access_token = auth_preston.access_token
```

#### 3. Fixed Database Session Issues ([app.py](app.py))

**Problem**: `DetachedInstanceError` when templates tried to access character roles after session was closed.

**Solution**: Eagerly load relationships before closing session:
```python
from sqlalchemy.orm import selectinload

# In dashboard() and settings() routes:
characters = db_session.query(Character).options(
    selectinload(Character.roles)
).all()
```

#### 4. Improved Error Handling ([app.py](app.py))

Added specific exception handling for better debugging:
```python
except ValueError as e:
    # Character info extraction failed
    flash('Authentication failed: Could not read character information.', 'error')
except Exception as e:
    # General errors
    flash('Authentication failed. Please try again.', 'error')
```

### Files Modified

1. **[auth.py](auth.py)** - Core authentication logic
   - Added `decode_jwt_payload()` function
   - Rewrote `authenticate()` to use Preston objects correctly
   - Fixed `refresh_access_token()` to use `authenticate_from_token()`
   - Added proper JWT expiry handling

2. **[app.py](app.py)** - Web application routes
   - Added `from sqlalchemy.orm import selectinload`
   - Fixed `dashboard()` route with eager loading
   - Fixed `settings()` route with eager loading
   - Improved error handling in `/callback` route

### Current State

✅ **Fully Functional**

- Characters can be added via EVE SSO authentication
- Dashboard displays characters with real-time data
- Settings page shows characters and roles
- Token refresh works automatically (background polling every 60s)
- Fit checker ready to use (requires EVE SDE database)

### Test Character Added

- **Name**: Sihcom Repinuj
- **Status**: Active and tracking
- Successfully authenticated and stored in database

## Environment Setup

### Required Configuration

**.env file** (already configured):
```env
EVE_CLIENT_ID=<your_client_id>
EVE_CLIENT_SECRET=<your_client_secret>
FLASK_SECRET_KEY=<your_secret_key>
EVE_CALLBACK_URL=http://localhost:5000/callback
```

### EVE Developer Application

Registered at https://developers.eveonline.com/ with:
- **Callback URL**: `http://localhost:5000/callback` (must match exactly)
- **Scopes**:
  - `esi-location.read_location.v1`
  - `esi-location.read_online.v1`
  - `esi-location.read_ship_type.v1`
  - `esi-skills.read_skills.v1`

### External Dependencies

1. **Python Packages** (installed via pip):
   - flask
   - preston
   - aiohttp
   - sqlalchemy
   - python-dotenv

2. **EVE SDE Database**:
   - File: `sde.sqlite` (already downloaded from Fuzzwork)
   - Contains: Item types and skill requirements
   - Used by: Fit checker functionality

### Running the Application

```bash
python app.py
```

Application runs on http://localhost:5000

## Architecture Notes

### Database Models ([models.py](models.py))

- **Character**: Stores character ID, name, tokens, and expiry
- **Role**: Custom tags for characters (Capital, Cyno, Scout, etc.)
- **LocationCache**: Cached character location/ship/online status
- **CharacterSkill**: Cached skill data for fit checking
- **SavedFit**: Stored EFT format fits

### Background Polling ([poller.py](poller.py))

- Runs in separate thread
- Polls ESI every 60 seconds for:
  - Character location
  - Ship type
  - Online status
- Automatically refreshes expired tokens
- Updates cached data in database

### Skill Checking ([skill_checker.py](skill_checker.py))

- Parses EFT format fits
- Queries SDE for skill requirements
- Cross-references with character skills
- Returns detailed results with missing skills

## Known Issues & Limitations

### None Currently!

All major issues have been resolved. The application is stable and functional.

## Potential Next Steps

### Features to Add

1. **Character Management**
   - Bulk character import/export
   - Character grouping beyond roles
   - Character notes/descriptions
   - Archive/hide inactive characters

2. **Location Tracking Enhancements**
   - Location history tracking
   - Movement alerts/notifications
   - Jump range calculator
   - Dotlan route planning integration

3. **Fit Checker Improvements**
   - Import fits from EVE clipboard
   - Save/organize fit categories
   - Compare fits side-by-side
   - Generate skill training plans
   - Export missing skills queue

4. **Dashboard Enhancements**
   - Customizable columns
   - Advanced filtering (by region, system, security status)
   - Map view of character locations
   - Corporation/Alliance grouping
   - Activity timeline

5. **Skills & Training**
   - Skill queue monitoring
   - Training time estimates
   - Skill plan recommendations
   - Implant tracking

6. **Alerts & Notifications**
   - Character goes online/offline
   - Character enters specific system/region
   - Skill training completes
   - Token expiration warnings
   - Desktop notifications

7. **Data Export**
   - CSV export of character data
   - Location history reports
   - Skill comparison matrices
   - Fit compatibility reports

### Technical Improvements

1. **Error Handling & Logging**
   - More granular error messages
   - Log rotation and management
   - User-friendly error pages
   - Retry logic for ESI failures

2. **Performance Optimization**
   - Database indexing review
   - Caching strategy improvements
   - Async ESI calls (already using aiohttp)
   - Reduce polling frequency options

3. **Security Enhancements**
   - Encrypt tokens in database
   - Session timeout management
   - Rate limiting
   - CSRF protection
   - Content Security Policy headers

4. **UI/UX Improvements**
   - Responsive design for mobile
   - Dark mode theme
   - Better loading states
   - Toast notifications instead of flash messages
   - Character portrait images
   - Ship type icons

5. **Testing & Quality**
   - Unit tests for auth flow
   - Integration tests for routes
   - Test coverage for skill checker
   - Mock ESI responses for testing

6. **Deployment & Operations**
   - Docker containerization
   - Configuration management
   - Health check endpoint
   - Monitoring and metrics
   - Backup strategy

### Code Quality

1. **Refactoring Opportunities**
   - Extract ESI client into separate module
   - Standardize error handling patterns
   - Add type hints throughout
   - Create service layer for business logic

2. **Documentation**
   - API endpoint documentation
   - Code comments for complex logic
   - Architecture diagrams
   - User guide/tutorial

3. **Configuration**
   - Move hardcoded values to config
   - Environment-specific settings (dev/prod)
   - Feature flags system

## Troubleshooting Guide

### Authentication Issues

**Symptom**: "Authentication failed" message

**Checks**:
1. Verify `.env` file exists and has correct values
2. Check EVE Developer portal callback URL matches exactly
3. Ensure scopes are configured correctly
4. Check console logs for specific errors

**Solution**: The JWT decoding approach should handle most auth issues automatically.

### Database Issues

**Symptom**: DetachedInstanceError

**Solution**: Ensure all routes use `selectinload()` for relationships accessed in templates.

**Symptom**: Database locked errors

**Solution**: Check that sessions are properly closed in all routes.

### Token Refresh Issues

**Symptom**: Characters showing as offline or not updating

**Checks**:
1. Check background poller is running (console logs)
2. Verify token expiry dates in database
3. Check for errors in poller thread

**Solution**: The `refresh_access_token()` function now correctly uses `authenticate_from_token()`.

### SDE Database Issues

**Symptom**: "Could not determine skill requirements"

**Checks**:
1. Verify `sde.sqlite` file exists in project root
2. Check file is not corrupted (try opening with SQLite browser)
3. Verify tables `invTypes` and `dgmTypeAttributes` exist

**Solution**: Re-download SDE from Fuzzwork if corrupted.

## Development Environment

- **Python Version**: 3.13
- **OS**: Windows 11 Home 10.0.26100
- **IDE**: VSCode with Claude Code extension
- **Database**: SQLite (local file `tracker.db`)

## Important Notes

1. **Never commit `.env` or `tracker.db`** - These contain sensitive data
2. **SDE updates** - EVE releases new SDE periodically; may need to update `sde.sqlite`
3. **Preston library** - Community-maintained; watch for breaking changes
4. **ESI versioning** - EVE may deprecate API versions; monitor ESI announcements
5. **Token security** - Tokens stored in plaintext in DB; consider encryption for production use

## Resources

- **Preston Library**: https://github.com/Celeo/preston
- **EVE ESI Documentation**: https://esi.evetech.net/
- **EVE Developers**: https://developers.eveonline.com/
- **Fuzzwork SDE**: https://www.fuzzwork.co.uk/dump/latest/
- **DOTLAN Maps**: https://evemaps.dotlan.net/

## Questions for Next Session

When continuing development, consider:

1. What features are highest priority?
2. Should we add a web-based admin panel?
3. Is multi-user support needed, or single-user only?
4. Should we add export/backup functionality?
5. Any specific EVE gameplay features to integrate (market, industry, etc.)?

---

**Last Updated**: February 11, 2026
**Status**: ✅ Fully Functional
**Next Session**: Ready for feature development or enhancements
