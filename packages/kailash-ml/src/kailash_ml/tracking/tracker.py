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
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional

if TYPE_CHECKING:
    import polars as pl  # noqa: F401 — referenced in forward-string annotations

from kailash_ml._env import resolve_store_url
from kailash_ml.errors import RunNotFoundError
from kailash_ml.tracking.query import (
    FilterParseError,
    RunDiff,
    RunRecord,
    build_search_sql,
    compute_run_diff,
    run_record_from_row,
)
from kailash_ml.tracking.runner import ExperimentRun
from kailash_ml.tracking.runner import track as _track_async
from kailash_ml.tracking.storage import AbstractTrackerStore, SqliteTrackerStore

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
        self._backend: Optional[AbstractTrackerStore] = None

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
        # call. For Postgres/MySQL the SqliteTrackerStore is not the
        # right backing store — callers supply a :class:`PostgresTrackerStore`
        # (W14b) via the explicit ``backend=`` kwarg to :meth:`track`
        # or pre-assigning ``tracker._backend`` when they need the
        # persistent-engine shape.
        sqlite_path = _sqlite_path_for(resolved)
        if sqlite_path is not None:
            tracker._backend = SqliteTrackerStore(sqlite_path)

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

        W11: ``parent_run_id`` is now passed through to the runner
        (spec §3.1 MUST honor every keyword argument) rather than
        being ignored in favour of ambient contextvar.
        """
        resolved_tenant = (
            tenant_id if tenant_id is not None else self._default_tenant_id
        )
        async with _track_async(
            experiment,
            backend=self._backend,
            tenant_id=resolved_tenant,
            parent_run_id=parent_run_id,
            store=self._store_url if self._backend is None else None,
            **params,
        ) as run:
            yield run

    # ------------------------------------------------------------------
    # Non-context-manager lifecycle — spec §11.2 MCP contract parity.
    #
    # W11 Decision 9 parity path: some callers (MCP server tools, RL
    # orchestrators, script-style usage) need explicit start/end
    # without the ``async with`` block. These methods return a
    # standalone :class:`ExperimentRun` that the caller MUST finalise
    # via :meth:`end_run`. The context-manager path remains the
    # recommended idiom — this pair is the interoperability surface
    # for API consumers that cannot use ``async with``.
    # ------------------------------------------------------------------

    async def start_run(
        self,
        experiment: str,
        *,
        tenant_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **params: Any,
    ) -> ExperimentRun:
        """Start a run without an ``async with`` block.

        Parity with spec §11.2 MCP tool signature
        ``start_run(experiment, tenant_id, parent_run_id, tags) -> run_id``.
        Returns the full :class:`ExperimentRun` so callers can later
        call :meth:`end_run` with the same object (no secondary lookup
        against the store).

        The caller MUST pair every ``start_run`` with exactly one
        ``end_run`` — orphaned runs stay in ``RUNNING`` status forever
        (spec §3.2 invariant 4 — ``finished_at`` must always populate
        on any exit path). If you can use ``async with tracker.track(...)``
        instead, prefer that; the context-manager path has automatic
        cleanup + signal handling and never leaves a RUNNING row.

        Args:
            experiment: Run grouping key.
            tenant_id: Tenant override; falls back to engine default
                when omitted.
            parent_run_id: Explicit parent id. When omitted, resolves
                to the ambient run via
                :func:`kailash_ml.tracking.get_current_run`.
            **params: Initial params logged on run start.

        Returns:
            An :class:`ExperimentRun` ready for :meth:`end_run`.
        """
        resolved_tenant = (
            tenant_id if tenant_id is not None else self._default_tenant_id
        )
        if self._backend is None:
            # Lazy-construct a backend on the resolved SQLite path so
            # the pair matches the context-manager path's defaults.
            self._backend = SqliteTrackerStore(
                _sqlite_path_for(self.store_url) or ":memory:"
            )
        # Resolve parent per spec §3.4 — explicit wins over ambient.
        from kailash_ml.tracking.runner import _current_run  # noqa: PLC0415

        resolved_parent: Optional[str]
        if parent_run_id is not None and parent_run_id != "":
            resolved_parent = parent_run_id
        else:
            ambient = _current_run.get()
            resolved_parent = ambient.run_id if ambient is not None else None

        run = ExperimentRun(
            experiment=experiment,
            backend=self._backend,
            params=params,
            tenant_id=resolved_tenant,
            parent_run_id=resolved_parent,
        )
        # Use the ExperimentRun's async-context machinery to insert the
        # row + register for signal handling. We do NOT hold the
        # context open — the caller ends the run explicitly via
        # :meth:`end_run`. We therefore synthesise __aenter__ directly
        # without the ``async with`` block.
        await run.__aenter__()
        return run

    async def end_run(
        self,
        run: ExperimentRun,
        *,
        status: str = "FINISHED",
        error: Optional[BaseException] = None,
    ) -> None:
        """Finalise a run previously started with :meth:`start_run`.

        The ``status`` kwarg MUST be one of
        ``{"FINISHED", "FAILED", "KILLED"}`` per spec §3.2 / §3.5.
        Legacy ``"COMPLETED"`` is BLOCKED — callers migrating from 0.x
        MUST rename at the call site.

        Args:
            run: The :class:`ExperimentRun` returned from
                :meth:`start_run`.
            status: Terminal status — ``"FINISHED"`` for clean exit,
                ``"FAILED"`` when an exception handled out-of-band,
                ``"KILLED"`` when the caller received a signal.
            error: Optional exception associated with ``FAILED``
                terminations. Stored as ``error_type`` / ``error_message``
                in the row.
        """
        from kailash_ml.tracking.runner import _ALLOWED_STATUSES  # noqa: PLC0415

        if status not in _ALLOWED_STATUSES or status == "RUNNING":
            raise ValueError(
                f"end_run status {status!r} is not a valid terminal status; "
                f"allowed: FINISHED / FAILED / KILLED (spec ml-tracking.md §3.2)."
            )
        exc_type = type(error) if error is not None else None
        if status == "FAILED" and exc_type is None:
            # Caller claimed FAILED but passed no exception — still
            # synthesise a minimal one so __aexit__'s FAILED branch
            # records an error_type of something useful.
            class _EndRunFailed(Exception):
                pass

            error = _EndRunFailed("end_run called with status=FAILED")
            exc_type = type(error)
        if status == "KILLED":
            # Ensure __aexit__ takes the KILLED branch even without an
            # actual signal having fired — `_killed` is the load-bearing
            # flag inside the run.
            run._killed = True
            if run._killed_reason is None:
                run._killed_reason = "end_run.explicit"
            exc_type = KeyboardInterrupt if exc_type is None else exc_type
            error = (
                error
                if error is not None
                else KeyboardInterrupt("end_run(status=KILLED)")
            )
        await run.__aexit__(exc_type, error, None)

    # ------------------------------------------------------------------
    # W13 — Query primitives (spec ml-tracking.md §5)
    # ------------------------------------------------------------------

    async def get_run(
        self, run_id: str, *, tenant_id: Optional[str] = None
    ) -> RunRecord:
        """Return a typed :class:`RunRecord` for ``run_id`` (spec §5.1).

        ``tenant_id`` scopes the lookup when set — reading another
        tenant's run raises :class:`RunNotFoundError`. When omitted,
        falls back to the engine-level default tenant.

        Raises :class:`RunNotFoundError` if the run does not exist or
        is scoped to a different tenant.
        """
        self._require_backend()
        assert self._backend is not None
        row = await self._backend.get_run(run_id)
        if row is None:
            raise RunNotFoundError(
                reason=f"run_id {run_id!r} not found",
                resource_id=run_id,
            )
        resolved_tenant = (
            tenant_id if tenant_id is not None else self._default_tenant_id
        )
        if resolved_tenant is not None and row.get("tenant_id") != resolved_tenant:
            raise RunNotFoundError(
                reason=f"run_id {run_id!r} not visible to tenant",
                resource_id=run_id,
                tenant_id=resolved_tenant,
            )
        return run_record_from_row(row)

    async def list_runs(
        self,
        *,
        experiment: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> "pl.DataFrame":
        """Return runs matching the given filters as a polars DataFrame.

        Columns: ``run_id``, ``experiment``, ``status``, ``tenant_id``,
        ``parent_run_id``, ``wall_clock_start``, ``wall_clock_end``,
        ``duration_seconds``, ``git_sha``, ``device_used``. Ordered by
        ``wall_clock_end DESC`` by default.
        """
        self._require_backend()
        assert self._backend is not None
        resolved_tenant = self._resolve_tenant(tenant_id)
        rows = await self._backend.query_runs(
            experiment=experiment,
            tenant_id=resolved_tenant,
            status=status,
            limit=limit,
        )
        return _runs_dataframe(rows)

    async def search_runs(
        self,
        *,
        filter: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: int = 100,
        tenant_id: Optional[str] = None,
    ) -> "pl.DataFrame":
        """MLflow-compatible search over runs (spec §5.2).

        ``filter`` accepts expressions like
        ``"metrics.val_loss < 0.5 AND params.family = 'lightgbm'"``.
        Parse errors raise :class:`ValueError` with prefix
        ``"invalid filter:"``.
        """
        self._require_backend()
        assert self._backend is not None
        resolved_tenant = self._resolve_tenant(tenant_id)
        try:
            sql, params = build_search_sql(
                filter,
                tenant_id=resolved_tenant,
                order_by=order_by,
                limit=limit,
            )
        except FilterParseError:
            raise
        rows = await self._backend.search_runs_raw(sql, params)
        return _runs_dataframe(rows)

    async def list_experiments(
        self, *, tenant_id: Optional[str] = None
    ) -> "pl.DataFrame":
        """Summarise every experiment as a polars DataFrame.

        Columns: ``experiment``, ``run_count``, ``finished_count``,
        ``failed_count``, ``killed_count``, ``latest_wall_clock_end``.
        """
        self._require_backend()
        assert self._backend is not None
        resolved_tenant = self._resolve_tenant(tenant_id)
        rows = await self._backend.list_experiments_summary(tenant_id=resolved_tenant)
        import polars as pl  # noqa: PLC0415

        if not rows:
            return pl.DataFrame(
                schema={
                    "experiment": pl.Utf8,
                    "run_count": pl.Int64,
                    "finished_count": pl.Int64,
                    "failed_count": pl.Int64,
                    "killed_count": pl.Int64,
                    "latest_wall_clock_end": pl.Utf8,
                }
            )
        return pl.DataFrame(rows)

    async def list_metrics(
        self, run_id: str, *, tenant_id: Optional[str] = None
    ) -> "pl.DataFrame":
        """Return every metric row logged against ``run_id``.

        Tenant-scoped via :meth:`get_run` — unauthorised access raises
        :class:`RunNotFoundError`. Columns: ``key``, ``step``,
        ``value``, ``timestamp``.
        """
        # Route through get_run so tenant-scope is enforced before the
        # metric rows are exposed.
        await self.get_run(run_id, tenant_id=tenant_id)
        assert self._backend is not None
        rows = await self._backend.list_metrics(run_id)
        import polars as pl  # noqa: PLC0415

        if not rows:
            return pl.DataFrame(
                schema={
                    "key": pl.Utf8,
                    "step": pl.Int64,
                    "value": pl.Float64,
                    "timestamp": pl.Utf8,
                }
            )
        return pl.DataFrame(rows)

    async def list_artifacts(
        self, run_id: str, *, tenant_id: Optional[str] = None
    ) -> "pl.DataFrame":
        """Return every artifact row logged against ``run_id``.

        Tenant-scoped via :meth:`get_run`. Columns: ``name``,
        ``sha256``, ``content_type``, ``size_bytes``, ``storage_uri``,
        ``created_at``.
        """
        await self.get_run(run_id, tenant_id=tenant_id)
        assert self._backend is not None
        rows = await self._backend.list_artifacts(run_id)
        import polars as pl  # noqa: PLC0415

        if not rows:
            return pl.DataFrame(
                schema={
                    "name": pl.Utf8,
                    "sha256": pl.Utf8,
                    "content_type": pl.Utf8,
                    "size_bytes": pl.Int64,
                    "storage_uri": pl.Utf8,
                    "created_at": pl.Utf8,
                }
            )
        return pl.DataFrame(rows)

    async def diff_runs(
        self,
        run_a: str,
        run_b: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> RunDiff:
        """Compute a :class:`RunDiff` between two runs (spec §5.3)."""
        record_a = await self.get_run(run_a, tenant_id=tenant_id)
        record_b = await self.get_run(run_b, tenant_id=tenant_id)
        assert self._backend is not None
        metrics_a = await self._backend.list_metrics(run_a)
        metrics_b = await self._backend.list_metrics(run_b)
        return compute_run_diff(record_a, record_b, metrics_a, metrics_b)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_backend(self) -> None:
        """Raise if the tracker has no backend attached.

        Query primitives route through an :class:`AbstractTrackerStore`;
        both :class:`SqliteTrackerStore` (the default) and
        :class:`PostgresTrackerStore` (W14b) satisfy the contract.
        """
        if self._backend is None:
            raise RuntimeError(
                "ExperimentTracker has no tracker store attached; "
                "supply a SqliteTrackerStore / PostgresTrackerStore "
                "via ExperimentTracker.create(store_url=...) or "
                "assign tracker._backend before calling query primitives."
            )

    def _resolve_tenant(self, explicit: Optional[str]) -> Optional[str]:
        """Resolve the tenant for a query (spec §10.2 + §7.2).

        Priority (first non-None wins):

        1. ``explicit`` kwarg — caller-side override.
        2. Ambient ``get_current_tenant_id()`` — the active
           ``km.track(tenant_id=...)`` scope. W14 contextvar plumbing
           lets any query invoked inside ``async with km.track("exp",
           tenant_id="acme"):`` auto-scope without callers re-passing.
        3. Engine default (``default_tenant_id=`` on ``create()``).
        4. ``None`` → unscoped.

        W15 will extend with ``multi_tenant_strict`` mode that raises
        :class:`TenantRequiredError` when none of the above yield a
        value and the tracker was opened in strict mode.
        """
        if explicit is not None:
            return explicit
        # Import at call-site to avoid a module-level cycle with
        # ``kailash_ml.tracking`` (which imports ExperimentTracker).
        from kailash_ml.tracking import get_current_tenant_id  # noqa: PLC0415

        ambient = get_current_tenant_id()
        if ambient is not None:
            return ambient
        return self._default_tenant_id

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


_RUN_DATAFRAME_COLUMNS: tuple[str, ...] = (
    "run_id",
    "experiment",
    "status",
    "tenant_id",
    "parent_run_id",
    "wall_clock_start",
    "wall_clock_end",
    "duration_seconds",
    "git_sha",
    "device_used",
    "accelerator",
)


def _runs_dataframe(rows: list[dict[str, Any]]) -> "Any":
    """Project run rows into the W13 polars DataFrame shape.

    Returns a polars DataFrame with a stable column set so downstream
    diff / dashboard consumers can rely on column names across empty
    and non-empty returns.
    """
    import polars as pl  # noqa: PLC0415 — polars is a declared kailash-ml dep

    if not rows:
        return pl.DataFrame(
            schema={
                "run_id": pl.Utf8,
                "experiment": pl.Utf8,
                "status": pl.Utf8,
                "tenant_id": pl.Utf8,
                "parent_run_id": pl.Utf8,
                "wall_clock_start": pl.Utf8,
                "wall_clock_end": pl.Utf8,
                "duration_seconds": pl.Float64,
                "git_sha": pl.Utf8,
                "device_used": pl.Utf8,
                "accelerator": pl.Utf8,
            }
        )
    projected = [{col: row.get(col) for col in _RUN_DATAFRAME_COLUMNS} for row in rows]
    return pl.DataFrame(projected)


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
