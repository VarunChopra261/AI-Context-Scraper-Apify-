from __future__ import annotations

import os

from apify import Actor
from pydantic import BaseModel, Field, ValidationError

from .exceptions import InputValidationError, SecurityError
from .orchestrator import ContextOrchestrator
from .security import InputValidator


class ActorInput(BaseModel):
    task: str = Field(..., min_length=3, description="Coding task description")
    max_sources: int = Field(default=10, ge=3, le=50)
    allowed_domains: list[str] = Field(default_factory=list)
    include_github: bool = Field(default=True)
    include_github_code_search: bool = Field(default=True)
    github_token: str | None = Field(default=None)
    github_code_languages: list[str] = Field(default_factory=list)
    max_code_snippets: int = Field(default=20, ge=1, le=100)
    include_stackoverflow: bool = Field(default=True)
    enable_cache: bool = Field(default=True)
    chunk_size: int = Field(default=500, ge=100, le=2000)
    enable_llm_synthesis: bool = Field(default=True, description="Enable LLM-powered RAG synthesis")
    openrouter_api_key: str | None = Field(default=None, description="OpenRouter API key for LLM synthesis")
    openrouter_model: str = Field(default="arcee-ai/trinity-large-preview:free", description="OpenRouter model ID")


async def main() -> None:
    async with Actor:
        raw_input = await Actor.get_input() or {}
        try:
            actor_input = ActorInput.model_validate(raw_input)
        except ValidationError as exc:
            Actor.log.error("Invalid input", extra={"errors": exc.errors()})
            raise

        # Security validation
        try:
            validated_task = InputValidator.validate_task(actor_input.task)
            for domain in actor_input.allowed_domains:
                InputValidator.validate_domain(domain)
            config = {
                "max_sources": actor_input.max_sources,
                "chunk_size": actor_input.chunk_size,
                "allowed_domains": actor_input.allowed_domains,
            }
            InputValidator.validate_config(config)
        except SecurityError as exc:
            Actor.log.error("Security validation failed", extra={"error": str(exc)})
            raise InputValidationError(f"Security validation failed: {exc}") from exc

        Actor.log.info("Starting AI context compilation", extra={"task": validated_task})
        token = actor_input.github_token or os.getenv("GITHUB_TOKEN")
        openrouter_key = actor_input.openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        orchestrator = ContextOrchestrator(
            logger=Actor.log,
            github_token=token,
            enable_cache=actor_input.enable_cache,
            enable_stackoverflow=actor_input.include_stackoverflow,
            chunk_size=actor_input.chunk_size,
            enable_llm_synthesis=actor_input.enable_llm_synthesis,
            openrouter_api_key=openrouter_key,
            openrouter_model=actor_input.openrouter_model,
        )
        result = await orchestrator.run(
            task=validated_task,
            max_sources=actor_input.max_sources,
            allowed_domains=actor_input.allowed_domains,
            include_github=actor_input.include_github,
            include_github_code_search=actor_input.include_github_code_search,
            github_code_languages=actor_input.github_code_languages,
            max_code_snippets=actor_input.max_code_snippets,
            include_stackoverflow=actor_input.include_stackoverflow,
        )

        await Actor.push_data(result)
        ctx = result.get("context", {})
        Actor.log.info(
            "Context compilation complete (relevant-context skill)",
            extra={
                "relevant_context_items": len(result.get("relevant_context", [])),
                "concepts": len(ctx.get("concepts", [])),
                "code_snippets": len(ctx.get("code_snippets", [])),
                "api_references": len(ctx.get("api_references", [])),
                "best_practices": len(ctx.get("best_practices", [])),
                "implementation_patterns": len(ctx.get("implementation_patterns", [])),
                "stackoverflow_answers": len(ctx.get("stackoverflow_answers", [])),
                "open_questions": len(result.get("open_questions", [])),
                "recommended_next_context": len(result.get("recommended_next_context", [])),
                "metrics": result.get("metrics", {}),
            },
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
