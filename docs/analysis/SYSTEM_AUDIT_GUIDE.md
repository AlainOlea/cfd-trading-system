# CFD Trading System - Financial Audit Guide

## System Overview

This is a **hybrid automated trading system** for CFDs (Contracts for Difference) that generates buy/sell signals using technical analysis and machine learning, then executes paper trades via Alpaca Markets API.

### How It Works (High Level)

```
Data Feed → Indicators → Strategy → Signal → ML Filter → Paper Trade
(yfinance)  (pandas-ta)   (3 strats)  (BUY/SELL)  (XGBoost)   (Alpaca)
```

- **Data**: Real-time and historical market data from Yahoo Finance (yfinance)
- **Indicators**: 21 technical indicators computed via pandas-ta (MACD, RSI, Bollinger Bands, VWAP, etc.)
- **Strategies**: 3 trading strategies generate signals:
  - MACD + VWAP (intraday scalping)
  - RSI + Bollinger Bands (mean reversion)
  - Moving Average Crossover (swing trading)
- **ML Filter**: XGBoost classifier filters signals (cross-sectional model trained on 19 tickers, 5 years of data)
- **Execution**: Paper trading on Alpaca Markets (bracket orders with SL/TP)

### Tickers Traded

- **Stocks/ETFs**: SPY, QQQ, IWM, DIA, GLD, SLV, USO, UNG, AAPL, NVDA, MSFT, AMZN, GOOGL, META, TSLA
- **Crypto**: BTC-USD, ETH-USD, SOL-USD, XRP-USD (buy only, no shorting)

### Automated Execution

- **Windows Task Scheduler** runs `.bat` files that invoke WSL
- **Hourly signals**: Mon-Fri, 07:00-15:59 ET (intraday, DAY orders, SL 0.5%, TP 1%)
- **Daily signals**: Mon-Fri, 07:00 ET (swing, GTC orders, SL 1.5%, TP 3%)

---

## Risk Management Rules

| Parameter | Value | Notes |
|-----------|-------|-------|
| Max risk per trade | 2% of equity (nominal) | For scalping strategies (tight 0.5-0.7% stops) the 5% position cap binds before this ever does — real $ risk per trade is closer to 0.03% of equity |
| Max position size | 5% of equity | Hard cap per position — this is what actually sizes every trade in practice |
| Max gross exposure | 50% of equity | Aligned with max concurrent positions (10 x 5% = 50%) |
| Max concurrent positions | 10 | Limit correlated exposure |
| Max crypto aggregate / single | 10% / 3% of equity | |
| Stop Loss | 0.5% intraday (macd_vwap), 0.7% (rsi_bb), 1.5% swing | Dynamic based on strategy/interval |
| Take Profit | 1% intraday (macd_vwap), bb_middle (rsi_bb), 3% swing | rsi_bb's TP is a distance to the Bollinger middle band, not a fixed % |
| Min confidence (ML) | 60% | Signals below this are rejected |
| Min confluence | 3 stars (default) | Multi-timeframe agreement required |

---

## Known Issues (Critical)

### DOGE-USD Bug (Now Fixed)

- **Problem**: The bot accumulated a $80K position in DOGE by buying every hour at $0.10, then DOGE dropped to $0.08 and the bot sold 589K tokens at a 20% loss
- **Impact**: -$9,134 loss (93% of total account loss)
- **Root cause**: No position sizing limits for crypto; the bot kept DCA-ing into a falling asset
- **Fix**: DOGE removed from default tickers
- **Lesson**: Position sizing and max exposure limits need to be enforced at the broker level

### Data Freshness Issue

- The system fetches data from Yahoo Finance, which can be delayed
- Signals may be based on stale prices
- **Status**: Known issue, awaiting API keys for EODHD or Finnhub for real-time data

---

## Historical Performance (Paper Trading)

**Period**: May 24 - June 15, 2026 (22 days)

| Metric | Value |
|--------|-------|
| Starting Equity | $100,000 |
| Ending Equity | $90,192 |
| Total P&L | -$9,808 (-9.8%) |
| Total Trades | 41 closed |
| Win Rate | ~55% |
| Biggest Winner | SLV: +$47.76 (95%) |
| Biggest Loser | DOGE: -$9,134 (see bug above) |

**Without DOGE bug**: Account would be ~$99,326 (-0.7%), which is within normal variance for a 3-week paper trading period.

---

## What to Evaluate

As a financial advisor, please assess:

### 1. Strategy Viability
- Are the 3 strategies (MACD+VWAP, RSI+BB, MA Crossover) sound for the asset classes traded?
- Are the SL/TP levels appropriate for intraday vs swing?
- Is the risk-reward ratio (1:2) realistic?

### 2. Risk Management
- Is 2% max risk per trade appropriate for paper trading? (note: in practice the 5% position-size
  cap binds first for scalping strategies — see the table above — so this parameter is mostly nominal today)
- Should crypto have different risk parameters than stocks? (it already does: 10%/3% aggregate/single vs 50%/5% for stocks)
- Is the 10-position max concurrent limit (raised from 3, aligned with the 50% gross exposure cap) sufficient diversification?
- Drawdown limits already exist (5% warning, 10% halt) — has the halt ever actually triggered in practice?

### 3. Position Sizing
- The bot uses a formula: `shares = min(risk_based, capital_based)` where risk_based = (equity * 2%) / (entry - SL)
- Is this formula correct for both stocks and crypto?
- Should crypto positions be smaller due to higher volatility?

### 4. ML Filter Effectiveness
- XGBoost cross-sectional model: 80.3% accuracy (1h), 73.4% accuracy (1d)
- Is this sufficient for signal filtering?
- Should the ML confidence threshold be higher than 60%? (also note: observed confidence values
  cluster in a narrow 60-63.5% band with no measured correlation to trade outcome — the score's
  calibration may need revisiting before raising the threshold would help)

### 5. Asset Allocation
- Current: 15 stocks/ETFs + 4 crypto
- Is this diversified enough?
- Should bonds (TLT), sectors (XLF, XLE), or international equities be added?

### 6. Execution Quality
- Bracket orders with SL/TP
- Crypto: notional market orders (no bracket due to Alpaca limitation)
- Intraday: DAY orders (expire at market close)
- Swing: GTC orders (good until canceled)
- Are these execution parameters appropriate?

### 7. Overall Assessment
- Is this system viable for live trading?
- What are the biggest risks?
- What improvements would you recommend before going live?
- Should the user paper trade for longer before switching to real money?

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `config/settings.py` | All configurable parameters |
| `signals/pipeline.py` | Main signal generation pipeline |
| `signals/alpaca_broker.py` | Alpaca execution logic |
| `strategies/` | Trading strategy implementations |
| `models/xgboost_model.py` | ML signal filter |
| `signals/telegram_bot.py` | Alert notifications |

---

## Commands for Reference

```bash
# Run a single signal
python3 main.py signal --ticker SPY --interval 1h --strategy macd_vwap

# Run full pipeline (all tickers)
python3 main.py pipeline

# Paper trade (manual)
python3 main.py paper-trade --ticker SPY --interval 1h

# Backtest a strategy
python3 main.py backtest --ticker SPY --strategy macd_vwap --interval 1d

# Check account status
python3 main.py status
```
