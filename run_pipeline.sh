#!/bin/bash
# CFD Trading System - Automated Pipeline Runner
# Run this every hour via cron to get Telegram signals

set -e
cd /home/alaindolea/proyectos/cfd-trading-system
source venv/bin/activate

exec >> /tmp/pipeline_$(date +%Y%m%d).log 2>&1

echo "========================================"
echo "Pipeline run: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "========================================"

python3 main.py pipeline --no-ensemble --no-news --telegram

echo
