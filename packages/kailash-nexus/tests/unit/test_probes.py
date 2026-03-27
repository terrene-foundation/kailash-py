# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for Kubernetes probe endpoints (S4-001).

Covers:
- ProbeState enum values and transitions
- Thread-safe state management
- Liveness, readiness, and startup probe responses
- Readiness check callbacks
- Invalid transition rejection
- Reset from FAILED state
"""

from __future__ import annotations

import concurrent.futures
import threading

import pytest

from nexus.probes import ProbeManager, ProbeResponse, ProbeState


class TestProbeState:
    """Test ProbeState enum values."""

    def test_state_values(self):
        assert ProbeState.STARTING.value == "starting"
        assert ProbeState.READY.value == "ready"
        assert ProbeState.DRAINING.value == "draining"
        assert ProbeState.FAILED.value == "failed"

    def test_all_states_present(self):
        states = {s.value for s in ProbeState}
        assert states == {"starting", "ready", "draining", "failed"}


class TestProbeResponse:
    """Test ProbeResponse serialization."""

    def test_to_dict_basic(self):
        resp = ProbeResponse(status="ok", http_status=200)
        d = resp.to_dict()
        assert d == {"status": "ok"}

    def test_to_dict_with_details(self):
        resp = ProbeResponse(
            status="ready",
            http_status=200,
            details={"workflows": 3, "state": "ready"},
        )
        d = resp.to_dict()
        assert d["status"] == "ready"
        assert d["details"]["workflows"] == 3

    def test_to_dict_empty_details_omitted(self):
        resp = ProbeResponse(status="ok", http_status=200, details={})
        d = resp.to_dict()
        assert "details" not in d


class TestProbeManagerInit:
    """Test ProbeManager initial state."""

    def test_initial_state_is_starting(self):
        pm = ProbeManager()
        assert pm.state == ProbeState.STARTING

    def test_initial_is_alive(self):
        pm = ProbeManager()
        assert pm.is_alive is True

    def test_initial_not_ready(self):
        pm = ProbeManager()
        assert pm.is_ready is False

    def test_initial_not_started(self):
        pm = ProbeManager()
        assert pm.is_started is False


class TestProbeStateTransitions:
    """Test valid and invalid state transitions."""

    def test_starting_to_ready(self):
        pm = ProbeManager()
        assert pm.mark_ready() is True
        assert pm.state == ProbeState.READY

    def test_starting_to_failed(self):
        pm = ProbeManager()
        assert pm.mark_failed("crash") is True
        assert pm.state == ProbeState.FAILED

    def test_ready_to_draining(self):
        pm = ProbeManager()
        pm.mark_ready()
        assert pm.mark_draining() is True
        assert pm.state == ProbeState.DRAINING

    def test_ready_to_failed(self):
        pm = ProbeManager()
        pm.mark_ready()
        assert pm.mark_failed("oom") is True
        assert pm.state == ProbeState.FAILED

    def test_draining_to_failed(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.mark_draining()
        assert pm.mark_failed("timeout") is True
        assert pm.state == ProbeState.FAILED

    # Invalid transitions
    def test_starting_to_draining_rejected(self):
        pm = ProbeManager()
        assert pm.mark_draining() is False
        assert pm.state == ProbeState.STARTING

    def test_ready_to_starting_not_possible(self):
        """READY cannot go back to STARTING (use reset for that)."""
        pm = ProbeManager()
        pm.mark_ready()
        # There's no mark_starting, and direct _transition is internal
        assert pm.state == ProbeState.READY

    def test_failed_is_terminal(self):
        pm = ProbeManager()
        pm.mark_failed("crash")
        assert pm.mark_ready() is False
        assert pm.mark_draining() is False
        assert pm.state == ProbeState.FAILED

    def test_double_ready_rejected(self):
        pm = ProbeManager()
        pm.mark_ready()
        assert pm.mark_ready() is False  # READY -> READY not allowed

    def test_reset_from_failed(self):
        pm = ProbeManager()
        pm.mark_failed("crash")
        pm.reset()
        assert pm.state == ProbeState.STARTING
        assert pm.is_alive is True

    def test_reset_from_ready(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.reset()
        assert pm.state == ProbeState.STARTING


class TestProbeProperties:
    """Test is_alive, is_ready, is_started properties."""

    def test_alive_in_all_non_failed_states(self):
        pm = ProbeManager()
        assert pm.is_alive  # STARTING
        pm.mark_ready()
        assert pm.is_alive  # READY
        pm.mark_draining()
        assert pm.is_alive  # DRAINING

    def test_not_alive_when_failed(self):
        pm = ProbeManager()
        pm.mark_failed("crash")
        assert pm.is_alive is False

    def test_ready_only_in_ready_state(self):
        pm = ProbeManager()
        assert pm.is_ready is False  # STARTING
        pm.mark_ready()
        assert pm.is_ready is True  # READY
        pm.mark_draining()
        assert pm.is_ready is False  # DRAINING

    def test_started_in_ready_and_draining(self):
        pm = ProbeManager()
        assert pm.is_started is False  # STARTING
        pm.mark_ready()
        assert pm.is_started is True  # READY
        pm.mark_draining()
        assert pm.is_started is True  # DRAINING


class TestLivenessCheck:
    """Test check_liveness() responses."""

    def test_liveness_ok_when_starting(self):
        pm = ProbeManager()
        resp = pm.check_liveness()
        assert resp.status == "ok"
        assert resp.http_status == 200
        assert "uptime_seconds" in resp.details

    def test_liveness_ok_when_ready(self):
        pm = ProbeManager()
        pm.mark_ready()
        resp = pm.check_liveness()
        assert resp.status == "ok"
        assert resp.http_status == 200

    def test_liveness_ok_when_draining(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.mark_draining()
        resp = pm.check_liveness()
        assert resp.status == "ok"
        assert resp.http_status == 200

    def test_liveness_failed_when_failed(self):
        pm = ProbeManager()
        pm.mark_failed("disk full")
        resp = pm.check_liveness()
        assert resp.status == "failed"
        assert resp.http_status == 503
        assert resp.details["reason"] == "disk full"


class TestReadinessCheck:
    """Test check_readiness() responses."""

    def test_not_ready_when_starting(self):
        pm = ProbeManager()
        resp = pm.check_readiness()
        assert resp.status == "not_ready"
        assert resp.http_status == 503

    def test_ready_when_ready(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.set_workflow_count(5)
        resp = pm.check_readiness()
        assert resp.status == "ready"
        assert resp.http_status == 200
        assert resp.details["workflows"] == 5

    def test_not_ready_when_draining(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.mark_draining()
        resp = pm.check_readiness()
        assert resp.status == "not_ready"
        assert resp.http_status == 503

    def test_not_ready_when_failed(self):
        pm = ProbeManager()
        pm.mark_failed("crash")
        resp = pm.check_readiness()
        assert resp.status == "not_ready"
        assert resp.http_status == 503


class TestReadinessCallbacks:
    """Test readiness check callback system."""

    def test_callback_passing(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.add_readiness_check(lambda: True)
        resp = pm.check_readiness()
        assert resp.status == "ready"
        assert resp.http_status == 200

    def test_callback_failing(self):
        pm = ProbeManager()
        pm.mark_ready()

        def db_check():
            return False

        pm.add_readiness_check(db_check)
        resp = pm.check_readiness()
        assert resp.status == "not_ready"
        assert resp.http_status == 503
        assert "failed_checks" in resp.details

    def test_callback_exception_treated_as_failure(self):
        pm = ProbeManager()
        pm.mark_ready()

        def broken_check():
            raise ConnectionError("database down")

        pm.add_readiness_check(broken_check)
        resp = pm.check_readiness()
        assert resp.status == "not_ready"
        assert resp.http_status == 503

    def test_multiple_callbacks_all_must_pass(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.add_readiness_check(lambda: True)
        pm.add_readiness_check(lambda: True)
        resp = pm.check_readiness()
        assert resp.status == "ready"

    def test_one_failing_callback_fails_overall(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.add_readiness_check(lambda: True)
        pm.add_readiness_check(lambda: False)
        resp = pm.check_readiness()
        assert resp.status == "not_ready"


class TestStartupCheck:
    """Test check_startup() responses."""

    def test_starting_during_init(self):
        pm = ProbeManager()
        resp = pm.check_startup()
        assert resp.status == "starting"
        assert resp.http_status == 503

    def test_started_when_ready(self):
        pm = ProbeManager()
        pm.mark_ready()
        resp = pm.check_startup()
        assert resp.status == "started"
        assert resp.http_status == 200
        assert "startup_duration_seconds" in resp.details

    def test_started_when_draining(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.mark_draining()
        resp = pm.check_startup()
        assert resp.status == "started"
        assert resp.http_status == 200

    def test_starting_when_failed(self):
        pm = ProbeManager()
        pm.mark_failed("crash")
        resp = pm.check_startup()
        assert resp.status == "starting"
        assert resp.http_status == 503


class TestThreadSafety:
    """Test concurrent access to ProbeManager."""

    def test_concurrent_mark_ready(self):
        """Only one thread should succeed in transitioning STARTING -> READY."""
        pm = ProbeManager()
        results = []
        barrier = threading.Barrier(10)

        def try_mark_ready():
            barrier.wait()
            results.append(pm.mark_ready())

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(try_mark_ready) for _ in range(10)]
            concurrent.futures.wait(futures)

        # Exactly one True (successful transition), rest False
        assert results.count(True) == 1
        assert results.count(False) == 9
        assert pm.state == ProbeState.READY

    def test_concurrent_reads_safe(self):
        """Multiple concurrent reads should not corrupt state."""
        pm = ProbeManager()
        pm.mark_ready()
        pm.set_workflow_count(10)

        errors = []

        def check_all():
            try:
                for _ in range(100):
                    assert pm.is_alive
                    assert pm.is_ready
                    pm.check_liveness()
                    pm.check_readiness()
                    pm.check_startup()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=check_all) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestWorkflowCount:
    """Test workflow count tracking."""

    def test_set_workflow_count(self):
        pm = ProbeManager()
        pm.mark_ready()
        pm.set_workflow_count(42)
        resp = pm.check_readiness()
        assert resp.details["workflows"] == 42

    def test_workflow_count_in_not_ready(self):
        pm = ProbeManager()
        pm.set_workflow_count(3)
        resp = pm.check_readiness()
        assert resp.details["workflows"] == 3
