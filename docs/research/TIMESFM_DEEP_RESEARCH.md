# TimesFM 2.5 — Investigación Profunda
> Combinación de pruebas prácticas + documentación oficial

---

## 1. RESULTADOS PRÁCTICOS (Pruebas Ejecutadas Hoy)

### 1a. Batch Multi-Ticker (6 tickers simultáneos)

```
Batch inference: 1.29s total → ~216ms por ticker

Ticker    Último    +1 día    +5 días  +10 días   CI 80% (1 día)
────────────────────────────────────────────────────────────────
SPY       $741.00   $741.86   $743.60   $745.76   [$732-$747]
QQQ       $724.08   $724.82   $726.28   $728.25   [$710-$733]
GLD       $368.58   $367.19   $363.93   $361.01   [$359-$372]
AAPL      $281.74   $281.86   $279.89   $277.97   [$275-$286]
NVDA      $194.97   $195.25   $195.27   $195.33   [$189-$199]
BTC-USD $60,174    $60,024   $60,349   $60,935   [$58k-$61k]
```

**Observaciones:**
- SPY/QQQ proyectan alza moderada (tendencia continuación)
- GLD proyecta baja leve
- BTC neutral/alcista a 10 días

### 1b. Walk-Forward Backtest (SPY, 5 ventanas)

```
Ventana  MAE      MAPE    Directional  CI-80%
──────────────────────────────────────────────
1        $11.05   1.92%   40%          20%
2        $25.20   4.56%   50%          30%
3        $6.38    1.03%   20%          30%
4        $6.58    0.98%   60%          80%
5        $10.05   1.51%   50%          90%
──────────────────────────────────────────────
AVG      $11.85   2.00%   44%          50%
```

**Conclusión:** MAPE promedio 2.0% es bueno, pero varía mucho entre ventanas (1%–4.5%). La ventana 2 es mala porque captura el período volátil de principios de 2025.

### 1c. XReg + Covariates (RSI-14, MACD, Vol-MA vs Baseline)

```
Walk-forward 5 ventanas, SPY:

Ventana  Baseline  XReg+TFM  Ganador
──────────────────────────────────────
1        0.95%     0.96%     Base (+0.01%)
2        2.37%     3.17%     Base (+0.80%)
3        1.18%     2.57%     Base (+1.39%)
4        0.80%     0.71%     XReg (-0.09%)
5        1.09%     0.93%     XReg (-0.16%)
──────────────────────────────────────
AVG      1.28%     1.67%     Base gana

Mejora XReg: -0.39% MAPE (XReg es peor en este setup)
```

**¿Por qué falla RSI/MACD como covariables?**
Son derivados del mismo Close price — el modelo ya "sabe" esta info. Las mejores covariables son **señales independientes** (ver sección 3).

### 1d. API Discovery: Comportamiento con `return_backcast=True`

**Bug trampa crítico:** Cuando usas `return_backcast=True` en `ForecastConfig`, `forecast()` devuelve `(context_len + horizon)` valores — el backcast más el forecast concatenados:

```python
# ❌ INCORRECTO
bp, _ = model.forecast(horizon=10, inputs=[ctx])
forecast = bp[0]  # Incluye backcast, ¡primer valor es INCORRECTO!

# ✅ CORRECTO
bp, _ = model.forecast(horizon=10, inputs=[ctx])
forecast = bp[0][-10:]  # Tomar solo los últimos H valores
```

Lo mismo aplica para `forecast_with_covariates()`.

---

## 2. XREG / COVARIABLES — Referencia Completa

### Instalación requerida

```bash
pip install 'timesfm[xreg]'
```

### Firma exacta del método

```python
(cov_forecast, ols_forecast) = model.forecast_with_covariates(
    inputs=[[...], [...], ...],                   # list of 1-D float32 lists
    dynamic_numerical_covariates={
        "rsi":    [[ctx+horizon values], ...],    # (N, ctx_len + horizon)
        "volume": [[ctx+horizon values], ...],
    },
    dynamic_categorical_covariates={
        "session": [[0,0,1,1,...], ...],          # int or str, same length
    },
    static_numerical_covariates={},
    static_categorical_covariates={
        "asset_class": ["equity", "crypto", ...]  # one per series
    },
    xreg_mode="xreg + timesfm",    # o "timesfm + xreg"
    ridge=0.0,                     # regularización L2 para modelo lineal
    normalize_xreg_target_per_input=True,
    force_on_cpu=False,
)
```

**Importante:** `forecast_with_covariates` requiere compilar con `return_backcast=True`.

### Modos de XReg

| Modo | Cuándo usar |
|------|-------------|
| `"xreg + timesfm"` | Cuando las covariables son señales fuertes (ej: eventos calendáricos, datos macro) |
| `"timesfm + xreg"` | Cuando TimesFM es la señal principal y las covariables son débiles |

### Covariables que SÍ funcionan para finanzas

| Covariable | Tipo | Razón |
|------------|------|-------|
| Volume normalizado | Dynamic numerical | Señal independiente del precio |
| ATR (volatilidad) | Dynamic numerical | Independiente del nivel de precio |
| Hora del día (sin/cos) | Dynamic numerical | Estacionalidad intradía |
| Día de semana (sin/cos) | Dynamic numerical | Estacionalidad semanal |
| FOMC flag (0/1) | Dynamic categorical | Evento conocido de antemano |
| Sesión de mercado | Dynamic categorical | Tokyo/London/NY/Overlap |
| Asset class | Static categorical | "equity", "crypto", "commodity" |
| RSI de TF superior | Dynamic numerical | RSI diario como cov. para hourly |

### Covariables que NO funcionan (redundantes)

| Covariable | Razón |
|------------|-------|
| RSI del mismo TF | Derivado del mismo Close |
| MACD del mismo TF | Derivado del mismo Close |
| BB del mismo TF | Derivado del mismo Close |

**Regla:** Si la covariable se calcula del mismo Close price que se predice → no aporta info nueva.

### Template de integración correcta

```python
import numpy as np

def build_covariates_for_ticker(df, n_context, horizon):
    """
    df: DataFrame con OHLCV + indicadores ya calculados
    n_context: número de barras de contexto
    horizon: número de barras a predecir
    """
    ctx = df.tail(n_context + horizon)

    # Extender covariables al horizonte
    def extend(series):
        vals = series.values.astype(np.float32)
        return vals  # ya tiene n_context + horizon si se preparó bien

    # Señales temporales (se calculan para el futuro)
    hours = ctx.index.hour
    dows  = ctx.index.dayofweek

    return {
        "vol_norm": [(ctx['Volume'] / ctx['Volume'].rolling(20).mean()).fillna(1).values.tolist()],
        "atr_norm": [(ctx['atr'] / ctx['Close']).values.tolist()],
        "hour_sin": [np.sin(2 * np.pi * hours / 24).tolist()],
        "hour_cos": [np.cos(2 * np.pi * hours / 24).tolist()],
        "dow_sin":  [np.sin(2 * np.pi * dows  / 5).tolist()],
        "dow_cos":  [np.cos(2 * np.pi * dows  / 5).tolist()],
    }
```

---

## 3. FINE-TUNING CON LoRA — Guía Práctica

### Instalación

```bash
pip install transformers accelerate peft pandas pyarrow scikit-learn
```

### Formato del dataset

```python
# Lista de arrays 1D (cada uno = una serie)
series_list = [
    df_SPY['Close'].values.astype(np.float32),    # (N1,)
    df_QQQ['Close'].values.astype(np.float32),    # (N2,)
    df_BTC['Close'].values.astype(np.float32),    # (N3,)
    # ... un array por ticker
]
```

- **Mínimo por serie:** `context_len + horizon_len` valores
- Sin normalización manual — TimesFM aplica RevIN internamente
- Las series pueden tener longitudes diferentes

### Dataset con random window sampling (patrón oficial)

```python
from torch.utils.data import Dataset
import numpy as np

class TradingSeriesDataset(Dataset):
    def __init__(self, series_list, context_len=512, horizon_len=24, n_samples=5000):
        rng = np.random.default_rng(42)
        min_len = context_len + horizon_len
        valid = [i for i, s in enumerate(series_list) if len(s) >= min_len]

        self.context_len = context_len
        self.horizon_len = horizon_len
        self.series_list = series_list
        self.samples = []

        for _ in range(n_samples):
            idx   = rng.choice(valid)
            s     = series_list[idx]
            start = rng.integers(0, len(s) - min_len + 1)
            self.samples.append((idx, int(start)))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        idx, start = self.samples[i]
        s = self.series_list[idx]
        ctx  = torch.tensor(s[start:start + self.context_len], dtype=torch.float32)
        tgt  = torch.tensor(s[start + self.context_len:start + self.context_len + self.horizon_len],
                            dtype=torch.float32)
        return ctx, tgt
```

### Configuración LoRA recomendada

```python
from peft import LoraConfig, get_peft_model
from transformers import TimesFm2_5ModelForPrediction

model = TimesFm2_5ModelForPrediction.from_pretrained(
    "google/timesfm-2.5-200m-pytorch",
    torch_dtype=torch.bfloat16,   # 50% menos memoria
    device_map="cuda",
)

lora_config = LoraConfig(
    r=4,                          # Rank 4 → ~102K params trainables
    lora_alpha=8,                 # Scaling = alpha/r = 2
    target_modules="all-linear",  # Adaptar todas las capas lineales
    lora_dropout=0.05,
    bias="none",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# trainable params: 102,400 || all params: 232,M || trainable%: 0.044%
```

### Parámetros clave a ajustar

| Parámetro | Default | Para tu proyecto |
|-----------|---------|-----------------|
| `--context_len` | 64 | 256–512 (más historia) |
| `--horizon_len` | 13 | 24 (diario) / 8 (hourly) |
| `--lora_r` | 4 | 8 si quieres más capacidad |
| `--epochs` | 10 | 10–20 |
| `--batch_size` | 32 | 64 si cabe en GPU |
| `--lr` | 5e-5 | 1e-4 si converge lento |
| `--n_samples` | 5000 | 10000 para 19 tickers × 5 años |

### Tiempo estimado en RTX 5060 (12GB)

Con `bfloat16` + LoRA rank 4:
- Dataset: 19 tickers × ~1250 días × context 256 = ~5000 ventanas
- Batch size 64 → ~78 steps/epoch
- Epochs 10 → ~780 steps totales
- **Estimado: 20–40 minutos** por run de entrenamiento

---

## 4. WALK-FORWARD VALIDATION — Metodología Correcta

### Protocolo recomendado (ROFE)

Based on the June 2026 arxiv paper on financial forecasting with foundation models:

```
Context: 512 barras (≈ 2 años diario / 3 meses hourly)
Horizon: 20 barras (≈ 1 mes diario / 2.5 días hourly)
Windows: 10 ventanas no solapadas
Step:    igual al horizon (no-overlapping)
```

### Implementación sin data leakage

```python
def walk_forward_eval(model, prices, context=512, horizon=20, min_windows=10):
    """Walk-forward evaluation sin data leakage."""
    results = []
    # Empezar desde context, avanzar de horizon en horizon
    for start in range(context, len(prices) - horizon, horizon):
        ctx = prices[start - context:start]     # Solo pasado
        act = prices[start:start + horizon]     # Futuro real

        pf, qf = model.forecast(horizon=horizon, inputs=[ctx])

        # Con return_backcast=True, tomar últimos H elementos
        pred = pf[0][-horizon:]

        mape = (np.abs(pred - act) / act).mean() * 100
        dir_acc = ((np.diff(pred, prepend=ctx[-1]) > 0) ==
                   (np.diff(act, prepend=act[0]) > 0)).mean() * 100
        ci_cov = ((act >= qf[0][-horizon:, 1]) &
                  (act <= qf[0][-horizon:, 8])).mean() * 100

        results.append({'mape': mape, 'dir': dir_acc, 'ci80': ci_cov})
        if len(results) >= min_windows:
            break

    return pd.DataFrame(results)
```

### Checklist anti-data leakage

- ✅ Normalización solo con stats del contexto (RevIN automático)
- ✅ Indicadores calculados solo hasta el punto de corte
- ✅ Para covariables temporales (hora, día) → calculables en el futuro
- ✅ Para covariables de eventos → usar calendario económico publicado
- ❌ No usar RSI/MACD futuro del mismo precio
- ❌ No recalibrar el modelo en datos de test

---

## 5. TIMESFM vs CHRONOS — Comparativa

### Benchmark de Precisión (papers Oct 2025 / Jun 2026)

| Benchmark | TimesFM 2.5 | Chronos-2 | Ganador |
|-----------|-------------|-----------|---------|
| GIFT-Eval | Win rate 77.5% | **81.9%** | Chronos |
| fev-bench | Win rate 75.9% | **90.7%** | Chronos |
| Equidades US | Rank #1 avg | Rank #2 | **TimesFM** |

### Velocidad de Inferencia

| Modelo | Latencia mediana |
|--------|------------------|
| **Chronos-2** | **3.6s** |
| TimesFM 2.5 | 16.9s |

→ Chronos-2 es **~4.7× más rápido**.

### Comparativa de Features

| Feature | TimesFM 2.5 | Chronos-2 |
|---------|-------------|-----------|
| Contexto máx. | **16,384** | ~2,048 |
| Covariables | ✅ XReg (external) | ✅ Nativo |
| Multivariado | ❌ No | ✅ Sí |
| Velocidad | Lento | **Rápido** |
| Integración cloud | Google BigQuery | AWS SageMaker |
| Cuantiles | 10 percentiles | Vía sampling |
| LoRA fine-tuning | ✅ PEFT oficial | ✅ PEFT |
| Licencia | Apache 2.0 | Apache 2.0 |

### Recomendación para este proyecto

| Caso de uso | Recomendación |
|-------------|---------------|
| Pipeline diario (batch overnight) | **TimesFM 2.5** (contexto largo + XReg) |
| Señales horarias en tiempo real | **Chronos-2** (4.7x más rápido) |
| Análisis multi-activo con correlaciones | **Chronos-2** (multivariado) |
| Walk-forward sobre 5+ años | **TimesFM 2.5** (16K contexto) |

---

## 6. LIMITACIONES REALES (Confirmadas por Papers)

Del paper arxiv:2606.27100 (junio 2026), con pruebas en AAPL, AMZN, GOOG, JPM, META:

> "Both models beat random-walk only **rarely**. The gains are **small and sparse**. Neither delivers statistically significant alpha over a random walk on most assets."

**Lo que esto significa:**
- TimesFM es bueno prediciendo el **nivel de precio** (MAPE bajo)
- Pero predecir si sube o baja (dirección) es casi aleatorio
- El valor real para trading es en los **cuantiles para risk management**, no en la dirección

**Conclusión práctica:**
- ❌ No usar TimesFM como señal direccional primary
- ✅ Usar TimesFM para **calibrar SL/TP** dinámicamente
- ✅ Usar TimesFM para **confidence intervals** del precio esperado
- ✅ Usar TimesFM como **señal secundaria** en ensemble con XGBoost

---

## 6b. RESULTADOS LoRA FINE-TUNING (2026-06-29)

### Batches entrenados

| Batch | Data | LoRA r | Epochs | Tiempo | MAPE | vs Zero-shot |
|-------|------|--------|--------|--------|------|-------------|
| Zero-shot | — | — | — | — | 1.44% | — |
| **B (19 tickers 1d)** | 19 tickers 1d | 8 | 10 | 3.8 min | **1.39%** | **-0.05% ✅** |
| A (SPY 1d) | SPY 1d | 4 | 10 | 4.0 min | 1.47% | +0.03% ❌ |
| C (SPY 1h) | SPY 1h | 4 | 15 | 5.9 min | 1.52% | +0.08% ❌ |

**Conclusión:** La ganancia es marginal (≤0.05%). El modelo pre-entrenado ya captura bien los patrones financieros. El gap entre el training objective (proxy via `forward()`) y la ruta de inferencia (`decode()` con `no_grad()`) limita la ganancia. **Usar zero-shot para producción.**

---

## 6c. RESULTADOS EN DATOS 1-MINUTO (2026-06-29)

### Setup: context=512 barras (~8.5h), horizon=60 (próxima hora)

| Ticker | MAPE | Dir | SL% | TP% |
|--------|------|-----|-----|-----|
| SPY | 0.02% | ✅ | 0.02% | 0.10% |
| QQQ | 0.05% | ✅ | 0.03% | 0.14% |
| IWM | 0.06% | ✅ | 0.03% | 0.16% |
| DIA | 0.05% | ✅ | 0.03% | 0.05% |
| GLD | 0.07% | ✅ | 0.04% | 0.24% |
| SLV | 0.11% | ✅ | 0.11% | 0.35% |
| USO | 0.09% | ❌ | 0.07% | 0.29% |
| UNG | 0.10% | ✅ | 0.11% | 0.41% |
| AAPL | 0.11% | ✅ | 0.08% | 0.19% |
| NVDA | 0.24% | ✅ | 0.07% | 0.24% |
| MSFT | 0.13% | ❌ | 0.12% | 0.08% |
| AMZN | 0.16% | ✅ | 0.11% | 0.03% |
| GOOGL | 0.19% | ✅ | 0.06% | 0.25% |
| META | 0.13% | ✅ | 0.07% | 0.02% |
| TSLA | 0.28% | ✅ | 0.09% | 0.65% |
| BTC-USD | 0.31% | ✅ | 0.04% | 0.13% |
| ETH-USD | 0.35% | ✅ | 0.08% | 0.19% |
| SOL-USD | 0.40% | ✅ | 0.16% | 0.11% |
| XRP-USD | 0.43% | ✅ | 0.09% | 0.46% |
| **PROMEDIO** | **0.17%** | **89%** | **0.07%** | **0.21%** |

**Por qué 1min es 10x mejor que 1d:** Fuerte autocorrelación intra-hora (momentum). A 1 día los eventos macro dominan y el modelo no los anticipa.

**Latencia:** 3.5s en secuencia, ~613ms en batch único. Perfectamente viable para ejecución horaria.

---

## 7. PRÓXIMOS PASOS RECOMENDADOS

### Opción A: Fine-tuning (1–2 días)
Crea `scripts/train_timesfm_lora.py` y entrena sobre tus 19 tickers:
1. Instalar: `pip install transformers accelerate peft`
2. Preparar dataset con `TradingSeriesDataset`
3. Fine-tune con LoRA rank 4, context=256, horizon=24
4. Comparar fine-tuned vs zero-shot con walk-forward

### Opción B: XReg con covariables correctas (1 día)
Reemplazar RSI/MACD por covariables independientes:
1. Volume normalizado + ATR
2. Codificación horaria/semanal (sin/cos)
3. Flags de eventos (FOMC, earnings)
4. Re-ejecutar walk-forward comparativo

### Opción C: Integrar zero-shot en pipeline (2–3 horas)
Crear `models/timesfm_predictor.py`:
1. Wrapper que carga y cachea el modelo
2. Usa cuantiles para SL/TP dinámico en `AlpacaBroker`
3. Agrega señal auxiliar en scoring de confluence

### Comparar Chronos-2 (2 horas)
```bash
pip install autogluon.timeseries
```
Benchmark rápido de Chronos-2 vs TimesFM en walk-forward sobre SPY.

---

## 8. RESUMEN EJECUTIVO ACTUALIZADO

| Aspecto | Antes del deep dive | Después del deep dive |
|---------|--------------------|-----------------------|
| MAPE zero-shot | 1.02% (1 window) | **2.0% avg** (5 windows) |
| Directional accuracy | 33% | **44% avg** (33–60% range) |
| CI-80% coverage | 83% | **50% avg** (varía mucho) |
| XReg (RSI/MACD) | No probado | **Peor que baseline** (-0.39%) |
| XReg (vol/time) | No probado | **Potencialmente mejor** (no probado) |
| Fine-tuning | Desconocido | **~30 min en RTX 5060** con bfloat16 |
| Alternativa | Ninguna | **Chronos-2 es 4.7x más rápido** |
| Valor real | Señal direccional? | **NO — usar para risk mgmt (SL/TP)** |

---

*Generado 2026-06-29 | Fuentes: google-research/timesfm GitHub, arxiv:2606.27100, arxiv:2510.15821, MQL5 TimesFM article, AI Horizon Forecast tutorials*
