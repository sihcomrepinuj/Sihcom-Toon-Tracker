# Route Finder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `/routes` page where the user types a destination system and sees all characters ranked by jump count (closest first).

**Architecture:** New Flask route + two API endpoints. `GET /api/systems?q=` queries the SDE for autocomplete. `POST /api/routes` fires parallel ESI `GET /route/{origin}/{destination}/` calls via `aiohttp` (one per character), returns characters sorted by jump count. Frontend is a new Jinja template with vanilla JS autocomplete and a results table.

**Tech Stack:** Flask, aiohttp, SQLite (SDE), ESI public route endpoint, vanilla JS.

---

### Task 1: Add nav link and page route

**Files:**
- Modify: `templates/base.html:21` (add nav link)
- Modify: `app.py:48-56` (add route handler, between fits and settings)
- Create: `templates/routes.html`

**Step 1: Add the nav link to `base.html`**

In `templates/base.html`, after the Fit Checker link (line 21) and before the Settings link (line 22), add:

```html
<a href="{{ url_for('routes') }}" class="nav-link {% if request.endpoint == 'routes' %}active{% endif %}">Routes</a>
```

**Step 2: Add the Flask route in `app.py`**

After the `fits()` route (around line 56) and before the `settings()` route, add:

```python
@app.route('/routes')
def routes():
    """Route finder page."""
    return render_template('routes.html')
```

**Step 3: Create `templates/routes.html`**

```html
{% extends "base.html" %}

{% block title %}Routes - Sihcom Toon Tracker{% endblock %}

{% block content %}
<div class="route-finder">
    <div class="route-input-section">
        <h2>Find Closest Characters</h2>
        <div class="system-search-wrapper">
            <input type="text" id="systemSearch" class="system-search-input"
                   placeholder="Type a system name..." autocomplete="off">
            <div class="system-dropdown" id="systemDropdown"></div>
        </div>
    </div>

    <div class="route-results" id="routeResults" style="display: none;">
        <h3 id="routeHeader">Distance to ...</h3>
        <div class="route-list" id="routeList"></div>
    </div>

    <div class="route-loading" id="routeLoading" style="display: none;">
        <div class="spinner"></div>
        <span>Calculating routes...</span>
    </div>

    <div class="route-empty" id="routeEmpty" style="display: none;">
        <p>No characters added yet.</p>
        <p><a href="/settings">Add a character</a> to get started.</p>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    /* JS will be added in Task 4 */
</script>
{% endblock %}
```

**Step 4: Verify**

Run `python app.py`, navigate to `http://localhost:5000/routes`. Confirm the page loads with the search input visible and the "Routes" nav link is highlighted.

**Step 5: Commit**

```
feat: add routes page skeleton and nav link
```

---

### Task 2: System autocomplete endpoint

**Files:**
- Modify: `app.py` (add endpoint after the notepad API section, before APPLICATION STARTUP)

**Step 1: Add `GET /api/systems` endpoint in `app.py`**

Add a new API section and endpoint. Place it after the Notepad API section (after line 707) and before the APPLICATION STARTUP section:

```python
# ============================================================================
# API ROUTES - Route Finder
# ============================================================================

@app.route('/api/systems')
def api_search_systems():
    """Search solar systems by name prefix for autocomplete."""
    import sqlite3
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    try:
        conn = sqlite3.connect(Config.SDE_DATABASE_PATH)
        cursor = conn.execute(
            "SELECT solarSystemID, solarSystemName FROM mapSolarSystems "
            "WHERE solarSystemName LIKE ? COLLATE NOCASE ORDER BY solarSystemName LIMIT 10",
            (query + '%',)
        )
        results = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
        conn.close()
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error searching systems: {e}", exc_info=True)
        return jsonify([])
```

**Step 2: Verify**

Run the app, then in a browser or terminal:
```
curl "http://localhost:5000/api/systems?q=Ji"
```
Expected: JSON array containing `{"id": 30000142, "name": "Jita"}` and other systems starting with "Ji".

Test edge cases:
- `?q=` (empty) returns `[]`
- `?q=X` (1 char) returns `[]`
- `?q=zzzzzz` (no match) returns `[]`

**Step 3: Commit**

```
feat: add system autocomplete endpoint querying SDE
```

---

### Task 3: Route calculation endpoint

**Files:**
- Modify: `app.py` (add endpoint in the Route Finder API section, after the systems endpoint)

**Step 1: Add `POST /api/routes` endpoint**

Add this below the `api_search_systems` function:

```python
@app.route('/api/routes', methods=['POST'])
def api_calculate_routes():
    """Calculate jump distance from all characters to a destination system."""
    data = request.json or {}
    destination_id = data.get('destination_id')

    if not destination_id:
        return jsonify({'error': 'destination_id is required'}), 400

    db_session = get_session()
    characters = db_session.query(Character).all()

    if not characters:
        db_session.close()
        return jsonify({'results': [], 'empty': True})

    # Build list of characters with their current system
    char_data = []
    for char in characters:
        location = char.location
        char_data.append({
            'id': char.id,
            'name': char.name,
            'system_id': location.solar_system_id if location else None,
            'system_name': location.solar_system_name if location else 'Unknown',
            'online': location.is_online if location else False,
            'portrait_url': f'https://images.evetech.net/characters/{char.id}/portrait?size=64',
        })
    db_session.close()

    # Calculate routes in parallel via asyncio
    async def fetch_routes():
        async with aiohttp.ClientSession() as http_session:
            tasks = []
            for c in char_data:
                tasks.append(get_route(http_session, c, destination_id))
            return await asyncio.gather(*tasks)

    async def get_route(http_session, char_info, dest_id):
        origin_id = char_info['system_id']
        if origin_id is None:
            return {**char_info, 'jumps': None}
        if origin_id == dest_id:
            return {**char_info, 'jumps': 0}
        try:
            url = f'https://esi.evetech.net/latest/route/{origin_id}/{dest_id}/'
            async with http_session.get(url) as resp:
                if resp.status == 200:
                    route = await resp.json()
                    return {**char_info, 'jumps': len(route) - 1}
                else:
                    return {**char_info, 'jumps': None}
        except Exception:
            return {**char_info, 'jumps': None}

    import aiohttp as _aiohttp
    results = asyncio.run(fetch_routes())

    # Sort: by jumps ascending, None values at the end
    results = sorted(results, key=lambda r: (r['jumps'] is None, r['jumps'] or 0))

    return jsonify({'results': results})
```

Note: `aiohttp` is already imported at the top of `poller.py` but not in `app.py`. Add `import aiohttp` to the top of `app.py` with the other imports.

**Step 2: Add `aiohttp` import to top of `app.py`**

At the top of `app.py` (line 3 area, after `import asyncio`), `aiohttp` is not needed as a top-level import since we import it locally inside the function. Actually, cleaner to just use a top-level import. Add after `import asyncio`:

```python
import aiohttp
```

**Step 3: Verify**

With the app running:
```
curl -X POST http://localhost:5000/api/routes -H "Content-Type: application/json" -d "{\"destination_id\": 30000142}"
```
Expected: JSON with `results` array, each entry having `character_id`, `name`, `system`, `jumps`, `online`, `portrait_url`. Results sorted by jumps ascending.

**Step 4: Commit**

```
feat: add route calculation endpoint with parallel ESI calls
```

---

### Task 4: Frontend autocomplete and route display

**Files:**
- Modify: `templates/routes.html` (replace placeholder script block)
- Modify: `static/style.css` (add route finder styles)

**Step 1: Add JavaScript to `templates/routes.html`**

Replace the `{% block scripts %}` section with:

```html
{% block scripts %}
<script>
    const searchInput = document.getElementById('systemSearch');
    const dropdown = document.getElementById('systemDropdown');
    const routeResults = document.getElementById('routeResults');
    const routeList = document.getElementById('routeList');
    const routeHeader = document.getElementById('routeHeader');
    const routeLoading = document.getElementById('routeLoading');
    const routeEmpty = document.getElementById('routeEmpty');

    let debounceTimer = null;
    let selectedSystemId = null;
    let selectedSystemName = '';

    // Autocomplete: search as user types
    searchInput.addEventListener('input', () => {
        const query = searchInput.value.trim();
        clearTimeout(debounceTimer);

        if (query.length < 2) {
            dropdown.innerHTML = '';
            dropdown.style.display = 'none';
            return;
        }

        debounceTimer = setTimeout(async () => {
            try {
                const resp = await fetch(`/api/systems?q=${encodeURIComponent(query)}`);
                const systems = await resp.json();
                renderDropdown(systems);
            } catch (e) {
                console.error('Autocomplete error:', e);
            }
        }, 250);
    });

    // Enter key selects top result
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const firstItem = dropdown.querySelector('.system-option');
            if (firstItem) firstItem.click();
        }
        if (e.key === 'Escape') {
            dropdown.style.display = 'none';
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.system-search-wrapper')) {
            dropdown.style.display = 'none';
        }
    });

    function renderDropdown(systems) {
        if (!systems.length) {
            dropdown.innerHTML = '<div class="system-option no-results">No systems found</div>';
            dropdown.style.display = 'block';
            return;
        }

        dropdown.innerHTML = systems.map(s =>
            `<div class="system-option" data-id="${s.id}" data-name="${s.name}">${s.name}</div>`
        ).join('');
        dropdown.style.display = 'block';

        dropdown.querySelectorAll('.system-option[data-id]').forEach(opt => {
            opt.addEventListener('click', () => {
                selectedSystemId = parseInt(opt.dataset.id);
                selectedSystemName = opt.dataset.name;
                searchInput.value = selectedSystemName;
                dropdown.style.display = 'none';
                calculateRoutes();
            });
        });
    }

    async function calculateRoutes() {
        if (!selectedSystemId) return;

        routeResults.style.display = 'none';
        routeEmpty.style.display = 'none';
        routeLoading.style.display = 'flex';

        try {
            const resp = await fetch('/api/routes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ destination_id: selectedSystemId })
            });
            const data = await resp.json();

            routeLoading.style.display = 'none';

            if (data.empty) {
                routeEmpty.style.display = 'block';
                return;
            }

            routeHeader.textContent = `Distance to ${selectedSystemName}`;
            renderResults(data.results);
            routeResults.style.display = 'block';

        } catch (e) {
            console.error('Route calculation error:', e);
            routeLoading.style.display = 'none';
        }
    }

    function renderResults(results) {
        routeList.innerHTML = results.map((r, i) => {
            const dotClass = r.online ? 'online' : 'offline';
            const jumpsText = r.jumps !== null ? r.jumps : '—';
            const jumpsUnit = r.jumps !== null ? (r.jumps === 1 ? 'jump' : 'jumps') : '';

            return `
                <div class="route-row">
                    <span class="route-rank">${i + 1}</span>
                    <div class="route-portrait">
                        <img src="${r.portrait_url}" class="small-portrait" alt="">
                        <span class="status-dot ${dotClass}"></span>
                    </div>
                    <span class="route-name">${r.name}</span>
                    <span class="route-system">${r.system_name}</span>
                    <span class="route-jumps">${jumpsText} <small>${jumpsUnit}</small></span>
                </div>
            `;
        }).join('');
    }
</script>
{% endblock %}
```

**Step 2: Add CSS to `static/style.css`**

Append the following at the end of `style.css`:

```css
/* ============================================
   Route Finder
   ============================================ */

.route-finder {
    max-width: 700px;
    margin: 0 auto;
}

.route-input-section h2 {
    margin-bottom: 1rem;
    color: var(--color-text-heading);
}

.system-search-wrapper {
    position: relative;
    max-width: 400px;
}

.system-search-input {
    width: 100%;
    padding: 0.6rem 1rem;
    border: 1px solid var(--color-border-input);
    border-radius: 20px;
    font-size: 0.95rem;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
    outline: none;
    box-sizing: border-box;
}

.system-search-input:focus {
    border-color: var(--color-btn-primary);
    box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.15);
}

.system-dropdown {
    display: none;
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-primary);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 100;
    max-height: 300px;
    overflow-y: auto;
}

.system-option {
    padding: 0.5rem 1rem;
    cursor: pointer;
    font-size: 0.9rem;
    color: var(--color-text-primary);
}

.system-option:hover {
    background: var(--color-bg-hover);
}

.system-option.no-results {
    color: var(--color-text-tertiary);
    cursor: default;
}

.route-results h3 {
    margin: 1.5rem 0 1rem;
    color: var(--color-text-heading);
}

.route-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--color-border-divider);
}

.route-row:last-child {
    border-bottom: none;
}

.route-rank {
    width: 1.5rem;
    text-align: center;
    font-weight: 600;
    font-size: 0.85rem;
    color: var(--color-text-tertiary);
}

.route-portrait {
    position: relative;
    flex-shrink: 0;
    width: 32px;
    height: 32px;
}

.route-portrait .small-portrait {
    width: 32px;
    height: 32px;
    border-radius: 4px;
}

.route-portrait .status-dot {
    position: absolute;
    bottom: -2px;
    right: -2px;
    width: 10px;
    height: 10px;
    border: 2px solid var(--color-bg-surface);
}

.route-name {
    font-weight: 600;
    font-size: 0.9rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.route-system {
    flex: 1;
    text-align: right;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.route-jumps {
    flex-shrink: 0;
    font-weight: 700;
    font-size: 1rem;
    min-width: 5rem;
    text-align: right;
}

.route-jumps small {
    font-weight: 400;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
}

/* Loading spinner */
.route-loading {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 2rem 0;
    color: var(--color-text-secondary);
}

.spinner {
    width: 20px;
    height: 20px;
    border: 2.5px solid var(--color-border-primary);
    border-top-color: var(--color-btn-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.route-empty {
    padding: 2rem 0;
    color: var(--color-text-secondary);
}
```

**Step 3: Verify**

Run the app, go to `/routes`. Type "Jita" into the search input. Confirm:
- Autocomplete dropdown appears after typing "Ji" (250ms delay)
- Clicking "Jita" triggers route calculation
- Loading spinner shows during ESI calls
- Results table appears with characters ranked by jump count
- Online/offline dots display correctly
- Unreachable characters show "—"

**Step 4: Commit**

```
feat: add route finder autocomplete UI and results table
```

---

### Task 5: Polish and edge cases

**Files:**
- Modify: `templates/routes.html` (minor UX additions)
- Modify: `static/style.css` (responsive tweaks)

**Step 1: Add keyboard navigation for dropdown**

In the `routes.html` script block, enhance the `keydown` listener on `searchInput` to support arrow-key navigation through dropdown options:

```javascript
// Replace the existing keydown listener with:
let highlightIndex = -1;

searchInput.addEventListener('keydown', (e) => {
    const options = dropdown.querySelectorAll('.system-option[data-id]');

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        highlightIndex = Math.min(highlightIndex + 1, options.length - 1);
        updateHighlight(options);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlightIndex = Math.max(highlightIndex - 1, 0);
        updateHighlight(options);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (highlightIndex >= 0 && options[highlightIndex]) {
            options[highlightIndex].click();
        } else if (options[0]) {
            options[0].click();
        }
    } else if (e.key === 'Escape') {
        dropdown.style.display = 'none';
        highlightIndex = -1;
    }
});

function updateHighlight(options) {
    options.forEach((opt, i) => {
        opt.classList.toggle('highlighted', i === highlightIndex);
    });
}
```

Reset `highlightIndex = -1` inside `renderDropdown()` at the top of that function.

**Step 2: Add highlighted style to CSS**

Append to the route finder CSS section:

```css
.system-option.highlighted {
    background: var(--color-bg-hover);
}
```

**Step 3: Add mobile responsive rule**

Append to the route finder CSS section:

```css
@media (max-width: 768px) {
    .system-search-wrapper {
        max-width: 100%;
    }

    .route-jumps {
        min-width: 3.5rem;
    }
}
```

**Step 4: Verify**

- Type "Am" in search, use arrow keys to highlight "Amarr", press Enter — routes calculate
- On narrow viewport (< 768px), search input spans full width
- Pressing Escape closes the dropdown

**Step 5: Commit**

```
feat: add keyboard nav and mobile responsive to route finder
```

---

### Summary of all files touched

| File | Action |
|------|--------|
| `templates/base.html` | Add nav link |
| `app.py` | Add `/routes` page route, `GET /api/systems`, `POST /api/routes`, `import aiohttp` |
| `templates/routes.html` | Create (page template + JS) |
| `static/style.css` | Add route finder styles |
