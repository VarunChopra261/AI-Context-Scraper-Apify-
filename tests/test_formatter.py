"""Tests for formatter.py module."""

import pytest

from src.chunker import LLMChunk
from src.extractor import ExtractedDoc, ExtractedSnippet
from src.formatter import ContextFormatter
from src.pattern_detector import ImplementationPattern, PatternType
from src.relevance import BucketizedContext, ScoredChunk, ScoredSnippet
from src.stackoverflow_miner import StackOverflowAnswer


@pytest.fixture
def formatter():
    """Create ContextFormatter instance."""
    return ContextFormatter()


def _make_doc(source="https://example.com", title="Test Doc", summary="Test summary"):
    """Helper to build an ExtractedDoc."""
    return ExtractedDoc(
        source=source,
        title=title,
        summary=summary,
        clean_markdown="# Test\nContent here.",
        headings=["Test"],
        snippets=[],
        api_references=[{"library": "fastapi", "function": "FastAPI()", "description": "Creates app", "source": source}],
        best_practices=[{"practice": "Use async endpoints", "reason": "Better perf", "source": source}],
    )


def _make_scored_chunk(text="Sample chunk", tokens=100, source="https://example.com", score=0.8):
    """Helper to build a ScoredChunk."""
    return ScoredChunk(chunk=LLMChunk(text=text, tokens=tokens, source=source), score=score)


def _make_scored_snippet(code="print('hello')", lang="python", source="https://example.com", score=0.9):
    """Helper to build a ScoredSnippet."""
    return ScoredSnippet(
        snippet=ExtractedSnippet(language=lang, code=code, source=source, description="Test snippet", score=1.0),
        score=score,
    )


def _make_pattern(pattern_type=PatternType.ASYNC_CONCURRENCY, code="async def f(): pass", source="https://example.com"):
    """Helper to build an ImplementationPattern."""
    return ImplementationPattern(
        pattern_type=pattern_type,
        description="Async pattern",
        code_snippet=code,
        source=source,
        confidence=0.9,
    )


def _make_so_answer():
    """Helper to build a StackOverflowAnswer."""
    return StackOverflowAnswer(
        question_title="How to use FastAPI?",
        question_url="https://stackoverflow.com/q/123",
        answer_body="Here's how...",
        score=50,
        accepted=True,
        tags=["python", "fastapi"],
    )


class TestResultFormatting:
    """Test result formatting functionality."""

    def test_format_basic_result(self, formatter):
        """Test formatting basic result structure."""
        doc = _make_doc()
        chunk = _make_scored_chunk()
        snippet = _make_scored_snippet()

        result = formatter.format(
            task="Build a FastAPI app",
            docs=[doc],
            scored_chunks=[chunk],
            scored_snippets=[snippet],
            max_code_snippets=20,
        )

        assert result["task"] == "Build a FastAPI app"
        assert "context" in result

    def test_format_includes_all_context_types(self, formatter):
        """Test formatted result includes all context types."""
        result = formatter.format(
            task="Test task",
            docs=[_make_doc()],
            scored_chunks=[_make_scored_chunk()],
            scored_snippets=[_make_scored_snippet()],
            max_code_snippets=20,
            patterns=[_make_pattern()],
            stackoverflow_answers=[_make_so_answer()],
        )

        context = result["context"]
        assert "concepts" in context
        assert "code_snippets" in context
        assert "api_references" in context
        assert "best_practices" in context
        assert "implementation_patterns" in context
        assert "stackoverflow_answers" in context
        assert "llm_chunks" in context

    def test_format_converts_chunks(self, formatter):
        """Test chunks are converted to proper format."""
        chunks = [
            _make_scored_chunk(text="Chunk 1", tokens=100, source="https://example.com/1"),
            _make_scored_chunk(text="Chunk 2", tokens=150, source="https://example.com/2"),
        ]

        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=chunks,
            scored_snippets=[],
            max_code_snippets=20,
        )

        llm_chunks = result["context"]["llm_chunks"]
        assert len(llm_chunks) == 2
        assert llm_chunks[0]["text"] == "Chunk 1"
        assert llm_chunks[0]["tokens"] == 100
        assert llm_chunks[0]["source"] == "https://example.com/1"


class TestContextFormatting:
    """Test context data formatting."""

    def test_format_empty_docs(self, formatter):
        """Test formatting with no docs or snippets."""
        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=[],
            scored_snippets=[],
            max_code_snippets=20,
        )

        context = result["context"]
        assert context["concepts"] == []
        assert context["code_snippets"] == []
        assert context["api_references"] == []

    def test_format_preserves_context_fields(self, formatter):
        """Test all context fields are preserved."""
        result = formatter.format(
            task="Test",
            docs=[_make_doc()],
            scored_chunks=[_make_scored_chunk()],
            scored_snippets=[_make_scored_snippet()],
            max_code_snippets=20,
            patterns=[_make_pattern()],
            stackoverflow_answers=[_make_so_answer()],
        )

        context = result["context"]

        # Concepts
        assert len(context["concepts"]) == 1
        assert context["concepts"][0]["title"] == "Test Doc"

        # Code snippets
        assert len(context["code_snippets"]) == 1
        assert context["code_snippets"][0]["language"] == "python"

        # API references
        assert len(context["api_references"]) == 1
        assert context["api_references"][0]["library"] == "fastapi"

        # Best practices
        assert len(context["best_practices"]) == 1
        assert context["best_practices"][0]["practice"] == "Use async endpoints"

        # Implementation patterns
        assert len(context["implementation_patterns"]) == 1
        assert context["implementation_patterns"][0]["pattern_type"] == PatternType.ASYNC_CONCURRENCY

        # StackOverflow answers
        assert len(context["stackoverflow_answers"]) == 1
        assert context["stackoverflow_answers"][0]["accepted"] is True


class TestChunkFormatting:
    """Test chunk formatting."""

    def test_format_single_chunk(self, formatter):
        """Test formatting single chunk."""
        chunk = _make_scored_chunk(text="Test content", tokens=50, source="https://example.com")

        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=[chunk],
            scored_snippets=[],
            max_code_snippets=20,
        )

        llm_chunks = result["context"]["llm_chunks"]
        assert len(llm_chunks) == 1
        assert llm_chunks[0]["text"] == "Test content"
        assert llm_chunks[0]["tokens"] == 50

    def test_format_multiple_chunks(self, formatter):
        """Test formatting multiple chunks."""
        chunks = [_make_scored_chunk(text=f"Chunk {i}", tokens=i * 10) for i in range(5)]

        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=chunks,
            scored_snippets=[],
            max_code_snippets=20,
        )

        llm_chunks = result["context"]["llm_chunks"]
        assert len(llm_chunks) == 5

    def test_format_empty_chunks(self, formatter):
        """Test formatting with no chunks."""
        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=[],
            scored_snippets=[],
            max_code_snippets=20,
        )

        assert result["context"]["llm_chunks"] == []


class TestSnippetLimiting:
    """Test code snippet limiting."""

    def test_max_code_snippets_respected(self, formatter):
        """Test max_code_snippets limits output."""
        snippets = [_make_scored_snippet(code=f"code_{i}") for i in range(10)]

        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=[],
            scored_snippets=snippets,
            max_code_snippets=3,
        )

        assert len(result["context"]["code_snippets"]) == 3


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_format_no_patterns(self, formatter):
        """Test formatting with no patterns."""
        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=[],
            scored_snippets=[],
            max_code_snippets=20,
            patterns=None,
        )

        assert result["context"]["implementation_patterns"] == []

    def test_format_no_stackoverflow(self, formatter):
        """Test formatting with no StackOverflow answers."""
        result = formatter.format(
            task="Test",
            docs=[],
            scored_chunks=[],
            scored_snippets=[],
            max_code_snippets=20,
            stackoverflow_answers=None,
        )

        assert result["context"]["stackoverflow_answers"] == []

    def test_unique_dicts_deduplication(self, formatter):
        """Test _unique_dicts removes duplicates by key."""
        items = [
            {"function": "foo()", "lib": "a"},
            {"function": "foo()", "lib": "b"},
            {"function": "bar()", "lib": "c"},
        ]
        result = ContextFormatter._unique_dicts(items, key="function")
        assert len(result) == 2
        assert result[0]["function"] == "foo()"
        assert result[1]["function"] == "bar()"


class TestRelevantContextFormatting:
    """Test skill-driven relevant context formatting."""

    def test_format_relevant_context_basic(self, formatter):
        """Test format_relevant_context populates skill required fields."""
        doc = _make_doc(source="https://docs.com")
        critical_chunk = _make_scored_chunk(text="critical chunk", source="https://docs.com", score=0.9)
        helpful_chunk = _make_scored_chunk(text="helpful chunk", score=0.6)

        crit_snip = _make_scored_snippet(code="print('crit')", score=0.85)
        help_snip = _make_scored_snippet(code="print('help')", score=0.65)

        bucketized = BucketizedContext(
            critical_chunks=[critical_chunk],
            helpful_chunks=[helpful_chunk],
            critical_snippets=[crit_snip],
            helpful_snippets=[help_snip],
        )

        result = formatter.format_relevant_context(
            task="Test relevant context",
            docs=[doc],
            bucketized=bucketized,
            max_code_snippets=20,
            patterns=[_make_pattern()],
            stackoverflow_answers=[_make_so_answer()],
        )

        # Check top-level keys
        assert result["task"] == "Test relevant context"
        assert "relevant_context" in result
        assert "open_questions" in result
        assert "recommended_next_context" in result
        assert "context" in result

        # Check relevant context list (2 items: critical + helpful chunks)
        assert len(result["relevant_context"]) == 2

        # Verify bucket labels
        context = result["context"]
        assert context["concepts"][0]["title"] == "Test Doc"

        assert len(context["code_snippets"]) == 2
        assert context["code_snippets"][0]["bucket"] == "critical"
        assert context["code_snippets"][1]["bucket"] == "helpful"

        # Verify questions are lists
        assert isinstance(result["open_questions"], list)
        assert isinstance(result["recommended_next_context"], list)

    def test_open_questions_generation(self, formatter):
        """Test open questions are conditionally generated when data is missing."""
        bucketized = BucketizedContext([], [], [], [])
        result = formatter.format_relevant_context(
            task="Empty test",
            docs=[],
            bucketized=bucketized,
            max_code_snippets=20,
        )
        questions = result["open_questions"]
        assert any("code examples" in q for q in questions)
        assert len(result["relevant_context"]) == 0
