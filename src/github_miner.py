from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx


@dataclass(slots=True)
class GitHubDoc:
    title: str
    url: str
    snippet: str
    score: float


class GitHubMiner:
    def __init__(self, logger, timeout: float = 12.0, github_token: str | None = None) -> None:
        self._logger = logger
        self._timeout = timeout
        self._github_token = github_token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-context-scraper-actor",
        }
        if self._github_token:
            headers["Authorization"] = f"Bearer {self._github_token}"
        return headers

    async def _search_repositories(self, query: str, max_items: int = 5) -> list[GitHubDoc]:
        endpoint = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&order=desc&per_page={max_items}"
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("GitHub repository search failed", extra={"query": query, "error": str(exc)})
            return []

        items = payload.get("items", [])
        results: list[GitHubDoc] = []
        for item in items:
            full_name = item.get("full_name", "")
            html_url = item.get("html_url", "")
            description = item.get("description") or ""
            stars = float(item.get("stargazers_count", 0) or 0)
            default_branch = item.get("default_branch") or "main"
            if not html_url:
                continue

            results.append(
                GitHubDoc(
                    title=full_name,
                    url=f"{html_url}#readme",
                    snippet=description,
                    score=min(5.0, 1.0 + (stars / 20000.0)),
                )
            )
            results.append(
                GitHubDoc(
                    title=f"{full_name} README",
                    url=f"https://raw.githubusercontent.com/{full_name}/{default_branch}/README.md",
                    snippet=description,
                    score=min(5.5, 1.5 + (stars / 18000.0)),
                )
            )

        return results

    async def _search_code(self, query: str, max_items: int = 8) -> list[GitHubDoc]:
        endpoint = f"https://api.github.com/search/code?q={quote_plus(query)}&sort=indexed&order=desc&per_page={max_items}"
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("GitHub code search failed", extra={"query": query, "error": str(exc)})
            return []

        items = payload.get("items", [])
        results: list[GitHubDoc] = []
        for item in items:
            repo = item.get("repository") or {}
            repo_name = repo.get("full_name", "")
            repo_html_url = repo.get("html_url", "")
            path = item.get("path", "")
            html_url = item.get("html_url", "")
            if not repo_name or not path:
                continue

            score = 2.0
            if path.lower().endswith((".py", ".ts", ".js", ".go", ".java", ".rs", ".md")):
                score += 0.6
            if "/example" in path.lower() or "/examples" in path.lower() or "/docs" in path.lower():
                score += 0.7

            results.append(
                GitHubDoc(
                    title=f"{repo_name}/{path}",
                    url=html_url or f"{repo_html_url}/blob/HEAD/{path}",
                    snippet=f"Code search match in {path}",
                    score=score,
                )
            )
            results.append(
                GitHubDoc(
                    title=f"{repo_name}/{path} raw",
                    url=f"https://raw.githubusercontent.com/{repo_name}/HEAD/{path}",
                    snippet=f"Raw code content from {path}",
                    score=score + 0.4,
                )
            )

        return results

    async def mine(
        self,
        task: str,
        signals: dict[str, list[str]],
        max_items: int = 8,
        include_code_search: bool = True,
        target_languages: list[str] | None = None,
    ) -> list[GitHubDoc]:
        query_terms = [task]
        libraries = signals.get("libraries", [])[:3]
        concepts = signals.get("concepts", [])[:3]

        if libraries or concepts:
            query_terms.append(" ".join(libraries + concepts + ["example", "python"]))

        jobs = [self._search_repositories(q, max_items=max(3, max_items // 2)) for q in query_terms]
        if include_code_search and self._github_token:
            languages = target_languages or signals.get("language", ["python"])
            code_queries = []
            for lang in languages[:3]:
                code_queries.append(f"{task} language:{lang}")
                if libraries:
                    code_queries.append(f"{' '.join(libraries[:2])} example language:{lang}")
            jobs.extend(self._search_code(q, max_items=max(4, max_items // 2)) for q in code_queries if q)
        elif include_code_search and not self._github_token:
            self._logger.warning(
                "GitHub code search requested but no GitHub token provided — code search will be skipped. "
                "Provide a github_token to enable code search.",
            )

        batches = await asyncio.gather(*jobs)

        merged: dict[str, GitHubDoc] = {}
        for item in [doc for batch in batches for doc in batch]:
            previous = merged.get(item.url)
            if previous is None or item.score > previous.score:
                merged[item.url] = item

        output = sorted(merged.values(), key=lambda x: x.score, reverse=True)
        self._logger.info(
            "GitHub mining complete",
            extra={
                "results": len(output),
                "authenticated": bool(self._github_token),
                "code_search": bool(include_code_search and self._github_token),
            },
        )
        return output[:max_items]
