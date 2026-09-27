# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ML experiment dashboard -- web UI for viewing experiments, runs, metrics.

Serves a single-page dashboard backed by ExperimentTracker + ModelRegistry
engines, using Starlette for the ASGI app and uvicorn as the server.

Usage::

    from kailash_ml.dashboard import MLDashboard

    dashboard = MLDashboard(db_url="sqlite:///ml.db")
    dashboard.serve(host="0.0.0.0", port=5000)

**Callable-module shim** — per ``rules/orphan-detection.md §6`` the public
Group-1 verb ``km.dashboard(...)`` is eager-imported in
:mod:`kailash_ml.__init__` as a module-scope callable. However Python's
import machinery sets ``kailash_ml.dashboard`` to THIS submodule object
the moment any test does ``from kailash_ml.dashboard import MLDashboard``,
silently shadowing the verb. To keep both surfaces working without
renaming the subpackage (breaking public import paths), this module
installs a ``_CallableModule`` subclass of :class:`types.ModuleType` that
forwards ``__call__`` to the :func:`kailash_ml._wrappers.dashboard`
verb. The callable-module pattern is a standard Python technique (PEP
562 / ``sys.modules[__name__].__class__`` assignment).
"""
from __future__ import annotations

import asyncio
import logging
import sys as _sys
from types import ModuleType as _ModuleType
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["MLDashboard", "main"]


class MLDashboard:
    """Web dashboard for kailash-ml experiment tracking.

    Serves a web UI for viewing experiments, runs, metrics, and models.
    Backed by ExperimentTracker + ModelRegistry engines.

    Parameters
    ----------
    db_url:
        Database URL for the experiment store. Defaults to a local SQLite file.
    artifact_root:
        Root directory for artifact storage.
    host:
        Bind address for the dashboard server.
    port:
        Port for the dashboard server.
    """

    def __init__(
        self,
        db_url: str = "sqlite:///kailash-ml.db",
        artifact_root: str = "./mlartifacts",
        host: str = "127.0.0.1",
        port: int = 5000,
        tenant_id: str | None = None,
        title: str = "Kailash ML",
        enable_control: bool = False,
        auth: str | None = None,
        cors_origins: tuple[str, ...] | None = None,
    ) -> None:
        """Initialize the dashboard orchestrator.

        Args:
            db_url: Database URL for the experiment store.
            artifact_root: Root directory for artifact storage.
            host: Bind address for the dashboard server.
            port: Bind port for the dashboard server.
            tenant_id: Optional tenant_id pinned on the dashboard instance.
                When set, every view filters to rows / runs / models
                scoped to this tenant (propagated to ``DashboardApp``).
            title: Human-readable page title surfaced in the HTML views.
            enable_control: Mount the WebSocket control routes (write
                operations — pause / resume / checkpoint). The CLI
                refuses non-loopback binds without ``auth``; this flag is
                consumed by the CLI wrapper in addition to being stored
                here for introspection.
            auth: Auth-policy URL (e.g. ``nexus://URL``) required when
                binding to a non-loopback host. Consumed by the CLI
                wrapper; stored here for introspection.
            cors_origins: Tuple of permitted CORS origins. Consumed by
                the CLI wrapper; stored here for introspection.
        """
        self._db_url = db_url
        self._artifact_root = artifact_root
        self._host = host
        self._port = port
        self._tenant_id = tenant_id
        self._title = title
        self._enable_control = enable_control
        self._auth = auth
        self._cors_origins: tuple[str, ...] = cors_origins or ()
        self._dashboard_app: Any | None = None

        # auth / cors_origins / enable_control are currently CLI-surface
        # configuration consumed by the cli.py wrapper; plumbing them
        # through the dashboard middleware layer is tracked as a P1
        # follow-up (see specs/ml-dashboard.md §8.3). Emit a single
        # DEBUG line on construction so operators can observe non-default
        # values via log introspection; a WARN would clutter normal runs.
        if enable_control or auth is not None or self._cors_origins:
            logger.debug(
                "mldashboard.init.cli_config",
                extra={
                    "enable_control": enable_control,
                    "auth_configured": auth is not None,
                    "cors_origin_count": len(self._cors_origins),
                    "tenant_id": tenant_id,
                    "title": title,
                },
            )

    def serve(self, host: str | None = None, port: int | None = None) -> None:
        """Start the dashboard server (blocking).

        Parameters
        ----------
        host:
            Override the bind address. Uses the constructor value if None.
        port:
            Override the port. Uses the constructor value if None.
        """
        import uvicorn

        from kailash_ml.dashboard.server import DashboardApp

        bind_host = host or self._host
        bind_port = port or self._port

        dashboard_app = DashboardApp(
            db_url=self._db_url,
            artifact_root=self._artifact_root,
            tenant_id=self._tenant_id if self._tenant_id is not None else "dashboard",
        )

        async def _lifespan_app() -> Any:
            await dashboard_app.initialize()
            return dashboard_app.app

        app = asyncio.get_event_loop().run_until_complete(_lifespan_app())

        logger.info(
            "Starting kailash-ml dashboard at http://%s:%d",
            bind_host,
            bind_port,
        )

        try:
            uvicorn.run(app, host=bind_host, port=bind_port, log_level="info")
        finally:
            asyncio.get_event_loop().run_until_complete(dashboard_app.close())

    async def serve_async(
        self, host: str | None = None, port: int | None = None
    ) -> None:
        """Start the dashboard server (async).

        Parameters
        ----------
        host:
            Override the bind address. Uses the constructor value if None.
        port:
            Override the port. Uses the constructor value if None.
        """
        import uvicorn

        from kailash_ml.dashboard.server import DashboardApp

        bind_host = host or self._host
        bind_port = port or self._port

        self._dashboard_app = DashboardApp(
            db_url=self._db_url,
            artifact_root=self._artifact_root,
            tenant_id=self._tenant_id if self._tenant_id is not None else "dashboard",
        )
        await self._dashboard_app.initialize()

        logger.info(
            "Starting kailash-ml dashboard at http://%s:%d",
            bind_host,
            bind_port,
        )

        config = uvicorn.Config(
            self._dashboard_app.app,
            host=bind_host,
            port=bind_port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        try:
            await server.serve()
        finally:
            await self._dashboard_app.close()


def main() -> None:
    """CLI entry point: kailash-ml-dashboard --port 5000 --db sqlite:///ml.db"""
    import click

    @click.command()
    @click.option("--port", default=5000, type=int, help="Dashboard port")
    @click.option("--host", default="127.0.0.1", help="Dashboard host")
    @click.option("--db", default="sqlite:///kailash-ml.db", help="Database URL")
    @click.option(
        "--artifact-root", default="./mlartifacts", help="Artifact storage root"
    )
    def serve(port: int, host: str, db: str, artifact_root: str) -> None:
        """Launch the kailash-ml experiment dashboard."""
        dashboard = MLDashboard(
            db_url=db,
            artifact_root=artifact_root,
            host=host,
            port=port,
        )
        dashboard.serve()

    serve()


# ---------------------------------------------------------------------------
# Callable-module shim (see module docstring for rationale).
# ---------------------------------------------------------------------------


class _CallableDashboardModule(_ModuleType):
    """Make ``kailash_ml.dashboard(...)`` forward to the Group-1 verb.

    Python's import machinery unconditionally sets
    ``kailash_ml.dashboard`` to this module object when any code runs
    ``import kailash_ml.dashboard`` or
    ``from kailash_ml.dashboard import ...``. That would silently
    overwrite the eager-imported ``dashboard`` callable exposed by
    :mod:`kailash_ml.__init__`, breaking the ``km.dashboard(...)``
    Group-1 contract tested by
    ``tests/unit/test_km_eager_imports.py::test_group_1_verbs_are_callable``.

    By swapping this module's ``__class__`` to a ``ModuleType`` subclass
    with ``__call__``, the module object IS callable — so
    ``kailash_ml.dashboard(...)`` still works as a verb invocation even
    after submodule loading.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # Lazy import to avoid a circular import at package init time.
        from kailash_ml._wrappers import dashboard as _dashboard_verb

        return _dashboard_verb(*args, **kwargs)


_sys.modules[__name__].__class__ = _CallableDashboardModule
