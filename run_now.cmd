@echo off
rem Boardroom "Run now" - fires ONE live checkpoint and shows the result.
rem This is what the "Run Boardroom Now" desktop shortcut points at.
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Convening the boardroom (live)...
echo.
"%PY%" -m boardroom.cli run --confirm-live --once
echo.
echo Done. Press any key to close.
pause >nul
