"""
Unit Tests for PostureCircuitBreaker (Tier 1)

Tests the circuit breaker for automatic posture downgrade on agent failures.
Part of CARE-028: PostureCircuitBreaker implementation.

Coverage:
- CircuitState enum
- FailureEvent dataclass
- CircuitBreakerConfig dataclass
- PostureCircuitBreaker class
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.trust.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    FailureEvent,
    PostureCircuitBreaker,
)
from kaizen.trust.postures import (
    PostureStateMachine,
    PostureTransitionRequest,
    TrustPosture,
)


class TestCircuitState:
    """Test CircuitState enum."""

    def test_circuit_state_values(self):
        """Test all circuit state values exist."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.HALF_OPEN.value == "half_open"
        assert CircuitState.OPEN.value == "open"

    def test_circuit_state_count(self):
        """Test that we have exactly 3 states."""
        assert len(CircuitState) == 3

    def test_circuit_state_is_string_enum(self):
        """Test that CircuitState inherits from str."""
        assert isinstance(CircuitState.CLOSED, str)
        assert CircuitState.CLOSED == "closed"


class TestFailureEvent:
    """Test FailureEvent dataclass."""

    def test_failure_event_creation(self):
        """Test creating a failure event."""
        now = datetime.now(timezone.utc)
        event = FailureEvent(
            timestamp=now,
            error_type="ConnectionError",
            error_message="Failed to connect",
            action="api_call",
            severity="medium",
        )

        assert event.timestamp == now
        assert event.error_type == "ConnectionError"
        assert event.error_message == "Failed to connect"
        assert event.action == "api_call"
        assert event.severity == "medium"

    def test_failure_event_default_severity(self):
        """Test default severity is medium."""
        event = FailureEvent(
            timestamp=datetime.now(timezone.utc),
            error_type="Error",
            error_message="Error",
            action="action",
        )
        assert event.severity == "medium"

    def test_failure_event_all_severities(self):
        """Test all valid severity levels."""
        for severity in ["low", "medium", "high", "critical"]:
            event = FailureEvent(
                timestamp=datetime.now(timezone.utc),
                error_type="Error",
                error_message="Error",
                action="action",
                severity=severity,
            )
            assert event.severity == severity

    def test_failure_event_invalid_severity(self):
        """Test that invalid severity raises error."""
        with pytest.raises(ValueError, match="Invalid severity"):
            FailureEvent(
                timestamp=datetime.now(timezone.utc),
                error_type="Error",
                error_message="Error",
                action="action",
                severity="invalid",
            )


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass."""

    def test_config_default_values(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60
        assert config.half_open_max_calls == 3
        assert config.failure_window_seconds == 300
        assert config.severity_weights == {
            "low": 0.5,
            "medium": 1.0,
            "high": 2.0,
            "critical": 5.0,
        }
        assert config.downgrade_on_open == "human_decides"

    def test_config_custom_values(self):
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            recovery_timeout=120,
            half_open_max_calls=5,
            failure_window_seconds=600,
            severity_weights={"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0},
            downgrade_on_open="blocked",
        )

        assert config.failure_threshold == 10
        assert config.recovery_timeout == 120
        assert config.half_open_max_calls == 5
        assert config.failure_window_seconds == 600
        assert config.downgrade_on_open == "blocked"

    def test_config_invalid_threshold(self):
        """Test that invalid threshold raises error."""
        with pytest.raises(ValueError, match="failure_threshold must be at least 1"):
            CircuitBreakerConfig(failure_threshold=0)

    def test_config_invalid_recovery_timeout(self):
        """Test that negative recovery timeout raises error."""
        with pytest.raises(ValueError, match="recovery_timeout must be non-negative"):
            CircuitBreakerConfig(recovery_timeout=-1)

    def test_config_invalid_half_open_max_calls(self):
        """Test that invalid half_open_max_calls raises error."""
        with pytest.raises(ValueError, match="half_open_max_calls must be at least 1"):
            CircuitBreakerConfig(half_open_max_calls=0)

    def test_config_invalid_failure_window(self):
        """Test that invalid failure window raises error."""
        with pytest.raises(
            ValueError, match="failure_window_seconds must be at least 1"
        ):
            CircuitBreakerConfig(failure_window_seconds=0)

    def test_config_invalid_downgrade_posture(self):
        """Test that invalid downgrade posture raises error."""
        with pytest.raises(ValueError, match="Invalid downgrade_on_open"):
            CircuitBreakerConfig(downgrade_on_open="invalid_posture")


class TestPostureCircuitBreaker:
    """Test PostureCircuitBreaker class."""

    @pytest.fixture
    def posture_machine(self):
        """Create a PostureStateMachine for testing."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        return machine

    @pytest.fixture
    def circuit_breaker(self, posture_machine):
        """Create a PostureCircuitBreaker with default config."""
        return PostureCircuitBreaker(posture_machine)

    @pytest.mark.asyncio
    async def test_initial_state_closed(self, circuit_breaker):
        """Test that initial circuit state is CLOSED."""
        state = circuit_breaker.get_state("agent-001")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_opens_on_threshold(self, posture_machine):
        """Test circuit opens when weighted failure count exceeds threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Record 3 medium failures (weight=1.0 each)
        for i in range(3):
            await breaker.record_failure(
                "agent-001",
                "Error",
                f"Error {i}",
                "action",
                severity="medium",
            )

        assert breaker.get_state("agent-001") == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_weighted_failures(self, posture_machine):
        """Test that critical failures with weight 5.0 open circuit with 1 failure."""
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Record 1 critical failure (weight=5.0)
        await breaker.record_failure(
            "agent-001",
            "CriticalError",
            "Critical failure",
            "action",
            severity="critical",
        )

        assert breaker.get_state("agent-001") == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_can_proceed_closed(self, circuit_breaker):
        """Test can_proceed returns True when circuit is CLOSED."""
        can_proceed = await circuit_breaker.can_proceed("agent-001")
        assert can_proceed is True

    @pytest.mark.asyncio
    async def test_can_proceed_open(self, posture_machine):
        """Test can_proceed returns False when circuit is OPEN."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60)
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open the circuit
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        can_proceed = await breaker.can_proceed("agent-001")
        assert can_proceed is False

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, posture_machine):
        """Test circuit transitions to HALF_OPEN after recovery timeout."""
        # Use very small timeout for testing
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0)
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open the circuit
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )
        assert breaker.get_state("agent-001") == CircuitState.OPEN

        # Call can_proceed - should transition to HALF_OPEN immediately
        can_proceed = await breaker.can_proceed("agent-001")
        assert can_proceed is True
        assert breaker.get_state("agent-001") == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self, posture_machine):
        """Test that successful calls in HALF_OPEN close the circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0, half_open_max_calls=2
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open then transition to half-open
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )
        await breaker.can_proceed("agent-001")  # Transitions to HALF_OPEN

        # Record successes
        await breaker.record_success("agent-001")
        await breaker.record_success("agent-001")

        assert breaker.get_state("agent-001") == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self, posture_machine):
        """Test that failure in HALF_OPEN reopens the circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0, half_open_max_calls=3
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open then transition to half-open
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )
        await breaker.can_proceed("agent-001")  # Transitions to HALF_OPEN
        assert breaker.get_state("agent-001") == CircuitState.HALF_OPEN

        # Record failure in half-open state
        await breaker.record_failure(
            "agent-001", "Error", "Another error", "action", severity="medium"
        )

        assert breaker.get_state("agent-001") == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_failure_window_cleanup(self, posture_machine):
        """Test that old failures outside the window are removed."""
        config = CircuitBreakerConfig(
            failure_threshold=5,
            failure_window_seconds=60,  # High threshold
        )
        breaker = PostureCircuitBreaker(posture_machine, config)

        # Manually add an old failure
        old_failure = FailureEvent(
            timestamp=datetime.now(timezone.utc)
            - timedelta(seconds=120),  # 2 minutes ago
            error_type="OldError",
            error_message="Old error",
            action="action",
            severity="medium",
        )
        breaker._failures["agent-001"] = [old_failure]

        # Record a new failure (this triggers cleanup)
        await breaker.record_failure(
            "agent-001", "NewError", "New error", "action", severity="medium"
        )

        # Old failure should be cleaned up
        failures = breaker._failures.get("agent-001", [])
        assert len(failures) == 1
        assert failures[0].error_type == "NewError"

    @pytest.mark.asyncio
    async def test_get_metrics(self, posture_machine):
        """Test get_metrics returns correct information."""
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        # Record some failures
        await breaker.record_failure(
            "agent-001", "Error1", "Error 1", "action", severity="low"
        )
        await breaker.record_failure(
            "agent-001", "Error2", "Error 2", "action", severity="high"
        )

        metrics = breaker.get_metrics("agent-001")

        assert metrics["agent_id"] == "agent-001"
        assert metrics["state"] == "closed"
        assert metrics["failure_count"] == 2
        assert metrics["weighted_failures"] == 2.5  # 0.5 + 2.0
        assert metrics["failure_threshold"] == 5
        assert metrics["current_posture"] == "supervised"
        assert metrics["failures_by_severity"] == {"low": 1, "high": 1}

    @pytest.mark.asyncio
    async def test_posture_downgrade_on_open(self, posture_machine):
        """Test that PostureStateMachine.transition is called on circuit open."""
        config = CircuitBreakerConfig(
            failure_threshold=1, downgrade_on_open="human_decides"
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open the circuit
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        # Verify posture was downgraded
        assert posture_machine.get_posture("agent-001") == TrustPosture.HUMAN_DECIDES

    @pytest.mark.asyncio
    async def test_severity_weights(self, posture_machine):
        """Test severity weights are applied correctly."""
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = PostureCircuitBreaker(posture_machine, config)

        # Record failures with different severities
        await breaker.record_failure(
            "agent-001", "LowError", "Low", "action", severity="low"
        )
        await breaker.record_failure(
            "agent-001", "HighError", "High", "action", severity="high"
        )

        # low (0.5) + high (2.0) = 2.5, below threshold of 5
        assert breaker.get_state("agent-001") == CircuitState.CLOSED

        # Add another high severity (2.0) -> total 4.5, still below
        await breaker.record_failure(
            "agent-001", "HighError", "High", "action", severity="high"
        )
        assert breaker.get_state("agent-001") == CircuitState.CLOSED

        # Add medium (1.0) -> total 5.5, exceeds threshold
        await breaker.record_failure(
            "agent-001", "MediumError", "Medium", "action", severity="medium"
        )
        assert breaker.get_state("agent-001") == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_multiple_agents_independent(self, posture_machine):
        """Test that circuit states are independent per agent."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)
        posture_machine.set_posture("agent-002", TrustPosture.FULL_AUTONOMY)

        # Open circuit for agent-001 only
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        assert breaker.get_state("agent-001") == CircuitState.OPEN
        assert breaker.get_state("agent-002") == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_original_posture_stored(self, posture_machine):
        """Test that original posture is stored when circuit opens."""
        config = CircuitBreakerConfig(
            failure_threshold=1, downgrade_on_open="human_decides"
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open the circuit
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        metrics = breaker.get_metrics("agent-001")
        assert metrics["original_posture"] == "full_autonomy"
        assert metrics["current_posture"] == "human_decides"

    @pytest.mark.asyncio
    async def test_posture_not_downgraded_if_already_lower(self, posture_machine):
        """Test that posture is not downgraded if already at or below target."""
        config = CircuitBreakerConfig(
            failure_threshold=1, downgrade_on_open="human_decides"
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.BLOCKED)

        # Open the circuit - should not change posture
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        assert posture_machine.get_posture("agent-001") == TrustPosture.BLOCKED

    @pytest.mark.asyncio
    async def test_half_open_limited_calls(self, posture_machine):
        """Test that half-open state limits the number of calls."""
        config = CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0, half_open_max_calls=2
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open then transition to half-open
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        # First call transitions to half-open and allows
        result1 = await breaker.can_proceed("agent-001")
        assert result1 is True

        # Second call allowed (within limit)
        result2 = await breaker.can_proceed("agent-001")
        assert result2 is True

        # Third call blocked (exceeds limit)
        result3 = await breaker.can_proceed("agent-001")
        assert result3 is False

    @pytest.mark.asyncio
    async def test_circuit_close_clears_failures(self, posture_machine):
        """Test that closing the circuit clears the failure list."""
        config = CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0, half_open_max_calls=1
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open the circuit
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        # Transition to half-open and close with success
        await breaker.can_proceed("agent-001")
        await breaker.record_success("agent-001")

        # Failures should be cleared
        assert breaker._failures.get("agent-001", []) == []

    @pytest.mark.asyncio
    async def test_success_in_closed_state_noop(self, circuit_breaker):
        """Test that recording success in CLOSED state is a no-op."""
        await circuit_breaker.record_success("agent-001")

        # Should still be closed, no errors
        assert circuit_breaker.get_state("agent-001") == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_metrics_in_open_state(self, posture_machine):
        """Test metrics include time information in OPEN state."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60)
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open the circuit
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )

        metrics = breaker.get_metrics("agent-001")
        assert "time_in_open_state" in metrics
        assert "time_until_half_open" in metrics
        assert metrics["time_in_open_state"] >= 0
        assert metrics["time_until_half_open"] <= 60

    @pytest.mark.asyncio
    async def test_metrics_in_half_open_state(self, posture_machine):
        """Test metrics include call count in HALF_OPEN state."""
        config = CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0, half_open_max_calls=3
        )
        breaker = PostureCircuitBreaker(posture_machine, config)
        posture_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

        # Open and transition to half-open
        await breaker.record_failure(
            "agent-001", "Error", "Error", "action", severity="medium"
        )
        await breaker.can_proceed("agent-001")

        metrics = breaker.get_metrics("agent-001")
        assert metrics["state"] == "half_open"
        assert "half_open_calls" in metrics
        assert "half_open_successes" in metrics
        assert "half_open_max_calls" in metrics
