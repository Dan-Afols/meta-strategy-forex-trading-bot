"""
Forex Trading System - Global Configuration
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Application
    app_name: str = "ForexTradingSystem"
    app_env: str = "production"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'trading.db'}"

    # MetaTrader 5
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""
    mt5_path: str = ""
    mt5_timeout: int = 10000

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_enabled: bool = True

    # Trading
    trading_pairs: str = "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP"
    default_timeframe: str = "H1"
    max_open_trades: int = 5
    max_risk_per_trade: float = 0.02
    max_daily_loss: float = 0.05
    account_currency: str = "USD"

    # News filter (manual calendar in UTC)
    enable_news_filter: bool = True
    enable_news_events_utc: bool = True
    news_events_utc: str = ""
    news_block_minutes_before: int = 45
    news_block_minutes_after: int = 30
    enable_news_auto_update: bool = True
    news_events_url: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    news_auto_refresh_minutes: int = 360

    # Multi-timeframe confirmation
    enable_mtf_confirmation: bool = True
    mtf_confirmation_timeframe: str = "H4"
    mtf_confirmation_ma_period: int = 50
    mtf_confirmation_strict: bool = False

    # Automatic strategy evolution
    enable_strategy_evolution: bool = True
    strategy_evolution_interval_cycles: int = 12
    strategy_evolution_min_trades: int = 8

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    secret_key: str = "change-this-to-a-random-secret-key"
    access_token_expire_minutes: int = 1440
    dashboard_username: str = "admin"
    dashboard_password: str = "change-this-password"

    # Directories
    data_dir: str = str(BASE_DIR / "data")
    chart_dir: str = str(BASE_DIR / "data" / "charts")
    log_dir: str = str(BASE_DIR / "logs")
    ml_model_dir: str = str(BASE_DIR / "ml_models" / "saved")

    # Backtesting
    backtest_start_date: str = "2024-01-01"
    backtest_end_date: str = "2025-12-31"

    @property
    def pairs_list(self) -> List[str]:
        return [p.strip() for p in self.trading_pairs.split(",") if p.strip()]

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


_settings_instance: Settings | None = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def ensure_directories(settings: Settings) -> None:
    """Create required directories if they don't exist."""
    for d in [settings.data_dir, settings.chart_dir, settings.log_dir, settings.ml_model_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)
