"""Tests for search.py module."""

import pytest

from src.search import PRIORITY_DOMAINS, QueryExpander, SearchClient, SearchResult


@pytest.fixture
def expander():
    """Create QueryExpander instance."""
    return QueryExpander()


class TestQueryExpansion:
    """Test query expansion functionality."""

    def test_expand_query_basic(self, expander):
        """Test basic query expansion."""
        signals = expander.extract_signals("Build a FastAPI endpoint")
        expanded = expander.expand(task="Build a FastAPI endpoint", signals=signals)

        assert len(expanded) > 1
        assert "Build a FastAPI endpoint" in expanded
        assert any("tutorial" in q.lower() for q in expanded)

    def test_expand_query_with_framework(self, expander):
        """Test query expansion includes framework terms."""
        signals = expander.extract_signals("Django authentication system")
        expanded = expander.expand(task="Django authentication system", signals=signals)

        combined = " ".join(expanded)
        assert "django" in combined.lower() or "Django" in combined

    def test_expand_query_limits_results(self, expander):
        """Test query expansion respects limit parameter."""
        signals = expander.extract_signals("Build a complex microservice architecture")
        expanded = expander.expand(task="Build a complex microservice architecture", signals=signals, limit=5)

        assert len(expanded) <= 5

    def test_expand_deduplicates(self, expander):
        """Test query expansion removes duplicate queries."""
        signals = expander.extract_signals("python tutorial")
        expanded = expander.expand(task="python tutorial", signals=signals)

        # Should not have duplicate entries (case-insensitive)
        normalized = [" ".join(q.lower().split()) for q in expanded]
        assert len(normalized) == len(set(normalized))


class TestSignalExtraction:
    """Test signal extraction from task descriptions."""

    def test_extract_libraries(self, expander):
        """Test library detection in task description."""
        signals = expander.extract_signals("Build an app using FastAPI and Redis")

        assert "fastapi" in signals["libraries"]
        assert "redis" in signals["libraries"]

    def test_extract_keywords(self, expander):
        """Test keyword extraction from task."""
        signals = expander.extract_signals("Build endpoint with authentication")

        assert "keywords" in signals
        assert len(signals["keywords"]) > 0

    def test_extract_produces_all_keys(self, expander):
        """Test all expected signal keys are present."""
        signals = expander.extract_signals("Simple task")

        assert "libraries" in signals
        assert "frameworks" in signals
        assert "language" in signals
        assert "keywords" in signals
        assert "concepts" in signals


class TestPriorityDomains:
    """Test priority domain configuration."""

    def test_priority_domains_exist(self):
        """Test PRIORITY_DOMAINS is defined at module level."""
        assert isinstance(PRIORITY_DOMAINS, dict)
        assert len(PRIORITY_DOMAINS) > 0

    def test_priority_domains_have_scores(self):
        """Test priority domains have valid boost scores."""
        for domain, score in PRIORITY_DOMAINS.items():
            assert isinstance(domain, str)
            assert isinstance(score, (int, float))
            assert score > 0

    def test_official_docs_prioritized(self):
        """Test official documentation domains have high priority."""
        assert "docs.python.org" in PRIORITY_DOMAINS
        assert "fastapi.tiangolo.com" in PRIORITY_DOMAINS


class TestDomainBoosting:
    """Test domain priority boosting logic."""

    def test_known_domain_gets_boost(self):
        """Test known domains return positive boost."""
        boost = SearchClient._domain_boost("https://docs.python.org/3/library/asyncio.html")
        assert boost > 0

    def test_unknown_domain_gets_zero(self):
        """Test unknown domains return zero boost."""
        boost = SearchClient._domain_boost("https://random-blog.example.com/post")
        assert boost == 0.0

    def test_subdomain_matching(self):
        """Test domain boost handles subdomains correctly."""
        boost = SearchClient._domain_boost("https://fastapi.tiangolo.com/tutorial/")
        assert boost > 0


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating a SearchResult."""
        sr = SearchResult(title="Test", url="https://example.com", snippet="A test result")
        assert sr.title == "Test"
        assert sr.url == "https://example.com"
        assert sr.snippet == "A test result"
        assert sr.source == "web"
        assert sr.score == 0.0
