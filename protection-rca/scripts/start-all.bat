@echo off
setlocal
set ROOT=%~dp0..
set NODE=%ROOT%\.tools\node
set PATH=%NODE%;%PATH%
set API_PORT=8001

start "Protection-RCA-API" cmd /k "cd /d %ROOT%\backend && set DATABASE_URL=sqlite+aiosqlite:///./protection_rca_local.db&& set SECRET_KEY=local-dev-secret-change-in-production&& set CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173&& set PYTHONPATH=%ROOT%\backend&& if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT% --reload) else (python -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT% --reload)"

timeout /t 4 /nobreak >nul

if not exist "%NODE%\node.exe" (
  echo Portable Node missing: %NODE%
  pause
  exit /b 1
)

cd /d %ROOT%\frontend
echo VITE_API_BASE_URL=http://127.0.0.1:%API_PORT%/api> .env
if not exist node_modules call "%NODE%\npm.cmd" install
start "Protection-RCA-UI" cmd /k "set PATH=%NODE%;%PATH%&& npm run dev -- --host 127.0.0.1 --port 5173"

echo.
echo API:  http://127.0.0.1:%API_PORT%/docs
echo UI:   http://127.0.0.1:5173
echo No demo data. Bootstrap admin via BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD if needed.
endlocal
