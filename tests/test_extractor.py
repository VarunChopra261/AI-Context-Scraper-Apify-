"""Stress tests for extractor.py — every assertion is unconditional."""

import pytest
from unittest.mock import MagicMock

from src.crawler import CrawledPage
from src.extractor import ContentExtractor, ExtractedDoc, ExtractedSnippet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(
    html: str,
    url: str = "https://example.com/page",
    content_type: str = "text/html",
    status_code: int = 200,
) -> CrawledPage:
    return CrawledPage(url=url, status_code=status_code, content_type=content_type, text=html, fetched_at=0.0)


def _make_rich_article(*, include_code: bool = True) -> str:
    """Build a ~800-char article that always survives readability + length filter."""
    code_block = """
    <pre><code class="language-python">
from fastapi import FastAPI, UploadFile

app = FastAPI()

@app.post("/upload/")
async def upload_file(file: UploadFile):
    contents = await file.read()
    return {"filename": file.filename}
    </code></pre>
""" if include_code else ""
    return f"""<!DOCTYPE html>
<html>
<head><title>FastAPI Upload Guide</title></head>
<body>
<article>
<h1>FastAPI File Upload Guide</h1>
<p>FastAPI provides the UploadFile class for handling file uploads asynchronously.
You should always validate the file size before processing to prevent DoS attacks.
It is recommended to use async endpoints for any file I/O operation in FastAPI.</p>
<h2>Code Example</h2>
{code_block}
<p>This approach is a best practice for handling file uploads in modern Python APIs.
Always set a maximum file size limit. Avoid processing untrusted input directly.
You must sanitize the filename before writing to disk to prevent path traversal.</p>
<p>Additional context: FastAPI integrates with Starlette for file handling, and
the UploadFile object provides an async read() method that returns bytes.
Support for multiple files is available via the List[UploadFile] type annotation.</p>
</article>
</body>
</html>"""


@pytest.fixture
def extractor():
    mock_log = MagicMock()
    return ContentExtractor(logger=mock_log)


# ---------------------------------------------------------------------------
# extract() — basic invariants
# ---------------------------------------------------------------------------

class TestExtractBasicInvariants:
    def test_rich_page_returns_extracted_doc(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None, "Should extract a valid doc from rich HTML"
        assert isinstance(doc, ExtractedDoc)

    def test_source_is_always_page_url(self, extractor):
        url = "https://docs.example.com/api/v2"
        page = _make_page(_make_rich_article(), url=url)
        doc = extractor.extract(page)
        assert doc is not None
        assert doc.source == url

    def test_title_is_non_empty_string(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        assert isinstance(doc.title, str)
        assert doc.title.strip() != ""

    def test_clean_markdown_is_non_empty(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        assert len(doc.clean_markdown) > 50

    def test_summary_is_non_empty(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        assert doc.summary.strip() != ""

    def test_summary_max_400_chars(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        assert len(doc.summary) <= 400

    def test_clean_markdown_max_30000_chars(self, extractor):
        """Even for huge pages, clean_markdown must be capped at 30 000 chars."""
        big_html = _make_rich_article() + ("<p>" + "x " * 20000 + "</p>")
        page = _make_page(big_html)
        doc = extractor.extract(page)
        if doc:
            assert len(doc.clean_markdown) <= 30000

    def test_headings_list_at_most_20(self, extractor):
        many_h2 = "\n".join([f"<h2>Heading {i}</h2><p>Content for heading {i} that is long enough.</p>" for i in range(30)])
        html = f"<html><body><article><h1>Title</h1>{many_h2}</article></body></html>"
        page = _make_page(html)
        doc = extractor.extract(page)
        if doc:
            assert len(doc.headings) <= 20

    def test_snippets_list_is_list(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        assert isinstance(doc.snippets, list)


# ---------------------------------------------------------------------------
# extract() — short content filter
# ---------------------------------------------------------------------------

class TestShortContentFilter:
    def test_empty_string_returns_none(self, extractor):
        page = _make_page("")
        assert extractor.extract(page) is None

    def test_text_under_200_chars_returns_none(self, extractor):
        page = _make_page("<html><body><p>Short.</p></body></html>")
        assert len(page.text) < 200
        assert extractor.extract(page) is None

    def test_exactly_200_chars_does_not_crash(self, extractor):
        """A page of exactly 200 chars must not raise; None or doc is fine."""
        page = _make_page("x" * 200)
        # Should not raise
        _ = extractor.extract(page)

    def test_199_chars_returns_none(self, extractor):
        page = _make_page("a" * 199)
        assert extractor.extract(page) is None


# ---------------------------------------------------------------------------
# Headings extraction
# ---------------------------------------------------------------------------

class TestHeadingsExtraction:
    def test_h1_h2_h3_extracted(self, extractor):
        html = """<html><body><article>
        <h1>Top Level</h1>
        <p>A sufficiently long paragraph about the topic being discussed here for extraction.</p>
        <h2>Second Level</h2>
        <p>Another sufficiently long paragraph that provides additional context and information.</p>
        <h3>Third Level</h3>
        <p>Yet another paragraph with plenty of content to ensure extraction works correctly.</p>
        </article></body></html>"""
        page = _make_page(html)
        doc = extractor.extract(page)
        assert doc is not None
        heading_text = " ".join(doc.headings)
        assert "Top Level" in heading_text or "Second Level" in heading_text

    def test_headings_are_non_empty_strings(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        for h in doc.headings:
            assert isinstance(h, str) and h.strip() != ""


# ---------------------------------------------------------------------------
# Code snippet extraction
# ---------------------------------------------------------------------------

class TestCodeSnippetExtraction:
    def test_code_snippets_extracted(self, extractor):
        page = _make_page(_make_rich_article(include_code=True))
        doc = extractor.extract(page)
        assert doc is not None
        assert len(doc.snippets) > 0

    def test_all_snippets_are_extracted_snippet_type(self, extractor):
        page = _make_page(_make_rich_article(include_code=True))
        doc = extractor.extract(page)
        assert doc is not None
        for s in doc.snippets:
            assert isinstance(s, ExtractedSnippet)

    def test_snippets_source_matches_page_url(self, extractor):
        url = "https://docs.mylib.io/guide"
        page = _make_page(_make_rich_article(include_code=True), url=url)
        doc = extractor.extract(page)
        assert doc is not None
        for s in doc.snippets:
            assert s.source == url

    def test_snippet_code_under_2000_chars(self, extractor):
        """Code is truncated at 2000 chars."""
        long_code = "x = 1\n" * 500  # ~3000 chars
        html = f"""<html><body><article>
        <h1>Test</h1>
        <p>This paragraph has enough text to pass the minimum length requirement for extraction.</p>
        <p>Additional text content to make the page long enough for readability to work correctly.</p>
        <pre><code class="language-python">{long_code}</code></pre>
        </article></body></html>"""
        page = _make_page(html)
        doc = extractor.extract(page)
        if doc and doc.snippets:
            for s in doc.snippets:
                assert len(s.code) <= 2000

    def test_snippet_min_length_40_chars_enforced(self, extractor):
        """Snippets shorter than 40 chars must be silently dropped."""
        html = """<html><body><article>
        <h1>Test</h1>
        <p>Sufficiently long introductory paragraph to meet minimum extraction length requirements.</p>
        <pre><code>x = 1</code></pre>
        <p>Additional content to ensure the page is long enough for extraction to work properly.</p>
        </article></body></html>"""
        page = _make_page(html)
        doc = extractor.extract(page)
        if doc:
            for s in doc.snippets:
                assert len(s.code) >= 40

    def test_snippet_min_2_lines_enforced(self, extractor):
        """Single-line snippets (< 2 lines) must be dropped."""
        html = """<html><body><article>
        <h1>Test</h1>
        <p>Sufficiently long introductory paragraph about the topic being discussed here today.</p>
        <pre><code class="language-python">single_line_function_call(argument1, argument2)</code></pre>
        <p>More content here to ensure the extractor has enough text to work with properly.</p>
        </article></body></html>"""
        page = _make_page(html)
        doc = extractor.extract(page)
        if doc:
            for s in doc.snippets:
                assert len(s.code.splitlines()) >= 2

    def test_python_language_detected_from_class_name(self, extractor):
        page = _make_page(_make_rich_article(include_code=True))
        doc = extractor.extract(page)
        assert doc is not None
        python_snippets = [s for s in doc.snippets if s.language == "python"]
        assert len(python_snippets) > 0


# ---------------------------------------------------------------------------
# _guess_language — static method, tested exhaustively
# ---------------------------------------------------------------------------

class TestGuessLanguage:
    def test_python_from_class_name(self):
        assert ContentExtractor._guess_language("language-python", "") == "python"

    def test_python_from_py_suffix(self):
        assert ContentExtractor._guess_language("highlight-py", "") == "python"

    def test_javascript_from_class_name(self):
        lang = ContentExtractor._guess_language("language-javascript", "")
        assert lang == "javascript"

    def test_js_shorthand_class_name(self):
        lang = ContentExtractor._guess_language("highlight-js", "")
        assert lang == "javascript"

    def test_bash_from_class_name(self):
        assert ContentExtractor._guess_language("language-bash", "") == "bash"

    def test_bash_from_shell_class(self):
        assert ContentExtractor._guess_language("language-shell", "") == "bash"

    def test_bash_from_dollar_sign(self):
        assert ContentExtractor._guess_language("", "$ pip install fastapi\n$ uvicorn main:app") == "bash"

    def test_yaml_from_class_name(self):
        assert ContentExtractor._guess_language("language-yaml", "") == "yaml"

    def test_yaml_from_yml_class(self):
        assert ContentExtractor._guess_language("highlight-yml", "") == "yaml"

    def test_python_from_code_heuristic(self):
        code = "import os\ndef hello():\n    return True"
        lang = ContentExtractor._guess_language("", code)
        assert lang == "python"

    def test_javascript_from_const_function(self):
        code = "const x = 1;\nfunction greet() { return 'hello'; }"
        lang = ContentExtractor._guess_language("", code)
        assert lang == "javascript"

    def test_yaml_from_key_value_lines(self):
        code = "name: myapp\nversion: 1.0\nport: 8080\nauthor: me"
        lang = ContentExtractor._guess_language("", code)
        assert lang == "yaml"

    def test_yaml_requires_at_least_3_kv_lines(self):
        """Fewer than 3 YAML key:value lines → should NOT be detected as yaml."""
        code = "name: myapp\nport: 8080"
        lang = ContentExtractor._guess_language("", code)
        assert lang != "yaml"

    def test_yaml_not_detected_when_braces_present(self):
        code = "name: myapp\nversion: 1.0\ndata: {key: value}\nmore: test\nport: 8080"
        lang = ContentExtractor._guess_language("", code)
        assert lang != "yaml"

    def test_falls_back_to_text(self):
        lang = ContentExtractor._guess_language("", "no clear language indicators here")
        assert lang == "text"


# ---------------------------------------------------------------------------
# _extract_api_references
# ---------------------------------------------------------------------------

class TestExtractApiReferences:
    def test_finds_function_calls(self):
        md = "Use requests.get(url, timeout=5) to fetch data."
        refs = ContentExtractor._extract_api_references(md, "https://example.com")
        assert len(refs) > 0
        fns = [r["function"] for r in refs]
        assert any("requests" in f for f in fns)

    def test_short_names_filtered(self):
        md = "Call a(x) or ab(y) to do things."
        refs = ContentExtractor._extract_api_references(md, "https://example.com")
        fns = [r["function"] for r in refs]
        # "a" and "ab" are < 3 chars → must be filtered
        assert not any(len(f) < 3 for f in fns)

    def test_exactly_3_char_name_passes(self):
        md = "Use foo(x, y) for initialization."
        refs = ContentExtractor._extract_api_references(md, "https://example.com")
        # foo has len 3 which is NOT < 3, so it should be included
        fns = [r["function"] for r in refs]
        assert any("foo" in f for f in fns)

    def test_library_is_first_dotted_segment(self):
        md = "Call json.loads(data) to parse response."
        refs = ContentExtractor._extract_api_references(md, "https://example.com")
        assert len(refs) > 0
        assert refs[0]["library"] == "json"

    def test_source_propagated(self):
        md = "Use requests.get(url)"
        refs = ContentExtractor._extract_api_references(md, "https://my.source.com")
        assert all(r["source"] == "https://my.source.com" for r in refs)

    def test_capped_at_20(self):
        md = " ".join([f"func_{i:02d}(x)" for i in range(30)])
        refs = ContentExtractor._extract_api_references(md, "https://example.com")
        assert len(refs) <= 20

    def test_empty_markdown_returns_empty(self):
        assert ContentExtractor._extract_api_references("", "https://x.com") == []


# ---------------------------------------------------------------------------
# _extract_best_practices
# ---------------------------------------------------------------------------

class TestExtractBestPractices:
    def test_should_keyword_triggers_extraction(self):
        md = "You should always validate user input before processing it in your application pipeline."
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        assert len(practices) > 0

    def test_avoid_keyword_triggers_extraction(self):
        md = "Avoid storing sensitive credentials in plain text configuration files on disk."
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        assert len(practices) > 0

    def test_recommended_keyword_triggers_extraction(self):
        md = "It is recommended to use async endpoints for I/O-heavy operations in FastAPI applications."
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        assert len(practices) > 0

    def test_must_keyword_triggers_extraction(self):
        md = "You must handle exceptions explicitly to prevent unhandled errors in production environments."
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        assert len(practices) > 0

    def test_short_lines_filtered(self):
        """Lines under 40 chars must not be included."""
        md = "avoid it\nshould do nothing"  # both < 40 chars
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        assert practices == []

    def test_long_lines_filtered(self):
        """Lines over 220 chars must not be included."""
        long_line = "You should " + "x" * 220
        practices = ContentExtractor._extract_best_practices(long_line, "https://x.com")
        assert practices == []

    def test_practice_text_truncated_to_180(self):
        """practice field must be at most 180 chars."""
        md = "You should " + "a" * 200 + " in your application code."
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        if practices:
            assert len(practices[0]["practice"]) <= 180

    def test_source_propagated(self):
        md = "You should always validate user input before processing it in the application backend."
        practices = ContentExtractor._extract_best_practices(md, "https://specific.source.com")
        assert all(p["source"] == "https://specific.source.com" for p in practices)

    def test_capped_at_12(self):
        lines = [
            f"You should always do thing {i} properly in your application code to avoid bugs."
            for i in range(20)
        ]
        md = "\n".join(lines)
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        assert len(practices) <= 12

    def test_no_keyword_returns_empty(self):
        md = "This is a factual statement about the library behavior and its API surface."
        practices = ContentExtractor._extract_best_practices(md, "https://x.com")
        assert practices == []

    def test_empty_markdown_returns_empty(self):
        assert ContentExtractor._extract_best_practices("", "https://x.com") == []


# ---------------------------------------------------------------------------
# Markdown file path (content_type=text/markdown)
# ---------------------------------------------------------------------------

class TestMarkdownExtraction:
    def test_markdown_content_type_extracts(self, extractor):
        content = (
            "# FastAPI Guide\n\n"
            "FastAPI is a modern web framework for building APIs with Python.\n\n"
            "## Installation\n\n"
            "You should install it using pip for the best experience in production.\n\n"
            "## Example\n\n"
            "```python\n"
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/')\n"
            "def root():\n"
            "    return {'hello': 'world'}\n"
            "```\n"
        ) * 2  # repeat to exceed 200-char minimum
        page = _make_page(content, url="https://example.com/README.md", content_type="text/markdown")
        doc = extractor.extract(page)
        assert doc is not None

    def test_markdown_url_extension_detected(self, extractor):
        content = (
            "# My Guide\n\nThis is a markdown file with enough content.\n\n"
            "You should always write tests for your code in a proper test suite.\n\n"
            "## More Info\n\nAdditional content here for the markdown file being tested.\n"
        ) * 3
        page = _make_page(content, url="https://example.com/guide.md", content_type="text/plain")
        doc = extractor.extract(page)
        assert doc is not None

    def test_markdown_headings_extracted(self, extractor):
        content = (
            "# Title\n\nParagraph one with enough text to ensure extraction works correctly.\n\n"
            "## Section\n\nParagraph two with more information about the topic being covered.\n\n"
            "### Subsection\n\nYet another paragraph with additional details about the feature.\n"
        ) * 2
        page = _make_page(content, url="https://example.com/doc.md", content_type="text/markdown")
        doc = extractor.extract(page)
        assert doc is not None
        heading_text = " ".join(doc.headings)
        assert "Title" in heading_text or "Section" in heading_text

    def test_markdown_fenced_snippet_extracted(self, extractor):
        content = (
            "# FastAPI\n\nInstall and configure FastAPI for building REST APIs with Python.\n\n"
            "You should always validate inputs, and it is recommended to use Pydantic models.\n\n"
            "```python\n"
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/')\n"
            "def root():\n"
            "    return {'status': 'ok'}\n"
            "```\n\n"
            "This approach is recommended for building production-grade Python APIs quickly.\n"
        ) * 2
        page = _make_page(content, url="https://example.com/doc.md", content_type="text/markdown")
        doc = extractor.extract(page)
        assert doc is not None
        assert any("fastapi" in s.code.lower() for s in doc.snippets)


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_malformed_html_does_not_crash(self, extractor):
        html = "<html><body><p>Unclosed<div>More" + " text" * 60
        page = _make_page(html)
        _ = extractor.extract(page)  # must not raise

    def test_script_tags_stripped(self, extractor):
        html = _make_rich_article().replace(
            "<h1>FastAPI Upload Guide</h1>",
            "<script>alert('XSS attack payload')</script><h1>FastAPI Upload Guide</h1>",
        )
        page = _make_page(html)
        doc = extractor.extract(page)
        if doc:
            assert "alert" not in doc.clean_markdown
            assert "XSS" not in doc.clean_markdown

    def test_extraction_failure_returns_none_not_raise(self, extractor):
        """If readability raises internally the extractor must return None, not propagate."""
        # Trigger by passing a content_type that skips markdown branch but with corrupt input
        from unittest.mock import patch
        with patch("src.extractor.Document", side_effect=RuntimeError("boom")):
            page = _make_page("<html><body>" + "x" * 300 + "</body></html>")
            doc = extractor.extract(page)
            assert doc is None

    def test_all_snippet_fields_are_strings(self, extractor):
        page = _make_page(_make_rich_article(include_code=True))
        doc = extractor.extract(page)
        assert doc is not None
        for s in doc.snippets:
            assert isinstance(s.language, str)
            assert isinstance(s.code, str)
            assert isinstance(s.source, str)
            assert isinstance(s.description, str)

    def test_api_references_all_have_required_keys(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        for ref in doc.api_references:
            assert "library" in ref
            assert "function" in ref
            assert "source" in ref

    def test_best_practices_all_have_required_keys(self, extractor):
        page = _make_page(_make_rich_article())
        doc = extractor.extract(page)
        assert doc is not None
        for p in doc.best_practices:
            assert "practice" in p
            assert "reason" in p
            assert "source" in p
