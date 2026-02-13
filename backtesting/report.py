"""
Backtest Report Module
=======================
Generates HTML reports with equity curves and trade analysis.
"""

import logging
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtesting.engine import BacktestResult
from config.settings import BACKTEST_RESULTS_DIR

logger = logging.getLogger(__name__)


class BacktestReport:
    """Generates visual backtest reports."""

    @staticmethod
    def generate_html(
        result: BacktestResult,
        metrics: dict[str, Any],
    ) -> Path:
        """Generate an HTML report with equity curve and trade markers.

        Args:
            result: BacktestResult from engine.
            metrics: Dict from PerformanceMetrics.calculate_all().

        Returns:
            Path to generated HTML file.
        """
        pf = result.portfolio

        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.25, 0.25],
            subplot_titles=('Equity Curve', 'Price + Signals', 'Drawdown'),
        )

        # Row 1: Equity curve
        equity = pf.value()
        fig.add_trace(
            go.Scatter(
                x=equity.index, y=equity.values,
                name='Portfolio Value',
                line=dict(color='#2196F3', width=2),
            ),
            row=1, col=1,
        )

        # Row 2: Price with buy/sell markers
        close = result.signals_df['close']
        fig.add_trace(
            go.Scatter(
                x=close.index, y=close.values,
                name='Close Price',
                line=dict(color='#757575', width=1),
            ),
            row=2, col=1,
        )

        # Buy markers
        buys = result.signals_df[result.signals_df['signal'] == 'BUY']
        if not buys.empty:
            fig.add_trace(
                go.Scatter(
                    x=buys.index, y=buys['close'],
                    mode='markers', name='BUY',
                    marker=dict(symbol='triangle-up', size=10, color='#4CAF50'),
                ),
                row=2, col=1,
            )

        # Sell markers
        sells = result.signals_df[result.signals_df['signal'] == 'SELL']
        if not sells.empty:
            fig.add_trace(
                go.Scatter(
                    x=sells.index, y=sells['close'],
                    mode='markers', name='SELL',
                    marker=dict(symbol='triangle-down', size=10, color='#F44336'),
                ),
                row=2, col=1,
            )

        # Row 3: Drawdown
        drawdown = pf.drawdown() * 100
        fig.add_trace(
            go.Scatter(
                x=drawdown.index, y=drawdown.values,
                name='Drawdown %',
                fill='tozeroy',
                line=dict(color='#F44336', width=1),
            ),
            row=3, col=1,
        )

        # Layout
        title = (
            f"Backtest: {metrics['strategy'].upper()} | "
            f"{metrics['ticker']} {metrics['interval']} | "
            f"Return: {metrics['total_return_pct']:.2f}% | "
            f"Win Rate: {metrics['win_rate_pct']:.1f}% | "
            f"Trades: {metrics['total_trades']}"
        )
        fig.update_layout(
            title=title,
            height=900,
            template='plotly_dark',
            showlegend=True,
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
        )
        fig.update_yaxes(title_text='Value ($)', row=1, col=1)
        fig.update_yaxes(title_text='Price', row=2, col=1)
        fig.update_yaxes(title_text='Drawdown %', row=3, col=1)

        # Save
        safe_ticker = result.ticker.replace('/', '_').replace('-', '_')
        filename = f"backtest_{result.strategy_name}_{safe_ticker}_{result.interval}.html"
        filepath = BACKTEST_RESULTS_DIR / filename
        fig.write_html(str(filepath))
        logger.info(f"Report saved to {filepath}")
        return filepath
