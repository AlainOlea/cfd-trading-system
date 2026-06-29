"""
XGBoost Model for Price Direction Prediction
==============================================
Primary ML model. Tree-based, regularized, outperforms LSTM on small
datasets (Piovezan et al. 2023, Henriques & Sadorsky 2023).

Supports cross-sectional training (all tickers pooled) and triple-barrier
labels (Lopez de Prado method).
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import MinMaxScaler

from config.settings import (
    ML_CONFIG, MODELS_SAVED_DIR, TRIPLE_BARRIER_CONFIG,
    XGBOOST_CONFIG, ML_PROMOTION_GATE, ML_SIGNAL_THRESHOLDS,
    COMMISSION, INITIAL_CAPITAL, SLIPPAGE,
)

logger = logging.getLogger(__name__)


def _triple_barrier_labels(
    df: pd.DataFrame,
    profit_factor: float = 2.0,
    stop_factor: float = 1.0,
    time_horizon: int = 5,
) -> np.ndarray:
    """Create labels using the triple-barrier method (Lopez de Prado).

    For each bar i, looks forward up to `time_horizon` bars.
    Label = +1 if upper barrier (profit) is touched first,
           -1 if lower barrier (stop) is touched first,
            0 if time expires without touching either.

    Barriers are dynamic: profit = entry + profit_factor × ATR,
    stop = entry - stop_factor × ATR.

    Args:
        df: DataFrame with 'close' and 'atr' columns.
        profit_factor: Multiplier on ATR for profit target.
        stop_factor: Multiplier on ATR for stop loss.
        time_horizon: Maximum bars to look forward.

    Returns:
        Array of labels (-1, 0, +1) aligned with df index.
    """
    close = df['close'].values
    atr = df['atr'].values if 'atr' in df.columns else np.full(len(df), df['close'].std())
    n = len(df)
    labels = np.zeros(n, dtype=np.float32)

    for i in range(n - 1):
        entry = close[i]
        vol = atr[i]
        if vol <= 0:
            continue

        upper = entry + profit_factor * vol
        lower = entry - stop_factor * vol
        horizon = min(i + time_horizon + 1, n)

        for j in range(i + 1, horizon):
            if close[j] >= upper:
                labels[i] = 2.0  # 2 = up (XGBoost expects 0/1/2)
                break
            elif close[j] <= lower:
                labels[i] = 0.0  # 0 = down
                break
        else:
            labels[i] = 1.0  # 1 = neutral (time expired)

    return labels


class XGBoostTrader:
    """XGBoost model with cross-sectional training and triple-barrier labels."""

    def __init__(
        self,
        n_estimators: int = XGBOOST_CONFIG['n_estimators'],
        max_depth: int = XGBOOST_CONFIG['max_depth'],
        learning_rate: float = XGBOOST_CONFIG['learning_rate'],
        subsample: float = XGBOOST_CONFIG['subsample'],
        colsample_bytree: float = XGBOOST_CONFIG['colsample_bytree'],
        min_child_weight: int = XGBOOST_CONFIG['min_child_weight'],
        reg_alpha: float = XGBOOST_CONFIG['reg_alpha'],
        reg_lambda: float = XGBOOST_CONFIG['reg_lambda'],
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.min_child_weight = min_child_weight
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda

        self.model = None
        self.scaler = MinMaxScaler()
        self.feature_names = None
        self._test_close = None
        self._test_index = None

    def build(self):
        self.model = xgb.XGBClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            min_child_weight=self.min_child_weight,
            reg_alpha=self.reg_alpha,
            reg_lambda=self.reg_lambda,
            random_state=42,
            eval_metric=XGBOOST_CONFIG['eval_metric'],
            verbosity=0,
        )
        logger.info(
            f"XGBoost built: {self.n_estimators} trees, depth={self.max_depth}, "
            f"lr={self.learning_rate}, min_child_weight={self.min_child_weight}, "
            f"alpha={self.reg_alpha}, lambda={self.reg_lambda}"
        )

    def prepare_data(self, df: pd.DataFrame, use_triple_barrier: bool = True) -> tuple:
        """Prepare data for single-ticker XGBoost training.

        Args:
            df: DataFrame with OHLCV + indicators + engineered features.
            use_triple_barrier: Use triple-barrier labels instead of next-bar direction.

        Returns:
            (X_train, y_train, X_test, y_test) with numpy arrays and scaler.
        """
        features = ML_CONFIG['features']
        available = [f for f in features if f in df.columns]

        X = df[available].dropna()
        if 'close' in df.columns:
            df_subset = df.loc[X.index]
        else:
            df_subset = df.loc[X.index] if len(df) == len(X) else df.iloc[:len(X)]

        if use_triple_barrier and 'atr' in df_subset.columns:
            raw_labels = _triple_barrier_labels(
                df_subset,
                TRIPLE_BARRIER_CONFIG['profit_factor'],
                TRIPLE_BARRIER_CONFIG['stop_factor'],
                TRIPLE_BARRIER_CONFIG['time_horizon'],
            )
            y = pd.Series(raw_labels, index=df_subset.index)
        else:
            y = (df_subset['close'].shift(-1) > df_subset['close']).astype(int)

        y = y.loc[X.index]

        # Remove tail rows that can't have labels
        horizon = TRIPLE_BARRIER_CONFIG['time_horizon'] if use_triple_barrier else 1
        X = X.iloc[:-horizon]
        y = y.iloc[:-horizon]

        if len(X) < 20:
            raise ValueError(f"Not enough data: {len(X)} rows")

        split_idx = int(len(X) * (1 - ML_CONFIG['test_split']))

        X_train_raw = X.iloc[:split_idx].values.astype(np.float32)
        X_test_raw = X.iloc[split_idx:].values.astype(np.float32)
        y_train = y.iloc[:split_idx].values
        y_test = y.iloc[split_idx:].values

        X_train = self.scaler.fit_transform(X_train_raw)
        X_test = self.scaler.transform(X_test_raw)

        self.feature_names = available
        self._test_close = df_subset['close'].iloc[split_idx:split_idx + len(y_test)] if 'close' in df_subset.columns else None
        self._test_index = self._test_close.index if self._test_close is not None else None

        logger.info(
            f"Data prepared: train={len(X_train)}, test={len(X_test)}, "
            f"features={len(available)}, triple_barrier={use_triple_barrier}"
        )
        return X_train, y_train, X_test, y_test

    def prepare_cross_sectional(
        self,
        ticker_dfs: dict[str, pd.DataFrame],
        use_triple_barrier: bool = True,
    ) -> tuple:
        """Pool data from multiple tickers into one training set.

        This implements the cross-sectional approach recommended by
        Alzaman (2024) and Byun et al. (2024): one model trained on
        all assets together captures common patterns while avoiding
        overfitting to individual ticker noise.

        When TRIPLE_BARRIER_CONFIG['use_binary_threshold'] is True,
        uses binary labels with a cost-aware threshold instead of
        triple-barrier. Per Piovezan et al. (2023), binary labels with
        an economic threshold outperform triple-barrier on small datasets.

        Args:
            ticker_dfs: Dict mapping ticker -> DataFrame with indicators.
            use_triple_barrier: Use triple-barrier or binary threshold labels.

        Returns:
            (X_train, y_train, X_test, y_test).
        """
        features = ML_CONFIG['features']
        train_parts = []
        test_parts = []
        use_binary = TRIPLE_BARRIER_CONFIG.get('use_binary_threshold', False)
        threshold = TRIPLE_BARRIER_CONFIG.get('binary_threshold', 0.005)

        for ticker, df in ticker_dfs.items():
            available = [f for f in features if f in df.columns]
            if len(available) < len(features) * 0.7:
                logger.warning(f"{ticker}: only {len(available)}/{len(features)} features, skipping")
                continue

            X = df[available].dropna()
            df_aligned = df.loc[X.index]

            if use_binary:
                ret = df_aligned['close'].pct_change(1).shift(-1)
                y = pd.Series(0, index=df_aligned.index)
                y[ret > threshold] = 1
                y[ret < -threshold] = 0
                mask = (ret > threshold) | (ret < -threshold)
                X = X[mask]
                y = y[mask]
            elif use_triple_barrier and 'atr' in df_aligned.columns:
                raw_labels = _triple_barrier_labels(
                    df_aligned,
                    TRIPLE_BARRIER_CONFIG['profit_factor'],
                    TRIPLE_BARRIER_CONFIG['stop_factor'],
                    TRIPLE_BARRIER_CONFIG['time_horizon'],
                )
                y = pd.Series(raw_labels, index=df_aligned.index)
                y = y.loc[X.index]
                horizon = TRIPLE_BARRIER_CONFIG['time_horizon']
                X = X.iloc[:-horizon]
                y = y.iloc[:-horizon]
            else:
                y = (df_aligned['close'].shift(-1) > df_aligned['close']).astype(int)

            y = y.loc[X.index]

            if len(X) < 20:
                continue

            split_idx = int(len(X) * (1 - ML_CONFIG['test_split']))

            train_parts.append((X.iloc[:split_idx].values.astype(np.float32), y.iloc[:split_idx].values))
            test_parts.append((X.iloc[split_idx:].values.astype(np.float32), y.iloc[split_idx:].values))

        if not train_parts:
            raise ValueError("No ticker had sufficient data for cross-sectional training")

        X_train_raw = np.vstack([p[0] for p in train_parts])
        y_train = np.concatenate([p[1] for p in train_parts])
        X_test_raw = np.vstack([p[0] for p in test_parts])
        y_test = np.concatenate([p[1] for p in test_parts])

        X_train = self.scaler.fit_transform(X_train_raw)
        X_test = self.scaler.transform(X_test_raw)

        self.feature_names = features

        n_classes = len(np.unique(y_train))
        if n_classes == 2:
            label_desc = f"{np.mean(y_train == 1):.1%} up / {np.mean(y_train == 0):.1%} down"
        else:
            label_desc = f"{np.mean(y_train == 2):.1%} up / {np.mean(y_train == 0):.1%} down / {np.mean(y_train == 1):.1%} neutral"

        logger.info(
            f"Cross-sectional data: train={len(X_train)}, test={len(X_test)}, "
            f"features={len(features)}, tickers={len(train_parts)}, "
            f"labels={label_desc}, binary={use_binary}"
        )
        return X_train, y_train, X_test, y_test

    def train(self, X_train, y_train, epochs: int = None) -> dict:
        if self.model is None:
            self.build()

        # Compute class weights to handle imbalanced labels
        unique, counts = np.unique(y_train, return_counts=True)
        n_samples = len(y_train)
        sample_weights = np.ones(n_samples)
        for cls, count in zip(unique, counts):
            weight = n_samples / (len(unique) * count)
            sample_weights[y_train == cls] = weight

        self.model.fit(
            X_train, y_train,
            sample_weight=sample_weights,
            verbose=0
        )

        train_pred = self.model.predict(X_train)
        train_acc = (train_pred == y_train).mean()

        logger.info(f"Training complete: accuracy={train_acc:.4f}")
        return {'accuracy': train_acc}

    def evaluate(self, X_test, y_test) -> dict:
        if self.model is None:
            raise RuntimeError("Model not trained.")

        y_pred = self.model.predict(X_test)

        accuracy = (y_pred == y_test).mean()

        n_classes = len(np.unique(y_test))
        if n_classes == 2:
            tp = ((y_pred == 1) & (y_test == 1)).sum()
            fp = ((y_pred == 1) & (y_test == 0)).sum()
            fn = ((y_pred == 0) & (y_test == 1)).sum()
            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
        else:
            pos_mask_test = (y_test == 2)
            pos_mask_pred = (y_pred == 2)
            tp = (pos_mask_pred & pos_mask_test).sum()
            precision = tp / max(pos_mask_pred.sum(), 1)
            recall = tp / max(pos_mask_test.sum(), 1)

        metrics = {
            'accuracy': float(accuracy),
            'precision': float(precision),
            'recall': float(recall),
        }

        # Per-class metrics for 3-class models (bearish=0, neutral=1, bullish=2)
        if n_classes >= 2:
            classes = sorted(np.unique(y_test))
            class_names = {0: 'bearish', 1: 'neutral', 2: 'bullish'}
            per_class = {}
            for cls in classes:
                name = class_names.get(cls, str(cls))
                cls_support = int((y_test == cls).sum())
                cls_tp = int(((y_pred == cls) & (y_test == cls)).sum())
                cls_fp = int(((y_pred == cls) & (y_test != cls)).sum())
                cls_fn = int(((y_test == cls) & (y_pred != cls)).sum())
                cls_precision = cls_tp / max(cls_tp + cls_fp, 1)
                cls_recall = cls_tp / max(cls_tp + cls_fn, 1)
                cls_f1 = 2 * cls_precision * cls_recall / max(cls_precision + cls_recall, 1e-9)
                per_class[name] = {
                    'precision': round(cls_precision, 4),
                    'recall': round(cls_recall, 4),
                    'f1': round(cls_f1, 4),
                    'support': cls_support,
                }
            metrics['per_class'] = per_class

            # Class distribution (check for dominant-class accuracy inflation)
            total = len(y_test)
            dist = {class_names.get(c, str(c)): int((y_test == c).sum()) / total
                    for c in classes}
            metrics['class_distribution'] = {k: round(v, 4) for k, v in dist.items()}

            # Confusion matrix
            cm = {}
            for true_cls in classes:
                true_name = class_names.get(true_cls, str(true_cls))
                cm[true_name] = {}
                for pred_cls in classes:
                    pred_name = class_names.get(pred_cls, str(pred_cls))
                    cm[true_name][pred_name] = int(((y_test == true_cls) & (y_pred == pred_cls)).sum())
            metrics['confusion_matrix'] = cm

            # Dominant class baseline accuracy
            max_class_pct = max(dist.values())
            metrics['dominant_class_accuracy'] = round(max_class_pct, 4)
            if accuracy < max_class_pct + 0.05:
                logger.warning(
                    f"Model accuracy ({accuracy:.4f}) is near or below dominant class "
                    f"baseline ({max_class_pct:.4f}). Model may be predicting the majority class."
                )

        logger.info(f"Eval: acc={accuracy:.4f} prec={precision:.4f} rec={recall:.4f}")
        return metrics

    def get_feature_importance(self) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("Model not trained.")

        importance = self.model.feature_importances_
        df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': importance,
        }).sort_values('importance', ascending=False)
        df['percentage'] = (df['importance'] / df['importance'].sum()) * 100
        return df

    def predict(self, X: np.ndarray) -> float:
        if self.model is None:
            raise RuntimeError("Model not trained.")
        if X.ndim == 1:
            X = X.reshape(1, -1)
        proba = self.model.predict_proba(X)
        if proba.shape[1] == 2:
            return float(proba[0, 1])
        elif proba.shape[1] == 3:
            return float(proba[0, 2] - proba[0, 0])
        return float(proba[0, -1])

    def save(self, ticker: str, interval: str = '1d') -> Path:
        if self.model is None:
            raise RuntimeError("No model to save.")
        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        model_dir = MODELS_SAVED_DIR / f"{safe_ticker}_{interval}_xgb"
        model_dir.mkdir(parents=True, exist_ok=True)

        self.model.save_model(str(model_dir / "model.json"))

        import joblib
        joblib.dump(self.scaler, str(model_dir / "scaler.pkl"))

        metadata = {
            'ticker': ticker,
            'interval': interval,
            'model_type': 'xgboost',
            'features': self.feature_names,
            'n_features': len(self.feature_names) if self.feature_names else 0,
            'n_estimators': self.n_estimators,
            'max_depth': self.max_depth,
            'learning_rate': self.learning_rate,
            'min_child_weight': self.min_child_weight,
            'trained_at': pd.Timestamp.now().isoformat(),
        }
        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"XGBoost model saved to {model_dir}")
        return model_dir

    @staticmethod
    def load(ticker: str, interval: str = '1d') -> tuple:
        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        model_dir = MODELS_SAVED_DIR / f"{safe_ticker}_{interval}_xgb"

        if not model_dir.exists():
            raise FileNotFoundError(f"No saved model found at {model_dir}")

        model = xgb.XGBClassifier()
        model.load_model(str(model_dir / "model.json"))

        import joblib
        scaler = joblib.load(str(model_dir / "scaler.pkl"))

        with open(model_dir / "metadata.json") as f:
            metadata = json.load(f)

        logger.info(f"XGBoost model loaded from {model_dir}")
        return model, scaler, metadata


class XGBoostPredictor:
    """Wrapper for XGBoost predictions in signal filtering."""

    def __init__(self, confidence_threshold: float = 0.55):
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.scaler = None
        self.metadata = None

    def load(self, ticker: str, interval: str = '1d') -> None:
        self.model, self.scaler, self.metadata = XGBoostTrader.load(ticker, interval)
        logger.info(f"XGBoost predictor loaded for {ticker} ({interval})")

    def predict_next(self, df: pd.DataFrame) -> dict[str, Any]:
        if self.model is None:
            raise RuntimeError("No model loaded.")

        features = self.metadata.get('features', ML_CONFIG['features'])
        available = [f for f in features if f in df.columns]
        data = df[available].dropna()

        if len(data) < 1:
            raise ValueError("Not enough data")

        X = data.iloc[-1:].values.astype(np.float32)
        X_scaled = self.scaler.transform(X)

        proba = self.model.predict_proba(X_scaled)
        if proba.shape[1] == 3:
            p_up = proba[0, 2]
            p_down = proba[0, 0]
            if p_up > p_down and p_up > 0.4:
                direction = 'BUY'
                confidence = p_up
            elif p_down > p_up and p_down > 0.4:
                direction = 'SELL'
                confidence = p_down
            else:
                direction = 'HOLD'
                confidence = max(p_up, p_down)
        else:
            # Binary: 0=down, 1=up
            probability = float(proba[0, 1])
            if probability > 0.55:
                direction = 'BUY'
                confidence = probability
            elif probability < 0.45:
                direction = 'SELL'
                confidence = 1 - probability
            else:
                direction = 'HOLD'
                confidence = max(probability, 1 - probability)
            probability = proba[0, 1]
            direction = 'BUY' if probability > 0.5 else 'SELL'
            confidence = probability if probability > 0.5 else 1 - probability

        return {
            'direction': direction,
            'confidence': round(float(confidence), 4),
            'probability': round(float(proba[0, 1]) if proba.shape[1] == 2 else max(proba[0, 2], proba[0, 0]), 4),
            'model': 'xgboost',
        }

    def filter_signal(self, signal_direction: str, prediction: dict[str, Any]) -> dict[str, Any]:
        xgb_dir = prediction['direction']
        xgb_conf = prediction['confidence']

        result = {
            'xgb_direction': xgb_dir,
            'xgb_confidence': xgb_conf,
            'original_signal': signal_direction,
        }

        if signal_direction == 'HOLD':
            result['accepted'] = True
            result['reason'] = 'HOLD signal - no XGBoost filter needed'
            return result

        if xgb_dir == 'HOLD':
            result['accepted'] = False
            result['reason'] = 'XGBoost neutral — insufficient conviction'
            return result

        if xgb_dir != signal_direction:
            result['accepted'] = False
            result['reason'] = f'XGBoost disagrees: signal={signal_direction}, XGB={xgb_dir}'
            return result

        if xgb_conf < self.confidence_threshold:
            result['accepted'] = False
            result['reason'] = f'XGBoost confidence too low: {xgb_conf:.1%}'
            return result

        result['accepted'] = True
        result['reason'] = f'XGBoost confirms {signal_direction} with {xgb_conf:.1%}'
        return result
