# veda.spec  —  PyInstaller build spec for Veda Scientific Article Editor
# Build:  pyinstaller veda.spec
# Output: dist/veda/veda.exe  (onedir bundle)

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Data files to bundle ─────────────────────────────────────────────────────
datas = [
    # Frontend static assets (HTML, JS, CSS)
    ('frontend', 'frontend'),
    # Backend environment config
    ('backend/.env', 'backend'),
    # citeproc-py locale/schema/style data files
    ('venv/Lib/site-packages/citeproc/data', 'citeproc/data'),
]
# Include pywebview JS assets and Windows WebView2 DLLs (via built-in hook)
datas += collect_data_files('webview', subdir='js')
datas += collect_data_files('webview', subdir='lib')

# ── Hidden imports (dynamically loaded, missed by static analysis) ────────────
hidden_imports = [
    # uvicorn internals
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    # fastapi / starlette internals
    'fastapi',
    'starlette.routing',
    'starlette.staticfiles',
    'starlette.responses',
    'starlette.middleware.cors',
    'multipart',
    'python_multipart',
    # pywebview Windows platform
    'webview',
    'webview.platforms',
    'webview.platforms.winforms',
    'clr',
    'clr_loader',
    # GitPython
    'git',
    'gitdb',
    'gitdb.db',
    'smmap',
    # citeproc
    'citeproc',
    'citeproc.source',
    'citeproc.source.json',
    # misc
    'tkinter',
    'tkinter.filedialog',
    'python_slugify',
    'dotenv',
]

a = Analysis(
    ['backend/main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=['venv/Lib/site-packages/webview/__pyinstaller'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'playwright', 'coverage'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='veda',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # No terminal window — desktop GUI app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='veda',
)
