@echo off
rem Boardroom daily checkpoint (batch launcher for Task Scheduler).
rem Runs ONE live checkpoint and exits. Output appended to logs\scheduler.log.
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
rem Force UTF-8 so console glyphs don't crash when redirected to a cp1252 file.
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo.>> "logs\scheduler.log"
echo ===== %date% %time% - checkpoint (%PY%) =====>> "logs\scheduler.log"
"%PY%" -m boardroom.cli run --confirm-live --once >> "logs\scheduler.log" 2>&1
echo ===== %date% %time% - checkpoint done (code %errorlevel%) =====>> "logs\scheduler.log"
