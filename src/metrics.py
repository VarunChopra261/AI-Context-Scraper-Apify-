"""Metrics and observability for actor performance tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass
class Metrics:
    """Performance and quality metrics for actor execution."""

    # Timing
    total_duration_seconds: float = 0.0
    search_duration_seconds: float = 0.0
    crawl_duration_seconds: float = 0.0
    extraction_duration_seconds: float = 0.0
    ranking_duration_seconds: float = 0.0
    llm_synthesis_duration_seconds: float = 0.0

    # Counts
    queries_generated: int = 0
    sources_discovered: int = 0
    pages_scraped: int = 0
    pages_failed: int = 0
    documents_extracted: int = 0
    documents_filtered_spam: int = 0
    code_snippets_extracted: int = 0
    code_snippets_ranked: int = 0
    chunks_created: int = 0
    chunks_ranked: int = 0
    patterns_detected: int = 0
    stackoverflow_answers: int = 0

    # Relevance-context skill buckets
    critical_chunks: int = 0
    helpful_chunks: int = 0
    critical_snippets: int = 0
    helpful_snippets: int = 0

    # Quality scores
    avg_chunk_relevance: float = 0.0
    avg_snippet_relevance: float = 0.0
    content_diversity_score: float = 0.0  # Unique domains / total sources

    # Cache stats
    cache_hits: int = 0
    cache_misses: int = 0

    # LLM synthesis
    llm_tokens_used: int = 0

    # Errors
    errors: list[str] = field(default_factory=list)


class MetricsCollector:
    """Collects and aggregates metrics during actor execution.

    Thread-safe for overlapping phases — each phase has its own start timestamp.
    """

    def __init__(self) -> None:
        self._metrics = Metrics()
        self._start_time = monotonic()
        self._phase_starts: dict[str, float] = {}

    def reset(self) -> None:
        """Reset all metrics for a fresh run (prevents stale data across retries)."""
        self._metrics = Metrics()
        self._start_time = monotonic()
        self._phase_starts.clear()

    def start_phase(self, phase: str) -> None:
        """Start timing a phase. Supports overlapping/nested phases."""
        self._phase_starts[phase] = monotonic()

    def end_phase(self, phase: str) -> float:
        """End timing a phase and return duration."""
        start = self._phase_starts.pop(phase, None)
        if start is None:
            return 0.0

        duration = monotonic() - start

        # Map phase to metric field
        phase_map = {
            "search": "search_duration_seconds",
            "crawl": "crawl_duration_seconds",
            "extraction": "extraction_duration_seconds",
            "ranking": "ranking_duration_seconds",
            "llm_synthesis": "llm_synthesis_duration_seconds",
        }

        if phase in phase_map:
            setattr(self._metrics, phase_map[phase], duration)

        return duration

    def record(self, metric_name: str, value: int | float) -> None:
        """Record a metric value."""
        if hasattr(self._metrics, metric_name):
            setattr(self._metrics, metric_name, value)

    def increment(self, metric_name: str, amount: int = 1) -> None:
        """Increment a counter metric."""
        if hasattr(self._metrics, metric_name):
            current = getattr(self._metrics, metric_name)
            setattr(self._metrics, metric_name, current + amount)

    def record_error(self, error: str) -> None:
        """Record an error message."""
        self._metrics.errors.append(error)

    def finalize(self) -> Metrics:
        """Finalize metrics with total duration. Call once at the very end."""
        if self._metrics.total_duration_seconds == 0.0:
            self._metrics.total_duration_seconds = monotonic() - self._start_time
        return self._metrics

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for logging.

        Computes elapsed time non-destructively so it can be called multiple times
        without overwriting previously recorded values.
        """
        elapsed = monotonic() - self._start_time
        m = self._metrics
        return {
            "timing": {
                "total_seconds": round(elapsed, 2),
                "search_seconds": round(m.search_duration_seconds, 2),
                "crawl_seconds": round(m.crawl_duration_seconds, 2),
                "extraction_seconds": round(m.extraction_duration_seconds, 2),
                "ranking_seconds": round(m.ranking_duration_seconds, 2),
                "llm_synthesis_seconds": round(m.llm_synthesis_duration_seconds, 2),
            },
            "counts": {
                "queries": m.queries_generated,
                "sources_found": m.sources_discovered,
                "pages_scraped": m.pages_scraped,
                "pages_failed": m.pages_failed,
                "documents": m.documents_extracted,
                "spam_filtered": m.documents_filtered_spam,
                "code_snippets": m.code_snippets_extracted,
                "chunks": m.chunks_created,
                "patterns": m.patterns_detected,
                "stackoverflow": m.stackoverflow_answers,
            },
            "relevance_buckets": {
                "critical_chunks": m.critical_chunks,
                "helpful_chunks": m.helpful_chunks,
                "critical_snippets": m.critical_snippets,
                "helpful_snippets": m.helpful_snippets,
            },
            "quality": {
                "avg_chunk_relevance": round(m.avg_chunk_relevance, 3),
                "avg_snippet_relevance": round(m.avg_snippet_relevance, 3),
                "content_diversity": round(m.content_diversity_score, 3),
            },
            "cache": {
                "hits": m.cache_hits,
                "misses": m.cache_misses,
                "hit_rate": round(m.cache_hits / max(1, m.cache_hits + m.cache_misses), 3),
            },
            "llm": {
                "tokens_used": m.llm_tokens_used,
            },
            "errors": m.errors,
        }
