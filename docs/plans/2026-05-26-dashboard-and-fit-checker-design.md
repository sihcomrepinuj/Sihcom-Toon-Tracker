# Dashboard & Fit Checker Enhancements — Design Doc

**Date**: 2026-05-26
**Status**: Approved

## Overview

Four dashboard improvements and a fit checker enhancement, plus a backlog revision.

## Batch 1 — Dashboard Quick Wins

### 1. Remove Account Filter Chips

Delete the `#accountFilters` div from `dashboard.html` and all associated JS (`activeAccountFilter`, `rebuildAccountFilterChips`, account chip click handler, account match logic in `applyFilters`). Account filtering is handled by the Grouped view's collapse/expand.

### 2. Layout Toggle: Text to Icons

Replace the "Grouped"/"Loose" text buttons in `.view-toggle` with SVG icon buttons:
- **Grid icon** (2x2 squares) = Grouped
- **List icon** (3 horizontal lines) = Loose

Icons are 20x20 inline SVGs, filled with `var(--color-text-secondary)`, matching the theme toggle style. Tooltips on hover for discoverability.

### 3. Density Toggle: Cards vs Slim

Add a second icon-button pair next to the layout toggle, separated by a subtle divider:
- **Card icon** (large square with inner lines) = Cards (default, current behavior)
- **Slim icon** (stacked thin rows) = Slim

Persists to `localStorage` as `dashboardDensity` (`cards` | `slim`), independent of `dashboardView`.

### 4. Slim View Rendering

In slim mode, each character renders as a horizontal row:
- 32px portrait with online/offline dot (scaled down)
- Character name (bold, left-aligned)
- System name (right-aligned)
- No ship, roles, corp logo, timestamp, or account chip
- Minimal padding (~0.5rem), subtle bottom border, no hover lift
- In grouped+slim: rows sit under account group headers
- In loose+slim: rows stack vertically with no headers
- `.character-grid` switches from CSS grid to flex column when slim is active

## Batch 2 — Fit Checker Injector Breakdown

### Data Layer

- Add `total_sp` (Integer, nullable) to the `Character` model
- Extend poller to store `total_sp` from `GET /characters/{id}/skills/` (already fetched every 24h)
- Migration: `ALTER TABLE characters ADD COLUMN total_sp INTEGER`

### Injector Math

SP gap per missing skill: `rank * 250 * sqrt(32)^(level-1)` (difference between required and current level SP).

Injector tiers based on character's total SP:
- Under 5M SP: 500k per injector
- 5M-50M SP: 400k per injector
- 50M-80M SP: 300k per injector
- Over 80M SP: 150k per injector

Skill rank comes from the SDE database (already used by `skill_checker`).

### API Changes

`/api/check-fit` response adds per-character:
- `injectors_needed` (integer)
- `missing_sp` (total SP gap)

### UI Changes

Saved fit chips: clicking expands a section below showing injector breakdown:
```
4 can fly now
2 need 1 injector
1 needs 2 injectors
0 need 3 injectors
1 needs 4+ injectors
```

Clicking again or clicking another chip collapses it. Main "Check Fit" flow unchanged.

## Revised Backlog

### Batch 1 — Quick wins (this session)
1. Remove account filter chips
2. Layout toggle icons (Grouped/Loose)
3. Density toggle (Cards/Slim)
4. Slim view rendering

### Batch 2 — Fit checker (next session)
5. Store total_sp per character
6. Injector math in /api/check-fit
7. Expandable injector breakdown UI

### Future (on backlog)
- App icon for Electron window/exe
- Bundle Python via PyInstaller
- Encrypt tokens in database
- Cyno chain / capital route planner

### Dropped
- Skill queue display
- Wallet balance
- Location history + alerts
- Auto-updater
- Code signing
- Type hints
- Unit tests
- ESI client extraction

### Already Done (mark complete)
- Dark mode theme
