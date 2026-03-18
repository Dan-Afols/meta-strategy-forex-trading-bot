"""
Main entry point — Forex Trading System.

Orchestrates all engines: data, strategy, ML, risk, execution,
notifications, and the dashboard API.

Architecture:
  CRITICAL PATH (blocking, lowest latency):
    Market Data → Parallel Strategy Eval → ML Filter → Risk Check → Trade Execution

  BACKGROUND (fire-and-forget, non-blocking):
    Chart generation, Telegram notifications, DB writes (snapshots, logs)
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from collections import deque

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from config.settings import get_settings, ensure_directories
from core.task_manager import BackgroundTaskManager
from database.session import init_db, close_db
from data.market_data import MarketDataEngine, MT5DataProvider
from strategies.engine import StrategyEngine
from ml_models.engine import MLEngine
from execution.risk_manager import RiskManager
from execution.trade_executor import TradeExecutor
from charts.generator import ChartGenerator
from notifications.telegram_bot import TelegramNotifier
from data.session_detector import SessionDetector
from data.news_filter import NewsEventFilter
from dashboard.api import router as api_router, set_bot_state, set_bot_reference
from utils.logging_config import setup_logging, get_logger

logger = get_logger("main")


# ── Trading Bot ─────────────────────────────────────────────────────────

class TradingBot:
    """Core trading loop that runs autonomously.

    Uses a BackgroundTaskManager to keep chart generation, Telegram
    notifications, and non-critical DB writes off the critical path.
    """

    def __init__(self):
        self._running = False
        self._settings = get_settings()
        self._bg = BackgroundTaskManager()

        # MT5 is the sole data provider
        self.data_engine = MarketDataEngine(MT5DataProvider())

        self.strategy_engine = StrategyEngine(use_meta_strategy=True, lookback_days=30)
        self.ml_engine = MLEngine()
        self.risk_manager = RiskManager()
        self.trade_executor = TradeExecutor(self.risk_manager)
        self.chart_generator = ChartGenerator()
        self.telegram = TelegramNotifier()
        self.session_detector = SessionDetector()
        self.news_filter = NewsEventFilter()

        self._cycle_count = 0
        self._latency_ms_window = deque(maxlen=200)

    async def start(self) -> None:
        """Initialize all engines and start the trading loop."""
        logger.info("Starting trading bot...")

        # Initialize database
        await init_db(self._settings.database_url)

        # Connect to MT5
        connected = await self.data_engine.start()
        if not connected:
            logger.error("MT5 connection failed — cannot trade without MT5")
            await self.telegram.send_startup_notification(connected=False)
            return

        # Update bot state for dashboard
        account = await self.data_engine.get_account_info()
        await self.news_filter.refresh_if_needed(force=True)
        set_bot_state("running", True)
        set_bot_state("active_pairs", self._settings.pairs_list)
        set_bot_state("strategies_active", len(self.strategy_engine.strategies))
        set_bot_state("account", account)

        self._running = True

        # Send startup notification with account details
        await self.telegram.send_startup_notification(
            connected=True,
            account=account,
            pairs=self._settings.pairs_list,
            strategies=len(self.strategy_engine.strategies),
        )

        # Start Telegram command listener (polling for /status, /balance, etc.)
        self.telegram.set_bot_reference(self)
        self.telegram.start_command_listener()

        logger.info("Bot initialized",
                     pairs=self._settings.pairs_list,
                     strategies=len(self.strategy_engine.strategies),
                     balance=account.get("balance"))

    async def stop(self) -> None:
        """Shutdown all engines and drain background tasks."""
        logger.info("Stopping trading bot...")
        self._running = False
        set_bot_state("running", False)

        self.telegram.stop_command_listener()
        await self._bg.shutdown(timeout=15.0)
        await self.data_engine.stop()
        await close_db()
        await self.telegram.send_error("🔴 Trading bot stopped")
        logger.info("Bot stopped")

    async def run_cycle(self) -> None:
        """Execute one full trading cycle.

        CRITICAL PATH (blocking):
          1. Check market hours
          2. Fetch market data (parallel across pairs)
          3. Analyze all pairs (parallel strategy evaluation)
          4. For each signal: ML filter → risk check → execute trade
          5. Update dashboard state

        BACKGROUND (fire-and-forget via BackgroundTaskManager):
          - Account snapshot DB write
          - Chart generation (matplotlib, CPU-bound)
          - Telegram signal/trade notifications
        """
        if not self._running:
            return

        try:
            cycle_start = time.time()
            logger.info("Starting trading cycle")

            # Refresh external news calendar on configured schedule.
            await self.news_filter.refresh_if_needed()

            # 0. Check if market is open
            if self.session_detector.is_weekend():
                logger.info("Market is closed (weekend), skipping cycle")
                return

            # ── CRITICAL PATH ────────────────────────────────────

            # 1. Fetch market data (already parallel via asyncio.gather)
            data = await self.data_engine.fetch_all_pairs(
                self._settings.default_timeframe, count=300
            )
            if not data:
                logger.warning("No market data received")
                return

            # Optional higher-timeframe confirmation data
            htf_data = {}
            if self._settings.enable_mtf_confirmation:
                htf = self._settings.mtf_confirmation_timeframe

                async def _fetch_htf(symbol: str):
                    try:
                        df = await self.data_engine.fetch_candles(
                            symbol, htf, count=300, store=False
                        )
                        return symbol, df
                    except Exception as e:
                        logger.warning("HTF fetch failed", symbol=symbol, timeframe=htf, error=str(e))
                        return symbol, None

                htf_results = await asyncio.gather(
                    *[_fetch_htf(sym) for sym in data.keys()]
                )
                htf_data = {sym: df for sym, df in htf_results if df is not None and not df.empty}

            # 2. Parallel strategy analysis (CPU-bound work offloaded to threads)
            all_signals = await self.strategy_engine.analyze_all_pairs(
                data, self._settings.default_timeframe
            )

            # 3. Publish meta-strategy decisions to dashboard (fast, in-memory)
            meta_decisions = self.strategy_engine.get_meta_decisions()
            set_bot_state("meta_decisions", meta_decisions)

            # 4. Get live account info from MT5
            account = await self.data_engine.get_account_info()
            balance = account.get("balance", 10000.0)
            set_bot_state("account", account)

            # 5. Save account snapshot → BACKGROUND
            self._bg.fire_and_forget(
                self._save_account_snapshot(account, balance),
                name="account_snapshot",
            )

            # 5b. Sync broker-closed positions and notify P&L outcomes
            await self._sync_closed_trades_and_notify()

            # 6. Process signals — CRITICAL PATH continues
            for symbol, signals in all_signals.items():
                for sig in signals:
                    blocked, event, _reason = self.news_filter.is_blocked(sig.symbol)
                    if blocked and event is not None:
                        logger.info(
                            "Signal blocked by news filter",
                            symbol=sig.symbol,
                            event=event.label,
                            event_time=event.timestamp_utc.isoformat(),
                            impact=event.impact,
                        )
                        continue

                    if self._settings.enable_mtf_confirmation:
                        if not self._confirm_multi_timeframe(sig, htf_data.get(symbol)):
                            logger.info(
                                "Signal blocked by MTF confirmation",
                                symbol=sig.symbol,
                                strategy=sig.strategy,
                                side=sig.signal_type.value,
                                htf=self._settings.mtf_confirmation_timeframe,
                            )
                            continue

                    # ML filter (CPU-bound → run in thread)
                    ml_approved = await asyncio.to_thread(
                        self.ml_engine.filter_signal,
                        data[symbol], symbol, sig.signal_type.value,
                    )
                    if not ml_approved:
                        logger.info("Signal filtered by ML", symbol=symbol,
                                     strategy=sig.strategy)
                        continue

                    # Execute trade FIRST — this is the critical path
                    result = await self.trade_executor.execute_signal(sig, balance)

                    # Chart generation + Telegram notifications → BACKGROUND
                    self._bg.fire_and_forget(
                        self._notify_signal(data[symbol], sig, result),
                        name=f"notify_{symbol}_{sig.strategy}",
                    )

            # 7. Update dashboard state
            set_bot_state("last_scan", datetime.utcnow())

            elapsed = time.time() - cycle_start
            latency_ms = round(elapsed * 1000.0, 2)
            self._latency_ms_window.append(latency_ms)

            avg_ms = round(sum(self._latency_ms_window) / len(self._latency_ms_window), 2)
            p95_ms = sorted(self._latency_ms_window)[max(0, int(len(self._latency_ms_window) * 0.95) - 1)]
            set_bot_state("latency", {
                "last_ms": latency_ms,
                "avg_ms": avg_ms,
                "p95_ms": round(float(p95_ms), 2),
            })

            # Automatic strategy evolution (safe, low-frequency)
            self._cycle_count += 1
            if (
                self._settings.enable_strategy_evolution
                and self._cycle_count % max(1, self._settings.strategy_evolution_interval_cycles) == 0
            ):
                evo = await self.strategy_engine.evolve_from_performance(
                    min_trades=self._settings.strategy_evolution_min_trades
                )
                set_bot_state("strategy_evolution", evo)

            logger.info("Trading cycle complete", elapsed_seconds=round(elapsed, 2),
                         signals_found=sum(len(s) for s in all_signals.values()),
                         bg_tasks_pending=self._bg.pending_count)

        except Exception as e:
            logger.error("Trading cycle error", error=str(e), exc_info=True)
            self._bg.fire_and_forget(
                self.telegram.send_error(f"Trading cycle error: {str(e)}"),
                name="cycle_error_notification",
            )

    # ── Background helpers ───────────────────────────────────────────

    async def _save_account_snapshot(self, account: dict, balance: float) -> None:
        """Save account snapshot to DB (runs in background)."""
        from database.session import get_session
        from database import repository as repo

        session = await get_session()
        try:
            open_count = await repo.count_open_trades(session)
            daily_pnl = await repo.get_daily_pnl(session)
            await repo.save_account_snapshot(
                session,
                balance=balance,
                equity=account.get("equity", balance),
                margin=account.get("margin", 0),
                free_margin=account.get("free_margin", balance),
                margin_level=account.get("margin_level", 0),
                open_positions=open_count,
                daily_pnl=daily_pnl,
            )
        finally:
            await session.close()

    async def _notify_signal(self, df, sig, trade_result) -> None:
        """Notify in execution-first order to avoid false trade alerts.

        Order:
          1) If executed: send signal chart + executed notification
          2) If failed/rejected: send failure notification only
        """
        if trade_result and trade_result.get("status") in {"FAILED", "REJECTED"}:
            await self.telegram.send_trade_failed({
                "symbol": sig.symbol,
                "status": trade_result.get("status"),
                "reason": trade_result.get("reason", "Order not executed"),
            })
            return

        # Generate chart in a thread (CPU-bound matplotlib work)
        chart_path = None
        try:
            chart_path = await asyncio.to_thread(
                self.chart_generator.generate_signal_chart, df, sig
            )
        except Exception as e:
            logger.error("Chart generation failed", error=str(e))

        # Send signal notification
        await self.telegram.send_signal(sig, chart_path)

        # Send trade executed notification if applicable
        if trade_result and trade_result["status"] == "EXECUTED":
            await self.telegram.send_trade_executed({
                "symbol": sig.symbol,
                "trade_id": trade_result["trade_id"],
                "lot_size": trade_result["lot_size"],
                "risk_percent": trade_result["risk_percent"],
                "meta_weight": sig.metadata.get("meta_weight", "N/A"),
                "meta_regime": sig.metadata.get("meta_regime", "N/A"),
            })

    async def _sync_closed_trades_and_notify(self) -> None:
        """Sync DB open trades with MT5 positions and notify closures.

        If a trade is OPEN in DB but no longer open at broker (e.g., TP/SL hit),
        close it in DB and send Telegram P&L notification.
        """
        from database.session import get_session
        from database import repository as repo

        session = await get_session()
        try:
            open_trades = await repo.get_open_trades(session)
        finally:
            await session.close()

        for t in open_trades:
            if not t.broker_ticket:
                continue

            try:
                still_open = await self.trade_executor.is_position_open(t.broker_ticket)
            except Exception as e:
                logger.error("Position sync check failed", trade_id=t.id, error=str(e))
                continue

            if still_open:
                continue

            result = await self.trade_executor.close_trade(t.id)
            if result and result.get("status") == "CLOSED":
                await self.telegram.send_trade_closed(result)
                logger.info(
                    "Trade closure synced",
                    trade_id=t.id,
                    symbol=result.get("symbol"),
                    pnl=result.get("pnl"),
                )

    async def run_loop(self, interval_seconds: int = 300) -> None:
        """Continuous trading loop."""
        while self._running:
            await self.run_cycle()

            # Keep closure sync responsive between full scan cycles.
            remaining = interval_seconds
            while self._running and remaining > 0:
                step = min(15, remaining)
                await asyncio.sleep(step)
                remaining -= step

                # Best-effort sync; do not break loop on monitor errors.
                try:
                    await self._sync_closed_trades_and_notify()
                except Exception as e:
                    logger.error("Inter-cycle trade sync failed", error=str(e))

    def _confirm_multi_timeframe(self, signal, htf_df: pd.DataFrame | None) -> bool:
        """Confirm signal direction against higher-timeframe trend.

        BUY is blocked when HTF trend is bearish.
        SELL is blocked when HTF trend is bullish.
        In strict mode, neutral HTF trend also blocks entries.
        """
        if htf_df is None or htf_df.empty or len(htf_df) < 60:
            return True

        period = max(10, int(self._settings.mtf_confirmation_ma_period))
        closes = htf_df["close"]
        ema = closes.ewm(span=period, adjust=False).mean()
        last_close = float(closes.iloc[-1])
        last_ema = float(ema.iloc[-1])
        prev_ema = float(ema.iloc[-5]) if len(ema) >= 5 else float(ema.iloc[0])

        if last_close > last_ema and last_ema >= prev_ema:
            trend = "BULLISH"
        elif last_close < last_ema and last_ema <= prev_ema:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        signal.metadata["mtf_trend"] = trend
        signal.metadata["mtf_timeframe"] = self._settings.mtf_confirmation_timeframe

        side = signal.signal_type.value
        if side == "BUY" and trend == "BEARISH":
            return False
        if side == "SELL" and trend == "BULLISH":
            return False
        if self._settings.mtf_confirmation_strict and trend == "NEUTRAL":
            return False
        return True


# ── Global bot instance ────────────────────────────────────────────────

bot: TradingBot | None = None
_start_time: float | None = None


# ── Lifecycle (replaces deprecated on_event) ───────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, _start_time
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir)
    ensure_directories(settings)
    bot = TradingBot()
    set_bot_reference(bot)
    await bot.start()
    bot._loop_task = asyncio.create_task(bot.run_loop(interval_seconds=300))
    _start_time = time.time()
    yield
    bot._loop_task.cancel()
    await bot.stop()
    bot = None


# ── FastAPI App ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Forex Trading System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if get_settings().debug else None,
    redoc_url=None,
)

# In production, restrict to your dashboard domain.
# Set CORS_ORIGINS in .env to a comma-separated list (e.g. https://yourdomain.com)
_cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# ── Health Check ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "trading": bot._running if bot else False,
        "uptime_seconds": int(time.time() - _start_time) if _start_time else 0,
    }


# ── Entry Point ────────────────────────────────────────────────────────

def main():
    """Run the full trading system."""
    s = get_settings()
    setup_logging(s.log_level, s.log_dir)
    ensure_directories(s)

    uvicorn.run(
        "main:app",
        host=s.dashboard_host,
        port=s.dashboard_port,
        reload=s.debug,
        log_level=s.log_level.lower(),
    )


if __name__ == "__main__":
    main()
