@echo off
REM ============================================================
REM  Portable package with ALL latest codes
REM  Double-click from: protection-rca\
REM  Output: protection-rca\portable-share\
REM
REM  Same safe path as build-exe.bat:
REM    verify backend\.venv (NO pip --upgrade / no numpy rebuild)
REM    rebuild frontend\dist + ProtectionRCA.exe
REM    copy into portable-share\
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo Building portable-share from ALL latest codes ...
echo (backend verify only — will NOT force-upgrade numpy)
echo This may take several minutes.
echo.

call "%~dp0scripts\build-portable-share.bat"
set ERR=%ERRORLEVEL%

if %ERR% NEQ 0 (
  echo.
  echo BUILD FAILED. See portable-build-log.txt if present.
  exit /b %ERR%
)

endlocal
exit /b 0
