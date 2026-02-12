# EVE Character Tracker

A local Flask web application that shows the real-time locations of all your EVE Online characters, with role-based filtering, Dotlan links, and a fit checker that tells you which characters can fly a given ship fitting.

## Features

- **Real-time Character Tracking**: Monitor all your characters' locations, ships, and online status
- **Role-based Filtering**: Tag characters with custom roles (Capital, Cyno, Industry, etc.) and filter the dashboard
- **Fit Checker**: Paste EFT format fits to see which characters can fly them
- **Skill Requirements**: Detailed breakdown of missing skills for each character
- **Auto-refresh**: Dashboard updates every 60 seconds automatically
- **Dotlan Integration**: Click system names to view on Dotlan
- **Save Fits**: Store frequently used fits for quick checking

## Screenshots

### Dashboard
The main dashboard shows all your characters with their current location, ship, and online status. Filter by roles to quickly find specific characters.

### Fit Checker
Paste any EFT format fit to see which characters can fly it, with detailed skill breakdowns for characters missing requirements.

## Prerequisites

- Python 3.8 or higher
- EVE Online developer application credentials
- EVE Online SDE (Static Data Export) SQLite database

## Installation

### 1. Clone or Download

Download this project to your local machine.

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Register EVE Application

1. Go to [EVE Developers](https://developers.eveonline.com/)
2. Create a new application with the following scopes:
   - `esi-location.read_location.v1`
   - `esi-location.read_online.v1`
   - `esi-location.read_ship_type.v1`
   - `esi-skills.read_skills.v1`
3. Set the callback URL to: `http://localhost:5000/callback`
4. Note down your Client ID and Client Secret

### 4. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```
EVE_CLIENT_ID=your_client_id_here
EVE_CLIENT_SECRET=your_client_secret_here
FLASK_SECRET_KEY=your_random_secret_key_here
EVE_CALLBACK_URL=http://localhost:5000/callback
```

### 5. Download SDE Database

You need the EVE Online Static Data Export (SDE) for skill checking:

1. Download the latest SDE from [Fuzzwork's SDE conversions](https://www.fuzzwork.co.uk/dump/latest/)
2. Extract the SQLite database
3. Place it in the project root as `sde.sqlite`

**Required tables in the SDE:**
- `invTypes` - Item type names and IDs
- `dgmTypeAttributes` - Skill requirements for items

Alternatively, you can create a minimal SDE with just these tables from the full SDE dump.

## Usage

### Starting the Application

```bash
python app.py
```

The application will start on `http://localhost:5000`

### Adding Characters

1. Navigate to Settings
2. Click "Add Character"
3. Log in with your EVE Online account
4. Authorize the application
5. Character will be added and start tracking immediately

### Managing Roles

1. Go to Settings
2. Create roles (e.g., "Capital", "Cyno", "Scout")
3. Assign roles to characters
4. Use role filters on the dashboard to find characters quickly

### Checking Fits

1. Go to Fit Checker
2. Paste an EFT format fit (from in-game or a fitting tool)
3. Click "Check Fit"
4. See which characters can fly it
5. Optionally save the fit for later

**Example EFT Format:**
```
[Raven, PvE Raven]
Ballistic Control System II
Ballistic Control System II
Cruise Missile Launcher II, Scourge Fury Cruise Missile
Cruise Missile Launcher II, Scourge Fury Cruise Missile
```

## Project Structure

```
eve-tracker/
├── app.py                  # Main Flask application
├── auth.py                 # Preston OAuth helpers
├── config.py               # Configuration
├── eft_parser.py           # EFT format parser
├── models.py               # Database models
├── poller.py               # Background ESI polling
├── skill_checker.py        # Fit skill validation
├── requirements.txt        # Python dependencies
├── .env                    # Configuration (not in git)
├── .env.example            # Configuration template
├── sde.sqlite              # EVE SDE database (not in git)
├── tracker.db              # App database (auto-generated)
├── static/
│   └── style.css           # Styles
└── templates/
    ├── base.html           # Base template
    ├── dashboard.html      # Character dashboard
    ├── fits.html           # Fit checker
    └── settings.html       # Settings page
```

## How It Works

### Background Polling

- The app runs a background thread that polls ESI every 60 seconds
- Character locations, ships, and online status are cached in SQLite
- Skills are polled on startup and then daily (or manually via Settings)
- Tokens are automatically refreshed when needed

### Skill Checking

- Parses EFT format to extract hull and module names
- Looks up type IDs from item names using the SDE
- Queries skill requirements from the SDE's `dgmTypeAttributes` table
- Cross-references against cached character skills
- Returns detailed results with missing skills

### Security

- All tokens are stored locally in SQLite
- No data is sent to external servers except EVE ESI
- OAuth flow follows EVE's official authentication

## Troubleshooting

### "Configuration error: EVE_CLIENT_ID not set"

Make sure you've created a `.env` file with your EVE application credentials.

### "Could not determine skill requirements"

Ensure the `sde.sqlite` file is present and contains the required tables (`invTypes` and `dgmTypeAttributes`).

### Characters not updating

- Check that characters have valid tokens (re-add if needed)
- Check the console for errors from the background poller
- Manually refresh skills from Settings if needed

### Preston/OAuth errors

Make sure your callback URL matches exactly what you registered with EVE (including the protocol: `http://` not `https://`).

## Development

### Running in Debug Mode

The app runs in debug mode by default when started with `python app.py`. This enables auto-reload on code changes.

### Database Schema

The app uses SQLAlchemy with SQLite. The database is automatically created on first run. To reset, delete `tracker.db` and restart the app.

## Tech Stack

- **Flask** - Web framework
- **SQLAlchemy** - ORM for database
- **Preston** - EVE SSO OAuth client
- **aiohttp** - Async HTTP for ESI polling
- **Jinja2** - Templating (built into Flask)
- **Vanilla JavaScript** - Frontend interactivity

## API Endpoints

The app provides several API endpoints for AJAX requests:

- `GET /api/locations` - Get all character locations
- `POST /api/check-fit` - Check fit requirements
- `POST /api/save-fit` - Save a fit
- `GET /api/saved-fits/<id>` - Get a saved fit
- `POST /api/roles` - Create a role
- `DELETE /api/roles/<id>` - Delete a role
- `DELETE /api/characters/<id>` - Remove a character
- `POST /api/characters/<id>/roles` - Add role to character
- `DELETE /api/characters/<id>/roles/<role_id>` - Remove role from character
- `POST /api/refresh-skills` - Manually refresh all skills

## License

This project is provided as-is for personal use. EVE Online and related imagery are property of CCP Games.

## Contributing

This is a personal project, but feel free to fork and modify for your own use.

## Credits

- Built for EVE Online
- Uses [Preston](https://github.com/Celeo/preston) for OAuth
- SDE data from [Fuzzwork](https://www.fuzzwork.co.uk/)
- Character portraits from EVE Image Server
- Map links to [DOTLAN EveMaps](https://evemaps.dotlan.net/)

## Support

For issues or questions, please check:
- EVE ESI documentation: https://esi.evetech.net/
- Preston documentation: https://github.com/Celeo/preston
- EVE Developers: https://developers.eveonline.com/

Fly safe! o7
