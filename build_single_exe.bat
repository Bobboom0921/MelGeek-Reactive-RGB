@echo off
setlocal
cd /d "%~dp0"
echo Installing build dependencies...
python -m pip install pyinstaller pywebview pystray pillow numpy PyAudioWPatch soundcard sounddevice hidapi
if errorlevel 1 pause & exit /b 1
echo.
echo Verifying syntax...
python -m py_compile backend\main.py backend\melgeek68_premium_reactive.py backend\melgeek68_direct_hid.py backend\melgeek_native_pressure_probe.py
if errorlevel 1 pause & exit /b 1
echo.
echo Building single-file GUI EXE (no console)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name MelGeekReactiveRGB ^
  --icon assets\MelGeekReactiveRGB.ico ^
  --add-data "assets\MelGeekReactiveRGB.ico;." ^
  --add-data "backend\melgeek_keyboard_params.json;." ^
  --add-data "backend\melgeek_keyboard_params.json;backend" ^
  --add-data "ui\index.html;ui" ^
  --hidden-import hid ^
  --hidden-import soundcard ^
  --hidden-import sounddevice ^
  --hidden-import pyaudiowpatch ^
  --hidden-import numpy ^
  --hidden-import webview ^
  --hidden-import pystray ^
  --hidden-import PIL ^
  --hidden-import melgeek68_premium_reactive ^
  --hidden-import melgeek68_direct_hid ^
  --hidden-import melgeek_native_pressure_probe ^
  backend\main.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
if not exist outputs mkdir outputs
copy /Y dist\MelGeekReactiveRGB.exe outputs\MelGeekReactiveRGB.exe
if not exist outputs\reactive_config.json copy /Y reactive_config.json outputs\reactive_config.json
copy /Y README_USER.md outputs\README_USER.md
copy /Y LICENSE outputs\LICENSE
copy /Y THIRD_PARTY_NOTICES.md outputs\THIRD_PARTY_NOTICES.md
echo.
echo Build complete:
echo outputs\MelGeekReactiveRGB.exe
pause
