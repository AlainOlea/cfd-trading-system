#!/usr/bin/env python3
"""
Train Ensemble Models - Complete Coverage
===========================================
Train both LSTM and XGBoost models for all key periods.

Priority: GLD (64%) > MSFT (60%) > QQQ (56%)

Models to train:
- 1h models (XGBoost): GLD, MSFT, QQQ
- Optionally re-train 1d models for consistency
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


# Priority training plan (best performers first)
TRAINING_PLAN = [
    # (ticker, interval, days, epochs, models_to_train)
    ('GLD', '1h', 90, 50, ['lstm', 'xgb']),       # Gold - best performer ⭐
    ('MSFT', '1h', 90, 50, ['lstm', 'xgb']),      # Microsoft - second best ⭐
    ('QQQ', '1h', 90, 50, ['lstm', 'xgb']),       # Nasdaq - third best
]


def train_models(ticker, interval, days, epochs, models_to_train):
    """Train LSTM and/or XGBoost models for a ticker+interval."""
    print(f"\n{'='*70}")
    print(f"Training {ticker} | {interval} | {days}d")
    print(f"Models: {', '.join(models_to_train)}")
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
            'lstm': None,
            'xgb': None,
        }

        # ============ LSTM TRAINING ============
        if 'lstm' in models_to_train:
            print(f"\n{'─'*70}")
            print(f"LSTM TRAINING")
            print(f"{'─'*70}")

            lstm_start = time.time()

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

        # ============ XGBOOST TRAINING ============
        if 'xgb' in models_to_train:
            print(f"\n{'─'*70}")
            print(f"XGBOOST TRAINING")
            print(f"{'─'*70}")

            xgb_start = time.time()

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
            print(f"\n📊 Feature Importance (Top 5):")
            for idx, (_, row) in enumerate(importance_df.head(5).iterrows()):
                print(f"   {row['feature']:15s} {row['percentage']:6.2f}%")

            result['xgb'] = {
                'accuracy': xgb_metrics['accuracy'],
                'time': xgb_time,
            }

        return result

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Train all models in priority order."""
    print(f"\n{'='*70}")
    print(f"🤖 ENSEMBLE MODEL TRAINING - Priority Build")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    results = []

    # Train models in priority order
    for ticker, interval, days, epochs, models in TRAINING_PLAN:
        result = train_models(ticker, interval, days, epochs, models)
        if result:
            results.append(result)

    # Summary
    print(f"\n{'='*70}")
    print(f"📊 TRAINING SUMMARY")
    print(f"{'='*70}\n")

    print(f"{'Ticker':<10} {'Interval':<10} {'LSTM Acc':<12} {'XGB Acc':<12} {'Status':<15}")
    print(f"{'-'*70}")

    for r in results:
        lstm_acc = f"{r['lstm']['accuracy']:.2%}" if r['lstm'] else "N/A"
        xgb_acc = f"{r['xgb']['accuracy']:.2%}" if r['xgb'] else "N/A"
        status = "✅ Complete"

        print(f"{r['ticker']:<10} {r['interval']:<10} {lstm_acc:<12} {xgb_acc:<12} {status:<15}")

    print(f"\n{'='*70}")
    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    print(f"✅ All models trained. Ready for live_signals_ensemble.py\n")


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
