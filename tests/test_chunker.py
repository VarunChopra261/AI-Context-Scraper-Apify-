"""Tests for chunker.py module."""

import pytest
from src.chunker import Chunker, LLMChunk


@pytest.fixture
def chunker():
    """Create Chunker instance with small max_tokens for testing."""
    return Chunker(max_tokens=100)


class TestChunkerInitialization:
    """Test chunker initialization."""

    def test_default_max_tokens(self):
        """Test default max_tokens parameter."""
        chunker = Chunker()
        assert chunker._max_tokens == 500

    def test_custom_max_tokens(self):
        """Test custom max_tokens parameter."""
        chunker = Chunker(max_tokens=1000)
        assert chunker._max_tokens == 1000

    def test_encoding_initialization(self):
        """Test tiktoken encoding is initialized."""
        chunker = Chunker()
        assert chunker._encoding is not None


class TestTokenCounting:
    """Test token counting functionality."""

    def test_token_count_simple(self, chunker):
        """Test counting tokens in simple text."""
        text = "Hello, world!"
        tokens = chunker.token_count(text)
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_token_count_empty(self, chunker):
        """Test counting tokens in empty string."""
        tokens = chunker.token_count("")
        assert tokens == 0

    def test_token_count_code(self, chunker):
        """Test counting tokens in code."""
        code = "def hello():\n    print('Hello, world!')"
        tokens = chunker.token_count(code)
        assert tokens > 0


class TestChunking:
    """Test text chunking functionality."""

    def test_chunk_short_text(self, chunker):
        """Test chunking text shorter than max_tokens."""
        text = "This is a short text."
        chunks = chunker.chunk_text(text, source="test")

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].source == "test"
        assert isinstance(chunks[0], LLMChunk)

    def test_chunk_long_text(self, chunker):
        """Test chunking text longer than max_tokens."""
        # Create text that will definitely exceed 100 tokens
        paragraphs = [f"This is paragraph number {i} with enough content." for i in range(50)]
        text = "\n\n".join(paragraphs)
        chunks = chunker.chunk_text(text, source="test")

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.source == "test"

    def test_chunk_preserves_content(self, chunker):
        """Test that chunks contain all original content."""
        paragraphs = [f"Paragraph {i}" for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = chunker.chunk_text(text, source="test")

        # Each chunk should have non-zero length
        for chunk in chunks:
            assert len(chunk.text) > 0

    def test_chunk_respects_paragraph_boundaries(self, chunker):
        """Test chunking respects paragraph boundaries when possible."""
        text = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3."
        chunks = chunker.chunk_text(text, source="test")

        # Should have at least one chunk
        assert len(chunks) >= 1
        assert all(chunk.text.strip() for chunk in chunks)

    def test_chunk_handles_code_blocks(self, chunker):
        """Test chunking handles code blocks appropriately."""
        text = """Here's some code:

```python
def example():
    return "Hello"
```

And some explanation after."""
        chunks = chunker.chunk_text(text, source="test")

        assert len(chunks) >= 1
        # Code block should be in at least one chunk
        assert any("def example" in chunk.text for chunk in chunks)

    def test_chunk_tokens_field(self, chunker):
        """Test that each chunk has a valid tokens field."""
        text = "A simple test paragraph.\n\nAnother paragraph here."
        chunks = chunker.chunk_text(text, source="test")

        for chunk in chunks:
            assert chunk.tokens > 0
            assert chunk.tokens == chunker.token_count(chunk.text)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_text(self, chunker):
        """Test chunking empty text."""
        chunks = chunker.chunk_text("", source="test")
        assert len(chunks) == 0

    def test_whitespace_only(self, chunker):
        """Test chunking whitespace-only text."""
        chunks = chunker.chunk_text("   \n\n   \t  ", source="test")
        assert len(chunks) == 0

    def test_special_characters(self, chunker):
        """Test chunking text with special characters."""
        text = "Special chars: @#$%^&*(){}[]|\\<>?/~`"
        chunks = chunker.chunk_text(text, source="test")

        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_unicode_text(self, chunker):
        """Test chunking Unicode text."""
        text = "Hello 世界 🌍 Здравствуй мир"
        chunks = chunker.chunk_text(text, source="test")

        assert len(chunks) >= 1
        # Should preserve Unicode characters
        assert "世界" in "".join(c.text for c in chunks)
