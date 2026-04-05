# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Response caching middleware for Nexus platform.

TTL-based response cache with LRU eviction, ETag support, and
Cache-Control header parsing. Thread-safe for concurrent access.

Features:
- TTL-based expiration with per-entry timestamps
- LRU eviction when cache exceeds max_entries
- ETag generation from response content SHA-256
- Cache-Control header parsing (max-age, no-cache, no-store)
- Per-handler cache configuration (exempt specific handlers)
- Thread-safe via threading.Lock
- Cache statistics (hits, misses, evictions)
- Programmatic cache invalidation

Usage:
    from nexus.middleware.cache import ResponseCacheMiddleware

    # Basic usage with defaults (60s TTL, 1000 entries)
    app.add_middleware(ResponseCacheMiddleware)

    # Custom configuration
    from nexus.middleware.cache import CacheConfig
    config = CacheConfig(default_ttl=300, max_entries=5000)
    app.add_middleware(ResponseCacheMiddleware, config=config)

    # Exempt specific handlers from caching
    config = CacheConfig(no_cache_handlers={"create_user", "delete_user"})
    app.add_middleware(ResponseCacheMiddleware, config=config)
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "ResponseCacheMiddleware",
]


@dataclass(frozen=True)
class CacheConfig:
    """Configuration for response caching.

    All fields have sensible defaults. Override only when you have a
    specific reason to change behavior.

    Attributes:
        default_ttl: Default time-to-live in seconds for cached responses.
        max_entries: Maximum number of entries before LRU eviction kicks in.
        no_cache_handlers: Set of handler names that should never be cached.
        no_cache_paths: Set of URL paths that should never be cached.
        cacheable_methods: HTTP methods whose responses can be cached.
            Only GET and HEAD are cacheable by default per RFC 7234.
        cacheable_status_codes: HTTP status codes whose responses can be cached.
        respect_cache_control: Whether to parse and respect Cache-Control
            request headers from clients.
        include_query_in_key: Whether to include query string in cache key.
    """

    default_ttl: int = 60
    max_entries: int = 1000
    no_cache_handlers: FrozenSet[str] = frozenset()
    no_cache_paths: FrozenSet[str] = frozenset()
    cacheable_methods: FrozenSet[str] = frozenset({"GET", "HEAD"})
    cacheable_status_codes: FrozenSet[int] = frozenset({200, 301})
    respect_cache_control: bool = True
    include_query_in_key: bool = True


@dataclass
class CacheEntry:
    """A single cached response.

    Stores the full response (status, headers, body) along with
    metadata for TTL expiry, ETag matching, and LRU tracking.

    Attributes:
        status: HTTP response status code.
        headers: Response headers as list of byte tuples.
        body: Response body bytes.
        etag: SHA-256 based ETag for the response body.
        created_at: Monotonic timestamp when the entry was created.
        ttl: Time-to-live in seconds for this entry.
    """

    status: int
    headers: List[Tuple[bytes, bytes]]
    body: bytes
    etag: str
    created_at: float
    ttl: int

    @property
    def is_expired(self) -> bool:
        """Check if this entry has exceeded its TTL."""
        return (time.monotonic() - self.created_at) >= self.ttl

    @property
    def age(self) -> int:
        """Seconds since this entry was created."""
        return int(time.monotonic() - self.created_at)


@dataclass
class CacheStats:
    """Cumulative cache statistics.

    All counters are monotonically increasing and never reset during
    the lifetime of the middleware instance.

    Attributes:
        hits: Number of cache hits (response served from cache).
        misses: Number of cache misses (response served from upstream).
        etag_hits: Number of 304 Not Modified responses from ETag match.
        evictions: Number of entries evicted due to LRU overflow.
        expirations: Number of entries expired due to TTL.
        invalidations: Number of entries explicitly invalidated via API.
        current_size: Current number of entries in the cache.
    """

    hits: int = 0
    misses: int = 0
    etag_hits: int = 0
    evictions: int = 0
    expirations: int = 0
    invalidations: int = 0
    current_size: int = 0

    def to_dict(self) -> Dict[str, int]:
        """Return stats as a plain dict for JSON serialization."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "etag_hits": self.etag_hits,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "invalidations": self.invalidations,
            "current_size": self.current_size,
            "total_requests": total,
            "hit_rate_percent": round(hit_rate, 2),
        }


def _generate_etag(body: bytes) -> str:
    """Generate a weak ETag from response body content.

    Uses SHA-256 truncated to 16 hex chars for a balance of
    collision resistance and header size.

    Args:
        body: Response body bytes.

    Returns:
        ETag string in weak validator format (W/"...").
    """
    digest = hashlib.sha256(body).hexdigest()[:16]
    return f'W/"{digest}"'


def _build_cache_key(method: str, path: str, query_string: bytes) -> str:
    """Build a unique cache key from request attributes.

    Args:
        method: HTTP method (GET, HEAD, etc.).
        path: Request path.
        query_string: Raw query string bytes.

    Returns:
        Cache key string.
    """
    qs = query_string.decode("latin-1") if query_string else ""
    return f"{method}:{path}?{qs}" if qs else f"{method}:{path}"


def _parse_cache_control(header_value: str) -> Dict[str, Optional[int]]:
    """Parse a Cache-Control header value into directives.

    Handles: no-cache, no-store, max-age=N, only-if-cached.

    Args:
        header_value: Raw Cache-Control header string.

    Returns:
        Dict mapping directive name to value (int for max-age, None for flags).
    """
    directives: Dict[str, Optional[int]] = {}
    if not header_value:
        return directives

    for part in header_value.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if "=" in part:
            key, _, val = part.partition("=")
            key = key.strip()
            val = val.strip()
            try:
                directives[key] = int(val)
            except ValueError:
                directives[key] = None
        else:
            directives[part] = None

    return directives


class ResponseCacheMiddleware:
    """ASGI middleware for caching HTTP responses.

    Caches responses for cacheable methods (GET, HEAD by default) with
    TTL-based expiration and LRU eviction. Supports ETag generation for
    conditional requests and Cache-Control header parsing.

    Thread-safe: all cache mutations are protected by a threading.Lock.

    Compatible with Starlette's add_middleware() pattern.
    """

    def __init__(
        self,
        app: Any,
        config: Optional[CacheConfig] = None,
    ) -> None:
        """Initialize the response cache middleware.

        Args:
            app: The ASGI application to wrap.
            config: Cache configuration. Uses defaults if None.
        """
        self.app = app
        self.config = config or CacheConfig()

        # OrderedDict for LRU: most recently used at the end
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        """Return current cache statistics (read-only snapshot)."""
        with self._lock:
            self._stats.current_size = len(self._cache)
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                etag_hits=self._stats.etag_hits,
                evictions=self._stats.evictions,
                expirations=self._stats.expirations,
                invalidations=self._stats.invalidations,
                current_size=len(self._cache),
            )

    def invalidate(self, path: str, method: str = "GET") -> bool:
        """Invalidate a specific cache entry.

        Args:
            path: The request path to invalidate.
            method: The HTTP method (default GET).

        Returns:
            True if an entry was found and removed, False otherwise.
        """
        # Try with and without query string
        with self._lock:
            key = f"{method}:{path}"
            # Exact match first
            if key in self._cache:
                del self._cache[key]
                self._stats.invalidations += 1
                return True
            # Also try matching keys that start with this path
            to_remove = [k for k in self._cache if k.startswith(key)]
            if to_remove:
                for k in to_remove:
                    del self._cache[k]
                    self._stats.invalidations += 1
                return True
        return False

    def invalidate_all(self) -> int:
        """Clear the entire cache.

        Returns:
            Number of entries that were removed.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.invalidations += count
            return count

    def _is_cacheable_request(
        self,
        method: str,
        path: str,
        cache_control: Dict[str, Optional[int]],
    ) -> bool:
        """Determine if a request is eligible for caching.

        Args:
            method: HTTP method.
            path: Request path.
            cache_control: Parsed Cache-Control directives from the request.

        Returns:
            True if the response for this request may be cached.
        """
        # Only cache configured methods
        if method not in self.config.cacheable_methods:
            return False

        # Skip paths configured as no-cache
        if path in self.config.no_cache_paths:
            return False

        # Check handler-based exclusion by extracting handler name from path
        # Convention: /api/v1/{handler_name} or /{handler_name}
        path_parts = [p for p in path.strip("/").split("/") if p]
        if path_parts:
            handler_name = path_parts[-1]
            if handler_name in self.config.no_cache_handlers:
                return False

        # Respect client Cache-Control if configured
        if self.config.respect_cache_control:
            if "no-store" in cache_control:
                return False
            if "no-cache" in cache_control:
                return False

        return True

    def _get_ttl(self, cache_control: Dict[str, Optional[int]]) -> int:
        """Determine TTL for a response.

        Client max-age overrides the default if respect_cache_control is
        enabled and the client sends a max-age directive.

        Args:
            cache_control: Parsed Cache-Control directives from the request.

        Returns:
            TTL in seconds.
        """
        if self.config.respect_cache_control and "max-age" in cache_control:
            client_max_age = cache_control["max-age"]
            if client_max_age is not None and client_max_age >= 0:
                return min(client_max_age, self.config.default_ttl)
        return self.config.default_ttl

    def _evict_expired(self) -> None:
        """Remove all expired entries. Caller MUST hold self._lock."""
        expired_keys = [k for k, v in self._cache.items() if v.is_expired]
        for key in expired_keys:
            del self._cache[key]
            self._stats.expirations += 1

    def _evict_lru(self) -> None:
        """Evict least-recently-used entries until under max_entries.

        Caller MUST hold self._lock.
        """
        while len(self._cache) >= self.config.max_entries:
            # popitem(last=False) removes the oldest (least recently used)
            self._cache.popitem(last=False)
            self._stats.evictions += 1

    def _lookup(self, key: str) -> Optional[CacheEntry]:
        """Look up a cache entry, moving it to most-recent on hit.

        Removes expired entries on access. Caller MUST hold self._lock.

        Args:
            key: Cache key.

        Returns:
            CacheEntry if found and not expired, None otherwise.
        """
        entry = self._cache.get(key)
        if entry is None:
            return None

        if entry.is_expired:
            del self._cache[key]
            self._stats.expirations += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return entry

    def _store(self, key: str, entry: CacheEntry) -> None:
        """Store a cache entry, evicting as needed.

        Caller MUST hold self._lock.

        Args:
            key: Cache key.
            entry: The entry to store.
        """
        # Remove existing entry if present (to update position)
        if key in self._cache:
            del self._cache[key]

        # Evict expired entries first to free space
        self._evict_expired()

        # Evict LRU if still over capacity
        self._evict_lru()

        # Insert at end (most recently used)
        self._cache[key] = entry

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        query_string = scope.get("query_string", b"")

        # Extract request headers
        headers_raw = dict(scope.get("headers", []))
        cache_control_header = headers_raw.get(b"cache-control", b"").decode(
            "latin-1", errors="replace"
        )
        if_none_match = headers_raw.get(b"if-none-match", b"").decode(
            "latin-1", errors="replace"
        )

        # Parse Cache-Control directives
        cache_control = _parse_cache_control(cache_control_header)

        # Check if this request is cacheable
        if not self._is_cacheable_request(method, path, cache_control):
            await self.app(scope, receive, send)
            return

        # Build cache key
        if self.config.include_query_in_key:
            cache_key = _build_cache_key(method, path, query_string)
        else:
            cache_key = _build_cache_key(method, path, b"")

        # Try cache lookup
        with self._lock:
            entry = self._lookup(cache_key)

        if entry is not None:
            # Check ETag conditional request (If-None-Match)
            if if_none_match and self._etag_matches(if_none_match, entry.etag):
                with self._lock:
                    self._stats.etag_hits += 1
                    self._stats.hits += 1
                await self._send_304(send, entry)
                return

            # Cache hit — serve from cache
            with self._lock:
                self._stats.hits += 1
            await self._send_cached(send, entry)
            return

        # Cache miss — call upstream and capture response
        with self._lock:
            self._stats.misses += 1

        ttl = self._get_ttl(cache_control)
        captured = _ResponseCapture()

        async def capturing_send(message: Dict[str, Any]) -> None:
            captured.capture(message)
            await send(message)

        await self.app(scope, receive, capturing_send)

        # Store in cache if the response is cacheable
        if (
            captured.is_complete
            and captured.status in self.config.cacheable_status_codes
        ):
            # Check response Cache-Control headers for no-store
            response_cc = self._get_response_cache_control(captured.headers)
            if "no-store" not in response_cc and "no-cache" not in response_cc:
                etag = _generate_etag(captured.body)
                new_entry = CacheEntry(
                    status=captured.status,
                    headers=captured.headers,
                    body=captured.body,
                    etag=etag,
                    created_at=time.monotonic(),
                    ttl=ttl,
                )
                with self._lock:
                    self._store(cache_key, new_entry)

    @staticmethod
    def _etag_matches(if_none_match: str, etag: str) -> bool:
        """Check if an If-None-Match header matches the cached ETag.

        Handles both single ETags and comma-separated lists.

        Args:
            if_none_match: The If-None-Match header value.
            etag: The cached entry's ETag.

        Returns:
            True if any provided ETag matches the cached one.
        """
        if if_none_match == "*":
            return True

        # Compare against each provided ETag
        for candidate in if_none_match.split(","):
            candidate = candidate.strip()
            if candidate == etag:
                return True
            # Strip W/ prefix for weak comparison (RFC 7232 Section 2.3)
            stripped_candidate = candidate.lstrip("W/").strip('"')
            stripped_etag = etag.lstrip("W/").strip('"')
            if stripped_candidate == stripped_etag:
                return True

        return False

    @staticmethod
    def _get_response_cache_control(
        headers: List[Tuple[bytes, bytes]],
    ) -> Dict[str, Optional[int]]:
        """Extract Cache-Control directives from response headers.

        Args:
            headers: Response headers as byte tuples.

        Returns:
            Parsed Cache-Control directives.
        """
        for name, value in headers:
            if name.lower() == b"cache-control":
                return _parse_cache_control(value.decode("latin-1", errors="replace"))
        return {}

    async def _send_304(self, send: Any, entry: CacheEntry) -> None:
        """Send a 304 Not Modified response with the cached ETag.

        Args:
            send: ASGI send callable.
            entry: The matched cache entry (for ETag).
        """
        response_headers: List[Tuple[bytes, bytes]] = [
            (b"etag", entry.etag.encode("latin-1")),
            (b"x-cache", b"HIT-ETAG"),
            (b"age", str(entry.age).encode()),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 304,
                "headers": response_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"",
            }
        )

    async def _send_cached(self, send: Any, entry: CacheEntry) -> None:
        """Send a full cached response with cache metadata headers.

        Args:
            send: ASGI send callable.
            entry: The cache entry to serve.
        """
        # Build headers: original response headers + cache metadata
        response_headers = list(entry.headers)
        response_headers.append((b"etag", entry.etag.encode("latin-1")))
        response_headers.append((b"x-cache", b"HIT"))
        response_headers.append((b"age", str(entry.age).encode()))

        await send(
            {
                "type": "http.response.start",
                "status": entry.status,
                "headers": response_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": entry.body,
            }
        )


class _ResponseCapture:
    """Captures ASGI response messages for caching.

    Accumulates the status code, headers, and body from the
    http.response.start and http.response.body messages.
    """

    def __init__(self) -> None:
        self.status: int = 0
        self.headers: List[Tuple[bytes, bytes]] = []
        self.body: bytes = b""
        self._got_start: bool = False
        self._got_body: bool = False

    @property
    def is_complete(self) -> bool:
        """True if both start and body messages have been captured."""
        return self._got_start and self._got_body

    def capture(self, message: Dict[str, Any]) -> None:
        """Capture an ASGI message.

        Args:
            message: ASGI message dict (http.response.start or http.response.body).
        """
        msg_type = message.get("type", "")

        if msg_type == "http.response.start":
            self.status = message.get("status", 200)
            self.headers = list(message.get("headers", []))
            self._got_start = True

        elif msg_type == "http.response.body":
            body_chunk = message.get("body", b"")
            if isinstance(body_chunk, memoryview):
                body_chunk = bytes(body_chunk)
            self.body += body_chunk
            # Only mark complete if this is the final body chunk
            # (more_body=False is the default per ASGI spec)
            if not message.get("more_body", False):
                self._got_body = True
