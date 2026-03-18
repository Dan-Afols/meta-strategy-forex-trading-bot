"""
Constants used across the trading system.
"""
from enum import Enum


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class MarketRegime(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    SIDEWAYS = "SIDEWAYS"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


class StrategyType(str, Enum):
    TREND_FOLLOWING = "TREND_FOLLOWING"
    MEAN_REVERSION = "MEAN_REVERSION"
    BREAKOUT = "BREAKOUT"
    VOLATILITY = "VOLATILITY"
    ML_BASED = "ML_BASED"


# Pip values for major pairs (per standard lot)
PIP_VALUES = {
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    "USDCAD": 10.0,
    "USDCHF": 10.0,
    "USDJPY": 1000.0 / 100.0,
    "EURGBP": 10.0,
    "EURJPY": 1000.0 / 100.0,
    "GBPJPY": 1000.0 / 100.0,
}

# Pip size (point value per pip)
PIP_SIZE = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "AUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCAD": 0.0001,
    "USDCHF": 0.0001,
    "USDJPY": 0.01,
    "EURGBP": 0.0001,
    "EURJPY": 0.01,
    "GBPJPY": 0.01,
}

# Default strategy parameters
DEFAULT_STRATEGY_PARAMS = {
    "TREND_FOLLOWING": {
        "fast_ma_period": 20,
        "slow_ma_period": 50,
        "signal_ma_period": 9,
        "adx_period": 14,
        "adx_threshold": 25,
    },
    "MEAN_REVERSION": {
        "rsi_period": 14,
        "rsi_overbought": 70,
        "rsi_oversold": 30,
        "bb_period": 20,
        "bb_std": 2.0,
    },
    "BREAKOUT": {
        "lookback_period": 20,
        "breakout_threshold": 1.5,
        "volume_multiplier": 1.5,
        "atr_period": 14,
    },
    "VOLATILITY": {
        "atr_period": 14,
        "volatility_lookback": 30,
        "high_vol_threshold": 1.5,
        "low_vol_threshold": 0.5,
    },
    "SESSION_ORB": {
        "london_open_hour_utc": 8,
        "newyork_open_hour_utc": 13,
        "open_range_minutes": 45,
        "max_trade_minutes_after_open": 180,
        "atr_period": 14,
        "min_range_atr": 0.35,
        "max_range_atr": 1.90,
        "breakout_buffer_atr": 0.15,
        "stop_buffer_atr": 0.15,
        "rr_ratio": 2.00,
        "allowed_timeframes": "M5,M15,M30",
        "allowed_symbols": "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY",
    },
    "LIQUIDITY_SWEEP_REVERSAL": {
        "lookback_levels": 24,
        "atr_period": 14,
        "rsi_period": 14,
        "rsi_sell_min": 60,
        "rsi_buy_max": 40,
        "sweep_atr_buffer": 0.08,
        "stop_atr_buffer": 0.12,
        "min_wick_body_ratio": 1.50,
        "volume_multiplier": 1.20,
        "rr_ratio": 2.20,
        "allowed_timeframes": "M5,M15,M30,H1",
        "allowed_symbols": "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY",
    },
}
