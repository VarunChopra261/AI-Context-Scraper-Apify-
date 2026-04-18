"""Comprehensive regression tests for cache_manager.py — zero coverage → full coverage."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cache_manager import CacheManager, DEFAULT_PAGE_TTL, DEFAULT_TASK_TTL, _now


# ---------------------------------------------------------------------------
# _now() helper
# ---------------------------------------------------------------------------

class TestNowHelper:
    def test_returns_positive_float(self):
        t = _now()
        assert isinstance(t, float)
        assert t > 0

    def test_is_monotonically_increasing(self):
        t1 = _now()
        time.sleep(0.01)
        t2 = _now()
        assert t2 > t1


# ---------------------------------------------------------------------------
# CacheManager — disabled mode
# ---------------------------------------------------------------------------

class TestCacheManagerDisabled:
    @pytest.fixture
    def disabled_cache(self):
        return CacheManager(enabled=False)

    async def test_get_page_returns_none_when_disabled(self, disabled_cache):
        result = await disabled_cache.get_page("https://example.com")
        assert result is None

    async def test_set_page_is_noop_when_disabled(self, disabled_cache):
        # Should not raise even without KVS
        await disabled_cache.set_page("https://example.com", {"data": "test"})

    async def test_get_embedding_returns_none_when_disabled(self, disabled_cache):
        result = await disabled_cache.get_embedding("some text")
        assert result is None

    async def test_set_embedding_is_noop_when_disabled(self, disabled_cache):
        await disabled_cache.set_embedding("some text", [0.1, 0.2, 0.3])

    async def test_get_task_result_returns_none_when_disabled(self, disabled_cache):
        result = await disabled_cache.get_task_result("task", "hash")
        assert result is None

    async def test_set_task_result_is_noop_when_disabled(self, disabled_cache):
        await disabled_cache.set_task_result("task", "hash", {"result": "data"})


# ---------------------------------------------------------------------------
# CacheManager — KVS unavailable (Actor not running)
# ---------------------------------------------------------------------------

class TestCacheManagerNoKvs:
    """When Actor.open_key_value_store raises, all operations silently return None."""

    @pytest.fixture
    def cache_no_kvs(self):
        with patch("src.cache_manager.Actor") as mock_actor:
            mock_actor.open_key_value_store = AsyncMock(side_effect=RuntimeError("not in actor"))
            yield CacheManager(enabled=True)

    async def test_get_page_returns_none_when_kvs_unavailable(self, cache_no_kvs):
        result = await cache_no_kvs.get_page("https://example.com")
        assert result is None

    async def test_set_page_is_noop_when_kvs_unavailable(self, cache_no_kvs):
        await cache_no_kvs.set_page("https://example.com", {"html": "content"})

    async def test_get_embedding_returns_none_when_kvs_unavailable(self, cache_no_kvs):
        result = await cache_no_kvs.get_embedding("query text")
        assert result is None

    async def test_set_embedding_is_noop_when_kvs_unavailable(self, cache_no_kvs):
        await cache_no_kvs.set_embedding("query text", [0.1, 0.9])

    async def test_get_task_result_returns_none_when_kvs_unavailable(self, cache_no_kvs):
        result = await cache_no_kvs.get_task_result("my task", "abc123")
        assert result is None

    async def test_set_task_result_is_noop_when_kvs_unavailable(self, cache_no_kvs):
        await cache_no_kvs.set_task_result("my task", "abc123", {"data": 1})


# ---------------------------------------------------------------------------
# CacheManager — with mock KVS
# ---------------------------------------------------------------------------

def _make_cache_with_kvs():
    """Return (CacheManager, mock_kvs) with Actor.open_key_value_store mocked."""
    mock_kvs = AsyncMock()
    mock_kvs.get_value = AsyncMock(return_value=None)
    mock_kvs.set_value = AsyncMock(return_value=None)

    with patch("src.cache_manager.Actor") as mock_actor:
        mock_actor.open_key_value_store = AsyncMock(return_value=mock_kvs)
        cache = CacheManager(enabled=True)
        cache._kvs = mock_kvs  # Inject directly to skip the Actor call path
    return cache, mock_kvs


class TestCacheManagerGetPageHit:
    async def test_get_page_returns_valid_entry(self):
        cache, mock_kvs = _make_cache_with_kvs()
        now_wall = time.time()
        cached = {"html": "content", "_cached_at": now_wall}
        mock_kvs.get_value = AsyncMock(return_value=cached)

        result = await cache.get_page("https://example.com")
        assert result is not None
        assert result["html"] == "content"

    async def test_get_page_returns_none_for_expired_entry(self):
        cache, mock_kvs = _make_cache_with_kvs()
        # Simulate entry cached 2 days ago
        old_wall = time.time() - (2 * 86400)
        cached = {"html": "old", "_cached_at": old_wall}
        mock_kvs.get_value = AsyncMock(return_value=cached)

        result = await cache.get_page("https://example.com", ttl_seconds=86400)
        assert result is None

    async def test_get_page_returns_none_for_entry_without_cached_at(self):
        cache, mock_kvs = _make_cache_with_kvs()
        cached = {"html": "content"}  # no _cached_at
        mock_kvs.get_value = AsyncMock(return_value=cached)

        result = await cache.get_page("https://example.com")
        assert result is None

    async def test_get_page_returns_none_when_nothing_cached(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.get_value = AsyncMock(return_value=None)

        result = await cache.get_page("https://example.com")
        assert result is None


class TestCacheManagerSetPage:
    async def test_set_page_stores_value_with_cached_at(self):
        cache, mock_kvs = _make_cache_with_kvs()
        await cache.set_page("https://example.com", {"html": "content"})

        assert mock_kvs.set_value.called
        call_args = mock_kvs.set_value.call_args
        stored_value = call_args[0][1]  # second positional arg
        assert "_cached_at" in stored_value
        assert stored_value["html"] == "content"

    async def test_set_page_exception_is_swallowed(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.set_value = AsyncMock(side_effect=RuntimeError("KVS exploded"))

        # Should not raise
        await cache.set_page("https://example.com", {"html": "content"})


class TestCacheManagerGetTaskResult:
    async def test_get_task_result_returns_valid_entry(self):
        cache, mock_kvs = _make_cache_with_kvs()
        now_wall = time.time()
        cached = {"task": "myresult", "_cached_at": now_wall}
        mock_kvs.get_value = AsyncMock(return_value=cached)

        result = await cache.get_task_result("my task", "hash123")
        assert result is not None
        assert result["task"] == "myresult"

    async def test_get_task_result_returns_none_for_expired_entry(self):
        cache, mock_kvs = _make_cache_with_kvs()
        old_wall = time.time() - 7200  # 2 hours ago
        cached = {"result": "data", "_cached_at": old_wall}
        mock_kvs.get_value = AsyncMock(return_value=cached)

        result = await cache.get_task_result("my task", "hash123", ttl_seconds=3600)
        assert result is None

    async def test_get_task_result_returns_none_when_nothing_cached(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.get_value = AsyncMock(return_value=None)

        result = await cache.get_task_result("my task", "hash")
        assert result is None


class TestCacheManagerSetTaskResult:
    async def test_set_task_result_stores_value_with_cached_at(self):
        cache, mock_kvs = _make_cache_with_kvs()
        await cache.set_task_result("my task", "hash", {"data": "result"})

        assert mock_kvs.set_value.called
        stored = mock_kvs.set_value.call_args[0][1]
        assert "_cached_at" in stored
        assert stored["data"] == "result"

    async def test_set_task_result_exception_swallowed(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.set_value = AsyncMock(side_effect=OSError("disk full"))

        # Must not raise
        await cache.set_task_result("task", "hash", {"data": "ok"})


class TestCacheManagerEmbeddings:
    async def test_get_embedding_returns_vector_when_cached(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.get_value = AsyncMock(return_value=[0.1, 0.2, 0.3])

        result = await cache.get_embedding("some text")
        assert result == [0.1, 0.2, 0.3]

    async def test_get_embedding_returns_none_when_not_cached(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.get_value = AsyncMock(return_value=None)

        result = await cache.get_embedding("some text")
        assert result is None

    async def test_set_embedding_stores_vector(self):
        cache, mock_kvs = _make_cache_with_kvs()
        await cache.set_embedding("some text", [0.9, 0.1])
        assert mock_kvs.set_value.called


# ---------------------------------------------------------------------------
# CacheManager — cache key determinism
# ---------------------------------------------------------------------------

class TestCacheKeyDeterminism:
    def test_same_prefix_and_value_produce_same_key(self):
        k1 = CacheManager._cache_key("page", "https://example.com")
        k2 = CacheManager._cache_key("page", "https://example.com")
        assert k1 == k2

    def test_different_values_produce_different_keys(self):
        k1 = CacheManager._cache_key("page", "https://example.com")
        k2 = CacheManager._cache_key("page", "https://other.com")
        assert k1 != k2

    def test_different_prefixes_produce_different_keys(self):
        k1 = CacheManager._cache_key("page", "same_value")
        k2 = CacheManager._cache_key("task", "same_value")
        assert k1 != k2

    def test_key_is_string(self):
        k = CacheManager._cache_key("emb", "query text")
        assert isinstance(k, str)

    def test_key_contains_prefix(self):
        k = CacheManager._cache_key("page", "url")
        assert k.startswith("page_")


# ---------------------------------------------------------------------------
# CacheManager — is_expired logic
# ---------------------------------------------------------------------------

class TestIsExpired:
    def test_no_cached_at_treated_as_expired(self):
        cm = CacheManager()
        assert cm._is_expired({}, ttl_seconds=3600) is True

    def test_fresh_entry_not_expired(self):
        cm = CacheManager()
        # Store a wall-clock time that corresponds to "now"
        now_wall = time.time()
        entry = {"_cached_at": now_wall}
        assert cm._is_expired(entry, ttl_seconds=3600) is False

    def test_old_entry_is_expired(self):
        cm = CacheManager()
        old_wall = time.time() - 7200  # 2 hours ago
        entry = {"_cached_at": old_wall}
        assert cm._is_expired(entry, ttl_seconds=3600) is True


# ---------------------------------------------------------------------------
# CacheManager — KVS exception handling in get operations
# ---------------------------------------------------------------------------

class TestExceptionHandlingInGet:
    async def test_get_page_swallows_kvs_exception(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.get_value = AsyncMock(side_effect=RuntimeError("network error"))

        result = await cache.get_page("https://example.com")
        assert result is None

    async def test_get_task_result_swallows_kvs_exception(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.get_value = AsyncMock(side_effect=RuntimeError("timeout"))

        result = await cache.get_task_result("task", "hash")
        assert result is None

    async def test_get_embedding_swallows_kvs_exception(self):
        cache, mock_kvs = _make_cache_with_kvs()
        mock_kvs.get_value = AsyncMock(side_effect=ValueError("corrupt data"))

        result = await cache.get_embedding("text")
        assert result is None
