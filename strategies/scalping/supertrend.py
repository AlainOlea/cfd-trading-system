"""
SuperTrend Strategy
===================
Entry LONG: SuperTrend flips from downtrend to uptrend
Entry SHORT: SuperTrend flips from uptrend to downtrend
Stop Loss: the SuperTrend line itself (natural trailing level)
Take Profit: 2x the SL distance (fallback to scalping % if degenerate)
"""

import pandas as pd
import pandas_ta as ta

from config.settings import (
    SCALPING_SL_PERCENT,
    SCALPING_TP_PERCENT,
    SIGNAL_CONFIDENCE_HIGH,
    SIGNAL_CONFIDENCE_MEDIUM,
    SUPERTREND_PARAMS,
)
from strategies.base import BaseStrategy


class SuperTrendStrategy(BaseStrategy):
    """SuperTrend flip strategy for intraday trading (1m-1h timeframes)."""

    require_trend: bool = True

    @property
    def name(self) -> str:
        return 'supertrend'

    @property
    def default_timeframe(self) -> str:
        return '1h'

    @property
    def description(self) -> str:
        length, mult = SUPERTREND_PARAMS['length'], SUPERTREND_PARAMS['multiplier']
        return (
            f"SuperTrend({length},{mult}) flip. "
            f"SL: SuperTrend line, TP: 2x SL distance"
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate BUY/SELL on SuperTrend direction flips.

        Required columns: high, low, close (SuperTrend computed internally).
        """
        df = self._init_signal_columns(df)

        required = ['high', 'low', 'close']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns for {self.name}: {missing}")

        length = SUPERTREND_PARAMS['length']
        mult = SUPERTREND_PARAMS['multiplier']
        st = ta.supertrend(df['high'], df['low'], df['close'],
                           length=length, multiplier=mult)
        if st is None or st.empty:
            return df

        # pandas-ta columns: SUPERT_{l}_{m} (line), SUPERTd_{l}_{m} (direction ±1)
        line_col = f'SUPERT_{length}_{mult}'
        dir_col = f'SUPERTd_{length}_{mult}'
        if line_col not in st.columns or dir_col not in st.columns:
            raise ValueError(f"Unexpected pandas-ta supertrend columns: {list(st.columns)}")

        st_line = st[line_col]
        st_dir = st[dir_col]
        valid = st_line.notna() & (st_line > 0)

        if self.require_trend:
            valid = valid & self._is_trending(df)

        dir_prev = st_dir.shift(1)
        flip_up = (dir_prev == -1) & (st_dir == 1)
        flip_down = (dir_prev == 1) & (st_dir == -1)

        for mask, direction in ((valid & flip_up, 'BUY'),
                                (valid & flip_down, 'SELL')):
            if not mask.any():
                continue
            entry = df.loc[mask, 'close']
            sl = st_line[mask]
            dist = (entry - sl).abs()
            # Degenerate distance -> fixed scalping percentages
            bad = dist <= 0
            if direction == 'BUY':
                sl = sl.where(~bad, entry * (1 - SCALPING_SL_PERCENT))
                tp = entry + 2 * (entry - sl)
                tp = tp.where(~bad, entry * (1 + SCALPING_TP_PERCENT))
            else:
                sl = sl.where(~bad, entry * (1 + SCALPING_SL_PERCENT))
                tp = entry - 2 * (sl - entry)
                tp = tp.where(~bad, entry * (1 - SCALPING_TP_PERCENT))

            df.loc[mask, 'signal'] = direction
            df.loc[mask, 'entry_price'] = entry
            df.loc[mask, 'stop_loss'] = sl
            df.loc[mask, 'take_profit'] = tp

        # Confidence: stronger ADX -> higher confidence
        signal_mask = df['signal'].isin(['BUY', 'SELL'])
        if 'adx' in df.columns:
            adx_ratio = (df['adx'].clip(0, 50) / 50).fillna(0.5)
            df.loc[signal_mask, 'confidence'] = (
                adx_ratio[signal_mask]
                * (SIGNAL_CONFIDENCE_HIGH - SIGNAL_CONFIDENCE_MEDIUM)
                + SIGNAL_CONFIDENCE_MEDIUM
            )
        else:
            df.loc[signal_mask, 'confidence'] = SIGNAL_CONFIDENCE_MEDIUM

        return df
