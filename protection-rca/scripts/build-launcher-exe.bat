@echo off
setlocal
cd /d "%~dp0.."
set ROOT=%CD%
set PY=%ROOT%\backend\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo Building ProtectionRCA.exe ...
"%PY%" -m pip install pyinstaller --quiet
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name ProtectionRCA ^
  --distpath "%ROOT%" ^
  --workpath "%ROOT%\scripts\build\work" ^
  --specpath "%ROOT%\scripts\build" ^
  "%ROOT%\scripts\launch_webapp.py"

if exist "%ROOT%\ProtectionRCA.exe" (
  echo.
  echo Created: %ROOT%\ProtectionRCA.exe
  echo Double-click it to start the web app.
) else (
  echo Build failed.
  exit /b 1
)
endlocal
