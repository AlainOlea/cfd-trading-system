#!/usr/bin/env python3
"""
LSTM vs XGBoost Comparison
===========================
Train both models on the same data and compare accuracy, speed, and interpretability.
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
from models.hybrid_model import HybridLSTMTransformer
from models.trainer import ModelTrainer
from models.xgboost_model import XGBoostTrader


COMPARISON_CONFIG = [
    ('GLD', '1d', 365),
    ('MSFT', '1d', 365),
    ('QQQ', '1d', 365),
]


def compare_ticker(ticker: str, interval: str, days: int):
    """Compare LSTM and XGBoost on a single ticker."""
    print(f"\n{'='*70}")
    print(f"COMPARING: {ticker:8s} | {interval} | {days}d")
    print(f"{'='*70}\n")

    try:
        # Fetch data
        fetcher = DataFetcher()
        processor = DataProcessor()

        try:
            df = fetcher.load_from_csv(ticker, interval)
            print(f"✅ Loaded from CSV: {len(df)} rows")
        except FileNotFoundError:
            print(f"📥 Fetching from Yahoo Finance...")
            df = fetcher.fetch_yfinance(ticker, interval, days)
            df = processor.clean_data(df)
            fetcher.save_to_csv(df, ticker, interval)
            print(f"✅ Fetched: {len(df)} rows")

        # Add indicators
        df = TechnicalIndicators.add_all_indicators(df)

        # Prepare data (shared between both models)
        trainer = ModelTrainer(epochs=50)
        X_train, y_train, X_test, y_test = trainer.prepare_data(df)
        print(f"📊 Train: {len(X_train)} | Test: {len(X_test)}\n")

        # ============ LSTM TRAINING ============
        print(f"{'─'*70}")
        print(f"LSTM TRAINING")
        print(f"{'─'*70}")

        lstm_start = time.time()

        hybrid = HybridLSTMTransformer()
        input_shape = (X_train.shape[1], X_train.shape[2])
        hybrid.build(input_shape)

        trainer.train(hybrid, X_train, y_train, epochs=50, batch_size=32)
        lstm_metrics = trainer.evaluate(hybrid, X_test, y_test)

        lstm_time = time.time() - lstm_start

        print(f"⏱️  Time: {lstm_time:.2f}s")
        print(f"📈 Accuracy: {lstm_metrics['accuracy']:.4f}")
        print(f"   Precision: {lstm_metrics['precision']:.4f}")
        print(f"   Recall: {lstm_metrics['recall']:.4f}\n")

        # ============ XGBOOST TRAINING ============
        print(f"{'─'*70}")
        print(f"XGBOOST TRAINING")
        print(f"{'─'*70}")

        xgb_start = time.time()

        xgb_trainer = XGBoostTrader(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1
        )

        X_train_xgb, y_train_xgb, X_test_xgb, y_test_xgb = xgb_trainer.prepare_data(df)
        xgb_trainer.train(X_train_xgb, y_train_xgb, epochs=100)
        xgb_metrics = xgb_trainer.evaluate(X_test_xgb, y_test_xgb)

        xgb_time = time.time() - xgb_start

        print(f"⏱️  Time: {xgb_time:.2f}s")
        print(f"📈 Accuracy: {xgb_metrics['accuracy']:.4f}")
        print(f"   Precision: {xgb_metrics['precision']:.4f}")
        print(f"   Recall: {xgb_metrics['recall']:.4f}\n")

        # ============ FEATURE IMPORTANCE ============
        print(f"{'─'*70}")
        print(f"FEATURE IMPORTANCE (XGBoost)")
        print(f"{'─'*70}\n")

        importance_df = xgb_trainer.get_feature_importance()
        for idx, row in importance_df.iterrows():
            print(f"  {row['feature']:15s} {row['percentage']:6.2f}%  {'█' * int(row['percentage']/5)}")
        print()

        # ============ COMPARISON SUMMARY ============
        print(f"{'='*70}")
        print(f"COMPARISON SUMMARY")
        print(f"{'='*70}\n")

        comparison = {
            'Metric': ['Accuracy', 'Precision', 'Recall', 'Training Time (s)', 'Speed (x faster)'],
            'LSTM': [
                f"{lstm_metrics['accuracy']:.4f}",
                f"{lstm_metrics['precision']:.4f}",
                f"{lstm_metrics['recall']:.4f}",
                f"{lstm_time:.2f}",
                f"1.0x (baseline)"
            ],
            'XGBoost': [
                f"{xgb_metrics['accuracy']:.4f}",
                f"{xgb_metrics['precision']:.4f}",
                f"{xgb_metrics['recall']:.4f}",
                f"{xgb_time:.2f}",
                f"{lstm_time/xgb_time:.1f}x faster"
            ],
            'Winner': [
                "✅ XGB" if xgb_metrics['accuracy'] > lstm_metrics['accuracy'] else "✅ LSTM",
                "✅ XGB" if xgb_metrics['precision'] > lstm_metrics['precision'] else "✅ LSTM",
                "✅ XGB" if xgb_metrics['recall'] > lstm_metrics['recall'] else "✅ LSTM",
                f"✅ XGB ({lstm_time/xgb_time:.1f}x faster)",
                "✅ XGB"
            ]
        }

        for i, metric in enumerate(comparison['Metric']):
            print(f"{metric:20s} | LSTM: {comparison['LSTM'][i]:15s} | XGB: {comparison['XGBoost'][i]:15s} | {comparison['Winner'][i]}")

        print()

        # Save models
        lstm_dir = trainer.save_model(hybrid, ticker, interval)
        xgb_dir = xgb_trainer.save(ticker, interval)
        print(f"✅ LSTM saved: {lstm_dir}")
        print(f"✅ XGBoost saved: {xgb_dir}\n")

        return {
            'ticker': ticker,
            'interval': interval,
            'lstm_accuracy': lstm_metrics['accuracy'],
            'xgb_accuracy': xgb_metrics['accuracy'],
            'lstm_time': lstm_time,
            'xgb_time': xgb_time,
            'speedup': lstm_time / xgb_time,
            'winner': 'XGBoost' if xgb_metrics['accuracy'] > lstm_metrics['accuracy'] else 'LSTM',
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Compare LSTM and XGBoost across multiple tickers."""
    print(f"\n{'='*70}")
    print(f"LSTM vs XGBOOST COMPARISON")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    results = []

    for ticker, interval, days in COMPARISON_CONFIG:
        result = compare_ticker(ticker, interval, days)
        if result:
            results.append(result)

    # Final Summary
    if results:
        print(f"\n{'='*70}")
        print(f"FINAL SUMMARY")
        print(f"{'='*70}\n")

        print(f"{'Ticker':<10} {'LSTM Acc':<12} {'XGB Acc':<12} {'Winner':<12} {'Speedup':<12}")
        print(f"{'-'*58}")

        xgb_wins = 0
        lstm_wins = 0
        total_speedup = 0

        for r in results:
            winner = r['winner']
            if winner == 'XGBoost':
                xgb_wins += 1
            else:
                lstm_wins += 1
            total_speedup += r['speedup']

            print(
                f"{r['ticker']:<10} "
                f"{r['lstm_accuracy']:<12.4f} "
                f"{r['xgb_accuracy']:<12.4f} "
                f"{winner:<12} "
                f"{r['speedup']:<12.1f}x"
            )

        print(f"\n{'='*70}")
        print(f"📊 STATISTICS")
        print(f"{'='*70}")
        print(f"XGBoost wins: {xgb_wins}/{len(results)} ({xgb_wins*100/len(results):.0f}%)")
        print(f"LSTM wins: {lstm_wins}/{len(results)} ({lstm_wins*100/len(results):.0f}%)")
        print(f"Average speedup: {total_speedup/len(results):.1f}x")
        print(f"\n✅ RECOMMENDATION: ", end="")

        if xgb_wins >= lstm_wins:
            print("Use XGBoost for speed + comparable accuracy")
        else:
            print("Use LSTM or ensemble both models")

        print(f"\n{'='*70}\n")

    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


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
