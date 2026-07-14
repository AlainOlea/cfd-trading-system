# CFD Trading System

## Session Start

Read this file, then `docs/README.md` for navigation. Full module API: `docs/reference/MODULES_API.md`.

## Project Overview
Sistema hibrido de trading tecnico para CFDs. Genera senales automaticas (analisis tecnico + ML) con ejecucion paper trading en Alpaca. Python 3.12.

## Setup Commands
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 main.py status              # verificar instalacion
python3 main.py list-strategies     # ver estrategias disponibles
python3 main.py fetch-1min-history  # fetch 3y data 1min (Alpaca API)
pytest tests/ -v                    # correr tests
```

## Environment
- **Python**: 3.12.3 (`/usr/bin/python3.12`)
- **venv**: `source venv/bin/activate`
- **pandas-ta**: 0.4.71b0, **yfinance**: 1.1.0, **ccxt**: 4.5.37
- **TensorFlow**: 2.21.0 (GPU-accelerated, RTX 5060 + CUDA 12.9/cuDNN 9.19), **XGBoost**: Primary ML model
- **VectorBT**: 0.28.4 (backtesting)
- **alpaca-py**: Data API (free tier: IEX feed, 200 calls/min, 15-min delay)

## Project Structure
```
config/settings.py          # Configuracion central (tickers, parametros, ML config)
config/ticker_types.py      # TickerConfig dataclass (sin deps de signals.pipeline, evita import circular)
main.py                     # CLI entry point (Click) - 16 comandos
data/fetcher.py             # DataFetcher: yfinance + CCXT + Alpaca incremental
data/processor.py           # DataProcessor: limpieza y validacion
data/alpaca_data.py         # AlpacaDataFetcher: Alpaca Data API wrapper (stocks + crypto)
data/rate_limiter.py        # RateLimiter: token bucket (200 calls/min)
data/metadata.py            # FetchMetadata: tracker de timestamps por ticker+interval
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
models/timesfm_predictor.py # TimesFMPredictor: zero-shot 1min forecast, validates XGBoost signal
scripts/                    # Utility scripts (training, comparison, backfill)
tests/                      # 147 tests (all passing)
```

## Key Features

### Unified Signal Pipeline
`python3 main.py pipeline` ejecuta todo: fetch fresh data -> indicators -> strategies -> ML filter -> TimesFM validation -> confluence scoring -> Telegram.
- Fresh data: Alpaca Data API (incremental, solo velas nuevas) con fallback a Yahoo Finance
- ML: XGBoost cross-sectional (19 tickers, 5y data), validado por TimesFM zero-shot (1min forecast)
- Confluence: Multi-timeframe scoring (0-5 stars)

### Paper Trading Automation
Windows Task Scheduler ejecuta `run_paper_hourly.ps1`/`run_paper_daily.ps1` (raíz del repo),
que invocan `wsl -d Ubuntu --exec bash -c "..."` para correr `main.py paper-trade` dentro de WSL:

| Task | Schedule | Orders |
|------|----------|--------|
| `CFD Paper Hourly` | Mon-Fri, 07:00-15:59 ET, 1h | DAY (SL 0.5%, TP 1%) |
| `CFD Paper Daily` | Mon-Fri, 07:00 ET, 1d | GTC (SL 1.5%, TP 3%) |

### Strategies
| Strategy | Type | Signal | SL | TP | Regime filter |
|----------|------|--------|----|----|----|
| MACD + VWAP | Scalping (momentum) | MACD cross + VWAP filter | 0.5% | 1% | `require_trend` (needs ADX >= 20) |
| RSI + BB | Scalping (mean reversion) | RSI oversold/overbought + BB touch | 0.7% | bb_middle | `require_ranging` (needs ADX < 20) |
| MA Crossover | Swing | SMA50/200 golden/death cross | 2% | 3% | none |

`mean_reversion=True` on `RSIBBStrategy` also tells `UnifiedPipeline._apply_timesfm()` to
leave its SL/TP alone — TimesFM's momentum-continuation forecast has no relation to a
reversion-to-bb_middle target and was previously overwriting it for every 1m/1h signal.

### Risk Management
- `MAX_POSITION_PCT=5%` per position is the size that actually binds for scalping strategies
  (tight 0.5-0.7% stops make the 2%-risk sizing formula moot — it always computes to more
  shares than the 5% capital cap allows). `RISK_PER_TRADE=2%` is nominal, not the real risk.
- `MAX_GROSS_EXPOSURE=50%` total (aligned with `MAX_CONCURRENT_POSITIONS=10` — 10 x 5% = 50%;
  it was 30%, which capped concurrency at 6 regardless of the 10-position setting)
- `MAX_CONCURRENT_POSITIONS=10`, `CRYPTO_MAX_AGGREGATE=10%`, `CRYPTO_MAX_SINGLE=3%`
- Min confluence: 3 stars (default), min confidence: 60% (`paper-trade` default)

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
| Data | Alpaca Data API (incremental) | Free tier, 200 calls/min, 7+ years history |
| Paper Trading | Windows Task Scheduler + WSL | Survives sleep/hibernate |

## Do's and Don'ts

### Do
- Usar parametros de `config/settings.py` para todo
- Implementar graceful degradation
- Validar DataFrames antes de procesar (columnas OHLCV completas)
- Risk management: max 5% per position (the binding cap), max 50% gross exposure, max 10 concurrent positions

### Don't
- NO hardcodear tickers, intervalos o parametros
- NO usar yfinance para produccion critica (se rompe frecuentemente)
- NO commitear .env, API keys, modelos entrenados, ni data/raw/*.csv
- NO usar `live_signals.py`, `live_signals_ensemble.py` - DEPRECATED (usar `pipeline`)
- NO renombrar ni mover `run_paper_hourly.ps1`, `run_paper_daily.ps1`, `setup_tasks.ps1` (raíz
  del repo) — están conectados a tareas reales de Windows Task Scheduler (`CFD Paper Hourly`,
  `CFD Paper Daily`); moverlos rompe la automatización sin ningún error visible en el repo
