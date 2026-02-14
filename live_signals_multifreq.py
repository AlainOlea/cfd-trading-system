#!/usr/bin/env python3
"""
Live Signal Generation - Multi-Frequency
==========================================
Generates trading signals across multiple timeframes simultaneously:
- Daily (1d): Trend confirmation
- Hourly (1h): Retracement zones
- 15-min (15m): Entry timing

Recommended setup for high-quality trades.
"""

import sys
from pathlib import Path
import logging
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

from signals.generator import SignalGenerator
from signals.manager import SignalManager
from signals.telegram_bot import TelegramNotifier


# Multi-frequency configuration
# (ticker, strategies, use_ml)
MULTIFREQ_TICKERS = [
    ('GLD', ['macd_vwap', 'rsi_bb'], True),      # Gold: 64% accuracy
    ('MSFT', ['macd_vwap', 'rsi_bb'], True),     # Microsoft: 60%
    ('QQQ', ['ma_crossover', 'macd_vwap'], True), # Nasdaq: 56%
    ('AAPL', ['rsi_bb', 'macd_vwap'], True),      # Apple: 52%
]

# Periods to generate (shorter periods = more signals)
PERIODS = ['1d', '1h', '15m']


def analyze_multifreq_signal(ticker, signals_by_period):
    """Analyze multi-frequency signals for confluence."""
    print(f"\n{'─'*70}")
    print(f"📊 CONFLUENCE ANALYSIS: {ticker}")
    print(f"{'─'*70}")

    # Analyze each period
    print(f"\n1️⃣  DAILY (1d) - Trend Confirmation:")
    daily_sigs = signals_by_period['1d']
    trend = 'UNKNOWN'
    for sig in daily_sigs:
        if sig.direction == 'BUY':
            print(f"   ✅ UPTREND confirmed ({sig.strategy})")
            trend = 'UP'
        elif sig.direction == 'SELL':
            print(f"   ❌ DOWNTREND confirmed ({sig.strategy})")
            trend = 'DOWN'
        else:
            print(f"   ⏸️  HOLD - No clear trend")

    print(f"\n2️⃣  HOURLY (1h) - Retracement Zone:")
    hourly_sigs = signals_by_period['1h']
    retracement = None
    for sig in hourly_sigs:
        if trend == 'UP' and sig.direction == 'BUY':
            print(f"   ✅ Found retrace BUY zone ({sig.strategy})")
            retracement = 'BUY'
        elif trend == 'DOWN' and sig.direction == 'SELL':
            print(f"   ✅ Found retrace SELL zone ({sig.strategy})")
            retracement = 'SELL'
        elif sig.direction == 'HOLD':
            print(f"   ⏸️  Neutral ({sig.strategy})")
        else:
            print(f"   ⚠️  Counter-trend signal ({sig.strategy}) - Risky")

    print(f"\n3️⃣  15-MINUTE (15m) - Entry Timing:")
    fifteenm_sigs = signals_by_period['15m']
    for sig in fifteenm_sigs:
        if sig.direction == 'BUY':
            print(f"   ⚡ BUY signal ({sig.strategy}) - Confidence: {sig.confidence:.2f}")
        elif sig.direction == 'SELL':
            print(f"   ⚡ SELL signal ({sig.strategy}) - Confidence: {sig.confidence:.2f}")
        else:
            print(f"   ⏸️  HOLD ({sig.strategy})")

    # Confluence score
    print(f"\n{'═'*70}")
    print(f"CONFLUENCE SCORE")
    print(f"{'═'*70}")

    confluence = 0
    recommendation = "SKIP"

    if trend != 'UNKNOWN' and retracement is not None:
        # Check if 15m aligns
        for sig in fifteenm_sigs:
            if sig.direction == retracement:
                confluence = 3
                recommendation = f"⭐⭐⭐ STRONG {retracement}"
                break
            elif sig.direction == 'HOLD':
                confluence = 2
                recommendation = f"⭐⭐ MEDIUM WAIT ({retracement} zone forming)"
                break
        else:
            if fifteenm_sigs and fifteenm_sigs[0].direction != 'HOLD':
                confluence = 1
                recommendation = f"⭐ WEAK (15m disagrees)"

    print(f"\nRecommendation: {recommendation}")
    print(f"Confluence: {confluence}/3")

    if confluence >= 2:
        best_sig = max(
            [s for s in fifteenm_sigs if s.direction != 'HOLD'],
            key=lambda x: x.confidence,
            default=None
        )
        if best_sig:
            print(f"\n✅ ENTRY OPPORTUNITY:")
            print(f"   Direction: {best_sig.direction}")
            print(f"   Entry: ${best_sig.entry_price:.2f}")
            print(f"   SL: ${best_sig.stop_loss:.2f}")
            print(f"   TP: ${best_sig.take_profit:.2f}")
            print(f"   R/R: 1:{best_sig.risk_reward_ratio:.1f}")
            print(f"   Confidence: {best_sig.confidence:.2f}")

    print()


def generate_multifreq_signals():
    """Generate signals for multiple frequencies."""
    print(f"\n{'='*70}")
    print(f"MULTI-FREQUENCY SIGNAL GENERATION")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Periods: {', '.join(PERIODS)}")
    print(f"{'='*70}\n")

    generator = SignalGenerator()
    manager = SignalManager()
    notifier = TelegramNotifier()

    all_signals = []
    signals_by_ticker = defaultdict(lambda: defaultdict(list))

    # Generate signals for each ticker
    for ticker, strategies, use_ml in MULTIFREQ_TICKERS:
        print(f"\n{'='*70}")
        print(f"TICKER: {ticker}")
        print(f"{'='*70}")

        signals_by_period = defaultdict(list)

        # Generate for each period
        for period in PERIODS:
            print(f"\n📊 Period: {period}")
            print(f"{'─'*70}")

            for strategy in strategies:
                try:
                    signal = generator.generate(
                        strategy_name=strategy,
                        ticker=ticker,
                        interval=period,
                        use_ml=use_ml,
                    )

                    manager.log_signal(signal)
                    signals_by_period[period].append(signal)
                    all_signals.append(signal)

                    # Display signal
                    if signal.direction != 'HOLD':
                        print(f"   ⚡ {signal.strategy:12s} | {signal.direction:4s} | "
                              f"Conf: {signal.confidence:.2f} | R/R: {signal.risk_reward_ratio:.1f}")
                    else:
                        print(f"   ⏸️  {signal.strategy:12s} | HOLD")

                except Exception as e:
                    print(f"   ❌ Error: {e}")

        # Analyze confluence
        analyze_multifreq_signal(ticker, signals_by_period)
        signals_by_ticker[ticker] = signals_by_period

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}\n")

    buy_signals = [s for s in all_signals if s.direction == 'BUY']
    sell_signals = [s for s in all_signals if s.direction == 'SELL']
    hold_signals = [s for s in all_signals if s.direction == 'HOLD']

    print(f"✅ BUY signals:  {len(buy_signals)}")
    print(f"❌ SELL signals: {len(sell_signals)}")
    print(f"⏸️  HOLD signals: {len(hold_signals)}")
    print(f"📊 Total signals: {len(all_signals)}")

    if buy_signals or sell_signals:
        print(f"\n🎯 ACTIONABLE SIGNALS:")
        for sig in buy_signals + sell_signals:
            print(f"   {sig.ticker:8s} {sig.interval:4s} {sig.direction:4s} "
                  f"@ ${sig.entry_price:7.2f} | Conf: {sig.confidence:.2f}")

        # Send alerts
        if notifier.is_configured:
            print(f"\n📱 Sending Telegram alerts...")
            for sig in buy_signals + sell_signals:
                try:
                    notifier.send_signal(sig)
                except Exception as e:
                    print(f"   ⚠️  Telegram error: {e}")

    print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*70}\n")

    return all_signals


def show_comparison():
    """Show comparison between single vs multi-frequency."""
    print(f"\n{'='*70}")
    print(f"SINGLE vs MULTI-FREQUENCY COMPARISON")
    print(f"{'='*70}\n")

    print(f"SINGLE FREQUENCY (1d only):")
    print(f"  • Signals per day: 1 maximum")
    print(f"  • Trades per year: ~250")
    print(f"  • Win rate: ~50-55%")
    print(f"  • ROI monthly: 0.5-1%")
    print(f"  • Comissions: Low")
    print(f"  • Risk: Very low")

    print(f"\nMULTI-FREQUENCY (1d + 1h + 15m):")
    print(f"  • Signals per day: 8-15 high-quality")
    print(f"  • Trades per year: 2,000-3,750")
    print(f"  • Win rate: ~53-56%")
    print(f"  • ROI monthly: 2-3%")
    print(f"  • Comissions: Medium")
    print(f"  • Risk: Low-Medium")

    print(f"\n✅ RECOMMENDATION: Multi-frequency strategy")
    print(f"{'='*70}\n")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate multi-frequency trading signals'
    )
    parser.add_argument(
        '--comparison',
        action='store_true',
        help='Show single vs multi-frequency comparison'
    )

    args = parser.parse_args()

    if args.comparison:
        show_comparison()
    else:
        signals = generate_multifreq_signals()
        return len(signals)


if __name__ == '__main__':
    try:
        count = main()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
