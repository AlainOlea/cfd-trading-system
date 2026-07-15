"""
Fibonacci Retracement Strategy
==============================
Programmatic replica of chart-based Fibonacci analysis:

1. Detect the most recent swing high/low over a rolling window.
2. In an uptrend (price above SMA50, ADX trending), wait for a pullback
   that touches a retracement level (38.2 / 50 / 61.8%) of the last
   upswing and closes back above it -> BUY.
3. In a downtrend, mirror logic on rallies into retracement levels -> SELL.

Stop Loss: beyond the 78.6% retracement.
Take Profit: the swing extreme (100% of the move back).
"""

import pandas as pd

from config.settings import (
    FIBONACCI_PARAMS,
    SIGNAL_CONFIDENCE_HIGH,
    SIGNAL_CONFIDENCE_MEDIUM,
)
from strategies.base import BaseStrategy


class FibonacciStrategy(BaseStrategy):
    """Trend-pullback entries at Fibonacci retracement levels."""

    require_trend: bool = True  # retracement entries only make sense in a trend

    @property
    def name(self) -> str:
        return 'fibonacci'

    @property
    def timeframe(self) -> str:
        return '1d'

    @property
    def description(self) -> str:
        lv = '/'.join(f"{l*100:.1f}" for l in FIBONACCI_PARAMS['levels'])
        return (
            f"Fibonacci retracement pullback ({lv}%) over "
            f"{FIBONACCI_PARAMS['swing_window']}-bar swings. "
            f"SL beyond {FIBONACCI_PARAMS['sl_level']*100:.1f}%, TP at swing extreme."
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate BUY/SELL on Fibonacci level bounces within a trend.

        Required columns: high, low, close. Uses 'sma_50' and 'adx' if
        present for trend context (safe degradation without them).
        """
        df = self._init_signal_columns(df)

        required = ['high', 'low', 'close']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns for {self.name}: {missing}")

        window = FIBONACCI_PARAMS['swing_window']
        prox = FIBONACCI_PARAMS['proximity_pct']
        sl_ratio = FIBONACCI_PARAMS['sl_level']
        if len(df) < window + 1:
            return df

        # Rolling swing extremes of the PRIOR window (exclude current bar)
        swing_high = df['high'].rolling(window).max().shift(1)
        swing_low = df['low'].rolling(window).min().shift(1)
        rng = swing_high - swing_low
        valid = rng.notna() & (rng > 0)

        if self.require_trend:
            valid = valid & self._is_trending(df)

        # Trend direction: price relative to SMA50 (fallback: close vs window mean)
        if 'sma_50' in df.columns:
            uptrend = df['close'] > df['sma_50']
        else:
            uptrend = df['close'] > df['close'].rolling(window).mean()
        downtrend = ~uptrend

        for level in FIBONACCI_PARAMS['levels']:
            # Uptrend pullback: retracement measured down from swing high
            fib_up = swing_high - level * rng
            touched = df['low'] <= fib_up * (1 + prox)
            closed_above = df['close'] > fib_up
            mask = valid & uptrend & touched & closed_above & (df['signal'] == 'HOLD')
            if mask.any():
                entry = df.loc[mask, 'close']
                sl = (swing_high - sl_ratio * rng)[mask]
                tp = swing_high[mask]
                idx = entry.index[(sl < entry) & (tp > entry)]
                df.loc[idx, 'signal'] = 'BUY'
                df.loc[idx, 'entry_price'] = df.loc[idx, 'close']
                df.loc[idx, 'stop_loss'] = sl[idx]
                df.loc[idx, 'take_profit'] = tp[idx]

            # Downtrend rally: retracement measured up from swing low
            fib_down = swing_low + level * rng
            touched = df['high'] >= fib_down * (1 - prox)
            closed_below = df['close'] < fib_down
            mask = valid & downtrend & touched & closed_below & (df['signal'] == 'HOLD')
            if mask.any():
                entry = df.loc[mask, 'close']
                sl = (swing_low + sl_ratio * rng)[mask]
                tp = swing_low[mask]
                idx = entry.index[(sl > entry) & (tp < entry)]
                df.loc[idx, 'signal'] = 'SELL'
                df.loc[idx, 'entry_price'] = df.loc[idx, 'close']
                df.loc[idx, 'stop_loss'] = sl[idx]
                df.loc[idx, 'take_profit'] = tp[idx]

        # Confidence: golden-ratio (61.8%) touches score higher
        signal_mask = df['signal'].isin(['BUY', 'SELL'])
        df.loc[signal_mask, 'confidence'] = SIGNAL_CONFIDENCE_MEDIUM
        golden_up = swing_high - 0.618 * rng
        golden_down = swing_low + 0.618 * rng
        golden = signal_mask & (
            ((df['signal'] == 'BUY') & (df['low'] <= golden_up * (1 + prox)))
            | ((df['signal'] == 'SELL') & (df['high'] >= golden_down * (1 - prox)))
        )
        df.loc[golden, 'confidence'] = SIGNAL_CONFIDENCE_HIGH

        return df
