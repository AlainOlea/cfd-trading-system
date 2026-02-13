"""
Backtesting Engine
==================
Runs strategy backtests using VectorBT for high-performance simulation.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import vectorbt as vbt

from config.settings import COMMISSION, INITIAL_CAPITAL, SLIPPAGE

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Container for backtest results."""
    strategy_name: str
    ticker: str
    interval: str
    portfolio: vbt.Portfolio
    signals_df: pd.DataFrame
    initial_capital: float


class BacktestEngine:
    """Runs backtests on trading strategies using VectorBT."""

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        commission: float = COMMISSION,
        slippage: float = SLIPPAGE,
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(
        self,
        strategy,
        df: pd.DataFrame,
        ticker: str = '',
        interval: str = '',
    ) -> BacktestResult:
        """Run a backtest for a given strategy on OHLCV+indicators data.

        Args:
            strategy: Strategy instance (must have generate_signals method).
            df: DataFrame with OHLCV + indicator columns.
            ticker: Ticker symbol for labeling.
            interval: Data interval for labeling.

        Returns:
            BacktestResult with portfolio and metrics.
        """
        logger.info(f"Running backtest: {strategy.name} on {ticker} ({interval})")

        # Generate signals
        signals_df = strategy.generate_signals(df)

        # Convert signals to boolean entry/exit arrays
        entries = signals_df['signal'] == 'BUY'
        exits = signals_df['signal'] == 'SELL'

        # Build portfolio with VectorBT
        portfolio = vbt.Portfolio.from_signals(
            close=signals_df['close'],
            entries=entries,
            exits=exits,
            init_cash=self.initial_capital,
            fees=self.commission,
            slippage=self.slippage,
            freq=self._interval_to_freq(interval),
        )

        result = BacktestResult(
            strategy_name=strategy.name,
            ticker=ticker,
            interval=interval,
            portfolio=portfolio,
            signals_df=signals_df,
            initial_capital=self.initial_capital,
        )

        logger.info(
            f"Backtest complete: {portfolio.stats()['Total Trades']} trades, "
            f"Return: {portfolio.stats()['Total Return [%]']:.2f}%"
        )
        return result

    @staticmethod
    def _interval_to_freq(interval: str) -> str | None:
        """Convert interval string to pandas frequency."""
        freq_map = {
            '1m': '1min',
            '5m': '5min',
            '15m': '15min',
            '1h': '1h',
            '1d': '1D',
        }
        return freq_map.get(interval)
