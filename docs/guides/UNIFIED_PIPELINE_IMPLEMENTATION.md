# Unified Signal Pipeline - Implementation Guide

**Last Updated**: 2026-07-13 (updated: LSTM+XGBoost ensemble layer removed — see note below)
**Status**: ✅ Production Ready

> **Nota (2026-07-13):** la "ENSEMBLE LAYER" descrita en este doc (`use_ensemble`,
> `ensemble_result`, `--no-ensemble`) fue código que quedó desconectado tras el pivote a
> XGBoost + TimesFM y se retiró por completo — nunca populaba nada en producción. Este doc se
> corrigió para reflejar el estado actual: **Technical + ML (XGBoost) + TimesFM validation + News**.

---

## 📋 Resumen Ejecutivo

The **Unified Signal Pipeline** consolidates 6 fragmented signal generation flows into a single, configurable, production-ready system. This document explains what was changed, why, and how to use it.

### What Changed?
- **Before**: 6 separate scripts (`live_signals.py`, `live_signals_ensemble.py`, etc.) with hardcoded tickers
- **After**: 1 unified `signals/pipeline.py` + centralized configuration (`PIPELINE_TICKERS_RAW`)
- **Benefit**: Consistency, reduced code duplication, centralized configuration, easier maintenance

### Key Improvements
✅ **Fresh Data Fetching**: Always pulls live data (fixes stale cache issues)
✅ **Multi-Layer Analysis**: Technical + ML (XGBoost) + TimesFM validation + News in one flow
✅ **Confluence Scoring**: Rates signal strength 0-5 stars (multi-timeframe agreement)
✅ **Parallel Processing**: Runs multiple tickers concurrently (4x faster)
✅ **Configurable Per-Ticker**: Choose strategies, intervals, analysis layers for each ticker
✅ **Unified CSV Logging**: Consistent signal history with rich metadata

---

## 🎯 Problem & Solution

### The Problem: Fragmentation

Before this implementation, signal generation was scattered across multiple files:

```
live_signals.py              → GLD 1d/1h (macd_vwap, rsi_bb)
live_signals_ensemble.py    → LSTM + XGBoost ensemble voting
live_signals_expanded.py    → News sentiment analysis (Gemini API)
live_signals_multifreq.py   → Multi-timeframe confluence
main.py signal/scan/watch   → Manual entry points
```

**Problems with this approach:**

1. **Inconsistent Tickers**: Each script hardcoded different ticker lists
2. **Duplicate Data Fetching**: `_fetch_data()` in pipeline + `generator.generate()` both fetched data
3. **Stale Cache**: Pipeline loaded CSV cache instead of fresh data
4. **Scattered Logic**: Multi-timeframe analysis spread across different files
5. **News Only on Expanded**: Sentiment analysis only available via `live_signals_expanded.py`
6. **Telegram Duplicates**: Different formatting in different scripts

### The Solution: Unified Pipeline

One `UnifiedPipeline` class that handles **all** flows:

```
┌─ FRESH DATA ──────────────────────────────────────────────┐
│                                                             │
│  fetch_yfinance() → clean() → add_indicators()            │
│  ALWAYS LIVE (never cached)                               │
│                                                             │
├─ TECHNICAL ANALYSIS ──────────────────────────────────────┤
│                                                             │
│  Strategy: MACD+VWAP, RSI+BB, MA Crossover              │
│  Output: Signal (direction, entry, SL, TP, confidence)   │
│                                                             │
├─ ML LAYER (Optional) ─────────────────────────────────────┤
│                                                             │
│  XGBoost prediction (direction + confidence)               │
│  Cross-sectional model first, per-ticker fallback         │
│  Can veto technical signal to HOLD on strong disagreement │
│  Graceful degradation if model not available             │
│                                                             │
├─ CONFLUENCE SCORING ──────────────────────────────────────┤
│                                                             │
│  0-4 stars based on:                                      │
│  • Multiple timeframes agreement                          │
│  • ML confirmation                                        │
│  • High confidence (>70%)                                 │
│  (a 5th star can be added by TimesFM below)                │
│                                                             │
├─ NEWS SENTIMENT (Optional) ───────────────────────────────┤
│                                                             │
│  NewsAPI + Google Gemini (only for actionable signals)    │
│  Sentiment: BULLISH/BEARISH/NEUTRAL                       │
│  Alignment: aligns/disagrees                              │
│                                                             │
├─ TIMESFM VALIDATION (post-processing, 1m/1h only) ────────┤
│                                                             │
│  Zero-shot price forecast, runs after all tickers finish   │
│  +1 confluence star if forecast direction agrees           │
│  Overwrites SL/TP with quantile levels — except for        │
│  mean-reversion strategies (rsi_bb), which keep their own  │
│                                                             │
└─ OUTPUT & LOGGING ────────────────────────────────────────┘
    │
    ├─ CSV Log (signals/logs.csv)
    ├─ Terminal Display (with Confluence stars)
    ├─ Telegram Notification (if enabled + actionable)
    └─ PipelineResult (full data structure for programmatic use)
```

---

## 🏗️ Architecture

### Core Components

#### 1. **TickerConfig**
Configuration per ticker for the pipeline.

```python
@dataclass
class TickerConfig:
    ticker: str                     # 'GLD', 'SPY', 'BTC-USD'
    category: str                   # 'indices', 'stocks', 'crypto', 'commodities'
    intervals: list[str]            # ['1d', '1h', '15m']
    strategies: list[str]           # ['macd_vwap', 'rsi_bb']
    use_ml: bool = True             # Enable ML predictions (XGBoost)
    use_news: bool = True           # Enable news sentiment
    confluence_min_stars: int = 2   # Min stars to consider actionable
```

**Example:**
```python
config = TickerConfig(
    ticker='GLD',
    category='commodities',
    intervals=['1d', '1h'],
    strategies=['macd_vwap', 'rsi_bb'],
    use_ml=True,
    use_news=True,
    confluence_min_stars=2,
)
```

#### 2. **PipelineResult**
Complete output from processing one ticker + interval.

```python
@dataclass
class PipelineResult:
    ticker: str                     # 'GLD'
    interval: str                   # '1d'
    technical_signal: Signal        # From strategy
    ml_prediction: dict | None      # From XGBoost
    news_sentiment: dict | None     # From NewsAPI+Gemini
    confluence_score: int = 0       # 0-5 stars
    final_direction: str = 'HOLD'   # BUY/SELL/HOLD
    final_confidence: float = 0.0   # 0-1
    timestamp: datetime             # When generated

    def is_actionable(self) -> bool:
        """True if final_direction is BUY or SELL"""
        return self.final_direction in ('BUY', 'SELL')
```

#### 3. **UnifiedPipeline**
Main orchestrator class.

```python
class UnifiedPipeline:
    def __init__(
        self,
        use_ml: bool = True,
        use_news: bool = True,
        send_telegram: bool = True,
        max_workers: int = 4,
    ):
        # Initialize components
        self.fetcher = DataFetcher()
        self.processor = DataProcessor()
        self.generator = SignalGenerator()
        self.manager = SignalManager()
        self.notifier = TelegramNotifier()

    def run_ticker(self, config: TickerConfig) -> list[PipelineResult]:
        """Execute pipeline for all intervals of a ticker."""
        # Returns one PipelineResult per interval

    def run_all(
        self,
        configs: list[TickerConfig] | None = None,
        category: str | None = None,
        ticker_filter: str | None = None,
    ) -> list[PipelineResult]:
        """Execute pipeline for all configured tickers (parallel)."""
        # Uses ThreadPoolExecutor for concurrent processing

    def notify_actionable(self, results: list[PipelineResult]) -> int:
        """Send Telegram notifications for actionable signals."""
        # Returns count of notifications sent
```

### Pipeline Execution Flow

```
1. Load TickerConfig (from settings or parameter)
   └─ User specifies: ticker, category, intervals, strategies, layers to use

2. For each TickerConfig:
   a. For each interval:
      - Fetch FRESH data (always via fetch_yfinance)
      - Clean & validate data
      - Add technical indicators
      - Apply strategies (get best signal)
      - Apply ML filter (XGBoost, if enabled)
      - Compute final direction (technical + ML vote)
      - Fetch news sentiment (if enabled + actionable)
      - Compute confluence score

3. Compute multi-timeframe confluence
   └─ Rate signal strength 0-4 stars

4. Run TimesFM batch (after all tickers, 1m/1h only)
   └─ Confluence bonus (+1 star, up to 5) + dynamic SL/TP for momentum strategies

5. Output results
   └─ Terminal display, CSV log, Telegram notifications
```

### Key Fix: Fresh Data Fetching

**BEFORE** (Stale Cache Problem):
```python
# In pipeline:
def _fetch_data(self, ticker, interval):
    df = load_from_csv(ticker, interval)  # ❌ STALE DATA
    return df

# In generator.generate():
df = fetch_yfinance(...)  # ❌ DUPLICATE FETCH
```

**AFTER** (Always Fresh):
```python
def _fetch_data(self, ticker, interval):
    df = fetch_yfinance(...)  # ✅ ALWAYS FRESH
    df = clean_data(df)
    save_to_csv(df, ...)  # Save as backup
    df = add_indicators(df)
    return df

# In _run_single():
df = self._fetch_data(...)  # ONE FETCH
# Strategies apply directly on DataFrame (no re-fetch)
```

**Impact:**
- ✅ Signals based on current prices (not yesterday's cached data)
- ✅ No duplicate data fetching
- ✅ Single source of truth per ticker+interval
- ✅ CSV backup maintained for offline analysis

---

## 💻 Usage

### Command: `python3 main.py pipeline`

#### Basic Scan (All Tickers)
```bash
python3 main.py pipeline
```
Output:
```
===============================================================
  PIPELINE SUMMARY - 2026-02-15 14:30:00
===============================================================
  Tickers analyzed: 12
  Total signals:    24
  Actionable:       4
  Hold:             20

---------------------------------------------------------------
  ACTIONABLE SIGNALS:
---------------------------------------------------------------
  GLD      1d   | BUY  | Conf: 72.5% | [****.]
  MSFT     1h   | SELL | Conf: 68.3% | [***.]
  BTC-USD  1d   | BUY  | Conf: 85.2% | [*****]
  SPY      1h   | HOLD | Confluence: [......]
===============================================================
```

#### Filter by Category
```bash
python3 main.py pipeline --category commodities
python3 main.py pipeline --category crypto
python3 main.py pipeline --category indices
```

#### Single Ticker
```bash
python3 main.py pipeline --ticker GLD
```

#### Disable Layers (Optional)
```bash
python3 main.py pipeline --no-ml         # Skip ML (XGBoost) predictions
python3 main.py pipeline --no-news       # Skip news sentiment
python3 main.py pipeline --no-ml --no-news  # Tech only
```

#### Disable Telegram
```bash
python3 main.py pipeline --no-telegram
```

### Configuration: PIPELINE_TICKERS_RAW

Edit `config/settings.py` to configure which tickers run in the pipeline:

```python
PIPELINE_TICKERS_RAW = [
    # (ticker, category, intervals, strategies, use_ml, use_news, confluence_min)
    ('GLD', 'commodities', ['1d', '1h'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    ('SPY', 'indices', ['1d', '1h'], ['macd_vwap', 'ma_crossover'], True, False, 2),
    ('BTC-USD', 'crypto', ['1d', '1h'], ['macd_vwap'], True, True, 2),
    ('MSFT', 'stocks', ['1d'], ['rsi_bb'], True, True, 3),
]
```

**Tuples format:**
```
(
    ticker,              # 'GLD', 'SPY', 'BTC-USD'
    category,            # 'indices', 'stocks', 'crypto', 'commodities'
    intervals,           # ['1d', '1h', '15m']
    strategies,          # ['macd_vwap', 'rsi_bb', 'ma_crossover']
    use_ml,              # True/False - enable ML filter (XGBoost)
    use_news,            # True/False - fetch news sentiment
    confluence_min_stars # 0-5 (minimum to consider actionable)
)
```

### Programmatic Usage

```python
from signals.pipeline import UnifiedPipeline, TickerConfig

# Create pipeline
pipeline = UnifiedPipeline(
    use_ml=True,
    use_news=True,
    send_telegram=True,
    max_workers=4,
)

# Run for specific ticker
config = TickerConfig(
    ticker='GLD',
    category='commodities',
    intervals=['1d', '1h'],
    strategies=['macd_vwap', 'rsi_bb'],
    use_ml=True,
    use_news=True,
    confluence_min_stars=2,
)

results = pipeline.run_ticker(config)

# Process results
for result in results:
    if result.is_actionable():
        print(f"{result.ticker} {result.interval}: {result.final_direction}")
        print(f"Confluence: {result.confluence_score}/5")
        print(f"Confidence: {result.final_confidence:.1%}")

# Send notifications
sent = pipeline.notify_actionable(results)
print(f"Telegram notifications sent: {sent}")
```

---

## 🔄 Migration from Legacy Scripts

### Deprecated Scripts

These scripts are now **deprecated** and should not be used:

| Legacy Script | Replacement | Status |
|---------------|-------------|--------|
| `live_signals.py` | `pipeline --ticker GLD` | ❌ Deprecated, deleted |
| `live_signals_ensemble.py` | `pipeline` (XGBoost + TimesFM included) | ❌ Deprecated, deleted |
| `live_signals_expanded.py` | `pipeline` (news included) | ❌ Deprecated, deleted |
| `live_signals_multifreq.py` | `pipeline` (confluence included) | ❌ Deprecated, deleted |

### Migration Guide

#### Before: `python3 live_signals.py` (GLD signals with tech + ML)
```bash
# Now use:
python3 main.py pipeline --ticker GLD
```

#### Before: Manual script with hardcoded tickers
```python
# live_signals.py (old)
tickers = ['GLD', 'SPY']
for ticker in tickers:
    signal = generate_signal(ticker, '1d')
```

```bash
# Now use:
python3 main.py pipeline --category commodities --category indices
# Or configure PIPELINE_TICKERS_RAW in settings.py
```

#### Before: Calling `generator.generate()` directly
```python
# SignalGenerator still exists, but is a single-ticker debug/ad-hoc tool now —
# it duplicates most of what UnifiedPipeline._run_single() does independently.
# Prefer UnifiedPipeline for anything beyond a quick manual check.
from signals.generator import SignalGenerator
gen = SignalGenerator()
signal = gen.generate('macd_vwap', 'GLD', '1d', use_ml=True)
```

```python
# Recommended (production path):
from signals.pipeline import UnifiedPipeline, TickerConfig
pipeline = UnifiedPipeline()
config = TickerConfig('GLD', 'commodities', ['1d'], ['macd_vwap'], True, True, 2)
results = pipeline.run_ticker(config)
# ✅ Fresh data, XGBoost ML filter, news, TimesFM validation (all layers)
```

---

## 🧪 Testing

### Unit Tests
```bash
pytest tests/test_signals.py -v  # Signal + manager tests
pytest tests/ -v                  # All tests
```

### Manual Testing
```bash
# Test full pipeline
python3 main.py pipeline

# Test with specific category
python3 main.py pipeline --category commodities

# Test with single ticker
python3 main.py pipeline --ticker GLD

# Test without ML (tech-only)
python3 main.py pipeline --no-ml

# Test Telegram notifications (if configured)
python3 main.py pipeline --telegram
```

### Verify Fresh Data
```bash
# Before running pipeline:
ls -la data/raw/GLD_1d.csv

# Run pipeline
python3 main.py pipeline --ticker GLD

# Check file was updated
ls -la data/raw/GLD_1d.csv
# Timestamp should be recent
```

---

## 📊 Signal Logging

All signals are logged to `logs/signals.csv` with these columns:

```
timestamp, strategy, ticker, interval, direction, entry_price, stop_loss,
take_profit, confidence, risk_reward, ml_filtered, ml_confidence,
ensemble_consensus, news_sentiment, confluence_score
```

(`ensemble_consensus` is a leftover column kept for CSV-schema stability — it's always empty now
that the ensemble layer is gone. See `signals/manager.py` for the exact header.)

### Query Signal History

There's no dedicated `signal-history` command (it never existed despite earlier drafts of this
doc implying otherwise). Options:

```bash
# Raw CSV
cat logs/signals.csv | head -20
grep ",BUY," logs/signals.csv
grep ",SELL," logs/signals.csv

# Aggregated win-rate/P&L analysis by strategy, ticker, hour, day
# (joins closed Alpaca trades against this same CSV)
python3 scripts/signal_accuracy_report.py --days 90
```

---

## 🎨 Output Formatting

### Terminal Display

**Actionable Signal:**
```
═════════════════════════════════════════════════════════════
  BUY GLD (1d)
  Confluence: ⭐⭐⭐⭐. (4/5)
─────────────────────────────────────────────────────────────
  Entry:      $202.50
  Stop Loss:  $201.00
  Take Profit:$204.50
  Risk/Reward: 1:2.5
  Confidence:       72.5%
─────────────────────────────────────────────────────────────
  Technical:  BUY  (macd_vwap, conf=72.5%)
  ML:         BUY  (conf=68.3%)
  TimesFM:    🟢 +1.2% | $200.10 – $206.80
  News:       BULLISH (alignment=aligns)
═════════════════════════════════════════════════════════════
```

**HOLD Signal:**
```
  GLD      1d   | HOLD | Confluence: [......]
```

### Telegram Format
```
🟢 *BUY* - `GLD`
Strategy: `macd_vwap` (1d)
Confluence: ⭐⭐⭐⭐. (4/5)

Entry:  `$202.50`
SL:     `$201.00`
TP:     `$204.50`
R/R:    `1:2.5`
Conf:   `72%`
ML:     `BUY (68%)`

📰 News: BULLISH (aligns with signal)

_2026-02-15 14:30:00_
```

---

## 🐛 Troubleshooting

### Problem: "No actionable signals"
**Possible causes:**
- Market conditions don't match strategy criteria
- Confluence score below threshold
- ML strongly disagrees with technical signal

**Solutions:**
1. Lower `confluence_min_stars` in config
2. Disable layers (`--no-ml`, `--no-news`)
3. Check indicator values manually: `python3 main.py signal --strategy macd_vwap --ticker GLD --interval 1h`

### Problem: "Fresh data not fetching"
**Check:**
```bash
# Verify network connection
python3 -c "from data.fetcher import DataFetcher; DataFetcher().fetch_yfinance('GLD', '1d', 7)"

# Check logs for errors
grep "Fetch" logs/trading_system.log | tail -20
```

### Problem: "ML model not found"
**Possible causes:**
- Model not trained for that ticker+interval
- Model file corrupt/deleted

**Solution:**
```bash
# Train the cross-sectional XGBoost model (primary ML path)
python3 main.py train-xgb-cross --interval 1d

# Verify file exists
ls -la models/saved/all_tickers_1d_xgb/
```

### Problem: "Telegram not sending"
**Check:**
```bash
# Verify Telegram is configured
cat .env | grep TELEGRAM
# Should show BOT_TOKEN and CHAT_ID

# Test notification manually
python3 -c "from signals.telegram_bot import TelegramNotifier; TelegramNotifier().send_alert('Test message')"
```

---

## 📈 Performance

### Timing
- **Single ticker (1 interval)**: ~2-3 seconds (fetch + indicators + strategies)
- **Single ticker (2 intervals)**: ~4-5 seconds
- **10 tickers × 2 intervals**: ~8-10 seconds (parallel with ThreadPoolExecutor)
- **Full pipeline (12 tickers × 2 intervals)**: ~10-15 seconds

### Memory
- Per ticker: ~50-100 MB (depends on data interval)
- Typical run: 500 MB - 1 GB total

### Data Freshness
- Data fetched at pipeline start
- Cached in memory during multi-interval processing
- Saved to CSV after processing

---

## 📚 Related Documentation

- [../reference/MODULES_API.md](../reference/MODULES_API.md) - Full module API, kept in sync with the code
- [FRESH_DATA_FIX.md](../analysis/FRESH_DATA_FIX.md) - Detailed data fix explanation
- [SIGNAL_GENERATION_GUIDE.md](SIGNAL_GENERATION_GUIDE.md) - Strategy details
- [ML_RETRAINING_IMPLEMENTATION.md](ML_RETRAINING_IMPLEMENTATION.md) - Model training (LSTM legacy path, see note in `docs/README.md`)

---

## ✨ Summary

The Unified Signal Pipeline replaces 6 fragmented scripts with a single, consistent, configurable system that:

✅ **Always uses fresh data** (not stale cache)
✅ **Combines all analysis layers** (technical + ML/XGBoost + TimesFM validation + news)
✅ **Rates signal strength** with confluence scoring
✅ **Processes multiple tickers in parallel** (4x faster)
✅ **Configurable per-ticker** (strategies, intervals, layers)
✅ **Rich output** (terminal, CSV, Telegram)
✅ **Easy to maintain** (single source of truth)

---

**Last Updated**: 2026-02-15
**Maintainer**: Claude Code
**Status**: ✅ Production Ready
