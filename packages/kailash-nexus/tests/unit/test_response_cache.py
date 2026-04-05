# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for response cache middleware.

Covers:
- CacheConfig defaults and customization
- CacheEntry TTL expiration
- CacheStats tracking and serialization
- ETag generation and 304 Not Modified responses
- Cache-Control header parsing (no-cache, no-store, max-age)
- LRU eviction when cache exceeds max_entries
- Per-handler and per-path cache exclusion
- Cache invalidation API (single and bulk)
- Thread safety under concurrent access
- Query string inclusion/exclusion in cache keys
- Non-cacheable method bypass (POST, PUT, DELETE, PATCH)
- Response Cache-Control no-store prevents caching
- Non-HTTP scope passthrough
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from nexus.middleware.cache import (
    CacheConfig,
    CacheEntry,
    CacheStats,
    ResponseCacheMiddleware,
    _build_cache_key,
    _generate_etag,
    _parse_cache_control,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scope(
    method: str = "GET",
    path: str = "/api/test",
    query_string: bytes = b"",
    headers: Optional[List[Tuple[bytes, bytes]]] = None,
) -> Dict[str, Any]:
    """Build a minimal ASGI HTTP scope for testing."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
    }


def _make_ws_scope() -> Dict[str, Any]:
    """Build a minimal ASGI WebSocket scope."""
    return {"type": "websocket", "path": "/ws"}


class _DummyApp:
    """ASGI app that returns a configurable response."""

    def __init__(
        self,
        status: int = 200,
        body: bytes = b'{"ok": true}',
        headers: Optional[List[Tuple[bytes, bytes]]] = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = headers or [(b"content-type", b"application/json")]
        self.call_count = 0

    async def __call__(self, scope: Dict, receive: Any, send: Any) -> None:
        self.call_count += 1
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": list(self.headers),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self.body,
            }
        )


class _MessageCollector:
    """Collects ASGI send messages for assertion."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    async def __call__(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        for m in self.messages:
            if m.get("type") == "http.response.start":
                return m["status"]
        return 0

    @property
    def body(self) -> bytes:
        for m in self.messages:
            if m.get("type") == "http.response.body":
                return m.get("body", b"")
        return b""

    @property
    def response_headers(self) -> Dict[bytes, bytes]:
        for m in self.messages:
            if m.get("type") == "http.response.start":
                return dict(m.get("headers", []))
        return {}


async def _do_request(
    mw: ResponseCacheMiddleware,
    method: str = "GET",
    path: str = "/api/test",
    query_string: bytes = b"",
    headers: Optional[List[Tuple[bytes, bytes]]] = None,
) -> _MessageCollector:
    """Run a single request through the middleware and return collected messages."""
    scope = _make_scope(
        method=method, path=path, query_string=query_string, headers=headers
    )
    collector = _MessageCollector()
    await mw(scope, None, collector)
    return collector


# ---------------------------------------------------------------------------
# CacheConfig Tests
# ---------------------------------------------------------------------------


class TestCacheConfig:
    """Test CacheConfig defaults and customization."""

    def test_defaults(self):
        config = CacheConfig()
        assert config.default_ttl == 60
        assert config.max_entries == 1000
        assert config.no_cache_handlers == frozenset()
        assert config.no_cache_paths == frozenset()
        assert config.cacheable_methods == frozenset({"GET", "HEAD"})
        assert config.cacheable_status_codes == frozenset({200, 301})
        assert config.respect_cache_control is True
        assert config.include_query_in_key is True

    def test_custom_ttl(self):
        config = CacheConfig(default_ttl=300)
        assert config.default_ttl == 300

    def test_custom_max_entries(self):
        config = CacheConfig(max_entries=50)
        assert config.max_entries == 50

    def test_custom_no_cache_handlers(self):
        config = CacheConfig(no_cache_handlers=frozenset({"create_user"}))
        assert "create_user" in config.no_cache_handlers

    def test_frozen_immutability(self):
        config = CacheConfig()
        with pytest.raises(AttributeError):
            config.default_ttl = 999


# ---------------------------------------------------------------------------
# CacheEntry Tests
# ---------------------------------------------------------------------------


class TestCacheEntry:
    """Test CacheEntry TTL expiration and age tracking."""

    def test_not_expired_within_ttl(self):
        entry = CacheEntry(
            status=200,
            headers=[],
            body=b"test",
            etag='W/"abc"',
            created_at=time.monotonic(),
            ttl=60,
        )
        assert entry.is_expired is False

    def test_expired_after_ttl(self):
        # Created 100 seconds ago, TTL is 1 second
        entry = CacheEntry(
            status=200,
            headers=[],
            body=b"test",
            etag='W/"abc"',
            created_at=time.monotonic() - 100,
            ttl=1,
        )
        assert entry.is_expired is True

    def test_age_tracking(self):
        entry = CacheEntry(
            status=200,
            headers=[],
            body=b"test",
            etag='W/"abc"',
            created_at=time.monotonic() - 5,
            ttl=60,
        )
        assert entry.age >= 5


# ---------------------------------------------------------------------------
# CacheStats Tests
# ---------------------------------------------------------------------------


class TestCacheStats:
    """Test CacheStats serialization and hit rate calculation."""

    def test_default_values(self):
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0

    def test_to_dict(self):
        stats = CacheStats(hits=10, misses=5)
        d = stats.to_dict()
        assert d["hits"] == 10
        assert d["misses"] == 5
        assert d["total_requests"] == 15
        assert d["hit_rate_percent"] == 66.67

    def test_to_dict_zero_requests(self):
        stats = CacheStats()
        d = stats.to_dict()
        assert d["hit_rate_percent"] == 0.0
        assert d["total_requests"] == 0


# ---------------------------------------------------------------------------
# Helper Function Tests
# ---------------------------------------------------------------------------


class TestGenerateEtag:
    """Test ETag generation from response body."""

    def test_produces_weak_etag(self):
        etag = _generate_etag(b"hello world")
        assert etag.startswith('W/"')
        assert etag.endswith('"')

    def test_deterministic(self):
        assert _generate_etag(b"same content") == _generate_etag(b"same content")

    def test_different_content_different_etag(self):
        assert _generate_etag(b"content a") != _generate_etag(b"content b")

    def test_sha256_based(self):
        body = b"test body"
        expected_prefix = hashlib.sha256(body).hexdigest()[:16]
        etag = _generate_etag(body)
        assert expected_prefix in etag


class TestBuildCacheKey:
    """Test cache key construction."""

    def test_without_query(self):
        assert _build_cache_key("GET", "/api/test", b"") == "GET:/api/test"

    def test_with_query(self):
        assert _build_cache_key("GET", "/api/test", b"page=1") == "GET:/api/test?page=1"

    def test_different_methods_different_keys(self):
        key_get = _build_cache_key("GET", "/api/test", b"")
        key_head = _build_cache_key("HEAD", "/api/test", b"")
        assert key_get != key_head


class TestParseCacheControl:
    """Test Cache-Control header parsing."""

    def test_empty_string(self):
        assert _parse_cache_control("") == {}

    def test_no_cache(self):
        result = _parse_cache_control("no-cache")
        assert "no-cache" in result
        assert result["no-cache"] is None

    def test_no_store(self):
        result = _parse_cache_control("no-store")
        assert "no-store" in result

    def test_max_age(self):
        result = _parse_cache_control("max-age=300")
        assert result["max-age"] == 300

    def test_combined_directives(self):
        result = _parse_cache_control("no-cache, max-age=0, no-store")
        assert "no-cache" in result
        assert "no-store" in result
        assert result["max-age"] == 0

    def test_whitespace_handling(self):
        result = _parse_cache_control("  max-age = 60 , no-cache  ")
        assert result["max-age"] == 60
        assert "no-cache" in result

    def test_non_numeric_value(self):
        result = _parse_cache_control("max-age=abc")
        assert result["max-age"] is None


# ---------------------------------------------------------------------------
# ASGI Middleware Tests — Basic Caching
# ---------------------------------------------------------------------------


class TestBasicCaching:
    """Test core cache hit/miss behavior."""

    @pytest.mark.asyncio
    async def test_first_request_is_cache_miss(self):
        app = _DummyApp(body=b'{"data": "hello"}')
        mw = ResponseCacheMiddleware(app)

        result = await _do_request(mw)
        assert result.status == 200
        assert result.body == b'{"data": "hello"}'
        assert app.call_count == 1
        assert mw.stats.misses == 1

    @pytest.mark.asyncio
    async def test_second_request_is_cache_hit(self):
        app = _DummyApp(body=b'{"data": "hello"}')
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)
        result = await _do_request(mw)

        assert result.status == 200
        assert result.body == b'{"data": "hello"}'
        assert app.call_count == 1  # Only called once
        assert mw.stats.hits == 1
        assert mw.stats.misses == 1

    @pytest.mark.asyncio
    async def test_cache_hit_includes_etag_header(self):
        app = _DummyApp(body=b"test body")
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)
        result = await _do_request(mw)

        headers = result.response_headers
        assert b"etag" in headers
        assert b"x-cache" in headers
        assert headers[b"x-cache"] == b"HIT"

    @pytest.mark.asyncio
    async def test_different_paths_cached_separately(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, path="/api/a")
        await _do_request(mw, path="/api/b")

        assert app.call_count == 2
        assert mw.stats.misses == 2

    @pytest.mark.asyncio
    async def test_query_string_included_in_key_by_default(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, path="/api/test", query_string=b"page=1")
        await _do_request(mw, path="/api/test", query_string=b"page=2")

        assert app.call_count == 2

    @pytest.mark.asyncio
    async def test_query_string_excluded_when_configured(self):
        app = _DummyApp()
        config = CacheConfig(include_query_in_key=False)
        mw = ResponseCacheMiddleware(app, config=config)

        await _do_request(mw, path="/api/test", query_string=b"page=1")
        await _do_request(mw, path="/api/test", query_string=b"page=2")

        assert app.call_count == 1  # Second request was a cache hit


# ---------------------------------------------------------------------------
# Non-cacheable Request Tests
# ---------------------------------------------------------------------------


class TestNonCacheableRequests:
    """Test that non-cacheable requests always pass through."""

    @pytest.mark.asyncio
    async def test_post_not_cached(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, method="POST")
        await _do_request(mw, method="POST")

        assert app.call_count == 2
        assert mw.stats.misses == 0  # POST requests are not counted

    @pytest.mark.asyncio
    async def test_put_not_cached(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, method="PUT")
        await _do_request(mw, method="PUT")

        assert app.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_not_cached(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, method="DELETE")
        await _do_request(mw, method="DELETE")

        assert app.call_count == 2

    @pytest.mark.asyncio
    async def test_head_is_cached_by_default(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, method="HEAD")
        await _do_request(mw, method="HEAD")

        assert app.call_count == 1

    @pytest.mark.asyncio
    async def test_non_200_status_not_cached(self):
        app = _DummyApp(status=404)
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)
        await _do_request(mw)

        assert app.call_count == 2

    @pytest.mark.asyncio
    async def test_301_status_is_cached(self):
        app = _DummyApp(status=301)
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)
        await _do_request(mw)

        assert app.call_count == 1

    @pytest.mark.asyncio
    async def test_websocket_scope_passes_through(self):
        """Non-HTTP scopes are forwarded without any caching logic."""
        call_count = 0

        async def ws_app(scope, receive, send):
            nonlocal call_count
            call_count += 1

        mw = ResponseCacheMiddleware(ws_app)
        ws_scope = _make_ws_scope()
        await mw(ws_scope, None, None)

        assert call_count == 1


# ---------------------------------------------------------------------------
# TTL Expiration Tests
# ---------------------------------------------------------------------------


class TestTTLExpiration:
    """Test that cached entries expire after their TTL."""

    @pytest.mark.asyncio
    async def test_expired_entry_causes_cache_miss(self):
        app = _DummyApp(body=b"fresh")
        config = CacheConfig(default_ttl=1)
        mw = ResponseCacheMiddleware(app, config=config)

        # First request — cache miss, stores entry
        await _do_request(mw)
        assert app.call_count == 1

        # Manually expire the entry by patching its created_at
        with mw._lock:
            for entry in mw._cache.values():
                entry.created_at = time.monotonic() - 100

        # Second request — entry is expired, so it's a cache miss
        await _do_request(mw)
        assert app.call_count == 2
        assert mw.stats.expirations >= 1

    @pytest.mark.asyncio
    async def test_non_expired_entry_is_still_valid(self):
        app = _DummyApp()
        config = CacheConfig(default_ttl=3600)
        mw = ResponseCacheMiddleware(app, config=config)

        await _do_request(mw)
        await _do_request(mw)

        assert app.call_count == 1
        assert mw.stats.hits == 1


# ---------------------------------------------------------------------------
# LRU Eviction Tests
# ---------------------------------------------------------------------------


class TestLRUEviction:
    """Test LRU eviction when cache exceeds max_entries."""

    @pytest.mark.asyncio
    async def test_eviction_when_over_capacity(self):
        app = _DummyApp()
        config = CacheConfig(max_entries=3)
        mw = ResponseCacheMiddleware(app, config=config)

        # Fill cache with 3 entries
        await _do_request(mw, path="/api/a")
        await _do_request(mw, path="/api/b")
        await _do_request(mw, path="/api/c")

        assert mw.stats.current_size == 3

        # Adding a 4th should evict the oldest (/api/a)
        await _do_request(mw, path="/api/d")

        assert mw.stats.current_size == 3
        assert mw.stats.evictions >= 1

        # /api/a should be evicted — cache miss
        result = await _do_request(mw, path="/api/a")
        assert mw.stats.misses >= 2  # Original miss + re-miss

    @pytest.mark.asyncio
    async def test_lru_access_prevents_eviction(self):
        app = _DummyApp()
        config = CacheConfig(max_entries=3)
        mw = ResponseCacheMiddleware(app, config=config)

        # Fill cache: a, b, c
        await _do_request(mw, path="/api/a")
        await _do_request(mw, path="/api/b")
        await _do_request(mw, path="/api/c")

        # Access /api/a to make it recently used
        await _do_request(mw, path="/api/a")

        # Add /api/d — should evict /api/b (oldest after a was refreshed)
        await _do_request(mw, path="/api/d")

        # /api/a should still be cached (it was refreshed)
        app.call_count = 0
        await _do_request(mw, path="/api/a")
        assert app.call_count == 0  # Still cached

        # /api/b should have been evicted
        await _do_request(mw, path="/api/b")
        assert app.call_count == 1  # Cache miss, had to call upstream

    @pytest.mark.asyncio
    async def test_eviction_stats_tracked(self):
        app = _DummyApp()
        config = CacheConfig(max_entries=2)
        mw = ResponseCacheMiddleware(app, config=config)

        await _do_request(mw, path="/api/a")
        await _do_request(mw, path="/api/b")
        await _do_request(mw, path="/api/c")

        assert mw.stats.evictions >= 1


# ---------------------------------------------------------------------------
# ETag Tests
# ---------------------------------------------------------------------------


class TestETag:
    """Test ETag generation and 304 Not Modified responses."""

    @pytest.mark.asyncio
    async def test_etag_match_returns_304(self):
        body = b'{"data": "stable"}'
        app = _DummyApp(body=body)
        mw = ResponseCacheMiddleware(app)

        # First request — populate cache
        first_result = await _do_request(mw)
        assert first_result.status == 200

        # Get the ETag from what would be in the cache
        etag = _generate_etag(body)

        # Second request with If-None-Match
        result = await _do_request(
            mw,
            headers=[(b"if-none-match", etag.encode("latin-1"))],
        )

        assert result.status == 304
        assert result.body == b""
        assert result.response_headers.get(b"x-cache") == b"HIT-ETAG"

    @pytest.mark.asyncio
    async def test_etag_mismatch_returns_full_response(self):
        app = _DummyApp(body=b"some content")
        mw = ResponseCacheMiddleware(app)

        # Populate cache
        await _do_request(mw)

        # Request with non-matching ETag
        result = await _do_request(
            mw,
            headers=[(b"if-none-match", b'W/"nonexistent"')],
        )

        assert result.status == 200
        assert result.body == b"some content"

    @pytest.mark.asyncio
    async def test_etag_wildcard_match(self):
        app = _DummyApp(body=b"content")
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)

        result = await _do_request(
            mw,
            headers=[(b"if-none-match", b"*")],
        )

        assert result.status == 304

    @pytest.mark.asyncio
    async def test_etag_stats_tracked(self):
        body = b"test"
        app = _DummyApp(body=body)
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)

        etag = _generate_etag(body)
        await _do_request(
            mw,
            headers=[(b"if-none-match", etag.encode("latin-1"))],
        )

        assert mw.stats.etag_hits == 1

    def test_etag_matches_comma_separated(self):
        etag = 'W/"abc123"'
        assert ResponseCacheMiddleware._etag_matches(
            f'W/"other", {etag}, W/"another"', etag
        )

    def test_etag_matches_weak_comparison(self):
        # Both weak ETags with same content should match
        assert ResponseCacheMiddleware._etag_matches('W/"abc123"', 'W/"abc123"')


# ---------------------------------------------------------------------------
# Cache-Control Header Tests
# ---------------------------------------------------------------------------


class TestCacheControl:
    """Test Cache-Control header parsing and behavior."""

    @pytest.mark.asyncio
    async def test_no_store_request_bypasses_cache(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(
            mw,
            headers=[(b"cache-control", b"no-store")],
        )
        await _do_request(
            mw,
            headers=[(b"cache-control", b"no-store")],
        )

        assert app.call_count == 2  # Both went to upstream

    @pytest.mark.asyncio
    async def test_no_cache_request_bypasses_cache(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(
            mw,
            headers=[(b"cache-control", b"no-cache")],
        )
        await _do_request(
            mw,
            headers=[(b"cache-control", b"no-cache")],
        )

        assert app.call_count == 2

    @pytest.mark.asyncio
    async def test_client_max_age_caps_ttl(self):
        app = _DummyApp()
        config = CacheConfig(default_ttl=300)
        mw = ResponseCacheMiddleware(app, config=config)

        # Client requests max-age=10, which is less than default 300
        await _do_request(
            mw,
            headers=[(b"cache-control", b"max-age=10")],
        )

        with mw._lock:
            for entry in mw._cache.values():
                assert entry.ttl == 10  # Capped by client max-age

    @pytest.mark.asyncio
    async def test_client_max_age_does_not_exceed_default(self):
        app = _DummyApp()
        config = CacheConfig(default_ttl=60)
        mw = ResponseCacheMiddleware(app, config=config)

        # Client requests max-age=3600, but default is 60
        await _do_request(
            mw,
            headers=[(b"cache-control", b"max-age=3600")],
        )

        with mw._lock:
            for entry in mw._cache.values():
                assert entry.ttl == 60  # Capped by server default

    @pytest.mark.asyncio
    async def test_respect_cache_control_disabled(self):
        app = _DummyApp()
        config = CacheConfig(respect_cache_control=False)
        mw = ResponseCacheMiddleware(app, config=config)

        # no-cache should be ignored when respect_cache_control is False
        await _do_request(
            mw,
            headers=[(b"cache-control", b"no-cache")],
        )
        await _do_request(mw)

        assert app.call_count == 1  # Second request was a cache hit

    @pytest.mark.asyncio
    async def test_response_no_store_prevents_caching(self):
        """If the upstream response has Cache-Control: no-store, don't cache."""
        app = _DummyApp(
            headers=[
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
            ]
        )
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)
        await _do_request(mw)

        assert app.call_count == 2  # Response wasn't cached
        assert mw.stats.current_size == 0


# ---------------------------------------------------------------------------
# Per-Handler Configuration Tests
# ---------------------------------------------------------------------------


class TestPerHandlerConfig:
    """Test per-handler and per-path cache exclusion."""

    @pytest.mark.asyncio
    async def test_no_cache_handler_bypasses_cache(self):
        app = _DummyApp()
        config = CacheConfig(no_cache_handlers=frozenset({"create_user"}))
        mw = ResponseCacheMiddleware(app, config=config)

        await _do_request(mw, path="/api/create_user")
        await _do_request(mw, path="/api/create_user")

        assert app.call_count == 2  # Never cached

    @pytest.mark.asyncio
    async def test_non_excluded_handler_is_cached(self):
        app = _DummyApp()
        config = CacheConfig(no_cache_handlers=frozenset({"create_user"}))
        mw = ResponseCacheMiddleware(app, config=config)

        await _do_request(mw, path="/api/list_users")
        await _do_request(mw, path="/api/list_users")

        assert app.call_count == 1  # Cached

    @pytest.mark.asyncio
    async def test_no_cache_path_bypasses_cache(self):
        app = _DummyApp()
        config = CacheConfig(no_cache_paths=frozenset({"/healthz"}))
        mw = ResponseCacheMiddleware(app, config=config)

        await _do_request(mw, path="/healthz")
        await _do_request(mw, path="/healthz")

        assert app.call_count == 2


# ---------------------------------------------------------------------------
# Cache Invalidation Tests
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    """Test programmatic cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_specific_path(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, path="/api/test")
        assert mw.stats.current_size == 1

        result = mw.invalidate("/api/test")
        assert result is True
        assert mw.stats.current_size == 0
        assert mw.stats.invalidations == 1

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_path(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        result = mw.invalidate("/does/not/exist")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_all(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, path="/api/a")
        await _do_request(mw, path="/api/b")
        await _do_request(mw, path="/api/c")
        assert mw.stats.current_size == 3

        count = mw.invalidate_all()
        assert count == 3
        assert mw.stats.current_size == 0
        assert mw.stats.invalidations == 3

    @pytest.mark.asyncio
    async def test_invalidate_prefix_matching(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw, path="/api/test", query_string=b"page=1")
        await _do_request(mw, path="/api/test", query_string=b"page=2")
        assert mw.stats.current_size == 2

        # Invalidate /api/test should match both query variants
        result = mw.invalidate("/api/test")
        assert result is True
        assert mw.stats.current_size == 0


# ---------------------------------------------------------------------------
# Cache Statistics Tests
# ---------------------------------------------------------------------------


class TestCacheStatistics:
    """Test cache statistics tracking and snapshot isolation."""

    @pytest.mark.asyncio
    async def test_stats_snapshot_is_isolated(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        await _do_request(mw)
        snapshot = mw.stats

        # Further requests should not modify the snapshot
        await _do_request(mw)

        assert snapshot.misses == 1
        assert snapshot.hits == 0
        # But current stats should show the hit
        assert mw.stats.hits == 1

    @pytest.mark.asyncio
    async def test_stats_accumulate_correctly(self):
        app = _DummyApp()
        mw = ResponseCacheMiddleware(app)

        # 3 misses to different paths
        await _do_request(mw, path="/api/a")
        await _do_request(mw, path="/api/b")
        await _do_request(mw, path="/api/c")

        # 3 hits to same paths
        await _do_request(mw, path="/api/a")
        await _do_request(mw, path="/api/b")
        await _do_request(mw, path="/api/c")

        stats = mw.stats
        assert stats.misses == 3
        assert stats.hits == 3
        assert stats.current_size == 3

        d = stats.to_dict()
        assert d["hit_rate_percent"] == 50.0


# ---------------------------------------------------------------------------
# Thread Safety Tests
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Test that concurrent access does not corrupt cache state."""

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self):
        app = _DummyApp()
        config = CacheConfig(max_entries=50)
        mw = ResponseCacheMiddleware(app, config=config)

        errors: List[Exception] = []

        async def make_requests(prefix: str, count: int):
            for i in range(count):
                try:
                    await _do_request(mw, path=f"/api/{prefix}/{i}")
                except Exception as e:
                    errors.append(e)

        # Run multiple concurrent request streams
        await asyncio.gather(
            make_requests("stream_a", 30),
            make_requests("stream_b", 30),
            make_requests("stream_c", 30),
        )

        assert len(errors) == 0
        # Cache should never exceed max_entries
        assert mw.stats.current_size <= 50

    def test_concurrent_invalidation(self):
        """Test that concurrent invalidation is safe."""
        app = _DummyApp()
        config = CacheConfig(max_entries=100)
        mw = ResponseCacheMiddleware(app, config=config)

        # Pre-populate cache directly
        for i in range(50):
            key = f"GET:/api/item/{i}"
            entry = CacheEntry(
                status=200,
                headers=[],
                body=f"item {i}".encode(),
                etag=_generate_etag(f"item {i}".encode()),
                created_at=time.monotonic(),
                ttl=3600,
            )
            with mw._lock:
                mw._cache[key] = entry

        errors: List[Exception] = []

        def invalidate_range(start: int, end: int):
            for i in range(start, end):
                try:
                    mw.invalidate(f"/api/item/{i}")
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=invalidate_range, args=(0, 25)),
            threading.Thread(target=invalidate_range, args=(25, 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert mw.stats.current_size == 0


# ---------------------------------------------------------------------------
# ResponseCapture Tests
# ---------------------------------------------------------------------------


class TestResponseCapture:
    """Test the internal _ResponseCapture helper."""

    def test_captures_start_and_body(self):
        from nexus.middleware.cache import _ResponseCapture

        cap = _ResponseCapture()
        assert cap.is_complete is False

        cap.capture({"type": "http.response.start", "status": 200, "headers": []})
        assert cap.is_complete is False

        cap.capture({"type": "http.response.body", "body": b"hello"})
        assert cap.is_complete is True
        assert cap.status == 200
        assert cap.body == b"hello"

    def test_accumulates_chunked_body(self):
        from nexus.middleware.cache import _ResponseCapture

        cap = _ResponseCapture()
        cap.capture({"type": "http.response.start", "status": 200, "headers": []})
        cap.capture(
            {"type": "http.response.body", "body": b"chunk1", "more_body": True}
        )
        assert cap.is_complete is False

        cap.capture(
            {"type": "http.response.body", "body": b"chunk2", "more_body": False}
        )
        assert cap.is_complete is True
        assert cap.body == b"chunk1chunk2"

    def test_handles_memoryview(self):
        from nexus.middleware.cache import _ResponseCapture

        cap = _ResponseCapture()
        cap.capture({"type": "http.response.start", "status": 200, "headers": []})
        cap.capture({"type": "http.response.body", "body": memoryview(b"data")})
        assert cap.body == b"data"
