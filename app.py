from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from datetime import datetime
import asyncio
import logging
from sqlalchemy.orm import selectinload

from config import Config
from models import init_db, get_session, Character, Role, LocationCache, SavedFit, CharacterSkill
from auth import init_preston, get_authorization_url, authenticate
from poller import poller
from eft_parser import parse_eft_fit, extract_item_names
from skill_checker import skill_checker

# Initialize Flask app
app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# ROUTES - Pages
# ============================================================================

@app.route('/')
def dashboard():
    """Main dashboard showing all characters and their locations."""
    db_session = get_session()

    # Eagerly load the roles relationship to avoid DetachedInstanceError
    characters = db_session.query(Character).options(selectinload(Character.roles)).all()
    roles = db_session.query(Role).all()

    # Sort characters: online first, then alphabetical
    characters.sort(key=lambda c: (
        not (c.location and c.location.is_online),
        c.name.lower()
    ))

    db_session.close()

    return render_template('dashboard.html', characters=characters, roles=roles)


@app.route('/fits')
def fits():
    """Fit checker page."""
    db_session = get_session()
    saved_fits = db_session.query(SavedFit).order_by(SavedFit.saved_at.desc()).all()
    db_session.close()

    return render_template('fits.html', saved_fits=saved_fits)


@app.route('/settings')
def settings():
    """Settings page for character and role management."""
    db_session = get_session()

    # Eagerly load the roles relationship to avoid DetachedInstanceError
    characters = db_session.query(Character).options(selectinload(Character.roles)).all()
    roles = db_session.query(Role).all()

    db_session.close()

    return render_template('settings.html', characters=characters, roles=roles)


# ============================================================================
# ROUTES - OAuth
# ============================================================================

@app.route('/login')
def login():
    """Redirect to EVE SSO for authentication."""
    try:
        auth_url = get_authorization_url()
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"Error initiating login: {e}", exc_info=True)
        flash('Error initiating login. Check your EVE SSO configuration.', 'error')
        return redirect(url_for('settings'))


@app.route('/callback')
def callback():
    """OAuth callback from EVE SSO."""
    code = request.args.get('code')

    if not code:
        flash('Authentication failed: No authorization code received.', 'error')
        return redirect(url_for('settings'))

    try:
        # Authenticate and get character info
        auth_data = authenticate(code)

        # Save character to database
        db_session = get_session()

        character = db_session.query(Character).filter_by(id=auth_data['character_id']).first()

        if character:
            # Update existing character
            character.access_token = auth_data['access_token']
            character.refresh_token = auth_data['refresh_token']
            character.token_expiry = auth_data['token_expiry']
            flash(f"Character {character.name} updated successfully!", 'success')
        else:
            # Create new character
            character = Character(
                id=auth_data['character_id'],
                name=auth_data['character_name'],
                access_token=auth_data['access_token'],
                refresh_token=auth_data['refresh_token'],
                token_expiry=auth_data['token_expiry'],
                added_at=datetime.utcnow()
            )
            db_session.add(character)
            flash(f"Character {character.name} added successfully!", 'success')

        db_session.commit()
        db_session.close()

        return redirect(url_for('settings'))

    except ValueError as e:
        logger.error(f"Character info extraction failed: {e}", exc_info=True)
        flash('Authentication failed: Could not read character information.', 'error')
        return redirect(url_for('settings'))
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}", exc_info=True)
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('settings'))


# ============================================================================
# API ROUTES - Characters
# ============================================================================

@app.route('/api/locations')
def api_locations():
    """Get all character locations as JSON."""
    db_session = get_session()

    characters = db_session.query(Character).all()

    data = []
    for char in characters:
        location = char.location
        data.append({
            'id': char.id,
            'name': char.name,
            'system': location.solar_system_name if location else 'Unknown',
            'ship': location.ship_name if location else 'Unknown',
            'online': location.is_online if location else False,
            'roles': [role.name for role in char.roles],
            'portrait_url': f'https://images.evetech.net/characters/{char.id}/portrait?size=64'
        })

    db_session.close()

    return jsonify(data)


@app.route('/api/characters/<int:character_id>', methods=['DELETE'])
def api_delete_character(character_id):
    """Delete a character."""
    db_session = get_session()

    character = db_session.query(Character).filter_by(id=character_id).first()

    if not character:
        db_session.close()
        return jsonify({'success': False, 'error': 'Character not found'}), 404

    db_session.delete(character)
    db_session.commit()
    db_session.close()

    return jsonify({'success': True})


# ============================================================================
# API ROUTES - Roles
# ============================================================================

@app.route('/api/roles', methods=['POST'])
def api_create_role():
    """Create a new role."""
    data = request.json
    role_name = data.get('name', '').strip()

    if not role_name:
        return jsonify({'success': False, 'error': 'Role name is required'}), 400

    db_session = get_session()

    # Check if role already exists
    existing = db_session.query(Role).filter_by(name=role_name).first()
    if existing:
        db_session.close()
        return jsonify({'success': False, 'error': 'Role already exists'}), 400

    role = Role(name=role_name)
    db_session.add(role)
    db_session.commit()
    db_session.close()

    return jsonify({'success': True})


@app.route('/api/roles/<int:role_id>', methods=['DELETE'])
def api_delete_role(role_id):
    """Delete a role."""
    db_session = get_session()

    role = db_session.query(Role).filter_by(id=role_id).first()

    if not role:
        db_session.close()
        return jsonify({'success': False, 'error': 'Role not found'}), 404

    db_session.delete(role)
    db_session.commit()
    db_session.close()

    return jsonify({'success': True})


@app.route('/api/characters/<int:character_id>/roles', methods=['POST'])
def api_add_character_role(character_id):
    """Add a role to a character."""
    data = request.json
    role_id = data.get('role_id')

    if not role_id:
        return jsonify({'success': False, 'error': 'Role ID is required'}), 400

    db_session = get_session()

    character = db_session.query(Character).filter_by(id=character_id).first()
    role = db_session.query(Role).filter_by(id=role_id).first()

    if not character or not role:
        db_session.close()
        return jsonify({'success': False, 'error': 'Character or role not found'}), 404

    if role not in character.roles:
        character.roles.append(role)
        db_session.commit()

    db_session.close()

    return jsonify({'success': True})


@app.route('/api/characters/<int:character_id>/roles/<int:role_id>', methods=['DELETE'])
def api_remove_character_role(character_id, role_id):
    """Remove a role from a character."""
    db_session = get_session()

    character = db_session.query(Character).filter_by(id=character_id).first()
    role = db_session.query(Role).filter_by(id=role_id).first()

    if not character or not role:
        db_session.close()
        return jsonify({'success': False, 'error': 'Character or role not found'}), 404

    if role in character.roles:
        character.roles.remove(role)
        db_session.commit()

    db_session.close()

    return jsonify({'success': True})


# ============================================================================
# API ROUTES - Fits
# ============================================================================

@app.route('/api/check-fit', methods=['POST'])
def api_check_fit():
    """Check which characters can fly a fit."""
    data = request.json
    fit_text = data.get('fit_text', '').strip()

    if not fit_text:
        return jsonify({'error': 'Fit text is required'}), 400

    try:
        # Parse fit
        parsed = parse_eft_fit(fit_text)

        if not parsed:
            return jsonify({'error': 'Invalid EFT format'}), 400

        # Get skill requirements
        item_names = parsed['all_items']
        fit_requirements = skill_checker.get_fit_requirements(item_names)

        if not fit_requirements:
            return jsonify({'error': 'Could not determine skill requirements'}), 400

        # Check all characters
        results = skill_checker.check_all_characters(fit_requirements)

        # Count how many can fly
        can_fly_count = sum(1 for r in results if r['can_fly'])

        return jsonify({
            'hull': parsed['hull'],
            'fit_name': parsed['fit_name'],
            'total_skills': len(fit_requirements),
            'total_characters': len(results),
            'can_fly_count': can_fly_count,
            'results': results
        })

    except Exception as e:
        logger.error(f"Error checking fit: {e}", exc_info=True)
        return jsonify({'error': 'Error checking fit'}), 500


@app.route('/api/save-fit', methods=['POST'])
def api_save_fit():
    """Save a fit to the database."""
    data = request.json
    fit_text = data.get('fit_text', '').strip()

    if not fit_text:
        return jsonify({'success': False, 'error': 'Fit text is required'}), 400

    try:
        parsed = parse_eft_fit(fit_text)

        if not parsed:
            return jsonify({'success': False, 'error': 'Invalid EFT format'}), 400

        db_session = get_session()

        # Get hull type ID
        hull_type_id = skill_checker.get_type_id(parsed['hull'])

        saved_fit = SavedFit(
            name=parsed['fit_name'],
            eft_text=fit_text,
            hull_type_id=hull_type_id,
            saved_at=datetime.utcnow()
        )

        db_session.add(saved_fit)
        db_session.commit()
        db_session.close()

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error saving fit: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Error saving fit'}), 500


@app.route('/api/saved-fits/<int:fit_id>')
def api_get_saved_fit(fit_id):
    """Get a saved fit by ID."""
    db_session = get_session()

    saved_fit = db_session.query(SavedFit).filter_by(id=fit_id).first()

    if not saved_fit:
        db_session.close()
        return jsonify({'error': 'Fit not found'}), 404

    data = {
        'id': saved_fit.id,
        'name': saved_fit.name,
        'eft_text': saved_fit.eft_text
    }

    db_session.close()

    return jsonify(data)


# ============================================================================
# API ROUTES - Skills
# ============================================================================

@app.route('/api/refresh-skills', methods=['POST'])
def api_refresh_skills():
    """Manually trigger a skills refresh for all characters."""
    try:
        # Run the skill poll in the background
        import threading

        def poll_skills():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(poller.poll_all_skills())
            loop.close()

        thread = threading.Thread(target=poll_skills, daemon=True)
        thread.start()

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error refreshing skills: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Error refreshing skills'}), 500


# ============================================================================
# APPLICATION STARTUP
# ============================================================================

def startup():
    """Initialize the application on startup."""
    logger.info("Starting EVE Character Tracker...")

    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please set EVE_CLIENT_ID and EVE_CLIENT_SECRET in your .env file")
        return False

    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Initialize Preston OAuth
    logger.info("Initializing Preston OAuth...")
    init_preston()

    # Start background poller
    logger.info("Starting background poller...")
    poller.start()

    logger.info("Startup complete!")
    return True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    import sys

    is_electron = '--electron' in sys.argv

    if startup():
        app.run(
            debug=not is_electron,
            host='127.0.0.1' if is_electron else '0.0.0.0',
            port=5000,
            use_reloader=not is_electron
        )
    else:
        logger.error("Startup failed. Please fix configuration errors and try again.")
        sys.exit(1)
