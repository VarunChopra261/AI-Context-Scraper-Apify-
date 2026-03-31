from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer

from .chunker import LLMChunk
from .extractor import ExtractedSnippet


@dataclass(slots=True)
class ScoredChunk:
    chunk: LLMChunk
    score: float


@dataclass(slots=True)
class ScoredSnippet:
    snippet: ExtractedSnippet
    score: float


# Bucket thresholds derived from the relevant-context skill:
# Critical  – the model is likely to fail without it
# Helpful   – improves speed or confidence but is not strictly required
# Noise     – interesting but unlikely to change the result
CRITICAL_THRESHOLD = 0.40
HELPFUL_THRESHOLD = 0.25


@dataclass(slots=True)
class BucketizedContext:
    """Context split into Critical / Helpful / Noise buckets."""

    critical_chunks: list[ScoredChunk]
    helpful_chunks: list[ScoredChunk]
    critical_snippets: list[ScoredSnippet]
    helpful_snippets: list[ScoredSnippet]


class RelevanceRanker:
    def __init__(self, logger) -> None:
        self._logger = logger
        self._model: SentenceTransformer | None = None
        self._model_failed = False

    def _get_model(self) -> SentenceTransformer | None:
        if self._model is not None:
            return self._model
        if self._model_failed:
            return None

        try:
            self._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            return self._model
        except Exception as exc:  # noqa: BLE001
            self._model_failed = True
            self._logger.warning("Embedding model unavailable, using lexical fallback", extra={"error": str(exc)})
            return None

    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        denom = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        if math.isclose(denom, 0.0):
            return 0.0
        return float(np.dot(vec_a, vec_b) / denom)

    @staticmethod
    def _lexical_score(task: str, text: str) -> float:
        partial = fuzz.partial_ratio(task, text) / 100.0
        token = fuzz.token_set_ratio(task, text) / 100.0
        return 0.5 * partial + 0.5 * token

    def compute_semantic_similarity(self, query: str, text: str) -> float:
        """Compute semantic similarity between query and text using embeddings.

        Falls back to lexical scoring if embeddings unavailable.
        Returns score in [0.0, 1.0] range.
        """
        model = self._get_model()
        if model is None:
            return self._lexical_score(query, text)

        try:
            query_embedding = model.encode([query], convert_to_numpy=True)[0]
            text_embedding = model.encode([text[:3000]], convert_to_numpy=True)[0]
            return self._cosine_similarity(query_embedding, text_embedding)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Embedding failed, using lexical fallback", extra={"error": str(exc)})
            return self._lexical_score(query, text)

    def rank_chunks(self, task: str, chunks: list[LLMChunk], top_k: int = 24) -> list[ScoredChunk]:
        if not chunks:
            return []

        model = self._get_model()
        if model is None:
            scored = [ScoredChunk(chunk=chunk, score=self._lexical_score(task, chunk.text[:2000])) for chunk in chunks]
            return sorted(scored, key=lambda x: x.score, reverse=True)[:top_k]

        texts = [chunk.text[:4000] for chunk in chunks]
        task_embedding = model.encode([task], convert_to_numpy=True)[0]
        content_embeddings = model.encode(texts, convert_to_numpy=True)

        scored = [
            ScoredChunk(chunk=chunk, score=self._cosine_similarity(task_embedding, embedding))
            for chunk, embedding in zip(chunks, content_embeddings, strict=False)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def rank_snippets(self, task: str, snippets: list[ExtractedSnippet], top_k: int = 20) -> list[ScoredSnippet]:
        if not snippets:
            return []

        model = self._get_model()
        if model is None:
            scored = [ScoredSnippet(snippet=s, score=self._lexical_score(task, s.code[:1200])) for s in snippets]
            scored.sort(key=lambda item: item.score, reverse=True)
            return scored[:top_k]

        texts = [f"{s.description}\n{s.code[:2500]}" for s in snippets]
        task_embedding = model.encode([task], convert_to_numpy=True)[0]
        snippet_embeddings = model.encode(texts, convert_to_numpy=True)

        scored = []
        for snippet, embedding in zip(snippets, snippet_embeddings, strict=False):
            sem_score = self._cosine_similarity(task_embedding, embedding)
            length_bonus = min(0.15, len(snippet.code) / 5000.0)
            snippet_score = sem_score + length_bonus
            scored.append(ScoredSnippet(snippet=snippet, score=snippet_score))

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def bucketize(
        self,
        scored_chunks: list[ScoredChunk],
        scored_snippets: list[ScoredSnippet],
    ) -> BucketizedContext:
        """Split ranked items into Critical / Helpful / Noise buckets.

        Implements the relevant-context skill's ranking step:
          - Critical (score >= 0.75): the model is likely to fail without it
          - Helpful  (0.55 <= score < 0.75): improves confidence
          - Noise    (score < 0.55): discarded entirely
        """
        critical_chunks = [sc for sc in scored_chunks if sc.score >= CRITICAL_THRESHOLD]
        helpful_chunks = [sc for sc in scored_chunks if HELPFUL_THRESHOLD <= sc.score < CRITICAL_THRESHOLD]

        critical_snippets = [ss for ss in scored_snippets if ss.score >= CRITICAL_THRESHOLD]
        helpful_snippets = [ss for ss in scored_snippets if HELPFUL_THRESHOLD <= ss.score < CRITICAL_THRESHOLD]

        self._logger.info(
            "Context bucketized (relevant-context skill)",
            extra={
                "critical_chunks": len(critical_chunks),
                "helpful_chunks": len(helpful_chunks),
                "noise_chunks_dropped": len(scored_chunks) - len(critical_chunks) - len(helpful_chunks),
                "critical_snippets": len(critical_snippets),
                "helpful_snippets": len(helpful_snippets),
                "noise_snippets_dropped": len(scored_snippets) - len(critical_snippets) - len(helpful_snippets),
            },
        )

        return BucketizedContext(
            critical_chunks=critical_chunks,
            helpful_chunks=helpful_chunks,
            critical_snippets=critical_snippets,
            helpful_snippets=helpful_snippets,
        )
