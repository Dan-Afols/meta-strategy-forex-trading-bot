"""
Trend-Following Strategy — uses moving averages, MACD, and ADX.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config.constants import SignalType, StrategyType, DEFAULT_STRATEGY_PARAMS, PIP_SIZE
from strategies.base import BaseStrategy, Signal
from utils.indicators import ema, sma, macd, adx, atr
from utils.math_helpers import signal_confidence


class TrendFollowingStrategy(BaseStrategy):
    name = "TrendFollowing"
    strategy_type = StrategyType.TREND_FOLLOWING

    def __init__(self, params: dict | None = None):
        defaults = DEFAULT_STRATEGY_PARAMS["TREND_FOLLOWING"]
        merged = {**defaults, **(params or {})}
        super().__init__(merged)

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        if not self.validate_data(df, min_rows=60):
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Moving averages
        fast_ma = ema(close, self.params["fast_ma_period"])
        slow_ma = ema(close, self.params["slow_ma_period"])

        # MACD
        macd_line, macd_signal, macd_hist = macd(
            close, fast=12, slow=26, signal=self.params["signal_ma_period"]
        )

        # ADX for trend strength
        adx_val = adx(high, low, close, self.params["adx_period"])

        # ATR for SL/TP
        atr_val = atr(high, low, close, 14)

        # Get latest values
        curr_fast = fast_ma.iloc[-1]
        curr_slow = slow_ma.iloc[-1]
        prev_fast = fast_ma.iloc[-2]
        prev_slow = slow_ma.iloc[-2]
        curr_macd_hist = macd_hist.iloc[-1]
        prev_macd_hist = macd_hist.iloc[-2]
        curr_adx = adx_val.iloc[-1] if not np.isnan(adx_val.iloc[-1]) else 0
        curr_atr = atr_val.iloc[-1]
        curr_price = close.iloc[-1]

        pip = PIP_SIZE.get(symbol, 0.0001)

        # ── BUY signal ──────────────────────────────────────────────
        if (curr_fast > curr_slow and prev_fast <= prev_slow and
                curr_macd_hist > 0 and curr_adx >= self.params["adx_threshold"]):

            indicators = {
                "ma_crossover": 1.0,
                "macd_histogram": min(curr_macd_hist / (curr_atr or 1), 1.0),
                "adx_strength": min(curr_adx / 50, 1.0),
            }
            conf = signal_confidence(indicators)

            sl = curr_price - 2.0 * curr_atr
            tp = curr_price + 3.0 * curr_atr

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

        # ── SELL signal ─────────────────────────────────────────────
        if (curr_fast < curr_slow and prev_fast >= prev_slow and
                curr_macd_hist < 0 and curr_adx >= self.params["adx_threshold"]):

            indicators = {
                "ma_crossover": -1.0,
                "macd_histogram": max(curr_macd_hist / (curr_atr or 1), -1.0),
                "adx_strength": min(curr_adx / 50, 1.0),
            }
            conf = signal_confidence(indicators)

            sl = curr_price + 2.0 * curr_atr
            tp = curr_price - 3.0 * curr_atr

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
