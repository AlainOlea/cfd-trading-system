"""
Kronos Predictor
================
Zero-shot candlestick forecasting using NeoQuasar's Kronos-mini foundation model.

Mirror of the `TimesFMPredictor` interface (models/timesfm_predictor.py) so the
pipeline's `_apply_timesfm` can consume it unchanged. Unlike TimesFM — which
forecasts a 1-D close series and derives SL/TP from close quantiles — Kronos
tokenizes and forecasts full OHLCV + volume + amount bars, so it can yield
realistic high/low path. The wrapper keeps the same result dict keys:
direction, forecast (close path), quantiles (10th/80th pct bands from sampled
trajectories), confidence, last_price, sl_price, tp_price.

Kronos architecture: a batch-quantization tokenizer discretizes K-lines into
hierarchical tokens; a decoder-only Transformer is pre-trained autoregressively
over 12B+ K-line records from 45 exchanges. KronosPredictor handles
normalization/denormalization internally.

Model choice: `Kronos-mini` (4.1M params, 2048-token context = ~34h of 1m bars,
F32 ~16MB). Loads from the HuggingFace Hub cache on first use.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch

logger = logging.getLogger(__name__)

VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

# Kronos uses absolute imports (`from model.module import *`), so the vendored
# package must be importable as top-level `model` — guaranteed by sys.path above.
from model import KronosPredictor as _KronosPredictor  # noqa: E402

CONTEXT_LEN = 512        # bars of history fed to the model (mini supports 2048; 512 is plenty)
DEFAULT_HORIZON = 60     # default forecast steps (1 hour at 1min interval)
DEFAULT_SAMPLES = 8      # sampled trajectories for quantile bands
DEFAULT_DEVICE = "cuda:0"

MODEL_ID = "NeoQuasar/Kronos-mini"
TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-2k"


def _intervals_from_index(index: pd.DatetimeIndex, n: int) -> pd.DatetimeIndex:
    """Build `n` future timestamps from a DatetimeIndex by inferring its spacing.

    The last bar timestamps a live 1m/1h series are never consecutive after a
    market close, so we take the median gap of the tail and extend forward from
    the last timestamp.
    """
    if len(index) >= 2:
        gaps = np.diff(index[-10:].asi8) / 1e9
        gaps = gaps[gaps > 0]
        step = pd.Timedelta(seconds=float(np.median(gaps))) if len(gaps) else pd.Timedelta(minutes=1)
    else:
        step = pd.Timedelta(minutes=1)
    last = index[-1]
    return pd.DatetimeIndex([last + step * (i + 1) for i in range(n)])


class KronosPredictor:
    """
    Lazy-loading wrapper around Kronos-mini for the trading pipeline.

    Drop-in replacement for `TimesFMPredictor`: same predict()/predict_batch()
    signature and the same result-dict schema consumed by
    `signals/pipeline.py:_apply_timesfm()` and `signals/store.log_tfm_forecast()`.

    Usage:
        predictor = KronosPredictor()

        # Single ticker (df must be OHLCV with DatetimeIndex)
        result = predictor.predict(df, horizon=60)

        # All tickers in one GPU call
        results = predictor.predict_batch({"SPY": df_spy, "QQQ": df_qqq}, horizon=60)
    """

    SUPPORTED_INTERVALS = frozenset({'1m', '1h'})  # same policy as TimesFM

    def __init__(
        self,
        model_id: str = MODEL_ID,
        tokenizer_id: str = TOKENIZER_ID,
        device: str = DEFAULT_DEVICE,
        sample_count: int = DEFAULT_SAMPLES,
    ):
        self._model_id = model_id
        self._tokenizer_id = tokenizer_id
        self._device = device
        self._sample_count = sample_count
        self._predictor: Optional[_KronosPredictor] = None

    def _load(self) -> None:
        if self._predictor is not None:
            return
        logger.info(
            "Loading Kronos-mini (%s + %s) — first call downloads ~32MB if not cached",
            self._tokenizer_id, self._model_id,
        )
        try:
            from model import Kronos, KronosTokenizer
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Kronos vendored package not found in vendor/. "
                f"Import failed: {exc}"
            )
        tokenizer = KronosTokenizer.from_pretrained(self._tokenizer_id)
        model = Kronos.from_pretrained(self._model_id)
        model.eval()
        self._predictor = _KronosPredictor(
            model, tokenizer, device=self._device, max_context=CONTEXT_LEN,
        )
        logger.info("Kronos ready on %s", self._device)

    def _as_ohlcv(self, df) -> pd.DataFrame:
        """Validate/normalize input into a clean OHLCV DataFrame indexed by time."""
        if isinstance(df, pd.DataFrame) and 'close' in df.columns and df.index is not None:
            out = df.copy()
            if not isinstance(out.index, pd.DatetimeIndex):
                if 'datetime' in out.columns:
                    out.index = pd.to_datetime(out['datetime'])
                else:
                    raise ValueError("Kronos input must have a DatetimeIndex or a 'datetime' column")
            out.index = out.index.tz_localize(None) if out.index.tz is not None else out.index
            return out
        raise ValueError(
            "Kronos requires an OHLCV DataFrame indexed by datetime "
            "(got %s), not a 1-D close array — Kronos forecasts the full K-line.",
            type(df).__name__,
        )

    def predict(
        self,
        df: pd.DataFrame,
        horizon: int = DEFAULT_HORIZON,
        *,
        T: float = 1.0,
        top_k: int = 1,
        top_p: float = 1.0,
        sample_count: Optional[int] = None,
    ) -> Optional[dict]:
        """Forecast OHLCV for a single ticker.

        Args:
            df: OHLCV DataFrame with DatetimeIndex ('open','high','low','close',['volume'])
            horizon: number of bars to forecast
            T/top_k/top_p/sample_count: sampling config (defaults to deterministic greedy,
                matching the official regression tests).

        Returns the standard result dict (same keys as TimesFMPredictor).
        """
        self._load()
        clean = self._as_ohlcv(df)
        if len(clean) < CONTEXT_LEN:
            logger.warning(
                "predict() received %d bars, need %d — padding with first value",
                len(clean), CONTEXT_LEN,
            )
        return self._build_batch_results(
            {0: clean}, horizon=horizon,
            T=T, top_k=top_k, top_p=top_p, sample_count=sample_count,
        ).get(0)

    def predict_batch(
        self,
        frames: dict[str, pd.DataFrame],
        horizon: int = DEFAULT_HORIZON,
        *,
        T: float = 1.0,
        top_k: int = 1,
        top_p: float = 1.0,
        sample_count: Optional[int] = None,
    ) -> dict[str, dict]:
        """Forecast OHLCV for multiple tickers in a single GPU call.

        Args:
            frames: {ticker: OHLCV DataFrame indexed by datetime}
            horizon: bars to forecast

        Returns {ticker: result_dict} — same schema as TimesFM. Tickers that
        fail individually are omitted from the output.
        """
        if not frames:
            return {}
        self._load()
        cleaned: list[tuple[str, pd.DataFrame]] = []
        for ticker, df in frames.items():
            try:
                cleaned.append((ticker, self._as_ohlcv(df)))
            except Exception as exc:
                logger.debug("Kronos: skipping %s (%s)", ticker, exc)
        if not cleaned:
            return {}
        return self._build_batch_results(
            {i: df for i, (_, df) in enumerate(cleaned)},
            horizon=horizon,
            ticker_map={i: t for i, (t, _) in enumerate(cleaned)},
            T=T, top_k=top_k, top_p=top_p, sample_count=sample_count,
        )

    # ─── Low-level ─────────────────────────────────────────────

    def _prepare_frames(
        self,
        frames: dict[int, pd.DataFrame],
        horizon: int,
    ):
        """Normalize each frame into (B, seq, feat) + time stamps + inverse stats.

        Returns (frame_keys, x_list, x_stamp_list, y_stamp_list, means, stds).
        """
        predictor = self._predictor
        frame_keys = [k for k in frames]
        x_list, x_stamp_list, y_stamp_list, means, stds = [], [], [], [], []
        for k in frame_keys:
            df = frames[k]
            x = df[['open', 'high', 'low', 'close', 'volume', 'amount']] \
                if 'amount' in df.columns else \
                df[['open', 'high', 'low', 'close', 'volume']]
            if 'amount' not in x.columns:
                x = x.assign(amount=x['volume'] * x[['open', 'high', 'low', 'close']].mean(axis=1))
            x = x.astype(np.float32)
            if x.isnull().values.any():
                continue

            x_ts = pd.DatetimeIndex(df.index)
            lookback = min(len(x), CONTEXT_LEN)
            xb = x.values[-lookback:]
            xstamp = pd.DataFrame({
                'minute': x_ts.minute, 'hour': x_ts.hour,
                'weekday': x_ts.weekday, 'day': x_ts.day, 'month': x_ts.month,
            }).values.astype(np.float32)[-lookback:]
            y_ts = _intervals_from_index(x_ts, horizon)
            ystamp = pd.DataFrame({
                'minute': y_ts.minute, 'hour': y_ts.hour,
                'weekday': y_ts.weekday, 'day': y_ts.day, 'month': y_ts.month,
            }).values.astype(np.float32)

            mean, std = xb.mean(axis=0), xb.std(axis=0)
            xn = np.clip((xb - mean) / (std + 1e-5), -predictor.clip, predictor.clip)

            x_list.append(xn)
            x_stamp_list.append(xstamp)
            y_stamp_list.append(ystamp)
            means.append(mean)
            stds.append(std)
        return frame_keys, x_list, x_stamp_list, y_stamp_list, means, stds

    def _raw_samples(
        self,
        frames: dict[int, pd.DataFrame],
        horizon: int,
        *,
        T: float = 1.0,
        top_k: int = 1,
        top_p: float = 1.0,
        sample_count: Optional[int] = None,
    ) -> dict[int, np.ndarray]:
        """Run the batched autoregressive pass and return denormalized samples.

        Returns {frame_index: (S, horizon, 6) ndarray} with OHLCV+volume+amount
        reconstructed in original price scale.
        """
        from model.kronos import auto_regressive_inference  # vendored

        predictor = self._predictor
        tok, model = predictor.tokenizer, predictor.model

        frame_keys, x_list, x_stamp_list, y_stamp_list, means, stds = self._prepare_frames(frames, horizon)

        if not x_list:
            logger.debug("Kronos: no valid frames for batch")
            return {}

        S = sample_count if sample_count is not None else self._sample_count
        B = len(x_list)

        # Chunk the batch so the expanded (B*S, seq, feat) tensor stays within
        # GPU memory. Each series is replicated S times for the sample ensemble,
        # so chunk by series count, not slot count. 32 series → 256 slots on the
        # autoregressive pass (fine on the 8GB RTX 5060 for 512x6 context).
        CHUNK_SERIES = 32
        out: dict[int, np.ndarray] = {}
        for start in range(0, B, CHUNK_SERIES):
            end = min(start + CHUNK_SERIES, B)
            x_batch = np.stack(x_list[start:end], axis=0)
            x_stamp_batch = np.stack(x_stamp_list[start:end], axis=0)
            y_stamp_batch = np.stack(y_stamp_list[start:end], axis=0)

            with torch.no_grad():
                x_t = torch.from_numpy(x_batch).to(self._device)
                x_s = torch.from_numpy(x_stamp_batch).to(self._device)
                y_s = torch.from_numpy(y_stamp_batch).to(self._device)

                # Replicate each series S times (== what auto_regressive_inference
                # does internally) but request the un-averaged samples back.
                x_r = x_t.unsqueeze(1).repeat(1, S, 1, 1).reshape(-1, x_t.size(1), x_t.size(2))
                x_sr = x_s.unsqueeze(1).repeat(1, S, 1, 1).reshape(-1, x_s.size(1), x_s.size(2))
                y_sr = y_s.unsqueeze(1).repeat(1, S, 1, 1).reshape(-1, y_s.size(1), y_s.size(2))

                samples = auto_regressive_inference(
                    tok, model, x_r, x_sr, y_sr,
                    predictor.max_context, horizon, predictor.clip,
                    T=T, top_k=top_k, top_p=top_p, sample_count=1, verbose=False,
                )  # (B*S, total_seq_len, feat); keep only the forecast tail (like generate() does)
            samples = samples[:, -horizon:, :].reshape(end - start, S, horizon, -1)

            for j in range(end - start):
                i = start + j
                mean0, std0 = means[i], stds[i]
                out[frame_keys[i]] = samples[j] * (std0 + 1e-5) + mean0  # (S, horizon, feat)

        return out

    def forecast_batch(
        self,
        frames: dict[str, pd.DataFrame],
        horizon: int = DEFAULT_HORIZON,
        **sampling_kwargs,
    ) -> dict[str, dict]:
        """Forecast full OHLCV paths (open/high/low/close/volume/amount).

        Unlike `predict_batch`, the returned dict keeps the per-series mean
        trajectory columns so callers can study range/volatility forecasts.

        Returns {ticker: {'forecast_ohlcv': (horizon,6) ndarray, 'last': float}}.
        """
        if not frames:
            return {}
        self._load()
        cleaned: list[tuple[str, pd.DataFrame]] = []
        for ticker, df in frames.items():
            try:
                cleaned.append((ticker, self._as_ohlcv(df)))
            except Exception as exc:
                logger.debug("Kronos: skipping %s (%s)", ticker, exc)
        if not cleaned:
            return {}
        inner = {i: df for i, (_, df) in enumerate(cleaned)}
        samples = self._raw_samples(inner, horizon, **sampling_kwargs)
        cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        out = {}
        for i, (ticker, df) in enumerate(cleaned):
            if i not in samples:
                continue
            traj = samples[i]                      # (S, horizon, 6)
            mean_path = traj.mean(axis=0)          # (horizon, 6)
            out[ticker] = {
                'forecast_ohlcv': mean_path,
                'samples': traj,
                'last': float(df['close'].iloc[-1]),
                'columns': cols,
            }
        return out

    def _build_batch_results(
        self,
        frames: dict[int, pd.DataFrame],
        horizon: int,
        ticker_map: Optional[dict[int, str]] = None,
        **sampling_kwargs,
    ) -> dict:
        """Run one batched autoregressive pass and build the pipeline result dicts.

        Same schema as TimesFM (`direction`, `quantiles`, `forecast`, ...).
        Sampling kwargs default to the deterministic greedy config used by the
        official regression tests (T=1.0, top_k=1, top_p=1.0, sample_count=1).
        Pass stochastic params (e.g. top_p=0.9, sample_count>1) for ensemble
        probability bands.
        """
        samples = self._raw_samples(frames, horizon, **sampling_kwargs)
        if not samples:
            return {}

        results: dict[int, dict] = {}
        frame_vals = {i: df for i, df in frames.items()}
        for i, traj in samples.items():
            df = frame_vals[i]
            close_traj = traj[:, :, 3]                  # close column index 3
            last = float(df['close'].iloc[-1])

            forecast = close_traj.mean(axis=0)
            direction = int(np.sign(forecast[-1] - last))

            # Per-step percentiles → (horizon, 10) bands, same convention as TimesFM.
            quantiles = np.percentile(close_traj, np.arange(0, 100, 10), axis=0).T

            sl_price = float(quantiles[0, 1])    # 10th pct at t=1
            tp_price = float(quantiles[-1, 8])   # 80th pct at t=end

            ci_width = float((quantiles[:, 8] - quantiles[:, 1]).mean())
            confidence = float(np.clip(1.0 - ci_width / max(last, 1e-6), 0.0, 1.0))

            results[i] = {
                "direction":  direction,
                "sl_price":   sl_price,
                "tp_price":   tp_price,
                "forecast":   forecast,
                "quantiles":  quantiles,
                "confidence": confidence,
                "last_price": last,
            }

        if ticker_map is not None:
            return {ticker_map[i]: r for i, r in results.items()}
        return results

    @property
    def sample_count(self) -> int:
        """Number of sampled trajectories used for quantile bands."""
        return self._sample_count