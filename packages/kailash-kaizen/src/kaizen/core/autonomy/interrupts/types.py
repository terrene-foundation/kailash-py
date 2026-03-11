"""
Core types for the Interrupt Mechanism.

Defines interrupt modes, sources, reasons, and status.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class InterruptMode(Enum):
    """
    How to handle interrupt.

    GRACEFUL: Finish current step, then checkpoint and stop
    IMMEDIATE: Stop now, checkpoint if possible
    """

    GRACEFUL = "graceful"
    IMMEDIATE = "immediate"


class InterruptSource(Enum):
    """
    Source of interrupt.

    SIGNAL: OS signal (SIGINT, SIGTERM, SIGUSR1)
    TIMEOUT: Execution time limit exceeded
    BUDGET: Token/cost budget exceeded
    USER: User requested via control protocol
    PROGRAMMATIC: Code-initiated interrupt (hook, policy)
    """

    SIGNAL = "signal"
    TIMEOUT = "timeout"
    BUDGET = "budget"
    USER = "user"
    PROGRAMMATIC = "programmatic"


@dataclass
class InterruptReason:
    """
    Details about why interrupt occurred.

    Captures complete context for debugging and auditing.
    """

    source: InterruptSource
    mode: InterruptMode
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Human-readable string representation"""
        return (
            f"Interrupt({self.source.value}, {self.mode.value}): "
            f"{self.message} at {self.timestamp.isoformat()}"
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to JSON-serializable dictionary.

        Returns:
            Dictionary with enum values as strings
        """
        return {
            "source": self.source.value,
            "mode": self.mode.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class InterruptStatus:
    """
    Current interrupt status after shutdown.

    Includes checkpoint information for resume capability.
    """

    interrupted: bool
    reason: InterruptReason | None = None
    checkpoint_id: str | None = None  # Checkpoint saved before interrupt

    def can_resume(self) -> bool:
        """Check if execution can be resumed from checkpoint"""
        return self.checkpoint_id is not None


class InterruptedError(Exception):
    """
    Exception raised when agent execution is interrupted.

    Raised when an interrupt is detected during autonomous loop execution.
    Contains the interrupt reason for debugging and recovery.
    """

    def __init__(self, message: str, reason: InterruptReason | None = None):
        super().__init__(message)
        self.reason = reason


# Export all public types
__all__ = [
    "InterruptMode",
    "InterruptSource",
    "InterruptReason",
    "InterruptStatus",
    "InterruptedError",
]
