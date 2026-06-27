@echo off
setlocal
cd /d "%~dp0"
echo Installing GUI dependencies for WebView2 desktop app...
python -m pip install pywebview pystray pillow
if errorlevel 1 (
  echo Installation failed.
  pause
  exit /b 1
)
echo.
echo Verifying pywebview + pystray...
python -c "import webview; import pystray; from PIL import Image; print('pywebview + pystray + pillow OK')"
if errorlevel 1 (
  echo Verification failed.
  pause
  exit /b 1
)
pause
