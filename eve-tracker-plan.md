# EVE Character Tracker — Project Plan

## Overview
A local Flask web app that shows the real-time locations of all your EVE Online characters, with role-based filtering, Dotlan links, and a fit checker that tells you which characters can fly a given ship fitting.

## Tech Stack
- **Flask** — web framework
- **SQLite** — persistent storage for characters, tokens, roles, skills, saved fits
- **aiohttp + asyncio** — async ESI polling in background thread
- **Preston** — OAuth2 flow and ESI authentication
- **Jinja2** — templating (comes with Flask)
- **Vanilla JS** — auto-refresh, filtering, fit checker interactions
- **Bundled SDE SQLite** — ship/module skill requirements lookup

## OAuth Scopes
```
esi-location.read_location.v1
esi-location.read_online.v1
esi-location.read_ship_type.v1
esi-skills.read_skills.v1
```

## Database Schema

### characters
- `id` — character_id from ESI (primary key)
- `name` — character name
- `refresh_token`
- `access_token`
- `token_expiry`
- `added_at`

### roles
- `id` — auto-increment primary key
- `name` — free-form role name (e.g., "Capital", "Cyno", "Industry")

### character_roles (many-to-many join)
- `character_id` — FK to characters
- `role_id` — FK to roles

### location_cache
- `character_id` — FK to characters
- `solar_system_id`
- `solar_system_name`
- `ship_type_id`
- `ship_name`
- `station_id` — nullable, populated if docked
- `is_online` — boolean
- `last_updated` — timestamp

### character_skills
- `character_id` — FK to characters
- `skill_id`
- `skill_level` — trained level (1-5)
- `last_updated` — timestamp

### saved_fits
- `id` — auto-increment primary key
- `name` — from EFT header (e.g., "PvE Raven")
- `eft_text` — raw pasted EFT format text
- `hull_type_id` — type ID of the hull
- `saved_at` — timestamp

### SDE tables (bundled, read-only)
- `invTypes` — type ID → name mapping
- `dgmTypeAttributes` — skill requirements per type

## Pages

### 1. Dashboard (`/`)

Main character location view.

```
┌──────────────────────────────────────────────────────┐
│  EVE Character Tracker   [Dashboard] [Fit Checker]   │
│                                    [Settings]        │
│                                                      │
│  Filter: [Capital] [Industry] [Cyno] [Scout]         │
│                            ↻ Refreshing in 45s       │
│──────────────────────────────────────────────────────│
│  🟢 Portrait  Neeraj Main    Jita        Golem       │
│               [Capital] [Industry]                   │
│                                                      │
│  🟢 Portrait  Scout Alt      Oijanen     Sabre       │
│               [Scout] [PvP]                          │
│                                                      │
│  ⚫ Portrait  Hauler 3       Amarr       Charon      │
│               [Hauler]                               │
└──────────────────────────────────────────────────────┘
```

**Features:**
- Character portraits from `https://images.evetech.net/characters/{id}/portrait`
- Online/offline indicator (green/gray dot)
- Offline characters grayed out but in same list
- Sort: online first, then alphabetical
- Role tags as small chips on each character
- Role filter bar at top — toggle one or more roles to filter, show all when none selected
- System names link to Dotlan (`https://evemaps.dotlan.net/system/{system_name}`)
- Auto-refresh every 60 seconds via JS polling `/api/locations` endpoint
- Subtle countdown indicator showing time until next refresh
- Minimal, clean, light UI

### 2. Fit Checker (`/fits`)

Paste an EFT fit to see which characters can fly it.

```
┌──────────────────────────────────────────────────────┐
│  EVE Character Tracker   [Dashboard] [Fit Checker]   │
│                                                      │
│  Paste EFT fit:                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ [Raven, PvE Raven]                           │    │
│  │ Ballistic Control System II                  │    │
│  │ Cruise Missile Launcher II, Scourge Fury ... │    │
│  └──────────────────────────────────────────────┘    │
│  [Check Fit]                [Save Fit]               │
│                                                      │
│  Saved fits: [PvE Raven] [Cyno Redeemer] [+3 more]  │
│──────────────────────────────────────────────────────│
│                                                      │
│  Raven — PvE Raven                                   │
│  Total unique skills required: 14                    │
│  Characters who can fully fly: 2 of 32               │
│                                                      │
│  ✅ Neeraj Main         — All 14/14 skills met       │
│  ✅ Mission Alt          — All 14/14 skills met       │
│  ⚠️ Indy Alt 7          — 12/14 ▶ expand             │
│     └ Missing: Cruise Missiles V (has IV)            │
│     └ Missing: Caldari BS IV (has III)               │
│  ❌ Cyno Alt 3           — 3/14 ▶ expand             │
│     └ Missing: Cruise Missiles (not trained)         │
│     └ Missing: ...                                   │
└──────────────────────────────────────────────────────┘
```

**Features:**
- Textarea for pasting EFT format fits
- Parses hull + all modules, ignores ammo/charges
- Looks up skill requirements for each item from bundled SDE
- Deduplicates skill requirements
- Cross-references against all characters' cached skills
- Status icons: ✅ fully qualified, ⚠️ partially trained, ❌ missing key skills
- ✅ characters show no detail by default
- ⚠️ and ❌ characters show expandable detail with missing skills only
- Summary line: "Characters who can fully fly: X of Y"
- Save fits to DB for quick re-checking later
- Saved fits appear as clickable chips
- Can also search by just pasting a bare `[Raven]` to check hull-only requirements
- Can search by skill name directly (e.g., type "Cynosural Field Theory" to see who has it and at what level)

### 3. Settings (`/settings`)

Character and role management.

**Features:**
- **Add Character**: Button triggers OAuth flow → EVE SSO login → callback saves character to DB → prompt to optionally assign roles
- **Manage Characters**: List all characters with their current roles, ability to add/remove role tags per character, remove character from tracking entirely
- **Manage Roles**: Create new roles (free-form name), delete existing roles
- **Refresh Skills**: Manual button to re-poll all character skills from ESI immediately

## User Flows

### First Launch
1. User visits `localhost:5000`
2. Empty dashboard with "Add Character" button
3. No characters, no roles yet

### Add Character
1. Click "Add Character" → redirects to EVE SSO login
2. User authenticates on EVE SSO
3. OAuth callback saves character (name, tokens) to DB
4. User is prompted to optionally assign roles (from existing roles or create new ones)
5. Character immediately appears on dashboard
6. Poller picks it up on next cycle

### Check a Fit
1. Navigate to Fit Checker page
2. Paste EFT format fit into textarea
3. Click "Check Fit"
4. App parses hull + modules → looks up all skill requirements from SDE → checks all characters
5. Results displayed with expandable detail for failing characters
6. Optionally click "Save Fit" to store for later

## Background Poller

- Runs in a daemon thread started on app startup
- Every 60 seconds, loops through all characters
- Uses `aiohttp` to fetch location + online status concurrently for all characters
- Resolves `solar_system_id` → system name and `ship_type_id` → ship name (cached in memory since static data)
- Writes results to `location_cache` table in SQLite
- Flask reads from `location_cache` on page load — never hits ESI directly on request
- Skills polled once on startup, then daily automatically (or via manual refresh button in Settings)
- Token refresh handled automatically via Preston

## API Endpoints

### `GET /api/locations`
Returns JSON array of all character locations for JS auto-refresh:
```json
[
  {
    "id": 12345,
    "name": "Neeraj Main",
    "system": "Jita",
    "ship": "Golem",
    "online": true,
    "roles": ["Capital", "Industry"],
    "portrait_url": "https://images.evetech.net/characters/12345/portrait?size=64"
  }
]
```

### `POST /api/check-fit`
Accepts EFT text, returns skill check results as JSON.

### `POST /api/save-fit`
Saves a fit to the database.

### `GET /api/saved-fits`
Returns list of saved fits.

## File Structure
```
eve-tracker/
├── app.py              # Flask app, routes, startup, poller thread launch
├── poller.py           # Async background polling loop (aiohttp + asyncio)
├── models.py           # SQLAlchemy models for all tables
├── auth.py             # Preston OAuth helpers (init, authenticate, refresh)
├── config.py           # Environment variable / config loading
├── eft_parser.py       # Parse EFT format → list of type names
├── skill_checker.py    # Cross-reference fits against character skills using SDE
├── sde.sqlite          # Bundled SDE extract (invTypes, dgmTypeAttributes)
├── static/
│   └── style.css       # Light, clean, minimal styling
├── templates/
│   ├── base.html       # Layout with nav (Dashboard, Fit Checker, Settings)
│   ├── dashboard.html  # Main character location grid
│   ├── fits.html       # Fit checker with textarea, results, saved fits
│   └── settings.html   # Character management, role management, skill refresh
├── tracker.db          # SQLite app database (gitignored)
├── requirements.txt
└── .env                # EVE_CLIENT_ID, EVE_CLIENT_SECRET, FLASK_SECRET_KEY
```

## Requirements
```
flask
preston
aiohttp
sqlalchemy
python-dotenv
```

## ESI Endpoints Used

| Endpoint | Scope | Cache Timer | Purpose |
|----------|-------|-------------|---------|
| `GET /characters/{id}/location/` | `esi-location.read_location.v1` | 5s | Character location |
| `GET /characters/{id}/online/` | `esi-location.read_online.v1` | 60s | Online status |
| `GET /characters/{id}/ship/` | `esi-location.read_ship_type.v1` | 5s | Current ship |
| `GET /characters/{id}/skills/` | `esi-skills.read_skills.v1` | 120s | All trained skills |
| `GET /universe/systems/{id}/` | none | 24h | System name resolution |
| `GET /universe/types/{id}/` | none | 24h | Ship/item name resolution |

## Design Notes

- **Polling interval**: 60 seconds for location and online status
- **Skills refresh**: Once on startup, daily thereafter, plus manual refresh button
- **System/ship name caching**: In-memory dict, populated on first encounter, never expires (static data)
- **Token storage**: Refresh tokens stored in SQLite, access tokens refreshed automatically by Preston
- **SDE data**: Bundled SQLite file with invTypes and dgmTypeAttributes tables extracted from the official EVE SDE
- **Offline characters**: Shown in same list but grayed out, sorted below online characters
- **Role filtering**: Multi-select — characters matching ANY selected role are shown. All shown when no filter active.
- **EFT parsing**: Extract hull name from `[Hull, Fit Name]` header, extract all module names from subsequent lines, ignore ammo after commas, ignore empty lines and `[Empty *]` slots
- **Portrait URLs**: `https://images.evetech.net/characters/{character_id}/portrait?size=64`
- **Dotlan links**: `https://evemaps.dotlan.net/system/{system_name}`
