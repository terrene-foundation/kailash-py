"""Unit tests for TODO-026: MCP Executor with real circuit breaker."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.nodes.enterprise.mcp_executor import (
    CircuitBreaker,
    CircuitState,
    EnterpriseMLCPExecutorNode,
    _circuit_breakers,
    _get_circuit_breaker,
)


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_record_success(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.success_rate == 1.0

    def test_record_failure_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=5, success_rate_threshold=0.5)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_circuit_opens_on_threshold(self):
        cb = CircuitBreaker(
            failure_threshold=3, success_rate_threshold=0.8, window_size=10
        )
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(
            failure_threshold=2,
            success_rate_threshold=0.8,
            recovery_timeout=0.01,
            window_size=10,
        )
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_success_in_half_open_closes_circuit(self):
        cb = CircuitBreaker(
            failure_threshold=2,
            success_rate_threshold=0.8,
            recovery_timeout=0.01,
            window_size=10,
        )
        for _ in range(5):
            cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_success_rate_calculation(self):
        cb = CircuitBreaker(window_size=10)
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        assert abs(cb.success_rate - 2 / 3) < 0.01


class TestGetCircuitBreaker:
    def setup_method(self):
        _circuit_breakers.clear()

    def test_creates_new(self):
        cb = _get_circuit_breaker("server-1")
        assert isinstance(cb, CircuitBreaker)

    def test_returns_same_instance(self):
        cb1 = _get_circuit_breaker("server-1")
        cb2 = _get_circuit_breaker("server-1")
        assert cb1 is cb2

    def test_different_servers_different_instances(self):
        cb1 = _get_circuit_breaker("server-1")
        cb2 = _get_circuit_breaker("server-2")
        assert cb1 is not cb2


class TestEnterpriseMLCPExecutorNode:
    def setup_method(self):
        _circuit_breakers.clear()

    def test_metadata(self):
        node = EnterpriseMLCPExecutorNode()
        assert "mcp" in node.metadata.tags
        assert "enterprise" in node.metadata.tags

    def test_get_parameters(self):
        node = EnterpriseMLCPExecutorNode()
        params = node.get_parameters()
        assert "tool_request" in params
        assert "circuit_breaker_enabled" in params
        assert "success_rate_threshold" in params

    def test_no_random_in_source(self):
        """Verify that random module is not used in the executor."""
        import inspect

        from kailash.nodes.enterprise import mcp_executor

        source = inspect.getsource(mcp_executor)
        assert "random.random()" not in source
        assert "random.randint(" not in source
        assert "random.choice(" not in source
        assert "random.uniform(" not in source

    def test_circuit_breaker_open_returns_failure(self):
        node = EnterpriseMLCPExecutorNode()

        # Pre-open the circuit
        cb = _get_circuit_breaker("test-server", success_rate_threshold=0.9)
        for _ in range(20):
            cb.record_failure()

        result = node.run(
            tool_request={"tool": "test", "parameters": {}, "server_id": "test-server"},
            circuit_breaker_enabled=True,
            success_rate_threshold=0.9,
        )

        assert result["success"] is False
        assert "Circuit breaker OPEN" in result["error"]
        assert result["fallback_used"] is True

    @patch("kailash.nodes.enterprise.mcp_executor._execute_mcp_tool")
    def test_successful_execution(self, mock_execute):
        """Successful MCP tool call records success in circuit breaker."""
        import asyncio

        mock_execute.return_value = {"data": {"answer": 42}, "is_error": False}

        node = EnterpriseMLCPExecutorNode()

        # Patch asyncio.run to return our mock result
        with patch(
            "asyncio.run", return_value={"data": {"answer": 42}, "is_error": False}
        ):
            result = node.run(
                tool_request={
                    "tool": "analytics",
                    "parameters": {"query": "test"},
                    "server_id": "http://mcp-server:8080",
                },
                circuit_breaker_enabled=True,
            )

        assert result["success"] is True
        assert result["data"] == {"answer": 42}
        assert result["compliance_validated"] is True
        assert "audit_info" in result
        assert "execution_results" in result

    @patch("kailash.nodes.enterprise.mcp_executor._execute_mcp_tool")
    def test_failed_execution_records_failure(self, mock_execute):
        """Failed MCP tool call records failure in circuit breaker."""
        from kailash.sdk_exceptions import NodeExecutionError

        mock_execute.side_effect = NodeExecutionError("connection refused")

        node = EnterpriseMLCPExecutorNode()

        with patch("asyncio.run", side_effect=NodeExecutionError("connection refused")):
            with pytest.raises(NodeExecutionError):
                node.run(
                    tool_request={
                        "tool": "test",
                        "parameters": {},
                        "server_id": "bad-server",
                    },
                    circuit_breaker_enabled=True,
                )

        # Verify failure was recorded
        cb = _get_circuit_breaker("bad-server")
        assert cb.success_rate < 1.0

    def test_circuit_breaker_disabled(self):
        """When circuit breaker is disabled, no CB logic executes."""
        node = EnterpriseMLCPExecutorNode()

        with patch("asyncio.run", return_value={"data": "ok", "is_error": False}):
            result = node.run(
                tool_request={"tool": "test", "parameters": {}, "server_id": "srv"},
                circuit_breaker_enabled=False,
            )

        assert result["success"] is True
        assert result["circuit_state"] == CircuitState.CLOSED

    def test_audit_info_present(self):
        node = EnterpriseMLCPExecutorNode()

        with patch("asyncio.run", return_value={"data": {}, "is_error": False}):
            result = node.run(
                tool_request={"tool": "t", "parameters": {}, "server_id": "s"},
            )

        assert "execution_id" in result["audit_info"]
        assert "timestamp" in result["audit_info"]
        assert result["audit_info"]["compliance_checked"] is True
