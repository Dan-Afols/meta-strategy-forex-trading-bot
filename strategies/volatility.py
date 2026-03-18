"""
Volatility Strategy — trades based on ATR expansion / contraction.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config.constants import SignalType, StrategyType, DEFAULT_STRATEGY_PARAMS, PIP_SIZE
from strategies.base import BaseStrategy, Signal
from utils.indicators import atr, bollinger_bands, ema, rsi
from utils.math_helpers import signal_confidence


class VolatilityStrategy(BaseStrategy):
    name = "Volatility"
    strategy_type = StrategyType.VOLATILITY

    def __init__(self, params: dict | None = None):
        defaults = DEFAULT_STRATEGY_PARAMS["VOLATILITY"]
        merged = {**defaults, **(params or {})}
        super().__init__(merged)

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        if not self.validate_data(df, min_rows=50):
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # ATR analysis
        atr_val = atr(high, low, close, self.params["atr_period"])
        avg_atr = atr_val.tail(self.params["volatility_lookback"]).mean()
        curr_atr = atr_val.iloc[-1]

        if avg_atr == 0 or np.isnan(avg_atr):
            return None

        vol_ratio = curr_atr / avg_atr

        # Bollinger Band width as volatility gauge
        bb_upper, bb_middle, bb_lower = bollinger_bands(close, 20, 2.0)
        bb_width = (bb_upper - bb_lower) / bb_middle
        avg_width = bb_width.tail(self.params["volatility_lookback"]).mean()
        curr_width = bb_width.iloc[-1]

        # Direction from EMA
        ema_20 = ema(close, 20)
        ema_50 = ema(close, 50)
        trend_up = ema_20.iloc[-1] > ema_50.iloc[-1]

        # RSI for direction confirmation
        rsi_val = rsi(close, 14)
        curr_rsi = rsi_val.iloc[-1]

        curr_price = close.iloc[-1]
        pip = PIP_SIZE.get(symbol, 0.0001)

        # Volatility expansion — trade in trend direction
        if vol_ratio > self.params["high_vol_threshold"]:

            if trend_up and curr_rsi > 50:
                indicators = {
                    "vol_expansion": min(vol_ratio / 2.5, 1.0),
                    "trend_alignment": 1.0,
                    "rsi_momentum": (curr_rsi - 50) / 50,
                }
                conf = signal_confidence(indicators)

                sl = curr_price - 2.5 * curr_atr
                tp = curr_price + 3.5 * curr_atr

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

            if not trend_up and curr_rsi < 50:
                indicators = {
                    "vol_expansion": min(vol_ratio / 2.5, 1.0),
                    "trend_alignment": 1.0,
                    "rsi_momentum": (50 - curr_rsi) / 50,
                }
                conf = signal_confidence(indicators)

                sl = curr_price + 2.5 * curr_atr
                tp = curr_price - 3.5 * curr_atr

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
