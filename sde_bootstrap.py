"""
SDE Bootstrap — checks for the latest Eve Online Static Data Export and
updates sde.sqlite.db if a newer build is available.

Called automatically at service startup. Safe to run repeatedly; skips the
download if the local build is already current.

Tables built (matching the schema skill_checker.py expects):
  invTypes          (typeID INTEGER PK, typeName TEXT)
  dgmTypeAttributes (typeID INTEGER, attributeID INTEGER, valueInt INTEGER, valueFloat REAL)

Source files in the CCP JSONL zip:
  types.jsonl     → invTypes      (_key = typeID, name.en = typeName)
  typeDogma.jsonl → dgmTypeAttributes  (_key = typeID, dogmaAttributes[].attributeID/value)
"""
import io
import json
import logging
import os
import sqlite3
import zipfile
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_LATEST_URL   = 'https://developers.eveonline.com/static-data/tranquility/latest.jsonl'
_DOWNLOAD_URL = ('https://developers.eveonline.com/static-data/tranquility/'
                 'eve-online-static-data-{build}-jsonl.zip')
_USER_AGENT   = 'ToonTracker-SDE-Bootstrap/1.0 (github.com/sihcom/toon-tracker)'

# Only import dogma attributes needed by skill_checker.py
_WANTED_ATTRIBUTES = frozenset({
    182, 183, 184,    # requireSkill1/2/3 type ID
    277, 278, 279,    # requireSkill1/2/3 level
    1285, 1286, 1287, # requireSkill4/5/6 type ID / level (pairs vary)
    1288, 1289, 1290, # requireSkill4/5/6 level / type ID (pairs vary)
})


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def _fetch(url: str, *, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_latest_build() -> int:
    raw = _fetch(_LATEST_URL)
    for line in raw.decode().splitlines():
        record = json.loads(line)
        if record.get('_key') == 'sde':
            return int(record['buildNumber'])
    raise ValueError('sde record not found in latest.jsonl')


def _read_local_build(version_path: str) -> int | None:
    try:
        with open(version_path, 'r') as f:
            return int(json.load(f)['buildNumber'])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return None


def _write_local_build(version_path: str, build: int) -> None:
    with open(version_path, 'w') as f:
        json.dump({'buildNumber': build}, f)


# ---------------------------------------------------------------------------
# SQLite builder
# ---------------------------------------------------------------------------

def _find_in_zip(zf: zipfile.ZipFile, filename: str) -> str:
    """Return the full path inside the zip for a given filename."""
    match = next((n for n in zf.namelist() if n.endswith(filename)), None)
    if match is None:
        raise FileNotFoundError(
            f'{filename} not found in zip. Available files: {zf.namelist()}'
        )
    return match


def _build_sqlite(zip_bytes: bytes, db_path: str) -> None:
    tmp_path = db_path + '.tmp'

    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        con = sqlite3.connect(tmp_path)
        cur = con.cursor()

        cur.executescript("""
            CREATE TABLE invTypes (
                typeID   INTEGER PRIMARY KEY,
                typeName TEXT
            );
            CREATE TABLE dgmTypeAttributes (
                typeID      INTEGER NOT NULL,
                attributeID INTEGER NOT NULL,
                valueInt    INTEGER,
                valueFloat  REAL,
                PRIMARY KEY (typeID, attributeID)
            );
        """)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:

            # --- types.jsonl → invTypes ---
            # Each record: {"_key": <typeID>, "name": {"en": "...", ...}, ...}
            logger.info('Importing types.jsonl → invTypes...')
            inv_rows = []
            with zf.open(_find_in_zip(zf, 'types.jsonl')) as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    type_id = rec.get('_key')
                    name_field = rec.get('name')
                    if type_id is None or not isinstance(name_field, dict):
                        continue
                    type_name = name_field.get('en')
                    if type_name is not None:
                        inv_rows.append((int(type_id), str(type_name)))

            cur.executemany('INSERT OR REPLACE INTO invTypes VALUES (?, ?)', inv_rows)
            logger.info(f'Imported {len(inv_rows):,} rows into invTypes')

            # --- typeDogma.jsonl → dgmTypeAttributes ---
            # Each record: {"_key": <typeID>, "dogmaAttributes": [{"attributeID": N, "value": F}, ...]}
            # skill_checker.py uses valueInt for skill type IDs and valueFloat for levels.
            # The SDE stores both as a single float "value". Map it to both columns so
            # existing queries (valueInt IS NOT NULL OR valueFloat IS NOT NULL) always hit.
            logger.info('Importing typeDogma.jsonl → dgmTypeAttributes (skill attrs only)...')
            dgm_rows = []
            with zf.open(_find_in_zip(zf, 'typeDogma.jsonl')) as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    type_id = rec.get('_key')
                    if type_id is None:
                        continue
                    for attr in rec.get('dogmaAttributes', []):
                        attr_id = attr.get('attributeID')
                        if attr_id not in _WANTED_ATTRIBUTES:
                            continue
                        value = attr.get('value')
                        if value is None:
                            continue
                        # Store as both int and float so skill_checker.py's
                        # "COALESCE(valueInt, valueFloat)" pattern works either way.
                        value_int   = int(value) if float(value) == int(value) else None
                        value_float = float(value)
                        dgm_rows.append((int(type_id), int(attr_id), value_int, value_float))

            cur.executemany(
                'INSERT OR REPLACE INTO dgmTypeAttributes VALUES (?, ?, ?, ?)',
                dgm_rows,
            )
            logger.info(f'Imported {len(dgm_rows):,} rows into dgmTypeAttributes')

        # Indexes matching skill_checker.py query patterns
        cur.executescript("""
            CREATE INDEX IF NOT EXISTS idx_invTypes_name
                ON invTypes (typeName COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_dgmAttr_type_attr
                ON dgmTypeAttributes (typeID, attributeID);
        """)

        con.commit()
        con.close()

        # Replace the live database. On Windows, os.replace() fails if the
        # destination is locked by another process. Remove it first if it is
        # a zero-byte placeholder (safe to discard — it has no usable data).
        if os.path.exists(db_path):
            if os.path.getsize(db_path) == 0:
                os.remove(db_path)
            else:
                os.replace(tmp_path, db_path)
                logger.info(f'SDE database written to {db_path}')
                return

        os.rename(tmp_path, db_path)
        logger.info(f'SDE database written to {db_path}')

    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ensure_sde(sde_db_path: str) -> None:
    """
    Ensure the local SDE SQLite is present and up to date.
    Blocks until complete. Network errors are logged as warnings and never
    prevent the service from starting (existing database is kept on failure).
    """
    version_path = sde_db_path + '.version'

    try:
        logger.info('Checking SDE version...')
        latest_build = _get_latest_build()
        logger.info(f'Latest SDE build: {latest_build}')

        local_build = _read_local_build(version_path)
        db_exists   = os.path.exists(sde_db_path)

        if db_exists and local_build == latest_build:
            logger.info(f'SDE is current (build {latest_build}) — skipping download.')
            return

        if not db_exists:
            logger.info('sde.sqlite.db not found — performing initial download.')
        else:
            logger.info(f'SDE update available: local={local_build} → latest={latest_build}')

        download_url = _DOWNLOAD_URL.format(build=latest_build)
        logger.info(f'Downloading SDE from {download_url} ...')
        zip_bytes = _fetch(download_url, timeout=300)
        logger.info(f'Download complete ({len(zip_bytes) / 1_048_576:.1f} MB). Building database...')

        _build_sqlite(zip_bytes, sde_db_path)
        _write_local_build(version_path, latest_build)

        logger.info(f'SDE bootstrap complete — build {latest_build} is now active.')

    except urllib.error.URLError as e:
        logger.warning(f'SDE check failed (network): {e}. Using existing database if present.')
    except Exception as e:
        logger.error(f'SDE bootstrap error: {e}', exc_info=True)
