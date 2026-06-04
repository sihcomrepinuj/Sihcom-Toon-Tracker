# Sihcom Toon Tracker - Development Context

## Project Overview

This is a local Flask web application called **Sihcom Toon Tracker** that tracks EVE Online characters in real-time. It shows character locations, ships, online status, and includes a fit checker to determine which characters can fly specific ship fittings. It runs as an Electron desktop app wrapping the Flask backend.

**Tech Stack:**
- **Backend**: Python 3.14, Flask, SQLAlchemy
- **Desktop Shell**: Electron (spawns Flask as a child process)
- **Authentication**: EVE Online SSO via Preston library + JWT decoding
- **Database**: SQLite (local)
- **Frontend**: Jinja2 templates, vanilla JavaScript
- **EVE API**: ESI (EVE Swagger Interface) via Preston
- **Build Tool**: electron-builder (portable .exe)

**GitHub**: https://github.com/sihcomrepinuj/Sihcom-Toon-Tracker

## Work Session - February 11-12, 2026

### Session 1 (Feb 11) - Auth Fixes

The original code was non-functional due to Preston library API changes. Fixed:
- Preston's `whoami()` returning empty `{}` — replaced with direct JWT decoding
- Preston's `authenticate()` returning objects instead of dicts — switched to attribute access
- Preston's `use_refresh_token()` removed — switched to `authenticate_from_token()`
- SQLAlchemy `DetachedInstanceError` — added `selectinload()` for relationships

### Session 2 (Feb 12) - Electron + UI Redesign

#### 1. Dashboard UI Changes

**Online/offline indicator** (`static/style.css`):
- Removed `opacity: 0.6` on offline character cards — cards are now full visibility regardless of status
- Online status indicator dot has a glowing green effect (`box-shadow` with green glow)
- Offline dot is plain gray, no glow

**Card layout redesign** (`templates/dashboard.html`, `static/style.css`):
- Changed from horizontal row list (`.character-list` with flex-column) to a responsive **grid of square-ish cards** (`.character-grid` with CSS grid)
- Grid uses `repeat(auto-fill, minmax(200px, 1fr))` — adapts from 2 columns on narrow to 5-6 on wide
- Each card is vertically stacked: portrait (80px, centered) → name → location/ship details → role chips
- Portrait size bumped from 64px to 80px, fetched at 128px for retina
- Location and ship shown as labeled rows (`detail-label` + value) instead of separate flex columns
- Role chips smaller (0.75rem) and centered at card bottom with a subtle top border
- Cards have hover lift effect (`translateY(-2px)` + shadow)
- JavaScript `updateCharacterDisplay()` and `applyRoleFilter()` updated to match new HTML structure
- Role filter uses `display: ''` instead of `display: 'flex'` for grid compatibility

#### 2. Electron Desktop App

**Architecture**: Electron spawns `python app.py --electron` as a child process, shows a loading screen while Flask boots, then loads `http://localhost:5000` in a BrowserWindow.

**Files created:**
- `main.js` — Electron main process
- `loading.html` — Splash screen shown during Flask startup
- `package.json` — Node.js project manifest with Electron + electron-builder

**`main.js` key components:**
- `findPython()` — Tries `python`, `python3`, `py` on PATH, then scans common Windows install paths (`C:\PythonXXX`, `AppData\Local\Programs\Python`, `Program Files`)
- `startFlask()` — Spawns Flask with `--electron` flag, sets `cwd` to `__dirname`, handles spawn errors with dialog
- `waitForFlask()` — Polls `http://localhost:5000` every 200ms for up to 10 seconds
- `createWindow()` — BrowserWindow 1200x800, `nodeIntegration: false`, `autoHideMenuBar: true`
- `will-navigate` handler — intercepts external URLs (EVE SSO, DOTLAN) and opens them in system browser via `shell.openExternal()`
- `startOAuthPolling()` — After EVE SSO opens in external browser, polls `/api/locations` every 2s to detect new characters, then navigates Electron to `/settings`
- `setWindowOpenHandler` — Opens `target="_blank"` links externally
- `killFlask()` — Uses `taskkill /pid <PID> /f /t` on Windows to kill the process tree
- Lifecycle: `window-all-closed`, `before-quit`, `process.exit` all call `killFlask()`

**`app.py` changes** (lines 451-465):
```python
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
        logger.error("Startup failed.")
        sys.exit(1)
```
- `--electron` flag disables debug mode, Werkzeug reloader, and binds to `127.0.0.1`
- `sys.exit(1)` on failure so Electron can detect startup errors
- Running `python app.py` without the flag works exactly as before

**electron-builder config** (`package.json`):
- `asar: false` — Python files are NOT packed into an asar archive (Python can't read from inside one)
- `.env` is included in the build files for the portable exe
- Build target: `portable` (single `.exe`, no installer)
- Output: `dist/EVE-Character-Tracker.exe`
- Build command: `npm run build` (requires admin PowerShell for symlink permissions)

#### 3. Rename to "Sihcom Toon Tracker"

- Updated all user-facing references from "EVE Character Tracker" to "Sihcom Toon Tracker" across `base.html`, `dashboard.html`, `settings.html`, `fits.html`, `main.js`, `loading.html`

#### 4. Git + GitHub Setup

- Initialized git repo, pushed to `sihcomrepinuj/Sihcom-Toon-Tracker`
- `.gitignore` updated to exclude: `.env`, `tracker.db`, `sde.sqlite`, `sde.sqlite.db`, `node_modules/`, `package-lock.json`, `dist/`, `out/`, `.claude/`

### Session 3 (Feb 12 continued) - Quick Wins + Search Refinement

#### 1. Search Bar with Ctrl+F (`templates/dashboard.html`, `static/style.css`)

- Added a search input in the `.dashboard-header` between role filter chips and the refresh timer
- Searches case-insensitively across character name, solar system, ship name, and roles (OR across fields)
- Combined with role chip filters using AND logic (must match both search text AND selected roles)
- `Ctrl+F` intercepts browser find and focuses the search input instead
- `Escape` clears the search text, blurs the input, and restores all cards
- **Result count**: `"Showing X of Y characters"` appears below the search bar when any filter (search or role) is active
- **No-results message**: `"No characters match your search."` appears when filters are active but nothing matches
- Search input has rounded pill style with blue focus ring
- On mobile (≤768px), the search bar goes full-width above the role chips

**Key JS structure:**
- `searchTerm` variable tracks current search text
- `applyFilters()` is the unified filter function (replaced the old `applyRoleFilter()`) — handles both role chips and search in one pass, counts visible/total cards, updates `#searchStatus` and `#noResults`
- Cards have `data-name`, `data-system`, `data-ship`, `data-roles` attributes for fast search matching without DOM traversal

#### 2. Last Updated Timestamps (`app.py`, `templates/dashboard.html`, `static/style.css`)

- `/api/locations` endpoint now returns `last_updated` (ISO 8601 string) from `LocationCache.last_updated`
- Each character card shows a relative time at the bottom: "Updated just now", "Updated 2m ago", "Updated 1h ago", etc.
- `relativeTime(isoString)` JS helper converts ISO timestamps to human-friendly relative times
- Timestamps auto-refresh every 30 seconds via `setInterval(refreshTimestamps, 30000)` — no full API call, just recalculates from stored `data-updated` attributes
- Jinja template also renders timestamps server-side on initial page load

#### 3. Token Health Indicator (`app.py`, `templates/settings.html`, `static/style.css`)

- Settings route now passes `now=datetime.utcnow()` to the template
- Each character in the settings page shows a token status badge next to their name:
  - **No badge** = healthy (token is valid and being refreshed normally)
  - **"Token Expired"** (red pill) = `token_expiry < now`, meaning the poller's auto-refresh has been failing. Tooltip suggests re-adding the character.
  - **"Unknown"** (gray pill) = `token_expiry` is `None`
- Note: since access tokens expire every ~20 minutes and the poller refreshes them automatically, a healthy character will always have `token_expiry` slightly in the future. An expired token means something is actually broken.

#### 4. Corporation Logo on Dashboard Cards (`models.py`, `app.py`, `poller.py`, `templates/dashboard.html`, `static/style.css`)

- Added `corporation_id = Column(Integer, nullable=True)` to the `Character` model — nullable for backward compatibility with existing database rows
- **Poller** (`poller.py`): Added a 4th parallel ESI call in `poll_character_location()` to `GET /latest/characters/{id}/` (public endpoint, no auth needed) to fetch `corporation_id`. Updates the character record if the corp has changed.
- **OAuth callback** (`app.py`): Fetches `corporation_id` from the same public endpoint via `urllib.request` during character registration, so corp logo appears immediately after adding a character
- **API** (`app.py`): `/api/locations` response now includes `corporation_id` field
- **Dashboard cards**: Both Jinja template and JS `updateCharacterDisplay()` render a corp logo overlay on the character portrait:
  ```html
  <img src="https://images.evetech.net/corporations/{id}/logo?size=32" class="corp-logo">
  ```
- **CSS**: `.corp-logo` is absolute-positioned at `bottom: -2px; left: -5px` within `.character-portrait` (20×20px, 3px border-radius, white border/background)
- Characters without a `corporation_id` (null) gracefully show no logo — no broken image icon
- No re-auth required for existing characters — the poller backfills `corporation_id` automatically on the next poll cycle

## Running the Application

**Development (from terminal):**
```bash
npm start
```
This runs `electron .` which spawns Flask automatically.

**Standalone Flask (no Electron):**
```bash
python app.py
```
Then visit `http://localhost:5000` in a browser.

**Build portable exe:**
```bash
npm run build   # Run from admin PowerShell
```
Produces `dist/EVE-Character-Tracker.exe`.

## Environment Setup

**Required:**
- Python 3.14 (installed at `C:\Python314\python.exe`)
- Node.js LTS (for `npm start` / `npm run build`)
- Python packages: `flask`, `preston`, `aiohttp` (poller only), `sqlalchemy`, `python-dotenv`, `requests` + `pyyaml` (SDE build only)
- SDE: run `python setup_sde.py` once to build `data/sqlite-latest.sqlite` from CCP's YAML SDE (see Session 9)

**`.env` file:**
```env
EVE_CLIENT_ID=<your_client_id>
EVE_CLIENT_SECRET=<your_client_secret>
FLASK_SECRET_KEY=<your_secret_key>
EVE_CALLBACK_URL=http://localhost:5000/callback
```

**EVE Developer Application** (https://developers.eveonline.com/):
- Callback URL: `http://localhost:5000/callback` (must match exactly)
- Scopes: `esi-location.read_location.v1`, `esi-location.read_online.v1`, `esi-location.read_ship_type.v1`, `esi-skills.read_skills.v1`

## Architecture Notes

### Token Refresh Behavior
The poller runs every 60 seconds for location data but only refreshes the access token when it has expired (~20 minutes). This is correct behavior — ESI access tokens are JWTs with a 20-minute `exp` claim. The refresh token is long-lived and used via `preston.authenticate_from_token()`.

### OAuth Flow in Electron
EVE SSO opens in the system browser (not Electron's Chromium) so the user has access to saved passwords and 2FA. The callback still hits `localhost:5000/callback` which Flask handles. Electron detects the new character by polling `/api/locations` and then navigates to `/settings`.

### Port 5000 is Hardcoded
The EVE SSO callback URL is registered as `http://localhost:5000/callback` at CCP's developer portal. Changing the port requires updating the registration. This is why we don't use a dynamic port.

### Background Polling (`poller.py`)
- Daemon thread with its own asyncio event loop
- Location/ship/online/corporation: every 60 seconds (`Config.LOCATION_POLL_INTERVAL`) — 4 parallel ESI calls per character
- Skills: every 24 hours (`Config.SKILLS_POLL_INTERVAL`)
- Token refresh: only when `token_expiry < utcnow()` (~every 20 min)
- Corporation fetch uses public ESI endpoint (no auth), so it works even if tokens are expired

### Database Models (`models.py`)
- **Character**: ID, name, tokens, expiry, corporation_id, account_id (nullable FK). `location` and `skills` relationships use `cascade='all, delete-orphan'` so deleting a character cleans up related rows.
- **Account**: First-class entity (name, subscription, notes). Nullable FK from Character (ON DELETE SET NULL).
- **Role**: Custom tags (Capital, Cyno, Scout, etc.)
- **LocationCache**: Cached location/ship/online status
- **CharacterSkill**: Cached skill data for fit checking
- **SavedFit**: Stored EFT format fits

### All Routes (`app.py`)
| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Dashboard |
| `/fits` | GET | Fit checker page |
| `/routes` | GET | Route finder page |
| `/settings` | GET | Character & role management |
| `/login` | GET | Initiates EVE SSO redirect |
| `/callback` | GET | OAuth callback handler |
| `/api/locations` | GET | All characters as JSON |
| `/api/characters/<id>` | DELETE | Remove character |
| `/api/roles` | POST | Create role |
| `/api/roles/<id>` | PATCH | Update role color |
| `/api/roles/<id>` | DELETE | Delete role |
| `/api/characters/<id>/roles` | POST | Assign role |
| `/api/characters/<id>/roles/<rid>` | DELETE | Remove role |
| `/api/accounts` | GET | List accounts |
| `/api/accounts` | POST | Create account |
| `/api/accounts/<id>` | PATCH | Update account |
| `/api/accounts/<id>` | DELETE | Delete account (chars become unassigned) |
| `/api/characters/<id>/account` | PUT | Assign character to account |
| `/api/check-fit` | POST | Validate EFT fit |
| `/api/save-fit` | POST | Save fit |
| `/api/saved-fits/<id>` | GET | Retrieve saved fit |
| `/api/refresh-skills` | POST | Trigger skills poll |
| `/api/systems` | GET | Search solar systems for autocomplete |
| `/api/routes` | POST | Calculate jump distances to destination |

## Known Issues

1. **Python not on PATH for Electron** — `findPython()` in `main.js` scans common Windows install paths as a fallback, but if Python is in an unusual location it won't be found. User's Python is at `C:\Python314\python.exe` which the scanner picks up.
2. **Portable .exe build requires admin PowerShell** — electron-builder needs symlink permissions on Windows. Run `npm run build` from an admin terminal.
3. **`.env` bundled in portable build** — The `.env` file with EVE SSO credentials is included in the portable exe. Fine for personal use, but would need a different strategy for distribution.
4. **Flash messages after OAuth** — When OAuth completes in the system browser, Flask's flash message appears in the browser tab, not in Electron. Minor cosmetic issue.

## Feature Backlog

### Completed Quick Wins (Session 3)
- ~~Search bar with Ctrl+F~~ ✅
- ~~Last updated timestamp on cards~~ ✅
- ~~Token health indicator on settings~~ ✅
- ~~Search result count~~ ✅
- ~~No-results message~~ ✅
- ~~Escape to clear search~~ ✅
- ~~Corporation logo on dashboard cards~~ ✅

### Completed (Session 4 — 2026-05-24)
- ~~Organize characters by account (first-class `Account` entity, view toggle, account filter)~~ ✅

### Completed (Session 5 — 2026-05-26)
- ~~Dark mode theme (CSS variables, toggle button, localStorage persistence)~~ ✅
- ~~Notepad widget (floating panel, auto-save, backtick shortcut)~~ ✅
- ~~Remove account filter chips from dashboard~~ ✅
- ~~Replace Grouped/Loose text toggle with SVG icons~~ ✅
- ~~Add Cards/Slim density toggle with icons~~ ✅
- ~~Slim view rendering (portrait + online dot + name + system)~~ ✅

### Completed (Session 5 continued — Fit Checker)
- ~~Store `total_sp` per character (model + migration + poller)~~ ✅
- ~~Injector math in `/api/check-fit` (diminishing returns per SP tier, skill rank from SDE)~~ ✅
- ~~Expandable injector breakdown UI on saved fit chips (can fly / 1 inj / 2 inj / 3 inj / 4+ inj)~~ ✅
- ~~Per-character injector count + missing SP shown in detailed results~~ ✅
- Design doc: `docs/plans/2026-05-26-dashboard-and-fit-checker-design.md`

### Completed (Session 6 — 2026-05-28)
- ~~Colors for role tags (preset palette + user override via color picker in Settings)~~ ✅
- ~~Horizontal card layout (portrait left, content right, wider grid columns)~~ ✅

#### Tag Colors Implementation
- Added `color` column to `Role` model (String, nullable) with idempotent migration + backfill
- `ROLE_PALETTE` constant (10 colors) defined in `models.py`, auto-assigned on role creation
- `PATCH /api/roles/<id>` endpoint to update a role's color
- `/api/locations` now returns roles as `[{name, color}, ...]` instead of `[name, ...]`
- Settings page: each role item has a clickable color dot — expands inline palette picker, PATCH on selection
- Existing roles are backfilled with palette colors during migration
- Settings character role chips show their color via `.colored` class (white text on role-color background)

#### Tag Colors on Dashboard
- **Cards**: colored left border (`border-left: 4px solid <color>`) using first role's color — no chips on cards
- **Filter chips**: always show role color background via `--role-color` CSS custom property, dimmed at `opacity: 0.55` when inactive, full opacity on hover or when active
- `.role-chip:hover` scoped with `:not(.filter-chip)` to prevent gray override on filter chips

#### Horizontal Card Layout
- Cards now use `flex-direction: row` with `position: relative` — portrait (64px) on the left, content on the right
- Grid columns widened to `minmax(280px, 1fr)` from `minmax(200px, 1fr)`
- New `.card-body` wrapper holds name, details, timestamp (no role chips on cards)
- Left-aligned text throughout (name, timestamp)
- Removed `.card-header` wrapper and `.card-account` section from cards

### Completed (Session 7 — 2026-06-01)
- ~~Subscription badge simplification (Omega/Alpha chip → small Greek symbols)~~ ✅
- ~~Route Finder page ("who's closest to X?")~~ ✅

### Completed (Session 8 — 2026-06-01)
- ~~Fix character deletion crash (cascade delete on LocationCache + CharacterSkill)~~ ✅
- ~~Fix routes search input not auto-focused on page load~~ ✅
- ~~Replace ESI HTTP route calls with local BFS on SDE jump graph (~86ms vs seconds)~~ ✅

#### Subscription Badge Change
- Replaced yellow "OMEGA" chip and gray "ALPHA" chip with small inline Greek letter symbols
- Omega: yellow Ω (`&#937;`), Alpha: gray Α (`&#913;`), Unknown: no symbol
- Removed chip styling (background, border-radius, padding) — now just styled text

#### Route Finder Implementation
- **New `/routes` page** with nav link between "Fit Checker" and "Settings"
- **`GET /api/systems?q=`** — autocomplete endpoint querying SDE `mapSolarSystems` table, case-insensitive prefix match, returns up to 10 results
- **`POST /api/routes`** — accepts `{"destination_id": <system_id>}`, loads all characters + their `solar_system_id` from `LocationCache`, calculates jump counts via BFS on the SDE `mapSolarSystemJumps` gate graph (loaded once and cached in memory), returns characters sorted by jump count ascending (nulls last). ~86ms for 35 characters vs seconds of ESI calls.
- **Frontend**: type-ahead search input (autofocused) with 250ms debounce, dropdown with arrow-key navigation, Enter to select. Results table shows rank, 32px portrait with online/offline dot, character name, current system, jump count (or "—" for unreachable)
- **Edge cases**: characters already at destination get `jumps: 0`, characters with no location get `jumps: null` and sort to bottom, empty state if no characters added
- Shortest route only (no secure/insecure toggle)
- Design docs: `docs/plans/2026-05-31-route-finder-design.md`, `docs/plans/2026-06-01-route-finder-plan.md`

### Completed (Session 9 — 2026-06-03)
- ~~Add `.env.example` template (colleague feedback)~~ ✅
- ~~Replace Fuzzwork SDE with CCP's official YAML SDE built via `setup_sde.py`~~ ✅

#### `.env.example`
- Added `.env.example` documenting the four required vars (`EVE_CLIENT_ID`, `EVE_CLIENT_SECRET`, `FLASK_SECRET_KEY`, `EVE_CALLBACK_URL`) with inline comments and a `secrets.token_hex(32)` hint for the Flask key. The README already referenced `cp .env.example .env`; the file just didn't exist.

#### SDE from CCP (was Fuzzwork)
Colleague feedback: stop using the third-party Fuzzwork SDE; pull from the source. Mirrors the approach in the sibling `Sihcom Inventory and Industry` project.
- **`setup_sde.py`** (new) — downloads CCP's official YAML SDE from `https://developers.eveonline.com/static-data/tranquility`, converts it to SQLite via the `noirsoldats/eve-sde-converter` submodule, installs to `data/sqlite-latest.sqlite`, and verifies the app's tables. Run `python setup_sde.py` (re-run after major patches).
- **`tools/eve-sde-converter`** — added as a git submodule, pinned to `f1f03f3` (same SHA as the Inventory project). `setup_sde.py` bootstraps it via submodule init or a pinned tarball fallback if missing.
- **Schema is unchanged** — the converter produces the classic SDE schema (`invTypes`, `dgmTypeAttributes`, `mapSolarSystems`, `mapSolarSystemJumps`) with identical column names, so `skill_checker.py` and `app.py` queries needed **no changes**.
- **`config.py`** — `SDE_DATABASE_PATH` now points at `data/sqlite-latest.sqlite` (absolute path) instead of `sde.sqlite.db` in the root.
- **`app.py`** — `startup()` now fails fast with a "run setup_sde.py" message if the SDE is absent (no silent multi-minute conversion during Electron boot).
- **`requirements.txt`** — added `requests` and `pyyaml` (used by `setup_sde.py` / the converter subprocess).
- **`.gitignore`** — ignores `data/sqlite-latest.sqlite`, `data/sde-build.txt`, and the converter's intermediate build artifacts.
- **README** — replaced the "Download SDE from Fuzzwork" section with `python setup_sde.py` instructions; updated prerequisites (git), project structure, troubleshooting, and credits.

### Future
- Add an app icon to the Electron window and portable exe
- Bundle Python via PyInstaller for a fully standalone exe (no Python install required)
- Encrypt tokens in database
- **Cyno chain / capital route planner** — use existing cyno-tagged characters to plan jump routes for titans, dreads, blops across the universe

---

**Last Updated**: 2026-06-03
**Status**: Fully functional as Electron desktop app via `npm start`
**Test Character**: Sihcom Repinuj (active, tracking)
