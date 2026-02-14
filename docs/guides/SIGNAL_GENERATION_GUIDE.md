# Signal Generation & ML Trading Guide

## 🔄 Cómo Funcionan las Señales

### Flujo Completo de Generación de Señales

```
1. FETCH DATA
   └─ Descarga datos históricos desde Yahoo Finance
   └─ Período: 1m, 5m, 15m, 1h, 1d
   └─ Cantidad: Auto-calculada según intervalo

2. CLEAN & VALIDATE
   └─ Elimina duplicados y datos faltantes
   └─ Verifica OHLCV completos
   └─ Valida rangos (high >= low, volume >= 0)

3. COMPUTE INDICATORS
   └─ Calcula 26 indicadores técnicos
   └─ MACD, RSI, Bollinger Bands, VWAP, etc.
   └─ Tarda ~100ms para 250 barras

4. APPLY STRATEGY
   └─ Análisis técnico puro
   └─ Genera BUY/SELL/HOLD basado en reglas
   └─ Calcula Entry, Stop Loss, Take Profit

5. ML FILTER (Opcional)
   └─ Carga modelo entrenado
   └─ Predice dirección (BUY/SELL)
   └─ Compara con señal técnica
   └─ Filtra si ML y técnico no coinciden

6. OUTPUT SIGNAL
   └─ Dirección (BUY/SELL/HOLD)
   └─ Entry price (precio actual)
   └─ Stop Loss, Take Profit
   └─ Confidence score (0-1)
   └─ Risk/Reward ratio
```

### Componentes de una Señal

```python
@dataclass
class Signal:
    strategy: str              # "macd_vwap", "rsi_bb", "ma_crossover"
    ticker: str                # "SPY", "GLD", "BTC-USD"
    interval: str              # "1m", "5m", "15m", "1h", "1d"
    direction: str             # "BUY", "SELL", "HOLD"
    entry_price: float         # Precio actual cuando se genera
    stop_loss: float           # Nivel de pérdida máxima (2% del entry)
    take_profit: float         # Nivel de ganancia objetivo
    confidence: float          # 0-1 (qué tan fuerte es la señal)
    ml_filtered: bool          # Si pasó filtro ML
    ml_confidence: float       # Confianza del modelo ML
    risk_reward_ratio: float   # take_profit - entry / entry - stop_loss
```

## 📊 Períodos Disponibles & Alcance

### Información de Datos por Período

| Período | Alcance | Barras | Uso | Señales/Día | Datos |
|---------|---------|--------|-----|-------------|-------|
| **1m** | 7 días | ~6,700 | Scalping HFT | 50+ | 1 semana |
| **5m** | 30 días | ~8,640 | Scalping intraday | 200+ | 1 mes |
| **15m** | 30 días | ~2,880 | Scalping corto | 96 | 1 mes |
| **1h** | 90 días | ~2,160 | Swing corto | 24 | 3 meses |
| **1d** | 365 días | ~251 | Swing largo | 1 | 1 año |

### Alcance Actual (Period = Daily)

**Período: 1d (Diario)**
- ✅ Datos: 1 año completo (365 días)
- ✅ Barras: ~251 (excluyendo fines de semana)
- ✅ Señales: 1 por día máximo
- ✅ Indicadores: Todos convergidos (200 SMAs necesitan 200 barras mínimo)
- ✅ Confiabilidad: Muy alta (datos históricos completos)

**Ventajas:**
- Menos ruido que intraday
- Indicadores totalmente formados
- Mejor para swing trading

**Limitaciones:**
- Solo 1 oportunidad por día
- Menos frequency trading

## 🎯 Las 3 Estrategias Actuales

### 1. MACD + VWAP (Scalping)
**Ideal para:** Mercados en tendencia

**Lógica:**
```
BUY:  MACD > Signal Line AND Price > VWAP
SELL: MACD < Signal Line OR Profit >= 1%
SL:   0.5% bajo entry
TP:   1% arriba entry
```

**Confidence:** Media-Alta (depende de MACD momentum)

### 2. RSI + Bollinger Bands (Reversión)
**Ideal para:** Mercados rangebound

**Lógica:**
```
BUY:  RSI < 30 (oversold) AND Price toca BB inferior
SELL: RSI > 70 (overbought) OR Profit >= TP
SL:   0.7% bajo entry
TP:   BB media
```

**Confidence:** Alta (RSI es muy confiable en reversiones)

### 3. Moving Average Crossover (Tendencia)
**Ideal para:** Mercados en tendencia fuerte

**Lógica:**
```
BUY:  SMA50 > SMA200 (Golden Cross)
SELL: SMA50 < SMA200 (Death Cross)
SL:   2% bajo entry
TP:   3% arriba entry
```

**Confidence:** Baja-Media (pocos cruces, pero decisivos)

## 🤖 ML Filtering

### Cómo Funciona

```
1. Estrategia genera: BUY (confidence 0.8)
2. ML modelo predice: SELL (0.52)
3. Comparación:
   - Técnico: BUY
   - ML: SELL
   ❌ CONFLICTO → Señal RECHAZADA

vs.

1. Estrategia genera: BUY (confidence 0.8)
2. ML modelo predice: BUY (0.60)
3. Comparación:
   - Técnico: BUY
   - ML: BUY
   ✅ ACUERDO → Señal ACEPTADA + ML FILTERED
```

### Accuracy por Modelo (Actual)

| Modelo | Accuracy | Recomendación |
|--------|----------|---------------|
| GLD | 64% | ✅ Usar para filtrar |
| MSFT | 60% | ✅ Usar para filtrar |
| QQQ | 56% | ✅ Usar para filtrar |
| AAPL | 52% | ✅ Usar con cuidado |
| Promedio | 50.36% | ⚠️ Mejor que aleatorio |

**Umbral mínimo:** 52% accuracy recomendado

## 💡 Mejoras Sugeridas

### Para Mejorar Accuracy

1. **Más Datos de Entrenamiento**
   - Entrenar con períodos 5m, 15m, 1h
   - Combinar múltiples años de datos
   - Cross-validation entre períodos

2. **Feature Engineering**
   - Agregar volatilidad (ATR)
   - Volumen relativo
   - Money Flow Index

3. **Arquitectura del Modelo**
   - Aumentar LSTM layers
   - Attention mechanism
   - Ensemble de modelos

4. **Entrenamiento Mejorado**
   - Más epochs (50 → 100)
   - Learning rate scheduling
   - Data augmentation

## 📈 Generación de Señales en Vivo

### Comando Básico

```bash
# Genera 1 señal ahora
python main.py signal --strategy macd_vwap --ticker SPY

# Con filtro ML
python main.py signal --strategy macd_vwap --ticker SPY --use-ml
```

### Output Ejemplo

```
==================================================
  SIGNAL: BUY - Acción Recomendada
  Strategy: macd_vwap
  Ticker: SPY (1m)
  Price: $681.50
  Time: 2026-02-14 12:45:30
  Confidence: 0.85

  Entry:      $681.50
  Stop Loss:  $677.00 (-0.5%)
  Take Profit: $688.50 (+1.0%)
  Risk/Reward: 1:2.0

  ML Filter: ✅ PASSED (confidence: 0.58)

==================================================
```

### Monitoreo Continuo

```bash
# Escanea todos los tickers cada 15 minutos
python main.py watch --use-ml --interval 15m --every 900

# Solo los mejores modelos
python main.py watch --tickers GLD,MSFT,QQQ,AAPL --use-ml
```

### Notificaciones Telegram

```bash
# Configura en .env:
# TELEGRAM_BOT_TOKEN=xxx
# TELEGRAM_CHAT_ID=xxx

# Automático: señales se envían a Telegram
python main.py watch --use-ml
```

## 🔍 Análisis Multi-Período

### Estrategia de Múltiples Temporalidades

```
1. Confirmar con período superior (1d)
   └─ Si 1d = BUY → Opción favorable

2. Entrar en período inferior (1h)
   └─ Esperar confirmación en 1h

3. Ejecutar en período táctico (5m)
   └─ Entry final con timing perfecto
```

### Ejemplo: GLD Multi-Período

```bash
# Verifica tendencia diaria
python main.py signal --strategy ma_crossover --ticker GLD --interval 1d

# Confirma con horario
python main.py signal --strategy rsi_bb --ticker GLD --interval 1h

# Ejecuta con táctico
python main.py signal --strategy macd_vwap --ticker GLD --interval 5m
```

## 📊 Próximos Pasos Recomendados

1. ✅ **Mejorar Modelos Existentes** (50-100 epochs)
2. ✅ **Entrenar Períodos Adicionales** (5m, 15m, 1h)
3. ✅ **Generar Señales Híbridas** (técnico + ML)
4. ✅ **Backtesting con ML Filtering**
5. ✅ **Paper Trading en Live Mode**

---

**Status:** Sistema completamente funcional ✅
**Recomendación:** Comenzar con GLD (64% accuracy) en período 1d
