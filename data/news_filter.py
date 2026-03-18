"""
High-impact news event filter.

This module provides a deterministic, config-driven blocker that can pause
trade entries around scheduled macro events (e.g., Fed/ECB/BoJ decisions).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree as ET

import httpx

from config.settings import get_settings
from utils.logging_config import get_logger

logger = get_logger("news_filter")


@dataclass
class NewsEvent:
    timestamp_utc: datetime
    label: str
    impact: str
    currencies: List[str]


class NewsEventFilter:
    """Blocks new trade entries near configured high-impact events.

    Events are read from `NEWS_EVENTS_UTC` with format:
      YYYY-MM-DDTHH:MM:SSZ|Label|HIGH|USD,EUR;YYYY-MM-DDTHH:MM:SSZ|Label|HIGH|JPY
    """

    def __init__(self):
        self.settings = get_settings()
        self._events: List[NewsEvent] = []
        self._last_refresh_utc: datetime | None = None
        self._cache_path = Path(self.settings.data_dir) / "news_events_cache.json"
        self.reload_events()

    def reload_events(self) -> None:
        if self.settings.enable_news_events_utc:
            self._events = self._parse_events(self.settings.news_events_utc)
        else:
            self._events = []

    async def refresh_if_needed(self, force: bool = False) -> None:
        """Refresh events from remote feed when enabled and interval elapsed.

        Uses local cache as fallback when network/source is unavailable.
        """
        if not self.settings.enable_news_auto_update:
            return

        now = datetime.now(timezone.utc)
        refresh_after = timedelta(minutes=max(5, self.settings.news_auto_refresh_minutes))
        if not force and self._last_refresh_utc and (now - self._last_refresh_utc) < refresh_after:
            return

        manual_events = (
            self._parse_events(self.settings.news_events_utc)
            if self.settings.enable_news_events_utc
            else []
        )
        auto_events = await self._fetch_auto_events()
        if not auto_events:
            auto_events = self._load_cache_events()

        merged = self._merge_events(manual_events, auto_events)
        self._events = merged
        self._last_refresh_utc = now

        if auto_events:
            self._save_cache_events(auto_events)

    async def _fetch_auto_events(self) -> List[NewsEvent]:
        url = (self.settings.news_events_url or "").strip()
        if not url:
            return []

        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            events = self._parse_forex_factory_xml(resp.text)
            if events:
                logger.info("News feed refreshed", count=len(events), url=url)
            return events
        except Exception as e:
            logger.warning("News feed refresh failed", error=str(e), url=url)
            return []

    def _parse_forex_factory_xml(self, xml_text: str) -> List[NewsEvent]:
        events: List[NewsEvent] = []
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return events

        for node in root.findall(".//event"):
            impact = (node.findtext("impact") or "").strip().upper()
            if "HIGH" not in impact:
                continue

            date_str = (node.findtext("date") or "").strip()
            time_str = (node.findtext("time") or "").strip().lower()
            if not date_str or not time_str or "all" in time_str or "tentative" in time_str:
                continue

            label = (node.findtext("title") or "High Impact Event").strip()
            currency = (node.findtext("country") or node.findtext("currency") or "").strip().upper()
            if not currency:
                continue

            ts = self._parse_ff_datetime_utc(date_str, time_str)
            if ts is None:
                continue

            events.append(
                NewsEvent(
                    timestamp_utc=ts,
                    label=label,
                    impact="HIGH",
                    currencies=[currency],
                )
            )

        events.sort(key=lambda e: e.timestamp_utc)
        return events

    @staticmethod
    def _parse_ff_datetime_utc(date_str: str, time_str: str) -> datetime | None:
        # Common feed formats include "03-12-2026" and time like "8:30am".
        candidates = [
            "%m-%d-%Y %I:%M%p",
            "%Y-%m-%d %I:%M%p",
            "%b %d %Y %I:%M%p",
            "%d %b %Y %I:%M%p",
        ]

        text = f"{date_str} {time_str}".replace(" ", "")
        for fmt in candidates:
            try:
                # Reinsert single space between date and time for strptime.
                dt = datetime.strptime(f"{date_str} {time_str}", fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _save_cache_events(self, events: List[NewsEvent]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [
                {
                    "timestamp_utc": e.timestamp_utc.isoformat(),
                    "label": e.label,
                    "impact": e.impact,
                    "currencies": e.currencies,
                }
                for e in events
            ]
            self._cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save news cache", error=str(e))

    def _load_cache_events(self) -> List[NewsEvent]:
        if not self._cache_path.exists():
            return []
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
            out: List[NewsEvent] = []
            for item in payload:
                ts = datetime.fromisoformat(item["timestamp_utc"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                out.append(
                    NewsEvent(
                        timestamp_utc=ts.astimezone(timezone.utc),
                        label=item.get("label", "High Impact Event"),
                        impact=item.get("impact", "HIGH"),
                        currencies=[c.upper() for c in item.get("currencies", []) if c],
                    )
                )
            out.sort(key=lambda e: e.timestamp_utc)
            if out:
                logger.info("Loaded news events from cache", count=len(out))
            return out
        except Exception as e:
            logger.warning("Failed to load news cache", error=str(e))
            return []

    @staticmethod
    def _merge_events(primary: List[NewsEvent], secondary: List[NewsEvent]) -> List[NewsEvent]:
        seen = set()
        merged: List[NewsEvent] = []
        for event in [*primary, *secondary]:
            key = (event.timestamp_utc.isoformat(), event.label, tuple(event.currencies))
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
        merged.sort(key=lambda e: e.timestamp_utc)
        return merged

    def _parse_events(self, raw: str) -> List[NewsEvent]:
        if not raw:
            return []

        parsed: List[NewsEvent] = []
        chunks = [c.strip() for c in raw.split(";") if c.strip()]
        for chunk in chunks:
            parts = [p.strip() for p in chunk.split("|")]
            if len(parts) < 4:
                continue
            ts_raw, label, impact, currencies_raw = parts[:4]
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
            except ValueError:
                continue

            currencies = [c.strip().upper() for c in currencies_raw.split(",") if c.strip()]
            if not currencies:
                continue

            parsed.append(
                NewsEvent(
                    timestamp_utc=ts,
                    label=label,
                    impact=impact.upper(),
                    currencies=currencies,
                )
            )
        parsed.sort(key=lambda e: e.timestamp_utc)
        return parsed

    @staticmethod
    def _symbol_currencies(symbol: str) -> tuple[str, str]:
        s = symbol.upper()
        if len(s) < 6:
            return ("", "")
        return s[:3], s[3:6]

    def is_blocked(self, symbol: str, now_utc: Optional[datetime] = None) -> tuple[bool, Optional[NewsEvent], str]:
        """Return whether entries for symbol should be blocked now."""
        if not self.settings.enable_news_filter:
            return False, None, "disabled"
        if not self._events:
            return False, None, "no_events_configured"

        now = now_utc or datetime.now(timezone.utc)
        base, quote = self._symbol_currencies(symbol)
        if not base or not quote:
            return False, None, "invalid_symbol"

        before = timedelta(minutes=self.settings.news_block_minutes_before)
        after = timedelta(minutes=self.settings.news_block_minutes_after)

        for event in self._events:
            if event.impact != "HIGH":
                continue
            if base not in event.currencies and quote not in event.currencies:
                continue

            start = event.timestamp_utc - before
            end = event.timestamp_utc + after
            if start <= now <= end:
                return True, event, "within_block_window"

        return False, None, "clear"

    def next_events(self, symbol: str, limit: int = 3) -> List[NewsEvent]:
        now = datetime.now(timezone.utc)
        base, quote = self._symbol_currencies(symbol)
        out: List[NewsEvent] = []
        for event in self._events:
            if event.timestamp_utc < now:
                continue
            if base in event.currencies or quote in event.currencies:
                out.append(event)
            if len(out) >= limit:
                break
        return out
