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
    COMMISSION, INITIAL_CAPITAL, ML_CONFIG, ML_PROMOTION_GATE,
    ML_SIGNAL_THRESHOLDS, MODELS_SAVED_DIR, NORMALIZE_FEATURES,
    PIPELINE_VERSION, SCALER_TYPE, SLIPPAGE,
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

        # Populated by prepare_data() so the OOS financial backtest can
        # reconstruct an entries/exits series aligned to real bar prices.
        self._test_close: pd.Series | None = None
        self._test_index: pd.DatetimeIndex | None = None

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

        values = data.values.astype(np.float32)

        # Split raw arrays BEFORE normalizing (chronological, no shuffle)
        # This prevents scaler leakage: scaler must not see future (test) data
        raw_split = int(len(values) * (1 - self.test_split))
        train_raw = values[:raw_split]
        test_raw  = values[raw_split:]
        train_labels = labels[:raw_split]
        test_labels  = labels[raw_split:]

        # Fit scaler on training portion only, then transform both
        if NORMALIZE_FEATURES:
            train_norm = self.scaler.fit_transform(train_raw)
            test_norm  = self.scaler.transform(test_raw)
        else:
            train_norm = train_raw
            test_norm  = test_raw

        # Create sliding windows from each split independently
        X_train, y_train = [], []
        for i in range(len(train_norm) - self.lookback_window):
            X_train.append(train_norm[i:i + self.lookback_window])
            y_train.append(train_labels[i + self.lookback_window])

        X_test, y_test = [], []
        for i in range(len(test_norm) - self.lookback_window):
            X_test.append(test_norm[i:i + self.lookback_window])
            y_test.append(test_labels[i + self.lookback_window])

        X_train = np.array(X_train)
        y_train = np.array(y_train)
        X_test  = np.array(X_test)
        y_test  = np.array(y_test)

        # Store the close price + timestamp aligned with each y_test entry.
        # y_test[i] corresponds to the bar at offset (raw_split + lookback + i)
        # in the cleaned DataFrame, so we slice the original close series at
        # the same positions for use by backtest_predictions().
        if 'close' in available:
            test_data = data.iloc[raw_split:]
            close_aligned = test_data['close'].iloc[self.lookback_window:]
            self._test_close = close_aligned.iloc[:len(y_test)]
            self._test_index = self._test_close.index

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

        # Create labels (one per bar, label[i] = up/down for bar i+1)
        close_col = 'close' if 'close' in available else available[0]
        close_values = data[close_col].values
        labels = (close_values[1:] > close_values[:-1]).astype(np.float32)
        data = data.iloc[:-1]

        # Keep raw (un-normalized) bar values. The scaler is fit per fold
        # below so test-set statistics never leak into training. An embargo
        # of `lookback_window` bars is inserted between train and test to
        # prevent window-overlap leakage (a test window starting at
        # train_end would otherwise include bars seen during training).
        raw_values = data.values.astype(np.float32)
        embargo = self.lookback_window

        n_bars = len(raw_values)
        # Convert window-counts to bar-counts (each window consumes
        # `lookback_window` bars of history before producing one sample).
        train_bars = train_window + self.lookback_window
        test_bars = test_window + self.lookback_window

        logger.info(
            f"Total bars: {n_bars}, lookback: {self.lookback_window}, "
            f"embargo: {embargo}, method: {method}"
        )

        # Per-fold scalers (one fitted scaler per fold, train-only)
        self._fold_scalers: list = []
        folds: list[dict] = []
        fold_idx = 0
        pos = 0

        while True:
            if method == 'anchored':
                train_start_bar = 0
                train_end_bar = pos + train_bars
            elif method == 'rolling':
                train_start_bar = pos
                train_end_bar = pos + train_bars
            else:
                raise ValueError(f"Unknown method: {method}. Use 'anchored' or 'rolling'")

            test_start_bar = train_end_bar + embargo
            test_end_bar = test_start_bar + test_bars

            if test_end_bar > n_bars:
                break

            train_bars_slice = raw_values[train_start_bar:train_end_bar]
            test_bars_slice = raw_values[test_start_bar:test_end_bar]

            # Fit scaler on TRAIN ONLY. This is the leakage fix.
            if NORMALIZE_FEATURES:
                fold_scaler = MinMaxScaler() if SCALER_TYPE == 'minmax' else StandardScaler()
                train_norm = fold_scaler.fit_transform(train_bars_slice)
                test_norm = fold_scaler.transform(test_bars_slice)
            else:
                fold_scaler = None
                train_norm = train_bars_slice
                test_norm = test_bars_slice

            # Build windows from each normalized slice independently
            X_tr, y_tr = [], []
            for i in range(len(train_norm) - self.lookback_window):
                X_tr.append(train_norm[i:i + self.lookback_window])
                y_tr.append(labels[train_start_bar + i + self.lookback_window])

            X_te, y_te = [], []
            for i in range(len(test_norm) - self.lookback_window):
                X_te.append(test_norm[i:i + self.lookback_window])
                y_te.append(labels[test_start_bar + i + self.lookback_window])

            self._fold_scalers.append(fold_scaler)
            folds.append({
                'fold': fold_idx,
                'X_train': np.array(X_tr),
                'y_train': np.array(y_tr),
                'X_test': np.array(X_te),
                'y_test': np.array(y_te),
                'train_dates': (data.index[train_start_bar], data.index[train_end_bar - 1]),
                'test_dates': (data.index[test_start_bar], data.index[test_end_bar - 1]),
                'scaler': fold_scaler,
            })

            pos += step_size
            fold_idx += 1

        # Promote the most recent fold's scaler to be the production scaler
        # (used by save_model), since it was fit on the largest/most-recent
        # train window in anchored mode.
        if self._fold_scalers and self._fold_scalers[-1] is not None:
            self.scaler = self._fold_scalers[-1]

        logger.info(f"Created {len(folds)} walk-forward folds (per-fold scalers, embargo={embargo})")
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

    def backtest_predictions(
        self,
        model: HybridLSTMTransformer,
        X_test: np.ndarray,
        ticker: str = '',
        interval: str = '1d',
        thresholds: dict | None = None,
        commission: float | None = None,
        slippage: float | None = None,
        initial_capital: float | None = None,
    ) -> dict:
        """Run an out-of-sample financial backtest of the model's predictions.

        Translates sigmoid output into BUY/SELL/HOLD signals using a
        configurable threshold band, then runs vectorbt over the test-set
        bars with realistic CFD costs. This is the only honest measure of
        whether the model has trading edge — accuracy on next-bar
        classification does not imply profitability after spreads.

        Requires `prepare_data()` to have been called previously so that
        `self._test_close` is populated.

        Returns a dict prefixed with `oos_` to merge cleanly into metadata.
        """
        import vectorbt as vbt

        if self._test_close is None or len(self._test_close) == 0:
            raise RuntimeError(
                "No test prices available. Call prepare_data() before "
                "backtest_predictions()."
            )

        thresholds = thresholds or ML_SIGNAL_THRESHOLDS
        commission = commission if commission is not None else COMMISSION
        slippage = slippage if slippage is not None else SLIPPAGE
        initial_capital = initial_capital or INITIAL_CAPITAL

        probs = model.model.predict(X_test, verbose=0).flatten()
        if len(probs) != len(self._test_close):
            # Defensive: align to the shorter series in case of off-by-one
            n = min(len(probs), len(self._test_close))
            probs = probs[:n]
            close = self._test_close.iloc[:n]
            index = self._test_index[:n]
        else:
            close = self._test_close
            index = self._test_index

        entries = pd.Series(probs > thresholds['buy_above'], index=index)
        exits = pd.Series(probs < thresholds['sell_below'], index=index)

        portfolio = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            init_cash=initial_capital,
            fees=commission,
            slippage=slippage,
            freq=self._interval_to_freq(interval),
        )

        stats = portfolio.stats()
        n_trades = int(stats.get('Total Trades', 0))

        def _safe(v, default=0.0):
            try:
                f = float(v)
                if np.isnan(f) or np.isinf(f):
                    return default
                return f
            except (TypeError, ValueError):
                return default

        oos = {
            'oos_sharpe': _safe(stats.get('Sharpe Ratio')),
            'oos_sortino': _safe(stats.get('Sortino Ratio')),
            'oos_max_drawdown_pct': _safe(stats.get('Max Drawdown [%]')),
            'oos_total_return_pct': _safe(stats.get('Total Return [%]')),
            'oos_win_rate_pct': _safe(stats.get('Win Rate [%]')),
            'oos_profit_factor': _safe(stats.get('Profit Factor')),
            'oos_expectancy': _safe(stats.get('Expectancy')),
            'oos_n_trades': n_trades,
            'oos_thresholds': dict(thresholds),
            'oos_commission': commission,
            'oos_slippage': slippage,
        }

        logger.info(
            f"OOS backtest {ticker} {interval}: "
            f"sharpe={oos['oos_sharpe']:.2f} "
            f"return={oos['oos_total_return_pct']:.2f}% "
            f"maxDD={oos['oos_max_drawdown_pct']:.2f}% "
            f"PF={oos['oos_profit_factor']:.2f} "
            f"trades={oos['oos_n_trades']}"
        )
        return oos

    @staticmethod
    def _interval_to_freq(interval: str) -> str | None:
        freq_map = {'1m': '1min', '5m': '5min', '15m': '15min', '1h': '1h', '1d': '1D'}
        return freq_map.get(interval)

    @staticmethod
    def evaluate_promotion(metrics: dict) -> tuple[bool, list[str]]:
        """Apply ML_PROMOTION_GATE to OOS metrics.

        Returns (promoted, reasons). `reasons` is empty when promoted.
        """
        gate = ML_PROMOTION_GATE
        reasons: list[str] = []
        if metrics.get('oos_sharpe', 0.0) < gate['min_sharpe']:
            reasons.append(
                f"sharpe {metrics.get('oos_sharpe', 0.0):.2f} < {gate['min_sharpe']}"
            )
        if metrics.get('oos_profit_factor', 0.0) < gate['min_profit_factor']:
            reasons.append(
                f"profit_factor {metrics.get('oos_profit_factor', 0.0):.2f} "
                f"< {gate['min_profit_factor']}"
            )
        if metrics.get('oos_n_trades', 0) < gate['min_trades']:
            reasons.append(
                f"n_trades {metrics.get('oos_n_trades', 0)} < {gate['min_trades']}"
            )
        if metrics.get('oos_max_drawdown_pct', 0.0) < gate['max_drawdown_pct']:
            reasons.append(
                f"max_drawdown {metrics.get('oos_max_drawdown_pct', 0.0):.2f}% "
                f"worse than {gate['max_drawdown_pct']}%"
            )
        return (len(reasons) == 0, reasons)

    def save_model(
        self,
        model: HybridLSTMTransformer,
        ticker: str,
        interval: str = '1d',
        metrics: dict | None = None,
    ) -> Path:
        """Save model weights, scaler, and metadata to disk.

        Args:
            model: Trained model.
            ticker: Ticker used for training (for filename).
            interval: Data interval.
            metrics: Evaluation metrics dict from evaluate() — accuracy, precision, recall.

        Returns:
            Path to saved model directory.
        """
        import joblib
        import json
        from datetime import datetime

        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        model_dir = MODELS_SAVED_DIR / f"{safe_ticker}_{interval}"
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save complete model (includes BatchNormalization variables)
        model_path = model_dir / "model.keras"
        model.model.save(str(model_path))

        # Save scaler
        scaler_path = model_dir / "scaler.pkl"
        joblib.dump(self.scaler, str(scaler_path))

        # Save metadata — include accuracy + timestamp so the dashboard can display them
        meta = {
            'pipeline_version': PIPELINE_VERSION,
            'features': self.features,
            'n_features': len(self.features),
            'lookback_window': self.lookback_window,
            'ticker': ticker,
            'interval': interval,
            'model_type': 'lstm_transformer',
            'lstm1_units': model.lstm1_units,
            'lstm2_units': model.lstm2_units,
            'd_model': model.d_model,
            'n_heads': model.n_heads,
            'ff_dim': model.ff_dim,
            'trained_at': datetime.now().isoformat(),
            'accuracy': float(metrics['accuracy']) if metrics and 'accuracy' in metrics else None,
            'precision': float(metrics['precision']) if metrics and 'precision' in metrics else None,
            'recall': float(metrics['recall']) if metrics and 'recall' in metrics else None,
        }

        # Merge any OOS financial metrics (from backtest_predictions)
        if metrics:
            for key, value in metrics.items():
                if key.startswith('oos_'):
                    meta[key] = value

        # Apply promotion gate so the predictor can refuse to load
        # un-tradeable models without operator override.
        promoted, reasons = self.evaluate_promotion(meta)
        meta['promoted'] = promoted
        meta['promotion_reasons'] = reasons

        meta_path = model_dir / "metadata.json"
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

        log_msg = (
            f"Model saved to {model_dir} "
            f"(accuracy={meta['accuracy']}, promoted={promoted})"
        )
        if not promoted:
            log_msg += f" - reasons: {reasons}"
        logger.info(log_msg)
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
        import tensorflow as tf

        safe_ticker = ticker.replace('/', '_').replace('-', '_')
        model_dir = MODELS_SAVED_DIR / f"{safe_ticker}_{interval}"

        if not model_dir.exists():
            raise FileNotFoundError(f"No saved model found at {model_dir}")

        # Load metadata
        with open(model_dir / "metadata.json") as f:
            meta = json.load(f)

        # Load complete model from .keras file (with custom layer support)
        from models.hybrid_model import TransformerEncoderBlock
        keras_model = tf.keras.models.load_model(
            str(model_dir / "model.keras"),
            custom_objects={'TransformerEncoderBlock': TransformerEncoderBlock}
        )

        # Wrap in HybridLSTMTransformer for consistency
        hybrid = HybridLSTMTransformer(
            lstm1_units=meta['lstm1_units'],
            lstm2_units=meta['lstm2_units'],
            d_model=meta['d_model'],
            n_heads=meta['n_heads'],
            ff_dim=meta['ff_dim'],
        )
        hybrid.model = keras_model

        # Load scaler
        scaler = joblib.load(str(model_dir / "scaler.pkl"))

        logger.info(f"Model loaded from {model_dir}")
        return hybrid, scaler, meta
