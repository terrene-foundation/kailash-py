"""Unit tests for ParticipantTransport implementations.

Tests LocalNodeTransport with MockNodeExecutor and HttpTransport with
an aiohttp TestServer. Following Tier 1 testing policy: fast execution,
mocking allowed for unit tests.

Copyright 2026 Terrene Foundation
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from kailash.nodes.transaction.node_executor import MockNodeExecutor
from kailash.nodes.transaction.participant_transport import (
    HttpTransport,
    LocalNodeTransport,
    ParticipantTransport,
    TransportResult,
)
from kailash.nodes.transaction.two_phase_commit import TwoPhaseCommitParticipant


# ---------------------------------------------------------------------------
# TransportResult tests
# ---------------------------------------------------------------------------


class TestTransportResult:
    """Test the TransportResult frozen dataclass."""

    def test_success_result(self):
        result = TransportResult(success=True, vote="prepared")
        assert result.success is True
        assert result.vote == "prepared"
        assert result.error is None
        assert result.details is None

    def test_failure_result(self):
        result = TransportResult(
            success=False, vote="abort", error="timeout", details={"code": 504}
        )
        assert result.success is False
        assert result.vote == "abort"
        assert result.error == "timeout"
        assert result.details == {"code": 504}

    def test_frozen(self):
        result = TransportResult(success=True)
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify that concrete transports satisfy the Protocol at runtime."""

    def test_local_node_transport_is_participant_transport(self):
        transport = LocalNodeTransport()
        assert isinstance(transport, ParticipantTransport)

    def test_http_transport_is_participant_transport(self):
        transport = HttpTransport(allow_private_urls=True)
        assert isinstance(transport, ParticipantTransport)


# ---------------------------------------------------------------------------
# LocalNodeTransport tests
# ---------------------------------------------------------------------------


class TestLocalNodeTransportNoExecutor:
    """LocalNodeTransport with default executor (RegistryNodeExecutor)."""

    @pytest.fixture
    def transport(self):
        # Use MockNodeExecutor since test participant IDs aren't real registered nodes
        return LocalNodeTransport(executor=MockNodeExecutor())

    @pytest.fixture
    def participant(self):
        return TwoPhaseCommitParticipant(
            participant_id="svc_a",
            endpoint="http://svc_a/2pc",
            timeout=10,
            retry_count=2,
        )

    @pytest.mark.asyncio
    async def test_prepare_returns_prepared(self, transport, participant):
        result = await transport.prepare(participant, "tx-001")
        assert result.success is True
        assert result.vote == "prepared"

    @pytest.mark.asyncio
    async def test_commit_returns_success(self, transport, participant):
        result = await transport.commit(participant, "tx-001")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_abort_returns_success(self, transport, participant):
        result = await transport.abort(participant, "tx-001")
        assert result.success is True


class TestLocalNodeTransportWithMockExecutor:
    """LocalNodeTransport backed by MockNodeExecutor."""

    @pytest.fixture
    def executor(self):
        return MockNodeExecutor()

    @pytest.fixture
    def transport(self, executor):
        return LocalNodeTransport(executor)

    @pytest.fixture
    def participant(self):
        return TwoPhaseCommitParticipant(
            participant_id="PaymentNode",
            endpoint="http://payment/2pc",
            timeout=30,
            retry_count=3,
        )

    @pytest.mark.asyncio
    async def test_prepare_success(self, transport, executor, participant):
        """Prepare delegates to executor.execute with operation=prepare."""
        executor.set_response("PaymentNode", {"vote": "prepared", "ready": True})

        result = await transport.prepare(participant, "tx-100", {"amount": 50})

        assert result.success is True
        assert result.vote == "prepared"
        assert result.details["ready"] is True

        # Verify executor was called correctly
        assert len(executor.calls) == 1
        call = executor.calls[0]
        assert call["node_type"] == "PaymentNode"
        assert call["params"]["operation"] == "prepare"
        assert call["params"]["transaction_id"] == "tx-100"
        assert call["params"]["context"]["amount"] == 50

    @pytest.mark.asyncio
    async def test_prepare_abort_vote(self, transport, executor, participant):
        """Participant voting abort is surfaced via TransportResult."""
        executor.set_response(
            "PaymentNode", {"vote": "abort", "reason": "insufficient funds"}
        )

        result = await transport.prepare(participant, "tx-101")

        assert result.success is True  # executor call succeeded
        assert result.vote == "abort"  # but participant voted abort

    @pytest.mark.asyncio
    async def test_prepare_executor_failure(self, transport, executor, participant):
        """Executor exception results in abort vote."""
        executor.set_failure("PaymentNode", RuntimeError("connection refused"))

        result = await transport.prepare(participant, "tx-102")

        assert result.success is False
        assert result.vote == "abort"
        assert "connection refused" in result.error

    @pytest.mark.asyncio
    async def test_commit_success(self, transport, executor, participant):
        executor.set_response("PaymentNode", {"status": "committed"})

        result = await transport.commit(participant, "tx-103")

        assert result.success is True
        assert len(executor.calls) == 1
        assert executor.calls[0]["params"]["operation"] == "commit"

    @pytest.mark.asyncio
    async def test_commit_failure(self, transport, executor, participant):
        executor.set_failure("PaymentNode", RuntimeError("disk full"))

        result = await transport.commit(participant, "tx-104")

        assert result.success is False
        assert "disk full" in result.error

    @pytest.mark.asyncio
    async def test_abort_success(self, transport, executor, participant):
        executor.set_response("PaymentNode", {"status": "aborted"})

        result = await transport.abort(participant, "tx-105")

        assert result.success is True
        assert len(executor.calls) == 1
        assert executor.calls[0]["params"]["operation"] == "abort"

    @pytest.mark.asyncio
    async def test_abort_failure_returns_result(self, transport, executor, participant):
        """Abort failures are returned as TransportResult, not raised."""
        executor.set_failure("PaymentNode", RuntimeError("unreachable"))

        result = await transport.abort(participant, "tx-106")

        assert result.success is False
        assert "unreachable" in result.error

    @pytest.mark.asyncio
    async def test_prepare_uses_participant_timeout(
        self, transport, executor, participant
    ):
        """Verify that the participant's timeout is forwarded to the executor."""
        executor.set_response("PaymentNode", {"vote": "prepared"})

        await transport.prepare(participant, "tx-107")

        call = executor.calls[0]
        assert call["timeout"] == 30.0  # participant.timeout


# ---------------------------------------------------------------------------
# Helper: create and start an aiohttp test server
# ---------------------------------------------------------------------------


def _make_2pc_app(
    prepare_response: Optional[Dict[str, Any]] = None,
    commit_response: Optional[Dict[str, Any]] = None,
    abort_response: Optional[Dict[str, Any]] = None,
    prepare_status: int = 200,
    commit_status: int = 200,
    abort_status: int = 200,
) -> web.Application:
    """Build a minimal aiohttp app that simulates a 2PC participant."""

    call_log: list[Dict[str, Any]] = []

    async def handle_prepare(request: web.Request) -> web.Response:
        body = await request.json()
        call_log.append({"phase": "prepare", "body": body})
        resp = prepare_response or {"vote": "prepared"}
        return web.json_response(resp, status=prepare_status)

    async def handle_commit(request: web.Request) -> web.Response:
        body = await request.json()
        call_log.append({"phase": "commit", "body": body})
        resp = commit_response or {"status": "committed"}
        return web.json_response(resp, status=commit_status)

    async def handle_abort(request: web.Request) -> web.Response:
        body = await request.json()
        call_log.append({"phase": "abort", "body": body})
        resp = abort_response or {"status": "aborted"}
        return web.json_response(resp, status=abort_status)

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
# HttpTransport tests (with aiohttp TestServer)
# ---------------------------------------------------------------------------


class TestHttpTransportPrepare:
    """HttpTransport.prepare against a real test HTTP server."""

    @pytest.mark.asyncio
    async def test_prepare_success(self):
        app = _make_2pc_app(prepare_response={"vote": "prepared", "wal_position": 42})
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=1,
            )

            result = await transport.prepare(participant, "tx-200", {"key": "val"})
            assert result.success is True
            assert result.vote == "prepared"
            assert result.details["wal_position"] == 42

            # Verify the server received the correct payload
            assert len(app["call_log"]) == 1
            log_entry = app["call_log"][0]
            assert log_entry["phase"] == "prepare"
            assert log_entry["body"]["transaction_id"] == "tx-200"
            assert log_entry["body"]["context"]["key"] == "val"

            await transport.close()
        finally:
            await server.close()

    @pytest.mark.asyncio
    async def test_prepare_server_votes_abort(self):
        app = _make_2pc_app(prepare_response={"vote": "abort", "reason": "locked"})
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=1,
            )

            result = await transport.prepare(participant, "tx-201")
            # Server returned 200 but vote=abort
            assert result.success is True
            assert result.vote == "abort"

            await transport.close()
        finally:
            await server.close()

    @pytest.mark.asyncio
    async def test_prepare_server_error(self):
        app = _make_2pc_app(
            prepare_response={"vote": "abort", "error": "internal"},
            prepare_status=500,
        )
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=1,
            )

            result = await transport.prepare(participant, "tx-202")
            assert result.success is False
            assert result.vote == "abort"
            assert "HTTP 500" in result.error

            await transport.close()
        finally:
            await server.close()

    @pytest.mark.asyncio
    async def test_prepare_connection_refused(self):
        """Transport handles unreachable participants gracefully."""
        transport = HttpTransport(default_timeout=2.0, allow_private_urls=True)
        participant = TwoPhaseCommitParticipant(
            participant_id="ghost",
            endpoint="http://localhost:19999/2pc",  # nothing listening
            timeout=2,
            retry_count=1,
        )

        try:
            result = await transport.prepare(participant, "tx-203")
            assert result.success is False
            assert result.vote == "abort"
            assert result.error is not None
        finally:
            await transport.close()


class TestHttpTransportCommit:
    """HttpTransport.commit against a real test HTTP server."""

    @pytest.mark.asyncio
    async def test_commit_success(self):
        app = _make_2pc_app(commit_response={"status": "committed"})
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=1,
            )

            result = await transport.commit(participant, "tx-300")
            assert result.success is True
            assert app["call_log"][0]["body"]["transaction_id"] == "tx-300"

            await transport.close()
        finally:
            await server.close()

    @pytest.mark.asyncio
    async def test_commit_server_error(self):
        app = _make_2pc_app(
            commit_response={"error": "disk full"},
            commit_status=500,
        )
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=1,
            )

            result = await transport.commit(participant, "tx-301")
            assert result.success is False
            assert "HTTP 500" in result.error

            await transport.close()
        finally:
            await server.close()

    @pytest.mark.asyncio
    async def test_commit_retries_on_server_error(self):
        """Commit retries on 5xx and eventually fails after retry_count."""
        app = _make_2pc_app(
            commit_response={"error": "overloaded"},
            commit_status=503,
        )
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=3,
            )

            result = await transport.commit(participant, "tx-302")
            assert result.success is False
            # All 3 retries should have been attempted
            assert len(app["call_log"]) == 3

            await transport.close()
        finally:
            await server.close()


class TestHttpTransportAbort:
    """HttpTransport.abort against a real test HTTP server."""

    @pytest.mark.asyncio
    async def test_abort_success(self):
        app = _make_2pc_app(abort_response={"status": "aborted"})
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=1,
            )

            result = await transport.abort(participant, "tx-400")
            assert result.success is True
            assert app["call_log"][0]["body"]["transaction_id"] == "tx-400"

            await transport.close()
        finally:
            await server.close()

    @pytest.mark.asyncio
    async def test_abort_server_error_retries(self):
        app = _make_2pc_app(
            abort_response={"error": "busy"},
            abort_status=503,
        )
        server = await _start_test_server(app)
        try:
            transport = HttpTransport(default_timeout=5.0, allow_private_urls=True)
            participant = TwoPhaseCommitParticipant(
                participant_id="db",
                endpoint=f"http://localhost:{server.port}/2pc",
                timeout=5,
                retry_count=2,
            )

            result = await transport.abort(participant, "tx-401")
            assert result.success is False
            assert len(app["call_log"]) == 2

            await transport.close()
        finally:
            await server.close()

    @pytest.mark.asyncio
    async def test_abort_connection_refused(self):
        """Abort handles unreachable participants gracefully."""
        transport = HttpTransport(default_timeout=2.0, allow_private_urls=True)
        participant = TwoPhaseCommitParticipant(
            participant_id="ghost",
            endpoint="http://localhost:19999/2pc",
            timeout=2,
            retry_count=1,
        )

        try:
            result = await transport.abort(participant, "tx-402")
            assert result.success is False
            assert result.error is not None
        finally:
            await transport.close()


class TestHttpTransportSessionManagement:
    """Test session lifecycle for HttpTransport."""

    @pytest.mark.asyncio
    async def test_close_owned_session(self):
        transport = HttpTransport(allow_private_urls=True)
        # Force session creation
        session = await transport._get_session()
        assert not session.closed

        await transport.close()
        assert session.closed

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        transport = HttpTransport(allow_private_urls=True)
        await transport._get_session()
        await transport.close()
        await transport.close()  # second close is no-op

    @pytest.mark.asyncio
    async def test_externally_provided_session(self):
        """When caller provides a session, HttpTransport does not own it."""
        import aiohttp

        app = _make_2pc_app()
        server = await _start_test_server(app)
        try:
            async with aiohttp.ClientSession() as ext_session:
                transport = HttpTransport(session=ext_session, allow_private_urls=True)
                participant = TwoPhaseCommitParticipant(
                    participant_id="ext",
                    endpoint=f"http://localhost:{server.port}/2pc",
                    timeout=5,
                    retry_count=1,
                )

                result = await transport.prepare(participant, "tx-500")
                assert result.success is True
                # Session still open since we provided it externally
                assert not ext_session.closed
        finally:
            await server.close()
