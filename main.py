#!/usr/bin/env python3
"""
CFD Trading System - Main CLI Entry Point
==========================================
Command-line interface for the trading system.

Usage:
    python main.py fetch-data --ticker SPY --interval 1m --days 30
    python main.py backtest --strategy macd_vwap --ticker SPY --interval 1m
    python main.py signal --strategy macd_vwap --ticker SPY
    python main.py train-lstm --ticker SPY --epochs 50
    python main.py list-strategies
    python main.py list-tickers
"""

import click
import logging
from pathlib import Path
from datetime import datetime
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    DEFAULT_TICKERS, SCALPING_INTERVAL, SWING_INTERVAL,
    LOG_FILE, LOG_LEVEL, DATA_DIR, RAW_DATA_DIR
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# COMMANDS GROUP
# ============================================

@click.group()
def cli():
    """
    CFD Trading System - Automated Technical Analysis & Backtesting

    A Python-based system for technical analysis, backtesting, and trading signal generation.
    Supports multiple strategies: MACD+VWAP, RSI+Bollinger Bands, MA Crossover.
    """
    logger.info("=" * 60)
    logger.info("CFD Trading System Started")
    logger.info("=" * 60)

# ============================================
# COMMAND: FETCH DATA
# ============================================

@cli.command('fetch-data')
@click.option('--ticker', default='SPY', help='Ticker symbol (e.g., SPY, GLD, BTC-USD)')
@click.option('--interval', default='1m', type=click.Choice(['1m', '5m', '15m', '1h', '1d']),
              help='Data interval')
@click.option('--days', default=30, type=int, help='Number of days of historical data')
@click.option('--source', default='yfinance', type=click.Choice(['yfinance', 'bitso']),
              help='Data source')
def fetch_data(ticker, interval, days, source):
    """Download historical OHLCV data for a ticker."""
    try:
        click.echo(f"\n📥 Fetching data...")
        click.echo(f"   Ticker: {ticker}")
        click.echo(f"   Interval: {interval}")
        click.echo(f"   Days: {days}")
        click.echo(f"   Source: {source}")

        from data.fetcher import DataFetcher
        from data.processor import DataProcessor

        fetcher = DataFetcher()
        processor = DataProcessor()

        # Fetch data from selected source
        if source == 'yfinance':
            df = fetcher.fetch_yfinance(ticker, interval, days)
        else:
            df = fetcher.fetch_ccxt(ticker, interval, limit=days * 24)

        # Clean and validate
        df = processor.clean_data(df)
        processor.validate_data(df)

        # Save raw data
        filepath = fetcher.save_to_csv(df, ticker, interval)

        click.echo(f"\n✅ Data fetched successfully!")
        click.echo(f"   Rows: {len(df)}")
        click.echo(f"   Range: {df.index[0]} to {df.index[-1]}")
        click.echo(f"   Saved to: {filepath}")
        logger.info(f"Data fetch completed for {ticker} ({interval}, {days}d) -> {len(df)} rows")

    except Exception as e:
        click.echo(f"\n❌ Error fetching data: {str(e)}", err=True)
        logger.error(f"Error fetching data: {e}", exc_info=True)
        sys.exit(1)

# ============================================
# COMMAND: BACKTEST
# ============================================

@cli.command('backtest')
@click.option('--strategy', required=True, type=click.Choice(['macd_vwap', 'rsi_bb', 'ma_crossover']),
              help='Strategy to backtest')
@click.option('--ticker', default='SPY', help='Ticker symbol')
@click.option('--interval', default='1m', type=click.Choice(['1m', '5m', '15m', '1h', '1d']),
              help='Data interval')
@click.option('--start-date', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', help='End date (YYYY-MM-DD)')
@click.option('--initial-capital', default=10000, type=float, help='Initial capital')
def backtest(strategy, ticker, interval, start_date, end_date, initial_capital):
    """Run backtesting on a strategy."""
    try:
        click.echo(f"\n📊 Running backtest...")
        click.echo(f"   Strategy: {strategy}")
        click.echo(f"   Ticker: {ticker}")
        click.echo(f"   Interval: {interval}")
        click.echo(f"   Capital: ${initial_capital:,.0f}")

        from data.fetcher import DataFetcher
        from data.processor import DataProcessor
        from indicators.technical import TechnicalIndicators
        from strategies import STRATEGY_MAP
        from backtesting.engine import BacktestEngine
        from backtesting.metrics import PerformanceMetrics
        from backtesting.report import BacktestReport

        # 1. Load or fetch data
        fetcher = DataFetcher()
        processor = DataProcessor()

        try:
            df = fetcher.load_from_csv(ticker, interval)
            click.echo(f"   Loaded cached data: {len(df)} rows")
        except FileNotFoundError:
            click.echo(f"   No cached data found, fetching...")
            df = fetcher.fetch_yfinance(ticker, interval, days=365)
            df = processor.clean_data(df)
            fetcher.save_to_csv(df, ticker, interval)
            click.echo(f"   Fetched {len(df)} rows")

        # Filter by date range if provided
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]

        # 2. Add indicators
        click.echo(f"   Computing indicators...")
        df = TechnicalIndicators.add_all_indicators(df)

        # 3. Initialize strategy and engine
        strategy_cls = STRATEGY_MAP[strategy]
        strat = strategy_cls()
        engine = BacktestEngine(initial_capital=initial_capital)

        # 4. Run backtest
        click.echo(f"   Running simulation...")
        result = engine.run(strat, df, ticker=ticker, interval=interval)

        # 5. Calculate metrics
        metrics = PerformanceMetrics.calculate_all(result)
        summary = PerformanceMetrics.format_summary(metrics)
        click.echo(summary)

        # 6. Generate HTML report
        report_path = BacktestReport.generate_html(result, metrics)
        click.echo(f"\n📄 HTML report saved to: {report_path}")
        logger.info(f"Backtest completed: {strategy} on {ticker} ({interval})")

    except Exception as e:
        click.echo(f"\n❌ Error running backtest: {str(e)}", err=True)
        logger.error(f"Error running backtest: {e}", exc_info=True)
        sys.exit(1)

# ============================================
# COMMAND: GENERATE SIGNALS
# ============================================

@cli.command('signal')
@click.option('--strategy', required=True, type=click.Choice(['macd_vwap', 'rsi_bb', 'ma_crossover']),
              help='Strategy to use')
@click.option('--ticker', default='SPY', help='Ticker symbol')
@click.option('--interval', default='1m', type=click.Choice(['1m', '5m', '15m', '1h', '1d']),
              help='Data interval')
@click.option('--use-ml', is_flag=True, help='Use LSTM prediction filter')
def signal(strategy, ticker, interval, use_ml):
    """Generate trading signals for a ticker."""
    try:
        click.echo(f"\n📈 Generating signals...")
        click.echo(f"   Strategy: {strategy}")
        click.echo(f"   Ticker: {ticker}")
        click.echo(f"   Interval: {interval}")
        if use_ml:
            click.echo(f"   ML Filter: ✅ Enabled")

        # TODO: Implement signal generation
        click.echo("\n⏳ This feature will be implemented in Phase 6 (Signal Generator)")
        logger.info(f"Signal generation requested: {strategy} on {ticker}")

    except Exception as e:
        click.echo(f"\n❌ Error generating signals: {str(e)}", err=True)
        logger.error(f"Error generating signals: {e}", exc_info=True)
        sys.exit(1)

# ============================================
# COMMAND: TRAIN LSTM MODEL
# ============================================

@cli.command('train-lstm')
@click.option('--ticker', default='SPY', help='Ticker symbol')
@click.option('--interval', default='1d', type=click.Choice(['1m', '5m', '15m', '1h', '1d']),
              help='Data interval')
@click.option('--epochs', default=50, type=int, help='Number of training epochs')
@click.option('--batch-size', default=32, type=int, help='Batch size')
@click.option('--validation-split', default=0.15, type=float, help='Validation split ratio')
def train_lstm(ticker, interval, epochs, batch_size, validation_split):
    """Train LSTM model for price prediction."""
    try:
        click.echo(f"\n🤖 Training LSTM model...")
        click.echo(f"   Ticker: {ticker}")
        click.echo(f"   Interval: {interval}")
        click.echo(f"   Epochs: {epochs}")
        click.echo(f"   Batch Size: {batch_size}")
        click.echo(f"   Validation Split: {validation_split*100:.0f}%")

        # TODO: Implement LSTM training
        click.echo("\n⏳ This feature will be implemented in Phase 8 (LSTM Model)")
        logger.info(f"LSTM training requested for {ticker}")

    except Exception as e:
        click.echo(f"\n❌ Error training model: {str(e)}", err=True)
        logger.error(f"Error training model: {e}", exc_info=True)
        sys.exit(1)

# ============================================
# COMMAND: LIST STRATEGIES
# ============================================

@cli.command('list-strategies')
def list_strategies():
    """List all available strategies."""
    click.echo("\n📋 Available Strategies:")
    click.echo("\nSCALPING STRATEGIES (1-5 minute timeframes):")
    click.echo("  • macd_vwap: MACD + VWAP crossover")
    click.echo("    Entry: MACD above signal + price above VWAP")
    click.echo("    Exit: MACD below signal OR 1% profit")
    click.echo("    SL: 0.5%")
    click.echo("")
    click.echo("  • rsi_bb: RSI + Bollinger Bands")
    click.echo("    Entry: RSI < 30 (oversold) + lower BB touch")
    click.echo("    Exit: RSI > 70 OR upper BB touch")
    click.echo("    SL: 0.7%")

    click.echo("\nSWING STRATEGIES (Daily timeframes):")
    click.echo("  • ma_crossover: Moving Average Crossover")
    click.echo("    Entry: Golden Cross (SMA50 > SMA200)")
    click.echo("    Exit: Death Cross (SMA50 < SMA200)")
    click.echo("    SL: 2%")

# ============================================
# COMMAND: LIST TICKERS
# ============================================

@cli.command('list-tickers')
def list_tickers():
    """List all available tickers."""
    from config.settings import TICKERS

    click.echo("\n📊 Available Tickers:")
    for category, tickers_list in TICKERS.items():
        click.echo(f"\n{category.upper()}:")
        for ticker in tickers_list:
            click.echo(f"  • {ticker}")

# ============================================
# COMMAND: STATUS
# ============================================

@cli.command('status')
def status():
    """Show system status."""
    click.echo("\n✅ CFD Trading System Status:")
    click.echo(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"   Data Directory: {RAW_DATA_DIR}")
    click.echo(f"   Logs: {LOG_FILE}")
    click.echo(f"   Configuration: config/settings.py")

    # Check if data exists
    data_files = list(RAW_DATA_DIR.glob('*.csv'))
    click.echo(f"\n   Data Files: {len(data_files)}")
    if data_files:
        for f in data_files[:5]:
            click.echo(f"     • {f.name}")

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n\n⏹️  System interrupted by user")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\n❌ Unexpected error: {str(e)}", err=True)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
