"""
Pivot Points Strategy
=====================
Classic floor-trader pivots computed from the PREVIOUS day's OHLC:
    PP = (H + L + C) / 3
    R1 = 2*PP - L,  S1 = 2*PP - H
    R2 = PP + (H - L),  S2 = PP - (H - L)

Entry LONG: price bounces off S1/S2 (touched the level and closed back
above it), optionally confirmed by RSI < 50.
Entry SHORT: price rejects R1/R2 (touched and closed back below),
optionally confirmed by RSI > 50.
Stop Loss: behind the next level down/up (or scalping % fallback).
Take Profit: the next level in the trade's direction.
"""

import pandas as pd

from config.settings import (
    PIVOT_PARAMS,
    SCALPING_SL_PERCENT,
    SIGNAL_CONFIDENCE_HIGH,
    SIGNAL_CONFIDENCE_MEDIUM,
)
from strategies.base import BaseStrategy


class PivotPointsStrategy(BaseStrategy):
    """Intraday support/resistance bounces on classic pivot levels."""

    # Mean-reversion at S/R levels: a strong trend blows through pivots,
    # so suppress signals when ADX confirms a trend. Also keep TimesFM from
    # overwriting the level-based SL/TP (same rationale as RSI+BB).
    require_ranging: bool = True
    mean_reversion: bool = True

    @property
    def name(self) -> str:
        return 'pivot_points'

    @property
    def default_timeframe(self) -> str:
        return '1h'

    @property
    def description(self) -> str:
        return (
            "Classic daily pivots (PP, S1-S2, R1-R2). BUY bounce off S1/S2, "
            "SELL rejection at R1/R2. SL behind next level, TP next level."
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate BUY/SELL on pivot-level bounces.

        Required columns: open, high, low, close. Index must be a
        DatetimeIndex (levels come from the previous day's OHLC).
        """
        df = self._init_signal_columns(df)

        required = ['high', 'low', 'close']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns for {self.name}: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(f"{self.name} requires a DatetimeIndex")

        # Previous day's OHLC -> today's pivot levels
        daily = df[['high', 'low', 'close']].resample('1D').agg(
            {'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna()
        if len(daily) < 2:
            return df

        pp = (daily['high'] + daily['low'] + daily['close']) / 3
        levels = pd.DataFrame({
            'pp': pp,
            'r1': 2 * pp - daily['low'],
            's1': 2 * pp - daily['high'],
            'r2': pp + (daily['high'] - daily['low']),
            's2': pp - (daily['high'] - daily['low']),
        }).shift(1)  # today trades against YESTERDAY's levels

        # Broadcast each day's levels onto its intraday bars
        lv = levels.reindex(df.index.normalize())
        lv.index = df.index

        prox = PIVOT_PARAMS['proximity_pct']
        valid = lv['pp'].notna()
        if self.require_ranging:
            valid = valid & ~self._is_trending(df)

        rsi_ok_buy = rsi_ok_sell = pd.Series(True, index=df.index)
        if PIVOT_PARAMS['rsi_confirm'] and 'rsi' in df.columns:
            rsi_ok_buy = df['rsi'] < 50
            rsi_ok_sell = df['rsi'] > 50

        # Bounce: bar's low touched the support (within proximity) but closed above it
        for support, sl_ref in (('s1', 's2'), ('s2', None)):
            s = lv[support]
            touched = df['low'] <= s * (1 + prox)
            closed_above = df['close'] > s
            mask = valid & touched & closed_above & rsi_ok_buy & (df['signal'] == 'HOLD')
            if mask.any():
                entry = df.loc[mask, 'close']
                sl = lv.loc[mask, sl_ref] if sl_ref else entry * (1 - SCALPING_SL_PERCENT)
                sl = sl.fillna(entry * (1 - SCALPING_SL_PERCENT))
                sl = sl.where(sl < entry, entry * (1 - SCALPING_SL_PERCENT))
                tp = lv.loc[mask, 'pp'].fillna(entry * 1.01)
                tp = tp.where(tp > entry, entry * 1.01)
                df.loc[mask, 'signal'] = 'BUY'
                df.loc[mask, 'entry_price'] = entry
                df.loc[mask, 'stop_loss'] = sl
                df.loc[mask, 'take_profit'] = tp

        # Rejection: bar's high touched the resistance but closed below it
        for resistance, sl_ref in (('r1', 'r2'), ('r2', None)):
            r = lv[resistance]
            touched = df['high'] >= r * (1 - prox)
            closed_below = df['close'] < r
            mask = valid & touched & closed_below & rsi_ok_sell & (df['signal'] == 'HOLD')
            if mask.any():
                entry = df.loc[mask, 'close']
                sl = lv.loc[mask, sl_ref] if sl_ref else entry * (1 + SCALPING_SL_PERCENT)
                sl = sl.fillna(entry * (1 + SCALPING_SL_PERCENT))
                sl = sl.where(sl > entry, entry * (1 + SCALPING_SL_PERCENT))
                tp = lv.loc[mask, 'pp'].fillna(entry * 0.99)
                tp = tp.where(tp < entry, entry * 0.99)
                df.loc[mask, 'signal'] = 'SELL'
                df.loc[mask, 'entry_price'] = entry
                df.loc[mask, 'stop_loss'] = sl
                df.loc[mask, 'take_profit'] = tp

        # Confidence: deeper levels (S2/R2) are stronger than S1/R1
        signal_mask = df['signal'].isin(['BUY', 'SELL'])
        df.loc[signal_mask, 'confidence'] = SIGNAL_CONFIDENCE_MEDIUM
        deep = signal_mask & (
            (df['low'] <= lv['s2'] * (1 + prox)) | (df['high'] >= lv['r2'] * (1 - prox))
        )
        df.loc[deep, 'confidence'] = SIGNAL_CONFIDENCE_HIGH

        return df
