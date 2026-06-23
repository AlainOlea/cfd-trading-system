#!/usr/bin/env python3
"""
Multi-Ticker LSTM Model Training
=================================
Trains models for multiple tickers and intervals to improve accuracy.
"""

import sys
from pathlib import Path
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import TICKERS
from config.gpu_config import configure_gpu
configure_gpu()

from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from models.hybrid_model import HybridLSTMTransformer
from models.trainer import ModelTrainer


def train_ticker(ticker, interval, epochs=30):
    """Train a model for a specific ticker/interval combination."""
    print(f"\n{'='*70}")
    print(f"Training: {ticker:12s} | Interval: {interval:3s} | Epochs: {epochs}")
    print(f"{'='*70}")

    try:
        # 1. Fetch data
        fetcher = DataFetcher()
        processor = DataProcessor()

        try:
            df = fetcher.load_from_csv(ticker, interval)
            print(f"✅ Loaded cached data: {len(df)} rows")
        except FileNotFoundError:
            print(f"📥 Fetching {ticker} ({interval}, 365d)...")
            df = fetcher.fetch_yfinance(ticker, interval, days=365)
            if len(df) < 100:
                print(f"⚠️  Insufficient data ({len(df)} rows). Skipping {ticker}.")
                return None
            df = processor.clean_data(df)
            fetcher.save_to_csv(df, ticker, interval)
            print(f"✅ Fetched and saved: {len(df)} rows")

        # 2. Add indicators
        print(f"📊 Computing indicators...")
        df = TechnicalIndicators.add_all_indicators(df)

        # 3. Prepare data
        trainer = ModelTrainer(epochs=epochs)
        X_train, y_train, X_test, y_test = trainer.prepare_data(df)
        print(f"✅ Data prepared: {len(X_train)} train, {len(X_test)} test samples")

        # 4. Build model
        hybrid = HybridLSTMTransformer()
        input_shape = (X_train.shape[1], X_train.shape[2])
        hybrid.build(input_shape)
        print(f"✅ Model built: {hybrid.model.count_params():,} parameters")

        # 5. Train
        print(f"🤖 Training...")
        trainer.train(hybrid, X_train, y_train, epochs=epochs, batch_size=32)

        # 6. Evaluate
        metrics = trainer.evaluate(hybrid, X_test, y_test)
        print(f"\n📈 Results:")
        print(f"   Accuracy:  {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
        print(f"   Precision: {metrics['precision']:.4f}")
        print(f"   Recall:    {metrics['recall']:.4f}")
        print(f"   Loss:      {metrics['loss']:.4f}")

        # 7. Save model
        model_dir = trainer.save_model(hybrid, ticker, interval)
        print(f"✅ Model saved to: {model_dir}")

        return {
            'ticker': ticker,
            'interval': interval,
            'accuracy': metrics['accuracy'],
            'precision': metrics['precision'],
            'recall': metrics['recall'],
            'loss': metrics['loss'],
            'samples': len(X_train) + len(X_test),
        }

    except Exception as e:
        print(f"❌ Error training {ticker}: {e}")
        return None


def main():
    """Train models for all tickers."""
    print(f"\n{'='*70}")
    print(f"CFD TRADING SYSTEM - MULTI-TICKER MODEL TRAINING")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    # Configuration
    training_config = [
        # (ticker, interval, epochs)
        ('SPY', '1d', 50),      # S&P 500 daily
        ('QQQ', '1d', 50),      # Nasdaq daily
        ('GLD', '1d', 40),      # Gold daily
        ('BTC-USD', '1h', 40),  # Bitcoin hourly
        ('ETH-USD', '1h', 40),  # Ethereum hourly
        ('AAPL', '1d', 35),     # Apple daily
        ('NVDA', '1d', 35),     # NVIDIA daily
        ('MSFT', '1d', 35),     # Microsoft daily
        ('SOL-USD', '1h', 30),  # Solana hourly
    ]

    results = []
    failed = []

    for ticker, interval, epochs in training_config:
        result = train_ticker(ticker, interval, epochs)
        if result:
            results.append(result)
        else:
            failed.append(f"{ticker}/{interval}")

    # Summary
    print(f"\n{'='*70}")
    print(f"TRAINING SUMMARY")
    print(f"{'='*70}")

    if results:
        print(f"\n✅ Successfully trained {len(results)} models:\n")
        print(f"{'Ticker':<12} {'Interval':<10} {'Accuracy':<12} {'Precision':<12} {'Samples':<10}")
        print("-" * 56)
        for r in sorted(results, key=lambda x: x['accuracy'], reverse=True):
            print(f"{r['ticker']:<12} {r['interval']:<10} {r['accuracy']:.4f}      {r['precision']:.4f}      {r['samples']:<10}")

        avg_accuracy = sum(r['accuracy'] for r in results) / len(results)
        print("-" * 56)
        print(f"{'AVERAGE':<12} {'':<10} {avg_accuracy:.4f}      {'':10s}")

    if failed:
        print(f"\n❌ Failed to train {len(failed)} models:")
        for ticker in failed:
            print(f"   - {ticker}")

    print(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    return len(results), len(failed)


if __name__ == '__main__':
    success, failed = main()
    sys.exit(0 if failed == 0 else 1)
