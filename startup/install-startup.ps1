# install-startup.ps1
# Registers ToonTracker-Service.exe to start automatically at Windows login
# via Task Scheduler with automatic restart on failure.
#
# Usage (Administrator PowerShell):
#   .\startup\install-startup.ps1 -ServicePath "C:\path\to\ToonTracker-Service.exe"
#
# To start immediately without rebooting:
#   Start-ScheduledTask -TaskName "SihcomToonTrackerService"
#
# To remove the task:
#   Unregister-ScheduledTask -TaskName "SihcomToonTrackerService" -Confirm:$false

param(
    [Parameter(Mandatory = $true)]
    [string]$ServicePath
)

$TaskName = "SihcomToonTrackerService"

if (-not (Test-Path $ServicePath)) {
    Write-Error "Service executable not found: $ServicePath"
    exit 1
}

$WorkDir = Split-Path -Parent $ServicePath

$Action = New-ScheduledTaskAction `
    -Execute $ServicePath `
    -WorkingDirectory $WorkDir

# Trigger: run at every user login (current user only, non-elevated)
$Trigger = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME

# Settings: run forever, restart up to 3 times on failure (1-minute gap), no idle requirement
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable $true `
    -RunOnlyIfIdle $false `
    -StopIfGoingOnBatteries $false `
    -DisallowStartIfOnBatteries $false

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

# Remove any existing registration before re-registering (idempotent)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Sihcom Toon Tracker — EVE Online character tracking background service"

Write-Host ""
Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "Service path : $ServicePath"
Write-Host "Working dir  : $WorkDir"
Write-Host ""
Write-Host "To start it now (no reboot needed):"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To check its status:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Select-Object -ExpandProperty State"
