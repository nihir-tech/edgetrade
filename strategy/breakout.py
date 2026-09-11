"""
strategy/breakout.py
----------------------
Entry Setup 2 - Breakout above a clear resistance level on significantly
higher volume, with a preference for a breakout + successful retest before
entry (higher quality, lower risk).
"""

from dataclasses import dataclass

import pandas as pd

from strategy.trend_filter import TrendStatus
from indicators.technicals import swing_high, swing_low
import config


@dataclass
class BreakoutSetup:
    valid: bool
    entry: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0
    risk_reward: float = 0.0
    is_retest: bool = False
    reason: str = ""


def detect_breakout(df: pd.DataFrame, trend: TrendStatus) -> BreakoutSetup:
    """
    Looks for a valid breakout (or breakout+retest) setup on the most recent bar.
    Requires the trend filter to already have passed.
    """
    if not trend.passes_trend_filter:
        return BreakoutSetup(valid=False, reason="Trend filter not passed")

    if len(df) < config.SWING_LOOKBACK + config.RETEST_LOOKBACK + 2:
        return BreakoutSetup(valid=False, reason="Not enough history")

    latest = df.iloc[-1]
    avg_vol = float(latest["AvgVolume"])
    volume = float(latest["Volume"])

    # Resistance = highest high of the lookback window BEFORE today
    resistance = swing_high(df, lookback=config.SWING_LOOKBACK, exclude_last=1)

    if pd.isna(resistance) or resistance <= 0:
        return BreakoutSetup(valid=False, reason="Could not establish a resistance level")

    breakout_today = latest["Close"] > resistance and volume >= (avg_vol * config.BREAKOUT_VOLUME_MULTIPLE)

    if breakout_today:
        entry = float(latest["Close"]) * 1.002  # enter slightly above breakout close on confirmation
        stop_loss = resistance * 0.995          # structure-based stop just below the breakout level
        risk_per_share = entry - stop_loss
        if risk_per_share <= 0:
            return BreakoutSetup(valid=False, reason="Invalid risk on fresh breakout")

        target = entry + risk_per_share * config.MIN_RISK_REWARD
        rr = (target - entry) / risk_per_share
        if rr < config.MIN_RISK_REWARD:
            return BreakoutSetup(valid=False, reason=f"RR {rr:.2f} below minimum on fresh breakout")

        return BreakoutSetup(
            valid=True,
            entry=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            target=round(target, 2),
            risk_reward=round(rr, 2),
            is_retest=False,
            reason="Fresh breakout on strong volume (no retest yet - lower conviction, size cautiously)",
        )

    # --- Look for a breakout-then-retest within the recent RETEST_LOOKBACK bars ---
    recent = df.iloc[-(config.RETEST_LOOKBACK + 1):]
    prior_resistance = swing_high(
        df, lookback=config.SWING_LOOKBACK, exclude_last=config.RETEST_LOOKBACK + 1
    )
    if pd.isna(prior_resistance) or prior_resistance <= 0:
        return BreakoutSetup(valid=False, reason="No breakout or retest detected")

    broke_out = (recent["Close"] > prior_resistance).any()
    if not broke_out:
        return BreakoutSetup(valid=False, reason="No breakout or retest detected")

    # Did price come back down to retest the breakout level and hold above it?
    retest_low = float(recent["Low"].min())
    held_level = retest_low >= prior_resistance * 0.98  # allow a small wick below
    reclaimed = float(latest["Close"]) > prior_resistance and float(latest["Close"]) > float(latest["Open"])

    if held_level and reclaimed:
        entry = float(latest["High"]) * 1.001
        stop_loss = retest_low * 0.998
        risk_per_share = entry - stop_loss
        if risk_per_share <= 0:
            return BreakoutSetup(valid=False, reason="Invalid risk on retest setup")

        target = entry + risk_per_share * config.MIN_RISK_REWARD
        rr = (target - entry) / risk_per_share
        if rr < config.MIN_RISK_REWARD:
            return BreakoutSetup(valid=False, reason=f"RR {rr:.2f} below minimum on retest")

        return BreakoutSetup(
            valid=True,
            entry=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            target=round(target, 2),
            risk_reward=round(rr, 2),
            is_retest=True,
            reason="Breakout + successful retest (high conviction)",
        )

    return BreakoutSetup(valid=False, reason="Breakout found but retest not yet confirmed")
