"""
config.py
---------
Central configuration for the Paper Trading System.
Change capital, risk, watchlist, Telegram credentials, and strategy
thresholds here. Nothing else in the codebase should hard-code these values.
"""

import os

# ---------------------------------------------------------------------------
# CAPITAL & RISK MANAGEMENT
# ---------------------------------------------------------------------------
INITIAL_CAPITAL = 100_000.0          # ₹1,00,000 virtual capital
RISK_PER_TRADE_PCT = 0.005           # 0.5% of capital risked per trade
MAX_RISK_PER_TRADE = INITIAL_CAPITAL * RISK_PER_TRADE_PCT   # ₹500 (on initial capital)
USE_LIVE_EQUITY_FOR_RISK = False     # If True, risk is % of current equity, not initial capital

MAX_OPEN_POSITIONS = 4               # Hard cap on concurrent open positions
MIN_OPEN_POSITIONS_WARNING = 2       # Below this, dashboard nudges "capital underused" (informational only)

MIN_RISK_REWARD = 2.0                # Minimum acceptable Risk:Reward (1:2)

MIN_HOLDING_DAYS = 2                 # Swing trade holding window
MAX_HOLDING_DAYS = 15

# ---------------------------------------------------------------------------
# WATCHLIST (NSE cash-equity symbols, yfinance format)
# ---------------------------------------------------------------------------
WATCHLIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "HINDUNILVR.NS",
    "ITC.NS",
    "BHARTIARTL.NS",
    "LT.NS",
]

# ---------------------------------------------------------------------------
# DATA / INDICATORS
# ---------------------------------------------------------------------------
DATA_PERIOD = "1y"                   # History window to download
DATA_INTERVAL = "1d"                 # Primary timeframe: Daily

EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14

RSI_IDEAL_MIN = 50
RSI_IDEAL_MAX = 65
RSI_HARD_CEILING = 75                # Avoid RSI > 75 (overextended)

VOLUME_AVG_PERIOD = 20               # For "healthy volume" comparison
VOLUME_HEALTHY_MULTIPLE = 1.0        # Current volume should be >= this x avg for a valid pullback confirmation
BREAKOUT_VOLUME_MULTIPLE = 1.5       # Breakout day volume should be >= this x avg

PULLBACK_EMA_PROXIMITY_PCT = 0.025   # Price within 2.5% of 20 EMA counts as "pulled back to EMA"
SWING_LOOKBACK = 10                  # Bars to look back for swing high/low & resistance level
RETEST_LOOKBACK = 4                  # Bars after breakout to check for a retest

# ---------------------------------------------------------------------------
# TRADE QUALITY SCORING
# ---------------------------------------------------------------------------
# Only setups scoring at these grades are actionable / alerted.
ACTIONABLE_GRADES = {"A+", "A"}

# ---------------------------------------------------------------------------
# TELEGRAM ALERTS
# ---------------------------------------------------------------------------
# Prefer environment variables in production; fall back to placeholders.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ---------------------------------------------------------------------------
# PERSISTENCE
# ---------------------------------------------------------------------------
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
PORTFOLIO_STATE_FILE = os.path.join(STATE_DIR, "portfolio_state.json")
LAST_SCAN_FILE = os.path.join(STATE_DIR, "last_scan.json")

os.makedirs(STATE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOG_LEVEL = "INFO"
