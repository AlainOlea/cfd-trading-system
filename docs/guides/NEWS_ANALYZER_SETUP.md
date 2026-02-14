# News Analyzer Integration Guide

## Overview

The news analyzer is now integrated into the live signal generation pipeline. When a trading signal is generated, the system automatically:

1. **Fetches relevant news** articles from NewsAPI
2. **Analyzes sentiment** using Google Gemini AI
3. **Includes the context** in Telegram messages

This helps traders make better decisions by providing news context and sentiment analysis alongside the technical ensemble signals.

## Setup Instructions

### 1. Get NewsAPI Key (Free)

1. Visit https://newsapi.org
2. Click "Sign Up" and create a free account
3. Verify your email
4. Copy your API key from the dashboard
5. Add to your `.env` file:

```bash
NEWS_API_KEY=your_newsapi_org_api_key
```

**Free tier limits:**
- 100 requests per day
- 30-day history
- Good for testing and monitoring

### 2. Get Google AI API Key (Free)

1. Visit https://ai.google.dev
2. Click "Get API Key" in the console
3. Create a new API key
4. Copy the key
5. Add to your `.env` file:

```bash
GOOGLE_AI_API_KEY=your_google_ai_api_key
```

**Free tier limits:**
- 60 requests per minute
- Generous daily quota
- Suitable for trading signal analysis

### 3. Update Your `.env` File

```bash
cp .env.example .env
# Edit .env and add your API keys:
# NEWS_API_KEY=your_newsapi_key
# GOOGLE_AI_API_KEY=your_google_ai_key
```

### 4. Install Required Dependencies (if not already installed)

```bash
source venv/bin/activate
pip install google-generativeai requests
```

## How It Works

### Signal Flow with News Context

```
Generate Ensemble Signal
    ↓
Check if Actionable (STRONG consensus + high confidence)
    ↓
If Actionable → Fetch News Articles (NewsAPI)
    ↓
Analyze Sentiment (Google Gemini AI)
    ↓
Format for Telegram (with news context)
    ↓
Send Telegram Notification
```

### Example Telegram Message with News

```
🎯 *Ensemble Signal*
Ticker: GLD
Direction: BUY
Confidence: 65.30%
Timeframe: 1d
Source: LSTM + XGBoost

📰 *News Analysis (5 articles)*
Sentiment: BULLISH
Alignment: Strongly aligns
⚠️  Risks: Fed policy concerns, market volatility
Confidence Adjustment: INCREASE

*Top News:*
1. [Reuters] Gold prices surge as Fed signals pause
2. [Bloomberg] Safe haven demand drives precious metals
3. [CNBC] Inflation concerns boost gold bullion demand
```

## Graceful Degradation

The system gracefully handles missing API keys:

- **No NEWS_API_KEY?** → Skips news fetching, still sends signal
- **No GOOGLE_AI_API_KEY?** → Skips sentiment analysis, still sends signal
- **API errors?** → Logs warning, continues with base signal
- **No models trained?** → Falls back to technical indicators only

## Usage

### Run Signal Generation with News Context

```bash
# All tickers
python3 live_signals_expanded.py

# Specific tickers
python3 live_signals_expanded.py --tickers "GLD,MSFT,BTC-USD"

# Verbose mode (shows more details)
python3 live_signals_expanded.py --verbose
```

## File Structure

- **signals/news_analyzer.py** - Main NewsAnalyzer class
- **live_signals_expanded.py** - Integrated signal generation with news context
- **.env** - Your API keys (never commit this)
- **.env.example** - Template with setup instructions

## Sentiment Analysis Details

The sentiment analyzer evaluates:

1. **Overall Sentiment** - Bullish/Bearish/Neutral based on article content
2. **Key Risks** - Risk factors mentioned in news
3. **Alignment** - How well news aligns with the trading signal direction
4. **Confidence Adjustment** - Should confidence increase/maintain/decrease

## API Costs

| Service | Free Tier | Cost |
|---------|-----------|------|
| NewsAPI | 100 req/day | $0 for testing, $29+/month for production |
| Google AI | 60 req/min | Free with some paid options |
| Telegram Bot | Unlimited | Free |

## Monitoring and Logging

All news fetches and sentiment analyses are logged:

```bash
# View logs
tail -f logs/signals.csv

# See what news was analyzed
tail -100 logs/signals.csv | grep -i "news\|sentiment"
```

## Troubleshooting

### Issue: "google-generativeai not installed"
```bash
source venv/bin/activate
pip install google-generativeai
```

### Issue: "requests not installed"
```bash
source venv/bin/activate
pip install requests
```

### Issue: "News not fetching"
- Check NEWS_API_KEY is set correctly in .env
- Check daily request limit (100/day on free tier)
- Verify ticker format (e.g., "GLD" not "GOLD")

### Issue: "Sentiment analysis failed"
- Check GOOGLE_AI_API_KEY is set correctly in .env
- Verify API key has Generative AI enabled
- Check rate limits (60/minute on free tier)

## Advanced: Custom News Sources

To use alternative news sources, modify `signals/news_analyzer.py`:

```python
# Replace NewsAPI with your preferred source
# Example: Alpha Vantage, IEX Cloud, Finnhub, etc.

def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict]:
    # Customize news fetching here
    pass
```

## Next Steps

1. **Get API keys** from NewsAPI and Google AI
2. **Add to `.env` file**
3. **Test with sample ticker:** `python3 live_signals_expanded.py --tickers "GLD"`
4. **Monitor Telegram messages** for news context
5. **Adjust confidence thresholds** in config/settings.py as needed

## Example Workflow

```bash
# 1. Setup
cp .env.example .env
# Edit .env with your API keys

# 2. Test with one ticker
python3 live_signals_expanded.py --tickers "GLD"

# 3. Check Telegram for signal with news context

# 4. Run full ensemble for all tickers
python3 live_signals_expanded.py

# 5. Monitor signals
tail -f logs/signals.csv
```

## Questions?

For issues or customizations:
1. Check the logs: `tail -100 logs/signals.csv`
2. Run with verbose: `python3 live_signals_expanded.py --verbose`
3. Review signals/news_analyzer.py for implementation details
