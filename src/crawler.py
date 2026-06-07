from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


@dataclass(slots=True)
class CrawledPage:
    url: str
    status_code: int
    content_type: str
    text: str
    fetched_at: float


# Maximum response body size in bytes — skip oversized pages to save RAM.
_MAX_CONTENT_BYTES = 200_000


class AsyncCrawler:
    def __init__(
        self,
        logger,
        timeout: float = 10.0,
        max_concurrency: int = 20,
        retries: int = 1,
        requests_per_second: float = 20.0,
        proxy_url: str | None = None,
    ) -> None:
        self._logger = logger
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._retries = retries
        self._min_interval = 1.0 / max(1.0, requests_per_second)
        self._last_request_at = 0.0
        self._rate_lock = asyncio.Lock()
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._user_agent = "ai-context-scraper-actor/1.0 (+https://apify.com)"
        self._proxy_url = proxy_url

    async def _throttle(self) -> None:
        async with self._rate_lock:
            now = monotonic()
            wait_for = self._min_interval - (now - self._last_request_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_at = monotonic()

    async def _fetch_robots(self, client: httpx.AsyncClient, url: str) -> RobotFileParser | None:
        """Fetch and cache robots.txt for a given URL's origin."""
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin in self._robots_cache:
            return self._robots_cache[origin]

        robots_url = f"{origin}/robots.txt"
        try:
            response = await client.get(robots_url, timeout=5.0)
            rp = RobotFileParser()
            rp.parse(response.text.splitlines())
            self._robots_cache[origin] = rp
            return rp
        except Exception:  # noqa: BLE001, S110
            # If we can't fetch robots.txt, allow crawling (permissive default)
            self._robots_cache[origin] = None
            return None

    def _is_allowed_by_robots(self, rp: RobotFileParser | None, url: str) -> bool:
        """Check if the URL is allowed by robots.txt."""
        if rp is None:
            return True  # No robots.txt found — allow
        return rp.can_fetch(self._user_agent, url)

    async def _fetch_one(self, client: httpx.AsyncClient, url: str) -> CrawledPage | None:
        async with self._semaphore:
            # Check robots.txt compliance
            rp = await self._fetch_robots(client, url)
            if not self._is_allowed_by_robots(rp, url):
                self._logger.info("Skipping URL disallowed by robots.txt", extra={"url": url})
                return None

            for attempt in range(self._retries + 1):
                try:
                    await self._throttle()
                    response = await client.get(url)
                    content_type = response.headers.get("content-type", "")
                    if not any(ct in content_type for ct in ("text", "json", "markdown", "xhtml", "xml")):
                        self._logger.warning("Skipping non-text response", extra={"url": url, "content_type": content_type})
                        return None

                    # Skip oversized responses to prevent RAM spikes
                    body = response.text
                    if len(body) > _MAX_CONTENT_BYTES:
                        self._logger.warning(
                            "Skipping oversized response",
                            extra={"url": url, "size": len(body)},
                        )
                        return None

                    return CrawledPage(
                        url=url,
                        status_code=response.status_code,
                        content_type=content_type,
                        text=body,
                        fetched_at=monotonic(),
                    )
                except Exception as exc:  # noqa: BLE001
                    if attempt >= self._retries:
                        self._logger.warning("Failed to fetch URL", extra={"url": url, "error": str(exc)})
                        return None
                    await asyncio.sleep(0.35 * (2**attempt))

        return None

    async def crawl(self, urls: list[str]) -> list[CrawledPage]:
        if not urls:
            return []

        timeout = httpx.Timeout(connect=self._timeout, read=self._timeout, write=self._timeout, pool=self._timeout)
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml,text/markdown;q=0.9,*/*;q=0.8",
        }

        # Configure proxy for the client if provided
        proxy = self._proxy_url if self._proxy_url else None
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=headers, proxy=proxy
        ) as client:
            tasks = [self._fetch_one(client=client, url=url) for url in urls]
            crawled = await asyncio.gather(*tasks)

        pages = [page for page in crawled if page is not None and page.status_code < 400]
        self._logger.info("Crawling complete", extra={"requested": len(urls), "successful": len(pages)})
        return pages
