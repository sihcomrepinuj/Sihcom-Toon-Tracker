# Design — Organize Characters by Account

**Date:** 2026-05-23
**Status:** Approved, awaiting implementation plan
**Scope:** Introduce a first-class `Account` entity so characters can be grouped, filtered, and (in future tasks) tagged with account-level properties such as Alpha/Omega subscription status.

## Motivation

The user manages many EVE characters across several EVE accounts and wants to organize them on the dashboard by account. Co-opting the existing `Role` tags was rejected because:

- Roles are many-to-many and AND-filterable. Account membership is single-value per character.
- Accounts have their own properties (subscription type, notes) that don't fit a tag model.
- A first-class `Account` entity also unlocks future features (Alpha/Omega badge, account-scoped notifications, account-level home location, etc.).

## Data Model

New `Account` table:

```python
class Account(Base):
    __tablename__ = 'accounts'
    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String, nullable=False, unique=True)
    subscription = Column(String, nullable=False, default='unknown')  # 'omega' | 'alpha' | 'unknown'
    notes        = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    characters   = relationship('Character', back_populates='account')
```

`Character` gains a nullable FK:

```python
account_id = Column(Integer, ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True)
account    = relationship('Account', back_populates='characters')
```

Rationale:
- `subscription` ships now (defaulted to `'unknown'`) so the Alpha/Omega task does not require a second migration.
- `account_id` is nullable → "Unassigned" is a valid state.
- `ON DELETE SET NULL` → deleting an account moves its characters to Unassigned rather than deleting them. Safer than cascade-delete; less friction than blocking deletion.
- Migration is a one-shot script (`CREATE TABLE accounts`, `ALTER TABLE characters ADD COLUMN account_id`). SQLite handles both without rewriting existing rows.

## API

New endpoints (mirrors the existing role endpoints):

| Route | Method | Purpose |
|---|---|---|
| `/api/accounts` | GET | List accounts (id, name, subscription, character count) |
| `/api/accounts` | POST | Create account (`name`, optional `subscription`, optional `notes`) |
| `/api/accounts/<id>` | PATCH | Edit name / subscription / notes |
| `/api/accounts/<id>` | DELETE | Delete account; characters become Unassigned via SET NULL |
| `/api/characters/<id>/account` | PUT | Assign character to an account (`{account_id: int \| null}`) |

Modified endpoints:
- `GET /api/locations` — response gains `account_id`, `account_name`, `account_subscription` per character so the dashboard renders groups and chips without a second fetch.
- `GET /settings` — template context gains the account list for assignment dropdowns.

Validation:
- `name` required, trimmed, unique; 422 on conflict.
- `subscription` constrained to `{'omega','alpha','unknown'}`; 422 otherwise.
- `PUT .../account` accepts `null` to unassign.

## Settings UI

Two additions to `templates/settings.html`:

**1. New "Accounts" section** (above the existing Characters list)
- List of accounts with inline-edit name / subscription / notes.
- `[+ New Account]` opens an inline form (name + subscription dropdown + notes).
- Delete button shows confirm: *"Move N characters to Unassigned and delete this account?"*

**2. Per-character account dropdown** on each character row
- Options: `— Unassigned —` then all existing accounts.
- Change handler PUTs to `/api/characters/<id>/account` immediately, no save button (matches existing role-assignment UX).

## Dashboard UI

**View toggle** in the dashboard header, next to the search bar. Persisted in `localStorage` as `dashboardView`. Defaults to **Grouped** on first load (since organizing by account is the whole point of the feature).

**Grouped view**
- One `.character-grid` per account, preceded by an `<h2>` header.
- Header shows account name (links to `/settings#account-<id>`), subscription badge (gold for Omega, gray for Alpha, hidden for Unknown), character count.
- Headers are collapsible. Collapsed state persisted per-account in `localStorage`.
- Final group is always "Unassigned" if any character has `account_id IS NULL`.

**Loose view** (current layout + two additions)
- Single flat `.character-grid` of all characters (unchanged behavior).
- New **account filter row** above the search bar — single-select chips (`[All] [Main] [Alt] [Unassigned]`), styled like the existing role chips.
- Each card gains a small account chip alongside the existing role chips, showing account name + subscription glyph.

**Filter / search interaction** (consistent with existing AND-logic):
- Role chips ∧ Account filter ∧ Search text → all must match.
- Search now also matches account name (extends `data-account` attribute).
- Existing "Showing X of Y characters" result count works in both views.

**JS structure**
- `applyFilters()` extended to account-chip state.
- `renderGrouped()` / `renderLoose()` split out, called by the view toggle and by `updateCharacterDisplay()` (the existing 60s refresh path).

## Error Handling

- **Duplicate account name** → 422 → form-level toast "Account name already exists".
- **Invalid subscription** → 422; shouldn't happen via UI (fixed dropdown).
- **Assigning to a deleted account** (cross-tab race) → 404 → toast "Account no longer exists, refreshing" and re-fetch dropdown options.
- **Migration failure on startup** → log + abort. Migration is idempotent (checks `PRAGMA table_info`), so re-running is safe.
- **Orphaned `account_id`** (defensive, should not occur with FK) → treat as Unassigned.

## Edge Cases

- **Zero accounts** → Grouped view renders only an "Unassigned" group; Loose view's account chips show only `[All] [Unassigned]`.
- **Account renamed while dashboard is open** → next `/api/locations` poll (60s) refreshes naturally; no push.
- **View toggle with active search/filter** → state persists; only layout swaps.
- **All groups collapsed** → no special case.

## Testing

Project has no existing test suite. Recommendation: add a single `tests/test_accounts.py` covering the new API surface (create / list / patch / delete / assign), using Flask's test client against a temp SQLite file. Small scope, no broader fixtures needed. Justified because the `Account` entity is load-bearing for several upcoming features (Alpha/Omega detection, home-location, notifications grouping).

Additionally:
- **Manual smoke-test checklist** in the PR: create account → assign char → group appears → rename → delete → char goes Unassigned → toggle view → search → filter.
- **Migration safety**: verify against a backup copy of `tracker.db` before merging.

## Out of Scope (deferred)

- Alpha/Omega auto-detection logic (backlog task #9) — schema is ready, computation comes later.
- Account-level notifications, account-level home location — separate backlog items.
- Enforcing the EVE 3-character-per-account limit — not enforced; user may have legacy accounts.

## Backlog Order (after this feature)

1. Fix character deletion bug
2. Add "home" location per character
3. Alpha/Omega auto-detection
4. Skill queue & training threshold notifications
5. Fit checker — skill-set templates with auto-generated tags
6. Mapping / wayfinding
