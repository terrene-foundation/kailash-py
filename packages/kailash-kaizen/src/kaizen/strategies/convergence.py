"""
Convergence Strategies for Multi-Cycle Execution.

This module provides abstract and concrete convergence strategies for
determining when iterative execution should stop.

Use Cases:
- Test-driven development (stop when tests pass)
- Satisfaction threshold (stop when confidence met)
- Hybrid approaches (combine multiple strategies)

References:
- TODO-157: Phase 3 Tasks 3S.2-3S.5 (Convergence Strategies)
- ADR-006: Agent Base Architecture (Strategy Pattern)

Author: Kaizen Framework Team
Created: 2025-10-02
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ConvergenceStrategy(ABC):
    """
    Abstract base class for convergence strategies.

    Convergence strategies determine when iterative execution should stop
    by analyzing execution results and reflection data.

    Methods:
        should_stop: Determine if execution should terminate (abstract)
        get_reason: Return reason for stopping (optional override)

    Example:
        >>> class SimpleConvergence(ConvergenceStrategy):
        ...     def should_stop(self, result, reflection):
        ...         return result.get('confidence', 0) >= 0.9
        ...
        >>> strategy = SimpleConvergence()
        >>> should_stop = strategy.should_stop({'confidence': 0.95}, {})
        >>> print(should_stop)
        True

    Notes:
        - Subclasses MUST implement should_stop method
        - get_reason has default implementation but can be overridden
        - Part of Phase 3 convergence strategy refactoring
    """

    @abstractmethod
    def should_stop(self, result: Dict[str, Any], reflection: Dict[str, Any]) -> bool:
        """
        Determine if iterative execution should stop.

        Args:
            result: Latest execution result with output data
            reflection: Reflection on result quality/metrics

        Returns:
            bool: True if execution should stop (converged), False to continue

        Example:
            >>> strategy.should_stop(
            ...     {'answer': '42', 'confidence': 0.95},
            ...     {'quality_score': 0.9}
            ... )
            True
        """
        pass

    def get_reason(self) -> str:
        """
        Get reason for stopping (optional override).

        Returns:
            str: Human-readable reason for convergence

        Example:
            >>> strategy.get_reason()
            'Convergence achieved'
        """
        return "Convergence achieved"


class TestDrivenConvergence(ConvergenceStrategy):
    """
    Test-driven convergence strategy.

    Stops execution when all tests pass (failed count == 0).

    Args:
        test_suite: Callable that runs tests and returns (passed, failed) tuple

    Example:
        >>> def my_tests(result):
        ...     # Run tests on result
        ...     code = result.get('code', '')
        ...     # Simple test: check if code contains 'def'
        ...     passed = 1 if 'def' in code else 0
        ...     failed = 0 if 'def' in code else 1
        ...     return (passed, failed)
        ...
        >>> strategy = TestDrivenConvergence(test_suite=my_tests)
        >>> should_stop = strategy.should_stop({'code': 'def foo(): pass'}, {})
        >>> print(should_stop)
        True

    Notes:
        - Converges when failed == 0
        - Tracks last test results for reporting
        - Part of Phase 3 convergence strategy implementation
    """

    def __init__(self, test_suite: callable):
        """
        Initialize test-driven convergence.

        Args:
            test_suite: Callable that runs tests and returns (passed, failed)
        """
        self.test_suite = test_suite
        self.last_results = None

    def should_stop(self, result: Dict[str, Any], reflection: Dict[str, Any]) -> bool:
        """
        Stop when all tests pass.

        Args:
            result: Latest execution result
            reflection: Reflection on result quality

        Returns:
            bool: True if all tests pass (failed == 0), False otherwise
        """
        passed, failed = self.test_suite(result)
        self.last_results = (passed, failed)
        return failed == 0

    def get_reason(self) -> str:
        """
        Get reason for stopping with test counts.

        Returns:
            str: Reason with test pass count
        """
        if self.last_results:
            passed, failed = self.last_results
            return f"All {passed} tests passed"
        return "Test-driven convergence"


class SatisfactionConvergence(ConvergenceStrategy):
    """
    Satisfaction/confidence-based convergence strategy.

    Stops execution when confidence threshold is met.

    Args:
        confidence_threshold: Minimum confidence to stop (0.0-1.0, default: 0.9)

    Example:
        >>> strategy = SatisfactionConvergence(confidence_threshold=0.85)
        >>> should_stop = strategy.should_stop({'confidence': 0.9}, {})
        >>> print(should_stop)
        True

    Notes:
        - Converges when confidence >= threshold
        - Tracks last confidence value for reporting
        - Missing confidence key defaults to 0.0
        - Part of Phase 3 convergence strategy implementation
    """

    def __init__(self, confidence_threshold: float = 0.9):
        """
        Initialize satisfaction-based convergence.

        Args:
            confidence_threshold: Minimum confidence to stop (0.0-1.0)
        """
        self.threshold = confidence_threshold
        self.last_confidence = None

    def should_stop(self, result: Dict[str, Any], reflection: Dict[str, Any]) -> bool:
        """
        Stop when confidence >= threshold.

        Args:
            result: Latest execution result with confidence score
            reflection: Reflection on result quality

        Returns:
            bool: True if confidence >= threshold, False otherwise
        """
        self.last_confidence = result.get("confidence", 0.0)
        return self.last_confidence >= self.threshold

    def get_reason(self) -> str:
        """
        Get reason for stopping with confidence values.

        Returns:
            str: Reason with confidence and threshold
        """
        if self.last_confidence is not None:
            return f"Confidence {self.last_confidence:.2f} >= {self.threshold:.2f}"
        return "Satisfaction threshold met"


class HybridConvergence(ConvergenceStrategy):
    """
    Hybrid convergence strategy composing multiple strategies.

    Combines multiple convergence strategies using AND/OR logic.

    Args:
        strategies: List of ConvergenceStrategy instances to compose
        mode: "AND" (all must converge) or "OR" (any can converge), default: "AND"

    Example:
        >>> test_driven = TestDrivenConvergence(test_suite=my_tests)
        >>> satisfaction = SatisfactionConvergence(confidence_threshold=0.9)
        >>> hybrid = HybridConvergence(
        ...     strategies=[test_driven, satisfaction],
        ...     mode="AND"
        ... )
        >>> # Converges when both tests pass AND confidence >= 0.9
        >>> should_stop = hybrid.should_stop({'confidence': 0.95, 'code': 'valid'}, {})

    Notes:
        - AND mode: all([strategy.should_stop(...) for strategy in strategies])
        - OR mode: any([strategy.should_stop(...) for strategy in strategies])
        - Tracks individual strategy results
        - Part of Phase 3 convergence strategy implementation
    """

    def __init__(self, strategies: List[ConvergenceStrategy], mode: str = "AND"):
        """
        Initialize hybrid convergence.

        Args:
            strategies: List of convergence strategies to compose
            mode: "AND" (all must converge) or "OR" (any can converge)
        """
        self.strategies = strategies
        self.mode = mode.upper()
        self.last_results = []

    def should_stop(self, result: Dict[str, Any], reflection: Dict[str, Any]) -> bool:
        """
        Compose multiple strategies with AND/OR logic.

        Args:
            result: Latest execution result
            reflection: Reflection on result quality

        Returns:
            bool: True if convergence condition met, False otherwise
        """
        self.last_results = [s.should_stop(result, reflection) for s in self.strategies]

        if self.mode == "AND":
            return all(self.last_results)  # All must converge
        else:  # OR (or any invalid mode defaults to AND behavior, but we'll use OR)
            # Actually, let's make invalid modes default to AND for safety
            if self.mode == "OR":
                return any(self.last_results)  # Any can converge
            else:
                # Invalid mode - default to AND
                return all(self.last_results)

    def get_reason(self) -> str:
        """
        Get reason for stopping with convergence counts.

        Returns:
            str: Reason with strategy convergence count
        """
        if self.last_results:
            count = sum(self.last_results)
            return f"{count}/{len(self.strategies)} strategies converged ({self.mode} mode)"
        return "Hybrid convergence"
