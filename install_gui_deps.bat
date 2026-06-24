@echo off
setlocal
cd /d "%~dp0"
echo Installing GUI dependencies...
echo This installs PySide6. WebEngine is verified after install because recent PySide6 builds may include it without a separate PySide6-WebEngine package.
python -m pip install PySide6
echo.
echo Verifying PySide6 + WebEngine...
python -c "import PySide6; import PySide6.QtWebEngineWidgets; print('PySide6 + WebEngine OK')"
if errorlevel 1 (
  echo WebEngine import failed. Your PySide6 build may not include QtWebEngine.
  pause
  exit /b 1
)
pause
