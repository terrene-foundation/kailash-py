# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for ``SchedulerAdminAPI`` (issue #913).

Per ``rules/testing.md`` Tier 2: NO mocking — every test runs against
a real ``WorkflowScheduler`` with an in-memory APScheduler job store.
The admin surface is exercised end-to-end and assertions observe
externally-visible behavior:

* ``next_run_time`` reflects cron edits within one tick.
* Disable / enable round-trip preserves schedule state.
* Delete removes the schedule from the listing.
* Retry spec + time-limit fields surface in the admin view (#910/#912
  pass-through reads).

The scheduler uses APScheduler's ``AsyncIOScheduler`` which requires a
running event loop at ``start()`` time — every test is therefore
async-marked so the fixture's ``scheduler.start()`` runs inside the
pytest-asyncio event loop.

Skips if APScheduler is not installed.
"""

from __future__ import annotations

import pytest

apscheduler = pytest.importorskip(
    "apscheduler", reason="WorkflowScheduler requires APScheduler"
)


def _trivial_workflow():
    """Build a do-nothing WorkflowBuilder safe to schedule under any cron.

    The body is a single PythonCodeNode that writes a constant — no
    side effects, no I/O. Sufficient for asserting that APScheduler
    accepts the registration and surfaces the schedule through the
    admin view; the firing semantics are covered by sibling tests.
    """
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "noop", {"code": "result = {'ok': True}"})
    return builder


@pytest.fixture
async def started_scheduler():
    """Yield a started in-memory ``WorkflowScheduler`` and shut it down.

    Async fixture so ``AsyncIOScheduler.start()`` runs inside the
    pytest-asyncio event loop (it calls ``asyncio.get_running_loop()``).
    """
    from kailash.runtime.scheduler import WorkflowScheduler

    sched = WorkflowScheduler(job_store_path=None)
    sched.start()
    try:
        yield sched
    finally:
        sched.shutdown(wait=False)


@pytest.fixture
async def admin(started_scheduler):
    """Return a ``SchedulerAdminAPI`` bound to the running scheduler."""
    from kailash.runtime.scheduler_admin import SchedulerAdminAPI

    return SchedulerAdminAPI(started_scheduler)


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerAdminAPIListAndGet:
    """list / get expose schedules through a JSON-friendly view."""

    async def test_list_returns_empty_when_no_schedules(self, admin):
        assert admin.list_schedules() == []

    async def test_list_surfaces_registered_cron_schedule(
        self, started_scheduler, admin
    ):
        sid = started_scheduler.schedule_cron(
            _trivial_workflow(), "0 6 * * *", name="morning-job"
        )

        views = admin.list_schedules()

        assert len(views) == 1
        view = views[0]
        assert view["schedule_id"] == sid
        assert view["schedule_type"] == "cron"
        assert view["workflow_name"] == "morning-job"
        assert view["trigger_args"] == {"cron_expression": "0 6 * * *"}
        assert view["enabled"] is True
        assert view["next_run_time"] is not None
        # Internal kwarg keys MUST NOT leak through the admin view.
        assert "_kailash_retry_spec" not in view["kwargs"]
        assert "_kailash_time_limits" not in view["kwargs"]

    async def test_get_schedule_returns_view_for_known_id(
        self, started_scheduler, admin
    ):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")

        view = admin.get_schedule(sid)

        assert view["schedule_id"] == sid
        assert view["schedule_type"] == "cron"

    async def test_get_schedule_raises_for_unknown_id(self, admin):
        from kailash.sdk_exceptions import ScheduleNotFound

        with pytest.raises(ScheduleNotFound) as exc:
            admin.get_schedule("sched-deadbeef0000")

        assert exc.value.schedule_id == "sched-deadbeef0000"


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerAdminAPIMutations:
    """disable / enable / update_cron / delete change observable state."""

    async def test_disable_then_list_shows_disabled(self, started_scheduler, admin):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")

        view = admin.disable_schedule(sid, actor="ops@example.com")

        assert view["enabled"] is False
        assert view["next_run_time"] is None
        # Confirm via list — read sees the same state.
        listed = {v["schedule_id"]: v for v in admin.list_schedules()}
        assert listed[sid]["enabled"] is False

    async def test_enable_after_disable_resumes_cadence(self, started_scheduler, admin):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")
        admin.disable_schedule(sid, actor="ops@example.com")

        view = admin.enable_schedule(sid, actor="ops@example.com")

        assert view["enabled"] is True
        assert view["next_run_time"] is not None

    async def test_update_cron_shifts_next_run_time(self, started_scheduler, admin):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")
        before = admin.get_schedule(sid)["next_run_time"]
        # Sanity check: cron parsing produced an actual fire time.
        assert before is not None and "T06:" in before

        view = admin.update_cron(sid, "0 7 * * *", actor="ops@example.com")

        assert view["trigger_args"] == {"cron_expression": "0 7 * * *"}
        # Externally visible: APScheduler recomputed next_run_time to
        # the new cron's first matching instant. Hour MUST be 07 now,
        # not 06.
        after = view["next_run_time"]
        assert (
            after is not None and "T07:" in after
        ), f"update_cron did not shift next_run_time to 07:00 — got {after!r}"

    async def test_update_cron_rejects_invalid_expression(
        self, started_scheduler, admin
    ):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")

        with pytest.raises(ValueError, match="invalid cron"):
            admin.update_cron(sid, "garbage", actor="ops@example.com")

    async def test_update_cron_refuses_non_cron_schedule(
        self, started_scheduler, admin
    ):
        sid = started_scheduler.schedule_interval(_trivial_workflow(), seconds=60)

        with pytest.raises(ValueError, match="only valid for cron"):
            admin.update_cron(sid, "0 7 * * *", actor="ops@example.com")

    async def test_delete_removes_from_listing(self, started_scheduler, admin):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")

        admin.delete_schedule(sid, actor="ops@example.com")

        assert all(v["schedule_id"] != sid for v in admin.list_schedules())

    async def test_delete_unknown_id_raises_typed_not_found(self, admin):
        from kailash.sdk_exceptions import ScheduleNotFound

        with pytest.raises(ScheduleNotFound):
            admin.delete_schedule("sched-missing0000", actor="ops@example.com")

    async def test_disable_unknown_id_raises_typed_not_found(self, admin):
        from kailash.sdk_exceptions import ScheduleNotFound

        with pytest.raises(ScheduleNotFound):
            admin.disable_schedule("sched-missing0000", actor="ops@example.com")


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerAdminAPIAuditAndIsolation:
    """Audit log + actor validation + tenant scope acceptance."""

    async def test_empty_actor_rejected_on_mutation(self, started_scheduler, admin):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")

        with pytest.raises(ValueError, match="non-empty string"):
            admin.disable_schedule(sid, actor="")

    async def test_whitespace_actor_rejected(self, started_scheduler, admin):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")

        with pytest.raises(ValueError, match="non-empty string"):
            admin.update_cron(sid, "0 7 * * *", actor="   ")

    async def test_audit_log_records_actor_and_schedule_id(
        self, started_scheduler, admin, caplog
    ):
        import logging

        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")
        with caplog.at_level(logging.INFO, logger="kailash.runtime.scheduler_admin"):
            admin.disable_schedule(sid, actor="ops@example.com")

        # Structural assertion: at least one INFO record with the
        # expected logger name carries the action keyword + schedule_id.
        # We assert structure (record exists with the expected logger
        # name + action + sid in its formatted message) NOT message
        # contents per `rules/probe-driven-verification.md` rule 3 —
        # the structural check is the deterministic probe for "the
        # audit log fired"; the body contents are covered by the
        # structured fields the logger emits.
        admin_records = [
            r for r in caplog.records if r.name == "kailash.runtime.scheduler_admin"
        ]
        assert any(
            "scheduler.admin.disable" in r.getMessage() and sid in r.getMessage()
            for r in admin_records
        ), (
            "audit log did not emit a scheduler.admin.disable record naming "
            f"the disabled schedule_id {sid!r}"
        )

    async def test_admin_rejects_none_scheduler(self):
        from kailash.runtime.scheduler_admin import SchedulerAdminAPI

        with pytest.raises(ValueError, match="non-None"):
            SchedulerAdminAPI(None)  # type: ignore[arg-type]

    async def test_admin_rejects_empty_tenant_scope(self, started_scheduler):
        from kailash.runtime.scheduler_admin import SchedulerAdminAPI

        with pytest.raises(ValueError, match="non-empty string"):
            SchedulerAdminAPI(started_scheduler, tenant_scope="")


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerAdminAPIRetryAndTimeLimitPassthrough:
    """retry_spec + time_limits surface through the admin view (#910/#912)."""

    async def test_retry_spec_surfaces_in_view(self, started_scheduler, admin):
        from kailash.runtime.scheduler import RetrySpec

        spec = RetrySpec(
            max_retries=3,
            backoff="exponential",
            backoff_base_seconds=1.0,
            backoff_max_seconds=30.0,
            retry_on=(ConnectionError, TimeoutError),
        )
        sid = started_scheduler.schedule_cron(
            _trivial_workflow(), "0 6 * * *", retry=spec
        )

        view = admin.get_schedule(sid)

        assert view["retry_spec"] is not None
        assert view["retry_spec"]["max_retries"] == 3
        assert view["retry_spec"]["backoff"] == "exponential"
        assert "ConnectionError" in view["retry_spec"]["retry_on"]
        assert "TimeoutError" in view["retry_spec"]["retry_on"]

    async def test_time_limits_surface_in_view(self, started_scheduler, admin):
        sid = started_scheduler.schedule_cron(
            _trivial_workflow(),
            "0 6 * * *",
            soft_time_limit=2.0,
            time_limit=5.0,
        )

        view = admin.get_schedule(sid)

        assert view["time_limits"] == {
            "soft_time_limit": 2.0,
            "time_limit": 5.0,
        }

    async def test_no_retry_or_time_limits_surfaces_as_null(
        self, started_scheduler, admin
    ):
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")

        view = admin.get_schedule(sid)

        assert view["retry_spec"] is None
        assert view["time_limits"] == {
            "soft_time_limit": None,
            "time_limit": None,
        }


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulerAdminAPIWiringThroughFacade:
    """R2-001 closure: the ``WorkflowScheduler.admin_api`` property + runtime
    re-export are the documented use paths. Per ``rules/orphan-detection.md``
    Rule 1 + ``facade-manager-detection.md`` Rule 1, the manager class MUST
    have a production call site AND be discoverable via the framework
    facade. This test exercises BOTH wiring paths end-to-end.
    """

    async def test_runtime_reexports_scheduler_admin_surface(self):
        """Top-level re-export: ``from kailash.runtime import SchedulerAdminAPI``
        resolves to the same class as the underlying module export.

        Imports here are inside the test (not at module top) so the test
        itself exercises the re-export path. Same-class identity assertion
        guards against a future refactor that ships a divergent shim.
        """
        from kailash.runtime import (
            DEFAULT_TENANT_SCOPE,
            ScheduleAdminView,
            ScheduleNotFound,
            SchedulerAdminAPI,
        )
        from kailash.runtime import scheduler_admin as _admin_module
        from kailash.sdk_exceptions import ScheduleNotFound as _exc_module

        assert SchedulerAdminAPI is _admin_module.SchedulerAdminAPI
        assert ScheduleAdminView is _admin_module.ScheduleAdminView
        assert DEFAULT_TENANT_SCOPE == _admin_module.DEFAULT_TENANT_SCOPE
        assert ScheduleNotFound is _exc_module

    async def test_admin_api_property_returns_bound_admin(self, started_scheduler):
        """``scheduler.admin_api`` returns a SchedulerAdminAPI bound to THIS
        scheduler — no parallel state.
        """
        from kailash.runtime import SchedulerAdminAPI

        admin = started_scheduler.admin_api

        assert isinstance(admin, SchedulerAdminAPI)
        # The admin's internal scheduler reference IS the same object.
        # (Per facade-manager-detection.md Rule 3 the admin holds the
        # parent framework instance — exposing the identity via the
        # public ``_visible_ids`` filter would be intrusive; we assert
        # that mutations on the admin observably touch the scheduler.)
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")
        listed_via_property = admin.list_schedules()
        assert sid in {v["schedule_id"] for v in listed_via_property}

    async def test_admin_api_property_memoizes_same_instance(self, started_scheduler):
        """Repeated property access returns the SAME admin object.

        Memoization matters because ops UIs frequently re-read the
        property per request; allocating a fresh admin every time would
        defeat any per-admin caching the surface might add later AND
        confuses identity-based assertions in test code.
        """
        first = started_scheduler.admin_api
        second = started_scheduler.admin_api
        third = started_scheduler.admin_api

        assert first is second, "admin_api property allocated a new admin"
        assert second is third

    async def test_admin_api_property_drives_update_cron_path(self, started_scheduler):
        """Property-driven mutation: ``scheduler.admin_api.update_cron(...)``
        changes the schedule's next fire time, end-to-end through the
        documented use path (no direct SchedulerAdminAPI(...) construction).

        This is the same observable assertion as
        ``test_update_cron_shifts_next_run_time`` above, but routed through
        the property — proving the property IS a production call site for
        the manager (closing the orphan-detection Rule 1 finding).
        """
        sid = started_scheduler.schedule_cron(_trivial_workflow(), "0 6 * * *")
        before = started_scheduler.admin_api.get_schedule(sid)["next_run_time"]
        assert before is not None and "T06:" in before

        view = started_scheduler.admin_api.update_cron(
            sid, "0 7 * * *", actor="ops@example.com"
        )

        assert view["trigger_args"] == {"cron_expression": "0 7 * * *"}
        after = view["next_run_time"]
        assert (
            after is not None and "T07:" in after
        ), f"property-driven update_cron did not shift next_run_time: {after!r}"
