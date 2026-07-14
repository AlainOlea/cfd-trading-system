# Scripts archivados

Estos scripts son experimentos y utilidades de entrenamiento de la era LSTM+Transformer
(9 modelos, `models/hybrid_model.py`), superada por XGBoost como modelo primario
(`PRIMARY_ML_MODEL = 'xgboost'` en `config/settings.py`) y validado por TimesFM.

No se borraron porque el historial de git ya los preserva, pero **no son parte del
flujo vigente** — no ejecutarlos esperando que reflejen el sistema actual. Para
entrenamiento/análisis actual, ver `scripts/fetch_historical_bulk.py`,
`scripts/train_timesfm_lora.py`, y el comando `main.py train-xgb-cross`.

| Script | Qué hacía |
|---|---|
| `backfill_model_metadata.py` | Migración de una sola vez (ya aplicada) para agregar campos a metadata.json de 19 modelos LSTM |
| `baseline_ml_backtest.py` | OOS financial backtest para modelos LSTM/Transformer ya entrenados — huérfano tras retirar `models/trainer.py` (Fase 4 de la limpieza arquitectónica) |
| `check_training_progress.py` | Monitor de entrenamiento LSTM, superado por `view_training_summary.py` (también archivado) |
| `compare_lstm_xgboost.py` | Comparación LSTM vs XGBoost — la decisión ya se tomó (XGBoost ganó) |
| `improve_best_models.py` | Reentrenamiento puntual de modelos LSTM específicos (GLD/MSFT/QQQ) |
| `timesfm_poc.py` | Prueba de concepto de TimesFM, superada por `models/timesfm_predictor.py` (producción) |
| `train_all_models.py` | Entrena `HybridLSTMTransformer` por ticker |
| `train_ensemble_models.py` | Entrena LSTM 1h + XGBoost para el ensemble (ver `models/ensemble_predictor.py`, también desconectado) |
| `train_intraday_expansion.py` | Expansión de entrenamiento intradía, experimento de una sola vez |
| `train_multi_ticker.py` / `train_multi_ticker_optimized.py` | Entrenador walk-forward de `HybridLSTMTransformer` multi-ticker (v1/v2) |
| `train_multiperiod_models.py` | Entrena `HybridLSTMTransformer` por timeframe |
| `verify_ml_improvements.py` | Verificación de mejoras del pipeline de reentrenamiento LSTM |
| `view_training_summary.py` | Resumen de entrenamiento LSTM, overlap con `check_training_progress.py` |
