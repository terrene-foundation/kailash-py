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
    ) -> None:
        self._db_url = db_url
        self._artifact_root = artifact_root
        self._host = host
        self._port = port
        self._dashboard_app: Any | None = None

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
