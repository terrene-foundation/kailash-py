"""
Kaizen Execution Strategies.

This package provides execution strategies for Kaizen agents using the
Strategy Pattern to enable pluggable execution logic.

Available Strategies:
- ExecutionStrategy: Base protocol defining the strategy interface
- SingleShotStrategy: One-pass execution (Q&A, Chain-of-Thought)
- MultiCycleStrategy: Multi-cycle execution (ReAct, iterative agents)

Convergence Strategies (Phase 3 Group 1):
- ConvergenceStrategy: Base class for convergence logic
- TestDrivenConvergence: Stop when all tests pass
- SatisfactionConvergence: Stop when confidence threshold met
- HybridConvergence: Compose multiple convergence strategies (AND/OR)

New Execution Strategies (Phase 3 Group 2):
- StreamingStrategy: Real-time token streaming for chat/interactive use cases
- ParallelBatchStrategy: Concurrent batch processing for high-throughput
- FallbackStrategy: Sequential fallback with progressive degradation
- HumanInLoopStrategy: Human approval checkpoints for critical decisions

References:
- ADR-006: Agent Base Architecture design (Strategy Pattern section)
- TODO-157: Phase 2 (Strategy Pattern implementation)
- TODO-157: Phase 3 (Convergence Strategy refactoring)

Author: Kaizen Framework Team
Created: 2025-10-01
Updated: 2025-10-02 (Phase 3 Group 1: Convergence Strategies)
Updated: 2025-10-02 (Phase 3 Group 2: New Execution Strategies)
"""

# Import base strategy protocol
from .base_strategy import ExecutionStrategy

# Import convergence strategies (Phase 3 Group 1)
from .convergence import (
    ConvergenceStrategy,
    HybridConvergence,
    SatisfactionConvergence,
    TestDrivenConvergence,
)
from .fallback import FallbackStrategy
from .human_in_loop import HumanInLoopStrategy
from .multi_cycle import MultiCycleStrategy
from .parallel_batch import ParallelBatchStrategy

# Import concrete execution strategies
from .single_shot import SingleShotStrategy

# Import new execution strategies (Phase 3 Group 2)
from .streaming import StreamingStrategy

__all__ = [
    # Execution Strategies
    "ExecutionStrategy",
    "SingleShotStrategy",
    "MultiCycleStrategy",
    # Convergence Strategies
    "ConvergenceStrategy",
    "TestDrivenConvergence",
    "SatisfactionConvergence",
    "HybridConvergence",
    # New Execution Strategies (Phase 3 Group 2)
    "StreamingStrategy",
    "ParallelBatchStrategy",
    "FallbackStrategy",
    "HumanInLoopStrategy",
]
