"""
Base Strategy Module
====================
Abstract base class for all trading strategies.
"""

from abc import ABC, abstractmethod

import pandas as pd

from config.settings import INITIAL_CAPITAL, RISK_PER_TRADE


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""

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
    def _init_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Initialize signal columns with defaults."""
        df = df.copy()
        df['signal'] = 'HOLD'
        df['entry_price'] = 0.0
        df['stop_loss'] = 0.0
        df['take_profit'] = 0.0
        df['confidence'] = 0.0
        return df
