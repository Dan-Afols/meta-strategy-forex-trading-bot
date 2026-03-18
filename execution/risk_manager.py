"""
Risk Management Engine — enforces all risk rules before trade execution.
"""
from __future__ import annotations

from typing import Optional

from config.settings import get_settings
from config.constants import PIP_SIZE, PIP_VALUES
from database.session import get_session
from database import repository as repo
from strategies.base import Signal
from utils.logging_config import get_logger

logger = get_logger("risk_manager")


class RiskManager:
    """Enforces risk rules and calculates position sizing."""

    def __init__(self):
        self._settings = get_settings()
        self.max_risk_per_trade = self._settings.max_risk_per_trade
        self.max_daily_loss = self._settings.max_daily_loss
        self.max_open_trades = self._settings.max_open_trades

    async def validate_trade(self, signal: Signal,
                             account_balance: float) -> dict:
        """
        Validate whether a trade should be executed based on risk rules.
        Returns dict with 'approved', 'reason', and 'lot_size'.
        """
        session = await get_session()
        try:
            # Check max open trades
            open_count = await repo.count_open_trades(session)
            if open_count >= self.max_open_trades:
                return self._reject(f"Max open trades ({self.max_open_trades}) reached")

            # Check daily loss limit
            daily_pnl = await repo.get_daily_pnl(session)
            max_loss_amount = account_balance * self.max_daily_loss
            if daily_pnl < 0 and abs(daily_pnl) >= max_loss_amount:
                return self._reject(
                    f"Daily loss limit reached: ${abs(daily_pnl):.2f} >= ${max_loss_amount:.2f}"
                )

            # Calculate position size
            risk_amount = account_balance * self.max_risk_per_trade
            sl_distance = abs(signal.entry_price - signal.stop_loss)

            if sl_distance <= 0:
                return self._reject("Invalid stop loss distance")

            pip_size = PIP_SIZE.get(signal.symbol, 0.0001)
            sl_pips = sl_distance / pip_size

            # Position size in lots (standard lot = 100k units)
            # Risk = lots * pip_value * sl_pips
            pip_value = PIP_VALUES.get(signal.symbol, 10.0)
            if sl_pips <= 0:
                return self._reject("Invalid stop loss pips")

            lot_size = risk_amount / (sl_pips * pip_value)
            lot_size = max(0.01, round(lot_size, 2))  # Minimum 0.01 lot
            lot_size = min(lot_size, 10.0)  # Maximum 10 lots safety cap

            # Risk-reward check
            if signal.risk_reward_ratio < 1.0:
                return self._reject(
                    f"Risk-reward ratio too low: {signal.risk_reward_ratio:.2f}"
                )

            # Minimum confidence check
            if signal.confidence < 0.45:
                return self._reject(
                    f"Signal confidence too low: {signal.confidence:.2f}"
                )

            actual_risk = (lot_size * sl_pips * pip_value) / account_balance
            logger.info(
                "Trade approved",
                symbol=signal.symbol,
                lot_size=lot_size,
                risk_percent=round(actual_risk * 100, 2),
                rr_ratio=signal.risk_reward_ratio,
            )

            return {
                "approved": True,
                "lot_size": lot_size,
                "risk_amount": round(risk_amount, 2),
                "risk_percent": round(actual_risk * 100, 2),
                "sl_pips": round(sl_pips, 1),
                "reason": "All risk checks passed",
            }

        finally:
            await session.close()

    def calculate_position_size(self, account_balance: float,
                                entry_price: float, stop_loss: float,
                                symbol: str) -> float:
        """Calculate lot size based on risk per trade."""
        risk_amount = account_balance * self.max_risk_per_trade
        sl_distance = abs(entry_price - stop_loss)
        pip_size = PIP_SIZE.get(symbol, 0.0001)
        sl_pips = sl_distance / pip_size

        if sl_pips <= 0:
            return 0.01

        pip_value = PIP_VALUES.get(symbol, 10.0)
        lot_size = risk_amount / (sl_pips * pip_value)
        return max(0.01, min(round(lot_size, 2), 10.0))

    def adjust_sl_tp(self, signal: Signal) -> Signal:
        """Adjust SL/TP to ensure minimum risk-reward ratio."""
        if signal.risk_reward_ratio < 1.5:
            sl_dist = abs(signal.entry_price - signal.stop_loss)
            if signal.signal_type.value == "BUY":
                signal.take_profit = signal.entry_price + 1.5 * sl_dist
            else:
                signal.take_profit = signal.entry_price - 1.5 * sl_dist
        return signal

    @staticmethod
    def _reject(reason: str) -> dict:
        logger.warning("Trade rejected", reason=reason)
        return {"approved": False, "lot_size": 0, "reason": reason}
