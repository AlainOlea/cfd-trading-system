#!/usr/bin/env python3
"""Monitor training progress and results."""

import sys
import json
from pathlib import Path
import os

def check_saved_models():
    """Check what models have been trained and their performance."""
    models_dir = Path('models/saved')

    if not models_dir.exists():
        print("❌ No models directory found")
        return

    models = sorted([d for d in models_dir.iterdir() if d.is_dir()])

    if not models:
        print("⏳ No models trained yet...")
        return

    print(f"\n{'='*70}")
    print(f"TRAINED MODELS STATUS")
    print(f"{'='*70}\n")

    results = []
    for model_dir in models:
        metadata_file = model_dir / 'metadata.json'
        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    meta = json.load(f)
                ticker = meta.get('ticker', 'Unknown')
                interval = meta.get('interval', 'Unknown')

                # Try to get model size
                weights_file = model_dir / 'model.weights.h5'
                if weights_file.exists():
                    size_mb = weights_file.stat().st_size / (1024*1024)
                    results.append({
                        'name': model_dir.name,
                        'ticker': ticker,
                        'interval': interval,
                        'size_mb': size_mb,
                    })
            except Exception as e:
                print(f"⚠️  Error reading {model_dir.name}: {e}")

    if results:
        print(f"{'Model':<20} {'Ticker':<12} {'Interval':<10} {'Size (MB)':<10}")
        print("-" * 52)
        for r in results:
            print(f"{r['name']:<20} {r['ticker']:<12} {r['interval']:<10} {r['size_mb']:.2f}")

        print(f"\n✅ Total models trained: {len(results)}")

    # Check for training log
    log_file = Path('training_results.log')
    if log_file.exists():
        print(f"\n📊 Latest training results:\n")
        with open(log_file) as f:
            lines = f.readlines()
            # Show last 50 lines
            for line in lines[-50:]:
                if any(x in line for x in ['Accuracy', 'Precision', 'AVERAGE', 'Results:', '✅', '❌']):
                    print(line.rstrip())


def main():
    """Main monitoring function."""
    print(f"\n🔍 Checking training progress at {Path.cwd()}...\n")
    check_saved_models()
    print(f"\n{'='*70}\n")


if __name__ == '__main__':
    main()
