"""
News Analyzer with Sentiment Analysis
======================================
Fetch news related to trading signals and analyze sentiment using Google AI.

Features:
- Fetch recent news for ticker
- Analyze sentiment with Gemini AI
- Summarize key points
- Rate impact on trading signal
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. News sentiment analysis disabled.")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests not installed. News fetching disabled.")


class NewsAnalyzer:
    """Analyze news sentiment for trading signals."""

    def __init__(self):
        """Initialize news analyzer with Google AI."""
        self.gemini_api_key = os.getenv("GOOGLE_AI_API_KEY")
        self.newsapi_key = os.getenv("NEWS_API_KEY")
        self.model_available = GEMINI_AVAILABLE and self.gemini_api_key

        if self.model_available:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            self.model = None

        self.newsapi_available = REQUESTS_AVAILABLE and self.newsapi_key

    def fetch_news(self, ticker: str, limit: int = 5) -> List[Dict]:
        """Fetch recent news for ticker using NewsAPI.

        Args:
            ticker: Stock ticker (e.g., 'AAPL', 'BTC', 'GLD')
            limit: Number of articles to fetch

        Returns:
            List of news articles with title, description, url, published_at
        """
        if not self.newsapi_available:
            logger.debug("NewsAPI not configured. Skipping news fetch.")
            return []

        try:
            # Clean ticker for news search
            search_term = ticker.replace("-USD", "").replace("-USDT", "")

            url = "https://newsapi.org/v2/everything"
            params = {
                "q": search_term,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": limit,
                "apiKey": self.newsapi_key,
            }

            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()
            articles = []

            for article in data.get("articles", [])[:limit]:
                articles.append(
                    {
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("url", ""),
                        "source": article.get("source", {}).get("name", ""),
                        "published_at": article.get("publishedAt", ""),
                    }
                )

            logger.info(f"Fetched {len(articles)} news articles for {ticker}")
            return articles

        except Exception as e:
            logger.warning(f"Error fetching news for {ticker}: {e}")
            return []

    def analyze_sentiment(self, ticker: str, signal: Dict, articles: List[Dict]) -> Optional[Dict]:
        """Analyze sentiment of news articles using Gemini.

        Args:
            ticker: Stock ticker
            signal: Trading signal (direction, confidence)
            articles: List of news articles

        Returns:
            Dict with sentiment analysis or None if error
        """
        if not self.model_available or not articles:
            return None

        try:
            # Format articles for analysis
            articles_text = "\n\n".join(
                [
                    f"Article {i+1}:\n"
                    f"Title: {a['title']}\n"
                    f"Source: {a['source']}\n"
                    f"Published: {a['published_at']}\n"
                    f"Summary: {a['description']}"
                    for i, a in enumerate(articles[:5])
                ]
            )

            prompt = f"""You are a professional trading sentiment analyst specializing in market-moving news.

===== SIGNAL CONTEXT =====
Ticker: {ticker}
Signal Direction: {signal['direction']}
Model Confidence: {signal['confidence']:.1%}
Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}

===== NEWS ARTICLES TO ANALYZE =====
{articles_text}

===== ANALYSIS FRAMEWORK =====

Step 1: SENTIMENT EXTRACTION
- Identify overall tone: bullish, bearish, or neutral
- For mixed sentiments, specify the ratio (e.g., "70% bullish, 30% bearish")
- Weight recent articles (today/yesterday) 2x more important than older articles
- Score from 0.0 (most bearish) to 1.0 (most bullish)

Step 2: CREDIBILITY ASSESSMENT
- High credibility sources (Reuters, Bloomberg, AP, SEC filings, official announcements)
- Medium credibility sources (Yahoo Finance, CNBC, major financial media)
- Low credibility sources (social media, minor blogs, speculation)
- Calculate weighted sentiment using source credibility

Step 3: MARKET-MOVING FACTORS
Focus only on factors that materially affect price:
✅ Earnings surprises, guidance changes, management statements
✅ Regulatory/legal changes affecting the company
✅ Major partnerships, customer wins/losses
✅ Product breakthroughs or failures
✅ Significant debt, financing, or M&A news
❌ General commentary, analyst opinions without new data
❌ Speculation about the company

Step 4: RISK IDENTIFICATION
Extract risks SPECIFIC to {ticker}:
- Company-specific risks (competitive position, cash flow, management)
- Financial risks (debt, leverage, earnings quality)
- Regulatory/legal risks
- Market/macro risks affecting the sector
- Assess severity: Critical > High > Medium > Low

Step 5: SIGNAL ALIGNMENT
Compare news sentiment to the {signal['direction']} signal:
- STRONGLY ALIGNS: News strongly confirms {signal['direction']} direction
- ALIGNS: News moderately supports {signal['direction']}
- NEUTRAL: News doesn't clearly support or oppose the signal
- CONFLICTS: News contradicts {signal['direction']} direction
- STRONGLY CONFLICTS: News strongly opposes {signal['direction']}

Step 6: CONFIDENCE ADJUSTMENT
Should trader confidence increase, maintain, or decrease?
- INCREASE (0.05-0.30): News strongly confirms signal direction
  → Use higher adjustment (0.20-0.30) if: high-credibility sources, unanimous agreement, major catalysts
  → Use lower adjustment (0.05-0.10) if: single source, minor news
- MAINTAIN (0.00): News is neutral or mixed
- DECREASE (0.05-0.30): News contradicts signal direction
  → Use higher adjustment (0.20-0.30) if: high-credibility sources, contradictory catalysts
  → Use lower adjustment (0.05-0.10) if: single source, minor contradictions

===== RESPONSE FORMAT =====
Return ONLY valid JSON with these fields:
{{
  "sentiment": "bullish|bearish|neutral|mixed",
  "sentiment_score": 0.65,
  "sentiment_breakdown": {{"bullish": 0.65, "neutral": 0.25, "bearish": 0.10}},
  "credibility": "high|medium|low",
  "key_risks": ["risk1", "risk2", "risk3"],
  "alignment": "strongly_aligns|aligns|neutral|conflicts|strongly_conflicts",
  "alignment_score": 0.68,
  "confidence_adjustment": "decrease|maintain|increase",
  "adjustment_strength": 0.12,
  "reasoning": "Brief one-sentence explanation of the recommendation"
}}

Critical: Return ONLY the JSON object, no other text."""

            response = self.model.generate_content(prompt)
            analysis_text = response.text

            # Parse Gemini response
            import json
            import re

            # Extract JSON from response
            json_match = re.search(r"\{.*\}", analysis_text, re.DOTALL)
            if json_match:
                try:
                    analysis = json.loads(json_match.group())
                    analysis["raw_response"] = analysis_text
                    return analysis
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON response: {analysis_text[:200]}")
                    return None
            else:
                # Fallback if JSON not found
                logger.warning(f"No JSON found in response: {analysis_text[:200]}")
                return None

        except Exception as e:
            logger.warning(f"Error analyzing sentiment for {ticker}: {e}")
            return None

    def get_signal_context(self, ticker: str, signal: Dict) -> Optional[Dict]:
        """Get news context for a trading signal.

        Args:
            ticker: Stock ticker
            signal: Trading signal dict

        Returns:
            Dict with news articles and sentiment analysis
        """
        logger.info(f"Fetching news context for {ticker}...")

        # Fetch news
        articles = self.fetch_news(ticker, limit=5)

        if not articles:
            logger.debug(f"No news found for {ticker}")
            return None

        # Analyze sentiment
        sentiment = self.analyze_sentiment(ticker, signal, articles)

        if not sentiment:
            logger.debug(f"No sentiment analysis for {ticker}")
            return None

        return {
            "ticker": ticker,
            "articles_count": len(articles),
            "articles": articles,
            "sentiment": sentiment,
            "analyzed_at": datetime.now().isoformat(),
        }

    def format_for_telegram(self, context: Dict) -> str:
        """Format news context for Telegram message.

        Args:
            context: News context dict with sentiment analysis

        Returns:
            Formatted string for Telegram
        """
        if not context or "sentiment" not in context:
            return ""

        sentiment = context["sentiment"]
        articles = context.get("articles", [])

        # Build message
        msg = f"\n📰 *News Analysis ({context['articles_count']} articles)*\n"

        # Overall sentiment with score
        sentiment_text = sentiment.get('sentiment', 'N/A').upper()
        sentiment_score = sentiment.get('sentiment_score', 0)
        if sentiment_score:
            msg += f"Sentiment: *{sentiment_text}* ({sentiment_score:.0%})\n"
        else:
            msg += f"Sentiment: *{sentiment_text}*\n"

        # Credibility assessment
        credibility = sentiment.get('credibility', '')
        if credibility:
            credibility_emoji = {'high': '✅', 'medium': '⚠️', 'low': '❌'}.get(credibility, '⚠️')
            msg += f"{credibility_emoji} Credibility: {credibility.capitalize()}\n"

        # Alignment with signal
        alignment = sentiment.get('alignment', 'N/A')
        alignment_score = sentiment.get('alignment_score', 0)
        alignment_emoji = {
            'strongly_aligns': '🟢',
            'aligns': '🟢',
            'neutral': '⚪',
            'conflicts': '🔴',
            'strongly_conflicts': '🔴'
        }.get(alignment, '⚪')

        if alignment_score:
            msg += f"{alignment_emoji} Alignment: {alignment} ({alignment_score:+.0%})\n"
        else:
            msg += f"{alignment_emoji} Alignment: {alignment}\n"

        # Key risks
        risks = sentiment.get("key_risks", [])
        if risks and risks != ["Unable to parse sentiment"]:
            risk_text = ", ".join(risks[:2])  # Top 2 risks
            msg += f"⚠️  Key Risks: {risk_text}\n"

        # Confidence adjustment with strength
        adjustment = sentiment.get('confidence_adjustment', 'maintain').upper()
        strength = sentiment.get('adjustment_strength', 0)

        adjustment_emoji = {
            'INCREASE': '📈',
            'MAINTAIN': '➡️',
            'DECREASE': '📉'
        }.get(adjustment, '➡️')

        if strength:
            msg += f"{adjustment_emoji} Confidence: {adjustment} (+{strength:.0%})\n"
        else:
            msg += f"{adjustment_emoji} Confidence: {adjustment}\n"

        # Reasoning
        reasoning = sentiment.get('reasoning', '')
        if reasoning and reasoning != 'Unable to parse sentiment':
            msg += f"💡 Insight: {reasoning}\n"

        # Add top articles
        if articles:
            msg += "\n*Top News:*\n"
            for i, article in enumerate(articles[:3], 1):
                source = article.get("source", "Source")
                title = article.get("title", "").replace("*", "").replace("_", "")[:60]
                msg += f"{i}. [{source}] {title}\n"

        return msg


def create_analyzer() -> NewsAnalyzer:
    """Create and initialize news analyzer."""
    return NewsAnalyzer()
