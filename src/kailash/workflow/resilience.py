"""Resilience features for Kailash workflows.

This module provides resilience patterns that can be applied to any workflow,
including retry policies, fallback nodes, and circuit breakers.
"""

import asyncio
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


class RetryStrategy(Enum):
    """Retry strategies for failed nodes."""

    IMMEDIATE = "immediate"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"


@dataclass
class RetryPolicy:
    """Configuration for node retry behavior."""

    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay: float = 1.0
    max_delay: float = 60.0
    retry_on: List[type] = field(default_factory=lambda: [Exception])

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay based on retry strategy."""
        if self.strategy == RetryStrategy.IMMEDIATE:
            return 0
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** (attempt - 1))
        elif self.strategy == RetryStrategy.FIBONACCI:
            # Fibonacci sequence
            fib = [1, 1]
            for _ in range(attempt - 1):
                fib.append(fib[-1] + fib[-2])
            delay = self.base_delay * fib[min(attempt - 1, len(fib) - 1)]
        else:
            delay = self.base_delay

        return min(delay, self.max_delay)

    def to_dict(self) -> dict:
        """Convert RetryPolicy to dictionary."""
        return {
            "max_retries": self.max_retries,
            "strategy": self.strategy.value,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "retry_on": [cls.__name__ for cls in self.retry_on],
        }


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker pattern."""

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 60.0

    # Runtime state
    failures: int = 0
    successes: int = 0
    state: str = "closed"  # closed, open, half-open
    last_failure_time: Optional[float] = None

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.state == "closed":
            return False

        if self.state == "open":
            # Check if timeout has passed
            if self.last_failure_time:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.timeout:
                    # Move to half-open state
                    self.state = "half-open"
                    self.successes = 0
                    return False
            return True

        # Half-open state
        return False

    def record_success(self):
        """Record successful execution."""
        self.failures = 0
        self.successes += 1

        # Close circuit if enough successes in half-open state
        if self.state == "half-open" and self.successes >= self.success_threshold:
            self.state = "closed"

    def record_failure(self):
        """Record failed execution."""
        self.failures += 1
        self.successes = 0
        self.last_failure_time = time.time()

        # Open circuit if threshold reached
        if self.failures >= self.failure_threshold:
            self.state = "open"


class WorkflowResilience:
    """Mixin class to add resilience features to workflows."""

    def __init__(self):
        """Initialize resilience features."""
        self._fallback_nodes: Dict[str, List[Any]] = {}
        self._retry_policies: Dict[str, RetryPolicy] = {}
        self._circuit_breakers: Dict[str, CircuitBreakerConfig] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._dead_letter_queue: List[Dict[str, Any]] = []
        self._node_metrics: Dict[str, Dict[str, Any]] = {}

    def configure_retry(
        self,
        node_id: str,
        max_retries: int = 3,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        retry_on: Optional[List[type]] = None,
    ):
        """
        Configure retry policy for a specific node.

        Args:
            node_id: Node to apply policy to
            max_retries: Maximum retry attempts
            strategy: Retry delay strategy
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            retry_on: List of exception types to retry on
        """
        self._retry_policies[node_id] = RetryPolicy(
            max_retries=max_retries,
            strategy=strategy,
            base_delay=base_delay,
            max_delay=max_delay,
            retry_on=retry_on or [Exception],
        )

    def add_fallback(self, primary_node_id: str, fallback_node_id: str):
        """
        Add a fallback node for automatic failover.

        Args:
            primary_node_id: Primary node that might fail
            fallback_node_id: Fallback node to use on failure
        """
        if primary_node_id not in self._fallback_nodes:
            self._fallback_nodes[primary_node_id] = []

        self._fallback_nodes[primary_node_id].append(fallback_node_id)

    def configure_circuit_breaker(
        self,
        node_id: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
    ):
        """
        Configure circuit breaker for a node.

        Args:
            node_id: Node to protect
            failure_threshold: Failures before opening circuit
            success_threshold: Successes needed to close circuit
            timeout: Time before attempting to close circuit
        """
        self._circuit_breakers[node_id] = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
        )

    def get_resilience_metrics(self) -> Dict[str, Any]:
        """Get execution metrics for monitoring."""
        return {
            "node_metrics": self._node_metrics,
            "circuit_breakers": {
                name: {
                    "state": breaker.state,
                    "failures": breaker.failures,
                    "last_failure": breaker.last_failure_time,
                }
                for name, breaker in self._circuit_breakers.items()
            },
            "dead_letter_queue_size": len(self._dead_letter_queue),
            "retry_policies": {
                name: {
                    "max_retries": policy.max_retries,
                    "strategy": policy.strategy.value,
                }
                for name, policy in self._retry_policies.items()
            },
        }

    def get_dead_letter_queue(self) -> List[Dict[str, Any]]:
        """Get failed executions for manual intervention."""
        return self._dead_letter_queue

    def clear_dead_letter_queue(self):
        """Clear the dead letter queue after processing."""
        self._dead_letter_queue = []

    def reset_circuit_breaker(self, node_id: str):
        """Manually reset a circuit breaker."""
        if node_id in self._circuit_breakers:
            breaker = self._circuit_breakers[node_id]
            breaker.state = "closed"
            breaker.failures = 0
            breaker.successes = 0
            breaker.last_failure_time = None


def apply_resilience_to_workflow(workflow_class):
    """Decorator to add resilience features to a workflow class."""

    # Store original methods
    original_init = workflow_class.__init__

    def new_init(self, *args, **kwargs):
        # Call original init
        original_init(self, *args, **kwargs)
        # Initialize resilience attributes directly on instance
        self._fallback_nodes = {}
        self._retry_policies = {}
        self._circuit_breakers = {}
        self._execution_history = []
        self._dead_letter_queue = []
        self._node_metrics = {}

    # Add resilience methods to the class
    for attr_name in dir(WorkflowResilience):
        if not attr_name.startswith("_"):
            attr = getattr(WorkflowResilience, attr_name)
            if callable(attr) and attr_name not in ["__init__"]:
                setattr(workflow_class, attr_name, attr)

    # Override __init__
    workflow_class.__init__ = new_init

    return workflow_class
