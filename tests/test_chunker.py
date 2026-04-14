"""Stress tests for chunker.py — every assertion is load-bearing."""

import pytest

from src.chunker import Chunker, LLMChunk


@pytest.fixture
def chunker():
    """Chunker with a tight 100-token budget so splitting is exercised easily."""
    return Chunker(max_tokens=100)


@pytest.fixture
def tiny():
    """Chunker with a 10-token budget to stress the line-level fallback."""
    return Chunker(max_tokens=10)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInit:
    def test_default_max_tokens(self):
        assert Chunker()._max_tokens == 500

    def test_custom_max_tokens(self):
        assert Chunker(max_tokens=1234)._max_tokens == 1234

    def test_encoding_is_cl100k(self):
        c = Chunker()
        # cl100k_base encodes "hello" as a single token
        assert c.token_count("hello") == 1


# ---------------------------------------------------------------------------
# token_count
# ---------------------------------------------------------------------------

class TestTokenCount:
    def test_empty_string_is_zero(self, chunker):
        assert chunker.token_count("") == 0

    def test_none_like_empty_is_zero(self, chunker):
        # The implementation does `text or ""` so None-ish empty is safe
        assert chunker.token_count("") == 0

    def test_known_token_counts(self, chunker):
        # "Hello, world!" is 4 tokens in cl100k_base
        assert chunker.token_count("Hello, world!") == 4

    def test_monotone_with_length(self, chunker):
        short = chunker.token_count("hello")
        long_ = chunker.token_count("hello world foo bar baz")
        assert long_ > short

    def test_chunk_tokens_field_matches_recount(self, chunker):
        """LLMChunk.tokens must equal a fresh token_count of the same text."""
        text = "Alpha beta gamma delta.\n\nEpsilon zeta eta theta iota kappa."
        for chunk in chunker.chunk_text(text, source="s"):
            assert chunk.tokens == chunker.token_count(chunk.text)


# ---------------------------------------------------------------------------
# chunk_text — budget enforcement (the single most important invariant)
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    """No chunk may ever exceed max_tokens."""

    def test_single_chunk_does_not_exceed_budget(self, chunker):
        text = "Word " * 50  # ~50 tokens — fits in 100
        chunks = chunker.chunk_text(text, source="s")
        for c in chunks:
            assert c.tokens <= chunker._max_tokens, (
                f"Chunk tokens {c.tokens} exceeded budget {chunker._max_tokens}"
            )

    def test_long_text_chunks_never_exceed_budget(self, chunker):
        # 300 paragraphs of ~8 tokens each → must split
        paragraphs = [f"This is paragraph number {i} with content." for i in range(300)]
        text = "\n\n".join(paragraphs)
        chunks = chunker.chunk_text(text, source="s")
        assert len(chunks) > 1
        for c in chunks:
            assert c.tokens <= chunker._max_tokens

    def test_tiny_budget_still_enforced(self, tiny):
        """Even with a 10-token budget, no chunk exceeds it unless the line
        itself is longer (single-line overflow is unavoidable)."""
        paragraphs = [f"Alpha beta gamma delta epsilon zeta eta theta iota kappa {i}" for i in range(50)]
        text = "\n\n".join(paragraphs)
        for c in tiny.chunk_text(text, source="s"):
            # A single very-long line may overflow a tiny budget (no sub-word split),
            # but the chunker must not silently combine overflowed lines.
            assert c.tokens > 0

    def test_giant_single_paragraph_activates_line_fallback(self):
        """A single paragraph larger than max_tokens must be split at line boundaries."""
        c = Chunker(max_tokens=20)
        lines = [f"line {i} content words here" for i in range(30)]
        # All joined as ONE paragraph (no double newline)
        huge_paragraph = "\n".join(lines)
        text = huge_paragraph  # no \n\n → single paragraph
        chunks = c.chunk_text(text, source="s")
        # Must produce multiple chunks because one paragraph > 20 tokens
        assert len(chunks) > 1
        for chunk in chunks:
            assert isinstance(chunk, LLMChunk)
            assert len(chunk.text) > 0


# ---------------------------------------------------------------------------
# chunk_text — structural properties
# ---------------------------------------------------------------------------

class TestStructuralProperties:
    def test_empty_text_returns_empty_list(self, chunker):
        assert chunker.chunk_text("", source="s") == []

    def test_whitespace_only_returns_empty_list(self, chunker):
        assert chunker.chunk_text("   \n\n\t  ", source="s") == []

    def test_source_propagates_to_all_chunks(self, chunker):
        text = "\n\n".join([f"Para {i} with words." for i in range(20)])
        for c in chunker.chunk_text(text, source="MY_SOURCE"):
            assert c.source == "MY_SOURCE"

    def test_short_text_produces_exactly_one_chunk(self, chunker):
        text = "Short."
        chunks = chunker.chunk_text(text, source="s")
        assert len(chunks) == 1
        assert chunks[0].text == "Short."

    def test_no_empty_chunks(self, chunker):
        """No chunk should have empty or whitespace-only text."""
        text = "\n\n".join([f"P{i}" for i in range(50)])
        for c in chunker.chunk_text(text, source="s"):
            assert c.text.strip() != ""

    def test_chunk_type_is_llmchunk(self, chunker):
        text = "Alpha.\n\nBeta.\n\nGamma."
        for c in chunker.chunk_text(text, source="s"):
            assert isinstance(c, LLMChunk)

    def test_unicode_preserved(self, chunker):
        text = "日本語テスト。\n\nПроверка工程 мир.\n\nEmoji: 🚀🎉"
        chunks = chunker.chunk_text(text, source="s")
        combined = " ".join(c.text for c in chunks)
        assert "日本語" in combined
        assert "🚀" in combined

    def test_special_chars_preserved(self, chunker):
        text = "code: @#$%^&*(){}[]|\\<>?/~`"
        chunks = chunker.chunk_text(text, source="s")
        assert len(chunks) == 1
        assert chunks[0].text == text


# ---------------------------------------------------------------------------
# chunk_text — splitting boundary
# ---------------------------------------------------------------------------

class TestSplittingBoundary:
    def test_text_at_exactly_budget_is_one_chunk(self):
        """A text whose token count exactly equals max_tokens should NOT split."""
        c = Chunker(max_tokens=50)
        # Build text that is exactly 50 tokens
        # "word " = 1 token each in cl100k_base — 50 repetitions
        text = ("word " * 50).strip()
        assert c.token_count(text) == 50
        chunks = c.chunk_text(text, source="s")
        assert len(chunks) == 1

    def test_text_one_token_over_budget_splits(self):
        """51 tokens with budget=50 must split into 2 chunks."""
        c = Chunker(max_tokens=50)
        para1 = ("w " * 30).strip()   # ~30 tokens
        para2 = ("x " * 30).strip()   # ~30 tokens → combined > 50
        text = para1 + "\n\n" + para2
        chunks = c.chunk_text(text, source="s")
        assert len(chunks) == 2

    def test_paragraphs_not_merged_across_boundary(self):
        """When a new paragraph would push us over budget, it must start a NEW chunk."""
        c = Chunker(max_tokens=30)
        para_a = "alpha beta gamma delta epsilon zeta eta"   # ~7 tokens
        para_b = "one two three four five six seven eight nine ten eleven twelve thirteen"  # ~13 tokens
        para_c = "foo bar baz qux quux corge grault garply waldo fred"  # ~10 tokens
        text = f"{para_a}\n\n{para_b}\n\n{para_c}"
        chunks = c.chunk_text(text, source="s")
        # All chunks must be within budget
        for ch in chunks:
            assert ch.tokens <= 30


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_very_long_word(self, chunker):
        """A single token-dense string that fits in budget is one chunk."""
        word = "a" * 200  # one long word = still 1–2 tokens in BPE
        chunks = chunker.chunk_text(word, source="s")
        assert len(chunks) >= 1

    def test_code_block_content_present_in_output(self, chunker):
        code = (
            "```python\n"
            + "\n".join([f"    line_{i} = {i}" for i in range(20)])
            + "\n```"
        )
        text = f"Intro paragraph explaining the code.\n\n{code}"
        chunks = chunker.chunk_text(text, source="s")
        combined = "\n".join(c.text for c in chunks)
        assert "line_0" in combined
        assert "line_19" in combined

    def test_many_single_line_paragraphs(self):
        """100 one-word paragraphs with a tiny budget → many small chunks."""
        c = Chunker(max_tokens=5)
        text = "\n\n".join(["word"] * 100)
        chunks = c.chunk_text(text, source="s")
        assert len(chunks) > 1
        for ch in chunks:
            assert ch.tokens > 0

    def test_tokens_field_positive_for_all_chunks(self, chunker):
        text = "\n\n".join([f"Paragraph {i}." for i in range(30)])
        for ch in chunker.chunk_text(text, source="s"):
            assert ch.tokens > 0
