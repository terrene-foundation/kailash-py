"""
MetricsCollector: Lightweight metric collection with <1ms overhead.

This module provides a singleton MetricsCollector that records metrics
with minimal performance impact using async queues and sampling.
"""

import asyncio
import functools
import logging
import random
import threading
import time
from contextlib import contextmanager
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Lightweight metrics collection with <1ms overhead.

    Singleton pattern ensures single collector per process.
    Thread-safe for concurrent access.

    Features:
    - Async metric recording (non-blocking)
    - Configurable sampling rates
    - Fail-safe (errors don't crash application)
    - Decorators and context managers for easy instrumentation
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._metrics_queue = asyncio.Queue(maxsize=10000)
        self._sample_rates = {
            "signature.resolution": 1.0,  # 100% sampling
            "cache.access": 1.0,  # 100% sampling
            "strategy.execution": 1.0,  # 100% sampling
            "workflow.node": 0.1,  # 10% sampling (high volume)
            "memory.allocation": 0.01,  # 1% sampling (very high volume)
        }
        self._initialized = True

    async def record_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None,
    ):
        """
        Record a metric with tags and timestamp.

        Args:
            metric_name: Name of the metric (e.g., 'signature.resolution.latency')
            value: Metric value
            tags: Optional tags for the metric
            timestamp: Optional timestamp (defaults to current time)
        """
        # Check sampling rate
        sample_rate = self._get_sample_rate(metric_name)
        if random.random() > sample_rate:
            return  # Skip this sample

        metric = {
            "name": metric_name,
            "value": value,
            "tags": tags or {},
            "timestamp": timestamp or time.time(),
            "sampled": sample_rate < 1.0,
            "sample_rate": sample_rate,
        }

        # Non-blocking queue put
        try:
            self._metrics_queue.put_nowait(metric)
        except asyncio.QueueFull:
            # Drop metric if queue full (fail-safe)
            logger.warning(f"Metrics queue full, dropping metric: {metric_name}")

    def _get_sample_rate(self, metric_name: str) -> float:
        """Get sampling rate for metric (supports prefix matching)."""
        # Try exact match first
        if metric_name in self._sample_rates:
            return self._sample_rates[metric_name]

        # Try prefix match (e.g., 'signature.resolution.latency' matches 'signature.resolution')
        for prefix, rate in self._sample_rates.items():
            if metric_name.startswith(prefix):
                return rate

        # Default to 100% sampling
        return 1.0

    def monitor_execution(
        self, operation_name: str, tags: Optional[Dict[str, str]] = None
    ):
        """
        Decorator for monitoring function execution time.

        Args:
            operation_name: Name of the operation being monitored
            tags: Optional tags to attach to the metric

        Returns:
            Decorator function

        Example:
            @collector.monitor_execution('signature.parse')
            async def parse(self, signature_def: str):
                # ... implementation ...
        """

        def decorator(func: Callable) -> Callable:
            if asyncio.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    start = time.perf_counter()
                    success = True
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except Exception:
                        success = False
                        raise
                    finally:
                        elapsed_ms = (time.perf_counter() - start) * 1000
                        await self.record_metric(
                            f"{operation_name}.latency",
                            elapsed_ms,
                            tags={**(tags or {}), "success": str(success)},
                        )

                return async_wrapper
            else:

                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    start = time.perf_counter()
                    success = True
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except Exception:
                        success = False
                        raise
                    finally:
                        elapsed_ms = (time.perf_counter() - start) * 1000
                        # Schedule async recording in background
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(
                                    self.record_metric(
                                        f"{operation_name}.latency",
                                        elapsed_ms,
                                        tags={**(tags or {}), "success": str(success)},
                                    )
                                )
                        except RuntimeError:
                            # No event loop running, skip metric recording
                            pass

                return sync_wrapper

        return decorator

    @contextmanager
    def monitor_operation(
        self, operation_name: str, tags: Optional[Dict[str, str]] = None
    ):
        """
        Context manager for monitoring operation duration.

        Args:
            operation_name: Name of the operation being monitored
            tags: Optional tags to attach to the metric

        Example:
            with collector.monitor_operation('agent.execution', tags={'agent_type': 'QA'}):
                # ... operation ...
        """
        start = time.perf_counter()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            # Schedule async recording in background
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        self.record_metric(
                            f"{operation_name}.latency",
                            elapsed_ms,
                            tags={**(tags or {}), "success": str(success)},
                        )
                    )
            except RuntimeError:
                # No event loop running, skip metric recording
                pass

    def set_sample_rate(self, metric_pattern: str, rate: float):
        """
        Set sampling rate for a metric pattern.

        Args:
            metric_pattern: Metric name or prefix pattern
            rate: Sampling rate between 0.0 and 1.0
        """
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"Sample rate must be between 0.0 and 1.0, got {rate}")

        self._sample_rates[metric_pattern] = rate

    def get_queue_size(self) -> int:
        """Get current metrics queue size."""
        return self._metrics_queue.qsize()

    def is_queue_full(self) -> bool:
        """Check if metrics queue is full."""
        return self._metrics_queue.full()
