"""
Unit Tests for PostureAwareAgent (Tier 1)

Tests posture-based behavior wrapping for Kaizen agents.
Part of CARE-029 implementation.

Coverage:
- FULL_AUTONOMY direct execution
- BLOCKED raises PermissionError
- HUMAN_DECIDES without handler raises ValueError
- SUPERVISED logs audit
- ASSISTED with delay
- Circuit breaker integration
- Success/failure recording to breaker
"""

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.trust.agents.posture_agent import AuditEntry, PostureAwareAgent
from kailash.trust.posture.postures import PostureStateMachine, TrustPosture


# Mock base agent for testing
class MockBaseAgent:
    """Simple mock base agent for testing."""

    def __init__(self, return_value: Optional[Dict[str, Any]] = None):
        self.return_value = return_value or {"answer": "test response"}
        self.call_count = 0
        self.last_kwargs: Optional[Dict[str, Any]] = None

    def run(self, **kwargs: Any) -> Dict[str, Any]:
        """Synchronous run method."""
        self.call_count += 1
        self.last_kwargs = kwargs
        return self.return_value


class MockAsyncBaseAgent:
    """Mock base agent with async run method."""

    def __init__(self, return_value: Optional[Dict[str, Any]] = None):
        self.return_value = return_value or {"answer": "async response"}
        self.call_count = 0
        self.last_kwargs: Optional[Dict[str, Any]] = None

    async def run(self, **kwargs: Any) -> Dict[str, Any]:
        """Asynchronous run method."""
        self.call_count += 1
        self.last_kwargs = kwargs
        return self.return_value


class MockCircuitBreaker:
    """Mock circuit breaker for testing."""

    def __init__(self, is_open_val: bool = False):
        self._is_open = is_open_val
        self.success_count = 0
        self.failure_count = 0

    def is_open(self) -> bool:
        return self._is_open

    def record_success(self) -> None:
        self.success_count += 1

    def record_failure(self) -> None:
        self.failure_count += 1


class MockApprovalHandler:
    """Mock approval handler for testing."""

    def __init__(self, approve: bool = True):
        self._approve = approve
        self.request_count = 0
        self.last_agent_id: Optional[str] = None

    async def request_approval(
        self,
        agent_id: str,
        action_description: str,
        kwargs: Dict[str, Any],
    ) -> bool:
        self.request_count += 1
        self.last_agent_id = agent_id
        return self._approve


class MockNotificationHandler:
    """Mock notification handler for testing."""

    def __init__(self):
        self.notifications: list = []

    async def notify(
        self,
        agent_id: str,
        message: str,
        action_kwargs: Dict[str, Any],
    ) -> None:
        self.notifications.append(
            {
                "agent_id": agent_id,
                "message": message,
                "kwargs": action_kwargs,
            }
        )


@pytest.fixture
def posture_machine() -> PostureStateMachine:
    """Create a posture machine without upgrade approval requirement."""
    return PostureStateMachine(require_upgrade_approval=False)


@pytest.fixture
def mock_agent() -> MockBaseAgent:
    """Create a mock base agent."""
    return MockBaseAgent()


@pytest.fixture
def mock_async_agent() -> MockAsyncBaseAgent:
    """Create a mock async base agent."""
    return MockAsyncBaseAgent()


class TestFullAutonomyExecution:
    """Test FULL_AUTONOMY posture behavior."""

    @pytest.mark.asyncio
    async def test_full_autonomy_direct_execution(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test that FULL_AUTONOMY executes directly without restrictions."""
        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
        )

        result = await agent.run(query="test query")

        assert result == {"answer": "test response"}
        assert mock_agent.call_count == 1
        assert mock_agent.last_kwargs == {"query": "test query"}

    @pytest.mark.asyncio
    async def test_full_autonomy_with_async_agent(
        self, posture_machine: PostureStateMachine, mock_async_agent: MockAsyncBaseAgent
    ):
        """Test FULL_AUTONOMY works with async base agents."""
        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)

        agent = PostureAwareAgent(
            base_agent=mock_async_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
        )

        result = await agent.run(query="async test")

        assert result == {"answer": "async response"}
        assert mock_async_agent.call_count == 1


class TestBlockedExecution:
    """Test BLOCKED posture behavior."""

    @pytest.mark.asyncio
    async def test_blocked_raises_permission_error(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test that BLOCKED posture raises PermissionError."""
        posture_machine.set_posture("agent-001", TrustPosture.PSEUDO)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
        )

        with pytest.raises(PermissionError) as exc_info:
            await agent.run(query="blocked query")

        assert "blocked from execution" in str(exc_info.value)
        assert mock_agent.call_count == 0


class TestHumanDecidesExecution:
    """Test HUMAN_DECIDES posture behavior."""

    @pytest.mark.asyncio
    async def test_human_decides_without_handler_raises(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test that HUMAN_DECIDES without approval_handler raises ValueError."""
        posture_machine.set_posture("agent-001", TrustPosture.PSEUDO)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            approval_handler=None,  # No handler
        )

        with pytest.raises(ValueError) as exc_info:
            await agent.run(query="needs approval")

        assert "requires approval_handler" in str(exc_info.value)
        assert mock_agent.call_count == 0

    @pytest.mark.asyncio
    async def test_human_decides_with_approval(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test HUMAN_DECIDES with approved request executes."""
        posture_machine.set_posture("agent-001", TrustPosture.PSEUDO)
        approval_handler = MockApprovalHandler(approve=True)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            approval_handler=approval_handler,
        )

        result = await agent.run(query="needs approval")

        assert result == {"answer": "test response"}
        assert mock_agent.call_count == 1
        assert approval_handler.request_count == 1

    @pytest.mark.asyncio
    async def test_human_decides_with_denial(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test HUMAN_DECIDES with denied request raises PermissionError."""
        posture_machine.set_posture("agent-001", TrustPosture.PSEUDO)
        approval_handler = MockApprovalHandler(approve=False)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            approval_handler=approval_handler,
        )

        with pytest.raises(PermissionError) as exc_info:
            await agent.run(query="needs approval")

        assert "denied by approver" in str(exc_info.value)
        assert mock_agent.call_count == 0
        assert approval_handler.request_count == 1


class TestSupervisedExecution:
    """Test SUPERVISED posture behavior."""

    @pytest.mark.asyncio
    async def test_supervised_logs_audit(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test that SUPERVISED posture creates audit log entries."""
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
        )

        result = await agent.run(query="supervised query")

        assert result == {"answer": "test response"}
        assert mock_agent.call_count == 1

        # Check audit log
        audit_log = agent.audit_log
        assert len(audit_log) == 1

        entry = audit_log[0]
        assert entry.agent_id == "agent-001"
        assert entry.posture == TrustPosture.SUPERVISED
        assert entry.action == "run"
        assert entry.kwargs == {"query": "supervised query"}
        assert entry.result == {"answer": "test response"}
        assert entry.error is None
        assert entry.duration_ms is not None
        assert entry.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_supervised_audit_on_error(
        self, posture_machine: PostureStateMachine
    ):
        """Test that SUPERVISED posture logs errors in audit."""
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        # Create agent that raises an error
        failing_agent = MockBaseAgent()
        failing_agent.run = MagicMock(side_effect=RuntimeError("Test error"))

        agent = PostureAwareAgent(
            base_agent=failing_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
        )

        with pytest.raises(RuntimeError):
            await agent.run(query="will fail")

        # Check audit log has error
        audit_log = agent.audit_log
        assert len(audit_log) == 1
        assert audit_log[0].error == "Test error"


class TestAssistedExecution:
    """Test ASSISTED posture behavior."""

    @pytest.mark.asyncio
    async def test_assisted_with_delay(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test ASSISTED mode waits for delay then executes."""
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)
        notification_handler = MockNotificationHandler()

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            notification_handler=notification_handler,
            assisted_delay_seconds=0.01,  # Short delay for testing
        )

        result = await agent.run(query="assisted query")

        assert result == {"answer": "test response"}
        assert mock_agent.call_count == 1

        # Check notification was sent
        assert len(notification_handler.notifications) == 1
        assert notification_handler.notifications[0]["agent_id"] == "agent-001"

        # Check audit log (ASSISTED also audits)
        assert len(agent.audit_log) == 1

    @pytest.mark.asyncio
    async def test_assisted_cancel_during_delay(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test that ASSISTED mode can be cancelled during delay."""
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            assisted_delay_seconds=10.0,  # Long delay
        )

        async def cancel_after_short_delay():
            await asyncio.sleep(0.01)
            agent.cancel_pending()

        # Start both the run and the cancel task
        cancel_task = asyncio.create_task(cancel_after_short_delay())

        with pytest.raises(PermissionError) as exc_info:
            await agent.run(query="will be cancelled")

        await cancel_task

        assert "cancelled" in str(exc_info.value)
        assert mock_agent.call_count == 0

    @pytest.mark.asyncio
    async def test_assisted_without_notification_handler(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test ASSISTED mode works without notification handler."""
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            notification_handler=None,  # No handler
            assisted_delay_seconds=0.01,
        )

        result = await agent.run(query="no notification")

        assert result == {"answer": "test response"}
        assert mock_agent.call_count == 1


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test that open circuit breaker blocks execution."""
        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)
        circuit_breaker = MockCircuitBreaker(is_open_val=True)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            circuit_breaker=circuit_breaker,
        )

        with pytest.raises(PermissionError) as exc_info:
            await agent.run(query="blocked by breaker")

        assert "Circuit breaker is open" in str(exc_info.value)
        assert mock_agent.call_count == 0

    @pytest.mark.asyncio
    async def test_success_recorded_to_breaker(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test that successful execution is recorded to circuit breaker."""
        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)
        circuit_breaker = MockCircuitBreaker(is_open_val=False)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            circuit_breaker=circuit_breaker,
        )

        await agent.run(query="successful")

        assert circuit_breaker.success_count == 1
        assert circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_failure_recorded_to_breaker(
        self, posture_machine: PostureStateMachine
    ):
        """Test that failed execution is recorded to circuit breaker."""
        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)
        circuit_breaker = MockCircuitBreaker(is_open_val=False)

        # Create failing agent
        failing_agent = MockBaseAgent()
        failing_agent.run = MagicMock(side_effect=RuntimeError("Test failure"))

        agent = PostureAwareAgent(
            base_agent=failing_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            circuit_breaker=circuit_breaker,
        )

        with pytest.raises(RuntimeError):
            await agent.run(query="will fail")

        assert circuit_breaker.success_count == 0
        assert circuit_breaker.failure_count == 1


class TestPostureProperty:
    """Test posture property and related attributes."""

    def test_posture_property(self, posture_machine: PostureStateMachine):
        """Test that posture property returns current posture."""
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        agent = PostureAwareAgent(
            base_agent=MockBaseAgent(),
            agent_id="agent-001",
            posture_machine=posture_machine,
        )

        assert agent.posture == TrustPosture.SUPERVISED

        # Change posture and verify
        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)
        assert agent.posture == TrustPosture.AUTONOMOUS

    def test_agent_id_property(self, posture_machine: PostureStateMachine):
        """Test that agent_id property returns correct ID."""
        agent = PostureAwareAgent(
            base_agent=MockBaseAgent(),
            agent_id="my-agent-123",
            posture_machine=posture_machine,
        )

        assert agent.agent_id == "my-agent-123"


class TestCancelPending:
    """Test cancel_pending method."""

    @pytest.mark.asyncio
    async def test_cancel_pending_returns_true_when_pending(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test cancel_pending returns True when there's a pending execution."""
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
            assisted_delay_seconds=10.0,
        )

        async def run_and_cancel():
            # Start execution in background
            run_task = asyncio.create_task(agent.run(query="test"))

            # Wait a tiny bit for the delay to start
            await asyncio.sleep(0.01)

            # Cancel should return True
            result = agent.cancel_pending()

            # Clean up the task
            try:
                await run_task
            except PermissionError:
                pass  # Expected

            return result

        cancelled = await run_and_cancel()
        assert cancelled is True

    def test_cancel_pending_returns_false_when_no_pending(
        self, posture_machine: PostureStateMachine, mock_agent: MockBaseAgent
    ):
        """Test cancel_pending returns False when nothing is pending."""
        agent = PostureAwareAgent(
            base_agent=mock_agent,
            agent_id="agent-001",
            posture_machine=posture_machine,
        )

        result = agent.cancel_pending()
        assert result is False
