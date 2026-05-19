"""
Technical Indicators Module
============================
Calculates technical indicators on OHLCV DataFrames using pandas-ta.
"""

import logging

import pandas as pd
import pandas_ta as ta

from config.settings import (
    ADX_PARAMS,
    BB_PARAMS,
    MA_PARAMS,
    MACD_PARAMS,
    RSI_PARAMS,
    STOCHASTIC_PARAMS,
)

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Adds technical indicators to OHLCV DataFrames."""

    @classmethod
    def add_all_indicators(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Add all configured technical indicators to a DataFrame.

        Args:
            df: OHLCV DataFrame with columns [open, high, low, close, volume].

        Returns:
            DataFrame with all indicator columns appended.
        """
        df = df.copy()

        df = cls.add_macd(df)
        df = cls.add_rsi(df)
        df = cls.add_bollinger_bands(df)
        df = cls.add_sma(df, period=MA_PARAMS['fast'])
        df = cls.add_sma(df, period=MA_PARAMS['slow'])
        df = cls.add_ema(df, period=MA_PARAMS['fast'])
        df = cls.add_ema(df, period=MA_PARAMS['slow'])
        df = cls.add_vwap(df)
        df = cls.add_stochastic(df)
        df = cls.add_adx(df)
        df = cls.add_atr(df)
        df = cls.add_obv(df)

        logger.info(f"Added {len(df.columns) - 5} indicator columns to DataFrame")
        return df

    @staticmethod
    def add_macd(
        df: pd.DataFrame,
        fast: int | None = None,
        slow: int | None = None,
        signal: int | None = None,
    ) -> pd.DataFrame:
        """Add MACD, signal line, and histogram.

        Columns added: macd, macd_signal, macd_histogram
        """
        fast = fast or MACD_PARAMS['fast']
        slow = slow or MACD_PARAMS['slow']
        signal = signal or MACD_PARAMS['signal']

        macd = ta.macd(df['close'], fast=fast, slow=slow, signal=signal)
        if macd is not None and not macd.empty:
            df['macd'] = macd.iloc[:, 0]
            df['macd_signal'] = macd.iloc[:, 2]
            df['macd_histogram'] = macd.iloc[:, 1]
        return df

    @staticmethod
    def add_rsi(
        df: pd.DataFrame,
        period: int | None = None,
    ) -> pd.DataFrame:
        """Add Relative Strength Index.

        Columns added: rsi
        """
        period = period or RSI_PARAMS['period']
        rsi = ta.rsi(df['close'], length=period)
        if rsi is not None:
            df['rsi'] = rsi
        return df

    @staticmethod
    def add_bollinger_bands(
        df: pd.DataFrame,
        period: int | None = None,
        std_dev: float | None = None,
    ) -> pd.DataFrame:
        """Add Bollinger Bands (upper, middle, lower).

        Columns added: bb_upper, bb_middle, bb_lower, bb_bandwidth, bb_percent
        """
        period = period or BB_PARAMS['period']
        std_dev = std_dev or BB_PARAMS['std_dev']

        bb = ta.bbands(df['close'], length=period, std=std_dev)
        if bb is not None and not bb.empty:
            df['bb_lower'] = bb.iloc[:, 0]
            df['bb_middle'] = bb.iloc[:, 1]
            df['bb_upper'] = bb.iloc[:, 2]
            df['bb_bandwidth'] = bb.iloc[:, 3]
            df['bb_percent'] = bb.iloc[:, 4]
        return df

    @staticmethod
    def add_sma(df: pd.DataFrame, period: int = 50) -> pd.DataFrame:
        """Add Simple Moving Average.

        Columns added: sma_{period}
        """
        sma = ta.sma(df['close'], length=period)
        if sma is not None:
            df[f'sma_{period}'] = sma
        return df

    @staticmethod
    def add_ema(df: pd.DataFrame, period: int = 50) -> pd.DataFrame:
        """Add Exponential Moving Average.

        Columns added: ema_{period}
        """
        ema = ta.ema(df['close'], length=period)
        if ema is not None:
            df[f'ema_{period}'] = ema
        return df

    @staticmethod
    def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
        """Add Volume Weighted Average Price.

        Note: VWAP requires intraday data with a proper datetime index.
        For daily data, falls back to a typical price * volume approximation.

        Columns added: vwap
        """
        vwap = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
        if vwap is not None:
            df['vwap'] = vwap
        else:
            # Fallback for daily data: use typical price (H+L+C)/3 as a proxy.
            # True VWAP resets each session and requires intraday tick data;
            # accumulating over multi-day history produces a meaningless number.
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            df['vwap'] = typical_price
            logger.debug("VWAP: using typical-price fallback (daily data — true VWAP requires intraday)")
        return df

    @staticmethod
    def add_stochastic(
        df: pd.DataFrame,
        period: int | None = None,
        smooth_k: int | None = None,
        smooth_d: int | None = None,
    ) -> pd.DataFrame:
        """Add Stochastic Oscillator (%K and %D).

        Columns added: stoch_k, stoch_d
        """
        period = period or STOCHASTIC_PARAMS['period']
        smooth_k = smooth_k or STOCHASTIC_PARAMS['smooth_k']
        smooth_d = smooth_d or STOCHASTIC_PARAMS['smooth_d']

        stoch = ta.stoch(
            df['high'], df['low'], df['close'],
            k=period, d=smooth_d, smooth_k=smooth_k,
        )
        if stoch is not None and not stoch.empty:
            df['stoch_k'] = stoch.iloc[:, 0]
            df['stoch_d'] = stoch.iloc[:, 1]
        return df

    @staticmethod
    def add_adx(
        df: pd.DataFrame,
        period: int | None = None,
    ) -> pd.DataFrame:
        """Add Average Directional Index with +DI and -DI.

        Columns added: adx, plus_di, minus_di
        """
        period = period or ADX_PARAMS['period']

        adx = ta.adx(df['high'], df['low'], df['close'], length=period)
        if adx is not None and not adx.empty:
            df['adx'] = adx.iloc[:, 0]
            df['plus_di'] = adx.iloc[:, 1]
            df['minus_di'] = adx.iloc[:, 2]
        return df

    @staticmethod
    def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Add Average True Range.

        Columns added: atr
        """
        atr = ta.atr(df['high'], df['low'], df['close'], length=period)
        if atr is not None:
            df['atr'] = atr
        return df

    @staticmethod
    def add_obv(df: pd.DataFrame) -> pd.DataFrame:
        """Add On Balance Volume.

        Columns added: obv
        """
        obv = ta.obv(df['close'], df['volume'])
        if obv is not None:
            df['obv'] = obv
        return df
