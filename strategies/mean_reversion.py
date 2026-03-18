"""
Mean-Reversion Strategy — uses RSI, Bollinger Bands, and z-scores.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config.constants import SignalType, StrategyType, DEFAULT_STRATEGY_PARAMS, PIP_SIZE
from strategies.base import BaseStrategy, Signal
from utils.indicators import rsi, bollinger_bands, atr
from utils.math_helpers import signal_confidence, rolling_zscore


class MeanReversionStrategy(BaseStrategy):
    name = "MeanReversion"
    strategy_type = StrategyType.MEAN_REVERSION

    def __init__(self, params: dict | None = None):
        defaults = DEFAULT_STRATEGY_PARAMS["MEAN_REVERSION"]
        merged = {**defaults, **(params or {})}
        super().__init__(merged)

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        if not self.validate_data(df, min_rows=40):
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # RSI
        rsi_val = rsi(close, self.params["rsi_period"])

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = bollinger_bands(
            close, self.params["bb_period"], self.params["bb_std"]
        )

        # Z-score
        zscore = rolling_zscore(close, self.params["bb_period"])

        # ATR for SL/TP
        atr_val = atr(high, low, close, 14)

        curr_rsi = rsi_val.iloc[-1]
        curr_price = close.iloc[-1]
        curr_bb_upper = bb_upper.iloc[-1]
        curr_bb_lower = bb_lower.iloc[-1]
        curr_bb_middle = bb_middle.iloc[-1]
        curr_zscore = zscore.iloc[-1]
        curr_atr = atr_val.iloc[-1]

        if np.isnan(curr_rsi) or np.isnan(curr_bb_upper):
            return None

        pip = PIP_SIZE.get(symbol, 0.0001)

        # ── BUY signal: oversold ────────────────────────────────────
        if (curr_rsi < self.params["rsi_oversold"] and
                curr_price <= curr_bb_lower and curr_zscore < -1.5):

            indicators = {
                "rsi_oversold": (self.params["rsi_oversold"] - curr_rsi) / self.params["rsi_oversold"],
                "bb_below_lower": min(abs(curr_price - curr_bb_lower) / (curr_atr or 1), 1.0),
                "zscore": min(abs(curr_zscore) / 3.0, 1.0),
            }
            conf = signal_confidence(indicators)

            sl = curr_price - 1.5 * curr_atr
            tp = curr_bb_middle  # Target the mean

            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=curr_price,
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                timeframe=timeframe,
                indicators=indicators,
            )

        # ── SELL signal: overbought ─────────────────────────────────
        if (curr_rsi > self.params["rsi_overbought"] and
                curr_price >= curr_bb_upper and curr_zscore > 1.5):

            indicators = {
                "rsi_overbought": (curr_rsi - self.params["rsi_overbought"]) / (100 - self.params["rsi_overbought"]),
                "bb_above_upper": min(abs(curr_price - curr_bb_upper) / (curr_atr or 1), 1.0),
                "zscore": min(abs(curr_zscore) / 3.0, 1.0),
            }
            conf = signal_confidence(indicators)

            sl = curr_price + 1.5 * curr_atr
            tp = curr_bb_middle

            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=curr_price,
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                timeframe=timeframe,
                indicators=indicators,
            )

        return None
