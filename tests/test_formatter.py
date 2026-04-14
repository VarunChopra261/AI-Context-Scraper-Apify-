"""Stress tests for formatter.py — every assertion is load-bearing."""

import pytest

from src.chunker import LLMChunk
from src.extractor import ExtractedDoc, ExtractedSnippet
from src.formatter import ContextFormatter
from src.pattern_detector import ImplementationPattern, PatternType
from src.relevance import BucketizedContext, ScoredChunk, ScoredSnippet
from src.stackoverflow_miner import StackOverflowAnswer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(
    source="https://docs.example.com",
    title="My Doc",
    summary="A useful summary.",
    api_refs=None,
    best_practices=None,
):
    return ExtractedDoc(
        source=source,
        title=title,
        summary=summary,
        clean_markdown="# My Doc\nContent.",
        headings=["My Doc"],
        snippets=[],
        api_references=api_refs or [
            {"library": "fastapi", "function": "FastAPI()", "description": "Creates app", "source": source}
        ],
        best_practices=best_practices or [
            {"practice": "Use async endpoints.", "reason": "Better perf.", "source": source}
        ],
    )


def _make_scored_chunk(text="Sample chunk text.", tokens=50, source="https://docs.example.com", score=0.8):
    return ScoredChunk(chunk=LLMChunk(text=text, tokens=tokens, source=source), score=score)


def _make_scored_snippet(code="print('hello')\nprint('world')", lang="python", source="https://docs.example.com", score=0.9):
    return ScoredSnippet(
        snippet=ExtractedSnippet(language=lang, code=code, source=source, description="A snippet", score=1.0),
        score=score,
    )


def _make_pattern(ptype=PatternType.ASYNC_CONCURRENCY, code="async def f(): pass", source="https://x.com", confidence=0.9):
    return ImplementationPattern(
        pattern_type=ptype,
        description="Pattern description",
        code_snippet=code,
        source=source,
        confidence=confidence,
    )


def _make_so_answer(title="How?", url="https://stackoverflow.com/q/1", score=10, accepted=True):
    return StackOverflowAnswer(
        question_title=title,
        question_url=url,
        answer_body="Here is the answer with code.",
        score=score,
        accepted=accepted,
        tags=["python"],
    )


@pytest.fixture
def formatter():
    return ContextFormatter()


# ---------------------------------------------------------------------------
# ContextFormatter.format() — structural invariants
# ---------------------------------------------------------------------------

class TestFormatStructure:
    def test_top_level_keys_present(self, formatter):
        result = formatter.format("task", [], [], [], max_code_snippets=10)
        assert "task" in result
        assert "context" in result

    def test_task_field_exact_value(self, formatter):
        result = formatter.format("Build a FastAPI app", [], [], [], max_code_snippets=10)
        assert result["task"] == "Build a FastAPI app"

    def test_context_has_all_seven_keys(self, formatter):
        result = formatter.format("t", [], [], [], max_code_snippets=10)
        ctx = result["context"]
        for key in ("concepts", "code_snippets", "api_references", "best_practices",
                    "implementation_patterns", "stackoverflow_answers", "llm_chunks"):
            assert key in ctx, f"Missing context key: {key}"

    def test_empty_inputs_produce_empty_lists(self, formatter):
        result = formatter.format("t", [], [], [], max_code_snippets=10)
        ctx = result["context"]
        assert ctx["concepts"] == []
        assert ctx["code_snippets"] == []
        assert ctx["api_references"] == []
        assert ctx["best_practices"] == []
        assert ctx["implementation_patterns"] == []
        assert ctx["stackoverflow_answers"] == []
        assert ctx["llm_chunks"] == []


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------

class TestConcepts:
    def test_doc_with_no_summary_excluded(self, formatter):
        doc = _make_doc(summary="")
        result = formatter.format("t", [doc], [], [], max_code_snippets=10)
        assert result["context"]["concepts"] == []

    def test_doc_with_summary_included(self, formatter):
        doc = _make_doc(title="Guide", summary="Important guide.")
        result = formatter.format("t", [doc], [], [], max_code_snippets=10)
        concepts = result["context"]["concepts"]
        assert len(concepts) == 1
        assert concepts[0]["title"] == "Guide"
        assert concepts[0]["summary"] == "Important guide."

    def test_concepts_capped_at_30(self, formatter):
        docs = [_make_doc(source=f"https://docs.example.com/{i}", title=f"Doc {i}", summary=f"Sum {i}") for i in range(40)]
        result = formatter.format("t", docs, [], [], max_code_snippets=10)
        assert len(result["context"]["concepts"]) == 30

    def test_concept_source_matches_doc_source(self, formatter):
        doc = _make_doc(source="https://specific.source.io")
        result = formatter.format("t", [doc], [], [], max_code_snippets=10)
        assert result["context"]["concepts"][0]["source"] == "https://specific.source.io"


# ---------------------------------------------------------------------------
# Code snippets / max_code_snippets
# ---------------------------------------------------------------------------

class TestCodeSnippets:
    def test_max_code_snippets_limit_enforced(self, formatter):
        snippets = [_make_scored_snippet(code=f"code_{i}\nline2") for i in range(20)]
        result = formatter.format("t", [], [], snippets, max_code_snippets=5)
        assert len(result["context"]["code_snippets"]) == 5

    def test_snippet_fields_present(self, formatter):
        snippet = _make_scored_snippet()
        result = formatter.format("t", [], [], [snippet], max_code_snippets=10)
        s = result["context"]["code_snippets"][0]
        assert "language" in s
        assert "description" in s
        assert "code" in s
        assert "source" in s

    def test_snippet_language_value_matches(self, formatter):
        snippet = _make_scored_snippet(lang="javascript")
        result = formatter.format("t", [], [], [snippet], max_code_snippets=10)
        assert result["context"]["code_snippets"][0]["language"] == "javascript"

    def test_zero_max_snippets(self, formatter):
        snippets = [_make_scored_snippet() for _ in range(5)]
        result = formatter.format("t", [], [], snippets, max_code_snippets=0)
        assert result["context"]["code_snippets"] == []


# ---------------------------------------------------------------------------
# LLM chunks
# ---------------------------------------------------------------------------

class TestLLMChunks:
    def test_chunk_text_token_source_preserved(self, formatter):
        chunk = _make_scored_chunk(text="Important text", tokens=42, source="https://x.com")
        result = formatter.format("t", [], [chunk], [], max_code_snippets=10)
        lc = result["context"]["llm_chunks"][0]
        assert lc["text"] == "Important text"
        assert lc["tokens"] == 42
        assert lc["source"] == "https://x.com"

    def test_chunk_order_preserved(self, formatter):
        chunks = [_make_scored_chunk(text=f"chunk_{i}", source=f"https://s.com/{i}") for i in range(5)]
        result = formatter.format("t", [], chunks, [], max_code_snippets=10)
        texts = [c["text"] for c in result["context"]["llm_chunks"]]
        assert texts == [f"chunk_{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# API references
# ---------------------------------------------------------------------------

class TestApiReferences:
    def test_refs_from_docs_included(self, formatter):
        doc = _make_doc(api_refs=[
            {"library": "boto3", "function": "s3.upload_file()", "description": "Uploads", "source": "https://x.com"},
        ])
        result = formatter.format("t", [doc], [], [], max_code_snippets=10)
        fns = [r["function"] for r in result["context"]["api_references"]]
        assert "s3.upload_file()" in fns

    def test_refs_deduplicated_by_function(self, formatter):
        ref = {"library": "requests", "function": "get()", "description": "HTTP GET", "source": "https://x.com"}
        doc1 = _make_doc(source="https://a.com", api_refs=[ref])
        doc2 = _make_doc(source="https://b.com", api_refs=[ref])
        result = formatter.format("t", [doc1, doc2], [], [], max_code_snippets=10)
        fns = [r["function"] for r in result["context"]["api_references"]]
        assert fns.count("get()") == 1

    def test_api_refs_capped_at_40(self, formatter):
        refs = [
            {"library": f"lib{i}", "function": f"fn_{i}()", "description": "desc", "source": "https://x.com"}
            for i in range(60)
        ]
        doc = _make_doc(api_refs=refs)
        result = formatter.format("t", [doc], [], [], max_code_snippets=10)
        assert len(result["context"]["api_references"]) <= 40


# ---------------------------------------------------------------------------
# Best practices
# ---------------------------------------------------------------------------

class TestBestPractices:
    def test_practices_from_docs_included(self, formatter):
        doc = _make_doc(best_practices=[
            {"practice": "Always sanitize input.", "reason": "Security.", "source": "https://x.com"},
        ])
        result = formatter.format("t", [doc], [], [], max_code_snippets=10)
        practices = [p["practice"] for p in result["context"]["best_practices"]]
        assert "Always sanitize input." in practices

    def test_practices_deduplicated_by_practice_key(self, formatter):
        p = {"practice": "Use HTTPS always.", "reason": "Security.", "source": "https://x.com"}
        doc1 = _make_doc(source="https://a.com", best_practices=[p])
        doc2 = _make_doc(source="https://b.com", best_practices=[p])
        result = formatter.format("t", [doc1, doc2], [], [], max_code_snippets=10)
        practices = [p["practice"] for p in result["context"]["best_practices"]]
        assert practices.count("Use HTTPS always.") == 1

    def test_practices_capped_at_30(self, formatter):
        pracs = [
            {"practice": f"Do thing {i}.", "reason": "Because.", "source": "https://x.com"}
            for i in range(40)
        ]
        doc = _make_doc(best_practices=pracs)
        result = formatter.format("t", [doc], [], [], max_code_snippets=10)
        assert len(result["context"]["best_practices"]) <= 30


# ---------------------------------------------------------------------------
# Implementation patterns
# ---------------------------------------------------------------------------

class TestImplementationPatterns:
    def test_pattern_none_returns_empty_list(self, formatter):
        result = formatter.format("t", [], [], [], max_code_snippets=10, patterns=None)
        assert result["context"]["implementation_patterns"] == []

    def test_pattern_fields_present(self, formatter):
        pattern = _make_pattern()
        result = formatter.format("t", [], [], [], max_code_snippets=10, patterns=[pattern])
        p = result["context"]["implementation_patterns"][0]
        assert "pattern_type" in p
        assert "description" in p
        assert "code_snippet" in p
        assert "source" in p
        assert "confidence" in p

    def test_pattern_type_is_string_value(self, formatter):
        """format() must output the .value string of PatternType, not the enum object."""
        pattern = _make_pattern(ptype=PatternType.AUTHENTICATION)
        result = formatter.format("t", [], [], [], max_code_snippets=10, patterns=[pattern])
        ptype = result["context"]["implementation_patterns"][0]["pattern_type"]
        assert isinstance(ptype, str), "pattern_type must be a string, not an enum"
        assert ptype == "authentication"

    def test_pattern_code_snippet_truncated_to_1000(self, formatter):
        long_code = "x = 1\n" * 500  # ~3000 chars
        pattern = _make_pattern(code=long_code)
        result = formatter.format("t", [], [], [], max_code_snippets=10, patterns=[pattern])
        assert len(result["context"]["implementation_patterns"][0]["code_snippet"]) <= 1000

    def test_confidence_rounded_to_3dp(self, formatter):
        pattern = _make_pattern(confidence=0.123456789)
        result = formatter.format("t", [], [], [], max_code_snippets=10, patterns=[pattern])
        conf = result["context"]["implementation_patterns"][0]["confidence"]
        assert conf == round(0.123456789, 3)


# ---------------------------------------------------------------------------
# StackOverflow answers
# ---------------------------------------------------------------------------

class TestStackOverflowAnswers:
    def test_none_returns_empty_list(self, formatter):
        result = formatter.format("t", [], [], [], max_code_snippets=10, stackoverflow_answers=None)
        assert result["context"]["stackoverflow_answers"] == []

    def test_answer_fields_present(self, formatter):
        answer = _make_so_answer()
        result = formatter.format("t", [], [], [], max_code_snippets=10, stackoverflow_answers=[answer])
        a = result["context"]["stackoverflow_answers"][0]
        assert "question_title" in a
        assert "question_url" in a
        assert "answer_body" in a
        assert "score" in a
        assert "accepted" in a
        assert "tags" in a

    def test_answer_body_truncated_to_2000(self, formatter):
        long_body = "x" * 5000
        answer = StackOverflowAnswer(
            question_title="Q", question_url="https://so.com/q/1",
            answer_body=long_body, score=1, accepted=False, tags=[],
        )
        result = formatter.format("t", [], [], [], max_code_snippets=10, stackoverflow_answers=[answer])
        assert len(result["context"]["stackoverflow_answers"][0]["answer_body"]) <= 2000

    def test_accepted_flag_preserved(self, formatter):
        answer = _make_so_answer(accepted=True)
        result = formatter.format("t", [], [], [], max_code_snippets=10, stackoverflow_answers=[answer])
        assert result["context"]["stackoverflow_answers"][0]["accepted"] is True


# ---------------------------------------------------------------------------
# _unique_dicts
# ---------------------------------------------------------------------------

class TestUniqueDicts:
    def test_deduplication_by_key(self):
        items = [
            {"function": "foo()", "lib": "a"},
            {"function": "foo()", "lib": "b"},
            {"function": "bar()", "lib": "c"},
        ]
        result = ContextFormatter._unique_dicts(items, key="function")
        assert len(result) == 2
        assert result[0]["function"] == "foo()"
        assert result[1]["function"] == "bar()"

    def test_empty_list_returns_empty(self):
        assert ContextFormatter._unique_dicts([], key="function") == []

    def test_none_value_items_excluded(self):
        items = [{"function": None, "lib": "a"}, {"function": "bar()", "lib": "b"}]
        result = ContextFormatter._unique_dicts(items, key="function")
        assert len(result) == 1
        assert result[0]["function"] == "bar()"

    def test_missing_key_items_excluded(self):
        items = [{"lib": "a"}, {"function": "foo()", "lib": "b"}]
        result = ContextFormatter._unique_dicts(items, key="function")
        assert len(result) == 1

    def test_first_occurrence_kept_not_last(self):
        items = [{"k": "x", "v": "first"}, {"k": "x", "v": "second"}]
        result = ContextFormatter._unique_dicts(items, key="k")
        assert result[0]["v"] == "first"


# ---------------------------------------------------------------------------
# format_relevant_context()
# ---------------------------------------------------------------------------

class TestFormatRelevantContext:
    def test_top_level_keys(self, formatter):
        bucketized = BucketizedContext([], [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        for key in ("task", "relevant_context", "context", "open_questions", "recommended_next_context"):
            assert key in result

    def test_task_field_exact(self, formatter):
        bucketized = BucketizedContext([], [], [], [])
        result = formatter.format_relevant_context("My exact task", [], bucketized, max_code_snippets=10)
        assert result["task"] == "My exact task"

    def test_critical_chunks_in_relevant_context(self, formatter):
        critical = _make_scored_chunk(text="critical chunk", score=0.95)
        bucketized = BucketizedContext([critical], [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        buckets = [rc["bucket"] for rc in result["relevant_context"]]
        assert "critical" in buckets

    def test_helpful_chunks_included_when_critical_lt_3(self, formatter):
        """Helpful chunks appear when critical < 3."""
        helpful = _make_scored_chunk(text="helpful chunk", score=0.65)
        bucketized = BucketizedContext([], [helpful], [], [])  # 0 critical → helpful is included
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        buckets = [rc["bucket"] for rc in result["relevant_context"]]
        assert "helpful" in buckets

    def test_helpful_chunks_excluded_when_critical_gte_3(self, formatter):
        """When critical >= 3, helpful chunks must NOT appear in relevant_context."""
        criticals = [_make_scored_chunk(text=f"critical {i}", score=0.9) for i in range(3)]
        helpful = _make_scored_chunk(text="helpful chunk", score=0.55)
        bucketized = BucketizedContext(criticals, [helpful], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        buckets = [rc["bucket"] for rc in result["relevant_context"]]
        assert "helpful" not in buckets
        assert buckets.count("critical") == 3

    def test_critical_snippets_labeled_critical(self, formatter):
        snippet = _make_scored_snippet()
        bucketized = BucketizedContext([], [], [snippet], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        if result["context"]["code_snippets"]:
            assert result["context"]["code_snippets"][0]["bucket"] == "critical"

    def test_helpful_snippets_labeled_helpful_when_included(self, formatter):
        """0 critical snippets → helpful snippets are included and labeled 'helpful'."""
        helpful_snippet = _make_scored_snippet()
        bucketized = BucketizedContext([], [], [], [helpful_snippet])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        snips = result["context"]["code_snippets"]
        if snips:
            assert snips[0]["bucket"] == "helpful"

    def test_concepts_only_from_kept_sources(self, formatter):
        """Concepts from docs not referenced in any chunk/snippet must be excluded."""
        kept_doc = _make_doc(source="https://kept.com", title="Kept")
        dropped_doc = _make_doc(source="https://dropped.com", title="Dropped")
        chunk = _make_scored_chunk(source="https://kept.com")
        bucketized = BucketizedContext([chunk], [], [], [])
        result = formatter.format_relevant_context("t", [kept_doc, dropped_doc], bucketized, max_code_snippets=10)
        titles = [c["title"] for c in result["context"]["concepts"]]
        assert "Kept" in titles
        assert "Dropped" not in titles

    def test_relevant_context_capped_at_30(self, formatter):
        criticals = [_make_scored_chunk(text=f"crit {i}", score=0.9) for i in range(40)]
        bucketized = BucketizedContext(criticals, [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        assert len(result["relevant_context"]) <= 30

    def test_open_questions_list_type(self, formatter):
        bucketized = BucketizedContext([], [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        assert isinstance(result["open_questions"], list)

    def test_recommended_next_context_list_type(self, formatter):
        bucketized = BucketizedContext([], [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        assert isinstance(result["recommended_next_context"], list)

    def test_open_questions_contains_code_examples_when_no_snippets(self, formatter):
        bucketized = BucketizedContext([], [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        questions = result["open_questions"]
        assert any("code examples" in q for q in questions)

    def test_open_questions_contains_stackoverflow_msg_when_no_answers(self, formatter):
        bucketized = BucketizedContext([], [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        questions = result["open_questions"]
        assert any("stackoverflow" in q.lower() or "StackOverflow" in q for q in questions)

    def test_code_snippet_has_relevance_score(self, formatter):
        snippet = _make_scored_snippet(score=0.77)
        bucketized = BucketizedContext([], [], [snippet], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        if result["context"]["code_snippets"]:
            score = result["context"]["code_snippets"][0]["relevance_score"]
            assert score == round(0.77, 3)

    def test_relevant_context_item_has_relevance_score(self, formatter):
        chunk = _make_scored_chunk(score=0.91)
        bucketized = BucketizedContext([chunk], [], [], [])
        result = formatter.format_relevant_context("t", [], bucketized, max_code_snippets=10)
        assert result["relevant_context"][0]["relevance_score"] == round(0.91, 3)


# ---------------------------------------------------------------------------
# _build_open_questions
# ---------------------------------------------------------------------------

class TestBuildOpenQuestions:
    def test_no_code_snippets_triggers_question(self):
        qs = ContextFormatter._build_open_questions(
            code_snippets=[], so_answers=[], include_helpful=False, helpful_chunks=[]
        )
        assert any("code examples" in q for q in qs)

    def test_no_so_answers_triggers_question(self):
        qs = ContextFormatter._build_open_questions(
            code_snippets=[{"code": "x"}], so_answers=[], include_helpful=False, helpful_chunks=[]
        )
        assert any("stackoverflow" in q.lower() or "StackOverflow" in q for q in qs)

    def test_helpful_but_empty_triggers_question(self):
        qs = ContextFormatter._build_open_questions(
            code_snippets=[{"code": "x"}], so_answers=[{"q": "y"}],
            include_helpful=True, helpful_chunks=[]
        )
        assert any("incomplete" in q.lower() or "few" in q.lower() for q in qs)

    def test_no_questions_when_all_data_present(self):
        qs = ContextFormatter._build_open_questions(
            code_snippets=[{"code": "x"}], so_answers=[{"q": "y"}],
            include_helpful=False, helpful_chunks=[]
        )
        assert qs == []
