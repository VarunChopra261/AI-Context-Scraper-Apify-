"""Comprehensive regression tests for the orchestrator.py — zero coverage → full coverage.

These tests mock all IO-bound collaborators (search, github, crawler, extractor, etc.)
so no real network calls are made.
"""

from __future__ import annotations

import logging
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator import ContextOrchestrator


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def logger():
    return logging.getLogger("test_orchestrator")


def _make_orchestrator(logger, **kwargs):
    """Build an orchestrator with caching and LLM disabled (safe for unit tests)."""
    return ContextOrchestrator(
        logger=logger,
        github_token=None,
        enable_cache=False,
        enable_stackoverflow=False,
        chunk_size=500,
        enable_llm_synthesis=False,
        openrouter_api_key=None,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Static utility method tests
# ---------------------------------------------------------------------------

class TestDomainExtraction:
    def test_strips_www_prefix(self):
        assert ContextOrchestrator._domain("https://www.example.com/path") == "example.com"

    def test_preserves_subdomain(self):
        assert ContextOrchestrator._domain("https://docs.python.org/3/") == "docs.python.org"

    def test_handles_path(self):
        assert ContextOrchestrator._domain("http://github.com/owner/repo") == "github.com"


class TestAllowedFilter:
    def test_empty_allowed_domains_permits_all(self):
        assert ContextOrchestrator._allowed("https://anything.com", []) is True

    def test_exact_domain_match_permitted(self):
        assert ContextOrchestrator._allowed("https://docs.python.org/", ["docs.python.org"]) is True

    def test_www_variant_permitted(self):
        assert ContextOrchestrator._allowed("https://www.github.com/", ["github.com"]) is True

    def test_subdomain_of_allowed_permitted(self):
        assert ContextOrchestrator._allowed("https://sub.allowed.com/path", ["allowed.com"]) is True

    def test_non_allowed_domain_rejected(self):
        assert ContextOrchestrator._allowed("https://evil.com/", ["safe.com"]) is False

    def test_partial_match_not_permitted(self):
        """'allowed.com' must not match 'notallowed.com'."""
        assert ContextOrchestrator._allowed("https://notallowed.com/", ["allowed.com"]) is False


class TestUrlRank:
    def test_docs_domain_gets_positive_score(self):
        score = ContextOrchestrator._url_rank("https://docs.python.org/3/")
        assert score > 0

    def test_readthedocs_gets_positive_score(self):
        score = ContextOrchestrator._url_rank("https://fastapi.readthedocs.io/")
        assert score > 0

    def test_github_gets_positive_score(self):
        score = ContextOrchestrator._url_rank("https://github.com/owner/repo")
        assert score > 0

    def test_medium_gets_negative_score(self):
        score = ContextOrchestrator._url_rank("https://medium.com/some/post")
        assert score < 0

    def test_reddit_gets_negative_score(self):
        score = ContextOrchestrator._url_rank("https://reddit.com/r/python")
        assert score < 0

    def test_unknown_domain_gets_zero_score(self):
        score = ContextOrchestrator._url_rank("https://somerandomblog.io/article")
        assert score == 0.0


class TestIsSeoSpam:
    def test_sponsored_content_detected(self):
        assert ContextOrchestrator._is_seo_spam("Best sponsored deals today") is True

    def test_casino_detected(self):
        assert ContextOrchestrator._is_seo_spam("Online casino free spins") is True

    def test_promo_code_detected(self):
        assert ContextOrchestrator._is_seo_spam("Use promo code SAVE50") is True

    def test_affiliate_link_detected(self):
        assert ContextOrchestrator._is_seo_spam("Affiliate link for extra commission") is True

    def test_clean_content_not_flagged(self):
        assert ContextOrchestrator._is_seo_spam("How to build a Python REST API") is False

    def test_empty_text_not_flagged(self):
        assert ContextOrchestrator._is_seo_spam("") is False

    def test_none_text_not_flagged(self):
        assert ContextOrchestrator._is_seo_spam(None) is False

    def test_case_insensitive_detection(self):
        assert ContextOrchestrator._is_seo_spam("CLICK HERE to download") is True


class TestTaskTerms:
    def test_stop_words_removed(self):
        terms = ContextOrchestrator._task_terms("Build a FastAPI app")
        assert "a" not in terms
        assert "build" not in terms

    def test_meaningful_words_kept(self):
        terms = ContextOrchestrator._task_terms("FastAPI SQLAlchemy authentication")
        assert "fastapi" in terms
        assert "sqlalchemy" in terms
        assert "authentication" in terms

    def test_short_words_removed(self):
        """Words of 2 chars or less must be excluded."""
        terms = ContextOrchestrator._task_terms("An app in Go")
        assert "go" not in terms  # len 2

    def test_returns_list_of_strings(self):
        terms = ContextOrchestrator._task_terms("Build REST API with Python")
        assert isinstance(terms, list)
        assert all(isinstance(t, str) for t in terms)


class TestTextRelevance:
    def test_exact_phrase_in_text_gives_high_score(self):
        task = "fastapi file upload"
        score = ContextOrchestrator._text_relevance(task, "this is about fastapi file upload")
        assert score >= 0.8

    def test_completely_unrelated_text_gives_low_score(self):
        task = "quantum computing algorithms"
        score = ContextOrchestrator._text_relevance(task, "baking bread recipe for sourdough")
        assert score < 0.3

    def test_partial_match_gives_intermediate_score(self):
        task = "fastapi boto3 s3 upload"
        score = ContextOrchestrator._text_relevance(task, "fastapi is great for APIs")
        assert 0.0 < score < 1.0

    def test_empty_task_returns_zero(self):
        score = ContextOrchestrator._text_relevance("", "some content")
        assert score == 0.0

    def test_score_bounded_at_1(self):
        task = "fastapi"
        text = "fastapi " * 50
        score = ContextOrchestrator._text_relevance(task, text)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# _collect_urls
# ---------------------------------------------------------------------------

def _make_item(url, title="Title", snippet="Snippet", score=0.0):
    item = MagicMock()
    item.url = url
    item.title = title
    item.snippet = snippet
    item.score = score
    return item


class TestCollectUrls:
    def test_returns_list_of_strings(self, logger):
        orc = _make_orchestrator(logger)
        items = [
            _make_item("https://docs.python.org/3/library/asyncio.html", score=1.0,
                       snippet="asyncio python async await concurrency event loop"),
            _make_item("https://fastapi.tiangolo.com/tutorial/", score=0.5,
                       snippet="fastapi python async REST API tutorial endpoint"),
        ]
        task = "python asyncio fastapi"
        urls = orc._collect_urls(task, items, [], max_sources=10, allowed_domains=[])
        assert isinstance(urls, list)

    def test_domain_dedup_caps_per_domain(self, logger):
        orc = _make_orchestrator(logger)
        task = "python fastapi asyncio tutorial example"
        items = [
            _make_item(f"https://example.com/page{i}", score=1.0,
                       snippet="fastapi python asyncio tutorial")
            for i in range(5)
        ]
        urls = orc._collect_urls(task, items, [], max_sources=10, allowed_domains=[])
        from collections import Counter
        domain_counts = Counter(
            ContextOrchestrator._domain(u) for u in urls
        )
        for domain, count in domain_counts.items():
            assert count <= 3, f"Domain {domain} exceeded max 3 per domain"

    def test_max_sources_cap_respected(self, logger):
        orc = _make_orchestrator(logger)
        task = "python tutorial"
        items = [
            _make_item(f"https://site{i}.com/page", score=1.0, snippet="python tutorial asyncio")
            for i in range(20)
        ]
        urls = orc._collect_urls(task, items, [], max_sources=5, allowed_domains=[])
        assert len(urls) <= 5

    def test_allowed_domains_filter_applied(self, logger):
        orc = _make_orchestrator(logger)
        task = "python"
        items = [
            _make_item("https://docs.python.org/3/", score=2.0, snippet="python docs reference"),
            _make_item("https://evil.com/attack", score=5.0, snippet="python evil"),
        ]
        urls = orc._collect_urls(task, items, [], max_sources=10, allowed_domains=["docs.python.org"])
        assert all("docs.python.org" in u for u in urls)
        assert not any("evil.com" in u for u in urls)


# ---------------------------------------------------------------------------
# Full pipeline — run() with all IO mocked
# ---------------------------------------------------------------------------

def _build_full_mock_orchestrator(logger):
    """Patch all network collaborators and return a test-safe orchestrator."""
    from src.chunker import LLMChunk
    from src.extractor import ExtractedDoc, ExtractedSnippet
    from src.crawler import CrawledPage
    from src.relevance import BucketizedContext, ScoredChunk, ScoredSnippet

    orc = _make_orchestrator(logger)

    # Fake search result
    fake_sr = MagicMock()
    fake_sr.url = "https://docs.python.org/3/library/asyncio.html"
    fake_sr.title = "asyncio — Asynchronous I/O"
    fake_sr.snippet = "python asyncio tutorial event loop coroutine"
    fake_sr.score = 0.0

    orc._search.multi_search = AsyncMock(return_value=[fake_sr])
    orc._github.mine = AsyncMock(return_value=[])

    # Fake crawled page
    fake_page = CrawledPage(
        url="https://docs.python.org/3/library/asyncio.html",
        status_code=200,
        content_type="text/html",
        text="<html><body><article><h1>asyncio</h1><p>Python asyncio tutorial for coroutines and event loops.</p></article></body></html>",
        fetched_at=0.0,
    )
    orc._crawler.crawl = AsyncMock(return_value=[fake_page])

    return orc


class TestOrchestratorRun:
    async def test_run_returns_dict_with_required_keys(self, logger):
        orc = _build_full_mock_orchestrator(logger)
        result = await orc.run(
            task="python asyncio tutorial",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
            include_stackoverflow=False,
        )
        assert isinstance(result, dict)
        required_keys = {"task", "relevant_context", "context", "open_questions",
                         "recommended_next_context", "metrics"}
        assert required_keys.issubset(result.keys())

    async def test_run_task_field_matches_input(self, logger):
        orc = _build_full_mock_orchestrator(logger)
        task = "build fastapi sqlalchemy crud"
        result = await orc.run(
            task=task,
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        assert result["task"] == task

    async def test_run_metrics_included(self, logger):
        orc = _build_full_mock_orchestrator(logger)
        result = await orc.run(
            task="python asyncio",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        assert "metrics" in result
        assert "timing" in result["metrics"]
        assert "counts" in result["metrics"]

    async def test_run_context_has_required_keys(self, logger):
        orc = _build_full_mock_orchestrator(logger)
        result = await orc.run(
            task="python asyncio",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        ctx = result["context"]
        assert "concepts" in ctx
        assert "code_snippets" in ctx
        assert "api_references" in ctx
        assert "best_practices" in ctx
        assert "implementation_patterns" in ctx
        assert "stackoverflow_answers" in ctx

    async def test_run_relevant_context_is_list(self, logger):
        orc = _build_full_mock_orchestrator(logger)
        result = await orc.run(
            task="python asyncio",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        assert isinstance(result["relevant_context"], list)

    async def test_run_metrics_reset_between_calls(self, logger):
        """Calling run() twice should not accumulate stale metrics from the first call."""
        orc = _build_full_mock_orchestrator(logger)
        kwargs = dict(
            task="query one",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        r1 = await orc.run(**kwargs)
        r2 = await orc.run(**kwargs)
        # Queries generated should be recorded fresh each time
        assert r1["metrics"]["counts"]["queries"] == r2["metrics"]["counts"]["queries"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestOrchestratorErrorHandling:
    async def test_httpx_error_returns_graceful_fallback(self, logger):
        import httpx
        orc = _make_orchestrator(logger)
        orc._search.multi_search = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        orc._github.mine = AsyncMock(return_value=[])
        result = await orc.run(
            task="python asyncio",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        assert isinstance(result, dict)
        assert "task" in result
        assert "Pipeline failed" in result["open_questions"][0]

    async def test_timeout_error_returns_graceful_fallback(self, logger):
        import asyncio
        orc = _make_orchestrator(logger)
        orc._search.multi_search = AsyncMock(side_effect=asyncio.TimeoutError())
        orc._github.mine = AsyncMock(return_value=[])
        result = await orc.run(
            task="python asyncio",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        assert isinstance(result, dict)
        assert result["relevant_context"] == []

    async def test_unexpected_error_propagates(self, logger):
        """A truly unexpected bug (e.g., AttributeError) must re-raise so the actor fails visibly."""
        orc = _make_orchestrator(logger)
        orc._search.multi_search = AsyncMock(side_effect=AttributeError("bug: attribute missing"))
        orc._github.mine = AsyncMock(return_value=[])
        with pytest.raises(AttributeError):
            await orc.run(
                task="python asyncio",
                max_sources=3,
                allowed_domains=[],
                include_github=False,
                include_github_code_search=False,
                github_code_languages=[],
                max_code_snippets=5,
            )

    async def test_zero_pages_crawled_returns_empty_context(self, logger):
        orc = _build_full_mock_orchestrator(logger)
        orc._crawler.crawl = AsyncMock(return_value=[])
        result = await orc.run(
            task="python asyncio",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        assert isinstance(result, dict)
        # May have recommended_next_context suggesting a retry
        assert "recommended_next_context" in result


# ---------------------------------------------------------------------------
# LLM synthesis disabled
# ---------------------------------------------------------------------------

class TestOrchestratorLlmDisabled:
    async def test_llm_guidance_is_none_when_not_configured(self, logger):
        orc = _build_full_mock_orchestrator(logger)
        result = await orc.run(
            task="python asyncio",
            max_sources=3,
            allowed_domains=[],
            include_github=False,
            include_github_code_search=False,
            github_code_languages=[],
            max_code_snippets=5,
        )
        # LLM synthesis disabled → llm_guidance absent or None
        if "llm_guidance" in result:
            assert result["llm_guidance"] is None
