# CFD Trading System - Hourly (1h) Intraday Paper Trade
# Runs: Every hour 11:00-20:00 UTC (7am-4pm ET) Mon-Fri via Windows Task Scheduler
# Orders: DAY (intraday), SL 0.5%, TP 1%

# ── Weekday guard: skip weekends ──
$dayOfWeek = (Get-Date).DayOfWeek
if ($dayOfWeek -eq 'Saturday' -or $dayOfWeek -eq 'Sunday') {
    Write-Host "[$( Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Weekend ($dayOfWeek) - skipping paper trade"
    exit 0
}

$ProjectDir = "/home/alaindolea/proyectos/cfd-trading-system"
$LogDir = "$ProjectDir/logs/paper"
$Date = Get-Date -Format "yyyy-MM-dd"

# Ensure WSL is running and log directory exists
wsl -d Ubuntu --exec bash -c "mkdir -p $LogDir 2>/dev/null"

# Run paper trade with logging
wsl -d Ubuntu --exec bash -c @"
cd $ProjectDir && source venv/bin/activate
echo '========================================'
echo 'Hourly (1h) signals: '`$(date -u '+%Y-%m-%d %H:%M UTC')
echo '========================================'
python3 main.py paper-trade --interval 1h --no-news --min-confluence 3 --min-confidence 60 2>&1 | tee -a $LogDir/hourly_${Date}.log
"@
