"""
Market Session Detector — identifies active Forex trading sessions.

Sessions (UTC times):
- Sydney:  21:00 – 06:00
- Tokyo:   00:00 – 09:00
- London:  07:00 – 16:00
- New York: 12:00 – 21:00

Overlaps produce higher volatility and volume.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List


class MarketSession(str, Enum):
    SYDNEY = "SYDNEY"
    TOKYO = "TOKYO"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"


@dataclass
class SessionInfo:
    """Current session state with overlap detection."""
    active_sessions: List[MarketSession]
    is_overlap: bool
    overlap_sessions: List[str]
    volatility_expectation: str  # LOW, MEDIUM, HIGH
    best_pairs: List[str]

    def to_dict(self) -> dict:
        return {
            "active_sessions": [s.value for s in self.active_sessions],
            "is_overlap": self.is_overlap,
            "overlap_sessions": self.overlap_sessions,
            "volatility_expectation": self.volatility_expectation,
            "best_pairs": self.best_pairs,
        }


# Session hours in UTC (start_hour, end_hour).
# When start > end, session crosses midnight.
_SESSION_HOURS = {
    MarketSession.SYDNEY: (21, 6),
    MarketSession.TOKYO: (0, 9),
    MarketSession.LONDON: (7, 16),
    MarketSession.NEW_YORK: (12, 21),
}

# Pairs that tend to be most active during each session
_SESSION_PAIRS = {
    MarketSession.SYDNEY: ["AUDUSD", "NZDUSD", "USDJPY"],
    MarketSession.TOKYO: ["USDJPY", "EURJPY", "GBPJPY", "AUDUSD"],
    MarketSession.LONDON: ["EURUSD", "GBPUSD", "EURGBP", "USDCHF"],
    MarketSession.NEW_YORK: ["EURUSD", "GBPUSD", "USDCAD", "USDJPY"],
}


class SessionDetector:
    """Detects which Forex trading sessions are currently active."""

    def _is_session_active(self, session: MarketSession, hour: int) -> bool:
        start, end = _SESSION_HOURS[session]
        if start > end:  # Crosses midnight
            return hour >= start or hour < end
        return start <= hour < end

    def detect(self, utc_now: datetime | None = None) -> SessionInfo:
        """Detect currently active sessions."""
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)
        hour = utc_now.hour

        active: List[MarketSession] = []
        for session in MarketSession:
            if self._is_session_active(session, hour):
                active.append(session)

        # Overlap detection
        overlap_names: List[str] = []
        if len(active) >= 2:
            overlap_names = [
                f"{active[i].value}-{active[j].value}"
                for i in range(len(active))
                for j in range(i + 1, len(active))
            ]

        # Volatility expectation
        if len(active) == 0:
            vol = "LOW"
        elif len(active) >= 2:
            vol = "HIGH"
        elif MarketSession.LONDON in active or MarketSession.NEW_YORK in active:
            vol = "MEDIUM"
        else:
            vol = "LOW"

        # Best pairs for current sessions
        pair_set: set = set()
        for sess in active:
            pair_set.update(_SESSION_PAIRS.get(sess, []))

        return SessionInfo(
            active_sessions=active,
            is_overlap=len(active) >= 2,
            overlap_sessions=overlap_names,
            volatility_expectation=vol,
            best_pairs=sorted(pair_set),
        )

    def is_weekend(self, utc_now: datetime | None = None) -> bool:
        """Check if market is closed (weekend)."""
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)
        # Forex closes Friday 21:00 UTC, reopens Sunday 21:00 UTC
        wd = utc_now.weekday()  # 0=Mon, 6=Sun
        if wd == 4 and utc_now.hour >= 21:
            return True
        if wd == 5:
            return True
        if wd == 6 and utc_now.hour < 21:
            return True
        return False
