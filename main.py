from __future__ import annotations

import asyncio
import logging
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    MESSAGE_CHECK_INTERVAL_MINUTES,
    STATS_CHECK_INTERVAL_MINUTES,
    SUMMARY_INTERVAL_HOURS,
    STATE_FILE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from database.models import init_db
from auth import get_authenticated_page, login_manual, shutdown_browser
from bot import send_notification, get_bot, start_polling, stop_polling
from monitor import check_inbox
from stats import check_stats, build_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("kwork_parser")

_shutdown_event = asyncio.Event()


async def _check_inbox_job() -> None:
    logger.info("▶ Inbox check starting …")
    try:
        _browser, _context, page = await get_authenticated_page()
        await check_inbox(page, send_notification)
    except Exception as exc:
        logger.exception("Inbox job failed: %s", exc)
        await send_notification(f"⚠️ Inbox job error: {exc}")


async def _check_stats_job() -> None:
    logger.info("▶ Stats check starting …")
    try:
        _browser, _context, page = await get_authenticated_page()
        await check_stats(page, send_notification)
    except Exception as exc:
        logger.exception("Stats job failed: %s", exc)
        await send_notification(f"⚠️ Stats job error: {exc}")


async def _summary_job() -> None:
    logger.info("▶ Summary job starting …")
    try:
        text = await build_summary()
        await send_notification(text)
    except Exception as exc:
        logger.exception("Summary job failed: %s", exc)
        await send_notification(f"⚠️ Summary job error: {exc}")


async def _cmd_stats() -> str:
    try:
        _browser, _context, page = await get_authenticated_page()
        await check_stats(page, send_notification)
        return await build_summary()
    except Exception as exc:
        logger.exception("/stats command failed: %s", exc)
        return f"⚠️ Ошибка: {exc}"


async def _cmd_inbox() -> str:
    try:
        _browser, _context, page = await get_authenticated_page()
        await check_inbox(page, send_notification)
        return "✅ Проверка завершена — новые сообщения (если были) отправлены выше."
    except Exception as exc:
        logger.exception("/inbox command failed: %s", exc)
        return f"⚠️ Ошибка: {exc}"


async def _cmd_summary() -> str:
    return await build_summary()


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set. "
            "Create a .env file or export them in the environment."
        )
        sys.exit(1)

    await init_db()
    logger.info("Database ready.")

    if not STATE_FILE.exists():
        logger.info("No session file found — launching login flow.")
        await login_manual()

    await get_authenticated_page()
    logger.info("Browser singleton ready.")

    polling_task = asyncio.create_task(
        start_polling(
            on_stats=_cmd_stats,
            on_inbox=_cmd_inbox,
            on_summary=_cmd_summary,
        )
    )

    await send_notification(
        "✅ *Kwork Parser запущен*\n"
        f"📩 Сообщения: раз в {MESSAGE_CHECK_INTERVAL_MINUTES} мин.\n"
        f"📊 Статистика: раз в {STATS_CHECK_INTERVAL_MINUTES} мин.\n"
        f"📋 Сводка: раз в {SUMMARY_INTERVAL_HOURS} ч.\n\n"
        "Команды: /stats  /inbox  /summary"
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _check_inbox_job,
        "interval",
        minutes=MESSAGE_CHECK_INTERVAL_MINUTES,
        id="inbox",
    )
    scheduler.add_job(
        _check_stats_job,
        "interval",
        minutes=STATS_CHECK_INTERVAL_MINUTES,
        id="stats",
    )
    scheduler.add_job(
        _summary_job,
        "interval",
        hours=SUMMARY_INTERVAL_HOURS,
        id="summary",
    )
    scheduler.start()
    logger.info(
        "Scheduler started (inbox: %d min, stats: %d min, summary: %d h).",
        MESSAGE_CHECK_INTERVAL_MINUTES,
        STATS_CHECK_INTERVAL_MINUTES,
        SUMMARY_INTERVAL_HOURS,
    )

    logger.info("Running initial checks …")
    await _check_inbox_job()
    await _check_stats_job()
    await _summary_job()

    _install_signal_handlers()
    try:
        await _shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")

    logger.info("Shutting down …")
    scheduler.shutdown(wait=False)

    await stop_polling()
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    try:
        bot = get_bot()
        await bot.session.close()
    except Exception:
        logger.debug("Error closing bot session", exc_info=True)

    await shutdown_browser()
    logger.info("Shutdown complete.")


def _install_signal_handlers() -> None:
    def _handle(_signum, _frame):
        logger.info("Received signal %s — initiating shutdown.", _signum)
        _shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
