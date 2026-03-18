"""
Market Data Engine — fetches real-time and historical OHLCV data
exclusively from MetaTrader 5.

Async architecture:
    - MT5 calls wrapped in asyncio.to_thread (blocking C API)
    - fetch_all_pairs uses asyncio.gather for parallel fetching
    - DB candle storage is deferred to background (non-blocking)
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from config.settings import get_settings
from config.constants import Timeframe
from database.session import get_session
from database import repository as repo
from utils.logging_config import get_logger

logger = get_logger("market_data")

# MT5 C API is NOT thread-safe — all calls must be serialised.
_mt5_lock = asyncio.Lock()
_db_write_lock = asyncio.Lock()

_MT5_TF_MAP: dict | None = None


def _get_mt5_tf_map():
    global _MT5_TF_MAP
    if _MT5_TF_MAP is None:
        import MetaTrader5 as mt5
        _MT5_TF_MAP = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
    return _MT5_TF_MAP


# ── Abstract provider ────────────────────────────────────────────────────

class DataProvider(ABC):

    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_candles(self, symbol: str, timeframe: str,
                          count: int = 500) -> pd.DataFrame: ...

    @abstractmethod
    async def get_tick(self, symbol: str) -> dict: ...

    @abstractmethod
    async def get_spread(self, symbol: str) -> float: ...

    @abstractmethod
    async def get_account_info(self) -> dict: ...


# ── MT5 Provider (sole data source) ──────────────────────────────────────

class MT5DataProvider(DataProvider):
    """MetaTrader 5 data provider — the only data source for real trading."""

    def __init__(self):
        self._connected = False
        self._settings = get_settings()

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        import MetaTrader5 as mt5

        init_kwargs: dict = {}
        if self._settings.mt5_path:
            init_kwargs["path"] = self._settings.mt5_path
        if self._settings.mt5_login:
            init_kwargs["login"] = self._settings.mt5_login
            init_kwargs["password"] = self._settings.mt5_password
            init_kwargs["server"] = self._settings.mt5_server
            init_kwargs["timeout"] = self._settings.mt5_timeout

        async with _mt5_lock:
            result = await asyncio.to_thread(mt5.initialize, **init_kwargs)
        if not result:
            error = mt5.last_error()
            logger.error("MT5 init failed", error=str(error))
            return False

        async with _mt5_lock:
            info = await asyncio.to_thread(mt5.account_info)
        if info:
            logger.info("MT5 connected",
                        account=info.login, server=info.server,
                        balance=info.balance, leverage=info.leverage)
        else:
            logger.info("MT5 connected")

        self._connected = True
        return True

    async def disconnect(self) -> None:
        if self._connected:
            import MetaTrader5 as mt5
            await asyncio.to_thread(mt5.shutdown)
            self._connected = False
            logger.info("MT5 disconnected")

    async def get_candles(self, symbol: str, timeframe: str,
                          count: int = 500) -> pd.DataFrame:
        import MetaTrader5 as mt5

        tf_map = _get_mt5_tf_map()
        mt5_tf = tf_map.get(timeframe)
        if mt5_tf is None:
            raise ValueError(f"Unknown timeframe: {timeframe}")

        async with _mt5_lock:
            rates = await asyncio.to_thread(
                mt5.copy_rates_from_pos, symbol, mt5_tf, 0, count
            )
        if rates is None or len(rates) == 0:
            logger.warning("No candles returned", symbol=symbol, timeframe=timeframe)
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={
            "time": "timestamp", "open": "open", "high": "high",
            "low": "low", "close": "close", "tick_volume": "volume",
            "spread": "spread",
        }, inplace=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume", "spread"]]
        return df

    async def get_tick(self, symbol: str) -> dict:
        import MetaTrader5 as mt5

        async with _mt5_lock:
            tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
        if tick is None:
            return {}
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "time": datetime.fromtimestamp(tick.time),
        }

    async def get_spread(self, symbol: str) -> float:
        tick = await self.get_tick(symbol)
        if not tick:
            return 0.0
        return tick["ask"] - tick["bid"]

    async def get_account_info(self) -> dict:
        import MetaTrader5 as mt5

        async with _mt5_lock:
            info = await asyncio.to_thread(mt5.account_info)
        if info is None:
            return {}
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "currency": info.currency,
            "leverage": info.leverage,
            "profit": info.profit,
            "name": info.name,
            "login": info.login,
            "server": info.server,
        }


# ── Market Data Engine ───────────────────────────────────────────────────

class MarketDataEngine:
    """Central market data engine.  Wraps the MT5 provider with caching
    and DB storage."""

    def __init__(self, provider: DataProvider):
        self.provider = provider
        self._cache: Dict[str, pd.DataFrame] = {}
        self._settings = get_settings()

    async def start(self) -> bool:
        return await self.provider.connect()

    async def stop(self) -> None:
        await self.provider.disconnect()

    async def fetch_candles(self, symbol: str, timeframe: str,
                            count: int = 500, store: bool = True) -> pd.DataFrame:
        df = await self.provider.get_candles(symbol, timeframe, count)
        if df.empty:
            return df
        cache_key = f"{symbol}_{timeframe}"
        self._cache[cache_key] = df
        if store and len(df) > 0:
            # Defer DB storage to background — don't block the data pipeline
            asyncio.create_task(
                self._store_candles_bg(symbol, timeframe, df.tail(10))
            )
        return df

    async def _store_candles_bg(self, symbol: str, timeframe: str,
                                 recent: pd.DataFrame) -> None:
        """Store candles to DB in background (non-blocking)."""
        try:
            # SQLite allows limited writer concurrency; serialize background writes.
            async with _db_write_lock:
                session = await get_session()
                try:
                    candles_list = []
                    for _, row in recent.iterrows():
                        candles_list.append({
                            "symbol": symbol, "timeframe": timeframe,
                            "open": row["open"], "high": row["high"],
                            "low": row["low"], "close": row["close"],
                            "volume": row.get("volume"), "spread": row.get("spread"),
                            "timestamp": row["timestamp"],
                        })
                    await repo.store_candles(session, candles_list)
                finally:
                    await session.close()
        except Exception as e:
            logger.error("Background candle storage failed",
                         symbol=symbol, error=str(e))

    def get_cached(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        return self._cache.get(f"{symbol}_{timeframe}")

    async def get_tick(self, symbol: str) -> dict:
        return await self.provider.get_tick(symbol)

    async def get_spread(self, symbol: str) -> float:
        return await self.provider.get_spread(symbol)

    async def get_account_info(self) -> dict:
        return await self.provider.get_account_info()

    async def fetch_all_pairs(self, timeframe: str | None = None,
                              count: int = 500) -> Dict[str, pd.DataFrame]:
        tf = timeframe or self._settings.default_timeframe

        async def _fetch_one(symbol: str) -> tuple:
            try:
                df = await self.fetch_candles(symbol, tf, count)
                return symbol, df
            except Exception as e:
                logger.error("Failed to fetch data", symbol=symbol, error=str(e))
                return symbol, pd.DataFrame()

        tasks = [_fetch_one(s) for s in self._settings.pairs_list]
        pair_results = await asyncio.gather(*tasks)
        return {sym: df for sym, df in pair_results if not df.empty}
