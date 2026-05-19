"""
Ensemble Predictor: LSTM + XGBoost
===================================
Combines predictions from both LSTM and XGBoost for robust signal filtering.
Voting mechanism: accepts signals only when both models agree strongly.
"""

import logging
from typing import Any

import pandas as pd

from models.predictor import PricePredictor
from models.xgboost_model import XGBoostPredictor

logger = logging.getLogger(__name__)


class EnsemblePredictor:
    """Ensemble of LSTM + XGBoost for robust predictions."""

    def __init__(self, lstm_threshold: float = 0.8, xgb_threshold: float = 0.8):
        """Initialize ensemble predictor.

        Args:
            lstm_threshold: Confidence threshold for LSTM
            xgb_threshold: Confidence threshold for XGBoost
        """
        self.lstm_predictor = PricePredictor(confidence_threshold=lstm_threshold, allow_unpromoted=True)
        self.xgb_predictor = XGBoostPredictor(confidence_threshold=xgb_threshold)
        self.lstm_loaded = False
        self.xgb_loaded = False

    def load(self, ticker: str, interval: str = '1d', models: list = None) -> None:
        """Load both models.

        Args:
            ticker: Ticker symbol
            interval: Data interval
            models: List of models to load ['lstm', 'xgb']. Default: both
        """
        if models is None:
            models = ['lstm', 'xgb']

        if 'lstm' in models:
            try:
                self.lstm_predictor.load(ticker, interval)
                self.lstm_loaded = True
                logger.info(f"✅ LSTM loaded for {ticker} ({interval})")
            except Exception as e:
                logger.warning(f"⚠️  LSTM load failed: {e}")

        if 'xgb' in models:
            try:
                self.xgb_predictor.load(ticker, interval)
                self.xgb_loaded = True
                logger.info(f"✅ XGBoost loaded for {ticker} ({interval})")
            except Exception as e:
                logger.warning(f"⚠️  XGBoost load failed: {e}")

    def predict_next(self, df: pd.DataFrame) -> dict[str, Any]:
        """Get ensemble prediction from both models.

        Args:
            df: DataFrame with OHLCV + indicators

        Returns:
            Dict with 'lstm', 'xgb' predictions and 'ensemble' consensus
        """
        result = {
            'lstm': None,
            'xgb': None,
            'ensemble': None,
        }

        # LSTM prediction
        if self.lstm_loaded:
            try:
                result['lstm'] = self.lstm_predictor.predict_next(df)
            except Exception as e:
                logger.warning(f"LSTM prediction failed: {e}")

        # XGBoost prediction
        if self.xgb_loaded:
            try:
                result['xgb'] = self.xgb_predictor.predict_next(df)
            except Exception as e:
                logger.warning(f"XGBoost prediction failed: {e}")

        # Ensemble voting
        if result['lstm'] and result['xgb']:
            result['ensemble'] = self._ensemble_vote(result['lstm'], result['xgb'])
        elif result['lstm']:
            result['ensemble'] = {
                'direction': result['lstm']['direction'],
                'confidence': result['lstm']['confidence'] * 0.9,  # Penalize single model
                'reason': 'LSTM only (XGBoost unavailable)',
                'model_count': 1,
            }
        elif result['xgb']:
            result['ensemble'] = {
                'direction': result['xgb']['direction'],
                'confidence': result['xgb']['confidence'] * 0.9,  # Penalize single model
                'reason': 'XGBoost only (LSTM unavailable)',
                'model_count': 1,
            }

        return result

    def _ensemble_vote(self, lstm_pred: dict, xgb_pred: dict) -> dict:
        """Combine predictions from LSTM and XGBoost.

        Args:
            lstm_pred: LSTM prediction dict
            xgb_pred: XGBoost prediction dict

        Returns:
            Ensemble prediction dict
        """
        lstm_dir = lstm_pred['direction']
        xgb_dir = xgb_pred['direction']
        lstm_conf = lstm_pred['confidence']
        xgb_conf = xgb_pred['confidence']

        # Average confidence
        avg_confidence = (lstm_conf + xgb_conf) / 2

        if lstm_dir == xgb_dir:
            # Both agree
            confidence = max(lstm_conf, xgb_conf)  # Take stronger confidence
            consensus = 'STRONG'
        else:
            # Disagree
            confidence = min(lstm_conf, xgb_conf) * 0.5  # Penalize disagreement
            consensus = 'WEAK'
            # Take direction from more confident model
            lstm_dir = lstm_pred['direction'] if lstm_conf > xgb_conf else xgb_pred['direction']

        result = {
            'direction': lstm_dir,
            'confidence': min(confidence, 0.95),  # Cap at 95%
            'consensus': consensus,
            'lstm_confidence': lstm_conf,
            'xgb_confidence': xgb_conf,
            'avg_confidence': avg_confidence,
            'model_count': 2,
            'reason': f"Ensemble ({consensus}): LSTM {lstm_pred['direction']} "
                     f"({lstm_conf:.2%}) + XGB {xgb_pred['direction']} ({xgb_conf:.2%})",
        }

        return result

    def filter_signal(self, signal_direction: str, df: pd.DataFrame) -> dict[str, Any]:
        """Filter a trading signal using ensemble prediction.

        Args:
            signal_direction: Original signal (BUY/SELL/HOLD)
            df: DataFrame for prediction

        Returns:
            Dict with filtering result
        """
        if signal_direction == 'HOLD':
            return {
                'accepted': True,
                'reason': 'HOLD signal - no ensemble filter needed',
                'original_signal': signal_direction,
            }

        # Get ensemble prediction
        pred = self.predict_next(df)
        ensemble = pred['ensemble']

        if not ensemble:
            return {
                'accepted': False,
                'reason': 'No models available for filtering',
                'original_signal': signal_direction,
            }

        result = {
            'original_signal': signal_direction,
            'ensemble_direction': ensemble['direction'],
            'ensemble_confidence': ensemble['confidence'],
            'consensus': ensemble['consensus'],
            'lstm_result': pred['lstm'],
            'xgb_result': pred['xgb'],
        }

        # Acceptance logic
        if ensemble['direction'] != signal_direction:
            result['accepted'] = False
            result['reason'] = f"Ensemble disagrees: signal={signal_direction}, ensemble={ensemble['direction']}"
        elif ensemble['confidence'] < 0.65 and ensemble['consensus'] == 'WEAK':
            result['accepted'] = False
            result['reason'] = f"Ensemble weak consensus ({ensemble['confidence']:.2%})"
        else:
            result['accepted'] = True
            result['reason'] = f"Ensemble confirms {signal_direction} ({ensemble['consensus']})"

        return result


def create_ensemble(ticker: str, interval: str = '1d', models: list = None) -> EnsemblePredictor:
    """Convenience function to create and load ensemble predictor.

    Args:
        ticker: Ticker symbol
        interval: Data interval
        models: Models to load ['lstm', 'xgb']

    Returns:
        Loaded EnsemblePredictor instance
    """
    predictor = EnsemblePredictor()
    predictor.load(ticker, interval, models=models)
    return predictor
