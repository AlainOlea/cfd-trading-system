#!/usr/bin/env python3
"""
Intraday Model Expansion
========================
Train 1h + XGBoost models for additional tickers to expand ensemble coverage.

Priority:
1. Existing stocks without 1h: AAPL, NVDA, SPY (high volume)
2. New commodities: GDX (gold miners), XLU (utilities), IWM (small cap)
"""

import sys
from pathlib import Path
import time
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from config.gpu_config import configure_gpu
configure_gpu()

from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from models.trainer import ModelTrainer
from models.xgboost_model import XGBoostTrader


# Expansion training plan
# (ticker, interval, days, epochs, priority_level)
EXPANSION_PLAN = [
    # High priority: Existing stocks that need 1h ensemble
    ('AAPL', '1h', 90, 50, 1),
    ('NVDA', '1h', 90, 50, 1),
    ('SPY', '1h', 90, 50, 1),

    # Medium priority: New commodities
    ('GDX', '1h', 90, 50, 2),
    ('XLU', '1h', 90, 50, 2),
    ('IWM', '1h', 90, 50, 2),
]


def train_models(ticker, interval, days, epochs, priority):
    """Train LSTM and XGBoost models for a ticker+interval."""
    print(f"\n{'='*70}")
    print(f"[Priority {priority}] Training {ticker} | {interval} | {days}d")
    print(f"{'='*70}\n")

    try:
        # Fetch data
        fetcher = DataFetcher()
        processor = DataProcessor()

        try:
            df = fetcher.load_from_csv(ticker, interval)
            print(f"✅ Loaded from CSV: {len(df)} rows")
        except FileNotFoundError:
            print(f"📥 Fetching from Yahoo Finance ({interval}, {days}d)...")
            df = fetcher.fetch_yfinance(ticker, interval, days)
            if df is None or len(df) == 0:
                print(f"❌ No data available for {ticker} {interval}")
                return None
            df = processor.clean_data(df)
            fetcher.save_to_csv(df, ticker, interval)
            print(f"✅ Fetched: {len(df)} rows")

        # Add indicators
        df = TechnicalIndicators.add_all_indicators(df)
        print(f"✅ Indicators added: {df.shape[1]} columns")

        result = {
            'ticker': ticker,
            'interval': interval,
            'priority': priority,
            'lstm': None,
            'xgb': None,
        }

        # ============ LSTM TRAINING ============
        print(f"\n{'─'*70}")
        print(f"LSTM TRAINING ({epochs} epochs)")
        print(f"{'─'*70}")

        lstm_start = time.time()

        try:
            # Prepare data
            trainer = ModelTrainer(epochs=epochs)
            X_train, y_train, X_test, y_test = trainer.prepare_data(df)
            print(f"Data: train={len(X_train)}, test={len(X_test)}")

            # Build and train
            from models.hybrid_model import HybridLSTMTransformer
            lstm = HybridLSTMTransformer()
            input_shape = (X_train.shape[1], X_train.shape[2])
            lstm.build(input_shape)

            trainer.train(lstm, X_train, y_train, epochs=epochs, batch_size=32)
            lstm_metrics = trainer.evaluate(lstm, X_test, y_test)

            lstm_time = time.time() - lstm_start

            print(f"\n⏱️  Time: {lstm_time:.2f}s")
            print(f"📈 Accuracy: {lstm_metrics['accuracy']:.4f}")
            print(f"   Precision: {lstm_metrics['precision']:.4f}")
            print(f"   Recall: {lstm_metrics['recall']:.4f}")

            # Save
            model_dir = trainer.save_model(lstm, ticker, interval)
            print(f"✅ Saved: {model_dir}")

            result['lstm'] = {
                'accuracy': lstm_metrics['accuracy'],
                'time': lstm_time,
            }
        except Exception as e:
            print(f"⚠️  LSTM training failed: {e}")
            result['lstm'] = {'error': str(e)}

        # ============ XGBOOST TRAINING ============
        print(f"\n{'─'*70}")
        print(f"XGBOOST TRAINING (100 estimators)")
        print(f"{'─'*70}")

        xgb_start = time.time()

        try:
            # Prepare data
            xgb_trainer = XGBoostTrader(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1
            )

            X_train, y_train, X_test, y_test = xgb_trainer.prepare_data(df)
            print(f"Data: train={len(X_train)}, test={len(X_test)}")

            # Train
            xgb_trainer.train(X_train, y_train, epochs=100)
            xgb_metrics = xgb_trainer.evaluate(X_test, y_test)

            xgb_time = time.time() - xgb_start

            print(f"\n⏱️  Time: {xgb_time:.2f}s")
            print(f"📈 Accuracy: {xgb_metrics['accuracy']:.4f}")
            print(f"   Precision: {xgb_metrics['precision']:.4f}")
            print(f"   Recall: {xgb_metrics['recall']:.4f}")

            # Save
            model_dir = xgb_trainer.save(ticker, interval)
            print(f"✅ Saved: {model_dir}")

            # Feature importance
            importance_df = xgb_trainer.get_feature_importance()
            print(f"\n📊 Feature Importance (Top 3):")
            for idx, (_, row) in enumerate(importance_df.head(3).iterrows()):
                print(f"   {row['feature']:15s} {row['percentage']:6.2f}%")

            result['xgb'] = {
                'accuracy': xgb_metrics['accuracy'],
                'time': xgb_time,
            }
        except Exception as e:
            print(f"⚠️  XGBoost training failed: {e}")
            result['xgb'] = {'error': str(e)}

        return result

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Train expansion models in priority order."""
    print(f"\n{'='*70}")
    print(f"🚀 INTRADAY MODEL EXPANSION - Training {len(EXPANSION_PLAN)} Tickers")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    results = []

    # Train models in priority order
    for ticker, interval, days, epochs, priority in EXPANSION_PLAN:
        result = train_models(ticker, interval, days, epochs, priority)
        if result:
            results.append(result)

    # Summary
    print(f"\n{'='*70}")
    print(f"📊 EXPANSION SUMMARY")
    print(f"{'='*70}\n")

    print(f"{'Priority':<10} {'Ticker':<10} {'Interval':<10} {'LSTM Acc':<12} {'XGB Acc':<12} {'Status':<15}")
    print(f"{'-'*70}")

    priority_1_results = [r for r in results if r.get('priority') == 1]
    priority_2_results = [r for r in results if r.get('priority') == 2]

    for r in priority_1_results + priority_2_results:
        priority_label = f"P{r['priority']}"
        lstm_acc = f"{r['lstm']['accuracy']:.2%}" if r['lstm'] and 'accuracy' in r['lstm'] else "ERROR"
        xgb_acc = f"{r['xgb']['accuracy']:.2%}" if r['xgb'] and 'accuracy' in r['xgb'] else "ERROR"
        status = "✅ Complete" if (r['lstm'] and r['xgb']) else "⚠️  Partial"

        print(f"{priority_label:<10} {r['ticker']:<10} {r['interval']:<10} {lstm_acc:<12} {xgb_acc:<12} {status:<15}")

    print(f"\n{'='*70}")
    print(f"📈 STATISTICS")
    print(f"{'='*70}")
    print(f"Total models trained: {len(results)}")
    print(f"Priority 1 (stocks): {len(priority_1_results)}")
    print(f"Priority 2 (commodities): {len(priority_2_results)}")

    avg_lstm = sum([r['lstm']['accuracy'] for r in results if r.get('lstm', {}).get('accuracy')]) / max(len([r for r in results if r.get('lstm', {}).get('accuracy')]), 1)
    avg_xgb = sum([r['xgb']['accuracy'] for r in results if r.get('xgb', {}).get('accuracy')]) / max(len([r for r in results if r.get('xgb', {}).get('accuracy')]), 1)

    print(f"\nAverage LSTM accuracy: {avg_lstm:.2%}")
    print(f"Average XGBoost accuracy: {avg_xgb:.2%}")

    print(f"\n{'='*70}")
    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    print(f"✅ Expansion complete. Ensemble coverage now includes intraday signals for {len(results)} new tickers.\n")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
