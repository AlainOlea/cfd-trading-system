"""
Compara MACD+VWAP sin filtro de volumen (A) vs con filtro (B, relative_volume > VOLUME_THRESHOLD)
para el mismo set de tickers/intervalos/datos/engine. Ver .sisyphus/plans/2026-07-20-timeframe-volume-fix.md
"""
import logging

logging.disable(logging.CRITICAL)

from data.fetcher import DataFetcher
from indicators.technical import TechnicalIndicators
from strategies.scalping.macd_vwap import MACDVWAPStrategy
from backtesting.engine import BacktestEngine
from backtesting.metrics import PerformanceMetrics

TICKERS = ['GOOGL', 'AAPL', 'NVDA', 'BTC_USD', 'MSFT']
INTERVALS = ['1d', '1h']

METRIC_KEYS = ['total_trades', 'win_rate_pct', 'sharpe_ratio', 'max_drawdown_pct', 'total_return_pct']


def run_variant(strategy, df, ticker, interval, engine):
    result = engine.run(strategy, df, ticker=ticker, interval=interval)
    return PerformanceMetrics.calculate_all(result)


def main():
    fetcher = DataFetcher()
    engine = BacktestEngine()
    rows = []

    for ticker in TICKERS:
        for interval in INTERVALS:
            df = fetcher.load_from_csv(ticker, interval)
            df = TechnicalIndicators.add_all_indicators(df)

            # Version A: sin filtro de volumen (columna ausente -> filtro no aplica)
            df_a = df.drop(columns=['relative_volume'])
            metrics_a = run_variant(MACDVWAPStrategy(), df_a, ticker, interval, engine)

            # Version B: con filtro de volumen (relative_volume presente)
            metrics_b = run_variant(MACDVWAPStrategy(), df.copy(), ticker, interval, engine)

            rows.append((ticker, interval, metrics_a, metrics_b))

    header = f"{'Ticker':<8}{'Int':<5}{'Variant':<8}{'Trades':>8}{'WinRate%':>10}{'Sharpe':>9}{'MaxDD%':>9}{'Return%':>10}"
    print(header)
    print('-' * len(header))
    for ticker, interval, ma, mb in rows:
        for label, m in (('A (sin)', ma), ('B (con)', mb)):
            print(
                f"{ticker:<8}{interval:<5}{label:<8}"
                f"{m['total_trades']:>8}{m['win_rate_pct']:>10.1f}"
                f"{m['sharpe_ratio']:>9.2f}{m['max_drawdown_pct']:>9.2f}{m['total_return_pct']:>10.2f}"
            )
        print()

    # Aggregate diffs (B - A) across all ticker/interval pairs
    print('=' * len(header))
    print('Promedio de diferencias (B - A) sobre todos los pares ticker/interval:')
    diffs = {k: [] for k in METRIC_KEYS}
    for _, _, ma, mb in rows:
        for k in METRIC_KEYS:
            diffs[k].append(mb[k] - ma[k])
    for k in METRIC_KEYS:
        avg = sum(diffs[k]) / len(diffs[k])
        print(f"  {k:<18}: {avg:+.3f}")


if __name__ == '__main__':
    main()
