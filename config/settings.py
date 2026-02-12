"""
CFD Trading System Configuration
================================
Central configuration file for all parameters.
"""

import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# ============================================
# TICKERS & INSTRUMENTS
# ============================================

TICKERS = {
    'indices': ['SPY', 'QQQ'],                    # S&P 500, Nasdaq
    'commodities': ['GLD', 'USO'],                # Gold, Oil
    'crypto': ['BTC-USD', 'ETH-USD'],             # Bitcoin, Ethereum (Yahoo Finance)
    'stocks': ['AAPL', 'MSFT', 'GOOGL', 'TSLA']  # Popular stocks
}

# Default tickers for testing
DEFAULT_TICKERS = ['SPY', 'GLD', 'BTC-USD']

# ============================================
# TIMEFRAMES & DATES
# ============================================

# Data intervals for different strategies
SCALPING_INTERVAL = '1m'   # 1-minute for scalping
SWING_INTERVAL = '1d'      # Daily for swing trading
HOURLY_INTERVAL = '1h'     # Hourly for position trading

# Historical data range
START_DATE = '2024-01-01'
END_DATE = None            # None = today

# Lookback periods for different purposes
BACKTEST_LOOKBACK_DAYS = 365  # How much historical data for backtesting
SIGNAL_LOOKBACK_BARS = 500    # Number of bars to load for signal generation

# ============================================
# BACKTESTING PARAMETERS
# ============================================

INITIAL_CAPITAL = 10000        # Starting capital in USD
RISK_PER_TRADE = 0.02          # 2% risk per trade
COMMISSION = 0.001             # 0.1% commission per trade (adjust for broker)
SLIPPAGE = 0.0005              # 0.05% slippage

# ============================================
# STRATEGY PARAMETERS
# ============================================

# MACD Parameters (for MACD + VWAP strategy)
MACD_PARAMS = {
    'fast': 12,
    'slow': 26,
    'signal': 9
}

# RSI Parameters (for RSI + Bollinger Bands strategy)
RSI_PARAMS = {
    'period': 14,
    'overbought': 70,
    'oversold': 30
}

# Bollinger Bands Parameters
BB_PARAMS = {
    'period': 20,
    'std_dev': 2
}

# Moving Average Parameters (for MA Crossover strategy)
MA_PARAMS = {
    'fast': 50,
    'slow': 200
}

# Stochastic Oscillator Parameters
STOCHASTIC_PARAMS = {
    'period': 14,
    'smooth_k': 3,
    'smooth_d': 3,
    'overbought': 80,
    'oversold': 20
}

# ADX Parameters
ADX_PARAMS = {
    'period': 14,
    'strong_trend': 25
}

# ============================================
# MACHINE LEARNING PARAMETERS
# ============================================

# Hybrid LSTM+Transformer Model Configuration
ML_CONFIG = {
    'lookback_window': 60,           # 60 timesteps (60 min for 1m data)
    'features': ['open', 'high', 'low', 'close', 'volume', 'rsi', 'macd', 'bb_upper', 'bb_lower'],
    'batch_size': 32,
    'epochs': 50,
    'validation_split': 0.15,
    'test_split': 0.15,
    'early_stopping_patience': 10,
    'learning_rate': 0.001
}

# LSTM Layers
LSTM_LAYERS = {
    'lstm1_units': 50,
    'lstm2_units': 50,
    'dropout_rate': 0.2
}

# Transformer Encoder
TRANSFORMER_CONFIG = {
    'n_heads': 2,                    # Multi-head attention heads
    'd_model': 64,                   # Model dimension (must be divisible by n_heads)
    'ff_dim': 128,                   # Feed-forward hidden dimension
    'transformer_dropout': 0.1,
    'dense_units': 25,               # Final dense layer before output
}

# Data normalization
NORMALIZE_FEATURES = True
SCALER_TYPE = 'minmax'  # 'minmax' or 'standard'

# ============================================
# DATA SOURCES
# ============================================

# Yahoo Finance settings
YFINANCE_AUTO_ADJUST = False  # Don't auto-adjust for splits/dividends
YFINANCE_PREPOST = False      # Don't include pre/post market data
YFINANCE_THREADS = 4           # Number of threads for parallel downloads

# CCXT (Bitso) settings
CCXT_EXCHANGE = 'bitso'
CCXT_ENABLE_RATEIMIT = True
CCXT_TIMEOUT = 30000  # 30 seconds

# Bitso API (if using direct API instead of CCXT)
BITSO_API_URL = 'https://api.bitso.com/v3'
BITSO_API_KEY = os.getenv('BITSO_API_KEY', '')
BITSO_API_SECRET = os.getenv('BITSO_API_SECRET', '')

# ============================================
# DATA & LOGGING
# ============================================

# Directory structure
DATA_DIR = PROJECT_ROOT / 'data'
RAW_DATA_DIR = DATA_DIR / 'raw'
PROCESSED_DATA_DIR = DATA_DIR / 'processed'
MODELS_DIR = PROJECT_ROOT / 'models'
MODELS_SAVED_DIR = MODELS_DIR / 'saved'
LOGS_DIR = PROJECT_ROOT / 'logs'
BACKTEST_RESULTS_DIR = PROJECT_ROOT / 'results'

# Create directories if they don't exist
for directory in [RAW_DATA_DIR, PROCESSED_DATA_DIR, MODELS_SAVED_DIR, LOGS_DIR, BACKTEST_RESULTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Logging configuration
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = LOGS_DIR / 'trading_system.log'
SIGNALS_LOG_FILE = LOGS_DIR / 'signals.csv'

# ============================================
# FEATURE ENGINEERING
# ============================================

# Technical indicators to calculate
INDICATORS_TO_CALCULATE = [
    'rsi', 'macd', 'bollinger_bands', 'ema',
    'sma', 'vwap', 'stochastic', 'adx', 'atr', 'obv'
]

# ============================================
# SIGNAL GENERATION
# ============================================

# Signal confidence thresholds
SIGNAL_CONFIDENCE_HIGH = 0.8
SIGNAL_CONFIDENCE_MEDIUM = 0.6
SIGNAL_CONFIDENCE_LOW = 0.4

# Take profit and stop loss percentages
SCALPING_TP_PERCENT = 0.01      # 1% for scalping
SCALPING_SL_PERCENT = 0.005     # 0.5% for scalping

SWING_TP_PERCENT = 0.03         # 3% for swing
SWING_SL_PERCENT = 0.02         # 2% for swing

# ============================================
# PERFORMANCE METRICS
# ============================================

# Metrics to calculate after backtesting
METRICS = [
    'total_return',
    'annual_return',
    'sharpe_ratio',
    'sortino_ratio',
    'max_drawdown',
    'win_rate',
    'profit_factor',
    'average_trade_duration',
    'consecutive_wins',
    'consecutive_losses'
]

# ============================================
# SYSTEM SETTINGS
# ============================================

# Verbosity level
DEBUG = False
VERBOSE = True

# Number of parallel jobs for data processing
NUM_JOBS = 4

# Random seed for reproducibility
RANDOM_SEED = 42

# ============================================
# BROKER SETTINGS (Future)
# ============================================

# OANDA settings (for future API integration)
OANDA_ACCOUNT_ID = os.getenv('OANDA_ACCOUNT_ID', '')
OANDA_API_KEY = os.getenv('OANDA_API_KEY', '')
OANDA_ENVIRONMENT = 'practice'  # 'practice' or 'live'

# Interactive Brokers settings
IB_ACCOUNT = os.getenv('IB_ACCOUNT', '')
IB_HOST = '127.0.0.1'
IB_PORT = 7497

# ============================================
# ALERTS & NOTIFICATIONS (Future)
# ============================================

# Email alerts
EMAIL_ALERTS_ENABLED = False
EMAIL_FROM = os.getenv('EMAIL_FROM', '')
EMAIL_TO = os.getenv('EMAIL_TO', '')
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

# Telegram alerts
TELEGRAM_ALERTS_ENABLED = False
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# ============================================
# TRADING RULES
# ============================================

# Maximum number of concurrent positions
MAX_CONCURRENT_POSITIONS = 3

# Minimum price movement for entry
MIN_PRICE_MOVEMENT = 0.0001

# Market hours (24-hour format)
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 16

# Don't trade during these hours
NO_TRADE_HOURS = [9.5, 10.0]  # Avoid opening bell volatility

print("✅ Configuration loaded successfully")
print(f"📊 Backtesting capital: ${INITIAL_CAPITAL:,.0f}")
print(f"📈 Risk per trade: {RISK_PER_TRADE*100:.1f}%")
print(f"🎯 Default tickers: {DEFAULT_TICKERS}")
