Forex Trading Bot — Complete Guide

## Overview

An autonomous forex trading system built with Python (FastAPI) and a Next.js dashboard. It fetches market data, runs multiple trading strategies with a meta-strategy selector, applies ML filtering, manages risk, executes trades via MetaTrader 5, and sends Telegram notifications.

---

## Architecture

```
main.py                  ← Entry point: FastAPI app + TradingBot orchestrator
│
├── config/
│   ├── settings.py      ← Pydantic settings (loaded from .env)
│   └── constants.py     ← Enums (Timeframe, OrderType, MarketRegime, etc.)
│
├── data/
│   ├── market_data.py   ← MarketDataEngine + MT5DataProvider (live data only)
│   └── session_detector.py ← Forex session detection (Sydney/Tokyo/London/NY)
│
├── strategies/
│   ├── base.py          ← Signal dataclass + BaseStrategy ABC
│   ├── engine.py        ← StrategyEngine (runs all strategies, meta-strategy)
│   ├── trend_following.py
│   ├── mean_reversion.py
│   ├── breakout.py
│   ├── volatility.py
│   ├── regime_detector.py  ← Market regime classification
│   ├── meta_strategy.py    ← Adaptive strategy selection engine
│   └── performance_tracker.py ← Per-strategy performance tracking
│
├── ml_models/
│   ├── engine.py        ← ML signal filter (Random Forest + LSTM)
│   ├── features.py      ← Feature engineering for ML
│   └── lstm_model.py    ← LSTM model definition (PyTorch)
│
├── execution/
│   ├── risk_manager.py  ← Position sizing, daily loss limits, trade validation
│   └── trade_executor.py ← MT5 order placement with retries
│
├── database/
│   ├── models.py        ← SQLAlchemy models (Trade, MarketData, etc.)
│   ├── session.py       ← Async DB engine + session factory
│   └── repository.py    ← CRUD operations (trades, candles, snapshots)
│
├── notifications/
│   └── telegram_bot.py  ← Telegram alerts (signals, trades, summaries)
│
├── charts/
│   └── generator.py     ← Signal chart generation (mplfinance)
│
├── backtesting/
│   └── engine.py        ← Backtesting framework
│
├── dashboard/
│   ├── api.py           ← FastAPI REST API (auth, trades, meta-strategy, etc.)
│   ├── auth.py          ← JWT authentication (HS256)
│   ├── schemas.py       ← Pydantic request/response models
│   └── frontend/        ← Next.js 14 + React 18 + Tailwind + Recharts
│       ├── src/app/page.tsx  ← Dashboard UI (login, overview, trades, meta)
│       └── src/lib/api.ts    ← API client with token management
│
├── utils/
|   ├── logging_config.py ← Structured JSON logging (structlog)
|   ├── indicators.py     ← Technical indicator calculations
|   └── math_helpers.py   ← Pip value, position size utilities
├── screenshots/
|   ├── This includes the Dashboard pictures and TradeBot Executions
```

---

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Backend, ML, trading logic |
| Node.js | 18+ (LTS) | Next.js dashboard frontend |
| MetaTrader 5 | Latest | Live/demo trading (Windows only) |
| Telegram Bot | Any | Trade notifications (optional) |

---

## Quick Start

### 1. Clone & Configure

```bash
cd trade_fx
cp .env.example .env   # or create .env manually
```

Edit `.env` with your settings (see Environment Variables section below).

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `MetaTrader5` is commented out in requirements.txt because it only works on Windows and requires the MT5 terminal installed. Install manually: `pip install MetaTrader5`

### 3. Install Frontend Dependencies

```bash
cd dashboard/frontend
npm install
cd ../..
```

### 4. Run the System

```bash
python main.py
```

This starts:
- **FastAPI backend** on `http://localhost:8000` (API + trading bot)
- The trading bot begins its 5-minute cycle automatically

In a separate terminal, start the dashboard:

```bash
cd dashboard/frontend
npm run dev
```

- **Dashboard** at `http://localhost:3000`
- Login with `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` from `.env`

---

## Operations Runbook (Local)

### A) News Filter: Autonomous + Fallback

The bot now supports autonomous news refresh from a calendar feed and keeps
`NEWS_EVENTS_UTC` as a fallback/safety override.

Recommended setup in `.env`:

```env
ENABLE_NEWS_FILTER=true
ENABLE_NEWS_EVENTS_UTC=true
ENABLE_NEWS_AUTO_UPDATE=true
NEWS_EVENTS_URL=https://nfs.faireconomy.media/ff_calendar_thisweek.xml
NEWS_AUTO_REFRESH_MINUTES=360
NEWS_BLOCK_MINUTES_BEFORE=45
NEWS_BLOCK_MINUTES_AFTER=30
```

Fallback/override list (`NEWS_EVENTS_UTC`) format:

```env
NEWS_EVENTS_UTC=2026-03-18T18:00:00Z|Federal Reserve Rate Decision|HIGH|USD;2026-03-26T12:15:00Z|ECB Main Refinancing Rate|HIGH|EUR;2026-03-19T02:00:00Z|BoJ Policy Rate|HIGH|JPY
```

Format rule per event:

```text
YYYY-MM-DDTHH:MM:SSZ|Event Label|HIGH|CCY1,CCY2
```

Examples:
- `USD` events block pairs containing USD (`EURUSD`, `USDJPY`, etc.)
- `EUR` events block EUR pairs (`EURUSD`, `EURGBP`, etc.)
- `JPY` events block JPY pairs (`USDJPY`, `GBPJPY`, etc.)

How it works:
- Bot refreshes feed automatically at startup and on schedule.
- If feed fails/unavailable, bot uses cached events.
- `NEWS_EVENTS_UTC` events are merged in (manual override).
- Block windows still apply per pair currencies.

Operational routine:
- Leave auto-update enabled.
- Only edit `NEWS_EVENTS_UTC` when you want to force/add specific events.
- Restart bot after major `.env` changes.

Related `.env` knobs:
- `ENABLE_NEWS_FILTER`
- `ENABLE_NEWS_EVENTS_UTC`
- `ENABLE_NEWS_AUTO_UPDATE`
- `NEWS_EVENTS_URL`
- `NEWS_AUTO_REFRESH_MINUTES`
- `NEWS_EVENTS_UTC`
- `NEWS_BLOCK_MINUTES_BEFORE`
- `NEWS_BLOCK_MINUTES_AFTER`

### B) Start Bot + API (Backend)

From project root:

```powershell
python main.py
```

Backend runs on `http://localhost:8000`.

### C) Start Dashboard Frontend

Open a second terminal:

```powershell
cd dashboard\frontend
npm run dev
```

Dashboard runs on `http://localhost:3000`.

### D) Confirm Bot Is Running (`running=true`)

The bot starts automatically with `python main.py`.

Ways to confirm:
- Log line: `"event": "Starting trading cycle"`
- API: login then check `/api/status` (`status` should be `RUNNING`)
- Telegram `/status` command

If paused/stopped:
- Dashboard control endpoint: `POST /api/control` with `{"action":"start"}`
- Telegram command: `/startbot`

### E) Toggle Manual `NEWS_EVENTS_UTC` From Dashboard

You can switch manual UTC events on/off live from the dashboard:

- Open `Overview` tab
- In `System Information`, use:
   - `Enable Manual UTC`
   - `Disable Manual UTC`

This calls:
- `GET /api/news/config`
- `POST /api/news/manual-source`

Notes:
- This does not disable auto news feed unless you turn it off in `.env`.
- No restart required for this runtime toggle.


---

## Environment Variables (.env)

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `ForexBot` | Application name |
| `APP_ENV` | `development` | Environment (development/production) |
| `DEBUG` | `false` | Enable debug mode + API docs at /docs |
| `LOG_LEVEL` | `INFO` | Logging level |
| **Database** | | |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/trading.db` | Async database URL |
| **MetaTrader 5** | | |
| `MT5_LOGIN` | `0` | MT5 account number |
| `MT5_PASSWORD` | | MT5 account password |
| `MT5_SERVER` | | MT5 broker server name |
| `MT5_PATH` | | Path to MT5 terminal (e.g., `C:\Program Files\MetaTrader 5\terminal64.exe`) |
| `MT5_TIMEOUT` | `10000` | Connection timeout (ms) |
| **Telegram** | | |
| `TELEGRAM_BOT_TOKEN` | | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | | Your chat ID (use @userinfobot) |
| `TELEGRAM_ENABLED` | `true` | Enable/disable notifications |
| **Windows Eval Alerts** | | |
| `ENABLE_WINDOWS_EVAL_EXPIRY_ALERT` | `false` | Enable Telegram reminders before Windows evaluation expiry |
| `WINDOWS_EVAL_EXPIRY_UTC` | | Evaluation expiry timestamp in UTC (ISO format, e.g. `2026-09-13T00:00:00Z`) |
| `WINDOWS_EVAL_ALERT_DAYS` | `30,14,7,3,1` | Comma-separated reminder thresholds in days |
| **Trading** | | |
| `TRADING_PAIRS` | `EURUSD,GBPUSD,...` | Comma-separated currency pairs |
| `DEFAULT_TIMEFRAME` | `H1` | Default analysis timeframe |
| `MAX_OPEN_TRADES` | `5` | Maximum concurrent open positions |
| `MAX_RISK_PER_TRADE` | `0.02` | Risk per trade (2% of balance) |
| `MAX_DAILY_LOSS` | `0.05` | Max daily loss before trading stops (5%) |
| `ACCOUNT_CURRENCY` | `USD` | Account denomination |
| **Dashboard** | | |
| `DASHBOARD_HOST` | `0.0.0.0` | API bind address |
| `DASHBOARD_PORT` | `8000` | API port |
| `SECRET_KEY` | | JWT secret key (generate a strong random string) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT token expiry (default: 24 hours) |
| `DASHBOARD_USERNAME` | | Dashboard login username |
| `DASHBOARD_PASSWORD` | | Dashboard login password |
| **Directories** | | |
| `DATA_DIR` | `./data` | Database and data files |
| `CHART_DIR` | `./charts/output` | Generated chart images |
| `LOG_DIR` | `./logs` | Log file directory |
| `ML_MODEL_DIR` | `./ml_models/saved` | Saved ML model files |

---

## Trading Cycle

Every 5 minutes the bot runs this cycle:

1. **Session check** — Skip if forex market is closed (weekends)
2. **Fetch data** — Get OHLCV candles for all pairs from MT5
3. **Strategy analysis** — Run all 4 strategies on each pair:
   - **Trend Following** — Moving average crossovers + ADX filter
   - **Mean Reversion** — RSI + Bollinger Bands extremes
   - **Breakout** — Support/resistance breakouts + volume confirmation
   - **Volatility** — ATR-based volatility expansion/contraction
4. **Meta-strategy selection** — Adaptive engine picks the best strategy per pair based on:
   - Current market regime (bullish/bearish/sideways/volatile)
   - Active forex session (Sydney/Tokyo/London/New York)
   - Recent strategy performance (win rate, Sharpe ratio)
5. **ML filter** — Random Forest model validates signals (reduces false signals)
6. **Risk validation** — Check position size, daily loss limits, max trades
7. **Execution** — Place orders via MT5 with SL/TP
8. **Notifications** — Send Telegram alerts with charts
9. **Dashboard update** — Push state to the REST API

---

## Dashboard

The web dashboard at `http://localhost:3000` provides:

| Tab | Features |
|---|---|
| **Overview** | Balance, equity, P&L chart, equity curve, open trades, MT5 connection banner, active pairs |
| **MT5 Account** | Live MT5 balance, equity, margin, profit, leverage, margin utilization bar |
| **Positions** | Currently open trades with entry price, SL/TP, P&L |
| **Trade History** | Completed trades with results |
| **Meta-Strategy** | Live regime detection, strategy rankings, decision reasoning |
| **Strategies** | Individual strategy configurations and status |
| **Logs** | Real-time system logs |

**API Endpoints** (all require JWT auth via `/api/auth/login`):

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Get JWT token |
| GET | `/api/status` | System status |
| GET | `/api/trades` | Trade history |
| GET | `/api/positions` | Open positions |
| GET | `/api/performance` | Performance summary |
| GET | `/api/balance` | Account balance (from DB snapshots) |
| GET | `/api/account/live` | Live MT5 account data (real-time) |
| GET | `/api/strategies` | Strategy info |
| GET | `/api/logs` | System logs |
| POST | `/api/control` | Start/stop/pause bot |
| GET | `/api/meta/decisions` | Meta-strategy decisions |
| GET | `/api/meta/rankings` | Strategy rankings |
| GET | `/api/meta/session` | Current session info |

---

## Why MT5 Is Required

MetaTrader 5 is the **sole data and execution provider**. The system does **not** have a simulated fallback — if MT5 is not connected, the bot will not start.

### Requirements

1. **Windows OS** — MT5 only runs on Windows
2. **MT5 Terminal installed and running** — must be open and logged in
3. **Python package** — `pip install MetaTrader5`
4. **Valid broker account** — MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in `.env`

---
###Screenshots
Check The Screenshots Folder For Dashboard Pictures, Trade Execution Pictures and Terminal Execuion Pictures 

## Setting Up MetaTrader 5 From Scratch (Demo Account)

Follow these steps to get a free demo account running:

### Step 1 — Download & Install MetaTrader 5

1. Go to [https://www.metatrader5.com/en/download](https://www.metatrader5.com/en/download)
2. Click **"Download MetaTrader 5"** and run the installer
3. Accept the license, choose install location (default is fine)
4. Wait for the install to finish — the MT5 terminal will open automatically

### Step 2 — Open a Demo Account

1. When MT5 opens for the first time, it shows a **"Open an Account"** dialog
2. Select **MetaQuotes-Demo** as the server (it's the built-in demo server) or search for your preferred broker
3. Choose **"Open a demo account"** and click **Next**
4. Fill in your details:
   - **Name**: Any name
   - **Email**: Any email (not verified)
   - **Account type**: Forex, Leverage 1:100 or 1:500
   - **Deposit**: Choose e.g. $10,000 virtual money
5. Click **Next** — your account will be created immediately
6. **IMPORTANT**: Write down the **login number**, **password**, and **server** shown on screen. You need these for `.env`.

### Step 3 — Verify MT5 Is Working

1. You should now see the MT5 terminal with live charts and prices
2. In the **Navigator** panel (left side), confirm your account shows under **Accounts**
3. At the bottom of the terminal, the **Trade** tab should show your demo balance

### Step 4 — Find the MT5 Terminal Path

You need the path to `terminal64.exe` for your `.env` file:

- Default path: `C:\Program Files\MetaTrader 5\terminal64.exe`
- If you installed to a custom location, right-click the MT5 desktop shortcut → **Properties** → copy the **Target** path

### Step 5 — Configure `.env`

Open your `.env` file and set these values:

```ini
MT5_LOGIN=12345678          # Your demo account login number
MT5_PASSWORD=YourPassword   # The password shown when you created the account
MT5_SERVER=MetaQuotes-Demo  # The server name (exactly as shown in MT5)
MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe #Where your MT5 terminal is located I
```

> **Note**: Use forward slashes `/` in the path, not backslashes `\`.

### Step 6 — Install the Python Package

```bash
pip install MetaTrader5
```

### Step 7 — Test the Connection

```bash
python test_system.py
```

Look at section **15. MT5 LIVE CONNECTION** in the output. If it shows `✓ PASS`, you're connected.

### Troubleshooting

| Problem | Fix |
|---|---|
| `MT5 initialize failed` | Make sure the MT5 terminal app is open and logged in |
| `Invalid account` | Double-check MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in `.env` |
| `Cannot find terminal` | Verify MT5_PATH points to the correct `terminal64.exe` |
| `ModuleNotFoundError: MetaTrader5` | Run `pip install MetaTrader5` |
| `timeout` | Increase MT5_TIMEOUT in `.env` (default 10000ms) |
| Demo account expired | Open MT5 terminal → File → Open Account → create a new demo |

---

## Telegram Bot Commands

The bot listens for Telegram commands (via polling). Send these to your bot in Telegram:

| Command | Description |
|---|---|
| `/status` | Bot status, active pairs, last scan time |
| `/balance` | Live MT5 account balance, equity, margin |
| `/trades` | List currently open trades |
| `/pairs` | Show which pairs are being traded |
| `/help` | Show all available commands |

### Notification types sent automatically:
- **Bot Started** — Sent when the bot starts with account info
- **Signal alerts** — New trading signal with entry/SL/TP and chart
- **Trade executed** — Confirmation with lot size and risk %
- **Trade closed** — Result with P&L
- **System errors** — Cycle errors, connection issues

---

## Risk Management

| Parameter | Default | Description |
|---|---|---|
| Max risk per trade | 2% | Of account balance |
| Max daily loss | 5% | Stops trading for the day if breached |
| Max open trades | 5 | Concurrent position limit |
| Min risk/reward ratio | 1.0 | Trades below this are rejected |
| Min signal confidence | 0.45 | Strategies must meet this threshold |
| Position size range | 0.01–10 lots | Clamped after calculation |
| Max spread filter | 3.0 pips | Trades rejected if spread too wide |

---

## Telegram Notifications

**Setup:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Copy the bot token → `TELEGRAM_BOT_TOKEN` in `.env`
3. Message [@userinfobot](https://t.me/userinfobot) → copy your chat ID → `TELEGRAM_CHAT_ID`
4. Set `TELEGRAM_ENABLED=true`

If the token is invalid (401 error), the bot will log a single warning and disable notifications automatically rather than flooding logs with errors.

See the **Telegram Bot Commands** section above for the full list of interactive commands.

---

## Dependency List

### Python (requirements.txt)

| Package | Purpose | Status |
|---|---|---|
| fastapi 0.104.1 | REST API framework | Required |
| uvicorn 0.24.0 | ASGI server | Required |
| pydantic 2.5.2 | Data validation | Required |
| pydantic-settings 2.1.0 | .env configuration | Required |
| python-dotenv 1.0.0 | .env file loading | Required |
| numpy 1.26.2 | Numerical computation | Required |
| pandas 2.1.4 | Data manipulation | Required |
| scipy 1.11.4 | Statistical functions | Required |
| statsmodels 0.14.1 | Time series analysis | Required |
| scikit-learn 1.3.2 | ML signal filtering | Required |
| torch 2.1.1 | LSTM model (PyTorch) | Required |
| joblib 1.3.2 | Model serialization | Required |
| matplotlib 3.8.2 | Chart generation | Required |
| mplfinance 0.12.10b0 | Candlestick charts | Required |
| plotly 5.18.0 | Interactive charts | Required |
| sqlalchemy 2.0.23 | Async ORM | Required |
| alembic 1.13.0 | Database migrations | Required |
| aiosqlite 0.19.0 | Async SQLite driver | Required |
| greenlet 3.0.2 | SQLAlchemy async support | Required |
| httpx 0.25.2 | HTTP client (Telegram) | Required |
| websockets 12.0 | WebSocket support | Required |
| python-multipart 0.0.6 | Form data parsing | Required |
| python-jose 3.3.0 | JWT tokens | Required |
| passlib 1.7.4 | Password hashing | Required |
| aiohttp 3.9.1 | Async HTTP | Required |
| aiofiles 23.2.1 | Async file I/O | Required |
| apscheduler 3.10.4 | Task scheduling | Required |
| structlog 23.2.0 | Structured logging | Required |
| ta 0.11.0 | Technical analysis indicators | Required |
| MetaTrader5 5.0.45 | MT5 broker API | Optional (Windows only) |

### Frontend (package.json)

| Package | Purpose |
|---|---|
| next 14 | React framework |
| react 18 | UI library |
| recharts 2.10 | Charts |
| lucide-react | Icons |
| tailwindcss 3 | Styling |
| typescript 5.3 | Type safety |

---

## Database

SQLite async (via aiosqlite) with these tables:

| Table | Purpose |
|---|---|
| `trades` | All executed trades with entry/exit/P&L |
| `market_data` | Cached OHLCV candles |
| `strategy_results` | Signal history per strategy |
| `performance_metrics` | Aggregated performance stats |
| `ml_model_records` | ML model metadata |
| `system_logs` | Application logs |
| `account_snapshots` | Balance/equity history |

The database is auto-created on first run at `DATA_DIR/trading.db`.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `MT5 not available` | Expected without MetaTrader 5 — uses simulated data. See "Why MT5 May Not Be Available" section |
| `Telegram 401 Unauthorized` | Bot token is invalid — get a new one from @BotFather or set `TELEGRAM_ENABLED=false` |
| `No market data received` | Fixed — simulated provider now generates synthetic data automatically |
| Dashboard won't load | Run `cd dashboard/frontend && npm install && npm run dev` |
| `Failed to load SWC binary` | Delete `node_modules` and `package-lock.json`, then `npm install` |
| Port 8000 already in use | Another instance is running — kill it or change `DASHBOARD_PORT` |
| Slow first startup | Normal — matplotlib builds font cache and torch loads on first import |

---

## Production Deployment

```bash
# Build frontend
cd dashboard/frontend
npm run build
cd ../..

# Run with production settings
APP_ENV=production DEBUG=false python main.py
```

For VPS deployment, see `deploy/setup_vps.sh` and `deploy/forex-trading.service` (systemd unit file).

