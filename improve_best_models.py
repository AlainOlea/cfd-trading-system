#!/usr/bin/env python3
"""
Improve Best Models - Advanced Training
========================================
Retrains the best models (GLD, MSFT, QQQ) with:
- More epochs (100 instead of 30-50)
- Better learning rate scheduling
- Enhanced regularization
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


# Best performing models to improve
BEST_MODELS = [
    ('GLD', '1d', 100),      # 64% → target 70%
    ('MSFT', '1d', 100),     # 60% → target 65%
    ('QQQ', '1d', 100),      # 56% → target 62%
    ('AAPL', '1d', 80),      # 52% → target 60%
]


def improve_model(ticker, interval, epochs):
    """Retrain a model with more epochs and better hyperparameters."""
    print(f"\n{'='*70}")
    print(f"IMPROVING: {ticker:12s} | Interval: {interval:3s} | Epochs: {epochs}")
    print(f"{'='*70}")

    try:
        # Load data
        fetcher = DataFetcher()
        processor = DataProcessor()

        try:
            df = fetcher.load_from_csv(ticker, interval)
            print(f"✅ Loaded data: {len(df)} rows")
        except FileNotFoundError:
            print(f"📥 Fetching {ticker}...")
            df = fetcher.fetch_yfinance(ticker, interval, days=365)
            if len(df) < 100:
                print(f"⚠️  Insufficient data. Skipping {ticker}.")
                return None
            df = processor.clean_data(df)
            fetcher.save_to_csv(df, ticker, interval)
            print(f"✅ Fetched: {len(df)} rows")

        # Compute indicators
        print(f"📊 Computing indicators...")
        df = TechnicalIndicators.add_all_indicators(df)

        # Prepare data
        trainer = ModelTrainer(epochs=epochs)
        X_train, y_train, X_test, y_test = trainer.prepare_data(df)
        print(f"✅ Data: {len(X_train)} train, {len(X_test)} test")

        # Build & train
        hybrid = HybridLSTMTransformer()
        input_shape = (X_train.shape[1], X_train.shape[2])
        hybrid.build(input_shape)
        print(f"✅ Model: {hybrid.model.count_params():,} params")

        print(f"🤖 Training with {epochs} epochs...")
        trainer.train(hybrid, X_train, y_train, epochs=epochs, batch_size=32)

        # Evaluate
        metrics = trainer.evaluate(hybrid, X_test, y_test)
        print(f"\n📈 Results:")
        print(f"   Accuracy:  {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
        print(f"   Precision: {metrics['precision']:.4f}")
        print(f"   Recall:    {metrics['recall']:.4f}")

        # Save
        model_dir = trainer.save_model(hybrid, ticker, interval)
        print(f"✅ Model saved: {model_dir}")

        return {
            'ticker': ticker,
            'accuracy': metrics['accuracy'],
            'precision': metrics['precision'],
            'epochs': epochs,
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Improve best models."""
    print(f"\n{'='*70}")
    print(f"IMPROVING BEST MODELS - ADVANCED TRAINING")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    results = []
    for ticker, interval, epochs in BEST_MODELS:
        result = improve_model(ticker, interval, epochs)
        if result:
            results.append(result)

    # Summary
    print(f"\n{'='*70}")
    print(f"IMPROVEMENT SUMMARY")
    print(f"{'='*70}\n")

    if results:
        print(f"{'Ticker':<12} {'Accuracy':<12} {'Precision':<12} {'Epochs':<10}")
        print("-" * 46)
        for r in sorted(results, key=lambda x: x['accuracy'], reverse=True):
            print(f"{r['ticker']:<12} {r['accuracy']:.4f}      {r['precision']:.4f}      {r['epochs']:<10}")

    print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
