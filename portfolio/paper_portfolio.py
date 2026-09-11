"""
portfolio/paper_portfolio.py
------------------------------
Manages the virtual paper-trading portfolio: capital, open positions,
closed trade history, position sizing, and equity curve tracking.
State is persisted to a JSON file so the dashboard and any scheduled
scan script share the same portfolio.
"""

import json
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional

import config


@dataclass
class Position:
    symbol: str
    setup_type: str          # "Pullback" or "Breakout"
    grade: str                # A+/A/B/C
    entry_price: float
    stop_loss: float
    target: float
    quantity: int
    entry_date: str           # ISO date string
    risk_amount: float        # ₹ risked at entry (qty * (entry - stop))
    status: str = "OPEN"      # OPEN / CLOSED
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None


@dataclass
class EquityPoint:
    date: str
    equity: float


class PaperPortfolio:
    """
    A simple, file-persisted paper portfolio. All money math uses the
    configured INITIAL_CAPITAL and RISK_PER_TRADE_PCT from config.py.
    """

    def __init__(self, state_file: str = config.PORTFOLIO_STATE_FILE):
        self.state_file = state_file
        self.cash: float = config.INITIAL_CAPITAL
        self.positions: list[Position] = []       # open + closed
        self.equity_curve: list[EquityPoint] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                self.cash = data.get("cash", config.INITIAL_CAPITAL)
                self.positions = [Position(**p) for p in data.get("positions", [])]
                self.equity_curve = [EquityPoint(**e) for e in data.get("equity_curve", [])]
            except Exception:
                # Corrupt or incompatible state file - start fresh rather than crash.
                self.cash = config.INITIAL_CAPITAL
                self.positions = []
                self.equity_curve = []
        if not self.equity_curve:
            self.equity_curve = [EquityPoint(date=str(date.today()), equity=self.cash)]

    def _save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        data = {
            "cash": self.cash,
            "positions": [asdict(p) for p in self.positions],
            "equity_curve": [asdict(e) for e in self.equity_curve],
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------
    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.status == "OPEN"]

    @property
    def closed_positions(self) -> list[Position]:
        return [p for p in self.positions if p.status == "CLOSED"]

    def invested_value(self) -> float:
        return sum(p.entry_price * p.quantity for p in self.open_positions)

    def realized_pnl(self) -> float:
        return sum(p.pnl or 0 for p in self.closed_positions)

    def mark_to_market_equity(self, current_prices: dict) -> float:
        """
        current_prices: {symbol: last_price}. Falls back to entry price if
        a live price isn't available (e.g. data fetch failed).
        """
        open_value = 0.0
        for p in self.open_positions:
            last_price = current_prices.get(p.symbol, p.entry_price)
            open_value += last_price * p.quantity
        return self.cash + open_value

    # ------------------------------------------------------------------
    # Position sizing (the critical risk-management calculation)
    # ------------------------------------------------------------------
    def calculate_position_size(self, entry: float, stop_loss: float) -> dict:
        """
        Position size = (Capital x Risk%) / (Entry - Stop Loss)

        Returns a dict with quantity, actual risk, max_loss, and whether
        the trade is even permissible under current capital/position limits.
        """
        risk_capital = (
            self.mark_to_market_equity({}) if config.USE_LIVE_EQUITY_FOR_RISK
            else config.INITIAL_CAPITAL
        )
        max_risk_rupees = risk_capital * config.RISK_PER_TRADE_PCT

        risk_per_share = entry - stop_loss
        if risk_per_share <= 0:
            return {"allowed": False, "reason": "Stop-loss must be below entry", "quantity": 0}

        raw_qty = max_risk_rupees / risk_per_share
        quantity = math.floor(raw_qty)

        if quantity < 1:
            return {
                "allowed": False,
                "reason": "Risk per share too large for ₹500 risk budget (would need <1 share)",
                "quantity": 0,
            }

        cost = quantity * entry
        if cost > self.cash:
            # Reduce quantity to what cash actually allows, capital protection first.
            affordable_qty = math.floor(self.cash / entry)
            quantity = min(quantity, affordable_qty)
            if quantity < 1:
                return {"allowed": False, "reason": "Insufficient cash", "quantity": 0}

        actual_risk = quantity * risk_per_share
        max_loss = actual_risk

        if len(self.open_positions) >= config.MAX_OPEN_POSITIONS:
            return {
                "allowed": False,
                "reason": f"Max open positions ({config.MAX_OPEN_POSITIONS}) reached",
                "quantity": 0,
            }

        return {
            "allowed": True,
            "quantity": quantity,
            "cost": round(quantity * entry, 2),
            "actual_risk": round(actual_risk, 2),
            "max_loss": round(max_loss, 2),
            "risk_budget": round(max_risk_rupees, 2),
        }

    # ------------------------------------------------------------------
    # Trade actions
    # ------------------------------------------------------------------
    def open_position(
        self, symbol: str, setup_type: str, grade: str,
        entry: float, stop_loss: float, target: float,
    ) -> dict:
        """Attempts to open a new paper position, respecting all risk rules."""

        # Never average down / duplicate an existing open position in the same symbol.
        if any(p.symbol == symbol for p in self.open_positions):
            return {"success": False, "reason": f"Already holding an open position in {symbol}"}

        sizing = self.calculate_position_size(entry, stop_loss)
        if not sizing["allowed"]:
            return {"success": False, "reason": sizing["reason"]}

        qty = sizing["quantity"]
        cost = qty * entry

        position = Position(
            symbol=symbol,
            setup_type=setup_type,
            grade=grade,
            entry_price=entry,
            stop_loss=stop_loss,
            target=target,
            quantity=qty,
            entry_date=str(date.today()),
            risk_amount=sizing["actual_risk"],
        )
        self.positions.append(position)
        self.cash -= cost
        self._record_equity_point()
        self._save()

        return {"success": True, "position": asdict(position), "sizing": sizing}

    def close_position(self, symbol: str, exit_price: float, reason: str = "Manual exit") -> dict:
        """Closes an open position and books realized P&L."""
        for p in self.open_positions:
            if p.symbol == symbol:
                p.status = "CLOSED"
                p.exit_price = exit_price
                p.exit_date = str(date.today())
                p.exit_reason = reason
                p.pnl = round((exit_price - p.entry_price) * p.quantity, 2)
                self.cash += exit_price * p.quantity
                self._record_equity_point()
                self._save()
                return {"success": True, "pnl": p.pnl}
        return {"success": False, "reason": f"No open position found for {symbol}"}

    def update_stop_loss(self, symbol: str, new_stop: float) -> dict:
        """
        Allows tightening a stop-loss only (never widening it), per the
        'never move stop-loss further away' rule.
        """
        for p in self.open_positions:
            if p.symbol == symbol:
                if new_stop <= p.stop_loss:
                    return {"success": False, "reason": "New stop must be tighter (higher), never further away"}
                p.stop_loss = new_stop
                self._save()
                return {"success": True}
        return {"success": False, "reason": f"No open position found for {symbol}"}

    def _record_equity_point(self, current_prices: Optional[dict] = None):
        equity = self.mark_to_market_equity(current_prices or {})
        today = str(date.today())
        if self.equity_curve and self.equity_curve[-1].date == today:
            self.equity_curve[-1].equity = equity
        else:
            self.equity_curve.append(EquityPoint(date=today, equity=equity))

    def refresh_equity_curve(self, current_prices: dict):
        """Call once per dashboard refresh to mark open positions to market."""
        self._record_equity_point(current_prices)
        self._save()

    def reset(self):
        """Wipes the paper portfolio back to initial capital (fresh start)."""
        self.cash = config.INITIAL_CAPITAL
        self.positions = []
        self.equity_curve = [EquityPoint(date=str(date.today()), equity=self.cash)]
        self._save()
