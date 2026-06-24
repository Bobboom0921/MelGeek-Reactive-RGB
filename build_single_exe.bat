@echo off
setlocal
cd /d "%~dp0"
echo Installing build dependencies...
python -m pip install pyinstaller PySide6 numpy PyAudioWPatch soundcard sounddevice hidapi
if errorlevel 1 pause & exit /b 1
echo Verifying WebEngine availability...
python -c "import PySide6.QtWebEngineWidgets; print('QtWebEngineWidgets OK')"
if errorlevel 1 (
  echo QtWebEngineWidgets import failed. Your PySide6 build may not include WebEngine.
  pause
  exit /b 1
)
echo.
echo Verifying syntax...
python -m py_compile work\reactive_control_panel_modern.py work\melgeek68_premium_reactive.py work\melgeek68_direct_hid.py work\melgeek_native_pressure_probe.py work\melgeek_local_webhid_pressure_server.py work\scan_loopback_devices.py work\verify_all.py
if errorlevel 1 pause & exit /b 1
echo Verifying full project...
if not exist outputs mkdir outputs
python work\verify_all.py > outputs\verify_all.log 2>&1
type outputs\verify_all.log
if errorlevel 1 pause & exit /b 1
echo.
echo Building single-file GUI EXE (no console)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name MelGeekReactiveRGB ^
  --add-data "work\melgeek_keyboard_params.json;." ^
  --add-data "work\melgeek_keyboard_params.json;work" ^
  --hidden-import hid ^
  --hidden-import soundcard ^
  --hidden-import sounddevice ^
  --hidden-import pyaudiowpatch ^
  --hidden-import numpy ^
  --hidden-import PySide6.QtWebEngineWidgets ^
  --hidden-import PySide6.QtWebEngineCore ^
  --hidden-import melgeek68_premium_reactive ^
  --hidden-import melgeek68_direct_hid ^
  --hidden-import melgeek_native_pressure_probe ^
  --hidden-import melgeek_local_webhid_pressure_server ^
  work\reactive_control_panel_modern.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
copy /Y dist\MelGeekReactiveRGB.exe outputs\MelGeekReactiveRGB.exe
if not exist outputs\reactive_config.json copy /Y reactive_config.json outputs\reactive_config.json
copy /Y README_USER.md outputs\README_USER.md
copy /Y LICENSE outputs\LICENSE
copy /Y THIRD_PARTY_NOTICES.md outputs\THIRD_PARTY_NOTICES.md
echo.
echo Verifying frozen EXE can load bundled data...
outputs\MelGeekReactiveRGB.exe --run-effect outputs\reactive_config.json --seconds 0.2 --dry-run --no-pressure --no-audio
if errorlevel 1 (
  echo Frozen EXE verification failed.
  pause
  exit /b 1
)
echo.
echo Build complete:
echo outputs\MelGeekReactiveRGB.exe
pause
