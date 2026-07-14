"""
RSI + Bollinger Bands Scalping Strategy
========================================
Entry LONG: RSI < 30 (oversold) + price touches/crosses lower BB
Entry SHORT: RSI > 70 (overbought) + price touches/crosses upper BB
Exit: RSI crosses opposite level OR opposite BB touched
Stop Loss: 0.7% from entry
Take Profit: based on opposite BB
"""

import pandas as pd

from config.settings import (
    BB_PARAMS,
    RSI_PARAMS,
    SIGNAL_CONFIDENCE_HIGH,
    SIGNAL_CONFIDENCE_MEDIUM,
)
from strategies.base import BaseStrategy

RSI_BB_SL_PERCENT = 0.007  # 0.7% stop loss for this strategy


class RSIBBStrategy(BaseStrategy):
    """RSI + Bollinger Bands mean-reversion strategy for scalping."""

    # Mean reversion needs a range to revert within — suppress signals when
    # ADX confirms a strong trend (see require_ranging in BaseStrategy).
    require_ranging: bool = True

    # Exit target is "distance back to bb_middle", not a momentum continuation —
    # must not be overwritten by TimesFM's trend-forecast SL/TP.
    mean_reversion: bool = True

    @property
    def name(self) -> str:
        return 'rsi_bb'

    @property
    def timeframe(self) -> str:
        return '1m'

    @property
    def description(self) -> str:
        return (
            f"RSI({RSI_PARAMS['period']}) oversold/overbought + "
            f"BB({BB_PARAMS['period']},{BB_PARAMS['std_dev']}) touch. "
            f"SL: {RSI_BB_SL_PERCENT*100:.1f}%"
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate BUY/SELL signals based on RSI extremes + BB touch.

        Required columns: close, rsi, bb_lower, bb_upper, bb_middle
        """
        df = self._init_signal_columns(df)

        required = ['close', 'rsi', 'bb_lower', 'bb_upper', 'bb_middle']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns for {self.name}: {missing}")

        valid = df['rsi'].notna() & df['bb_lower'].notna()

        # Market regime filter: skip signals in strongly trending markets —
        # a mean-reversion entry needs room to revert before the stop is hit.
        if self.require_ranging:
            ranging = ~self._is_trending(df)
            valid = valid & ranging

        oversold = RSI_PARAMS['oversold']
        overbought = RSI_PARAMS['overbought']

        # RSI conditions
        rsi_oversold = df['rsi'] < oversold
        rsi_overbought = df['rsi'] > overbought

        # BB touch conditions (price at or below/above band)
        touches_lower_bb = df['close'] <= df['bb_lower']
        touches_upper_bb = df['close'] >= df['bb_upper']

        # BUY: RSI oversold + touches lower BB (mean reversion up expected)
        buy_mask = valid & rsi_oversold & touches_lower_bb
        df.loc[buy_mask, 'signal'] = 'BUY'
        df.loc[buy_mask, 'entry_price'] = df.loc[buy_mask, 'close']
        if self.use_atr_sl:
            sl, tp = self._atr_sl_tp(df, buy_mask, 'BUY')
            if sl is not None:
                df.loc[buy_mask, 'stop_loss'] = sl
                df.loc[buy_mask, 'take_profit'] = tp
        else:
            df.loc[buy_mask, 'stop_loss'] = df.loc[buy_mask, 'close'] * (1 - RSI_BB_SL_PERCENT)
            df.loc[buy_mask, 'take_profit'] = df.loc[buy_mask, 'bb_middle']  # Target: middle BB

        # SELL: RSI overbought + touches upper BB (mean reversion down expected)
        sell_mask = valid & rsi_overbought & touches_upper_bb
        df.loc[sell_mask, 'signal'] = 'SELL'
        df.loc[sell_mask, 'entry_price'] = df.loc[sell_mask, 'close']
        if self.use_atr_sl:
            sl, tp = self._atr_sl_tp(df, sell_mask, 'SELL')
            if sl is not None:
                df.loc[sell_mask, 'stop_loss'] = sl
                df.loc[sell_mask, 'take_profit'] = tp
        else:
            df.loc[sell_mask, 'stop_loss'] = df.loc[sell_mask, 'close'] * (1 + RSI_BB_SL_PERCENT)
            df.loc[sell_mask, 'take_profit'] = df.loc[sell_mask, 'bb_middle']  # Target: middle BB

        # Confidence: stronger when RSI is more extreme
        signal_mask = buy_mask | sell_mask
        rsi_distance = (df['rsi'] - 50).abs() / 50  # 0-1 scale from neutral
        df.loc[signal_mask, 'confidence'] = (
            rsi_distance[signal_mask].clip(0, 1)
            * (SIGNAL_CONFIDENCE_HIGH - SIGNAL_CONFIDENCE_MEDIUM)
            + SIGNAL_CONFIDENCE_MEDIUM
        )

        return df
