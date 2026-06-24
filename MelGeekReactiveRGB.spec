# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['work\\reactive_control_panel_modern.py'],
    pathex=[],
    binaries=[],
    datas=[('work\\melgeek_keyboard_params.json', '.'), ('work\\melgeek_keyboard_params.json', 'work')],
    hiddenimports=['hid', 'soundcard', 'sounddevice', 'pyaudiowpatch', 'numpy', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'melgeek68_premium_reactive', 'melgeek68_direct_hid', 'melgeek_native_pressure_probe', 'melgeek_local_webhid_pressure_server'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='MelGeekReactiveRGB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
