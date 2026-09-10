@echo off
REM ============================================================
REM  Build frontend from latest sources
REM  Always: npm install (pick up package.json) + npm run build
REM  Never reuses a failed/stale build.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0.."
set ROOT=%CD%

set "NODE_DIR="
if exist "%ROOT%\.tools\node\node.exe" set "NODE_DIR=%ROOT%\.tools\node"
if defined NODE_DIR set "PATH=%NODE_DIR%;%PATH%"

set "NPM="
if exist "%ROOT%\.tools\node\npm.cmd" set "NPM=%ROOT%\.tools\node\npm.cmd"
where npm >nul 2>&1 && if not defined NPM for /f "delims=" %%I in ('where npm') do (
  if not defined NPM set "NPM=%%I"
)
if exist "%ProgramFiles%\nodejs\npm.cmd" if not defined NPM set "NPM=%ProgramFiles%\nodejs\npm.cmd"
if exist "%ProgramFiles(x86)%\nodejs\npm.cmd" if not defined NPM set "NPM=%ProgramFiles(x86)%\nodejs\npm.cmd"

echo.
echo [frontend] Sync deps + build production UI from latest sources...
echo   ROOT: %ROOT%

if defined NODE_DIR (
  echo   Node: %NODE_DIR%
  "%NODE_DIR%\node.exe" -v
) else (
  where node >nul 2>&1
  if errorlevel 1 (
    echo ERROR: node.exe not found.
    echo Install Node.js OR place portable Node in .tools\node\
    exit /b 1
  )
)

if not defined NPM (
  echo ERROR: npm not found.
  echo Install Node.js OR place portable Node in .tools\node\
  exit /b 1
)

if not exist "%ROOT%\frontend\package.json" (
  echo ERROR: frontend\package.json missing.
  exit /b 1
)

cd /d "%ROOT%\frontend"
echo VITE_API_BASE_URL=/api> .env.production
echo   Using npm: %NPM%
echo   npm install...
call "%NPM%" install
if errorlevel 1 (
  echo ERROR: npm install failed.
  exit /b 1
)

REM Remove old dist so we never ship a mixed old/new bundle
if exist "%ROOT%\frontend\dist" (
  echo   Clearing old frontend\dist ...
  rmdir /s /q "%ROOT%\frontend\dist" 2>nul
)

echo   npm run build...
call "%NPM%" run build
if errorlevel 1 (
  echo ERROR: frontend build failed.
  exit /b 1
)

if not exist "%ROOT%\frontend\dist\index.html" (
  echo ERROR: frontend\dist\index.html missing after build.
  exit /b 1
)

echo [frontend] OK — %ROOT%\frontend\dist
echo Built: %DATE% %TIME%> "%ROOT%\frontend\dist\.build-stamp.txt"
endlocal
exit /b 0
