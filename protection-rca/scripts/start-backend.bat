@echo off
cd /d "%~dp0..\backend"
set PYTHONPATH=%CD%
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
) else (
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
)
