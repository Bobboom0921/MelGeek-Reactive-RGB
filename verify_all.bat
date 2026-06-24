@echo off
setlocal
cd /d "%~dp0"
if not exist outputs mkdir outputs
echo Running full project verification on Windows files...
python -m py_compile work\melgeek68_premium_reactive.py work\melgeek68_direct_hid.py work\melgeek_native_pressure_probe.py work\reactive_control_panel_modern.py work\melgeek_local_webhid_pressure_server.py work\scan_loopback_devices.py work\verify_all.py
if errorlevel 1 (
  echo Syntax verification failed.
  pause
  exit /b 1
)
python work\verify_all.py > outputs\verify_all.log 2>&1
type outputs\verify_all.log
if errorlevel 1 (
  echo Full verification failed.
  pause
  exit /b 1
)
echo Full verification OK.
pause
