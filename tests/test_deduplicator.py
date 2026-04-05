"""Tests for deduplicator.py module."""

from dataclasses import dataclass

import pytest

from src.deduplicator import ContentDeduplicator, ContentFingerprint


@dataclass
class MockChunk:
    """Mock LLMChunk for testing."""
    text: str
    tokens: int
    source: str


@pytest.fixture
def deduplicator():
    """Create ContentDeduplicator instance."""
    return ContentDeduplicator(similarity_threshold=0.85)


class TestDeduplicatorInitialization:
    """Test deduplicator initialization."""

    def test_default_threshold(self):
        """Test default similarity threshold."""
        dedup = ContentDeduplicator()
        assert dedup._similarity_threshold == 0.85

    def test_custom_threshold(self):
        """Test custom similarity threshold."""
        dedup = ContentDeduplicator(similarity_threshold=0.7)
        assert dedup._similarity_threshold == 0.7

    def test_shingle_size(self):
        """Test shingle size is set correctly."""
        dedup = ContentDeduplicator()
        assert dedup._shingle_size == 5


class TestFingerprintCreation:
    """Test content fingerprinting."""

    def test_create_fingerprint_identical_text(self, deduplicator):
        """Test identical text produces identical fingerprints."""
        text1 = "This is a test sentence for deduplication"
        text2 = "This is a test sentence for deduplication"

        fp1 = deduplicator.create_fingerprint(text1)
        fp2 = deduplicator.create_fingerprint(text2)

        assert fp1.shingle_hashes == fp2.shingle_hashes
        assert getattr(fp1, "hash", getattr(fp1, "content_hash", None)) == getattr(fp2, "hash", getattr(fp2, "content_hash", None))

    def test_create_fingerprint_different_text(self, deduplicator):
        """Test different text produces different fingerprints."""
        text1 = "This is the first test sentence for checking"
        text2 = "This is completely different content altogether"

        fp1 = deduplicator.create_fingerprint(text1)
        fp2 = deduplicator.create_fingerprint(text2)

        assert fp1.shingle_hashes != fp2.shingle_hashes

    def test_create_fingerprint_case_insensitive(self, deduplicator):
        """Test fingerprinting handles case differences."""
        text1 = "Hello World Test For Dedup"
        text2 = "hello world test for dedup"

        fp1 = deduplicator.create_fingerprint(text1)
        fp2 = deduplicator.create_fingerprint(text2)

        # Should be identical (lowercased internally)
        similarity = deduplicator._jaccard_similarity(fp1.shingle_hashes, fp2.shingle_hashes)
        assert similarity > 0.9

    def test_create_fingerprint_short_text(self, deduplicator):
        """Test fingerprinting short text."""
        text = "short"
        fp = deduplicator.create_fingerprint(text)

        # Should handle short text gracefully
        assert isinstance(fp.shingle_hashes, frozenset)
        assert isinstance(fp, ContentFingerprint)


class TestJaccardSimilarity:
    """Test Jaccard similarity computation."""

    def test_jaccard_identical(self, deduplicator):
        """Test Jaccard similarity of identical sets."""
        text = "The quick brown fox jumps over the lazy dog"
        fp1 = deduplicator.create_fingerprint(text)
        fp2 = deduplicator.create_fingerprint(text)

        similarity = deduplicator._jaccard_similarity(fp1.shingle_hashes, fp2.shingle_hashes)
        assert similarity == 1.0

    def test_jaccard_completely_different(self, deduplicator):
        """Test Jaccard similarity of completely different sets."""
        text1 = "aaaa bbbb cccc dddd eeee"
        text2 = "xxxx yyyy zzzz wwww vvvv"

        fp1 = deduplicator.create_fingerprint(text1)
        fp2 = deduplicator.create_fingerprint(text2)

        similarity = deduplicator._jaccard_similarity(fp1.shingle_hashes, fp2.shingle_hashes)
        assert similarity < 0.3

    def test_jaccard_similar_text(self, deduplicator):
        """Test Jaccard similarity of similar text."""
        text1 = "This is a sample text for testing similarity"
        text2 = "This is a sample text for testing purposes"

        fp1 = deduplicator.create_fingerprint(text1)
        fp2 = deduplicator.create_fingerprint(text2)

        similarity = deduplicator._jaccard_similarity(fp1.shingle_hashes, fp2.shingle_hashes)
        assert 0.3 < similarity < 1.0

    def test_jaccard_empty_sets(self, deduplicator):
        """Test Jaccard similarity with empty sets."""
        similarity = deduplicator._jaccard_similarity(frozenset(), frozenset())
        assert similarity == 0.0


class TestIsDuplicate:
    """Test is_duplicate method."""

    def test_exact_duplicates_detected(self, deduplicator):
        """Test exact duplicates are identified via hash."""
        fp1 = deduplicator.create_fingerprint("exact same text here")
        fp2 = deduplicator.create_fingerprint("exact same text here")

        assert deduplicator.is_duplicate(fp1, fp2) is True

    def test_different_content_not_duplicate(self, deduplicator):
        """Test clearly different content is not a duplicate."""
        fp1 = deduplicator.create_fingerprint("alpha bravo charlie delta echo")
        fp2 = deduplicator.create_fingerprint("foxtrot golf hotel india juliet")

        assert deduplicator.is_duplicate(fp1, fp2) is False


class TestDeduplication:
    """Test deduplication of chunks."""

    def test_deduplicate_no_duplicates(self, deduplicator):
        """Test deduplication with no duplicates."""
        chunks = [
            MockChunk("First unique piece of content about topic A", 10, "source1"),
            MockChunk("Second completely different content on topic B", 10, "source2"),
            MockChunk("Third entirely distinct content for topic C", 10, "source3"),
        ]

        result = deduplicator.deduplicate_chunks(chunks)
        assert len(result) == 3

    def test_deduplicate_exact_duplicates(self, deduplicator):
        """Test deduplication removes exact duplicates."""
        chunks = [
            MockChunk("This is duplicate content here", 10, "source1"),
            MockChunk("This is duplicate content here", 10, "source2"),
            MockChunk("This is duplicate content here", 10, "source3"),
        ]

        result = deduplicator.deduplicate_chunks(chunks)
        assert len(result) == 1

    def test_deduplicate_keeps_first_occurrence(self, deduplicator):
        """Test deduplication keeps the first occurrence of duplicates."""
        chunks = [
            MockChunk("This is duplicate content", 10, "source1"),
            MockChunk("This is duplicate content", 10, "source2"),
        ]

        result = deduplicator.deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0].source == "source1"

    def test_deduplicate_empty_list(self, deduplicator):
        """Test deduplication with empty list."""
        result = deduplicator.deduplicate_chunks([])
        assert len(result) == 0

    def test_deduplicate_single_chunk(self, deduplicator):
        """Test deduplication with single chunk."""
        chunks = [MockChunk("Only one chunk", 10, "source1")]
        result = deduplicator.deduplicate_chunks(chunks)
        assert len(result) == 1

    def test_deduplicate_max_chunks_cap(self, deduplicator):
        """Test that deduplication handles more than MAX_DEDUP_CHUNKS by slicing."""
        import src.deduplicator
        original_max = src.deduplicator.MAX_DEDUP_CHUNKS
        src.deduplicator.MAX_DEDUP_CHUNKS = 5
        try:
            chunks = [MockChunk(f"chunk {i}", 10, f"source{i}") for i in range(10)]
            result = deduplicator.deduplicate_chunks(chunks)
            # Should have capped at 5 and processed them, returning 5 since they are unique
            assert len(result) == 5
            assert result[-1].text == "chunk 4"
        finally:
            src.deduplicator.MAX_DEDUP_CHUNKS = original_max
