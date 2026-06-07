"""Web search using DuckDuckGo (ddgs) with rate-limiting and query expansion."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse

from ddgs import DDGS

PRIORITY_DOMAINS = {
    "docs.python.org": 4.0,
    "fastapi.tiangolo.com": 4.0,
    "pytorch.org": 3.5,
    "huggingface.co": 3.5,
    "docs.aws.amazon.com": 4.0,
    "python.langchain.com": 4.0,
    "langchain.readthedocs.io": 4.0,
    "developer.mozilla.org": 3.0,
}

# Per-query timeout in seconds — prevents ddgs from hanging indefinitely.
_SEARCH_TIMEOUT_SECONDS = 20.0


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "web"
    score: float = 0.0


class QueryExpander:
    def __init__(self) -> None:
        self._concept_suffixes = [
            "tutorial",
            "official documentation",
            "api reference",
            "best practices",
            "example",
            "implementation guide",
            "python",
        ]

    def extract_signals(self, task: str) -> dict[str, list[str]]:
        words = [w.strip(" ,.-:_()[]{}\n\t").lower() for w in task.split()]
        words = [w for w in words if len(w) > 2]

        keyword_set = set(words)
        known_libraries = {
            "fastapi",
            "boto3",
            "langchain",
            "chroma",
            "pydantic",
            "django",
            "flask",
            "pytorch",
            "tensorflow",
            "sqlalchemy",
            "pandas",
            "numpy",
            "openai",
            "anthropic",
            "redis",
            "postgres",
            "mongodb",
            "kafka",
            "celery",
        }

        libraries = sorted([k for k in known_libraries if k in keyword_set])
        concepts = sorted(keyword_set - set(libraries))

        return {
            "libraries": libraries,
            "frameworks": libraries,
            "language": ["python"],
            "keywords": sorted(keyword_set),
            "concepts": concepts[:20],
        }

    def expand(self, task: str, signals: dict[str, list[str]], limit: int = 6) -> list[str]:
        base_queries = [task.strip()]

        core_terms = signals.get("libraries", [])[:3] + signals.get("concepts", [])[:4]
        core_phrase = " ".join(core_terms).strip()
        if core_phrase:
            base_queries.append(core_phrase)

        for suffix in self._concept_suffixes:
            base_queries.append(f"{task} {suffix}")
            if core_phrase:
                base_queries.append(f"{core_phrase} {suffix}")

        unique_queries: list[str] = []
        seen = set()
        for q in base_queries:
            normalized = " ".join(q.lower().split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_queries.append(q)

        return unique_queries[:limit]


class SearchClient:
    def __init__(self, logger, proxy_url: str | None = None) -> None:
        self._logger = logger
        self._proxy_url = proxy_url

    @staticmethod
    def _domain_boost(url: str) -> float:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        for preferred_domain, boost in PRIORITY_DOMAINS.items():
            if domain == preferred_domain or domain.endswith(f".{preferred_domain}"):
                return boost
        return 0.0

    async def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        def _run() -> list[SearchResult]:
            output: list[SearchResult] = []
            ddgs = DDGS(proxy=self._proxy_url)
            for item in ddgs.text(query, max_results=max_results):
                url = item.get("href") or item.get("url") or ""
                if not url:
                    continue
                title = item.get("title") or ""
                snippet = item.get("body") or ""
                score = self._domain_boost(url)
                output.append(
                    SearchResult(title=title, url=url, snippet=snippet, source="web", score=score)
                )
            return output

        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(_run),
                timeout=_SEARCH_TIMEOUT_SECONDS,
            )
            self._logger.info(
                "Search query executed",
                extra={"query": query, "results": len(results)},
            )
            return results
        except asyncio.TimeoutError:
            self._logger.warning("Search query timed out", extra={"query": query})
            return []
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Search query failed", extra={"query": query, "error": str(exc)})
            return []

    async def multi_search(self, queries: list[str], per_query: int = 5) -> list[SearchResult]:
        # Rate-limit DDG queries strictly.
        # DuckDuckGo's aggressive rate-limiter blocks concurrent and rapid requests.
        sem = asyncio.Semaphore(1)
        results_by_query: list[list[SearchResult]] = []

        async def _rate_limited_search(query: str) -> list[SearchResult]:
            async with sem:
                # Sleep INSIDE the semaphore to enforce a genuine delay between outgoing requests
                await asyncio.sleep(1.5)
                result = await self.search(query=query, max_results=per_query)
                return result

        tasks = [_rate_limited_search(q) for q in queries]
        results_by_query = await asyncio.gather(*tasks)

        flattened = [item for group in results_by_query for item in group]
        dedup: dict[str, SearchResult] = {}
        for item in flattened:
            previous = dedup.get(item.url)
            if previous is None or item.score > previous.score:
                dedup[item.url] = item

        output = list(dedup.values())
        output.sort(key=lambda x: x.score, reverse=True)
        return output
