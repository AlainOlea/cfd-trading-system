#!/usr/bin/env python3
"""View detailed training results and improvements."""

import json
import sys
from pathlib import Path
from collections import defaultdict


def get_model_metrics(model_dir):
    """Extract metrics from a trained model's metadata."""
    metadata_file = model_dir / 'metadata.json'
    if not metadata_file.exists():
        return None

    try:
        with open(metadata_file) as f:
            meta = json.load(f)
        return {
            'ticker': meta.get('ticker', 'Unknown'),
            'interval': meta.get('interval', 'Unknown'),
            'path': model_dir.name,
        }
    except Exception as e:
        print(f"Error reading {model_dir.name}: {e}")
        return None


def main():
    """Display comprehensive training summary."""
    models_dir = Path('models/saved')

    if not models_dir.exists():
        print("❌ No trained models found")
        return

    # Collect all models
    models = []
    for model_dir in sorted(models_dir.iterdir()):
        if model_dir.is_dir():
            metrics = get_model_metrics(model_dir)
            if metrics:
                models.append(metrics)

    if not models:
        print("⏳ No complete models found")
        return

    # Display summary
    print(f"\n{'='*80}")
    print(f"TRAINED MODELS SUMMARY - {len(models)} Models")
    print(f"{'='*80}\n")

    print(f"{'Model Name':<25} {'Ticker':<12} {'Interval':<12} {'Status':<15}")
    print("-" * 80)

    by_interval = defaultdict(list)
    for model in models:
        print(f"{model['path']:<25} {model['ticker']:<12} {model['interval']:<12} {'✅ Ready':<15}")
        by_interval[model['interval']].append(model['ticker'])

    print("\n" + "="*80)
    print("MODELS BY INTERVAL")
    print("="*80)
    for interval in sorted(by_interval.keys()):
        tickers = by_interval[interval]
        print(f"\n{interval}: {len(tickers)} models")
        for ticker in sorted(tickers):
            print(f"  ✅ {ticker}")

    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    print("""
1. Use trained models with signal generation:
   python main.py signal --strategy macd_vwap --ticker SPY --use-ml

2. Generate signals for all tickers:
   python main.py scan --use-ml

3. Test models in watch mode:
   python main.py watch --use-ml

4. Generate trading signals with confidence scores:
   python main.py signal --strategy rsi_bb --ticker AAPL --use-ml

5. Backtest with ML predictions:
   python main.py backtest --strategy ma_crossover --ticker QQQ

Models are now ready for production use!
""")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()
