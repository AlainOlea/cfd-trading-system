#!/usr/bin/env python3
"""
TimesFM 2.5 Proof-of-Concept: Evaluate Google's foundation model for price forecasting

Tests TimesFM 2.5 on historical price data and compares against actual prices.
Measures latency, accuracy (MAE, MAPE), and directional accuracy.

TimesFM 2.5 API:
  - Model: TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
  - Compile: model.compile(ForecastConfig(max_context=512, max_horizon=128))
  - Forecast: point, quantiles = model.forecast(horizon=H, inputs=[series])
  - Output: point_forecast (batch, horizon), quantiles (batch, horizon, 10)
  - Quantiles: [0%, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%] percentiles
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

# Prevent JAX from pre-allocating a fixed GPU memory block at startup.
# Without this, JAX tries to reserve ~90% of VRAM upfront and fails on
# GPUs with limited free memory (e.g. 6GB free on RTX 5060 with display active).
os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")

import numpy as np
import pandas as pd
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import timesfm
    from timesfm import ForecastConfig
    TIMESFM_AVAILABLE = True
except ImportError:
    TIMESFM_AVAILABLE = False
    logger.warning("timesfm not installed. Run: pip install timesfm[torch]")


class TimesFMEvaluator:
    """Evaluate TimesFM on price prediction tasks."""

    def __init__(self, ticker: str = "SPY", interval: str = "1d"):
        self.ticker = ticker
        self.interval = interval
        self.model = None
        self.data = None

    def download_data(self, days_back: int = 500) -> pd.DataFrame:
        """Download historical price data."""
        logger.info(f"Downloading {self.ticker} {self.interval} data ({days_back} bars)...")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back * 2)  # Extra buffer for holidays/weekends

        data = yf.download(
            self.ticker,
            start=start_date.date(),
            end=end_date.date(),
            interval=self.interval,
            progress=False,
            auto_adjust=True
        )

        # Handle yfinance multi-index columns
        if isinstance(data.columns, pd.MultiIndex):
            # If ticker is in columns, select it; otherwise take first
            if self.ticker in data.columns.get_level_values(1):
                data = data[('Close', self.ticker)]
            else:
                data = data['Close'].iloc[:, 0]
        else:
            data = data['Close']

        # Ensure 1D Series
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]

        self.data = data.dropna().to_frame('Close')
        logger.info(f"✓ Downloaded {len(self.data)} bars")

        return self.data

    def load_model(self) -> bool:
        """Load and compile pre-trained TimesFM 2.5 model."""
        if not TIMESFM_AVAILABLE:
            logger.error("timesfm not available")
            return False

        try:
            logger.info("Loading TimesFM 2.5 model...")
            self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                "google/timesfm-2.5-200m-pytorch"
            )

            logger.info("Compiling model...")
            # ForecastConfig parameters:
            #   max_context: max input sequence length (512 = 2 years daily)
            #   max_horizon: max forecast horizon (128 steps)
            #   normalize_inputs: auto-normalize data (recommended)
            config = ForecastConfig(
                max_context=512,
                max_horizon=128,
                normalize_inputs=True
            )
            self.model.compile(config)

            logger.info("✓ Model loaded and compiled")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            import traceback
            traceback.print_exc()
            return False

    def forecast_prices(self, lookback: int = 500, horizon: int = 24) -> dict:
        """Forecast price movement using TimesFM 2.5."""
        if self.model is None:
            logger.error("Model not loaded")
            return {}

        logger.info(f"Forecasting {horizon} steps ahead with {lookback} lookback...")

        try:
            # Extract close prices (last lookback bars)
            close_prices = self.data['Close'].values[-lookback:]

            # Ensure 1D array
            if close_prices.ndim > 1:
                close_prices = close_prices.flatten()

            close_prices = close_prices.astype(np.float32)

            if len(close_prices) < 100:
                logger.error(f"Insufficient data: {len(close_prices)} bars (need 100+)")
                return {}

            # TimesFM with normalize_inputs=True will auto-normalize
            # But we track stats for denormalization of quantiles
            price_mean = close_prices.mean()
            price_std = close_prices.std()

            logger.info(f"  Price stats: mean={price_mean:.2f}, std={price_std:.2f}")

            # Forecast using TimesFM API
            # Inputs: list of numpy arrays (batch processing)
            # Outputs: (point_forecast, quantile_forecast)
            import time
            start_time = time.time()

            point_forecast, quantile_forecast = self.model.forecast(
                horizon=horizon,
                inputs=[close_prices]  # List with single series
            )

            elapsed = time.time() - start_time

            logger.info(f"✓ Forecast completed in {elapsed:.2f}s")

            # Output shapes:
            #   point_forecast: (batch=1, horizon)
            #   quantile_forecast: (batch=1, horizon, quantiles=10)
            # Quantile indices: [0%, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%]

            point = point_forecast[0][:horizon]
            quantiles = quantile_forecast[0][:horizon]  # (horizon, 10)

            return {
                'point_forecast': point,
                'quantiles': quantiles,  # (horizon, 10) - 10 percentiles
                'quantile_labels': ['0%', '10%', '20%', '30%', '40%', '50%', '60%', '70%', '80%', '90%'],
                'last_price': close_prices[-1],
                'price_mean': price_mean,
                'price_std': price_std,
                'latency_seconds': elapsed,
                'input_length': len(close_prices),
            }

        except Exception as e:
            logger.error(f"Forecast failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def backtest_forecast(self, lookback: int = 500, horizon: int = 12) -> dict:
        """Backtest: forecast recent bars, compare vs actual prices."""
        logger.info(f"Backtesting: forecast last {horizon} bars using {lookback}-bar window...")

        if len(self.data) < lookback + horizon:
            logger.error(f"Insufficient data: need {lookback + horizon}, have {len(self.data)}")
            return {}

        # Get data
        all_prices = self.data['Close'].values

        # Ensure 1D array
        if all_prices.ndim > 1:
            all_prices = all_prices.flatten()

        all_prices = all_prices.astype(np.float32)

        # Use bars before the forecast horizon for training context
        context = all_prices[-(lookback+horizon):-horizon]
        actual_future = all_prices[-horizon:]

        # Forecast
        import time
        start_time = time.time()

        try:
            # TimesFM will auto-normalize with normalize_inputs=True in config
            point_forecast, quantile_forecast = self.model.forecast(
                horizon=horizon,
                inputs=[context]  # Provide last lookback bars as context
            )
            elapsed = time.time() - start_time

            point_forecast = point_forecast[0][:horizon]
            quantiles = quantile_forecast[0][:horizon]  # (horizon, 10)

        except Exception as e:
            logger.error(f"Forecast failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

        # Calculate accuracy metrics
        mae = np.mean(np.abs(point_forecast - actual_future))
        rmse = np.sqrt(np.mean((point_forecast - actual_future) ** 2))
        mape = np.mean(np.abs((point_forecast - actual_future) / actual_future)) * 100

        # Directional accuracy: predict up/down correctly?
        forecast_direction = np.diff(point_forecast, prepend=context[-1]) > 0
        actual_direction = np.diff(actual_future, prepend=actual_future[0]) > 0
        directional_accuracy = np.mean(forecast_direction == actual_direction) * 100

        # Use quantiles for confidence interval
        lower_band = quantiles[:, 1]   # 10th percentile
        upper_band = quantiles[:, 8]   # 80th percentile
        coverage = np.mean((actual_future >= lower_band) & (actual_future <= upper_band)) * 100

        logger.info(f"✓ Backtest Results:")
        logger.info(f"  MAE:                  ${mae:.2f}")
        logger.info(f"  RMSE:                 ${rmse:.2f}")
        logger.info(f"  MAPE:                 {mape:.2f}%")
        logger.info(f"  Directional Accuracy: {directional_accuracy:.1f}%")
        logger.info(f"  80% CI Coverage:      {coverage:.1f}%")
        logger.info(f"  Forecast latency:     {elapsed:.2f}s")

        return {
            'mae': mae,
            'rmse': rmse,
            'mape': mape,
            'directional_accuracy': directional_accuracy,
            'ci_coverage': coverage,
            'point_forecast': point_forecast,
            'quantiles': quantiles,
            'actual': actual_future,
            'context_last': context[-1],
        }

    def estimate_memory(self) -> dict:
        """Estimate GPU/CPU memory usage."""
        logger.info("Estimating memory requirements...")

        try:
            import psutil
            import os

            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()

            # Model size (200M params × 4 bytes per float32)
            model_size_gb = (200e6 * 4) / (1024**3)

            # Current process memory
            process_mem_gb = mem_info.rss / (1024**3)

            logger.info(f"  Model size (200M params): ~{model_size_gb:.2f} GB")
            logger.info(f"  Current process: {process_mem_gb:.2f} GB")

            # Check GPU if available
            gpu_info = "Not available"
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    gpu_info = f"{gpu_mem_gb:.2f} GB"
                    logger.info(f"  GPU VRAM available: {gpu_info}")
            except Exception:
                pass

            return {
                'model_size_gb': model_size_gb,
                'process_memory_gb': process_mem_gb,
                'gpu_vram': gpu_info,
            }

        except ImportError:
            logger.warning("psutil not available for memory estimation")
            return {}

    def run_full_evaluation(self):
        """Run complete evaluation: download, forecast, backtest, memory."""
        logger.info("=" * 60)
        logger.info(f"TimesFM Evaluation: {self.ticker} {self.interval}")
        logger.info("=" * 60)

        # Download data
        self.download_data(days_back=500)

        # Memory estimation
        self.estimate_memory()

        if not TIMESFM_AVAILABLE:
            logger.error("timesfm package not installed. Skipping model tests.")
            logger.info("Install with: pip install timesfm[torch]")
            return

        # Load model
        if not self.load_model():
            return

        # Forecast latest data
        forecast = self.forecast_prices(lookback=500, horizon=24)
        if forecast:
            logger.info("\nForecast Sample (next 12 bars):")
            logger.info(f"  Last price: ${forecast['last_price']:.2f}")
            logger.info(f"  Next 12 forecasted:")
            for i, price in enumerate(forecast['point_forecast'][:12]):
                logger.info(f"    +{i+1}h: ${price:.2f}")

        # Backtest
        backtest = self.backtest_forecast(lookback=500, horizon=12)

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("EVALUATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Ticker: {self.ticker}")
        logger.info(f"Data bars: {len(self.data)}")
        logger.info(f"Zero-shot performance: {'Promising' if backtest.get('mape', 100) < 5 else 'Needs fine-tuning'}")
        logger.info(f"Recommended next step: {'Ensemble with XGBoost' if backtest.get('directional_accuracy', 0) > 55 else 'Fine-tune on financial data'}")
        logger.info("=" * 60)


if __name__ == "__main__":
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    interval = sys.argv[2] if len(sys.argv) > 2 else "1d"

    evaluator = TimesFMEvaluator(ticker=ticker, interval=interval)
    evaluator.run_full_evaluation()
