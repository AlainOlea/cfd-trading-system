# CFD Trading System - Windows Task Scheduler Setup
# Run this script as Administrator to register paper trading tasks

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HourlyScript = Join-Path $ScriptDir "run_paper_hourly.ps1"
$DailyScript = Join-Path $ScriptDir "run_paper_daily.ps1"

Write-Host "CFD Trading System - Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "=" * 50

# Verify scripts exist
if (-not (Test-Path $HourlyScript)) {
    Write-Host "ERROR: run_paper_hourly.ps1 not found at $HourlyScript" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $DailyScript)) {
    Write-Host "ERROR: run_paper_daily.ps1 not found at $DailyScript" -ForegroundColor Red
    exit 1
}

Write-Host "Scripts found:" -ForegroundColor Green
Write-Host "  Hourly: $HourlyScript"
Write-Host "  Daily:  $DailyScript"
Write-Host ""

# Task 1: Hourly (11:00-20:00 UTC Mon-Fri)
Write-Host "Registering CFD Paper Hourly task..." -ForegroundColor Yellow
$hourlyAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$HourlyScript`""

# Weekly trigger: Mon-Fri, starting at 11:00 UTC (7am ET during EDT)
# Repeat every 1 hour for 9 hours (11:00-20:00 UTC)
$hourlyTrigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:00"

$hourlySettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$hourlyPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Remove existing task if present
Get-ScheduledTask -TaskName "CFD Paper Hourly" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

Register-ScheduledTask `
    -TaskName "CFD Paper Hourly" `
    -Action $hourlyAction `
    -Trigger $hourlyTrigger `
    -Settings $hourlySettings `
    -Principal $hourlyPrincipal `
    -Description "CFD Trading System - Hourly intraday signals (1h interval, DAY orders)" `
    -Force

Write-Host "  CFD Paper Hourly registered" -ForegroundColor Green

# Task 2: Daily swing (12:00 UTC / 7am ET Mon-Fri)
Write-Host "Registering CFD Paper Daily task..." -ForegroundColor Yellow
$dailyAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$DailyScript`""

$dailyTrigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:00"

$dailySettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$dailyPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Remove existing task if present
Get-ScheduledTask -TaskName "CFD Paper Daily" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

Register-ScheduledTask `
    -TaskName "CFD Paper Daily" `
    -Action $dailyAction `
    -Trigger $dailyTrigger `
    -Settings $dailySettings `
    -Principal $dailyPrincipal `
    -Description "CFD Trading System - Daily swing signals (1d interval, GTC orders)" `
    -Force

Write-Host "  CFD Paper Daily registered" -ForegroundColor Green

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tasks registered:" -ForegroundColor White
Get-ScheduledTask -TaskName "CFD Paper*" | Format-Table TaskName, State, @{L='NextRun';E={$_.NextRunTime}} -AutoSize
Write-Host ""
Write-Host "To verify: Get-ScheduledTask -TaskName 'CFD Paper*'" -ForegroundColor Gray
Write-Host "To remove: Unregister-ScheduledTask -TaskName 'CFD Paper Hourly'" -ForegroundColor Gray
