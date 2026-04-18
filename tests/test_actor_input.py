"""Regression tests for input validation in __main__.py (ActorInput model)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# We test the Pydantic model directly, without needing Actor context
from src.__main__ import ActorInput


# ---------------------------------------------------------------------------
# Valid inputs
# ---------------------------------------------------------------------------

class TestActorInputValid:
    def test_minimal_valid_input(self):
        ai = ActorInput.model_validate({"task": "Build a FastAPI endpoint"})
        assert ai.task == "Build a FastAPI endpoint"
        assert ai.max_sources == 10
        assert ai.include_github is True
        assert ai.include_stackoverflow is True
        assert ai.enable_cache is True
        assert ai.chunk_size == 500

    def test_full_valid_input(self):
        ai = ActorInput.model_validate({
            "task": "Build a REST API with FastAPI",
            "max_sources": 20,
            "allowed_domains": ["docs.python.org"],
            "include_github": False,
            "include_github_code_search": False,
            "github_token": "gho_token123",
            "github_code_languages": ["python"],
            "max_code_snippets": 15,
            "include_stackoverflow": False,
            "enable_cache": False,
            "chunk_size": 750,
            "enable_llm_synthesis": False,
            "openrouter_api_key": "sk-or-v1-test",
            "openrouter_model": "nvidia/model:free",
        })
        assert ai.max_sources == 20
        assert ai.chunk_size == 750

    def test_max_sources_at_min_boundary(self):
        ai = ActorInput.model_validate({"task": "Task test", "max_sources": 3})
        assert ai.max_sources == 3

    def test_max_sources_at_max_boundary(self):
        ai = ActorInput.model_validate({"task": "Task test", "max_sources": 50})
        assert ai.max_sources == 50

    def test_chunk_size_at_min_boundary(self):
        ai = ActorInput.model_validate({"task": "Task test", "chunk_size": 100})
        assert ai.chunk_size == 100

    def test_chunk_size_at_max_boundary(self):
        ai = ActorInput.model_validate({"task": "Task test", "chunk_size": 2000})
        assert ai.chunk_size == 2000

    def test_max_code_snippets_at_min_boundary(self):
        ai = ActorInput.model_validate({"task": "Task test", "max_code_snippets": 1})
        assert ai.max_code_snippets == 1

    def test_max_code_snippets_at_max_boundary(self):
        ai = ActorInput.model_validate({"task": "Task test", "max_code_snippets": 100})
        assert ai.max_code_snippets == 100

    def test_optional_token_fields_default_none(self):
        ai = ActorInput.model_validate({"task": "Task"})
        assert ai.github_token is None
        assert ai.openrouter_api_key is None

    def test_github_code_languages_empty_by_default(self):
        ai = ActorInput.model_validate({"task": "Task"})
        assert ai.github_code_languages == []

    def test_allowed_domains_empty_by_default(self):
        ai = ActorInput.model_validate({"task": "Task"})
        assert ai.allowed_domains == []


# ---------------------------------------------------------------------------
# Missing / invalid required fields
# ---------------------------------------------------------------------------

class TestActorInputInvalid:
    def test_missing_task_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ActorInput.model_validate({})
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("task",) for e in errors)

    def test_empty_task_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": ""})

    def test_task_too_short_raises(self):
        """min_length=3 enforced."""
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "ab"})

    def test_max_sources_below_3_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "Valid task here", "max_sources": 2})

    def test_max_sources_above_50_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "Valid task here", "max_sources": 51})

    def test_max_sources_string_type_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "Valid task", "max_sources": "ten"})

    def test_chunk_size_below_100_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "Valid task here", "chunk_size": 99})

    def test_chunk_size_above_2000_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "Valid task here", "chunk_size": 2001})

    def test_max_code_snippets_zero_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "Valid task", "max_code_snippets": 0})

    def test_max_code_snippets_above_100_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": "Valid task", "max_code_snippets": 101})

    def test_include_github_must_be_bool(self):
        """Pydantic coerces strings to bool — "false" → False in lax mode."""
        # Just ensure validation doesn't raise for bool values
        ai = ActorInput.model_validate({"task": "Valid task", "include_github": False})
        assert ai.include_github is False

    def test_null_task_raises(self):
        with pytest.raises(ValidationError):
            ActorInput.model_validate({"task": None})


# ---------------------------------------------------------------------------
# Schema completeness
# ---------------------------------------------------------------------------

class TestActorInputSchemaCompleteness:
    def test_all_expected_fields_exist(self):
        ai = ActorInput.model_validate({"task": "Valid task test"})
        fields = ai.model_fields_set | set(ActorInput.model_fields.keys())
        expected = {
            "task", "max_sources", "allowed_domains", "include_github",
            "include_github_code_search", "github_token", "github_code_languages",
            "max_code_snippets", "include_stackoverflow", "enable_cache",
            "chunk_size", "enable_llm_synthesis", "openrouter_api_key", "openrouter_model",
        }
        assert expected.issubset(fields)

    def test_model_json_schema_is_valid(self):
        """model_json_schema() must succeed without raising."""
        schema = ActorInput.model_json_schema()
        assert "properties" in schema
        assert "task" in schema["properties"]

    def test_default_model_is_free_tier(self):
        ai = ActorInput.model_validate({"task": "Task"})
        assert "free" in ai.openrouter_model or "nemotron" in ai.openrouter_model
