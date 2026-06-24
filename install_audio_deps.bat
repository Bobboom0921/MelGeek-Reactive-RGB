@echo off
setlocal
cd /d "%~dp0"
echo Installing audio dependencies for MelGeek reactive effect...
echo This installs numpy, PyAudioWPatch WASAPI loopback, sounddevice fallback, and soundcard fallback capture.
python -m pip install --upgrade pip
python -m pip install numpy PyAudioWPatch sounddevice soundcard
echo.
echo Verifying installation...
python -c "import numpy, pyaudiowpatch, sounddevice, soundcard as sc; print('numpy', numpy.__version__); print('pyaudiowpatch ok'); print('sounddevice', sounddevice.__version__); print('soundcard ok'); print('default speaker:', sc.default_speaker()); print('all speakers:', sc.all_speakers())"
echo.
echo If you see default speaker and speaker list above, audio dependencies are ready.
pause
