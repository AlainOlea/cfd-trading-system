#!/usr/bin/env python3
"""
Phase 1: Fetch Historical Data (2-3 Years)
===========================================
Fetches extended historical data for ML model training.
"""

import logging
from datetime import datetime
import click

from data.fetcher import DataFetcher
from data.processor import DataProcessor
from config.settings import DEFAULT_TICKERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_bulk_data(
    tickers: list = None,
    intervals: list = None,
    days_map: dict = None,
    dry_run: bool = False
):
    """
    Fetch bulk historical data for multiple tickers and intervals.

    Args:
        tickers: List of ticker symbols (default: DEFAULT_TICKERS)
        intervals: List of intervals to fetch (default: ['1d', '1h'])
        days_map: Dict mapping interval -> days (default: 3y daily, 2y hourly)
        dry_run: If True, only print what would be fetched (no actual fetch)
    """
    if tickers is None:
        tickers = DEFAULT_TICKERS

    if intervals is None:
        intervals = ['1d', '1h']

    if days_map is None:
        days_map = {
            '1d': 1095,  # 3 years of trading days (~750 rows)
            '1h': 730,   # 2 years of hourly candles (~17,500 rows)
            '1m': 60,    # 60 days (yfinance max for minute data)
        }

    fetcher = DataFetcher()
    processor = DataProcessor()

    print("\n" + "="*70)
    print("📊 HISTORICAL DATA BULK FETCH")
    print("="*70)
    print(f"Tickers: {tickers}")
    print(f"Intervals: {intervals}")
    print(f"Days mapping: {days_map}")
    print(f"Dry run: {dry_run}")
    print("="*70 + "\n")

    total_rows_fetched = 0
    total_rows_processed = 0
    errors = []

    for ticker in tickers:
        print(f"\n🎯 Processing ticker: {ticker}")
        print("-" * 70)

        for interval in intervals:
            if interval not in days_map:
                logger.warning(f"Skipping {interval} (not in days_map)")
                continue

            days = days_map[interval]
            print(f"\n  ⏱️  {interval} ({days} days)...", end=" ")

            try:
                if dry_run:
                    print("(DRY RUN - skipped)")
                    continue

                # Fetch raw data
                df = fetcher.fetch_yfinance(ticker, interval, days=days)
                total_rows_fetched += len(df)
                print(f"✅ {len(df)} rows fetched")

                # Save raw data
                fetcher.save_to_csv(df, ticker, interval)
                print(f"     💾 Saved to data/raw/{ticker}_{interval}.csv")

                # Clean and validate
                df_clean = processor.clean_data(df)
                processor.validate_data(df_clean)
                processor.save_processed(df_clean, ticker, interval)
                total_rows_processed += len(df_clean)
                print(f"     ✨ Cleaned: {len(df_clean)} rows → data/processed/")

                # Print date range
                print(f"     📅 Date range: {df_clean.index[0].date()} to {df_clean.index[-1].date()}")

            except Exception as e:
                error_msg = f"{ticker} {interval}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                print(f"❌ ERROR: {str(e)}")

    # Summary
    print("\n" + "="*70)
    print("📈 SUMMARY")
    print("="*70)
    print(f"✅ Total rows fetched: {total_rows_fetched:,}")
    print(f"✨ Total rows processed: {total_rows_processed:,}")

    if errors:
        print(f"\n⚠️  Errors ({len(errors)}):")
        for error in errors:
            print(f"   - {error}")
    else:
        print("\n✅ All data fetched successfully!")

    print("="*70 + "\n")

    return {
        'total_fetched': total_rows_fetched,
        'total_processed': total_rows_processed,
        'errors': errors,
        'success': len(errors) == 0
    }


@click.command()
@click.option('--tickers', default=None, help='Comma-separated tickers (default: DEFAULT_TICKERS)')
@click.option('--intervals', default='1d,1h', help='Comma-separated intervals (default: 1d,1h)')
@click.option('--days-1d', type=int, default=1095, help='Days for 1d data (default: 1095 = 3 years)')
@click.option('--days-1h', type=int, default=730, help='Days for 1h data (default: 730 = 2 years)')
@click.option('--days-1m', type=int, default=60, help='Days for 1m data (default: 60 = yfinance max)')
@click.option('--dry-run', is_flag=True, help='Print what would be fetched (no actual fetch)')
def main(tickers, intervals, days_1d, days_1h, days_1m, dry_run):
    """
    Fetch 2-3 years of historical data for ML model training.

    Expected output:
    - 1d data: ~750 rows (3 years of trading days)
    - 1h data: ~17,500 rows (2 years of hourly candles)
    """
    # Parse tickers
    if tickers:
        ticker_list = [t.strip() for t in tickers.split(',')]
    else:
        ticker_list = DEFAULT_TICKERS

    # Parse intervals
    interval_list = [i.strip() for i in intervals.split(',')]

    # Build days map
    days_map = {
        '1d': days_1d,
        '1h': days_1h,
        '1m': days_1m,
    }

    # Fetch bulk data
    result = fetch_bulk_data(
        tickers=ticker_list,
        intervals=interval_list,
        days_map=days_map,
        dry_run=dry_run
    )

    # Exit with appropriate code
    exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
