# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('settings.json', '.')
    ],
    hiddenimports=[
        'winshell',
        'win32com.client',
        'pystray._win32',
        'win11toast',
        'customtkinter',
        'PIL._tkinter_finder',
        'bs4',
        'lxml'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy', 'IPython',
        'jupyter', 'notebook', 'pytest', 'unittest', 'test', 'tkinter.test'
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Freelance Tracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # CRITICAL: Disabled — prevents AV false positives & Python 3.13 crashes
    console=False,      # Windowed — no CMD window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icons\\FWT.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,          # CRITICAL: Disabled for AV safety
    upx_exclude=[],
    name='Freelance Tracker',
)
