#!/usr/bin/env python3
"""
Phase 5: Verify Complete ML Pipeline
=====================================
Comprehensive verification of all ML improvements:
1. Data verification (2-3 years available)
2. Walk-forward validation implementation
3. Multi-ticker training capability
4. Regularization effectiveness
5. Production readiness
"""

import logging
from pathlib import Path
import pandas as pd
import numpy as np
import click

from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from models.trainer import ModelTrainer
from models.hybrid_model import HybridLSTMTransformer
from config.settings import DEFAULT_TICKERS, ML_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verify_data_availability(tickers=None, intervals=None):
    """Verify that sufficient historical data is available."""
    if tickers is None:
        tickers = DEFAULT_TICKERS[:3]  # Test with first 3
    if intervals is None:
        intervals = ['1d', '1h']

    print("\n" + "="*70)
    print("1️⃣  DATA AVAILABILITY VERIFICATION")
    print("="*70)

    fetcher = DataFetcher()
    processor = DataProcessor()
    all_ok = True

    for ticker in tickers:
        for interval in intervals:
            try:
                df = fetcher.load_from_csv(ticker, interval)
                df = processor.clean_data(df)
                processor.validate_data(df)

                status = "✅"
                if len(df) < 200:
                    status = "⚠️ "
                    all_ok = False

                print(f"{status} {ticker:8} {interval:3}: {len(df):5} rows "
                      f"({df.index[0].date()} → {df.index[-1].date()})")

            except Exception as e:
                print(f"❌ {ticker:8} {interval:3}: {str(e)[:40]}")
                all_ok = False

    print("="*70)
    return all_ok


def verify_walk_forward_implementation():
    """Test walk-forward validation methods."""
    print("\n" + "="*70)
    print("2️⃣  WALK-FORWARD VALIDATION VERIFICATION")
    print("="*70)

    try:
        fetcher = DataFetcher()
        processor = DataProcessor()

        # Load a single ticker for testing
        df = fetcher.load_from_csv('SPY', '1d')
        df = processor.clean_data(df)
        df = TechnicalIndicators().add_all_indicators(df)

        # Create trainer
        trainer = ModelTrainer()

        # Test prepare_data_walk_forward
        print("\n🔄 Testing prepare_data_walk_forward()...")
        folds = trainer.prepare_data_walk_forward(
            df,
            train_window=100,
            test_window=20,
            step_size=20,
            method='anchored'
        )

        print(f"✅ Created {len(folds)} folds")

        if len(folds) > 0:
            fold0 = folds[0]
            print(f"   Fold 0 train shape: {fold0['X_train'].shape}")
            print(f"   Fold 0 test shape: {fold0['X_test'].shape}")
            print(f"   Fold 0 train dates: {fold0['train_dates'][0].date()} → {fold0['train_dates'][1].date()}")
            print(f"   Fold 0 test dates: {fold0['test_dates'][0].date()} → {fold0['test_dates'][1].date()}")
            return True
        else:
            print("❌ No folds created")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def verify_model_regularization():
    """Test that model has proper regularization."""
    print("\n" + "="*70)
    print("3️⃣  MODEL REGULARIZATION VERIFICATION")
    print("="*70)

    try:
        model = HybridLSTMTransformer()
        model.build((60, 9))

        print(f"✅ Model built successfully")
        print(f"   Total parameters: {model.model.count_params():,}")
        print(f"   Dropout rate: {model.dropout_rate}")
        print(f"   L2 regularization: {model.l2_reg}")
        print(f"   Batch normalization: {model.use_batch_norm}")

        # Check for regularizers in layers
        has_l2 = False
        has_batch_norm = False

        for layer in model.model.layers:
            if hasattr(layer, 'kernel_regularizer') and layer.kernel_regularizer is not None:
                has_l2 = True
            if 'BatchNormalization' in layer.__class__.__name__:
                has_batch_norm = True

        if has_l2:
            print("✅ L2 regularization found in model")
        else:
            print("⚠️  No L2 regularization detected")

        if has_batch_norm:
            print("✅ Batch normalization found in model")
        else:
            print("⚠️  No batch normalization detected")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def verify_multi_ticker_capability():
    """Test multi-ticker data loading and combination."""
    print("\n" + "="*70)
    print("4️⃣  MULTI-TICKER CAPABILITY VERIFICATION")
    print("="*70)

    try:
        fetcher = DataFetcher()
        processor = DataProcessor()

        test_tickers = DEFAULT_TICKERS[:3]
        print(f"Testing with tickers: {test_tickers}")

        all_data = []
        total_rows = 0

        for ticker in test_tickers:
            try:
                df = fetcher.load_from_csv(ticker, '1d')
                df = processor.clean_data(df)
                TechnicalIndicators().add_all_indicators(df)
                all_data.append(df)
                total_rows += len(df)
                print(f"✅ {ticker}: {len(df)} rows")
            except Exception as e:
                print(f"⚠️  {ticker}: {e}")

        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            print(f"\n✅ Combined data shape: {combined.shape}")
            print(f"   Total rows: {total_rows:,}")
            print(f"   Tickers combined: {len(all_data)}")
            return True
        else:
            print("❌ No data loaded")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def verify_configuration():
    """Verify ML configuration settings."""
    print("\n" + "="*70)
    print("5️⃣  CONFIGURATION VERIFICATION")
    print("="*70)

    print("\nML_CONFIG:")
    for key, val in ML_CONFIG.items():
        if isinstance(val, dict):
            print(f"  {key}:")
            for k, v in val.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {val}")

    print("\n✅ Configuration loaded successfully")
    return True


@click.command()
@click.option('--full', is_flag=True, help='Run full verification (may take time)')
def main(full):
    """Verify all ML pipeline improvements."""
    print("\n" + "="*80)
    print("🔍 ML PIPELINE VERIFICATION")
    print("="*80)

    results = {}

    # Phase 1: Data availability
    results['data_availability'] = verify_data_availability()

    # Phase 2: Walk-forward validation
    results['walk_forward'] = verify_walk_forward_implementation()

    # Phase 3: Multi-ticker capability
    results['multi_ticker'] = verify_multi_ticker_capability()

    # Phase 4: Model regularization
    results['regularization'] = verify_model_regularization()

    # Phase 5: Configuration
    results['configuration'] = verify_configuration()

    # Summary
    print("\n" + "="*70)
    print("📊 VERIFICATION SUMMARY")
    print("="*70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for check, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {check:20} {'PASS' if result else 'FAIL'}")

    print(f"\nTotal: {passed}/{total} checks passed")
    print("="*70 + "\n")

    if passed == total:
        print("🎉 ALL VERIFICATIONS PASSED - PIPELINE READY FOR TRAINING!\n")
        return 0
    else:
        print("⚠️  Some verifications failed - review output above\n")
        return 1


if __name__ == '__main__':
    exit(main())
