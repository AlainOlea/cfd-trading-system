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

        # 6. Evaluate (classification metrics)
        metrics = trainer.evaluate(hybrid, X_test, y_test)
        click.echo(f"\n   Test Results:")
        click.echo(f"   Accuracy:  {metrics['accuracy']:.4f}")
        click.echo(f"   Precision: {metrics['precision']:.4f}")
        click.echo(f"   Recall:    {metrics['recall']:.4f}")
        click.echo(f"   Loss:      {metrics['loss']:.4f}")

        # 6b. OOS financial backtest — the only honest measure of edge
        try:
            oos = trainer.backtest_predictions(hybrid, X_test, ticker=ticker, interval=interval)
            metrics.update(oos)
            click.echo(f"\n   OOS Financial Backtest (with CFD costs):")
            click.echo(f"   Sharpe:        {oos['oos_sharpe']:>8.2f}")
            click.echo(f"   Total Return:  {oos['oos_total_return_pct']:>8.2f}%")
            click.echo(f"   Max Drawdown:  {oos['oos_max_drawdown_pct']:>8.2f}%")
            click.echo(f"   Profit Factor: {oos['oos_profit_factor']:>8.2f}")
            click.echo(f"   Win Rate:      {oos['oos_win_rate_pct']:>8.2f}%")
            click.echo(f"   Trades:        {oos['oos_n_trades']:>8d}")
        except Exception as e:
            click.echo(f"\n   ⚠️  OOS backtest skipped: {e}")
            logger.warning(f"OOS backtest failed for {ticker}: {e}")

        # 7. Save model (promotion gate applied inside save_model)
        model_dir = trainer.save_model(hybrid, ticker, interval, metrics=metrics)
        promoted, reasons = trainer.evaluate_promotion(metrics)
        if promoted:
            click.echo(f"\n   ✅ Model PROMOTED (passes OOS gate)")
        else:
            click.echo(f"\n   ⚠️  Model NOT promoted: {reasons}")
        click.echo(f"\n   Model saved to: {model_dir}")
        logger.info(f"LSTM training completed for {ticker}: acc={metrics['accuracy']:.4f}")

    except Exception as e:
        click.echo(f"\n❌ Error training model: {str(e)}", err=True)
        logger.error(f"Error training model: {e}", exc_info=True)
        sys.exit(1)


@cli.command('train-xgb-cross')
@click.option('--interval', default='1d', type=click.Choice(['1d', '1h']),
              help='Data interval')
@click.option('--tickers', default='SPY,QQQ,IWM,GLD,AAPL,NVDA,MSFT',
              help='Comma-separated tickers to pool for cross-sectional training')
@click.option('--no-triple-barrier', is_flag=True,
              help='Use simple next-bar direction instead of triple barrier labels')
@click.option('--from-csv', is_flag=True,
              help='Load pre-fetched CSV data instead of live fetching (use after fetch-all-history)')
def train_xgb_cross(interval, tickers, no_triple_barrier, from_csv):
    """Train one XGBoost model on ALL tickers pooled together (cross-sectional).

    Per Alzaman (2024) and Byun et al. (2024), cross-sectional training
    outperforms per-asset training by pooling information across assets.
    Uses binary threshold labels (0.5% min move) by default.
    """
    try:
        ticker_list = [t.strip() for t in tickers.split(',')]
        use_triple = not no_triple_barrier

        click.echo(f"\n  CROSS-SECTIONAL XGBOOST TRAINING")
        click.echo(f"  {'=' * 60}")
        click.echo(f"  Interval:          {interval}")
        click.echo(f"  Tickers:           {len(ticker_list)} ({', '.join(ticker_list[:5])}...)")
        click.echo(f"  Labels:            {'triple-barrier' if use_triple else 'binary-threshold'}")
        click.echo(f"  Data source:       {'CSV cache' if from_csv else 'Live Yahoo Finance'}")
        click.echo()

        from data.fetcher import DataFetcher
        from data.processor import DataProcessor
        from indicators.technical import TechnicalIndicators
        from models.xgboost_model import XGBoostTrader

        fetcher = DataFetcher()
        processor = DataProcessor()
        ticker_dfs = {}
        total_samples = 0

        for ticker in ticker_list:
            click.echo(f"  Loading {ticker}...", nl=False)
            try:
                if from_csv:
                    df = fetcher.load_from_csv(ticker, interval)
                else:
                    df = fetcher.fetch_yfinance(ticker, interval, 365)
                    df = processor.clean_data(df)
                df = TechnicalIndicators.add_all_indicators(df)
                ticker_dfs[ticker] = df
                samples = len(df.dropna())
                total_samples += samples
                click.echo(f" {samples} bars")
            except Exception as e:
                click.echo(f" SKIP ({e})")

        if not ticker_dfs:
            click.echo("\n  ❌ No data loaded for any ticker.")
            return

        click.echo(f"\n  Total pooled bars: {total_samples}")
        click.echo(f"  Training cross-sectional model...")

        trader = XGBoostTrader()
        X_train, y_train, X_test, y_test = trader.prepare_cross_sectional(
            ticker_dfs, use_triple_barrier=use_triple
        )

        click.echo(f"  Train: {len(X_train)} samples | Test: {len(X_test)} samples")
        click.echo(f"  Features: {len(trader.feature_names)}")

        trader.train(X_train, y_train)
        metrics = trader.evaluate(X_test, y_test)

        click.echo(f"\n  Test Results:")
        click.echo(f"  Accuracy:  {metrics['accuracy']:.4f}")
        click.echo(f"  Precision: {metrics['precision']:.4f}")
        click.echo(f"  Recall:    {metrics['recall']:.4f}")

        importance = trader.get_feature_importance()
        click.echo(f"\n  Top 5 Features:")
        for _, row in importance.head(5).iterrows():
            click.echo(f"    {row['feature']:<20} {row['percentage']:>6.1f}%")

        model_dir = trader.save('all_tickers', interval)
        click.echo(f"\n  ✅ Cross-sectional model saved to: {model_dir}")
        click.echo(f"  Use with: python3 main.py pipeline  (XGBoost is now default)")

    except Exception as e:
        click.echo(f"\n❌ Error: {str(e)}", err=True)
        logger.error(f"Cross-sectional training error: {e}", exc_info=True)
        sys.exit(1)


@cli.command('fetch-all-history')
@click.option('--years', default=5, type=int, help='Years of daily data to fetch')
@click.option('--tickers', default='SPY,QQQ,IWM,GLD,AAPL,NVDA,MSFT',
              help='Comma-separated tickers')
def fetch_all_history(years, tickers):
    """Fetch extended historical data for training (bypasses yfinance limits).

    Fetches daily data up to 10 years back and hourly data up to 2 years.
    Saves clean CSVs to data/raw/ for use in training.
    """
    from data.fetcher import DataFetcher
    from data.processor import DataProcessor

    ticker_list = [t.strip() for t in tickers.split(',')]
    fetcher = DataFetcher()
    processor = DataProcessor()

    click.echo(f"\n📥 FETCHING EXTENDED HISTORY ({years}y daily, 2y hourly)")
    click.echo(f"   Tickers: {len(ticker_list)}")
    click.echo()

    for ticker in ticker_list:
        click.echo(f"  {ticker}:", nl=False)

        try:
            # Daily: unlimited history
            df_d = fetcher.fetch_bulk(ticker, '1d', total_days=years * 365)
            df_d = processor.clean_data(df_d)
            processor.validate_data(df_d)
            fetcher.save_to_csv(df_d, ticker, '1d')
            click.echo(f" {len(df_d)}d", nl=False)
        except Exception as e:
            click.echo(f" daily:SKIP({e})", nl=False)

        try:
            # Hourly: up to 2 years
            df_h = fetcher.fetch_bulk(ticker, '1h', total_days=700, chunk_days=350)
            df_h = processor.clean_data(df_h)
            processor.validate_data(df_h)
            fetcher.save_to_csv(df_h, ticker, '1h')
            click.echo(f" {len(df_h)}h")
        except Exception as e:
            click.echo(f" hourly:SKIP({e})")

    click.echo(f"\n✅ History fetched. Ready for training:")
    click.echo(f"   python3 main.py train-xgb-cross --interval 1d")
    click.echo(f"   python3 main.py train-xgb-cross --interval 1h")

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


@cli.command('paper-trade')
@click.option('--category', default=None, help='Filter by category (indices, commodities, stocks, crypto)')
@click.option('--ticker', default=None, help='Single ticker (e.g. SPY, GLD)')
@click.option('--interval', default='all',
              type=click.Choice(['1d', '1h', 'all']),
              help='Timeframe to trade: 1d (swing), 1h (intraday), all (both, default)')
@click.option('--no-ml', is_flag=True, help='Disable ML predictions')
@click.option('--no-ensemble', is_flag=True, help='Disable ensemble voting')
@click.option('--no-news', is_flag=True, help='Disable news sentiment')
@click.option('--no-telegram', is_flag=True, help='Disable Telegram notifications')
@click.option('--min-confluence', default=2, type=int, help='Min confluence stars to trade (1-5)')
@click.option('--min-confidence', default=60.0, type=float, help='Min confidence % to trade')
@click.option('--close-all', is_flag=True, help='Close all open paper positions first')
@click.option('--dry-run', is_flag=True, help='Show what would be traded without executing')
def paper_trade(category, ticker, interval, no_ml, no_ensemble, no_news, no_telegram,
                min_confluence, min_confidence, close_all, dry_run):
    """Run pipeline and auto-execute signals in Alpaca paper trading sandbox.

    Connects to Alpaca Markets paper account ($100k virtual capital).
    For each actionable BUY/SELL signal, places a bracket order (entry + SL + TP)
    automatically. Skips tickers you already hold.

    Use --interval to run only one timeframe (recommended for cron jobs):
      --interval 1d  : swing trades (GTC orders, 2-3% SL, 4-6% TP)
      --interval 1h  : intraday trades (DAY orders, 0.5% SL, 1% TP)

    Requires ALPACA_API_KEY and ALPACA_SECRET_KEY in .env
    """
    from signals.pipeline import UnifiedPipeline
    from signals.alpaca_broker import AlpacaBroker, TradeResult
    from signals.manager import SignalManager
    import time

    use_ml = not no_ml
    use_ensemble = not no_ensemble
    use_news = not no_news
    send_telegram = not no_telegram
    manager = SignalManager()

    click.echo(f"\n  PAPER TRADING MODE")
    click.echo(f"  {'=' * 50}")
    click.echo(f"  Interval:        {interval} {'(swing)' if interval == '1d' else '(intraday)' if interval == '1h' else '(mixed - not recommended for cron)'}")
    click.echo(f"  Min confluence:  {min_confluence}/5 stars")
    click.echo(f"  Min confidence:  {min_confidence:.0f}%")
    click.echo(f"  Dry run:         {'YES (no orders placed)' if dry_run else 'No (live paper trades)'}")
    click.echo()

    broker = AlpacaBroker()
    if not broker.is_configured:
        click.echo("  ALPACA_API_KEY not set in .env. Skipping paper trading.", err=True)
        return

    acct = broker.get_account_summary()
    if acct:
        click.echo(f"  Account: ${acct.get('cash', 0):,.0f} cash | "
                   f"${acct.get('equity', 0):,.0f} equity | "
                   f"{acct.get('status', 'unknown')}")

    existing = broker.get_open_positions()
    if existing:
        click.echo(f"\n  Existing positions ({len(existing)}):")
        for sym, pos in existing.items():
            click.echo(f"    {sym}: {pos['qty']:.4f} sh | "
                       f"entry ${pos['avg_entry']:.2f} | "
                       f"P&L ${pos['unrealized_pl']:.2f} ({pos['unrealized_pl_pct']:.2f}%)")

    if close_all and existing and not dry_run:
        click.echo(f"\n  Closing {len(existing)} existing positions...")
        results = broker.close_all()
        for r in results:
            status = "+" if r.placed else "x"
            click.echo(f"    [{status}] {r.symbol}: {r.reason}")

    click.echo(f"\n  Running signal pipeline...")
    click.echo(f"  {'─' * 50}")

    # Run pipeline
    pipeline = UnifiedPipeline(
        use_ml=use_ml, use_ensemble=use_ensemble,
        use_news=use_news, send_telegram=send_telegram
    )
    results = pipeline.run_all(
        category=category,
        ticker_filter=ticker,
        interval_filter=interval if interval != 'all' else None,
    )
    actionable = [r for r in results if r.is_actionable()]

    # Send Telegram only for quality signals (3+ stars, before trade filter)
    if send_telegram:
        quality = [r for r in actionable if r.confluence_score >= min_confluence]
        if quality:
            sent_count = pipeline.notify_actionable(quality)
            if sent_count > 0:
                click.echo(f"  Telegram: {sent_count} notification(s) sent")
        else:
            click.echo(f"  Telegram: no signals with {min_confluence}+ stars")

    click.echo(f"\n  Generated {len(results)} signals, {len(actionable)} actionable")
    click.echo()

    if not actionable:
        click.echo("  No actionable signals. Nothing to trade.")
        return

    trades: list[TradeResult] = []
    skipped = 0
    dry_count = 0
    for r in actionable:
        # Apply quality filters
        if r.confluence_score < min_confluence:
            skipped += 1
            continue
        if r.final_confidence * 100 < min_confidence:
            skipped += 1
            continue

        # Signal cooldown: skip if same ticker+direction traded recently
        cooldown_hours = 4 if r.interval == '1h' else 24
        recent_signals = manager.get_history(ticker=r.ticker, n=10)
        if recent_signals is not None and not recent_signals.empty:
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(hours=cooldown_hours)
            recent_signals['ts'] = pd.to_datetime(recent_signals['timestamp'], errors='coerce')
            recent_same = recent_signals[
                (recent_signals['direction'] == r.technical_signal.direction) &
                (recent_signals['ts'] > cutoff)
            ]
            if not recent_same.empty:
                skipped += 1
                click.echo(
                    f"  [SKIP] {r.ticker} {r.technical_signal.direction} — "
                    f"cooldown ({cooldown_hours}h since last signal)"
                )
                continue

        if dry_run:
            dry_count += 1
            shares = broker.calculate_shares(
                r.technical_signal.entry_price,
                r.technical_signal.stop_loss
            )
            click.echo(
                f"  [DRY] {r.technical_signal.direction} {r.ticker} | "
                f"entry=${r.technical_signal.entry_price:.2f} | "
                f"SL=${r.technical_signal.stop_loss:.2f} | "
                f"TP=${r.technical_signal.take_profit:.2f} | "
                f"conf={r.final_confidence:.0%} | "
                f"stars={r.confluence_score}/5 | "
                f"shares={shares:.2f}"
            )
        else:
            result = broker.place_signal(r.technical_signal, interval=r.interval)
            trades.append(result)
            status = "+" if result.placed else "x"
            click.echo(
                f"  [{status}] {r.technical_signal.direction} {result.symbol} | "
                f"{result.qty:.2f} sh @ ~${result.entry_price:.2f} | "
                f"SL=${result.stop_loss:.2f} TP=${result.take_profit:.2f} | "
                f"conf={result.confidence:.0%} | "
                f"{'OK' if result.placed else result.reason}"
            )
            manager.log_signal(r.technical_signal)

    placed = sum(1 for t in trades if t.placed)
    failed = sum(1 for t in trades if not t.placed)
    bid = 'DRY RUN' if dry_run else 'PAPER'
    if dry_run:
        click.echo(f"\n  DRY RUN: {dry_count} signals would be traded, {skipped} skipped (quality filter)")
    else:
        click.echo(f"\n  {bid} TRADING COMPLETE: {placed} placed, {failed} failed, {skipped} skipped (quality filter)")

    if placed > 0 and not dry_run:
        click.echo(f"\n  View your trades: https://app.alpaca.markets/paper/dashboard/overview")


@cli.command('paper-status')
def paper_status():
    """Check Alpaca paper trading account status and open positions."""
    from signals.alpaca_broker import AlpacaBroker

    broker = AlpacaBroker()
    if not broker.is_configured:
        click.echo("ALPACA_API_KEY not set in .env")
        return

    click.echo("\n  ALPACA PAPER TRADING ACCOUNT")
    click.echo(f"  {'=' * 50}")

    acct = broker.get_account_summary()
    if not acct:
        click.echo("  Failed to connect to Alpaca")
        return

    pnl = acct['equity'] - 100000
    pnl_pct = (pnl / 100000) * 100
    click.echo(f"  Cash:         ${acct['cash']:>12,.2f}")
    click.echo(f"  Equity:       ${acct['equity']:>12,.2f}")
    click.echo(f"  Buying power: ${acct['buying_power']:>12,.2f}")
    click.echo(f"  P&L:          ${pnl:>+12,.2f} ({pnl_pct:+.2f}%)")
    click.echo(f"  Status:       {acct['status']}")

    positions = broker.get_open_positions()
    click.echo(f"\n  Open Positions: {len(positions)}")
    if positions:
        click.echo(f"  {'Symbol':<8} {'Qty':>8} {'Entry':>10} {'Current':>10} {'P&L':>10} {'P&L%':>8}")
        click.echo(f"  {'─'*8} {'─'*8} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")
        for sym, pos in positions.items():
            click.echo(f"  {sym:<8} {pos['qty']:>8.4f} "
                       f"${pos['avg_entry']:>9.2f} ${pos['current_price']:>9.2f} "
                       f"${pos['unrealized_pl']:>+9.2f} {pos['unrealized_pl_pct']:>+7.2f}%")
    else:
        click.echo("  No open positions.")

    # Show pending orders
    try:
        from dotenv import load_dotenv; load_dotenv()
        import os
        from alpaca.trading.client import TradingClient
        client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
        orders = client.get_orders()
        if orders:
            click.echo(f"\n  Pending Orders: {len(orders)}")
            click.echo(f"  {'Symbol':<8} {'Side':<6} {'Qty':>8} {'Type':>8} {'Status':>12}")
            click.echo(f"  {'─'*8} {'─'*6} {'─'*8} {'─'*8} {'─'*12}")
            for o in orders:
                click.echo(f"  {o.symbol:<8} {str(o.side):<6} {o.qty:>8} {str(o.type):>8} {str(o.status):>12}")
    except Exception:
        pass


@cli.command('paper-close')
@click.argument('symbol', required=False)
def paper_close(symbol):
    """Close a paper position. Close all if no symbol specified."""
    from signals.alpaca_broker import AlpacaBroker

    broker = AlpacaBroker()
    if not broker.is_configured:
        click.echo("ALPACA_API_KEY not set in .env")
        return

    if symbol:
        result = broker.close_position(symbol)
        status = "+" if result.placed else "x"
        click.echo(f"[{status}] {result.symbol}: {result.reason}")
    else:
        click.echo("Closing ALL paper positions...")
        results = broker.close_all()
        for r in results:
            status = "+" if r.placed else "x"
            click.echo(f"[{status}] {r.symbol}: {r.reason}")


@cli.command('paper-history')
@click.option('--days', default=30, type=int, help='Days of history to show')
@click.option('--csv', 'csv_path', type=click.Path(), default=None,
              help='Export trades to CSV file (e.g. results/paper_trades.csv)')
@click.option('--all', 'show_all', is_flag=True,
              help='Show all trades, not just the last 20')
def paper_history(days, csv_path, show_all):
    """Show paper trading performance: trades, win rate, P&L."""
    import csv
    from signals.alpaca_broker import AlpacaBroker

    broker = AlpacaBroker()
    if not broker.is_configured:
        click.echo("ALPACA_API_KEY not set in .env")
        return

    perf = broker.get_performance(days)
    trades = broker.get_trade_history(days)

    if csv_path:
        if not trades:
            click.echo(f"  No trades to export.")
            return
        fieldnames = ['symbol', 'side', 'qty', 'entry', 'exit', 'pnl',
                      'pnl_pct', 'exit_type', 'duration_min', 'entry_at', 'exit_at']
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(trades)
        click.echo(f"  Exported {len(trades)} trades -> {csv_path}")
        return

    click.echo(f"\n  PAPER TRADING PERFORMANCE (last {days} days)")
    click.echo(f"  {'=' * 50}")

    if not trades:
        click.echo(f"\n  No closed trades yet. Paper trading is just getting started.")
        click.echo(f"  Trades will appear here once your bracket orders execute.\n")
        return

    pnl_sign = "+" if perf['total_pnl'] >= 0 else ""
    click.echo(f"  Total trades:    {perf['trades']}")
    click.echo(f"  Wins:            {perf['wins']}")
    click.echo(f"  Losses:          {perf['losses']}")
    click.echo(f"  Win rate:        {perf['win_rate']}%")
    click.echo(f"  Total P&L:       {pnl_sign}${perf['total_pnl']:,.2f}")
    click.echo(f"  Avg win:         ${perf['avg_win']:,.2f}")
    click.echo(f"  Avg loss:        ${perf['avg_loss']:,.2f}")
    click.echo(f"  Best trade:      ${perf['best']:,.2f}")
    click.echo(f"  Worst trade:     ${perf['worst']:,.2f}")
    if perf['profit_factor'] > 0:
        click.echo(f"  Profit factor:   {perf['profit_factor']:.2f}")

    tp_count = sum(1 for t in trades if t['exit_type'] == 'TP')
    sl_count = sum(1 for t in trades if t['exit_type'] == 'SL')
    click.echo(f"  Exits:           {tp_count} TP / {sl_count} SL")

    display = trades if show_all else trades[-20:]
    click.echo(f"\n  Closed trades{' (all)' if show_all else ' (last 20)'}:")
    click.echo(f"  {'Symbol':<8} {'Side':<5} {'Qty':>7} {'Entry':>10} {'Exit':>10} "
               f"{'P&L':>10} {'P&L%':>8} {'Exit':>5} {'Min':>6}")
    click.echo(f"  {'─'*8} {'─'*5} {'─'*7} {'─'*10} {'─'*10} {'─'*10} {'─'*8} {'─'*5} {'─'*6}")
    for t in display:
        pnl_s = f"${t['pnl']:+,.2f}"
        click.echo(f"  {t['symbol']:<8} {t['side']:<5} {t['qty']:>7.2f} "
                   f"${t['entry']:>9.2f} ${t['exit']:>9.2f} "
                   f"{pnl_s:>10} {t['pnl_pct']:>+7.2f}% "
                   f"{t['exit_type']:>5} {t['duration_min']:>6.1f}")


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
