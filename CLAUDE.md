# CFD Trading System

## Session Start

Read this file, then `docs/README.md` for navigation. Full module API: `docs/reference/MODULES_API.md`.

## Project Overview
Sistema hibrido de trading tecnico para CFDs. Genera senales automaticas (analisis tecnico + ML) con ejecucion paper trading en Alpaca. Python 3.12.

## Setup Commands
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 main.py status          # verificar instalacion
python3 main.py list-strategies # ver estrategias disponibles
pytest tests/ -v                # correr tests
```

## Environment
- **Python**: 3.12.3 (`/usr/bin/python3.12`)
- **venv**: `source venv/bin/activate`
- **pandas-ta**: 0.4.71b0, **yfinance**: 1.1.0, **ccxt**: 4.5.37
- **TensorFlow**: 2.20.0 (CPU mode), **XGBoost**: Primary ML model
- **VectorBT**: 0.28.4 (backtesting)

## Project Structure
```
config/settings.py          # Configuracion central (tickers, parametros, ML config)
main.py                     # CLI entry point (Click) - 9 comandos
data/fetcher.py             # DataFetcher: yfinance + CCXT
data/processor.py           # DataProcessor: limpieza y validacion
indicators/technical.py     # TechnicalIndicators: 12 indicadores via pandas-ta
strategies/base.py          # BaseStrategy: clase abstracta + position sizing
strategies/scalping/        # MACDVWAPStrategy, RSIBBStrategy
strategies/swing/           # MACrossoverStrategy
backtesting/engine.py       # BacktestEngine: VectorBT Portfolio.from_signals()
backtesting/metrics.py      # PerformanceMetrics: 17 metrics
backtesting/report.py       # BacktestReport: HTML + plotly
signals/pipeline.py         # UnifiedPipeline: consolidacion de flujos
signals/generator.py        # SignalGenerator + Signal dataclass
signals/manager.py          # SignalManager: log CSV, historial
signals/telegram_bot.py     # TelegramNotifier: senales via Telegram
signals/alpaca_broker.py    # AlpacaBroker: paper trading bracket orders
models/xgboost_model.py     # XGBoostTrader: primary ML model
models/ensemble_predictor.py # EnsemblePredictor: LSTM + XGBoost voting
tests/                      # 47 tests (all passing)
```

## Key Features

### Unified Signal Pipeline
`python3 main.py pipeline` ejecuta todo: fetch fresh data -> indicators -> strategies -> ML filter -> ensemble -> confluence scoring -> Telegram.
- Fresh data: Siempre fetch de Yahoo Finance (nunca CSV stale)
- ML: XGBoost cross-sectional (19 tickers, 5y data) + LSTM ensemble
- Confluence: Multi-timeframe scoring (0-5 stars)

### Paper Trading Automation
Windows Task Scheduler ejecuta `.bat` que invocan `wsl.exe`:

| Task | Schedule | Orders |
|------|----------|--------|
| `CFD Paper Hourly` | Mon-Fri, 07:00-15:59 ET, 1h | DAY (SL 0.5%, TP 1%) |
| `CFD Paper Daily` | Mon-Fri, 07:00 ET, 1d | GTC (SL 1.5%, TP 3%) |

### Strategies
| Strategy | Type | Signal | SL | TP |
|----------|------|--------|----|----|
| MACD + VWAP | Scalping | MACD cross + VWAP filter | 0.5% | 1% |
| RSI + BB | Scalping | RSI oversold/overbought + BB touch | 0.7% | bb_middle |
| MA Crossover | Swing | SMA50/200 golden/death cross | 2% | 3% |

### Risk Management
- Max 2% risk per trade, 5% max position size
- Max 3 concurrent positions
- Min confluence: 3 stars, ML confidence: 65%

## Tickers (19)
**Stocks/ETFs**: SPY, QQQ, IWM, DIA, GLD, SLV, USO, UNG, AAPL, NVDA, MSFT, AMZN, GOOGL, META, TSLA
**Crypto**: BTC-USD, ETH-USD, SOL-USD, XRP-USD

## Code Style
- Python 3.12+ con type hints, clases con docstrings
- Parametros en `config/settings.py`, nunca hardcoded
- Logging via `logging`, secrets en `.env`
- Graceful degradation (ej: Telegram no configurado -> solo terminal)

## Architecture Decisions
| Decision | Choice | Reason |
|----------|--------|--------|
| Signal Pipeline | UnifiedPipeline | Single source of truth, fresh data |
| ML Model | XGBoost (primary) | Better than LSTM on tabular data |
| Backtesting | VectorBT | 1000x faster, ideal para scalping |
| Alertas | Terminal + Telegram | Senales consola + notificaciones moviles |
| Data | Always fresh from Yahoo | Never use stale CSV cache |
| Paper Trading | Windows Task Scheduler + WSL | Survives sleep/hibernate |

## Do's and Don'ts

### Do
- Usar parametros de `config/settings.py` para todo
- Implementar graceful degradation
- Validar DataFrames antes de procesar (columnas OHLCV completas)
- Risk management: max 2% por trade, max 3 posiciones concurrentes

### Don't
- NO hardcodear tickers, intervalos o parametros
- NO usar yfinance para produccion critica (se rompe frecuentemente)
- NO commitear .env, API keys, modelos entrenados, ni data/raw/*.csv
- NO usar `live_signals.py`, `live_signals_ensemble.py` - DEPRECATED (usar `pipeline`)
- NO renombrar `run_cfd_hourly.bat`, `run_cfd_daily.bat` (rompe automation)
