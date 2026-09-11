"""
strategy/trend_filter.py
--------------------------
The mandatory trend gate. No pullback or breakout setup is considered
unless this filter passes. This encodes:
    - Price > 20 EMA > 50 EMA
    - Prefer higher highs / higher lows structure
    - RSI(14) preferably 50-65, hard avoid > 75
    - Healthy volume
"""

from dataclasses import dataclass

import pandas as pd

from indicators.technicals import higher_highs_higher_lows
import config


@dataclass
class TrendStatus:
    is_uptrend: bool           # Hard requirement: Price > EMA20 > EMA50
    price: float
    ema_fast: float
    ema_slow: float
    rsi: float
    rsi_in_ideal_zone: bool    # 50-65
    rsi_overextended: bool     # > 75 (disqualifying)
    volume_healthy: bool
    structure_hh_hl: bool      # Higher highs / higher lows (preferred, not mandatory)
    notes: str = ""

    @property
    def passes_trend_filter(self) -> bool:
        """
        Hard requirements to even be considered for a trade:
          - uptrend (price > ema20 > ema50)
          - RSI not overextended (> 75)
          - volume healthy
        Structure (HH/HL) and the ideal RSI zone are quality boosters
        handled by the scorer, not hard blockers, since real markets
        rarely produce textbook-perfect structure every day.
        """
        return self.is_uptrend and (not self.rsi_overextended) and self.volume_healthy


def evaluate_trend(df: pd.DataFrame) -> TrendStatus:
    """
    Evaluate the trend filter on the latest bar of an indicator-enriched
    DataFrame (must already contain EMA_fast, EMA_slow, RSI, AvgVolume).
    """
    latest = df.iloc[-1]

    price = float(latest["Close"])
    ema_fast = float(latest["EMA_fast"]) if pd.notna(latest["EMA_fast"]) else float("nan")
    ema_slow = float(latest["EMA_slow"]) if pd.notna(latest["EMA_slow"]) else float("nan")
    rsi_val = float(latest["RSI"]) if pd.notna(latest["RSI"]) else float("nan")
    avg_vol = float(latest["AvgVolume"]) if pd.notna(latest["AvgVolume"]) else float("nan")
    volume = float(latest["Volume"])

    notes = []

    if any(pd.isna(x) for x in [ema_fast, ema_slow, rsi_val, avg_vol]):
        return TrendStatus(
            is_uptrend=False, price=price, ema_fast=ema_fast, ema_slow=ema_slow,
            rsi=rsi_val, rsi_in_ideal_zone=False, rsi_overextended=False,
            volume_healthy=False, structure_hh_hl=False,
            notes="Insufficient indicator history",
        )

    is_uptrend = price > ema_fast > ema_slow
    if not is_uptrend:
        notes.append("Trend structure broken (Price>EMA20>EMA50 not satisfied)")

    rsi_ideal = config.RSI_IDEAL_MIN <= rsi_val <= config.RSI_IDEAL_MAX
    rsi_overextended = rsi_val > config.RSI_HARD_CEILING
    if rsi_overextended:
        notes.append(f"RSI overextended ({rsi_val:.1f} > {config.RSI_HARD_CEILING})")

    volume_healthy = volume >= (avg_vol * config.VOLUME_HEALTHY_MULTIPLE)
    if not volume_healthy:
        notes.append("Volume below healthy threshold")

    structure = higher_highs_higher_lows(df, lookback=config.SWING_LOOKBACK * 2)

    return TrendStatus(
        is_uptrend=is_uptrend,
        price=price,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi_val,
        rsi_in_ideal_zone=rsi_ideal,
        rsi_overextended=rsi_overextended,
        volume_healthy=volume_healthy,
        structure_hh_hl=structure,
        notes="; ".join(notes) if notes else "OK",
    )
