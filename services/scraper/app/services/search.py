"""Finds and fetches factual context for a topic with no user-supplied URL
— the one thing app/services/crawler.py doesn't cover (it only fetches a URL you
already have). A real general-web search with no API key isn't practically
achievable: DuckDuckGo's HTML results page (the usual free option) actively
CAPTCHA-challenges scripted requests, confirmed while building this — and
Google/Bing search only offer that without a paid API key. Wikipedia's own
API is the honest alternative: free, no key, explicitly documented for
programmatic use, and covers a wide range of factual/reference topics well
— just not current events, products, or anything Wikipedia doesn't have an
article on, which is a real and worth-stating limitation of this feature.
"""
import logging

import httpx

logger = logging.getLogger("scraper.search")

# Wikimedia's API etiquette policy requires a descriptive User-Agent
# identifying the application — requests without one get a 403.
_HEADERS = {"User-Agent": "CreditFlowBot/1.0 (https://github.com/AbdullahZubair-1/CreditFlow-AI-Platform)"}
_API_URL = "https://en.wikipedia.org/w/api.php"


async def research(query: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
        try:
            search_response = await client.get(
                _API_URL,
                params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1},
            )
            search_response.raise_for_status()
            results = search_response.json().get("query", {}).get("search", [])
            if not results:
                return None
            title = results[0]["title"]

            extract_response = await client.get(
                _API_URL,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "titles": title,
                    "format": "json",
                },
            )
            extract_response.raise_for_status()
            pages = extract_response.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            extract = page.get("extract", "")
            if not extract:
                return None

            return {
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "title": title,
                "text_content": extract,
            }
        except httpx.HTTPError:
            logger.warning("web research failed for query %r", query, exc_info=True)
            return None
