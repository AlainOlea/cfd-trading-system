# TimesFM POC (Proof of Concept) Guide

## Quick Start

### 1. Install TimesFM

```bash
# Activate venv
source venv/bin/activate

# Install timesfm with PyTorch backend
pip install timesfm[torch]

# Optional: psutil for memory estimation
pip install psutil
```

**Requirements:**
- Python >= 3.10 ✓ (you have 3.12.3)
- PyTorch (installs automatically with timesfm[torch])
- numpy >= 1.26.4, huggingface_hub >= 0.23.0

### 2. Run POC Script

#### Test on Daily Data (SPY)

```bash
cd /home/alaindolea/proyectos/cfd-trading-system
python3 scripts/timesfm_poc.py SPY 1d
```

**Output example:**
```
Forecast Sample (next 12 bars):
  Last price: $450.23
  Next 12 forecasted:
    +1d: $450.45
    +2d: $450.67
    +3d: $451.02
    ...

EVALUATION SUMMARY
Ticker: SPY
Data bars: 500
Zero-shot performance: Promising
Recommended next step: Ensemble with XGBoost
```

#### Test on Hourly Data (QQQ)

```bash
python3 scripts/timesfm_poc.py QQQ 1h
```

#### Test on Any Ticker

```bash
python3 scripts/timesfm_poc.py NVDA 1d
python3 scripts/timesfm_poc.py BTC-USD 1d
```

---

## What the Script Does

### Phase 1: Data Download
- Downloads last 500 bars of historical price data via yfinance
- Keeps only Close prices (univariate)
- Logs data statistics

### Phase 2: Memory Estimation
- Calculates TimesFM model size (~25GB for 200M params)
- Estimates current process memory
- Detects available GPU VRAM

### Phase 3: Model Loading
- Downloads pre-trained TimesFM 2.5 from Hugging Face (first run only, ~500MB)
- Caches model locally (~/.cache/huggingface)
- Measures load time

### Phase 4: Live Forecast
- Takes last 500 bars of price history
- Generates forecast for next 24 periods
- Normalizes data before inference (numerical stability)
- Denormalizes predictions to original price scale
- Measures inference latency

### Phase 5: Backtest
- Hides last 12 bars from training
- Forecasts those 12 bars using previous 500 bars
- Calculates accuracy metrics:
  - **MAE**: Mean Absolute Error (dollars)
  - **RMSE**: Root Mean Squared Error (dollars)
  - **MAPE**: Mean Absolute Percentage Error (%)
  - **Directional Accuracy**: % of correct up/down predictions

---

## Expected Results

### If Zero-Shot Works Well
- **MAPE < 3%**: Excellent (rare)
- **MAPE 3-5%**: Good (TimesFM foundation model is strong)
- **Directional Accuracy > 55%**: Better than coin flip
- **Action**: Consider integrating into ensemble

### If Zero-Shot Doesn't Work
- **MAPE > 5%**: Needs fine-tuning
- **Directional Accuracy < 55%**: Random predictions
- **Action**: Fine-tune on your 5-year financial data (see Fine-tuning Guide below)

---

## Integration Strategies

### Strategy 1: Quick Ensemble
After POC succeeds:

1. Create `models/timesfm_predictor.py`:
```python
from timesfm import TimesFM
import numpy as np

class TimesFMPredictor:
    def __init__(self):
        self.model = TimesFM(context_len=512, prediction_len=24)
    
    def predict(self, close_prices: np.ndarray, horizon: int = 12):
        """Forecast next 12 bars with uncertainty quantiles."""
        point, quantiles = self.model.forecast(
            inputs=close_prices.reshape(1, -1),
            quantile_levels=[0.1, 0.5, 0.9]  # 10%, 50%, 90%
        )
        return {
            'forecast': point[0][:horizon],
            'lower_bound': quantiles[0, :horizon, 0],  # 10% quantile
            'upper_bound': quantiles[0, :horizon, 2],  # 90% quantile
        }
```

2. Modify `signals/pipeline.py`:
```python
# In UnifiedPipeline class
from models.timesfm_predictor import TimesFMPredictor

self.timesfm = TimesFMPredictor()

# In signal generation
timesfm_pred = self.timesfm.predict(close_prices)
confluence_score += 1 if timesfm_pred['forecast'][-1] > close_prices[-1] else -1
```

3. Use quantiles for dynamic SL/TP:
```python
upper_band = timesfm_pred['upper_bound'][0]  # 90% confidence
lower_band = timesfm_pred['lower_bound'][0]  # 10% confidence

# Risk-adjusted stops
tp_price = upper_band * 0.9
sl_price = lower_band * 1.1
```

### Strategy 2: Fine-tuning
After POC, if zero-shot performance is weak (MAPE > 5%):

```bash
# Create fine-tuning script
python3 main.py train-timesfm --tickers SPY,QQQ,IWM --interval 1d --epochs 10 --use-lora

# LoRA keeps only ~100K params trainable (vs 200M total)
# Train time: ~2-4 hours on GPU
# Result: Specialized model for your 19 tickers
```

### Strategy 3: Indicator Forecasting
Apply TimesFM to technical indicators instead of price:

```python
# Forecast RSI next value
rsi_values = calculate_rsi(close_prices)
timesfm_rsi_next = timesfm.forecast(rsi_values)

# Same for MACD, Bollinger Bands, ATR, etc.
# Improves confluence scoring with forward-looking indicators
```

---

## GPU Considerations

### Memory Requirements

| Model | VRAM | Device | Notes |
|-------|------|--------|-------|
| TimesFM 2.5 | ~18GB | GPU | Baseline + batch size 4 |
| Optimized | ~12GB | GPU | With optimizations (rtx 5060 ~fits) |
| CPU Inference | Unlimited | CPU | 10x slower, but works |

### Your Setup (RTX 5060 12GB)

**Tight fit but possible with optimizations:**

```python
# In timesfm_poc.py or integration
import torch

# Enable memory optimizations
torch.backends.cudnn.benchmark = False
torch.backends.cuda.empty_cache()

# Use half precision (float16) instead of float32
model = model.half()  # Saves 50% memory

# Smaller batch size
batch_size = 1  # Process one ticker at a time
```

---

## Next Steps

### Recommended Flow

1. **Run POC** (this script) on SPY daily
   - Takes ~5-10 minutes first run (downloads model)
   - Takes ~2-3 minutes on subsequent runs

2. **If MAPE < 5% and Directional Accuracy > 55%:**
   - Proceed to Strategy 1 (Ensemble)
   - Minimal integration effort

3. **If MAPE > 5%:**
   - Proceed to Strategy 2 (Fine-tuning)
   - Requires 2-4 hours of training on GPU
   - Improves accuracy significantly

4. **Test different intervals:**
   - Run on 1h data (SPY 1h, QQQ 1h)
   - Run on crypto (BTC-USD 1d)
   - See if zero-shot generalizes

5. **Benchmark latency:**
   - Log inference time for different window sizes
   - Ensure it fits trading schedule (hourly forecasts OK, 1min risky)

---

## Troubleshooting

### Error: "timesfm not installed"

```bash
pip install timesfm[torch]
```

### Error: "CUDA out of memory"

Option A: Use CPU (slower)
```python
model = model.to('cpu')
```

Option B: Use half precision
```python
model = model.half()
```

Option C: Reduce batch size
```python
# Process one ticker at a time instead of multiple
```

### Error: "Model download timeout"

First run downloads ~500MB from Hugging Face. If network is slow:

```bash
# Manual download (run once)
python3 -c "from transformers import AutoModel; \
AutoModel.from_pretrained('google/timesfm-2.5-200m-pytorch')"

# Then script will use cached version
```

### Forecast looks wrong (NaN or all zeros)

- Check that Close prices are non-zero
- Check that series has no gaps (holidays/weekends)
- yfinance should handle this, but verify with: `print(data['Close'].describe())`

---

## Files Created

- `scripts/timesfm_poc.py` — Main evaluation script
- `scripts/TIMESFM_GUIDE.md` — This file
- (Future) `models/timesfm_predictor.py` — Integration module
- (Future) `scripts/train_timesfm_lora.py` — Fine-tuning script

---

## References

- GitHub: https://github.com/google-research/timesfm
- Hugging Face: https://huggingface.co/google/timesfm-2.5-200m-pytorch
- Paper: TimesFM arxiv (search arXiv for exact citation)
- Google Blog: https://research.google/blog/a-decoder-only-foundation-model-for-time-series-forecasting/

---

## Questions?

If POC results are promising, next conversation can focus on:
1. Integration into `signals/pipeline.py`
2. Fine-tuning if needed
3. Ensemble weighting with XGBoost
4. Latency optimization for production
