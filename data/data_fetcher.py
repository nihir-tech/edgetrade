"""
data/data_fetcher.py
---------------------
Fetches daily OHLCV data for watchlist symbols using yfinance.
Handles missing / insufficient data gracefully so the rest of the
pipeline never crashes on a bad ticker.
"""

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Minimum number of daily bars required for indicators (50 EMA + buffer) to be meaningful.
MIN_REQUIRED_BARS = 60


def fetch_daily_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV data for a single symbol.

    Returns a cleaned DataFrame with columns:
        Open, High, Low, Close, Volume
    indexed by date (ascending), or None if data is missing/insufficient.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001 - we want to swallow any network/lib error here
        logger.warning("Failed to fetch data for %s: %s", symbol, exc)
        return None

    if df is None or df.empty:
        logger.warning("No data returned for %s", symbol)
        return None

    # Keep only the columns we need, drop rows with NaNs in essential fields.
    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        logger.warning("%s missing columns %s", symbol, missing_cols)
        return None

    df = df[required_cols].copy()
    df.dropna(subset=required_cols, inplace=True)
    df.sort_index(inplace=True)

    if len(df) < MIN_REQUIRED_BARS:
        logger.warning(
            "%s has insufficient history (%d bars, need >= %d)",
            symbol, len(df), MIN_REQUIRED_BARS,
        )
        return None

    # Drop rows with non-positive prices/volume (bad data)
    df = df[(df["Close"] > 0) & (df["Volume"] >= 0)]

    return df


def fetch_watchlist_data(
    symbols: list,
    period: str = "1y",
    interval: str = "1d",
) -> dict:
    """
    Fetch data for every symbol in the watchlist.
    Returns {symbol: DataFrame}. Symbols with unusable data are silently
    omitted (a warning is logged) so the scan can continue with the rest.
    """
    result = {}
    for symbol in symbols:
        df = fetch_daily_data(symbol, period=period, interval=interval)
        if df is not None:
            result[symbol] = df
    return result
