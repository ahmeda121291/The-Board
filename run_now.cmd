@echo off
rem Boardroom "Run now" - fires ONE live checkpoint and shows the result.
rem This is what the "Run Boardroom Now" desktop shortcut points at.
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
rem Force UTF-8 so console glyphs render instead of crashing on a cp1252 console.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Convening the boardroom (live)...
echo.
"%PY%" -m boardroom.cli run --confirm-live --once
echo.
echo Done. Press any key to close.
pause >nul
