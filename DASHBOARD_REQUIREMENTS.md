# CFD Trading System - Dashboard Requirements & Architecture

**Fecha**: 2026-03-13
**Versión**: 1.0 - Especificación Inicial
**Estado**: 📋 En Definición de Requisitos

---

## 📊 ESTADO ACTUAL DEL SISTEMA

### 🏗️ Arquitectura Actual

```
┌─────────────────────────────────────────────────────────────┐
│                     CFD TRADING SYSTEM                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │  DATA LAYER  │   │   ML LAYER   │   │ SIGNAL LAYER │   │
│  ├──────────────┤   ├──────────────┤   ├──────────────┤   │
│  │ • Fetcher    │   │ • Hybrid     │   │ • Pipeline   │   │
│  │ • Processor  │   │ • XGBoost    │   │ • Generator  │   │
│  │ • Validator  │   │ • Ensemble   │   │ • Manager    │   │
│  │              │   │ • Trainer    │   │ • Telegram   │   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
│         │                   │                   │          │
│         └───────────────────┴───────────────────┘          │
│                       ↓                                    │
│  ┌──────────────────────────────────────────────────────┐ │
│  │    BACKTESTING ENGINE (VectorBT)                   │ │
│  │    • Performance Metrics                           │ │
│  │    • HTML Reports + Plotly Charts                 │ │
│  └──────────────────────────────────────────────────────┘ │
│                       ↓                                    │
│  ┌──────────────────────────────────────────────────────┐ │
│  │    TRADING STRATEGIES (3 tipos)                    │ │
│  │    • MACD + VWAP (scalping)                        │ │
│  │    • RSI + Bollinger Bands (mean reversion)        │ │
│  │    • MA Crossover (trending)                       │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 DATASETS DISPONIBLES

### Raw Data (CSV)
```
data/raw/
├── AAPL_1d.csv         ✅ Apple - Daily
├── AAPL_1h.csv         ✅ Apple - Hourly
├── BTC_USD_1d.csv      ✅ Bitcoin - Daily
├── BTC_USD_1h.csv      ✅ Bitcoin - Hourly
├── ETH_USD_1d.csv      ✅ Ethereum - Daily
├── ETH_USD_1h.csv      ✅ Ethereum - Hourly
├── GDX_1h.csv          ✅ Miners ETF - Hourly
├── GLD_1d.csv          ✅ Gold - Daily
├── GLD_1h.csv          ✅ Gold - Hourly
├── GLD_15m.csv         ✅ Gold - 15min
├── IWM_1d.csv          ✅ Russell 2000 - Daily
├── IWM_1h.csv          ✅ Russell 2000 - Hourly
├── MSFT_1d.csv         ✅ Microsoft - Daily
├── MSFT_1h.csv         ✅ Microsoft - Hourly
├── NVDA_1d.csv         ✅ NVIDIA - Daily
├── NVDA_1h.csv         ✅ NVIDIA - Hourly
├── QQQ_1d.csv          ✅ Nasdaq 100 - Daily
├── QQQ_1h.csv          ✅ Nasdaq 100 - Hourly
├── SOL_USD_1d.csv      ✅ Solana - Daily
└── [+SPY, +others]
```

**Estructura OHLCV**:
```
Index: Datetime
Columns: Open, High, Low, Close, Volume
```

### Processed Data
```
data/processed/
├── AAPL_1d_processed.csv
├── BTC_USD_1d_processed.csv
├── ETH_USD_1d_processed.csv
├── GLD_1d_processed.csv
├── NVDA_1d_processed.csv
├── QQQ_1d_processed.csv
└── SPY_1d_processed.csv

⚡ NOTA: Incluyen 26 columnas (5 OHLCV + 21 indicadores técnicos)
```

**Indicadores Incluidos**:
- MACD, MACD Signal, MACD Histogram
- RSI
- Bollinger Bands (upper, middle, lower, bandwidth, percent)
- SMA (50, 200)
- EMA (50, 200)
- VWAP
- Stochastic (K, D)
- ADX, Plus DI, Minus DI
- ATR
- OBV

---

## 🤖 MODELOS DISPONIBLES

### Estructura de Modelos Guardados
```
models/saved/
├── BTC_USD_1d/
│   ├── model.keras          (LSTM+Transformer)
│   ├── metadata.json        (accuracy, params, training_data)
│   └── scaler.pkl          (MinMaxScaler para features)
│
├── AAPL_1h_xgb/
│   ├── model.json          (XGBoost)
│   ├── metadata.json       (feature importance, accuracy)
│   └── scaler.pkl
│
├── MSFT_1h_xgb/
├── GDX_1h_xgb/
├── GLD_1h_xgb/
├── QQQ_1d_xgb/
├── SPY_1h_xgb/
└── [+10 más]
```

### Tipos de Modelos
1. **LSTM + Transformer** (Hybrid)
   - Arquitectura: LSTM 2x50 → Transformer 2-head → Dense → sigmoid
   - Casos: BTC_USD_1d
   - Accuracy: 44%+

2. **XGBoost**
   - Más modelos disponibles
   - Mejor para CFDs con features técnicas
   - Casos: SPY_1h, MSFT_1h, GDX_1h, GLD_1h, QQQ_1d

3. **Ensemble Predictor**
   - Combina múltiples modelos
   - Implementado en `models/ensemble_predictor.py`

### Metadata por Modelo
```json
{
  "ticker": "SPY",
  "interval": "1h",
  "model_type": "xgboost",
  "accuracy": 0.55,
  "training_samples": 1000,
  "training_period": "2024-01-01 to 2026-02-15",
  "features_count": 21,
  "created_at": "2026-02-15T16:55:00Z",
  "last_updated": "2026-02-15T16:55:00Z"
}
```

---

## 🔄 PIPELINE ACTUAL

### Signal Generation Pipeline (UnifiedPipeline)
```
┌─────────────────────────────────────────┐
│  Fetch Fresh Data (Yahoo Finance)       │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  Calculate Technical Indicators (26)     │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  Apply Trading Strategies (3)            │
│  • MACD+VWAP, RSI+BB, MA Crossover      │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  ML Filter (si disponible)               │
│  • LSTM, XGBoost, Ensemble              │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  Apply News Sentiment (si disponible)    │
│  • NewsAPI + Google AI                   │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  Multi-Timeframe Confluence (0-5 stars)  │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  Output Signal                           │
│  {direction, price, SL, TP, confidence} │
└─────────────────────────────────────────┘
```

### Características del Pipeline
- ✅ Fresh data (no cache stale)
- ✅ Graceful degradation (ML/News optional)
- ✅ Parallel processing (ThreadPoolExecutor)
- ✅ Multi-timeframe analysis
- ✅ Configuración por ticker

---

## 📊 REQUISITOS INICIALES DEL DASHBOARD

### 1️⃣ **Gestión de Modelos** 📌

**Como usuario quiero:**
- ✅ Ver tabla de modelos actuales
- ✅ Filtrar por:
  - Instrumento/Ticker (SPY, BTC-USD, AAPL, etc)
  - Período de entrenamiento (1d, 1h, 15m)
  - Accuracy (rango 40%-100%)
  - Tipo de modelo (LSTM, XGBoost, Ensemble)
  - Fecha de creación
  - Estado (active, archived, deprecated)

**Columnas Sugeridas**:
```
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ Ticker   │ Interval │ Type     │ Accuracy │ Samples  │ Created  │ Actions  │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ SPY      │ 1h       │ XGBoost  │ 55%      │ 1000     │ 2026-02  │ [Re]train│
│ BTC-USD  │ 1d       │ LSTM     │ 44%      │ 500      │ 2026-02  │ View     │
│ MSFT     │ 1h       │ XGBoost  │ 52%      │ 800      │ 2026-02  │ Archive  │
│ GLD      │ 1h       │ XGBoost  │ 48%      │ 600      │ 2026-02  │ Delete   │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

**Acciones**:
- Ver detalles del modelo
- Reentrenar modelo
- Cambiar estado (active/archived)
- Eliminar modelo
- Comparar múltiples modelos

---

### 2️⃣ **Visualización de Datos** 📈

**Como usuario quiero:**
- ✅ Ver gráficas de los datasets guardados
- ✅ Tipos de gráficas:
  - Candlestick OHLC
  - Precio + Indicadores técnicos
  - Performance histórico
  - Predicciones vs Actual

**Interactividad**:
- Zoom/Pan
- Seleccionar período de tiempo
- Superponer indicadores
- Exportar gráficas (PNG)

---

### 3️⃣ **Gestión de Datasets** 💾

**Como usuario quiero:**
- ✅ Ver tabla de datasets disponibles
- ✅ Filtrar por:
  - Fuente (Yahoo Finance, CCXT, etc)
  - Período de datos (rango de fechas)
  - Período de muestreo (1m, 1h, 1d)
  - Instrumento (ticker)
  - Tamaño (# de filas)
  - Estado (raw, processed, training)

**Columnas Sugeridas**:
```
┌──────────┬──────────┬──────────┬────────────┬──────────┬──────────┐
│ Ticker   │ Interval │ Source   │ Date Range │ Rows     │ Status   │
├──────────┼──────────┼──────────┼────────────┼──────────┼──────────┤
│ SPY      │ 1d       │ Yahoo    │ 365 días   │ 251      │ Raw      │
│ BTC-USD  │ 1h       │ Yahoo    │ 30 días    │ 720      │ Process. │
│ GLD      │ 15m      │ Yahoo    │ 7 días     │ 448      │ Raw      │
└──────────┴──────────┴──────────┴────────────┴──────────┴──────────┘
```

**Acciones**:
- Descargar data CSV
- Procesar dataset (raw → processed)
- Eliminar dataset
- Re-fetch data
- Obtener estadísticas (min, max, avg, volatility)

---

## 🎯 PRÓXIMAS HISTORIAS DE USUARIO

### Historia 2: Entrenamiento de Modelos
```
Como usuario quiero poder entrenar nuevos modelos desde el dashboard:
- Seleccionar dataset + instrumento
- Elegir tipo de modelo (LSTM, XGBoost, Ensemble)
- Configurar hiperparámetros
- Ver progreso de entrenamiento
- Comparar resultados vs modelos anteriores
```

### Historia 3: Backtesting Visual
```
Como usuario quiero backtestear estrategias visualmente:
- Seleccionar estrategia + dataset
- Configurar parámetros
- Ver equity curve, drawdown, trades
- Exportar reporte HTML
```

### Historia 4: Trading Signals Real-time
```
Como usuario quiero ver signals en tiempo real:
- Panel de signals actuales
- Histórico de signals
- Performance de cada signal
- Integración con Telegram alerts
```

---

## 🏛️ TECH STACK ACTUAL

### Backend (Existente)
- Python 3.12
- pandas, numpy (data)
- pandas-ta (technical indicators)
- TensorFlow/Keras (LSTM)
- XGBoost (tree models)
- VectorBT (backtesting)
- Click (CLI)
- pytest (testing)

### Frontend (A Definir)
- Framework: React / Vue / FastAPI+Jinja2 ?
- Charts: Plotly / Chart.js / TradingView ?
- State: Redux / Pinia / Context ?
- UI: Material-UI / Tailwind / Bootstrap ?

### Database (A Definir)
- SQLite / PostgreSQL ?
- Para almacenar: metadata modelos, datasets, signals históricos

---

## ✅ CONCLUSIÓN

El sistema CFD Trading ya tiene:
- ✅ **Data Layer**: Fetcher + Processor completo
- ✅ **ML Layer**: Múltiples modelos entrenados
- ✅ **Signal Generation**: Pipeline unificado
- ✅ **Backtesting**: Motor VectorBT con reportes HTML
- ✅ **Strategies**: 3 estrategias implementadas

**FALTA**:
- ❌ **Dashboard Web** para administrar todo
- ❌ **UI para visualizar** modelos y datos
- ❌ **Interface para entrenar** nuevos modelos

---

## 🚀 NEXT STEP

Que el usuario defina:
1. ¿Qué tech stack prefieres para el dashboard?
2. ¿Prioridad de features?
3. ¿Deployment target? (local, cloud, docker?)
4. ¿Usuarios finales?

