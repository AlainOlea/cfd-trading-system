# CFD Trading System - Module API Reference

Detailed API documentation for all modules.

---

## data/fetcher.py - DataFetcher

- `fetch_yfinance(ticker, interval, days)` -> DataFrame OHLCV. Tested: SPY 1d, BTC-USD 1h
- `fetch_ccxt(symbol, timeframe, limit)` -> DataFrame OHLCV via CCXT. Lazy-loads exchange connection
- `save_to_csv(df, ticker, interval)` -> guarda en `data/raw/{TICKER}_{interval}.csv`. Escritura atomica
  (tmp file + os.replace, via `_atomic_write_csv()`) — un write interrumpido a mitad de camino deja el
  archivo anterior intacto en vez de corromper el CSV
- `load_from_csv(ticker, interval)` -> carga desde `data/raw/`
- `_normalize_columns(df)` -> flatten MultiIndex de yfinance, lowercase, valida OHLCV
- `fetch_incremental(ticker, interval)` -> incremental fetch via Alpaca Data API, fallback yfinance
- `fetch_incremental_batch(tickers, interval)` -> batch incremental para multiples tickers
- `fetch_1min_history(tickers, years, chunk_days)` -> fetch historico 1min por chunks (max 7y stocks, 5y crypto)
- `_merge_dataframes(existing, new)` -> merge dos DataFrames, dedup por index, sort

## data/alpaca_data.py - AlpacaDataFetcher

- Wrapper de Alpaca Data API con rate limiting y paginacion
- `fetch_bars(symbols, interval, start, end)` -> dict[ticker, DataFrame]. Auto-rutea stocks vs crypto
- `fetch_batch_ranges(symbols, interval, total_days, chunk_days)` -> fetch historico por chunks
- Soporta: 1m, 5m, 15m, 30m, 1h, 1d
- Free tier: feed IEX (no SIP), 15-min delay en REST API, 200 calls/min
- Crypto: convierte `BTC-USD` -> `BTC/USD` para Alpaca
- `ALPACA_DATA_AVAILABLE` flag: True si alpaca-py esta instalado

## data/rate_limiter.py - RateLimiter

- Token bucket rate limiter, thread-safe
- `__init__(calls_per_minute)` -> inicializa tokens y rate
- `acquire(tokens=1)` -> bloquea si no hay tokens suficientes
- Usado por AlpacaDataFetcher para respetar limites del free tier

## data/metadata.py - FetchMetadata

- Tracker de timestamps de ultimo fetch por ticker+interval
- Persiste en `data/raw/fetch_metadata.json`
- `get_last_fetch(ticker, interval)` -> datetime|None
- `set_last_fetch(ticker, interval, timestamp, rows)` -> guarda timestamp
- Escritura atomica (tmp + rename) para evitar corrupcion
- Schema: `{ticker: {interval: {last_fetch, rows}}}`

## data/processor.py - DataProcessor

- `clean_data(df)` -> deduplica index, sort, ffill gaps (limit=3), drop NaN, clip volume >= 0
- `validate_data(df)` -> verifica: columnas OHLCV, no vacio, DatetimeIndex, no NaN, high >= low
- `save_processed(df, ticker, interval)` -> guarda en `data/processed/`

## indicators/technical.py - TechnicalIndicators

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

## strategies/ - Trading Strategies

- `strategies/base.py` - BaseStrategy ABC: generate_signals(), calculate_position_size(), _init_signal_columns()
  - Class flags subclasses can set: `require_trend` (only signal when ADX confirms a trend, e.g.
    macd_vwap), `require_ranging` (only signal when ADX does NOT confirm a trend — mean reversion
    needs room to revert, e.g. rsi_bb), `use_atr_sl` (ATR-based SL/TP instead of fixed %),
    `mean_reversion` (tells `UnifiedPipeline._apply_timesfm()` to leave this strategy's own SL/TP
    alone instead of overwriting it with TimesFM's momentum-continuation forecast)
- `strategies/scalping/macd_vwap.py` - MACDVWAPStrategy: MACD cross + VWAP filter. SL 0.5%, TP 1%.
  `require_trend=True`
- `strategies/scalping/rsi_bb.py` - RSIBBStrategy: RSI oversold/overbought + BB touch. SL 0.7%,
  TP=bb_middle. `require_ranging=True`, `mean_reversion=True`
- `strategies/swing/ma_crossover.py` - MACrossoverStrategy: SMA50/200 golden/death cross. SL 2%, TP 3%
- `strategies/__init__.py` - STRATEGY_MAP = {'macd_vwap': ..., 'rsi_bb': ..., 'ma_crossover': ...}
- Signal columns added: signal (BUY/SELL/HOLD), entry_price, stop_loss, take_profit, confidence (0-1)

## backtesting/engine.py - BacktestEngine

- `BacktestResult` dataclass: strategy_name, ticker, interval, portfolio (vbt.Portfolio), signals_df, initial_capital
- `BacktestEngine(initial_capital, commission, slippage)` uses config/settings.py defaults
- `run(strategy, df, ticker, interval)` -> BacktestResult. Uses VectorBT Portfolio.from_signals()
- `_interval_to_freq(interval)` -> pandas frequency string for VectorBT

## backtesting/metrics.py - PerformanceMetrics

- `calculate_all(result)` -> dict with 17 metrics: return, trades, win_rate, sharpe, sortino, drawdown, profit_factor, expectancy, best/worst/avg trades, consecutive wins/losses, avg duration
- `format_summary(metrics)` -> formatted terminal string
- `_safe_float(value, default)` -> handles NaN/inf from VectorBT stats
- `_max_consecutive(mask)` -> counts max consecutive True in boolean series

## backtesting/report.py - BacktestReport

- `generate_html(result, metrics)` -> HTML file path
- 3-row plotly subplot: equity curve (blue), price + BUY/SELL markers (green/red triangles), drawdown % (red fill)
- Title includes strategy, ticker, interval, return, win rate, trade count
- Uses plotly_dark template, saves to results/ directory

## signals/pipeline.py - Unified Signal Pipeline

- `UnifiedPipeline` class: Consolidates all signal flows (technical + ML + TimesFM + news)
- `TickerConfig` dataclass: Per-ticker configuration (strategies, intervals, layers)
- `PipelineResult` dataclass: Complete output with all analysis layers
- `run_all(category, ticker_filter)` -> List[PipelineResult]. Parallel processing with ThreadPoolExecutor
- `run_ticker(config)` -> List[PipelineResult]. One per interval, shared data cache
- `_fetch_data(ticker, interval)` -> **Alpaca Data API incremental** (fallback Yahoo Finance)
- `_apply_ml()`, `_apply_news()` -> Graceful degradation layers. `_apply_ml()` uses XGBoost
  (cross-sectional `all_tickers` model first, per-ticker fallback) per `PRIMARY_ML_MODEL`
- `_run_timesfm_batch()` / `_apply_timesfm()` -> TimesFM zero-shot validation, post-processing over
  1m/1h results only. Adds a confluence bonus on direction agreement and overwrites SL/TP with
  quantile-based levels — **except** for strategies with `mean_reversion=True` (e.g. rsi_bb), whose
  own SL/TP is left untouched since TimesFM's forecast has no relation to a reversion target
- `_compute_final_signal()` -> combines technical + ML (XGBoost) votes; ML can veto with a strong
  disagreement (>65% confidence). No longer includes an LSTM ensemble vote (see
  `models/ensemble_predictor.py` below — disconnected from the pipeline)
- `_compute_confluence()` -> Multi-timeframe confluence scoring (0-4 stars; TimesFM can add a 5th)
- Features: Fresh data, no duplicates, parallel processing, configurable per-ticker

## signals/generator.py - SignalGenerator

- `Signal` dataclass: direction, entry_price, stop_loss, take_profit, confidence, risk_reward_ratio, ensemble_consensus, news_sentiment, confluence_score
- `SignalGenerator.generate(strategy_name, ticker, interval, days, use_ml)` -> Signal. Full pipeline: fetch -> clean -> indicators -> strategy -> latest signal
- `SignalGenerator.get_latest_actionable(strategy_name, ticker, interval, lookback)` -> Signal|None. Searches last N bars for BUY/SELL
- `_apply_ml_filter(signal, df)` -> graceful degradation if ML model not available
- `_estimate_days(interval)` -> auto-calculates days for sufficient indicator warmup (1m=7d, 5m=30d, 1h=90d, 1d=365d)
- **Note**: Prefer `UnifiedPipeline` over `generate()` for new code (deprecated in favor of pipeline)

## signals/manager.py - SignalManager

- `log_signal(signal)` -> appends to logs/signals.csv (DictWriter, 12 columns)
- `get_history(ticker, n)` -> DataFrame with last N signals (optional ticker filter)
- `format_signal(signal)` -> formatted terminal block with entry/SL/TP/RR/confidence
- `format_history(df)` -> tabular display of signal history

## signals/telegram_bot.py - TelegramNotifier

- `send_signal(signal)` -> sends Markdown-formatted signal to Telegram chat. Only if enabled + configured
- `send_alert(message)` -> sends generic alert message
- `_format_signal_message(signal)` -> Markdown with emoji, entry/SL/TP/RR/confidence, ML info
- `is_configured` property: checks BOT_TOKEN and CHAT_ID are set
- Graceful degradation: returns False silently if not configured

## signals/alpaca_broker.py - AlpacaBroker

- `place_signal(signal, interval)` -> executes bracket orders on Alpaca paper sandbox
- `get_open_positions()` -> dict of current positions with P&L
- `has_position(symbol)` -> checks if holding a position
- `_normalize_symbol(symbol)` -> strips `/` and `-` for cross-format comparison. Alpaca returns
  crypto symbols inconsistently across endpoints (`SOL/USD` on orders, `SOLUSD` on positions; our
  internal ticker is `SOL-USD`) — every symbol comparison in this module goes through this first
- `calculate_shares(entry, stop_loss)` -> position sizing (2% risk, 5% max per position)
- `get_trade_history(days)` -> closed trades with P&L calculation
- `get_performance(days)` -> win rate, profit factor, avg win/loss
- Stocks: bracket orders with SL/TP. Crypto: notional market orders (no SL/TP — Alpaca limitation)
- Swing trades (1d): GTC orders, 2x wider SL/TP via `_widen_sl_tp_for_swing()`

## models/hybrid_model.py - HybridLSTMTransformer (DEPRECATED)

- `TransformerEncoderBlock` custom Keras layer: MultiHeadAttention + FFN + LayerNorm + residuals
- `HybridLSTMTransformer.build(input_shape)` -> compiled Keras model
- Architecture: Input -> LSTM(50) -> Dropout -> LSTM(50) -> Dropout -> Dense(d_model) -> TransformerEncoder -> GlobalAvgPool -> Dense(25) -> Dropout -> sigmoid
- `predict(X)` -> bullish probability (0-1). Input shape: (1, lookback_window, n_features)

## models/trainer.py - ModelTrainer

- `prepare_data(df)` -> (X_train, y_train, X_test, y_test). Sliding windows of lookback_window. Labels: 1 if next close > current close. MinMaxScaler normalization. Chronological split (no shuffle)
- `train(model, X_train, y_train)` -> history dict. EarlyStopping(patience=10) + ReduceLROnPlateau
- `evaluate(model, X_test, y_test)` -> {loss, accuracy, precision, recall}
- `save_model(model, ticker, interval)` -> saves weights.h5 + scaler.pkl + metadata.json to models/saved/{ticker}_{interval}/
- `load_model(ticker, interval)` -> (model, scaler, metadata) tuple. Rebuilds architecture from metadata

## models/predictor.py - PricePredictor

- `load(ticker, interval)` -> loads model+scaler+metadata from disk
- `predict_next(df)` -> {direction: BUY/SELL, confidence: 0-1, probability: raw sigmoid}
- `filter_signal(signal_direction, prediction)` -> {accepted: bool, reason: str}. Rejects if ML disagrees or confidence < threshold

## models/xgboost_model.py - XGBoostTrader (Primary ML)

- Primary ML model. Tree-based, regularized, outperforms LSTM on small datasets
- `prepare_data(df)` -> single-ticker train/test split with triple-barrier labels
- `prepare_cross_sectional(ticker_dfs)` -> pools data from multiple tickers (Alzaman 2024, Byun 2024)
- `train(X_train, y_train)` -> fits XGBClassifier with class weight balancing
- `evaluate(X_test, y_test)` -> {accuracy, precision, recall}
- `save(ticker, interval)` -> saves model.json + scaler.pkl + metadata.json to models/saved/{ticker}_{interval}_xgb/
- `XGBoostPredictor` wrapper: `load()`, `predict_next(df)`, `filter_signal(direction, prediction)`
- Cross-sectional model saved as `all_tickers_{interval}_xgb/`

## models/ensemble_predictor.py - EnsemblePredictor

- **Standalone — not wired into `UnifiedPipeline`.** The pipeline's ML layer (`_apply_ml()`) uses
  XGBoost alone, validated by TimesFM (see `signals/pipeline.py` above); this class still works if
  called directly, but no longer participates in live signal generation
- Combines LSTM + XGBoost predictions via voting mechanism
- `load(ticker, interval, models=['lstm', 'xgb'])` -> loads both models
- `predict_next(df)` -> {lstm: prediction, xgb: prediction, ensemble: consensus}
- `_ensemble_vote(lstm_pred, xgb_pred)` -> STRONG (both agree) or WEAK (disagree)
- `filter_signal(signal_direction, df)` -> accepts only when ensemble agrees strongly
- Graceful degradation: works with single model if one fails to load
