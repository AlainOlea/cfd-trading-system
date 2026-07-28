"""
Re-audita las 6 estrategias x 19 tickers x intervalos disponibles con el
BacktestEngine YA CORREGIDO (sl_stop/tp_stop reales, no salida por señal
contraria). Reemplaza los números de .sisyphus/plans/2026-07-20-strategy-audit-full.md,
que se generaron con el motor viejo (bug confirmado: mismos números que
produce hoy engine.run() con exits='SELL').

Usage:
    source venv/bin/activate
    PYTHONPATH=. python3 scripts/audit_all_strategies.py
"""
import logging
import warnings

logging.disable(logging.CRITICAL)
warnings.filterwarnings('ignore')

import pandas as pd

from data.fetcher import DataFetcher
from indicators.technical import TechnicalIndicators
from strategies import STRATEGY_MAP
from backtesting.engine import BacktestEngine
from backtesting.metrics import PerformanceMetrics

TICKERS = [
    'SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'SLV', 'USO', 'UNG',
    'AAPL', 'NVDA', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD',
]
INTERVALS = ['1d', '1h', '1m']
MIN_TRADES_RELIABLE = 20

fetcher = DataFetcher()
engine = BacktestEngine()
_indicator_cache: dict[str, pd.DataFrame] = {}


def get_data(ticker: str, interval: str) -> pd.DataFrame | None:
    key = f"{ticker}_{interval}"
    if key not in _indicator_cache:
        try:
            df = fetcher.load_from_csv(ticker, interval)
        except FileNotFoundError:
            _indicator_cache[key] = None
            return None
        df = TechnicalIndicators.add_all_indicators(df)
        _indicator_cache[key] = df
    return _indicator_cache[key]


def main():
    rows = []
    for strat_name, strat_cls in STRATEGY_MAP.items():
        for ticker in TICKERS:
            for interval in INTERVALS:
                df = get_data(ticker, interval)
                if df is None or len(df) < 100:
                    continue
                try:
                    result = engine.run(strat_cls(), df, ticker=ticker, interval=interval)
                    m = PerformanceMetrics.calculate_all(result)
                except Exception as e:
                    continue
                if m['total_trades'] == 0:
                    continue
                rows.append({
                    'strategy': strat_name,
                    'ticker': ticker,
                    'interval': interval,
                    'trades': m['total_trades'],
                    'win_rate': m['win_rate_pct'],
                    'sharpe': m['sharpe_ratio'],
                    'max_dd': m['max_drawdown_pct'],
                    'return_pct': m['total_return_pct'],
                    'profit_factor': m['profit_factor'],
                    'reliable': m['total_trades'] >= MIN_TRADES_RELIABLE,
                })

    out = pd.DataFrame(rows)
    out.to_csv('results/audit_fixed_engine.csv', index=False)

    pd.set_option('display.width', 160)
    pd.set_option('display.max_rows', 500)

    for strat_name in STRATEGY_MAP:
        sub = out[out['strategy'] == strat_name].sort_values('sharpe', ascending=False)
        if sub.empty:
            print(f"\n=== {strat_name}: SIN TRADES en ningún ticker/intervalo ===")
            continue
        print(f"\n=== {strat_name} ({len(sub)} combinaciones con trades) ===")
        print(sub[['ticker', 'interval', 'trades', 'win_rate', 'sharpe', 'max_dd', 'return_pct', 'profit_factor']]
              .to_string(index=False))

    print("\n\n=== TOP 15 por Sharpe (>=5 trades) ===")
    top = out[out['trades'] >= 5].sort_values('sharpe', ascending=False).head(15)
    print(top[['strategy', 'ticker', 'interval', 'trades', 'win_rate', 'sharpe', 'return_pct']].to_string(index=False))

    print(f"\nGuardado: results/audit_fixed_engine.csv ({len(out)} filas)")


if __name__ == '__main__':
    main()
