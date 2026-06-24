@echo off
setlocal
cd /d "%~dp0"
echo Make sure music/system audio is playing now.
echo Scanning soundcard loopback speakers...
python -m py_compile work\scan_loopback_devices.py
if errorlevel 1 pause & exit /b 1
python work\scan_loopback_devices.py
pause
