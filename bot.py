from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dispatcher: Dispatcher | None = None

CommandCallback = Callable[[], Awaitable[str]]


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
    return _bot


async def send_notification(text: str, chat_id: str | None = None) -> None:
    bot = get_bot()
    target = chat_id or TELEGRAM_CHAT_ID
    try:
        await bot.send_message(chat_id=target, text=text)
        logger.info("Telegram notification sent to %s.", target)
    except Exception:
        try:
            await bot.send_message(
                chat_id=target, text=text, parse_mode=None
            )
            logger.info("Telegram notification sent (plain-text fallback) to %s.", target)
        except Exception as exc:
            logger.exception("Failed to send Telegram notification: %s", exc)


async def start_polling(
    *,
    on_stats: CommandCallback | None = None,
    on_inbox: CommandCallback | None = None,
    on_summary: CommandCallback | None = None,
) -> None:
    global _dispatcher
    bot = get_bot()
    _dispatcher = Dispatcher()

    async def _require_owner(msg: Message) -> bool:
        return str(msg.chat.id) == TELEGRAM_CHAT_ID

    @_dispatcher.message(Command("start"))
    async def _start_cmd(msg: Message) -> None:
        if not await _require_owner(msg):
            return
        await msg.answer(
            "👋 *Kwork Parser*\n\n"
            "Команды:\n"
            "/stats — собрать статистику\n"
            "/inbox — проверить сообщения\n"
            "/summary — сводка по кворкам"
        )

    if on_stats:

        @_dispatcher.message(Command("stats"))
        async def _stats_cmd(msg: Message) -> None:
            if not await _require_owner(msg):
                return
            await msg.answer("⏳ Собираю свежую статистику с Kwork…")
            text = await on_stats()
            await msg.answer(text)

    if on_inbox:

        @_dispatcher.message(Command("inbox"))
        async def _inbox_cmd(msg: Message) -> None:
            if not await _require_owner(msg):
                return
            await msg.answer("⏳ Проверяю входящие сообщения…")
            text = await on_inbox()
            await msg.answer(text)

    if on_summary:

        @_dispatcher.message(Command("summary"))
        async def _summary_cmd(msg: Message) -> None:
            if not await _require_owner(msg):
                return
            text = await on_summary()
            await msg.answer(text)

    logger.info("Bot polling started — commands: /stats /inbox /summary")
    await _dispatcher.start_polling(bot)


async def stop_polling() -> None:
    global _dispatcher
    if _dispatcher is not None:
        try:
            await _dispatcher.stop_polling()
        except Exception:
            logger.debug("Error stopping dispatcher", exc_info=True)
        _dispatcher = None
