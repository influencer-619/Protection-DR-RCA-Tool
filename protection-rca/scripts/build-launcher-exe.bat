@echo off
REM ============================================================
REM  Build ProtectionRCA.exe using ALL latest codes
REM  (backend deps + frontend dist + launcher)
REM  Delegates to scripts\build-all-latest.bat
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0.."
call "%~dp0build-all-latest.bat"
exit /b %ERRORLEVEL%
