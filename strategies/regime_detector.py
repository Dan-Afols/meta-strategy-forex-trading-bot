"""
Market Regime Detector — identifies current market conditions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config.constants import MarketRegime
from utils.indicators import adx, atr, sma, ema, rsi, bollinger_bands
from utils.math_helpers import hurst_exponent
from utils.logging_config import get_logger

logger = get_logger("regime_detector")


class RegimeDetector:
    """Detects the current market regime from OHLCV data."""

    def __init__(self, adx_period: int = 14, atr_period: int = 14,
                 vol_lookback: int = 30, trend_ma_fast: int = 20,
                 trend_ma_slow: int = 50):
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.vol_lookback = vol_lookback
        self.trend_ma_fast = trend_ma_fast
        self.trend_ma_slow = trend_ma_slow

    def detect(self, df: pd.DataFrame) -> MarketRegime:
        """
        Determine market regime from price data.
        Uses ADX for trend strength, moving averages for direction,
        ATR for volatility, and Hurst exponent for mean-reversion tendency.
        """
        if len(df) < self.trend_ma_slow + 10:
            return MarketRegime.SIDEWAYS

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Trend direction
        fast_ma = ema(close, self.trend_ma_fast)
        slow_ma = ema(close, self.trend_ma_slow)
        ma_diff = (fast_ma.iloc[-1] - slow_ma.iloc[-1]) / slow_ma.iloc[-1]

        # Trend strength (ADX)
        adx_val = adx(high, low, close, self.adx_period)
        current_adx = adx_val.iloc[-1] if not np.isnan(adx_val.iloc[-1]) else 0

        # Volatility analysis
        atr_val = atr(high, low, close, self.atr_period)
        current_atr = atr_val.iloc[-1]
        avg_atr = atr_val.tail(self.vol_lookback).mean()
        vol_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

        # Hurst exponent for trending vs mean-reverting
        try:
            h = hurst_exponent(close.tail(100))
        except Exception:
            h = 0.5

        # Decision logic
        if vol_ratio > 1.8:
            return MarketRegime.HIGH_VOLATILITY
        if vol_ratio < 0.5:
            return MarketRegime.LOW_VOLATILITY

        if current_adx > 30:
            if ma_diff > 0.001:
                return MarketRegime.STRONG_BULLISH
            elif ma_diff < -0.001:
                return MarketRegime.STRONG_BEARISH

        if current_adx > 20:
            if ma_diff > 0:
                return MarketRegime.BULLISH
            else:
                return MarketRegime.BEARISH

        return MarketRegime.SIDEWAYS

    def get_regime_details(self, df: pd.DataFrame) -> dict:
        """Return detailed regime analysis."""
        regime = self.detect(df)
        close = df["close"]
        high = df["high"]
        low = df["low"]

        adx_val = adx(high, low, close, self.adx_period)
        atr_val = atr(high, low, close, self.atr_period)
        avg_atr = atr_val.tail(self.vol_lookback).mean()
        fast_ma = ema(close, self.trend_ma_fast)
        slow_ma = ema(close, self.trend_ma_slow)

        try:
            h = hurst_exponent(close.tail(100))
        except Exception:
            h = 0.5

        return {
            "regime": regime.value,
            "adx": round(float(adx_val.iloc[-1]), 2) if not np.isnan(adx_val.iloc[-1]) else 0,
            "atr": round(float(atr_val.iloc[-1]), 6),
            "avg_atr": round(float(avg_atr), 6),
            "volatility_ratio": round(float(atr_val.iloc[-1] / avg_atr), 3) if avg_atr > 0 else 1.0,
            "fast_ma": round(float(fast_ma.iloc[-1]), 5),
            "slow_ma": round(float(slow_ma.iloc[-1]), 5),
            "hurst_exponent": round(h, 3),
            "is_trending": h > 0.55,
            "is_mean_reverting": h < 0.45,
        }
