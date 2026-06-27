# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['backend\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets\\MelGeekReactiveRGB.ico', '.'), ('backend\\melgeek_keyboard_params.json', '.'), ('backend\\melgeek_keyboard_params.json', 'backend'), ('ui\\index.html', 'ui')],
    hiddenimports=['hid', 'soundcard', 'sounddevice', 'pyaudiowpatch', 'numpy', 'webview', 'pystray', 'PIL', 'melgeek68_premium_reactive', 'melgeek68_direct_hid', 'melgeek_native_pressure_probe'],
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
    icon=['assets\\MelGeekReactiveRGB.ico'],
)
