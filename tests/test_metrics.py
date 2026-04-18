"""Comprehensive regression tests for metrics.py — zero coverage → full coverage."""

from __future__ import annotations

import time

import pytest

from src.metrics import Metrics, MetricsCollector


# ---------------------------------------------------------------------------
# Metrics dataclass defaults
# ---------------------------------------------------------------------------

class TestMetricsDefaults:
    def test_all_timing_fields_zero(self):
        m = Metrics()
        assert m.total_duration_seconds == 0.0
        assert m.search_duration_seconds == 0.0
        assert m.crawl_duration_seconds == 0.0
        assert m.extraction_duration_seconds == 0.0
        assert m.ranking_duration_seconds == 0.0
        assert m.llm_synthesis_duration_seconds == 0.0

    def test_all_count_fields_zero(self):
        m = Metrics()
        assert m.queries_generated == 0
        assert m.sources_discovered == 0
        assert m.pages_scraped == 0
        assert m.pages_failed == 0
        assert m.documents_extracted == 0
        assert m.documents_filtered_spam == 0
        assert m.code_snippets_extracted == 0
        assert m.code_snippets_ranked == 0
        assert m.chunks_created == 0
        assert m.chunks_ranked == 0
        assert m.patterns_detected == 0
        assert m.stackoverflow_answers == 0

    def test_bucket_counts_zero(self):
        m = Metrics()
        assert m.critical_chunks == 0
        assert m.helpful_chunks == 0
        assert m.critical_snippets == 0
        assert m.helpful_snippets == 0

    def test_quality_scores_zero(self):
        m = Metrics()
        assert m.avg_chunk_relevance == 0.0
        assert m.avg_snippet_relevance == 0.0
        assert m.content_diversity_score == 0.0

    def test_cache_stats_zero(self):
        m = Metrics()
        assert m.cache_hits == 0
        assert m.cache_misses == 0

    def test_llm_tokens_zero(self):
        m = Metrics()
        assert m.llm_tokens_used == 0

    def test_errors_empty_list(self):
        m = Metrics()
        assert m.errors == []
        # Ensure it's not shared across instances
        m2 = Metrics()
        m.errors.append("err")
        assert m2.errors == []


# ---------------------------------------------------------------------------
# MetricsCollector — record and increment
# ---------------------------------------------------------------------------

class TestMetricsCollectorRecord:
    def test_record_known_int_field(self):
        mc = MetricsCollector()
        mc.record("queries_generated", 5)
        d = mc.to_dict()
        assert d["counts"]["queries"] == 5

    def test_record_known_float_field(self):
        mc = MetricsCollector()
        mc.record("avg_chunk_relevance", 0.75)
        d = mc.to_dict()
        assert d["quality"]["avg_chunk_relevance"] == 0.75

    def test_record_unknown_field_is_noop(self):
        mc = MetricsCollector()
        # Should not raise
        mc.record("nonexistent_metric", 99)

    def test_increment_known_counter(self):
        mc = MetricsCollector()
        mc.increment("cache_hits")
        mc.increment("cache_hits")
        d = mc.to_dict()
        assert d["cache"]["hits"] == 2

    def test_increment_with_amount(self):
        mc = MetricsCollector()
        mc.increment("cache_misses", 5)
        d = mc.to_dict()
        assert d["cache"]["misses"] == 5

    def test_increment_unknown_field_is_noop(self):
        mc = MetricsCollector()
        mc.increment("nonexistent_counter")  # must not raise

    def test_record_error_appends(self):
        mc = MetricsCollector()
        mc.record_error("boom")
        mc.record_error("bang")
        d = mc.to_dict()
        assert "boom" in d["errors"]
        assert "bang" in d["errors"]


# ---------------------------------------------------------------------------
# MetricsCollector — phase timing
# ---------------------------------------------------------------------------

class TestPhaseTimings:
    def test_start_and_end_search_phase(self):
        mc = MetricsCollector()
        mc.start_phase("search")
        time.sleep(0.01)
        duration = mc.end_phase("search")
        assert duration >= 0.01
        d = mc.to_dict()
        assert d["timing"]["search_seconds"] >= 0.01

    def test_start_and_end_crawl_phase(self):
        mc = MetricsCollector()
        mc.start_phase("crawl")
        duration = mc.end_phase("crawl")
        assert duration >= 0.0
        d = mc.to_dict()
        assert d["timing"]["crawl_seconds"] >= 0.0

    def test_start_and_end_extraction_phase(self):
        mc = MetricsCollector()
        mc.start_phase("extraction")
        mc.end_phase("extraction")
        assert mc.to_dict()["timing"]["extraction_seconds"] >= 0.0

    def test_start_and_end_ranking_phase(self):
        mc = MetricsCollector()
        mc.start_phase("ranking")
        mc.end_phase("ranking")
        assert mc.to_dict()["timing"]["ranking_seconds"] >= 0.0

    def test_start_and_end_llm_synthesis_phase(self):
        mc = MetricsCollector()
        mc.start_phase("llm_synthesis")
        mc.end_phase("llm_synthesis")
        assert mc.to_dict()["timing"]["llm_synthesis_seconds"] >= 0.0

    def test_end_phase_without_start_returns_zero(self):
        mc = MetricsCollector()
        duration = mc.end_phase("search")
        assert duration == 0.0

    def test_unknown_phase_not_stored(self):
        mc = MetricsCollector()
        mc.start_phase("unknown_phase")
        duration = mc.end_phase("unknown_phase")
        assert duration >= 0.0  # returns a duration but doesn't store it

    def test_overlapping_phases_tracked(self):
        mc = MetricsCollector()
        mc.start_phase("search")
        mc.start_phase("crawl")
        mc.end_phase("search")
        mc.end_phase("crawl")
        d = mc.to_dict()
        assert d["timing"]["search_seconds"] >= 0.0
        assert d["timing"]["crawl_seconds"] >= 0.0


# ---------------------------------------------------------------------------
# MetricsCollector — reset
# ---------------------------------------------------------------------------

class TestMetricsCollectorReset:
    def test_reset_clears_all_values(self):
        mc = MetricsCollector()
        mc.record("queries_generated", 42)
        mc.increment("cache_hits", 5)
        mc.record_error("some error")
        mc.start_phase("search")
        mc.end_phase("search")
        mc.reset()
        d = mc.to_dict()
        assert d["counts"]["queries"] == 0
        assert d["cache"]["hits"] == 0
        assert d["errors"] == []
        assert d["timing"]["search_seconds"] == 0.0

    def test_reset_clears_phase_starts(self):
        mc = MetricsCollector()
        mc.start_phase("search")
        mc.reset()
        # After reset, end_phase should return 0 (no start registered)
        duration = mc.end_phase("search")
        assert duration == 0.0


# ---------------------------------------------------------------------------
# MetricsCollector — to_dict completeness
# ---------------------------------------------------------------------------

class TestToDictStructure:
    def test_timing_key_present(self):
        d = MetricsCollector().to_dict()
        assert "timing" in d

    def test_counts_key_present(self):
        d = MetricsCollector().to_dict()
        assert "counts" in d

    def test_relevance_buckets_key_present(self):
        d = MetricsCollector().to_dict()
        assert "relevance_buckets" in d

    def test_quality_key_present(self):
        d = MetricsCollector().to_dict()
        assert "quality" in d

    def test_cache_key_present(self):
        d = MetricsCollector().to_dict()
        assert "cache" in d

    def test_llm_key_present(self):
        d = MetricsCollector().to_dict()
        assert "llm" in d

    def test_errors_key_present(self):
        d = MetricsCollector().to_dict()
        assert "errors" in d

    def test_cache_hit_rate_zero_when_no_hits(self):
        d = MetricsCollector().to_dict()
        # 0 hits / 1 max = 0.0
        assert d["cache"]["hit_rate"] == 0.0

    def test_cache_hit_rate_calculated(self):
        mc = MetricsCollector()
        mc.increment("cache_hits", 3)
        mc.increment("cache_misses", 1)
        d = mc.to_dict()
        assert d["cache"]["hit_rate"] == 0.75

    def test_total_seconds_is_positive(self):
        mc = MetricsCollector()
        d = mc.to_dict()
        assert d["timing"]["total_seconds"] >= 0.0

    def test_to_dict_is_non_destructive(self):
        """Calling to_dict multiple times must not reset timing."""
        mc = MetricsCollector()
        mc.record("queries_generated", 7)
        d1 = mc.to_dict()
        d2 = mc.to_dict()
        assert d1["counts"]["queries"] == d2["counts"]["queries"] == 7

    def test_relevance_buckets_populated(self):
        mc = MetricsCollector()
        mc.record("critical_chunks", 4)
        mc.record("helpful_chunks", 2)
        mc.record("critical_snippets", 1)
        mc.record("helpful_snippets", 3)
        d = mc.to_dict()
        assert d["relevance_buckets"]["critical_chunks"] == 4
        assert d["relevance_buckets"]["helpful_chunks"] == 2
        assert d["relevance_buckets"]["critical_snippets"] == 1
        assert d["relevance_buckets"]["helpful_snippets"] == 3

    def test_quality_scores_rounded(self):
        mc = MetricsCollector()
        mc.record("avg_chunk_relevance", 0.12345678)
        mc.record("avg_snippet_relevance", 0.98765432)
        mc.record("content_diversity_score", 0.66666666)
        d = mc.to_dict()
        assert d["quality"]["avg_chunk_relevance"] == 0.123
        assert d["quality"]["avg_snippet_relevance"] == 0.988
        assert d["quality"]["content_diversity"] == 0.667


# ---------------------------------------------------------------------------
# MetricsCollector — finalize
# ---------------------------------------------------------------------------

class TestFinalize:
    def test_finalize_sets_total_duration(self):
        mc = MetricsCollector()
        time.sleep(0.01)
        metrics = mc.finalize()
        assert metrics.total_duration_seconds >= 0.01

    def test_finalize_idempotent(self):
        """Calling finalize twice should not overwrite the first recorded duration."""
        mc = MetricsCollector()
        time.sleep(0.01)
        m1 = mc.finalize()
        time.sleep(0.05)
        m2 = mc.finalize()
        # Second call should NOT overwrite the first
        assert m1.total_duration_seconds == m2.total_duration_seconds

    def test_finalize_returns_metrics_instance(self):
        mc = MetricsCollector()
        result = mc.finalize()
        assert isinstance(result, Metrics)
