"""
dashboard/app.py
----------------
Responsive, mobile-first Streamlit dashboard for the Paper Trading System.

Run with:
    streamlit run dashboard/app.py

Designed to render beautifully on phones, tablets and desktops:
tabs collapse to swipeable rows on small screens, metric cards stack,
tables scroll horizontally, and the sidebar becomes a bottom drawer.

Tabs:
    1. Watchlist   - trend status, EMAs, RSI + per-stock detail chart
    2. Setups      - scored A+/A/B/C candidates, "NO TRADE" state
    3. Positions   - live paper positions, unrealized P&L, allocation
    4. Equity      - equity curve vs NIFTY 50 benchmark + trade stats
    5. Manual      - manual paper trade entry with live preview
"""

import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from main import run_scan
from portfolio.paper_portfolio import PaperPortfolio
from data.data_fetcher import fetch_daily_data
from indicators.technicals import ema, rsi
from utils.helpers import format_inr

st.set_page_config(
    page_title="Paper Trading System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

GRADE_COLORS = {"A+": "#facc15", "A": "#22c55e", "B": "#f59e0b", "C": "#ef4444"}
IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Brand CSS (dark, responsive, mobile-first)
# ---------------------------------------------------------------------------

CSS = """
<style>
:root{
  --bg:#070b16;--panel:#0f1730;--panel2:#121d3c;--border:#223050;
  --accent:#38bdf8;--green:#22c55e;--red:#ef4444;--gold:#facc15;
  --amber:#f59e0b;--text:#e2e8f0;--muted:#8fa3c0;
}

.stApp{
  background:
    radial-gradient(1100px 500px at 85% -10%, rgba(56,189,248,.10), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, rgba(99,102,241,.12), transparent 60%),
    linear-gradient(165deg, #070b16 0%, #0a1120 45%, #080d1b 100%);
}

.block-container{padding:1.1rem 1.2rem 3rem; max-width:1280px; margin:0 auto;}
@media (min-width: 900px){.block-container{padding:1.4rem 2rem 4rem;}}

[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#0a0f1f 0%,#0d1428 100%);
  border-right:1px solid var(--border);
}
[data-testid="stSidebar"] *{color:var(--text);}

/* ---------- Hero ---------- */
.hero{background:linear-gradient(135deg,rgba(20,29,58,.9),rgba(15,23,46,.75));
  border:1px solid var(--border);border-radius:18px;padding:20px 22px;margin-bottom:18px;
  box-shadow:0 10px 30px rgba(0,0,0,.35);backdrop-filter:blur(6px);}
.hero-title{font-size:1.9rem;font-weight:800;letter-spacing:-.5px;line-height:1.15;
  background:linear-gradient(90deg,#f8fafc 10%,#38bdf8 90%);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;}
.hero-sub{color:var(--muted);margin:6px 0 14px;font-size:.95rem;}
.chips{display:flex;flex-wrap:wrap;gap:8px;}
.chip{font-size:.78rem;font-weight:600;padding:5px 12px;border-radius:999px;
  background:rgba(255,255,255,.06);border:1px solid var(--border);color:var(--text);}
.chip .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;}
@media (max-width:768px){.hero-title{font-size:1.35rem;}.hero{padding:16px;}}

/* ---------- Metric cards ---------- */
[data-testid="stMetric"]{
  background:linear-gradient(160deg,rgba(20,29,58,.85),rgba(15,23,46,.85));
  border:1px solid var(--border);border-radius:16px;padding:12px 16px;
  box-shadow:0 6px 20px rgba(0,0,0,.3);}
[data-testid="stMetricLabel"]{color:var(--muted);font-size:.75rem;font-weight:600;
  text-transform:uppercase;letter-spacing:.6px;}
[data-testid="stMetricValue"]{font-size:1.55rem;font-weight:800;color:#f8fafc;}
[data-testid="stMetricDelta"]{font-size:.9rem;font-weight:700;}
[data-testid="stMetricDelta"] [data-testid="stIconMaterial"]{display:none;}
@media (max-width:768px){
  [data-testid="stMetric"]{padding:9px 12px;border-radius:12px;}
  [data-testid="stMetricValue"]{font-size:1.15rem;}
}

/* ---------- Panels / cards ---------- */
.panel{background:linear-gradient(160deg,rgba(20,29,58,.9),rgba(15,23,46,.9));
  border:1px solid var(--border);border-radius:16px;padding:16px;margin-bottom:14px;
  box-shadow:0 6px 20px rgba(0,0,0,.28);height:100%;}
.panel h4{margin:0 0 10px;font-size:1.02rem;color:#f1f5f9;display:flex;align-items:center;gap:8px;}
.kv{display:flex;justify-content:space-between;font-size:.92rem;padding:3px 0;border-bottom:1px dashed rgba(255,255,255,.06);}
.kv .k{color:var(--muted);}
.kv .v{font-weight:700;color:#f8fafc;text-align:right;}

/* ---------- Colors ---------- */
.pos{color:var(--green)!important;font-weight:700;}
.neg{color:var(--red)!important;font-weight:700;}
.muted{color:var(--muted)!important;}
.gold{color:var(--gold)!important;font-weight:800;}
.up{color:var(--green);font-weight:800;}
.down{color:var(--red);font-weight:800;}

.badge{display:inline-block;font-weight:800;padding:2px 10px;border-radius:8px;font-size:.8rem;color:#0b1220;}

/* ---------- Buttons ---------- */
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{
  background:linear-gradient(135deg,#2563eb,#38bdf8);color:#fff;font-weight:700;
  border:none;border-radius:10px;box-shadow:0 6px 18px rgba(56,189,248,.25);
  transition:transform .15s ease,box-shadow .15s ease,opacity .15s;}
.stButton>button:hover,.stFormSubmitButton>button:hover{
  transform:translateY(-1px);box-shadow:0 10px 26px rgba(56,189,248,.4);opacity:.96;}
.stButton>button:active{transform:translateY(0);}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"]{gap:6px;flex-wrap:wrap;}
.stTabs [data-baseweb="tab"]{border-radius:10px;padding:8px 14px;font-weight:600;
  color:var(--text);border:1px solid transparent;}
.stTabs [data-baseweb="tab"]:hover{background:rgba(56,189,248,.08);}
.stTabs [aria-selected="true"]{background:rgba(56,189,248,.14)!important;border-color:var(--accent)!important;}

.stApp h1,.stApp h2,.stApp h3{color:#f1f5f9;letter-spacing:-.3px;}

/* ---------- Dataframes: smooth scroll on all devices ---------- */
div[data-testid="stDataFrame"]{border-radius:12px;overflow-x:auto;-webkit-overflow-scrolling:touch;}

/* ---------- Expanders ---------- */
[data-testid="stExpander"]{
  background:rgba(15,23,46,.6);border:1px solid var(--border);border-radius:14px;
  overflow:hidden;}

/* ---------- Inputs ---------- */
div[data-baseweb="select"]>div{border-radius:10px;}
.stTextInput input,.stNumberInput input{border-radius:10px;}

/* ---------- Warmups ---------- */
div[data-testid="stForm"]{border:1px dashed var(--border);border-radius:16px;padding:8px;}
</style>
"""


def _html(css_class: str, inner: str) -> str:
    return f'<div class="{css_class}">{inner}</div>'


def _badge(grade: str) -> str:
    color = GRADE_COLORS.get(grade, "#94a3b8")
    return f'<span class="badge" style="background:{color};">{grade}</span>'


# ---------------------------------------------------------------------------
# Cached data helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _cached_scan():
    return run_scan(send_alerts=True)


@st.cache_data(ttl=120, show_spinner=False)
def _cached_last_price(symbol: str):
    df = fetch_daily_data(symbol, period="1mo", interval="1d")
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[-1])


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_stock_history(symbol: str, bars: int = 130):
    df = fetch_daily_data(symbol, period="1y", interval="1d")
    if df is None or df.empty:
        return None
    df = df.tail(bars)
    out = pd.DataFrame(index=df.index)
    out["Close"] = df["Close"]
    out["EMA20"] = ema(df["Close"], 20)
    out["EMA50"] = ema(df["Close"], 50)
    out["RSI"] = rsi(df["Close"], 14)
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _nifty_df():
    df = fetch_daily_data("^NSEI", period="1y", interval="1d")
    if df is None or df.empty:
        return None
    return df["Close"].astype(float).to_frame("NIFTY 50")


def _market_status() -> tuple:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return "Closed", "Weekend", "neg"
    t = now.time()
    if time(9, 15) <= t <= time(15, 30):
        return "Open", "Trading now", "pos"
    if t < time(9, 15):
        return "Closed", "Opens at 09:15 IST", "muted"
    return "Closed", "Market closed", "muted"


def _scan_age(scan: dict) -> tuple:
    try:
        dt = datetime.fromisoformat(scan["scan_time"])
        mins = (datetime.now() - dt).total_seconds() / 60
        if mins < 1:
            return "just now", "pos"
        if mins < 60:
            return f"{mins:.0f} min ago", "pos"
        if mins < 180:
            return f"{mins / 60:.1f} h ago", "muted"
        return f"{mins / 60:.1f} h ago", "neg"
    except Exception:
        return "unknown", "muted"


def _pnl_span(value: float) -> str:
    cls = "pos" if value >= 0 else "neg"
    sign = "+" if value >= 0 else ""
    return f'<span class="{cls}">{sign}{format_inr(value)}</span>'


def get_portfolio() -> PaperPortfolio:
    return PaperPortfolio()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    market, market_note, _cls = _market_status()
    dot = {"Open": "#22c55e", "Closed": "#ef4444"}.get(market, "#94a3b8")

    with st.sidebar:
        st.markdown(
            _html("panel", f"""
            <div style="font-size:1.15rem;font-weight:800;letter-spacing:-.3px;">📈 Paper Trading</div>
            <div style="color:#8fa3c0;font-size:.8rem;margin-bottom:10px;">Indian Swing Strategy</div>
            <div class="kv"><span class="k">Market</span>
              <span class="v" style="color:{dot};">● {market} <span class="muted" style="font-weight:400">· {market_note}</span></span></div>
            """),
            unsafe_allow_html=True,
        )

        st.markdown(
            _html("panel", f"""
            <div style="font-size:.8rem;color:#8fa3c0;text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px;">⚙️ System</div>
            <div class="kv"><span class="k">Virtual capital</span><span class="v">{format_inr(config.INITIAL_CAPITAL)}</span></div>
            <div class="kv"><span class="k">Risk / trade</span><span class="v">{config.RISK_PER_TRADE_PCT*100:.1f}%</span></div>
            <div class="kv"><span class="k">Max positions</span><span class="v">{config.MAX_OPEN_POSITIONS}</span></div>
            <div class="kv"><span class="k">Min risk:reward</span><span class="v">1:{config.MIN_RISK_REWARD:.0f}</span></div>
            <div class="kv"><span class="k">Holding</span><span class="v">{config.MIN_HOLDING_DAYS}–{config.MAX_HOLDING_DAYS} d</span></div>
            <div class="kv"><span class="k">Watchlist</span><span class="v">{len(config.WATCHLIST)} stocks</span></div>
            <div class="kv"><span class="k">Telegram</span>
              <span class="v">{"✅ on" if config.TELEGRAM_ENABLED else "⚪ off"}</span></div>
            """),
            unsafe_allow_html=True,
        )

        nifty = _nifty_df()
        if nifty is not None and len(nifty) > 1:
            chg = (nifty["NIFTY 50"].iloc[-1] / nifty["NIFTY 50"].iloc[-2] - 1) * 100
            chg_cls = "pos" if chg >= 0 else "neg"
            st.markdown(
                _html("panel", f"""
                <div style="font-size:.8rem;color:#8fa3c0;text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px;">🌐 NIFTY 50</div>
                <div class="kv"><span class="k">Last</span><span class="v">{format_inr(nifty['NIFTY 50'].iloc[-1])}</span></div>
                <div class="kv"><span class="k">Day change</span><span class="{chg_cls}">{chg:+.2f}%</span></div>
                """),
                unsafe_allow_html=True,
            )

        st.markdown("### Actions")
        if st.button("🔄 Run Scan Now", width="stretch", type="primary"):
            _cached_scan.clear()
            _cached_stock_history.clear()
            _cached_last_price.clear()
            st.toast("Scan triggered…", icon="🔄")
            st.rerun()
        if st.button("♻️ Reset Paper Portfolio", width="stretch"):
            get_portfolio().reset()
            st.toast("Portfolio reset.", icon="♻️")
            st.rerun()

        st.caption("Data: yfinance (Yahoo Finance) · Paper trading only — no real orders.")


# ---------------------------------------------------------------------------
# Watchlist tab
# ---------------------------------------------------------------------------

def render_watchlist(scan: dict):
    rows = scan.get("watchlist_overview", [])
    age, age_cls = _scan_age(scan)
    st.markdown(f"#### 📋 Watchlist Overview <span class='muted' style='font-size:.85rem;font-weight:400;'>· last scan {age}</span>", unsafe_allow_html=True)

    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No watchlist data available yet.")
        return

    def _style(v):
        if v == "UPTREND":
            return "background-color: rgba(34,197,94,.18); color:#4ade80; font-weight:800;"
        if v == "NOT IN UPTREND":
            return "background-color: rgba(239,68,68,.14); color:#f87171; font-weight:800;"
        return ""

    display = df.rename(columns={
        "symbol": "Symbol", "price": "Price (₹)", "ema20": "EMA20",
        "ema50": "EMA50", "rsi": "RSI", "trend": "Trend",
        "volume_healthy": "Vol", "structure": "Structure",
    })
    if "Vol" in display.columns:
        display["Vol"] = display["Vol"].map({True: "✅", False: "❌"})
    styled = (
        display.style
        .format({"Price (₹)": lambda v: f"{v:,.2f}" if pd.notna(v) else "—",
                 "EMA20": lambda v: f"{v:,.2f}" if pd.notna(v) else "—",
                 "EMA50": lambda v: f"{v:,.2f}" if pd.notna(v) else "—",
                 "RSI": lambda v: f"{v:.1f}" if pd.notna(v) else "—"})
        .map(_style, subset=["Trend"])
    )
    st.dataframe(styled, width="stretch", hide_index=True)

    uptrends = [r for r in rows if r.get("trend") == "UPTREND"]
    st.caption(f"**{len(uptrends)}** of **{len(rows)}** symbols in uptrend → eligible for setup scanning.")

    st.markdown("#### 🔎 Stock Detail")
    selected = st.selectbox(
        "Pick a stock", [r["symbol"] for r in rows],
        format_func=lambda s: s.replace(".NS", ""),
    )
    hist = _cached_stock_history(selected)
    if hist is not None and len(hist) > 5:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.line_chart(hist[["Close", "EMA20", "EMA50"]])
        with c2:
            last_close = float(hist["Close"].iloc[-1])
            last_ema20 = float(hist["EMA20"].iloc[-1])
            last_ema50 = float(hist["EMA50"].iloc[-1])
            last_rsi = float(hist["RSI"].iloc[-1])
            above = "above" if last_close >= last_ema20 else "below"
            rsi_tag = "Overbought" if last_rsi > 75 else ("Oversold" if last_rsi < 30 else "Neutral")
            st.markdown(
                _html("panel", f"""
                <h4>🏷️ {selected.replace('.NS', '')}</h4>
                <div class="kv"><span class="k">Close</span><span class="v">{format_inr(last_close)}</span></div>
                <div class="kv"><span class="k">EMA20</span><span class="v">{format_inr(last_ema20)}</span></div>
                <div class="kv"><span class="k">EMA50</span><span class="v">{format_inr(last_ema50)}</span></div>
                <div class="kv"><span class="k">Price vs EMA20</span><span class="{('pos' if last_close>=last_ema20 else 'neg')}">{above} EMA</span></div>
                <div class="kv"><span class="k">RSI(14)</span><span class="v">{last_rsi:.1f} <span class="muted" style="font-weight:400">· {rsi_tag}</span></span></div>
                """),
                unsafe_allow_html=True,
            )
    else:
        st.caption("No history available for this symbol.")


# ---------------------------------------------------------------------------
# Setups tab
# ---------------------------------------------------------------------------

def render_setups(scan: dict, portfolio: PaperPortfolio):
    st.markdown("#### 🎯 Today's High-Quality Setups")
    actionable = [s for s in scan["setups"] if s["grade"] in config.ACTIONABLE_GRADES]
    other = [s for s in scan["setups"] if s["grade"] not in config.ACTIONABLE_GRADES]

    if not actionable:
        st.markdown(
            _html("panel", f"""
            <div style="font-size:1.15rem;font-weight:800;">🚫 NO TRADE — WAIT</div>
            <div style="color:#8fa3c0;margin-top:6px;">No A/A+ quality setups found in the latest scan.
            Capital protection comes first — no trade is better than a forced trade.</div>
            """),
            unsafe_allow_html=True,
        )
    else:
        for i in range(0, len(actionable), 2):
            cols = st.columns(2)
            for col, s in zip(cols, actionable[i:i + 2]):
                with col:
                    sizing = portfolio.calculate_position_size(s["entry"], s["stop_loss"])
                    with st.container():
                        st.markdown(
                            _html("panel", f"""
                            <h4>{s['symbol'].replace('.NS', '')} &nbsp;{_badge(s['grade'])}
                                &nbsp;<span class="muted" style="font-size:.8rem;font-weight:400;">{s['setup_type']}</span></h4>
                            <div class="kv"><span class="k">Score</span>
                              <span class="v"><span class="gold">{s['score']:.0f}</span>/100</span></div>
                            <div class="kv"><span class="k">Entry</span><span class="v">{format_inr(s['entry'])}</span></div>
                            <div class="kv"><span class="k">Stop-loss</span><span class="neg">{format_inr(s['stop_loss'])}</span></div>
                            <div class="kv"><span class="k">Target</span><span class="pos">{format_inr(s['target'])}</span></div>
                            <div class="kv"><span class="k">Reward : Risk</span><span class="v">1:{s['risk_reward']:.2f}</span></div>
                            <div style="font-size:.82rem;color:#8fa3c0;margin-top:8px;">{s['reason']}</div>
                            """),
                            unsafe_allow_html=True,
                        )
                        st.progress(min(s["score"] / 100, 1.0), text="Quality score")
                        if sizing["allowed"]:
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Qty", sizing["quantity"])
                            c2.metric("Risk", format_inr(sizing["actual_risk"]))
                            c3.metric("Cost", format_inr(sizing["cost"]))
                            key = f"open_{s['symbol']}_{s['setup_type']}"
                            if st.button(f"▶ Open Paper Trade — {s['symbol'].replace('.NS', '')}", key=key, width="stretch", type="primary"):
                                res = portfolio.open_position(
                                    symbol=s["symbol"], setup_type=s["setup_type"], grade=s["grade"],
                                    entry=s["entry"], stop_loss=s["stop_loss"], target=s["target"],
                                )
                                if res["success"]:
                                    st.toast(f"Opened {s['symbol'].split('.')[0]} — {res['position']['quantity']} @ {format_inr(s['entry'])}", icon="✅")
                                    st.rerun()
                                else:
                                    st.error(res["reason"])
                        else:
                            st.caption(f"⚠️ {sizing['reason']}")

    if other:
        with st.expander(f"Show {len(other)} lower-grade / rejected candidates"):
            df = pd.DataFrame(other)[
                ["symbol", "setup_type", "grade", "score", "entry", "stop_loss", "target", "risk_reward", "reason"]
            ].rename(columns={
                "symbol": "Symbol", "setup_type": "Setup", "grade": "Grade", "score": "Score",
                "entry": "Entry", "stop_loss": "Stop", "target": "Target", "risk_reward": "RR",
                "reason": "Reason",
            })
            st.dataframe(df.style.map(lambda g: f"color:{GRADE_COLORS.get(g,'#94a3b8')}; font-weight:800;", subset=["Grade"]),
                         width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Positions tab
# ---------------------------------------------------------------------------

def render_positions(portfolio: PaperPortfolio):
    st.markdown("#### 💼 Open Paper Positions")
    open_positions = portfolio.open_positions

    if not open_positions:
        st.markdown(
            _html("panel", "💼 **No open positions.** Capital fully protected in cash."),
            unsafe_allow_html=True,
        )
        return

    current_prices = {}
    for p in open_positions:
        current_prices[p.symbol] = _cached_last_price(p.symbol) or p.entry_price

    total_unrealized = sum((current_prices[p.symbol] - p.entry_price) * p.quantity for p in open_positions)
    invested = sum(p.entry_price * p.quantity for p in open_positions)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Invested", format_inr(invested))
    m2.metric("Unrealized P&L", format_inr(total_unrealized), delta=f"{total_unrealized / invested * 100:+.2f}%" if invested else None)
    m3.metric("Cash", format_inr(portfolio.cash))
    m4.metric("Positions", f"{len(open_positions)} / {config.MAX_OPEN_POSITIONS}")

    allocation = pd.DataFrame(
        [{"Symbol": p.symbol.replace(".NS", ""), "Invested": round(p.entry_price * p.quantity, 2)} for p in open_positions]
    )
    c_chart, c_list = st.columns([1, 1])
    with c_chart:
        st.markdown("##### Portfolio Allocation")
        st.bar_chart(allocation.set_index("Symbol"), color="#38bdf8")
    with c_list:
        st.dataframe(
            pd.DataFrame([{
                "Symbol": p.symbol.replace(".NS", ""), "Qty": p.quantity,
                "Entry": round(p.entry_price, 2), "Current": round(current_prices[p.symbol], 2),
                "Stop": round(p.stop_loss, 2), "Target": round(p.target, 2),
                "P&L": round((current_prices[p.symbol] - p.entry_price) * p.quantity, 2),
            } for p in open_positions]),
            width="stretch", hide_index=True,
        )

    portfolio.refresh_equity_curve(current_prices)

    for p in open_positions:
        cur = current_prices[p.symbol]
        pnl = (cur - p.entry_price) * p.quantity
        pnl_pct = (cur / p.entry_price - 1) * 100
        with st.container(border=True):
            cc1, cc2, cc3 = st.columns([2, 3, 2])
            with cc1:
                st.markdown(f"##### {p.symbol.replace('.NS', '')} {_badge(p.grade)}")
                st.caption(f"{p.setup_type} · opened {p.entry_date}")
            with cc2:
                st.markdown(
                    f"Entry **{format_inr(p.entry_price)}** · Stop **{format_inr(p.stop_loss)}** · "
                    f"Target **{format_inr(p.target)}** · Qty **{p.quantity}**"
                )
            with cc3:
                st.markdown(
                    f"**P&L** {_pnl_span(pnl)} <span style='color:#8fa3c0;font-size:.8rem;'>({pnl_pct:+.1f}%)</span>",
                    unsafe_allow_html=True,
                )

    st.markdown("##### 🚪 Manual Exit")
    exit_symbol = st.selectbox(
        "Select position to close",
        [p.symbol for p in open_positions],
        format_func=lambda s: s.replace(".NS", ""),
    )
    exit_default = float(current_prices[exit_symbol])
    exit_price = st.number_input("Exit price (₹)", value=exit_default, min_value=0.0, step=0.05)
    exit_reason = st.text_input("Exit reason", value="Manual exit")
    if st.button("Close Position", type="primary", width="stretch"):
        res = portfolio.close_position(exit_symbol, exit_price, exit_reason)
        if res["success"]:
            st.toast(f"Closed {exit_symbol.split('.')[0]} — P&L {res['pnl']:+,.2f}", icon="✅")
            st.rerun()
        else:
            st.error(res["reason"])

    st.divider()
    st.markdown("##### 📜 Closed Trade History")
    closed = portfolio.closed_positions
    if closed:
        hist_df = pd.DataFrame([{
            "Symbol": p.symbol.replace(".NS", ""), "Setup": p.setup_type, "Grade": p.grade,
            "Entry": p.entry_price, "Exit": p.exit_price, "Qty": p.quantity, "P&L": p.pnl,
            "Entry Date": p.entry_date, "Exit Date": p.exit_date, "Reason": p.exit_reason,
        } for p in list(reversed(closed))[:15]])
        styled = (hist_df.style
                  .format({"Entry": lambda v: f"{v:,.2f}", "Exit": lambda v: f"{v:,.2f}",
                           "P&L": lambda v: f"{v:+,.2f}"})
                  .map(lambda v: "color:#22c55e;font-weight:700;" if v > 0 else ("color:#ef4444;font-weight:700;" if v < 0 else ""), subset=["P&L"]))
        st.dataframe(styled, width="stretch", hide_index=True)
    else:
        st.caption("No closed trades yet.")


# ---------------------------------------------------------------------------
# Equity tab
# ---------------------------------------------------------------------------

def render_equity(portfolio: PaperPortfolio):
    st.markdown("#### 📈 Portfolio Equity Curve")
    current_prices = {
        p.symbol: (_cached_last_price(p.symbol) or p.entry_price) for p in portfolio.open_positions
    }
    equity_now = portfolio.mark_to_market_equity(current_prices)
    portfolio.refresh_equity_curve(current_prices)

    closed = portfolio.closed_positions
    wins = [p.pnl for p in closed if p.pnl and p.pnl > 0]
    losses = [p.pnl for p in closed if p.pnl and p.pnl < 0]
    total_closed_pnl = sum(wins) + sum(losses)
    win_rate = len(wins) / len(closed) * 100 if closed else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (float("inf") if wins else 0.0)

    first_equity = portfolio.equity_curve[0].equity if portfolio.equity_curve else equity_now
    start_return = (equity_now / first_equity - 1) * 100 if first_equity else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current Equity", format_inr(equity_now), delta=f"{start_return:+.2f}% since start")
    m2.metric("Realized P&L", format_inr(portfolio.realized_pnl()), delta=f"{total_closed_pnl:+,.2f}")
    m3.metric("Cash", format_inr(portfolio.cash))
    m4.metric("Win Rate", f"{win_rate:.0f}%" if closed else "—")

    chart_toggle = st.toggle("Compare with NIFTY 50", value=False)
    curve_df = pd.DataFrame([{"Date": e.date, "Equity": e.equity} for e in portfolio.equity_curve])
    if not curve_df.empty:
        curve_df["Date"] = pd.to_datetime(curve_df["Date"])
        curve_df = curve_df.sort_values("Date").set_index("Date")
        norm = curve_df / curve_df.iloc[0] * 100

        if chart_toggle:
            nifty = _nifty_df()
            if nifty is not None:
                nifty = nifty.copy()
                nifty.index = pd.to_datetime(nifty.index)
                nifty = nifty[nifty.index >= norm.index.min()]
                nifty = nifty / nifty.iloc[0] * 100
                comp = norm.join(nifty, how="inner").rename(columns={"Equity": "Portfolio"})
                if not comp.empty:
                    st.line_chart(comp)
                    last_comp = comp.iloc[-1]
                    rel = last_comp["Portfolio"] / last_comp["NIFTY 50"] * 100 - 100
                    out = "outperforming" if rel >= 0 else "underperforming"
                    st.caption(f"Portfolio is **{out}** NIFTY 50 by **{abs(rel):.1f}%** since start.")
                else:
                    st.line_chart(norm)
        else:
            st.area_chart(norm, color="#38bdf8")

    st.divider()
    st.markdown("##### 🧮 Performance Stats")
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.metric("Total Trades", len(closed))
    s2.metric("Avg Win", format_inr(avg_win) if wins else "—")
    s3.metric("Avg Loss", format_inr(avg_loss) if losses else "—")
    s4.metric("Profit Factor", f"{profit_factor:.2f}" if closed else "—")
    s5.metric("Best Trade", format_inr(max(wins, default=0)) if wins else "—")
    s6.metric("Worst Trade", format_inr(min(losses, default=0)) if losses else "—")

    if not closed:
        st.info("No closed trades yet — stats will populate once positions are closed.")


# ---------------------------------------------------------------------------
# Manual trade tab
# ---------------------------------------------------------------------------

def render_manual(portfolio: PaperPortfolio):
    st.markdown("#### ✍️ Manual Paper Trade Entry")
    st.caption("For discretionary trades outside the automated scan, still governed by the same risk rules.")

    with st.form("manual_trade_form"):
        c1, c2 = st.columns(2)
        with c1:
            symbol = st.selectbox("Symbol", config.WATCHLIST, format_func=lambda s: s.replace(".NS", ""))
            setup_type = st.selectbox("Setup Type", ["Pullback", "Breakout", "Manual"])
            grade = st.selectbox("Trade Grade", ["A+", "A", "B", "C"])
        with c2:
            entry = st.number_input("Entry Price (₹)", min_value=0.0, step=0.05, value=0.0)
            stop_loss = st.number_input("Stop-Loss (₹)", min_value=0.0, step=0.05, value=0.0)
            target = st.number_input("Target Price (₹)", min_value=0.0, step=0.05, value=0.0)
        preview = st.form_submit_button("Preview Position Size", width="stretch")

    if preview:
        sizing = portfolio.calculate_position_size(entry, stop_loss)
        last = _cached_last_price(symbol)
        if last:
            st.markdown(f"Last close: **{format_inr(last)}**")

        if not sizing["allowed"]:
            st.error(sizing["reason"])
        else:
            rr = (target - entry) / (entry - stop_loss) if entry > stop_loss else 0.0
            ok = rr >= config.MIN_RISK_REWARD and (last is None or entry > 0)
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Suggested Qty", sizing["quantity"])
            s2.metric("Risk", format_inr(sizing["actual_risk"]))
            s3.metric("Cost", format_inr(sizing["cost"]))
            s4.metric("Risk:Reward", f"1:{rr:.2f}")
            if rr and rr < config.MIN_RISK_REWARD:
                st.warning(f"⚠️ RR is below the minimum 1:{config.MIN_RISK_REWARD:.0f}. Reconsider this trade.")

            if st.button("Confirm & Open Manual Position", type="primary", width="stretch"):
                res = portfolio.open_position(
                    symbol=symbol, setup_type=setup_type, grade=grade,
                    entry=entry, stop_loss=stop_loss, target=target,
                )
                if res["success"]:
                    st.toast(f"Opened {symbol.split('.')[0]} — {res['position']['quantity']} @ {format_inr(entry)}", icon="✅")
                    st.rerun()
                else:
                    st.error(res["reason"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.markdown(CSS, unsafe_allow_html=True)
    render_sidebar()

    market, market_note, market_cls = _market_status()
    dot = {"Open": "#22c55e", "Closed": "#ef4444"}.get(market, "#94a3b8")

    with st.spinner("Scanning watchlist…"):
        scan = _cached_scan()

    age, age_cls = _scan_age(scan)
    portfolio = get_portfolio()

    st.markdown(
        _html("hero", f"""
        <div class="hero-title">📈 Paper Trading System</div>
        <div class="hero-sub">Indian Swing Strategy · Cash equity · Daily timeframe · {format_inr(config.MAX_RISK_PER_TRADE)} risk per trade</div>
        <div class="chips">
          <span class="chip"><span class="dot" style="background:{dot};"></span>Market {market.lower()}</span>
          <span class="chip">🕐 Last scan {age}</span>
          <span class="chip">🎯 {scan['actionable_count']} actionable setups</span>
          <span class="chip">💼 {len(portfolio.open_positions)} positions</span>
          <span class="chip">🤖 Telegram {'on' if config.TELEGRAM_ENABLED else 'off'}</span>
        </div>
        """),
        unsafe_allow_html=True,
    )

    equity_now = portfolio.mark_to_market_equity(
        {p.symbol: (_cached_last_price(p.symbol) or p.entry_price) for p in portfolio.open_positions}
    )
    first_equity = portfolio.equity_curve[0].equity if portfolio.equity_curve else equity_now
    unrealized = sum(
        ((_cached_last_price(p.symbol) or p.entry_price) - p.entry_price) * p.quantity
        for p in portfolio.open_positions
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Current Equity", format_inr(equity_now),
              delta=f"{(equity_now / first_equity - 1) * 100:+.2f}%" if first_equity else None)
    m2.metric("Cash", format_inr(portfolio.cash))
    m3.metric("Realized P&L", format_inr(portfolio.realized_pnl()))
    m4.metric("Unrealized P&L", format_inr(unrealized))
    m5.metric("Open / Max", f"{len(portfolio.open_positions)} / {config.MAX_OPEN_POSITIONS}")

    tab_w, tab_s, tab_p, tab_e, tab_m = st.tabs(
        ["📋 Watchlist", "🎯 Setups", "💼 Positions", "📈 Equity", "✍️ Manual"]
    )
    with tab_w:
        render_watchlist(scan)
    with tab_s:
        render_setups(scan, portfolio)
    with tab_p:
        render_positions(portfolio)
    with tab_e:
        render_equity(portfolio)
    with tab_m:
        render_manual(portfolio)

    st.markdown(
        "<div style='text-align:center;color:#8fa3c0;font-size:.75rem;margin-top:28px;'>"
        "Paper trading only · Data via yfinance · No trade is better than a forced trade</div>",
        unsafe_allow_html=True,
    )


main()