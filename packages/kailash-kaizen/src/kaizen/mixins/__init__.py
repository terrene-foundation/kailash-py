"""
Kaizen Agent Mixins.

This package provides mixin classes for modular agent features using
the Mixin Composition pattern.

Available Mixins:
- LoggingMixin: Structured logging for agent execution
- PerformanceMixin: Performance tracking and benchmarking
- ErrorHandlingMixin: Comprehensive error handling
- BatchProcessingMixin: Batch processing for multiple inputs
- MemoryMixin: Persistent memory for agents
- TransparencyMixin: Transparency and audit features
- MCPIntegrationMixin: MCP (Model Context Protocol) integration

Usage Pattern:
    >>> from kaizen.core.base_agent import BaseAgent
    >>> from kaizen.mixins import LoggingMixin, PerformanceMixin
    >>>
    >>> class MyAgent(BaseAgent, LoggingMixin, PerformanceMixin):
    ...     def __init__(self, config):
    ...         BaseAgent.__init__(self, config)
    ...         LoggingMixin.__init__(self)
    ...         PerformanceMixin.__init__(self)

Or use BaseAgent's automatic mixin application:
    >>> config = BaseAgentConfig(
    ...     logging_enabled=True,
    ...     performance_enabled=True
    ... )
    >>> agent = BaseAgent(config=config)  # Mixins auto-applied

References:
- ADR-006: Agent Base Architecture design (Mixin Composition section)
- TODO-157: Phase 3 (Mixin System implementation)

Author: Kaizen Framework Team
Created: 2025-10-01

Notes:
- Mixins are applied conditionally based on BaseAgentConfig feature flags
- Each mixin is independent and composable
- Full implementation in Phase 3 (Tasks 3.1-3.8)
"""

from .batch_processing import BatchProcessingMixin
from .error_handling import ErrorHandlingMixin

# Import mixins (Phase 3 implementation)
from .logging import LoggingMixin
from .performance import PerformanceMixin

# from .memory import MemoryMixin
# from .transparency import TransparencyMixin
# from .mcp_integration import MCPIntegrationMixin

__all__ = [
    "LoggingMixin",
    "ErrorHandlingMixin",
    "PerformanceMixin",
    "BatchProcessingMixin",
    # "MemoryMixin",
    # "TransparencyMixin",
    # "MCPIntegrationMixin",
]

# TODO: Phase 3 (Tasks 3.1-3.8) - Implement mixins
# Task 3.1: LoggingMixin
# Task 3.2: PerformanceMixin
# Task 3.3: ErrorHandlingMixin
# Task 3.4: BatchProcessingMixin
# Task 3.5: MemoryMixin
# Task 3.6: TransparencyMixin
# Task 3.7: MCPIntegrationMixin
# Task 3.8: Mixin composition tests
