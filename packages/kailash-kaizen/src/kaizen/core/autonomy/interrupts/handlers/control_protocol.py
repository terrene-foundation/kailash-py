"""
Control Protocol interrupt handler.

Allows API/programmatic interrupt requests via Control Protocol.
"""

import logging
from typing import Any

from ..manager import InterruptManager
from ..types import InterruptMode, InterruptSource

logger = logging.getLogger(__name__)


class ControlProtocolInterruptHandler:
    """
    Handle programmatic interrupt requests via API.

    Allows external systems to request interrupts through Control Protocol.
    """

    def __init__(
        self,
        interrupt_manager: InterruptManager,
        default_mode: InterruptMode = InterruptMode.GRACEFUL,
    ):
        """
        Initialize control protocol handler.

        Args:
            interrupt_manager: InterruptManager to trigger interrupts
            default_mode: Default interrupt mode (GRACEFUL or IMMEDIATE)
        """
        self.interrupt_manager = interrupt_manager
        self.default_mode = default_mode

    def request_interrupt(
        self,
        message: str,
        mode: InterruptMode | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Request interrupt from external system.

        Args:
            message: Reason for interrupt
            mode: Interrupt mode (defaults to handler's default_mode)
            metadata: Additional interrupt metadata
        """
        actual_mode = mode or self.default_mode

        logger.info(f"API interrupt requested: {message} (mode: {actual_mode.value})")

        self.interrupt_manager.request_interrupt(
            mode=actual_mode,
            source=InterruptSource.USER,  # API requests are user-initiated
            message=message,
            metadata=metadata or {},
        )


# Export all public types
__all__ = [
    "ControlProtocolInterruptHandler",
]
