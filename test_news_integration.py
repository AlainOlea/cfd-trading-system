#!/usr/bin/env python3
"""
Test News Analyzer Integration
==============================
Simulate a trading signal and fetch news + sentiment analysis
"""

import sys
from pathlib import Path
import logging
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from signals.news_analyzer import NewsAnalyzer
from signals.telegram_bot import TelegramNotifier


def test_news_integration(ticker='GLD', direction='BUY', confidence=0.72):
    """Test news analyzer with a simulated signal"""

    print(f"\n{'='*80}")
    print(f"🔬 Testing News Analyzer Integration")
    print(f"{'='*80}\n")

    # Create sample signal
    signal = {
        'direction': direction,
        'confidence': confidence
    }

    print(f"📊 Simulated Signal:")
    print(f"   Ticker: {ticker}")
    print(f"   Direction: {direction}")
    print(f"   Confidence: {confidence:.2%}")
    print(f"   Timeframe: 1d")
    print(f"   Source: LSTM + XGBoost Ensemble\n")

    # Initialize news analyzer
    news_analyzer = NewsAnalyzer()

    # Check if APIs are configured
    print(f"🔧 API Status:")
    print(f"   NewsAPI: {'✅ Configured' if news_analyzer.newsapi_available else '❌ Not configured'}")
    print(f"   Google AI: {'✅ Configured' if news_analyzer.model_available else '❌ Not configured'}\n")

    # Fetch news and sentiment
    print(f"📰 Fetching news for {ticker}...")

    try:
        # Get signal context (news + sentiment)
        news_context = news_analyzer.get_signal_context(ticker, signal)

        if news_context:
            print(f"✅ News fetched: {news_context['articles_count']} articles\n")

            # Get sentiment analysis
            sentiment = news_context['sentiment']
            print(f"📊 Sentiment Analysis:")
            print(f"   Overall Sentiment: {sentiment.get('sentiment', 'N/A').upper()}")
            print(f"   Alignment with Signal: {sentiment.get('alignment', 'N/A')}")
            print(f"   Key Risks: {sentiment.get('risks', 'None mentioned')}")
            print(f"   Confidence Adjustment: {sentiment.get('confidence_adjustment', 'maintain').upper()}\n")

            # Format for Telegram
            print(f"💬 Formatted for Telegram:\n")
            telegram_format = news_analyzer.format_for_telegram(news_context)
            print(telegram_format)

            # Build complete message
            print(f"\n{'='*80}")
            print(f"📱 Complete Telegram Message:")
            print(f"{'='*80}\n")

            complete_msg = (
                f"🎯 *Ensemble Signal*\n"
                f"Ticker: {ticker}\n"
                f"Direction: {direction}\n"
                f"Confidence: {confidence:.2%}\n"
                f"Timeframe: 1d\n"
                f"Source: LSTM + XGBoost"
            )
            complete_msg += telegram_format

            print(complete_msg)

            # Send to Telegram if configured
            notifier = TelegramNotifier()
            if notifier.is_configured:
                print(f"\n{'='*80}")
                print(f"🚀 Sending to Telegram...")
                notifier.send_alert(complete_msg)
                print(f"✅ Telegram notification sent!")
            else:
                print(f"\n{'='*80}")
                print(f"ℹ️  Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env)")

        else:
            print(f"⚠️  Could not fetch news context for {ticker}")
            print(f"   Check your API keys in .env file")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'='*80}\n")


def test_multiple_tickers():
    """Test with multiple tickers and different signals"""

    test_cases = [
        ('GLD', 'BUY', 0.72),
        ('MSFT', 'SELL', 0.68),
        ('BTC-USD', 'BUY', 0.65),
    ]

    for ticker, direction, confidence in test_cases:
        test_news_integration(ticker, direction, confidence)
        print("\n" + "="*80 + "\n")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test news analyzer integration')
    parser.add_argument('--ticker', type=str, default='GLD', help='Ticker symbol (default: GLD)')
    parser.add_argument('--direction', type=str, default='BUY', choices=['BUY', 'SELL'],
                       help='Signal direction (default: BUY)')
    parser.add_argument('--confidence', type=float, default=0.72,
                       help='Signal confidence 0-1 (default: 0.72)')
    parser.add_argument('--multiple', action='store_true', help='Test multiple tickers')

    args = parser.parse_args()

    if args.multiple:
        test_multiple_tickers()
    else:
        test_news_integration(args.ticker, args.direction, args.confidence)
