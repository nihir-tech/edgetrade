"""
indicators/technicals.py
--------------------------
Pure pandas/numpy implementations of the indicators the strategy needs:
EMA(20), EMA(50), RSI(14), rolling average volume, and simple swing
high/low detection. Implemented from scratch (no ta-lib dependency
required) so the system stays lightweight and reliable.
"""

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's RSI (the standard RSI formula).
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    # Where avg_loss is 0 and avg_gain > 0, RSI is 100
    rsi_val = rsi_val.where(avg_loss != 0, 100)
    return rsi_val


def average_volume(series: pd.Series, period: int = 20) -> pd.Series:
    """Rolling simple average of volume, excluding the current bar (shifted)."""
    return series.rolling(window=period, min_periods=period).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range - useful as a volatility-based stop-loss fallback."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def swing_low(df: pd.DataFrame, lookback: int, exclude_last: int = 0) -> float:
    """
    Lowest low over the last `lookback` bars, optionally excluding the most
    recent `exclude_last` bars (e.g. to find the swing low before today).
    """
    window = df["Low"].iloc[-(lookback + exclude_last): len(df) - exclude_last] \
        if exclude_last else df["Low"].iloc[-lookback:]
    if window.empty:
        return float("nan")
    return float(window.min())


def swing_high(df: pd.DataFrame, lookback: int, exclude_last: int = 0) -> float:
    """Highest high over the last `lookback` bars, optionally excluding recent bars."""
    window = df["High"].iloc[-(lookback + exclude_last): len(df) - exclude_last] \
        if exclude_last else df["High"].iloc[-lookback:]
    if window.empty:
        return float("nan")
    return float(window.max())


def higher_highs_higher_lows(df: pd.DataFrame, lookback: int = 20, segment: int = 5) -> bool:
    """
    Very simple structure check: compare the highest-high and lowest-low of
    the most recent `segment`-bar block against the previous `segment`-bar
    block within the lookback window. Returns True if both the high and the
    low have stepped up (a rough proxy for "higher highs, higher lows").
    """
    if len(df) < lookback + segment:
        return False

    recent = df.iloc[-lookback:]
    if len(recent) < 2 * segment:
        return False

    first_block = recent.iloc[:segment]
    last_block = recent.iloc[-segment:]

    higher_high = last_block["High"].max() > first_block["High"].max()
    higher_low = last_block["Low"].min() > first_block["Low"].min()

    return bool(higher_high and higher_low)


def add_all_indicators(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
    vol_avg_period: int = 20,
) -> pd.DataFrame:
    """
    Returns a copy of df with all indicator columns appended:
    EMA_fast, EMA_slow, RSI, AvgVolume, ATR
    """
    out = df.copy()
    out["EMA_fast"] = ema(out["Close"], ema_fast)
    out["EMA_slow"] = ema(out["Close"], ema_slow)
    out["RSI"] = rsi(out["Close"], rsi_period)
    out["AvgVolume"] = average_volume(out["Volume"], vol_avg_period)
    out["ATR"] = atr(out, 14)
    return out
