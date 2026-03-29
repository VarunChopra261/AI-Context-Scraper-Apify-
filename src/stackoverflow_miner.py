"""StackOverflow integration for high-quality Q&A mining."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from typing import Any

import httpx
from bs4 import BeautifulSoup


@dataclass(slots=True)
class StackOverflowAnswer:
    question_title: str
    question_url: str
    answer_body: str
    score: int
    accepted: bool
    tags: list[str]


class StackOverflowMiner:
    """Mines high-quality answers from StackOverflow for developer context."""

    def __init__(self, logger, timeout: float = 12.0) -> None:
        self._logger = logger
        self._timeout = timeout
        self._base_url = "https://api.stackexchange.com/2.3"

    async def search_questions(
        self, query: str, tags: list[str] | None = None, max_results: int = 5
    ) -> list[StackOverflowAnswer]:
        """Search StackOverflow for relevant questions with accepted answers."""
        tagged = ";".join(tags[:3]) if tags else ""
        params: dict[str, Any] = {
            "order": "desc",
            "sort": "votes",
            "intitle": query,
            "site": "stackoverflow",
            "filter": "withbody",
            "pagesize": max_results,
        }
        if tagged:
            params["tagged"] = tagged

        endpoint = f"{self._base_url}/search/advanced"

        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("StackOverflow search failed", extra={"query": query, "error": str(exc)})
            return []

        items = data.get("items", [])

        # Collect questions with accepted answers and batch-fetch answers
        questions_with_answers: list[tuple[dict, int]] = []
        for item in items:
            if not item.get("is_answered") or item.get("accepted_answer_id") is None:
                continue
            questions_with_answers.append((item, item["accepted_answer_id"]))

        if not questions_with_answers:
            self._logger.info("StackOverflow mining complete", extra={"query": query, "results": 0})
            return []

        # Batch fetch all accepted answers in a single API call
        answer_ids = [aid for _, aid in questions_with_answers]
        answers_map = await self._fetch_answers_batch(answer_ids)

        results: list[StackOverflowAnswer] = []
        for item, answer_id in questions_with_answers:
            answer = answers_map.get(answer_id)
            if answer:
                question_id = item.get("question_id")
                title = unescape(item.get("title", ""))
                tags_list = item.get("tags", [])
                url = f"https://stackoverflow.com/questions/{question_id}"
                results.append(
                    StackOverflowAnswer(
                        question_title=title,
                        question_url=url,
                        answer_body=answer["body"],
                        score=answer["score"],
                        accepted=True,
                        tags=tags_list,
                    )
                )

        self._logger.info("StackOverflow mining complete", extra={"query": query, "results": len(results)})
        return results

    async def _fetch_answers_batch(self, answer_ids: list[int]) -> dict[int, dict]:
        """Fetch multiple answers in a single API call using semicolon-delimited IDs."""
        if not answer_ids:
            return {}

        # StackExchange API supports semicolon-delimited IDs for batch fetching
        ids_str = ";".join(str(aid) for aid in answer_ids)
        endpoint = f"{self._base_url}/answers/{ids_str}"
        params = {"site": "stackoverflow", "filter": "withbody"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])

                results: dict[int, dict] = {}
                for item in items:
                    aid = item.get("answer_id")
                    if aid is not None:
                        soup = BeautifulSoup(item.get("body", ""), "html.parser")
                        results[aid] = {
                            "body": soup.get_text("\n").strip(),
                            "score": item.get("score", 0),
                        }
                return results
        except Exception as exc:  # noqa: BLE001, S110
            self._logger.warning("StackOverflow batch answer fetch failed", extra={"error": str(exc)})
            return {}

    async def mine(self, task: str, signals: dict[str, list[str]], max_results: int = 5) -> list[StackOverflowAnswer]:
        """Mine StackOverflow for relevant Q&A based on task and detected signals."""
        libraries = signals.get("libraries", [])
        tags = libraries[:3] if libraries else ["python"]

        # Search with task query
        results = await self.search_questions(query=task, tags=tags, max_results=max_results)
        return results
