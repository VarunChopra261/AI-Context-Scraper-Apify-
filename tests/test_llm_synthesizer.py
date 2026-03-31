"""Tests for llm_synthesizer.py module."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.llm_synthesizer import LLMSynthesizer, LLMResponse, SYSTEM_PROMPT, MAX_CONTEXT_CHARS


@pytest.fixture
def logger():
    """Mock logger."""
    mock = MagicMock()
    mock.info = MagicMock()
    mock.warning = MagicMock()
    mock.error = MagicMock()
    return mock


@pytest.fixture
def synthesizer(logger):
    """Create LLMSynthesizer instance."""
    return LLMSynthesizer(
        logger=logger,
        api_key="sk-or-v1-test-key",
        model="nvidia/nemotron-3-super-120b-a12b:free",
        timeout=10.0,
        max_retries=1,
    )


@pytest.fixture
def sample_result():
    """Sample result dictionary as produced by the formatter."""
    return {
        "task": "Test task",
        "relevant_context": [
            {
                "source": "https://fastapi.tiangolo.com/tutorial/",
                "bucket": "critical",
                "why_it_matters": "Core concepts",
                "key_detail": "FastAPI provides UploadFile"
            }
        ],
        "open_questions": ["Are there specific file size limits?"],
        "recommended_next_context": [],
        "context": {
            "concepts": [
                {
                    "title": "FastAPI File Uploads",
                    "summary": "FastAPI provides UploadFile for handling file uploads asynchronously.",
                    "source": "https://fastapi.tiangolo.com/tutorial/"
                }
            ],
            "code_snippets": [
                {
                    "language": "python",
                    "code": "from fastapi import UploadFile\n\n@app.post('/upload/')\nasync def upload(file: UploadFile):\n    return {'filename': file.filename}",
                    "description": "FastAPI file upload endpoint",
                    "source": "https://fastapi.tiangolo.com",
                    "bucket": "critical"
                }
            ],
            "api_references": [
                {
                    "library": "fastapi",
                    "function": "UploadFile()",
                    "description": "Handles file uploads",
                    "source": "https://fastapi.tiangolo.com"
                }
            ],
            "best_practices": [
                {
                    "practice": "Always validate file size before processing",
                    "reason": "Prevents DoS",
                    "source": "https://example.com"
                }
            ],
            "implementation_patterns": [
                {
                    "pattern_type": "ASYNC_CONCURRENCY",
                    "description": "Async file I/O pattern",
                    "code_snippet": "async def read_file(f): pass",
                    "source": "https://example.com",
                    "confidence": 0.85
                }
            ],
            "stackoverflow_answers": [
                {
                    "question_title": "How to upload files in FastAPI?",
                    "question_url": "https://stackoverflow.com/q/12345",
                    "answer_body": "Use UploadFile with the POST endpoint...",
                    "score": 42,
                    "accepted": True,
                    "tags": ["python", "fastapi"]
                }
            ],
            "llm_chunks": [
                {
                    "text": "FastAPI file upload tutorial content here.",
                    "tokens": 50,
                    "source": "https://fastapi.tiangolo.com"
                }
            ]
        }
    }


class TestPromptConstruction:
    """Test prompt building from context."""

    def test_build_includes_task(self, synthesizer, sample_result):
        """Test prompt includes the developer task."""
        prompt = synthesizer.build_context_prompt("Build a file upload endpoint", sample_result)
        assert "Build a file upload endpoint" in prompt

    def test_build_includes_concepts(self, synthesizer, sample_result):
        """Test prompt includes documentation concepts."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "FastAPI File Uploads" in prompt
        assert "UploadFile" in prompt

    def test_build_includes_code_snippets(self, synthesizer, sample_result):
        """Test prompt includes code snippets."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "from fastapi import UploadFile" in prompt
        assert "```python" in prompt
        # the critical bucket from sample_result should be applied
        assert "[CRITICAL]" in prompt

    def test_build_includes_api_references(self, synthesizer, sample_result):
        """Test prompt includes API references."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "UploadFile()" in prompt

    def test_build_includes_best_practices(self, synthesizer, sample_result):
        """Test prompt includes best practices."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "validate file size" in prompt

    def test_build_includes_patterns(self, synthesizer, sample_result):
        """Test prompt includes implementation patterns."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "ASYNC_CONCURRENCY" in prompt

    def test_build_includes_stackoverflow(self, synthesizer, sample_result):
        """Test prompt includes StackOverflow answers."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "How to upload files in FastAPI?" in prompt
        assert "stackoverflow.com" in prompt

    def test_build_includes_relevant_context(self, synthesizer, sample_result):
        """Test prompt includes pre-bucketized relevant context items."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "Pre-Ranked Context" in prompt
        assert "[CRITICAL] https://fastapi.tiangolo.com/tutorial/: Core concepts" in prompt

    def test_build_includes_open_questions(self, synthesizer, sample_result):
        """Test prompt surfaces known gaps and open questions."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "Known Gaps (from pipeline)" in prompt
        assert "Are there specific file size limits?" in prompt

    def test_build_includes_final_instruction(self, synthesizer, sample_result):
        """Test prompt ends with synthesis instruction."""
        prompt = synthesizer.build_context_prompt("test", sample_result)
        assert "relevant-context skill template" in prompt
        assert "Task restatement" in prompt

    def test_build_empty_context(self, synthesizer):
        """Test prompt with empty context."""
        prompt = synthesizer.build_context_prompt("test task", {})
        assert "test task" in prompt
        assert "relevant-context skill template" in prompt

    def test_build_truncates_long_context(self, synthesizer):
        """Test prompt truncation for very long context."""
        long_result = {"context": {
            "concepts": [
                {"title": f"Concept {i}", "summary": "x" * 5000, "source": f"https://example.com/{i}"}
                for i in range(20)
            ],
            "code_snippets": [],
            "api_references": [],
            "best_practices": [],
            "implementation_patterns": [],
            "stackoverflow_answers": [],
            "llm_chunks": [],
        }}
        prompt = synthesizer.build_context_prompt("test", long_result)
        assert len(prompt) < MAX_CONTEXT_CHARS + 500  # Some padding for final instruction


class TestContextTruncation:
    """Test that context items are limited."""

    def test_concepts_limited_to_10(self, synthesizer):
        """Test at most 10 concepts included."""
        result = {"context": {
            "concepts": [
                {"title": f"Concept {i}", "summary": f"Summary {i}", "source": f"https://example.com/{i}"}
                for i in range(30)
            ],
        }}
        prompt = synthesizer.build_context_prompt("test", result)
        assert "Concept 9" in prompt
        assert "Concept 10" not in prompt

    def test_snippets_limited_to_6(self, synthesizer):
        """Test at most 6 code snippets included."""
        result = {"context": {
            "code_snippets": [
                {"language": "python", "code": f"code_{i}", "description": f"Snippet {i}", "source": "url"}
                for i in range(20)
            ],
        }}
        prompt = synthesizer.build_context_prompt("test", result)
        assert "Snippet 5" in prompt
        assert "Snippet 6" not in prompt

    def test_so_answers_limited_to_3(self, synthesizer):
        """Test at most 3 stackoverflow answers included."""
        result = {"context": {
            "stackoverflow_answers": [
                {"question_title": f"Q{i}", "question_url": f"url{i}", "answer_body": f"A{i}", "score": i}
                for i in range(10)
            ],
        }}
        prompt = synthesizer.build_context_prompt("test", result)
        assert "Q2" in prompt
        assert "Q3" not in prompt


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_response_fields(self):
        """Test LLMResponse has all expected fields."""
        resp = LLMResponse(
            content="Hello",
            model="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            finish_reason="stop",
        )
        assert resp.content == "Hello"
        assert resp.model == "test-model"
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 50
        assert resp.total_tokens == 150
        assert resp.finish_reason == "stop"


class TestSynthesizeErrorHandling:
    """Test error handling in synthesize method."""

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self, synthesizer):
        """Test synthesize returns None when API times out."""
        import httpx

        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await synthesizer.synthesize("test task", {"concepts": []})
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self, synthesizer):
        """Test synthesize returns None on HTTP errors."""
        import httpx

        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_response = MagicMock(status_code=500)
            instance = AsyncMock()
            instance.post = AsyncMock(
                side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=mock_response)
            )
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await synthesizer.synthesize("test task", {"concepts": []})
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_choices(self, synthesizer):
        """Test synthesize returns None when API returns no choices."""
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"choices": [], "usage": {}}

            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await synthesizer.synthesize("test task", {"concepts": []})
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_response_parsing(self, synthesizer):
        """Test successful API response is parsed correctly."""
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {"content": "Here is your guidance..."},
                        "finish_reason": "stop",
                    }
                ],
                "model": "nvidia/nemotron-3-super-120b-a12b:free",
                "usage": {
                    "prompt_tokens": 500,
                    "completion_tokens": 200,
                    "total_tokens": 700,
                },
            }

            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await synthesizer.synthesize("test task", {"concepts": []})
            assert result is not None
            assert result.content == "Here is your guidance..."
            assert result.total_tokens == 700
            assert result.finish_reason == "stop"


class TestSystemPrompt:
    """Test system prompt configuration."""

    def test_system_prompt_is_defined(self):
        """Test system prompt constant is defined."""
        assert len(SYSTEM_PROMPT) > 100
        assert "relevant-context" in SYSTEM_PROMPT.lower()
        assert "coding" in SYSTEM_PROMPT.lower()

    def test_system_prompt_includes_structure_guidance(self):
        """Test system prompt tells LLM to use structured output."""
        assert "Relevant Context" in SYSTEM_PROMPT
        assert "Implementation" in SYSTEM_PROMPT
        assert "Open Questions" in SYSTEM_PROMPT
        assert "Recommended Next Context" in SYSTEM_PROMPT


class TestEdgeCases:
    """Test edge cases."""

    def test_synthesizer_creation_with_defaults(self, logger):
        """Test creating synthesizer with default params."""
        s = LLMSynthesizer(logger=logger, api_key="test-key")
        assert s._model == "nvidia/nemotron-3-super-120b-a12b:free"
        assert s._timeout == 60.0
        assert s._max_retries == 2

    def test_synthesizer_custom_model(self, logger):
        """Test creating synthesizer with custom model."""
        s = LLMSynthesizer(logger=logger, api_key="test", model="custom/model")
        assert s._model == "custom/model"

    def test_build_prompt_partial_context(self, synthesizer):
        """Test prompt building with only some context fields."""
        partial_result = {
            "context": {
                "concepts": [{"title": "Test", "summary": "Test summary", "source": "url"}],
                # Missing other fields
            }
        }
        prompt = synthesizer.build_context_prompt("test", partial_result)
        assert "Test" in prompt
        assert "test" in prompt
