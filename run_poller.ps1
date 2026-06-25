# Boardroom — background poller. Watches Supabase for dashboard "Run now"
# requests and executes each as a live checkpoint on THIS machine (where the
# trading keys live). Runs continuously; logs to logs\poller.log.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null
$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
"`n===== $ts UTC — poller started =====" | Out-File -FilePath ".\logs\poller.log" -Append -Encoding utf8

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -m boardroom.cli poll --confirm-live --interval 20 *>> ".\logs\poller.log"
