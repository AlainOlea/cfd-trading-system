#!/bin/bash
# Weekly paper account reset - closes all positions every Sunday
# Add to crontab: 0 0 * * 0 /home/alaindolea/proyectos/cfd-trading-system/reset_paper.sh

set -e
cd /home/alaindolea/proyectos/cfd-trading-system
source venv/bin/activate

exec >> /tmp/paper_trade_$(date +%Y%m%d).log 2>&1

echo "========================================"
echo "WEEKLY RESET: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "========================================"

python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
from alpaca.trading.client import TradingClient
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
# Cancel all orders
for o in client.get_orders():
    client.cancel_order_by_id(o.id)
    print(f'Cancelled: {o.symbol}')
# Close all positions
client.close_all_positions()
print('All positions closed. Ready for new week.')
"

echo "Reset complete: $(date -u)"
echo
