"""
Base Strategy Module
====================
Abstract base class for all trading strategies.
"""

from abc import ABC, abstractmethod

import pandas as pd

from config.settings import INITIAL_CAPITAL, RISK_PER_TRADE

ADX_TREND_THRESHOLD = 20  # ADX above this value = trending market
ATR_SL_MULTIPLIER = 1.5   # SL = entry ± 1.5 × ATR(14)
ATR_TP_MULTIPLIER = 3.0   # TP = entry ± 3.0 × ATR(14)


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""

    # Subclasses can set this to True to suppress BUY/SELL signals in ranging markets.
    require_trend: bool = False

    # Set to True to use ATR-based dynamic SL/TP instead of fixed percentages.
    # SL = entry ± ATR_SL_MULTIPLIER × ATR(14)
    # TP = entry ± ATR_TP_MULTIPLIER × ATR(14)
    use_atr_sl: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier (e.g. 'macd_vwap')."""

    @property
    @abstractmethod
    def timeframe(self) -> str:
        """Recommended timeframe (e.g. '1m', '1d')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable strategy description."""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals from a DataFrame with indicators.

        Args:
            df: DataFrame with OHLCV + indicator columns.

        Returns:
            DataFrame with added columns:
            - signal: 'BUY', 'SELL', or 'HOLD'
            - entry_price: suggested entry price
            - stop_loss: stop loss price
            - take_profit: take profit price
            - confidence: float 0.0-1.0
        """

    @staticmethod
    def calculate_position_size(
        capital: float = INITIAL_CAPITAL,
        risk_per_trade: float = RISK_PER_TRADE,
        stop_loss_pct: float = 0.01,
    ) -> float:
        """Calculate position size based on risk management rules.

        Args:
            capital: Available trading capital.
            risk_per_trade: Fraction of capital to risk (e.g. 0.02 = 2%).
            stop_loss_pct: Stop loss as fraction of entry price.

        Returns:
            Position size in currency units.
        """
        if stop_loss_pct <= 0:
            return 0.0
        risk_amount = capital * risk_per_trade
        return risk_amount / stop_loss_pct

    @staticmethod
    def _atr_sl_tp(
        df: pd.DataFrame,
        mask: pd.Series,
        direction: str,
        sl_mult: float = ATR_SL_MULTIPLIER,
        tp_mult: float = ATR_TP_MULTIPLIER,
    ) -> tuple[pd.Series | None, pd.Series | None]:
        """Compute ATR-based stop-loss and take-profit for a set of rows.

        Args:
            df: DataFrame with 'atr' and 'close' columns.
            mask: Boolean mask selecting the rows to compute SL/TP for.
            direction: 'BUY' or 'SELL'.
            sl_mult: ATR multiplier for stop-loss (default 1.5).
            tp_mult: ATR multiplier for take-profit (default 3.0).

        Returns:
            Tuple (stop_loss_series, take_profit_series) aligned with df[mask].
            Returns (None, None) if 'atr' column is missing.
        """
        if 'atr' not in df.columns:
            return None, None
        entry = df.loc[mask, 'close']
        atr = df.loc[mask, 'atr']
        if direction == 'BUY':
            return entry - sl_mult * atr, entry + tp_mult * atr
        return entry + sl_mult * atr, entry - tp_mult * atr

    @staticmethod
    def _is_trending(df: pd.DataFrame, threshold: float = ADX_TREND_THRESHOLD) -> pd.Series:
        """Return a boolean Series: True where ADX confirms a trending market.

        Strategies with require_trend=True use this to filter out signals
        generated during ranging/choppy conditions (ADX < threshold).

        Args:
            df: DataFrame with an 'adx' column (added by TechnicalIndicators).
            threshold: ADX value above which the market is considered trending.

        Returns:
            Boolean Series aligned with df.index. Falls back to all-True if
            'adx' column is missing (safe degradation).
        """
        if 'adx' not in df.columns:
            return pd.Series(True, index=df.index)
        return df['adx'] >= threshold

    @staticmethod
    def _init_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Initialize signal columns with defaults."""
        df = df.copy()
        df['signal'] = 'HOLD'
        df['entry_price'] = 0.0
        df['stop_loss'] = 0.0
        df['take_profit'] = 0.0
        df['confidence'] = 0.0
        return df
