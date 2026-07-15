"""
CFD Trading System Configuration
================================
Central configuration file for all parameters.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from config.ticker_types import TickerConfig

# Load environment variables from .env
load_dotenv(Path(__file__).parent.parent / '.env')

# Allow TensorFlow to grow GPU memory on demand instead of pre-allocating a
# fixed block at startup. Without this, TF grabs VRAM that blocks PyTorch
# cuTLASS kernels (used by TimesFM) from launching.
os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# ============================================
# TICKERS & INSTRUMENTS
# ============================================

TICKERS = {
    'indices': [
        'SPY',      # S&P 500
        'QQQ',      # Nasdaq 100
        'IWM',      # Russell 2000
        'VTI',      # Total US Market
    ],
    'commodities': [
        'GLD',      # Gold
        'USO',      # Crude Oil
        'DBC',      # Commodities Index
        'UNG',      # Natural Gas
    ],
    'crypto': [
        'BTC-USD',  # Bitcoin
        'ETH-USD',  # Ethereum
        'SOL-USD',  # Solana
        'ADA-USD',  # Cardano
    ],
    'stocks': [
        'AAPL',     # Apple
        'MSFT',     # Microsoft
        'GOOGL',    # Google
        'TSLA',     # Tesla
        'NVDA',     # NVIDIA
        'AMZN',     # Amazon
        'META',     # Meta/Facebook
        'NFLX',     # Netflix
    ]
}

# Default tickers for testing (expanded)
DEFAULT_TICKERS = ['SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'SLV', 'USO', 'UNG', 'AAPL', 'NVDA', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD']

# ============================================
# TIMEFRAMES & DATES
# ============================================

# Data intervals for different strategies
SCALPING_INTERVAL = '1h'   # Hourly for scalping (1m requires tick data and different strategy)
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
RISK_PER_TRADE = 0.02          # 2% risk per trade (dynamic: recomputed from live equity per order)

# Portfolio risk limits (enforced by AlpacaBroker.place_signal)
MAX_POSITION_PCT = 0.05        # 5% max per single position (of equity)
MAX_GROSS_EXPOSURE = 0.50      # 50% max total open exposure — aligned with MAX_CONCURRENT_POSITIONS
                                # (10 positions x MAX_POSITION_PCT 5% = 50%; at 30% only 6 fit, making
                                # the 10-position cap unreachable)
MAX_NAME_EXPOSURE = 0.10       # 10% max per single name
MAX_CONCURRENT_POSITIONS = 10  # Hard cap on open positions
DRAWDOWN_WARNING_PCT = 0.05    # 5% drawdown from session high → warn in logs
DRAWDOWN_HALT_PCT = 0.10       # 10% drawdown from session high → reject new entries
CRYPTO_MAX_AGGREGATE = 0.10    # 10% max aggregate crypto exposure
CRYPTO_MAX_SINGLE = 0.03       # 3% max per single crypto position

# CFD cost model (Plus500 spread-based, not commission-based)
# CFDs have no explicit commission — cost is embedded in the bid/ask spread.
# VectorBT applies fees at entry AND exit, so we use half-spread per leg
# (entry cost = spread/2, exit cost = spread/2 → round-trip = full spread).
CFD_SPREADS = {
    'indices':     0.0001,   # SPY, QQQ, IWM — very liquid, ~0.01% spread
    'stocks':      0.0003,   # AAPL, MSFT, NVDA — ~0.03% spread
    'crypto':      0.0040,   # BTC-USD, ETH-USD — ~0.4% spread on Plus500
    'commodities': 0.0002,   # GLD, USO — ~0.02% spread
    'default':     0.0002,
}
CFD_OVERNIGHT_RATE = 0.0001    # ~0.01% per night (based on ~3.65%/yr SOFR proxy)
COMMISSION = CFD_SPREADS['default'] / 2  # Half-spread per leg (round-trip = full spread)
SLIPPAGE = 0.0                 # Spread already captures execution cost for CFDs

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

# SuperTrend Parameters (for SuperTrend strategy)
SUPERTREND_PARAMS = {
    'length': 10,       # ATR lookback
    'multiplier': 3.0,  # ATR band multiplier
}

# Pivot Points Parameters (for Pivot Points strategy)
PIVOT_PARAMS = {
    'proximity_pct': 0.002,  # price within 0.2% of a level counts as a touch
    'rsi_confirm': True,     # require RSI confirmation on bounces
}

# Fibonacci Retracement Parameters (for Fibonacci strategy)
FIBONACCI_PARAMS = {
    'swing_window': 50,           # bars to detect swing high/low
    'levels': [0.382, 0.5, 0.618],  # retracement entry levels
    'proximity_pct': 0.003,       # price within 0.3% of a level counts as a touch
    'sl_level': 0.786,            # stop-loss placed beyond this retracement
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
    'features': [
        # Core OHLCV
        'open', 'high', 'low', 'close', 'volume',
        # Technical indicators (from pandas-ta)
        'rsi', 'macd', 'bb_upper', 'bb_lower',
        # Engineered features (from TechnicalIndicators)
        'return_5d', 'return_20d', 'volatility_20d', 'atr_ratio',
    ],
    'batch_size': 32,
    'epochs': 100,
    'validation_split': 0.15,
    'test_split': 0.15,
    'early_stopping_patience': 20,
    'learning_rate': 0.0005,
    # Walk-forward validation parameters
    'walk_forward': {
        'enabled': False,
        'train_window': 200,
        'test_window': 20,
        'step_size': 20,
        'method': 'anchored',
        'retrain_every_fold': True,
        'min_folds': 3,
    }
}

# LSTM Layers with Regularization
LSTM_LAYERS = {
    'lstm1_units': 50,
    'lstm2_units': 50,
    'dropout_rate': 0.4,             # Aumentado: 0.3 → 0.4 para mayor regularización
    'l2_regularization': 0.02,       # Aumentado: 0.01 → 0.02 para penalización más fuerte
    'use_batch_norm': True,          # Use batch normalization after LSTM
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

# Pipeline version stamped into metadata.json. Bump on breaking changes
# (label scheme, feature set, scaler semantics) so predictor can reject
# incompatible legacy artefacts.
PIPELINE_VERSION = '2.0'

# Thresholds applied to model sigmoid output when generating BUY/SELL
# signals for the OOS financial backtest. Asymmetric band leaves a HOLD
# zone in the middle to avoid trading low-conviction predictions.
ML_SIGNAL_THRESHOLDS = {
    'buy_above': 0.55,
    'sell_below': 0.45,
}

# Minimum OOS metrics required to mark a trained model as `promoted: True`
# in metadata.json. Predictor refuses to load non-promoted models unless
# explicitly overridden.
# Adjusted per Piovezan et al. (2023) and Henriques & Sadorsky (2023):
# gate should be calibrated to data volume, not absolute thresholds.
ML_PROMOTION_GATE = {
    'min_sharpe': 0.0,
    'min_profit_factor': 0.8,
    'min_trades': 3,
    'max_drawdown_pct': -30.0,
}

# XGBoost Model Configuration (primary ML model — tree-based,
# regularized, outperforms LSTM on small datasets per literature)
XGBOOST_CONFIG = {
    'n_estimators': 200,
    'max_depth': 5,
    'learning_rate': 0.05,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'min_child_weight': 3,
    'reg_alpha': 0.1,
    'reg_lambda': 1.0,
    'eval_metric': 'logloss',
}

# Triple-barrier label configuration (Lopez de Prado method)
# Labels are created when price touches one of three barriers:
# profit (upper), stop-loss (lower), or time expiration (vertical).
# When use_binary_threshold=True, uses simple threshold-based binary labels
# (per Piovezan et al. 2023 recommendation for small datasets).
TRIPLE_BARRIER_CONFIG = {
    'profit_factor': 1.5,
    'stop_factor': 1.5,
    'time_horizon': 5,
    'use_binary_threshold': True,    # Binary label with cost-aware threshold
    'binary_threshold': 0.005,       # 0.5% min move to be tradeable
}

# ============================================
# DATA SOURCES
# ============================================

# Yahoo Finance settings
YFINANCE_AUTO_ADJUST = True   # Adjust prices for splits and dividends (avoids false jumps in history)
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

# Alpaca Data API settings (free tier: 200 calls/min, 7+ years 1-min bars)
ALPACA_DATA_RATE_LIMIT = 200       # Calls per minute
ALPACA_DATA_DEFAULT_CHUNK_DAYS = 90 # Days per batch fetch chunk
ALPACA_DATA_1MIN_YEARS = 3          # Years of 1-min data for model training

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

# Fetch metadata tracker (persists last fetch timestamps)
FETCH_METADATA_FILE = RAW_DATA_DIR / 'fetch_metadata.json'

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
SIGNAL_CONFIDENCE_HIGH = 0.65
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
# ALERTS & NOTIFICATIONS
# ============================================

# Telegram alerts
TELEGRAM_ALERTS_ENABLED = True
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Telegram health check: send data freshness summary after each pipeline run
TELEGRAM_HEALTH_CHECK_ENABLED = os.getenv('TELEGRAM_HEALTH_CHECK_ENABLED', 'true').lower() == 'true'

# Telegram error alerts: send critical/unexpected errors via Telegram
TELEGRAM_ERROR_ALERTS_ENABLED = os.getenv('TELEGRAM_ERROR_ALERTS_ENABLED', 'true').lower() == 'true'

# ============================================
# TRADING RULES
# ============================================

# Minimum price movement for entry
MIN_PRICE_MOVEMENT = 0.0001

# Market hours per instrument type (UTC, 24-hour format)
# Plus500 CFD hours vary by instrument
MARKET_HOURS = {
    'indices': {'open': 23, 'close': 21, 'days': [0, 1, 2, 3, 4, 5, 6]},  # Sun 23-Fri 21 UTC (CFD extended hours)
    'stocks': {'open': 14, 'close': 21, 'days': [0, 1, 2, 3, 4]},        # Mon-Fri 9:30-4 ET -> 14-21 UTC
    'commodities': {'open': 23, 'close': 22, 'days': [0, 1, 2, 3, 4, 5, 6]},   # Nearly 24h Sun-Fri (gold, oil CFDs)
    'crypto': {'open': 0, 'close': 24, 'days': [0, 1, 2, 3, 4, 5, 6]},   # 24/7
}

# Watch mode defaults
WATCH_INTERVAL_SECONDS = 900  # 15 minutes default
WATCH_STRATEGIES = ['macd_vwap', 'rsi_bb']  # Default strategies for watch mode

# ============================================
# UNIFIED PIPELINE CONFIGURATION
# ============================================

# Unified pipeline ticker configurations
# TickerConfig fields: (ticker, category, intervals, strategies, use_ml, use_news, confluence_min)
PIPELINE_TICKERS: list[TickerConfig] = [
    # Indices
    TickerConfig('SPY', 'indices', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('QQQ', 'indices', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb', 'supertrend'], True, True, 2),
    TickerConfig('IWM', 'indices', ['1d', '1h', '1m'], ['macd_vwap', 'supertrend', 'pivot_points'], True, True, 2),
    TickerConfig('DIA', 'indices', ['1d', '1h', '1m'], ['macd_vwap'], True, True, 2),
    # Commodities
    TickerConfig('GLD', 'commodities', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('SLV', 'commodities', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('USO', 'commodities', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('UNG', 'commodities', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    # Stocks
    TickerConfig('AAPL', 'stocks', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb', 'pivot_points'], True, True, 2),
    TickerConfig('NVDA', 'stocks', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('MSFT', 'stocks', ['1d', '1h', '1m'], ['macd_vwap', 'supertrend'], True, True, 2),
    TickerConfig('AMZN', 'stocks', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('GOOGL', 'stocks', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('META', 'stocks', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    TickerConfig('TSLA', 'stocks', ['1d', '1h', '1m'], ['macd_vwap', 'rsi_bb'], True, True, 2),
    # Crypto
    TickerConfig('BTC-USD', 'crypto', ['1d', '1h', '1m'], ['macd_vwap'], True, True, 2),
    TickerConfig('ETH-USD', 'crypto', ['1d', '1h', '1m'], ['macd_vwap'], True, True, 2),
    TickerConfig('SOL-USD', 'crypto', ['1d', '1h', '1m'], ['macd_vwap'], True, False, 2),
    TickerConfig('XRP-USD', 'crypto', ['1d', '1h', '1m'], ['macd_vwap'], True, True, 2),
]

print("✅ Configuration loaded successfully")
print(f"📊 Backtesting capital: ${INITIAL_CAPITAL:,.0f}")
print(f"📈 Risk per trade: {RISK_PER_TRADE*100:.1f}%")
print(f"🎯 Default tickers: {DEFAULT_TICKERS}")
