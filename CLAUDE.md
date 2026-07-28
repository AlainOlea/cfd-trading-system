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
signals/store.py            # SignalStore: SQLite (logs/signals.db), desglose ML/TimesFM/estrellas por senal
signals/telegram_bot.py     # TelegramNotifier: senales via Telegram
signals/alpaca_broker.py    # AlpacaBroker: paper trading bracket orders
models/xgboost_model.py     # XGBoostTrader: primary ML model
models/timesfm_predictor.py # TimesFMPredictor: zero-shot 1min forecast, validates XGBoost signal
scripts/                    # Utility scripts (training, comparison, backfill)
scripts/replay_signals.py   # Replay: resuelve senales historicas vs datos 1min (TP o SL primero) — ver docs/guides/SIGNAL_REPLAY_GUIDE.md
scripts/validate_tfm_forecasts.py  # Valida forecasts TimesFM (tabla tfm_forecasts) vs velas 1min reales
tests/                      # 162 tests (all passing)
```

## Key Features

### Unified Signal Pipeline
`python3 main.py pipeline` ejecuta todo: fetch fresh data -> indicators -> strategies -> ML filter -> TimesFM validation -> confluence scoring -> Telegram.
- Fresh data: Alpaca Data API (incremental, solo velas nuevas) con fallback a Yahoo Finance
- ML: XGBoost cross-sectional (19 tickers, 5y data), validado por TimesFM zero-shot (1min forecast)
- Confluence: Multi-timeframe scoring (0-5 stars)

### Paper Trading Automation
Windows Task Scheduler ejecuta `powershell.exe -File "\\wsl.localhost\Ubuntu\...\run_paper_*.ps1"`
directo sobre los `.ps1` del repo (vía ruta UNC) — el repo es la única fuente de verdad; cualquier
cambio commiteado a un `run_paper_*.ps1` aplica en la siguiente corrida sin tocar nada en Windows.
Cada `.ps1` hace `wsl -d Ubuntu --exec bash -c "..."` para correr `main.py paper-trade` dentro de WSL:

| Task | Schedule | Orders |
|------|----------|--------|
| `CFD Paper Hourly` | Mon-Fri, 07:00-15:59 ET, cada 1h, `--interval 1h` | GTC (SL 0.5%, TP 1%) |
| `CFD Paper Daily` | Mon-Fri, 07:00 ET, `--interval 1d` | GTC (SL 1.5%, TP 3%) |
| `CFD Paper 1min` | Mon-Fri, 07:00-15:59 ET, cada 30min (:00/:30), `--interval 1m` | GTC (SL/TP scalping por estrategia) |

Nota histórica (corregida 2026-07-15): hasta esta fecha las tareas de Windows en realidad
ejecutaban `.bat` con el comando completo hardcodeado, fuera del repo — cualquier cambio a los
`.ps1` nunca se aplicaba en producción (así se coló silenciosamente `--min-confluence 2` en vez
de 3 durante días). Se reconfiguraron las 3 tareas para apuntar directo al `.ps1` vía UNC; los
`.bat` viejos quedan como respaldo temporal, ya no se usan.

Nota (corregida 2026-07-28): `CFD Paper Hourly`/`1min` usaban TIF `DAY` para el bracket
completo (entrada + SL + TP). Alpaca hace que las patas de SL/TP hereden el TIF de la orden
padre, así que si ninguna se tocaba antes del cierre del mercado, ambas expiraban/cancelaban
solas — la posición (ya llena) quedaba abierta sin ninguna protección, y `has_position()`
evita que corridas futuras la vuelvan a tocar. Confirmado en cuenta real: AAPL/AMZN/DIA/GLD/
GOOGL llevaban entre 13 y 40 días abiertas con 0 órdenes pendientes. Ahora todos los
intervalos usan GTC (`signals/alpaca_broker.py:place_signal`), igual que ya hacía 1d.

### Strategies
| Strategy | Type | Signal | SL | TP | Regime filter |
|----------|------|--------|----|----|----|
| MACD + VWAP | Scalping (momentum) | MACD cross + VWAP filter | 0.5% | 1% | `require_trend` (needs ADX >= 20) |
| RSI + BB | Scalping (mean reversion) | RSI oversold/overbought + BB touch | 0.7% | bb_middle | `require_ranging` (needs ADX < 20) |
| MA Crossover | Swing | SMA50/200 golden/death cross | 2% | 3% | none |
| SuperTrend | Scalping (momentum) | SuperTrend(10,3) flip | ST line | 2x SL dist | `require_trend` |
| Pivot Points | Scalping (mean reversion) | Rebote S1/S2, rechazo R1/R2 | next level | PP | `require_ranging` |
| Fibonacci | Swing | Pullback a 38.2/50/61.8% en tendencia (SMA50 + impulso low→high ordenado + RSI) | tras 78.6% | swing extreme | none (ADX suprime pullbacks) |

Estado de activacion (bateria con salidas bracket SL/TP, 2026-07-15; commodities 2026-07-28):
- SuperTrend: ACTIVA en MSFT, USO, y CORN/CPER/DBA (commodities, 1h Sharpe 1.4-2.6, 76-80
  trades; evidencia robusta). Negativa en cripto/AMZN/META.
- Pivot Points: en STRATEGY_MAP pero NO activa (negativa en 17/19 tickers con brackets reales)
- Fibonacci: en STRATEGY_MAP pero NO activa (mediocre tras corregir ADX/orden temporal)
Nuevas estrategias: usar la skill `/strategy-research` — exige backtest en TODOS los
tickers con salidas SL/TP (vbt sl_stop/tp_stop), nunca por senal opuesta.

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

## Tickers
**Pipeline activo (22)** — los que operan en paper trading (`PIPELINE_TICKERS`):
- **Stocks/ETFs**: SPY, QQQ, IWM, DIA, GLD, SLV, USO, UNG, AAPL, NVDA, MSFT, AMZN, GOOGL, META, TSLA
- **Commodities nuevas (2026-07-28)**: CORN, CPER, DBA (con edge; SuperTrend/MACD+VWAP en 1h)
- **Crypto**: BTC-USD, ETH-USD, SOL-USD, XRP-USD

**Con data pero NO en pipeline**: BNO, PPLT, WEAT — fetched y en `DEFAULT_TICKERS`/modelo XGBoost,
pero sin edge defendible en backtest (BNO/PPLT negativos, WEAT dudoso), así que no en `PIPELINE_TICKERS`.

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
- NO renombrar ni mover `run_paper_hourly.ps1`, `run_paper_daily.ps1`, `run_paper_1min.ps1`,
  `setup_tasks.ps1` (raíz del repo) — las tareas reales de Windows Task Scheduler (`CFD Paper
  Hourly`, `CFD Paper Daily`, `CFD Paper 1min`) las ejecutan directo por ruta UNC
  (`\\wsl.localhost\Ubuntu\...`); renombrar o mover el archivo rompe la automatización sin
  ningún error visible en el repo (la tarea de Windows fallaría silenciosamente al no encontrar
  el archivo en la ruta esperada)
- NO incluir firma de Claude (`Co-Authored-By`/`Claude-Session`) en los mensajes de commit
