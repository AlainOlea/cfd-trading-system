# CFD Trading System - Daily (1d) Swing Paper Trade
# Runs: Once at 12:00 UTC (7am ET) Mon-Fri via Windows Task Scheduler
# Orders: GTC (swing), SL 1.5%, TP 3%

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
echo 'Daily (1d) signals: '`$(date -u '+%Y-%m-%d %H:%M UTC')
echo '========================================'
python3 main.py paper-trade --interval 1d --no-news --min-confluence 3 --min-confidence 60 2>&1 | tee -a $LogDir/daily_${Date}.log
"@
