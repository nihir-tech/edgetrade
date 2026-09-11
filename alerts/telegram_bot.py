"""
alerts/telegram_bot.py
-------------------------
Sends Telegram alerts for A / A+ quality setups only. Uses plain
`requests` against the Bot API so no extra heavy dependency is required.
Fails silently (with a log message) if Telegram isn't configured, so the
rest of the system keeps working without it.
"""

import logging

import requests

import config
from utils.helpers import format_inr

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
TELEGRAM_SEND_URL = f"{TELEGRAM_API}/sendMessage"


def send_telegram_message(
    text: str, chat_id: str = None, reply_to_message_id: int = None, reply_markup: dict = None
) -> bool:
    """Low-level send. Returns True on success, False otherwise."""
    if not config.TELEGRAM_ENABLED:
        logger.info("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing) - skipping alert.")
        return False

    target_chat = chat_id or config.TELEGRAM_CHAT_ID
    url = TELEGRAM_SEND_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    payload = {"chat_id": target_chat, "text": text}
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(url, json={**payload, "parse_mode": "Markdown"}, timeout=10)
        if not resp.ok:
            logger.info("Markdown send failed (%s) - retrying as plain text.", resp.status_code)
            resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send Telegram alert: %s", exc)
        return False


def get_updates(offset: int = 0, timeout_seconds: int = 20) -> list:
    """Long-polls the Telegram Bot API for new updates. Returns a list of updates."""
    if not config.TELEGRAM_ENABLED:
        return []
    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN) + "/getUpdates"
    try:
        resp = requests.get(
            url,
            params={"offset": offset, "timeout": timeout_seconds},
            timeout=timeout_seconds + 10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("getUpdates failed: %s", exc)
        return []


def answer_callback_query(callback_query_id: str) -> bool:
    """Acknowledges an inline-button press so the spinner clears immediately."""
    if not config.TELEGRAM_ENABLED:
        return False
    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN) + "/answerCallbackQuery"
    try:
        resp = requests.post(url, json={"callback_query_id": callback_query_id}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("answerCallbackQuery failed: %s", exc)
        return False


def format_setup_alert(symbol: str, setup_type: str, grade: str, entry: float,
                        stop_loss: float, target: float, risk_reward: float,
                        quantity: int, risk_amount: float) -> str:
    """Builds a clean, readable Telegram message for a high-quality setup."""
    return (
        f"🚨 *{grade} SETUP - {setup_type.upper()}*\n"
        f"*Symbol:* `{symbol}`\n\n"
        f"*Entry:* {format_inr(entry)}\n"
        f"*Stop-Loss:* {format_inr(stop_loss)}\n"
        f"*Target (1:{risk_reward:.1f}):* {format_inr(target)}\n\n"
        f"*Suggested Qty:* {quantity} shares\n"
        f"*Risk:* {format_inr(risk_amount)} (0.5% capital)\n\n"
        f"_Paper trade only. Confirm setup is still valid before acting._"
    )


def send_setup_alert(symbol: str, setup_type: str, grade: str, entry: float,
                      stop_loss: float, target: float, risk_reward: float,
                      quantity: int, risk_amount: float) -> bool:
    """Sends an alert only if the grade is actionable (A / A+)."""
    if grade not in config.ACTIONABLE_GRADES:
        return False
    message = format_setup_alert(
        symbol, setup_type, grade, entry, stop_loss, target,
        risk_reward, quantity, risk_amount,
    )
    return send_telegram_message(message)


def send_no_trade_summary(scanned_count: int) -> bool:
    """Optional daily summary when nothing actionable was found."""
    message = (
        f"📋 *Daily Scan Complete*\n"
        f"Scanned {scanned_count} stocks - *NO TRADE — WAIT*.\n"
        f"No A/A+ setups today. Capital protected."
    )
    return send_telegram_message(message)
