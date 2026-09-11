"""
alerts/telegram_manager.py
---------------------------
Button-driven management bot for the paper trading system. `Start` the
bot, and an inline menu opens with a button for everything the Streamlit
dashboard can do:

    📋 Watchlist     - trend overview of every symbol
    🎯 Setups        - today's scored setups (A/A+ first)
    🔄 Scan Now      - run a fresh watchlist scan right now
    💼 Positions     - open positions with live unrealized P&L
    📈 Equity        - equity curve + summary stats
    ⚙️ Status        - system config + portfolio snapshot
    ✍️ Open Trade    - guided manual trade entry (buttons for setup/grade)
    📜 History       - closed trade history
    🚀 Full Report   - scan + watchlist + positions + equity in one tap
    ♻️ Reset         - reset the paper portfolio (button confirm)

Text commands (same actions, must be typed) also work:

    /open RELIANCE 2985.5 2935 3120 Pullback A
    /close RELIANCE 2990
    /updatestop RELIANCE 2965
    /cancel

Run with:
    python -m alerts.telegram_manager
"""

import json
import logging
import time
from datetime import datetime

import config
from alerts.telegram_bot import answer_callback_query, get_updates, send_telegram_message
from data.data_fetcher import fetch_daily_data
from main import run_scan
from portfolio.paper_portfolio import PaperPortfolio
from utils.helpers import format_inr, setup_logging

logger = logging.getLogger(__name__)

PENDING = {}

SETUP_OPTIONS = ["Pullback", "Breakout", "Manual"]
GRADE_OPTIONS = ["A+", "A", "B", "C"]

FLOWS = {
    "open": [
        ("symbol", "Enter symbol, e.g. `RELIANCE.NS`:"),
        ("entry", "Enter entry price (₹):"),
        ("stop", "Enter stop-loss (₹):"),
        ("target", "Enter target (₹):"),
        ("setup", f"Setup type — {' / '.join(SETUP_OPTIONS)}:"),
        ("grade", f"Grade — {' / '.join(GRADE_OPTIONS)}:"),
    ],
    "close": [
        ("symbol", "Which position to close?"),
        ("price", "Enter exit price (₹):"),
        ("reason", "Exit reason (or `-` for 'Manual exit'):"),
    ],
    "updatestop": [
        ("symbol", "Which position?"),
        ("new_stop", "New stop-loss (₹) — must be tighter / higher:"),
    ],
}

MENU_HEADER = (
    "🤖 *PAPER TRADING BOT — MENU*\n\n"
    "_Tap a button below. Everything the dashboard does works here._\n\n"
    "Current: {equity} · {open} open positions"
)


def _kb(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


BACK_BUTTON = [[("⬅️ Back to Menu", "menu")]]


def _reply(text: str, rows=None) -> bool:
    return send_telegram_message(text, reply_markup=_kb(rows) if rows else None)


def _reply_menu(text: str) -> bool:
    return _reply(text, BACK_BUTTON)


def _main_menu_message() -> str:
    portfolio = PaperPortfolio()
    equity = portfolio.mark_to_market_equity({})
    return MENU_HEADER.format(
        equity=format_inr(equity), open=len(portfolio.open_positions)
    )


def _main_menu_rows():
    return [
        [("📋 Watchlist", "menu:watchlist"), ("🎯 Setups", "menu:setups")],
        [("🔄 Scan Now", "menu:scan"), ("💼 Positions", "menu:positions")],
        [("📈 Equity", "menu:equity"), ("⚙️ Status", "menu:status")],
        [("✍️ Open Trade", "menu:open"), ("📜 History", "menu:history")],
        [("🚀 Full Report", "menu:full")],
        [("♻️ Reset Portfolio", "menu:reset")],
    ]


def _send_main_menu():
    _reply(_main_menu_message(), _main_menu_rows())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_symbol(raw: str) -> str:
    sym = raw.strip().upper().replace(" ", "")
    if "." not in sym:
        sym = f"{sym}.NS"
    return sym


def _now_short(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except Exception:
        return iso or "?"


def _num(text: str):
    try:
        return float(str(text).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return None


def _get_scan(max_age_hours: float = 6) -> dict:
    try:
        with open(config.LAST_SCAN_FILE, "r") as f:
            scan = json.load(f)
        last = datetime.fromisoformat(scan.get("scan_time", ""))
        age_s = (datetime.now() - last).total_seconds()
        if age_s < max_age_hours * 3600 and scan.get("watchlist_overview"):
            return scan
    except Exception:
        pass
    return run_scan(send_alerts=False)


def _fetch_last_price(symbol: str):
    df = fetch_daily_data(symbol, period="1mo", interval="1d")
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[-1])


def _symbol_buttons() -> list:
    portfolio = PaperPortfolio()
    open_positions = portfolio.open_positions
    if not open_positions:
        return None
    return [tuple((p.symbol, f"pick|symbol|{p.symbol}") for p in open_positions)]


def _field_buttons(action: str, field: str):
    if field == "setup":
        return [tuple((o, f"pick|setup|{o}") for o in SETUP_OPTIONS)]
    if field == "grade":
        return [tuple((g, f"pick|grade|{g}") for g in GRADE_OPTIONS)]
    if field == "symbol" and action in ("close", "updatestop"):
        return _symbol_buttons()
    return None


# ---------------------------------------------------------------------------
# Simple command builders
# ---------------------------------------------------------------------------

def _build_status() -> str:
    portfolio = PaperPortfolio()
    open_positions = portfolio.open_positions
    equity = portfolio.mark_to_market_equity(_live_prices(open_positions))
    return (
        "⚙️ *SYSTEM CONFIGURATION*\n"
        f"Virtual capital: {format_inr(config.INITIAL_CAPITAL)}\n"
        f"Risk per trade: {config.RISK_PER_TRADE_PCT * 100:.1f}% ({format_inr(config.MAX_RISK_PER_TRADE)})\n"
        f"Max open positions: {config.MAX_OPEN_POSITIONS}\n"
        f"Min Risk:Reward: 1:{config.MIN_RISK_REWARD:.0f}\n"
        f"Holding period: {config.MIN_HOLDING_DAYS}–{config.MAX_HOLDING_DAYS} days\n"
        f"Watchlist: {len(config.WATCHLIST)} symbols\n"
        f"Telegram: {'✅ enabled' if config.TELEGRAM_ENABLED else '⚪ not configured'}\n\n"
        "💼 *PORTFOLIO SNAPSHOT*\n"
        f"Current equity: {format_inr(equity)}\n"
        f"Cash: {format_inr(portfolio.cash)}\n"
        f"Open positions: {len(open_positions)} / {config.MAX_OPEN_POSITIONS}\n"
        f"Realized P&L: {format_inr(portfolio.realized_pnl())}"
    )


def _build_watchlist(scan: dict) -> str:
    rows = scan.get("watchlist_overview", [])
    t = _now_short(scan.get("scan_time", ""))
    lines = ["📋 *WATCHLIST OVERVIEW*", f"_Scan: {t}_", "", "```"]
    lines.append(f"{'SYMBOL':<14}{'PRICE':>11}{'EMA20':>10}{'RSI':>6} {'TREND':<10}")
    lines.append("-" * 52)
    n_data = 0
    for r in rows:
        sym = r.get("symbol", "?")
        if r.get("status") == "NO DATA" or r.get("price") is None:
            lines.append(f"{sym:<14}{'NO DATA':>22}{'':>5}")
            continue
        n_data += 1
        trend = "UPTREND" if r.get("trend") == "UPTREND" else "NO UPTREND"
        price = f"{r['price']:,.2f}"
        ema = "—" if r.get("ema20") is None else f"{r['ema20']:,.2f}"
        rsi = "—" if r.get("rsi") is None else f"{r['rsi']:.1f}"
        lines.append(f"{sym:<14}{price:>11}{ema:>10}{rsi:>6} {trend:<10}")
    lines.append("```")
    lines.append(f"_{n_data}/{len(rows)} symbols with data._")
    return "\n".join(lines)


def _build_setups_message(scan: dict) -> str:
    setups = scan.get("setups", [])
    actionable = [s for s in setups if s["grade"] in config.ACTIONABLE_GRADES]
    others = [s for s in setups if s["grade"] not in config.ACTIONABLE_GRADES]
    t = _now_short(scan.get("scan_time", ""))

    lines = ["🎯 *TODAY'S SETUPS*", f"_Scan: {t} · {len(config.WATCHLIST)} symbols_", ""]
    if actionable:
        lines.append(f"✅ *{len(actionable)} actionable (A/A+):*")
        lines.append("")
        for s in actionable:
            short = s["symbol"].split(".")[0]
            lines.append(
                f"🚨 *{s['grade']} SETUP — {s['setup_type'].upper()}*\n"
                f"`{s['symbol']}`\n"
                f"Entry: {format_inr(s['entry'])}\n"
                f"Stop: {format_inr(s['stop_loss'])} · Target: {format_inr(s['target'])} "
                f"(RR 1:{s['risk_reward']:.1f})\n"
                f"_{s['reason']}_"
            )
            lines.append(f"Open it: `/open {short} {s['entry']} {s['stop_loss']} "
                         f"{s['target']} {s['setup_type']} {s['grade']}`")
            lines.append("")
    else:
        lines.append("🚫 *NO TRADE — WAIT*")
        lines.append("No A/A+ setups in the latest scan. Capital protected.")
        lines.append("")

    if others:
        lines.append(f"📊 *Other candidates ({len(others)}):*")
        for s in others:
            lines.append(
                f"• `{s['symbol']}` {s['setup_type']} · Grade {s['grade']} "
                f"({s['score']}/100) · RR 1:{s['risk_reward']:.1f}"
            )
    return "\n".join(lines)


def _live_prices(positions) -> dict:
    prices = {}
    for p in positions:
        price = _fetch_last_price(p.symbol)
        prices[p.symbol] = price if price is not None else p.entry_price
    return prices


def _build_positions() -> str:
    portfolio = PaperPortfolio()
    open_positions = portfolio.open_positions
    if not open_positions:
        return "💼 *OPEN POSITIONS*\n\nNo open positions. Capital fully protected in cash."
    prices = _live_prices(open_positions)
    portfolio.refresh_equity_curve(prices)

    lines = ["💼 *OPEN POSITIONS*", "", "```"]
    lines.append(f"{'SYMBOL':<14}{'QTY':>5}{'ENTRY':>10}{'CUR':>10}{'STOP':>10}{'TGT':>10}{'P&L':>10}")
    lines.append("-" * 70)
    total_pnl = 0.0
    for p in open_positions:
        cur = prices.get(p.symbol, p.entry_price)
        pnl = (cur - p.entry_price) * p.quantity
        total_pnl += pnl
        lines.append(
            f"{p.symbol:<14}{p.quantity:>5}{p.entry_price:>10,.2f}{cur:>10,.2f}"
            f"{p.stop_loss:>10,.2f}{p.target:>10,.2f}{pnl:>10,.2f}"
        )
    lines.append("```")
    lines.append(f"*Total unrealized P&L:* {format_inr(total_pnl)}")
    return "\n".join(lines)


def _build_history() -> str:
    portfolio = PaperPortfolio()
    closed = portfolio.closed_positions
    if not closed:
        return "📜 *CLOSED TRADES*\n\nNo closed trades yet."
    lines = ["📜 *CLOSED TRADES*", "", "```"]
    lines.append(f"{'SYMBOL':<14}{'ENTRY':>10}{'EXIT':>10}{'QTY':>5}{'P&L':>10}")
    lines.append("-" * 50)
    for p in list(reversed(closed))[:10]:
        pnl = p.pnl or 0.0
        lines.append(
            f"{p.symbol:<14}{p.entry_price:>10,.2f}{p.exit_price or 0:>10,.2f}"
            f"{p.quantity:>5}{pnl:>10,.2f}"
        )
    lines.append("```")
    lines.append(f"*Total realized P&L:* {format_inr(portfolio.realized_pnl())}")
    return "\n".join(lines)


def _build_equity() -> str:
    portfolio = PaperPortfolio()
    open_positions = portfolio.open_positions
    prices = _live_prices(open_positions)
    equity = portfolio.mark_to_market_equity(prices)
    portfolio.refresh_equity_curve(prices)

    curve = portfolio.equity_curve
    start = curve[0].equity if curve else equity
    best = max(e.equity for e in curve) if curve else equity
    worst = min(e.equity for e in curve) if curve else equity
    change = equity - start
    change_pct = (change / start * 100) if start else 0.0

    return (
        "📈 *EQUITY*\n"
        f"Current equity: {format_inr(equity)}\n"
        f"Cash: {format_inr(portfolio.cash)}\n"
        f"Realized P&L: {format_inr(portfolio.realized_pnl())}\n"
        f"Open positions: {len(open_positions)} / {config.MAX_OPEN_POSITIONS}\n\n"
        f"Since {_now_short(curve[0].date)}: {format_inr(change)} ({change_pct:+.1f}%)\n"
        f"Best: {format_inr(best)} · Worst: {format_inr(worst)}"
    )


def _build_full_report(scan: dict) -> str:
    return "\n\n".join([
        _build_watchlist(scan),
        _build_setups_message(scan),
        _build_positions(),
        _build_equity(),
    ])


# ---------------------------------------------------------------------------
# Command handlers (menu replies)
# ---------------------------------------------------------------------------

def cmd_help(chat_id, args):
    _send_main_menu()


def cmd_status(chat_id, args):
    _reply_menu(_build_status())


def cmd_watchlist(chat_id, args):
    _reply_menu(_build_watchlist(_get_scan()))


def cmd_setups(chat_id, args):
    _reply_menu(_build_setups_message(_get_scan()))


def cmd_full(chat_id, args):
    _reply("⏳ Running full report… (scan up to 60 s)")
    try:
        scan = run_scan(send_alerts=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Full report failed: %s", exc)
        _reply_menu(f"❌ Scan failed: {exc}")
        return
    _reply_menu(_build_full_report(scan))


def cmd_scan(chat_id, args):
    _reply("⏳ Running a fresh scan… (30–60 s)")
    try:
        scan = run_scan(send_alerts=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scan failed: %s", exc)
        _reply_menu(f"❌ Scan failed: {exc}")
        return
    _reply_menu(_build_setups_message(scan))


def cmd_positions(chat_id, args):
    _reply_menu(_build_positions())


def cmd_history(chat_id, args):
    _reply_menu(_build_history())


def cmd_equity(chat_id, args):
    _reply_menu(_build_equity())


def cmd_reset(chat_id, args):
    PENDING[chat_id] = {"action": "confirm_reset", "data": {}}
    _reply(
        "⚠️ *Reset paper portfolio?*\n\n"
        "This wipes all open + closed trades and restores the initial capital.",
        [[("✅ Yes, Reset", "cnf|yes|confirm_reset"), ("❌ Cancel", "cnf|no|confirm_reset")]],
    )


# ---------------------------------------------------------------------------
# Guided flows
# ---------------------------------------------------------------------------

def _begin_flow(chat_id, action):
    PENDING[chat_id] = {"action": action, "step": 0, "data": {}}
    _prompt_next(chat_id)


def _prompt_next(chat_id):
    pending = PENDING.get(chat_id)
    if not pending:
        return
    flow = FLOWS[pending["action"]]
    step = pending["step"]
    if step < len(flow):
        field, prompt = flow[step]
        pending["step"] += 1
        buttons = _field_buttons(pending["action"], field)
        if buttons:
            _reply(f"*{step + 1}/{len(flow)}* — {prompt}", buttons)
        else:
            _reply(f"*{step + 1}/{len(flow)}* — {prompt}")


def _parse_field(action, field, text):
    if field == "symbol":
        return _norm_symbol(str(text))
    if field in ("entry", "stop", "target", "price", "new_stop"):
        return _num(text)
    if field == "reason":
        return "Manual exit" if str(text).strip() == "-" else str(text).strip()
    if field == "setup":
        return next((o for o in SETUP_OPTIONS if o.lower() == str(text).strip().lower()), None)
    if field == "grade":
        return next((g for g in GRADE_OPTIONS if g.lower() == str(text).strip().lower()), None)
    return text


def _consume_value(chat_id, value):
    pending = PENDING.get(chat_id)
    if not pending:
        return
    action = pending["action"]
    flow = FLOWS[action]
    field = flow[pending["step"] - 1][0]
    parsed = _parse_field(action, field, value)
    if parsed is None:
        _reply(f"❌ Invalid input for *{field}* — try again:")
        return
    pending["data"][field] = parsed

    if pending["step"] >= len(flow):
        data = pending["data"]
        if action == "open":
            _open_preview(chat_id, data)
        elif action == "close":
            _close_preview(chat_id, data)
        elif action == "updatestop":
            _stop_preview(chat_id, data)
    else:
        _prompt_next(chat_id)


def cmd_open(chat_id, args):
    if len(args) >= 4:
        try:
            data = {
                "symbol": _norm_symbol(args[0]),
                "entry": float(args[1]),
                "stop": float(args[2]),
                "target": float(args[3]),
                "setup": args[4] if len(args) > 4 and args[4][:1].isalpha() else "Manual",
                "grade": args[5] if len(args) > 5 else "B",
            }
            _open_preview(chat_id, data)
            return
        except ValueError:
            pass
    _begin_flow(chat_id, "open")


def _open_preview(chat_id, data):
    entry, stop, target = data["entry"], data["stop"], data["target"]
    if stop >= entry:
        _reply("❌ Stop-loss must be **below** entry price. Try again.")
        return
    if target <= entry:
        _reply("❌ Target must be **above** entry price. Try again.")
        return
    if data["setup"] not in SETUP_OPTIONS:
        data["setup"] = "Manual"
    if data["grade"] not in GRADE_OPTIONS:
        data["grade"] = "B"

    portfolio = PaperPortfolio()
    sizing = portfolio.calculate_position_size(entry, stop)
    if not sizing["allowed"]:
        _reply(f"❌ Cannot size this trade: {sizing['reason']}")
        return

    rr = (target - entry) / (entry - stop)
    hint = ""
    if rr < config.MIN_RISK_REWARD:
        hint = f"\n⚠️ RR 1:{rr:.2f} is below the minimum 1:{config.MIN_RISK_REWARD:.0f}."

    PENDING[chat_id] = {"action": "confirm_open", "data": data}
    _reply(
        "📋 *PREVIEW — MANUAL TRADE*\n"
        f"Symbol: `{data['symbol']}`\n"
        f"Setup: {data['setup']} · Grade: {data['grade']}\n"
        f"Entry: {format_inr(entry)}\n"
        f"Stop: {format_inr(stop)}\n"
        f"Target: {format_inr(target)} (RR 1:{rr:.2f})\n"
        f"Qty: *{sizing['quantity']}* · Risk: {format_inr(sizing['actual_risk'])} · "
        f"Cost: {format_inr(sizing['cost'])}{hint}",
        [[("✅ Confirm & Open", "cnf|yes|confirm_open"), ("❌ Cancel", "cnf|no|confirm_open")]],
    )


def cmd_close(chat_id, args):
    if len(args) >= 2:
        price = _num(args[1])
        if price and price > 0:
            reason = " ".join(args[2:]).strip() or "Manual exit"
            data = {"symbol": _norm_symbol(args[0]), "price": price, "reason": reason}
            _close_preview(chat_id, data)
            return
    _begin_flow(chat_id, "close")


def _close_preview(chat_id, data):
    portfolio = PaperPortfolio()
    if not any(p.symbol == data["symbol"] for p in portfolio.open_positions):
        _reply(f"❌ No open position found for `{data['symbol']}`.")
        return
    PENDING[chat_id] = {"action": "confirm_close", "data": data}
    _reply(
        "📋 *PREVIEW — CLOSE POSITION*\n"
        f"Symbol: `{data['symbol']}`\n"
        f"Exit price: {format_inr(data['price'])}\n"
        f"Reason: {data['reason']}",
        [[("✅ Confirm Close", "cnf|yes|confirm_close"), ("❌ Cancel", "cnf|no|confirm_close")]],
    )


def cmd_updatestop(chat_id, args):
    if len(args) >= 2:
        new_stop = _num(args[1])
        if new_stop and new_stop > 0:
            data = {"symbol": _norm_symbol(args[0]), "new_stop": new_stop}
            _stop_preview(chat_id, data)
            return
    _begin_flow(chat_id, "updatestop")


def _stop_preview(chat_id, data):
    portfolio = PaperPortfolio()
    if not any(p.symbol == data["symbol"] for p in portfolio.open_positions):
        _reply(f"❌ No open position found for `{data['symbol']}`.")
        return
    PENDING[chat_id] = {"action": "confirm_stop", "data": data}
    _reply(
        "📋 *PREVIEW — UPDATE STOP-LOSS*\n"
        f"Symbol: `{data['symbol']}`\n"
        f"New stop: {format_inr(data['new_stop'])}",
        [[("✅ Set Stop", "cnf|yes|confirm_stop"), ("❌ Cancel", "cnf|no|confirm_stop")]],
    )


def cmd_cancel(chat_id, args):
    if PENDING.pop(chat_id, None):
        _reply("Cancelled.")
    else:
        _send_main_menu()


def _run_confirm(chat_id, action, data):
    portfolio = PaperPortfolio()
    try:
        if action == "confirm_open":
            res = portfolio.open_position(
                symbol=data["symbol"], setup_type=data["setup"], grade=data["grade"],
                entry=data["entry"], stop_loss=data["stop"], target=data["target"],
            )
            if res["success"]:
                sizing = res["sizing"]
                _reply_menu(
                    "✅ *PAPER TRADE OPENED*\n"
                    f"Symbol: `{data['symbol']}`\n"
                    f"Setup: {data['setup']} · Grade: {data['grade']}\n"
                    f"Entry: {format_inr(data['entry'])}\n"
                    f"Stop: {format_inr(data['stop'])} · Target: {format_inr(data['target'])}\n"
                    f"Qty: {sizing['quantity']} · Risk: {format_inr(sizing['actual_risk'])}\n"
                    f"Cost: {format_inr(sizing['cost'])}"
                )
            else:
                _reply_menu(f"❌ Could not open: {res['reason']}")

        elif action == "confirm_close":
            res = portfolio.close_position(data["symbol"], data["price"], data["reason"])
            if res["success"]:
                _reply_menu(
                    f"✅ *POSITION CLOSED*\n`{data['symbol']}` @ {format_inr(data['price'])}\n"
                    f"Realized P&L: **{format_inr(res['pnl'])}**"
                )
            else:
                _reply_menu(f"❌ {res['reason']}")

        elif action == "confirm_stop":
            res = portfolio.update_stop_loss(data["symbol"], data["new_stop"])
            if res["success"]:
                _reply_menu(f"✅ Stop-loss updated for `{data['symbol']}` → {format_inr(data['new_stop'])}")
            else:
                _reply_menu(f"❌ {res['reason']}")

        elif action == "confirm_reset":
            portfolio.reset()
            _reply_menu("✅ Paper portfolio reset to initial capital. Fresh start.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Confirm action failed: %s", exc)
        _reply_menu(f"❌ Failed: {exc}")
    finally:
        PENDING.pop(chat_id, None)


# ---------------------------------------------------------------------------
# Update dispatch + polling loop
# ---------------------------------------------------------------------------

MENU_ACTIONS = {
    "watchlist": cmd_watchlist,
    "setups": cmd_setups,
    "scan": cmd_scan,
    "positions": cmd_positions,
    "equity": cmd_equity,
    "status": cmd_status,
    "full": cmd_full,
    "history": cmd_history,
    "open": cmd_open,
    "reset": cmd_reset,
}


def _execute_menu_action(chat_id, action):
    handler = MENU_ACTIONS.get(action)
    if handler:
        handler(chat_id, [])
    else:
        _send_main_menu()


def handle_callback(chat_id, data, cq_id=None):
    if cq_id:
        answer_callback_query(cq_id)

    if data == "menu":
        _send_main_menu()
        PENDING.pop(chat_id, None)
    elif data.startswith("menu:"):
        _execute_menu_action(chat_id, data.split(":", 1)[1])
    elif data.startswith("pick|"):
        _, field, value = data.split("|", 2)
        _consume_value(chat_id, value)
    elif data.startswith("cnf|"):
        _, yesno, action = data.split("|")
        if yesno == "yes":
            _run_confirm(chat_id, action, PENDING.get(chat_id, {}).get("data", {}))
        else:
            PENDING.pop(chat_id, None)
            _send_main_menu()
    else:
        _send_main_menu()


def handle(chat_id: int, command: str, args: list):
    if chat_id in PENDING and command.lower().startswith("/"):
        PENDING.pop(chat_id, None)

    mapping = {
        "/help": cmd_help, "/start": cmd_help,
        "/status": cmd_status, "/scan": cmd_scan,
        "/watchlist": cmd_watchlist, "/setups": cmd_setups,
        "/full": cmd_full, "/positions": cmd_positions,
        "/history": cmd_history, "/equity": cmd_equity,
        "/reset": cmd_reset, "/open": cmd_open,
        "/close": cmd_close, "/updatestop": cmd_updatestop,
        "/cancel": cmd_cancel,
    }
    handler = mapping.get(command.lower())
    if handler:
        handler(chat_id, args)
    else:
        _reply(f"Unknown command `{command}`. Tap the menu or type `/start`.")


def handle_update(update: dict):
    if "callback_query" in update:
        cq = update["callback_query"]
        msg = cq.get("message") or {}
        chat_id = msg.get("chat", {}).get("id")
        if not chat_id or str(chat_id) != str(config.TELEGRAM_CHAT_ID):
            return
        handle_callback(chat_id, cq.get("data", ""), cq_id=cq.get("id"))
        return

    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return
    chat_id = msg["chat"]["id"]
    text = msg["text"].strip()

    if str(chat_id) != str(config.TELEGRAM_CHAT_ID):
        logger.info("Ignoring message from chat %s (not the configured chat id).", chat_id)
        return

    if text.lower() == "/cancel":
        cmd_cancel(chat_id, [])
        return

    if chat_id in PENDING and not text.startswith("/"):
        pending = PENDING[chat_id]
        if pending["action"].startswith("confirm_"):
            if text.strip().lower() == "yes":
                _run_confirm(chat_id, pending["action"], pending.get("data", {}))
            else:
                PENDING.pop(chat_id, None)
                _send_main_menu()
        else:
            _consume_value(chat_id, text)
        return

    parts = text.split()
    handle(chat_id, parts[0], parts[1:])


def run_bot(poll_interval: float = 1.0):
    setup_logging()
    if not config.TELEGRAM_ENABLED:
        logger.warning("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing) - bot won't start.")
        print("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first.")
        return

    logger.info("Telegram manager bot started. Send /start in Telegram.")
    offset = 0
    while True:
        try:
            updates = get_updates(offset=offset, timeout_seconds=20)
            for u in updates or []:
                offset = max(offset, u.get("update_id", 0) + 1)
                try:
                    handle_update(u)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error handling update: %s", exc)
        except KeyboardInterrupt:
            logger.info("Bot stopped.")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Poll error: %s", exc)
        time.sleep(poll_interval)


if __name__ == "__main__":
    run_bot()