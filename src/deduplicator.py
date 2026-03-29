"""Content deduplication using MinHash for near-duplicate detection."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Maximum number of chunks to process before skipping deduplication to avoid
# excessive O(N²) comparisons.
MAX_DEDUP_CHUNKS = 500


@dataclass(slots=True)
class ContentFingerprint:
    """Content fingerprint for deduplication."""

    content_hash: str
    shingle_hashes: frozenset[int]


class ContentDeduplicator:
    """Detects and removes near-duplicate content using shingling and hashing."""

    def __init__(self, shingle_size: int = 5, similarity_threshold: float = 0.85) -> None:
        self._shingle_size = shingle_size
        self._similarity_threshold = similarity_threshold

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        text = re.sub(r"\s+", " ", text.lower())
        text = re.sub(r"[^\w\s]", "", text)
        return text.strip()

    def _create_shingle_hashes(self, text: str) -> frozenset[int]:
        """Create hashed word-level shingles from text.

        Uses integer hashes of shingles instead of storing full strings to
        reduce memory usage significantly for large documents.
        """
        normalized = self._normalize_text(text)
        words = normalized.split()

        if len(words) < self._shingle_size:
            return frozenset({hash(normalized)})

        shingle_hashes: set[int] = set()
        for i in range(len(words) - self._shingle_size + 1):
            shingle = " ".join(words[i : i + self._shingle_size])
            shingle_hashes.add(hash(shingle))

        return frozenset(shingle_hashes)

    def _content_hash(self, text: str) -> str:
        """Create hash of normalized content."""
        normalized = self._normalize_text(text)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _jaccard_similarity(self, set_a: frozenset[int], set_b: frozenset[int]) -> float:
        """Calculate Jaccard similarity between two sets of shingle hashes."""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def create_fingerprint(self, text: str) -> ContentFingerprint:
        """Create content fingerprint for deduplication."""
        return ContentFingerprint(
            content_hash=self._content_hash(text),
            shingle_hashes=self._create_shingle_hashes(text),
        )

    def is_duplicate(self, fp_a: ContentFingerprint, fp_b: ContentFingerprint) -> bool:
        """Check if two content fingerprints are near-duplicates."""
        # Fast exact match check
        if fp_a.content_hash == fp_b.content_hash:
            return True

        # Similarity check using shingle hashes
        similarity = self._jaccard_similarity(fp_a.shingle_hashes, fp_b.shingle_hashes)
        return similarity >= self._similarity_threshold

    def deduplicate_chunks(self, chunks: list) -> list:
        """Deduplicate list of chunk objects with .text attribute.

        Caps the number of chunks processed to avoid excessive O(N²) comparisons.
        """
        if not chunks:
            return []

        # Cap to prevent O(N²) blowup on large crawls
        if len(chunks) > MAX_DEDUP_CHUNKS:
            chunks = chunks[:MAX_DEDUP_CHUNKS]

        # Build fingerprints
        fingerprints = [self.create_fingerprint(chunk.text) for chunk in chunks]

        # Single-pass deduplication: compare each chunk against seen fingerprints
        unique_indices: list[int] = []
        # Use hash-based fast path: group by content_hash first
        seen_hashes: set[str] = set()
        seen_fingerprints: list[ContentFingerprint] = []

        for i, fp in enumerate(fingerprints):
            # Fast exact-match dedup via content hash
            if fp.content_hash in seen_hashes:
                continue

            # Near-duplicate check against already-accepted fingerprints
            is_dup = False
            for seen_fp in seen_fingerprints:
                if self._jaccard_similarity(fp.shingle_hashes, seen_fp.shingle_hashes) >= self._similarity_threshold:
                    is_dup = True
                    break

            if not is_dup:
                unique_indices.append(i)
                seen_hashes.add(fp.content_hash)
                seen_fingerprints.append(fp)

        return [chunks[i] for i in unique_indices]
