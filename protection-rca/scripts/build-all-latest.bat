@echo off
REM ============================================================
REM  Refresh ALL latest application CODE for packaging:
REM    - backend: use existing .venv (verify imports; no forced --upgrade)
REM    - frontend: npm install + fresh dist
REM    - ProtectionRCA.exe launcher
REM
REM  Note: We do NOT pip --upgrade every build. That tries to rebuild
REM  numpy/scipy from source when no wheel exists (needs Visual Studio).
REM  Latest app code = your .py / TS / rules files + rebuilt UI/EXE.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0.."
set ROOT=%CD%
set PY=%ROOT%\backend\.venv\Scripts\python.exe
if not exist "%PY%" (
  echo ERROR: backend\.venv not found.
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

echo ============================================================
echo  Refresh ALL latest codes
echo  %ROOT%
echo ============================================================

echo.
echo [1/3] Backend — verify existing venv ^(latest .py is used as-is^) ...
"%PY%" -c "import fastapi, uvicorn, numpy, sqlalchemy, yaml; print('venv OK', __import__('sys').version.split()[0])"
if errorlevel 1 (
  echo.
  echo Venv missing packages — installing from requirements.txt ^(wheels only^)...
  "%PY%" -m pip install -r "%ROOT%\backend\requirements.txt" --only-binary=:all:
  if errorlevel 1 (
    echo ERROR: Could not install Python deps ^(no compiler / no wheel^).
    echo Keep using a working backend\.venv — do not use pip --upgrade without VS Build Tools.
    exit /b 1
  )
  "%PY%" -c "import fastapi, uvicorn, numpy; print('venv OK after install')"
  if errorlevel 1 (
    echo ERROR: Backend imports still failing after install.
    exit /b 1
  )
)
"%PY%" -m pip install pyinstaller --quiet
if errorlevel 1 (
  echo ERROR: could not install pyinstaller.
  exit /b 1
)
echo [1/3] Backend OK — live sources in backend\ will be used

echo.
echo [2/3] Frontend — npm install + production build ...
call "%ROOT%\scripts\build-frontend.bat"
if errorlevel 1 (
  echo ERROR: frontend refresh failed.
  exit /b 1
)
echo [2/3] Frontend OK

echo.
echo [3/3] ProtectionRCA.exe — rebuild launcher from latest scripts\launch_webapp.py ...
REM Unlock previous EXE if still running (common Access denied cause)
tasklist /FI "IMAGENAME eq ProtectionRCA.exe" 2>nul | find /I "ProtectionRCA.exe" >nul
if not errorlevel 1 (
  echo Stopping running ProtectionRCA.exe so the file can be replaced...
  taskkill /F /IM ProtectionRCA.exe >nul 2>&1
  timeout /t 2 /nobreak >nul
)
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name ProtectionRCA ^
  --distpath "%ROOT%" ^
  --workpath "%ROOT%\scripts\build\work" ^
  --specpath "%ROOT%\scripts\build" ^
  "%ROOT%\scripts\launch_webapp.py"
if errorlevel 1 (
  echo.
  echo ERROR: PyInstaller failed to build ProtectionRCA.exe
  echo   Usually: Access denied — close ProtectionRCA.exe / Explorer preview, then retry.
  echo   Or run: taskkill /F /IM ProtectionRCA.exe
  exit /b 1
)
if not exist "%ROOT%\ProtectionRCA.exe" (
  echo ERROR: ProtectionRCA.exe not created.
  exit /b 1
)
echo [3/3] EXE OK — %ROOT%\ProtectionRCA.exe

echo.
echo ============================================================
echo  ALL LATEST CODES READY
echo    Backend : %ROOT%\backend  ^(latest .py; existing venv^)
echo    UI      : %ROOT%\frontend\dist
echo    EXE     : %ROOT%\ProtectionRCA.exe
echo    Rules   : %ROOT%\rules
echo ============================================================
endlocal
exit /b 0
