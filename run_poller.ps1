# Boardroom — background poller. Watches Supabase for dashboard "Run now"
# requests and executes each as a live checkpoint on THIS machine (where the
# trading keys live). Runs continuously; logs to logs\poller.log.
#
# Self-healing: if the Python poller ever exits (crash, network, etc.) this
# wrapper logs it and restarts after a short pause, so the scheduled task stays
# "Running" and never silently drops to "Ready".
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

while ($true) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
    "`n===== $ts UTC — poller starting ($py) =====" | Out-File -FilePath ".\logs\poller.log" -Append -Encoding utf8
    & $py -m boardroom.cli poll --confirm-live --interval 20 *>> ".\logs\poller.log"
    $code = $LASTEXITCODE
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
    "===== $ts UTC — poller exited (code $code); restarting in 15s =====" | Out-File -FilePath ".\logs\poller.log" -Append -Encoding utf8
    Start-Sleep -Seconds 15
}
