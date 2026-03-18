"""In-memory TTL cache for catalog and conjunction data."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    """A cached value with expiration."""

    value: Any
    expires_at: float


class TTLCache:
    """Simple in-memory cache with per-key TTL."""

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str) -> Any | None:
        """Get a cached value, or None if expired/missing."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        """Store a value with TTL."""
        self._store[key] = CacheEntry(
            value=value,
            expires_at=time.monotonic() + ttl_seconds,
        )

    def lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a cache key (prevents stampede)."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()


# Global cache instance
cache = TTLCache()
