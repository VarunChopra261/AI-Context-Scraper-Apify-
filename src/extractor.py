from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from readability import Document

from .crawler import CrawledPage

CODE_FENCE_PATTERN = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
API_REF_PATTERN = re.compile(r"\b([a-zA-Z_][\w\.]{2,})\(([^)]*)\)")
MD_HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


@dataclass(slots=True)
class ExtractedSnippet:
    language: str
    code: str
    source: str
    description: str
    score: float


@dataclass(slots=True)
class ExtractedDoc:
    source: str
    title: str
    summary: str
    clean_markdown: str
    headings: list[str]
    snippets: list[ExtractedSnippet]
    api_references: list[dict[str, str]]
    best_practices: list[dict[str, str]]


class ContentExtractor:
    def __init__(self, logger) -> None:
        self._logger = logger

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned

    @staticmethod
    def _guess_language(class_name: str, code: str) -> str:
        lowered = (class_name or "").lower()
        if "python" in lowered or "py" in lowered:
            return "python"
        if "javascript" in lowered or "js" in lowered:
            return "javascript"
        if "bash" in lowered or "shell" in lowered or code.strip().startswith("$"):
            return "bash"
        if "yaml" in lowered or "yml" in lowered:
            return "yaml"

        code_l = code.lower()
        if "import " in code_l and "def " in code_l:
            return "python"
        if "const " in code_l or "function " in code_l:
            return "javascript"
        # Tighter YAML heuristic: require multiple key: value lines (at least 3)
        if "{" not in code and "}" not in code:
            yaml_lines = [line for line in code.splitlines() if re.match(r"^\s*[\w_-]+\s*:", line)]
            if len(yaml_lines) >= 3:
                return "yaml"
        return "text"

    @staticmethod
    def _extract_best_practices(markdown_text: str, source: str) -> list[dict[str, str]]:
        practices: list[dict[str, str]] = []
        lines = [line.strip() for line in markdown_text.splitlines()]

        for line in lines:
            if len(line) < 40 or len(line) > 220:
                continue
            lowered = line.lower()
            if any(key in lowered for key in ["should", "avoid", "recommended", "best practice", "must"]):
                practices.append(
                    {
                        "practice": line[:180],
                        "reason": "Extracted from authoritative guidance text.",
                        "source": source,
                    }
                )
        return practices[:12]

    @staticmethod
    def _extract_api_references(markdown_text: str, source: str) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        for match in API_REF_PATTERN.finditer(markdown_text):
            fn = match.group(1)
            args = match.group(2)
            if len(fn) < 3:
                continue
            refs.append(
                {
                    "library": fn.split(".")[0],
                    "function": fn,
                    "description": f"Usage pattern with arguments: ({args})",
                    "source": source,
                }
            )
        return refs[:20]

    def _extract_from_html(
        self, raw: str, page: CrawledPage,
    ) -> tuple[str, str, list[str], list[ExtractedSnippet]]:
        """Extract title, markdown, headings, and snippets from an HTML page."""
        readable = Document(raw)
        title = readable.short_title() or page.url
        article_html = readable.summary(html_partial=True)
        soup = BeautifulSoup(article_html, "html.parser")
        for tag in soup(["nav", "footer", "script", "style", "noscript", "aside", "form"]):
            tag.decompose()
        markdown_text = md(str(soup), heading_style="ATX")

        headings = [self._clean_text(h.get_text(" ")) for h in soup.find_all(re.compile("^h[1-4]$"))]
        headings = [h for h in headings if h]

        snippets: list[ExtractedSnippet] = []
        for block in soup.find_all(["pre", "code"]):
            text = block.get_text("\n")
            text = text.strip("\n ")
            if len(text) < 40 or len(text.splitlines()) < 2:
                continue
            class_name = " ".join(block.get("class") or [])
            lang = self._guess_language(class_name, text)
            snippets.append(
                ExtractedSnippet(
                    language=lang,
                    code=text[:3000],
                    source=page.url,
                    description=f"Extracted code block from {title}",
                    score=1.0,
                )
            )

        for fenced in CODE_FENCE_PATTERN.finditer(markdown_text):
            lang = (fenced.group(1) or "text").strip().lower()
            code = fenced.group(2).strip()
            if len(code) < 40 or len(code.splitlines()) < 2:
                continue
            snippets.append(
                ExtractedSnippet(
                    language=lang or "text",
                    code=code[:3000],
                    source=page.url,
                    description=f"Markdown fenced snippet from {title}",
                    score=1.0,
                )
            )

        return title, markdown_text, headings, snippets

    def extract(self, page: CrawledPage) -> ExtractedDoc | None:
        raw = page.text or ""
        if len(raw) < 200:
            return None

        try:
            is_markdown = "markdown" in page.content_type or page.url.endswith(".md")

            if is_markdown:
                title = page.url.rsplit("/", maxsplit=1)[-1] or "README"
                markdown_text = raw

                headings = [
                    self._clean_text(match.group(2))
                    for match in MD_HEADING_PATTERN.finditer(markdown_text)
                ]
                headings = [h for h in headings if h]

                snippets: list[ExtractedSnippet] = []
                for fenced in CODE_FENCE_PATTERN.finditer(markdown_text):
                    lang = (fenced.group(1) or "text").strip().lower()
                    code = fenced.group(2).strip()
                    if len(code) < 40 or len(code.splitlines()) < 2:
                        continue
                    snippets.append(
                        ExtractedSnippet(
                            language=lang or "text",
                            code=code[:3000],
                            source=page.url,
                            description=f"Markdown fenced snippet from {title}",
                            score=1.0,
                        )
                    )
            else:
                title, markdown_text, headings, snippets = self._extract_from_html(raw, page)

            summary = self._clean_text(" ".join(markdown_text.splitlines()[:8]))[:400]
            api_refs = self._extract_api_references(markdown_text, page.url)
            practices = self._extract_best_practices(markdown_text, page.url)

            return ExtractedDoc(
                source=page.url,
                title=title,
                summary=summary,
                clean_markdown=markdown_text[:50000],
                headings=headings[:20],
                snippets=snippets,
                api_references=api_refs,
                best_practices=practices,
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Extraction failed", extra={"url": page.url, "error": str(exc)})
            return None
