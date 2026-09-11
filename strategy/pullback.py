"""
strategy/pullback.py
----------------------
Entry Setup 1 - Pullback to the 20 EMA / support in an established uptrend,
confirmed by a bullish candle, with RSI holding above 50.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from strategy.trend_filter import TrendStatus
from indicators.technicals import swing_low
import config


@dataclass
class PullbackSetup:
    valid: bool
    entry: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0
    risk_reward: float = 0.0
    reason: str = ""


def _is_bullish_confirmation_candle(bar: pd.Series, prev_close: float) -> bool:
    """
    A simple, robust bullish-confirmation definition:
      - Candle closes green (Close > Open)
      - Closes above the previous close (reclaiming momentum)
      - Close is in the upper half of the day's range (not a weak close)
    """
    open_, close, high, low = bar["Open"], bar["Close"], bar["High"], bar["Low"]
    if close <= open_:
        return False
    if close <= prev_close:
        return False
    day_range = high - low
    if day_range <= 0:
        return False
    close_position = (close - low) / day_range
    return close_position >= 0.5


def detect_pullback(df: pd.DataFrame, trend: TrendStatus) -> PullbackSetup:
    """
    Looks for a valid pullback setup on the most recent bar.
    Requires the trend filter to already have passed.
    """
    if not trend.passes_trend_filter:
        return PullbackSetup(valid=False, reason="Trend filter not passed")

    if len(df) < config.SWING_LOOKBACK + 2:
        return PullbackSetup(valid=False, reason="Not enough history for swing low")

    latest = df.iloc[-1]
    prev_close = float(df.iloc[-2]["Close"])

    # RSI must hold above 50 during the pullback (not breaking down)
    if trend.rsi < 50:
        return PullbackSetup(valid=False, reason=f"RSI below 50 ({trend.rsi:.1f}) - momentum weak")

    # Price must have pulled back close to the 20 EMA (or support), not chasing an extended move.
    distance_to_ema = abs(latest["Close"] - trend.ema_fast) / trend.ema_fast
    near_ema = distance_to_ema <= config.PULLBACK_EMA_PROXIMITY_PCT
    # Also accept pullbacks where the LOW of the day tagged the EMA/support even if close is a bit above
    low_tagged_ema = latest["Low"] <= trend.ema_fast * (1 + config.PULLBACK_EMA_PROXIMITY_PCT)

    if not (near_ema or low_tagged_ema):
        return PullbackSetup(valid=False, reason="Price has not pulled back to 20 EMA / support")

    # Bullish confirmation candle on the latest bar
    if not _is_bullish_confirmation_candle(latest, prev_close):
        return PullbackSetup(valid=False, reason="No bullish confirmation candle yet")

    # Entry: break above the confirmation candle's high (buy-stop trigger)
    entry = float(latest["High"]) * 1.001  # tiny buffer above high to trigger the stop-entry

    # Stop-loss: below the recent swing low (logical support), excluding today
    sl_level = swing_low(df, lookback=config.SWING_LOOKBACK, exclude_last=0)
    stop_loss = sl_level * 0.998  # small buffer below swing low

    if stop_loss <= 0 or stop_loss >= entry:
        return PullbackSetup(valid=False, reason="Invalid stop-loss (below zero or above entry)")

    risk_per_share = entry - stop_loss
    if risk_per_share <= 0:
        return PullbackSetup(valid=False, reason="Non-positive risk per share")

    target = entry + (risk_per_share * config.MIN_RISK_REWARD)
    rr = (target - entry) / risk_per_share

    if rr < config.MIN_RISK_REWARD:
        return PullbackSetup(valid=False, reason=f"Risk:Reward {rr:.2f} below minimum {config.MIN_RISK_REWARD}")

    return PullbackSetup(
        valid=True,
        entry=round(entry, 2),
        stop_loss=round(stop_loss, 2),
        target=round(target, 2),
        risk_reward=round(rr, 2),
        reason="Valid pullback setup",
    )
