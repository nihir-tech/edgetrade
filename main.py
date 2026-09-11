"""
main.py
--------
Orchestrates a full scan of the watchlist:
    1. Fetch daily data
    2. Compute indicators
    3. Run trend filter
    4. Detect pullback / breakout setups
    5. Score each candidate setup
    6. Save results to state/last_scan.json (consumed by the dashboard)
    7. Send Telegram alerts for A / A+ setups

Run directly (`python main.py`) for a one-off scan, e.g. from a daily
cron job / scheduled task after market close. The Streamlit dashboard
also calls `run_scan()` on demand via its "Run Scan Now" button.
"""

import json
import logging
from datetime import datetime

import config
from data.data_fetcher import fetch_watchlist_data
from indicators.technicals import add_all_indicators
from strategy.trend_filter import evaluate_trend
from strategy.pullback import detect_pullback
from strategy.breakout import detect_breakout
from strategy.scorer import score_setup
from portfolio.paper_portfolio import PaperPortfolio
from alerts.telegram_bot import send_setup_alert, send_no_trade_summary
from utils.helpers import setup_logging

logger = logging.getLogger(__name__)


def _compute_sector_strength(all_data: dict) -> dict:
    """
    Simple relative-strength proxy: each symbol's 10-day return vs the
    watchlist's average 10-day return. Used as a light-weight stand-in
    for 'sector strength' scoring since granular sector data isn't
    reliably available via yfinance for NSE names.
    """
    returns = {}
    for symbol, df in all_data.items():
        if len(df) >= 11:
            ret = (df["Close"].iloc[-1] / df["Close"].iloc[-11] - 1) * 100
            returns[symbol] = ret
    if not returns:
        return {}
    avg_return = sum(returns.values()) / len(returns)
    return {sym: (ret - avg_return) for sym, ret in returns.items()}


def run_scan(send_alerts: bool = True) -> dict:
    """
    Executes a full watchlist scan and returns a results dict:
        {
          "scan_time": iso timestamp,
          "watchlist_overview": [ {symbol, price, ema20, ema50, rsi, trend, ...} ],
          "setups": [ {symbol, setup_type, grade, entry, stop_loss, target, ...} ],
        }
    Also writes this dict to config.LAST_SCAN_FILE for the dashboard to read.
    """
    setup_logging()
    logger.info("Starting watchlist scan for %d symbols...", len(config.WATCHLIST))

    all_data = fetch_watchlist_data(
        config.WATCHLIST, period=config.DATA_PERIOD, interval=config.DATA_INTERVAL
    )
    sector_strength = _compute_sector_strength(all_data)

    portfolio = PaperPortfolio()
    open_symbols = {p.symbol for p in portfolio.open_positions}

    watchlist_overview = []
    setups = []

    for symbol in config.WATCHLIST:
        df = all_data.get(symbol)
        if df is None:
            watchlist_overview.append({
                "symbol": symbol, "status": "NO DATA", "price": None,
                "ema20": None, "ema50": None, "rsi": None, "trend": "N/A",
            })
            continue

        enriched = add_all_indicators(
            df, ema_fast=config.EMA_FAST, ema_slow=config.EMA_SLOW,
            rsi_period=config.RSI_PERIOD, vol_avg_period=config.VOLUME_AVG_PERIOD,
        )
        trend = evaluate_trend(enriched)

        watchlist_overview.append({
            "symbol": symbol,
            "status": "OK",
            "price": round(trend.price, 2),
            "ema20": round(trend.ema_fast, 2) if trend.ema_fast == trend.ema_fast else None,
            "ema50": round(trend.ema_slow, 2) if trend.ema_slow == trend.ema_slow else None,
            "rsi": round(trend.rsi, 1) if trend.rsi == trend.rsi else None,
            "trend": "UPTREND" if trend.is_uptrend else "NOT IN UPTREND",
            "volume_healthy": trend.volume_healthy,
            "structure": "HH/HL" if trend.structure_hh_hl else "Weak/Unclear",
            "notes": trend.notes,
        })

        if symbol in open_symbols:
            # Already holding a position in this name - skip new-entry scanning
            # (never average down / duplicate entries).
            continue

        if not trend.passes_trend_filter:
            continue

        rel_strength = sector_strength.get(symbol)

        # --- Pullback setup ---
        pullback = detect_pullback(enriched, trend)
        if pullback.valid:
            result = score_setup(trend, pullback.risk_reward, is_retest=None, sector_strength_pct=rel_strength)
            candidate = {
                "symbol": symbol, "setup_type": "Pullback", "grade": result.grade,
                "score": result.score, "entry": pullback.entry, "stop_loss": pullback.stop_loss,
                "target": pullback.target, "risk_reward": pullback.risk_reward,
                "reason": pullback.reason, "breakdown": result.breakdown,
            }
            setups.append(candidate)

        # --- Breakout setup ---
        breakout = detect_breakout(enriched, trend)
        if breakout.valid:
            result = score_setup(
                trend, breakout.risk_reward, is_retest=breakout.is_retest, sector_strength_pct=rel_strength
            )
            candidate = {
                "symbol": symbol, "setup_type": "Breakout", "grade": result.grade,
                "score": result.score, "entry": breakout.entry, "stop_loss": breakout.stop_loss,
                "target": breakout.target, "risk_reward": breakout.risk_reward,
                "reason": breakout.reason, "breakdown": result.breakdown,
            }
            setups.append(candidate)

    # Sort setups best-first
    setups.sort(key=lambda s: s["score"], reverse=True)

    actionable = [s for s in setups if s["grade"] in config.ACTIONABLE_GRADES]

    if send_alerts:
        for s in actionable:
            sizing = portfolio.calculate_position_size(s["entry"], s["stop_loss"])
            qty = sizing.get("quantity", 0)
            risk_amt = sizing.get("actual_risk", 0)
            send_setup_alert(
                symbol=s["symbol"], setup_type=s["setup_type"], grade=s["grade"],
                entry=s["entry"], stop_loss=s["stop_loss"], target=s["target"],
                risk_reward=s["risk_reward"], quantity=qty, risk_amount=risk_amt,
            )
        if not actionable:
            send_no_trade_summary(scanned_count=len(config.WATCHLIST))

    result = {
        "scan_time": datetime.now().isoformat(timespec="seconds"),
        "watchlist_overview": watchlist_overview,
        "setups": setups,
        "actionable_count": len(actionable),
    }

    with open(config.LAST_SCAN_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(
        "Scan complete. %d setups found, %d actionable (A/A+).",
        len(setups), len(actionable),
    )
    return result


if __name__ == "__main__":
    scan_result = run_scan(send_alerts=True)
    if scan_result["actionable_count"] == 0:
        print("\nNO TRADE — WAIT. No A/A+ quality setups today. Capital protected.\n")
    else:
        print(f"\n{scan_result['actionable_count']} actionable setup(s) found. See dashboard for details.\n")
