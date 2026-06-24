# Boardroom — daily checkpoint launcher for Windows Task Scheduler.
# Runs ONE live checkpoint and exits; Task Scheduler is the daily trigger, so
# this survives reboots and needs no terminal kept open. Output is appended to
# logs\scheduler.log.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null
$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
"`n===== $ts UTC — checkpoint =====" | Out-File -FilePath ".\logs\scheduler.log" -Append -Encoding utf8

# Prefer the venv's python; fall back to PATH python.
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -m boardroom.cli run --confirm-live --once *>> ".\logs\scheduler.log"
