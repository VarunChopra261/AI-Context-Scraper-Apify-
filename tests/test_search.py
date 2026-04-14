"""Stress tests for search.py — every assertion is load-bearing."""

import pytest

from src.search import PRIORITY_DOMAINS, QueryExpander, SearchClient, SearchResult


@pytest.fixture
def expander():
    return QueryExpander()


# ---------------------------------------------------------------------------
# SearchResult dataclass
# ---------------------------------------------------------------------------

class TestSearchResultDataclass:
    def test_required_fields(self):
        sr = SearchResult(title="T", url="https://x.com", snippet="S")
        assert sr.title == "T"
        assert sr.url == "https://x.com"
        assert sr.snippet == "S"

    def test_default_source(self):
        sr = SearchResult(title="T", url="u", snippet="s")
        assert sr.source == "web"

    def test_default_score(self):
        sr = SearchResult(title="T", url="u", snippet="s")
        assert sr.score == 0.0

    def test_custom_source_and_score(self):
        sr = SearchResult(title="T", url="u", snippet="s", source="github", score=3.5)
        assert sr.source == "github"
        assert sr.score == 3.5


# ---------------------------------------------------------------------------
# PRIORITY_DOMAINS
# ---------------------------------------------------------------------------

class TestPriorityDomains:
    def test_is_dict(self):
        assert isinstance(PRIORITY_DOMAINS, dict)

    def test_non_empty(self):
        assert len(PRIORITY_DOMAINS) > 0

    def test_all_domains_are_strings(self):
        for d in PRIORITY_DOMAINS:
            assert isinstance(d, str)

    def test_all_scores_positive_floats_or_ints(self):
        for domain, score in PRIORITY_DOMAINS.items():
            assert isinstance(score, (int, float)), f"{domain} has non-numeric score"
            assert score > 0, f"{domain} has non-positive score"

    def test_known_high_value_domains_present(self):
        assert "docs.python.org" in PRIORITY_DOMAINS
        assert "fastapi.tiangolo.com" in PRIORITY_DOMAINS

    def test_known_domains_have_high_scores(self):
        assert PRIORITY_DOMAINS["docs.python.org"] >= 3.0
        assert PRIORITY_DOMAINS["fastapi.tiangolo.com"] >= 3.0


# ---------------------------------------------------------------------------
# SearchClient._domain_boost
# ---------------------------------------------------------------------------

class TestDomainBoost:
    def test_exact_match_returns_boost(self):
        assert SearchClient._domain_boost("https://docs.python.org/3/library/asyncio.html") > 0

    def test_fastapi_subdomain_returns_boost(self):
        assert SearchClient._domain_boost("https://fastapi.tiangolo.com/tutorial/") > 0

    def test_unknown_domain_returns_zero(self):
        assert SearchClient._domain_boost("https://random-blog-xyz.io/post/123") == 0.0

    def test_www_stripped_from_domain(self):
        """www.docs.python.org should still get a boost."""
        boost = SearchClient._domain_boost("https://www.docs.python.org/3/")
        # 'www.' is stripped → 'docs.python.org' matches exactly
        assert boost > 0

    def test_returns_correct_boost_value(self):
        expected = PRIORITY_DOMAINS["docs.python.org"]
        actual = SearchClient._domain_boost("https://docs.python.org/3/tutorial/")
        assert actual == expected

    def test_subdomain_of_priority_domain_gets_boost(self):
        # e.g. "api.fastapi.tiangolo.com" should match "fastapi.tiangolo.com" via endswith
        boost = SearchClient._domain_boost("https://api.fastapi.tiangolo.com/docs")
        assert boost > 0

    def test_similar_but_different_domain_no_boost(self):
        # "notdocs.python.org" should NOT match "docs.python.org"
        boost = SearchClient._domain_boost("https://notdocs.python.org/3/")
        assert boost == 0.0

    def test_empty_url_does_not_crash(self):
        boost = SearchClient._domain_boost("")
        assert boost == 0.0


# ---------------------------------------------------------------------------
# QueryExpander.extract_signals
# ---------------------------------------------------------------------------

class TestExtractSignals:
    def test_all_keys_present(self, expander):
        signals = expander.extract_signals("Simple task")
        for key in ("libraries", "frameworks", "language", "keywords", "concepts"):
            assert key in signals

    def test_language_always_python(self, expander):
        signals = expander.extract_signals("anything at all")
        assert signals["language"] == ["python"]

    def test_known_library_detected(self, expander):
        signals = expander.extract_signals("Use FastAPI with Redis for caching")
        assert "fastapi" in signals["libraries"]
        assert "redis" in signals["libraries"]

    def test_libraries_equals_frameworks(self, expander):
        """libraries and frameworks must be identical lists."""
        signals = expander.extract_signals("FastAPI Django redis")
        assert signals["libraries"] == signals["frameworks"]

    def test_unknown_terms_not_in_libraries(self, expander):
        signals = expander.extract_signals("Build something with myownlib")
        assert "myownlib" not in signals["libraries"]

    def test_concepts_capped_at_20(self, expander):
        # 30 unique long words, all > 2 chars
        task = " ".join([f"word{i}" for i in range(30)])
        signals = expander.extract_signals(task)
        assert len(signals["concepts"]) <= 20

    def test_short_words_filtered_from_keywords(self, expander):
        """Words of 2 chars or fewer must be excluded from keyword_set."""
        signals = expander.extract_signals("to be or not to be")
        # "to"=2, "be"=2, "or"=2, "not"=3 → filter: only words len > 2
        kw = signals["keywords"]
        for w in kw:
            assert len(w) > 2

    def test_keywords_sorted(self, expander):
        signals = expander.extract_signals("bravo alpha charlie")
        assert signals["keywords"] == sorted(signals["keywords"])

    def test_all_libraries_detected(self, expander):
        """Every library in known_libraries should be extracted when present."""
        known = [
            "fastapi", "boto3", "langchain", "chroma", "pydantic", "django",
            "flask", "pytorch", "tensorflow", "sqlalchemy", "pandas", "numpy",
            "openai", "anthropic", "redis", "postgres", "mongodb", "kafka", "celery",
        ]
        task = " ".join(known)
        signals = expander.extract_signals(task)
        for lib in known:
            assert lib in signals["libraries"], f"{lib} not detected"


# ---------------------------------------------------------------------------
# QueryExpander.expand
# ---------------------------------------------------------------------------

class TestExpandQueries:
    def test_always_includes_original_task(self, expander):
        signals = expander.extract_signals("Build a FastAPI app")
        queries = expander.expand("Build a FastAPI app", signals=signals)
        assert "Build a FastAPI app" in queries

    def test_limit_respected(self, expander):
        signals = expander.extract_signals("Build complex microservice with FastAPI")
        queries = expander.expand("Build complex microservice with FastAPI", signals=signals, limit=3)
        assert len(queries) <= 3

    def test_no_duplicates(self, expander):
        signals = expander.extract_signals("python tutorial")
        queries = expander.expand("python tutorial", signals=signals)
        normalized = [" ".join(q.lower().split()) for q in queries]
        assert len(normalized) == len(set(normalized))

    def test_includes_tutorial_suffix(self, expander):
        signals = expander.extract_signals("Build FastAPI endpoint")
        queries = expander.expand("Build FastAPI endpoint", signals=signals, limit=20)
        assert any("tutorial" in q.lower() for q in queries)

    def test_includes_api_reference_suffix(self, expander):
        signals = expander.extract_signals("Build FastAPI endpoint")
        queries = expander.expand("Build FastAPI endpoint", signals=signals, limit=20)
        assert any("api reference" in q.lower() for q in queries)

    def test_includes_best_practices_suffix(self, expander):
        signals = expander.extract_signals("Build FastAPI endpoint")
        queries = expander.expand("Build FastAPI endpoint", signals=signals, limit=20)
        assert any("best practices" in q.lower() for q in queries)

    def test_default_limit_is_6(self, expander):
        signals = expander.extract_signals("FastAPI Redis caching")
        queries = expander.expand("FastAPI Redis caching", signals=signals)
        assert len(queries) <= 6

    def test_returns_list_of_strings(self, expander):
        signals = expander.extract_signals("any task")
        queries = expander.expand("any task", signals=signals)
        assert isinstance(queries, list)
        for q in queries:
            assert isinstance(q, str)

    def test_all_queries_non_empty(self, expander):
        signals = expander.extract_signals("FastAPI endpoint")
        for q in expander.expand("FastAPI endpoint", signals=signals, limit=20):
            assert q.strip() != ""

    def test_task_with_library_produces_core_phrase_query(self, expander):
        """A task with known libraries should produce a core-phrase query (lib + concepts)."""
        signals = expander.extract_signals("Upload a file using FastAPI")
        queries = expander.expand("Upload a file using FastAPI", signals=signals, limit=20)
        # Should contain a query that is NOT the original task and NOT a suffixed task
        non_task_queries = [q for q in queries if q != "Upload a file using FastAPI" and "Upload a file using FastAPI" not in q]
        # At least one should be a short core-phrase query
        assert any(len(q.split()) < 10 for q in non_task_queries)
