"""
Price Predictor Module
=======================
Uses trained LSTM+Transformer model to predict price direction
and filter trading signals.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

from config.settings import ML_CONFIG, SIGNAL_CONFIDENCE_HIGH
from models.trainer import ModelTrainer

logger = logging.getLogger(__name__)


class PricePredictor:
    """Predicts price direction using a trained hybrid model."""

    def __init__(self, confidence_threshold: float = SIGNAL_CONFIDENCE_HIGH):
        self.confidence_threshold = confidence_threshold
        self._model = None
        self._scaler = None
        self._meta = None

    def load(self, ticker: str, interval: str = '1d') -> None:
        """Load a trained model for a specific ticker.

        Args:
            ticker: Ticker symbol.
            interval: Data interval.
        """
        self._model, self._scaler, self._meta = ModelTrainer.load_model(ticker, interval)
        logger.info(f"Predictor loaded for {ticker} ({interval})")

    def predict_next(self, df: pd.DataFrame) -> dict[str, Any]:
        """Predict the next price direction from a DataFrame.

        Args:
            df: DataFrame with OHLCV + indicator columns.
                Must have at least lookback_window rows after dropping NaN.

        Returns:
            Dict with 'direction' (BUY/SELL), 'confidence' (0-1),
            'probability' (raw sigmoid output).
        """
        if self._model is None or self._meta is None:
            raise RuntimeError("No model loaded. Call load(ticker, interval) first.")

        features = self._meta['features']
        lookback = self._meta['lookback_window']

        # Select features
        available = [f for f in features if f in df.columns]
        if len(available) != len(features):
            missing = set(features) - set(available)
            raise ValueError(f"Missing features in DataFrame: {missing}")

        data = df[features].dropna()
        if len(data) < lookback:
            raise ValueError(
                f"Not enough data: {len(data)} rows, need {lookback}"
            )

        # Take the last lookback_window rows
        window = data.iloc[-lookback:].values.astype(np.float32)

        # Normalize with the saved scaler
        window = self._scaler.transform(window)

        # Reshape for model: (1, lookback_window, n_features)
        X = window.reshape(1, lookback, len(features))

        # Predict
        probability = self._model.predict(X)

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
        }

        logger.info(f"Prediction: {direction} (conf={confidence:.4f}, prob={probability:.4f})")
        return result

    def filter_signal(self, signal_direction: str, prediction: dict[str, Any]) -> dict[str, Any]:
        """Filter a trading signal using ML prediction.

        If ML disagrees with the signal or confidence is below threshold,
        the signal is rejected.

        Args:
            signal_direction: Original signal direction (BUY/SELL/HOLD).
            prediction: Dict from predict_next().

        Returns:
            Dict with 'accepted' (bool), 'reason' (str),
            'ml_direction', 'ml_confidence'.
        """
        ml_direction = prediction['direction']
        ml_confidence = prediction['confidence']

        result = {
            'ml_direction': ml_direction,
            'ml_confidence': ml_confidence,
            'original_signal': signal_direction,
        }

        if signal_direction == 'HOLD':
            result['accepted'] = True
            result['reason'] = 'HOLD signal - no ML filter needed'
            return result

        if ml_direction != signal_direction:
            result['accepted'] = False
            result['reason'] = f'ML disagrees: signal={signal_direction}, ML={ml_direction}'
            return result

        if ml_confidence < self.confidence_threshold:
            result['accepted'] = False
            result['reason'] = f'ML confidence too low: {ml_confidence:.1%} < {self.confidence_threshold:.1%}'
            return result

        result['accepted'] = True
        result['reason'] = f'ML confirms {signal_direction} with {ml_confidence:.1%} confidence'
        return result
