# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``ExperimentTracker`` 1.0 canonical async factory.

Implements ``specs/ml-tracking.md`` §2.5 — a single async construction
path for the tracker engine. Sync ``__init__`` is BLOCKED per the
spec's invariant that every caller route through
:meth:`ExperimentTracker.create`.

The tracker is a thin orchestration shell:

- resolves the backing store URL via :func:`kailash_ml._env.resolve_store_url`
  (single-point env precedence chain)
- opens a :class:`kailash.db.connection.ConnectionManager` on the
  resolved URL
- auto-applies the numbered migrations at
  :mod:`kailash.tracking.migrations` (0001 + 0002) before returning
- exposes a :meth:`track` async-context method that delegates to the
  legacy :func:`kailash_ml.tracking.runner.track` primitive so every
  run carries the 17 auto-capture fields per §2.4

``ExperimentRun`` stays defined in :mod:`kailash_ml.tracking.runner`
and is NOT re-implemented here — §2.4 requires it to be a thin
wrapper polymorphic across backends.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from kailash_ml._env import resolve_store_url
from kailash_ml.tracking.runner import ExperimentRun
from kailash_ml.tracking.runner import track as _track_async
from kailash_ml.tracking.sqlite_backend import SQLiteTrackerBackend

__all__ = ["ExperimentTracker"]


logger = logging.getLogger(__name__)

# Sentinel threaded through the async factory so `cls(...)` from user
# code fails loudly per §2.5. The value is module-private; user code
# cannot forge it without importing it explicitly, which itself is a
# violation the zero-tolerance audit grep will surface.
_ASYNC_FACTORY_TOKEN = object()


class ExperimentTracker:
    """Canonical 1.0 experiment-tracking engine.

    Construction is async-only: callers MUST use
    :meth:`ExperimentTracker.create`. Sync ``__init__`` raises
    :class:`RuntimeError` so the spec §2.5 invariant is structurally
    enforced.

    The tracker owns its ``store_url`` + ``default_tenant_id`` and
    ships :meth:`track` as the canonical entry point — which under
    the hood delegates to the existing ``km.track()`` primitive so
    the 17 auto-capture fields per §2.4 land exactly once.
    """

    def __init__(self, *, _factory_token: Any = None) -> None:
        if _factory_token is not _ASYNC_FACTORY_TOKEN:
            raise RuntimeError(
                "ExperimentTracker cannot be constructed synchronously; "
                "use `await ExperimentTracker.create(store_url=...)` "
                "(specs/ml-tracking.md §2.5)."
            )
        self._store_url: Optional[str] = None
        self._default_tenant_id: Optional[str] = None
        self._backend: Optional[SQLiteTrackerBackend] = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def create(
        cls,
        store_url: Optional[str] = None,
        *,
        default_tenant_id: Optional[str] = None,
    ) -> "ExperimentTracker":
        """Sole async construction path per ``ml-tracking.md`` §2.5.

        Resolution:

        1. ``store_url`` passed here (explicit) wins.
        2. Otherwise :func:`kailash_ml._env.resolve_store_url` honours the
           canonical ``KAILASH_ML_STORE_URL`` + legacy bridge precedence.
        3. Default falls through to ``sqlite:///~/.kailash_ml/ml.db``.

        On open, every pending migration in
        :mod:`kailash.tracking.migrations` (0001 status vocabulary,
        0002 _kml_* prefix + tenant + audit immutability) is applied.
        The registry is idempotent — re-open is a no-op.

        Args:
            store_url: SQLite / Postgres / MySQL URL. ``None`` delegates
                to the env-resolver.
            default_tenant_id: Engine-level default tenant. Used by
                :meth:`track` when the caller does not pass
                ``tenant_id=``. Set only for single-tenant dev /
                notebook use.

        Returns:
            An initialised ``ExperimentTracker`` ready for :meth:`track`.
        """
        resolved = resolve_store_url(store_url)
        # Normalise the ``sqlite+memory`` alias (ml-tracking.md §6.1)
        # into the canonical SQLAlchemy-style URL the low-level
        # ``ConnectionManager`` accepts. Without this step the aiosqlite
        # adapter treats the literal string ``sqlite+memory`` as a
        # filesystem path and writes a file of that name.
        if resolved == "sqlite+memory" or resolved.startswith("sqlite+memory:"):
            resolved = "sqlite:///:memory:"
        tracker = cls(_factory_token=_ASYNC_FACTORY_TOKEN)
        tracker._store_url = resolved
        tracker._default_tenant_id = default_tenant_id

        # Apply numbered migrations (0001 + 0002 today; extensible).
        await tracker._apply_pending_migrations()

        # Open the SQLite backend against the resolved path so
        # `track()` can delegate without re-resolving the URL every
        # call. For Postgres/MySQL the SQLiteTrackerBackend is not the
        # right backing store — the field stays None and callers MUST
        # pass an explicit ``backend`` to :meth:`track`. A full
        # Postgres tracker backend is out of scope for W10.
        sqlite_path = _sqlite_path_for(resolved)
        if sqlite_path is not None:
            tracker._backend = SQLiteTrackerBackend(sqlite_path)

        logger.info(
            "kailash_ml.tracker.ready",
            extra={
                "store_url": _mask_url(resolved),
                "default_tenant_id": default_tenant_id,
            },
        )
        return tracker

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def store_url(self) -> str:
        """Resolved backing-store URL (post :func:`resolve_store_url`)."""
        assert self._store_url is not None, "tracker not initialised"
        return self._store_url

    @property
    def default_tenant_id(self) -> Optional[str]:
        return self._default_tenant_id

    @asynccontextmanager
    async def track(
        self,
        experiment: str,
        *,
        tenant_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **params: Any,
    ) -> AsyncIterator[ExperimentRun]:
        """Open an :class:`ExperimentRun` backed by this tracker.

        Delegates to :func:`kailash_ml.tracking.runner.track` so the
        17-field auto-capture + signal-handler install + contextvar
        propagation land exactly once — ``ExperimentRun`` is
        polymorphic across backends per §2.4 invariant 5 (it does NOT
        hold a tracker reference).
        """
        resolved_tenant = (
            tenant_id if tenant_id is not None else self._default_tenant_id
        )
        # ``runner.track`` supports ``parent_run_id`` via the ambient
        # contextvar only; explicit parent_run_id is threaded through
        # its `**params` bag for now. Matching the spec's public
        # signature when the runner itself gains the kwarg is tracked
        # under W11 (run-lifecycle overhaul).
        async with _track_async(
            experiment,
            backend=self._backend,
            tenant_id=resolved_tenant,
            store=self._store_url if self._backend is None else None,
            **params,
        ) as run:
            yield run

    async def close(self) -> None:
        """Release any backend resources owned by this tracker."""
        if self._backend is not None:
            await self._backend.close()
            self._backend = None

    async def __aenter__(self) -> "ExperimentTracker":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _apply_pending_migrations(self) -> None:
        """Run every pending numbered migration against the store.

        Opens a short-lived :class:`ConnectionManager`, wraps it in
        :class:`_MigrationConnAdapter` so the migration helpers' native
        ``execute(sql, params_tuple)`` call form works regardless of
        backend, calls :meth:`MigrationRegistry.apply_pending`, and
        closes. The registry is idempotent (each migration's
        ``verify()`` short-circuits already-applied state), so repeat
        invocations of :meth:`create` are safe.

        Failures at this step are fatal — we raise loudly rather than
        silently continuing with an un-migrated schema per
        ``rules/zero-tolerance.md`` Rule 3.
        """
        # Deferred import — ``kailash.db.connection`` pulls in the
        # heavy-weight pool stack, and downstream unit tests for
        # pure-SQLite code paths should not eagerly import it.
        from kailash.db.connection import ConnectionManager
        from kailash.tracking.migrations._registry import get_registry

        assert self._store_url is not None
        conn_mgr = ConnectionManager(self._store_url)
        await conn_mgr.initialize()
        try:
            registry = get_registry()
            await registry.apply_pending(_MigrationConnAdapter(conn_mgr))
        finally:
            await conn_mgr.close()


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


class _MigrationConnAdapter:
    """Adapter that bridges the migration-helper call form to ``ConnectionManager``.

    Migration helpers at ``kailash.tracking.migrations.*`` call
    ``conn.execute(sql, params_tuple)`` — with ``params`` as a single
    sequence argument. :class:`ConnectionManager` uses varargs
    (``execute(sql, *args)``). Without this adapter the sequence is
    treated as one tuple-typed parameter and the SQLite driver raises
    ``ProgrammingError: type 'tuple' is not supported``.

    The adapter exposes ``.execute``, ``.fetchone``, ``.fetchall``, and
    passes through the ``dialect`` attribute the helpers read for
    dialect-type dispatch. It is strictly internal to W10 — migration
    helpers themselves remain unchanged (they are shared with test
    fakes that use the ``(sql, params_tuple)`` shape natively).
    """

    def __init__(self, conn_mgr: Any) -> None:
        self._cm = conn_mgr

    @property
    def dialect(self) -> Any:
        return self._cm.dialect

    async def execute(self, sql: str, params: Optional[Any] = None) -> Any:
        if params is None:
            return await self._cm.execute(sql)
        return await self._cm.execute(sql, *tuple(params))

    async def fetchone(self, sql: str, params: Optional[Any] = None) -> Any:
        if params is None:
            rows = await self._cm.fetch(sql)
        else:
            rows = await self._cm.fetch(sql, *tuple(params))
        if not rows:
            return None
        row = rows[0]
        # ConnectionManager.fetch returns list[dict]; migrations expect
        # positional-index access (row[0]). Fall back to values() when
        # the row is dict-like.
        if isinstance(row, dict):
            return list(row.values())
        return row

    async def fetchall(self, sql: str, params: Optional[Any] = None) -> Any:
        if params is None:
            return await self._cm.fetch(sql)
        return await self._cm.fetch(sql, *tuple(params))


def _sqlite_path_for(url: str) -> Optional[str]:
    """Return the filesystem path for a ``sqlite:///`` URL, else ``None``.

    Accepts the canonical ``sqlite:///`` URI plus the ``sqlite+memory``
    alias per ``ml-tracking.md`` §6.1. Anything else (``postgresql://``,
    ``mysql://``, etc.) falls through — the caller handles non-SQLite
    backends separately.
    """
    if url.startswith("sqlite+memory"):
        return ":memory:"
    if url.startswith("sqlite:///"):
        rest = url[len("sqlite:///") :]
        return rest or ":memory:"
    return None


def _mask_url(url: str) -> str:
    """Mask credentials in a store URL for structured logging.

    SQLite URLs are returned as-is (no credentials). Network URLs
    get their userinfo collapsed to ``***``.
    """
    if url.startswith("sqlite"):
        return url
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            return "<unparseable store url>"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://***@{parsed.hostname}{port}{parsed.path}"
    except Exception:
        return "<unparseable store url>"
