"""Runtime mixins for shared functionality.

This module provides mixins that encapsulate shared logic between
synchronous (LocalRuntime) and asynchronous (AsyncLocalRuntime) runtimes.

Available Mixins:
    - ValidationMixin: Workflow, node, and connection validation logic
    - ParameterHandlingMixin: Parameter resolution and template handling
    - ConditionalExecutionMixin: Conditional workflow execution and branching logic
    - CycleExecutionMixin: Cyclic workflow execution delegation to CyclicWorkflowExecutor

Design Pattern:
    These mixins follow the SecureGovernedNode pattern for composition:
    - Each mixin is 100% shared logic (no sync/async variants)
    - Mixins are stateless or use super().__init__() for initialization
    - Can be composed via multiple inheritance with proper MRO

Usage:
    from kailash.runtime.mixins import (
        ValidationMixin,
        ParameterHandlingMixin,
        ConditionalExecutionMixin,
        CycleExecutionMixin
    )

    class LocalRuntime(
        BaseRuntime,
        ValidationMixin,
        ParameterHandlingMixin,
        ConditionalExecutionMixin,
        CycleExecutionMixin
    ):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Inherits all validation, parameter handling, conditional execution,
            # and cycle execution

Version:
    Added in: v0.10.0
    Part of: Runtime parity remediation (Phase 1 + Phase 2 + Phase 3)
"""

from kailash.runtime.mixins.conditional_execution import ConditionalExecutionMixin
from kailash.runtime.mixins.cycle_execution import CycleExecutionMixin
from kailash.runtime.mixins.parameters import ParameterHandlingMixin
from kailash.runtime.mixins.validation import ValidationMixin

__all__ = [
    "ConditionalExecutionMixin",
    "CycleExecutionMixin",
    "ParameterHandlingMixin",
    "ValidationMixin",
]
