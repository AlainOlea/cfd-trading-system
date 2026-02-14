"""
XGBoost Model for Price Direction Prediction
==============================================
Fast, interpretable ensemble model for trading signal filtering.
Alternative to LSTM with feature importance analysis.
"""

import logging
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import MinMaxScaler

from config.settings import ML_CONFIG, MODELS_SAVED_DIR

logger = logging.getLogger(__name__)


class XGBoostTrader:
    """XGBoost model for price direction prediction with feature importance."""

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 5,
        learning_rate: float = 0.1,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
    ):
        """Initialize XGBoost model."""
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree

        self.model = None
        self.scaler = MinMaxScaler()
        self.feature_names = None

    def build(self):
        """Build XGBoost classifier."""
        self.model = xgb.XGBClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            random_state=42,
            use_label_encoder=False,
            eval_metric='logloss',
            verbosity=0,
        )
        logger.info(f"XGBoost built: {self.n_estimators} estimators, depth={self.max_depth}")

    def prepare_data(self, df: pd.DataFrame) -> tuple:
        """Prepare data for XGBoost training.

        Args:
            df: DataFrame with OHLCV + indicators

        Returns:
            Tuple of (X_train, y_train, X_test, y_test, scaler)
        """
        features = ML_CONFIG['features']

        # Select features
        X = df[features].dropna()

        # Create target: 1 if next close > current close
        y = (df['close'].shift(-1) > df['close']).astype(int)

        # Align X and y
        valid_idx = X.index.intersection(y.index)
        X = X.loc[valid_idx]
        y = y.loc[valid_idx]

        # Remove last row (no future data for target)
        X = X.iloc[:-1]
        y = y.iloc[:-1]

        if len(X) < 20:
            raise ValueError(f"Not enough data: {len(X)} rows")

        # Normalize
        X_scaled = self.scaler.fit_transform(X)

        # Train/test split (chronological, not random)
        split_idx = int(len(X) * 0.85)
        X_train = X_scaled[:split_idx]
        y_train = y.iloc[:split_idx]
        X_test = X_scaled[split_idx:]
        y_test = y.iloc[split_idx:]

        self.feature_names = features

        logger.info(
            f"Data prepared: train={len(X_train)}, test={len(X_test)}, "
            f"features={len(features)}"
        )
        return X_train, y_train, X_test, y_test

    def train(self, X_train, y_train, epochs: int = 100) -> dict:
        """Train XGBoost model.

        Args:
            X_train: Training features
            y_train: Training targets
            epochs: Number of boosting rounds (n_estimators)

        Returns:
            Dict with training metrics
        """
        if self.model is None:
            self.build()

        self.model.fit(X_train, y_train, verbose=0)

        # Get training accuracy
        train_pred = self.model.predict(X_train)
        train_acc = (train_pred == y_train.values).mean()

        logger.info(f"Training complete: accuracy={train_acc:.4f}")
        return {'accuracy': train_acc}

    def evaluate(self, X_test, y_test) -> dict:
        """Evaluate model on test set.

        Args:
            X_test: Test features
            y_test: Test targets

        Returns:
            Dict with metrics
        """
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        y_pred = self.model.predict(X_test)
        y_pred_proba = self.model.predict_proba(X_test)[:, 1]

        accuracy = (y_pred == y_test.values).mean()
        precision = ((y_pred == 1) & (y_test.values == 1)).sum() / max((y_pred == 1).sum(), 1)
        recall = ((y_pred == 1) & (y_test.values == 1)).sum() / max((y_test.values == 1).sum(), 1)

        metrics = {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
        }

        logger.info(
            f"Evaluation: accuracy={accuracy:.4f}, "
            f"precision={precision:.4f}, recall={recall:.4f}"
        )
        return metrics

    def get_feature_importance(self) -> pd.DataFrame:
        """Get feature importance from trained model.

        Returns:
            DataFrame with feature importance scores and percentages
        """
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        importance = self.model.feature_importances_
        features = self.feature_names

        df = pd.DataFrame({
            'feature': features,
            'importance': importance,
        }).sort_values('importance', ascending=False)

        df['percentage'] = (df['importance'] / df['importance'].sum()) * 100

        return df

    def predict(self, X: np.ndarray) -> float:
        """Predict bullish probability for a single sample.

        Args:
            X: Features (should be normalized)

        Returns:
            Probability of bullish movement (0-1)
        """
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        if X.ndim == 1:
            X = X.reshape(1, -1)

        proba = self.model.predict_proba(X)[0, 1]
        return float(proba)

    def save(self, ticker: str, interval: str = '1d') -> Path:
        """Save model to disk.

        Args:
            ticker: Ticker symbol
            interval: Data interval

        Returns:
            Path to saved model directory
        """
        if self.model is None:
            raise RuntimeError("No model to save. Train first.")

        model_dir = MODELS_SAVED_DIR / f"{ticker}_{interval}_xgb"
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save model
        self.model.save_model(str(model_dir / "model.json"))

        # Save scaler
        import pickle
        with open(model_dir / "scaler.pkl", "wb") as f:
            pickle.dump(self.scaler, f)

        # Save metadata
        metadata = {
            'ticker': ticker,
            'interval': interval,
            'features': self.feature_names,
            'n_estimators': self.n_estimators,
            'max_depth': self.max_depth,
            'learning_rate': self.learning_rate,
        }
        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

        logger.info(f"XGBoost model saved to {model_dir}")
        return model_dir

    @staticmethod
    def load(ticker: str, interval: str = '1d') -> tuple:
        """Load a saved XGBoost model.

        Args:
            ticker: Ticker symbol
            interval: Data interval

        Returns:
            Tuple of (model, scaler, metadata)
        """
        model_dir = MODELS_SAVED_DIR / f"{ticker}_{interval}_xgb"

        if not model_dir.exists():
            raise FileNotFoundError(f"No saved model found at {model_dir}")

        # Load model
        model = xgb.XGBClassifier()
        model.load_model(str(model_dir / "model.json"))

        # Load scaler
        import pickle
        with open(model_dir / "scaler.pkl", "rb") as f:
            scaler = pickle.load(f)

        # Load metadata
        with open(model_dir / "metadata.json", "r") as f:
            metadata = json.load(f)

        logger.info(f"XGBoost model loaded from {model_dir}")
        return model, scaler, metadata


class XGBoostPredictor:
    """Wrapper for XGBoost predictions in signal filtering."""

    def __init__(self, confidence_threshold: float = 0.8):
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.scaler = None
        self.metadata = None

    def load(self, ticker: str, interval: str = '1d') -> None:
        """Load a trained XGBoost model."""
        self.model, self.scaler, self.metadata = XGBoostTrader.load(ticker, interval)
        logger.info(f"XGBoost predictor loaded for {ticker} ({interval})")

    def predict_next(self, df: pd.DataFrame) -> dict[str, Any]:
        """Predict price direction from DataFrame."""
        if self.model is None:
            raise RuntimeError("No model loaded. Call load(ticker, interval) first.")

        features = self.metadata['features']
        data = df[features].dropna()

        if len(data) < 1:
            raise ValueError("Not enough data in DataFrame")

        # Take last row and normalize
        X = data.iloc[-1:].values.astype(np.float32)
        X_scaled = self.scaler.transform(X)

        # Predict
        probability = self.model.predict_proba(X_scaled)[0, 1]

        # Interpret
        if probability > 0.5:
            direction = 'BUY'
            confidence = probability
        else:
            direction = 'SELL'
            confidence = 1 - probability

        result = {
            'direction': direction,
            'confidence': round(float(confidence), 4),
            'probability': round(float(probability), 4),
            'model': 'xgboost',
        }

        logger.info(f"XGBoost prediction: {direction} (conf={confidence:.4f})")
        return result

    def filter_signal(self, signal_direction: str, prediction: dict[str, Any]) -> dict[str, Any]:
        """Filter a signal using XGBoost prediction."""
        xgb_direction = prediction['direction']
        xgb_confidence = prediction['confidence']

        result = {
            'xgb_direction': xgb_direction,
            'xgb_confidence': xgb_confidence,
            'original_signal': signal_direction,
        }

        if signal_direction == 'HOLD':
            result['accepted'] = True
            result['reason'] = 'HOLD signal - no XGBoost filter needed'
            return result

        if xgb_direction != signal_direction:
            result['accepted'] = False
            result['reason'] = f'XGBoost disagrees: signal={signal_direction}, XGB={xgb_direction}'
            return result

        if xgb_confidence < self.confidence_threshold:
            result['accepted'] = False
            result['reason'] = f'XGBoost confidence too low: {xgb_confidence:.1%}'
            return result

        result['accepted'] = True
        result['reason'] = f'XGBoost confirms {signal_direction} with {xgb_confidence:.1%}'
        return result
