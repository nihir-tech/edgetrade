"""
utils/helpers.py
-------------------
Small shared utilities: logging setup and currency formatting.
"""

import logging
import sys

import config


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def format_inr(amount: float) -> str:
    """Formats a number as Indian Rupees with lakh/crore-style commas, e.g. ₹1,00,000.00"""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return str(amount)

    is_negative = amount < 0
    amount = abs(amount)
    whole, _, frac = f"{amount:.2f}".partition(".")

    if len(whole) > 3:
        last3 = whole[-3:]
        rest = whole[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        whole = ",".join(parts) + "," + last3

    sign = "-" if is_negative else ""
    return f"{sign}₹{whole}.{frac}"
