"""robots.txt compliance check. urllib.robotparser's RobotFileParser can
parse an already-fetched robots.txt (via .parse(lines)) without doing its
own blocking network I/O, so we fetch it ourselves with httpx (async,
consistent with the rest of this async codebase) and hand it the lines."""
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger("scraper.robots")

USER_AGENT = "CreditFlowBot/1.0"


async def is_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    parser = RobotFileParser()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(robots_url)
        if response.status_code >= 400:
            # No robots.txt (or it's unreachable) is conventionally
            # treated as "everything allowed".
            return True
        parser.parse(response.text.splitlines())
    except httpx.HTTPError:
        logger.warning("could not fetch robots.txt for %s, allowing by default", parsed.netloc)
        return True

    return parser.can_fetch(USER_AGENT, url)
