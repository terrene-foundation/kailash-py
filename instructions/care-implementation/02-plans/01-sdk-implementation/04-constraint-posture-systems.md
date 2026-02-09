# Constraint and Posture System Implementation Plan

## Overview

This document details the implementation of the 5-posture state machine and extensible constraint system for the CARE/EATP framework. These systems enable fine-grained agent autonomy control and custom constraint dimensions.

**Target Modules**:

- Posture System: `apps/kailash-kaizen/src/kaizen/trust/postures.py`
- Constraint System: `apps/kailash-kaizen/src/kaizen/trust/constraints/`
- Circuit Breaker: `apps/kailash-kaizen/src/kaizen/trust/circuit_breaker.py`

---

## Part 1: 5-Posture State Machine

### 1.1 Current State Analysis

The current `postures.py` implements a 4-posture model:

- FULL_AUTONOMY
- SUPERVISED
- HUMAN_DECIDES
- BLOCKED

**Gap**: The Enterprise-App specification defines 5 postures. Missing: **ASSISTED** posture.

### 1.2 Updated Posture Enum

**File**: `apps/kailash-kaizen/src/kaizen/trust/postures.py` (MODIFY)

```python
"""
Trust posture state machine for Enterprise-App integration.

Implements the 5-posture model with formal state transitions,
transition guards, and automatic downgrade on failures.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING
from datetime import datetime, timezone
import logging

if TYPE_CHECKING:
    from kaizen.trust.chain import VerificationResult

logger = logging.getLogger(__name__)


class TrustPosture(str, Enum):
    """
    Trust posture levels for Enterprise-App.

    The 5-posture model (ordered from most to least autonomous):

    1. FULL_AUTONOMY: Agent acts freely without approval
       - No human intervention required
       - Full capability access
       - Used for highly trusted, low-risk operations

    2. ASSISTED: Agent proposes, human can override
       - Agent takes action after brief delay
       - Human can cancel during delay window
       - Notifications sent to human

    3. SUPERVISED: Agent actions are logged, human monitors
       - All actions logged for review
       - Human reviews periodically
       - Agent proceeds without waiting

    4. HUMAN_DECIDES: Each action requires human approval
       - Agent proposes action
       - Waits for explicit human approval
       - Blocked until approval received

    5. BLOCKED: Action is denied
       - Agent cannot perform action
       - Requires capability upgrade or delegation
    """

    FULL_AUTONOMY = "full_autonomy"
    ASSISTED = "assisted"
    SUPERVISED = "supervised"
    HUMAN_DECIDES = "human_decides"
    BLOCKED = "blocked"

    @property
    def autonomy_level(self) -> int:
        """Get numeric autonomy level (higher = more autonomy)."""
        levels = {
            self.FULL_AUTONOMY: 5,
            self.ASSISTED: 4,
            self.SUPERVISED: 3,
            self.HUMAN_DECIDES: 2,
            self.BLOCKED: 1,
        }
        return levels[self]

    def can_upgrade_to(self, other: "TrustPosture") -> bool:
        """Check if upgrade to other posture is possible."""
        return other.autonomy_level > self.autonomy_level

    def can_downgrade_to(self, other: "TrustPosture") -> bool:
        """Check if downgrade to other posture is possible."""
        return other.autonomy_level < self.autonomy_level


class PostureTransition(str, Enum):
    """Types of posture transitions."""
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    MAINTAIN = "maintain"
    EMERGENCY_DOWNGRADE = "emergency_downgrade"


@dataclass
class TransitionGuard:
    """
    Guard condition for posture transition.

    Guards prevent invalid transitions and enforce policies.

    Attributes:
        name: Guard identifier
        condition: Callable that returns True if transition allowed
        error_message: Message to show if guard fails
        required_approvals: Number of approvals needed
    """
    name: str
    condition: Callable[["PostureTransitionRequest"], bool]
    error_message: str
    required_approvals: int = 0


@dataclass
class PostureTransitionRequest:
    """
    Request to transition between postures.

    Attributes:
        agent_id: Agent requesting transition
        current_posture: Current posture
        target_posture: Desired posture
        reason: Reason for transition
        approvals: List of approver IDs
        context: Additional context
        timestamp: Request timestamp
    """
    agent_id: str
    current_posture: TrustPosture
    target_posture: TrustPosture
    reason: str = ""
    approvals: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_upgrade(self) -> bool:
        return self.current_posture.can_upgrade_to(self.target_posture)

    @property
    def is_downgrade(self) -> bool:
        return self.current_posture.can_downgrade_to(self.target_posture)


@dataclass
class TransitionResult:
    """Result of a posture transition attempt."""
    success: bool
    new_posture: TrustPosture
    reason: str
    failed_guards: List[str] = field(default_factory=list)
    audit_id: Optional[str] = None


class PostureStateMachine:
    """
    Formal state machine for trust posture transitions.

    Manages posture state for agents with:
    - Transition guards (policy enforcement)
    - Upgrade approval requirements
    - Automatic downgrade on failures
    - Audit trail of all transitions

    State Diagram:
        BLOCKED <-> HUMAN_DECIDES <-> SUPERVISED <-> ASSISTED <-> FULL_AUTONOMY

    Transition Rules:
    - Downgrades: Always allowed (may be automatic)
    - Upgrades: Require approval based on target level
    - Emergency: Immediate downgrade to BLOCKED

    Example:
        >>> machine = PostureStateMachine()
        >>>
        >>> # Check current posture
        >>> posture = machine.get_posture("agent-123")
        >>>
        >>> # Request upgrade
        >>> request = PostureTransitionRequest(
        ...     agent_id="agent-123",
        ...     current_posture=TrustPosture.SUPERVISED,
        ...     target_posture=TrustPosture.ASSISTED,
        ...     reason="Task requires timely execution",
        ...     approvals=["manager@corp.com"],
        ... )
        >>> result = await machine.transition(request)
        >>>
        >>> # Emergency downgrade
        >>> await machine.emergency_downgrade("agent-123", "Security incident")
    """

    # Default guards for posture transitions
    DEFAULT_GUARDS = [
        TransitionGuard(
            name="upgrade_requires_approval",
            condition=lambda r: not r.is_upgrade or len(r.approvals) > 0,
            error_message="Upgrades require at least one approval",
        ),
        TransitionGuard(
            name="full_autonomy_requires_manager",
            condition=lambda r: (
                r.target_posture != TrustPosture.FULL_AUTONOMY
                or "manager" in str(r.approvals)
            ),
            error_message="FULL_AUTONOMY requires manager approval",
            required_approvals=2,
        ),
        TransitionGuard(
            name="no_upgrade_during_incident",
            condition=lambda r: r.context.get("incident_active") != True or not r.is_upgrade,
            error_message="Cannot upgrade during active incident",
        ),
    ]

    def __init__(
        self,
        guards: Optional[List[TransitionGuard]] = None,
        audit_logger=None,
    ):
        self._guards = guards or self.DEFAULT_GUARDS
        self._audit = audit_logger
        self._agent_postures: Dict[str, TrustPosture] = {}
        self._transition_history: Dict[str, List[TransitionResult]] = {}

    def get_posture(self, agent_id: str) -> TrustPosture:
        """
        Get current posture for agent.

        Returns BLOCKED for unknown agents (fail-safe default).
        """
        return self._agent_postures.get(agent_id, TrustPosture.BLOCKED)

    def set_initial_posture(
        self,
        agent_id: str,
        posture: TrustPosture,
    ) -> None:
        """Set initial posture for agent (no guards applied)."""
        self._agent_postures[agent_id] = posture
        if agent_id not in self._transition_history:
            self._transition_history[agent_id] = []

    async def transition(
        self,
        request: PostureTransitionRequest,
    ) -> TransitionResult:
        """
        Attempt to transition to a new posture.

        Args:
            request: Transition request with target and approvals

        Returns:
            TransitionResult indicating success/failure
        """
        # Check if same posture
        if request.current_posture == request.target_posture:
            return TransitionResult(
                success=True,
                new_posture=request.target_posture,
                reason="Already at target posture",
            )

        # Run guards
        failed_guards = []
        for guard in self._guards:
            try:
                if not guard.condition(request):
                    failed_guards.append(guard.name)
                    logger.warning(
                        f"Guard '{guard.name}' failed for {request.agent_id}: "
                        f"{guard.error_message}"
                    )
            except Exception as e:
                logger.error(f"Guard '{guard.name}' raised exception: {e}")
                failed_guards.append(guard.name)

        if failed_guards:
            result = TransitionResult(
                success=False,
                new_posture=request.current_posture,
                reason=f"Guards failed: {', '.join(failed_guards)}",
                failed_guards=failed_guards,
            )
        else:
            # Transition successful
            self._agent_postures[request.agent_id] = request.target_posture
            result = TransitionResult(
                success=True,
                new_posture=request.target_posture,
                reason=request.reason,
            )

        # Record history
        if request.agent_id not in self._transition_history:
            self._transition_history[request.agent_id] = []
        self._transition_history[request.agent_id].append(result)

        # Audit
        if self._audit:
            result.audit_id = await self._audit.log_transition(
                request, result
            )

        return result

    async def emergency_downgrade(
        self,
        agent_id: str,
        reason: str,
    ) -> TransitionResult:
        """
        Emergency downgrade to BLOCKED.

        Bypasses normal guards for immediate safety.

        Args:
            agent_id: Agent to downgrade
            reason: Reason for emergency action

        Returns:
            TransitionResult (always succeeds)
        """
        current = self.get_posture(agent_id)
        self._agent_postures[agent_id] = TrustPosture.BLOCKED

        result = TransitionResult(
            success=True,
            new_posture=TrustPosture.BLOCKED,
            reason=f"EMERGENCY: {reason}",
        )

        if agent_id not in self._transition_history:
            self._transition_history[agent_id] = []
        self._transition_history[agent_id].append(result)

        logger.warning(
            f"Emergency downgrade: {agent_id} from {current} to BLOCKED. "
            f"Reason: {reason}"
        )

        return result

    def get_transition_history(
        self,
        agent_id: str,
    ) -> List[TransitionResult]:
        """Get transition history for agent."""
        return self._transition_history.get(agent_id, [])

    def add_guard(self, guard: TransitionGuard) -> None:
        """Add a transition guard."""
        self._guards.append(guard)

    def remove_guard(self, name: str) -> bool:
        """Remove a guard by name."""
        original_len = len(self._guards)
        self._guards = [g for g in self._guards if g.name != name]
        return len(self._guards) < original_len
```

### 1.3 Posture Circuit Breaker

**File**: `apps/kailash-kaizen/src/kaizen/trust/circuit_breaker.py` (NEW)

```python
"""
Circuit breaker for automatic posture downgrade on failures.

Implements the circuit breaker pattern for agent postures,
automatically downgrading agents that exhibit problematic behavior.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    HALF_OPEN = "half_open"  # Testing recovery
    OPEN = "open"  # Failures blocked, posture downgraded


@dataclass
class FailureEvent:
    """Record of a failure event."""
    timestamp: datetime
    error_type: str
    error_message: str
    action: str
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for posture circuit breaker.

    Attributes:
        failure_threshold: Failures before opening circuit
        recovery_timeout: Seconds before testing recovery
        half_open_max_calls: Calls allowed in half-open state
        failure_window_seconds: Window for counting failures
        severity_weights: Weight multipliers for severity levels
        downgrade_on_open: Posture to downgrade to when circuit opens
    """
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3
    failure_window_seconds: int = 300  # 5 minutes
    severity_weights: Dict[str, float] = field(default_factory=lambda: {
        "low": 0.5,
        "medium": 1.0,
        "high": 2.0,
        "critical": 5.0,
    })
    downgrade_on_open: str = "human_decides"


class PostureCircuitBreaker:
    """
    Circuit breaker for automatic posture downgrade.

    Monitors agent failures and automatically downgrades posture
    when failure threshold is exceeded.

    Circuit States:
    - CLOSED: Normal operation, counting failures
    - OPEN: Too many failures, posture downgraded
    - HALF_OPEN: Testing if agent has recovered

    Example:
        >>> breaker = PostureCircuitBreaker(
        ...     posture_machine=posture_machine,
        ...     config=CircuitBreakerConfig(failure_threshold=3),
        ... )
        >>>
        >>> # Record failures
        >>> await breaker.record_failure(
        ...     agent_id="agent-123",
        ...     error_type="RateLimitExceeded",
        ...     error_message="API rate limit hit",
        ...     action="fetch_data",
        ...     severity="medium",
        ... )
        >>>
        >>> # Check if action allowed
        >>> if await breaker.can_proceed("agent-123"):
        ...     result = await agent.execute(action)
        ...     if result.success:
        ...         await breaker.record_success("agent-123")
    """

    def __init__(
        self,
        posture_machine: "PostureStateMachine",
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self._machine = posture_machine
        self._config = config or CircuitBreakerConfig()

        # Track state per agent
        self._states: Dict[str, CircuitState] = {}
        self._failures: Dict[str, List[FailureEvent]] = {}
        self._last_failure: Dict[str, datetime] = {}
        self._half_open_calls: Dict[str, int] = {}
        self._original_postures: Dict[str, TrustPosture] = {}

    def get_state(self, agent_id: str) -> CircuitState:
        """Get current circuit state for agent."""
        return self._states.get(agent_id, CircuitState.CLOSED)

    async def record_failure(
        self,
        agent_id: str,
        error_type: str,
        error_message: str,
        action: str,
        severity: str = "medium",
    ) -> None:
        """
        Record a failure event for an agent.

        May trigger circuit opening and posture downgrade.

        Args:
            agent_id: Agent that failed
            error_type: Type of error
            error_message: Error details
            action: Action that failed
            severity: Failure severity (low, medium, high, critical)
        """
        failure = FailureEvent(
            timestamp=datetime.now(timezone.utc),
            error_type=error_type,
            error_message=error_message,
            action=action,
            severity=severity,
        )

        # Initialize tracking
        if agent_id not in self._failures:
            self._failures[agent_id] = []

        self._failures[agent_id].append(failure)
        self._last_failure[agent_id] = failure.timestamp

        # Clean old failures
        self._clean_old_failures(agent_id)

        # Calculate weighted failure count
        weighted_count = self._calculate_weighted_failures(agent_id)

        state = self.get_state(agent_id)

        if state == CircuitState.HALF_OPEN:
            # Any failure in half-open reopens circuit
            await self._open_circuit(agent_id, f"Failure during recovery: {error_type}")

        elif state == CircuitState.CLOSED:
            if weighted_count >= self._config.failure_threshold:
                await self._open_circuit(
                    agent_id,
                    f"Threshold exceeded ({weighted_count:.1f} >= {self._config.failure_threshold})"
                )

        logger.warning(
            f"Failure recorded for {agent_id}: {error_type} (severity={severity}). "
            f"Weighted count: {weighted_count:.1f}, State: {self.get_state(agent_id)}"
        )

    async def record_success(self, agent_id: str) -> None:
        """
        Record a successful operation.

        May trigger circuit closing in half-open state.

        Args:
            agent_id: Agent that succeeded
        """
        state = self.get_state(agent_id)

        if state == CircuitState.HALF_OPEN:
            self._half_open_calls[agent_id] = self._half_open_calls.get(agent_id, 0) + 1

            if self._half_open_calls[agent_id] >= self._config.half_open_max_calls:
                await self._close_circuit(agent_id)

    async def can_proceed(self, agent_id: str) -> bool:
        """
        Check if agent can proceed with an action.

        Handles state transitions between OPEN and HALF_OPEN.

        Args:
            agent_id: Agent to check

        Returns:
            True if agent can proceed, False if blocked
        """
        state = self.get_state(agent_id)

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.OPEN:
            # Check if recovery timeout elapsed
            last = self._last_failure.get(agent_id)
            if last:
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed >= self._config.recovery_timeout:
                    await self._transition_to_half_open(agent_id)
                    return True
            return False

        if state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open
            calls = self._half_open_calls.get(agent_id, 0)
            return calls < self._config.half_open_max_calls

        return False

    async def _open_circuit(self, agent_id: str, reason: str) -> None:
        """Open circuit and downgrade posture."""
        from kaizen.trust.postures import TrustPosture

        self._states[agent_id] = CircuitState.OPEN

        # Store original posture for recovery
        if agent_id not in self._original_postures:
            self._original_postures[agent_id] = self._machine.get_posture(agent_id)

        # Downgrade posture
        target_posture = TrustPosture(self._config.downgrade_on_open)
        current_posture = self._machine.get_posture(agent_id)

        if current_posture.autonomy_level > target_posture.autonomy_level:
            from kaizen.trust.postures import PostureTransitionRequest

            request = PostureTransitionRequest(
                agent_id=agent_id,
                current_posture=current_posture,
                target_posture=target_posture,
                reason=f"Circuit breaker opened: {reason}",
            )
            await self._machine.transition(request)

        logger.warning(
            f"Circuit OPENED for {agent_id}. Posture downgraded to {target_posture}. "
            f"Reason: {reason}"
        )

    async def _transition_to_half_open(self, agent_id: str) -> None:
        """Transition to half-open state for testing."""
        self._states[agent_id] = CircuitState.HALF_OPEN
        self._half_open_calls[agent_id] = 0

        logger.info(f"Circuit HALF_OPEN for {agent_id}. Testing recovery...")

    async def _close_circuit(self, agent_id: str) -> None:
        """Close circuit and potentially restore posture."""
        from kaizen.trust.postures import TrustPosture, PostureTransitionRequest

        self._states[agent_id] = CircuitState.CLOSED
        self._failures[agent_id] = []
        self._half_open_calls.pop(agent_id, None)

        # Consider restoring original posture
        original = self._original_postures.get(agent_id)
        if original:
            current = self._machine.get_posture(agent_id)
            if current.autonomy_level < original.autonomy_level:
                # Note: This still requires approval via normal transition
                logger.info(
                    f"Circuit CLOSED for {agent_id}. Consider restoring posture "
                    f"from {current} to {original}."
                )

            del self._original_postures[agent_id]

        logger.info(f"Circuit CLOSED for {agent_id}. Agent recovered.")

    def _clean_old_failures(self, agent_id: str) -> None:
        """Remove failures outside the window."""
        if agent_id not in self._failures:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=self._config.failure_window_seconds
        )
        self._failures[agent_id] = [
            f for f in self._failures[agent_id] if f.timestamp > cutoff
        ]

    def _calculate_weighted_failures(self, agent_id: str) -> float:
        """Calculate weighted failure count."""
        if agent_id not in self._failures:
            return 0.0

        total = 0.0
        for failure in self._failures[agent_id]:
            weight = self._config.severity_weights.get(failure.severity, 1.0)
            total += weight

        return total

    def get_metrics(self, agent_id: str) -> Dict[str, Any]:
        """Get circuit breaker metrics for agent."""
        return {
            "state": self.get_state(agent_id).value,
            "failure_count": len(self._failures.get(agent_id, [])),
            "weighted_failures": self._calculate_weighted_failures(agent_id),
            "threshold": self._config.failure_threshold,
            "last_failure": (
                self._last_failure[agent_id].isoformat()
                if agent_id in self._last_failure
                else None
            ),
            "half_open_calls": self._half_open_calls.get(agent_id, 0),
        }
```

### 1.4 Posture-Aware Agent Wrapper

**File**: `apps/kailash-kaizen/src/kaizen/trust/posture_agent.py` (NEW)

```python
"""
Posture-aware agent wrapper for Kaizen BaseAgent.

Wraps agent execution with posture-based behavior control.
"""

from __future__ import annotations
from typing import Any, Dict, Optional, TYPE_CHECKING
import asyncio
import logging

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent
    from kaizen.trust.postures import TrustPosture, PostureStateMachine
    from kaizen.trust.circuit_breaker import PostureCircuitBreaker

logger = logging.getLogger(__name__)


class PostureAwareAgent:
    """
    Wrapper that adds posture-based behavior to any Kaizen agent.

    Enforces posture constraints:
    - FULL_AUTONOMY: Execute immediately
    - ASSISTED: Execute with notification + cancel window
    - SUPERVISED: Execute with audit logging
    - HUMAN_DECIDES: Wait for approval before execution
    - BLOCKED: Reject execution

    Example:
        >>> from kaizen.agents import QAAgent
        >>> from kaizen.trust.postures import PostureStateMachine
        >>>
        >>> base_agent = QAAgent(config=qa_config)
        >>> posture_machine = PostureStateMachine()
        >>> posture_machine.set_initial_posture("agent-123", TrustPosture.SUPERVISED)
        >>>
        >>> agent = PostureAwareAgent(
        ...     base_agent=base_agent,
        ...     agent_id="agent-123",
        ...     posture_machine=posture_machine,
        ... )
        >>>
        >>> # Execution follows posture rules
        >>> result = await agent.run(query="What is IRP?")
    """

    def __init__(
        self,
        base_agent: "BaseAgent",
        agent_id: str,
        posture_machine: "PostureStateMachine",
        circuit_breaker: Optional["PostureCircuitBreaker"] = None,
        approval_handler=None,
        notification_handler=None,
        assisted_delay_seconds: float = 5.0,
    ):
        self._agent = base_agent
        self._agent_id = agent_id
        self._machine = posture_machine
        self._breaker = circuit_breaker
        self._approval_handler = approval_handler
        self._notification_handler = notification_handler
        self._assisted_delay = assisted_delay_seconds

    @property
    def posture(self) -> "TrustPosture":
        """Get current posture."""
        return self._machine.get_posture(self._agent_id)

    async def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute agent with posture-based behavior.

        Args:
            **kwargs: Arguments passed to underlying agent

        Returns:
            Agent execution result

        Raises:
            PermissionError: If posture is BLOCKED
            TimeoutError: If approval not received in time
        """
        from kaizen.trust.postures import TrustPosture

        posture = self.posture

        # Check circuit breaker
        if self._breaker:
            if not await self._breaker.can_proceed(self._agent_id):
                raise PermissionError(
                    f"Circuit breaker open for {self._agent_id}. "
                    "Please wait for recovery."
                )

        # Handle based on posture
        if posture == TrustPosture.BLOCKED:
            raise PermissionError(
                f"Agent {self._agent_id} is BLOCKED. Execution not allowed."
            )

        elif posture == TrustPosture.HUMAN_DECIDES:
            return await self._execute_with_approval(kwargs)

        elif posture == TrustPosture.SUPERVISED:
            return await self._execute_with_audit(kwargs)

        elif posture == TrustPosture.ASSISTED:
            return await self._execute_with_delay(kwargs)

        else:  # FULL_AUTONOMY
            return await self._execute_direct(kwargs)

    async def _execute_direct(self, kwargs: Dict) -> Dict[str, Any]:
        """Execute without restrictions."""
        try:
            result = self._agent.run(**kwargs)
            if self._breaker:
                await self._breaker.record_success(self._agent_id)
            return result
        except Exception as e:
            if self._breaker:
                await self._breaker.record_failure(
                    agent_id=self._agent_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    action="run",
                    severity="medium",
                )
            raise

    async def _execute_with_audit(self, kwargs: Dict) -> Dict[str, Any]:
        """Execute with audit logging."""
        logger.info(f"[AUDIT] Agent {self._agent_id} executing with kwargs: {list(kwargs.keys())}")

        start_time = asyncio.get_event_loop().time()
        result = await self._execute_direct(kwargs)
        duration = asyncio.get_event_loop().time() - start_time

        logger.info(
            f"[AUDIT] Agent {self._agent_id} completed in {duration:.2f}s. "
            f"Result keys: {list(result.keys()) if isinstance(result, dict) else 'non-dict'}"
        )

        return result

    async def _execute_with_delay(self, kwargs: Dict) -> Dict[str, Any]:
        """Execute with notification and delay (cancel window)."""
        if self._notification_handler:
            cancel_event = asyncio.Event()
            await self._notification_handler.notify_pending_action(
                agent_id=self._agent_id,
                action_summary=str(kwargs),
                cancel_callback=lambda: cancel_event.set(),
            )

            # Wait for delay, checking for cancellation
            try:
                await asyncio.wait_for(
                    cancel_event.wait(),
                    timeout=self._assisted_delay,
                )
                # If we get here, action was cancelled
                raise asyncio.CancelledError("Action cancelled by human")
            except asyncio.TimeoutError:
                # Delay elapsed without cancellation, proceed
                pass

        return await self._execute_with_audit(kwargs)

    async def _execute_with_approval(self, kwargs: Dict) -> Dict[str, Any]:
        """Execute only after human approval."""
        if not self._approval_handler:
            raise PermissionError(
                f"HUMAN_DECIDES posture requires approval_handler. "
                f"Agent {self._agent_id} cannot execute."
            )

        # Request approval
        approved = await self._approval_handler.request_approval(
            agent_id=self._agent_id,
            action_summary=str(kwargs),
            timeout_seconds=300,  # 5 minute timeout
        )

        if not approved:
            raise PermissionError(
                f"Human denied action for agent {self._agent_id}"
            )

        return await self._execute_with_audit(kwargs)
```

---

## Part 2: Constraint Extensibility Plugin Architecture

### 2.1 Constraint Dimension Protocol

**File**: `apps/kailash-kaizen/src/kaizen/trust/constraints/__init__.py` (NEW)

```python
"""
Extensible constraint system for EATP.

Provides plugin architecture for custom constraint dimensions.
"""

from kaizen.trust.constraints.dimension import (
    ConstraintDimension,
    ConstraintDimensionRegistry,
)
from kaizen.trust.constraints.evaluator import (
    MultiDimensionEvaluator,
    EvaluationResult,
    InteractionMode,
)
from kaizen.trust.constraints.builtin import (
    CostLimitDimension,
    TimeDimension,
    ResourceDimension,
    RateLimitDimension,
    DataAccessDimension,
    CommunicationDimension,
)

__all__ = [
    "ConstraintDimension",
    "ConstraintDimensionRegistry",
    "MultiDimensionEvaluator",
    "EvaluationResult",
    "InteractionMode",
    "CostLimitDimension",
    "TimeDimension",
    "ResourceDimension",
    "RateLimitDimension",
    "DataAccessDimension",
    "CommunicationDimension",
]
```

**File**: `apps/kailash-kaizen/src/kaizen/trust/constraints/dimension.py` (NEW)

```python
"""
Constraint dimension protocol for extensible constraints.

Defines the interface that all constraint dimensions must implement.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConstraintValue:
    """
    A constraint value within a dimension.

    Attributes:
        dimension: Dimension this value belongs to
        raw_value: The raw constraint value
        parsed: Parsed/normalized value
        metadata: Additional metadata
    """
    dimension: str
    raw_value: Any
    parsed: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstraintCheckResult:
    """
    Result of checking a constraint.

    Attributes:
        satisfied: Whether constraint is satisfied
        reason: Explanation of result
        remaining: Remaining allowance (for quotas)
        used: Amount used (for quotas)
        limit: The limit value
    """
    satisfied: bool
    reason: str = ""
    remaining: Optional[float] = None
    used: Optional[float] = None
    limit: Optional[float] = None


class ConstraintDimension(ABC):
    """
    Abstract base class for constraint dimensions.

    A dimension represents a category of constraints (e.g., cost, time, resources).
    Each dimension knows how to:
    - Parse constraint values
    - Check if constraints are satisfied
    - Validate constraint tightening (inheritance)
    - Compose with other constraints

    To create a custom dimension:
    1. Subclass ConstraintDimension
    2. Implement required abstract methods
    3. Register with ConstraintDimensionRegistry

    Example:
        >>> class TokenLimitDimension(ConstraintDimension):
        ...     name = "token_limit"
        ...     description = "Limits on LLM token usage"
        ...
        ...     def parse(self, value: Any) -> ConstraintValue:
        ...         # Parse token limit value
        ...         limit = int(value) if isinstance(value, (int, str)) else 0
        ...         return ConstraintValue(
        ...             dimension=self.name,
        ...             raw_value=value,
        ...             parsed=limit,
        ...         )
        ...
        ...     def check(self, constraint: ConstraintValue, context: Dict) -> ConstraintCheckResult:
        ...         used = context.get("tokens_used", 0)
        ...         limit = constraint.parsed
        ...         return ConstraintCheckResult(
        ...             satisfied=used <= limit,
        ...             reason=f"Token usage {used}/{limit}",
        ...             remaining=max(0, limit - used),
        ...             used=used,
        ...             limit=limit,
        ...         )
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this dimension."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        pass

    @property
    def version(self) -> str:
        """Dimension version for compatibility."""
        return "1.0.0"

    @property
    def requires_audit(self) -> bool:
        """Whether uses of this dimension should be audited."""
        return False

    @abstractmethod
    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse a raw constraint value.

        Args:
            value: Raw constraint value from configuration

        Returns:
            Parsed ConstraintValue
        """
        pass

    @abstractmethod
    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if constraint is satisfied.

        Args:
            constraint: The constraint to check
            context: Execution context (action, resources, etc.)

        Returns:
            ConstraintCheckResult indicating if satisfied
        """
        pass

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        """
        Validate that child is tighter than parent.

        Default implementation compares parsed values.
        Override for dimension-specific logic.

        Args:
            parent: Parent constraint
            child: Child constraint (must be tighter)

        Returns:
            True if child is tighter or equal, False if widening
        """
        # Default: numeric comparison if possible
        try:
            parent_val = float(parent.parsed)
            child_val = float(child.parsed)
            return child_val <= parent_val
        except (TypeError, ValueError):
            # Non-numeric: require exact match or subset
            return child.parsed == parent.parsed

    def compose(
        self,
        constraints: List[ConstraintValue],
    ) -> ConstraintValue:
        """
        Compose multiple constraints into one.

        Default: take the tightest constraint.

        Args:
            constraints: List of constraints to compose

        Returns:
            Single composed constraint
        """
        if not constraints:
            raise ValueError("Cannot compose empty constraint list")

        if len(constraints) == 1:
            return constraints[0]

        # Default: find tightest (smallest numeric value)
        tightest = constraints[0]
        for c in constraints[1:]:
            try:
                if float(c.parsed) < float(tightest.parsed):
                    tightest = c
            except (TypeError, ValueError):
                pass

        return tightest


class ConstraintDimensionRegistry:
    """
    Registry for constraint dimensions.

    Manages registration, lookup, and validation of constraint dimensions.
    Supports security review of custom dimensions.

    Example:
        >>> registry = ConstraintDimensionRegistry()
        >>>
        >>> # Register builtin dimensions
        >>> registry.register(CostLimitDimension())
        >>> registry.register(TimeDimension())
        >>>
        >>> # Register custom dimension (requires review for production)
        >>> registry.register(
        ...     TokenLimitDimension(),
        ...     requires_review=True,
        ... )
        >>>
        >>> # Get dimension
        >>> cost_dim = registry.get("cost_limit")
        >>>
        >>> # List all dimensions
        >>> for name, dim in registry.all():
        ...     print(f"{name}: {dim.description}")
    """

    # Builtin dimensions that don't require review
    BUILTIN_DIMENSIONS = {
        "cost_limit",
        "time_window",
        "resources",
        "rate_limit",
        "geo_restrictions",
        "budget_limit",
        "max_delegation_depth",
        "allowed_actions",
    }

    def __init__(self, allow_unreviewed: bool = False):
        self._dimensions: Dict[str, ConstraintDimension] = {}
        self._pending_review: Set[str] = set()
        self._reviewed: Set[str] = set()
        self._allow_unreviewed = allow_unreviewed

    def register(
        self,
        dimension: ConstraintDimension,
        requires_review: bool = False,
    ) -> None:
        """
        Register a constraint dimension.

        Args:
            dimension: The dimension to register
            requires_review: Whether dimension needs security review
        """
        name = dimension.name

        if name in self._dimensions:
            logger.warning(f"Replacing dimension: {name}")

        self._dimensions[name] = dimension

        if requires_review and name not in self.BUILTIN_DIMENSIONS:
            self._pending_review.add(name)
            logger.info(f"Dimension '{name}' registered but pending security review")
        elif name in self.BUILTIN_DIMENSIONS:
            self._reviewed.add(name)

    def approve_dimension(self, name: str, reviewer: str) -> None:
        """Mark a dimension as security reviewed."""
        if name in self._pending_review:
            self._pending_review.remove(name)
            self._reviewed.add(name)
            logger.info(f"Dimension '{name}' approved by {reviewer}")

    def get(self, name: str) -> Optional[ConstraintDimension]:
        """
        Get a dimension by name.

        Args:
            name: Dimension name

        Returns:
            ConstraintDimension or None if not found
        """
        dim = self._dimensions.get(name)

        if dim and name in self._pending_review and not self._allow_unreviewed:
            logger.warning(f"Dimension '{name}' is pending security review")
            return None

        return dim

    def has(self, name: str) -> bool:
        """Check if dimension is registered."""
        return name in self._dimensions

    def all(self) -> List[tuple[str, ConstraintDimension]]:
        """Get all registered dimensions."""
        return list(self._dimensions.items())

    def pending_review(self) -> List[str]:
        """Get dimensions pending security review."""
        return list(self._pending_review)

    def parse_constraint(
        self,
        dimension_name: str,
        value: Any,
    ) -> Optional[ConstraintValue]:
        """
        Parse a constraint value using the appropriate dimension.

        Args:
            dimension_name: Name of dimension
            value: Raw constraint value

        Returns:
            Parsed ConstraintValue or None if dimension not found
        """
        dim = self.get(dimension_name)
        if dim is None:
            return None
        return dim.parse(value)
```

### 2.2 Multi-Dimension Evaluator

**File**: `apps/kailash-kaizen/src/kaizen/trust/constraints/evaluator.py` (NEW)

```python
"""
Multi-dimension constraint evaluator.

Evaluates constraints across multiple dimensions with interaction modes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import logging

from kaizen.trust.constraints.dimension import (
    ConstraintDimension,
    ConstraintDimensionRegistry,
    ConstraintValue,
    ConstraintCheckResult,
)

logger = logging.getLogger(__name__)


class InteractionMode(str, Enum):
    """
    How multiple constraints interact.

    Modes:
    - INDEPENDENT: Each constraint evaluated separately
    - CONJUNCTIVE: ALL constraints must be satisfied (AND)
    - DISJUNCTIVE: ANY constraint being satisfied is enough (OR)
    - HIERARCHICAL: Priority-ordered evaluation
    """
    INDEPENDENT = "independent"
    CONJUNCTIVE = "conjunctive"
    DISJUNCTIVE = "disjunctive"
    HIERARCHICAL = "hierarchical"


@dataclass
class EvaluationResult:
    """
    Result of multi-dimension constraint evaluation.

    Attributes:
        satisfied: Overall satisfaction
        dimension_results: Results per dimension
        interaction_mode: Mode used for evaluation
        failed_dimensions: Dimensions that failed
        warnings: Non-fatal warnings
        anti_gaming_flags: Detected constraint gaming attempts
    """
    satisfied: bool
    dimension_results: Dict[str, ConstraintCheckResult]
    interaction_mode: InteractionMode
    failed_dimensions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    anti_gaming_flags: List[str] = field(default_factory=list)


class MultiDimensionEvaluator:
    """
    Evaluates constraints across multiple dimensions.

    Supports different interaction modes and constraint gaming detection.

    Anti-Gaming Measures:
    - Detects constraint splitting attacks
    - Flags rapid constraint changes
    - Identifies boundary manipulation

    Example:
        >>> registry = ConstraintDimensionRegistry()
        >>> # ... register dimensions ...
        >>>
        >>> evaluator = MultiDimensionEvaluator(registry)
        >>>
        >>> constraints = {
        ...     "cost_limit": 1000,
        ...     "rate_limit": 100,
        ...     "resources": ["invoices/*"],
        ... }
        >>>
        >>> context = {
        ...     "cost_used": 500,
        ...     "requests_made": 50,
        ...     "resource_requested": "invoices/2025/jan.pdf",
        ... }
        >>>
        >>> result = evaluator.evaluate(
        ...     constraints,
        ...     context,
        ...     mode=InteractionMode.CONJUNCTIVE,
        ... )
        >>>
        >>> if result.satisfied:
        ...     # Proceed with action
        ...     pass
    """

    def __init__(
        self,
        registry: ConstraintDimensionRegistry,
        enable_anti_gaming: bool = True,
    ):
        self._registry = registry
        self._anti_gaming = enable_anti_gaming
        self._evaluation_history: Dict[str, List[EvaluationResult]] = {}

    def evaluate(
        self,
        constraints: Dict[str, Any],
        context: Dict[str, Any],
        mode: InteractionMode = InteractionMode.CONJUNCTIVE,
        agent_id: Optional[str] = None,
    ) -> EvaluationResult:
        """
        Evaluate constraints across all dimensions.

        Args:
            constraints: Dict of dimension_name -> constraint_value
            context: Execution context
            mode: Interaction mode for combining results
            agent_id: Agent ID for anti-gaming tracking

        Returns:
            EvaluationResult with overall and per-dimension results
        """
        dimension_results: Dict[str, ConstraintCheckResult] = {}
        failed_dimensions: List[str] = []
        warnings: List[str] = []
        anti_gaming_flags: List[str] = []

        for dim_name, raw_value in constraints.items():
            # Get dimension
            dimension = self._registry.get(dim_name)
            if dimension is None:
                warnings.append(f"Unknown dimension: {dim_name}")
                continue

            # Parse constraint
            try:
                constraint = dimension.parse(raw_value)
            except Exception as e:
                warnings.append(f"Failed to parse {dim_name}: {e}")
                continue

            # Check constraint
            try:
                result = dimension.check(constraint, context)
                dimension_results[dim_name] = result

                if not result.satisfied:
                    failed_dimensions.append(dim_name)

            except Exception as e:
                warnings.append(f"Error checking {dim_name}: {e}")
                failed_dimensions.append(dim_name)

        # Determine overall satisfaction based on mode
        satisfied = self._compute_satisfaction(
            dimension_results, failed_dimensions, mode
        )

        # Anti-gaming checks
        if self._anti_gaming and agent_id:
            gaming_flags = self._check_anti_gaming(
                agent_id, constraints, context, dimension_results
            )
            anti_gaming_flags.extend(gaming_flags)

            if gaming_flags:
                # Gaming detected - may override satisfaction
                logger.warning(
                    f"Constraint gaming detected for {agent_id}: {gaming_flags}"
                )

        result = EvaluationResult(
            satisfied=satisfied,
            dimension_results=dimension_results,
            interaction_mode=mode,
            failed_dimensions=failed_dimensions,
            warnings=warnings,
            anti_gaming_flags=anti_gaming_flags,
        )

        # Track history for anti-gaming
        if agent_id:
            if agent_id not in self._evaluation_history:
                self._evaluation_history[agent_id] = []
            self._evaluation_history[agent_id].append(result)

            # Keep last 100 evaluations
            if len(self._evaluation_history[agent_id]) > 100:
                self._evaluation_history[agent_id] = self._evaluation_history[agent_id][-100:]

        return result

    def _compute_satisfaction(
        self,
        results: Dict[str, ConstraintCheckResult],
        failed: List[str],
        mode: InteractionMode,
    ) -> bool:
        """Compute overall satisfaction based on mode."""
        if not results:
            return True  # No constraints = satisfied

        if mode == InteractionMode.CONJUNCTIVE:
            # All must pass
            return len(failed) == 0

        elif mode == InteractionMode.DISJUNCTIVE:
            # At least one must pass
            return len(results) > len(failed)

        elif mode == InteractionMode.HIERARCHICAL:
            # First dimension determines result
            # (Assumes constraints dict maintains order)
            if results:
                first_dim = next(iter(results.keys()))
                return results[first_dim].satisfied
            return True

        else:  # INDEPENDENT
            # Report per-dimension, overall true if majority pass
            return len(failed) <= len(results) / 2

    def _check_anti_gaming(
        self,
        agent_id: str,
        constraints: Dict[str, Any],
        context: Dict[str, Any],
        results: Dict[str, ConstraintCheckResult],
    ) -> List[str]:
        """
        Check for constraint gaming attempts.

        Gaming patterns detected:
        - Boundary pushing: Consistently hitting limits
        - Constraint splitting: Breaking operations to avoid limits
        - Rapid switching: Frequent constraint changes
        """
        flags = []

        # Check boundary pushing
        for dim_name, result in results.items():
            if result.remaining is not None and result.limit:
                usage_ratio = (result.limit - result.remaining) / result.limit
                if usage_ratio > 0.95:
                    flags.append(f"boundary_pushing:{dim_name}")

        # Check history for patterns
        history = self._evaluation_history.get(agent_id, [])
        if len(history) >= 10:
            # Check for constraint splitting (many small operations)
            recent = history[-10:]
            small_ops = sum(
                1 for h in recent
                if any(
                    r.used and r.limit and r.used / r.limit < 0.1
                    for r in h.dimension_results.values()
                )
            )
            if small_ops >= 8:
                flags.append("potential_splitting")

        return flags

    def validate_tightening(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
    ) -> List[str]:
        """
        Validate that child constraints are tighter than parent.

        Returns list of violations (empty if valid).
        """
        violations = []

        for dim_name, child_value in child_constraints.items():
            dimension = self._registry.get(dim_name)
            if dimension is None:
                continue

            parent_value = parent_constraints.get(dim_name)
            if parent_value is None:
                # New constraint - always allowed
                continue

            parent_cv = dimension.parse(parent_value)
            child_cv = dimension.parse(child_value)

            if not dimension.validate_tightening(parent_cv, child_cv):
                violations.append(
                    f"{dim_name}: child {child_value} looser than parent {parent_value}"
                )

        return violations
```

### 2.3 Builtin Constraint Dimensions

**File**: `apps/kailash-kaizen/src/kaizen/trust/constraints/builtin.py` (NEW)

```python
"""
Builtin constraint dimensions for EATP.

Provides standard constraint dimensions for common use cases.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set
import fnmatch
from datetime import datetime, timezone

from kaizen.trust.constraints.dimension import (
    ConstraintDimension,
    ConstraintValue,
    ConstraintCheckResult,
)


class CostLimitDimension(ConstraintDimension):
    """Cost/budget limit constraint dimension."""

    @property
    def name(self) -> str:
        return "cost_limit"

    @property
    def description(self) -> str:
        return "Maximum cost/budget for operations"

    @property
    def requires_audit(self) -> bool:
        return True

    def parse(self, value: Any) -> ConstraintValue:
        limit = float(value) if isinstance(value, (int, float, str)) else 0.0
        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=limit,
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        used = context.get("cost_used", 0.0)
        limit = constraint.parsed

        return ConstraintCheckResult(
            satisfied=used <= limit,
            reason=f"Cost ${used:.2f} / ${limit:.2f}",
            remaining=max(0, limit - used),
            used=used,
            limit=limit,
        )


class TimeDimension(ConstraintDimension):
    """Time window constraint dimension."""

    @property
    def name(self) -> str:
        return "time_window"

    @property
    def description(self) -> str:
        return "Allowed time window for operations (HH:MM-HH:MM)"

    def parse(self, value: Any) -> ConstraintValue:
        # Expected format: "09:00-17:00"
        if isinstance(value, str) and "-" in value:
            start, end = value.split("-")
            start_mins = self._time_to_minutes(start.strip())
            end_mins = self._time_to_minutes(end.strip())
            parsed = {"start": start_mins, "end": end_mins}
        else:
            parsed = {"start": 0, "end": 1440}  # Full day

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
        )

    def _time_to_minutes(self, time_str: str) -> int:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        now = context.get("current_time", datetime.now(timezone.utc))
        current_mins = now.hour * 60 + now.minute

        start = constraint.parsed["start"]
        end = constraint.parsed["end"]

        in_window = start <= current_mins <= end

        return ConstraintCheckResult(
            satisfied=in_window,
            reason=f"Current time {now.strftime('%H:%M')} vs window {start//60}:{start%60:02d}-{end//60}:{end%60:02d}",
        )

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        # Child window must be subset of parent
        return (
            child.parsed["start"] >= parent.parsed["start"]
            and child.parsed["end"] <= parent.parsed["end"]
        )


class ResourceDimension(ConstraintDimension):
    """Resource access constraint dimension with glob support."""

    @property
    def name(self) -> str:
        return "resources"

    @property
    def description(self) -> str:
        return "Allowed resources (glob patterns)"

    def parse(self, value: Any) -> ConstraintValue:
        if isinstance(value, str):
            patterns = [value]
        elif isinstance(value, list):
            patterns = value
        else:
            patterns = []

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=patterns,
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        resource = context.get("resource_requested", "")
        patterns = constraint.parsed

        for pattern in patterns:
            if fnmatch.fnmatch(resource, pattern):
                return ConstraintCheckResult(
                    satisfied=True,
                    reason=f"Resource '{resource}' matches pattern '{pattern}'",
                )

        return ConstraintCheckResult(
            satisfied=False,
            reason=f"Resource '{resource}' not allowed by patterns {patterns}",
        )

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        # Each child pattern must match at least one parent pattern
        for child_pattern in child.parsed:
            matched = False
            for parent_pattern in parent.parsed:
                # Check if child is more specific than parent
                if fnmatch.fnmatch(child_pattern, parent_pattern):
                    matched = True
                    break
            if not matched:
                return False
        return True


class RateLimitDimension(ConstraintDimension):
    """Rate limit constraint dimension."""

    @property
    def name(self) -> str:
        return "rate_limit"

    @property
    def description(self) -> str:
        return "Maximum requests per time period"

    def parse(self, value: Any) -> ConstraintValue:
        # Can be int (per minute) or "100/hour"
        if isinstance(value, int):
            parsed = {"limit": value, "period": "minute"}
        elif isinstance(value, str) and "/" in value:
            limit, period = value.split("/")
            parsed = {"limit": int(limit), "period": period}
        else:
            parsed = {"limit": int(value), "period": "minute"}

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        requests = context.get("requests_in_period", 0)
        limit = constraint.parsed["limit"]
        period = constraint.parsed["period"]

        return ConstraintCheckResult(
            satisfied=requests <= limit,
            reason=f"Requests {requests}/{limit} per {period}",
            remaining=max(0, limit - requests),
            used=requests,
            limit=limit,
        )


class DataAccessDimension(ConstraintDimension):
    """Data access constraint dimension for PII/sensitivity."""

    @property
    def name(self) -> str:
        return "data_access"

    @property
    def description(self) -> str:
        return "Data access restrictions (PII, sensitivity levels)"

    @property
    def requires_audit(self) -> bool:
        return True

    def parse(self, value: Any) -> ConstraintValue:
        if isinstance(value, dict):
            parsed = value
        elif isinstance(value, str):
            # Simple strings like "no_pii" or "internal_only"
            parsed = {"level": value}
        else:
            parsed = {}

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        data_classification = context.get("data_classification", "public")
        contains_pii = context.get("contains_pii", False)

        level = constraint.parsed.get("level", "all")

        if level == "no_pii" and contains_pii:
            return ConstraintCheckResult(
                satisfied=False,
                reason="PII access not allowed",
            )

        if level == "internal_only" and data_classification == "external":
            return ConstraintCheckResult(
                satisfied=False,
                reason="External data access not allowed",
            )

        return ConstraintCheckResult(
            satisfied=True,
            reason=f"Data access allowed (level={level})",
        )


class CommunicationDimension(ConstraintDimension):
    """Communication/network constraint dimension."""

    @property
    def name(self) -> str:
        return "communication"

    @property
    def description(self) -> str:
        return "Network and communication restrictions"

    def parse(self, value: Any) -> ConstraintValue:
        if isinstance(value, dict):
            parsed = value
        elif isinstance(value, str):
            parsed = {"mode": value}
        else:
            parsed = {"mode": "all"}

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        target = context.get("communication_target", "")
        mode = constraint.parsed.get("mode", "all")
        allowed_domains = constraint.parsed.get("allowed_domains", [])

        if mode == "none":
            return ConstraintCheckResult(
                satisfied=False,
                reason="No external communication allowed",
            )

        if mode == "internal_only":
            if target and not target.endswith(".internal"):
                return ConstraintCheckResult(
                    satisfied=False,
                    reason=f"External communication to {target} not allowed",
                )

        if allowed_domains and target:
            if not any(target.endswith(d) for d in allowed_domains):
                return ConstraintCheckResult(
                    satisfied=False,
                    reason=f"Target {target} not in allowed domains",
                )

        return ConstraintCheckResult(
            satisfied=True,
            reason=f"Communication allowed (mode={mode})",
        )
```

---

## Part 3: Posture Metrics Collection

**File**: `apps/kailash-kaizen/src/kaizen/trust/metrics.py` (NEW)

```python
"""
Metrics collection for posture and constraint systems.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict


@dataclass
class PostureMetrics:
    """Metrics for posture system."""
    posture_distribution: Dict[str, int] = field(default_factory=dict)
    transitions_by_type: Dict[str, int] = field(default_factory=dict)
    circuit_breaker_opens: int = 0
    emergency_downgrades: int = 0
    average_posture_level: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConstraintMetrics:
    """Metrics for constraint system."""
    evaluations_total: int = 0
    evaluations_passed: int = 0
    evaluations_failed: int = 0
    dimension_failures: Dict[str, int] = field(default_factory=dict)
    anti_gaming_flags: Dict[str, int] = field(default_factory=dict)
    average_evaluation_time_ms: float = 0.0


class TrustMetricsCollector:
    """
    Collects and aggregates trust system metrics.
    """

    def __init__(self):
        self._posture_counts: Dict[str, int] = defaultdict(int)
        self._transition_counts: Dict[str, int] = defaultdict(int)
        self._constraint_counts: Dict[str, int] = defaultdict(int)
        self._dimension_failures: Dict[str, int] = defaultdict(int)
        self._gaming_flags: Dict[str, int] = defaultdict(int)
        self._circuit_breaker_opens = 0
        self._emergency_downgrades = 0
        self._evaluation_times: List[float] = []

    def record_posture(self, agent_id: str, posture: str) -> None:
        """Record an agent's current posture."""
        self._posture_counts[posture] += 1

    def record_transition(self, transition_type: str) -> None:
        """Record a posture transition."""
        self._transition_counts[transition_type] += 1

    def record_circuit_breaker_open(self) -> None:
        """Record a circuit breaker opening."""
        self._circuit_breaker_opens += 1

    def record_emergency_downgrade(self) -> None:
        """Record an emergency downgrade."""
        self._emergency_downgrades += 1

    def record_constraint_evaluation(
        self,
        passed: bool,
        failed_dimensions: List[str],
        gaming_flags: List[str],
        duration_ms: float,
    ) -> None:
        """Record a constraint evaluation."""
        if passed:
            self._constraint_counts["passed"] += 1
        else:
            self._constraint_counts["failed"] += 1

        for dim in failed_dimensions:
            self._dimension_failures[dim] += 1

        for flag in gaming_flags:
            self._gaming_flags[flag] += 1

        self._evaluation_times.append(duration_ms)
        if len(self._evaluation_times) > 1000:
            self._evaluation_times = self._evaluation_times[-1000:]

    def get_posture_metrics(self) -> PostureMetrics:
        """Get aggregated posture metrics."""
        total_agents = sum(self._posture_counts.values())
        avg_level = 0.0
        if total_agents > 0:
            level_sum = sum(
                count * {"full_autonomy": 5, "assisted": 4, "supervised": 3, "human_decides": 2, "blocked": 1}.get(p, 0)
                for p, count in self._posture_counts.items()
            )
            avg_level = level_sum / total_agents

        return PostureMetrics(
            posture_distribution=dict(self._posture_counts),
            transitions_by_type=dict(self._transition_counts),
            circuit_breaker_opens=self._circuit_breaker_opens,
            emergency_downgrades=self._emergency_downgrades,
            average_posture_level=avg_level,
        )

    def get_constraint_metrics(self) -> ConstraintMetrics:
        """Get aggregated constraint metrics."""
        avg_time = sum(self._evaluation_times) / len(self._evaluation_times) if self._evaluation_times else 0.0

        return ConstraintMetrics(
            evaluations_total=self._constraint_counts["passed"] + self._constraint_counts["failed"],
            evaluations_passed=self._constraint_counts["passed"],
            evaluations_failed=self._constraint_counts["failed"],
            dimension_failures=dict(self._dimension_failures),
            anti_gaming_flags=dict(self._gaming_flags),
            average_evaluation_time_ms=avg_time,
        )

    def reset(self) -> None:
        """Reset all metrics."""
        self._posture_counts.clear()
        self._transition_counts.clear()
        self._constraint_counts.clear()
        self._dimension_failures.clear()
        self._gaming_flags.clear()
        self._circuit_breaker_opens = 0
        self._emergency_downgrades = 0
        self._evaluation_times.clear()
```

---

## Testing Requirements

### Posture Tests

```python
# tests/unit/trust/test_posture_machine.py

def test_5_posture_levels():
    """All 5 postures should be defined."""
    from kaizen.trust.postures import TrustPosture
    assert len(TrustPosture) == 5
    assert TrustPosture.ASSISTED in TrustPosture


@pytest.mark.asyncio
async def test_upgrade_requires_approval():
    """Upgrades should require approval."""
    machine = PostureStateMachine()
    machine.set_initial_posture("agent-1", TrustPosture.SUPERVISED)

    request = PostureTransitionRequest(
        agent_id="agent-1",
        current_posture=TrustPosture.SUPERVISED,
        target_posture=TrustPosture.ASSISTED,
        approvals=[],  # No approvals
    )

    result = await machine.transition(request)
    assert not result.success
    assert "approval" in result.reason.lower()


@pytest.mark.asyncio
async def test_emergency_downgrade():
    """Emergency downgrade should bypass guards."""
    machine = PostureStateMachine()
    machine.set_initial_posture("agent-1", TrustPosture.FULL_AUTONOMY)

    result = await machine.emergency_downgrade("agent-1", "Security incident")

    assert result.success
    assert result.new_posture == TrustPosture.BLOCKED
```

### Circuit Breaker Tests

```python
# tests/unit/trust/test_circuit_breaker.py

@pytest.mark.asyncio
async def test_circuit_opens_on_threshold():
    """Circuit should open when failure threshold reached."""
    breaker = PostureCircuitBreaker(
        posture_machine=PostureStateMachine(),
        config=CircuitBreakerConfig(failure_threshold=3),
    )

    for i in range(3):
        await breaker.record_failure(
            agent_id="agent-1",
            error_type="TestError",
            error_message="Test failure",
            action="test",
        )

    assert breaker.get_state("agent-1") == CircuitState.OPEN
```

### Constraint Tests

```python
# tests/unit/trust/test_constraints.py

def test_cost_dimension():
    """Cost dimension should track usage."""
    dim = CostLimitDimension()
    constraint = dim.parse(1000)

    result = dim.check(constraint, {"cost_used": 500})
    assert result.satisfied
    assert result.remaining == 500

    result = dim.check(constraint, {"cost_used": 1500})
    assert not result.satisfied


def test_constraint_gaming_detection():
    """Anti-gaming should detect boundary pushing."""
    registry = ConstraintDimensionRegistry()
    registry.register(CostLimitDimension())

    evaluator = MultiDimensionEvaluator(registry, enable_anti_gaming=True)

    # Simulate boundary pushing
    for i in range(10):
        evaluator.evaluate(
            {"cost_limit": 100},
            {"cost_used": 99},  # 99% usage
            agent_id="gamer",
        )

    result = evaluator.evaluate(
        {"cost_limit": 100},
        {"cost_used": 99},
        agent_id="gamer",
    )

    assert "boundary_pushing" in str(result.anti_gaming_flags)
```

---

## References

- Enterprise-App Specification
- Current postures.py: `apps/kailash-kaizen/src/kaizen/trust/postures.py`
- Constraint validator: `apps/kailash-kaizen/src/kaizen/trust/constraint_validator.py`
