# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W11 Tier-1 unit tests — run lifecycle, status transitions, parent wiring.

Per ``specs/ml-tracking.md`` §3.2 + §3.5, every terminal status MUST be
one of the 4-member set ``{FINISHED, FAILED, KILLED}`` (+ ``RUNNING`` as
the sole pre-terminal). Legacy ``COMPLETED`` / ``SUCCESS`` / ``SUCCEEDED``
are BLOCKED — ``RunStatus`` MUST NOT carry any of those as class
attributes and the ``_ALLOWED_STATUSES`` frozenset MUST match exactly.

The tests below use the in-memory ``sqlite+memory`` alias — Tier 1 is
permitted to mock via ``store="sqlite+memory"`` per `rules/testing.md`
§ Tier 1, and the backend itself is real SQLite not a mock.
"""
from __future__ import annotations

import asyncio

import pytest
from kailash_ml.tracking import ExperimentTracker, get_current_run
from kailash_ml.tracking.runner import _ALLOWED_STATUSES, RunStatus

# ---------------------------------------------------------------------------
# Status enum byte-parity invariants (spec §3.5 Decision 3)
# ---------------------------------------------------------------------------


def test_run_status_members_match_4_member_spec() -> None:
    """The enum MUST be byte-identical to the 4-member cross-SDK set."""
    assert RunStatus.RUNNING == "RUNNING"
    assert RunStatus.FINISHED == "FINISHED"
    assert RunStatus.FAILED == "FAILED"
    assert RunStatus.KILLED == "KILLED"


def test_run_status_has_no_legacy_completed_attribute() -> None:
    """Legacy ``COMPLETED`` MUST NOT leak back in (spec §3.2)."""
    assert not hasattr(RunStatus, "COMPLETED")
    assert not hasattr(RunStatus, "SUCCESS")
    assert not hasattr(RunStatus, "SUCCEEDED")
    assert not hasattr(RunStatus, "CANCELLED")
    assert not hasattr(RunStatus, "DONE")


def test_allowed_statuses_frozenset_matches_spec() -> None:
    """Structural invariant: the frozenset is exactly the spec 4-member set."""
    assert _ALLOWED_STATUSES == frozenset({"RUNNING", "FINISHED", "FAILED", "KILLED"})


# ---------------------------------------------------------------------------
# Status transitions (spec §3.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_exit_records_finished() -> None:
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("clean") as run:
            pass
        # Refetch to see the persisted terminal status.
        rows = await tracker._backend.list_runs("clean")
        assert len(rows) == 1
        assert rows[0]["status"] == RunStatus.FINISHED
        assert rows[0]["run_id"] == run.run_id
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_exception_exit_records_failed_and_reraises() -> None:
    tracker = await ExperimentTracker.create("sqlite+memory")
    run_id_captured = ""
    try:
        with pytest.raises(ValueError, match="user code"):
            async with tracker.track("boom") as run:
                run_id_captured = run.run_id
                raise ValueError("user code")
        rows = await tracker._backend.list_runs("boom")
        assert len(rows) == 1
        assert rows[0]["status"] == RunStatus.FAILED
        assert rows[0]["run_id"] == run_id_captured
        assert rows[0]["error_type"] == "ValueError"
        assert "user code" in (rows[0]["error_message"] or "")
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_cancelled_error_records_killed() -> None:
    """Spec §3.2 — ``asyncio.CancelledError`` maps to KILLED."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        with pytest.raises(asyncio.CancelledError):
            async with tracker.track("cancelled"):
                raise asyncio.CancelledError()
        rows = await tracker._backend.list_runs("cancelled")
        assert len(rows) == 1
        assert rows[0]["status"] == RunStatus.KILLED
        assert rows[0]["error_type"] == "CancelledError"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_keyboard_interrupt_records_killed() -> None:
    """Spec §3.2 — KeyboardInterrupt (raw signal surface) → KILLED."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        with pytest.raises(KeyboardInterrupt):
            async with tracker.track("sigint"):
                raise KeyboardInterrupt()
        rows = await tracker._backend.list_runs("sigint")
        assert len(rows) == 1
        assert rows[0]["status"] == RunStatus.KILLED
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# Parent-run resolution (spec §3.1 MUST honor + §3.4 ambient fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_parent_run_id_wins_over_ambient() -> None:
    """Spec §3.1 MUST honor every kwarg — explicit ``parent_run_id``
    MUST be used even when an ambient run is active."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("outer") as outer:
            async with tracker.track(
                "inner", parent_run_id="fixed-parent-abc"
            ) as inner:
                # Explicit kwarg wins; ambient (outer.run_id) is ignored.
                assert inner.parent_run_id == "fixed-parent-abc"
                assert inner.parent_run_id != outer.run_id
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_ambient_parent_used_when_no_explicit_kwarg() -> None:
    """Spec §3.4 — ambient contextvar resolves when parent_run_id omitted."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        async with tracker.track("outer") as outer:
            async with tracker.track("inner") as inner:
                assert inner.parent_run_id == outer.run_id
                assert get_current_run() is inner
            assert get_current_run() is outer
        assert get_current_run() is None
    finally:
        await tracker.close()


# ---------------------------------------------------------------------------
# Sync-variant start_run / end_run parity path (spec §11.2 + W11 DoD)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_end_run_round_trip_finished() -> None:
    """Non-context-manager pair persists FINISHED on explicit end_run."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        run = await tracker.start_run("explicit", lr=0.05)
        assert run.run_id
        rows_running = await tracker._backend.list_runs("explicit")
        assert rows_running[0]["status"] == RunStatus.RUNNING
        await tracker.end_run(run, status="FINISHED")
        rows_done = await tracker._backend.list_runs("explicit")
        assert rows_done[0]["status"] == RunStatus.FINISHED
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_end_run_rejects_legacy_completed_status() -> None:
    """Legacy ``COMPLETED`` MUST be rejected at the sync API surface."""
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        run = await tracker.start_run("legacy")
        with pytest.raises(ValueError, match="spec ml-tracking.md §3.2"):
            await tracker.end_run(run, status="COMPLETED")
        # Clean up the still-running row.
        await tracker.end_run(run, status="FINISHED")
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_end_run_killed_persists_killed_and_reason() -> None:
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        run = await tracker.start_run("killed-explicit")
        await tracker.end_run(run, status="KILLED")
        rows = await tracker._backend.list_runs("killed-explicit")
        assert rows[0]["status"] == RunStatus.KILLED
        assert run._killed_reason == "end_run.explicit"
    finally:
        await tracker.close()


@pytest.mark.asyncio
async def test_end_run_failed_with_error_records_type_and_msg() -> None:
    tracker = await ExperimentTracker.create("sqlite+memory")
    try:
        run = await tracker.start_run("failed-explicit")
        await tracker.end_run(run, status="FAILED", error=RuntimeError("boom explicit"))
        rows = await tracker._backend.list_runs("failed-explicit")
        assert rows[0]["status"] == RunStatus.FAILED
        assert rows[0]["error_type"] == "RuntimeError"
        assert "boom explicit" in (rows[0]["error_message"] or "")
    finally:
        await tracker.close()
