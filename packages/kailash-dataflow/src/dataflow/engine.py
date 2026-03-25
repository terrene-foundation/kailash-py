# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DataFlowEngine — unified database engine with builder pattern.

Wraps the DataFlow primitive with validation layers, data classification
policies, query performance monitoring, and a fluent builder API. Matches
the kailash-rs DataFlowEngine API surface for cross-SDK parity.

Usage:
    from dataflow import DataFlowEngine

    # Zero-config (SQLite)
    engine = await DataFlowEngine.builder("sqlite:///app.db").build()

    # PostgreSQL with validation and classification
    engine = await (
        DataFlowEngine.builder("postgresql://localhost/mydb")
        .slow_query_threshold(0.5)
        .validation(my_validation_layer)
        .classification_policy(my_policy)
        .build()
    )

    # Register models and use
    engine.register_model(registry, UserModel)
    health = await engine.health_check()
    await engine.close()
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from dataflow.core.engine import DataFlow

logger = logging.getLogger(__name__)


@runtime_checkable
class ValidationLayer(Protocol):
    """Protocol for field-level validation on DataFlow operations."""

    def validate(self, model_name: str, field_name: str, value: Any) -> bool:
        """Validate a field value. Returns True if valid."""
        ...

    def get_errors(self) -> List[str]:
        """Get validation error messages from the last validate call."""
        ...


@runtime_checkable
class DataClassificationPolicy(Protocol):
    """Protocol for data classification and retention policies."""

    def classify(self, model_name: str, field_name: str) -> str:
        """Classify a field. Returns classification level (e.g., 'PII', 'INTERNAL')."""
        ...

    def get_retention_days(self, classification: str) -> Optional[int]:
        """Get retention period in days for a classification level."""
        ...


@dataclass
class QueryStats:
    """Statistics for a single query execution."""

    sql: str
    duration_ms: float
    timestamp: float
    is_slow: bool = False


@dataclass
class HealthStatus:
    """Health check result for the DataFlow engine."""

    healthy: bool
    database_connected: bool
    pool_size: int = 0
    active_connections: int = 0
    slow_queries_last_hour: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


class QueryEngine:
    """Query performance monitoring engine.

    Tracks query execution times, detects slow queries, and provides
    performance metrics. Matches kailash-rs QueryEngine.
    """

    def __init__(self, slow_query_threshold: float = 1.0) -> None:
        self._slow_query_threshold = slow_query_threshold
        self._query_log: deque[QueryStats] = deque(maxlen=10000)

    @property
    def slow_query_threshold(self) -> float:
        """Get the slow query threshold in seconds."""
        return self._slow_query_threshold

    def record(self, sql: str, duration_ms: float) -> QueryStats:
        """Record a query execution."""
        stats = QueryStats(
            sql=sql,
            duration_ms=duration_ms,
            timestamp=time.time(),
            is_slow=duration_ms / 1000.0 > self._slow_query_threshold,
        )
        self._query_log.append(stats)
        if stats.is_slow:
            logger.warning(
                "Slow query detected (%.1fms > %.1fs threshold): %s",
                duration_ms,
                self._slow_query_threshold,
                sql[:200],
            )
        return stats

    def slow_queries(self, last_n_seconds: float = 3600.0) -> List[QueryStats]:
        """Get slow queries from the last N seconds."""
        cutoff = time.time() - last_n_seconds
        return [q for q in self._query_log if q.is_slow and q.timestamp > cutoff]

    def stats(self) -> Dict[str, Any]:
        """Get aggregate query statistics."""
        if not self._query_log:
            return {"total_queries": 0, "slow_queries": 0, "avg_ms": 0.0}
        durations = [q.duration_ms for q in self._query_log]
        return {
            "total_queries": len(self._query_log),
            "slow_queries": sum(1 for q in self._query_log if q.is_slow),
            "avg_ms": sum(durations) / len(durations),
            "p95_ms": (
                sorted(durations)[int(len(durations) * 0.95)] if durations else 0.0
            ),
            "max_ms": max(durations),
        }


class DataFlowEngineBuilder:
    """Fluent builder for DataFlowEngine. Matches kailash-rs DataFlowEngineBuilder API."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._validation: Optional[ValidationLayer] = None
        self._classification: Optional[DataClassificationPolicy] = None
        self._slow_query_threshold: float = 1.0
        self._dataflow_kwargs: Dict[str, Any] = {}

    def validation(self, layer: ValidationLayer) -> DataFlowEngineBuilder:
        """Set a validation layer for field-level validation."""
        self._validation = layer
        return self

    def classification_policy(
        self, policy: DataClassificationPolicy
    ) -> DataFlowEngineBuilder:
        """Set a data classification policy."""
        self._classification = policy
        return self

    def slow_query_threshold(self, seconds: float) -> DataFlowEngineBuilder:
        """Set the slow query detection threshold in seconds (default: 1.0)."""
        self._slow_query_threshold = seconds
        return self

    def config(self, **kwargs: Any) -> DataFlowEngineBuilder:
        """Pass additional configuration to the underlying DataFlow instance."""
        self._dataflow_kwargs.update(kwargs)
        return self

    async def build(self) -> DataFlowEngine:
        """Build the DataFlowEngine instance (async — connects to database)."""
        dataflow = DataFlow(
            database_url=self._database_url,
            slow_query_threshold=self._slow_query_threshold,
            **self._dataflow_kwargs,
        )

        query_engine = QueryEngine(slow_query_threshold=self._slow_query_threshold)

        return DataFlowEngine(
            dataflow=dataflow,
            validation=self._validation,
            classification=self._classification,
            query_engine=query_engine,
        )


class DataFlowEngine:
    """Unified database engine wrapping DataFlow with enterprise features.

    Provides a builder-pattern API matching kailash-rs DataFlowEngine for
    cross-SDK parity. Wraps the DataFlow primitive with validation,
    classification, and query performance monitoring.

    Use DataFlowEngine.builder(url) to create instances.
    """

    def __init__(
        self,
        dataflow: DataFlow,
        validation: Optional[ValidationLayer] = None,
        classification: Optional[DataClassificationPolicy] = None,
        query_engine: Optional[QueryEngine] = None,
    ) -> None:
        self._dataflow = dataflow
        self._validation = validation
        self._classification = classification
        self._query_engine = query_engine or QueryEngine()

    @staticmethod
    def builder(database_url: str) -> DataFlowEngineBuilder:
        """Create a new DataFlowEngine builder."""
        return DataFlowEngineBuilder(database_url)

    @property
    def dataflow(self) -> DataFlow:
        """Read-only access to the underlying DataFlow instance."""
        return self._dataflow

    @property
    def query_engine(self) -> QueryEngine:
        """Get the query performance monitoring engine."""
        return self._query_engine

    @property
    def validation(self) -> Optional[ValidationLayer]:
        """Get the validation layer, if set."""
        return self._validation

    @property
    def classification(self) -> Optional[DataClassificationPolicy]:
        """Get the data classification policy, if set."""
        return self._classification

    def register_model(self, registry: Any, model: Any) -> None:
        """Register a model and generate its CRUD nodes.

        Delegates to DataFlow's model registration which auto-generates
        11 workflow nodes per SQL model.
        """
        self._dataflow.register_model(model)

    async def health_check(self) -> HealthStatus:
        """Check database connection health."""
        try:
            connected = self._dataflow._engine is not None
            slow_count = len(self._query_engine.slow_queries(3600.0))
            return HealthStatus(
                healthy=connected,
                database_connected=connected,
                slow_queries_last_hour=slow_count,
                details=self._query_engine.stats(),
            )
        except Exception as e:
            return HealthStatus(
                healthy=False,
                database_connected=False,
                details={"error": str(e)},
            )

    async def close(self) -> None:
        """Close the DataFlow engine and release database connections."""
        if hasattr(self._dataflow, "close"):
            self._dataflow.close()
