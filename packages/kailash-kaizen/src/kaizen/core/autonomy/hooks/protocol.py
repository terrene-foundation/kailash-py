"""
Hook handler protocol and base implementation.

Defines the interface for hook handlers and provides a convenient base class.
"""

from abc import abstractmethod
from typing import Protocol, runtime_checkable

from .types import HookContext, HookResult


@runtime_checkable
class HookHandler(Protocol):
    """Protocol for hook handlers (must be async)"""

    @abstractmethod
    async def handle(self, context: HookContext) -> HookResult:
        """
        Handle hook event.

        Args:
            context: Hook execution context with event type and data

        Returns:
            HookResult indicating success/failure and optional data

        Raises:
            Exception: Any exception will be caught by HookManager
        """
        ...


class BaseHook:
    """
    Base class for hook implementations.

    Provides common functionality and error handling for hooks.
    """

    def __init__(self, name: str):
        """
        Initialize hook with a name.

        Args:
            name: Unique identifier for this hook (used in logging/stats)
        """
        self.name = name

    async def handle(self, context: HookContext) -> HookResult:
        """
        Handle hook event. Override this in subclasses.

        Args:
            context: Hook execution context

        Returns:
            HookResult with success status and optional data

        Raises:
            NotImplementedError: If not overridden in subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.handle() must be implemented"
        )

    async def on_error(self, error: Exception, context: HookContext) -> None:
        """
        Optional error handler called when handle() raises an exception.

        Override this to implement custom error handling (logging, notifications, etc.)

        Args:
            error: The exception that was raised
            context: The hook context that caused the error
        """
        pass

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}(name={self.name!r})"


# Export all public types
__all__ = [
    "HookHandler",
    "BaseHook",
]
