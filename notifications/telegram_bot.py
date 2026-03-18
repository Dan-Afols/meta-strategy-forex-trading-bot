"""
Telegram Command & Notification Engine.

Provides full remote control of the trading bot via Telegram commands,
sends signal alerts with chart snapshots, and logs all command usage.

Security:
  - Only accepts commands from authorized chat IDs (TELEGRAM_CHAT_ID).
  - Unauthorized messages are silently ignored and logged.

Performance:
  - Polling runs as a background asyncio task — never blocks the trading loop.
  - HTTP requests use httpx.AsyncClient with timeouts and retries.
"""
from __future__ import annotations

import asyncio
import platform
import time
from datetime import datetime
from pathlib import Path

import httpx
import psutil

from config.settings import get_settings
from strategies.base import Signal
from utils.logging_config import get_logger

logger = get_logger("telegram")

_BOT_START_TIME: float = time.time()


class TelegramNotifier:
    """Secure Telegram command interface and notification engine."""

    def __init__(self):
        self._settings = get_settings()
        self._token = self._settings.telegram_bot_token
        self._chat_id = self._settings.telegram_chat_id
        self._enabled = self._settings.telegram_enabled
        self._base_url = f"https://api.telegram.org/bot{self._token}"
        self._validated = False
        self._disabled_reason: str | None = None
        self._last_update_id = 0
        self._polling_task: asyncio.Task | None = None
        self._bot_ref = None  # set by main.py

    # ── Properties ───────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        if self._disabled_reason:
            return False
        return bool(self._token and self._chat_id and self._enabled)

    # ── Bot reference ────────────────────────────────────────────────

    def set_bot_reference(self, bot) -> None:
        """Store reference to TradingBot for command callbacks."""
        self._bot_ref = bot

    # ── Command listener lifecycle ───────────────────────────────────

    def start_command_listener(self) -> None:
        if not self.is_configured:
            return
        self._polling_task = asyncio.create_task(self._poll_updates())
        logger.info("Telegram command listener started")

    def stop_command_listener(self) -> None:
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

    # ── Polling loop ─────────────────────────────────────────────────

    async def _poll_updates(self) -> None:
        """Long-poll Telegram getUpdates for commands."""
        while True:
            try:
                async with httpx.AsyncClient(timeout=35) as client:
                    resp = await client.get(
                        f"{self._base_url}/getUpdates",
                        params={
                            "offset": self._last_update_id + 1,
                            "timeout": 30,
                        },
                    )
                    if resp.status_code == 401:
                        self._disabled_reason = "invalid bot token (401)"
                        logger.warning("Bot token invalid — listener stopped")
                        return
                    if resp.status_code != 200:
                        await asyncio.sleep(5)
                        continue

                    data = resp.json()
                    for update in data.get("result", []):
                        self._last_update_id = update["update_id"]
                        msg = update.get("message", {})
                        text = msg.get("text", "")
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        user = msg.get("from", {})

                        # SECURITY: ignore unauthorised users
                        if chat_id != self._chat_id:
                            logger.warning(
                                "Unauthorised Telegram access attempt",
                                chat_id=chat_id,
                                user=user.get("username", "unknown"),
                            )
                            continue

                        if text.startswith("/"):
                            logger.info(
                                "Command received",
                                cmd=text,
                                user=user.get("username", "unknown"),
                            )
                            await self._dispatch_command(text.strip())

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug("Telegram poll error", error=str(e))
                await asyncio.sleep(10)

    # ── Command dispatcher ───────────────────────────────────────────

    async def _dispatch_command(self, text: str) -> None:
        parts = text.split()
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:] if len(parts) > 1 else []

        handlers = {
            "/startbot": self._cmd_startbot,
            "/stopbot": self._cmd_stopbot,
            "/status": self._cmd_status,
            "/balance": self._cmd_balance,
            "/positions": self._cmd_positions,
            "/performance": self._cmd_performance,
            "/pairs": self._cmd_pairs,
            "/enablepair": self._cmd_enablepair,
            "/disablepair": self._cmd_disablepair,
            "/risk": self._cmd_risk,
            "/logs": self._cmd_logs,
            "/restart": self._cmd_restart,
            "/health": self._cmd_health,
            "/newsutcon": self._cmd_newsutcon,
            "/newsutcoff": self._cmd_newsutcoff,
            "/help": self._cmd_help,
        }

        handler = handlers.get(cmd)
        if handler is None:
            await self._send_message(
                "❓ Unknown command. Type /help for available commands."
            )
            return

        try:
            import inspect
            sig = inspect.signature(handler)
            # Check if handler accepts arguments beyond 'self'
            params = [p for p in sig.parameters.values()
                      if p.name != "self"]
            if args and params:
                await handler(args)
            else:
                await handler()
        except Exception as e:
            logger.error("Command handler error", cmd=cmd, error=str(e))
            await self._send_message(f"⚠️ Error executing {cmd}: {e}")

    # ═══════════════════════════════════════════════════════════════════
    #  COMMANDS
    # ═══════════════════════════════════════════════════════════════════

    async def _cmd_startbot(self) -> None:
        from dashboard.api import get_bot_state, set_bot_state

        if get_bot_state().get("running"):
            await self._send_message("⚠️ Bot is already running.")
            return

        if self._bot_ref is None:
            await self._send_message("⚠️ Bot reference not available.")
            return

        self._bot_ref._running = True
        set_bot_state("running", True)
        task = asyncio.create_task(self._bot_ref.run_loop(interval_seconds=300))
        self._bot_ref._loop_task = task
        logger.info("Bot started via Telegram command")
        await self._send_message("🟢 <b>Trading bot STARTED</b>")

    async def _cmd_stopbot(self) -> None:
        from dashboard.api import get_bot_state, set_bot_state

        if not get_bot_state().get("running"):
            await self._send_message("⚠️ Bot is already stopped.")
            return

        if self._bot_ref:
            self._bot_ref._running = False
        set_bot_state("running", False)
        logger.info("Bot stopped via Telegram command")
        await self._send_message(
            "🔴 <b>Trading bot STOPPED</b>\n"
            "No new trades will be executed."
        )

    async def _cmd_status(self) -> None:
        from dashboard.api import get_bot_state
        from database.session import get_session
        from database import repository as repo

        state = get_bot_state()
        running = "🟢 RUNNING" if state.get("running") else "🔴 STOPPED"
        pairs_count = len(state.get("active_pairs", []))
        strategies = state.get("strategies_active", 0)

        session = await get_session()
        try:
            open_count = await repo.count_open_trades(session)
        finally:
            await session.close()

        last_scan = state.get("last_scan")
        scan_str = last_scan.strftime("%Y-%m-%d %H:%M:%S UTC") if last_scan else "N/A"

        uptime = time.time() - _BOT_START_TIME
        h, rem = divmod(int(uptime), 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s"

        msg = (
            f"📊 <b>BOT STATUS</b>\n\n"
            f"State: {running}\n"
            f"Uptime: {uptime_str}\n"
            f"Active Strategies: {strategies}\n"
            f"Active Pairs: {pairs_count}\n"
            f"Open Trades: {open_count}\n"
            f"Last Scan: {scan_str}\n"
        )
        await self._send_message(msg)

    async def _cmd_balance(self) -> None:
        from dashboard.api import get_bot_state

        account = get_bot_state().get("account", {})
        if not account:
            await self._send_message("⚠️ No account data available yet.")
            return

        msg = (
            f"💰 <b>ACCOUNT BALANCE</b>\n\n"
            f"Balance: <code>${account.get('balance', 0):,.2f}</code>\n"
            f"Equity: <code>${account.get('equity', 0):,.2f}</code>\n"
            f"Margin: <code>${account.get('margin', 0):,.2f}</code>\n"
            f"Free Margin: <code>${account.get('free_margin', 0):,.2f}</code>\n"
            f"Profit: <code>${account.get('profit', 0):,.2f}</code>\n"
            f"Leverage: 1:{account.get('leverage', 0)}\n"
        )
        await self._send_message(msg)

    async def _cmd_positions(self) -> None:
        from database.session import get_session
        from database import repository as repo

        session = await get_session()
        try:
            open_trades = await repo.get_open_trades(session)
        finally:
            await session.close()

        if not open_trades:
            await self._send_message("📭 No open positions.")
            return

        lines = [f"📋 <b>OPEN POSITIONS ({len(open_trades)})</b>\n"]
        for t in open_trades[:15]:
            emoji = "🟢" if t.order_type == "BUY" else "🔴"
            pnl_str = f"${t.pnl:+.2f}" if t.pnl is not None else "—"
            lines.append(
                f"{emoji} <b>{t.symbol}</b> {t.order_type}\n"
                f"   Entry: <code>{t.entry_price:.5f}</code>\n"
                f"   SL: <code>{t.stop_loss:.5f}</code>  |  "
                f"TP: <code>{t.take_profit:.5f}</code>\n"
                f"   Lots: {t.lot_size}  |  P&L: {pnl_str}\n"
            )
        await self._send_message("\n".join(lines))

    async def _cmd_performance(self) -> None:
        from database.session import get_session
        from database import repository as repo

        session = await get_session()
        try:
            perf = await repo.get_performance_summary(session)
        finally:
            await session.close()

        if perf.get("total_trades", 0) == 0:
            await self._send_message("📭 No closed trades yet.")
            return

        msg = (
            f"📈 <b>PERFORMANCE SUMMARY</b>\n\n"
            f"Total Trades: {perf['total_trades']}\n"
            f"Wins: {perf.get('wins', 0)}  |  Losses: {perf.get('losses', 0)}\n"
            f"Win Rate: {perf.get('win_rate', 0):.1%}\n"
            f"Total P&L: <code>${perf.get('total_pnl', 0):,.2f}</code>\n"
            f"Avg P&L: <code>${perf.get('avg_pnl', 0):,.2f}</code>\n"
            f"Max Drawdown: {perf.get('max_drawdown', 0):.1%}\n"
        )
        await self._send_message(msg)

    async def _cmd_pairs(self) -> None:
        from dashboard.api import get_bot_state

        pairs = get_bot_state().get("active_pairs", [])
        if not pairs:
            await self._send_message("📭 No active pairs configured.")
            return
        numbered = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(pairs))
        msg = f"📈 <b>ACTIVE PAIRS ({len(pairs)})</b>\n\n{numbered}"
        await self._send_message(msg)

    async def _cmd_enablepair(self, args: list | None = None) -> None:
        if not args:
            await self._send_message("⚠️ Usage: /enablepair EURUSD")
            return

        from dashboard.api import get_bot_state, set_bot_state

        pair = args[0].upper()
        active = list(get_bot_state().get("active_pairs", []))
        if pair in active:
            await self._send_message(f"⚠️ {pair} is already active.")
            return

        active.append(pair)
        set_bot_state("active_pairs", active)
        if self._bot_ref:
            self._bot_ref._settings.trading_pairs = ",".join(active)
        logger.info("Pair enabled via Telegram", pair=pair)
        await self._send_message(f"✅ <b>{pair}</b> enabled for trading.")

    async def _cmd_disablepair(self, args: list | None = None) -> None:
        if not args:
            await self._send_message("⚠️ Usage: /disablepair EURUSD")
            return

        from dashboard.api import get_bot_state, set_bot_state

        pair = args[0].upper()
        active = list(get_bot_state().get("active_pairs", []))
        if pair not in active:
            await self._send_message(f"⚠️ {pair} is not in the active list.")
            return

        active.remove(pair)
        set_bot_state("active_pairs", active)
        if self._bot_ref:
            self._bot_ref._settings.trading_pairs = ",".join(active)
        logger.info("Pair disabled via Telegram", pair=pair)
        await self._send_message(f"🚫 <b>{pair}</b> disabled for trading.")

    async def _cmd_risk(self, args: list | None = None) -> None:
        if not args:
            current = self._settings.max_risk_per_trade * 100
            await self._send_message(
                f"⚙️ Current risk per trade: <b>{current:.1f}%</b>\n\n"
                f"Usage: /risk 2.5"
            )
            return

        try:
            pct = float(args[0])
        except ValueError:
            await self._send_message("⚠️ Invalid number. Usage: /risk 2.5")
            return

        if not (0.1 <= pct <= 10.0):
            await self._send_message("⚠️ Risk must be between 0.1% and 10%.")
            return

        new_val = pct / 100.0
        self._settings.max_risk_per_trade = new_val
        if self._bot_ref:
            self._bot_ref.risk_manager.max_risk_per_trade = new_val
        logger.info("Risk updated via Telegram", risk_pct=pct)
        await self._send_message(f"✅ Risk per trade set to <b>{pct:.1f}%</b>")

    async def _cmd_logs(self) -> None:
        from database.session import get_session
        from database import repository as repo

        session = await get_session()
        try:
            logs = await repo.get_recent_logs(session, limit=10)
        finally:
            await session.close()

        if not logs:
            await self._send_message("📭 No system logs yet.")
            return

        lines = ["📋 <b>RECENT LOGS</b>\n"]
        for log in logs:
            ts = log.created_at.strftime("%H:%M:%S") if log.created_at else ""
            level_icon = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(
                log.level, "⚪"
            )
            lines.append(
                f"{level_icon} [{ts}] <b>{log.module}</b>: {log.message}"
            )
        await self._send_message("\n".join(lines))

    async def _cmd_restart(self) -> None:
        if self._bot_ref is None:
            await self._send_message("⚠️ Bot reference not available.")
            return

        await self._send_message("🔄 <b>Restarting trading bot...</b>")
        logger.info("Bot restart requested via Telegram")

        # Stop gracefully — cancel old loop if tracked
        self._bot_ref._running = False
        from dashboard.api import set_bot_state
        set_bot_state("running", False)

        old_loop = getattr(self._bot_ref, "_loop_task", None)
        if old_loop and not old_loop.done():
            old_loop.cancel()
            try:
                await old_loop
            except asyncio.CancelledError:
                pass

        await asyncio.sleep(1)

        await self._bot_ref.start()
        task = asyncio.create_task(self._bot_ref.run_loop(interval_seconds=300))
        self._bot_ref._loop_task = task
        await self._send_message("✅ <b>Bot restarted successfully.</b>")

    async def _cmd_health(self) -> None:
        cpu = await asyncio.to_thread(psutil.cpu_percent, 0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(
            "/" if platform.system() != "Windows" else "C:\\"
        )

        uptime = time.time() - _BOT_START_TIME
        h, rem = divmod(int(uptime), 3600)
        m, s = divmod(rem, 60)

        msg = (
            f"🏥 <b>SYSTEM HEALTH</b>\n\n"
            f"CPU: {cpu:.1f}%\n"
            f"RAM: {mem.percent:.1f}%  "
            f"({mem.used // (1024**2)} / {mem.total // (1024**2)} MB)\n"
            f"Disk: {disk.percent:.1f}%  "
            f"({disk.used // (1024**3)} / {disk.total // (1024**3)} GB)\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Python: {platform.python_version()}\n"
            f"Bot Uptime: {h}h {m}m {s}s\n"
        )
        await self._send_message(msg)

    async def _cmd_help(self) -> None:
        msg = (
            "🤖 <b>TRADING BOT COMMANDS</b>\n\n"
            "<b>Control</b>\n"
            "/startbot — Start trading engine\n"
            "/stopbot — Stop trading engine\n"
            "/restart — Restart the bot\n\n"
            "<b>Monitoring</b>\n"
            "/status — Bot status & uptime\n"
            "/balance — Account balance & equity\n"
            "/positions — Open positions detail\n"
            "/performance — P&L, win rate, drawdown\n"
            "/health — CPU, RAM, disk usage\n"
            "/logs — Recent system logs\n\n"
            "<b>Configuration</b>\n"
            "/pairs — List active trading pairs\n"
            "/enablepair &lt;PAIR&gt; — Enable a pair\n"
            "/disablepair &lt;PAIR&gt; — Disable a pair\n"
            "/risk &lt;%&gt; — Set risk per trade\n\n"
            "<b>News Filter</b>\n"
            "/newsutcon — Enable manual NEWS_EVENTS_UTC source\n"
            "/newsutcoff — Disable manual NEWS_EVENTS_UTC source\n\n"
            "/help — Show this message\n"
        )
        await self._send_message(msg)

    async def _cmd_newsutcon(self) -> None:
        self._settings.enable_news_events_utc = True
        if self._bot_ref and getattr(self._bot_ref, "news_filter", None):
            self._bot_ref.news_filter.reload_events()
            await self._bot_ref.news_filter.refresh_if_needed(force=True)
        logger.info("Manual NEWS_EVENTS_UTC source enabled via Telegram")
        await self._send_message("✅ Manual NEWS_EVENTS_UTC source enabled.")

    async def _cmd_newsutcoff(self) -> None:
        self._settings.enable_news_events_utc = False
        if self._bot_ref and getattr(self._bot_ref, "news_filter", None):
            self._bot_ref.news_filter.reload_events()
            await self._bot_ref.news_filter.refresh_if_needed(force=True)
        logger.info("Manual NEWS_EVENTS_UTC source disabled via Telegram")
        await self._send_message("✅ Manual NEWS_EVENTS_UTC source disabled.")

    # ═══════════════════════════════════════════════════════════════════
    #  NOTIFICATION METHODS (called by the trading engine)
    # ═══════════════════════════════════════════════════════════════════

    async def send_startup_notification(
        self,
        connected: bool,
        account: dict | None = None,
        pairs: list | None = None,
        strategies: int = 0,
    ) -> bool:
        if not self.is_configured:
            return False
        if not connected:
            return await self._send_message(
                "🔴 <b>TRADING BOT FAILED TO START</b>\n\n"
                "MT5 connection failed. Check your MT5 terminal is running "
                "and credentials in .env are correct."
            )
        lines = [
            "🟢 <b>TRADING BOT STARTED</b>\n",
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n",
        ]
        if account:
            lines.append(
                f"💰 Balance: ${account.get('balance', 0):,.2f}  |  "
                f"Equity: ${account.get('equity', 0):,.2f}"
            )
            lines.append(
                f"🏦 Server: {account.get('server', 'N/A')}  |  "
                f"Account: {account.get('login', 'N/A')}"
            )
            lines.append(f"⚙️ Leverage: 1:{account.get('leverage', 0)}")
        if pairs:
            lines.append(f"\n📈 Pairs ({len(pairs)}): {', '.join(pairs)}")
        lines.append(f"🧠 Strategies: {strategies}")
        lines.append("\nType /help for commands.")
        return await self._send_message("\n".join(lines))

    async def send_signal(self, signal: Signal,
                          chart_path: str | None = None) -> bool:
        if not self.is_configured:
            return False
        direction = signal.signal_type.value
        emoji = "🟢" if direction == "BUY" else "🔴"
        regime_emoji = self._regime_emoji(signal.market_regime)
        message = (
            f"{emoji} <b>SIGNAL: {direction} {signal.symbol}</b>\n\n"
            f"📊 Strategy: <b>{signal.strategy}</b>\n"
            f"📈 Regime: {regime_emoji} {signal.market_regime}\n\n"
            f"💰 Entry: <code>{signal.entry_price:.5f}</code>\n"
            f"🛑 Stop Loss: <code>{signal.stop_loss:.5f}</code>\n"
            f"🎯 Take Profit: <code>{signal.take_profit:.5f}</code>\n\n"
            f"⚖️ Risk/Reward: <b>{signal.risk_reward_ratio:.1f}</b>\n"
            f"🔍 Confidence: <b>{signal.confidence:.0%}</b>\n"
            f"⏰ Timeframe: {signal.timeframe}\n"
        )
        if signal.indicators:
            message += "\n📐 <b>Indicators:</b>\n"
            for k, v in signal.indicators.items():
                message += f"  • {k}: {v:.4f}\n"
        if chart_path and Path(chart_path).exists():
            sent = await self._send_photo(chart_path, message)
            try:
                Path(chart_path).unlink(missing_ok=True)
            except OSError:
                pass
            return sent
        return await self._send_message(message)

    async def send_trade_executed(self, trade_info: dict) -> bool:
        if not self.is_configured:
            return False
        message = (
            f"✅ <b>TRADE EXECUTED</b>\n\n"
            f"🏷️ Symbol: {trade_info.get('symbol', 'N/A')}\n"
            f"📝 Trade ID: {trade_info.get('trade_id', 'N/A')}\n"
            f"📦 Lot Size: {trade_info.get('lot_size', 0)}\n"
            f"⚠️ Risk: {trade_info.get('risk_percent', 0):.1f}%\n"
        )
        return await self._send_message(message)

    async def send_trade_failed(self, trade_info: dict) -> bool:
        if not self.is_configured:
            return False
        status = trade_info.get("status", "FAILED")
        reason = trade_info.get("reason", "Order not executed")
        symbol = trade_info.get("symbol", "N/A")
        message = (
            f"⚠️ <b>TRADE NOT EXECUTED</b>\n\n"
            f"🏷️ Symbol: {symbol}\n"
            f"📌 Status: {status}\n"
            f"📝 Reason: {reason}\n"
        )
        return await self._send_message(message)

    async def send_trade_closed(self, trade_info: dict) -> bool:
        if not self.is_configured:
            return False
        pnl = trade_info.get("pnl", 0)
        emoji = "💰" if pnl > 0 else "💸"
        message = (
            f"{emoji} <b>TRADE CLOSED</b>\n\n"
            f"🏷️ Trade ID: {trade_info.get('trade_id', 'N/A')}\n"
            f"📊 Exit Price: {trade_info.get('exit_price', 0):.5f}\n"
            f"💵 P&L: <b>${pnl:.2f}</b>\n"
            f"📏 Pips: {trade_info.get('pnl_pips', 0):.1f}\n"
        )
        return await self._send_message(message)

    async def send_daily_summary(self, summary: dict) -> bool:
        if not self.is_configured:
            return False
        message = (
            f"📋 <b>DAILY SUMMARY</b>\n\n"
            f"📊 Total Trades: {summary.get('total_trades', 0)}\n"
            f"✅ Wins: {summary.get('wins', 0)}\n"
            f"❌ Losses: {summary.get('losses', 0)}\n"
            f"🎯 Win Rate: {summary.get('win_rate', 0):.0%}\n"
            f"💵 Daily P&L: ${summary.get('total_pnl', 0):.2f}\n"
            f"💰 Balance: ${summary.get('balance', 0):.2f}\n"
        )
        return await self._send_message(message)

    async def send_error(self, error_msg: str) -> bool:
        if not self.is_configured:
            return False
        message = f"🚨 <b>SYSTEM ALERT</b>\n\n{error_msg}"
        return await self._send_message(message)

    # ═══════════════════════════════════════════════════════════════════
    #  LOW-LEVEL TRANSPORT (with retry)
    # ═══════════════════════════════════════════════════════════════════

    async def _send_message(self, text: str, retries: int = 2) -> bool:
        if len(text) > 4096:
            text = text[:4090] + "\n…"
        for attempt in range(1, retries + 2):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{self._base_url}/sendMessage",
                        json={
                            "chat_id": self._chat_id,
                            "text": text,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True,
                        },
                    )
                    if resp.status_code == 200:
                        self._validated = True
                        return True
                    if resp.status_code == 401:
                        self._disabled_reason = "invalid bot token (401)"
                        logger.warning("Bot token invalid — disabled")
                        return False
                    logger.error(
                        "Telegram send failed",
                        status=resp.status_code,
                        attempt=attempt,
                    )
            except Exception as e:
                logger.error("Telegram error", error=str(e), attempt=attempt)

            if attempt <= retries:
                await asyncio.sleep(2 * attempt)
        return False

    async def _send_photo(self, photo_path: str, caption: str,
                          retries: int = 2) -> bool:
        for attempt in range(1, retries + 2):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    with open(photo_path, "rb") as f:
                        resp = await client.post(
                            f"{self._base_url}/sendPhoto",
                            data={
                                "chat_id": self._chat_id,
                                "caption": caption[:1024],
                                "parse_mode": "HTML",
                            },
                            files={
                                "photo": ("chart.png", f, "image/png"),
                            },
                        )
                    if resp.status_code == 200:
                        return True
                    logger.error(
                        "Telegram photo failed",
                        status=resp.status_code,
                        attempt=attempt,
                    )
            except Exception as e:
                logger.error(
                    "Telegram photo error", error=str(e), attempt=attempt
                )

            if attempt <= retries:
                await asyncio.sleep(2 * attempt)
        return False

    @staticmethod
    def _regime_emoji(regime: str) -> str:
        mapping = {
            "STRONG_BULLISH": "🚀", "BULLISH": "📈", "SIDEWAYS": "↔️",
            "BEARISH": "📉", "STRONG_BEARISH": "💥",
            "HIGH_VOLATILITY": "⚡", "LOW_VOLATILITY": "😴",
        }
        return mapping.get(regime, "❓")
