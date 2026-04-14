"""Stress tests for llm_synthesizer.py — every assertion is load-bearing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm_synthesizer import MAX_CONTEXT_CHARS, SYSTEM_PROMPT, LLMResponse, LLMSynthesizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logger():
    mock = MagicMock()
    mock.info = MagicMock()
    mock.warning = MagicMock()
    mock.error = MagicMock()
    return mock


def _make_synthesizer(**kwargs):
    defaults = dict(
        logger=_make_logger(),
        api_key="sk-or-v1-test-key-only",
        model="test/model",
        timeout=10.0,
        max_retries=1,
    )
    defaults.update(kwargs)
    return LLMSynthesizer(**defaults)


def _full_result():
    """Produce a realistic result dict with all context fields populated."""
    return {
        "task": "Upload a file to S3 using FastAPI",
        "relevant_context": [
            {
                "source": "https://fastapi.tiangolo.com/tutorial/",
                "bucket": "critical",
                "why_it_matters": "Core UploadFile docs",
                "key_detail": "Use UploadFile with async read()",
            },
            {
                "source": "https://boto3.amazonaws.com",
                "bucket": "helpful",
                "why_it_matters": "S3 client API",
                "key_detail": "boto3.client('s3').upload_fileobj()",
            },
        ],
        "open_questions": ["What is the max file size?", "Is multipart supported?"],
        "recommended_next_context": ["Check boto3 docs for multipart."],
        "context": {
            "concepts": [
                {"title": "FastAPI Uploads", "summary": "UploadFile handles async file uploads.", "source": "https://fastapi.tiangolo.com"},
                {"title": "Boto3 S3", "summary": "AWS SDK for S3 operations.", "source": "https://boto3.amazonaws.com"},
            ],
            "code_snippets": [
                {
                    "language": "python",
                    "code": "from fastapi import UploadFile\n@app.post('/upload/')\nasync def upload(f: UploadFile):\n    contents = await f.read()\n    return {'name': f.filename}",
                    "description": "FastAPI upload endpoint",
                    "source": "https://fastapi.tiangolo.com",
                    "bucket": "critical",
                }
            ],
            "api_references": [
                {"library": "fastapi", "function": "UploadFile()", "description": "File upload handler", "source": "https://fastapi.tiangolo.com"},
            ],
            "best_practices": [
                {"practice": "Always validate file size before processing.", "reason": "Prevents DoS.", "source": "https://example.com"},
            ],
            "implementation_patterns": [
                {
                    "pattern_type": "ASYNC_CONCURRENCY",
                    "description": "Async I/O",
                    "code_snippet": "async def f(): pass",
                    "source": "https://example.com",
                    "confidence": 0.9,
                }
            ],
            "stackoverflow_answers": [
                {
                    "question_title": "How to upload to S3 with FastAPI?",
                    "question_url": "https://stackoverflow.com/q/99999",
                    "answer_body": "Use UploadFile with boto3.upload_fileobj.",
                    "score": 55,
                }
            ],
            "llm_chunks": [
                {"text": "FastAPI UploadFile reads bytes asynchronously.", "tokens": 8, "source": "https://fastapi.tiangolo.com"},
            ],
        },
    }


def _mock_successful_client(content="Synthesized content here."):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "model": "test/model",
        "usage": {"prompt_tokens": 300, "completion_tokens": 100, "total_tokens": 400},
    }
    instance = AsyncMock()
    instance.post = AsyncMock(return_value=mock_response)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    return instance


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------

class TestLLMResponse:
    def test_all_fields(self):
        r = LLMResponse(content="C", model="M", prompt_tokens=1, completion_tokens=2, total_tokens=3, finish_reason="stop")
        assert r.content == "C"
        assert r.model == "M"
        assert r.prompt_tokens == 1
        assert r.completion_tokens == 2
        assert r.total_tokens == 3
        assert r.finish_reason == "stop"


# ---------------------------------------------------------------------------
# LLMSynthesizer initialization
# ---------------------------------------------------------------------------

class TestInit:
    def test_defaults(self):
        s = LLMSynthesizer(logger=_make_logger(), api_key="key")
        assert s._model == "nvidia/nemotron-3-super-120b-a12b:free"
        assert s._timeout == 60.0
        assert s._max_retries == 2

    def test_custom_model(self):
        s = LLMSynthesizer(logger=_make_logger(), api_key="key", model="custom/model-x")
        assert s._model == "custom/model-x"

    def test_custom_timeout_and_retries(self):
        s = LLMSynthesizer(logger=_make_logger(), api_key="key", timeout=30.0, max_retries=5)
        assert s._timeout == 30.0
        assert s._max_retries == 5


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_non_trivially_long(self):
        assert len(SYSTEM_PROMPT) > 200

    def test_contains_relevant_context_keyword(self):
        assert "relevant-context" in SYSTEM_PROMPT.lower()

    def test_contains_coding_guidance(self):
        assert "coding" in SYSTEM_PROMPT.lower() or "code" in SYSTEM_PROMPT.lower()

    def test_contains_all_required_sections(self):
        for section in ("Relevant Context", "Implementation", "Open Questions", "Recommended Next Context"):
            assert section in SYSTEM_PROMPT, f"Missing section: {section}"

    def test_task_restatement_in_prompt(self):
        assert "Task" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# build_context_prompt — content assertions
# ---------------------------------------------------------------------------

class TestBuildContextPrompt:
    def test_task_in_prompt(self):
        s = _make_synthesizer()
        result = _full_result()
        prompt = s.build_context_prompt("My developer task XYZ", result)
        assert "My developer task XYZ" in prompt

    def test_concepts_in_prompt(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "FastAPI Uploads" in prompt
        assert "UploadFile handles async file uploads." in prompt

    def test_code_snippet_in_prompt(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "from fastapi import UploadFile" in prompt
        assert "```python" in prompt

    def test_critical_bucket_label_applied(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "[CRITICAL]" in prompt

    def test_api_references_in_prompt(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "UploadFile()" in prompt

    def test_best_practices_in_prompt(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "validate file size" in prompt

    def test_implementation_patterns_in_prompt(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "ASYNC_CONCURRENCY" in prompt

    def test_stackoverflow_in_prompt(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "How to upload to S3 with FastAPI?" in prompt
        assert "stackoverflow.com" in prompt

    def test_relevant_context_section_present(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "Pre-Ranked Context" in prompt
        assert "[CRITICAL] https://fastapi.tiangolo.com/tutorial/: Core UploadFile docs" in prompt

    def test_open_questions_section_present(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "Known Gaps" in prompt
        assert "What is the max file size?" in prompt

    def test_final_synthesis_instruction_appended(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("task", _full_result())
        assert "relevant-context skill template" in prompt
        assert "Task restatement" in prompt

    def test_empty_result_does_not_crash(self):
        s = _make_synthesizer()
        prompt = s.build_context_prompt("test task", {})
        assert "test task" in prompt
        assert len(prompt) > 10

    def test_partial_result_does_not_crash(self):
        s = _make_synthesizer()
        partial = {"context": {"concepts": [{"title": "X", "summary": "Y", "source": "url"}]}}
        prompt = s.build_context_prompt("task", partial)
        assert "X" in prompt


# ---------------------------------------------------------------------------
# build_context_prompt — truncation
# ---------------------------------------------------------------------------

class TestPromptTruncation:
    def test_huge_context_truncated_to_max_chars(self):
        s = _make_synthesizer()
        big = {
            "context": {
                "concepts": [
                    {"title": f"C{i}", "summary": "x" * 5000, "source": f"https://x.com/{i}"}
                    for i in range(30)
                ],
                "code_snippets": [],
                "api_references": [],
                "best_practices": [],
                "implementation_patterns": [],
                "stackoverflow_answers": [],
                "llm_chunks": [],
            }
        }
        prompt = s.build_context_prompt("task", big)
        # The full_prompt before instruction is at most MAX_CONTEXT_CHARS
        # After truncation, the whole prompt is ≤ MAX_CONTEXT_CHARS + instruction overhead
        assert len(prompt) < MAX_CONTEXT_CHARS + 600

    def test_truncation_marker_present_in_long_prompt(self):
        s = _make_synthesizer()
        big = {
            "context": {
                "concepts": [
                    {"title": f"C{i}", "summary": "x" * 5000, "source": f"https://x.com/{i}"}
                    for i in range(30)
                ],
            }
        }
        prompt = s.build_context_prompt("task", big)
        assert "[Context truncated for length]" in prompt

    def test_concepts_limited_to_10_in_prompt(self):
        s = _make_synthesizer()
        result = {
            "context": {
                "concepts": [
                    {"title": f"Concept {i}", "summary": f"Sum {i}", "source": f"https://x.com/{i}"}
                    for i in range(20)
                ],
            }
        }
        prompt = s.build_context_prompt("task", result)
        assert "Concept 9" in prompt
        assert "Concept 10" not in prompt

    def test_snippets_limited_to_6_in_prompt(self):
        s = _make_synthesizer()
        result = {
            "context": {
                "code_snippets": [
                    {"language": "python", "code": f"code_{i}", "description": f"Snippet {i}", "source": "url"}
                    for i in range(20)
                ],
            }
        }
        prompt = s.build_context_prompt("task", result)
        assert "Snippet 5" in prompt
        assert "Snippet 6" not in prompt

    def test_so_answers_limited_to_3_in_prompt(self):
        s = _make_synthesizer()
        result = {
            "context": {
                "stackoverflow_answers": [
                    {"question_title": f"Q{i}", "question_url": f"url{i}", "answer_body": f"A{i}", "score": i}
                    for i in range(10)
                ],
            }
        }
        prompt = s.build_context_prompt("task", result)
        assert "Q2" in prompt
        assert "Q3" not in prompt

    def test_relevant_items_limited_to_15(self):
        s = _make_synthesizer()
        result = {
            "relevant_context": [
                {"source": f"url{i}", "bucket": "critical", "why_it_matters": f"reason{i}", "key_detail": f"detail{i}"}
                for i in range(20)
            ],
            "context": {},
        }
        prompt = s.build_context_prompt("task", result)
        assert "reason14" in prompt
        assert "reason15" not in prompt


# ---------------------------------------------------------------------------
# synthesize() — error handling
# ---------------------------------------------------------------------------

class TestSynthesizeErrorHandling:
    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        import httpx
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_500(self):
        import httpx
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock(status_code=500)
            instance = AsyncMock()
            instance.post = AsyncMock(
                side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=mock_resp)
            )
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_choices(self):
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"choices": [], "usage": {}}
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_response_parsed_correctly(self):
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            MockClient.return_value = _mock_successful_client("Here is your guidance.")
            result = await s.synthesize("task", {})
            assert result is not None
            assert result.content == "Here is your guidance."
            assert result.total_tokens == 400
            assert result.finish_reason == "stop"
            assert result.prompt_tokens == 300
            assert result.completion_tokens == 100

    @pytest.mark.asyncio
    async def test_model_field_from_response(self):
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            MockClient.return_value = _mock_successful_client()
            result = await s.synthesize("task", {})
            assert result is not None
            assert result.model == "test/model"


# ---------------------------------------------------------------------------
# synthesize() — retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self):
        """On a 429, the synthesizer should retry and eventually succeed."""
        import httpx
        s = _make_synthesizer(max_retries=1)

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status = MagicMock()
        success_response.json.return_value = {
            "choices": [{"message": {"content": "Retry worked!"}, "finish_reason": "stop"}],
            "model": "test/model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: simulate 429 response
                r = MagicMock()
                r.status_code = 429
                r.raise_for_status = MagicMock()
                r.json.return_value = {}
                return r
            return success_response

        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            with patch("src.llm_synthesizer.asyncio.sleep", new_callable=AsyncMock):
                instance = AsyncMock()
                instance.post = mock_post
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance
                result = await s.synthesize("task", {})
                # Should have retried and succeeded
                assert result is not None
                assert result.content == "Retry worked!"
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries_returns_none(self):
        """After max_retries+1 attempts all fail → None returned."""
        import httpx
        s = _make_synthesizer(max_retries=2)

        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_exception_returns_none_after_retries(self):
        s = _make_synthesizer(max_retries=1)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(side_effect=ValueError("unexpected"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is None


# ---------------------------------------------------------------------------
# synthesize() — missing/partial usage fields
# ---------------------------------------------------------------------------

class TestPartialResponseHandling:
    @pytest.mark.asyncio
    async def test_missing_usage_field_defaults_to_zero(self):
        """When 'usage' is absent from the API response, token counts default to 0."""
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "model": "test/model",
                # 'usage' key deliberately absent
            }
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is not None
            assert result.total_tokens == 0
            assert result.prompt_tokens == 0
            assert result.completion_tokens == 0

    @pytest.mark.asyncio
    async def test_missing_finish_reason_defaults(self):
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "OK"}}],  # no finish_reason
                "model": "test/model",
                "usage": {},
            }
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is not None
            assert result.finish_reason == "unknown"

    @pytest.mark.asyncio
    async def test_empty_content_still_returns_response(self):
        s = _make_synthesizer(max_retries=0)
        with patch("src.llm_synthesizer.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
                "model": "test/model",
                "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
            }
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance
            result = await s.synthesize("task", {})
            assert result is not None
            assert result.content == ""
