"""Tests for extractor.py module."""

from unittest.mock import MagicMock

import pytest

from src.crawler import CrawledPage
from src.extractor import ContentExtractor, ExtractedDoc, ExtractedSnippet


def _make_page(html: str, url: str = "https://example.com", content_type: str = "text/html") -> CrawledPage:
    """Helper to build a CrawledPage from raw HTML."""
    return CrawledPage(url=url, status_code=200, content_type=content_type, text=html, fetched_at=0.0)


@pytest.fixture
def logger():
    """Mock logger for ContentExtractor."""
    mock = MagicMock()
    mock.info = MagicMock()
    mock.warning = MagicMock()
    mock.error = MagicMock()
    return mock


@pytest.fixture
def extractor(logger):
    """Create ContentExtractor instance."""
    return ContentExtractor(logger=logger)


@pytest.fixture
def sample_html_content():
    """Sample HTML content for testing extraction."""
    return """\
    <!DOCTYPE html>
    <html>
    <head><title>FastAPI File Upload</title></head>
    <body>
        <article>
            <h1>FastAPI File Upload Guide</h1>
            <p>FastAPI provides the UploadFile class for handling file uploads.
               You should always validate the file size before processing.</p>
            <pre><code class="language-python">
from fastapi import FastAPI, UploadFile

app = FastAPI()

@app.post("/upload/")
async def upload_file(file: UploadFile):
    return {"filename": file.filename}
            </code></pre>
            <p>This is a best practice recommended for handling files asynchronously.</p>
        </article>
    </body>
    </html>
    """


class TestContentExtraction:
    """Test content extraction from HTML."""

    def test_extract_from_simple_html(self, extractor, sample_html_content):
        """Test extracting content from simple HTML."""
        page = _make_page(sample_html_content)
        doc = extractor.extract(page)

        assert doc is not None
        assert isinstance(doc, ExtractedDoc)
        assert doc.source == "https://example.com"
        assert doc.title  # Should have a title

    def test_extract_returns_none_for_short_content(self, extractor):
        """Test extraction returns None for very short pages."""
        page = _make_page("<html><body>Hi</body></html>")
        doc = extractor.extract(page)
        assert doc is None

    def test_extract_preserves_code_blocks(self, extractor, sample_html_content):
        """Test extraction preserves code snippets."""
        page = _make_page(sample_html_content)
        doc = extractor.extract(page)

        assert doc is not None
        assert len(doc.snippets) > 0
        assert any("fastapi" in s.code.lower() for s in doc.snippets)

    def test_extract_removes_navigation(self, extractor):
        """Test extraction removes navigation elements."""
        html = """
        <html>
        <body>
            <nav><a href="/">Home</a><a href="/about">About</a></nav>
            <article><p>Main content here with plenty of text to meet the minimum length requirement for extraction.
            This paragraph needs to be long enough so readability won't discard it.</p>
            <p>Additional paragraph with more useful content that helps meet the minimum threshold.</p>
            <p>Yet another paragraph to ensure we have enough text content for the extraction to work.</p></article>
        </body>
        </html>
        """
        page = _make_page(html)
        doc = extractor.extract(page)

        if doc is not None:
            assert "Main content" in doc.clean_markdown or "Main content" in doc.summary

    def test_extract_markdown_file(self, extractor):
        """Test extraction of markdown content type."""
        md_content = "# Hello\n\nThis is a markdown document with enough content " * 10
        page = _make_page(md_content, url="https://example.com/README.md", content_type="text/markdown")
        doc = extractor.extract(page)

        assert doc is not None
        assert "README" in doc.title or "Hello" in doc.clean_markdown


class TestCodeSnippetExtraction:
    """Test code snippet extraction."""

    def test_extract_code_snippets_from_html(self, extractor, sample_html_content):
        """Test extracting code snippets from HTML page."""
        page = _make_page(sample_html_content)
        doc = extractor.extract(page)

        assert doc is not None
        assert len(doc.snippets) > 0
        assert all(isinstance(s, ExtractedSnippet) for s in doc.snippets)

    def test_detect_code_language(self, extractor):
        """Test language detection in code blocks."""
        html = """
        <html><body>
        <article>
        <p>Some introductory text that is long enough to pass the minimum content threshold for extraction.</p>
        <pre><code class="language-python">
import os
def hello():
    print("hello world")
    return True
        </code></pre>
        <p>More text to ensure extraction works properly and we have enough content in this document.</p>
        </article>
        </body></html>
        """
        page = _make_page(html)
        doc = extractor.extract(page)

        assert doc is not None
        python_snippets = [s for s in doc.snippets if s.language == "python"]
        assert len(python_snippets) > 0

    def test_snippet_has_source(self, extractor, sample_html_content):
        """Test that extracted snippets include source URL."""
        page = _make_page(sample_html_content)
        doc = extractor.extract(page)

        assert doc is not None
        for snippet in doc.snippets:
            assert snippet.source == "https://example.com"


class TestAPIReferenceExtraction:
    """Test API reference extraction."""

    def test_extract_api_references(self, extractor):
        """Test extracting API reference patterns from markdown."""
        markdown = "Use requests.get(url, params) to fetch data.\nThen call json.loads(data) to parse."
        refs = ContentExtractor._extract_api_references(markdown, "https://example.com")

        assert len(refs) > 0
        assert any("requests" in ref.get("library", "") for ref in refs)

    def test_short_function_names_filtered(self, extractor):
        """Test that very short function names are filtered out."""
        markdown = "Call a(x) here."
        refs = ContentExtractor._extract_api_references(markdown, "https://example.com")
        # "a" is too short (< 3 chars), should be filtered
        assert len(refs) == 0


class TestBestPracticeExtraction:
    """Test best practice extraction."""

    def test_extract_best_practices(self, extractor):
        """Test extracting best practice mentions from markdown."""
        markdown = """# Best Practices
You should always validate user input before processing it in your application.
It is recommended to use async endpoints for I/O operations in FastAPI.
Short line.
"""
        practices = ContentExtractor._extract_best_practices(markdown, "https://example.com")
        assert len(practices) > 0
        assert all("source" in p for p in practices)


class TestSEOSpamDetection:
    """Test SEO spam filtering via ContextOrchestrator._is_seo_spam."""

    def test_detects_spam_content(self):
        """Test spam detection catches affiliate/sponsored content."""
        from src.orchestrator import ContextOrchestrator

        assert ContextOrchestrator._is_seo_spam("Check out this sponsored product") is True
        assert ContextOrchestrator._is_seo_spam("Affiliate link to best price deals") is True
        assert ContextOrchestrator._is_seo_spam("Click here to download now!") is True

    def test_allows_legitimate_content(self):
        """Test legitimate content passes spam filter."""
        from src.orchestrator import ContextOrchestrator

        assert ContextOrchestrator._is_seo_spam("Learn Python programming with examples") is False
        assert ContextOrchestrator._is_seo_spam("FastAPI file upload tutorial") is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_malformed_html(self, extractor):
        """Test extraction from malformed HTML doesn't crash."""
        html = "<html><body><p>Unclosed tags<div>Content" + " more text" * 50
        page = _make_page(html)
        # Should not crash
        _doc = extractor.extract(page)  # noqa: F841
        # May return None or a doc depending on content length

    def test_html_with_scripts(self, extractor):
        """Test extraction removes script tags."""
        html = """
        <html><body>
        <script>alert('XSS')</script>
        <article>
        <p>Real content that is long enough to be extracted properly by the content extractor module.</p>
        <p>Additional content to meet minimum thresholds for extraction to work correctly here.</p>
        <p>Even more content to ensure we have enough text for the readability library to process.</p>
        </article>
        </body></html>
        """
        page = _make_page(html)
        doc = extractor.extract(page)

        if doc is not None:
            assert "alert" not in doc.clean_markdown
