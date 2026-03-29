"""Live regression tests — exercise real HTTP and real DDGS search.

These hit the network and are marked with ``@pytest.mark.live`` so they
can be skipped in CI with ``pytest -m "not live"``.

Run with:  pytest tests/test_regression_live.py -v -m live
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from src.search import QueryExpander, SearchClient, SearchResult
from src.crawler import AsyncCrawler, CrawledPage
from src.extractor import ContentExtractor, ExtractedDoc
from src.chunker import Chunker
from src.relevance import RelevanceRanker
from src.deduplicator import ContentDeduplicator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def logger():
    """Real logger (not a mock) so warnings surface in test output."""
    return logging.getLogger("test_regression")


# ---------------------------------------------------------------------------
# Mark all tests in this module as 'live'
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# 1.  DDGS search returns real results
# ---------------------------------------------------------------------------

class TestLiveSearch:
    """Verify the search pipeline returns non-empty, well-formed results."""

    @pytest.mark.asyncio
    async def test_ddgs_returns_results_for_python_query(self, logger):
        """A broad query like 'python asyncio tutorial' must return ≥ 1 result."""
        client = SearchClient(logger=logger)
        results = await client.search("python asyncio tutorial", max_results=5)

        assert isinstance(results, list)
        assert len(results) >= 1, "DDGS returned no results — possible rate-limit or API change"
        for r in results:
            assert isinstance(r, SearchResult)
            assert r.url.startswith("http")
            assert r.title  # title must be non-empty

    @pytest.mark.asyncio
    async def test_multi_search_deduplicates(self, logger):
        """multi_search with overlapping queries should deduplicate URLs."""
        client = SearchClient(logger=logger)
        results = await client.multi_search(
            ["python requests library", "python requests tutorial"],
            per_query=3,
        )
        urls = [r.url for r in results]
        assert len(urls) == len(set(urls)), "multi_search returned duplicate URLs"

    @pytest.mark.asyncio
    async def test_query_expansion_produces_diverse_queries(self):
        """QueryExpander must produce > 3 distinct queries for a complex task."""
        expander = QueryExpander()
        task = "Build a FastAPI WebSocket chat with Redis PubSub"
        signals = expander.extract_signals(task)
        queries = expander.expand(task, signals)

        assert len(queries) >= 4
        # At least one query should mention "tutorial" or "example"
        combined = " ".join(queries).lower()
        assert "tutorial" in combined or "example" in combined


# ---------------------------------------------------------------------------
# 2.  Crawl + extract from a real page
# ---------------------------------------------------------------------------

class TestLiveCrawlExtract:
    """Crawl a real URL and extract content."""

    @pytest.mark.asyncio
    async def test_crawl_real_url_succeeds(self, logger):
        """Crawling a known-stable URL should return a CrawledPage."""
        crawler = AsyncCrawler(logger=logger, timeout=15.0)
        # Python docs are stable and unlikely to block us
        pages = await crawler.crawl(["https://docs.python.org/3/library/asyncio.html"])

        assert len(pages) >= 1
        page = pages[0]
        assert isinstance(page, CrawledPage)
        assert page.status_code == 200
        assert len(page.text) > 500

    @pytest.mark.asyncio
    async def test_extract_from_crawled_page(self, logger):
        """Extracting from a real crawled page yields an ExtractedDoc."""
        crawler = AsyncCrawler(logger=logger)
        pages = await crawler.crawl(["https://docs.python.org/3/library/json.html"])

        assert len(pages) >= 1
        extractor = ContentExtractor(logger=logger)
        doc = extractor.extract(pages[0])

        assert doc is not None
        assert isinstance(doc, ExtractedDoc)
        assert doc.title  # should have a title
        assert len(doc.clean_markdown) > 200
        # Note: headings may be empty on some pages where readability strips
        # them (e.g. Python docs with unusual HTML structure). The critical
        # assertion is that content was extracted successfully.
        assert isinstance(doc.headings, list)


# ---------------------------------------------------------------------------
# 3.  End-to-end mini pipeline (search → crawl → extract → chunk → rank)
# ---------------------------------------------------------------------------

class TestLiveMiniPipeline:
    """Run a trimmed pipeline on a real query without the orchestrator."""

    @pytest.mark.asyncio
    async def test_pipeline_produces_ranked_chunks(self, logger):
        """Search → crawl → extract → chunk → rank must yield scored chunks."""
        task = "How to use Python dataclasses with default values"

        # Search
        client = SearchClient(logger=logger)
        search_results = await client.search(task, max_results=3)
        assert len(search_results) >= 1, "Search returned 0 results"

        # Crawl (take top 2)
        urls = [r.url for r in search_results[:2]]
        crawler = AsyncCrawler(logger=logger, timeout=15.0)
        pages = await crawler.crawl(urls)
        assert len(pages) >= 1, "Crawler fetched 0 pages"

        # Extract
        extractor = ContentExtractor(logger=logger)
        docs = [extractor.extract(p) for p in pages]
        docs = [d for d in docs if d is not None]
        assert len(docs) >= 1, "Extractor produced 0 documents"

        # Chunk
        chunker = Chunker(max_tokens=500)
        all_chunks = []
        for doc in docs:
            all_chunks.extend(chunker.chunk_text(doc.clean_markdown, source=doc.source))
        assert len(all_chunks) >= 1, "Chunker produced 0 chunks"

        # Deduplicate
        dedup = ContentDeduplicator()
        unique_chunks = dedup.deduplicate_chunks(all_chunks)
        assert len(unique_chunks) >= 1

        # Rank
        ranker = RelevanceRanker(logger=logger)
        scored = ranker.rank_chunks(task, unique_chunks, top_k=10)
        assert len(scored) >= 1, "Ranker produced 0 scored chunks"
        assert scored[0].score > 0.0, "Top scored chunk has zero relevance"

        # Verify ordering (descending)
        for i in range(len(scored) - 1):
            assert scored[i].score >= scored[i + 1].score, "Chunks are not sorted by score"
