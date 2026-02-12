# CFD Trading System

## Project Overview
Sistema hibrido de trading tecnico para CFDs. Genera senales automaticas (analisis tecnico + ML) con ejecucion manual en Plus500 y senales para crypto. Python 3.10+.

## Setup Commands
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py status          # verificar instalacion
python main.py list-strategies # ver estrategias disponibles
pytest tests/ -v               # correr tests
```

## Project Structure
```
config/settings.py          # Configuracion central (tickers, parametros, ML config)
main.py                     # CLI entry point (Click) - 7 comandos
data/fetcher.py             # DataFetcher: yfinance + CCXT/Bitso
data/processor.py           # DataProcessor: limpieza y validacion
indicators/technical.py     # TechnicalIndicators: 10+ indicadores via pandas-ta
strategies/base.py          # BaseStrategy: clase abstracta
strategies/scalping/        # MACDVWAPStrategy, RSIBBStrategy
strategies/swing/           # MACrossoverStrategy
backtesting/engine.py       # BacktestEngine: wrapper backtesting.py
backtesting/metrics.py      # PerformanceMetrics: sharpe, drawdown, win_rate
backtesting/report.py       # BacktestReport: HTML + plotly
signals/generator.py        # SignalGenerator: datos -> indicadores -> estrategia -> senal
signals/manager.py          # SignalManager: log CSV, historial, formato
signals/telegram_bot.py     # TelegramNotifier: alertas moviles
models/hybrid_model.py      # HybridLSTMTransformer: LSTM + Transformer encoder
models/trainer.py           # ModelTrainer: prepare, train, evaluate, save/load
models/predictor.py         # PricePredictor: filtro ML para senales
tests/                      # pytest con fixtures en conftest.py
```

## Code Style
- Python 3.10+ con type hints
- Clases con docstrings descriptivos
- Parametros configurables desde `config/settings.py`, nunca hardcoded
- Usar pandas-ta para indicadores, NO calculos manuales
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
| Indicators | pandas-ta | 130+ indicadores, bien mantenido, MIT license |
| Plus500 | Manual execution | Plus500 NO tiene API |

## Do's and Don'ts

### Do
- Usar parametros de `config/settings.py` para todo (MACD_PARAMS, RSI_PARAMS, etc.)
- Implementar graceful degradation (ej: Telegram no configurado -> solo terminal)
- Guardar datos en `data/raw/` (CSV) y modelos en `models/saved/`
- Validar DataFrames antes de procesar (columnas OHLCV completas)
- Usar `click.echo()` para output al usuario en CLI
- Risk management: max 2% por trade, max 3 posiciones concurrentes

### Don't
- NO hardcodear tickers, intervalos o parametros de estrategias
- NO usar TFLite - usar TensorFlow completo (se corre en laptop)
- NO automatizar ejecucion en Plus500 (no tiene API)
- NO hacer HFT/scalping en Bitso (no lo soporta)
- NO usar yfinance para produccion critica (se rompe frecuentemente)
- NO commitear .env, API keys, o modelos entrenados (.h5, .keras)

## Key Libraries
| Library | Use | Notes |
|---------|-----|-------|
| pandas-ta | Indicadores tecnicos | 130+ indicadores. Preferir sobre TA-Lib |
| backtesting (backtesting.py) | Motor de backtesting | Wrapper en backtesting/engine.py |
| yfinance | Datos stocks/indices/commodities | Datos OHLCV historicos |
| ccxt | Datos crypto (Bitso) | Solo datos, NO ejecucion |
| tensorflow>=2.15 | Modelo LSTM+Transformer | Keras API para el hibrido |
| python-telegram-bot>=20.0 | Alertas Telegram | Async, v22.6+ |
| plotly | Graficas backtesting | Equity curves en HTML reports |
| scikit-learn | Preprocessing ML | MinMaxScaler, train_test_split |

## Recommended Reference Repos
- `vercel-labs/agent-skills` - Patron AGENTS.md para contexto de agentes
- `0xemmkty/QuantMuse` - Pipeline completo: data->indicadores->portfolio->backtesting->AI
- `whchien/ai-trader` - Backtrader + CLI + 20 estrategias ejemplo
- `nkaz001/hftbacktest` - Backtesting tick-level para scalping
- `freqtrade/freqtrade` - Trading bot con integracion Telegram completa
- `dcajasn/Riskfolio-Lib` - Portfolio optimization y risk management
- `stefan-jansen/machine-learning-for-trading` - ML workflow para trading

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
- DONE: Directory structure, config/settings.py, main.py (CLI scaffold), README.md, requirements.txt
- PENDING: All business logic (16 new files, 12 files to modify)

### Phase 0: Dependencies Update
Modify: `requirements.txt` (tensorflow-lite -> tensorflow, add python-telegram-bot), `config/settings.py` (Transformer params)
Verify: `pip install -r requirements.txt`

### Phase 1: Data Module (`data/`)
Create: `data/fetcher.py` (DataFetcher), `data/processor.py` (DataProcessor)
Modify: `data/__init__.py`, `main.py:77-78` (connect fetch-data command)
Verify: `python main.py fetch-data --ticker SPY --interval 1d --days 30`

### Phase 2: Technical Indicators (`indicators/`)
Create: `indicators/technical.py` (TechnicalIndicators: macd, rsi, bb, vwap, sma, ema, stochastic, adx, atr, obv)
Modify: `indicators/__init__.py`
Depends: Phase 1

### Phase 3: Trading Strategies (`strategies/`)
Create: `strategies/base.py`, `strategies/scalping/macd_vwap.py`, `strategies/scalping/rsi_bb.py`, `strategies/swing/ma_crossover.py`
Modify: `strategies/__init__.py` (STRATEGY_MAP), `strategies/scalping/__init__.py`, `strategies/swing/__init__.py`
Depends: Phase 2

### Phase 4: Backtesting Engine (`backtesting/`)
Create: `backtesting/engine.py`, `backtesting/metrics.py`, `backtesting/report.py`
Modify: `backtesting/__init__.py`, `main.py:108-109`
Depends: Phase 3 + Phase 1

### Phase 5: Signal Generator (`signals/`)
Create: `signals/generator.py`, `signals/manager.py`
Modify: `signals/__init__.py`, `main.py:138-139`
Depends: Phases 1+2+3

### Phase 6: Hybrid ML Model (`models/`)
Create: `models/hybrid_model.py` (LSTM 2x50 -> Transformer 2-head attention -> Dense -> sigmoid), `models/trainer.py`, `models/predictor.py`
Modify: `models/__init__.py`, `config/settings.py`, `main.py:168-169`, `signals/generator.py` (--use-ml)
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
| 1 | 0 + 1 | Setup + Data fetching | NEXT |
| 2 | 2 | Technical indicators | - |
| 3 | 3 | Trading strategies | - |
| 4 | 4 | Backtesting engine | - |
| 5 | 5 | Signal generator | - |
| 6 | 6 | Hybrid ML model | - |
| 7 | 7 | Telegram bot | - |
| 8 | 8 + 9 | Tests + final integration | - |
