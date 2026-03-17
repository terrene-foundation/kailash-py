"""Integration tests for Two-Phase Commit with ParticipantTransport.

Tests the full 2PC protocol using LocalNodeTransport (with MockNodeExecutor)
and HttpTransport (with aiohttp TestServer). These tests exercise the
coordinator end-to-end without mocking any 2PC internal methods.

Copyright 2026 Terrene Foundation
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from kailash.nodes.transaction.node_executor import MockNodeExecutor
from kailash.nodes.transaction.participant_transport import (
    HttpTransport,
    LocalNodeTransport,
    TransportResult,
)
from kailash.nodes.transaction.two_phase_commit import (
    ParticipantVote,
    TransactionState,
    TwoPhaseCommitCoordinatorNode,
    TwoPhaseCommitParticipant,
)


# ---------------------------------------------------------------------------
# Integration: 2PC with LocalNodeTransport (3 local participants, all commit)
# ---------------------------------------------------------------------------


class TestTwoPhaseCommitLocalTransportAllCommit:
    """End-to-end 2PC with 3 local participants that all vote prepared."""

    @pytest.fixture
    def executor(self):
        executor = MockNodeExecutor()
        # All three participants vote prepared on prepare, succeed on commit
        for name in ("inventory", "payment", "shipping"):
            executor.set_response(name, {"vote": "prepared", "status": "ok"})
        return executor

    @pytest.fixture
    def coordinator(self, executor):
        transport = LocalNodeTransport(executor)
        return TwoPhaseCommitCoordinatorNode(
            transaction_name="order_fulfillment",
            participants=["inventory", "payment", "shipping"],
            prepare_timeout=10,
            commit_timeout=10,
            transport=transport,
        )

    @pytest.mark.asyncio
    async def test_full_commit_lifecycle(self, coordinator, executor):
        """Three participants all prepare and commit successfully."""
        # Begin
        begin_result = await coordinator.async_run(
            operation="begin_transaction",
            context={"order_id": "ORD-001", "total": 299.99},
        )
        assert begin_result["status"] == "success"

        # Execute (prepare + commit)
        exec_result = await coordinator.async_run(operation="execute_transaction")

        assert exec_result["status"] == "success"
        assert exec_result["state"] == "committed"
        assert coordinator.state == TransactionState.COMMITTED
        assert coordinator.completed_at is not None

        # Verify all participants were contacted
        # Each participant gets called twice: once for prepare, once for commit
        called_types = [c["node_type"] for c in executor.calls]
        for name in ("inventory", "payment", "shipping"):
            assert called_types.count(name) == 2  # prepare + commit

        # Verify prepare calls included the context
        prepare_calls = [
            c for c in executor.calls if c["params"]["operation"] == "prepare"
        ]
        for call in prepare_calls:
            assert call["params"]["context"]["order_id"] == "ORD-001"

    @pytest.mark.asyncio
    async def test_all_participants_have_timestamps_after_commit(self, coordinator):
        """After a successful commit every participant has prepare_time and commit_time."""
        await coordinator.async_run(
            operation="begin_transaction", context={"test": True}
        )
        await coordinator.async_run(operation="execute_transaction")

        for p in coordinator.participants.values():
            assert p.vote == ParticipantVote.PREPARED
            assert p.prepare_time is not None
            assert p.commit_time is not None
            assert p.last_contact is not None

    @pytest.mark.asyncio
    async def test_status_after_commit(self, coordinator):
        """get_status reflects committed state with participant details."""
        await coordinator.async_run(
            operation="begin_transaction", context={"test": True}
        )
        await coordinator.async_run(operation="execute_transaction")

        status = await coordinator.async_run(operation="get_status")
        assert status["state"] == "committed"
        assert len(status["participants"]) == 3
        for p in status["participants"]:
            assert p["vote"] == "prepared"
            assert p["commit_time"] is not None


# ---------------------------------------------------------------------------
# Integration: 2PC with LocalNodeTransport (1 participant votes abort)
# ---------------------------------------------------------------------------


class TestTwoPhaseCommitLocalTransportOneAbort:
    """End-to-end 2PC where one participant votes abort during prepare."""

    @pytest.fixture
    def executor(self):
        executor = MockNodeExecutor()
        # inventory and shipping vote prepared
        executor.set_response("inventory", {"vote": "prepared"})
        executor.set_response("shipping", {"vote": "prepared"})
        # payment votes ABORT
        executor.set_response(
            "payment", {"vote": "abort", "reason": "insufficient funds"}
        )
        return executor

    @pytest.fixture
    def coordinator(self, executor):
        transport = LocalNodeTransport(executor)
        return TwoPhaseCommitCoordinatorNode(
            transaction_name="failing_order",
            participants=["inventory", "payment", "shipping"],
            prepare_timeout=10,
            commit_timeout=10,
            transport=transport,
        )

    @pytest.mark.asyncio
    async def test_transaction_aborts_on_single_abort_vote(self, coordinator, executor):
        """If any participant votes abort, the entire transaction aborts."""
        await coordinator.async_run(
            operation="begin_transaction", context={"order_id": "ORD-002"}
        )

        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "aborted"
        assert result["state"] == "aborted"
        assert coordinator.state == TransactionState.ABORTED

        # Verify abort was sent to all participants
        abort_calls = [c for c in executor.calls if c["params"]["operation"] == "abort"]
        abort_targets = {c["node_type"] for c in abort_calls}
        assert abort_targets == {"inventory", "payment", "shipping"}

    @pytest.mark.asyncio
    async def test_payment_participant_voted_abort(self, coordinator):
        """The payment participant's vote is recorded as ABORT."""
        await coordinator.async_run(
            operation="begin_transaction", context={"order_id": "ORD-002"}
        )
        await coordinator.async_run(operation="execute_transaction")

        payment = coordinator.participants["payment"]
        assert payment.vote == ParticipantVote.ABORT

    @pytest.mark.asyncio
    async def test_no_commit_calls_on_abort(self, coordinator, executor):
        """No commit calls should be made when prepare fails."""
        await coordinator.async_run(
            operation="begin_transaction", context={"order_id": "ORD-002"}
        )
        await coordinator.async_run(operation="execute_transaction")

        commit_calls = [
            c for c in executor.calls if c["params"]["operation"] == "commit"
        ]
        assert len(commit_calls) == 0


# ---------------------------------------------------------------------------
# Integration: 2PC with LocalNodeTransport (executor exception on prepare)
# ---------------------------------------------------------------------------


class TestTwoPhaseCommitLocalTransportExecutorFailure:
    """2PC where a participant's executor raises an exception."""

    @pytest.fixture
    def executor(self):
        executor = MockNodeExecutor()
        executor.set_response("db", {"vote": "prepared"})
        executor.set_failure("cache", RuntimeError("connection reset"))
        return executor

    @pytest.fixture
    def coordinator(self, executor):
        transport = LocalNodeTransport(executor)
        return TwoPhaseCommitCoordinatorNode(
            transaction_name="partial_failure",
            participants=["db", "cache"],
            prepare_timeout=10,
            commit_timeout=10,
            transport=transport,
        )

    @pytest.mark.asyncio
    async def test_executor_error_causes_abort(self, coordinator):
        """An exception from the executor causes the participant to vote abort."""
        await coordinator.async_run(
            operation="begin_transaction", context={"key": "value"}
        )

        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "aborted"
        assert coordinator.state == TransactionState.ABORTED
        assert coordinator.participants["cache"].vote == ParticipantVote.ABORT


# ---------------------------------------------------------------------------
# Helper: aiohttp test server for HTTP transport integration tests
# ---------------------------------------------------------------------------


def _make_participant_app(
    vote: str = "prepared",
    commit_ok: bool = True,
    abort_ok: bool = True,
) -> web.Application:
    """Build an aiohttp app simulating a 2PC participant."""

    call_log: list[Dict[str, Any]] = []

    async def handle_prepare(request: web.Request) -> web.Response:
        body = await request.json()
        call_log.append({"phase": "prepare", "body": body})
        return web.json_response({"vote": vote})

    async def handle_commit(request: web.Request) -> web.Response:
        body = await request.json()
        call_log.append({"phase": "commit", "body": body})
        if commit_ok:
            return web.json_response({"status": "committed"})
        return web.json_response({"error": "commit failed"}, status=500)

    async def handle_abort(request: web.Request) -> web.Response:
        body = await request.json()
        call_log.append({"phase": "abort", "body": body})
        if abort_ok:
            return web.json_response({"status": "aborted"})
        return web.json_response({"error": "abort failed"}, status=500)

    app = web.Application()
    app.router.add_post("/2pc/prepare", handle_prepare)
    app.router.add_post("/2pc/commit", handle_commit)
    app.router.add_post("/2pc/abort", handle_abort)
    app["call_log"] = call_log
    return app


async def _start_test_server(app: web.Application) -> TestServer:
    """Create and start a TestServer for the given app."""
    server = TestServer(app)
    await server.start_server()
    return server


# ---------------------------------------------------------------------------
# Integration: 2PC with HttpTransport (full HTTP round-trip)
# ---------------------------------------------------------------------------


class TestTwoPhaseCommitHttpTransportAllCommit:
    """Full 2PC over HTTP with three participant servers that all commit."""

    @pytest.mark.asyncio
    async def test_http_full_commit(self):
        # Start 3 participant HTTP servers
        apps = []
        servers = []
        for _ in range(3):
            app = _make_participant_app(vote="prepared")
            server = await _start_test_server(app)
            apps.append(app)
            servers.append(server)

        transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
        try:
            coordinator = TwoPhaseCommitCoordinatorNode(
                transaction_name="http_order",
                prepare_timeout=5,
                commit_timeout=5,
                transport=transport,
            )

            # Add participants with real server endpoints
            names = ["inventory", "payment", "shipping"]
            for name, srv in zip(names, servers):
                await coordinator.async_run(
                    operation="add_participant",
                    participant_id=name,
                    endpoint=f"http://localhost:{srv.port}/2pc",
                )

            # Begin + Execute
            await coordinator.async_run(
                operation="begin_transaction",
                context={"order_id": "HTTP-001"},
            )

            result = await coordinator.async_run(operation="execute_transaction")

            assert result["status"] == "success"
            assert result["state"] == "committed"
            assert coordinator.state == TransactionState.COMMITTED

            # Each server saw prepare + commit
            for app in apps:
                phases = [entry["phase"] for entry in app["call_log"]]
                assert "prepare" in phases
                assert "commit" in phases
        finally:
            await transport.close()
            for srv in servers:
                await srv.close()


class TestTwoPhaseCommitHttpTransportOneAbort:
    """Full 2PC over HTTP where one participant votes abort."""

    @pytest.mark.asyncio
    async def test_http_abort_on_vote(self):
        # Two participants vote prepared, one votes abort
        app_ok1 = _make_participant_app(vote="prepared")
        app_ok2 = _make_participant_app(vote="prepared")
        app_abort = _make_participant_app(vote="abort")

        server_ok1 = await _start_test_server(app_ok1)
        server_ok2 = await _start_test_server(app_ok2)
        server_abort = await _start_test_server(app_abort)

        all_servers = [server_ok1, server_ok2, server_abort]

        transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
        try:
            coordinator = TwoPhaseCommitCoordinatorNode(
                transaction_name="http_abort_test",
                prepare_timeout=5,
                commit_timeout=5,
                transport=transport,
            )

            await coordinator.async_run(
                operation="add_participant",
                participant_id="ok_svc_1",
                endpoint=f"http://localhost:{server_ok1.port}/2pc",
            )
            await coordinator.async_run(
                operation="add_participant",
                participant_id="ok_svc_2",
                endpoint=f"http://localhost:{server_ok2.port}/2pc",
            )
            await coordinator.async_run(
                operation="add_participant",
                participant_id="abort_svc",
                endpoint=f"http://localhost:{server_abort.port}/2pc",
            )

            await coordinator.async_run(
                operation="begin_transaction",
                context={"order_id": "HTTP-002"},
            )

            result = await coordinator.async_run(operation="execute_transaction")

            assert result["status"] == "aborted"
            assert result["state"] == "aborted"
            assert coordinator.state == TransactionState.ABORTED

            # Verify abort was sent to all participants
            for app in (app_ok1, app_ok2, app_abort):
                phases = [entry["phase"] for entry in app["call_log"]]
                assert "prepare" in phases
                assert "abort" in phases
                # No commit should have been sent
                assert "commit" not in phases
        finally:
            await transport.close()
            for srv in all_servers:
                await srv.close()


# ---------------------------------------------------------------------------
# Integration: backward compatibility (default transport, no executor)
# ---------------------------------------------------------------------------


class TestTwoPhaseCommitDefaultTransportBackwardCompat:
    """Verify the coordinator works with the default LocalNodeTransport(None).

    This ensures backward compatibility: the coordinator works exactly as
    before when no transport is explicitly provided.
    """

    @pytest.mark.asyncio
    async def test_default_transport_commit(self):
        """Default transport with MockNodeExecutor succeeds."""
        # Real RegistryNodeExecutor — TestParticipantNode registered via conftest
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="compat_test",
            participants=[
                "TestParticipantNode",
                "TestParticipantNode",
                "TestParticipantNode",
            ],
        )

        await coordinator.async_run(
            operation="begin_transaction", context={"compat": True}
        )

        result = await coordinator.async_run(operation="execute_transaction")

        assert result["status"] == "success"
        assert result["state"] == "committed"

        # All participants voted prepared
        for p in coordinator.participants.values():
            assert p.vote == ParticipantVote.PREPARED
            assert p.commit_time is not None

    @pytest.mark.asyncio
    async def test_default_transport_abort(self):
        """Manual abort with default transport."""
        coordinator = TwoPhaseCommitCoordinatorNode(
            transaction_name="abort_compat",
            participants=["svc1", "svc2"],
        )

        await coordinator.async_run(operation="begin_transaction")

        result = await coordinator.async_run(operation="abort_transaction")

        assert result["status"] == "success"
        assert result["state"] == "aborted"
