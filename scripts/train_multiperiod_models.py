#!/usr/bin/env python3
"""
Multi-Period Model Training
============================
Trains models for different time periods (1m, 5m, 15m, 1h, 1d)
to understand price prediction across timeframes.
"""

import sys
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from config.gpu_config import configure_gpu
configure_gpu()

from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from models.hybrid_model import HybridLSTMTransformer
from models.trainer import ModelTrainer


# Multi-period training config
# (ticker, intervals with epochs, days_history)
MULTIPERIOD_CONFIG = [
    # (ticker, [(interval, epochs, days), ...])
    ('GLD', [
        ('1d', 50, 365),      # Daily - best period
        ('1h', 40, 90),       # Hourly - good period
        ('15m', 30, 30),      # 15-min - intraday
    ]),
    ('MSFT', [
        ('1d', 50, 365),
        ('1h', 40, 90),
    ]),
    ('QQQ', [
        ('1d', 50, 365),
        ('1h', 40, 90),
    ]),
]


def train_period(ticker, interval, epochs, days):
    """Train model for a specific period."""
    print(f"\n{'─'*70}")
    print(f"Training: {ticker:12s} | {interval:4s} | {epochs:3d} epochs | {days:3d} days")
    print(f"{'─'*70}")

    try:
        fetcher = DataFetcher()
        processor = DataProcessor()

        # Fetch data
        try:
            df = fetcher.load_from_csv(ticker, interval)
            print(f"✅ Loaded: {len(df)} rows")
        except FileNotFoundError:
            print(f"📥 Fetching...")
            df = fetcher.fetch_yfinance(ticker, interval, days)
            if len(df) < 50:
                print(f"⚠️  Insufficient data ({len(df)} rows). Skipping.")
                return None
            df = processor.clean_data(df)
            fetcher.save_to_csv(df, ticker, interval)
            print(f"✅ Fetched: {len(df)} rows")

        # Indicators
        df = TechnicalIndicators.add_all_indicators(df)

        # Prepare data
        trainer = ModelTrainer(epochs=epochs)
        X_train, y_train, X_test, y_test = trainer.prepare_data(df)
        print(f"📊 Train: {len(X_train)} | Test: {len(X_test)}")

        # Build & train
        hybrid = HybridLSTMTransformer()
        input_shape = (X_train.shape[1], X_train.shape[2])
        hybrid.build(input_shape)

        print(f"🤖 Training...")
        trainer.train(hybrid, X_train, y_train, epochs=epochs, batch_size=32)

        # Evaluate
        metrics = trainer.evaluate(hybrid, X_test, y_test)
        print(f"📈 Accuracy: {metrics['accuracy']:.4f}")

        # Save
        model_dir = trainer.save_model(hybrid, ticker, interval)
        print(f"✅ Saved: {model_dir}")

        return {
            'ticker': ticker,
            'interval': interval,
            'accuracy': metrics['accuracy'],
            'samples': len(X_train) + len(X_test),
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def main():
    """Train multi-period models."""
    print(f"\n{'='*70}")
    print(f"MULTI-PERIOD MODEL TRAINING")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    results = []

    for ticker, periods in MULTIPERIOD_CONFIG:
        print(f"\n\n{'='*70}")
        print(f"TICKER: {ticker}")
        print(f"{'='*70}")

        for interval, epochs, days in periods:
            result = train_period(ticker, interval, epochs, days)
            if result:
                results.append(result)

    # Summary
    print(f"\n\n{'='*70}")
    print(f"MULTI-PERIOD SUMMARY")
    print(f"{'='*70}\n")

    if results:
        # Group by ticker
        by_ticker = {}
        for r in results:
            if r['ticker'] not in by_ticker:
                by_ticker[r['ticker']] = []
            by_ticker[r['ticker']].append(r)

        for ticker in sorted(by_ticker.keys()):
            print(f"\n{ticker}:")
            print(f"  {'Interval':<10} {'Accuracy':<12} {'Samples':<10}")
            print(f"  {'-'*32}")
            for r in sorted(by_ticker[ticker], key=lambda x: x['interval']):
                print(f"  {r['interval']:<10} {r['accuracy']:.4f}      {r['samples']:<10}")

        # Period comparison
        print(f"\n{'='*70}")
        print(f"PERIOD COMPARISON (Accuracy)")
        print(f"{'='*70}\n")

        by_interval = {}
        for r in results:
            if r['interval'] not in by_interval:
                by_interval[r['interval']] = []
            by_interval[r['interval']].append(r['accuracy'])

        print(f"{'Interval':<10} {'Avg Accuracy':<12} {'Best':<12} {'Count':<10}")
        print(f"{'-'*44}")
        for interval in sorted(by_interval.keys(), key=lambda x: int(x.replace('m', '').replace('h', '').replace('d', ''))):
            accs = by_interval[interval]
            avg = sum(accs) / len(accs)
            best = max(accs)
            print(f"{interval:<10} {avg:.4f}      {best:.4f}      {len(accs):<10}")

        print(f"\n{'='*70}")
        print(f"Key Findings:")
        print(f"  • Daily (1d) typically has higher accuracy (more data)")
        print(f"  • Hourly (1h) is good for swing trades")
        print(f"  • Intraday (15m) requires more features/data")
        print(f"  • Combine periods: Use 1d for trend, 1h for timing")
        print(f"{'='*70}\n")

    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == '__main__':
    main()
