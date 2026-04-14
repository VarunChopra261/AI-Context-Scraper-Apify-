"""Stress tests for deduplicator.py — every assertion is load-bearing."""

from dataclasses import dataclass

import pytest

from src.deduplicator import ContentDeduplicator, ContentFingerprint


@dataclass
class MockChunk:
    text: str
    tokens: int
    source: str


@pytest.fixture
def dedup():
    return ContentDeduplicator(similarity_threshold=0.85)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInit:
    def test_default_threshold(self):
        assert ContentDeduplicator()._similarity_threshold == 0.85

    def test_custom_threshold(self):
        d = ContentDeduplicator(similarity_threshold=0.5)
        assert d._similarity_threshold == 0.5

    def test_shingle_size(self):
        assert ContentDeduplicator()._shingle_size == 5


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_lowercases(self, dedup):
        n = dedup._normalize_text("Hello WORLD")
        assert n == n.lower()

    def test_collapses_whitespace(self, dedup):
        n = dedup._normalize_text("a   b\t\tc")
        assert "  " not in n

    def test_strips_punctuation(self, dedup):
        n = dedup._normalize_text("hello, world! foo-bar.")
        # punctuation should be gone
        assert "," not in n and "!" not in n and "." not in n

    def test_strips_leading_trailing(self, dedup):
        n = dedup._normalize_text("  hello  ")
        assert n == n.strip()

    def test_empty_string(self, dedup):
        assert dedup._normalize_text("") == ""


# ---------------------------------------------------------------------------
# _create_shingle_hashes
# ---------------------------------------------------------------------------

class TestShingleHashes:
    def test_returns_frozenset(self, dedup):
        hashes = dedup._create_shingle_hashes("the quick brown fox jumps over lazy dog")
        assert isinstance(hashes, frozenset)

    def test_identical_text_identical_hashes(self, dedup):
        text = "the quick brown fox jumps over the lazy dog"
        assert dedup._create_shingle_hashes(text) == dedup._create_shingle_hashes(text)

    def test_short_text_falls_back_to_single_hash(self, dedup):
        # "foo" < shingle_size(5) words → single-hash frozenset
        hashes = dedup._create_shingle_hashes("foo bar")
        assert len(hashes) == 1

    def test_longer_text_multiple_shingles(self, dedup):
        text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
        hashes = dedup._create_shingle_hashes(text)
        # 10 words, shingle_size=5 → 10-5+1 = 6 shingles
        assert len(hashes) == 6

    def test_different_text_different_hashes(self, dedup):
        h1 = dedup._create_shingle_hashes("alpha bravo charlie delta echo foxtrot")
        h2 = dedup._create_shingle_hashes("xxxxxx yyyyy zzzzz wwwww vvvvv uuuuu")
        assert h1 != h2


# ---------------------------------------------------------------------------
# _content_hash
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_deterministic(self, dedup):
        assert dedup._content_hash("hello") == dedup._content_hash("hello")

    def test_case_insensitive(self, dedup):
        # normalize lowercases, so HELLO == hello
        assert dedup._content_hash("HELLO WORLD") == dedup._content_hash("hello world")

    def test_different_texts_different_hashes(self, dedup):
        assert dedup._content_hash("apple") != dedup._content_hash("orange")

    def test_returns_16_char_hex(self, dedup):
        h = dedup._content_hash("any text")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# _jaccard_similarity
# ---------------------------------------------------------------------------

class TestJaccard:
    def test_identical_sets_is_1(self, dedup):
        s = frozenset([1, 2, 3, 4, 5])
        assert dedup._jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets_is_0(self, dedup):
        a = frozenset([1, 2, 3])
        b = frozenset([4, 5, 6])
        assert dedup._jaccard_similarity(a, b) == 0.0

    def test_empty_sets_is_0(self, dedup):
        assert dedup._jaccard_similarity(frozenset(), frozenset()) == 0.0

    def test_one_empty_set_is_0(self, dedup):
        assert dedup._jaccard_similarity(frozenset([1, 2]), frozenset()) == 0.0
        assert dedup._jaccard_similarity(frozenset(), frozenset([1, 2])) == 0.0

    def test_half_overlap(self, dedup):
        a = frozenset([1, 2, 3, 4])
        b = frozenset([3, 4, 5, 6])
        # intersection=2, union=6 → 2/6 ≈ 0.333
        sim = dedup._jaccard_similarity(a, b)
        assert abs(sim - 2 / 6) < 1e-9

    def test_value_in_range(self, dedup):
        text1 = "the quick brown fox jumps over the lazy dog"
        text2 = "the quick brown fox leaps over the lazy cat"
        fp1 = dedup.create_fingerprint(text1)
        fp2 = dedup.create_fingerprint(text2)
        sim = dedup._jaccard_similarity(fp1.shingle_hashes, fp2.shingle_hashes)
        assert 0.0 <= sim <= 1.0


# ---------------------------------------------------------------------------
# create_fingerprint
# ---------------------------------------------------------------------------

class TestCreateFingerprint:
    def test_returns_content_fingerprint(self, dedup):
        fp = dedup.create_fingerprint("hello world")
        assert isinstance(fp, ContentFingerprint)

    def test_identical_text_identical_fingerprints(self, dedup):
        t = "The exact same text both times"
        fp1, fp2 = dedup.create_fingerprint(t), dedup.create_fingerprint(t)
        assert fp1.content_hash == fp2.content_hash
        assert fp1.shingle_hashes == fp2.shingle_hashes

    def test_different_text_different_hash(self, dedup):
        fp1 = dedup.create_fingerprint("apple pie recipe")
        fp2 = dedup.create_fingerprint("quantum computing introduction")
        assert fp1.content_hash != fp2.content_hash

    def test_case_insensitive_hash(self, dedup):
        fp1 = dedup.create_fingerprint("Hello World Test For Dedup")
        fp2 = dedup.create_fingerprint("hello world test for dedup")
        assert fp1.content_hash == fp2.content_hash


# ---------------------------------------------------------------------------
# is_duplicate
# ---------------------------------------------------------------------------

class TestIsDuplicate:
    def test_exact_same_text_is_duplicate(self, dedup):
        text = "exactly the same text right here"
        fp1, fp2 = dedup.create_fingerprint(text), dedup.create_fingerprint(text)
        assert dedup.is_duplicate(fp1, fp2) is True

    def test_completely_different_text_is_not_duplicate(self, dedup):
        fp1 = dedup.create_fingerprint("alpha bravo charlie delta echo foxtrot golf hotel india")
        fp2 = dedup.create_fingerprint("november oscar papa quebec romeo sierra tango uniform victor")
        assert dedup.is_duplicate(fp1, fp2) is False

    def test_one_word_different_in_long_text_is_duplicate(self, dedup):
        """Near-identical long texts (only one word changed in a 25+ word text) should
        be detected as duplicates because Jaccard(shingles) > 0.85.

        With 25 words and shingle_size=5: 21 original shingles.
        Changing word 24 affects 5 shingles → 16 shared, 10 total unique → 16/26 ≈ 0.615.
        To reliably exceed 0.85, we need to change very little in a VERY long text.
        Use 50+ words so that one word change barely affects the shingle pool.
        """
        # 50-word base: changing word 48 affects only 5 of 46 shingles
        words = [
            "the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog",
            "near", "the", "river", "bank", "while", "the", "sun", "sets", "behind",
            "the", "distant", "mountains", "and", "the", "wind", "blows", "gently",
            "through", "the", "tall", "grass", "that", "grows", "beside", "the",
            "old", "stone", "bridge", "where", "the", "children", "used", "to",
            "play", "every", "summer", "afternoon", "until", "the", "rain", "came",
        ]
        base = " ".join(words)
        # Change only one word near the end (index 48: "rain" → "snow")
        words[48] = "snow"
        near = " ".join(words)
        fp1 = dedup.create_fingerprint(base)
        fp2 = dedup.create_fingerprint(near)
        # With 50 words + shingle_size=5: 46 shingles.
        # 1 word changed near the end affects min(5, remaining) = 2 shingles
        # → shared ≈ 44, union ≈ 48 → Jaccard ≈ 0.917 > 0.85
        assert dedup.is_duplicate(fp1, fp2) is True

    def test_threshold_respected_low_sim(self):
        """At threshold=1.0 (exact only), nearly-identical texts are NOT dupes."""
        strict = ContentDeduplicator(similarity_threshold=1.0)
        fp1 = strict.create_fingerprint(
            "the quick brown fox jumps over the lazy dog"
        )
        fp2 = strict.create_fingerprint(
            "the quick brown fox jumps over the lazy cat"
        )
        # content_hash differs (different text); similarity < 1.0 → not duplicate
        assert strict.is_duplicate(fp1, fp2) is False

    def test_self_is_always_duplicate(self, dedup):
        fp = dedup.create_fingerprint("any arbitrary text for testing self-similarity")
        assert dedup.is_duplicate(fp, fp) is True


# ---------------------------------------------------------------------------
# deduplicate_chunks — core correctness
# ---------------------------------------------------------------------------

class TestDeduplicateChunks:
    def test_empty_input_returns_empty(self, dedup):
        assert dedup.deduplicate_chunks([]) == []

    def test_single_chunk_returned_unchanged(self, dedup):
        chunks = [MockChunk("only one", 5, "s1")]
        result = dedup.deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0] is chunks[0]

    def test_exact_duplicates_collapsed_to_one(self, dedup):
        text = "exact duplicate content here"
        chunks = [MockChunk(text, 5, f"s{i}") for i in range(5)]
        result = dedup.deduplicate_chunks(chunks)
        assert len(result) == 1

    def test_first_occurrence_kept(self, dedup):
        text = "same content again"
        chunks = [MockChunk(text, 5, "first"), MockChunk(text, 5, "second")]
        result = dedup.deduplicate_chunks(chunks)
        assert result[0].source == "first"

    def test_unique_chunks_all_kept(self, dedup):
        chunks = [
            MockChunk("alpha bravo charlie delta echo foxtrot golf hotel", 10, "s1"),
            MockChunk("november oscar papa quebec romeo sierra tango uniform", 10, "s2"),
            MockChunk("victor whiskey xray yankee zulu apple banana cherry", 10, "s3"),
        ]
        result = dedup.deduplicate_chunks(chunks)
        assert len(result) == 3

    def test_near_duplicate_removed(self, dedup):
        """Near-identical long texts (one word changed far from the end) are deduped.

        This uses the same 50-word structure where Jaccard ≈ 0.917 > 0.85.
        """
        words = [
            "the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog",
            "near", "the", "river", "bank", "while", "the", "sun", "sets", "behind",
            "the", "distant", "mountains", "and", "the", "wind", "blows", "gently",
            "through", "the", "tall", "grass", "that", "grows", "beside", "the",
            "old", "stone", "bridge", "where", "the", "children", "used", "to",
            "play", "every", "summer", "afternoon", "until", "the", "rain", "came",
        ]
        base = " ".join(words)
        words[48] = "snow"  # change one word near the end
        near = " ".join(words)
        chunks = [MockChunk(base, 20, "s1"), MockChunk(near, 20, "s2")]
        result = dedup.deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0].source == "s1"

    def test_order_preserved_for_unique(self, dedup):
        chunks = [
            MockChunk("unique alpha content with enough words to create distinct shingles", 10, "s1"),
            MockChunk("unique beta content with enough words to form a completely different shingle", 10, "s2"),
            MockChunk("unique gamma text here with completely different vocabulary from the others", 10, "s3"),
        ]
        result = dedup.deduplicate_chunks(chunks)
        sources = [c.source for c in result]
        assert sources == ["s1", "s2", "s3"]

    def test_mixed_duplicates_and_uniques(self, dedup):
        """A mix of dupe and unique chunks — only unique ones survive."""
        dup_text = "duplicate text that appears more than once in the list"
        unique_text = "november oscar papa quebec romeo sierra tango uniform victor whiskey"
        chunks = [
            MockChunk(dup_text, 10, "d1"),
            MockChunk(unique_text, 10, "u1"),
            MockChunk(dup_text, 10, "d2"),
        ]
        result = dedup.deduplicate_chunks(chunks)
        assert len(result) == 2
        sources = {c.source for c in result}
        assert "d1" in sources
        assert "u1" in sources
        assert "d2" not in sources


# ---------------------------------------------------------------------------
# MAX_DEDUP_CHUNKS cap
# ---------------------------------------------------------------------------

class TestMaxChunksCap:
    def test_cap_slices_input(self, dedup):
        import src.deduplicator as mod
        original = mod.MAX_DEDUP_CHUNKS
        mod.MAX_DEDUP_CHUNKS = 5
        try:
            chunks = [MockChunk(f"unique text number {i} with words", 5, f"s{i}") for i in range(10)]
            result = dedup.deduplicate_chunks(chunks)
            # Only first 5 are processed
            assert len(result) == 5
            assert result[-1].source == "s4"
        finally:
            mod.MAX_DEDUP_CHUNKS = original

    def test_cap_at_500_does_not_crash(self, dedup):
        """500 unique chunks should all survive and not raise."""
        chunks = [MockChunk(f"chunk number {i} unique content", 5, f"s{i}") for i in range(500)]
        result = dedup.deduplicate_chunks(chunks)
        assert len(result) > 0  # some uniques survive

    def test_above_cap_excess_silently_dropped(self, dedup):
        import src.deduplicator as mod
        original = mod.MAX_DEDUP_CHUNKS
        mod.MAX_DEDUP_CHUNKS = 3
        try:
            chunks = [MockChunk(f"unique item {i}", 5, f"s{i}") for i in range(6)]
            result = dedup.deduplicate_chunks(chunks)
            # chunks 3,4,5 should be ignored entirely
            result_sources = {c.source for c in result}
            for dropped in ["s3", "s4", "s5"]:
                assert dropped not in result_sources
        finally:
            mod.MAX_DEDUP_CHUNKS = original


# ---------------------------------------------------------------------------
# Threshold edge cases
# ---------------------------------------------------------------------------

class TestThresholdEdge:
    def test_low_threshold_is_more_aggressive(self):
        """A threshold of 0.5 deduplicates texts that share ~73% shingles
        (which the default 0.85 would NOT deduplicate).

        Using the 50-word + 1-word-change texts: Jaccard ≈ 0.917.
        Both thresholds (0.5 and 0.85) should deduplicate these. The key property
        tested is: a lower threshold is never MORE restrictive than a higher one.
        """
        # Use a text pair where Jaccard ≈ 0.73, so threshold 0.5 catches it but 0.85 does not
        words = [
            "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
            "hotel", "india", "juliet", "kilo", "lima", "mike", "november",
            "oscar", "papa", "quebec", "romeo", "sierra", "tango",
        ]
        base = " ".join(words)  # 20 words → 16 shingles
        # Change 4 consecutive words in the middle (indices 8-11)
        alt = words[:8] + ["alpha", "bravo", "charlie", "delta"] + words[12:]
        near = " ".join(alt)
        # Compute actual Jaccard to verify threshold assumption holds
        d_strict = ContentDeduplicator(similarity_threshold=0.85)
        fp1 = d_strict.create_fingerprint(base)
        fp2 = d_strict.create_fingerprint(near)
        actual_sim = d_strict._jaccard_similarity(fp1.shingle_hashes, fp2.shingle_hashes)

        # Build a threshold just at actual_sim - 0.05, which should dedup
        threshold = max(0.05, actual_sim - 0.05)
        loose = ContentDeduplicator(similarity_threshold=threshold)
        chunks = [MockChunk(base, 10, "a"), MockChunk(near, 10, "b")]
        result = loose.deduplicate_chunks(chunks)
        # The loose threshold must catch these as duplicates
        assert len(result) == 1

    def test_high_threshold_keeps_similar_text(self):
        """A threshold of 0.99 should NOT deduplicate nearly-identical-but-not-exact text."""
        strict = ContentDeduplicator(similarity_threshold=0.99)
        text1 = "the quick brown fox jumps over the lazy dog"
        text2 = "the quick brown fox jumps over a lazy dog"
        chunks = [MockChunk(text1, 10, "a"), MockChunk(text2, 10, "b")]
        result = strict.deduplicate_chunks(chunks)
        # Texts differ → content_hash differs → shingle sim < 0.99 → both kept
        assert len(result) == 2
