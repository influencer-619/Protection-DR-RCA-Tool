@echo off
REM ============================================================
REM  Portable share package — ALL latest app codes
REM  Uses scripts\build-all-latest.bat (verify venv, NO pip --upgrade)
REM  then copies backend + frontend\dist + rules + EXE → portable-share\
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."
set "ROOT=%CD%"
set "OUT=%ROOT%\portable-share"
set "LOG=%ROOT%\portable-build-log.txt"

echo ============================================================
echo  Protection RCA — portable share (ALL LATEST CODES)
echo ============================================================
echo  ROOT: %ROOT%
echo  OUT : %OUT%
echo  LOG : %LOG%
echo.
echo  Backend: existing .venv verified ^(no pip --upgrade / no numpy rebuild^)
echo  UI     : fresh frontend\dist from latest sources
echo  EXE    : rebuilt ProtectionRCA.exe
echo ============================================================
echo.

> "%LOG%" echo Protection RCA portable build log
>> "%LOG%" echo Started: %DATE% %TIME%
>> "%LOG%" echo ROOT=%ROOT%
>> "%LOG%" echo Mode=verify-venv-no-pip-upgrade

if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo ERROR: backend\.venv not found.
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  >> "%LOG%" echo ERROR: missing backend\.venv
  goto :fail
)

echo [1/2] Refresh ALL latest codes via build-all-latest.bat ...
call "%ROOT%\scripts\build-all-latest.bat"
if errorlevel 1 (
  echo Full refresh failed ^(same fix as build-exe: no forced numpy rebuild^).
  >> "%LOG%" echo ERROR: build-all-latest failed
  goto :fail
)
if not exist "%ROOT%\ProtectionRCA.exe" (
  echo ERROR: ProtectionRCA.exe missing after refresh.
  >> "%LOG%" echo ERROR: missing EXE
  goto :fail
)
if not exist "%ROOT%\frontend\dist\index.html" (
  echo ERROR: frontend\dist missing after refresh.
  >> "%LOG%" echo ERROR: missing frontend dist
  goto :fail
)
>> "%LOG%" echo build-all-latest OK

echo.
echo [2/2] Assembling portable-share folder...
REM Only replace what this script produces; keep anything else (e.g. sample event folders).
for %%D in (backend frontend rules scripts python) do (
  if exist "%OUT%\%%D" rmdir /s /q "%OUT%\%%D"
)
if exist "%OUT%\ProtectionRCA.exe" del /q "%OUT%\ProtectionRCA.exe"
mkdir "%OUT%" 2>nul
mkdir "%OUT%\backend" 2>nul
mkdir "%OUT%\frontend" 2>nul
mkdir "%OUT%\rules" 2>nul
mkdir "%OUT%\scripts" 2>nul

robocopy "%ROOT%\backend" "%OUT%\backend" /E /XD __pycache__ .pytest_cache htmlcov .mypy_cache storage .venv logs /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy backend failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy backend code=!RC!
  goto :fail
)

REM Bundle a standalone Python (base runtime + venv packages) so the target PC
REM needs no Python install. A venv alone only redirects to the build PC's Python.
set "PYHOME="
for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%\backend\.venv\pyvenv.cfg") do (
  set "K=%%A"
  set "K=!K: =!"
  if /i "!K!"=="home" (
    set "PYHOME=%%B"
  )
)
for /f "tokens=* delims= " %%A in ("!PYHOME!") do set "PYHOME=%%A"
if not exist "!PYHOME!\python.exe" (
  echo ERROR: base Python for backend\.venv not found: "!PYHOME!"
  >> "%LOG%" echo ERROR: base python missing PYHOME=!PYHOME!
  goto :fail
)
echo Bundling Python runtime from "!PYHOME!" ...
>> "%LOG%" echo PYHOME=!PYHOME!
robocopy "!PYHOME!" "%OUT%\python" /E /XD Doc include libs Scripts tcl __pycache__ "!PYHOME!\Lib\test" "!PYHOME!\Lib\site-packages" "!PYHOME!\Lib\idlelib" /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy python runtime failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy python code=!RC!
  goto :fail
)
robocopy "%ROOT%\backend\.venv\Lib\site-packages" "%OUT%\python\Lib\site-packages" /E /XD __pycache__ /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy site-packages failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy site-packages code=!RC!
  goto :fail
)

robocopy "%ROOT%\frontend\dist" "%OUT%\frontend\dist" /E /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy frontend\dist failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy frontend code=!RC!
  goto :fail
)

robocopy "%ROOT%\rules" "%OUT%\rules" /E /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy rules failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy rules code=!RC!
  goto :fail
)

copy /Y "%ROOT%\ProtectionRCA.exe" "%OUT%\ProtectionRCA.exe" >nul
if errorlevel 1 (
  echo Failed to copy ProtectionRCA.exe
  >> "%LOG%" echo ERROR: copy exe failed
  goto :fail
)
copy /Y "%ROOT%\scripts\launch_webapp.py" "%OUT%\scripts\launch_webapp.py" >nul
if exist "%ROOT%\frontend\dist\.build-stamp.txt" (
  copy /Y "%ROOT%\frontend\dist\.build-stamp.txt" "%OUT%\frontend\dist\.build-stamp.txt" >nul
)

> "%OUT%\HOW_TO_RUN.txt" (
  echo Protection RCA — portable package ^(ALL LATEST CODES^)
  echo ======================================================
  echo.
  echo Packaged from current backend .py, rules, frontend\dist,
  echo and ProtectionRCA.exe. Includes its own Python in python\
  echo ^(no Python / Visual Studio / pip install needed on this PC^).
  echo.
  echo START
  echo   1. Copy this whole folder anywhere.
  echo   2. Double-click ProtectionRCA.exe
  echo   3. Browser opens http://127.0.0.1:8001/
  echo   4. Keep the control window open while using the app.
  echo.
  echo LAN SHARE
  echo   Use the LAN URL shown in the control window on other PCs
  echo   on the same network ^(not 127.0.0.1 from other machines^).
  echo.
  echo STOP
  echo   Close the Protection RCA control window.
)

if not exist "%OUT%\ProtectionRCA.exe" goto :fail
if not exist "%OUT%\frontend\dist\index.html" goto :fail
if not exist "%OUT%\python\python.exe" goto :fail
"%OUT%\python\python.exe" -c "import uvicorn, fastapi, sqlalchemy, numpy" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: bundled Python cannot import backend packages - see %LOG%
  goto :fail
)

echo.
echo ============================================================
echo  SUCCESS — portable-share has ALL latest codes
echo  %OUT%
echo ============================================================
>> "%LOG%" echo SUCCESS OUT=%OUT%
>> "%LOG%" echo Finished: %DATE% %TIME%
explorer "%OUT%"
echo.
pause
endlocal
exit /b 0

:fail
echo.
echo ============================================================
echo  BUILD FAILED — see %LOG%
echo ============================================================
>> "%LOG%" echo FAILED: %DATE% %TIME%
echo.
pause
endlocal
exit /b 1
