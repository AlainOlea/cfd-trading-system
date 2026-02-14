#!/usr/bin/env python3
"""
Live Signal Generation - Ensemble (LSTM + XGBoost)
==================================================
Generates trading signals using ensemble voting between LSTM and XGBoost models.

Features:
- Combines LSTM (higher accuracy) + XGBoost (faster, interpretable)
- Only accepts signals when both models strongly agree
- Multi-frequency analysis (1d trend + 1h confluence)
- Confidence filtering (only high-confidence ensemble votes)
"""

import sys
from pathlib import Path
import logging
import csv
from datetime import datetime
from collections import defaultdict

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
from models.ensemble_predictor import EnsemblePredictor
from signals.manager import SignalManager
from signals.telegram_bot import TelegramNotifier


# Ensemble configuration - prioritize best performers
ENSEMBLE_TICKERS = [
    ('GLD', ['macd_vwap', 'rsi_bb'], 0.75),       # Gold: 64% LSTM accuracy ⭐
    ('MSFT', ['macd_vwap', 'rsi_bb'], 0.75),      # Microsoft: 60% LSTM accuracy ⭐
    ('QQQ', ['ma_crossover', 'macd_vwap'], 0.70), # Nasdaq: 56% LSTM accuracy
]

# Periods for multi-frequency analysis
PERIODS = ['1d', '1h']  # 15m limited by Yahoo Finance (60 days max)


def analyze_ensemble_signal(ticker, signals_by_period, ensemble_results):
    """Analyze ensemble voting results across timeframes."""
    print(f"\n{'═'*80}")
    print(f"🤖 ENSEMBLE ANALYSIS: {ticker}")
    print(f"{'═'*80}\n")

    # Daily analysis
    print(f"📊 DAILY (1d) SIGNAL:")
    print(f"{'─'*80}")
    daily_ensemble = ensemble_results['1d']

    if daily_ensemble['ensemble']:
        ensemble_pred = daily_ensemble['ensemble']
        print(f"  Direction: {ensemble_pred['direction']}")
        print(f"  Confidence: {ensemble_pred['confidence']:.2%}")
        print(f"  Consensus: {ensemble_pred['consensus']}")
        print(f"  Reason: {ensemble_pred['reason']}")

        # Show individual model predictions
        if daily_ensemble['lstm']:
            lstm_conf = daily_ensemble['lstm']['confidence']
            print(f"\n  └─ LSTM: {daily_ensemble['lstm']['direction']} ({lstm_conf:.2%})")
        if daily_ensemble['xgb']:
            xgb_conf = daily_ensemble['xgb']['confidence']
            print(f"  └─ XGBoost: {daily_ensemble['xgb']['direction']} ({xgb_conf:.2%})")
    else:
        print(f"  ⚠️  No models available for ensemble prediction")

    # Hourly analysis
    print(f"\n📊 HOURLY (1h) CONFLUENCE:")
    print(f"{'─'*80}")
    hourly_ensemble = ensemble_results['1h']

    if hourly_ensemble['ensemble']:
        ensemble_pred = hourly_ensemble['ensemble']
        print(f"  Direction: {ensemble_pred['direction']}")
        print(f"  Confidence: {ensemble_pred['confidence']:.2%}")
        print(f"  Consensus: {ensemble_pred['consensus']}")

        # Confluence analysis
        daily_dir = ensemble_results['1d']['ensemble']['direction'] if ensemble_results['1d']['ensemble'] else 'UNKNOWN'
        hourly_dir = ensemble_pred['direction']

        if daily_dir == hourly_dir:
            print(f"\n  ✅ STRONG CONFLUENCE: 1d and 1h agree on {daily_dir}")
        else:
            print(f"\n  ⚠️  CONFLICT: 1d={daily_dir}, 1h={hourly_dir}")
    else:
        print(f"  ⚠️  No hourly models available")

    # Overall recommendation
    print(f"\n{'═'*80}")
    print(f"🎯 ENSEMBLE RECOMMENDATION")
    print(f"{'═'*80}\n")

    daily_accept = False
    hourly_accept = False

    if daily_ensemble['ensemble']:
        daily_conf = daily_ensemble['ensemble']['confidence']
        daily_accept = daily_conf >= 0.65 and daily_ensemble['ensemble']['consensus'] == 'STRONG'
        status = "✅ STRONG" if daily_accept else "⚠️  WEAK"
        print(f"  Daily signal: {status} (conf={daily_conf:.2%}, consensus={daily_ensemble['ensemble']['consensus']})")

    if hourly_ensemble['ensemble']:
        hourly_conf = hourly_ensemble['ensemble']['confidence']
        hourly_accept = hourly_conf >= 0.65 and hourly_ensemble['ensemble']['consensus'] == 'STRONG'
        status = "✅ STRONG" if hourly_accept else "⚠️  WEAK"
        print(f"  Hourly signal: {status} (conf={hourly_conf:.2%}, consensus={hourly_ensemble['ensemble']['consensus']})")

    if daily_accept and hourly_accept:
        print(f"\n  🚀 OPTIMAL: Both daily and hourly ensemble votes are STRONG")
        return True, "ensemble_strong"
    elif daily_accept:
        print(f"\n  ⚡ GOOD: Daily ensemble is STRONG (hourly weak/unavailable)")
        return True, "daily_only"
    elif hourly_accept:
        print(f"\n  ⏸️  RISKY: Only hourly ensemble is STRONG (daily weak)")
        return False, "hourly_only_risky"
    else:
        print(f"\n  ❌ SKIP: Neither daily nor hourly ensemble votes are STRONG enough")
        return False, "no_confluence"


def generate_ensemble_signals(ticker, strategies, confidence_threshold):
    """Generate signals using ensemble LSTM+XGBoost voting."""
    print(f"\n{'═'*80}")
    print(f"Generating ensemble signals for {ticker}...")
    print(f"{'═'*80}")

    fetcher = DataFetcher()
    processor = DataProcessor()
    manager = SignalManager()

    ensemble_results = {}

    # Process each period
    for period in PERIODS:
        print(f"\n  Fetching {ticker} {period} data...")

        try:
            # Load data
            try:
                df = fetcher.load_from_csv(ticker, period)
                print(f"  ✅ Loaded from cache: {len(df)} rows")
            except FileNotFoundError:
                print(f"  📥 Fetching from Yahoo Finance...")
                days = {'1d': 365, '1h': 90, '15m': 60}[period]
                df = fetcher.fetch_yfinance(ticker, period, days)
                if df is None or len(df) == 0:
                    print(f"  ⚠️  No data available for {ticker} {period}")
                    ensemble_results[period] = {
                        'ensemble': None,
                        'lstm': None,
                        'xgb': None,
                    }
                    continue
                df = processor.clean_data(df)
                fetcher.save_to_csv(df, ticker, period)
                print(f"  ✅ Fetched: {len(df)} rows")

            # Add indicators
            df = TechnicalIndicators.add_all_indicators(df)

            # Load ensemble predictor
            try:
                ensemble = EnsemblePredictor(
                    lstm_threshold=confidence_threshold,
                    xgb_threshold=confidence_threshold
                )
                ensemble.load(ticker, period, models=['lstm', 'xgb'])

                # Get prediction
                pred = ensemble.predict_next(df)

                print(f"  📊 Ensemble prediction for {period}:")
                if pred['ensemble']:
                    ens = pred['ensemble']
                    print(f"     Direction: {ens['direction']}")
                    print(f"     Confidence: {ens['confidence']:.2%}")
                    print(f"     Consensus: {ens['consensus']}")
                else:
                    print(f"     ⚠️  No ensemble prediction (models unavailable)")

                ensemble_results[period] = pred

            except FileNotFoundError as e:
                print(f"  ⚠️  Model not found: {e}")
                ensemble_results[period] = {
                    'ensemble': None,
                    'lstm': None,
                    'xgb': None,
                }

        except Exception as e:
            print(f"  ❌ Error processing {ticker} {period}: {e}")
            ensemble_results[period] = {
                'ensemble': None,
                'lstm': None,
                'xgb': None,
            }

    return ensemble_results


def main():
    """Main: Generate ensemble signals for all tickers."""
    print(f"\n{'='*80}")
    print(f"🤖 ENSEMBLE SIGNAL GENERATION (LSTM + XGBoost Voting)")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    notifier = TelegramNotifier()
    manager = SignalManager()

    all_results = {}
    actionable_signals = []

    # Process each ticker
    for ticker, strategies, confidence_threshold in ENSEMBLE_TICKERS:
        print(f"\n{'#'*80}")
        print(f"# {ticker}")
        print(f"{'#'*80}")

        # Generate ensemble signals
        ensemble_results = generate_ensemble_signals(ticker, strategies, confidence_threshold)
        all_results[ticker] = ensemble_results

        # Analyze ensemble voting
        accept, reason = analyze_ensemble_signal(ticker, {}, ensemble_results)

        # Log if actionable
        if accept and ensemble_results['1d']['ensemble']:
            signal_dir = ensemble_results['1d']['ensemble']['direction']
            if signal_dir in ['BUY', 'SELL']:
                consensus = ensemble_results['1d']['ensemble']['consensus']
                confidence = ensemble_results['1d']['ensemble']['confidence']

                result = {
                    'ticker': ticker,
                    'direction': signal_dir,
                    'confidence': confidence,
                    'consensus': consensus,
                    'reason': reason,
                    'timestamp': datetime.now().isoformat(),
                }

                actionable_signals.append(result)

                # Log to CSV
                log_file = Path('logs/signals.csv')
                log_file.parent.mkdir(exist_ok=True, parents=True)

                with open(log_file, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'timestamp', 'ticker', 'direction', 'confidence',
                        'strategy', 'entry_price', 'stop_loss', 'take_profit'
                    ])
                    # Create header if file is new
                    if f.tell() == 0:
                        writer.writeheader()

                    writer.writerow({
                        'timestamp': datetime.now().isoformat(),
                        'ticker': ticker,
                        'direction': signal_dir,
                        'confidence': f'{confidence:.4f}',
                        'strategy': 'ensemble',
                        'entry_price': '',
                        'stop_loss': '',
                        'take_profit': '',
                    })

                print(f"\n{'✅'*40}")
                print(f"ACTIONABLE ENSEMBLE SIGNAL LOGGED")
                print(f"{'✅'*40}\n")

    # Summary
    print(f"\n{'='*80}")
    print(f"📊 ENSEMBLE SUMMARY")
    print(f"{'='*80}\n")

    if actionable_signals:
        print(f"🎯 ACTIONABLE SIGNALS: {len(actionable_signals)}")
        for sig in actionable_signals:
            print(f"  • {sig['ticker']:6s} {sig['direction']:4s} | "
                  f"Confidence: {sig['confidence']:.2%} | Consensus: {sig['consensus']}")

        # Send Telegram notification
        if notifier.is_configured:
            for sig in actionable_signals:
                msg = (
                    f"🤖 *Ensemble Signal*\n"
                    f"Ticker: {sig['ticker']}\n"
                    f"Direction: {sig['direction']}\n"
                    f"Confidence: {sig['confidence']:.2%}\n"
                    f"Consensus: {sig['consensus']}\n"
                    f"Source: LSTM + XGBoost Voting"
                )
                notifier.send_alert(msg)
        else:
            print(f"\n  ℹ️  Telegram not configured (set BOT_TOKEN and CHAT_ID in .env)")
    else:
        print(f"❌ No actionable ensemble signals at this time")
        print(f"   All signals too weak or disagreement between models")

    print(f"\n{'='*80}")
    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")


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
