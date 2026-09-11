# Paper Trading System — Indian Swing Strategy

A disciplined, low-risk **paper trading bot + Streamlit dashboard** for cash-equity
swing trading on NSE stocks. Capital protection is the first priority: the system
only ever surfaces **A / A+** graded setups, and defaults to **"NO TRADE — WAIT"**
when the market doesn't offer a high-quality opportunity.

## Quick Start

```bash
# 1. Create and activate a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Configure Telegram alerts
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# 4. Run a one-off scan (prints results, sends Telegram alert if configured)
python main.py

# 5. Launch the dashboard
streamlit run dashboard/app.py
```

## Project Structure

```
trading_bot/
├── main.py                    # Orchestrates the full scan pipeline
├── config.py                  # All tunables: capital, risk %, watchlist, Telegram
├── data/
│   └── data_fetcher.py        # yfinance data download + validation
├── indicators/
│   └── technicals.py          # EMA, RSI, ATR, swing high/low, structure
├── strategy/
│   ├── trend_filter.py        # Mandatory trend gate
│   ├── pullback.py            # Entry Setup 1
│   ├── breakout.py            # Entry Setup 2 (+ retest logic)
│   └── scorer.py              # A+/A/B/C/NO TRADE quality scoring
├── portfolio/
│   └── paper_portfolio.py     # Capital, position sizing, open/close, equity curve
├── dashboard/
│   └── app.py                 # Streamlit UI
├── alerts/
│   └── telegram_bot.py        # Sends alerts for A/A+ setups only
├── utils/
│   └── helpers.py             # Logging, ₹ formatting
├── state/                     # Auto-created: portfolio_state.json, last_scan.json
└── requirements.txt
```

## How the Strategy Works

1. **Trend filter (mandatory):** Price > EMA20 > EMA50, RSI not overextended (>75),
   healthy volume. Nothing is considered without this.
2. **Entry Setup 1 — Pullback:** Price pulls back near the 20 EMA/support, a bullish
   confirmation candle prints, RSI holds above 50. Entry is a stop order above the
   confirmation candle's high; stop-loss sits below the recent swing low.
3. **Entry Setup 2 — Breakout:** A clear resistance level breaks on volume ≥1.5x the
   20-day average. Fresh breakouts are scored lower than a **breakout + successful
   retest**, which is the higher-conviction version of this setup.
4. **Scoring:** Every valid candidate is scored across 8 weighted dimensions (trend
   structure, EMA alignment, RSI, volume, entry quality, stop-loss quality,
   risk:reward, relative sector strength) into a 0–100 score and a letter grade.
   **Only A/A+ setups are actionable** — everything else is shown for transparency
   but not alerted or defaulted into the "open trade" flow.
5. **Position sizing:** `Quantity = (Capital × 0.5%) / (Entry − Stop Loss)`, capped by
   available cash and a hard limit of `MAX_OPEN_POSITIONS` (default 4).

## Risk Rules Enforced in Code

- Exactly **0.5% of capital (₹500)** risked per trade — see `PaperPortfolio.calculate_position_size`.
- **No duplicate/averaging-down** entries — `open_position` blocks a second entry in a symbol already held.
- **Stop-loss can only be tightened, never widened** — `update_stop_loss` rejects any move away from price.
- **Max 2–4 open positions** — enforced before any new position is sized.
- Minimum **1:2 Risk:Reward** is a hard gate in both `pullback.py` and `breakout.py`; anything below it never reaches the scorer as actionable.

## Notes & Limitations

- Data comes from `yfinance` (Yahoo Finance), which is sufficient for a paper
  system but can have gaps/delays — always sanity-check before relying on it live.
- "Sector strength" is approximated via each stock's 10-day return relative to the
  watchlist average, since granular NSE sector data isn't reliably free. Swap in a
  real sector index feed in `main.py::_compute_sector_strength` if you have one.
- This is a **paper trading** system only — no real orders are placed. Wire in a
  broker API (e.g. Zerodha Kite Connect, Upstox) separately if you want to go live,
  and re-test thoroughly first.
- Run `main.py` on a schedule (cron / Task Scheduler) after market close for daily
  Telegram alerts; the dashboard also triggers a scan on demand.
