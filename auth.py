from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

from config import STATE_FILE, HEADLESS, USER_AGENT, KWORK_URL

if TYPE_CHECKING:
    from playwright.async_api import Playwright

logger = logging.getLogger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None


async def get_authenticated_page() -> tuple[Browser, BrowserContext, Page]:
    if not STATE_FILE.exists():
        raise FileNotFoundError(
            f"Session file {STATE_FILE} not found. Run login_manual() first."
        )
    return await _ensure_singleton()


async def login_manual() -> None:
    logger.info("Starting manual login flow …")
    logger.info("Browser will open — log in, then press Enter here.")
    logger.info("Session will be saved to %s", STATE_FILE)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(user_agent=USER_AGENT)
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    await page.goto(KWORK_URL, wait_until="domcontentloaded")
    logger.info("Opened %s", KWORK_URL)
    input("[auth] >>> Log in manually, then press Enter to save session … ")

    await context.storage_state(path=str(STATE_FILE))
    logger.info("Session saved → %s", STATE_FILE)

    await context.close()
    await browser.close()
    await pw.stop()
    logger.info("Login browser closed.")


async def shutdown_browser() -> None:
    global _page, _context, _browser, _playwright

    for resource, name in (
        (_page, "page"),
        (_context, "context"),
        (_browser, "browser"),
        (_playwright, "playwright"),
    ):
        if resource is not None:
            try:
                await resource.close()
            except Exception:
                logger.debug("Error closing %s", name, exc_info=True)

    _page = _context = _browser = _playwright = None
    logger.info("Browser shut down.")


async def _ensure_singleton() -> tuple[Browser, BrowserContext, Page]:
    global _playwright, _browser, _context, _page

    if _playwright is None:
        _playwright = await async_playwright().start()

    if _browser is None:
        _browser = await _playwright.chromium.launch(headless=HEADLESS)
        logger.info("Chromium launched (headless=%s)", HEADLESS)

    if _context is None:
        _context = await _browser.new_context(
            user_agent=USER_AGENT,
            storage_state=str(STATE_FILE),
        )
        logger.info("Context created from saved session.")

    if _page is not None and not _page.is_closed():
        try:
            await _page.close()
        except Exception:
            logger.debug("Error closing old page", exc_info=True)

    _page = await _context.new_page()
    await Stealth().apply_stealth_async(_page)
    logger.debug("Fresh page created + stealth applied.")

    return _browser, _context, _page
