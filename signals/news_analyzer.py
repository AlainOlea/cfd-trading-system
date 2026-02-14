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
            self.model = genai.GenerativeModel("gemini-1.5-flash")
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
                    f"Title: {a['title']}\n"
                    f"Source: {a['source']}\n"
                    f"Published: {a['published_at']}\n"
                    f"Summary: {a['description']}"
                    for a in articles[:5]
                ]
            )

            prompt = f"""Analyze the sentiment of these news articles about {ticker} in the context of a {signal['direction']} trading signal with {signal['confidence']:.2%} confidence.

News Articles:
{articles_text}

Provide a brief analysis (2-3 sentences max) addressing:
1. Overall sentiment (bullish/bearish/neutral)
2. Key risk factors mentioned
3. Alignment with trading signal (strongly aligns/aligns/neutral/conflicts/strongly conflicts)
4. Confidence adjustment (decrease/maintain/increase)

Format as JSON with keys: sentiment, risks, alignment, confidence_adjustment, summary"""

            response = self.model.generate_content(prompt)
            analysis_text = response.text

            # Parse Gemini response
            import json
            import re

            # Extract JSON from response
            json_match = re.search(r"\{.*\}", analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analysis["raw_response"] = analysis_text
                return analysis
            else:
                # Fallback if JSON parsing fails
                return {
                    "sentiment": "neutral",
                    "risks": "Unable to parse sentiment",
                    "alignment": "neutral",
                    "confidence_adjustment": "maintain",
                    "summary": analysis_text[:200],
                }

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
            context: News context dict

        Returns:
            Formatted string for Telegram
        """
        if not context or "sentiment" not in context:
            return ""

        sentiment = context["sentiment"]
        articles = context.get("articles", [])

        # Build message
        msg = f"\n📰 *News Analysis ({context['articles_count']} articles)*\n"
        msg += f"Sentiment: *{sentiment.get('sentiment', 'N/A').upper()}*\n"
        msg += f"Alignment: {sentiment.get('alignment', 'N/A')}\n"

        if sentiment.get("risks"):
            msg += f"⚠️  Risks: {sentiment['risks']}\n"

        msg += f"Confidence Adjustment: {sentiment.get('confidence_adjustment', 'maintain').upper()}\n"

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
