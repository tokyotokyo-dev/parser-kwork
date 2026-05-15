from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Callable, Awaitable

from playwright.async_api import Page

from database.models import is_message_processed, mark_message_processed

logger = logging.getLogger(__name__)

SendTelegram = Callable[[str], Awaitable[None]]

INBOX_URL = "https://kwork.ru/inbox"

_EXTRACT_SCRIPT = r"""
() => {
    if (document.querySelector('.chat__conversation-empty, .chat_without-dialogs')) {
        return [];
    }

    const container = document.querySelector('.kwork-conversation__list');
    if (!container) return [];

    const items = container.querySelectorAll(
        'a[href*="/inbox/"], [class*="conversation__item"], [class*="dialog-item"]'
    );

    return Array.from(items).map(el => {
        const unread = el.querySelector(
            '.unread, .new-message, [class*="unread"], .badge--unread, [class*="counter"]'
        );
        const sender = el.querySelector(
            '[class*="name"], [class*="username"], [class*="sender"], [class*="interlocutor"]'
        );
        const text = el.querySelector(
            '[class*="last-message"], [class*="message-text"], [class*="preview"], [class*="body"]'
        );
        return {
            hasUnread: !!unread,
            sender: (sender?.textContent || '').trim(),
            text: (text?.textContent || '').trim(),
        };
    }).filter(r => r.sender || r.text);
}
"""


async def check_inbox(page: Page, send_telegram: SendTelegram) -> None:
    try:
        await page.goto(INBOX_URL, wait_until="domcontentloaded", timeout=60_000)
        await _settle(page, seconds=5)

        current_url = page.url
        logger.info("Current URL: %s", current_url)

        conversations: list[dict] = await page.evaluate(_EXTRACT_SCRIPT)
        logger.info("Found %d conversation items.", len(conversations))

        if not conversations:
            await page.screenshot(path="debug_inbox.png")
            logger.info("Saved debug screenshot → debug_inbox.png")

        found_unread = 0

        for entry in conversations:
            if not entry["hasUnread"]:
                continue

            found_unread += 1
            sender = entry["sender"]
            text = entry["text"]

            message_id = _make_id(sender, text)

            if await is_message_processed(message_id):
                continue

            await mark_message_processed(message_id)

            notify = f"📩 *Новое сообщение от {sender or '—'}*\n{text or '(нет текста)'}"
            logger.info("New message: %s", notify)
            await send_telegram(notify)

        if found_unread == 0:
            logger.info("No unread conversations found.")
        else:
            logger.info("Checked %d unread conversation(s).", found_unread)

    except Exception as exc:
        logger.exception("check_inbox failed: %s", exc)
        await send_telegram(f"⚠️ Ошибка мониторинга сообщений: {exc}")


async def _settle(page: Page, seconds: float) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    await asyncio.sleep(seconds)


def _make_id(sender: str, text: str) -> str:
    raw = f"{sender}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
