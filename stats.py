from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

from playwright.async_api import Page

from database.models import save_kwork_stat, get_previous_stats, get_latest_stats

logger = logging.getLogger(__name__)

SendTelegram = Callable[[str], Awaitable[None]]

MANAGE_URL = "https://kwork.ru/manage_kworks"

_EXTRACT_SCRIPT = r"""
() => {
    const rows = document.querySelectorAll('tr.manage-kworks__row');
    return Array.from(rows).map(row => {
        const nameEl = row.querySelector('.manage-kworks-item__title');
        const name = (nameEl?.textContent || '').trim();

        const metrics = row.querySelectorAll('.manage-kworks-item__metrics-item');
        let views = '0', orders = '0';

        if (metrics.length >= 1) {
            const spans = metrics[0].querySelectorAll('span.ml5');
            if (spans.length >= 2) views = spans[1].textContent.trim();
        }
        if (metrics.length >= 2) {
            const spans = metrics[1].querySelectorAll('span.ml5');
            if (spans.length >= 2) orders = spans[1].textContent.trim();
        }

        return { name, views, orders };
    }).filter(r => r.name);
}
"""


async def check_stats(page: Page, send_telegram: SendTelegram) -> None:
    try:
        await page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        await _settle(page, seconds=5)

        current_url = page.url
        logger.info("Current URL: %s", current_url)

        rows: list[dict] = await page.evaluate(_EXTRACT_SCRIPT)
        logger.info("Found %d kwork rows.", len(rows))

        if not rows:
            logger.warning("No kwork rows found — selectors may be outdated.")
            await page.screenshot(path="debug_stats.png")
            logger.info("Saved debug screenshot → debug_stats.png")
            return

        previous = await get_previous_stats()
        deltas: list[str] = []
        fresh: list[str] = []

        for entry in rows:
            name = entry["name"]
            views = _parse_int(entry["views"])
            orders = _parse_int(entry["orders"])

            await save_kwork_stat(name, views, orders)

            prev = previous.get(name)
            if prev is None:
                fresh.append(name)
                continue

            prev_views, prev_orders = prev
            v_delta = views - prev_views
            o_delta = orders - prev_orders

            if v_delta > 0 or o_delta > 0:
                parts = [f"📊 *{name}*"]
                if v_delta > 0:
                    parts.append(f"👁 Просмотры: +{v_delta} (сейчас {views})")
                if o_delta > 0:
                    parts.append(f"📦 Заказы: +{o_delta} (сейчас {orders})")
                deltas.append("\n".join(parts))

        messages: list[str] = []

        if deltas:
            messages.append("📈 *Статистика за период:*\n\n" + "\n\n".join(deltas))

        if fresh:
            messages.append(
                "🆕 *Новые кворки:*\n" + "\n".join(f"• {n}" for n in fresh)
            )

        if messages:
            text = "\n\n".join(messages)
            logger.info("Stats report:\n%s", text)
            await send_telegram(text)
        else:
            logger.info("No stats changes detected.")

    except Exception as exc:
        logger.exception("check_stats failed: %s", exc)
        await send_telegram(f"⚠️ Ошибка сбора статистики: {exc}")


async def build_summary() -> str:
    rows = await get_latest_stats()
    if not rows:
        return "📊 *Сводка:* пока нет данных."

    total_views = 0
    total_orders = 0
    lines: list[str] = []

    for name, views, orders in rows:
        total_views += views
        total_orders += orders
        lines.append(f"• *{name}* — 👁 {views}  📦 {orders}")

    lines.append("")
    lines.append(
        f"📊 *Итого:* {len(rows)} кворков, 👁 {total_views} просмотров, 📦 {total_orders} заказов"
    )

    return "\n".join(lines)


async def _settle(page: Page, seconds: float) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    await asyncio.sleep(seconds)


def _parse_int(raw: str) -> int:
    try:
        digits = "".join(ch for ch in raw if ch.isdigit())
        return int(digits) if digits else 0
    except (ValueError, TypeError):
        return 0
