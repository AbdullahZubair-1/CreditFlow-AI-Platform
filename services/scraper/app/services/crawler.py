"""Headless-browser fetch via Playwright — chosen over Crawl4AI (the
spec's other option) since it needs no extra wrapper for this scope's
simple "load the page, grab title/text/html" use case. Respects
robots.txt and a per-domain politeness delay before ever launching a
page load.
"""
from playwright.async_api import async_playwright

from app.core.config import settings
from app.services import rate_limiter, robots


class CrawlerError(Exception):
    pass


class RobotsDisallowedError(CrawlerError):
    pass


async def crawl(url: str) -> dict:
    if not await robots.is_allowed(url):
        raise RobotsDisallowedError(f"robots.txt disallows crawling {url}")

    await rate_limiter.wait_for_turn(url)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=robots.USER_AGENT)
            await page.goto(url, timeout=settings.page_load_timeout_seconds * 1000, wait_until="networkidle")

            title = await page.title()
            text_content = await page.evaluate("document.body ? document.body.innerText : ''")
            html = await page.content()

            return {"url": url, "title": title, "text_content": text_content, "html": html}
        finally:
            await browser.close()
