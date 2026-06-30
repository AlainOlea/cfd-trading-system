# TimesFM Integration Plan
> Cómo integrar TimesFM en el pipeline existente

---

## Resumen de lo que sabemos

| Intervalo | MAPE | Dir Acc | Veredicto |
|-----------|------|---------|-----------|
| 1-minute  | 0.17% | 89% | **Usar en producción** |
| 1-day     | 1.4-2.4% | 44% | Auxiliar para SL/TP |

TimesFM en 1-min es muy preciso en precio y dirección. Esto lo hace útil como:
1. **Señal de dirección** auxiliar en el scoring de confluence
2. **SL/TP dinámico** basado en cuantiles (reemplaza los % fijos actuales)
3. **Filtro de confianza**: si TimesFM contradice la señal técnica → reducir size

---

## Flujo actual del pipeline

```
main.py pipeline
    ↓
UnifiedPipeline.run()
    ├── DataFetcher (Alpaca incremental + fallback yfinance)
    ├── TechnicalIndicators (12 indicadores)
    ├── Strategies: MACD+VWAP, RSI+BB, MA Crossover
    ├── XGBoostTrader (ML filter, 65% confidence)
    ├── EnsemblePredictor (LSTM + XGBoost voting)
    ├── Confluence scoring (0-5 estrellas, min 3)
    └── AlpacaBroker (bracket orders: SL fijo 0.5%, TP fijo 1%)
```

---

## Flujo propuesto con TimesFM

```
main.py pipeline
    ↓
UnifiedPipeline.run()
    ├── DataFetcher (igual)
    ├── TechnicalIndicators (igual)
    ├── Strategies (igual)
    ├── XGBoostTrader (igual)
    ├── EnsemblePredictor (igual)
    ├── [NUEVO] TimesFMPredictor
    │       ├── Input: close prices 1min (últimas 512 barras)
    │       ├── Output: forecast 60 barras + cuantiles
    │       └── Produce: dir_signal + sl_price + tp_price
    ├── Confluence scoring (igual + bonus si TimesFM coincide)
    └── AlpacaBroker (bracket orders con SL/TP dinámico de TimesFM)
```

---

## Archivo a crear: `models/timesfm_predictor.py`

```python
import os
import numpy as np
import timesfm
from timesfm import ForecastConfig

os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")

class TimesFMPredictor:
    """
    Zero-shot TimesFM wrapper para integración en el pipeline.
    
    Uso:
        predictor = TimesFMPredictor()
        result = predictor.predict(prices_1min, horizon=60)
        # result["direction"]: +1 / -1
        # result["sl_price"]:  stop-loss price (10th percentile)
        # result["tp_price"]:  take-profit price (80th percentile)
        # result["mape_est"]:  estimación de error esperado
    """
    
    CONTEXT = 512   # barras de contexto
    
    def __init__(self):
        self._model = None
    
    def _load(self):
        if self._model is not None:
            return
        self._model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            "google/timesfm-2.5-200m-pytorch"
        )
        self._model.compile(ForecastConfig(
            max_context=self.CONTEXT,
            max_horizon=128,
            normalize_inputs=True,
            infer_is_positive=True,
        ))
    
    def predict(self, prices: np.ndarray, horizon: int = 60) -> dict:
        """
        prices: array 1D float32, al menos CONTEXT barras
        horizon: pasos a predecir (default 60 = 1 hora en 1min)
        
        Returns dict con:
            direction:  +1 (alcista) / -1 (bajista) / 0 (neutral)
            sl_price:   precio stop-loss (10° percentil)
            tp_price:   precio take-profit (80° percentil)
            forecast:   array(horizon,) de precios pronosticados
            quantiles:  array(horizon, 10) de percentiles
            confidence: 0.0-1.0 basado en rango de CI
        """
        self._load()
        
        prices = np.array(prices, dtype=np.float32).flatten()
        ctx = prices[-self.CONTEXT:]
        
        pf, qf = self._model.forecast(horizon=horizon, inputs=[ctx])
        forecast = pf[0][:horizon]
        quantiles = qf[0][:horizon]     # (horizon, 10)
        
        last = ctx[-1]
        direction = int(np.sign(forecast[-1] - last))
        
        sl_price = float(quantiles[0, 1])    # 10th percentile en t=0
        tp_price = float(quantiles[-1, 8])   # 80th percentile en t=horizon
        
        # Confidence: cuanto más estrecho el CI, más confiable
        ci_width = (quantiles[:, 8] - quantiles[:, 1]).mean()
        confidence = max(0.0, 1.0 - ci_width / last)
        
        return {
            "direction":  direction,
            "sl_price":   sl_price,
            "tp_price":   tp_price,
            "forecast":   forecast,
            "quantiles":  quantiles,
            "confidence": min(1.0, confidence),
            "last_price": float(last),
        }
    
    def predict_batch(self, prices_dict: dict, horizon: int = 60) -> dict:
        """
        prices_dict: {ticker: np.ndarray} — todos los tickers a la vez
        Returns: {ticker: result_dict}
        Más eficiente que llamar predict() N veces.
        """
        self._load()
        
        tickers = list(prices_dict.keys())
        inputs  = [
            np.array(prices_dict[t], dtype=np.float32).flatten()[-self.CONTEXT:]
            for t in tickers
        ]
        
        pf, qf = self._model.forecast(horizon=horizon, inputs=inputs)
        
        results = {}
        for i, ticker in enumerate(tickers):
            forecast  = pf[i][:horizon]
            quantiles = qf[i][:horizon]
            last      = inputs[i][-1]
            direction = int(np.sign(forecast[-1] - last))
            ci_width  = (quantiles[:, 8] - quantiles[:, 1]).mean()
            
            results[ticker] = {
                "direction":  direction,
                "sl_price":   float(quantiles[0, 1]),
                "tp_price":   float(quantiles[-1, 8]),
                "forecast":   forecast,
                "quantiles":  quantiles,
                "confidence": min(1.0, max(0.0, 1.0 - ci_width / last)),
                "last_price": float(last),
            }
        
        return results
```

---

## Cambios en `signals/pipeline.py`

Solo 3 bloques:

### 1. Import + init (en `__init__`)
```python
from models.timesfm_predictor import TimesFMPredictor

class UnifiedPipeline:
    def __init__(self):
        # ... código existente ...
        self.timesfm = TimesFMPredictor()  # lazy-load en primer uso
```

### 2. Llamada batch en `run()` (después de fetch data)
```python
# Obtener precios 1min para todos los tickers
prices_1min = {}
for ticker in self.tickers:
    df_1m = self.fetcher.get_data(ticker, interval="1m")
    if df_1m is not None and len(df_1m) >= 512:
        prices_1min[ticker] = df_1m["Close"].values

# Forecast batch — una sola llamada para todos
if prices_1min:
    tfm_results = self.timesfm.predict_batch(prices_1min, horizon=60)
else:
    tfm_results = {}
```

### 3. Uso en scoring por ticker
```python
def _compute_confluence(self, ticker, signals, tfm_result=None):
    score = 0
    # ... lógica existente de confluence ...
    
    # Bonus TimesFM: +1 si coincide dirección con señal técnica
    if tfm_result and tfm_result["direction"] != 0:
        tech_direction = +1 if signals["action"] == "BUY" else -1
        if tfm_result["direction"] == tech_direction:
            score += 1
    
    return score
```

### 4. SL/TP dinámico en `AlpacaBroker`
```python
# En lugar de SL fijo (0.5%), usar cuantiles de TimesFM
if tfm_result:
    sl_price = tfm_result["sl_price"]
    tp_price = tfm_result["tp_price"]
else:
    # fallback a porcentajes fijos del config
    sl_price = entry_price * (1 - settings.STOP_LOSS_PCT)
    tp_price = entry_price * (1 + settings.TAKE_PROFIT_PCT)
```

---

## Scheduling: 60 barras nuevas cada hora

El pipeline horario ya existe (`CFD Paper Hourly`, Mon-Fri 07:00-15:59 ET, cada hora). Solo hay que asegurar que cuando corre:

1. Alpaca Data API descarga las últimas 60 barras de 1min (incremental — ya implementado en `data/fetcher.py`)
2. Se agregan al contexto rolling de 512 barras
3. TimesFM corre con el contexto actualizado

```
07:00 ET → fetch 60 barras nuevas → context=512 → forecast(60) → señales
08:00 ET → fetch 60 barras nuevas → context=512 → forecast(60) → señales
...
15:59 ET → fetch 60 barras nuevas → context=512 → forecast(60) → señales
```

El `FetchMetadata` ya trackea el último timestamp por ticker+intervalo — el fetch incremental funciona automáticamente.

---

## Estimación de latencia en producción

| Operación | Tiempo |
|-----------|--------|
| Fetch incremental 60 barras × 19 tickers (Alpaca) | ~5-10s |
| TimesFM batch forecast (19 tickers simultáneos) | ~0.6s |
| Indicators + strategies + XGBoost | ~2-5s |
| Alpaca order submission | ~1s |
| **Total pipeline** | **~10-20s** |

Perfectamente dentro del margen de 1 hora.

---

## Orden de implementación sugerido

1. **Crear `models/timesfm_predictor.py`** (30 min) — wrapper listo para importar
2. **Añadir llamada batch en `pipeline.py`** (1 hora) — conectar al flujo existente
3. **SL/TP dinámico en `alpaca_broker.py`** (1 hora) — reemplazar % fijos por cuantiles
4. **Tests** (1 hora) — `tests/test_timesfm_predictor.py`
5. **Paper trade monitoring** (1 semana) — comparar SL/TP fijo vs dinámico
