"""
Advanced Chart Snapshot Generator.

Produces high-quality trading chart images with:
  - 150 candlesticks for broad context
  - EMA 20/50, Bollinger Bands, ATR volatility bands
  - RSI sub-panel with overbought/oversold shading
  - MACD sub-panel with histogram
  - Shaded risk/reward zones (entry→SL red, entry→TP green)
  - Entry / SL / TP level lines with labels
  - Overlay information box (pair, timeframe, strategy, confidence, risk%, timestamp)
  - Dark theme, 150 DPI, optimised for Telegram display
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config.settings import get_settings
from strategies.base import Signal
from utils.indicators import ema, bollinger_bands, rsi, macd, atr
from utils.logging_config import get_logger

logger = get_logger("chart_generator")

_CANDLES = 150
_DPI = 150
_BG = "#1a1a2e"
_PANEL = "#16213e"
_GREEN = "#00ff88"
_RED = "#ff4444"
_BLUE = "#00aaff"
_ORANGE = "#ffaa00"
_GREY = "#888888"


class ChartGenerator:
    """Generates professional chart snapshots for trade signals."""

    def __init__(self):
        self._settings = get_settings()
        self._chart_dir = Path(self._settings.chart_dir)
        self._chart_dir.mkdir(parents=True, exist_ok=True)
        plt.style.use("dark_background")

    def generate_signal_chart(
        self,
        df: pd.DataFrame,
        signal: Signal,
        filename: str | None = None,
        risk_pct: float | None = None,
    ) -> str:
        """Generate chart image. Returns filesystem path."""
        plot_df = df.tail(_CANDLES).copy()
        if "timestamp" in plot_df.columns:
            plot_df = plot_df.set_index("timestamp")
        plot_df.index = pd.to_datetime(plot_df.index)

        fig, axes = plt.subplots(
            3, 1, figsize=(14, 10),
            gridspec_kw={"height_ratios": [3, 1, 1]},
            sharex=True,
        )
        fig.patch.set_facecolor(_BG)
        for ax in axes:
            ax.set_facecolor(_PANEL)

        self._draw_candlesticks(axes[0], plot_df)
        self._draw_indicators(axes[0], plot_df)
        self._draw_atr_bands(axes[0], plot_df)
        self._draw_risk_reward_zones(axes[0], plot_df, signal)
        self._draw_trade_levels(axes[0], plot_df, signal)
        self._draw_overlay(axes[0], plot_df, signal, risk_pct)
        self._draw_rsi(axes[1], plot_df)
        self._draw_macd(axes[2], plot_df)

        # Title
        direction = signal.signal_type.value
        color = _GREEN if direction == "BUY" else _RED
        axes[0].set_title(
            f"{signal.symbol}  |  {direction}  |  {signal.strategy}  |  "
            f"Confidence: {signal.confidence:.0%}  |  RR: {signal.risk_reward_ratio:.1f}",
            fontsize=13, fontweight="bold", color=color, pad=10,
        )

        axes[2].set_xlabel("Time", fontsize=10)
        axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        plt.setp(axes[2].xaxis.get_majorticklabels(), rotation=30, ha="right")

        fig.tight_layout()

        if filename is None:
            ts = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{signal.symbol}_{signal.strategy}_{ts}.png"

        filepath = self._chart_dir / filename
        fig.savefig(filepath, dpi=_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)

        logger.info("Chart generated", path=str(filepath))
        return str(filepath)

    # ─── Candlesticks ────────────────────────────────────────────

    def _draw_candlesticks(self, ax, df: pd.DataFrame) -> None:
        up = df[df["close"] >= df["open"]]
        down = df[df["close"] < df["open"]]

        span = (df.index[-1] - df.index[0]).total_seconds()
        width = max(span / len(df) / 86400 * 0.6, 0.002)

        ax.bar(up.index, up["close"] - up["open"], width,
               bottom=up["open"], color=_GREEN, alpha=0.9,
               edgecolor=_GREEN, linewidth=0.5)
        ax.vlines(up.index, up["low"], up["high"], color=_GREEN, linewidth=0.7)

        ax.bar(down.index, down["close"] - down["open"], width,
               bottom=down["open"], color=_RED, alpha=0.9,
               edgecolor=_RED, linewidth=0.5)
        ax.vlines(down.index, down["low"], down["high"], color=_RED, linewidth=0.7)

        ax.set_ylabel("Price", fontsize=10)
        ax.grid(True, alpha=0.15)

    # ─── Indicators (EMAs + Bollinger) ───────────────────────────

    def _draw_indicators(self, ax, df: pd.DataFrame) -> None:
        close = df["close"]
        ema20 = ema(close, 20)
        ema50 = ema(close, 50)
        ax.plot(df.index, ema20, color=_ORANGE, linewidth=1.2,
                label="EMA 20", alpha=0.8)
        ax.plot(df.index, ema50, color=_BLUE, linewidth=1.2,
                label="EMA 50", alpha=0.8)

        bb_upper, _, bb_lower = bollinger_bands(close, 20, 2.0)
        ax.fill_between(df.index, bb_upper, bb_lower, color="#ffffff",
                        alpha=0.04, label="BB 20")
        ax.plot(df.index, bb_upper, color=_GREY, linewidth=0.5,
                linestyle="--", alpha=0.5)
        ax.plot(df.index, bb_lower, color=_GREY, linewidth=0.5,
                linestyle="--", alpha=0.5)

        ax.legend(loc="upper left", fontsize=7, framealpha=0.3)

    # ─── ATR volatility bands ────────────────────────────────────

    def _draw_atr_bands(self, ax, df: pd.DataFrame) -> None:
        if not {"high", "low", "close"}.issubset(df.columns):
            return
        atr_val = atr(df["high"], df["low"], df["close"], 14)
        mid = df["close"]
        upper = mid + atr_val
        lower = mid - atr_val
        ax.plot(df.index, upper, color="#ff66ff", linewidth=0.6,
                linestyle=":", alpha=0.45, label="ATR band")
        ax.plot(df.index, lower, color="#ff66ff", linewidth=0.6,
                linestyle=":", alpha=0.45)
        ax.fill_between(df.index, upper, lower, color="#ff66ff", alpha=0.03)

    # ─── Risk / Reward shaded zones ─────────────────────────────

    def _draw_risk_reward_zones(self, ax, df: pd.DataFrame,
                                signal: Signal) -> None:
        entry = signal.entry_price
        sl = signal.stop_loss
        tp = signal.take_profit

        # Risk zone: entry → SL (red)
        ax.axhspan(min(entry, sl), max(entry, sl),
                   color=_RED, alpha=0.08, zorder=0)
        # Reward zone: entry → TP (green)
        ax.axhspan(min(entry, tp), max(entry, tp),
                   color=_GREEN, alpha=0.08, zorder=0)

    # ─── Trade levels ────────────────────────────────────────────

    def _draw_trade_levels(self, ax, df: pd.DataFrame,
                           signal: Signal) -> None:
        xmax = df.index[-1]

        ax.axhline(y=signal.entry_price, color="#ffffff", linewidth=1.5,
                   linestyle="-", alpha=0.8)
        ax.text(xmax, signal.entry_price,
                f"  Entry: {signal.entry_price:.5f}",
                fontsize=8, color="#ffffff", va="center", fontweight="bold")

        ax.axhline(y=signal.stop_loss, color=_RED, linewidth=1.5,
                   linestyle="--", alpha=0.8)
        ax.text(xmax, signal.stop_loss,
                f"  SL: {signal.stop_loss:.5f}",
                fontsize=8, color=_RED, va="center")

        ax.axhline(y=signal.take_profit, color=_GREEN, linewidth=1.5,
                   linestyle="--", alpha=0.8)
        ax.text(xmax, signal.take_profit,
                f"  TP: {signal.take_profit:.5f}",
                fontsize=8, color=_GREEN, va="center")

        arrow_color = _GREEN if signal.signal_type.value == "BUY" else _RED
        marker = "^" if signal.signal_type.value == "BUY" else "v"
        ax.scatter([df.index[-1]], [signal.entry_price], color=arrow_color,
                   marker=marker, s=200, zorder=5)

    # ─── Overlay info box ────────────────────────────────────────

    def _draw_overlay(self, ax, df: pd.DataFrame, signal: Signal,
                      risk_pct: float | None) -> None:
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        risk_str = f"{risk_pct:.1f}%" if risk_pct else "—"
        text = (
            f"Pair: {signal.symbol}\n"
            f"TF: {signal.timeframe}\n"
            f"Strategy: {signal.strategy}\n"
            f"Confidence: {signal.confidence:.0%}\n"
            f"Risk: {risk_str}\n"
            f"{now_str}"
        )
        props = dict(boxstyle="round,pad=0.5", facecolor="#000000",
                     alpha=0.55, edgecolor="#555555")
        ax.text(
            0.01, 0.97, text, transform=ax.transAxes, fontsize=7,
            verticalalignment="top", fontfamily="monospace",
            color="#cccccc", bbox=props,
        )

    # ─── RSI ─────────────────────────────────────────────────────

    def _draw_rsi(self, ax, df: pd.DataFrame) -> None:
        rsi_val = rsi(df["close"], 14)
        ax.plot(df.index, rsi_val, color=_ORANGE, linewidth=1.2)
        ax.axhline(y=70, color=_RED, linewidth=0.7, linestyle="--", alpha=0.5)
        ax.axhline(y=30, color=_GREEN, linewidth=0.7, linestyle="--", alpha=0.5)
        ax.axhline(y=50, color=_GREY, linewidth=0.5, linestyle=":", alpha=0.3)
        ax.fill_between(df.index, 70, rsi_val, where=rsi_val >= 70,
                        color=_RED, alpha=0.15)
        ax.fill_between(df.index, 30, rsi_val, where=rsi_val <= 30,
                        color=_GREEN, alpha=0.15)
        ax.set_ylabel("RSI", fontsize=9)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.15)

    # ─── MACD ────────────────────────────────────────────────────

    def _draw_macd(self, ax, df: pd.DataFrame) -> None:
        macd_line, signal_line, histogram = macd(df["close"])
        ax.plot(df.index, macd_line, color=_BLUE, linewidth=1.0, label="MACD")
        ax.plot(df.index, signal_line, color=_ORANGE, linewidth=1.0, label="Signal")

        pos_hist = histogram.where(histogram >= 0)
        neg_hist = histogram.where(histogram < 0)
        ax.bar(df.index, pos_hist, color=_GREEN, alpha=0.5, width=0.01)
        ax.bar(df.index, neg_hist, color=_RED, alpha=0.5, width=0.01)

        ax.axhline(y=0, color=_GREY, linewidth=0.5, alpha=0.3)
        ax.set_ylabel("MACD", fontsize=9)
        ax.legend(loc="upper left", fontsize=7, framealpha=0.3)
        ax.grid(True, alpha=0.15)
