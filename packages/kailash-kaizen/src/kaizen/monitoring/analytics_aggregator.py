"""
AnalyticsAggregator: Real-time metrics aggregation with windowed statistics.

This module processes raw metrics from MetricsCollector and produces
percentile distributions, rates, trends, and anomalies.
"""

import asyncio
import logging
import statistics
import threading
import time
from typing import Any, Dict, List, Tuple

from .metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class TimeWindow:
    """Rolling time window for metric samples."""

    def __init__(self, duration_seconds: int):
        """
        Initialize time window.

        Args:
            duration_seconds: Window duration in seconds
        """
        self.duration_seconds = duration_seconds
        self._samples: Dict[str, List[Tuple[float, float]]] = (
            {}
        )  # metric -> [(timestamp, value)]
        self._lock = threading.RLock()

    def add_sample(self, metric_name: str, value: float, tags: Dict, timestamp: float):
        """
        Add sample to window.

        Args:
            metric_name: Name of the metric
            value: Metric value
            tags: Metric tags (not currently used, for future filtering)
            timestamp: Sample timestamp
        """
        with self._lock:
            if metric_name not in self._samples:
                self._samples[metric_name] = []

            # Add sample with timestamp
            self._samples[metric_name].append((timestamp, value))

            # Evict old samples
            cutoff = time.time() - self.duration_seconds
            self._samples[metric_name] = [
                (ts, val) for ts, val in self._samples[metric_name] if ts > cutoff
            ]

    def get_samples(self, metric_name: str) -> List[float]:
        """
        Get all samples for metric in window.

        Args:
            metric_name: Name of the metric

        Returns:
            List of sample values
        """
        with self._lock:
            return [val for _, val in self._samples.get(metric_name, [])]

    def get_metric_names(self) -> List[str]:
        """
        Get all metric names in window.

        Returns:
            List of metric names
        """
        with self._lock:
            return list(self._samples.keys())


class AnalyticsAggregator:
    """
    Real-time metrics aggregation with windowed statistics.

    Consumes metrics from MetricsCollector queue and produces:
    - Percentile distributions (p50, p90, p95, p99)
    - Rate calculations (ops/sec, errors/sec)
    - Trend detection (moving averages)
    - Anomaly detection (outliers)
    """

    def __init__(self, collector: MetricsCollector):
        """
        Initialize aggregator.

        Args:
            collector: MetricsCollector instance to consume metrics from
        """
        self.collector = collector
        self._windows = {
            "1s": TimeWindow(1),
            "1m": TimeWindow(60),
            "5m": TimeWindow(300),
            "1h": TimeWindow(3600),
        }
        self._aggregated_stats: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._worker_task = None

    async def start(self):
        """Start aggregation worker."""
        self._running = True
        self._worker_task = asyncio.create_task(self._aggregation_worker())

    async def stop(self):
        """Stop aggregation worker."""
        self._running = False
        if self._worker_task:
            await self._worker_task

    async def _aggregation_worker(self):
        """Background worker for continuous aggregation."""
        while self._running:
            try:
                # Process metrics from queue (batch of 100)
                metrics = []
                for _ in range(100):
                    try:
                        metric = await asyncio.wait_for(
                            self.collector._metrics_queue.get(), timeout=0.1
                        )
                        metrics.append(metric)
                    except asyncio.TimeoutError:
                        break

                if metrics:
                    await self._process_metrics_batch(metrics)

            except Exception as e:
                logger.error(f"Aggregation worker error: {e}")
                await asyncio.sleep(1)

    async def _process_metrics_batch(self, metrics: List[Dict]):
        """
        Process batch of metrics.

        Args:
            metrics: List of metric dictionaries
        """
        for metric in metrics:
            metric_name = metric["name"]
            value = metric["value"]
            tags = metric["tags"]
            timestamp = metric["timestamp"]

            # Add to all time windows
            for window in self._windows.values():
                window.add_sample(metric_name, value, tags, timestamp)

        # Calculate aggregated statistics
        await self._calculate_stats()

    async def _calculate_stats(self):
        """Calculate aggregated statistics from time windows."""
        for window_name, window in self._windows.items():
            for metric_name in window.get_metric_names():
                samples = window.get_samples(metric_name)

                if samples:
                    self._aggregated_stats[f"{metric_name}.{window_name}"] = {
                        "count": len(samples),
                        "mean": statistics.mean(samples),
                        "median": statistics.median(samples),
                        "p90": self._percentile(samples, 0.90),
                        "p95": self._percentile(samples, 0.95),
                        "p99": self._percentile(samples, 0.99),
                        "min": min(samples),
                        "max": max(samples),
                        "stddev": statistics.stdev(samples) if len(samples) > 1 else 0,
                        "samples": samples,  # Keep samples for visualization
                    }

    def get_stats(self, metric_name: str, window: str = "1m") -> Dict[str, float]:
        """
        Get aggregated statistics for a metric.

        Args:
            metric_name: Name of the metric
            window: Time window ('1s', '1m', '5m', '1h')

        Returns:
            Dictionary of statistics (count, mean, median, percentiles, etc.)
        """
        key = f"{metric_name}.{window}"
        return self._aggregated_stats.get(key, {})

    @staticmethod
    def _percentile(data: List[float], percentile: float) -> float:
        """
        Calculate percentile.

        Args:
            data: List of values
            percentile: Percentile to calculate (0.0 to 1.0)

        Returns:
            Percentile value
        """
        if not data:
            return 0.0

        sorted_data = sorted(data)
        index = int(percentile * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]

    def get_all_metrics(self, window: str = "1m") -> Dict[str, Dict[str, float]]:
        """
        Get statistics for all metrics in a window.

        Args:
            window: Time window ('1s', '1m', '5m', '1h')

        Returns:
            Dictionary mapping metric names to statistics
        """
        result = {}
        suffix = f".{window}"

        for key, stats in self._aggregated_stats.items():
            if key.endswith(suffix):
                metric_name = key[: -len(suffix)]
                result[metric_name] = stats

        return result
