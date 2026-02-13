# CFD Trading System

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
backtesting/engine.py       # [PENDING] BacktestEngine: wrapper backtesting.py
backtesting/metrics.py      # [PENDING] PerformanceMetrics: sharpe, drawdown, win_rate
backtesting/report.py       # [PENDING] BacktestReport: HTML + plotly
signals/generator.py        # [PENDING] SignalGenerator: datos -> indicadores -> estrategia -> senal
signals/manager.py          # [PENDING] SignalManager: log CSV, historial, formato
signals/telegram_bot.py     # [PENDING] TelegramNotifier: alertas moviles
models/hybrid_model.py      # [PENDING] HybridLSTMTransformer: LSTM + Transformer encoder
models/trainer.py           # [PENDING] ModelTrainer: prepare, train, evaluate, save/load
models/predictor.py         # [PENDING] PricePredictor: filtro ML para senales
tests/                      # [PENDING] pytest con fixtures en conftest.py
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
| Backtesting | backtesting.py | Facil, suficiente para prototipado. En requirements |
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
| tensorflow>=2.15 | Phase 6: ML Model | Compatible con Python 3.12 |
| python-telegram-bot>=20.0 | Phase 7: Telegram | Verificar compatibilidad |
| backtesting.py | Phase 4: Backtesting | Verificar compatibilidad |

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
- **NEXT Phase 4**: Backtesting engine

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

### Phase 4: Backtesting Engine (`backtesting/`) - NEXT
Create: `backtesting/engine.py`, `backtesting/metrics.py`, `backtesting/report.py`
Modify: `backtesting/__init__.py`, `main.py` (backtest command)
Depends: Phase 3 + Phase 1

### Phase 5: Signal Generator (`signals/`)
Create: `signals/generator.py`, `signals/manager.py`
Modify: `signals/__init__.py`, `main.py` (signal command)
Depends: Phases 1+2+3

### Phase 6: Hybrid ML Model (`models/`)
**IMPORTANT**: Requiere Python 3.10-3.12 para TensorFlow. Migrar venv antes de esta fase.
Create: `models/hybrid_model.py` (LSTM 2x50 -> Transformer 2-head attention -> Dense -> sigmoid), `models/trainer.py`, `models/predictor.py`
Modify: `models/__init__.py`, `config/settings.py`, `main.py` (train-lstm command), `signals/generator.py` (--use-ml)
Depends: Phases 1+2+5

### Phase 7: Telegram Alerts (`signals/`)
Create: `signals/telegram_bot.py` (TelegramNotifier)
Modify: `config/settings.py`, `signals/generator.py`, `.env.example`
Depends: Phase 5

### Phase 8: Tests (`tests/`)
Create: `tests/conftest.py`, `tests/test_data.py`, `tests/test_indicators.py`, `tests/test_strategies.py`, `tests/test_backtesting.py`, `tests/test_signals.py`

### Phase 9: Final Integration
Add CLI commands: `scan` (multi-ticker/strategy), `report` (performance reports)
Full E2E verification

## Session Schedule

| Session | Phases | Description | Status |
|---------|--------|-------------|--------|
| 1 | 0 + 1 | Setup + Data fetching | DONE |
| 2 | 2 | Technical indicators | DONE |
| 3 | 3 | Trading strategies | DONE |
| 4 | 4 | Backtesting engine | NEXT |
| 5 | 5 | Signal generator | - |
| 6 | 6 | Hybrid ML model | - |
| 7 | 7 | Telegram bot | - |
| 8 | 8 + 9 | Tests + final integration | - |
