#!/usr/bin/env python3
"""
Live Signal Generation - Expanded Ensemble
===========================================
Generate trading signals across expanded ensemble with 11+ tickers.

Usage:
    python3 live_signals_expanded.py [--verbose] [--tickers TICKER,TICKER]

Features:
- Multi-tier coverage (Stocks, Commodities, Crypto)
- Ensemble voting (LSTM + XGBoost)
- Multi-frequency analysis (1d + 1h)
- Signal strength scoring
- Grouping by market sector
"""

import sys
from pathlib import Path
import logging
import argparse
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
from signals.telegram_bot import TelegramNotifier
from signals.news_analyzer import NewsAnalyzer
import csv


# Comprehensive ensemble coverage
ENSEMBLE_COVERAGE = {
    'Stocks': [
        ('GLD', 0.75),      # Gold: Best performer (64%)
        ('MSFT', 0.75),     # Microsoft
        ('QQQ', 0.70),      # Nasdaq
        ('AAPL', 0.70),     # Apple (new)
        ('NVDA', 0.70),     # NVIDIA (new)
        ('SPY', 0.70),      # S&P 500 (new)
    ],
    'Commodities': [
        ('GDX', 0.70),      # Gold miners (new)
        ('XLU', 0.70),      # Utilities (new)
        ('IWM', 0.70),      # Small cap (new)
    ],
    'Crypto': [
        ('BTC-USD', 0.70),  # Bitcoin
        ('ETH-USD', 0.70),  # Ethereum
        ('SOL-USD', 0.70),  # Solana
    ],
}


def generate_ensemble_signal(ticker, confidence_threshold):
    """Generate ensemble signal for a single ticker."""
    try:
        fetcher = DataFetcher()
        processor = DataProcessor()
        notifier = TelegramNotifier()

        result = {
            'ticker': ticker,
            '1d': {},
            '1h': {},
            'actionable': False,
        }

        # Process each period
        for period in ['1d', '1h']:
            try:
                # Load data
                try:
                    df = fetcher.load_from_csv(ticker, period)
                except FileNotFoundError:
                    days = 365 if period == '1d' else 90
                    df = fetcher.fetch_yfinance(ticker, period, days)
                    if df is None or len(df) == 0:
                        continue
                    df = processor.clean_data(df)
                    fetcher.save_to_csv(df, ticker, period)

                # Add indicators
                df = TechnicalIndicators.add_all_indicators(df)

                # Load ensemble
                try:
                    ensemble = EnsemblePredictor(
                        lstm_threshold=confidence_threshold,
                        xgb_threshold=confidence_threshold
                    )
                    ensemble.load(ticker, period, models=['lstm', 'xgb'])
                    pred = ensemble.predict_next(df)

                    if pred['ensemble']:
                        result[period] = {
                            'direction': pred['ensemble']['direction'],
                            'confidence': pred['ensemble']['confidence'],
                            'consensus': pred['ensemble']['consensus'],
                            'lstm': pred['lstm'],
                            'xgb': pred['xgb'],
                        }
                except FileNotFoundError:
                    # Model not yet trained
                    pass

            except Exception as e:
                logger.debug(f"Error processing {ticker} {period}: {e}")

        # Determine if actionable
        if result['1d'] and result['1d'].get('consensus') == 'STRONG':
            if result['1d'].get('confidence', 0) >= 0.65:
                result['actionable'] = True
                result['reason'] = 'Strong 1d ensemble'
        elif result['1h'] and result['1h'].get('consensus') == 'STRONG':
            if result['1h'].get('confidence', 0) >= 0.70:
                result['actionable'] = True
                result['reason'] = 'Strong 1h ensemble (risky without 1d)'

        return result

    except Exception as e:
        logger.error(f"Error generating signal for {ticker}: {e}")
        return None


def main(args):
    """Generate signals for all configured tickers."""
    print(f"\n{'='*80}")
    print(f"🚀 EXPANDED ENSEMBLE SIGNAL GENERATION")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    notifier = TelegramNotifier()
    news_analyzer = NewsAnalyzer()
    all_signals = []
    actionable_by_sector = defaultdict(list)

    # Determine which tickers to process
    if args.tickers:
        tickers_to_process = [t.strip().upper() for t in args.tickers.split(',')]
    else:
        tickers_to_process = [t for sector_tickers in ENSEMBLE_COVERAGE.values()
                             for t, _ in sector_tickers]

    # Process each ticker
    for ticker in tickers_to_process:
        # Find confidence threshold
        conf_threshold = 0.70
        for sector, tickers in ENSEMBLE_COVERAGE.items():
            for t, threshold in tickers:
                if t == ticker:
                    conf_threshold = threshold
                    break

        # Generate signal
        signal = generate_ensemble_signal(ticker, conf_threshold)
        if signal:
            all_signals.append(signal)

            # Log to CSV
            if signal['actionable']:
                direction = signal['1d'].get('direction') or signal['1h'].get('direction')
                confidence = signal['1d'].get('confidence') or signal['1h'].get('confidence')
                period = '1d' if signal['1d'] else '1h'

                log_file = Path('logs/signals.csv')
                log_file.parent.mkdir(exist_ok=True, parents=True)

                with open(log_file, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'timestamp', 'ticker', 'direction', 'confidence',
                        'strategy', 'entry_price', 'stop_loss', 'take_profit'
                    ])
                    if f.tell() == 0:
                        writer.writeheader()

                    writer.writerow({
                        'timestamp': datetime.now().isoformat(),
                        'ticker': ticker,
                        'direction': direction,
                        'confidence': f'{confidence:.4f}',
                        'strategy': f'ensemble_{period}',
                        'entry_price': '',
                        'stop_loss': '',
                        'take_profit': '',
                    })

                # Categorize by sector
                for sector, tickers_list in ENSEMBLE_COVERAGE.items():
                    if any(t == ticker for t, _ in tickers_list):
                        actionable_by_sector[sector].append({
                            'ticker': ticker,
                            'direction': direction,
                            'confidence': confidence,
                            'period': period,
                        })
                        break

                # Send Telegram notification with news context
                if notifier.is_configured:
                    msg = (
                        f"🎯 *Ensemble Signal*\n"
                        f"Ticker: {ticker}\n"
                        f"Direction: {direction}\n"
                        f"Confidence: {confidence:.2%}\n"
                        f"Timeframe: {period}\n"
                        f"Source: LSTM + XGBoost"
                    )

                    # Fetch and append news context
                    signal_dict = {
                        'direction': direction,
                        'confidence': confidence
                    }
                    try:
                        news_context = news_analyzer.get_signal_context(ticker, signal_dict)
                        if news_context:
                            news_msg = news_analyzer.format_for_telegram(news_context)
                            if news_msg:
                                msg += news_msg
                    except Exception as e:
                        logger.debug(f"Could not fetch news for {ticker}: {e}")

                    notifier.send_alert(msg)

    # Summary by sector
    print(f"\n{'='*80}")
    print(f"📊 SIGNALS BY SECTOR")
    print(f"{'='*80}\n")

    total_actionable = 0
    for sector in ['Stocks', 'Commodities', 'Crypto']:
        signals = actionable_by_sector[sector]
        if signals:
            print(f"📈 {sector}: {len(signals)} signal(s)")
            for sig in signals:
                print(f"   • {sig['ticker']:10s} {sig['direction']:4s} | "
                      f"Conf: {sig['confidence']:.2%} | {sig['period']}")
            total_actionable += len(signals)
        else:
            print(f"⏸️  {sector}: No actionable signals")

    # Overall summary
    print(f"\n{'='*80}")
    print(f"✅ TOTAL ACTIONABLE SIGNALS: {total_actionable}")
    print(f"📊 Tickers analyzed: {len(all_signals)}")
    print(f"🔗 Models with coverage: {sum(1 for s in all_signals if s['1d'] or s['1h'])}")
    print(f"⚠️  Untrained models: {sum(1 for s in all_signals if not s['1d'] and not s['1h'])}")

    print(f"\n{'='*80}")
    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Generate expanded ensemble trading signals'
    )
    parser.add_argument(
        '--tickers',
        type=str,
        help='Comma-separated list of tickers (e.g., "GLD,MSFT,QQQ")'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    try:
        main(args)
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
