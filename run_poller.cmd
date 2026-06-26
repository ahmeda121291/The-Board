@echo off
rem Boardroom poller (batch launcher - reliable from Task Scheduler / Startup).
rem Watches Supabase for dashboard "Run now" requests and runs them locally.
rem Self-healing: if the poller exits, it logs and restarts after 15s.
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

:loop
echo.>> "logs\poller.log"
echo ===== %date% %time% - poller starting (%PY%) =====>> "logs\poller.log"
"%PY%" -m boardroom.cli poll --confirm-live --interval 20 >> "logs\poller.log" 2>&1
echo ===== %date% %time% - poller exited (code %errorlevel%); restart in 15s =====>> "logs\poller.log"
timeout /t 15 /nobreak >nul
goto loop
