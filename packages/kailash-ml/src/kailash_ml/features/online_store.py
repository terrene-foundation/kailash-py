# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``OnlineFeatureStore`` — Redis-backed online serving adapter (FM2 Wave-3 Shard C).

Graduates the online surface deferred at ``specs/ml-feature-store.md §11.4a``.
1.0+ ships the *offline* feature store (DataFlow-backed, point-in-time-correct
:class:`~kailash_ml.features.store.FeatureStore`). This module adds the *online*
serving tier: a low-latency key/value cache keyed by the SAME canonical
tenant-scoped cache key the offline store already emits, so a feature row
materialised offline can be served online with **byte-identical key parity**.

**Framework-first (``rules/framework-first.md``).** This composes
``redis.asyncio`` — the SDK's own Redis-client pattern (mirrors
``src/kailash/events/backends.py::RedisStreamsEventBackend``). It does NOT
hand-roll a bespoke connection pool: ``redis.asyncio.from_url`` owns pooling,
reconnection, and timeouts.

**Online/offline key parity (spec §5 / §9).** Every entry is keyed via the
EXISTING :func:`~kailash_ml.features.cache_keys.make_feature_cache_key`
(``kailash_ml:{v}:{tenant}:feature:{schema}:{version}:{row_key}``). The helper
is REUSED, never re-derived — so an offline write and an online write for the
same ``(tenant, schema, version, entity)`` land on the same key, and a key-space
version bump patches one helper for both surfaces.

**Tenant isolation (``rules/tenant-isolation.md`` Rule 1/2).** Because the key
embeds ``tenant_id`` (validated by ``make_feature_cache_key`` → raises
:class:`~kailash_ml.errors.TenantRequiredError` on a missing / forbidden
tenant), tenant A's serve never reads tenant B's rows: their keys differ in the
second dimension. There is no cross-tenant read surface in this adapter.

**Unavailability (``rules/zero-tolerance.md`` Rule 3).** A backend-down condition
(connection refused, DNS failure, socket / command timeout) is wrapped in the
typed :class:`~kailash_ml.errors.OnlineStoreUnavailableError` at the raise site —
never a bare ``redis.ConnectionError`` / ``TimeoutError``. The raise-site message
masks the Redis URL (``scheme://***@host:port/db``) so credentials embedded in
the connection string never reach a log line (``rules/observability.md`` Rule 6 +
``rules/security.md`` § "No secrets in logs").

**Optional dependency (``rules/dependencies.md`` § "Optional Extras with Loud
Failure").** ``redis`` is the ``[online-store]`` extra. Constructing an
:class:`OnlineFeatureStore` without it raises a loud, actionable ``ImportError``
naming the extra — NO silent ``None`` fallback.

See ``specs/ml-feature-store.md §11.4`` / §11.4a (online surface — now shipped).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from datetime import time as _time
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import urlsplit, urlunsplit

import polars as pl
from kailash_ml.errors import OnlineStoreUnavailableError
from kailash_ml.features.cache_keys import make_feature_cache_key, validate_tenant_id
from kailash_ml.features.schema import FeatureSchema

if TYPE_CHECKING:  # avoid importing the optional redis dep on type-only paths
    import redis.asyncio as _redis_async_t

__all__ = ["OnlineFeatureStore"]

logger = logging.getLogger(__name__)

#: Default Redis URL when neither ``url`` nor ``ONLINE_FEATURE_STORE_REDIS_URL``
#: is supplied — mirrors the events-backend default (``backends.py``).
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _mask_redis_url(url: str) -> str:
    """Mask credentials in a Redis URL for log / error surfaces.

    Canonical form per ``rules/observability.md`` Rule 6.2:
    ``scheme://***@host[:port][/path]``. On a parse failure returns a grep-able
    sentinel distinct from a successful mask (Rule 6.1) so triage can tell
    "masked OK" apart from "masker bailed".
    """
    try:
        parts = urlsplit(url)
    except Exception:
        return "<unparseable redis url>"
    if not parts.scheme or not parts.hostname:
        return "<unparseable redis url>"
    host = parts.hostname
    netloc = f"***@{host}"
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _json_default(obj: Any) -> Any:
    """Serialize the non-JSON-native types feature rows may carry."""
    if isinstance(obj, (datetime, date, _time)):
        return obj.isoformat()
    raise TypeError(f"unserializable feature value of type {type(obj).__name__}")


class OnlineFeatureStore:
    """[P1] Redis-backed online feature serving (FM2 Wave-3 Shard C).

    Composes ``redis.asyncio`` (``rules/framework-first.md`` — the SDK's own
    Redis-client pattern, NOT a hand-rolled pool). Every entry is keyed via the
    canonical tenant-scoped :func:`make_feature_cache_key`, so online and offline
    surfaces share one key space (spec §5 / §9).

    Parameters
    ----------
    url:
        Redis connection URL (``redis://[:password@]host:port/db``). When
        ``None`` the adapter reads ``ONLINE_FEATURE_STORE_REDIS_URL`` from the
        environment, then falls back to ``redis://localhost:6379/0``.
    default_ttl_seconds:
        Optional default TTL (seconds) applied to every populated key when the
        per-call ``ttl_seconds`` is omitted. ``None`` (the default) means keys
        do not expire unless a per-call TTL is supplied.

    Raises
    ------
    ImportError
        The ``redis`` package is not installed. Install the optional extra:
        ``pip install 'kailash-ml[online-store]'``. NO silent ``None`` fallback
        (``rules/dependencies.md`` § "Optional Extras with Loud Failure").
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        default_ttl_seconds: int | None = None,
    ) -> None:
        try:
            import redis.asyncio as _redis_async
        except ImportError as exc:  # pragma: no cover - exercised w/o the extra
            raise ImportError(
                "OnlineFeatureStore requires the 'redis' package — install the "
                "online-store extra: pip install 'kailash-ml[online-store]'. "
                "The online feature-serving surface (specs/ml-feature-store.md "
                "§11.4a) composes redis.asyncio; there is no silent fallback."
            ) from exc
        import os

        self._redis_async = _redis_async
        self._url = (
            url
            or os.environ.get("ONLINE_FEATURE_STORE_REDIS_URL")
            or _DEFAULT_REDIS_URL
        )
        self._masked_url = _mask_redis_url(self._url)
        if default_ttl_seconds is not None:
            if isinstance(default_ttl_seconds, bool) or not isinstance(
                default_ttl_seconds, int
            ):
                raise TypeError(
                    "OnlineFeatureStore(default_ttl_seconds=...) must be int, "
                    f"got {type(default_ttl_seconds).__name__}"
                )
            if default_ttl_seconds < 1:
                raise ValueError(
                    "OnlineFeatureStore(default_ttl_seconds=...) must be >= 1, "
                    f"got {default_ttl_seconds}"
                )
        self._default_ttl = default_ttl_seconds
        # redis.asyncio.from_url is lazy — it does NOT connect until first
        # command, so a bad host surfaces at get/populate time (wrapped below),
        # NOT at construction. Mirrors backends.py::RedisStreamsEventBackend.
        self._client: "_redis_async_t.Redis" = _redis_async.from_url(
            self._url, decode_responses=True
        )

    # ------------------------------------------------------------------
    # Key parity (REUSE make_feature_cache_key — never re-derive)
    # ------------------------------------------------------------------

    def _key(self, schema: FeatureSchema, *, tenant_id: str, entity_id: str) -> str:
        """Canonical tenant-scoped key for an entity's online feature row.

        Delegates to :func:`make_feature_cache_key` (spec §5.1) so the online
        key is byte-identical to the offline cache key for the same
        ``(tenant, schema, version, entity)`` — online/offline parity by reuse.
        """
        return make_feature_cache_key(
            tenant_id=tenant_id,
            schema_name=schema.name,
            version=schema.version,
            row_key=entity_id,
        )

    # ------------------------------------------------------------------
    # Write-through populate (called by FeatureStore.materialize, composed)
    # ------------------------------------------------------------------

    async def populate(
        self,
        schema: FeatureSchema,
        frame: pl.DataFrame,
        *,
        tenant_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> int:
        """Write each row of ``frame`` to the online store, keyed per entity.

        One Redis ``SET`` per entity row, keyed by :meth:`_key`. The value is the
        JSON-serialized per-entity feature mapping (``entity_id`` + declared
        field columns). Returns the number of rows written.

        Parameters
        ----------
        schema:
            The :class:`FeatureSchema` whose ``entity_id_column`` + ``field_names``
            define the served row shape.
        frame:
            A ``polars.DataFrame`` carrying ``entity_id_column`` + declared
            columns (the redacted/persisted materialise frame is a valid input).
        tenant_id:
            Tenant scope. Validated via :func:`validate_tenant_id` (missing /
            forbidden raises :class:`~kailash_ml.errors.TenantRequiredError`).
        ttl_seconds:
            Per-call TTL override. When omitted, the instance ``default_ttl``
            applies (or no expiry when that is also ``None``).

        Raises
        ------
        kailash_ml.errors.TenantRequiredError
            ``tenant_id`` missing / invalid.
        kailash_ml.errors.OnlineStoreUnavailableError
            The Redis backend is unreachable.
        """
        if not isinstance(schema, FeatureSchema):
            raise TypeError(
                "OnlineFeatureStore.populate(schema=...) must be FeatureSchema, "
                f"got {type(schema).__name__}"
            )
        if not isinstance(frame, pl.DataFrame):
            raise TypeError(
                "OnlineFeatureStore.populate(frame=...) must be polars.DataFrame "
                f"(polars-native), got {type(frame).__name__}"
            )
        tenant = validate_tenant_id(tenant_id, operation="OnlineFeatureStore.populate")
        entity_col = schema.entity_id_column
        served_cols = [entity_col] + [c for c in schema.field_names if c != entity_col]
        present = [c for c in served_cols if c in frame.columns]
        effective_ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        started_at = time.monotonic()
        logger.info(
            "online_feature_store.populate.start",
            extra={
                "backend": "redis",
                "url": self._masked_url,
                "tenant_fingerprint": _fingerprint(tenant),
                "schema": schema.name,
                "version": schema.version,
                "input_rows": frame.height,
                "ttl_seconds": effective_ttl,
            },
        )
        written = 0
        try:
            for row in frame.select(present).iter_rows(named=True):
                entity_val = row.get(entity_col)
                if entity_val is None:
                    # A row without an entity id cannot be served — skip it,
                    # never write under a None key (silent merge across entities).
                    continue
                key = self._key(schema, tenant_id=tenant, entity_id=str(entity_val))
                payload = json.dumps(row, default=_json_default)
                if effective_ttl is not None:
                    await self._client.set(key, payload, ex=effective_ttl)
                else:
                    await self._client.set(key, payload)
                written += 1
        except Exception as exc:  # noqa: BLE001 — re-raised typed below
            self._raise_unavailable("populate", exc)

        latency_ms = (time.monotonic() - started_at) * 1000.0
        logger.info(
            "online_feature_store.populate.ok",
            extra={
                "backend": "redis",
                "url": self._masked_url,
                "tenant_fingerprint": _fingerprint(tenant),
                "schema": schema.name,
                "version": schema.version,
                "row_count": written,
                "latency_ms": latency_ms,
            },
        )
        return written

    # ------------------------------------------------------------------
    # Serve path — low-latency point reads
    # ------------------------------------------------------------------

    async def get(
        self,
        schema: FeatureSchema,
        entity_ids: list[str],
        *,
        tenant_id: str | None = None,
    ) -> pl.DataFrame:
        """Serve the online feature rows for ``entity_ids`` (low-latency point read).

        Returns a ``polars.DataFrame`` containing one row per FOUND entity
        (``entity_id_column`` + declared field columns). Entities absent from the
        online store are simply omitted from the result — a partial-hit serve is
        NOT an error. The returned frame is always column-shaped (entity_id +
        declared fields) even when empty, so a downstream ``.filter`` on the
        entity column never raises ``ColumnNotFoundError``.

        Parameters
        ----------
        schema:
            The :class:`FeatureSchema` being served.
        entity_ids:
            The entity identifiers to look up. Each is keyed via :meth:`_key`
            (canonical tenant-scoped key — offline/online parity).
        tenant_id:
            Tenant scope. Validated via :func:`validate_tenant_id`. Because the
            key embeds ``tenant_id``, tenant A's serve never reads tenant B's
            rows (``rules/tenant-isolation.md`` Rule 1/2).

        Raises
        ------
        kailash_ml.errors.TenantRequiredError
            ``tenant_id`` missing / invalid.
        kailash_ml.errors.OnlineStoreUnavailableError
            The Redis backend is unreachable.
        """
        if not isinstance(schema, FeatureSchema):
            raise TypeError(
                "OnlineFeatureStore.get(schema=...) must be FeatureSchema, "
                f"got {type(schema).__name__}"
            )
        if not isinstance(entity_ids, list):
            raise TypeError(
                "OnlineFeatureStore.get(entity_ids=...) must be a list, "
                f"got {type(entity_ids).__name__}"
            )
        tenant = validate_tenant_id(tenant_id, operation="OnlineFeatureStore.get")
        entity_col = schema.entity_id_column
        projection = [entity_col] + [c for c in schema.field_names if c != entity_col]

        started_at = time.monotonic()
        logger.info(
            "online_feature_store.get.start",
            extra={
                "backend": "redis",
                "url": self._masked_url,
                "tenant_fingerprint": _fingerprint(tenant),
                "schema": schema.name,
                "version": schema.version,
                "entity_count": len(entity_ids),
            },
        )

        keys = [
            self._key(schema, tenant_id=tenant, entity_id=str(eid))
            for eid in entity_ids
        ]
        try:
            raw_values = await self._client.mget(keys) if keys else []
        except Exception as exc:  # noqa: BLE001 — re-raised typed below
            self._raise_unavailable("get", exc)

        rows: list[dict[str, Any]] = []
        for raw in raw_values:
            if raw is None:
                continue
            try:
                rows.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                # A corrupt/non-JSON value is NOT a silent skip class —
                # surface it as a backend-integrity fault so triage sees it.
                logger.warning(
                    "online_feature_store.get.corrupt_value",
                    extra={
                        "backend": "redis",
                        "url": self._masked_url,
                        "tenant_fingerprint": _fingerprint(tenant),
                        "schema": schema.name,
                        "version": schema.version,
                    },
                )

        if not rows:
            out = pl.DataFrame(schema=projection)
        else:
            out = pl.DataFrame(rows)
            present = [c for c in projection if c in out.columns]
            if present:
                out = out.select(present)

        latency_ms = (time.monotonic() - started_at) * 1000.0
        logger.info(
            "online_feature_store.get.ok",
            extra={
                "backend": "redis",
                "url": self._masked_url,
                "tenant_fingerprint": _fingerprint(tenant),
                "schema": schema.name,
                "version": schema.version,
                "row_count": out.height,
                "latency_ms": latency_ms,
            },
        )
        return out

    # ------------------------------------------------------------------
    # Unavailability wrapping + lifecycle
    # ------------------------------------------------------------------

    def _raise_unavailable(self, operation: str, exc: Exception) -> NoReturn:
        """Wrap a backend-down failure in the typed error (never a bare one).

        Re-raises a :class:`~kailash_ml.errors.OnlineStoreUnavailableError`
        chained from the underlying redis exception. The Redis URL is masked
        in the message so credentials never reach the log / aggregator
        (``rules/observability.md`` Rule 6 + ``rules/security.md``).
        """
        logger.warning(
            "online_feature_store.%s.unavailable",
            operation,
            extra={
                "backend": "redis",
                "url": self._masked_url,
                "error_type": type(exc).__name__,
            },
        )
        raise OnlineStoreUnavailableError(
            reason=(
                f"OnlineFeatureStore.{operation}: Redis backend unreachable at "
                f"{self._masked_url} ({type(exc).__name__})"
            ),
        ) from exc

    async def close(self) -> None:
        """Release the underlying redis.asyncio connection pool.

        Best-effort (cleanup-path) per ``rules/zero-tolerance.md`` Rule 3 — a
        close failure during teardown is logged, not raised.
        """
        try:
            await self._client.aclose()
        except Exception:  # pragma: no cover - best-effort cleanup
            logger.debug("online_feature_store.close_error", exc_info=True)

    async def __aenter__(self) -> "OnlineFeatureStore":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    @property
    def masked_url(self) -> str:
        """Return the credential-masked Redis URL (read-only, log-safe)."""
        return self._masked_url


def _fingerprint(tenant: str) -> str:
    """Local fingerprint helper — never echo the raw tenant on a log line."""
    from kailash_ml.errors import fingerprint_classified_value

    return fingerprint_classified_value(tenant)
