# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: issue #531 — Nexus 2.1.0 lifespan called non-existent
``app.router.startup()`` / ``app.router.shutdown()`` on some FastAPI
versions.

The #500 fix shipped in kailash-nexus 2.1.0 (commit 1535f4be) invoked
``app.router.startup()`` + ``app.router.shutdown()`` believing them to
be stable Starlette coroutines. FastAPI has shipped both
``.startup()`` and the underscore-prefixed ``._startup()`` at
different points, and the version installed in some production
deployments (per the issue reporter) exposed only ``_startup``. Every
production Nexus service on 2.1.0 against that FastAPI version failed
at uvicorn lifespan startup with
``AttributeError: 'APIRouter' object has no attribute 'startup'``.

The fix (2.1.1): iterate ``router.on_startup`` / ``router.on_shutdown``
directly, awaiting any coroutine results. This is what FastAPI's own
``_DefaultLifespan`` does internally and survives every FastAPI /
Starlette version transition — there is no dispatch method name to
drift.

These tests:

1. ``test_workflow_server_lifespan_runs_on_startup_hooks`` —
   behavioural reproduction: construct a WorkflowServer, register
   ``on_startup`` + ``on_shutdown`` handlers on the FastAPI router,
   drive the lifespan context, assert both handlers fire. On 2.1.0
   this raised ``AttributeError`` before the ``yield``; on 2.1.1+ it
   completes cleanly.

2. ``test_lifespan_survives_missing_startup_method`` — structural
   pin: the lifespan implementation MUST NOT call any method named
   ``startup`` / ``shutdown`` / ``_startup`` / ``_shutdown`` on
   ``app.router``. Driving ``on_startup`` / ``on_shutdown`` lists is
   the only version-stable surface.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from kailash.servers.workflow_server import WorkflowServer


@pytest.mark.regression
@pytest.mark.asyncio
async def test_workflow_server_lifespan_runs_on_startup_hooks() -> None:
    """Lifespan MUST run registered on_startup + on_shutdown handlers.

    Reproduction of the #531 crash: constructing a WorkflowServer,
    registering on_startup / on_shutdown handlers, and driving the
    FastAPI lifespan context manager must fire both.
    """
    server = WorkflowServer(title="issue-531-regression", version="test")

    startup_calls: list[str] = []
    shutdown_calls: list[str] = []

    async def _on_startup() -> None:
        startup_calls.append("fired")

    async def _on_shutdown() -> None:
        shutdown_calls.append("fired")

    app: FastAPI = server.app
    app.router.on_startup.append(_on_startup)
    app.router.on_shutdown.append(_on_shutdown)

    # Drive the lifespan via FastAPI's bound context — the exact path
    # uvicorn uses at boot. On 2.1.0 this raised AttributeError inside
    # the context manager because `app.router.startup()` did not exist.
    async with app.router.lifespan_context(app):
        assert startup_calls == ["fired"], (
            f"on_startup handler did not fire during lifespan; "
            f"workflow_server.lifespan regressed "
            f"(startup_calls={startup_calls!r})"
        )

    assert shutdown_calls == ["fired"], (
        f"on_shutdown handler did not fire during lifespan teardown; "
        f"workflow_server.lifespan shutdown regressed "
        f"(shutdown_calls={shutdown_calls!r})"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_lifespan_fires_handlers_even_when_dispatch_methods_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifespan MUST fire on_startup / on_shutdown handlers even when
    the FastAPI APIRouter exposes NEITHER ``.startup()`` NOR
    ``._startup()``.

    This is the structural defense against #531: FastAPI has shipped
    both method names at different points, so the only version-stable
    path is iterating the ``on_startup`` / ``on_shutdown`` lists. This
    test patches BOTH dispatch method names off the APIRouter to prove
    the lifespan never calls them — if the lifespan regresses to
    calling either method, this test raises ``AttributeError`` inside
    the context manager.
    """
    server = WorkflowServer(title="issue-531-no-dispatch", version="test")
    app: FastAPI = server.app

    # Poison both potential dispatch method names — if the lifespan
    # calls either, the call raises and the test fails. Simulates
    # the issue reporter's FastAPI version where one of the two
    # raised AttributeError; confirms the fix doesn't depend on
    # either method existing.
    def _poisoned(*_args: object, **_kwargs: object) -> None:
        raise AttributeError(
            "workflow_server.lifespan called a version-drifting "
            "dispatch method (startup/_startup/shutdown/_shutdown) — "
            "it should iterate router.on_startup / router.on_shutdown "
            "directly per #531."
        )

    for attr in ("startup", "shutdown", "_startup", "_shutdown"):
        monkeypatch.setattr(app.router, attr, _poisoned, raising=False)

    fired: list[str] = []

    async def _on_startup() -> None:
        fired.append("startup")

    async def _on_shutdown() -> None:
        fired.append("shutdown")

    app.router.on_startup.append(_on_startup)
    app.router.on_shutdown.append(_on_shutdown)

    async with app.router.lifespan_context(app):
        assert fired == ["startup"], (
            f"on_startup did not fire when dispatch methods were "
            f"removed — lifespan is calling a version-drifting method "
            f"rather than iterating on_startup directly. See #531."
        )

    assert fired == ["startup", "shutdown"], (
        f"on_shutdown did not fire when dispatch methods were "
        f"removed — lifespan teardown is calling a version-drifting "
        f"method. See #531."
    )
