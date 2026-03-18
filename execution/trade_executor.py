"""
Trade Execution Engine — places and manages orders via broker API.
"""
from __future__ import annotations

import asyncio
from data.market_data import _mt5_lock
from datetime import datetime
from typing import Optional

from config.constants import OrderType, OrderStatus, PIP_SIZE, PIP_VALUES
from config.settings import get_settings
from database.session import get_session
from database import repository as repo
from strategies.base import Signal
from execution.risk_manager import RiskManager
from utils.logging_config import get_logger

logger = get_logger("trade_executor")


class TradeExecutor:
    """
    Handles trade placement, modification, and closing via broker API.
    """

    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager
        self._settings = get_settings()
        self._mt5_available = False
        self._check_mt5()

    def _check_mt5(self):
        try:
            import MetaTrader5 as mt5
            self._mt5_available = True
        except ImportError:
            self._mt5_available = False

    async def execute_signal(self, signal: Signal,
                             account_balance: float) -> Optional[dict]:
        """
        Execute a trading signal:
        1. Validate risk
        2. Check spread
        3. Place order
        4. Log to database
        """
        # Risk validation
        risk_result = await self.risk_manager.validate_trade(signal, account_balance)
        if not risk_result["approved"]:
            return {"status": "REJECTED", "reason": risk_result["reason"]}

        lot_size = risk_result["lot_size"]

        # Spread filter
        spread = await self._get_current_spread(signal.symbol)
        pip_size = PIP_SIZE.get(signal.symbol, 0.0001)
        max_spread_pips = 3.0
        if spread / pip_size > max_spread_pips:
            reason = f"Spread too wide: {spread/pip_size:.1f} pips"
            logger.warning("Trade rejected - spread", symbol=signal.symbol, reason=reason)
            return {"status": "REJECTED", "reason": reason}

        # Execute on broker
        ticket = await self._place_order(signal, lot_size)
        if ticket is None:
            return {"status": "FAILED", "reason": "Order placement failed"}

        # Save to database
        session = await get_session()
        try:
            trade = await repo.create_trade(
                session,
                symbol=signal.symbol,
                order_type=signal.signal_type.value,
                strategy=signal.strategy,
                status="OPEN",
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                lot_size=lot_size,
                risk_percent=risk_result["risk_percent"],
                signal_confidence=signal.confidence,
                broker_ticket=str(ticket),
                market_regime=signal.market_regime,
            )
            logger.info(
                "Trade executed",
                trade_id=trade.id,
                symbol=signal.symbol,
                type=signal.signal_type.value,
                lot_size=lot_size,
                entry=signal.entry_price,
            )
            return {
                "status": "EXECUTED",
                "trade_id": trade.id,
                "ticket": ticket,
                "lot_size": lot_size,
                "risk_percent": risk_result["risk_percent"],
            }
        finally:
            await session.close()

    async def close_trade(self, trade_id: int,
                          exit_price: float | None = None) -> Optional[dict]:
        """Close an open trade."""
        session = await get_session()
        try:
            from database.models import Trade

            trade = await session.get(Trade, trade_id)
            if not trade or trade.status != "OPEN":
                return {"status": "FAILED", "reason": "Trade not found or not open"}

            # Close on broker
            if trade.broker_ticket and self._mt5_available:
                await self._close_broker_order(trade.broker_ticket, trade.symbol,
                                                trade.order_type, trade.lot_size)

            # Calculate PnL
            if exit_price is None:
                tick = await self._get_tick(trade.symbol)
                exit_price = tick.get("bid" if trade.order_type == "BUY" else "ask",
                                      trade.entry_price)

            pip_size = PIP_SIZE.get(trade.symbol, 0.0001)
            if trade.order_type == "BUY":
                pnl_pips = (exit_price - trade.entry_price) / pip_size
            else:
                pnl_pips = (trade.entry_price - exit_price) / pip_size

            pip_value = PIP_VALUES.get(trade.symbol, 10.0)
            pnl = pnl_pips * pip_value * trade.lot_size

            await repo.update_trade(
                session, trade_id,
                status="CLOSED",
                exit_price=exit_price,
                pnl=round(pnl, 2),
                pnl_pips=round(pnl_pips, 1),
                closed_at=datetime.utcnow(),
            )

            logger.info("Trade closed", trade_id=trade_id, pnl=pnl, pnl_pips=pnl_pips)
            return {
                "status": "CLOSED",
                "trade_id": trade_id,
                "symbol": trade.symbol,
                "exit_price": exit_price,
                "pnl": round(pnl, 2),
                "pnl_pips": round(pnl_pips, 1),
            }
        finally:
            await session.close()

    async def is_position_open(self, broker_ticket: str) -> bool:
        """Check whether a broker position is still open in MT5."""
        if not self._mt5_available or not broker_ticket:
            return False

        import MetaTrader5 as mt5

        try:
            ticket_int = int(broker_ticket)
        except (TypeError, ValueError):
            return False

        async with _mt5_lock:
            positions = await asyncio.to_thread(mt5.positions_get, ticket=ticket_int)
        return positions is not None and len(positions) > 0

    async def _place_order(self, signal: Signal, lot_size: float,
                           retries: int = 3) -> Optional[str]:
        """Place order on broker with retry logic."""
        if not self._mt5_available:
            logger.info("Simulated order placement", symbol=signal.symbol)
            return f"SIM_{signal.symbol}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        import MetaTrader5 as mt5

        order_type = mt5.ORDER_TYPE_BUY if signal.signal_type.value == "BUY" else mt5.ORDER_TYPE_SELL

        filling_modes = await self._get_filling_modes(signal.symbol)

        for attempt in range(retries):
            async with _mt5_lock:
                tick = await asyncio.to_thread(mt5.symbol_info_tick, signal.symbol)
            if tick is None:
                continue

            price = tick.ask if signal.signal_type.value == "BUY" else tick.bid

            for fill_mode in filling_modes:
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": signal.symbol,
                    "volume": lot_size,
                    "type": order_type,
                    "price": price,
                    "sl": signal.stop_loss,
                    "tp": signal.take_profit,
                    "deviation": 20,
                    "magic": 234000,
                    "comment": f"FX_{signal.strategy}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": fill_mode,
                }

                async with _mt5_lock:
                    result = await asyncio.to_thread(mt5.order_send, request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return str(result.order)

                logger.warning(
                    "Order attempt failed",
                    attempt=attempt + 1,
                    fill_mode=self._fill_mode_name(fill_mode),
                    error=result.comment if result else "No response",
                )

            await asyncio.sleep(1)

        return None

    async def _close_broker_order(self, ticket: str, symbol: str,
                                   order_type: str, lot_size: float) -> bool:
        """Close position on MT5."""
        if not self._mt5_available:
            return True

        import MetaTrader5 as mt5

        close_type = mt5.ORDER_TYPE_SELL if order_type == "BUY" else mt5.ORDER_TYPE_BUY
        async with _mt5_lock:
            tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
        if tick is None:
            return False

        price = tick.bid if order_type == "BUY" else tick.ask

        filling_modes = await self._get_filling_modes(symbol)

        for fill_mode in filling_modes:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot_size,
                "type": close_type,
                "position": int(ticket),
                "price": price,
                "deviation": 20,
                "magic": 234000,
                "comment": "FX_close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": fill_mode,
            }

            async with _mt5_lock:
                result = await asyncio.to_thread(mt5.order_send, request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return True

            logger.warning(
                "Close order attempt failed",
                symbol=symbol,
                fill_mode=self._fill_mode_name(fill_mode),
                error=result.comment if result else "No response",
            )

        return False

    async def _get_filling_modes(self, symbol: str) -> list[int]:
        """Return best-effort filling-mode order for a symbol.

        Some brokers reject IOC/FOK/RETURN depending on symbol execution mode.
        We derive supported modes from symbol_info where available, then fall back.
        """
        import MetaTrader5 as mt5

        preferred = [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]

        async with _mt5_lock:
            info = await asyncio.to_thread(mt5.symbol_info, symbol)
        if info is None:
            return preferred

        raw_mode = getattr(info, "filling_mode", None)
        if raw_mode is None:
            return preferred

        # Some terminals expose one mode; others expose a bitmask.
        supported: list[int] = []
        if raw_mode in preferred:
            supported.append(raw_mode)
        else:
            bit_to_mode = [
                (getattr(mt5, "SYMBOL_FILLING_FOK", 1), mt5.ORDER_FILLING_FOK),
                (getattr(mt5, "SYMBOL_FILLING_IOC", 2), mt5.ORDER_FILLING_IOC),
                (getattr(mt5, "SYMBOL_FILLING_RETURN", 4), mt5.ORDER_FILLING_RETURN),
            ]
            for bit, mode in bit_to_mode:
                try:
                    if int(raw_mode) & int(bit):
                        supported.append(mode)
                except Exception:
                    continue

        if not supported:
            supported = preferred[:]

        # Always include all fallback modes because some brokers report one mode
        # but reject it at order_send time depending on execution context.
        for mode in preferred:
            if mode not in supported:
                supported.append(mode)

        # Keep deterministic order and avoid duplicates.
        ordered: list[int] = []
        for mode in preferred:
            if mode in supported and mode not in ordered:
                ordered.append(mode)
        for mode in supported:
            if mode not in ordered:
                ordered.append(mode)
        return ordered

    @staticmethod
    def _fill_mode_name(fill_mode: int) -> str:
        try:
            import MetaTrader5 as mt5
            if fill_mode == mt5.ORDER_FILLING_RETURN:
                return "RETURN"
            if fill_mode == mt5.ORDER_FILLING_IOC:
                return "IOC"
            if fill_mode == mt5.ORDER_FILLING_FOK:
                return "FOK"
        except Exception:
            pass
        return str(fill_mode)

    async def _get_current_spread(self, symbol: str) -> float:
        tick = await self._get_tick(symbol)
        if not tick or (tick.get("bid", 0) == 0 and tick.get("ask", 0) == 0):
            return float("inf")  # No valid tick → block trading
        return tick.get("ask", 0) - tick.get("bid", 0)

    async def _get_tick(self, symbol: str) -> dict:
        if not self._mt5_available:
            return {}  # No simulated data — caller must handle empty dict

        import MetaTrader5 as mt5
        tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
        if tick is None:
            return {}
        return {"bid": tick.bid, "ask": tick.ask, "time": tick.time}
