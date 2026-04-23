# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Top-level ``km.*`` convenience wrappers.

Per ``specs/ml-engines-v2.md §15``, kailash-ml ships a package-level
convenience layer that dispatches into the eight-method :class:`MLEngine`
surface. The wrappers live in this module so :mod:`kailash_ml` imports
them eagerly (``rules/orphan-detection.md §6`` + CodeQL
``py/modification-of-default-value``).

Wrappers covered in this file
-----------------------------

- :func:`train`     — §15.3
- :func:`autolog`   — re-exported from :mod:`kailash_ml.autolog`
- :func:`track`     — re-exported from :mod:`kailash_ml.tracking`
- :func:`register`  — §15.4
- :func:`serve`     — §15.5
- :func:`watch`     — §15.6 (dispatches to :class:`DriftMonitor`)
- :func:`dashboard` — §15.7 (non-blocking :class:`MLDashboard` launcher)
- :func:`diagnose`  — :mod:`kailash_ml.diagnostics` §3
- :func:`rl_train`  — re-exported from :mod:`kailash_ml.rl._rl_train`

``seed``, ``reproduce``, ``resume``, and ``lineage`` are declared inline
in :mod:`kailash_ml.__init__` rather than here because they are the
canonical declaration point per §11.1, §12, §12A, §15.8.

Cached default engine
---------------------

Per ``§15.2 MUST 1`` every wrapper routes through a per-tenant cached
default :class:`MLEngine` instance. The cache is a module-level dict so
the same ``MLEngine(tenant_id=…)`` is reused across wrapper calls (one
SQLite connection + primitive construction paid once per process per
tenant, not once per wrapper call).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any, Optional

from kailash_ml._result import TrainingResult
from kailash_ml._results import RegisterResult, ServeResult
from kailash_ml.engine import MLEngine
from kailash_ml.errors import ModelRegistryError

# autolog / track / rl_train / diagnostic helpers re-exported through
# this module so ``from kailash_ml._wrappers import autolog`` works
# alongside the rest of Group 1. The ``from kailash_ml import autolog``
# path in ``__init__.py`` pulls them from here.
from kailash_ml.autolog import autolog as _autolog_cm
from kailash_ml.autolog import autolog_fn  # noqa: F401 — sibling surface
from kailash_ml.diagnostics import diagnose_classifier, diagnose_regressor
from kailash_ml.diagnostics.dl import DLDiagnostics
from kailash_ml.diagnostics.rag import RAGDiagnostics
from kailash_ml.diagnostics.rl import RLDiagnostics
from kailash_ml.rl._rl_train import rl_train as _rl_train
from kailash_ml.tracking import erase_subject as _erase_subject  # noqa: F401
from kailash_ml.tracking import track as _track_cm

if TYPE_CHECKING:
    import polars as pl

    from kailash_ml.autolog.config import AutologHandle
    from kailash_ml.engines.drift_monitor import DriftMonitor
    from kailash_ml.tracking.runner import ExperimentRun


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tenant-scoped default engine cache (§15.2 MUST 1)
# ---------------------------------------------------------------------------

# Keys are ``tenant_id`` strings (or ``None`` for the single-tenant
# default). Access is guarded by ``_DEFAULT_ENGINE_LOCK`` so two
# concurrent wrapper calls on a fresh tenant do not race to construct
# two :class:`MLEngine` instances (each with its own SQLite connection).
_default_engines: dict[Optional[str], MLEngine] = {}
_DEFAULT_ENGINE_LOCK = threading.Lock()


def _get_default_engine(tenant_id: Optional[str]) -> MLEngine:
    """Return the cached default :class:`MLEngine` for ``tenant_id``.

    Constructs the engine on first use and caches it per-tenant. The
    lock ensures only one engine instance is created per
    ``tenant_id`` even under concurrent async tasks.

    Per ``§15.2 MUST 1`` this helper is the only site that constructs
    the default engine — wrapper functions MUST NOT build their own
    ``MLEngine()`` instances.
    """
    with _DEFAULT_ENGINE_LOCK:
        if tenant_id not in _default_engines:
            _default_engines[tenant_id] = MLEngine(tenant_id=tenant_id)
        return _default_engines[tenant_id]


def _reset_default_engines() -> None:
    """Test-only hook: clear the cached engines.

    Used by the wrapper-dispatch Tier-2 tests so the cache does not
    leak state across tenants between tests. MUST NOT be called by
    production code.
    """
    with _DEFAULT_ENGINE_LOCK:
        _default_engines.clear()


# ---------------------------------------------------------------------------
# §15.3 — km.train
# ---------------------------------------------------------------------------


async def train(
    df: "pl.DataFrame | Any",
    *,
    target: str,
    family: str = "auto",
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    tracker: "ExperimentRun | None" = None,
    ignore: Optional[list[str]] = None,
    hyperparameters: Optional[dict] = None,
    hp_search: str = "none",
    n_trials: int = 0,
    metric: Optional[str] = None,
) -> TrainingResult:
    """Train a model end-to-end through the cached default engine.

    Per ``specs/ml-engines-v2.md §15.3``:

    1. Resolve the cached :class:`MLEngine` via
       :func:`_get_default_engine` (tenant-scoped).
    2. Call ``await engine.setup(df, target=target, ignore=ignore)``.
    3. When ``family == "auto"``, run ``engine.compare()`` and return
       the winner's :class:`TrainingResult`; otherwise run
       ``engine.fit(family=family, ...)`` and return its result.

    The wrapper MUST NOT silently call ``engine.register(...)`` or
    ``engine.serve(...)`` per §15.3 BLOCKED clause.
    """
    engine = _get_default_engine(tenant_id)

    # Step 2 — setup the engine with the training frame and target.
    await engine.setup(df, target=target, ignore=ignore)

    # Step 3 — compare for "auto" family, otherwise fit a single family.
    if family == "auto":
        comparison = await engine.compare(metric=metric)
        # ``comparison.winner`` is the winning family name; we fit it
        # explicitly so the caller receives a populated TrainingResult.
        winner = getattr(comparison, "winner", None)
        if winner is None:
            # Fall back to sklearn when compare() couldn't pick a winner
            # (empty compare result). The engine validates the family.
            winner = "sklearn"
        return await engine.fit(
            family=winner,
            hyperparameters=hyperparameters,
            hp_search=hp_search,
            n_trials=n_trials,
            metric=metric,
        )

    return await engine.fit(
        family=family,
        hyperparameters=hyperparameters,
        hp_search=hp_search,
        n_trials=n_trials,
        metric=metric,
    )


# ---------------------------------------------------------------------------
# §15.4 — km.register
# ---------------------------------------------------------------------------


async def register(
    training_result: TrainingResult,
    *,
    name: str,
    alias: Optional[str] = None,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    format: str = "onnx",
    stage: str = "staging",
    metadata: Optional[dict] = None,
) -> RegisterResult:
    """Register a :class:`TrainingResult` in the default model registry.

    Per ``§15.4`` — dispatches through the tenant-scoped cached engine
    into :meth:`MLEngine.register`. The ``alias`` kwarg, when supplied,
    triggers a follow-up ``set_alias`` on the returned version.
    """
    engine = _get_default_engine(tenant_id)
    result = await engine.register(
        training_result,
        name=name,
        alias=None,  # set below so the base register path is unambiguous
        stage=stage,
        format=format,
    )
    # Alias assignment happens after the base register call so the
    # version row exists before we point an alias at it. The registry
    # exposes ``set_alias`` on the underlying ``_model_registry``
    # instance (per §15.4 step 4).
    if alias is not None:
        registry = getattr(engine, "_model_registry", None)
        version = getattr(result, "version", None)
        if registry is not None and version is not None:
            await registry.set_alias(
                name=name,
                version=version,
                alias=alias,
                actor_id=actor_id,
                reason=f"km.register alias={alias}",
            )
    # Attach metadata if the engine surfaced a hook (forward-compatible);
    # core registries persist metadata via the register() path already.
    _ = metadata  # reserved for §15.4 metadata passthrough when engine extends
    return result


# ---------------------------------------------------------------------------
# §15.5 — km.serve
# ---------------------------------------------------------------------------


async def serve(
    model_uri_or_result: "str | RegisterResult",
    *,
    alias: Optional[str] = None,
    channels: tuple[str, ...] = ("rest",),
    tenant_id: Optional[str] = None,
    version: Optional[int] = None,
    autoscale: bool = False,
    options: Optional[dict] = None,
) -> ServeResult:
    """Bring up inference channels for ``model_uri_or_result``.

    Per ``§15.5``. Returns the :class:`ServeResult` the engine produces —
    the caller uses ``.url`` / ``.stop()`` on it. ``alias`` is tolerated
    as a convenience alias for ``model_uri_or_result`` when the caller
    wants ``km.serve(alias="fraud@production")``; it maps onto the
    engine's model-resolution path.
    """
    engine = _get_default_engine(tenant_id)
    target = model_uri_or_result if model_uri_or_result is not None else alias
    if target is None:
        raise ValueError(
            "serve() requires either a model URI / RegisterResult "
            "positional arg OR alias='name@stage'"
        )
    return await engine.serve(
        target,
        channels=list(channels),
        version=version,
        autoscale=autoscale,
        options=options,
    )


# ---------------------------------------------------------------------------
# §15.6 — km.watch (DriftMonitor)
# ---------------------------------------------------------------------------


async def watch(
    model_uri: str,
    *,
    reference: "pl.DataFrame | None" = None,
    axes: tuple[str, ...] = ("feature", "prediction", "performance"),
    alerts: Any = None,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> "DriftMonitor":
    """Construct a :class:`DriftMonitor` bound to ``model_uri``.

    Per ``specs/ml-drift.md §12``, ``km.watch`` is a package-level
    wrapper that dispatches to the tenant-scoped cached engine. The
    caller receives the constructed :class:`DriftMonitor` and invokes
    ``.start()`` / ``.stop()`` / ``.inspect()`` on it.
    """
    # Lazy-import the DriftMonitor engine: pulling it here (rather
    # than at module scope) keeps ``kailash_ml._wrappers`` import cost
    # low and matches the legacy lazy-load path in
    # ``kailash_ml/__init__.py::__getattr__``.
    from kailash_ml.engines.drift_monitor import DriftMonitor  # noqa: WPS433

    engine = _get_default_engine(tenant_id)
    # DriftMonitor needs a connection manager — pull one from the
    # default engine's composition so the monitor shares the tenant's
    # SQLite store.
    conn = getattr(engine, "_connection_manager", None)
    # DriftMonitor requires a non-empty tenant_id (§W26.e
    # ``TenantRequiredError``). In single-tenant mode callers may pass
    # ``tenant_id=None`` into ``km.watch`` — bridge that to the
    # DriftMonitor's canonical ``"_single"`` tenant (same convention
    # :class:`MLEngine` uses for single-tenant persistence).
    monitor_tenant = tenant_id if tenant_id else "_single"
    monitor = DriftMonitor(conn, tenant_id=monitor_tenant, alerts=alerts)
    # Ensure schema exists before the caller queries it.
    if hasattr(monitor, "initialize"):
        init_fn = monitor.initialize
        if asyncio.iscoroutinefunction(init_fn):
            await init_fn()
        else:
            init_fn()
    if reference is not None:
        # Persist the reference distribution eagerly so the monitor is
        # ready for ``check_drift`` immediately. The engine method is
        # ``set_reference_data`` per §E1.1 / drift_monitor.py.
        setter = getattr(monitor, "set_reference_data", None)
        if setter is None:
            setter = getattr(monitor, "set_reference", None)
        if setter is None:
            raise ModelRegistryError(
                reason=(
                    "km.watch(reference=...) — DriftMonitor exposes "
                    "neither set_reference_data nor set_reference"
                ),
            )
        await setter(model_uri, reference)
    _ = axes, actor_id  # accepted for forward compatibility; current
    # DriftMonitor derives active axes from the reference distribution.
    return monitor


# ---------------------------------------------------------------------------
# §15.7 — km.dashboard (non-blocking launcher)
# ---------------------------------------------------------------------------


class DashboardHandle:
    """Handle returned by :func:`dashboard`.

    Exposes ``.url``, ``.stop()``. Per ``specs/ml-dashboard.md §8.6``,
    ``km.dashboard`` is a non-blocking launcher — the caller receives
    the handle immediately and the dashboard runs on a background
    event-loop thread so notebook cells remain interactive.
    """

    __slots__ = ("url", "_thread", "_server", "_stopped")

    def __init__(self, url: str, thread: threading.Thread, server: Any) -> None:
        self.url = url
        self._thread = thread
        self._server = server
        self._stopped = False

    def stop(self) -> None:
        """Stop the dashboard server and join the background thread."""
        if self._stopped:
            return
        self._stopped = True
        stopper = getattr(self._server, "stop", None)
        if callable(stopper):
            try:
                stopper()
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("dashboard.stop.error", extra={"error": str(exc)})
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)


def dashboard(
    *,
    db_url: Optional[str] = None,
    port: int = 5000,
    bind: str = "127.0.0.1",
    auth: Any = None,
    tenant_id: Optional[str] = None,
    title: str = "Kailash ML",
) -> DashboardHandle:
    """Non-blocking launcher for :class:`MLDashboard`.

    Per ``specs/ml-dashboard.md §8.6``, this returns a
    :class:`DashboardHandle` immediately while the dashboard process
    runs on a background thread. Notebook-friendly: the caller keeps
    REPL interactivity and calls ``handle.stop()`` when finished.

    The launcher is deliberately synchronous (NOT async) because the
    underlying :class:`MLDashboard` uses a blocking server loop.
    """
    # Lazy-import so the dashboard's Flask stack is loaded only when
    # the wrapper is actually used.
    from kailash_ml.dashboard import MLDashboard  # noqa: WPS433

    # The current :class:`MLDashboard` signature is
    # ``(db_url, artifact_root, host, port)``. ``auth`` / ``tenant_id``
    # / ``title`` are reserved per ``§15.7`` for a future version of
    # the dashboard that implements them; accepting them at this
    # wrapper boundary keeps ``km.dashboard`` future-compatible without
    # forcing the dashboard module to change its signature today.
    _ = (auth, tenant_id, title)  # reserved — see comment above
    server_kwargs: dict[str, Any] = {"host": bind, "port": port}
    if db_url is not None:
        server_kwargs["db_url"] = db_url
    server = MLDashboard(**server_kwargs)

    url = f"http://{bind}:{port}"

    def _run() -> None:
        try:
            server.serve()
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("dashboard.run.error", extra={"error": str(exc)})

    thread = threading.Thread(
        target=_run,
        name="kailash_ml.dashboard",
        daemon=True,
    )
    thread.start()
    return DashboardHandle(url=url, thread=thread, server=server)


# ---------------------------------------------------------------------------
# §3 of ml-diagnostics — km.diagnose
# ---------------------------------------------------------------------------


def diagnose(
    subject: Any,
    *,
    kind: str = "auto",
    data: Any = None,
    tracker: Any = None,
    show: bool = True,
    sensitive: bool = False,
) -> Any:
    """Single-call diagnostic entry per ``ml-diagnostics.md §3``.

    Dispatches to the adapter appropriate to ``subject`` + ``kind``.
    Per §3.2 the dispatch table inspects ``subject`` when
    ``kind == "auto"``; explicit ``kind`` bypasses inspection.

    The default tracker is resolved from the ambient ``km.track()`` run
    via :func:`kailash_ml.tracking.get_current_run` (§3.3 step 4) when
    ``tracker is None``.
    """
    # Resolve ambient tracker only when the caller did not supply one.
    if tracker is None:
        from kailash_ml.tracking import get_current_run

        tracker = get_current_run()

    if kind not in (
        "auto",
        "dl",
        "classical_classifier",
        "classical_regressor",
        "clustering",
        "rag",
        "rl",
        "alignment",
        "llm",
        "agent",
    ):
        raise ValueError(
            f"diagnose(kind={kind!r}) — kind must be one of the §3.1 literals"
        )

    # Explicit-kind dispatch first — the §3.2 table.
    if kind == "dl":
        return DLDiagnostics(subject, tracker=tracker)
    if kind == "rl":
        return RLDiagnostics(
            algo=subject if isinstance(subject, str) else "ppo", tracker=tracker
        )
    if kind == "rag":
        return (
            RAGDiagnostics(tracker=tracker) if tracker is not None else RAGDiagnostics()
        )
    if kind == "classical_classifier":
        if data is None:
            raise ValueError(
                "diagnose(kind='classical_classifier') requires data=(X, y)"
            )
        X, y = data
        return diagnose_classifier(subject, X, y, tracker=tracker)
    if kind == "classical_regressor":
        if data is None:
            raise ValueError(
                "diagnose(kind='classical_regressor') requires data=(X, y)"
            )
        X, y = data
        return diagnose_regressor(subject, X, y, tracker=tracker)

    # kind == "auto" — inspect subject for dispatch. Ordering here
    # mirrors the §3.2 dispatch table verbatim.
    if isinstance(subject, TrainingResult):
        framework = getattr(subject, "framework", "")
        if framework in ("lightning", "torch"):
            return DLDiagnostics.from_training_result(subject, tracker=tracker)
        if framework == "sklearn":
            if data is None:
                raise ValueError(
                    "diagnose(TrainingResult, framework='sklearn') requires "
                    "data=(X, y) for classical dispatch"
                )
            X, y = data
            model = getattr(subject, "model", None)
            # Inspect model to pick classifier vs regressor branch.
            from sklearn.base import ClassifierMixin, RegressorMixin  # noqa: WPS433

            if isinstance(model, ClassifierMixin):
                return diagnose_classifier(model, X, y, tracker=tracker)
            if isinstance(model, RegressorMixin):
                return diagnose_regressor(model, X, y, tracker=tracker)
            raise TypeError(
                "diagnose(TrainingResult, framework='sklearn') — model is "
                "neither ClassifierMixin nor RegressorMixin"
            )

    # Direct subject dispatch for sklearn models — the convenience path
    # for users who hold the fitted estimator rather than a
    # TrainingResult.
    try:
        from sklearn.base import ClassifierMixin, RegressorMixin  # noqa: WPS433
    except ImportError:  # pragma: no cover — sklearn is a base dep
        ClassifierMixin = RegressorMixin = type(None)  # type: ignore[assignment,misc]

    if isinstance(subject, ClassifierMixin):
        if data is None:
            raise ValueError(
                "diagnose(classifier) — data=(X, y) required for classical classifier"
            )
        X, y = data
        return diagnose_classifier(subject, X, y, tracker=tracker)
    if isinstance(subject, RegressorMixin):
        if data is None:
            raise ValueError(
                "diagnose(regressor) — data=(X, y) required for classical regressor"
            )
        X, y = data
        return diagnose_regressor(subject, X, y, tracker=tracker)

    # Fallback — treat as a DL / Lightning module.
    return DLDiagnostics(subject, tracker=tracker)


# ---------------------------------------------------------------------------
# §15.8 pass-throughs — autolog / track / rl_train / erase_subject
#
# These are re-exported here so the `kailash_ml._wrappers` module is
# the single eager-import site for every Group 1 verb. ``__init__.py``
# imports them from here.
# ---------------------------------------------------------------------------


def autolog(*args: Any, **kwargs: Any) -> Any:
    """Pass-through to :func:`kailash_ml.autolog.autolog`.

    Re-exported at the package level for the ``km.autolog`` idiom.
    The underlying function is an async context manager; the wrapper
    returns the CM object so ``async with km.autolog(): ...`` still
    works.
    """
    return _autolog_cm(*args, **kwargs)


def track(*args: Any, **kwargs: Any) -> Any:
    """Pass-through to :func:`kailash_ml.tracking.track` (async CM)."""
    return _track_cm(*args, **kwargs)


def rl_train(*args: Any, **kwargs: Any) -> Any:
    """Pass-through to :func:`kailash_ml.rl.rl_train`."""
    return _rl_train(*args, **kwargs)


# ---------------------------------------------------------------------------
# Helpers exported from this module for __init__.py plumbing
# ---------------------------------------------------------------------------


__all__ = [
    "train",
    "register",
    "serve",
    "watch",
    "dashboard",
    "diagnose",
    "autolog",
    "autolog_fn",
    "track",
    "rl_train",
    "DashboardHandle",
    "_get_default_engine",
    "_reset_default_engines",
]
