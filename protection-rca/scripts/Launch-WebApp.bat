@echo off
REM Fallback launcher (same behavior as ProtectionRCA.exe)
cd /d "%~dp0.."
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" "scripts\launch_webapp.py"
) else (
  python "scripts\launch_webapp.py"
)
