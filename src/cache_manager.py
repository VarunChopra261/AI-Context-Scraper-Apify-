"""Caching layer using Apify Key-Value store."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from apify import Actor

# Default TTLs in seconds
DEFAULT_PAGE_TTL = 86400   # 24 hours
DEFAULT_TASK_TTL = 3600    # 1 hour


def _now() -> float:
    """Return current monotonic time for TTL calculations.

    Uses ``time.monotonic()`` instead of ``time.time()`` so TTL decisions
    are immune to wall-clock drift or NTP adjustments inside containers.
    """
    return time.monotonic()


class CacheManager:
    """Manages caching of scraped pages and computed embeddings."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._kvs: Any | None = None
        self._boot_monotonic = _now()
        self._boot_wall = time.time()

    async def _get_kvs(self):
        """Get or open Key-Value store.

        Returns None if the Actor context is not available (e.g., in tests).
        """
        if self._kvs is None:
            try:
                self._kvs = await Actor.open_key_value_store()
            except Exception:  # noqa: BLE001, S110
                return None
        return self._kvs

    @staticmethod
    def _cache_key(prefix: str, value: str) -> str:
        """Generate cache key from prefix and value."""
        value_hash = hashlib.sha256(value.encode()).hexdigest()[:16]
        return f"{prefix}_{value_hash}"

    def _monotonic_from_wall(self, wall_ts: float) -> float:
        """Convert a stored wall-clock timestamp to approximate monotonic.

        Cached entries written by a **previous** actor run will have been
        created under a different monotonic epoch.  We translate via the
        wall-clock offset captured at boot, which is accurate enough for
        TTLs in the 1-24 hour range.
        """
        return self._boot_monotonic + (wall_ts - self._boot_wall)

    def _is_expired(self, cached: dict, ttl_seconds: int) -> bool:
        """Check if a cached entry has expired based on its _cached_at timestamp."""
        cached_at = cached.get("_cached_at")
        if cached_at is None:
            # No timestamp — treat as expired to be safe
            return True
        cached_monotonic = self._monotonic_from_wall(cached_at)
        return (_now() - cached_monotonic) > ttl_seconds

    async def get_page(self, url: str, ttl_seconds: int = DEFAULT_PAGE_TTL) -> dict | None:
        """Retrieve cached page content, respecting TTL."""
        if not self._enabled:
            return None

        try:
            kvs = await self._get_kvs()
            if kvs is None:
                return None
            key = self._cache_key("page", url)
            cached = await kvs.get_value(key)
            if not cached:
                return None
            if self._is_expired(cached, ttl_seconds):
                return None
            return cached
        except Exception:  # noqa: BLE001, S110
            return None

    async def set_page(self, url: str, content: dict, ttl_seconds: int = DEFAULT_PAGE_TTL) -> None:
        """Cache page content with TTL metadata."""
        if not self._enabled:
            return

        try:
            kvs = await self._get_kvs()
            if kvs is None:
                return
            key = self._cache_key("page", url)
            # Store wall-clock time so it survives across actor restarts
            cached = {**content, "_cached_at": time.time()}
            await kvs.set_value(key, cached)
        except Exception:  # noqa: BLE001, S110
            pass

    async def get_embedding(self, text: str) -> list[float] | None:
        """Retrieve cached embedding vector (no TTL — embeddings are stable)."""
        if not self._enabled:
            return None

        try:
            kvs = await self._get_kvs()
            if kvs is None:
                return None
            key = self._cache_key("emb", text[:500])  # Use first 500 chars
            cached = await kvs.get_value(key)
            return cached if cached else None
        except Exception:  # noqa: BLE001, S110
            return None

    async def set_embedding(self, text: str, embedding: list[float]) -> None:
        """Cache embedding vector."""
        if not self._enabled:
            return

        try:
            kvs = await self._get_kvs()
            if kvs is None:
                return
            key = self._cache_key("emb", text[:500])
            await kvs.set_value(key, embedding)
        except Exception:  # noqa: BLE001, S110
            pass

    async def get_task_result(self, task: str, config_hash: str, ttl_seconds: int = DEFAULT_TASK_TTL) -> dict | None:
        """Retrieve cached complete task result, respecting TTL."""
        if not self._enabled:
            return None

        try:
            kvs = await self._get_kvs()
            if kvs is None:
                return None
            key = self._cache_key("task", f"{task}_{config_hash}")
            cached = await kvs.get_value(key)
            if not cached:
                return None
            if self._is_expired(cached, ttl_seconds):
                return None
            return cached
        except Exception:  # noqa: BLE001, S110
            return None

    async def set_task_result(self, task: str, config_hash: str, result: dict, ttl_seconds: int = DEFAULT_TASK_TTL) -> None:
        """Cache complete task result with TTL metadata."""
        if not self._enabled:
            return

        try:
            kvs = await self._get_kvs()
            if kvs is None:
                return
            key = self._cache_key("task", f"{task}_{config_hash}")
            # Store wall-clock for persistence; compare via monotonic offset
            cached = {**result, "_cached_at": time.time()}
            await kvs.set_value(key, cached)
        except Exception:  # noqa: BLE001, S110
            pass
