# CFD Trading System - Plan de Implementacion y Contexto

## Descripcion del Proyecto

Sistema hibrido de trading tecnico para CFDs. Genera senales automaticas basadas en analisis tecnico + ML, con ejecucion manual en Plus500 y senales para crypto.

**Uso hibrido:**
- **Plus500 (CFDs)**: Sistema genera senales -> usuario ejecuta manualmente (Plus500 NO tiene API)
- **Crypto**: Solo generacion de senales (Bitso no soporta HFT/scalping)
- **Bitso API**: Se usa SOLO para obtener datos de mercado crypto, NO para ejecucion automatica

## Decisiones de Arquitectura

| Decision | Eleccion | Razon |
|----------|----------|-------|
| ML Model | Hibrido LSTM+Transformer | Mejor accuracy (~95.9%) que LSTM puro. TensorFlow completo (se corre en laptop, no movil) |
| Backtesting | backtesting.py | Facil de usar, suficiente para prototipado. Ya en requirements |
| Alertas | Terminal + Telegram bot | Senales en consola + notificaciones moviles para ejecucion manual |
| Crypto | Solo senales | No automatizar ejecucion. Bitso no soporta scalping/HFT |
| Data sources | Yahoo Finance + CCXT/Bitso | yfinance para stocks/indices/commodities, CCXT para crypto data |

## Research: Mejores Practicas 2025-2026

### Indicadores para Scalping (Estado del Arte)
- **Tier 1 Core**: VWAP (precio ponderado por volumen), Volume Profile, Order Flow/Cumulative Delta
- **Tier 2 Confirmacion**: MACD (momentum), RSI+Stochastic (sobrecompra/sobreventa)
- **Tier 3 Refinamiento**: Bollinger Bands (volatilidad), MFI (momentum por volumen)
- **MACD settings para scalping rapido**: 5,13,8 o 8,17,9 (mas cortos que el estandar 12,26,9)
- **VWAP+MACD**: Price cierra a traves de VWAP + MACD histogram confirma = entrada de alta probabilidad

### ML para Prediccion de Precios
- **Hibrido LSTM+Transformer** supera a LSTM puro: ~95.9% vs 91.6% accuracy
- **GRU** supera a LSTM para crypto minute-level (menor RMSE, MAE, MAPE)
- **Features criticos**: volumen, indicadores tecnicos (RSI, MACD, BB, ATR), OHLCV
- **Feature engineering importa mas que la arquitectura del modelo**
- **Pitfalls**: No usar solo precio raw, usar early stopping, preprocessing critico

### Gestion de Riesgo
- **Regla 1-2%**: Maximo 1-2% del capital por trade (configurado al 2%)
- **Drawdown dinamico**: Reducir posicion al 5% abajo, pausar al 15% abajo
- **Risk-reward scalping**: Minimo 1:1.5, ideal 1:2 o 1:3
- **Max posiciones concurrentes**: 3 (ya configurado)
- **Correlacion**: Evitar multiples posiciones en instrumentos correlacionados

### Librerias Python (Ecosistema 2025)
- **backtesting.py**: Mejor para prototipado rapido, facil de usar
- **vectorbt**: 1000x mas rapido, mejor para optimizacion masiva (alternativa futura)
- **pandas-ta**: Mejor libreria para indicadores tecnicos en pandas
- **yfinance**: Confiable para datos historicos gratuitos
- **ccxt**: Acceso unificado a exchanges crypto (incluye Bitso)

### Plus500
- **NO tiene API** - solo ejecucion manual
- Workflow: Sistema genera senal -> Telegram notifica -> usuario ejecuta en Plus500
- Alternativas futuras con API: OANDA, Interactive Brokers, cTrader

### Bitso (Crypto Mexico/LATAM)
- API para datos y ordenes spot (NO futuros/derivados)
- **NO soporta HFT** - explicito en su documentacion
- Rate limiting habilitado - usar exponential backoff
- Mejor para swing trading (timeframes largos)
- Timeout recomendado: 30 segundos

---

## Plan de Implementacion (10 Fases)

### Estado Actual
- **Completado**: Estructura de directorios, config/settings.py, main.py (CLI scaffold), README.md, requirements.txt
- **Pendiente**: Toda la logica de negocio (16 archivos nuevos, 12 archivos a modificar)

### Fase 0: Ajustes al Scaffold y Dependencias
**Objetivo:** Actualizar requirements.txt y settings.py para nuevas decisiones.
**Archivos a modificar:**
- `requirements.txt` - Cambiar `tensorflow-lite==2.15.0` por `tensorflow>=2.15.0`, agregar `python-telegram-bot>=20.0`
- `config/settings.py` - Agregar config Transformer (n_heads, d_model), actualizar LSTM_CONFIG
**Verificacion:** `pip install -r requirements.txt` sin errores

### Fase 1: Modulo de Datos (`data/`)
**Objetivo:** Descargar y almacenar datos OHLCV desde Yahoo Finance y Bitso/CCXT.
**Archivos a crear:**
- `data/fetcher.py` - Clase `DataFetcher`:
  - `fetch_yfinance(ticker, interval, days)` -> DataFrame OHLCV
  - `fetch_ccxt(symbol, timeframe, limit)` -> DataFrame OHLCV
  - `save_to_csv(df, ticker, interval)` -> guarda en `data/raw/`
  - `load_from_csv(ticker, interval)` -> lee de `data/raw/`
- `data/processor.py` - Clase `DataProcessor`:
  - `clean_data(df)` -> elimina NaN, duplicados, normaliza columnas
  - `validate_data(df)` -> verifica integridad OHLCV
  - `save_processed(df, ticker)` -> guarda en `data/processed/`
**Modificar:** `data/__init__.py`, `main.py` (conectar comando fetch-data, linea 77-78)
**Verificacion:** `python main.py fetch-data --ticker SPY --interval 1d --days 30`

### Fase 2: Indicadores Tecnicos (`indicators/`)
**Objetivo:** Calcular todos los indicadores usando pandas-ta.
**Crear:** `indicators/technical.py` - Clase `TechnicalIndicators`:
  - `add_all_indicators(df)`, `add_macd()`, `add_rsi()`, `add_bollinger_bands()`, `add_vwap()`, `add_sma()`, `add_ema()`, `add_stochastic()`, `add_adx()`, `add_atr()`, `add_obv()`
  - Parametros default desde `config/settings.py`
**Modificar:** `indicators/__init__.py`
**Depende de:** Fase 1

### Fase 3: Estrategias de Trading (`strategies/`)
**Objetivo:** Implementar 3 estrategias con logica entrada/salida y risk management.
**Crear:**
- `strategies/base.py` - Clase abstracta `BaseStrategy`:
  - `generate_signals(df)` -> DataFrame con signal, entry_price, stop_loss, take_profit, confidence
  - `calculate_position_size(capital, risk_per_trade, stop_loss_pct)`
- `strategies/scalping/macd_vwap.py` - `MACDVWAPStrategy(BaseStrategy)`:
  - LONG: MACD cruza arriba signal + precio > VWAP | SHORT: inverso
  - Exit: cruce opuesto OR 1% profit | SL: 0.5%
- `strategies/scalping/rsi_bb.py` - `RSIBBStrategy(BaseStrategy)`:
  - LONG: RSI < 30 + toca lower BB | SHORT: RSI > 70 + toca upper BB
  - Exit: RSI cruza nivel opuesto OR BB opuesta | SL: 0.7%
- `strategies/swing/ma_crossover.py` - `MACrossoverStrategy(BaseStrategy)`:
  - LONG: Golden Cross (SMA50 > SMA200) | SHORT: Death Cross
  - SL: 2%
**Modificar:** `strategies/__init__.py` (+ STRATEGY_MAP dict), `strategies/scalping/__init__.py`, `strategies/swing/__init__.py`
**Depende de:** Fase 2

### Fase 4: Motor de Backtesting (`backtesting/`)
**Objetivo:** Evaluar estrategias con datos historicos usando backtesting.py.
**Crear:**
- `backtesting/engine.py` - `BacktestEngine`: wrapper sobre backtesting.py con comision/slippage
- `backtesting/metrics.py` - `PerformanceMetrics`: total_return, sharpe, sortino, max_drawdown, win_rate, profit_factor, etc.
- `backtesting/report.py` - `BacktestReport`: HTML con plotly equity curves + summary terminal
**Modificar:** `backtesting/__init__.py`, `main.py` (conectar comando backtest, linea 108-109)
**Depende de:** Fase 3 + Fase 1
**Verificacion:** `python main.py backtest --strategy macd_vwap --ticker SPY --interval 1d`

### Fase 5: Generador de Senales (`signals/`)
**Objetivo:** Generar senales de trading near-real-time.
**Crear:**
- `signals/generator.py` - `SignalGenerator`: descarga datos recientes, calcula indicadores, aplica estrategia
- `signals/manager.py` - `SignalManager`: log en CSV, historial, formato para terminal/telegram
**Modificar:** `signals/__init__.py`, `main.py` (conectar comando signal, linea 138-139)
**Depende de:** Fases 1+2+3
**Verificacion:** `python main.py signal --strategy macd_vwap --ticker SPY`

### Fase 6: Modelo ML Hibrido LSTM+Transformer (`models/`)
**Objetivo:** Prediccion de precios como filtro de senales tecnicas.
**Crear:**
- `models/hybrid_model.py` - `HybridLSTMTransformer`:
  - Arquitectura: LSTM (2x50 units) -> Transformer encoder (2 heads attention) -> Dense -> sigmoid
  - Output: probabilidad movimiento alcista/bajista
- `models/trainer.py` - `ModelTrainer`: prepare_data, train, evaluate, save/load
  - Early stopping, learning rate scheduling
- `models/predictor.py` - `PricePredictor`:
  - `predict_next(ticker, interval)` -> direction, confidence, price_target
  - `filter_signal(signal, prediction)` -> solo toma senales cuando ML confirma con confianza > threshold
**Modificar:** `models/__init__.py`, `config/settings.py` (transformer params), `main.py` (train-lstm, linea 168-169), `signals/generator.py` (--use-ml flag)
**Depende de:** Fases 1+2+5

### Fase 7: Alertas Telegram (`signals/`)
**Objetivo:** Notificaciones via Telegram bot.
**Crear:** `signals/telegram_bot.py` - `TelegramNotifier`:
  - `send_signal(signal)` -> formato markdown con ticker, direccion, precio, SL, TP, confianza
  - Graceful degradation si Telegram no configurado
**Modificar:** `config/settings.py`, `signals/generator.py`, `.env.example`
**Depende de:** Fase 5

### Fase 8: Tests (`tests/`)
**Crear:** `tests/conftest.py`, `tests/test_data.py`, `tests/test_indicators.py`, `tests/test_strategies.py`, `tests/test_backtesting.py`, `tests/test_signals.py`
**Verificacion:** `pytest tests/ -v`

### Fase 9: Integracion Final
**Objetivo:** Pulir CLI, agregar comando `scan` (multiples tickers/estrategias) y `report`.
**Verificacion end-to-end:**
```bash
python main.py fetch-data --ticker SPY --interval 1d --days 365
python main.py backtest --strategy macd_vwap --ticker SPY --interval 1d
python main.py train-lstm --ticker SPY --epochs 50
python main.py signal --strategy macd_vwap --ticker SPY --use-ml
```

---

## Resumen de Archivos

### 16 Archivos Nuevos:
| Archivo | Fase | Complejidad |
|---------|------|-------------|
| `data/fetcher.py` | 1 | Media |
| `data/processor.py` | 1 | Simple |
| `indicators/technical.py` | 2 | Media |
| `strategies/base.py` | 3 | Media |
| `strategies/scalping/macd_vwap.py` | 3 | Media |
| `strategies/scalping/rsi_bb.py` | 3 | Media |
| `strategies/swing/ma_crossover.py` | 3 | Simple |
| `backtesting/engine.py` | 4 | Compleja |
| `backtesting/metrics.py` | 4 | Media |
| `backtesting/report.py` | 4 | Media |
| `signals/generator.py` | 5 | Media |
| `signals/manager.py` | 5 | Simple |
| `models/hybrid_model.py` | 6 | Compleja |
| `models/trainer.py` | 6 | Compleja |
| `models/predictor.py` | 6 | Media |
| `signals/telegram_bot.py` | 7 | Simple |

### 12 Archivos a Modificar:
`requirements.txt`, `config/settings.py`, `main.py`, `data/__init__.py`, `indicators/__init__.py`, `strategies/__init__.py`, `strategies/scalping/__init__.py`, `strategies/swing/__init__.py`, `backtesting/__init__.py`, `signals/__init__.py`, `models/__init__.py`, `.env.example`

## Orden de Sesiones

| Sesion | Fases | Descripcion | Proxima accion |
|--------|-------|-------------|----------------|
| 1 | 0 + 1 | Setup + Data fetching | PENDIENTE |
| 2 | 2 | Indicadores tecnicos | - |
| 3 | 3 | Estrategias de trading | - |
| 4 | 4 | Motor de backtesting | - |
| 5 | 5 | Generador de senales | - |
| 6 | 6 | Modelo ML hibrido | - |
| 7 | 7 | Telegram bot | - |
| 8 | 8 + 9 | Tests + integracion final | - |
