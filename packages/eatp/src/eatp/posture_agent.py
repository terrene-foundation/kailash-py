# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Posture-aware agent wrapper for trust-based execution control.

Provides posture-based behavior wrapping for any Kaizen agent,
enforcing trust postures (DELEGATED, CONTINUOUS_INSIGHT, SHARED_PLANNING,
SUPERVISED, PSEUDO_AGENT) on agent execution.

Part of CARE-029 implementation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Protocol

from eatp.postures import PostureStateMachine, TrustPosture

logger = logging.getLogger(__name__)


class ApprovalHandler(Protocol):
    """Protocol for handling human approval requests."""

    async def request_approval(
        self,
        agent_id: str,
        action_description: str,
        kwargs: Dict[str, Any],
    ) -> bool:
        """Request human approval for an action.

        Args:
            agent_id: The agent requesting approval
            action_description: Description of the action to approve
            kwargs: The action parameters

        Returns:
            True if approved, False if denied
        """
        ...


class NotificationHandler(Protocol):
    """Protocol for handling notifications."""

    async def notify(
        self,
        agent_id: str,
        message: str,
        action_kwargs: Dict[str, Any],
    ) -> None:
        """Send a notification about an action.

        Args:
            agent_id: The agent performing the action
            message: Notification message
            action_kwargs: The action parameters
        """
        ...


class CircuitBreaker(Protocol):
    """Protocol for circuit breaker integration."""

    def is_open(self) -> bool:
        """Check if the circuit breaker is open (blocking executions)."""
        ...

    def record_success(self) -> None:
        """Record a successful execution."""
        ...

    def record_failure(self) -> None:
        """Record a failed execution."""
        ...


@dataclass
class AuditEntry:
    """Audit log entry for agent actions."""

    agent_id: str
    posture: TrustPosture
    action: str
    kwargs: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class PostureAwareAgent:
    """Wrapper that adds posture-based behavior to any Kaizen agent.

    Enforces trust postures on agent execution:
    - DELEGATED: Execute directly without restrictions
    - CONTINUOUS_INSIGHT: Notify, wait for cancel window, then execute with audit
    - SHARED_PLANNING: Execute with audit logging
    - SUPERVISED: Require approval before execution
    - PSEUDO_AGENT: Deny execution

    Example:
        >>> from eatp.postures import PostureStateMachine, TrustPosture
        >>> # PostureAgent wraps any agent with trust posture management
        >>>
        >>> machine = PostureStateMachine()
        >>> machine.set_posture("agent-001", TrustPosture.DELEGATED)
        >>>
        >>> base_agent = MyAgent(config)
        >>> agent = PostureAwareAgent(
        ...     base_agent=base_agent,
        ...     agent_id="agent-001",
        ...     posture_machine=machine,
        ... )
        >>> result = await agent.run(query="What is AI?")
    """

    def __init__(
        self,
        base_agent: Any,
        agent_id: str,
        posture_machine: PostureStateMachine,
        circuit_breaker: Optional[CircuitBreaker] = None,
        approval_handler: Optional[ApprovalHandler] = None,
        notification_handler: Optional[NotificationHandler] = None,
        assisted_delay_seconds: float = 5.0,
    ):
        """Initialize posture-aware agent wrapper.

        Args:
            base_agent: The base Kaizen agent to wrap
            agent_id: Unique identifier for this agent
            posture_machine: PostureStateMachine for posture management
            circuit_breaker: Optional circuit breaker for failure protection
            approval_handler: Handler for SUPERVISED approval requests
            notification_handler: Handler for CONTINUOUS_INSIGHT mode notifications
            assisted_delay_seconds: Delay in seconds for CONTINUOUS_INSIGHT mode cancel window
        """
        self._base_agent = base_agent
        self._agent_id = agent_id
        self._posture_machine = posture_machine
        self._circuit_breaker = circuit_breaker
        self._approval_handler = approval_handler
        self._notification_handler = notification_handler
        self._assisted_delay_seconds = assisted_delay_seconds
        self._cancel_event: Optional[asyncio.Event] = None
        self._audit_log: list[AuditEntry] = []

    @property
    def posture(self) -> TrustPosture:
        """Get current trust posture for this agent."""
        return self._posture_machine.get_posture(self._agent_id)

    @property
    def agent_id(self) -> str:
        """Get the agent ID."""
        return self._agent_id

    @property
    def audit_log(self) -> list[AuditEntry]:
        """Get the audit log entries."""
        return list(self._audit_log)

    async def run(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute the wrapped agent with posture-based behavior.

        Args:
            **kwargs: Arguments to pass to the base agent

        Returns:
            Result from the base agent execution

        Raises:
            PermissionError: If posture is PSEUDO_AGENT or circuit breaker is open
            ValueError: If SUPERVISED without approval_handler
        """
        # Check circuit breaker first if configured
        if self._circuit_breaker is not None and self._circuit_breaker.is_open():
            logger.warning(
                f"Circuit breaker open for agent {self._agent_id}, " "execution blocked"
            )
            raise PermissionError(f"Circuit breaker is open for agent {self._agent_id}")

        posture = self.posture

        # Execute based on posture
        if posture == TrustPosture.PSEUDO_AGENT:
            logger.warning(f"Agent {self._agent_id} is PSEUDO_AGENT, execution denied")
            raise PermissionError(f"Agent {self._agent_id} is blocked from execution")

        if posture == TrustPosture.SUPERVISED:
            return await self._execute_with_approval(kwargs)

        if posture == TrustPosture.SHARED_PLANNING:
            return await self._execute_with_audit(kwargs)

        if posture == TrustPosture.CONTINUOUS_INSIGHT:
            return await self._execute_with_delay(kwargs)

        # DELEGATED
        return await self._execute_direct(kwargs)

    async def _execute_direct(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute directly without restrictions.

        Records success/failure to circuit breaker if configured.
        """
        try:
            result = await self._invoke_base_agent(kwargs)
            if self._circuit_breaker is not None:
                self._circuit_breaker.record_success()
            return result
        except Exception as e:
            if self._circuit_breaker is not None:
                self._circuit_breaker.record_failure()
            raise

    async def _execute_with_audit(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute with audit logging before and after."""
        start_time = datetime.now(timezone.utc)
        entry = AuditEntry(
            agent_id=self._agent_id,
            posture=self.posture,
            action="run",
            kwargs=dict(kwargs),
            timestamp=start_time,
        )

        logger.info(
            f"[AUDIT] Agent {self._agent_id} starting execution with "
            f"posture={self.posture.value}, kwargs={kwargs}"
        )

        try:
            result = await self._execute_direct(kwargs)
            end_time = datetime.now(timezone.utc)
            entry.result = result
            entry.duration_ms = (end_time - start_time).total_seconds() * 1000

            logger.info(
                f"[AUDIT] Agent {self._agent_id} completed execution "
                f"in {entry.duration_ms:.2f}ms"
            )
            return result
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            entry.error = str(e)
            entry.duration_ms = (end_time - start_time).total_seconds() * 1000

            logger.error(f"[AUDIT] Agent {self._agent_id} failed execution: {e}")
            raise
        finally:
            self._audit_log.append(entry)

    async def _execute_with_delay(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute with notification, cancel window, and audit.

        Sends notification, waits for cancel window (can be cancelled via
        cancel_pending() method), then executes with audit.
        """
        # Send notification if handler is configured
        if self._notification_handler is not None:
            await self._notification_handler.notify(
                agent_id=self._agent_id,
                message=f"Agent {self._agent_id} will execute in "
                f"{self._assisted_delay_seconds} seconds",
                action_kwargs=kwargs,
            )

        logger.info(
            f"Agent {self._agent_id} in CONTINUOUS_INSIGHT mode, "
            f"waiting {self._assisted_delay_seconds}s for cancel"
        )

        # Create cancel event for this execution
        self._cancel_event = asyncio.Event()

        try:
            # Wait for delay or cancel
            cancelled = await self._wait_for_cancel_or_timeout()
            if cancelled:
                logger.info(
                    f"Agent {self._agent_id} execution cancelled during "
                    "CONTINUOUS_INSIGHT delay"
                )
                raise PermissionError(f"Agent {self._agent_id} execution was cancelled")

            # Execute with audit
            return await self._execute_with_audit(kwargs)
        finally:
            self._cancel_event = None

    async def _wait_for_cancel_or_timeout(self) -> bool:
        """Wait for cancel event or timeout.

        Returns:
            True if cancelled, False if timeout reached
        """
        try:
            await asyncio.wait_for(
                self._cancel_event.wait(),
                timeout=self._assisted_delay_seconds,
            )
            return True  # Event was set (cancelled)
        except asyncio.TimeoutError:
            return False  # Timeout reached without cancel

    def cancel_pending(self) -> bool:
        """Cancel a pending CONTINUOUS_INSIGHT mode execution.

        Returns:
            True if there was a pending execution to cancel
        """
        if self._cancel_event is not None:
            self._cancel_event.set()
            return True
        return False

    async def _execute_with_approval(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute with human approval requirement."""
        if self._approval_handler is None:
            raise ValueError(
                f"Agent {self._agent_id} requires approval_handler for "
                "SUPERVISED posture"
            )

        logger.info(f"Agent {self._agent_id} requesting approval for execution")

        approved = await self._approval_handler.request_approval(
            agent_id=self._agent_id,
            action_description=f"Execute agent run with kwargs: {kwargs}",
            kwargs=kwargs,
        )

        if not approved:
            logger.warning(
                f"Agent {self._agent_id} execution denied by approval handler"
            )
            raise PermissionError(
                f"Agent {self._agent_id} execution was denied by approver"
            )

        # Execute with audit after approval
        return await self._execute_with_audit(kwargs)

    async def _invoke_base_agent(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke the base agent's run method.

        Handles both sync and async run methods.
        """
        # Check if base agent has async run method
        run_method = getattr(self._base_agent, "run", None)
        if run_method is None:
            raise AttributeError("Base agent does not have a 'run' method")

        result = run_method(**kwargs)

        # Handle coroutine if async
        if asyncio.iscoroutine(result):
            result = await result

        # Ensure we return a dict
        if isinstance(result, dict):
            return result
        return {"result": result}


__all__ = [
    "PostureAwareAgent",
    "ApprovalHandler",
    "NotificationHandler",
    "CircuitBreaker",
    "AuditEntry",
]
