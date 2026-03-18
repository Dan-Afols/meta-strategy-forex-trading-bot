"""
Feature engineering for ML models.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from utils.indicators import (
    sma, ema, rsi, macd, bollinger_bands, atr, adx, stochastic, volatility_ratio,
)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build ML feature matrix from OHLCV data.
    Returns DataFrame with feature columns + 'target' column.
    """
    feat = pd.DataFrame(index=df.index)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]

    # Returns
    feat["return_1"] = close.pct_change(1)
    feat["return_3"] = close.pct_change(3)
    feat["return_5"] = close.pct_change(5)
    feat["return_10"] = close.pct_change(10)

    # Moving averages relative to price
    for period in [5, 10, 20, 50]:
        ma = sma(close, period)
        feat[f"sma_{period}_ratio"] = close / ma - 1

    for period in [5, 10, 20, 50]:
        ma = ema(close, period)
        feat[f"ema_{period}_ratio"] = close / ma - 1

    # RSI
    feat["rsi_14"] = rsi(close, 14)
    feat["rsi_7"] = rsi(close, 7)

    # MACD
    macd_line, macd_signal, macd_hist = macd(close)
    feat["macd_line"] = macd_line
    feat["macd_signal"] = macd_signal
    feat["macd_hist"] = macd_hist

    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = bollinger_bands(close, 20, 2.0)
    feat["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)
    feat["bb_width"] = (bb_upper - bb_lower) / bb_middle

    # ATR
    atr_val = atr(high, low, close, 14)
    feat["atr_14"] = atr_val / close  # Normalized ATR

    # ADX
    feat["adx_14"] = adx(high, low, close, 14)

    # Stochastic
    k, d = stochastic(high, low, close)
    feat["stoch_k"] = k
    feat["stoch_d"] = d

    # Volatility ratio
    feat["vol_ratio"] = volatility_ratio(close, 10, 30)

    # Candle patterns
    body = close - open_
    range_ = high - low
    feat["body_ratio"] = body / range_.replace(0, np.nan)
    feat["upper_shadow"] = (high - pd.concat([close, open_], axis=1).max(axis=1)) / range_.replace(0, np.nan)
    feat["lower_shadow"] = (pd.concat([close, open_], axis=1).min(axis=1) - low) / range_.replace(0, np.nan)

    # Volume features (if available)
    if "volume" in df.columns:
        vol = df["volume"]
        feat["volume_sma_ratio"] = vol / sma(vol, 20).replace(0, np.nan)
        feat["volume_change"] = vol.pct_change()

    # Rolling statistics
    feat["rolling_std_20"] = close.pct_change().rolling(20).std()
    feat["rolling_skew_20"] = close.pct_change().rolling(20).skew()
    feat["rolling_kurt_20"] = close.pct_change().rolling(20).kurt()

    # Target: 1 if price goes up in next candle, 0 otherwise
    # Note: last row target uses shift(-1) which is NaN → dropped by dropna()
    feat["target"] = (close.shift(-1) > close).astype(float)
    feat.loc[feat.index[-1], "target"] = np.nan  # Explicitly mark last row invalid

    return feat.dropna()


def get_feature_columns(feat_df: pd.DataFrame) -> list:
    """Return list of feature column names (excluding target)."""
    return [c for c in feat_df.columns if c != "target"]
