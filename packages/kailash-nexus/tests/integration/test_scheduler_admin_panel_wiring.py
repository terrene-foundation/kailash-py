# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 integration — Nexus scheduler-admin HTTP panel (issue #937).

NO mocking (rules/testing.md Tier 2). Exercises the six routes registered by
``nexus.admin.register_scheduler_admin`` end-to-end through a real HTTP client
against a real ``Nexus`` app, a real ``WorkflowScheduler``, and a real
``SchedulerAdminAPI``. Assertions observe externally-visible effects: the
schedule's ``enabled`` state changes after a PATCH, the cron edit changes
``trigger_args``, delete removes the schedule, and the audit log records the
JWT subject as ``actor`` (orphan/facade non-wiring guard).

Uses ``httpx.AsyncClient`` + ``ASGITransport`` so the HTTP calls and the
``AsyncIOScheduler`` share ONE event loop (a starlette ``TestClient`` would
drive the app in a separate loop from the async-fixture-started scheduler).

Skips if APScheduler is not installed.
"""

from __future__ import annotations

from typing import List, Optional

import httpx
import jwt as pyjwt
import pytest

pytest.importorskip("apscheduler", reason="WorkflowScheduler requires APScheduler")

from nexus import Nexus
from nexus.admin import register_scheduler_admin
from nexus.auth.jwt import JWTConfig, JWTMiddleware

JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"  # noqa: S105 (test secret, ≥32B)
ADMIN_ROLE = "scheduler-admin"


def _make_token(sub: str, roles: Optional[List[str]] = None) -> str:
    payload = {"sub": sub, "roles": roles or []}
    return pyjwt.encode(payload, JWT_TEST_SECRET, algorithm="HS256")


def _auth(sub: str, roles: Optional[List[str]] = None) -> dict:
    return {"Authorization": f"Bearer {_make_token(sub, roles)}"}


def _trivial_workflow():
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "noop", {"code": "result = {'ok': True}"})
    return builder


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
async def panel():
    """Yield (client, scheduler) — real Nexus app + scheduler + admin panel."""
    from kailash.runtime.scheduler import WorkflowScheduler
    from kailash.runtime.scheduler_admin import SchedulerAdminAPI

    scheduler = WorkflowScheduler(job_store_path=None)
    scheduler.start()

    app = Nexus(api_port=_free_port(), auto_discovery=False)
    app.fastapi_app.add_middleware(
        JWTMiddleware,
        config=JWTConfig(secret=JWT_TEST_SECRET, algorithm="HS256"),
    )
    admin = SchedulerAdminAPI(scheduler)
    register_scheduler_admin(app, admin)

    transport = httpx.ASGITransport(app=app.fastapi_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    try:
        yield client, scheduler
    finally:
        await client.aclose()
        scheduler.shutdown(wait=False)
        try:
            app.stop()
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerAdminPanelRoundTrip:
    """Full list/get/disable/enable/cron/delete cycle through HTTP."""

    async def test_round_trip_through_http(self, panel, caplog):
        import logging

        client, scheduler = panel
        admin_auth = _auth("ops-alice", roles=[ADMIN_ROLE])

        sid = scheduler.schedule_cron(
            _trivial_workflow(), "0 6 * * *", name="morning-job"
        )

        # list
        resp = await client.get("/admin/schedules", headers=admin_auth)
        assert resp.status_code == 200, resp.text
        listed = resp.json()
        assert any(v["schedule_id"] == sid for v in listed)

        # get
        resp = await client.get(f"/admin/schedules/{sid}", headers=admin_auth)
        assert resp.status_code == 200
        assert resp.json()["schedule_type"] == "cron"

        # disable — observe enabled flips False + audit actor == JWT subject
        with caplog.at_level(logging.INFO, logger="kailash.runtime.scheduler_admin"):
            resp = await client.patch(
                f"/admin/schedules/{sid}/disable", headers=admin_auth
            )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
        assert "ops-alice" in caplog.text  # actor sourced from JWT sub, not body

        # confirm state change via re-read (external observation)
        resp = await client.get(f"/admin/schedules/{sid}", headers=admin_auth)
        assert resp.status_code == 200, resp.text
        assert resp.json()["enabled"] is False  # fresh read, not stale-cached (#937)

        # enable
        resp = await client.patch(f"/admin/schedules/{sid}/enable", headers=admin_auth)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        # update cron — trigger_args reflects the new expression
        resp = await client.patch(
            f"/admin/schedules/{sid}/cron",
            headers=admin_auth,
            json={"cron_expression": "30 7 * * *"},
        )
        assert resp.status_code == 200
        assert resp.json()["trigger_args"] == {"cron_expression": "30 7 * * *"}

        # delete → 204, then get → 404
        resp = await client.delete(f"/admin/schedules/{sid}", headers=admin_auth)
        assert resp.status_code == 204
        resp = await client.get(f"/admin/schedules/{sid}", headers=admin_auth)
        assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerAdminPanelAuthAndErrors:
    """401 / 403 / 404 / 400 status mapping through HTTP."""

    async def test_no_token_is_401(self, panel):
        client, _ = panel
        resp = await client.get("/admin/schedules")
        assert resp.status_code == 401

    async def test_wrong_role_is_403(self, panel):
        client, _ = panel
        resp = await client.get(
            "/admin/schedules", headers=_auth("intruder", roles=["viewer"])
        )
        assert resp.status_code == 403

    async def test_unknown_id_is_404(self, panel):
        client, _ = panel
        resp = await client.get(
            "/admin/schedules/sched-deadbeef0000",
            headers=_auth("ops", roles=[ADMIN_ROLE]),
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"

    async def test_invalid_cron_is_400(self, panel):
        client, scheduler = panel
        sid = scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")
        resp = await client.patch(
            f"/admin/schedules/{sid}/cron",
            headers=_auth("ops", roles=[ADMIN_ROLE]),
            json={"cron_expression": "not-a-valid-cron"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "validation_error"
