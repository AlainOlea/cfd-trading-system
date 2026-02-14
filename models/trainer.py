"""
Model Trainer Module
=====================
Handles data preparation, model training, evaluation, and persistence.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from config.settings import (
    ML_CONFIG, MODELS_SAVED_DIR, NORMALIZE_FEATURES, SCALER_TYPE,
)
from models.hybrid_model import HybridLSTMTransformer

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Trains and evaluates the hybrid LSTM+Transformer model."""

    def __init__(
        self,
        lookback_window: int = ML_CONFIG['lookback_window'],
        features: list[str] | None = None,
        batch_size: int = ML_CONFIG['batch_size'],
        epochs: int = ML_CONFIG['epochs'],
        validation_split: float = ML_CONFIG['validation_split'],
        test_split: float = ML_CONFIG['test_split'],
        early_stopping_patience: int = ML_CONFIG['early_stopping_patience'],
    ):
        self.lookback_window = lookback_window
        self.features = features or ML_CONFIG['features']
        self.batch_size = batch_size
        self.epochs = epochs
        self.validation_split = validation_split
        self.test_split = test_split
        self.early_stopping_patience = early_stopping_patience
        self.scaler = MinMaxScaler() if SCALER_TYPE == 'minmax' else StandardScaler()

        # Configure GPU memory growth (prevents OOM errors)
        try:
            import tensorflow as tf
            gpus = tf.config.list_physical_devices('GPU')
            if gpus:
                for gpu in gpus:
                    tf.config.experimental.set_memory_growth(gpu, True)
                logger.info(f"✅ GPU memory growth enabled: {len(gpus)} GPU(s)")
        except Exception as e:
            logger.warning(f"GPU config warning: {e}")

    def prepare_data(
        self, df: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Prepare windowed sequences for training.

        Creates sliding windows of `lookback_window` timesteps.
        Label: 1 if next close > current close, else 0.

        Args:
            df: DataFrame with OHLCV + indicator columns.

        Returns:
            (X_train, y_train, X_test, y_test) numpy arrays.
        """
        # Select and validate features
        available = [f for f in self.features if f in df.columns]
        if len(available) < len(self.features):
            missing = set(self.features) - set(available)
            logger.warning(f"Missing features (will skip): {missing}")
        if not available:
            raise ValueError(f"No features found in DataFrame. Available: {df.columns.tolist()}")

        data = df[available].copy()

        # Drop NaN rows (from indicator warmup)
        data = data.dropna()
        if len(data) < self.lookback_window + 10:
            raise ValueError(
                f"Not enough data after dropping NaN: {len(data)} rows, "
                f"need at least {self.lookback_window + 10}"
            )

        # Create labels: 1 if next close goes up
        close_col = 'close' if 'close' in available else available[0]
        close_values = data[close_col].values
        labels = (close_values[1:] > close_values[:-1]).astype(np.float32)
        data = data.iloc[:-1]  # Drop last row (no label)

        # Normalize features
        values = data.values.astype(np.float32)
        if NORMALIZE_FEATURES:
            values = self.scaler.fit_transform(values)

        # Create sliding windows
        X, y = [], []
        for i in range(len(values) - self.lookback_window):
            X.append(values[i:i + self.lookback_window])
            y.append(labels[i + self.lookback_window])

        X = np.array(X)
        y = np.array(y)

        # Train/test split (chronological, no shuffle)
        split_idx = int(len(X) * (1 - self.test_split))
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        logger.info(
            f"Data prepared: {len(X_train)} train, {len(X_test)} test samples. "
            f"Shape: {X_train.shape}. Features: {available}"
        )
        return X_train, y_train, X_test, y_test

    def train(
        self,
        model: HybridLSTMTransformer,
        X_train: np.ndarray,
        y_train: np.ndarray,
        epochs: int | None = None,
        batch_size: int | None = None,
    ) -> dict:
        """Train the model with early stopping and learning rate reduction.

        Args:
            model: HybridLSTMTransformer instance (must have .model built).
            X_train: Training features.
            y_train: Training labels.
            epochs: Override default epochs.
            batch_size: Override default batch size.

        Returns:
            Training history dict.
        """
        import tensorflow as tf

        epochs = epochs or self.epochs
        batch_size = batch_size or self.batch_size

        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor='val_loss',
                patience=self.early_stopping_patience,
                restore_best_weights=True,
                verbose=1,
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=self.early_stopping_patience // 2,
                min_lr=1e-6,
                verbose=1,
            ),
        ]

        logger.info(f"Training started: {epochs} epochs, batch_size={batch_size}")

        history = model.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=self.validation_split,
            callbacks=callbacks,
            verbose=1,
        )

        logger.info(
            f"Training complete: "
            f"loss={history.history['loss'][-1]:.4f}, "
            f"acc={history.history['accuracy'][-1]:.4f}, "
            f"val_loss={history.history['val_loss'][-1]:.4f}, "
            f"val_acc={history.history['val_accuracy'][-1]:.4f}"
        )
        return history.history

    def evaluate(
        self,
        model: HybridLSTMTransformer,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict[str, float]:
        """Evaluate model on test set.

        Args:
            model: Trained HybridLSTMTransformer.
            X_test: Test features.
            y_test: Test labels.

        Returns:
            Dict with loss, accuracy, precision, recall.
        """
        loss, accuracy = model.model.evaluate(X_test, y_test, verbose=0)

        # Calculate precision and recall
        y_pred = (model.model.predict(X_test, verbose=0) > 0.5).astype(int).flatten()
        y_true = y_test.astype(int)

        tp = np.sum((y_pred == 1) & (y_true == 1))
        fp = np.sum((y_pred == 1) & (y_true == 0))
        fn = np.sum((y_pred == 0) & (y_true == 1))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        metrics = {
            'loss': float(loss),
            'accuracy': float(accuracy),
            'precision': float(precision),
            'recall': float(recall),
        }

        logger.info(
            f"Evaluation: acc={accuracy:.4f}, "
            f"precision={precision:.4f}, recall={recall:.4f}"
        )
        return metrics

    def save_model(
        self,
        model: HybridLSTMTransformer,
        ticker: str,
        interval: str = '1d',
    ) -> Path:
        """Save model weights and scaler to disk.

        Args:
            model: Trained model.
            ticker: Ticker used for training (for filename).
            interval: Data interval.

        Returns:
            Path to saved model directory.
        """
        import joblib

        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        model_dir = MODELS_SAVED_DIR / f"{safe_ticker}_{interval}"
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save model weights
        weights_path = model_dir / "model.weights.h5"
        model.model.save_weights(str(weights_path))

        # Save scaler
        scaler_path = model_dir / "scaler.pkl"
        joblib.dump(self.scaler, str(scaler_path))

        # Save metadata
        import json
        meta = {
            'features': self.features,
            'lookback_window': self.lookback_window,
            'ticker': ticker,
            'interval': interval,
            'lstm1_units': model.lstm1_units,
            'lstm2_units': model.lstm2_units,
            'd_model': model.d_model,
            'n_heads': model.n_heads,
            'ff_dim': model.ff_dim,
        }
        meta_path = model_dir / "metadata.json"
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Model saved to {model_dir}")
        return model_dir

    @staticmethod
    def load_model(ticker: str, interval: str = '1d') -> tuple[HybridLSTMTransformer, 'MinMaxScaler | StandardScaler', dict]:
        """Load a saved model from disk.

        Args:
            ticker: Ticker symbol.
            interval: Data interval.

        Returns:
            (model, scaler, metadata) tuple.
        """
        import joblib
        import json

        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        model_dir = MODELS_SAVED_DIR / f"{safe_ticker}_{interval}"

        if not model_dir.exists():
            raise FileNotFoundError(f"No saved model found at {model_dir}")

        # Load metadata
        with open(model_dir / "metadata.json") as f:
            meta = json.load(f)

        # Rebuild model with same architecture
        hybrid = HybridLSTMTransformer(
            lstm1_units=meta['lstm1_units'],
            lstm2_units=meta['lstm2_units'],
            d_model=meta['d_model'],
            n_heads=meta['n_heads'],
            ff_dim=meta['ff_dim'],
        )
        input_shape = (meta['lookback_window'], len(meta['features']))
        hybrid.build(input_shape)

        # Load weights
        hybrid.model.load_weights(str(model_dir / "model.weights.h5"))

        # Load scaler
        scaler = joblib.load(str(model_dir / "scaler.pkl"))

        logger.info(f"Model loaded from {model_dir}")
        return hybrid, scaler, meta
