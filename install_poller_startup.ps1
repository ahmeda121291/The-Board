# Boardroom — start the "Run now" poller via the Startup folder (no admin, no
# Task Scheduler). Drops a shortcut to run_poller.cmd in your per-user Startup
# folder so the poller launches at every logon, and starts it right now too.
# (Uses a .cmd launcher — PowerShell scripts won't run from background hosts.)
#
#   powershell -ExecutionPolicy Bypass -File .\install_poller_startup.ps1
$ErrorActionPreference = "Stop"

$target = Join-Path $PSScriptRoot "run_poller.cmd"
if (-not (Test-Path $target)) { throw "run_poller.cmd not found next to this script." }

$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "Boardroom Poller.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $target
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.WindowStyle = 7  # minimized
$lnk.Description = "Boardroom on-demand Run-now poller"
$lnk.Save()
Write-Host "Created startup shortcut: $lnkPath" -ForegroundColor Green

# Remove the old scheduled-task version if present, so they don't compete.
try {
    Unregister-ScheduledTask -TaskName "Boardroom Poller" -Confirm:$false -ErrorAction Stop
    Write-Host "Removed the old 'Boardroom Poller' scheduled task (replaced by startup shortcut)."
} catch { }

# Start it now (minimized) so you don't have to log off/in.
Start-Process -FilePath $target -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
Write-Host "Poller started in the background." -ForegroundColor Green
Write-Host "Watch it:   Get-Content .\logs\poller.log -Tail 15 -Wait"
