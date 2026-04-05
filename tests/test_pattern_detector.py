"""Tests for pattern_detector.py module."""

import pytest

from src.pattern_detector import ImplementationPattern, PatternDetector, PatternType


@pytest.fixture
def detector():
    """Create PatternDetector instance."""
    return PatternDetector()


class TestPatternDetection:
    """Test pattern detection functionality."""

    def test_detect_authentication_pattern(self, detector):
        """Test authentication pattern detection."""
        code = """
        @jwt_required()
        def protected_route():
            user = get_jwt_identity()
            token = verify_token(request.headers.get('Authorization'))
            return {"user": user}
        """
        patterns = detector.detect(code, source="test")
        auth_patterns = [p for p in patterns if p.pattern_type == PatternType.AUTHENTICATION]

        assert len(auth_patterns) > 0
        assert auth_patterns[0].confidence > 0.5

    def test_detect_caching_pattern(self, detector):
        """Test caching pattern detection."""
        code = """
        @cache.memoize(timeout=300)
        def expensive_operation():
            redis_client.set(key, value, ex=3600)
            cached = cache.get(cache_key)
            return result
        """
        patterns = detector.detect(code, source="test")
        cache_patterns = [p for p in patterns if p.pattern_type == PatternType.CACHING]

        assert len(cache_patterns) > 0

    def test_detect_async_pattern(self, detector):
        """Test async/concurrency pattern detection."""
        code = """
        async def fetch_data():
            results = await asyncio.gather(*tasks)
            async with aiohttp.ClientSession() as session:
                return await session.get(url)
        """
        patterns = detector.detect(code, source="test")
        async_patterns = [p for p in patterns if p.pattern_type == PatternType.ASYNC_CONCURRENCY]

        assert len(async_patterns) > 0

    def test_detect_database_pattern(self, detector):
        """Test database access pattern detection."""
        code = """
        from sqlalchemy import create_engine

        engine = create_engine('postgresql://user:pass@localhost/db')
        with session.begin() as transaction:
            result = session.execute("SELECT * FROM users")
            transaction.commit()
        """
        patterns = detector.detect(code, source="test")
        db_patterns = [p for p in patterns if p.pattern_type == PatternType.DATABASE_ACCESS]

        assert len(db_patterns) > 0

    def test_detect_error_handling_pattern(self, detector):
        """Test error handling pattern detection."""
        code = """
        try:
            risky_operation()
        except ValueError as e:
            logger.error(f"Error: {e}")
            raise CustomException("Failed") from e
        finally:
            cleanup()
        """
        patterns = detector.detect(code, source="test")
        error_patterns = [p for p in patterns if p.pattern_type == PatternType.ERROR_HANDLING]

        assert len(error_patterns) > 0

    def test_detect_logging_pattern(self, detector):
        """Test logging pattern detection."""
        code = """
        import logging

        logger = logging.getLogger(__name__)
        logger.info("Processing request", extra={"user_id": 123})
        logger.debug("Debug info")
        """
        patterns = detector.detect(code, source="test")
        log_patterns = [p for p in patterns if p.pattern_type == PatternType.LOGGING]

        assert len(log_patterns) > 0

    def test_detect_configuration_pattern(self, detector):
        """Test configuration pattern detection."""
        code = """
        from pydantic import BaseSettings

        class Settings(BaseSettings):
            api_key: str = os.getenv("API_KEY")
            env = "production"
            config = load_dotenv()
        """
        patterns = detector.detect(code, source="test")
        config_patterns = [p for p in patterns if p.pattern_type == PatternType.CONFIGURATION]

        assert len(config_patterns) > 0

    def test_detect_api_client_pattern(self, detector):
        """Test API client pattern detection."""
        code = """
        import requests

        response = requests.get("https://api.example.com/data")
        response.raise_for_status()
        """
        patterns = detector.detect(code, source="test")
        api_patterns = [p for p in patterns if p.pattern_type == PatternType.API_CLIENT]

        assert len(api_patterns) > 0


class TestConfidenceScoring:
    """Test confidence scoring logic."""

    def test_higher_confidence_for_clear_patterns(self, detector):
        """Test clear patterns get higher confidence scores."""
        clear_code = """
        @app.route('/protected')
        @jwt_required()
        def protected():
            token = request.headers.get('Authorization')
            user = verify_jwt_token(token)
            password = check_credential(user)
        """
        patterns = detector.detect(clear_code, source="test")

        if patterns:
            assert patterns[0].confidence > 0.5

    def test_no_patterns_for_simple_code(self, detector):
        """Test simple code produces few or no patterns."""
        simple_code = "x = 1\ny = 2\nz = x + y"
        patterns = detector.detect(simple_code, source="test")

        # Very simple code should not trigger patterns (requires >= 2 matches)
        assert len(patterns) == 0


class TestBatchDetection:
    """Test batch pattern detection."""

    def test_detect_batch_aggregates(self, detector):
        """Test batch detection across multiple snippets."""
        snippets = [
            ("async def f(): await asyncio.gather(*tasks)\ncreate_task(coro)", "source1"),
            ("import logging\nlogger = logging.getLogger(__name__)\nlogger.info('x')", "source2"),
        ]
        patterns = detector.detect_batch(snippets)

        pattern_types = {p.pattern_type for p in patterns}
        assert PatternType.ASYNC_CONCURRENCY in pattern_types
        assert PatternType.LOGGING in pattern_types

    def test_detect_batch_deduplicates_by_type(self, detector):
        """Test batch detection keeps only the highest-confidence per type."""
        snippets = [
            ("async def a(): await asyncio.gather(*tasks)\ncreate_task(c)", "source1"),
            ("async def b(): await asyncio.gather(*more)\ncreate_task(d)", "source2"),
        ]
        patterns = detector.detect_batch(snippets)

        async_patterns = [p for p in patterns if p.pattern_type == PatternType.ASYNC_CONCURRENCY]
        # Should deduplicate to one per type
        assert len(async_patterns) == 1

    def test_detect_batch_empty(self, detector):
        """Test batch detection with empty list."""
        patterns = detector.detect_batch([])
        assert patterns == []


class TestImplementationPatternDataclass:
    """Test ImplementationPattern dataclass."""

    def test_pattern_fields(self, detector):
        """Test pattern has all expected fields."""
        code = """
        async def handler():
            result = await asyncio.gather(*tasks)
            task = create_task(process())
        """
        patterns = detector.detect(code, source="https://example.com")

        if patterns:
            p = patterns[0]
            assert isinstance(p, ImplementationPattern)
            assert isinstance(p.pattern_type, PatternType)
            assert isinstance(p.description, str)
            assert isinstance(p.code_snippet, str)
            assert isinstance(p.source, str)
            assert isinstance(p.confidence, float)
            assert 0.0 <= p.confidence <= 1.0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_code(self, detector):
        """Test detection with empty code."""
        patterns = detector.detect("", source="test")
        assert isinstance(patterns, list)

    def test_whitespace_only_code(self, detector):
        """Test detection with whitespace-only code."""
        patterns = detector.detect("   \n\n   ", source="test")
        assert isinstance(patterns, list)

    def test_unicode_in_code(self, detector):
        """Test detection with Unicode characters."""
        code = """
        # 认证系统
        def authenticate(用户名: str):
            return "认证成功"
        """
        patterns = detector.detect(code, source="test")
        assert isinstance(patterns, list)

    def test_code_snippet_truncation(self, detector):
        """Test that code_snippet is truncated to 1500 chars."""
        long_code = "x = 1\n" * 500 + "async def f(): await asyncio.gather(*tasks)\ncreate_task(c)"
        patterns = detector.detect(long_code, source="test")

        for p in patterns:
            assert len(p.code_snippet) <= 1500
