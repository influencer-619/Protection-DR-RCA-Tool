@echo off
REM ============================================================
REM  Portable share package — ALL latest app codes
REM  Uses scripts\build-all-latest.bat (verify venv, NO pip --upgrade)
REM  then copies backend + frontend\dist + rules + templates + EXE → portable-share\
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
for %%D in (backend frontend rules templates scripts python) do (
  if exist "%OUT%\%%D" rmdir /s /q "%OUT%\%%D"
)
if exist "%OUT%\ProtectionRCA.exe" del /q "%OUT%\ProtectionRCA.exe"
mkdir "%OUT%" 2>nul
mkdir "%OUT%\backend" 2>nul
mkdir "%OUT%\frontend" 2>nul
mkdir "%OUT%\rules" 2>nul
mkdir "%OUT%\scripts" 2>nul

REM Exclude developer databases / storage — portable ships blank plant+events.
robocopy "%ROOT%\backend" "%OUT%\backend" /E /XD __pycache__ .pytest_cache htmlcov .mypy_cache storage .venv logs /XF *.db *.db-wal *.db-shm *.sqlite *.sqlite3 /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy backend failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy backend code=!RC!
  goto :fail
)

echo Stripping any leftover DBs / storage so first run is blank...
>> "%LOG%" echo Clearing packaged databases for blank event DB
del /q "%OUT%\backend\*.db" 2>nul
del /q "%OUT%\backend\*.db-wal" 2>nul
del /q "%OUT%\backend\*.db-shm" 2>nul
del /q "%OUT%\backend\*.sqlite" 2>nul
del /q "%OUT%\backend\*.sqlite3" 2>nul
if exist "%OUT%\backend\storage" rmdir /s /q "%OUT%\backend\storage"
mkdir "%OUT%\backend\storage" 2>nul
mkdir "%OUT%\backend\logs" 2>nul
>> "%LOG%" echo Blank DB package OK ^(created on first EXE start^)

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

robocopy "%ROOT%\templates" "%OUT%\templates" /E /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy templates failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy templates code=!RC!
  goto :fail
)
if not exist "%OUT%\templates\reports\event_report.html.j2" (
  echo ERROR: report template missing in portable-share\templates
  >> "%LOG%" echo ERROR: templates\reports\event_report.html.j2 missing
  goto :fail
)

copy /Y "%ROOT%\ProtectionRCA.exe" "%OUT%\ProtectionRCA.exe" >nul
if errorlevel 1 (
  echo Failed to copy ProtectionRCA.exe
  >> "%LOG%" echo ERROR: copy exe failed
  goto :fail
)
if not exist "%ROOT%\_internal" (
  echo ERROR: _internal folder missing — rebuild with build-all-latest.bat ^(onedir launcher^)
  >> "%LOG%" echo ERROR: missing _internal
  goto :fail
)
if exist "%OUT%\_internal" rmdir /s /q "%OUT%\_internal"
robocopy "%ROOT%\_internal" "%OUT%\_internal" /E /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo robocopy _internal failed, code=!RC!
  >> "%LOG%" echo ERROR: robocopy _internal code=!RC!
  goto :fail
)
copy /Y "%ROOT%\scripts\launch_webapp.py" "%OUT%\scripts\launch_webapp.py" >nul
if exist "%ROOT%\frontend\dist\.build-stamp.txt" (
  copy /Y "%ROOT%\frontend\dist\.build-stamp.txt" "%OUT%\frontend\dist\.build-stamp.txt" >nul
)

echo Precompiling Python bytecode ^(faster first start^)...
>> "%LOG%" echo compileall start
"%OUT%\python\python.exe" -m compileall -q -f "%OUT%\backend\app" "%OUT%\python\Lib\site-packages" >> "%LOG%" 2>&1
>> "%LOG%" echo compileall done

> "%OUT%\HOW_TO_RUN.txt" (
  echo Protection RCA — portable package ^(ALL LATEST CODES^)
  echo ======================================================
  echo.
  echo Packaged from current backend .py, rules, frontend\dist,
  echo and ProtectionRCA.exe. Includes its own Python in python\
  echo ^(no Python / Visual Studio / pip install needed on this PC^).
  echo.
  echo DATABASE
  echo   Ships with a BLANK plant/events database. First start creates
  echo   empty SQLite files under backend\ and bootstrap admin:
  echo     username: admin
  echo     password: admin123
  echo   Change the password after first login.
  echo.
  echo START
  echo   1. Copy this WHOLE folder anywhere ^(keep _internal next to the EXE^).
  echo   2. Double-click ProtectionRCA.exe
  echo   3. Browser opens http://127.0.0.1:8001/ when the API is ready
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
if not exist "%OUT%\_internal" goto :fail
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
