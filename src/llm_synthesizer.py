"""LLM synthesis layer using OpenRouter API for RAG-powered context generation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_CONTEXT_CHARS = 48_000  # Stay well within typical context windows


SYSTEM_PROMPT = """\
You are an expert context curator following the 'relevant-context' skill workflow.

You will receive a developer's coding task and retrieved context that has already been \
ranked into Critical and Helpful buckets. Your job is to synthesize this into a compact, \
high-signal context package that can be directly consumed by AI coding agents or developers.

Follow these rules strictly:

1. COMPRESS WITHOUT DISTORTING: For each piece of context, provide:
   - The source path or URL
   - One short reason it matters
   - The smallest accurate summary of the relevant part
   Prefer bullets, signatures, interfaces, and behavior summaries over long prose. \
Quote exact text only when wording itself matters.

2. SURFACE UNKNOWNS AND RISKS: Call out missing context explicitly instead of padding \
with guesses. Examples:
   - "The error is known but the failing input is missing"
   - "Tests exist for success cases but not edge cases"
   If a gap is material, state what should be fetched next.

3. INCLUDE WORKING CODE: When the task involves implementation, include production-ready \
code examples synthesized from the retrieved snippets.

4. OUTPUT FORMAT — use this exact structure:

## Task
- Short restatement of the goal

## Relevant Context
- [source]: why it matters; key detail

## Implementation
- Working code examples (if applicable)

## Open Questions
- Missing details that could change the answer

## Recommended Next Context
- The next file, doc, or search worth checking

5. DECISION RULES:
   - Prefer task-local context over general background
   - Prefer behavior-defining artifacts over explanatory artifacts
   - Prefer concrete examples over abstract descriptions
   - Stop elaborating once additional material no longer changes the plan
"""


@dataclass(slots=True)
class LLMResponse:
    """Response from the LLM synthesis."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str


class LLMSynthesizer:
    """Synthesizes gathered context into actionable guidance using an LLM."""

    def __init__(
        self,
        logger: Any,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self._logger = logger
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

    @staticmethod
    def _build_relevant_items_section(result: dict) -> list[str]:
        """Build the pre-ranked context section."""
        relevant_items = result.get("relevant_context", [])
        if not relevant_items:
            return []
        parts = ["## Pre-Ranked Context (already filtered for relevance)\n"]
        for item in relevant_items[:20]:
            bucket = item.get("bucket", "").upper()
            source = item.get("source", "")
            reason = item.get("why_it_matters", "")
            detail = item.get("key_detail", "")
            parts.append(f"[{bucket}] {source}: {reason}\n> {detail}\n")
        return parts

    @staticmethod
    def _build_concepts_section(context: dict) -> list[str]:
        """Build the documentation context section."""
        concepts = context.get("concepts", [])
        if not concepts:
            return []
        parts = ["## Documentation Context\n"]
        for concept in concepts[:15]:
            parts.append(
                f"### {concept.get('title', '')}\n"
                f"{concept.get('summary', '')}\n"
                f"Source: {concept.get('source', '')}\n"
            )
        return parts

    @staticmethod
    def _build_snippets_section(context: dict) -> list[str]:
        """Build the code examples section."""
        snippets = context.get("code_snippets", [])
        if not snippets:
            return []
        parts = ["## Code Examples\n"]
        for snippet in snippets[:10]:
            bucket = snippet.get("bucket", "").upper()
            lang = snippet.get("language", "text")
            desc = snippet.get("description", "")
            code = snippet.get("code", "")[:2000]
            source = snippet.get("source", "")
            label = f" [{bucket}]" if bucket else ""
            parts.append(f"### {desc}{label}\n```{lang}\n{code}\n```\nSource: {source}\n")
        return parts

    @staticmethod
    def _build_reference_sections(context: dict) -> list[str]:
        """Build API refs, best practices, and implementation patterns sections."""
        parts: list[str] = []

        api_refs = context.get("api_references", [])
        if api_refs:
            parts.append("## API References\n")
            for ref in api_refs[:10]:
                parts.append(f"- `{ref.get('function', '')}`: {ref.get('description', '')}\n")

        practices = context.get("best_practices", [])
        if practices:
            parts.append("## Best Practices\n")
            for p in practices[:8]:
                parts.append(f"- {p.get('practice', '')}\n")

        patterns = context.get("implementation_patterns", [])
        if patterns:
            parts.append("## Implementation Patterns\n")
            for pattern in patterns[:5]:
                ptype = pattern.get("pattern_type", "")
                desc = pattern.get("description", "")
                confidence = pattern.get("confidence", 0)
                snippet = pattern.get("code_snippet", "")[:800]
                parts.append(f"### {ptype} (confidence: {confidence})\n{desc}\n```\n{snippet}\n```\n")

        return parts

    @staticmethod
    def _build_community_sections(context: dict, result: dict) -> list[str]:
        """Build StackOverflow answers and known gaps sections."""
        parts: list[str] = []

        so_answers = context.get("stackoverflow_answers", [])
        if so_answers:
            parts.append("## StackOverflow Answers\n")
            for answer in so_answers[:3]:
                q_title = answer.get("question_title", "")
                q_url = answer.get("question_url", "")
                body = answer.get("answer_body", "")[:1500]
                score = answer.get("score", 0)
                parts.append(f"### {q_title} (score: {score})\n{body}\nSource: {q_url}\n")

        open_questions = result.get("open_questions", [])
        if open_questions:
            parts.append("## Known Gaps (from pipeline)\n")
            for q in open_questions:
                parts.append(f"- {q}\n")

        return parts

    def build_context_prompt(self, task: str, result: dict) -> str:
        """Build a structured prompt from the relevant-context skill output.

        Constructs the user message containing the task and all bucketized context,
        annotating each item with its [CRITICAL] or [HELPFUL] bucket label.
        The LLM uses these labels to decide what to emphasize in its synthesis.
        """
        context = result.get("context", {})
        parts: list[str] = [f"## Developer Task\n\n{task}\n"]

        parts.extend(self._build_relevant_items_section(result))
        parts.extend(self._build_concepts_section(context))
        parts.extend(self._build_snippets_section(context))
        parts.extend(self._build_reference_sections(context))
        parts.extend(self._build_community_sections(context, result))

        # Join and truncate to stay within limits
        full_prompt = "\n".join(parts)
        if len(full_prompt) > MAX_CONTEXT_CHARS:
            full_prompt = full_prompt[:MAX_CONTEXT_CHARS] + "\n\n[Context truncated for length]"

        full_prompt += (
            "\n\n---\n\n"
            "Based on the context above, synthesize a compact, high-signal response "
            "following the relevant-context skill template: Task restatement, Relevant "
            "Context (compressed), Implementation (code), Open Questions, Recommended Next "
            "Context. Focus on [CRITICAL] items. Include [HELPFUL] items only when they "
            "add material information."
        )

        return full_prompt

    async def synthesize(self, task: str, result: dict) -> LLMResponse | None:
        """Call the LLM API to synthesize context into an actionable response.

        Args:
            task: The developer's coding task.
            result: The full formatted result dict from the pipeline (includes
                    relevant_context, context, open_questions, etc.).

        Returns:
            LLMResponse with the synthesized content, or None on failure.
        """
        user_prompt = self.build_context_prompt(task, result)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://apify.com/ai-context-scraper",
            "X-Title": "AI Context Scraper",
        }

        for attempt in range(self._max_retries + 1):
            try:
                self._logger.info(
                    "Calling LLM API",
                    extra={"model": self._model, "attempt": attempt + 1},
                )
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        OPENROUTER_BASE_URL,
                        json=payload,
                        headers=headers,
                    )

                if response.status_code == 429:
                    # Rate limited — wait and retry
                    self._logger.warning("LLM API rate limited, retrying")
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue

                response.raise_for_status()
                data = response.json()

                # Parse OpenAI-compatible response
                choices = data.get("choices", [])
                if not choices:
                    self._logger.warning("LLM API returned no choices")
                    return None

                message = choices[0].get("message", {})
                content = message.get("content", "")
                finish_reason = choices[0].get("finish_reason", "unknown")

                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)

                self._logger.info(
                    "LLM synthesis complete",
                    extra={
                        "tokens_used": total_tokens,
                        "finish_reason": finish_reason,
                        "response_length": len(content),
                    },
                )

                return LLMResponse(
                    content=content,
                    model=data.get("model", self._model),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    finish_reason=finish_reason,
                )

            except httpx.TimeoutException:
                self._logger.warning(
                    "LLM API timeout",
                    extra={"attempt": attempt + 1, "timeout": self._timeout},
                )
                if attempt >= self._max_retries:
                    return None
            except httpx.HTTPStatusError as exc:
                self._logger.warning(
                    "LLM API HTTP error",
                    extra={"status": exc.response.status_code, "attempt": attempt + 1},
                )
                if attempt >= self._max_retries:
                    return None
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "LLM API call failed",
                    extra={"error": str(exc), "attempt": attempt + 1},
                )
                if attempt >= self._max_retries:
                    return None

        return None
