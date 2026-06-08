# PyInstaller spec for ToonTracker-Service.exe  (PyInstaller 6.x)
# Build: python -m PyInstaller service.spec --clean --noconfirm
#
# After building, place the following next to dist\ToonTracker-Service.exe:
#   .env          (EVE API credentials)
#   sde.sqlite.db (EVE static data — https://www.fuzzwork.co.uk/dump/)
#   tracker.db    (created automatically on first run if absent)

a = Analysis(
    ['service.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static',    'static'),
        # .env is NOT bundled — it must sit next to the exe, writable by the user.
    ],
    hiddenimports=[
        'sde_bootstrap',
        'flask',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.middleware.proxy_fix',
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.pool',
        'sqlalchemy.orm',
        'sqlalchemy.event',
        'sqlalchemy.engine',
        'aiohttp',
        'aiohttp.connector',
        'preston',
        'dotenv',
        'python_dotenv',
        'pkg_resources',
        'email.mime.text',
        'email.mime.multipart',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'PyQt5',
        'wx',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ToonTracker-Service',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # Silent — no terminal window. Logs → toontracker-service.log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Replace with path to a .ico file when available.
)
