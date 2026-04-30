"""Regression: #712 (S2) — sibling FastAPI sites drive router.on_startup.

Three public classes were confirmed (in `workspaces/issues-712-714/01-analysis/`)
to construct FastAPI with `lifespan=` set BUT NOT iterate `app.router.on_startup` /
`app.router.on_shutdown` — silent #500-class bugs:

  - APIGateway   — `src/kailash/middleware/communication/api_gateway.py`
  - WorkflowAPIGateway  — `src/kailash/api/gateway.py`
  - WorkflowAPI         — `src/kailash/api/workflow_api.py`

The fix routes their custom `lifespan` through the shared helpers
`drive_router_lifespan_startup` / `drive_router_lifespan_shutdown` (added in
S1). This test exercises the lifespan via Starlette's public
`router.lifespan_context` — the same context manager uvicorn invokes in
production — registering `@app.on_event("startup")` and asserting it fires.

This regression MUST NOT be deleted per `rules/orphan-detection.md` Rule 4.
"""

from __future__ import annotations

import pytest


@pytest.mark.regression
@pytest.mark.asyncio
async def test_workflow_api_drives_router_on_startup():
    """WorkflowAPI lifespan iterates router.on_startup post-S2."""
    from fastapi import FastAPI

    from kailash.api.workflow_api import WorkflowAPI
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "noop", {"code": "result = {'ok': True}"})
    api = WorkflowAPI(builder.build())
    app: FastAPI = api.app

    fired: list[int] = []

    async def my_startup() -> None:
        fired.append(1)

    async def my_shutdown() -> None:
        fired.append(-1)

    app.router.add_event_handler("startup", my_startup)
    app.router.add_event_handler("shutdown", my_shutdown)

    # Drive lifespan via Starlette's public lifespan_context (same as uvicorn)
    async with app.router.lifespan_context(app):
        pass

    assert fired == [1, -1], (
        f"WorkflowAPI router-iteration broken: hooks did not fire (got {fired}). "
        f"Pre-S2 the custom _lifespan replaced Starlette's _DefaultLifespan "
        f"and silently dropped every router.on_startup/on_shutdown handler."
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_workflow_api_gateway_drives_router_on_startup():
    """WorkflowAPIGateway (api/gateway.py) lifespan iterates router.on_startup."""
    from fastapi import FastAPI

    from kailash.api.gateway import WorkflowAPIGateway

    gateway = WorkflowAPIGateway()
    app: FastAPI = gateway.app

    fired: list[int] = []

    async def my_startup() -> None:
        fired.append(1)

    async def my_shutdown() -> None:
        fired.append(-1)

    app.router.add_event_handler("startup", my_startup)
    app.router.add_event_handler("shutdown", my_shutdown)

    async with app.router.lifespan_context(app):
        pass

    assert fired == [1, -1], (
        f"WorkflowAPIGateway router-iteration broken: hooks did not fire "
        f"(got {fired}). Pre-S2 this was an unmitigated #500-class bug."
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_kailash_api_gateway_drives_router_on_startup():
    """APIGateway (middleware) lifespan iterates router.on_startup."""
    pytest.importorskip("kailash.middleware.communication.api_gateway")

    from fastapi import FastAPI

    from kailash.middleware.communication.api_gateway import APIGateway

    try:
        gateway = APIGateway()
    except Exception as e:
        pytest.skip(f"APIGateway construction requires deps: {e}")
    app: FastAPI = gateway.app

    fired: list[int] = []

    async def my_startup() -> None:
        fired.append(1)

    async def my_shutdown() -> None:
        fired.append(-1)

    app.router.add_event_handler("startup", my_startup)
    app.router.add_event_handler("shutdown", my_shutdown)

    async with app.router.lifespan_context(app):
        pass

    assert fired == [1, -1], (
        f"APIGateway router-iteration broken: hooks did not fire "
        f"(got {fired}). Pre-S2 this was an unmitigated #500-class bug."
    )


@pytest.mark.regression
def test_sibling_lifespans_call_shared_helper():
    """Mechanical sweep: every sibling FastAPI site MUST call the helper.

    Per `rules/security.md` § Multi-Site Kwarg Plumbing, all three sibling
    sites and the canonical workflow_server.py MUST route through the shared
    helper. This grep audit fails loudly if a future refactor inlines
    `router.on_startup` iteration at any one site without the helper, or
    drops the helper call from a site.
    """
    from pathlib import Path

    repo_root = Path(__file__).parent.parent.parent
    sites = [
        repo_root / "src/kailash/middleware/communication/api_gateway.py",
        repo_root / "src/kailash/api/gateway.py",
        repo_root / "src/kailash/api/workflow_api.py",
        repo_root / "src/kailash/servers/workflow_server.py",
    ]
    for site in sites:
        text = site.read_text()
        assert "drive_router_lifespan_startup" in text, (
            f"{site.name} no longer calls drive_router_lifespan_startup — "
            f"if the lifespan was removed entirely, drop this site from the "
            f"audit; if a sibling helper was used instead, re-route through "
            f"the shared helper. See rules/security.md § Multi-Site Kwarg "
            f"Plumbing."
        )
        assert (
            "drive_router_lifespan_shutdown" in text
        ), f"{site.name} no longer calls drive_router_lifespan_shutdown."
