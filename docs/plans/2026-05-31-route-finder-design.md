# Route Finder — Design Doc

**Date**: 2026-05-31
**Status**: Approved

## Overview

New `/routes` page that answers "who's closest to X?" — the user types a destination system, and the app shows all characters ranked by jump count.

## Approach

ESI API calls per character (Approach A). The backend calls `GET /route/{origin}/{destination}/` once per character in parallel via `aiohttp`. Simple, accurate, no local graph needed. May revisit with a local BFS graph (Approach B) if future features like cyno chain planning require it.

## Page & Navigation

- New `/routes` route rendering `templates/routes.html`
- Nav link "Routes" added to `base.html` between "Fit Checker" and "Settings"

## System Autocomplete

- New endpoint: `GET /api/systems?q=<term>`
- Queries SDE `mapSolarSystems` table: `solarSystemName LIKE 'term%'` (case-insensitive)
- Returns up to 10 matches: `[{"id": 30000142, "name": "Jita"}, ...]`
- Frontend: text input with dropdown, 250ms debounce, triggers after 2+ characters
- Wormhole systems handled gracefully (ESI returns error for unreachable systems)

## Route Calculation

- New endpoint: `POST /api/routes` with body `{"destination_id": 30000142}`
- Loads all characters + their `solar_system_id` from `LocationCache`
- Fires parallel `aiohttp` GET requests to `https://esi.evetech.net/latest/route/{origin}/{destination}/`
- ESI returns array of system IDs; jump count = `len(route) - 1`
- Characters already at destination: `jumps: 0`
- Characters with no location or ESI error: `jumps: null` (sort to bottom)
- Response sorted by jump count ascending:

```json
[
  {"character_id": 123, "name": "Sihcom Repinuj", "system": "Perimeter", "jumps": 1, "online": true, "portrait_url": "..."},
  {"character_id": 456, "name": "Alt Toon", "system": "Amarr", "jumps": 9, "online": false, "portrait_url": "..."}
]
```

- Route preference: shortest only (no user toggle)
- Async pattern: synchronous Flask route calls `asyncio.run()` on an async function, same as the poller

## Results UI

- Compact rows similar to dashboard slim view:
  - 32px portrait with online/offline dot
  - Character name
  - Current system
  - Jump count (integer, or "—" for unreachable)
- Header above table: "Distance to {system name}"
- Loading spinner during ESI calls
- Empty state if no characters added
- No route visualization or system-by-system path

## Not Included

- Route preferences (secure/insecure toggle)
- Route caching
- Path visualization / system list
- Local jump graph (deferred to potential future work)
