from strategies.scalping.macd_vwap import MACDVWAPStrategy
from strategies.scalping.pivot_points import PivotPointsStrategy
from strategies.scalping.rsi_bb import RSIBBStrategy
from strategies.scalping.supertrend import SuperTrendStrategy
from strategies.swing.fibonacci import FibonacciStrategy
from strategies.swing.ma_crossover import MACrossoverStrategy

STRATEGY_MAP = {
    'macd_vwap': MACDVWAPStrategy,
    'rsi_bb': RSIBBStrategy,
    'ma_crossover': MACrossoverStrategy,
    'supertrend': SuperTrendStrategy,
    'pivot_points': PivotPointsStrategy,
    'fibonacci': FibonacciStrategy,
}

__all__ = [
    'MACDVWAPStrategy', 'RSIBBStrategy', 'MACrossoverStrategy',
    'SuperTrendStrategy', 'PivotPointsStrategy', 'FibonacciStrategy',
    'STRATEGY_MAP',
]
