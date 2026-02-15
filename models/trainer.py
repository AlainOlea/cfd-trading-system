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
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
        epochs: int | None = None,
        batch_size: int | None = None,
    ) -> dict:
        """Train the model with early stopping and learning rate reduction.

        Args:
            model: HybridLSTMTransformer instance (must have .model built).
            X_train: Training features.
            y_train: Training labels.
            X_val: Optional explicit validation features (chronological).
            y_val: Optional explicit validation labels (chronological).
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

        # Use explicit validation set if provided, otherwise split chronologically
        if X_val is not None and y_val is not None:
            validation_data = (X_val, y_val)
            val_split = 0.0
        else:
            # Chronological split from training data (not from shuffled)
            val_size = int(len(X_train) * self.validation_split)
            X_train_sub = X_train[:-val_size]
            y_train_sub = y_train[:-val_size]
            X_val = X_train[-val_size:]
            y_val = y_train[-val_size:]
            validation_data = (X_val, y_val)
            val_split = 0.0
            X_train = X_train_sub
            y_train = y_train_sub

        history = model.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
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

    def prepare_data_walk_forward(
        self,
        df: pd.DataFrame,
        train_window: int = 200,
        test_window: int = 20,
        step_size: int = 20,
        method: str = 'anchored',
    ) -> list[dict]:
        """Create walk-forward validation splits for robust testing.

        Creates multiple chronological train/test folds to simulate real-world
        rolling deployment and assess model degradation over time.

        Args:
            df: DataFrame with OHLCV + indicator columns.
            train_window: Number of bars (sliding windows) for training.
            test_window: Number of bars (sliding windows) for testing.
            step_size: How many bars to roll forward per fold.
            method: 'anchored' (expanding), 'rolling' (fixed-size), or 'expanding'.

        Returns:
            List of dicts with keys:
                - fold: Fold index
                - X_train, y_train: Training data
                - X_test, y_test: Test data
                - train_dates: (start_date, end_date) tuple
                - test_dates: (start_date, end_date) tuple
        """
        # First prepare the full dataset
        available = [f for f in self.features if f in df.columns]
        if len(available) < len(self.features):
            missing = set(self.features) - set(available)
            logger.warning(f"Missing features: {missing}")
        if not available:
            raise ValueError(f"No features found. Available: {df.columns.tolist()}")

        data = df[available].copy()
        data = data.dropna()

        # Create labels
        close_col = 'close' if 'close' in available else available[0]
        close_values = data[close_col].values
        labels = (close_values[1:] > close_values[:-1]).astype(np.float32)
        data = data.iloc[:-1]

        # Normalize features (fit on full dataset for consistency)
        values = data.values.astype(np.float32)
        if NORMALIZE_FEATURES:
            values = self.scaler.fit_transform(values)

        # Create all sliding windows
        X_all, y_all = [], []
        for i in range(len(values) - self.lookback_window):
            X_all.append(values[i:i + self.lookback_window])
            y_all.append(labels[i + self.lookback_window])

        X_all = np.array(X_all)
        y_all = np.array(y_all)

        logger.info(f"Total windows created: {len(X_all)}")
        logger.info(f"Using walk-forward method: {method}")

        # Create folds
        folds = []
        fold_idx = 0

        if method == 'anchored':
            # Expanding window: train grows, test moves forward
            pos = 0
            while pos + train_window + test_window <= len(X_all):
                train_end = pos + train_window
                test_end = train_end + test_window

                X_tr = X_all[:train_end]
                y_tr = y_all[:train_end]
                X_te = X_all[train_end:test_end]
                y_te = y_all[train_end:test_end]

                # Map back to dates
                train_date_start = data.index[0]
                train_date_end = data.index[train_end]
                test_date_start = data.index[train_end]
                test_date_end = data.index[min(test_end, len(data) - 1)]

                folds.append({
                    'fold': fold_idx,
                    'X_train': X_tr,
                    'y_train': y_tr,
                    'X_test': X_te,
                    'y_test': y_te,
                    'train_dates': (train_date_start, train_date_end),
                    'test_dates': (test_date_start, test_date_end),
                })

                pos += step_size
                fold_idx += 1

        elif method == 'rolling':
            # Rolling window: train size fixed, both roll forward
            pos = 0
            while pos + train_window + test_window <= len(X_all):
                train_start = pos
                train_end = pos + train_window
                test_end = train_end + test_window

                X_tr = X_all[train_start:train_end]
                y_tr = y_all[train_start:train_end]
                X_te = X_all[train_end:test_end]
                y_te = y_all[train_end:test_end]

                train_date_start = data.index[train_start]
                train_date_end = data.index[train_end - 1]
                test_date_start = data.index[train_end]
                test_date_end = data.index[min(test_end - 1, len(data) - 1)]

                folds.append({
                    'fold': fold_idx,
                    'X_train': X_tr,
                    'y_train': y_tr,
                    'X_test': X_te,
                    'y_test': y_te,
                    'train_dates': (train_date_start, train_date_end),
                    'test_dates': (test_date_start, test_date_end),
                })

                pos += step_size
                fold_idx += 1

        else:
            raise ValueError(f"Unknown method: {method}. Use 'anchored' or 'rolling'")

        logger.info(f"Created {len(folds)} walk-forward folds")
        return folds

    def train_walk_forward(
        self,
        model_builder: callable,
        df: pd.DataFrame,
        train_window: int = 200,
        test_window: int = 20,
        step_size: int = 20,
        method: str = 'anchored',
        retrain_every_fold: bool = True,
    ) -> dict:
        """Train model using walk-forward validation.

        Tests model on multiple time periods to assess generalization and
        detect performance degradation over time.

        Args:
            model_builder: Callable that returns fresh HybridLSTMTransformer instances.
            df: Full historical DataFrame.
            train_window: Bars for training.
            test_window: Bars for testing.
            step_size: Bars to roll forward.
            method: 'anchored' or 'rolling'.
            retrain_every_fold: If True, build fresh model per fold.

        Returns:
            Dict with aggregate metrics:
                - folds: List of per-fold results
                - mean_accuracy, std_accuracy
                - mean_precision, mean_recall
                - best_fold, worst_fold
                - fold_accuracies: List of test accuracies
        """
        # Create folds
        folds = self.prepare_data_walk_forward(
            df,
            train_window=train_window,
            test_window=test_window,
            step_size=step_size,
            method=method,
        )

        if not folds:
            raise ValueError("No folds created. Check data size and window parameters.")

        fold_results = []
        accuracies = []
        precisions = []
        recalls = []

        print(f"\n{'='*70}")
        print(f"🔄 WALK-FORWARD VALIDATION - {len(folds)} folds")
        print(f"{'='*70}\n")

        for fold in folds:
            fold_num = fold['fold']
            print(f"Fold {fold_num + 1}/{len(folds)}: ", end="", flush=True)

            # Build fresh model or reuse
            if retrain_every_fold or not fold_results:
                model = model_builder()
            else:
                model = model_builder()

            # Train
            try:
                history = self.train(
                    model,
                    fold['X_train'], fold['y_train'],
                    X_val=fold['X_test'], y_val=fold['y_test'],
                    epochs=self.epochs,
                    batch_size=self.batch_size,
                )
            except Exception as e:
                logger.error(f"Training failed on fold {fold_num}: {e}")
                print(f"❌ ERROR: {e}")
                continue

            # Evaluate
            metrics = self.evaluate(model, fold['X_test'], fold['y_test'])
            fold_results.append({
                'fold': fold_num,
                'metrics': metrics,
                'train_dates': fold['train_dates'],
                'test_dates': fold['test_dates'],
            })

            accuracies.append(metrics['accuracy'])
            precisions.append(metrics['precision'])
            recalls.append(metrics['recall'])

            print(
                f"✅ acc={metrics['accuracy']:.2%}, "
                f"prec={metrics['precision']:.2%}, "
                f"recall={metrics['recall']:.2%}"
            )

        # Aggregate results
        print(f"\n{'='*70}")
        print(f"📊 AGGREGATE RESULTS")
        print(f"{'='*70}\n")

        mean_acc = np.mean(accuracies) if accuracies else 0.0
        std_acc = np.std(accuracies) if accuracies else 0.0
        mean_prec = np.mean(precisions) if precisions else 0.0
        mean_recall = np.mean(recalls) if recalls else 0.0

        best_fold_idx = np.argmax(accuracies) if accuracies else -1
        worst_fold_idx = np.argmin(accuracies) if accuracies else -1

        print(f"Mean Accuracy:   {mean_acc:.4f} ± {std_acc:.4f}")
        print(f"Mean Precision:  {mean_prec:.4f}")
        print(f"Mean Recall:     {mean_recall:.4f}")
        print(f"Best Fold:       {best_fold_idx} (acc={accuracies[best_fold_idx]:.4f})")
        print(f"Worst Fold:      {worst_fold_idx} (acc={accuracies[worst_fold_idx]:.4f})")
        print(f"\n{'='*70}\n")

        return {
            'folds': fold_results,
            'mean_accuracy': float(mean_acc),
            'std_accuracy': float(std_acc),
            'mean_precision': float(mean_prec),
            'mean_recall': float(mean_recall),
            'fold_accuracies': accuracies,
            'best_fold': int(best_fold_idx),
            'worst_fold': int(worst_fold_idx),
            'num_folds': len(fold_results),
        }

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
        # Model now returns [loss, accuracy, precision, recall] because of compiled metrics
        eval_results = model.model.evaluate(X_test, y_test, verbose=0)

        # Unpack all metrics (loss, accuracy, precision, recall)
        if len(eval_results) == 4:
            loss, accuracy, precision, recall = eval_results
        else:
            # Fallback for older models (loss, accuracy only)
            loss, accuracy = eval_results
            # Calculate precision and recall manually
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
