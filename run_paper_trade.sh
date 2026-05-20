#!/bin/bash
# CFD Trading System - Automated Paper Trading
# Runs every hour during market hours to auto-execute signals

set -e
cd /home/alaindolea/proyectos/cfd-trading-system
source venv/bin/activate

exec >> /tmp/paper_trade_$(date +%Y%m%d).log 2>&1

echo "========================================"
echo "Paper Trade: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "========================================"

python3 main.py paper-trade --no-ensemble --no-news \
    --min-confluence 3 --min-confidence 60

echo
