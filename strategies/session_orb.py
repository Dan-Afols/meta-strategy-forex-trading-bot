"""
Session Opening Range Breakout (ORB) strategy.

Focus:
  - Trade only when price decisively breaks the opening range of London/NY sessions.
  - Avoid low-quality setups by enforcing opening-range size sanity vs ATR.
  - Keep risk/reward structured using the opposite side of the opening range.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from config.constants import DEFAULT_STRATEGY_PARAMS, SignalType, StrategyType
from strategies.base import BaseStrategy, Signal
from utils.indicators import atr
from utils.math_helpers import signal_confidence


class SessionOpeningRangeBreakoutStrategy(BaseStrategy):
    name = "SessionORB"
    strategy_type = StrategyType.BREAKOUT

    def __init__(self, params: dict | None = None):
        defaults = DEFAULT_STRATEGY_PARAMS["SESSION_ORB"]
        merged = {**defaults, **(params or {})}
        super().__init__(merged)

    @staticmethod
    def _timeframe_minutes(timeframe: str) -> Optional[int]:
        tf = (timeframe or "").upper().strip()
        if tf.startswith("M") and tf[1:].isdigit():
            return int(tf[1:])
        if tf.startswith("H") and tf[1:].isdigit():
            return int(tf[1:]) * 60
        return None

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

    def _session_window(self, now: datetime) -> Optional[tuple[str, datetime, datetime]]:
        sessions = [
            ("LONDON", int(self.params["london_open_hour_utc"])),
            ("NEW_YORK", int(self.params["newyork_open_hour_utc"])),
        ]
        open_window = int(self.params["open_range_minutes"])
        max_trade_minutes = int(self.params["max_trade_minutes_after_open"])

        chosen: Optional[tuple[str, datetime, datetime]] = None
        for name, open_hour in sessions:
            start = now.replace(hour=open_hour, minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=open_window)
            latest_allowed = start + timedelta(minutes=max_trade_minutes)
            if now >= end and now <= latest_allowed:
                if chosen is None or start > chosen[1]:
                    chosen = (name, start, end)
        return chosen

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        if not self._is_allowed_symbol(symbol):
            return None
        if not self._is_allowed_timeframe(timeframe):
            return None
        if not self.validate_data(df, min_rows=80):
            return None
        if "timestamp" not in df.columns:
            return None

        data = df.copy()
        data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
        data = data.dropna(subset=["timestamp"])
        if len(data) < 80:
            return None

        now = data["timestamp"].iloc[-1].to_pydatetime()
        session = self._session_window(now)
        if session is None:
            return None

        session_name, range_start, range_end = session
        orb = data[(data["timestamp"] >= range_start) & (data["timestamp"] < range_end)]
        tf_minutes = self._timeframe_minutes(timeframe)
        if tf_minutes is None or tf_minutes <= 0:
            return None
        min_orb_bars = max(2, int(np.ceil(float(self.params["open_range_minutes"]) / float(tf_minutes))))
        if len(orb) < min_orb_bars:
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]

        atr_series = atr(high, low, close, int(self.params["atr_period"]))
        curr_atr = float(atr_series.iloc[-1])
        if np.isnan(curr_atr) or curr_atr <= 0:
            return None

        orb_high = float(orb["high"].max())
        orb_low = float(orb["low"].min())
        orb_range = orb_high - orb_low
        orb_range_atr = orb_range / curr_atr

        if orb_range_atr < float(self.params["min_range_atr"]):
            return None
        if orb_range_atr > float(self.params["max_range_atr"]):
            return None

        buffer_atr = float(self.params["breakout_buffer_atr"])
        break_buffer = buffer_atr * curr_atr

        curr_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        momentum = abs(curr_close - float(close.iloc[-4])) / curr_atr if len(close) > 4 else 0.0
        momentum = float(min(momentum, 1.0))

        # Buy breakout above opening range.
        if curr_close > orb_high + break_buffer and prev_close <= orb_high + break_buffer:
            stop = orb_low - curr_atr * float(self.params["stop_buffer_atr"])
            risk = curr_close - stop
            if risk <= 0:
                return None
            rr = float(self.params["rr_ratio"])
            target = curr_close + rr * risk

            indicators = {
                "break_strength": min((curr_close - orb_high) / curr_atr, 1.0),
                "range_quality": max(0.0, 1.0 - min(abs(orb_range_atr - 1.0) / 1.5, 1.0)),
                "momentum": momentum,
            }
            conf = signal_confidence(indicators)

            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=curr_close,
                stop_loss=round(stop, 5),
                take_profit=round(target, 5),
                timeframe=timeframe,
                indicators=indicators,
                metadata={
                    "session": session_name,
                    "orb_high": orb_high,
                    "orb_low": orb_low,
                    "orb_bars": len(orb),
                },
            )

        # Sell breakout below opening range.
        if curr_close < orb_low - break_buffer and prev_close >= orb_low - break_buffer:
            stop = orb_high + curr_atr * float(self.params["stop_buffer_atr"])
            risk = stop - curr_close
            if risk <= 0:
                return None
            rr = float(self.params["rr_ratio"])
            target = curr_close - rr * risk

            indicators = {
                "break_strength": min((orb_low - curr_close) / curr_atr, 1.0),
                "range_quality": max(0.0, 1.0 - min(abs(orb_range_atr - 1.0) / 1.5, 1.0)),
                "momentum": momentum,
            }
            conf = signal_confidence(indicators)

            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=curr_close,
                stop_loss=round(stop, 5),
                take_profit=round(target, 5),
                timeframe=timeframe,
                indicators=indicators,
                metadata={
                    "session": session_name,
                    "orb_high": orb_high,
                    "orb_low": orb_low,
                    "orb_bars": len(orb),
                },
            )

        return None
