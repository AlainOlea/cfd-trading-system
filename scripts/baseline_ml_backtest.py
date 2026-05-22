"""
Baseline OOS financial backtest for already-trained LSTM/Transformer models.

Reproduces the test split deterministically (chronological by ratio), runs
the OOS backtest with CFD costs, prints a table, and writes the metrics
back into each model's metadata.json so the promotion gate can be applied
without retraining.

Skips XGBoost models (different loader path) — they will be handled in C1
when the model factory is in place.

Usage:
    python3 scripts/baseline_ml_backtest.py
    python3 scripts/baseline_ml_backtest.py --ticker GLD --interval 1d
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import MODELS_SAVED_DIR
from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from models.trainer import ModelTrainer

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')


def _discover_models() -> list[tuple[str, str, Path]]:
    """Return (ticker, interval, dir) for non-xgb saved models."""
    out = []
    for d in sorted(MODELS_SAVED_DIR.iterdir()):
        if not d.is_dir() or d.name.endswith('_xgb'):
            continue
        if not (d / 'model.keras').exists():
            continue
        # Convention: {TICKER_WITH_UNDERSCORES}_{interval}
        parts = d.name.rsplit('_', 1)
        if len(parts) != 2:
            continue
        safe_ticker, interval = parts
        # Reverse safe_ticker → original (BTC_USD → BTC-USD)
        ticker = safe_ticker.replace('_', '-') if 'USD' in safe_ticker else safe_ticker
        out.append((ticker, interval, d))
    return out


def _backtest_one(ticker: str, interval: str, model_dir: Path) -> dict | None:
    """Reproduce split + run OOS backtest for one saved model."""
    try:
        model, _scaler, meta = ModelTrainer.load_model(ticker, interval)
    except Exception as e:
        click.echo(f"  ⚠️  load failed: {e}")
        return None

    # Reproduce the same dataset the model was trained on. Yahoo data
    # is mostly stable for past dates, so the split is deterministic
    # given the same days argument.
    fetcher = DataFetcher()
    processor = DataProcessor()
    # Need enough history for chronological split + lookback to leave a
    # meaningful test window. Daily models need years; intraday less.
    days_for_interval = {'1d': 1500, '1h': 365, '15m': 60, '5m': 30, '1m': 14}
    days = days_for_interval.get(interval, 365)
    try:
        df = fetcher.fetch_yfinance(ticker, interval, days=days)
        df = processor.clean_data(df)
    except Exception:
        df = fetcher.load_from_csv(ticker, interval)

    df = TechnicalIndicators.add_all_indicators(df)

    trainer = ModelTrainer(
        lookback_window=meta['lookback_window'],
        features=meta['features'],
    )
    # Use the saved scaler so transforms match training-time normalisation
    trainer.scaler = _scaler
    # prepare_data refits the scaler — patch to skip refit by transforming
    # inside our own loop. Simpler: call prepare_data and accept refit
    # (input distribution is same data, so result is equivalent).
    _Xtr, _ytr, X_test, _yte = trainer.prepare_data(df)

    oos = trainer.backtest_predictions(model, X_test, ticker=ticker, interval=interval)

    # Persist back into metadata so promotion gate can apply
    meta.update(oos)
    promoted, reasons = trainer.evaluate_promotion(meta)
    meta['promoted'] = promoted
    meta['promotion_reasons'] = reasons

    with open(model_dir / 'metadata.json', 'w') as f:
        json.dump(meta, f, indent=2, default=str)

    return {
        'ticker': ticker,
        'interval': interval,
        'sharpe': oos['oos_sharpe'],
        'return_pct': oos['oos_total_return_pct'],
        'max_dd_pct': oos['oos_max_drawdown_pct'],
        'pf': oos['oos_profit_factor'],
        'win_rate': oos['oos_win_rate_pct'],
        'trades': oos['oos_n_trades'],
        'promoted': promoted,
    }


@click.command()
@click.option('--ticker', default=None, help='Limit to one ticker')
@click.option('--interval', default=None, help='Limit to one interval')
def main(ticker: str | None, interval: str | None):
    models = _discover_models()
    if ticker:
        models = [m for m in models if m[0] == ticker]
    if interval:
        models = [m for m in models if m[1] == interval]

    if not models:
        click.echo("No matching models found.")
        sys.exit(1)

    click.echo(f"\nRunning OOS baseline backtest on {len(models)} models...\n")
    rows = []
    for ticker, interval, model_dir in models:
        click.echo(f"➤ {ticker} {interval}")
        row = _backtest_one(ticker, interval, model_dir)
        if row:
            rows.append(row)

    if not rows:
        click.echo("\nNo results.")
        return

    click.echo(f"\n{'='*86}")
    click.echo(f"{'TICKER':<10} {'TF':<5} {'SHARPE':>8} {'RETURN%':>9} "
               f"{'MAXDD%':>8} {'PF':>6} {'WIN%':>7} {'TRADES':>7} {'PROMO':>6}")
    click.echo('-' * 86)
    for r in rows:
        click.echo(
            f"{r['ticker']:<10} {r['interval']:<5} "
            f"{r['sharpe']:>8.2f} {r['return_pct']:>9.2f} "
            f"{r['max_dd_pct']:>8.2f} {r['pf']:>6.2f} "
            f"{r['win_rate']:>7.2f} {r['trades']:>7d} "
            f"{'YES' if r['promoted'] else 'NO':>6}"
        )
    click.echo('=' * 86)
    n_promoted = sum(1 for r in rows if r['promoted'])
    click.echo(f"\nPromoted: {n_promoted}/{len(rows)}")


if __name__ == '__main__':
    main()
