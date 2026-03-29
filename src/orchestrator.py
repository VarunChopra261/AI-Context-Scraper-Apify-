from __future__ import annotations

import asyncio
import hashlib
import json
import re
import traceback
from urllib.parse import urlparse

import httpx

from .cache_manager import CacheManager
from .chunker import Chunker
from .crawler import AsyncCrawler
from .deduplicator import ContentDeduplicator
from .extractor import ContentExtractor, ExtractedDoc, ExtractedSnippet
from .formatter import ContextFormatter
from .github_miner import GitHubMiner
from .llm_synthesizer import LLMSynthesizer
from .metrics import MetricsCollector
from .pattern_detector import PatternDetector
from .relevance import RelevanceRanker
from .search import QueryExpander, SearchClient
from .stackoverflow_miner import StackOverflowMiner


class ContextOrchestrator:
    def __init__(
        self,
        logger,
        github_token: str | None = None,
        enable_cache: bool = True,
        enable_stackoverflow: bool = True,
        chunk_size: int = 500,
        enable_llm_synthesis: bool = True,
        openrouter_api_key: str | None = None,
        openrouter_model: str = "arcee-ai/trinity-large-preview:free",
    ) -> None:
        self._logger = logger
        self._expander = QueryExpander()
        self._search = SearchClient(logger=logger)
        self._github = GitHubMiner(logger=logger, github_token=github_token)
        self._stackoverflow = StackOverflowMiner(logger=logger) if enable_stackoverflow else None
        self._crawler = AsyncCrawler(logger=logger)
        self._extractor = ContentExtractor(logger=logger)
        self._chunker = Chunker(max_tokens=chunk_size)
        self._ranker = RelevanceRanker(logger=logger)
        self._formatter = ContextFormatter()
        self._pattern_detector = PatternDetector()
        self._deduplicator = ContentDeduplicator()
        self._cache = CacheManager(enabled=enable_cache)
        self._metrics = MetricsCollector()
        self._llm: LLMSynthesizer | None = None
        if enable_llm_synthesis and openrouter_api_key:
            self._llm = LLMSynthesizer(
                logger=logger, api_key=openrouter_api_key, model=openrouter_model,
            )

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower().replace("www.", "")

    @staticmethod
    def _allowed(url: str, allowed_domains: list[str]) -> bool:
        if not allowed_domains:
            return True
        domain = urlparse(url).netloc.lower().replace("www.", "")
        for allowed in allowed_domains:
            allowed_norm = allowed.lower().replace("www.", "")
            if domain == allowed_norm or domain.endswith(f".{allowed_norm}"):
                return True
        return False

    @staticmethod
    def _url_rank(url: str) -> float:
        url_l = url.lower()
        score = 0.0
        if "docs" in url_l or "readthedocs" in url_l:
            score += 2.2
        if "github.com" in url_l or "raw.githubusercontent.com" in url_l:
            score += 1.0
        if any(x in url_l for x in ["medium.com", "quora.com", "pinterest", "reddit.com"]):
            score -= 2.0
        return score

    @staticmethod
    def _is_seo_spam(text: str) -> bool:
        lowered = (text or "").lower()
        spam_signals = [
            "sponsored",
            "affiliate",
            "casino",
            "promo code",
            "click here",
            "best price",
            "coupon",
            "download now",
        ]
        return any(signal in lowered for signal in spam_signals)

    @staticmethod
    def _task_terms(task: str) -> list[str]:
        words = re.findall(r"[a-zA-Z0-9_]+", task.lower())
        stop = {
            "a",
            "an",
            "and",
            "or",
            "the",
            "to",
            "for",
            "of",
            "in",
            "on",
            "with",
            "that",
            "this",
            "create",
            "build",
            "make",
        }
        return [w for w in words if len(w) > 2 and w not in stop]

    @classmethod
    def _text_relevance(cls, task: str, text: str) -> float:
        terms = cls._task_terms(task)
        if not terms:
            return 0.0
        lowered = (text or "").lower()
        matches = sum(1 for term in terms if term in lowered)
        coverage = matches / len(terms)
        phrase_bonus = 0.25 if task.lower() in lowered else 0.0
        return min(1.0, coverage + phrase_bonus)

    def _collect_urls(
        self,
        task: str,
        search_results,
        github_results,
        max_sources: int,
        allowed_domains: list[str],
    ) -> list[str]:
        scored: list[tuple[str, float]] = []

        # Hybrid approach: semantic + term-based scoring
        # Embeddings on short snippets may miss relevant results, so we use both signals
        for item in search_results:
            if self._allowed(item.url, allowed_domains):
                combined_text = f"{item.title} {item.snippet}"
                sem_score = self._ranker.compute_semantic_similarity(task, combined_text)
                term_score = self._text_relevance(task, combined_text)
                # Use the maximum of semantic and term scores, apply gentle threshold
                relevance_score = max(sem_score, term_score)
                if relevance_score < 0.18:
                    continue
                scored.append((item.url, item.score + self._url_rank(item.url) + (2.5 * relevance_score)))

        for item in github_results:
            if self._allowed(item.url, allowed_domains):
                combined_text = f"{item.title} {item.snippet}"
                sem_score = self._ranker.compute_semantic_similarity(task, combined_text)
                term_score = self._text_relevance(task, combined_text)
                relevance_score = max(sem_score, term_score)
                if relevance_score < 0.16:
                    continue
                scored.append((item.url, item.score + self._url_rank(item.url) + (2.5 * relevance_score)))

        dedup: dict[str, float] = {}
        for url, score in scored:
            existing = dedup.get(url)
            if existing is None or score > existing:
                dedup[url] = score

        ordered = sorted(dedup.items(), key=lambda x: x[1], reverse=True)
        urls = [url for url, _ in ordered[: max_sources * 2]]

        # Domain-level de-dup to avoid overfitting on one site.
        selected: list[str] = []
        domain_counts: dict[str, int] = {}
        for url in urls:
            domain = self._domain(url)
            if domain_counts.get(domain, 0) >= 3:
                continue
            selected.append(url)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            if len(selected) >= max_sources:
                break

        return selected

    async def run(
        self,
        task: str,
        max_sources: int,
        allowed_domains: list[str],
        include_github: bool,
        include_github_code_search: bool,
        github_code_languages: list[str],
        max_code_snippets: int,
        include_stackoverflow: bool = True,
    ) -> dict:
        try:
            # Reset metrics for a fresh run — prevents stale data from prior calls
            self._metrics.reset()

            # Check cache first — hash ALL parameters that affect output
            config_hash = hashlib.sha256(
                f"{max_sources}|{allowed_domains}|{include_github}|{max_code_snippets}"
                f"|{include_github_code_search}|{github_code_languages}"
                f"|{include_stackoverflow}".encode()
            ).hexdigest()
            cached_result = await self._cache.get_task_result(task, config_hash)
            if cached_result:
                self._logger.info("Returning cached result", extra={"task": task})
                self._metrics.increment("cache_hits")
                return cached_result
            self._metrics.increment("cache_misses")

            signals = self._expander.extract_signals(task)
            queries = self._expander.expand(task=task, signals=signals)
            self._metrics.record("queries_generated", len(queries))

            self._logger.info("Queries generated", extra={"queries": queries})

            # Search phase
            self._metrics.start_phase("search")
            search_results = await self._search.multi_search(queries=queries[:8], per_query=5)

            github_results = []
            if include_github:
                github_results = await self._github.mine(
                    task=task,
                    signals=signals,
                    max_items=max_sources,
                    include_code_search=include_github_code_search,
                    target_languages=github_code_languages,
                )

            stackoverflow_answers = []
            if include_stackoverflow and self._stackoverflow:
                stackoverflow_answers = await self._stackoverflow.mine(
                    task=task, signals=signals, max_results=5
                )
                self._metrics.record("stackoverflow_answers", len(stackoverflow_answers))

            self._metrics.end_phase("search")

            urls = self._collect_urls(
                task=task,
                search_results=search_results,
                github_results=github_results,
                max_sources=max_sources,
                allowed_domains=allowed_domains,
            )
            self._metrics.record("sources_discovered", len(urls))

            # Calculate content diversity
            unique_domains = len(set(self._domain(url) for url in urls))
            self._metrics.record("content_diversity_score", unique_domains / max(1, len(urls)))

            self._logger.info("Sources discovered", extra={"count": len(urls), "urls": urls})

            # Crawl phase
            self._metrics.start_phase("crawl")
            pages = await self._crawler.crawl(urls)
            self._metrics.record("pages_scraped", len(pages))
            self._metrics.record("pages_failed", len(urls) - len(pages))
            self._metrics.end_phase("crawl")

            self._logger.info("Pages scraped", extra={"count": len(pages)})

            # Extraction phase
            self._metrics.start_phase("extraction")
            docs: list[ExtractedDoc] = []
            snippets: list[ExtractedSnippet] = []
            chunks = []
            spam_count = 0

            for page in pages:
                doc = self._extractor.extract(page)
                if doc is None:
                    continue
                if self._is_seo_spam(f"{doc.title} {doc.summary}"):
                    spam_count += 1
                    continue
                docs.append(doc)
                snippets.extend(doc.snippets)
                chunks.extend(self._chunker.chunk_text(text=doc.clean_markdown, source=doc.source))

            self._metrics.record("documents_extracted", len(docs))
            self._metrics.record("documents_filtered_spam", spam_count)
            self._metrics.record("code_snippets_extracted", len(snippets))
            self._metrics.record("chunks_created", len(chunks))
            self._metrics.end_phase("extraction")

            self._logger.info(
                "Extraction complete",
                extra={
                    "documents": len(docs),
                    "code_snippets": len(snippets),
                    "chunks": len(chunks),
                    "spam_filtered": spam_count,
                },
            )

            # Deduplication
            chunks = self._deduplicator.deduplicate_chunks(chunks)
            self._logger.info("Deduplication complete", extra={"unique_chunks": len(chunks)})

            # Ranking phase
            self._metrics.start_phase("ranking")
            scored_chunks = self._ranker.rank_chunks(task=task, chunks=chunks, top_k=24)
            scored_snippets = self._ranker.rank_snippets(task=task, snippets=snippets, top_k=max_code_snippets)

            # Prune weakly related items to reduce off-topic drift in final context.
            if scored_chunks:
                top_chunk_score = scored_chunks[0].score
                min_chunk_score = max(0.18, top_chunk_score * 0.55)
                scored_chunks = [sc for sc in scored_chunks if sc.score >= min_chunk_score][:24]

            if scored_snippets:
                top_snippet_score = scored_snippets[0].score
                min_snippet_score = max(0.20, top_snippet_score * 0.60)
                scored_snippets = [ss for ss in scored_snippets if ss.score >= min_snippet_score][:max_code_snippets]

            # --- Relevant-context skill: Bucketize into Critical / Helpful / Noise ---
            bucketized = self._ranker.bucketize(scored_chunks, scored_snippets)

            # Filter docs to only those referenced by critical/helpful sources
            relevant_sources = {
                sc.chunk.source for sc in bucketized.critical_chunks
            } | {
                sc.chunk.source for sc in bucketized.helpful_chunks
            } | {
                ss.snippet.source for ss in bucketized.critical_snippets
            } | {
                ss.snippet.source for ss in bucketized.helpful_snippets
            }

            if relevant_sources:
                docs = [doc for doc in docs if doc.source in relevant_sources]

            if stackoverflow_answers:
                stackoverflow_answers = [
                    answer
                    for answer in stackoverflow_answers
                    if max(
                        self._ranker.compute_semantic_similarity(
                            task,
                            f"{answer.question_title} {answer.answer_body[:800]}",
                        ),
                        self._text_relevance(
                            task,
                            f"{answer.question_title} {answer.answer_body[:800]}",
                        ),
                    ) >= 0.22
                ]

            # Calculate avg relevance scores
            if scored_chunks:
                avg_chunk_rel = sum(sc.score for sc in scored_chunks) / len(scored_chunks)
                self._metrics.record("avg_chunk_relevance", avg_chunk_rel)
            if scored_snippets:
                avg_snippet_rel = sum(ss.score for ss in scored_snippets) / len(scored_snippets)
                self._metrics.record("avg_snippet_relevance", avg_snippet_rel)

            self._metrics.record("chunks_ranked", len(scored_chunks))
            self._metrics.record("code_snippets_ranked", len(scored_snippets))
            self._metrics.record("critical_chunks", len(bucketized.critical_chunks))
            self._metrics.record("helpful_chunks", len(bucketized.helpful_chunks))
            self._metrics.record("critical_snippets", len(bucketized.critical_snippets))
            self._metrics.record("helpful_snippets", len(bucketized.helpful_snippets))
            self._metrics.end_phase("ranking")

            # Pattern detection
            all_snippets = bucketized.critical_snippets + bucketized.helpful_snippets
            snippet_tuples = [(s.snippet.code, s.snippet.source) for s in all_snippets]
            patterns = self._pattern_detector.detect_batch(snippet_tuples)
            self._metrics.record("patterns_detected", len(patterns))

            self._logger.info(
                "Semantic filtering complete (relevant-context skill)",
                extra={
                    "critical_chunks": len(bucketized.critical_chunks),
                    "helpful_chunks": len(bucketized.helpful_chunks),
                    "critical_snippets": len(bucketized.critical_snippets),
                    "helpful_snippets": len(bucketized.helpful_snippets),
                    "patterns_detected": len(patterns),
                },
            )

            # --- Format using the relevant-context skill output schema ---
            result = self._formatter.format_relevant_context(
                task=task,
                docs=docs,
                bucketized=bucketized,
                max_code_snippets=max_code_snippets,
                patterns=patterns,
                stackoverflow_answers=stackoverflow_answers,
            )

            # LLM RAG synthesis step — pass the full result dict (not just context)
            if self._llm:
                self._metrics.start_phase("llm_synthesis")
                self._logger.info("Starting LLM RAG synthesis (relevant-context skill)")
                llm_response = await self._llm.synthesize(task=task, result=result)
                self._metrics.end_phase("llm_synthesis")

                if llm_response:
                    result["llm_guidance"] = {
                        "content": llm_response.content,
                        "model": llm_response.model,
                        "tokens_used": llm_response.total_tokens,
                        "finish_reason": llm_response.finish_reason,
                    }
                    self._metrics.record("llm_tokens_used", llm_response.total_tokens)
                    self._logger.info(
                        "LLM synthesis complete",
                        extra={"tokens": llm_response.total_tokens, "model": llm_response.model},
                    )
                else:
                    result["llm_guidance"] = None
                    self._logger.warning("LLM synthesis returned no result — raw context still available")
            else:
                result["llm_guidance"] = None

            # Add metrics to result
            result["metrics"] = self._metrics.to_dict()

            # Cache result
            await self._cache.set_task_result(task, config_hash, result, ttl_seconds=3600)

            return result
        except (
            httpx.HTTPError,
            httpx.TimeoutException,
            asyncio.TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            RuntimeError,
            OSError,
            ValueError,
        ) as exc:
            # Known recoverable errors: return empty context gracefully
            self._metrics.record_error(str(exc))
            self._logger.error(
                "Pipeline execution failed with recoverable error",
                extra={"error": str(exc), "type": type(exc).__name__, "metrics": self._metrics.to_dict()},
            )
            return {
                "task": task,
                "relevant_context": [],
                "context": {
                    "concepts": [],
                    "code_snippets": [],
                    "api_references": [],
                    "best_practices": [],
                    "implementation_patterns": [],
                    "stackoverflow_answers": [],
                },
                "open_questions": [f"Pipeline failed with error: {type(exc).__name__}: {exc}"],
                "recommended_next_context": ["Retry with different parameters or check network connectivity."],
                "metrics": self._metrics.to_dict(),
            }
        except Exception as exc:
            # Unexpected bug — log full traceback and re-raise so the actor fails visibly
            self._metrics.record_error(str(exc))
            self._logger.error(
                "Pipeline execution failed with unexpected error",
                extra={
                    "error": str(exc),
                    "type": type(exc).__name__,
                    "traceback": traceback.format_exc(),
                    "metrics": self._metrics.to_dict(),
                },
            )
            raise
