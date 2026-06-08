"""
ToonTracker Background Service entry point.

Run this instead of app.py to start the headless background service.
It binds to 127.0.0.1:SERVICE_PORT (default 5000) and writes logs to
toontracker-service.log alongside the executable.

When frozen by PyInstaller (onefile), bundled assets (templates/, static/)
are extracted to sys._MEIPASS. User data (.env, databases) is read from
the directory containing the exe.
"""
import os
import sys

# --- Path resolution ---------------------------------------------------------
# _exe_dir: writable directory next to the exe — holds .env, tracker.db, logs.
# _bundle_dir: read-only directory where PyInstaller extracts bundled files.
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    _bundle_dir = sys._MEIPASS
else:
    _exe_dir = os.path.dirname(os.path.abspath(__file__))
    _bundle_dir = _exe_dir

# --- Load .env before any project imports ------------------------------------
from dotenv import load_dotenv
load_dotenv(os.path.join(_exe_dir, '.env'))

# --- Logging -----------------------------------------------------------------
import logging

_log_path = os.path.join(_exe_dir, 'toontracker-service.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SERVICE] %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(_log_path, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# --- Import app and fix template/static paths for frozen builds --------------
from app import app, startup
from config import Config

# When frozen, Flask resolves templates/static relative to app.py's location
# inside _MEIPASS. Explicitly point it at the extracted bundle directories.
app.template_folder = os.path.join(_bundle_dir, 'templates')
app.static_folder   = os.path.join(_bundle_dir, 'static')

if __name__ == '__main__':
    logger.info("=== Sihcom Toon Tracker Background Service Starting ===")
    logger.info(f"Log file: {_log_path}")
    logger.info(f"Binding to 127.0.0.1:{Config.SERVICE_PORT}")

    # Check for SDE updates before starting Flask.
    # Runs synchronously; network errors are logged but never fatal.
    from sde_bootstrap import ensure_sde
    ensure_sde(Config.SDE_DATABASE_PATH)

    if not startup():
        logger.error("Startup failed — check configuration and try again.")
        sys.exit(1)

    app.run(
        debug=False,
        host='127.0.0.1',
        port=Config.SERVICE_PORT,
        use_reloader=False,
    )
