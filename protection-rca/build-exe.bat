@echo off
REM ============================================================
REM  Build with ALL latest codes → ProtectionRCA.exe + frontend\dist
REM  Double-click from: protection-rca\
REM
REM  Updates:
REM    - backend\.venv from requirements.txt
REM    - frontend npm deps + fresh frontend\dist
REM    - ProtectionRCA.exe launcher
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo Building ALL latest codes (backend + UI + EXE) ...
echo.

call "%~dp0scripts\build-all-latest.bat"
set ERR=%ERRORLEVEL%

echo.
if %ERR% NEQ 0 (
  echo BUILD FAILED.
  pause
  exit /b %ERR%
)

echo Done — latest codes are ready.
echo   EXE : %CD%\ProtectionRCA.exe
echo   UI  : %CD%\frontend\dist
echo   API : %CD%\backend
echo.
echo Close any old ProtectionRCA.exe window, then start the new EXE.
echo.
pause
endlocal
exit /b 0
