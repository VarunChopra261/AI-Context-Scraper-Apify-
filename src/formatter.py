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
        relevant_context: list[dict] = []

        for sc in bucketized.critical_chunks:
            relevant_context.append({
                "source": sc.chunk.source,
                "bucket": "critical",
                "relevance_score": round(sc.score, 3),
                "why_it_matters": "High-relevance documentation chunk — model likely to fail without it",
                "key_detail": sc.chunk.text[:400],
            })
        if include_helpful:
            for sc in bucketized.helpful_chunks:
                relevant_context.append({
                    "source": sc.chunk.source,
                    "bucket": "helpful",
                    "relevance_score": round(sc.score, 3),
                    "why_it_matters": "Helpful supporting context — improves confidence",
                    "key_detail": sc.chunk.text[:300],
                })

        # --- Code snippets (Critical first, then Helpful if needed) ---
        code_snippets: list[dict] = []
        for ss in bucketized.critical_snippets[:max_code_snippets]:
            code_snippets.append({
                "language": ss.snippet.language,
                "description": ss.snippet.description,
                "code": ss.snippet.code,
                "source": ss.snippet.source,
                "bucket": "critical",
                "relevance_score": round(ss.score, 3),
            })
        if include_helpful:
            remaining = max_code_snippets - len(code_snippets)
            for ss in bucketized.helpful_snippets[:remaining]:
                code_snippets.append({
                    "language": ss.snippet.language,
                    "description": ss.snippet.description,
                    "code": ss.snippet.code,
                    "source": ss.snippet.source,
                    "bucket": "helpful",
                    "relevance_score": round(ss.score, 3),
                })

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

        # --- Patterns ---
        implementation_patterns = []
        if patterns:
            for pattern in patterns:
                implementation_patterns.append({
                    "pattern_type": pattern.pattern_type.value,
                    "description": pattern.description,
                    "code_snippet": pattern.code_snippet[:1000],
                    "source": pattern.source,
                    "confidence": round(pattern.confidence, 3),
                })

        # --- StackOverflow ---
        so_answers = []
        if stackoverflow_answers:
            for answer in stackoverflow_answers:
                so_answers.append({
                    "question_title": answer.question_title,
                    "question_url": answer.question_url,
                    "answer_body": answer.answer_body[:2000],
                    "score": answer.score,
                    "accepted": answer.accepted,
                    "tags": answer.tags,
                })

        # --- Open questions (surface unknowns) ---
        open_questions: list[str] = []
        if not code_snippets:
            open_questions.append("No code examples survived relevance filtering — the task may need more specific search terms.")
        if not so_answers:
            open_questions.append("No StackOverflow answers matched the task — community solutions may exist under different terminology.")
        if include_helpful and not bucketized.helpful_chunks:
            open_questions.append("Very few relevant context chunks found — results may be incomplete.")

        # --- Recommended next context ---
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
