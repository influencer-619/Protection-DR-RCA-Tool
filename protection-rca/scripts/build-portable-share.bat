@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set ROOT=%CD%
set OUT=%ROOT%\portable-share
set LOG=%ROOT%\portable-build-log.txt
set PY=%ROOT%\backend\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

set NPM=
set "NODE_DIR="
if exist "%ROOT%\.tools\node\node.exe" set "NODE_DIR=%ROOT%\.tools\node"
if defined NODE_DIR set "PATH=%NODE_DIR%;%PATH%"
if exist "%ROOT%\.tools\node\npm.cmd" set "NPM=%ROOT%\.tools\node\npm.cmd"
where npm >nul 2>&1 && if not defined NPM for /f "delims=" %%I in ('where npm') do (
  if not defined NPM set "NPM=%%I"
)
if exist "%ProgramFiles%\nodejs\npm.cmd" if not defined NPM set "NPM=%ProgramFiles%\nodejs\npm.cmd"
if exist "%ProgramFiles(x86)%\nodejs\npm.cmd" if not defined NPM set "NPM=%ProgramFiles(x86)%\nodejs\npm.cmd"

echo ============================================================
echo  Protection RCA — build portable share package
echo ============================================================
echo  ROOT: %ROOT%
echo  OUT : %OUT%
echo  LOG : %LOG%
echo ============================================================
echo.

> "%LOG%" echo Protection RCA portable build log
>> "%LOG%" echo Started: %DATE% %TIME%
>> "%LOG%" echo ROOT=%ROOT%
>> "%LOG%" echo NODE_DIR=%NODE_DIR%
>> "%LOG%" echo NPM=%NPM%

if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo ERROR: backend\.venv not found.
  echo Create it first:
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  >> "%LOG%" echo ERROR: missing backend\.venv
  goto :fail
)

echo [1/4] Building frontend ^(production^)...
if defined NODE_DIR (
  echo Using portable Node: %NODE_DIR%
  "%NODE_DIR%\node.exe" -v
) else (
  where node >nul 2>&1
  if errorlevel 1 (
    if exist "%ROOT%\frontend\dist\index.html" (
      echo WARNING: node.exe not found — reusing existing frontend\dist
      >> "%LOG%" echo WARN: no node, reuse dist
      goto :after_frontend
    )
    echo ERROR: node.exe not found.
    echo Install Node.js OR place portable Node in .tools\node\ ^(need node.exe + npm.cmd^)
    >> "%LOG%" echo ERROR: node.exe not found
    goto :fail
  )
)

if not defined NPM (
  if exist "%ROOT%\frontend\dist\index.html" (
    echo WARNING: npm not found — reusing existing frontend\dist
    >> "%LOG%" echo WARN: no npm, reuse dist
    goto :after_frontend
  )
  echo ERROR: npm not found.
  echo Install Node.js OR place portable Node in .tools\node\
  >> "%LOG%" echo ERROR: npm not found
  goto :fail
)

cd /d "%ROOT%\frontend"
echo VITE_API_BASE_URL=/api> .env.production
echo Using npm: %NPM%
call "%NPM%" run build
if errorlevel 1 (
  if exist "%ROOT%\frontend\dist\index.html" (
    echo WARNING: frontend build failed — reusing existing frontend\dist
    >> "%LOG%" echo WARN: build failed, reuse dist
    goto :after_frontend
  )
  echo Frontend build failed. See log: %LOG%
  echo Tip: ensure .tools\node\node.exe is on PATH ^(this script now adds it automatically^).
  >> "%LOG%" echo ERROR: frontend build failed
  goto :fail
)
if not exist "%ROOT%\frontend\dist\index.html" (
  echo frontend\dist\index.html missing after build.
  >> "%LOG%" echo ERROR: missing frontend\dist\index.html
  goto :fail
)
echo Frontend OK.
>> "%LOG%" echo Frontend OK

:after_frontend
if not exist "%ROOT%\frontend\dist\index.html" (
  echo frontend\dist\index.html missing.
  >> "%LOG%" echo ERROR: missing frontend\dist\index.html
  goto :fail
)

echo.
echo [2/4] Building ProtectionRCA.exe launcher...
echo Close any running ProtectionRCA.exe if rebuild fails with Access denied.
call "%ROOT%\scripts\build-launcher-exe.bat"
if errorlevel 1 (
  echo Launcher build failed.
  >> "%LOG%" echo ERROR: launcher build failed
  goto :fail
)
if not exist "%ROOT%\ProtectionRCA.exe" (
  echo ProtectionRCA.exe missing after build.
  >> "%LOG%" echo ERROR: missing ProtectionRCA.exe
  goto :fail
)
echo Exe OK.
>> "%LOG%" echo Exe OK

echo.
echo [3/4] Assembling portable-share folder...
echo This can take a few minutes ^(copies backend\.venv^)...
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%" 2>nul
mkdir "%OUT%\backend" 2>nul
mkdir "%OUT%\frontend" 2>nul
mkdir "%OUT%\rules" 2>nul
mkdir "%OUT%\scripts" 2>nul

robocopy "%ROOT%\backend" "%OUT%\backend" /E /XD __pycache__ .pytest_cache htmlcov .mypy_cache storage /NFL /NDL /NJH /NJS /nc /ns /np
set RC=%ERRORLEVEL%
if %RC% GEQ 8 (
  echo robocopy backend failed, code=%RC%
  >> "%LOG%" echo ERROR: robocopy backend code=%RC%
  goto :fail
)

robocopy "%ROOT%\frontend\dist" "%OUT%\frontend\dist" /E /NFL /NDL /NJH /NJS /nc /ns /np
set RC=%ERRORLEVEL%
if %RC% GEQ 8 (
  echo robocopy frontend\dist failed, code=%RC%
  >> "%LOG%" echo ERROR: robocopy frontend code=%RC%
  goto :fail
)

robocopy "%ROOT%\rules" "%OUT%\rules" /E /NFL /NDL /NJH /NJS /nc /ns /np
set RC=%ERRORLEVEL%
if %RC% GEQ 8 (
  echo robocopy rules failed, code=%RC%
  >> "%LOG%" echo ERROR: robocopy rules code=%RC%
  goto :fail
)

copy /Y "%ROOT%\ProtectionRCA.exe" "%OUT%\ProtectionRCA.exe" >nul
if errorlevel 1 (
  echo Failed to copy ProtectionRCA.exe
  >> "%LOG%" echo ERROR: copy exe failed
  goto :fail
)
copy /Y "%ROOT%\scripts\launch_webapp.py" "%OUT%\scripts\launch_webapp.py" >nul

echo.
echo [4/4] Writing HOW_TO_RUN.txt ...
> "%OUT%\HOW_TO_RUN.txt" (
  echo Protection RCA — portable package
  echo ==================================
  echo.
  echo REQUIREMENTS ON THIS PC
  echo   - Windows 10/11 64-bit
  echo   - No Python / Node install needed ^(Python runtime is inside backend\.venv^)
  echo.
  echo START ON YOUR LAPTOP
  echo   1. Unzip / copy this whole folder anywhere ^(keep structure^).
  echo   2. Double-click ProtectionRCA.exe
  echo   3. Browser opens http://127.0.0.1:8001/
  echo   4. Keep the small "Protection RCA is running" window open.
  echo.
  echo SHARE ON YOUR NETWORK ^(others open your laptop^)
  echo   1. Start ProtectionRCA.exe on the host laptop.
  echo   2. Note the LAN URL shown in the control window, e.g.
  echo        http://192.168.1.50:8001/
  echo   3. On first run, allow Windows Firewall for private networks.
  echo   4. Other PCs on the SAME Wi-Fi / LAN open that LAN URL in Chrome/Edge.
  echo   5. Do NOT use 127.0.0.1 from other PCs — that only works on the host.
  echo.
  echo STOP
  echo   Close the Protection RCA control window ^(Stop ^& Close^).
)

if not exist "%OUT%\ProtectionRCA.exe" goto :fail
if not exist "%OUT%\frontend\dist\index.html" goto :fail
if not exist "%OUT%\backend\.venv\Scripts\python.exe" goto :fail

echo.
echo ============================================================
echo  SUCCESS
echo  Package folder:
echo  %OUT%
echo ============================================================
echo Zip that folder and send it.
echo Log: %LOG%
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
echo  BUILD FAILED — portable-share was NOT created/completed
echo  See log: %LOG%
echo ============================================================
>> "%LOG%" echo FAILED: %DATE% %TIME%
echo.
pause
endlocal
exit /b 1
