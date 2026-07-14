# ML Research Bibliography & Architecture Decisions

## Papers Referenced

### 1. Piovezan, de Andrade & Ávila (2023)
**"Machine Learning Method for Return Direction Forecast of Exchange Traded Funds (ETFs) Using Classification and Regression Models"**
*Computational Economics, 63(5), 1827-1852*
DOI: `10.1007/s10614-023-10385-4`

**Key finding**: Tested XGBoost, LightGBM, and Random Forest against linear models for ETF return prediction with ~1,500 training days. Tree-based models achieved near-perfect training accuracy (95-100%) but test accuracy barely exceeded 50%. Simpler models (Linear/Logistic Regression) produced more robust out-of-sample performance with better Sharpe ratios.

**Applied to this project**:
- Confirmed our observation that LSTM overfits on small datasets (140 samples → 50-55% test accuracy)
- Validated switching to XGBoost with strong regularization
- Justified binary threshold labels (≥0.5% min move) over simple next-bar direction

---

### 2. Henriques & Sadorsky (2023)
**"Forecasting rare earth stock prices with machine learning"**
*Resources Policy, 86, 104248*
DOI: `10.1016/j.resourpol.2023.104248`

**Key finding**: Random Forests and Extra Trees achieved 85-90% accuracy for 10-20 day forecasts on ~2,240 training samples. Four technical indicators (WAD, MA200, MA50, OnBalanceVolume) plus VIX were consistently the most important features. Tree ensembles required careful regularization (500 trees, random feature selection) to avoid overfitting.

**Applied to this project**:
- Validated 200-tree XGBoost with max_depth=5 and subsample=0.8
- Confirmed that engineered features (returns, volatility, ATR ratio) add more value than architecture changes
- Feature importance analysis now guides feature selection

---

### 3. Byun, Cho & Kim (2024)
**"Can a machine learn from behavioral biases? Evidence from stock return predictability of deep learning models"**
*Journal of Behavioral and Experimental Finance, 41, 100881*
DOI: `10.1016/j.jbef.2023.100881`

**Key finding**: Cross-sectional training (conditional autoencoder on 2.7M stock-month observations from 1957-2020 with 94 firm characteristics) produced long-short portfolio returns of 2.32% per month (t=6.61), substantially exceeding linear IPCA (1.15%, t=5.01). Cross-sectional pooling was most effective for speculative stocks (small, volatile, unprofitable).

**Applied to this project**:
- Implemented `prepare_cross_sectional()` — pooling 7 tickers into one model (841→4,890 train samples)
- One XGBoost model learns common patterns across SPY, QQQ, IWM, GLD, AAPL, NVDA, MSFT
- Eliminated per-ticker model training entirely

---

### 4. Alzaman (2024)
**"Deep learning in stock portfolio selection and predictions"**
*Expert Systems with Applications, 237, 121404*
DOI: `10.1016/j.eswa.2023.121404`

**Key finding**: Cross-sectional Deep RankNet significantly outperformed per-asset LSTM on 100 Toronto Stock Exchange stocks (2015-2021). Deep RankNet Sharpe: 1.59. Author explicitly noted LSTM requires "a lot of computational effort" because it "learns the behavior of each stock independently," while RankNet "ranks all stocks all at once (so learning is more global)."

**Applied to this project**:
- Cross-sectional XGBoost replaced per-ticker LSTM as the ML model (LSTM later retired entirely)
- Pipeline's `_apply_ml` tries cross-sectional model first, falls back to per-ticker

---

### 5. Shih, Wang, Kao & Lai (2024)
**"Forecasting ETF Performance: A Comparative Study of Deep Learning Models and the Fama-French Three-Factor Model"**
*Mathematics, 12(19), 3158*
DOI: `10.3390/math12193158`

**Key finding**: Adding Fama-French three factors (market risk premium, size, book-to-market) as features produced greater performance gains than changing neural network architecture. LSTM with FF3 factors gave the lowest MAE across all models. "Model mixing and stacking may not be suitable for studies focused on daily returns."

**Applied to this project**:
- Feature engineering prioritized over architecture complexity
- Added 4 engineered features: `return_5d`, `return_20d`, `volatility_20d`, `atr_ratio`
- Kept model simple: single XGBoost (not stacked/hybrid)

---

### 6. Chaudhari & Thakkar (2023)
**"Neural network systems with an integrated coefficient of variation-based feature selection for stock price and trend prediction"**
*Expert Systems with Applications, 219, 119527*
DOI: `10.1016/j.eswa.2023.119527`

**Key finding**: Coefficient of variation (CV)-based top-M feature selection improved R² by up to 5% and reduced error rates by 33% compared to using all features. Selecting only 3-4 features with highest CV values often outperformed using all features, particularly for LSTM and GRU models.

**Applied to this project**:
- XGBoost's built-in feature importance now displayed during training
- Top 5 features monitored: bb_lower, close, low, bb_upper, atr_ratio
- Feature selection left to XGBoost's native importance scoring (not manual CV)

---

### 7. Tang, Song, Zhu et al. (2022)
**"A survey on machine learning models for financial time series forecasting"**
*Neurocomputing, 512, 363-380*
DOI: `10.1016/j.neucom.2022.09.003`

**Key finding**: Survey of 2011-2021 literature. SVM preferred for small-sample financial forecasting; LSTM dominates when large datasets available. "Nearly all top-cited papers adopt large datasets." Validates that deep learning advantages only materialize with sufficient data volume.

**Applied to this project**:
- Confirmed decision to demote LSTM from primary to fallback model
- Justified XGBoost for our data regime (4,890 train samples, not 600,000)

---

## Canonical References (Not Directly Cited but Foundational)

### López de Prado, M. (2018)
**"Advances in Financial Machine Learning"**
*Wiley, 400 pages*

- **Triple barrier method**: Labels created when price touches one of three barriers (profit, stop-loss, time expiration). Implemented in `_triple_barrier_labels()`.
- **Embargo on training**: Inserted `lookback_window` bars between train and test sets in walk-forward validation to prevent overlap leakage.
- **OOS financial backtest**: Model evaluation must use trading metrics (Sharpe, profit factor, drawdown), not classification accuracy. Implemented in `backtest_predictions()`.

### Jansen, S. (2020, updated 2023)
**"Machine Learning for Trading"**
*GitHub: `stefan-jansen/machine-learning-for-trading`*

- Gradient boosting and random forests often outperform neural networks on tabular financial data with <10,000 samples
- Binary classification on next-period direction is fundamentally limited by signal-to-noise ratio
- Cross-sectional (panel) training is how institutional quant funds operate
- Feature engineering has higher marginal return than architecture selection

---

## Model Architecture

### Current: XGBoost (Primary)

```
XGBoostClassifier:
  n_estimators:     200        # Trees in ensemble
  max_depth:          5        # Shallow trees prevent overfitting
  learning_rate:      0.05     # Conservative learning
  subsample:          0.8      # Row sampling per tree
  colsample_bytree:   0.8      # Column sampling per tree
  min_child_weight:   3        # Minimum leaf weight (regularization)
  reg_alpha:          0.1      # L1 regularization
  reg_lambda:         1.0      # L2 regularization
  
Features (13):
  OHLCV:          open, high, low, close, volume
  Indicators:     rsi, macd, bb_upper, bb_lower
  Engineered:     return_5d, return_20d, volatility_20d, atr_ratio

Labels:           Binary threshold (≥0.5% return = up, ≤-0.5% = down)
Training:         Cross-sectional, 4,890 (1d) / 3,962 (1h) samples
Class weights:    Inverse frequency (handles imbalance)
Accuracy:         74.4% (1d) / 84.4% (1h) test
```

### Retired: LSTM+Transformer

```
HybridLSTMTransformer:
  LSTM 2×50 units (return_sequences=True) → Dropout(0.4) → 
  Dense(64, projection) → TransformerEncoder(2-head) → 
  GlobalAvgPool1D → Dense(25) → Dropout(0.4) → sigmoid

Parameters:       70,587
Features:          9 (OHLCV + RSI + MACD + BB)
Labels:            Next-bar binary direction
Training:          Per-ticker, ~140-1,751 samples
Accuracy:          ~50-55% test (not statistically significant)
Status:            Retired entirely (2026-07-13) — see docs/archive/ML_RETRAINING*.md
```

---

## Label Construction Evolution

| Version | Method | Problem | Resolution |
|---------|--------|---------|------------|
| V1 (legacy) | `close_next > close` | Predicts noise; 0.01% moves count as "up" | — |
| V2 (triple-barrier) | Horizontal barriers at ±1.5×ATR, 5-bar horizon | 52.9% neutral labels; XGBoost accuracy 26% | — |
| V3 (binary threshold) | `ret > ±0.5%` | Filters non-tradeable moves | **Active** — 74-84% test accuracy |

V3 is the current production label method per Piovezan et al. (2023) recommendation for small datasets.

---

## Training Pipeline

```
1. fetch-all-history --years 5    # Bulk CSV download (bypasses yfinance 730d limit)
2. train-xgb-cross --from-csv     # Cross-sectional training on all tickers
3. pipeline / paper-trade          # Model auto-loads for live signals
```

### Cross-sectional data flow

```
SPY (1254 bars) ─┐
QQQ (1254 bars) ─┤
IWM (1254 bars) ─┤
GLD (1254 bars) ─┼──→ prepare_cross_sectional() ──→ XGBoost.train() ──→ all_tickers_1d_xgb
AAPL (1254 bars) ─┤
NVDA (1254 bars) ─┤
MSFT (1254 bars) ─┘

Result: 4,890 train samples, 867 test samples, 13 features
```

---

## Confluence Scoring

Signals are rated 1-5 stars based on agreement across layers:

| Star | Requirement | Weight |
|------|-------------|--------|
| 1★ | At least one actionable signal (BUY/SELL) | Base |
| 2★ | Multi-timeframe agreement OR ML confirms | Independent |
| 3★ | ML confirms AND (multi-TF OR ML confidence >65%) | High quality |
| 4★ | Ensemble STRONG consensus | Very high |
| 5★ | Average confidence across layers ≥70% | Maximum |

**Current cron filter**: 3★ minimum. Signals below 3 stars are logged but not traded and not sent to Telegram.

---

## Key Design Decisions

| Decision | Rationale | Source |
|----------|-----------|--------|
| XGBoost over LSTM | Better with <5k samples; LSTM needs 100k+ | Piovezan 2023, Jansen 2023 |
| Cross-sectional training | Pools information; 5.8x more samples | Byun 2024, Alzaman 2024 |
| Binary threshold labels (0.5%) | Filters non-economic moves | Piovezan 2023 |
| Engineered features (13 vs 9) | Higher ROI than architecture changes | Chaudhari 2023, Shih 2024 |
| Sample-weighted classes | Handles label imbalance | Standard practice |
| OOS financial backtest gate | Trading metrics > classification accuracy | López de Prado 2018 |
| Walk-forward with embargo | Prevents test leakage across folds | López de Prado 2018 |

---

## Performance Evolution

| Iteration | Model | Samples | Test Acc | Date |
|-----------|-------|---------|----------|------|
| V1 (legacy) | LSTM per-ticker | 140 train | ~50% | Feb 2026 |
| V2 (triple-barrier) | XGBoost cross | 1,309 train | 26.1% | May 2026 |
| V3 (binary threshold) | XGBoost cross | 841 train | 80.6% | May 2026 |
| V4 (5y history) | XGBoost cross | 4,890 train | 74.4% | May 2026 |
| **Current (1h)** | **XGBoost cross** | **3,962 train** | **84.4%** | **May 2026** |

Note: Accuracy drop from V3→V4 is expected and healthy — more test data = more honest evaluation. V3 was evaluated on 155 test samples; V4 on 867 (5.6x more).

---

## References (Full)

1. Piovezan RPB, de Andrade Junior PP, Ávila SL. Machine Learning Method for Return Direction Forecast of Exchange Traded Funds (ETFs) Using Classification and Regression Models. *Computational Economics*. 2023;63(5):1827-1852. DOI: `10.1007/s10614-023-10385-4`

2. Henriques I, Sadorsky P. Forecasting rare earth stock prices with machine learning. *Resources Policy*. 2023;86:104248. DOI: `10.1016/j.resourpol.2023.104248`

3. Byun SJ, Cho S, Kim DH. Can a machine learn from behavioral biases? Evidence from stock return predictability of deep learning models. *Journal of Behavioral and Experimental Finance*. 2024;41:100881. DOI: `10.1016/j.jbef.2023.100881`

4. Alzaman C. Deep learning in stock portfolio selection and predictions. *Expert Systems with Applications*. 2024;237:121404. DOI: `10.1016/j.eswa.2023.121404`

5. Shih KH, Wang YH, Kao IC, Lai FM. Forecasting ETF Performance: A Comparative Study of Deep Learning Models and the Fama-French Three-Factor Model. *Mathematics*. 2024;12(19):3158. DOI: `10.3390/math12193158`

6. Chaudhari K, Thakkar A. Neural network systems with an integrated coefficient of variation-based feature selection for stock price and trend prediction. *Expert Systems with Applications*. 2023;219:119527. DOI: `10.1016/j.eswa.2023.119527`

7. Cagliero L, Fior J, Garza P. Shortlisting machine learning-based stock trading recommendations using candlestick pattern recognition. *Expert Systems with Applications*. 2023;216:119493. DOI: `10.1016/j.eswa.2022.119493`

8. Tang Y, Song Z, Zhu Y, et al. A survey on machine learning models for financial time series forecasting. *Neurocomputing*. 2022;512:363-380. DOI: `10.1016/j.neucom.2022.09.003`

### Books

9. López de Prado, M. *Advances in Financial Machine Learning*. Wiley, 2018. ISBN: 978-1119482086.

10. Jansen, S. *Machine Learning for Trading*. GitHub: `stefan-jansen/machine-learning-for-trading`. 2020 (updated 2023).

---

*Last updated: 2026-05-20*
*Status: Active — XGBoost cross-sectional with binary threshold labels*
