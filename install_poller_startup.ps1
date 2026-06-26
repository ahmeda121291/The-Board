# Boardroom — start the "Run now" poller via the Startup folder (no admin, no
# Task Scheduler). Drops a shortcut in your per-user Startup folder so the poller
# launches hidden at every logon, and starts it right now too.
#
#   powershell -ExecutionPolicy Bypass -File .\install_poller_startup.ps1
$ErrorActionPreference = "Stop"

$target = Join-Path $PSScriptRoot "run_poller.ps1"
if (-not (Test-Path $target)) { throw "run_poller.ps1 not found next to this script." }

$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "Boardroom Poller.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = "powershell.exe"
$lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$target`""
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.WindowStyle = 7  # minimized/hidden
$lnk.Description = "Boardroom on-demand Run-now poller"
$lnk.Save()
Write-Host "Created startup shortcut: $lnkPath" -ForegroundColor Green

# If the old scheduled-task version exists, remove it so they don't fight.
try {
    Unregister-ScheduledTask -TaskName "Boardroom Poller" -Confirm:$false -ErrorAction Stop
    Write-Host "Removed the old 'Boardroom Poller' scheduled task (replaced by startup shortcut)."
} catch {
    # not present / not removable — fine
}

# Start it now (hidden) so you don't have to log off/in.
Start-Process powershell.exe `
    -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-WindowStyle","Hidden","-File","`"$target`"" `
    -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
Write-Host "Poller started in the background." -ForegroundColor Green
Write-Host "Watch it:   Get-Content .\logs\poller.log -Tail 15 -Wait"
Write-Host "Stop it:    Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { `$_.CommandLine -like '*run_poller.ps1*' } | ForEach-Object { Stop-Process -Id `$_.ProcessId }"
