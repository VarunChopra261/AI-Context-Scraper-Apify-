"""Implementation pattern detection for common coding patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class PatternType(str, Enum):
    """Types of implementation patterns."""

    AUTHENTICATION = "authentication"
    CACHING = "caching"
    ASYNC_CONCURRENCY = "async_concurrency"
    DATABASE_ACCESS = "database_access"
    API_CLIENT = "api_client"
    ERROR_HANDLING = "error_handling"
    CONFIGURATION = "configuration"
    LOGGING = "logging"


@dataclass(slots=True)
class ImplementationPattern:
    """Detected implementation pattern with code example."""

    pattern_type: PatternType
    description: str
    code_snippet: str
    source: str
    confidence: float


class PatternDetector:
    """Detects common implementation patterns in code snippets."""

    def __init__(self) -> None:
        self._patterns = {
            PatternType.AUTHENTICATION: [
                (r"(jwt|token|auth|bearer|oauth)", 0.6),
                (r"(login|authenticate|verify|authorize)", 0.7),
                (r"(password|credential|secret|api[_-]?key)", 0.5),
            ],
            PatternType.CACHING: [
                (r"(cache|redis|memcached|lru)", 0.8),
                (r"(@cache|@lru_cache|@cached)", 0.9),
                (r"(set_cache|get_cache|cache_key)", 0.7),
            ],
            PatternType.ASYNC_CONCURRENCY: [
                (r"(async\s+def|await|asyncio)", 0.9),
                (r"(concurrent|thread|multiprocess|parallel)", 0.6),
                (r"(gather|create_task|queue)", 0.7),
            ],
            PatternType.DATABASE_ACCESS: [
                (r"(select|insert|update|delete|query)", 0.5),
                (r"(session|transaction|commit|rollback)", 0.7),
                (r"(sqlalchemy|django\.orm|pymongo|psycopg)", 0.8),
            ],
            PatternType.API_CLIENT: [
                (r"(requests|httpx|aiohttp|urllib)", 0.7),
                (r"(get|post|put|delete|patch)\(", 0.4),
                (r"(api|endpoint|rest|graphql)", 0.6),
            ],
            PatternType.ERROR_HANDLING: [
                (r"(try|except|finally|raise)", 0.6),
                (r"(error|exception|failure|retry)", 0.5),
                (r"(circuit.?breaker|fallback|timeout)", 0.8),
            ],
            PatternType.CONFIGURATION: [
                (r"(config|settings|environment|env)", 0.6),
                (r"(getenv|load_dotenv|pydantic.*settings)", 0.8),
                (r"(yaml|json|toml|ini).*load", 0.7),
            ],
            PatternType.LOGGING: [
                (r"(logger|logging|log\.|debug|info|warn|error)", 0.7),
                (r"(structlog|loguru|getLogger)", 0.8),
            ],
        }

    def detect(self, code: str, source: str) -> list[ImplementationPattern]:
        """Detect implementation patterns in code snippet."""
        code_lower = code.lower()
        detected: list[ImplementationPattern] = []

        for pattern_type, rules in self._patterns.items():
            confidence = 0.0
            matches = 0

            for pattern_re, weight in rules:
                if re.search(pattern_re, code_lower, re.IGNORECASE):
                    confidence += weight
                    matches += 1

            # Require at least 2 matches and confidence > 1.0
            if matches >= 2 and confidence > 1.0:
                normalized_confidence = min(1.0, confidence / 2.0)
                detected.append(
                    ImplementationPattern(
                        pattern_type=pattern_type,
                        description=self._get_description(pattern_type),
                        code_snippet=code[:1500],
                        source=source,
                        confidence=normalized_confidence,
                    )
                )

        return detected

    @staticmethod
    def _get_description(pattern_type: PatternType) -> str:
        """Get human-readable description for pattern type."""
        descriptions = {
            PatternType.AUTHENTICATION: "Authentication and authorization implementation",
            PatternType.CACHING: "Caching strategy and implementation",
            PatternType.ASYNC_CONCURRENCY: "Asynchronous and concurrent execution pattern",
            PatternType.DATABASE_ACCESS: "Database access and ORM usage",
            PatternType.API_CLIENT: "HTTP API client implementation",
            PatternType.ERROR_HANDLING: "Error handling and resilience pattern",
            PatternType.CONFIGURATION: "Configuration management",
            PatternType.LOGGING: "Logging and observability setup",
        }
        return descriptions.get(pattern_type, str(pattern_type))

    def detect_batch(self, snippets: list[tuple[str, str]]) -> list[ImplementationPattern]:
        """Detect patterns across multiple code snippets."""
        all_patterns: list[ImplementationPattern] = []
        for code, source in snippets:
            patterns = self.detect(code, source)
            all_patterns.extend(patterns)

        # Deduplicate by pattern type, keeping highest confidence
        dedup: dict[PatternType, ImplementationPattern] = {}
        for pattern in all_patterns:
            existing = dedup.get(pattern.pattern_type)
            if existing is None or pattern.confidence > existing.confidence:
                dedup[pattern.pattern_type] = pattern

        return sorted(dedup.values(), key=lambda p: p.confidence, reverse=True)
