"""
Liquidity Sweep Reversal strategy.

Idea:
  - Detect stop-hunt style sweeps above/below recent swing levels.
  - Require strong rejection (wick dominance + close back inside).
  - Trade reversal with fixed minimum risk/reward profile.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config.constants import DEFAULT_STRATEGY_PARAMS, SignalType, StrategyType
from strategies.base import BaseStrategy, Signal
from utils.indicators import atr, rsi
from utils.math_helpers import signal_confidence


class LiquiditySweepReversalStrategy(BaseStrategy):
    name = "LiquiditySweepReversal"
    strategy_type = StrategyType.MEAN_REVERSION

    def __init__(self, params: dict | None = None):
        defaults = DEFAULT_STRATEGY_PARAMS["LIQUIDITY_SWEEP_REVERSAL"]
        merged = {**defaults, **(params or {})}
        super().__init__(merged)

    def _is_allowed_symbol(self, symbol: str) -> bool:
        raw = str(self.params.get("allowed_symbols", "")).strip()
        if not raw:
            return True
        allowed = {s.strip().upper() for s in raw.split(",") if s.strip()}
        return symbol.upper() in allowed

    def _is_allowed_timeframe(self, timeframe: str) -> bool:
        raw = str(self.params.get("allowed_timeframes", "")).strip()
        if not raw:
            return True
        allowed = {s.strip().upper() for s in raw.split(",") if s.strip()}
        return timeframe.upper() in allowed

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        if not self._is_allowed_symbol(symbol):
            return None
        if not self._is_allowed_timeframe(timeframe):
            return None
        if not self.validate_data(df, min_rows=70):
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_ = df["open"]
        volume = df.get("volume", pd.Series(dtype=float))

        atr_series = atr(high, low, close, int(self.params["atr_period"]))
        rsi_series = rsi(close, int(self.params["rsi_period"]))

        curr_atr = float(atr_series.iloc[-1])
        curr_rsi = float(rsi_series.iloc[-1])
        if np.isnan(curr_atr) or curr_atr <= 0 or np.isnan(curr_rsi):
            return None

        lookback = int(self.params["lookback_levels"])
        if len(df) < lookback + 5:
            return None

        level_high = float(high.iloc[-(lookback + 2):-2].max())
        level_low = float(low.iloc[-(lookback + 2):-2].min())

        o = float(open_.iloc[-1])
        h = float(high.iloc[-1])
        l = float(low.iloc[-1])
        c = float(close.iloc[-1])

        body = max(abs(c - o), 1e-10)
        upper_wick = max(h - max(o, c), 0.0)
        lower_wick = max(min(o, c) - l, 0.0)

        wick_body_ratio_up = upper_wick / body
        wick_body_ratio_down = lower_wick / body

        sweep_buffer = float(self.params["sweep_atr_buffer"]) * curr_atr
        stop_buffer = float(self.params["stop_atr_buffer"]) * curr_atr
        rr = float(self.params["rr_ratio"])

        vol_ok = True
        if len(volume.dropna()) > lookback:
            avg_vol = float(volume.tail(lookback).mean())
            curr_vol = float(volume.iloc[-1])
            vol_ok = curr_vol >= avg_vol * float(self.params["volume_multiplier"])

        # Bearish reversal after sweeping highs.
        swept_high = h >= (level_high + sweep_buffer)
        rejected_high = c < level_high
        wick_ok_sell = wick_body_ratio_up >= float(self.params["min_wick_body_ratio"])
        rsi_ok_sell = curr_rsi >= float(self.params["rsi_sell_min"])

        if swept_high and rejected_high and wick_ok_sell and rsi_ok_sell and vol_ok:
            stop = h + stop_buffer
            risk = stop - c
            if risk <= 0:
                return None
            target = c - rr * risk

            indicators = {
                "sweep_strength": min((h - level_high) / curr_atr, 1.0),
                "rejection_strength": min((upper_wick / curr_atr), 1.0),
                "rsi_extreme": min(max((curr_rsi - 50.0) / 30.0, 0.0), 1.0),
            }
            conf = signal_confidence(indicators)

            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=c,
                stop_loss=round(stop, 5),
                take_profit=round(target, 5),
                timeframe=timeframe,
                indicators=indicators,
                metadata={"level_high": level_high, "swept_high": h},
            )

        # Bullish reversal after sweeping lows.
        swept_low = l <= (level_low - sweep_buffer)
        rejected_low = c > level_low
        wick_ok_buy = wick_body_ratio_down >= float(self.params["min_wick_body_ratio"])
        rsi_ok_buy = curr_rsi <= float(self.params["rsi_buy_max"])

        if swept_low and rejected_low and wick_ok_buy and rsi_ok_buy and vol_ok:
            stop = l - stop_buffer
            risk = c - stop
            if risk <= 0:
                return None
            target = c + rr * risk

            indicators = {
                "sweep_strength": min((level_low - l) / curr_atr, 1.0),
                "rejection_strength": min((lower_wick / curr_atr), 1.0),
                "rsi_extreme": min(max((50.0 - curr_rsi) / 30.0, 0.0), 1.0),
            }
            conf = signal_confidence(indicators)

            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=c,
                stop_loss=round(stop, 5),
                take_profit=round(target, 5),
                timeframe=timeframe,
                indicators=indicators,
                metadata={"level_low": level_low, "swept_low": l},
            )

        return None
