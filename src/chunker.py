from __future__ import annotations

from dataclasses import dataclass

import tiktoken


@dataclass(slots=True)
class LLMChunk:
    text: str
    tokens: int
    source: str


class Chunker:
    def __init__(self, max_tokens: int = 500) -> None:
        self._max_tokens = max_tokens
        self._encoding = tiktoken.get_encoding("cl100k_base")

    def token_count(self, text: str) -> int:
        return len(self._encoding.encode(text or ""))

    def chunk_text(self, text: str, source: str) -> list[LLMChunk]:
        if not text.strip():
            return []

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[LLMChunk] = []
        current_parts: list[str] = []
        current_tokens = 0

        def flush() -> None:
            nonlocal current_parts, current_tokens
            if not current_parts:
                return
            combined = "\n\n".join(current_parts).strip()
            tokens = self.token_count(combined)
            chunks.append(LLMChunk(text=combined, tokens=tokens, source=source))
            current_parts = []
            current_tokens = 0

        for paragraph in paragraphs:
            paragraph_tokens = self.token_count(paragraph)

            # Keep code blocks intact when possible by splitting only by large lines if needed.
            if paragraph_tokens > self._max_tokens:
                flush()
                lines = paragraph.splitlines()
                line_bucket: list[str] = []
                line_tokens = 0
                for line in lines:
                    t = self.token_count(line + "\n")
                    if line_bucket and line_tokens + t > self._max_tokens:
                        chunk_text = "\n".join(line_bucket)
                        chunks.append(LLMChunk(text=chunk_text, tokens=self.token_count(chunk_text), source=source))
                        line_bucket = [line]
                        line_tokens = t
                    else:
                        line_bucket.append(line)
                        line_tokens += t
                if line_bucket:
                    chunk_text = "\n".join(line_bucket)
                    chunks.append(LLMChunk(text=chunk_text, tokens=self.token_count(chunk_text), source=source))
                continue

            if current_parts and current_tokens + paragraph_tokens > self._max_tokens:
                flush()

            current_parts.append(paragraph)
            current_tokens += paragraph_tokens

        flush()
        return chunks
