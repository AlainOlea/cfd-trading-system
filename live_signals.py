#!/usr/bin/env python3
"""
Live Signal Generation with Best Models
========================================
Generates trading signals in real-time using:
- Best performing models (GLD, MSFT, QQQ, AAPL)
- ML filtering enabled
- Multiple strategies combined
"""

import sys
from pathlib import Path
import logging
from datetime import datetime

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


# Best models and their strategies
LIVE_SIGNALS_CONFIG = [
    # (ticker, interval, strategies, use_ml)
    ('GLD', '1d', ['macd_vwap', 'rsi_bb'], True),      # Best: 64%
    ('MSFT', '1d', ['macd_vwap', 'rsi_bb'], True),     # Good: 60%
    ('QQQ', '1d', ['ma_crossover', 'macd_vwap'], True),  # Good: 56%
    ('AAPL', '1d', ['rsi_bb', 'macd_vwap'], True),      # OK: 52%
]


def generate_live_signals():
    """Generate signals from all best models right now."""
    print(f"\n{'='*80}")
    print(f"LIVE SIGNAL GENERATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*80}\n")

    generator = SignalGenerator()
    manager = SignalManager()
    notifier = TelegramNotifier()

    actionable_signals = []
    total_signals = 0

    for ticker, interval, strategies, use_ml in LIVE_SIGNALS_CONFIG:
        print(f"\n{'─'*80}")
        print(f"📊 {ticker} ({interval})")
        print(f"{'─'*80}")

        for strategy in strategies:
            try:
                total_signals += 1
                signal = generator.generate(
                    strategy_name=strategy,
                    ticker=ticker,
                    interval=interval,
                    use_ml=use_ml,
                )

                # Log the signal
                manager.log_signal(signal)

                # Display
                print(manager.format_signal(signal))

                # Collect actionable
                if signal.direction != 'HOLD':
                    actionable_signals.append(signal)

                    # Send Telegram if configured
                    if notifier.is_configured:
                        try:
                            notifier.send_signal(signal)
                            print(f"   📱 Telegram notification sent")
                        except Exception as e:
                            print(f"   ⚠️  Telegram error: {e}")

            except Exception as e:
                print(f"   ❌ Error: {e}")

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Total signals generated: {total_signals}")
    print(f"🎯 Actionable signals (BUY/SELL): {len(actionable_signals)}")

    if actionable_signals:
        print(f"\n📈 Actionable Signals:")
        print(f"{'Ticker':<12} {'Strategy':<15} {'Direction':<10} {'Confidence':<12}")
        print("-" * 49)
        for sig in actionable_signals:
            print(f"{sig.ticker:<12} {sig.strategy:<15} {sig.direction:<10} {sig.confidence:.2f}")

        # Show best opportunity
        best = max(actionable_signals, key=lambda s: s.confidence)
        print(f"\n⭐ BEST OPPORTUNITY:")
        print(f"   {best.ticker} - {best.direction} @ {best.entry_price:.2f}")
        print(f"   Confidence: {best.confidence:.2f} (ML: {best.ml_confidence:.2f})")
        print(f"   Risk/Reward: 1:{best.risk_reward_ratio:.1f}")
    else:
        print(f"\n⏸️  No actionable signals at this time (all HOLD)")

    print(f"\n{'='*80}\n")

    return actionable_signals


def show_signal_history():
    """Display recent signal history."""
    manager = SignalManager()
    history = manager.get_history(n=10)

    if len(history) > 0:
        print(f"\n{'='*80}")
        print(f"RECENT SIGNAL HISTORY (Last 10)")
        print(f"{'='*80}\n")
        print(manager.format_history(history))
        print(f"\n{'='*80}\n")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate live trading signals with best ML models'
    )
    parser.add_argument(
        '--history',
        action='store_true',
        help='Show recent signal history'
    )

    args = parser.parse_args()

    if args.history:
        show_signal_history()
    else:
        signals = generate_live_signals()
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
