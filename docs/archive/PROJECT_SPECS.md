> **ARCHIVADO** — snapshot de la etapa más temprana del proyecto: sin Alpaca, sin XGBoost, sin
> TimesFM, referencia `run_script.py` (no existe). El `CLAUDE.md` actual en la raíz del repo es
> el documento vigente para setup y arquitectura. Solo referencia histórica.

# CFD Trading System (snapshot histórico)

## ⚡ IMPORTANT: Initial Session Setup

**REQUIRED ON SESSION START:**

When beginning a new session with Claude, you MUST read the following documentation as context:

1. **FIRST** - Read this file (CLAUDE.md) - Project specifications
2. **THEN** - Read documentation in order:
   - `docs/README.md` - Documentation index and quick navigation
   - `docs/guides/INTEGRATION_SUMMARY.md` - System architecture and features
   - `docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md` - Sentiment analysis improvements
   - `docs/guides/NEWS_ANALYZER_SETUP.md` - News sentiment integration

**Quick Command to Load All Context:**
```bash
cat CLAUDE.md docs/README.md docs/guides/INTEGRATION_SUMMARY.md docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md
```

**Why?** The documentation contains:
- ✅ Current system state and capabilities
- ✅ Sentiment analysis improvements (V2 prompt)
- ✅ News sentiment integration details
- ✅ 41 pre-configured scripts and workflows
- ✅ Central script manager usage
- ✅ All recent improvements and architecture

**Failure to read docs will result in:**
- ❌ Incomplete understanding of project state
- ❌ Inability to suggest improvements
- ❌ Missing context on recent changes
- ❌ Inefficient task execution

---

## Project Overview
Sistema hibrido de trading tecnico para CFDs. Genera senales automaticas (analisis tecnico + ML) con ejecucion manual en Plus500 y senales para crypto. Python 3.10+.

## Setup Commands
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 main.py status          # verificar instalacion
python3 main.py list-strategies # ver estrategias disponibles
pytest tests/ -v                # correr tests
```

## Environment
- **Python**: 3.12.3 (/usr/bin/python3.12) - Migrado desde 3.14 por compatibilidad con pandas-ta, numba, tensorflow
- **venv**: `source venv/bin/activate` (Python 3.12, todas las dependencias core instaladas)
- **pandas-ta**: 0.4.71b0 - Funciona correctamente. 26 columnas de indicadores verificadas con SPY 1d 365d
- **TensorFlow**: Pendiente instalar (Phase 6). Compatible con Python 3.12
- **yfinance**: 1.1.0 - Probado con SPY (daily) y BTC-USD (hourly)

## Project Structure
```
config/settings.py          # Configuracion central (tickers, parametros, ML config)
main.py                     # CLI entry point (Click) - 7 comandos
data/fetcher.py             # [DONE] DataFetcher: yfinance + CCXT/Bitso
data/processor.py           # [DONE] DataProcessor: limpieza y validacion
indicators/technical.py     # [DONE] TechnicalIndicators: 12 indicadores via pandas-ta
strategies/base.py          # [DONE] BaseStrategy: clase abstracta + position sizing
strategies/scalping/        # [DONE] MACDVWAPStrategy, RSIBBStrategy
strategies/swing/           # [DONE] MACrossoverStrategy
backtesting/engine.py       # [DONE] BacktestEngine: VectorBT Portfolio.from_signals()
backtesting/metrics.py      # [DONE] PerformanceMetrics: sharpe, sortino, drawdown, win_rate, etc.
backtesting/report.py       # [DONE] BacktestReport: HTML + plotly (3-row: equity, signals, drawdown)
signals/generator.py        # [DONE] SignalGenerator + Signal dataclass: fetch -> indicators -> strategy -> signal
signals/manager.py          # [DONE] SignalManager: log CSV, historial, formato terminal
signals/telegram_bot.py     # [DONE] TelegramNotifier: Markdown signals via Telegram bot
models/hybrid_model.py      # [DONE] HybridLSTMTransformer: LSTM 2x50 -> Transformer 2-head -> Dense -> sigmoid
models/trainer.py           # [DONE] ModelTrainer: prepare data, train, evaluate, save/load (weights + scaler + metadata)
models/predictor.py         # [DONE] PricePredictor: load model, predict direction, filter signals
tests/                      # [DONE] 47 tests (conftest, data, indicators, strategies, backtesting, signals)
```

## Implemented Modules (Details)

### data/fetcher.py - DataFetcher
- `fetch_yfinance(ticker, interval, days)` -> DataFrame OHLCV. Tested: SPY 1d, BTC-USD 1h
- `fetch_ccxt(symbol, timeframe, limit)` -> DataFrame OHLCV via CCXT. Lazy-loads exchange connection
- `save_to_csv(df, ticker, interval)` -> guarda en `data/raw/{TICKER}_{interval}.csv`
- `load_from_csv(ticker, interval)` -> carga desde `data/raw/`
- `_normalize_columns(df)` -> flatten MultiIndex de yfinance, lowercase, valida OHLCV

### data/processor.py - DataProcessor
- `clean_data(df)` -> deduplica index, sort, ffill gaps (limit=3), drop NaN, clip volume >= 0
- `validate_data(df)` -> verifica: columnas OHLCV, no vacio, DatetimeIndex, no NaN, high >= low
- `save_processed(df, ticker, interval)` -> guarda en `data/processed/`

### indicators/technical.py - TechnicalIndicators
- `add_all_indicators(df)` -> agrega los 12 indicadores de golpe
- `add_macd(df, fast, slow, signal)` -> macd, macd_signal, macd_histogram
- `add_rsi(df, period)` -> rsi
- `add_bollinger_bands(df, period, std_dev)` -> bb_upper, bb_middle, bb_lower, bb_bandwidth, bb_percent
- `add_sma(df, period)` -> sma_{period} (default: sma_50, sma_200)
- `add_ema(df, period)` -> ema_{period} (default: ema_50, ema_200)
- `add_vwap(df)` -> vwap (con fallback para daily data)
- `add_stochastic(df, period, smooth_k, smooth_d)` -> stoch_k, stoch_d
- `add_adx(df, period)` -> adx, plus_di, minus_di
- `add_atr(df, period)` -> atr
- `add_obv(df)` -> obv
- Total: 26 columnas (5 OHLCV + 21 indicadores). Todos usan params de config/settings.py
- Tested: SPY 1d 251 rows -> all indicators computed correctly

### strategies/ - Trading Strategies
- `strategies/base.py` - BaseStrategy ABC: generate_signals(), calculate_position_size(), _init_signal_columns()
- `strategies/scalping/macd_vwap.py` - MACDVWAPStrategy: MACD cross + VWAP filter. SL 0.5%, TP 1%
- `strategies/scalping/rsi_bb.py` - RSIBBStrategy: RSI oversold/overbought + BB touch. SL 0.7%, TP=bb_middle
- `strategies/swing/ma_crossover.py` - MACrossoverStrategy: SMA50/200 golden/death cross. SL 2%, TP 3%
- `strategies/__init__.py` - STRATEGY_MAP = {'macd_vwap': ..., 'rsi_bb': ..., 'ma_crossover': ...}
- Signal columns added: signal (BUY/SELL/HOLD), entry_price, stop_loss, take_profit, confidence (0-1)

### backtesting/engine.py - BacktestEngine
- `BacktestResult` dataclass: strategy_name, ticker, interval, portfolio (vbt.Portfolio), signals_df, initial_capital
- `BacktestEngine(initial_capital, commission, slippage)` uses config/settings.py defaults
- `run(strategy, df, ticker, interval)` -> BacktestResult. Uses VectorBT Portfolio.from_signals()
- `_interval_to_freq(interval)` -> pandas frequency string for VectorBT

### backtesting/metrics.py - PerformanceMetrics
- `calculate_all(result)` -> dict with 17 metrics: return, trades, win_rate, sharpe, sortino, drawdown, profit_factor, expectancy, best/worst/avg trades, consecutive wins/losses, avg duration
- `format_summary(metrics)` -> formatted terminal string
- `_safe_float(value, default)` -> handles NaN/inf from VectorBT stats
- `_max_consecutive(mask)` -> counts max consecutive True in boolean series

### backtesting/report.py - BacktestReport
- `generate_html(result, metrics)` -> HTML file path
- 3-row plotly subplot: equity curve (blue), price + BUY/SELL markers (green/red triangles), drawdown % (red fill)
- Title includes strategy, ticker, interval, return, win rate, trade count
- Uses plotly_dark template, saves to results/ directory

### signals/generator.py - SignalGenerator
- `Signal` dataclass: direction, entry_price, stop_loss, take_profit, confidence, risk_reward_ratio, ml_filtered, to_dict()
- `SignalGenerator.generate(strategy_name, ticker, interval, days, use_ml)` -> Signal. Full pipeline: fetch -> clean -> indicators -> strategy -> latest signal
- `SignalGenerator.get_latest_actionable(strategy_name, ticker, interval, lookback)` -> Signal|None. Searches last N bars for BUY/SELL
- `_apply_ml_filter(signal, df)` -> graceful degradation if ML model not available (Phase 6 hook)
- `_estimate_days(interval)` -> auto-calculates days for sufficient indicator warmup (1m=7d, 5m=30d, 1h=90d, 1d=365d)

### signals/manager.py - SignalManager
- `log_signal(signal)` -> appends to logs/signals.csv (DictWriter, 12 columns)
- `get_history(ticker, n)` -> DataFrame with last N signals (optional ticker filter)
- `format_signal(signal)` -> formatted terminal block with entry/SL/TP/RR/confidence
- `format_history(df)` -> tabular display of signal history

### signals/telegram_bot.py - TelegramNotifier
- `send_signal(signal)` -> sends Markdown-formatted signal to Telegram chat. Only if enabled + configured
- `send_alert(message)` -> sends generic alert message
- `_format_signal_message(signal)` -> Markdown with emoji, entry/SL/TP/RR/confidence, ML info
- `is_configured` property: checks BOT_TOKEN and CHAT_ID are set
- Graceful degradation: returns False silently if not configured

### models/hybrid_model.py - HybridLSTMTransformer
- `TransformerEncoderBlock` custom Keras layer: MultiHeadAttention + FFN + LayerNorm + residuals
- `HybridLSTMTransformer.build(input_shape)` -> compiled Keras model. Architecture: Input -> LSTM(50) -> Dropout -> LSTM(50) -> Dropout -> Dense(d_model) -> TransformerEncoder -> GlobalAvgPool -> Dense(25) -> Dropout -> sigmoid
- `predict(X)` -> bullish probability (0-1). Input shape: (1, lookback_window, n_features)
- All hyperparams from config/settings.py (LSTM_LAYERS, TRANSFORMER_CONFIG, ML_CONFIG)

### models/trainer.py - ModelTrainer
- `prepare_data(df)` -> (X_train, y_train, X_test, y_test). Sliding windows of lookback_window. Labels: 1 if next close > current close. MinMaxScaler normalization. Chronological split (no shuffle)
- `train(model, X_train, y_train)` -> history dict. EarlyStopping(patience=10) + ReduceLROnPlateau
- `evaluate(model, X_test, y_test)` -> {loss, accuracy, precision, recall}
- `save_model(model, ticker, interval)` -> saves weights.h5 + scaler.pkl + metadata.json to models/saved/{ticker}_{interval}/
- `load_model(ticker, interval)` -> (model, scaler, metadata) tuple. Rebuilds architecture from metadata

### models/predictor.py - PricePredictor
- `load(ticker, interval)` -> loads model+scaler+metadata from disk
- `predict_next(df)` -> {direction: BUY/SELL, confidence: 0-1, probability: raw sigmoid}
- `filter_signal(signal_direction, prediction)` -> {accepted: bool, reason: str}. Rejects if ML disagrees or confidence < threshold

### config/settings.py - Cambios Fase 0
- `LSTM_CONFIG` renombrado a `ML_CONFIG` (mismos params de entrenamiento)
- Nuevo `TRANSFORMER_CONFIG`: n_heads=2, d_model=64, ff_dim=128, transformer_dropout=0.1, dense_units=25
- `LSTM_LAYERS`: quitado `dense1_units` (ahora en TRANSFORMER_CONFIG)

### main.py - Comando fetch-data (lineas 77-93)
- Conectado a DataFetcher + DataProcessor
- Flujo: fetch -> clean -> validate -> save_to_csv
- Soporta --source yfinance|bitso

## Code Style
- Python 3.10+ con type hints
- Clases con docstrings descriptivos
- Parametros configurables desde `config/settings.py`, nunca hardcoded
- Indicadores: usar pandas-ta si disponible, sino implementar con pandas/numpy
- Logging via modulo `logging` (ya configurado en main.py)
- Variables de entorno para secrets via python-dotenv (.env)

## Architecture Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| ML Model | Hibrido LSTM+Transformer | ~95.9% accuracy. TensorFlow completo en laptop |
| Backtesting | VectorBT | 1000x faster, ideal para scalping. Portfolio.from_signals() |
| Alertas | Terminal + Telegram bot | Senales consola + notificaciones moviles |
| Crypto | Solo senales | Bitso NO soporta HFT/scalping |
| Data | yfinance + CCXT | yfinance=stocks/indices, CCXT=crypto data |
| Indicators | pandas-ta (o manual si Python 3.14) | 130+ indicadores, MIT license |
| Plus500 | Manual execution | Plus500 NO tiene API |

## Do's and Don'ts

### Do
- Usar parametros de `config/settings.py` para todo (MACD_PARAMS, RSI_PARAMS, etc.)
- Implementar graceful degradation (ej: Telegram no configurado -> solo terminal)
- Guardar datos en `data/raw/` (CSV) y modelos en `models/saved/`
- Validar DataFrames antes de procesar (columnas OHLCV completas)
- Usar `click.echo()` para output al usuario en CLI
- Risk management: max 2% por trade, max 3 posiciones concurrentes
- Usar `source venv/bin/activate` antes de ejecutar comandos

### Don't
- NO hardcodear tickers, intervalos o parametros de estrategias
- NO usar TFLite - usar TensorFlow completo (se corre en laptop)
- NO automatizar ejecucion en Plus500 (no tiene API)
- NO hacer HFT/scalping en Bitso (no lo soporta)
- NO usar yfinance para produccion critica (se rompe frecuentemente con scraping)
- NO commitear .env, API keys, modelos entrenados (.h5, .keras), ni data/raw/*.csv

## Key Libraries (Installed - Python 3.12 venv)
| Library | Version | Use | Status |
|---------|---------|-----|--------|
| pandas | 3.0.0 | DataFrames | OK |
| numpy | 2.2.6 | Calculo numerico | OK |
| pandas-ta | 0.4.71b0 | Indicadores tecnicos | OK, tested |
| yfinance | 1.1.0 | Datos stocks/indices | OK, tested |
| ccxt | 4.5.37 | Datos crypto (Bitso) | OK |
| click | 8.3.1 | CLI framework | OK |
| python-dotenv | 1.2.1 | Variables de entorno | OK |
| matplotlib | 3.10.8 | Graficas | OK |
| plotly | 6.5.2 | Graficas interactivas | OK |
| scikit-learn | 1.8.0 | Preprocessing ML | OK |
| pytest | 9.0.2 | Testing | OK |

## Libraries Pending Install
| Library | Needed For | Notes |
|---------|------------|-------|
| tensorflow 2.20.0 | Phase 6: ML Model | Installed, CPU mode, tested OK |
| python-telegram-bot 22.6 | Phase 7: Telegram | Installed, tested OK |
| vectorbt>=0.28 | Phase 4: Backtesting | Installed v0.28.4, tested OK |

## Recommended Reference Repos
- `vercel-labs/agent-skills` - Patron AGENTS.md para contexto de agentes (formato de este archivo)
- `0xemmkty/QuantMuse` - Pipeline completo: data->indicadores->portfolio->backtesting->AI
- `whchien/ai-trader` - Backtrader + CLI + 20 estrategias ejemplo
- `nkaz001/hftbacktest` - Backtesting tick-level para scalping
- `freqtrade/freqtrade` - Trading bot con integracion Telegram completa
- `dcajasn/Riskfolio-Lib` - Portfolio optimization y risk management
- `stefan-jansen/machine-learning-for-trading` - ML workflow para trading

## Alternative Data Sources (for production, replace yfinance)
- **Finnhub** (finnhub.io) - Real-time forex/stocks, 60 calls/min free tier
- **Alpha Vantage** (alphavantage.co) - Multi-asset, built-in indicators, 5 calls/min free
- **EODHD** (eodhd.com) - Historical tick data, stock screeners, best for backtesting
- **Twelve Data** (twelvedata.com) - Global coverage, simple API

## Trading Research (2025-2026)

### Scalping Indicators (State of the Art)
- Tier 1: VWAP + Volume Profile + Order Flow/Cumulative Delta
- Tier 2: MACD (momentum) + RSI+Stochastic (overbought/oversold)
- Tier 3: Bollinger Bands (volatility) + MFI (volume momentum)
- MACD scalping settings: 5,13,8 o 8,17,9 (shorter than standard 12,26,9)
- VWAP+MACD: price closes through VWAP + MACD histogram confirms = high probability

### ML Price Prediction
- Hybrid LSTM+Transformer > pure LSTM (~95.9% vs 91.6%)
- GRU > LSTM for crypto minute-level
- Feature engineering > model architecture (volume, RSI, MACD, BB, ATR, OHLCV)
- XGBoost + features beats LSTM in 80% of cases for tabular signals
- LSTM-Transformer best for multi-step prediction (5-20 candles ahead)

### Risk Management
- 1-2% max risk per trade (configured at 2%)
- Dynamic drawdown: reduce at 5% down, halt at 15%
- Scalping risk-reward: min 1:1.5, ideal 1:2 or 1:3
- Max 3 concurrent positions
- Avoid correlated instruments simultaneously

---

## Implementation Plan (10 Phases)

### Current Status
- **DONE Phase 0**: requirements.txt updated (tensorflow, python-telegram-bot), config/settings.py updated (ML_CONFIG, TRANSFORMER_CONFIG)
- **DONE Phase 1**: data/fetcher.py, data/processor.py, data/__init__.py, main.py fetch-data command connected and tested
- **DONE Phase 2**: indicators/technical.py with 12 indicators (26 columns total). Migrated venv to Python 3.12
- **DONE Phase 3**: 3 strategies implemented (MACD+VWAP: 21 signals, RSI+BB: 7 signals on SPY 1y). STRATEGY_MAP dict
- **DONE Phase 4**: VectorBT backtesting engine, metrics, HTML reports. Tested all 3 strategies on SPY 1d
- **DONE Phase 5**: SignalGenerator + SignalManager. CLI command `signal` connected. Logs to CSV
- **DONE Phase 6**: Hybrid LSTM+Transformer model. 70,587 params. train-lstm + --use-ml working
- **DONE Phase 7**: TelegramNotifier with graceful degradation. Integrated into signal command
- **DONE Phase 8**: 47 tests (all passing). conftest fixtures, 5 test modules
- **DONE Phase 9**: `scan` (multi-ticker x multi-strategy) + `watch` (continuous monitoring with market hours). Market hours per instrument type (indices, commodities, crypto). GPU detected (RTX 5060 8GB) but needs CUDA toolkit in WSL2

### Phase 0: Dependencies Update - DONE
- `requirements.txt`: tensorflow-lite -> tensorflow>=2.15.0, added python-telegram-bot>=20.0
- `config/settings.py`: LSTM_CONFIG -> ML_CONFIG, added TRANSFORMER_CONFIG (n_heads=2, d_model=64, ff_dim=128)

### Phase 1: Data Module (`data/`) - DONE
- Created `data/fetcher.py` (DataFetcher), `data/processor.py` (DataProcessor)
- Modified `data/__init__.py`, `main.py` (fetch-data command working)
- Verified: SPY 1d (21 rows), BTC-USD 1h (168 rows) fetched and saved successfully

### Phase 2: Technical Indicators (`indicators/`) - DONE
- Migrated venv to Python 3.12.3 (from 3.14) for pandas-ta/numba compatibility
- Created `indicators/technical.py` with TechnicalIndicators class (12 indicators, 21 new columns)
- Modified `indicators/__init__.py`
- Verified: SPY 1d 251 rows -> 26 columns (5 OHLCV + 21 indicators), all values reasonable

### Phase 3: Trading Strategies (`strategies/`) - DONE
Create: `strategies/base.py`, `strategies/scalping/macd_vwap.py`, `strategies/scalping/rsi_bb.py`, `strategies/swing/ma_crossover.py`
Modify: `strategies/__init__.py` (STRATEGY_MAP), `strategies/scalping/__init__.py`, `strategies/swing/__init__.py`
Depends: Phase 2

### Phase 4: Backtesting Engine (`backtesting/`) - DONE
- Switched from backtesting.py to **VectorBT** (1000x faster, ideal for scalping)
- Created `backtesting/engine.py` (BacktestEngine + BacktestResult dataclass, uses Portfolio.from_signals())
- Created `backtesting/metrics.py` (PerformanceMetrics: 17 metrics, NaN/inf safe, formatted terminal summary)
- Created `backtesting/report.py` (BacktestReport: 3-row plotly HTML - equity curve, price+signals, drawdown)
- Modified `backtesting/__init__.py`, `main.py` (backtest command fully connected)
- Tested: MACD+VWAP (8 trades, 7.16% return), RSI+BB (1 trade, 21.91%), MA Crossover (0 trades - expected on 1y daily)
- Reports saved to `results/backtest_{strategy}_{ticker}_{interval}.html`

### Phase 5: Signal Generator (`signals/`) - DONE
- Created `signals/generator.py` (Signal dataclass + SignalGenerator: fetch -> clean -> indicators -> strategy -> signal)
- Created `signals/manager.py` (SignalManager: CSV log, history retrieval, terminal formatting)
- Modified `signals/__init__.py`, `main.py` (signal command fully connected)
- Features: auto-days estimation per interval, ML filter hook (Phase 6), risk/reward ratio, signal history display
- Tested: SPY 1d (macd_vwap, rsi_bb), BTC-USD 1h (macd_vwap). CSV log accumulates in logs/signals.csv

### Phase 6: Hybrid ML Model (`models/`) - DONE
- TensorFlow 2.20.0 + Keras 3.13.2 installed (CPU mode, Python 3.12)
- Created `models/hybrid_model.py` (HybridLSTMTransformer: LSTM 2x50 -> projection -> TransformerEncoderBlock 2-head -> GAP -> Dense -> sigmoid). 70,587 params
- Created `models/trainer.py` (ModelTrainer: prepare_data with sliding windows + labels, train with EarlyStopping + ReduceLROnPlateau, evaluate with precision/recall, save/load model+scaler+metadata)
- Created `models/predictor.py` (PricePredictor: load trained model, predict_next from DataFrame, filter_signal with confidence threshold)
- Modified `models/__init__.py`, `main.py` (train-lstm command connected), `signals/generator.py` (--use-ml loads and applies model)
- Tested: SPY 1d 20 epochs -> 44% accuracy (expected with only 140 train samples). Model saved to models/saved/SPY_1d/
- --use-ml flag working: loads model, predicts, filters signal by direction + confidence

### Phase 7: Telegram Alerts (`signals/`) - DONE
- Installed python-telegram-bot 22.6
- Created `signals/telegram_bot.py` (TelegramNotifier: send_signal, send_alert, Markdown formatting)
- Modified `signals/__init__.py`, `main.py` (signal command sends Telegram if configured + actionable signal)
- Updated `.env.example` with Telegram setup instructions
- Graceful degradation: no crash if Telegram not configured, just skips notification
- Only sends notifications for BUY/SELL signals (not HOLD)

### Phase 8: Tests (`tests/`) - DONE
- Created `tests/conftest.py` (3 fixtures: sample_ohlcv_df 100 rows, large_ohlcv_df 300 rows, df_with_indicators)
- Created `tests/test_data.py` (7 tests: clean, validate, edge cases)
- Created `tests/test_indicators.py` (8 tests: all indicators, ranges, column checks)
- Created `tests/test_strategies.py` (12 tests: strategy map, signal generation, position sizing)
- Created `tests/test_backtesting.py` (11 tests: engine, metrics, safe_float)
- Created `tests/test_signals.py` (9 tests: Signal dataclass, manager log/retrieve/format)
- All 47 tests passing

### Phase 9: Final Integration - DONE
- Added `scan` command: multi-ticker x multi-strategy scan, sends Telegram for actionable signals
- Added `watch` command: continuous monitoring loop with market hours awareness per instrument type
- Added `MARKET_HOURS` config: indices (14-21 UTC Mon-Fri), commodities (near 24h Mon-Fri), crypto (24/7)
- Added `_is_market_open()` helper: checks UTC time + day of week against instrument hours
- GPU: RTX 5060 detected via nvidia-smi but TF needs CUDA toolkit installed in WSL2

## Session Schedule

| Session | Phases | Description | Status |
|---------|--------|-------------|--------|
| 1 | 0 + 1 | Setup + Data fetching | DONE |
| 2 | 2 | Technical indicators | DONE |
| 3 | 3 | Trading strategies | DONE |
| 4 | 4 | Backtesting engine (VectorBT) | DONE |
| 5 | 5 | Signal generator | DONE |
| 6 | 6 | Hybrid ML model (TF 2.20) | DONE |
| 7 | 7 | Telegram bot | DONE |
| 8 | 8 + 9 | Tests + final integration | DONE |

---

## 🔴 CRITICAL: Documentation Reading Requirement

**This section is MANDATORY for every new Claude session:**

### What You MUST Do at Session Start:

1. **Read CLAUDE.md** (this file) - You're reading it now ✓

2. **Read docs/README.md** - Overview and navigation guide
   ```bash
   cat docs/README.md
   ```

3. **Read docs/guides/INTEGRATION_SUMMARY.md** - Full system architecture
   ```bash
   cat docs/guides/INTEGRATION_SUMMARY.md
   ```

4. **Read docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md** - Sentiment analysis improvements
   ```bash
   cat docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md
   ```

5. **Read docs/guides/NEWS_ANALYZER_SETUP.md** - News sentiment integration
   ```bash
   cat docs/guides/NEWS_ANALYZER_SETUP.md
   ```

### Why This Is Critical:

- ✅ You need to understand **current system state**
- ✅ You need to know about **recent improvements** (sentiment analysis V2, script manager)
- ✅ You need context on **41 pre-configured scripts** and **5 workflows**
- ✅ You need to know about **news sentiment integration**
- ✅ You need to understand **central script manager** (run_script.py)
- ✅ You need to avoid **suggesting already-implemented features**
- ✅ You need to provide **context-aware suggestions**

### What Happens If You Don't Read Docs:

❌ You won't know about sentiment analysis improvements (V2 prompt with +15-20% accuracy)
❌ You won't know about the centralized script manager (41 scripts, 8 categories)
❌ You won't understand the new project structure (/docs organization)
❌ You'll suggest features that already exist
❌ You'll miss important context about news sentiment integration
❌ Your suggestions will be less valuable

### Verification Checklist:

Before helping the user, confirm you have read:
- [x] CLAUDE.md (this file)
- [ ] docs/README.md
- [ ] docs/guides/INTEGRATION_SUMMARY.md
- [ ] docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md
- [ ] docs/guides/NEWS_ANALYZER_SETUP.md

**Do not proceed with tasks until ALL items are checked.**

---

## Documentation Quick Reference

| Document | Location | Purpose |
|----------|----------|---------|
| **Project Overview** | CLAUDE.md | Specifications, architecture, design decisions |
| **Documentation Index** | docs/README.md | Navigation guide, quick start by role |
| **System Architecture** | docs/guides/INTEGRATION_SUMMARY.md | Full integration, features, examples |
| **Sentiment Analysis** | docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md | Before/after comparison, improvements |
| **News Setup** | docs/guides/NEWS_ANALYZER_SETUP.md | API keys, setup, troubleshooting |
| **Prompt Analysis** | docs/prompts/PROMPT_OPTIMIZATION.md | Prompt engineering, 3 versions |

## Key Information to Know:

### Recent Improvements (Latest Session)
- ✅ Sentiment analysis V2: +15-20% accuracy improvement
- ✅ Centralized script manager: 41 scripts in 8 categories
- ✅ Project reorganization: /docs with guides/, prompts/, analysis/, tests/
- ✅ News sentiment integration: Google Gemini AI + NewsAPI
- ✅ Professional documentation structure

### Available Scripts (Quick Access)
```bash
python3 run_script.py list              # Show all categories
python3 run_script.py list signals      # Show signals scripts
python3 run_script.py data fetch-all    # Fetch all data
python3 run_script.py signals ensemble-expanded  # Generate signals
python3 run_script.py news test-gld     # Test news sentiment
python3 run_script.py test test-all     # Run all tests
```

### Script Categories
- **data** - Data fetching (4 scripts)
- **train** - ML model training (6 scripts)
- **signals** - Signal generation (7 scripts)
- **backtest** - Strategy backtesting (4 scripts)
- **news** - News sentiment testing (5 scripts)
- **test** - Unit tests (7 scripts)
- **docs** - Documentation access (3 scripts)
- **workflows** - Multi-step workflows (5 scripts)

---

## Agent Accountability

If an agent fails to read the documentation and misses important context, it is:
- ❌ Not following instructions
- ❌ Providing suboptimal suggestions
- ❌ Wasting the user's time

**Every new session MUST start with reading the /docs folder to maintain context continuity.**
