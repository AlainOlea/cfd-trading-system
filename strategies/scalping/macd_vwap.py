"""
MACD + VWAP Scalping Strategy
==============================
Entry LONG: MACD crosses above signal line + price above VWAP
Entry SHORT: MACD crosses below signal line + price below VWAP
Exit: MACD crosses opposite direction OR take profit hit
Stop Loss: 0.5% from entry
Take Profit: 1% from entry
"""

import pandas as pd

from config.settings import (
    MACD_PARAMS,
    SCALPING_SL_PERCENT,
    SCALPING_TP_PERCENT,
    SIGNAL_CONFIDENCE_HIGH,
    SIGNAL_CONFIDENCE_MEDIUM,
)
from strategies.base import BaseStrategy


class MACDVWAPStrategy(BaseStrategy):
    """MACD + VWAP crossover strategy for scalping (1-5 min timeframes)."""

    @property
    def name(self) -> str:
        return 'macd_vwap'

    @property
    def timeframe(self) -> str:
        return '1m'

    @property
    def description(self) -> str:
        fast, slow, sig = MACD_PARAMS['fast'], MACD_PARAMS['slow'], MACD_PARAMS['signal']
        return (
            f"MACD({fast},{slow},{sig}) + VWAP crossover. "
            f"SL: {SCALPING_SL_PERCENT*100:.1f}%, TP: {SCALPING_TP_PERCENT*100:.1f}%"
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate BUY/SELL signals based on MACD crossover + VWAP filter.

        Required columns: close, macd, macd_signal, vwap
        """
        df = self._init_signal_columns(df)

        required = ['close', 'macd', 'macd_signal', 'vwap']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns for {self.name}: {missing}")

        # Drop rows where indicators haven't warmed up
        valid = df['macd'].notna() & df['macd_signal'].notna() & df['vwap'].notna()

        # MACD crossover detection
        macd_prev = df['macd'].shift(1)
        signal_prev = df['macd_signal'].shift(1)

        # Bullish cross: MACD was below signal, now above
        bullish_cross = (macd_prev < signal_prev) & (df['macd'] >= df['macd_signal'])
        # Bearish cross: MACD was above signal, now below
        bearish_cross = (macd_prev > signal_prev) & (df['macd'] <= df['macd_signal'])

        # VWAP filter
        price_above_vwap = df['close'] > df['vwap']
        price_below_vwap = df['close'] < df['vwap']

        # BUY: bullish MACD cross + price above VWAP
        buy_mask = valid & bullish_cross & price_above_vwap
        df.loc[buy_mask, 'signal'] = 'BUY'
        df.loc[buy_mask, 'entry_price'] = df.loc[buy_mask, 'close']
        df.loc[buy_mask, 'stop_loss'] = df.loc[buy_mask, 'close'] * (1 - SCALPING_SL_PERCENT)
        df.loc[buy_mask, 'take_profit'] = df.loc[buy_mask, 'close'] * (1 + SCALPING_TP_PERCENT)

        # SELL: bearish MACD cross + price below VWAP
        sell_mask = valid & bearish_cross & price_below_vwap
        df.loc[sell_mask, 'signal'] = 'SELL'
        df.loc[sell_mask, 'entry_price'] = df.loc[sell_mask, 'close']
        df.loc[sell_mask, 'stop_loss'] = df.loc[sell_mask, 'close'] * (1 + SCALPING_SL_PERCENT)
        df.loc[sell_mask, 'take_profit'] = df.loc[sell_mask, 'close'] * (1 - SCALPING_TP_PERCENT)

        # Confidence: higher when MACD histogram is strong
        histogram_strength = df['macd'] - df['macd_signal']
        median_strength = histogram_strength.abs().median()
        if median_strength > 0:
            strength_ratio = (histogram_strength.abs() / median_strength).clip(0, 2) / 2
        else:
            strength_ratio = 0.5

        signal_mask = buy_mask | sell_mask
        df.loc[signal_mask, 'confidence'] = (
            strength_ratio[signal_mask] * (SIGNAL_CONFIDENCE_HIGH - SIGNAL_CONFIDENCE_MEDIUM)
            + SIGNAL_CONFIDENCE_MEDIUM
        )

        return df
