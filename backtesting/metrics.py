"""
Performance Metrics Module
===========================
Extracts and formats backtesting performance metrics.
"""

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from backtesting.engine import BacktestResult

logger = logging.getLogger(__name__)


def _safe_float(value, default: float = 0.0) -> float:
    """Convert a value to float, replacing NaN/inf with default."""
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


class PerformanceMetrics:
    """Extracts performance metrics from backtest results."""

    @staticmethod
    def calculate_all(result: BacktestResult) -> dict[str, Any]:
        """Calculate all performance metrics from a backtest result.

        Args:
            result: BacktestResult from BacktestEngine.run().

        Returns:
            Dict with all metrics.
        """
        pf = result.portfolio
        stats = pf.stats()

        metrics = {
            'strategy': result.strategy_name,
            'ticker': result.ticker,
            'interval': result.interval,
            'initial_capital': result.initial_capital,
            'final_value': _safe_float(stats.get('End Value', 0)),
            'total_return_pct': _safe_float(stats.get('Total Return [%]', 0)),
            'total_trades': int(stats.get('Total Trades', 0)),
            'win_rate_pct': _safe_float(stats.get('Win Rate [%]', 0)),
            'best_trade_pct': _safe_float(stats.get('Best Trade [%]', 0)),
            'worst_trade_pct': _safe_float(stats.get('Worst Trade [%]', 0)),
            'avg_winning_trade_pct': _safe_float(stats.get('Avg Winning Trade [%]', 0)),
            'avg_losing_trade_pct': _safe_float(stats.get('Avg Losing Trade [%]', 0)),
            'max_drawdown_pct': _safe_float(stats.get('Max Drawdown [%]', 0)),
            'sharpe_ratio': _safe_float(stats.get('Sharpe Ratio', 0)),
            'sortino_ratio': _safe_float(stats.get('Sortino Ratio', 0)),
            'profit_factor': _safe_float(stats.get('Profit Factor', 0)),
            'expectancy': _safe_float(stats.get('Expectancy', 0)),
        }

        # Calculate additional custom metrics
        trades = pf.trades.records_readable
        if len(trades) > 0:
            pnl = trades['PnL']
            wins = pnl[pnl > 0]
            losses = pnl[pnl < 0]
            metrics['consecutive_wins'] = int(_max_consecutive(pnl > 0))
            metrics['consecutive_losses'] = int(_max_consecutive(pnl <= 0))
            metrics['avg_trade_duration'] = str(trades['Duration'].mean()) if 'Duration' in trades.columns else 'N/A'
        else:
            metrics['consecutive_wins'] = 0
            metrics['consecutive_losses'] = 0
            metrics['avg_trade_duration'] = 'N/A'

        return metrics

    @staticmethod
    def format_summary(metrics: dict[str, Any]) -> str:
        """Format metrics as a readable terminal summary.

        Args:
            metrics: Dict from calculate_all().

        Returns:
            Formatted string.
        """
        lines = [
            "",
            "=" * 50,
            f"  BACKTEST RESULTS: {metrics['strategy'].upper()}",
            f"  Ticker: {metrics['ticker']} | Interval: {metrics['interval']}",
            "=" * 50,
            f"  Initial Capital:    ${metrics['initial_capital']:>12,.2f}",
            f"  Final Value:        ${metrics['final_value']:>12,.2f}",
            f"  Total Return:       {metrics['total_return_pct']:>12.2f}%",
            "-" * 50,
            f"  Total Trades:       {metrics['total_trades']:>12}",
            f"  Win Rate:           {metrics['win_rate_pct']:>12.1f}%",
            f"  Profit Factor:      {metrics['profit_factor']:>12.2f}",
            f"  Expectancy:         {metrics['expectancy']:>12.4f}",
            "-" * 50,
            f"  Best Trade:         {metrics['best_trade_pct']:>12.2f}%",
            f"  Worst Trade:        {metrics['worst_trade_pct']:>12.2f}%",
            f"  Avg Winner:         {metrics['avg_winning_trade_pct']:>12.2f}%",
            f"  Avg Loser:          {metrics['avg_losing_trade_pct']:>12.2f}%",
            "-" * 50,
            f"  Max Drawdown:       {metrics['max_drawdown_pct']:>12.2f}%",
            f"  Sharpe Ratio:       {metrics['sharpe_ratio']:>12.2f}",
            f"  Sortino Ratio:      {metrics['sortino_ratio']:>12.2f}",
            "-" * 50,
            f"  Consec. Wins:       {metrics['consecutive_wins']:>12}",
            f"  Consec. Losses:     {metrics['consecutive_losses']:>12}",
            f"  Avg Duration:       {metrics['avg_trade_duration']:>12}",
            "=" * 50,
        ]
        return "\n".join(lines)


def _max_consecutive(mask: pd.Series) -> int:
    """Count maximum consecutive True values in a boolean series."""
    if mask.empty:
        return 0
    groups = mask.ne(mask.shift()).cumsum()
    counts = mask.groupby(groups).sum()
    return int(counts.max()) if len(counts) > 0 else 0
