# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric cache backends — pluggable storage for product cache entries.

The :class:`FabricCacheBackend` ABC defines the contract used by
:class:`PipelineExecutor`. Two implementations are shipped:

* :class:`InMemoryFabricCacheBackend` — process-local LRU. Replaces the
  three parallel dicts (data/hash/metadata) that the executor used before.
  Suitable for dev mode and single-replica deployments.

* :class:`RedisFabricCacheBackend` — Redis-backed shared cache for
  multi-replica deployments. Stores each entry as a Redis hash, uses a
  Lua CAS script to refuse stale ``run_started_at`` overwrites, exposes a
  metadata-only fast path, and degrades gracefully when Redis is
  unreachable (``fabric_cache_degraded`` gauge flipped, cache miss returned).

Tenant partitioning lives in the cache key construction at the caller
side; this module enforces it via :class:`FabricTenantRequiredError`. The
caller (PipelineExecutor / FabricRuntime) is responsible for raising the
error when a ``multi_tenant=True`` product fails to supply ``tenant_id``.

References:
- ``workspaces/issue-354/02-plans/01-fix-plan.md`` — full design rationale
- ``workspaces/issue-354/04-validate/01-red-team-findings.md`` amendments
  A (tenant plumbing), C (write CAS), D (Redis-outage fallback)
- ``rules/observability.md`` — structured logging contract used here
- ``rules/dataflow-pool.md`` — pool patterns for shared Redis client
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

__all__ = [
    "FabricCacheBackend",
    "FabricTenantRequiredError",
    "InMemoryFabricCacheBackend",
    "RedisFabricCacheBackend",
    "_FabricCacheEntry",
]


# ---------------------------------------------------------------------------
# Errors and dataclasses
# ---------------------------------------------------------------------------


class FabricTenantRequiredError(Exception):
    """Raised when a ``multi_tenant=True`` product is queried without a tenant.

    Per ``workspaces/issue-354/04-validate/01-red-team-findings.md``
    amendment A, the absence of ``tenant_id`` on a multi-tenant product is
    an invariant violation, not an operational failure. Callers must
    propagate the tenant identifier explicitly.
    """


@dataclass(frozen=True)
class _FabricCacheEntry:
    """Immutable cache entry covering data + metadata + content hash.

    Replaces the three parallel dicts (data/hash/metadata) that the
    executor used before. ``run_started_at`` is the wall-clock time the
    pipeline started executing; the Redis backend uses it for write CAS
    so an older writer cannot overwrite a newer entry.
    """

    product_name: str
    tenant_id: Optional[str]
    data_bytes: bytes
    content_hash: str
    metadata: Dict[str, Any]
    cached_at: datetime
    run_started_at: datetime
    schema_version: int = 2
    size_bytes: int = 0


# ---------------------------------------------------------------------------
# URL masking helper (no secrets in logs)
# ---------------------------------------------------------------------------


def _mask_url(url: Optional[str]) -> str:
    """Replace the userinfo section of a URL with ``***``.

    Used in every log line that touches a Redis URL. Returns the original
    string when parsing fails (e.g. ``unix://``) but masks anything that
    looks like ``user:password``.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            netloc = "***@" + (parsed.hostname or "")
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
        return url
    except (ValueError, AttributeError):
        return "<unparseable>"


# ---------------------------------------------------------------------------
# Metric dispatchers (Phase 5.12 — wired to FabricMetrics singleton)
# ---------------------------------------------------------------------------


def _record_cache_error(backend: str, operation: str) -> None:
    """Increment ``fabric_cache_errors_total{backend, operation}``.

    Logs at DEBUG and dispatches to the FabricMetrics singleton. The
    log line is retained so tests can assert via ``caplog`` even when
    prometheus_client is not installed.
    """
    logger.debug(
        "fabric.cache.error_recorded",
        extra={"backend": backend, "operation": operation},
    )
    # Local import avoids a circular dependency between metrics and
    # cache (metrics.py only imports stdlib and prometheus_client).
    from dataflow.fabric.metrics import get_fabric_metrics

    get_fabric_metrics().record_cache_error(backend=backend, operation=operation)


def _set_cache_degraded(backend: str, value: int) -> None:
    """Set ``fabric_cache_degraded{backend}`` to 0 or 1.

    Logs the transition at WARN/INFO and dispatches to the
    FabricMetrics singleton so the gauge is visible at /fabric/metrics.
    """
    if value:
        logger.warning(
            "fabric.cache.degraded.flipped_on",
            extra={"backend": backend, "fabric_cache_degraded": value},
        )
    else:
        logger.info(
            "fabric.cache.degraded.flipped_off",
            extra={"backend": backend, "fabric_cache_degraded": value},
        )

    from dataflow.fabric.metrics import get_fabric_metrics

    get_fabric_metrics().record_cache_degraded(backend=backend, value=value)


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------


class FabricCacheBackend(ABC):
    """Pluggable storage for fabric product cache entries.

    All methods are async so an in-memory implementation, a Redis
    implementation, and any future backend (Memcached, etc.) share the
    same call shape from :class:`PipelineExecutor`.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[_FabricCacheEntry]:
        """Return the cache entry at ``key`` or ``None`` if absent."""

    @abstractmethod
    async def get_hash(self, key: str) -> Optional[str]:
        """Fast path: return the content hash without loading the payload."""

    @abstractmethod
    async def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Fast path: return ``cached_at, content_hash, size_bytes,
        run_started_at`` (and any other metadata fields) without loading
        the payload bytes. Used by ``product_info``/health probes.
        """

    @abstractmethod
    async def set(self, key: str, entry: _FabricCacheEntry) -> bool:
        """Store the entry. Returns ``False`` if a CAS check rejected the
        write (existing entry has a newer ``run_started_at``).
        """

    @abstractmethod
    async def invalidate(self, key: str) -> None:
        """Remove a single key. Idempotent."""

    @abstractmethod
    async def invalidate_all(self, prefix: Optional[str] = None) -> None:
        """Remove every key, or every key matching ``prefix``. Idempotent."""

    @abstractmethod
    async def scan_prefix(self, prefix: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Return ``(relative_key, metadata_dict)`` pairs for every entry
        whose key starts with ``prefix``.

        Metadata-only (no payload bytes) — mirrors the :meth:`get_metadata`
        contract but across multiple keys at once. Used by fabric health
        probes to aggregate parameterized product freshness without
        transferring payload bytes.

        The returned keys are relative to the backend (not the backend's
        internal namespace prefix), so callers can pass them directly to
        :meth:`get` / :meth:`get_metadata` / :meth:`invalidate`.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any backend-side resources (Redis client, etc.)."""


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryFabricCacheBackend(FabricCacheBackend):
    """Process-local LRU cache, async-over-sync.

    Single :class:`OrderedDict` keyed by the caller-supplied cache key.
    The previous executor used three parallel dicts (data, hash, metadata);
    consolidating into one dict guarantees they cannot drift.

    LRU cap: ``max_entries`` (default 10,000) — bounds memory growth for
    high-cardinality parameterized products. Eviction happens on every
    successful ``set``.

    Thread safety: asyncio is single-threaded; ``OrderedDict`` operations
    here are atomic with respect to other awaits because none of these
    methods yields the event loop. The ``async`` annotation exists solely
    to satisfy the ABC contract.
    """

    BACKEND_NAME = "memory"

    def __init__(self, max_entries: int = 10_000) -> None:
        self._store: "OrderedDict[str, _FabricCacheEntry]" = OrderedDict()
        self._max_entries = max_entries

    async def get(self, key: str) -> Optional[_FabricCacheEntry]:
        entry = self._store.get(key)
        if entry is not None:
            self._store.move_to_end(key)
        return entry

    async def get_hash(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        return entry.content_hash if entry is not None else None

    async def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._store.get(key)
        if entry is None:
            return None
        return {
            "cached_at": entry.cached_at,
            "content_hash": entry.content_hash,
            "size_bytes": entry.size_bytes,
            "run_started_at": entry.run_started_at,
            "schema_version": entry.schema_version,
            **entry.metadata,
        }

    async def set(self, key: str, entry: _FabricCacheEntry) -> bool:
        existing = self._store.get(key)
        if existing is not None and existing.run_started_at > entry.run_started_at:
            logger.debug(
                "fabric.cache.cas_rejected",
                extra={
                    "backend": self.BACKEND_NAME,
                    "key": key,
                    "existing_run_started_at": existing.run_started_at.isoformat(),
                    "incoming_run_started_at": entry.run_started_at.isoformat(),
                },
            )
            return False

        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = entry

        # LRU eviction
        while len(self._store) > self._max_entries:
            evicted_key, _ = self._store.popitem(last=False)
            logger.debug(
                "fabric.cache.evicted",
                extra={
                    "backend": self.BACKEND_NAME,
                    "evicted_key": evicted_key,
                    "max_entries": self._max_entries,
                },
            )
        return True

    async def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    async def invalidate_all(self, prefix: Optional[str] = None) -> None:
        if prefix is None:
            self._store.clear()
            return
        # Iterate over a snapshot since we're mutating
        for key in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(key, None)

    async def scan_prefix(self, prefix: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Return metadata for every stored key that starts with ``prefix``.

        Used by fabric health probes to aggregate parameterized product
        freshness across every param combination without loading payload
        bytes. Iterates the OrderedDict without mutating it.
        """
        results: List[Tuple[str, Dict[str, Any]]] = []
        for key, entry in self._store.items():
            if not key.startswith(prefix):
                continue
            metadata: Dict[str, Any] = {
                "cached_at": entry.cached_at,
                "content_hash": entry.content_hash,
                "size_bytes": entry.size_bytes,
                "run_started_at": entry.run_started_at,
                "schema_version": entry.schema_version,
                **entry.metadata,
            }
            results.append((key, metadata))
        return results

    async def close(self) -> None:
        # Nothing to release.
        return None

    # ------------------------------------------------------------------
    # Test/debug helpers (not part of the ABC contract)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

# Lua CAS script: refuses to write when the existing run_started_at is
# strictly newer than the incoming run_started_at. We always write a
# fully-formed hash so partial writes cannot leave the entry inconsistent.
#
# KEYS[1] = full Redis key
# ARGV    = field/value pairs followed by the TTL seconds value as the
#           final argument. The Lua loop below extracts the TTL.
#
# Returns 1 on write, 0 on CAS reject.
_REDIS_CAS_SET_LUA = """
local key = KEYS[1]
local incoming_ts = ARGV[1]
local ttl = tonumber(ARGV[#ARGV])

local existing_ts = redis.call('HGET', key, 'run_started_at')
if existing_ts and existing_ts > incoming_ts then
    return 0
end

-- Build HMSET argv from ARGV[2 .. #ARGV-1]
local fields = {}
for i = 2, #ARGV - 1 do
    fields[#fields + 1] = ARGV[i]
end
redis.call('DEL', key)
if #fields > 0 then
    redis.call('HSET', key, unpack(fields))
end
if ttl and ttl > 0 then
    redis.call('EXPIRE', key, ttl)
end
return 1
"""


class RedisFabricCacheBackend(FabricCacheBackend):
    """Redis-backed product cache for multi-replica deployments.

    Stores each cache entry as a Redis HASH with these fields:

    * ``data_bytes`` — payload bytes (msgpack or json depending on the
      caller's serializer choice; the backend is opaque)
    * ``content_hash`` — sha256 hex digest
    * ``cached_at`` — ISO-8601 string in UTC
    * ``run_started_at`` — ISO-8601 string used for write CAS
    * ``metadata_json`` — JSON-encoded metadata dict
    * ``schema_version`` — integer (currently ``2``)
    * ``size_bytes`` — payload size

    Key shape:

    * Without tenant: ``{key_prefix}:product:{instance_name}:{product_name}``
    * With tenant: ``{key_prefix}:product:{instance_name}:{tenant_id}:{product_name}``

    The caller is responsible for building the cache key string; the
    backend treats it as opaque.

    Resilience:

    * Every operation is wrapped in try/except for
      ``redis.ConnectionError``, ``redis.TimeoutError``,
      ``asyncio.TimeoutError``, and ``OSError``.
    * On error: ``get``/``get_metadata`` return ``None`` (cache miss),
      ``set`` returns ``False`` (treat as not-written), ``invalidate``
      no-ops with WARN.
    * The ``fabric_cache_degraded{backend=redis}`` gauge flips to ``1``
      on first error and back to ``0`` on first success.
    """

    BACKEND_NAME = "redis"

    def __init__(
        self,
        redis_client: Any,
        key_prefix: str = "fabric",
        instance_name: str = "default",
        ttl_seconds: int = 3600,
        redis_url_for_logging: Optional[str] = None,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._instance_name = instance_name
        self._ttl_seconds = ttl_seconds
        self._url_masked = _mask_url(redis_url_for_logging)
        self._degraded: bool = False
        self._cas_script_sha: Optional[str] = None
        logger.debug(
            "fabric.cache.redis_backend.constructed",
            extra={
                "backend": self.BACKEND_NAME,
                "key_prefix": key_prefix,
                "instance_name": instance_name,
                "ttl_seconds": ttl_seconds,
                "redis_url_masked": self._url_masked,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _full_key(self, key: str) -> str:
        return f"{self._key_prefix}:product:{self._instance_name}:{key}"

    def _on_redis_error(self, operation: str, error: BaseException) -> None:
        """Log + flip degraded gauge on a Redis exception."""
        logger.warning(
            "fabric.cache.redis_unreachable",
            extra={
                "backend": self.BACKEND_NAME,
                "operation": operation,
                "error_class": type(error).__name__,
                "error_message": str(error),
                "redis_url_masked": self._url_masked,
            },
        )
        _record_cache_error(self.BACKEND_NAME, operation)
        if not self._degraded:
            self._degraded = True
            _set_cache_degraded(self.BACKEND_NAME, 1)

    def _on_redis_success(self) -> None:
        """Flip the degraded gauge back to 0 on the first post-error success."""
        if self._degraded:
            self._degraded = False
            _set_cache_degraded(self.BACKEND_NAME, 0)

    async def _ensure_cas_script(self) -> str:
        """Lazy-load the Lua CAS script and cache its SHA."""
        sha = self._cas_script_sha
        if sha is None:
            loaded = await self._redis.script_load(_REDIS_CAS_SET_LUA)
            sha = str(loaded) if not isinstance(loaded, str) else loaded
            self._cas_script_sha = sha
        return sha

    @staticmethod
    def _decode(value: Any) -> Optional[str]:
        """Decode a Redis hash value (bytes or str) to ``str``."""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    @staticmethod
    def _decode_int(value: Any, default: int = 0) -> int:
        decoded = RedisFabricCacheBackend._decode(value)
        if decoded is None:
            return default
        try:
            return int(decoded)
        except ValueError:
            return default

    @staticmethod
    def _parse_iso(value: Any) -> Optional[datetime]:
        decoded = RedisFabricCacheBackend._decode(value)
        if decoded is None:
            return None
        try:
            dt = datetime.fromisoformat(decoded)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    # ------------------------------------------------------------------
    # ABC implementation
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[_FabricCacheEntry]:
        full_key = self._full_key(key)
        try:
            raw = await self._redis.hgetall(full_key)
        except (
            asyncio.TimeoutError,
            OSError,
        ) as exc:
            self._on_redis_error("get", exc)
            return None
        except Exception as exc:
            if _is_redis_runtime_error(exc):
                self._on_redis_error("get", exc)
                return None
            raise

        if not raw:
            return None

        # Normalize keys for clients that return bytes
        decoded_raw: Dict[str, Any] = {}
        for k, v in raw.items():
            decoded_raw[self._decode(k) or ""] = v

        data_bytes = decoded_raw.get("data_bytes")
        if isinstance(data_bytes, str):
            data_bytes = data_bytes.encode("utf-8")
        if not isinstance(data_bytes, (bytes, bytearray)):
            return None

        cached_at = self._parse_iso(decoded_raw.get("cached_at"))
        run_started_at = self._parse_iso(decoded_raw.get("run_started_at"))
        if cached_at is None or run_started_at is None:
            return None

        metadata_json = self._decode(decoded_raw.get("metadata_json")) or "{}"
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            metadata = {}

        # product_name and tenant_id are encoded back so callers do not
        # need a separate lookup. They live in the metadata when present.
        product_name = metadata.pop("__product_name__", "")
        tenant_id = metadata.pop("__tenant_id__", None)

        entry = _FabricCacheEntry(
            product_name=product_name,
            tenant_id=tenant_id,
            data_bytes=bytes(data_bytes),
            content_hash=self._decode(decoded_raw.get("content_hash")) or "",
            metadata=metadata,
            cached_at=cached_at,
            run_started_at=run_started_at,
            schema_version=self._decode_int(decoded_raw.get("schema_version"), 2),
            size_bytes=self._decode_int(decoded_raw.get("size_bytes"), 0),
        )
        self._on_redis_success()
        return entry

    async def get_hash(self, key: str) -> Optional[str]:
        full_key = self._full_key(key)
        try:
            value = await self._redis.hget(full_key, "content_hash")
        except (asyncio.TimeoutError, OSError) as exc:
            self._on_redis_error("get_hash", exc)
            return None
        except Exception as exc:
            if _is_redis_runtime_error(exc):
                self._on_redis_error("get_hash", exc)
                return None
            raise

        self._on_redis_success()
        return self._decode(value)

    async def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        full_key = self._full_key(key)
        try:
            values = await self._redis.hmget(
                full_key,
                "cached_at",
                "content_hash",
                "size_bytes",
                "run_started_at",
                "schema_version",
            )
        except (asyncio.TimeoutError, OSError) as exc:
            self._on_redis_error("get_metadata", exc)
            return None
        except Exception as exc:
            if _is_redis_runtime_error(exc):
                self._on_redis_error("get_metadata", exc)
                return None
            raise

        cached_at_raw, content_hash, size_bytes, run_started_at_raw, schema_version = (
            values
        )
        if cached_at_raw is None:
            self._on_redis_success()
            return None

        cached_at = self._parse_iso(cached_at_raw)
        run_started_at = self._parse_iso(run_started_at_raw)
        if cached_at is None or run_started_at is None:
            self._on_redis_success()
            return None

        result = {
            "cached_at": cached_at,
            "content_hash": self._decode(content_hash) or "",
            "size_bytes": self._decode_int(size_bytes, 0),
            "run_started_at": run_started_at,
            "schema_version": self._decode_int(schema_version, 2),
        }
        self._on_redis_success()
        return result

    async def set(self, key: str, entry: _FabricCacheEntry) -> bool:
        full_key = self._full_key(key)

        # Encode metadata so we can round-trip product_name and tenant_id
        # without storing them as separate fields.
        metadata_with_hidden = dict(entry.metadata)
        if entry.product_name:
            metadata_with_hidden["__product_name__"] = entry.product_name
        if entry.tenant_id is not None:
            metadata_with_hidden["__tenant_id__"] = entry.tenant_id
        try:
            metadata_json = json.dumps(metadata_with_hidden, default=str)
        except (TypeError, ValueError):
            # Metadata that cannot serialize is a programmer error — fall
            # back to an empty object so the entry still writes.
            logger.warning(
                "fabric.cache.metadata_serialize_failed",
                extra={
                    "backend": self.BACKEND_NAME,
                    "key": key,
                },
            )
            metadata_json = "{}"

        run_started_at_iso = entry.run_started_at.isoformat()
        cached_at_iso = entry.cached_at.isoformat()

        # Argv layout: incoming run_started_at, then field/value pairs,
        # then ttl as the final element.
        argv: list[Any] = [
            run_started_at_iso,
            "data_bytes",
            entry.data_bytes,
            "content_hash",
            entry.content_hash,
            "cached_at",
            cached_at_iso,
            "run_started_at",
            run_started_at_iso,
            "metadata_json",
            metadata_json,
            "schema_version",
            str(entry.schema_version),
            "size_bytes",
            str(entry.size_bytes),
            self._ttl_seconds,
        ]

        try:
            sha = await self._ensure_cas_script()
            try:
                result = await self._redis.evalsha(sha, 1, full_key, *argv)
            except Exception as inner:
                # Some Redis client versions raise NoScriptError when the
                # script is evicted from the script cache; reload and retry.
                if _is_no_script_error(inner):
                    self._cas_script_sha = None
                    sha = await self._ensure_cas_script()
                    result = await self._redis.evalsha(sha, 1, full_key, *argv)
                else:
                    raise
        except (asyncio.TimeoutError, OSError) as exc:
            self._on_redis_error("set", exc)
            return False
        except Exception as exc:
            if _is_redis_runtime_error(exc):
                self._on_redis_error("set", exc)
                return False
            raise

        self._on_redis_success()

        try:
            written = int(result) == 1
        except (TypeError, ValueError):
            written = bool(result)

        if not written:
            logger.debug(
                "fabric.cache.cas_rejected",
                extra={
                    "backend": self.BACKEND_NAME,
                    "key": key,
                    "incoming_run_started_at": run_started_at_iso,
                },
            )
        return written

    async def invalidate(self, key: str) -> None:
        full_key = self._full_key(key)
        try:
            await self._redis.delete(full_key)
        except (asyncio.TimeoutError, OSError) as exc:
            self._on_redis_error("invalidate", exc)
            return
        except Exception as exc:
            if _is_redis_runtime_error(exc):
                self._on_redis_error("invalidate", exc)
                return
            raise
        self._on_redis_success()

    async def invalidate_all(self, prefix: Optional[str] = None) -> None:
        # Always scope to our key prefix; ``prefix`` further narrows.
        match = f"{self._key_prefix}:product:{self._instance_name}:"
        if prefix:
            match = f"{match}{prefix}"
        match = f"{match}*"

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor, match=match, count=200
                )
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except (asyncio.TimeoutError, OSError) as exc:
            self._on_redis_error("invalidate_all", exc)
            return
        except Exception as exc:
            if _is_redis_runtime_error(exc):
                self._on_redis_error("invalidate_all", exc)
                return
            raise
        self._on_redis_success()

    async def scan_prefix(self, prefix: str) -> List[Tuple[str, Dict[str, Any]]]:
        """SCAN + HMGET metadata for every key starting with ``prefix``.

        Uses Redis SCAN (not KEYS) for non-blocking iteration, followed by
        per-key HMGET for metadata-only fields. Returns relative keys (the
        backend's internal namespace prefix is stripped) so callers can
        pass them to :meth:`get` / :meth:`get_metadata` directly.
        """
        namespace = f"{self._key_prefix}:product:{self._instance_name}:"
        match = f"{namespace}{prefix}*"
        results: List[Tuple[str, Dict[str, Any]]] = []
        keys_found: List[bytes | str] = []

        try:
            cursor = 0
            while True:
                cursor, batch = await self._redis.scan(
                    cursor=cursor, match=match, count=200
                )
                if batch:
                    keys_found.extend(batch)
                if cursor == 0:
                    break
        except (asyncio.TimeoutError, OSError) as exc:
            self._on_redis_error("scan_prefix", exc)
            return results
        except Exception as exc:
            if _is_redis_runtime_error(exc):
                self._on_redis_error("scan_prefix", exc)
                return results
            raise

        for full_key_raw in keys_found:
            full_key = self._decode(full_key_raw) or ""
            if not full_key.startswith(namespace):
                continue
            relative_key = full_key[len(namespace) :]
            try:
                values = await self._redis.hmget(
                    full_key,
                    "cached_at",
                    "content_hash",
                    "size_bytes",
                    "run_started_at",
                    "schema_version",
                )
            except (asyncio.TimeoutError, OSError) as exc:
                self._on_redis_error("scan_prefix", exc)
                return results
            except Exception as exc:
                if _is_redis_runtime_error(exc):
                    self._on_redis_error("scan_prefix", exc)
                    return results
                raise

            (
                cached_at_raw,
                content_hash,
                size_bytes,
                run_started_at_raw,
                schema_version,
            ) = values
            cached_at = self._parse_iso(cached_at_raw)
            run_started_at = self._parse_iso(run_started_at_raw)
            if cached_at is None or run_started_at is None:
                # Entry was evicted between SCAN and HMGET, or the hash
                # is malformed — skip it.
                continue
            metadata: Dict[str, Any] = {
                "cached_at": cached_at,
                "content_hash": self._decode(content_hash) or "",
                "size_bytes": self._decode_int(size_bytes, 0),
                "run_started_at": run_started_at,
                "schema_version": self._decode_int(schema_version, 2),
            }
            results.append((relative_key, metadata))

        self._on_redis_success()
        return results

    async def close(self) -> None:
        # The Redis client is owned by FabricRuntime; do NOT close it
        # here. The runtime closes the shared client during stop().
        return None

    # ------------------------------------------------------------------
    # Test/debug accessors
    # ------------------------------------------------------------------

    @property
    def degraded(self) -> bool:
        return self._degraded


# ---------------------------------------------------------------------------
# Redis exception class detection
# ---------------------------------------------------------------------------
#
# We use a class-name match so test fakes that raise their own
# ConnectionError/TimeoutError subclasses route through the same fallback
# path without an isinstance chain that depends on the redis import.


def _is_redis_runtime_error(exc: BaseException) -> bool:
    """Return True for Redis connectivity/timeout errors.

    Catches anything from the ``redis`` package whose name ends with
    ``ConnectionError``, ``TimeoutError``, or ``BusyLoadingError``, plus
    any standard ``ConnectionError`` / ``TimeoutError``.
    """
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    name = type(exc).__name__
    if name.endswith("ConnectionError"):
        return True
    if name.endswith("TimeoutError"):
        return True
    if name.endswith("BusyLoadingError"):
        return True
    return False


def _is_no_script_error(exc: BaseException) -> bool:
    """Return True when Redis tells us the Lua script is not in the cache."""
    name = type(exc).__name__
    if name == "NoScriptError":
        return True
    msg = str(exc).upper()
    return "NOSCRIPT" in msg
