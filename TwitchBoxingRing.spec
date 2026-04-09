# TwitchBoxingRing.spec
# PyInstaller spec for Twitch Boxing Ring.
# Compatible with PyInstaller 6+
#
# Run with: pyinstaller TwitchBoxingRing.spec
# Or use:   python build.py

from PyInstaller.utils.hooks import collect_submodules

# Collect all submodules from websockets and aiohttp so dynamic imports work
hidden_imports = (
    collect_submodules('websockets') +
    collect_submodules('aiohttp') +
    collect_submodules('aiosignal') +
    collect_submodules('frozenlist') +
    collect_submodules('multidict') +
    collect_submodules('yarl') +
    ['rumble', 'rumble.main', 'rumble.auth', 'rumble.eventsub', 'rumble.config']
)

# Data files bundled inside the executable.
# These are read-only internal copies — user-editable copies are placed
# alongside the executable by build.py / the GitHub Actions workflow.
# Format: (source_path, dest_folder_inside_bundle)
datas = [
    ('configs/typechart.json',  'configs'),
    ('configs/movepool.json',   'configs'),
    ('web/overlay.html',        'web'),
    ('web/overlay.css',         'web'),
    ('web/overlay.js',          'web'),
]

a = Analysis(
    ['rumble/main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# PyInstaller 6: PYZ takes only a.pure — zlib_data and cipher are removed
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TwitchBoxingRing',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
