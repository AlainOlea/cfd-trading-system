from strategies.scalping.macd_vwap import MACDVWAPStrategy
from strategies.scalping.rsi_bb import RSIBBStrategy
from strategies.swing.ma_crossover import MACrossoverStrategy

STRATEGY_MAP = {
    'macd_vwap': MACDVWAPStrategy,
    'rsi_bb': RSIBBStrategy,
    'ma_crossover': MACrossoverStrategy,
}

__all__ = ['MACDVWAPStrategy', 'RSIBBStrategy', 'MACrossoverStrategy', 'STRATEGY_MAP']
