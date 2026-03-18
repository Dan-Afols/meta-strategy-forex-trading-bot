"""
System Health Check — verifies that every component of the trading system
is correctly wired, importable, and configured.

Run:  python test_system.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path

# Ensure project root is on the path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = ""):
    tag = PASS if passed else FAIL
    results.append((name, passed, detail))
    print(f"  {tag}  {name}" + (f"  ({detail})" if detail else ""))


def section(title: str):
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


# ════════════════════════════════════════════════════════════════════════
# 1. File Structure
# ════════════════════════════════════════════════════════════════════════

def test_file_structure():
    section("1. FILE STRUCTURE")
    required = [
        "main.py",
        ".env",
        "config/settings.py",
        "config/constants.py",
        "data/market_data.py",
        "data/session_detector.py",
        "strategies/base.py",
        "strategies/engine.py",
        "strategies/trend_following.py",
        "strategies/mean_reversion.py",
        "strategies/breakout.py",
        "strategies/volatility.py",
        "strategies/meta_strategy.py",
        "strategies/regime_detector.py",
        "strategies/performance_tracker.py",
        "ml_models/engine.py",
        "execution/risk_manager.py",
        "execution/trade_executor.py",
        "database/models.py",
        "database/session.py",
        "database/repository.py",
        "notifications/telegram_bot.py",
        "charts/generator.py",
        "dashboard/api.py",
        "dashboard/auth.py",
        "dashboard/schemas.py",
        "utils/logging_config.py",
        "utils/indicators.py",
        "dashboard/frontend/package.json",
        "dashboard/frontend/src/app/page.tsx",
        "dashboard/frontend/src/lib/api.ts",
    ]
    for f in required:
        check(f"File exists: {f}", (ROOT / f).exists())


# ════════════════════════════════════════════════════════════════════════
# 2. Imports
# ════════════════════════════════════════════════════════════════════════

def test_imports():
    section("2. MODULE IMPORTS")
    modules = [
        "config.settings",
        "config.constants",
        "data.market_data",
        "data.session_detector",
        "strategies.base",
        "strategies.engine",
        "strategies.trend_following",
        "strategies.mean_reversion",
        "strategies.breakout",
        "strategies.volatility",
        "strategies.meta_strategy",
        "strategies.regime_detector",
        "strategies.performance_tracker",
        "ml_models.engine",
        "execution.risk_manager",
        "execution.trade_executor",
        "database.models",
        "database.session",
        "database.repository",
        "notifications.telegram_bot",
        "charts.generator",
        "dashboard.api",
        "dashboard.auth",
        "dashboard.schemas",
        "utils.logging_config",
        "utils.indicators",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
            check(f"Import: {mod}", True)
        except Exception as e:
            check(f"Import: {mod}", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 3. Configuration / .env
# ════════════════════════════════════════════════════════════════════════

def test_configuration():
    section("3. CONFIGURATION (.env)")
    try:
        from config.settings import get_settings
        s = get_settings()
        check("Settings loaded", True)

        check("MT5 login configured", s.mt5_login != 0, f"login={s.mt5_login}")
        check("MT5 server configured", len(s.mt5_server) > 0, s.mt5_server)
        check("MT5 password set", len(s.mt5_password) > 0)
        check("MT5 path set", len(s.mt5_path) > 0, s.mt5_path)
        check("Telegram token set", len(s.telegram_bot_token) > 5)
        check("Telegram chat_id set", len(s.telegram_chat_id) > 0)
        check("Dashboard username set", len(s.dashboard_username) > 0)
        check("Dashboard password set", len(s.dashboard_password) > 0)
        check("Secret key set", s.secret_key != "change-this-to-a-random-secret-key")
        check("Trading pairs configured", len(s.pairs_list) > 0,
              f"{len(s.pairs_list)} pairs")
    except Exception as e:
        check("Settings loaded", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 4. Database
# ════════════════════════════════════════════════════════════════════════

def test_database():
    section("4. DATABASE")
    try:
        from database.models import Trade, MarketData, StrategyResult
        from database.models import PerformanceMetric, MLModelRecord
        from database.models import SystemLog, AccountSnapshot
        check("All 7 ORM models importable", True)
    except Exception as e:
        check("All 7 ORM models importable", False, str(e)[:80])

    try:
        from database.session import init_db, close_db
        check("init_db / close_db importable", True)
    except Exception as e:
        check("init_db / close_db importable", False, str(e)[:80])

    try:
        from database import repository as repo
        funcs = [
            "create_trade", "get_open_trades", "get_trade_history",
            "store_candles", "save_account_snapshot",
            "get_latest_snapshot", "count_open_trades", "get_daily_pnl",
            "get_performance_summary", "get_recent_logs",
        ]
        missing = [f for f in funcs if not hasattr(repo, f)]
        check("Repository functions present", len(missing) == 0,
              f"missing: {missing}" if missing else f"{len(funcs)} functions OK")
    except Exception as e:
        check("Repository functions importable", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 5. MT5 Data Provider
# ════════════════════════════════════════════════════════════════════════

def test_mt5_provider():
    section("5. MT5 DATA PROVIDER")
    try:
        from data.market_data import MT5DataProvider, MarketDataEngine
        check("MT5DataProvider importable", True)
        check("MarketDataEngine importable", True)

        # Check SimulatedDataProvider is NOT present
        from data import market_data as mdmod
        has_simulated = hasattr(mdmod, "SimulatedDataProvider")
        check("SimulatedDataProvider removed", not has_simulated)

        provider = MT5DataProvider()
        check("MT5DataProvider instantiates", True)
        check("has connect()", hasattr(provider, "connect"))
        check("has get_candles()", hasattr(provider, "get_candles"))
        check("has get_account_info()", hasattr(provider, "get_account_info"))
        check("has connected property", hasattr(type(provider), "connected"))
    except Exception as e:
        check("MT5DataProvider", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 6. Strategies
# ════════════════════════════════════════════════════════════════════════

def test_strategies():
    section("6. STRATEGIES")
    try:
        from strategies.engine import StrategyEngine
        engine = StrategyEngine(use_meta_strategy=True, lookback_days=30)
        count = len(engine.strategies)
        check("StrategyEngine creates", True, f"{count} strategies loaded")
        check("At least 2 strategies", count >= 2)
    except Exception as e:
        check("StrategyEngine creates", False, str(e)[:80])

    try:
        from strategies.base import Signal
        from config.constants import OrderType
        check("Signal dataclass importable", True)
    except Exception as e:
        check("Signal dataclass", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 7. Telegram Bot
# ════════════════════════════════════════════════════════════════════════

def test_telegram():
    section("7. TELEGRAM NOTIFIER")
    try:
        from notifications.telegram_bot import TelegramNotifier
        notifier = TelegramNotifier()
        check("TelegramNotifier instantiates", True)
        check("is_configured property", hasattr(notifier, "is_configured"))

        methods = [
            "send_signal", "send_trade_executed", "send_trade_closed",
            "send_daily_summary", "send_error", "send_startup_notification",
            "start_command_listener", "stop_command_listener",
            "set_bot_reference",
        ]
        missing = [m for m in methods if not hasattr(notifier, m)]
        check("All notification methods present", len(missing) == 0,
              f"missing: {missing}" if missing else f"{len(methods)} methods OK")
    except Exception as e:
        check("TelegramNotifier", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 8. Dashboard API
# ════════════════════════════════════════════════════════════════════════

def test_dashboard_api():
    section("8. DASHBOARD API")
    try:
        from dashboard.api import router, set_bot_state, get_bot_state
        check("API router importable", True)
        check("set_bot_state importable", True)
        check("get_bot_state importable", True)

        # Check that expected routes exist
        route_paths = [r.path for r in router.routes if hasattr(r, "path")]
        expected = [
            "/api/auth/login", "/api/trades", "/api/positions",
            "/api/performance", "/api/balance", "/api/account/live",
            "/api/strategies", "/api/logs", "/api/status",
            "/api/control", "/api/meta/decisions",
        ]
        for ep in expected:
            check(f"Route {ep}", ep in route_paths)
    except Exception as e:
        check("Dashboard API", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 9. Dashboard Schemas
# ════════════════════════════════════════════════════════════════════════

def test_schemas():
    section("9. PYDANTIC SCHEMAS")
    try:
        from dashboard.schemas import (
            AccountInfo, TokenResponse, TradeResponse, PerformanceSummary,
            SystemStatus, LogEntry, BotControlRequest, MetaDecisionResponse,
            StrategyPerformanceResponse, SessionInfoResponse,
        )
        check("All schema models importable", True)

        # Verify AccountInfo has required fields
        ai = AccountInfo(balance=1000, equity=1000)
        check("AccountInfo constructs", True)
    except Exception as e:
        check("Schema models", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 10. ML Engine
# ════════════════════════════════════════════════════════════════════════

def test_ml_engine():
    section("10. ML ENGINE")
    try:
        from ml_models.engine import MLEngine
        engine = MLEngine()
        check("MLEngine instantiates", True)
        check("has filter_signal()", hasattr(engine, "filter_signal"))
    except Exception as e:
        check("MLEngine", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 11. Risk Manager + Trade Executor
# ════════════════════════════════════════════════════════════════════════

def test_execution():
    section("11. RISK MANAGER & TRADE EXECUTOR")
    try:
        from execution.risk_manager import RiskManager
        rm = RiskManager()
        check("RiskManager instantiates", True)
        check("has validate_trade()", hasattr(rm, "validate_trade"))
        check("has calculate_position_size()", hasattr(rm, "calculate_position_size"))
    except Exception as e:
        check("RiskManager", False, str(e)[:80])

    try:
        from execution.trade_executor import TradeExecutor
        from execution.risk_manager import RiskManager
        te = TradeExecutor(RiskManager())
        check("TradeExecutor instantiates", True)
        check("has execute_signal()", hasattr(te, "execute_signal"))
    except Exception as e:
        check("TradeExecutor", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 12. Chart Generator
# ════════════════════════════════════════════════════════════════════════

def test_charts():
    section("12. CHART GENERATOR")
    try:
        from charts.generator import ChartGenerator
        cg = ChartGenerator()
        check("ChartGenerator instantiates", True)
        check("has generate_signal_chart()", hasattr(cg, "generate_signal_chart"))
    except Exception as e:
        check("ChartGenerator", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 13. Main Entry Point
# ════════════════════════════════════════════════════════════════════════

def test_main_module():
    section("13. MAIN MODULE")
    try:
        from main import TradingBot, app
        check("TradingBot class importable", True)
        check("FastAPI app importable", True)

        bot = TradingBot()
        check("TradingBot instantiates", True)
        check("has start()", hasattr(bot, "start"))
        check("has stop()", hasattr(bot, "stop"))
        check("has run_cycle()", hasattr(bot, "run_cycle"))
        check("data_engine is MarketDataEngine",
              type(bot.data_engine).__name__ == "MarketDataEngine")
    except Exception as e:
        check("Main module", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# 14. Frontend Files
# ════════════════════════════════════════════════════════════════════════

def test_frontend():
    section("14. FRONTEND")
    fe = ROOT / "dashboard" / "frontend"
    check("package.json exists", (fe / "package.json").exists())
    check("node_modules exists", (fe / "node_modules").is_dir())
    check("next.config.js exists", (fe / "next.config.js").exists())
    check("page.tsx exists", (fe / "src" / "app" / "page.tsx").exists())
    check("api.ts exists", (fe / "src" / "lib" / "api.ts").exists())

    # Quick check that api.ts has getLiveAccount
    api_ts = fe / "src" / "lib" / "api.ts"
    if api_ts.exists():
        content = api_ts.read_text(encoding="utf-8")
        check("api.ts has getLiveAccount", "getLiveAccount" in content)
    else:
        check("api.ts has getLiveAccount", False, "file missing")


# ════════════════════════════════════════════════════════════════════════
# 15. MT5 Connection (live)
# ════════════════════════════════════════════════════════════════════════

def test_mt5_connection():
    section("15. MT5 LIVE CONNECTION (optional)")
    try:
        import MetaTrader5 as mt5
        check("MetaTrader5 package installed", True)

        from config.settings import get_settings
        s = get_settings()
        ok = mt5.initialize(
            path=s.mt5_path,
            login=s.mt5_login,
            password=s.mt5_password,
            server=s.mt5_server,
            timeout=s.mt5_timeout,
        )
        if ok:
            info = mt5.account_info()
            check("MT5 connected successfully", True,
                  f"balance={info.balance if info else '?'}")
            if info:
                check("Account balance > 0", info.balance > 0,
                      f"${info.balance:.2f}")
            mt5.shutdown()
        else:
            err = mt5.last_error()
            check("MT5 connected successfully", False,
                  f"error {err}")
    except ImportError:
        check("MetaTrader5 package installed", False,
              "pip install MetaTrader5")
    except Exception as e:
        check("MT5 connection", False, str(e)[:80])


# ════════════════════════════════════════════════════════════════════════
# Run All
# ════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 60)
    print("  FOREX TRADING SYSTEM - HEALTH CHECK")
    print("=" * 60)

    test_file_structure()
    test_imports()
    test_configuration()
    test_database()
    test_mt5_provider()
    test_strategies()
    test_telegram()
    test_dashboard_api()
    test_schemas()
    test_ml_engine()
    test_execution()
    test_charts()
    test_main_module()
    test_frontend()
    test_mt5_connection()

    # Summary
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed}/{total} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED")
    else:
        print(f"  |  ALL PASSED")
    print(f"{'=' * 60}")

    if failed:
        print(f"\n  Failed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"    x {name}" + (f" - {detail}" if detail else ""))
        print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
