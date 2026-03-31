from __future__ import annotations

from .extractor import ExtractedDoc
from .relevance import BucketizedContext, ScoredChunk, ScoredSnippet


class ContextFormatter:
    @staticmethod
    def _unique_dicts(items: list[dict], key: str) -> list[dict]:
        seen = set()
        output: list[dict] = []
        for item in items:
            value = item.get(key)
            if not value or value in seen:
                continue
            seen.add(value)
            output.append(item)
        return output

    def format(
        self,
        task: str,
        docs: list[ExtractedDoc],
        scored_chunks: list[ScoredChunk],
        scored_snippets: list[ScoredSnippet],
        max_code_snippets: int,
        patterns: list | None = None,
        stackoverflow_answers: list | None = None,
    ) -> dict:
        concepts = [
            {
                "title": doc.title,
                "summary": doc.summary,
                "source": doc.source,
            }
            for doc in docs
            if doc.summary
        ]

        api_refs = [ref for doc in docs for ref in doc.api_references]
        best_practices = [practice for doc in docs for practice in doc.best_practices]

        snippets = []
        for scored in scored_snippets[:max_code_snippets]:
            snippet = scored.snippet
            snippets.append(
                {
                    "language": snippet.language,
                    "description": snippet.description,
                    "code": snippet.code,
                    "source": snippet.source,
                }
            )

        llm_chunks = [
            {
                "text": scored.chunk.text,
                "tokens": scored.chunk.tokens,
                "source": scored.chunk.source,
            }
            for scored in scored_chunks
        ]

        # Format implementation patterns
        implementation_patterns = []
        if patterns:
            for pattern in patterns:
                implementation_patterns.append(
                    {
                        "pattern_type": pattern.pattern_type.value,
                        "description": pattern.description,
                        "code_snippet": pattern.code_snippet[:1000],
                        "source": pattern.source,
                        "confidence": round(pattern.confidence, 3),
                    }
                )

        # Format StackOverflow answers
        so_answers = []
        if stackoverflow_answers:
            for answer in stackoverflow_answers:
                so_answers.append(
                    {
                        "question_title": answer.question_title,
                        "question_url": answer.question_url,
                        "answer_body": answer.answer_body[:2000],
                        "score": answer.score,
                        "accepted": answer.accepted,
                        "tags": answer.tags,
                    }
                )

        return {
            "task": task,
            "context": {
                "concepts": concepts[:30],
                "code_snippets": snippets,
                "api_references": self._unique_dicts(api_refs, key="function")[:40],
                "best_practices": self._unique_dicts(best_practices, key="practice")[:30],
                "implementation_patterns": implementation_patterns,
                "stackoverflow_answers": so_answers,
                "llm_chunks": llm_chunks,
            },
        }

    @staticmethod
    def _format_patterns(patterns: list | None) -> list[dict]:
        """Format implementation patterns for output."""
        if not patterns:
            return []
        return [
            {
                "pattern_type": p.pattern_type.value,
                "description": p.description,
                "code_snippet": p.code_snippet[:1000],
                "source": p.source,
                "confidence": round(p.confidence, 3),
            }
            for p in patterns
        ]

    @staticmethod
    def _format_stackoverflow(stackoverflow_answers: list | None) -> list[dict]:
        """Format StackOverflow answers for output."""
        if not stackoverflow_answers:
            return []
        return [
            {
                "question_title": a.question_title,
                "question_url": a.question_url,
                "answer_body": a.answer_body[:2000],
                "score": a.score,
                "accepted": a.accepted,
                "tags": a.tags,
            }
            for a in stackoverflow_answers
        ]

    @staticmethod
    def _build_open_questions(
        code_snippets: list[dict],
        so_answers: list[dict],
        include_helpful: bool,
        helpful_chunks: list,
    ) -> list[str]:
        """Build open-questions and recommended-next-context lists."""
        questions: list[str] = []
        if not code_snippets:
            questions.append(
                "No code examples survived relevance filtering — the task may need more specific search terms."
            )
        if not so_answers:
            questions.append(
                "No StackOverflow answers matched the task — community solutions may exist under different terminology."
            )
        if include_helpful and not helpful_chunks:
            questions.append("Very few relevant context chunks found — results may be incomplete.")
        return questions

    def format_relevant_context(
        self,
        task: str,
        docs: list[ExtractedDoc],
        bucketized: BucketizedContext,
        max_code_snippets: int,
        patterns: list | None = None,
        stackoverflow_answers: list | None = None,
    ) -> dict:
        """Format output following the relevant-context skill schema.

        Only Critical items are always included. Helpful items are included
        only when there are fewer than 3 Critical chunks (the task boundary
        is likely ambiguous).
        """
        # Decide whether to include helpful items
        include_helpful = len(bucketized.critical_chunks) < 3

        # --- Build relevant_context entries ---
        relevant_context: list[dict] = [
            {
                "source": sc.chunk.source,
                "bucket": "critical",
                "relevance_score": round(sc.score, 3),
                "why_it_matters": "High-relevance documentation chunk — model likely to fail without it",
                "key_detail": sc.chunk.text[:400],
            }
            for sc in bucketized.critical_chunks
        ]
        if include_helpful:
            relevant_context.extend(
                {
                    "source": sc.chunk.source,
                    "bucket": "helpful",
                    "relevance_score": round(sc.score, 3),
                    "why_it_matters": "Helpful supporting context — improves confidence",
                    "key_detail": sc.chunk.text[:300],
                }
                for sc in bucketized.helpful_chunks
            )

        # --- Code snippets (Critical first, then Helpful if needed) ---
        code_snippets: list[dict] = [
            {
                "language": ss.snippet.language,
                "description": ss.snippet.description,
                "code": ss.snippet.code,
                "source": ss.snippet.source,
                "bucket": "critical",
                "relevance_score": round(ss.score, 3),
            }
            for ss in bucketized.critical_snippets[:max_code_snippets]
        ]
        if include_helpful:
            remaining = max_code_snippets - len(code_snippets)
            code_snippets.extend(
                {
                    "language": ss.snippet.language,
                    "description": ss.snippet.description,
                    "code": ss.snippet.code,
                    "source": ss.snippet.source,
                    "bucket": "helpful",
                    "relevance_score": round(ss.score, 3),
                }
                for ss in bucketized.helpful_snippets[:remaining]
            )

        # --- Concepts (only from docs whose sources appear in kept chunks) ---
        kept_sources = {rc["source"] for rc in relevant_context} | {cs["source"] for cs in code_snippets}
        concepts = [
            {"title": doc.title, "summary": doc.summary, "source": doc.source}
            for doc in docs
            if doc.summary and doc.source in kept_sources
        ]

        # --- API references & best practices from kept docs ---
        kept_docs = [doc for doc in docs if doc.source in kept_sources]
        api_refs = [ref for doc in kept_docs for ref in doc.api_references]
        best_practices = [p for doc in kept_docs for p in doc.best_practices]

        # --- Patterns & StackOverflow ---
        implementation_patterns = self._format_patterns(patterns)
        so_answers = self._format_stackoverflow(stackoverflow_answers)

        # --- Open questions & recommended next context ---
        open_questions = self._build_open_questions(
            code_snippets, so_answers, include_helpful, bucketized.helpful_chunks,
        )
        recommended_next: list[str] = []
        if not code_snippets:
            recommended_next.append("Search for official GitHub examples or cookbooks related to the task libraries.")
        if not api_refs:
            recommended_next.append("Fetch the official API reference docs for the frameworks mentioned in the task.")

        return {
            "task": task,
            "relevant_context": relevant_context[:30],
            "context": {
                "concepts": concepts[:20],
                "code_snippets": code_snippets,
                "api_references": self._unique_dicts(api_refs, key="function")[:30],
                "best_practices": self._unique_dicts(best_practices, key="practice")[:20],
                "implementation_patterns": implementation_patterns,
                "stackoverflow_answers": so_answers,
            },
            "open_questions": open_questions,
            "recommended_next_context": recommended_next,
        }
