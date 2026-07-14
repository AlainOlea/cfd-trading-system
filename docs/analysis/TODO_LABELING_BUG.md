# TODO: Fix Binary Label Forward-Looking Bug

## Bug Description

**File**: `models/xgboost_model.py:232`
**Current code**:
```python
ret = df_aligned['close'].pct_change(-1).shift(1) * -1
```

**Problem**: Computes backward-looking return (what happened BEFORE bar i), not forward-looking (what happens AFTER bar i).

**Impact**: Model learns to classify past momentum (trivial) instead of predicting future direction (useful). Inflated accuracy (~91% vs expected ~55-65%).

## Sources

| Source | What it says |
|--------|-------------|
| **López de Prado (2018)** *Advances in Financial Machine Learning* | Triple barrier labels look forward `for j in range(i+1, horizon)` — our implementation is correct |
| **Jansen (2023)** *ML for Trading, 3rd ed.* + `ml4t-engineer` lib | Fixed time horizon: "compute **forward returns** over a fixed horizon." Rolling percentile: "binary signals based on whether **forward returns** exceed threshold" |
| **Piovezan et al. (2023)** *Computational Economics* | Binary threshold labels (≥0.5% min move) — paper behind paywall, but methodology references forward returns |
| **Our docs** `ML_RESEARCH.md:173` | "V3 (binary threshold): `ret > ±0.5%`" — intent is forward-looking, implementation is backward |

## The Fix

```python
# Bug (backward-looking):
ret = df_aligned['close'].pct_change(-1).shift(1) * -1

# Fix (forward-looking):
ret = df_aligned['close'].pct_change(1).shift(-1)
```

**Location**: `models/xgboost_model.py:232` (inside `prepare_cross_sectional()`)

## Affected Models (all use `use_binary_threshold=True`)

| Model | File | Needs retrain |
|-------|------|---------------|
| `all_tickers_1m_xgb` | models/saved/ | Yes |
| `all_tickers_1h_xgb` | models/saved/ | Yes |
| `all_tickers_1d_xgb` | models/saved/ | Yes |
| Per-ticker 1h models (SPY, QQQ, etc.) | models/saved/ | Yes |

## Execution Steps

1. Fix label computation in `models/xgboost_model.py:232`
2. Retrain all models:
   ```bash
   python3 main.py train-xgb-cross --interval 1m --from-csv
   python3 main.py train-xgb-cross --interval 1h --from-csv
   python3 main.py train-xgb-cross --interval 1d --from-csv
   ```
3. Compare metrics — expect lower accuracy (55-65%) but more honest evaluation
4. Test pipeline — run `python3 main.py pipeline --ticker SPY --no-telegram` and verify signals are reasonable
5. Run tests — `pytest tests/ -v` to ensure no regressions

## Expected Outcomes

| Metric | Before (buggy) | After (fixed) |
|--------|-----------------|---------------|
| Accuracy | ~91% | ~55-65% |
| Train samples | 35K (1m) | Fewer (forward labels drop trailing bars) |
| Signal quality | Classifies past momentum | Predicts future direction |
| Trading performance | Unknown | Should improve (labels match reality) |

## Risk

User may revert if model behavior degrades. The fix is a single line change, easily revertable.
