"""
strategy/scorer.py
---------------------
Assigns a Trade Quality Score (A+, A, B, C, NO TRADE) to any candidate
setup (pullback or breakout) based on:
    Trend quality, EMA alignment, Support/Resistance quality, RSI,
    Volume, Entry quality, Stop-loss quality, Risk/Reward, and a proxy
    for sector strength (relative volume/momentum vs peers, if supplied).

Only A / A+ setups should be surfaced as actionable alerts.
"""

from dataclasses import dataclass, field
from typing import Optional

from strategy.trend_filter import TrendStatus
import config


@dataclass
class ScoreResult:
    grade: str                     # "A+", "A", "B", "C", "NO TRADE"
    score: float                   # 0-100
    breakdown: dict = field(default_factory=dict)
    actionable: bool = False


def _grade_from_score(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 78:
        return "A"
    if score >= 62:
        return "B"
    if score >= 45:
        return "C"
    return "NO TRADE"


def score_setup(
    trend: TrendStatus,
    risk_reward: float,
    is_retest: Optional[bool] = None,
    sector_strength_pct: Optional[float] = None,
) -> ScoreResult:
    """
    Weighted scoring across 9 dimensions (each contributes points, max 100):
        Trend quality (structure HH/HL)      : 12
        EMA alignment (price>20>50, strength) : 12
        RSI quality                           : 12
        Volume quality                        : 12
        Support/Resistance & entry quality    : 14
        Stop-loss quality (tight & logical)   : 12
        Risk:Reward                           : 16
        Sector strength (optional, else avg)  : 10
    """
    breakdown = {}

    # 1. Trend / structure quality (HH/HL)
    breakdown["trend_structure"] = 12.0 if trend.structure_hh_hl else 6.0

    # 2. EMA alignment quality - reward separation (strength) but not too extended
    ema_gap_pct = (trend.ema_fast - trend.ema_slow) / trend.ema_slow if trend.ema_slow else 0
    if trend.is_uptrend and 0.01 <= ema_gap_pct <= 0.08:
        breakdown["ema_alignment"] = 12.0
    elif trend.is_uptrend:
        breakdown["ema_alignment"] = 8.0
    else:
        breakdown["ema_alignment"] = 0.0

    # 3. RSI quality
    if trend.rsi_in_ideal_zone:
        breakdown["rsi"] = 12.0
    elif 45 <= trend.rsi <= 70 and not trend.rsi_overextended:
        breakdown["rsi"] = 8.0
    elif not trend.rsi_overextended:
        breakdown["rsi"] = 4.0
    else:
        breakdown["rsi"] = 0.0

    # 4. Volume quality
    breakdown["volume"] = 12.0 if trend.volume_healthy else 3.0

    # 5. Support/Resistance & entry quality (retest > fresh breakout > plain pullback)
    if is_retest is True:
        breakdown["entry_quality"] = 14.0
    elif is_retest is False:
        breakdown["entry_quality"] = 9.0   # fresh breakout, no retest yet
    else:
        breakdown["entry_quality"] = 11.0  # pullback setup

    # 6. Stop-loss quality - tighter, logical stops score higher.
    #    We proxy this via risk_reward: a very low RR usually means a sloppy/wide stop.
    if risk_reward >= 3.0:
        breakdown["stop_loss_quality"] = 12.0
    elif risk_reward >= config.MIN_RISK_REWARD:
        breakdown["stop_loss_quality"] = 9.0
    else:
        breakdown["stop_loss_quality"] = 0.0

    # 7. Risk:Reward
    if risk_reward >= 3.0:
        breakdown["risk_reward"] = 16.0
    elif risk_reward >= 2.5:
        breakdown["risk_reward"] = 13.0
    elif risk_reward >= config.MIN_RISK_REWARD:
        breakdown["risk_reward"] = 10.0
    else:
        breakdown["risk_reward"] = 0.0

    # 8. Sector strength (optional signal - if not supplied, award a neutral midpoint)
    if sector_strength_pct is None:
        breakdown["sector_strength"] = 5.0
    elif sector_strength_pct >= 1.0:
        breakdown["sector_strength"] = 10.0
    elif sector_strength_pct >= 0.0:
        breakdown["sector_strength"] = 6.0
    else:
        breakdown["sector_strength"] = 2.0

    total = sum(breakdown.values())
    grade = _grade_from_score(total)

    # Hard override: if the trend filter itself failed or RR is below minimum,
    # this can never be actionable regardless of points accumulated elsewhere.
    if not trend.passes_trend_filter or risk_reward < config.MIN_RISK_REWARD:
        grade = "NO TRADE"
        total = min(total, 44.0)

    return ScoreResult(
        grade=grade,
        score=round(total, 1),
        breakdown=breakdown,
        actionable=grade in config.ACTIONABLE_GRADES,
    )
