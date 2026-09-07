@echo off
set ROOT=%~dp0..
set NODE=%ROOT%\.tools\node
set PATH=%NODE%;%PATH%
cd /d "%ROOT%\frontend"
if not exist "%NODE%\node.exe" (
  echo Portable Node not found at %NODE%
  exit /b 1
)
if not exist "node_modules" call "%NODE%\npm.cmd" install
call "%NODE%\npm.cmd" run dev -- --host 127.0.0.1 --port 5173
