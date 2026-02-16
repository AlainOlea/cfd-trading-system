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
import os
import pandas as pd

# Configure GPU for RTX 5060 compatibility (before TensorFlow import)
from config.gpu_config import configure_gpu
configure_gpu()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    DEFAULT_TICKERS, SCALPING_INTERVAL, SWING_INTERVAL,
    LOG_FILE, LOG_LEVEL, DATA_DIR, RAW_DATA_DIR,
    INITIAL_CAPITAL
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
@click.option('--initial-capital', default=INITIAL_CAPITAL, type=float, help='Initial capital')
@click.option('--use-ml', is_flag=True, help='Use ML filter in backtest')
@click.option('--delay', type=float, default=0.0, help='Delay between ML predictions (seconds)')
def backtest(strategy, ticker, interval, start_date, end_date, initial_capital, use_ml, delay):
    """Run backtesting on a strategy."""
    try:
        click.echo(f"\n📊 Running backtest...")
        click.echo(f"   Strategy: {strategy}")
        click.echo(f"   Ticker: {ticker}")
        click.echo(f"   Interval: {interval}")
        click.echo(f"   Capital: ${initial_capital:,.2f}")
        if use_ml:
            click.echo(f"   ML Filter: ✅ Enabled (Delay: {delay}s)")

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

        # 2. Add indicators
        click.echo(f"   Computing indicators...")
        df = TechnicalIndicators.add_all_indicators(df)

        # 3. Initialize strategy, predictor and engine
        strategy_cls = STRATEGY_MAP[strategy]
        strat = strategy_cls()
        
        predictor = None
        if use_ml:
            from models.predictor import PricePredictor
            predictor = PricePredictor()
            try:
                predictor.load(ticker, interval)
            except Exception as e:
                click.echo(f"   ⚠️ Could not load ML model: {e}. Running without ML.")
                predictor = None
                
        engine = BacktestEngine(initial_capital=initial_capital)

        # 4. Run backtest
        click.echo(f"   Running simulation...")
        result = engine.run(strat, df, ticker=ticker, interval=interval, predictor=predictor, delay_sec=delay)

        # 4.5 Filter result by date if provided (AFTER backtest to keep history for ML)
        if start_date or end_date:
            mask = pd.Series(True, index=result.signals_df.index)
            if start_date:
                mask &= (result.signals_df.index >= start_date)
            if end_date:
                mask &= (result.signals_df.index <= end_date)
            
            filtered_signals = result.signals_df[mask]
            
            # Re-run VectorBT on the filtered signals
            import vectorbt as vbt
            new_portfolio = vbt.Portfolio.from_signals(
                close=filtered_signals['close'],
                entries=filtered_signals['signal'] == 'BUY',
                exits=filtered_signals['signal'] == 'SELL',
                init_cash=initial_capital,
                fees=engine.commission,
                slippage=engine.slippage,
                freq=engine._interval_to_freq(interval),
            )
            result.portfolio = new_portfolio
            result.signals_df = filtered_signals

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

        from signals.generator import SignalGenerator
        from signals.manager import SignalManager
        from signals.telegram_bot import TelegramNotifier

        generator = SignalGenerator()
        manager = SignalManager()
        notifier = TelegramNotifier()

        # Generate signal
        signal = generator.generate(
            strategy_name=strategy,
            ticker=ticker,
            interval=interval,
            use_ml=use_ml,
        )

        # Log and display
        manager.log_signal(signal)
        click.echo(manager.format_signal(signal))

        # Send Telegram notification (if configured and signal is actionable)
        if signal.direction != 'HOLD' and notifier.is_configured:
            sent = notifier.send_signal(signal)
            if sent:
                click.echo("   Telegram notification sent")

        # Show recent history
        history = manager.get_history(ticker=ticker, n=5)
        if len(history) > 1:
            click.echo(f"\n  Recent signals for {ticker}:")
            click.echo(manager.format_history(history))

        logger.info(f"Signal generated: {signal.direction} {ticker} @ {signal.entry_price:.2f}")

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

        from data.fetcher import DataFetcher
        from data.processor import DataProcessor
        from indicators.technical import TechnicalIndicators
        from models.hybrid_model import HybridLSTMTransformer
        from models.trainer import ModelTrainer

        # 1. Fetch data
        fetcher = DataFetcher()
        processor = DataProcessor()

        try:
            df = fetcher.load_from_csv(ticker, interval)
            click.echo(f"   Loaded cached data: {len(df)} rows")
        except FileNotFoundError:
            click.echo(f"   Fetching data...")
            df = fetcher.fetch_yfinance(ticker, interval, days=365)
            df = processor.clean_data(df)
            fetcher.save_to_csv(df, ticker, interval)
            click.echo(f"   Fetched {len(df)} rows")

        # 2. Add indicators (features for ML)
        click.echo(f"   Computing indicators...")
        df = TechnicalIndicators.add_all_indicators(df)

        # 3. Prepare data
        trainer = ModelTrainer(
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
        )
        X_train, y_train, X_test, y_test = trainer.prepare_data(df)
        click.echo(f"   Train samples: {len(X_train)}, Test samples: {len(X_test)}")

        # 4. Build model
        hybrid = HybridLSTMTransformer()
        input_shape = (X_train.shape[1], X_train.shape[2])
        hybrid.build(input_shape)
        click.echo(f"   Model params: {hybrid.model.count_params():,}")

        # 5. Train
        click.echo(f"\n   Training...")
        trainer.train(hybrid, X_train, y_train, epochs=epochs, batch_size=batch_size)

        # 6. Evaluate
        metrics = trainer.evaluate(hybrid, X_test, y_test)
        click.echo(f"\n   Test Results:")
        click.echo(f"   Accuracy:  {metrics['accuracy']:.4f}")
        click.echo(f"   Precision: {metrics['precision']:.4f}")
        click.echo(f"   Recall:    {metrics['recall']:.4f}")
        click.echo(f"   Loss:      {metrics['loss']:.4f}")

        # 7. Save model
        model_dir = trainer.save_model(hybrid, ticker, interval)
        click.echo(f"\n   Model saved to: {model_dir}")
        logger.info(f"LSTM training completed for {ticker}: acc={metrics['accuracy']:.4f}")

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
# COMMAND: SCAN (multi-ticker, multi-strategy)
# ============================================

@cli.command('scan')
@click.option('--strategies', default='macd_vwap,rsi_bb',
              help='Comma-separated strategies to scan')
@click.option('--tickers', default=None,
              help='Comma-separated tickers (default: all configured)')
@click.option('--interval', default='1d', type=click.Choice(['1m', '5m', '15m', '1h', '1d']),
              help='Data interval')
@click.option('--use-ml', is_flag=True, help='Use ML prediction filter')
def scan(strategies, tickers, interval, use_ml):
    """Scan multiple tickers with multiple strategies.

    Now powered by UnifiedPipeline internally.
    """
    try:
        from config.settings import TICKERS
        from signals.pipeline import UnifiedPipeline, TickerConfig

        strategy_list = [s.strip() for s in strategies.split(',')]
        if tickers:
            ticker_list = [t.strip() for t in tickers.split(',')]
        else:
            ticker_list = [t for group in TICKERS.values() for t in group]

        click.echo(f"\n  Scanning {len(ticker_list)} tickers x {len(strategy_list)} strategies...")
        click.echo(f"   Interval: {interval} | ML: {'ON' if use_ml else 'OFF'}")

        # Build TickerConfig list from scan parameters
        ticker_category = {}
        for category, syms in TICKERS.items():
            for sym in syms:
                ticker_category[sym] = category

        configs = [
            TickerConfig(
                ticker=t,
                category=ticker_category.get(t, 'stocks'),
                intervals=[interval],
                strategies=strategy_list,
                use_ml=use_ml,
                use_ensemble=use_ml,  # ensemble only if ML is on
                use_news=False,       # scan is meant to be fast
            )
            for t in ticker_list
        ]

        pipe = UnifiedPipeline(
            use_ml=use_ml,
            use_ensemble=use_ml,
            use_news=False,
            send_telegram=True,
        )

        results = pipe.run_all(configs=configs)

        # Display actionable results
        for result in results:
            if result.is_actionable():
                click.echo(pipe.format_result(result))

        click.echo(pipe.format_summary(results))

        # Send Telegram
        sent = pipe.notify_actionable(results)
        if sent:
            click.echo(f"\n   Telegram: {sent} notification(s) sent")

        # Log signals
        from signals.manager import SignalManager
        manager = SignalManager()
        for result in results:
            if result.is_actionable():
                manager.log_signal(result.technical_signal)

    except Exception as e:
        click.echo(f"\n  Error scanning: {str(e)}", err=True)
        logger.error(f"Error scanning: {e}", exc_info=True)
        sys.exit(1)

# ============================================
# COMMAND: WATCH (continuous monitoring)
# ============================================

@cli.command('watch')
@click.option('--strategies', default='macd_vwap,rsi_bb',
              help='Comma-separated strategies')
@click.option('--tickers', default='SPY,GLD,BTC-USD',
              help='Comma-separated tickers to monitor')
@click.option('--interval', default='15m', type=click.Choice(['1m', '5m', '15m', '1h', '1d']),
              help='Data interval')
@click.option('--every', default=900, type=int,
              help='Seconds between scans (default: 900 = 15 min)')
@click.option('--use-ml', is_flag=True, help='Use ML prediction filter')
def watch(strategies, tickers, interval, every, use_ml):
    """Continuously monitor markets and send alerts. Press Ctrl+C to stop.

    Now powered by UnifiedPipeline internally.
    """
    import time
    from config.settings import MARKET_HOURS, TICKERS as TICKER_GROUPS
    from signals.pipeline import UnifiedPipeline, TickerConfig

    strategy_list = [s.strip() for s in strategies.split(',')]
    ticker_list = [t.strip() for t in tickers.split(',')]

    # Build ticker -> category map for market hours
    ticker_category = {}
    for category, syms in TICKER_GROUPS.items():
        for sym in syms:
            ticker_category[sym] = category

    # Build TickerConfig list
    configs = [
        TickerConfig(
            ticker=t,
            category=ticker_category.get(t, 'stocks'),
            intervals=[interval],
            strategies=strategy_list,
            use_ml=use_ml,
            use_ensemble=use_ml,
            use_news=False,
        )
        for t in ticker_list
    ]

    pipe = UnifiedPipeline(
        use_ml=use_ml,
        use_ensemble=use_ml,
        use_news=False,
        send_telegram=True,
    )

    click.echo(f"\n  Watch mode started")
    click.echo(f"   Tickers: {', '.join(ticker_list)}")
    click.echo(f"   Strategies: {', '.join(strategy_list)}")
    click.echo(f"   Interval: {interval}")
    click.echo(f"   Scan every: {every}s ({every//60} min)")
    click.echo(f"   ML Filter: {'ON' if use_ml else 'OFF'}")
    click.echo(f"   Press Ctrl+C to stop\n")

    scan_count = 0
    try:
        while True:
            scan_count += 1
            now = datetime.now(tz=__import__('datetime').timezone.utc).replace(tzinfo=None)
            click.echo(f"--- Scan #{scan_count} at {now.strftime('%H:%M:%S UTC')} ---")

            # Filter configs by market hours
            open_configs = []
            for config in configs:
                hours = MARKET_HOURS.get(config.category, MARKET_HOURS['stocks'])
                if _is_market_open(now, hours):
                    open_configs.append(config)
                else:
                    click.echo(f"   {config.ticker} ({config.category}): market closed")

            if open_configs:
                results = pipe.run_all(configs=open_configs)

                actionable = [r for r in results if r.is_actionable()]
                for result in actionable:
                    click.echo(pipe.format_result(result))

                # Send Telegram
                pipe.notify_actionable(results)

                # Log signals
                from signals.manager import SignalManager
                manager = SignalManager()
                for result in actionable:
                    manager.log_signal(result.technical_signal)

                if not actionable:
                    click.echo(f"   No actionable signals this scan.")
            else:
                click.echo(f"   All markets closed.")

            click.echo(f"   Next scan in {every}s...\n")
            time.sleep(every)

    except KeyboardInterrupt:
        click.echo(f"\n\n  Watch stopped after {scan_count} scans")


# ============================================
# COMMAND: PIPELINE (unified signal generation)
# ============================================

@cli.command('pipeline')
@click.option('--category', default='all',
              type=click.Choice(['all', 'indices', 'stocks', 'crypto', 'commodities']),
              help='Filter by asset category')
@click.option('--ticker', default=None, help='Run for a specific ticker only')
@click.option('--no-ml', is_flag=True, help='Skip ML predictions')
@click.option('--no-ensemble', is_flag=True, help='Skip ensemble voting')
@click.option('--no-news', is_flag=True, help='Skip news sentiment analysis')
@click.option('--telegram/--no-telegram', default=True, help='Send Telegram notifications')
def pipeline(category, ticker, no_ml, no_ensemble, no_news, telegram):
    """Run unified signal pipeline across all configured tickers.

    Consolidates technical analysis, ML prediction, ensemble voting,
    and news sentiment into a single flow.
    """
    try:
        from signals.pipeline import UnifiedPipeline

        click.echo(f"\n{'='*65}")
        click.echo(f"  UNIFIED SIGNAL PIPELINE")
        click.echo(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo(f"{'='*65}")
        click.echo(f"  Category:  {category}")
        if ticker:
            click.echo(f"  Ticker:    {ticker}")
        click.echo(f"  ML:        {'OFF' if no_ml else 'ON'}")
        click.echo(f"  Ensemble:  {'OFF' if no_ensemble else 'ON'}")
        click.echo(f"  News:      {'OFF' if no_news else 'ON'}")
        click.echo(f"  Telegram:  {'ON' if telegram else 'OFF'}")
        click.echo(f"{'='*65}\n")

        pipe = UnifiedPipeline(
            use_ml=not no_ml,
            use_ensemble=not no_ensemble,
            use_news=not no_news,
            send_telegram=telegram,
        )

        results = pipe.run_all(
            category=category if category != 'all' else None,
            ticker_filter=ticker,
        )

        # Display individual results
        for result in results:
            if result.is_actionable():
                click.echo(pipe.format_result(result))

        # Display summary
        click.echo(pipe.format_summary(results))

        # Send Telegram notifications
        if telegram:
            sent = pipe.notify_actionable(results)
            if sent:
                click.echo(f"\n  Telegram: {sent} notification(s) sent")

        # Log actionable signals
        from signals.manager import SignalManager
        manager = SignalManager()
        for result in results:
            if result.is_actionable():
                manager.log_signal(result.technical_signal)

        logger.info(f"Pipeline completed: {len(results)} results, "
                    f"{sum(1 for r in results if r.is_actionable())} actionable")

    except Exception as e:
        click.echo(f"\n  Error running pipeline: {str(e)}", err=True)
        logger.error(f"Error running pipeline: {e}", exc_info=True)
        sys.exit(1)


def _is_market_open(now: datetime, hours: dict) -> bool:
    """Check if the market is currently open based on UTC time."""
    if now.weekday() not in hours['days']:
        return False

    open_h = hours['open']
    close_h = hours['close']

    # Handle 24h markets (open=0, close=24) or wrap-around (open=23, close=22)
    if close_h >= 24 or open_h > close_h:
        return True  # Near-24h market, always open on valid days

    current_hour = now.hour + now.minute / 60
    return open_h <= current_hour < close_h


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
