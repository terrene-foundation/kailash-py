"""System-wide resource quotas for the Kailash SDK.

This module provides configurable resource quotas and enforcement for
workflow execution. It enables operators to set limits on concurrent
workflows, execution duration, and queue depth to prevent resource
exhaustion in production deployments.

Usage:
    >>> from kailash.runtime.quotas import ResourceQuotas, QuotaEnforcer
    >>>
    >>> quotas = ResourceQuotas(
    ...     max_concurrent_workflows=50,
    ...     max_workflow_duration_seconds=1800.0,
    ...     max_queued_workflows=500,
    ... )
    >>> enforcer = QuotaEnforcer(quotas)
    >>>
    >>> # In async context:
    >>> async with enforcer.acquire() as token:
    ...     # Execute workflow within quota limits
    ...     results = await run_workflow()
    >>>
    >>> # Standalone acquire/release:
    >>> token = await enforcer.acquire_slot()
    >>> try:
    ...     results = await run_workflow()
    ... finally:
    ...     enforcer.release_slot(token)

See Also:
    - LocalRuntime: Can accept QuotaEnforcer for execution limits
    - ResourceCoordinator: Cross-runtime resource coordination

Version:
    Added in: v0.13.0
"""

import asyncio
import logging
import math
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, AsyncIterator, Dict, Optional, Set

logger = logging.getLogger(__name__)

__all__ = [
    "ResourceQuotas",
    "QuotaEnforcer",
    "QuotaExceededError",
    "WorkflowDurationExceededError",
]


class QuotaExceededError(Exception):
    """Raised when a resource quota is exceeded.

    Attributes:
        quota_name: The name of the quota that was exceeded.
        current_value: The current usage level.
        max_value: The configured limit.
    """

    def __init__(self, quota_name: str, current_value: int, max_value: int) -> None:
        self.quota_name = quota_name
        self.current_value = current_value
        self.max_value = max_value
        super().__init__(
            f"Quota exceeded: {quota_name} (current={current_value}, max={max_value})"
        )


class WorkflowDurationExceededError(Exception):
    """Raised when a workflow exceeds its maximum allowed duration.

    Attributes:
        duration_seconds: How long the workflow ran.
        max_seconds: The configured maximum duration.
        workflow_id: The ID of the workflow that exceeded the limit.
    """

    def __init__(
        self, duration_seconds: float, max_seconds: float, workflow_id: str = ""
    ) -> None:
        self.duration_seconds = duration_seconds
        self.max_seconds = max_seconds
        self.workflow_id = workflow_id
        super().__init__(
            f"Workflow duration {duration_seconds:.1f}s exceeded "
            f"maximum {max_seconds:.1f}s"
            + (f" (workflow_id={workflow_id})" if workflow_id else "")
        )


@dataclass
class ResourceQuotas:
    """Configuration for system-wide resource quotas.

    Attributes:
        max_concurrent_workflows: Maximum number of workflows that can
            execute simultaneously. Defaults to 100.
        max_workflow_duration_seconds: Maximum wall-clock time in seconds
            for a single workflow execution. Defaults to 3600 (1 hour).
        max_queued_workflows: Maximum number of workflows waiting to
            acquire an execution slot. Defaults to 1000.

    Example:
        >>> quotas = ResourceQuotas(
        ...     max_concurrent_workflows=20,
        ...     max_workflow_duration_seconds=600.0,
        ... )
    """

    max_concurrent_workflows: int = 100
    max_workflow_duration_seconds: float = 3600.0
    max_queued_workflows: int = 1000

    def __post_init__(self) -> None:
        """Validate quota values."""
        if (
            not math.isfinite(self.max_concurrent_workflows)
            or self.max_concurrent_workflows < 1
        ):
            raise ValueError(
                f"max_concurrent_workflows must be a finite number >= 1, "
                f"got {self.max_concurrent_workflows}"
            )
        if (
            not math.isfinite(self.max_workflow_duration_seconds)
            or self.max_workflow_duration_seconds <= 0
        ):
            raise ValueError(
                f"max_workflow_duration_seconds must be a finite number > 0, "
                f"got {self.max_workflow_duration_seconds}"
            )
        if (
            not math.isfinite(self.max_queued_workflows)
            or self.max_queued_workflows < 0
        ):
            raise ValueError(
                f"max_queued_workflows must be a finite number >= 0, "
                f"got {self.max_queued_workflows}"
            )


@dataclass
class _SlotToken:
    """Internal token representing an acquired execution slot.

    Attributes:
        token_id: Unique identifier for this slot acquisition.
        acquired_at: When the slot was acquired.
    """

    token_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    acquired_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class QuotaEnforcer:
    """Enforces resource quotas on workflow execution.

    Uses asyncio.Semaphore for concurrency limiting and asyncio.timeout
    for duration enforcement. Tracks active and queued workflows for
    observability.

    Args:
        quotas: The ResourceQuotas configuration to enforce.

    Example:
        >>> enforcer = QuotaEnforcer(ResourceQuotas(max_concurrent_workflows=10))
        >>> async with enforcer.acquire() as token:
        ...     await execute_workflow()
    """

    def __init__(self, quotas: Optional[ResourceQuotas] = None) -> None:
        self._quotas = quotas or ResourceQuotas()
        self._semaphore = asyncio.Semaphore(self._quotas.max_concurrent_workflows)
        self._active_slots: Dict[str, _SlotToken] = {}
        self._queued_count: int = 0
        self._total_acquired: int = 0
        self._total_released: int = 0
        self._total_rejected: int = 0

        logger.info(
            "QuotaEnforcer initialized: max_concurrent=%d, max_duration=%.1fs, max_queued=%d",
            self._quotas.max_concurrent_workflows,
            self._quotas.max_workflow_duration_seconds,
            self._quotas.max_queued_workflows,
        )

    @property
    def quotas(self) -> ResourceQuotas:
        """Get the current quota configuration."""
        return self._quotas

    @property
    def active_count(self) -> int:
        """Number of currently active (executing) workflows."""
        return len(self._active_slots)

    @property
    def queued_count(self) -> int:
        """Number of workflows waiting for an execution slot."""
        return self._queued_count

    @property
    def available_slots(self) -> int:
        """Number of available execution slots."""
        return self._quotas.max_concurrent_workflows - len(self._active_slots)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get quota enforcement statistics.

        Returns:
            A dictionary with current and cumulative statistics.
        """
        return {
            "active": self.active_count,
            "queued": self._queued_count,
            "available": self.available_slots,
            "total_acquired": self._total_acquired,
            "total_released": self._total_released,
            "total_rejected": self._total_rejected,
            "max_concurrent": self._quotas.max_concurrent_workflows,
            "max_duration_seconds": self._quotas.max_workflow_duration_seconds,
            "max_queued": self._quotas.max_queued_workflows,
        }

    async def acquire_slot(self) -> _SlotToken:
        """Acquire an execution slot.

        Blocks until a slot is available, respecting the queue depth limit.

        Returns:
            A _SlotToken that must be passed to release_slot() when done.

        Raises:
            QuotaExceededError: If the queue is full (max_queued_workflows
                reached).
        """
        # Try non-blocking acquire first. If a slot is immediately
        # available, no queuing occurs and max_queued_workflows is irrelevant.
        if self._semaphore._value > 0:
            await self._semaphore.acquire()
        else:
            # Slot not immediately available -- this caller must queue.
            # Check queue depth limit before waiting.
            if self._queued_count >= self._quotas.max_queued_workflows:
                self._total_rejected += 1
                raise QuotaExceededError(
                    quota_name="max_queued_workflows",
                    current_value=self._queued_count,
                    max_value=self._quotas.max_queued_workflows,
                )

            self._queued_count += 1
            try:
                await self._semaphore.acquire()
            except BaseException:
                self._queued_count -= 1
                raise
            self._queued_count -= 1

        token = _SlotToken()
        self._active_slots[token.token_id] = token
        self._total_acquired += 1

        logger.debug(
            "Slot acquired: token=%s, active=%d/%d",
            token.token_id,
            self.active_count,
            self._quotas.max_concurrent_workflows,
        )
        return token

    def release_slot(self, token: _SlotToken) -> None:
        """Release an execution slot.

        Args:
            token: The token returned by acquire_slot().

        Raises:
            KeyError: If the token is not recognized (already released
                or invalid).
        """
        if token.token_id not in self._active_slots:
            raise KeyError(
                f"Slot token '{token.token_id}' not found. "
                f"It may have already been released."
            )

        del self._active_slots[token.token_id]
        self._semaphore.release()
        self._total_released += 1

        logger.debug(
            "Slot released: token=%s, active=%d/%d",
            token.token_id,
            self.active_count,
            self._quotas.max_concurrent_workflows,
        )

    @asynccontextmanager
    async def acquire(
        self, timeout_seconds: Optional[float] = None
    ) -> AsyncIterator[_SlotToken]:
        """Context manager that acquires a slot and enforces duration limit.

        The duration limit defaults to the quota's max_workflow_duration_seconds
        but can be overridden per-call via timeout_seconds.

        Args:
            timeout_seconds: Optional override for maximum execution duration.
                Defaults to the quota's max_workflow_duration_seconds.

        Yields:
            A _SlotToken for the acquired slot.

        Raises:
            QuotaExceededError: If the queue is full.
            WorkflowDurationExceededError: If the workflow exceeds its
                maximum duration.

        Example:
            >>> async with enforcer.acquire() as token:
            ...     await execute_workflow()
        """
        max_duration = timeout_seconds or self._quotas.max_workflow_duration_seconds
        token = await self.acquire_slot()

        try:
            async with asyncio.timeout(max_duration):
                yield token
        except asyncio.TimeoutError:
            elapsed = (datetime.now(UTC) - token.acquired_at).total_seconds()
            raise WorkflowDurationExceededError(
                duration_seconds=elapsed,
                max_seconds=max_duration,
            )
        finally:
            if token.token_id in self._active_slots:
                self.release_slot(token)
