"""
Kaizen Runtime Abstraction Layer

Provides a unified interface for multiple autonomous agent runtimes
(Claude Code, OpenAI Codex, Gemini CLI, Kaizen Native).

Key Components:
- RuntimeAdapter: Abstract interface for runtime implementations
- RuntimeCapabilities: Describes what a runtime can do
- ExecutionContext: Normalized input for task execution
- ExecutionResult: Normalized output from execution
- RuntimeSelector: Intelligent runtime selection

Example:
    >>> from kaizen.runtime import (
    ...     get_runtime,
    ...     RuntimeSelector,
    ...     ExecutionContext,
    ...     SelectionStrategy,
    ... )
    >>>
    >>> # Direct runtime access
    >>> adapter = get_runtime("kaizen_local")
    >>> result = await adapter.execute(
    ...     ExecutionContext(task="List files in current directory")
    ... )
    >>>
    >>> # Intelligent runtime selection
    >>> selector = RuntimeSelector(get_all_runtimes())
    >>> adapter = selector.select(context, SelectionStrategy.COST_OPTIMIZED)
"""

from typing import Dict, Optional

from kaizen.runtime.adapter import BaseRuntimeAdapter, ProgressCallback, RuntimeAdapter
from kaizen.runtime.capabilities import (
    CLAUDE_CODE_CAPABILITIES,
    GEMINI_CLI_CAPABILITIES,
    KAIZEN_LOCAL_CAPABILITIES,
    OPENAI_CODEX_CAPABILITIES,
    RuntimeCapabilities,
)
from kaizen.runtime.context import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ToolCallRecord,
)
from kaizen.runtime.selector import RuntimeSelector, SelectionStrategy

# Specialist System (ADR-013)
from kaizen.runtime.specialist_loader import SpecialistLoader
from kaizen.runtime.specialist_registry import SkillRegistry, SpecialistRegistry

# Global registry of runtime adapters
_runtime_registry: Dict[str, RuntimeAdapter] = {}
_default_runtime: str = "kaizen_local"


def register_runtime(name: str, adapter: RuntimeAdapter) -> None:
    """Register a runtime adapter in the global registry.

    Args:
        name: Unique name for this runtime
        adapter: RuntimeAdapter instance

    Raises:
        TypeError: If adapter is not a RuntimeAdapter instance
    """
    if not isinstance(adapter, RuntimeAdapter):
        raise TypeError(f"Expected RuntimeAdapter, got {type(adapter).__name__}")

    _runtime_registry[name] = adapter


def unregister_runtime(name: str) -> bool:
    """Remove a runtime from the registry.

    Args:
        name: Name of runtime to remove

    Returns:
        True if runtime was removed, False if not found
    """
    if name in _runtime_registry:
        del _runtime_registry[name]
        return True
    return False


def get_runtime(name: str) -> Optional[RuntimeAdapter]:
    """Get a runtime adapter by name.

    Args:
        name: Name of the runtime

    Returns:
        RuntimeAdapter instance or None if not found
    """
    return _runtime_registry.get(name)


def get_all_runtimes() -> Dict[str, RuntimeAdapter]:
    """Get all registered runtime adapters.

    Returns:
        Dictionary mapping names to adapters
    """
    return dict(_runtime_registry)


def list_runtimes() -> list:
    """List all registered runtime names.

    Returns:
        List of runtime names
    """
    return list(_runtime_registry.keys())


def set_default_runtime(name: str) -> None:
    """Set the default runtime.

    Args:
        name: Name of runtime to use as default

    Raises:
        ValueError: If runtime is not registered
    """
    global _default_runtime
    if name not in _runtime_registry:
        raise ValueError(f"Runtime '{name}' not registered")
    _default_runtime = name


def get_default_runtime() -> Optional[RuntimeAdapter]:
    """Get the default runtime adapter.

    Returns:
        Default RuntimeAdapter or None if not set
    """
    return _runtime_registry.get(_default_runtime)


def create_selector() -> RuntimeSelector:
    """Create a RuntimeSelector with all registered runtimes.

    Returns:
        RuntimeSelector configured with current registry
    """
    return RuntimeSelector(
        runtimes=get_all_runtimes(),
        default_runtime=_default_runtime,
    )


# Public exports
__all__ = [
    # Core types
    "RuntimeAdapter",
    "BaseRuntimeAdapter",
    "RuntimeCapabilities",
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionStatus",
    "ToolCallRecord",
    "ProgressCallback",
    # Selection
    "RuntimeSelector",
    "SelectionStrategy",
    # Specialist System (ADR-013)
    "SpecialistRegistry",
    "SkillRegistry",
    "SpecialistLoader",
    # Registry functions
    "register_runtime",
    "unregister_runtime",
    "get_runtime",
    "get_all_runtimes",
    "list_runtimes",
    "set_default_runtime",
    "get_default_runtime",
    "create_selector",
    # Pre-defined capabilities
    "KAIZEN_LOCAL_CAPABILITIES",
    "CLAUDE_CODE_CAPABILITIES",
    "OPENAI_CODEX_CAPABILITIES",
    "GEMINI_CLI_CAPABILITIES",
]
