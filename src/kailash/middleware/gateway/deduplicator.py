"""Request deduplication with fingerprinting and caching.

This module provides:
- Request fingerprinting for deduplication
- Idempotency key support
- Time-window based detection
- Result caching for duplicate requests
"""

import asyncio
import datetime as dt
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    """Cached response for duplicate request."""

    request_fingerprint: str
    idempotency_key: Optional[str]
    response_data: Dict[str, Any]
    status_code: int
    headers: Dict[str, str]
    created_at: datetime
    request_count: int = 1
    last_accessed: datetime = None

    def __post_init__(self):
        if not self.last_accessed:
            self.last_accessed = self.created_at

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cached response is expired."""
        # Handle both timezone-aware and naive datetimes
        created_at = self.created_at
        if created_at.tzinfo is None:
            # Assume naive datetime is UTC
            created_at = created_at.replace(tzinfo=dt.UTC)

        age = (datetime.now(dt.UTC) - created_at).total_seconds()
        return age > ttl_seconds

    def to_response(self) -> Dict[str, Any]:
        """Convert to response format."""
        return {
            "data": self.response_data,
            "status_code": self.status_code,
            "headers": self.headers,
            "cached": True,
            "cache_age_seconds": (
                datetime.now(dt.UTC)
                - (
                    self.created_at.replace(tzinfo=dt.UTC)
                    if self.created_at.tzinfo is None
                    else self.created_at
                )
            ).total_seconds(),
        }


class RequestFingerprinter:
    """Creates unique fingerprints for requests."""

    @staticmethod
    def create_fingerprint(
        method: str,
        path: str,
        query_params: Dict[str, str],
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_headers: Optional[Set[str]] = None,
    ) -> str:
        """Create a unique fingerprint for the request."""
        # Build fingerprint components
        components = {
            "method": method.upper(),
            "path": path,
            "query": RequestFingerprinter._normalize_params(query_params),
        }

        # Include body if present
        if body:
            components["body"] = RequestFingerprinter._normalize_body(body)

        # Include specific headers if requested
        if headers and include_headers:
            header_values = {
                k: v
                for k, v in headers.items()
                if k.lower() in {h.lower() for h in include_headers}
            }
            if header_values:
                components["headers"] = header_values

        # Create stable JSON representation
        fingerprint_data = json.dumps(components, sort_keys=True)

        # Create hash
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()

    @staticmethod
    def _normalize_params(params: Dict[str, str]) -> Dict[str, str]:
        """Normalize query parameters."""
        # Sort by key and handle empty values
        return {k: v for k, v in sorted(params.items()) if v is not None and v != ""}

    @staticmethod
    def _normalize_body(body: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize request body."""

        # Remove null values and sort keys
        def clean_dict(d):
            if isinstance(d, dict):
                return {k: clean_dict(v) for k, v in sorted(d.items()) if v is not None}
            elif isinstance(d, list):
                return [clean_dict(item) for item in d]
            else:
                return d

        return clean_dict(body)


class RequestDeduplicator:
    """Deduplicates requests using fingerprinting and idempotency keys."""

    def __init__(
        self,
        ttl_seconds: int = 3600,  # 1 hour default
        max_cache_size: int = 10000,
        include_headers: Optional[Set[str]] = None,
        storage_backend: Optional[Any] = None,  # For persistent storage
    ):
        """Initialize deduplicator."""
        self.ttl_seconds = ttl_seconds
        self.max_cache_size = max_cache_size
        self.include_headers = include_headers or set()
        self.storage_backend = storage_backend

        # In-memory cache (LRU)
        self._cache: OrderedDict[str, CachedResponse] = OrderedDict()
        self._idempotency_cache: Dict[str, str] = {}  # idempotency_key -> fingerprint
        self._lock = asyncio.Lock()

        # Metrics
        self.hit_count = 0
        self.miss_count = 0
        self.eviction_count = 0

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def check_duplicate(
        self,
        method: str,
        path: str,
        query_params: Dict[str, str],
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Check if request is a duplicate and return cached response."""
        # Get request fingerprint
        fingerprint = RequestFingerprinter.create_fingerprint(
            method=method,
            path=path,
            query_params=query_params,
            body=body,
            headers=headers,
            include_headers=self.include_headers,
        )

        async with self._lock:
            # Check idempotency key first
            if idempotency_key:
                if idempotency_key in self._idempotency_cache:
                    cached_fingerprint = self._idempotency_cache[idempotency_key]
                    if cached_fingerprint != fingerprint:
                        # Same idempotency key but different request
                        raise ValueError(
                            f"Idempotency key {idempotency_key} used with different request"
                        )
                    fingerprint = cached_fingerprint

            # Check cache
            if fingerprint in self._cache:
                cached = self._cache[fingerprint]

                # Check if expired
                if cached.is_expired(self.ttl_seconds):
                    # Remove expired entry
                    del self._cache[fingerprint]
                    if cached.idempotency_key:
                        del self._idempotency_cache[cached.idempotency_key]
                    self.miss_count += 1
                    return None

                # Move to end (LRU)
                self._cache.move_to_end(fingerprint)

                # Update access info
                cached.request_count += 1
                cached.last_accessed = datetime.now(dt.UTC)

                self.hit_count += 1

                logger.info(
                    f"Duplicate request detected: {method} {path} "
                    f"(fingerprint: {fingerprint[:8]}..., count: {cached.request_count})"
                )

                return cached.to_response()

            # Check persistent storage if available
            if self.storage_backend:
                stored = await self._check_storage(fingerprint)
                if stored:
                    # Add to cache
                    self._add_to_cache(fingerprint, stored, idempotency_key)
                    self.hit_count += 1
                    return stored.to_response()

            self.miss_count += 1
            return None

    async def cache_response(
        self,
        method: str,
        path: str,
        query_params: Dict[str, str],
        body: Optional[Dict[str, Any]],
        headers: Optional[Dict[str, str]],
        idempotency_key: Optional[str],
        response_data: Dict[str, Any],
        status_code: int = 200,
        response_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Cache a response for deduplication."""
        # Only cache successful responses by default
        if status_code >= 400:
            return

        fingerprint = RequestFingerprinter.create_fingerprint(
            method=method,
            path=path,
            query_params=query_params,
            body=body,
            headers=headers,
            include_headers=self.include_headers,
        )

        cached_response = CachedResponse(
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            response_data=response_data,
            status_code=status_code,
            headers=response_headers or {},
            created_at=datetime.now(dt.UTC),
        )

        async with self._lock:
            self._add_to_cache(fingerprint, cached_response, idempotency_key)

        # Store in persistent storage if available
        if self.storage_backend:
            asyncio.create_task(self._store_response(fingerprint, cached_response))

        logger.debug(
            f"Cached response for {method} {path} (fingerprint: {fingerprint[:8]}...)"
        )

    def _add_to_cache(
        self,
        fingerprint: str,
        response: CachedResponse,
        idempotency_key: Optional[str],
    ) -> None:
        """Add response to cache with LRU eviction."""
        # Evict oldest if at capacity
        while len(self._cache) >= self.max_cache_size:
            oldest_key, oldest_value = self._cache.popitem(last=False)
            if oldest_value.idempotency_key:
                del self._idempotency_cache[oldest_value.idempotency_key]
            self.eviction_count += 1
            logger.debug(f"Evicted cached response: {oldest_key[:8]}...")

        # Add to cache
        self._cache[fingerprint] = response

        # Add idempotency mapping
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = fingerprint

    async def _check_storage(self, fingerprint: str) -> Optional[CachedResponse]:
        """Check persistent storage for cached response."""
        try:
            data = await self.storage_backend.get(f"dedup:{fingerprint}")
            if data:
                return CachedResponse(**data)
        except Exception as e:
            logger.error(f"Failed to check storage for {fingerprint}: {e}")
        return None

    async def _store_response(self, fingerprint: str, response: CachedResponse) -> None:
        """Store response in persistent storage."""
        try:
            data = {
                "request_fingerprint": response.request_fingerprint,
                "idempotency_key": response.idempotency_key,
                "response_data": response.response_data,
                "status_code": response.status_code,
                "headers": response.headers,
                "created_at": response.created_at.isoformat(),
                "request_count": response.request_count,
                "last_accessed": response.last_accessed.isoformat(),
            }
            await self.storage_backend.set(
                f"dedup:{fingerprint}",
                data,
                ttl=self.ttl_seconds,
            )
        except Exception as e:
            logger.error(f"Failed to store response for {fingerprint}: {e}")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _cleanup_expired(self) -> None:
        """Remove expired cache entries."""
        async with self._lock:
            expired_keys = []

            for fingerprint, cached in self._cache.items():
                if cached.is_expired(self.ttl_seconds):
                    expired_keys.append(fingerprint)

            for key in expired_keys:
                cached = self._cache.pop(key)
                if cached.idempotency_key:
                    self._idempotency_cache.pop(cached.idempotency_key, None)

            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        total_requests = self.hit_count + self.miss_count
        hit_rate = self.hit_count / total_requests if total_requests > 0 else 0.0

        return {
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": hit_rate,
            "cache_size": len(self._cache),
            "eviction_count": self.eviction_count,
            "idempotency_keys": len(self._idempotency_cache),
            "ttl_seconds": self.ttl_seconds,
        }

    async def close(self) -> None:
        """Close deduplicator and cleanup."""
        self._cleanup_task.cancel()
        try:
            await self._cleanup_task
        except asyncio.CancelledError:
            pass
