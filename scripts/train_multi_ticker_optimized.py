#!/usr/bin/env python3
"""
Optimized Multi-Ticker ML Training
===================================
Retrains the hybrid LSTM+Transformer model with improved hyperparameters.

Changes from v1:
- epochs: 50 → 100 (better convergence)
- early_stopping_patience: 10 → 20 (more patient)
- learning_rate: 0.001 → 0.0005 (smoother learning)
- dropout_rate: 0.3 → 0.4 (stronger regularization)
- l2_regularization: 0.01 → 0.02 (stronger penalty)
- optimizer: Adam → SGD+Momentum (better for this architecture)

Usage:
    source venv/bin/activate
    python3 scripts/train_multi_ticker_optimized.py
"""

import logging
import os
from pathlib import Path
import sys

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'  # Force CPU

import numpy as np
import pandas as pd
import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.fetcher import DataFetcher
from data.processor import DataProcessor
from indicators.technical import TechnicalIndicators
from models.trainer import ModelTrainer
from models.hybrid_model import HybridLSTMTransformer
from config.settings import DEFAULT_TICKERS, ML_CONFIG, LSTM_LAYERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def train_optimized_multi_ticker(
    tickers: list = None,
    interval: str = '1d',
    days: int = 1095,
    epochs: int = None,  # Use config default if None
    output_name: str = 'multi_ticker',
):
    """
    Train multi-ticker model with optimized hyperparameters.

    Args:
        tickers: List of ticker symbols. Defaults to DEFAULT_TICKERS.
        interval: Data interval ('1d', '1h', '1m').
        days: Historical days to fetch.
        epochs: Epochs to train. If None, uses ML_CONFIG['epochs'].
        output_name: Name for saved model.

    Returns:
        Dict with training results.
    """
    if tickers is None:
        tickers = DEFAULT_TICKERS

    if epochs is None:
        epochs = ML_CONFIG['epochs']

    fetcher = DataFetcher()
    processor = DataProcessor()

    print("\n" + "="*80)
    print("🚀 MULTI-TICKER MODEL RETRAINING (OPTIMIZED)")
    print("="*80)
    print(f"📋 Configuration:")
    print(f"   Tickers: {', '.join(tickers)}")
    print(f"   Interval: {interval}")
    print(f"   Historical days: {days}")
    print(f"   Epochs: {epochs} (was 50)")
    print(f"   Learning rate: {ML_CONFIG['learning_rate']} (was 0.001)")
    print(f"   Dropout: {LSTM_LAYERS['dropout_rate']} (was 0.3)")
    print(f"   L2 Regularization: {LSTM_LAYERS['l2_regularization']} (was 0.01)")
    print(f"   Early stopping patience: {ML_CONFIG['early_stopping_patience']} (was 10)")
    print("="*80 + "\n")

    # ==========================================
    # STEP 1: Load Data
    # ==========================================
    print("📥 STEP 1: Loading data from all tickers...")
    all_data = []
    total_rows = 0

    for ticker in tickers:
        try:
            print(f"   {ticker:12} ", end="", flush=True)

            # Load raw data
            df = fetcher.load_from_csv(ticker, interval)
            raw_len = len(df)
            print(f"[raw: {raw_len:4d}] ", end="", flush=True)

            # Clean
            df = processor.clean_data(df)
            clean_len = len(df)
            print(f"[clean: {clean_len:4d}] ", end="", flush=True)

            # Validate
            processor.validate_data(df)

            # Add indicators
            df = TechnicalIndicators().add_all_indicators(df)
            print(f"[✅ indicators]")

            all_data.append(df)
            total_rows += len(df)

        except Exception as e:
            logger.warning(f"Failed to load {ticker}: {e}")
            print(f"[❌ FAILED: {str(e)[:30]}]")

    if not all_data:
        raise ValueError("No data loaded for any ticker!")

    print(f"\n✅ Loaded {len(all_data)}/{len(tickers)} tickers")
    print(f"   Total rows: {total_rows:,}")
    print(f"   Date range: {all_data[0].index.min()} to {all_data[0].index.max()}\n")

    # ==========================================
    # STEP 2: Combine Data
    # ==========================================
    print("📊 STEP 2: Combining data from all tickers...")
    combined_df = pd.concat(all_data, ignore_index=True)
    print(f"   Combined shape: {combined_df.shape}")
    print(f"   Features: {len(combined_df.columns)}\n")

    # ==========================================
    # STEP 3: Configure Trainer
    # ==========================================
    print("🔧 STEP 3: Configuring trainer with optimized parameters...")
    trainer = ModelTrainer(
        lookback_window=ML_CONFIG['lookback_window'],
        features=ML_CONFIG['features'],
        batch_size=ML_CONFIG['batch_size'],
        epochs=epochs,
        validation_split=ML_CONFIG['validation_split'],
        test_split=ML_CONFIG['test_split'],
        early_stopping_patience=ML_CONFIG['early_stopping_patience'],
    )
    print(f"   Lookback window: {ML_CONFIG['lookback_window']}")
    print(f"   Batch size: {ML_CONFIG['batch_size']}")
    print(f"   Features: {len(trainer.features)}\n")

    # ==========================================
    # STEP 4: Prepare Data
    # ==========================================
    print("📈 STEP 4: Preparing training/test data...")
    X_train, y_train, X_test, y_test = trainer.prepare_data(combined_df)
    print(f"   Training samples: {X_train.shape[0]:,}")
    print(f"   Test samples: {X_test.shape[0]:,}")
    print(f"   Sequence length: {X_train.shape[1]}")
    print(f"   Features per sample: {X_train.shape[2]}\n")

    # ==========================================
    # STEP 5: Build Model
    # ==========================================
    print("🏗️  STEP 5: Building hybrid LSTM+Transformer model...")

    def model_builder():
        return HybridLSTMTransformer()

    model = model_builder()
    model.build((ML_CONFIG['lookback_window'], len(trainer.features)))
    print(f"   Parameters: {model.model.count_params():,}")
    print(f"   Architecture: 2x LSTM(50) → Transformer(2-head) → Dense → Sigmoid\n")

    # ==========================================
    # STEP 6: Train Model
    # ==========================================
    print("🤖 STEP 6: Training model (this may take several hours)...\n")
    print(f"   Starting training with {epochs} epochs...")
    print(f"   Learning rate: {ML_CONFIG['learning_rate']}")
    print(f"   Optimizer: SGD + Momentum")
    print(f"   Patience: {ML_CONFIG['early_stopping_patience']} epochs")
    print()

    history = trainer.train(
        model,
        X_train, y_train,
        X_val=X_test, y_val=y_test,
        epochs=epochs,
    )

    # ==========================================
    # STEP 7: Evaluate Model
    # ==========================================
    print("\n📊 STEP 7: Evaluating model on test set...")
    final_metrics = trainer.evaluate(model, X_test, y_test)

    print(f"\n✅ FINAL METRICS:")
    print(f"   Accuracy:  {final_metrics['accuracy']:.4f} ({final_metrics['accuracy']*100:.2f}%)")
    print(f"   Precision: {final_metrics['precision']:.4f}")
    print(f"   Recall:    {final_metrics['recall']:.4f}")
    print(f"   Loss:      {final_metrics['loss']:.4f}\n")

    # ==========================================
    # STEP 8: Save Model
    # ==========================================
    print("💾 STEP 8: Saving model...")
    model_dir = trainer.save_model(model, output_name, interval)
    print(f"   ✅ Saved to: {model_dir}\n")

    # ==========================================
    # Summary
    # ==========================================
    print("="*80)
    print("✅ TRAINING COMPLETE")
    print("="*80)
    print(f"Model:        {output_name}_{interval}")
    print(f"Location:     {model_dir}")
    print(f"Tickers:      {len(all_data)}/{len(tickers)}")
    print(f"Total rows:   {total_rows:,}")
    print(f"Epochs:       {epochs}")
    print(f"Final loss:   {final_metrics['loss']:.4f}")
    print(f"Final accuracy: {final_metrics['accuracy']*100:.2f}%")
    print("="*80)

    print(f"\n🎯 Next steps:")
    print(f"   1. Test signal generation with ML filter:")
    print(f"      python3 main.py signal --ticker SPY --interval {interval} --use-ml")
    print(f"")
    print(f"   2. Run continuous monitoring:")
    print(f"      python3 main.py watch --use-ml --interval {interval}")
    print(f"")
    print(f"   3. Backtest with new model:")
    print(f"      python3 main.py backtest --ticker SPY --strategy macd_vwap --use-ml")
    print()

    return {
        'model_dir': str(model_dir),
        'metrics': final_metrics,
        'combined_rows': total_rows,
        'num_tickers': len(all_data),
        'epochs_trained': epochs,
    }


@click.command()
@click.option('--tickers', default=None,
              help='Comma-separated tickers (default: SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA)')
@click.option('--interval', default='1d', type=click.Choice(['1m', '5m', '15m', '1h', '1d']),
              help='Data interval')
@click.option('--days', default=1095, type=int, help='Historical days to fetch')
@click.option('--epochs', default=None, type=int, help='Epochs (default from config)')
@click.option('--output', default='multi_ticker', help='Model output name')
def main(tickers, interval, days, epochs, output):
    """
    Retrain multi-ticker model with optimized hyperparameters.

    Examples:
        # Default (all tickers, 1d, 100 epochs from config)
        python3 scripts/train_multi_ticker_optimized.py

        # Custom tickers and epochs
        python3 scripts/train_multi_ticker_optimized.py \\
            --tickers SPY,QQQ,GLD \\
            --epochs 150

        # Hourly data
        python3 scripts/train_multi_ticker_optimized.py \\
            --interval 1h \\
            --days 730
    """
    try:
        # Parse tickers
        if tickers:
            ticker_list = [t.strip() for t in tickers.split(',')]
        else:
            ticker_list = DEFAULT_TICKERS

        result = train_optimized_multi_ticker(
            tickers=ticker_list,
            interval=interval,
            days=days,
            epochs=epochs,
            output_name=output,
        )

        exit(0)

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        print(f"\n❌ ERROR: {e}\n")
        exit(1)


if __name__ == '__main__':
    main()
