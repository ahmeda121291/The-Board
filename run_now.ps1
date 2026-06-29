# Boardroom — "Run now" launcher. Fires ONE live checkpoint immediately and
# shows the result in the window. This is what the desktop "Run Boardroom Now"
# shortcut points at. Output is also appended to logs\runs.log.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null
$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
"`n===== $ts UTC — manual run =====" | Out-File -FilePath ".\logs\runs.log" -Append -Encoding utf8

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "Convening the boardroom (live)..." -ForegroundColor Cyan
& $py -m boardroom.cli run --confirm-live --once 2>&1 | Tee-Object -FilePath ".\logs\runs.log" -Append
Write-Host "`nDone. You can close this window." -ForegroundColor Green
Start-Sleep -Seconds 4
