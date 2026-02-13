"""
Moving Average Crossover Swing Strategy
=========================================
Entry LONG: Golden Cross (SMA fast > SMA slow)
Entry SHORT: Death Cross (SMA fast < SMA slow)
Stop Loss: 2% from entry
Take Profit: 3% from entry
"""

import pandas as pd

from config.settings import (
    MA_PARAMS,
    SIGNAL_CONFIDENCE_HIGH,
    SIGNAL_CONFIDENCE_MEDIUM,
    SWING_SL_PERCENT,
    SWING_TP_PERCENT,
)
from strategies.base import BaseStrategy


class MACrossoverStrategy(BaseStrategy):
    """Moving Average Crossover strategy for swing trading (daily timeframe)."""

    @property
    def name(self) -> str:
        return 'ma_crossover'

    @property
    def timeframe(self) -> str:
        return '1d'

    @property
    def description(self) -> str:
        return (
            f"SMA({MA_PARAMS['fast']}/{MA_PARAMS['slow']}) crossover. "
            f"SL: {SWING_SL_PERCENT*100:.1f}%, TP: {SWING_TP_PERCENT*100:.1f}%"
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate BUY/SELL signals based on SMA crossover.

        Required columns: close, sma_{fast}, sma_{slow}
        """
        df = self._init_signal_columns(df)

        fast_col = f"sma_{MA_PARAMS['fast']}"
        slow_col = f"sma_{MA_PARAMS['slow']}"

        required = ['close', fast_col, slow_col]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns for {self.name}: {missing}")

        valid = df[fast_col].notna() & df[slow_col].notna()

        # Crossover detection
        fast_prev = df[fast_col].shift(1)
        slow_prev = df[slow_col].shift(1)

        # Golden Cross: fast was below slow, now above
        golden_cross = (fast_prev <= slow_prev) & (df[fast_col] > df[slow_col])
        # Death Cross: fast was above slow, now below
        death_cross = (fast_prev >= slow_prev) & (df[fast_col] < df[slow_col])

        # BUY on Golden Cross
        buy_mask = valid & golden_cross
        df.loc[buy_mask, 'signal'] = 'BUY'
        df.loc[buy_mask, 'entry_price'] = df.loc[buy_mask, 'close']
        df.loc[buy_mask, 'stop_loss'] = df.loc[buy_mask, 'close'] * (1 - SWING_SL_PERCENT)
        df.loc[buy_mask, 'take_profit'] = df.loc[buy_mask, 'close'] * (1 + SWING_TP_PERCENT)

        # SELL on Death Cross
        sell_mask = valid & death_cross
        df.loc[sell_mask, 'signal'] = 'SELL'
        df.loc[sell_mask, 'entry_price'] = df.loc[sell_mask, 'close']
        df.loc[sell_mask, 'stop_loss'] = df.loc[sell_mask, 'close'] * (1 + SWING_SL_PERCENT)
        df.loc[sell_mask, 'take_profit'] = df.loc[sell_mask, 'close'] * (1 - SWING_TP_PERCENT)

        # Confidence: based on separation between fast and slow MA
        signal_mask = buy_mask | sell_mask
        ma_spread = (df[fast_col] - df[slow_col]).abs() / df[slow_col]
        median_spread = ma_spread.median()
        if median_spread > 0:
            spread_ratio = (ma_spread / median_spread).clip(0, 2) / 2
        else:
            spread_ratio = 0.5

        df.loc[signal_mask, 'confidence'] = (
            spread_ratio[signal_mask]
            * (SIGNAL_CONFIDENCE_HIGH - SIGNAL_CONFIDENCE_MEDIUM)
            + SIGNAL_CONFIDENCE_MEDIUM
        )

        return df
