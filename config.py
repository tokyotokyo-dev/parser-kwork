from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_dotenv_path = Path(__file__).resolve().parent / ".env"
if _dotenv_path.exists():
    load_dotenv(_dotenv_path)

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
DB_PATH = BASE_DIR / "kwork_parser.db"

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

KWORK_URL = "https://kwork.ru"
KWORK_INBOX_URL = "https://kwork.ru/inbox"
KWORK_MANAGE_URL = "https://kwork.ru/manage_kworks"

MESSAGE_CHECK_INTERVAL_MINUTES = int(os.getenv("MESSAGE_CHECK_INTERVAL", "3"))
STATS_CHECK_INTERVAL_MINUTES = int(os.getenv("STATS_CHECK_INTERVAL", "60"))
SUMMARY_INTERVAL_HOURS = int(os.getenv("SUMMARY_INTERVAL_HOURS", "6"))

HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_MISSING: list[str] = []
if not TELEGRAM_BOT_TOKEN:
    _MISSING.append("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_CHAT_ID:
    _MISSING.append("TELEGRAM_CHAT_ID")
if _MISSING:
    logger.warning(
        "Missing environment variables: %s. "
        "Set them in .env or the environment, then restart.",
        ", ".join(_MISSING),
    )
