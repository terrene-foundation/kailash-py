"""
SQLite Performance Monitor Integration

Extends the DataFlow performance monitoring system with SQLite-specific capabilities:
- Real-time SQLite performance metrics collection
- WAL file monitoring and checkpoint analysis
- Database fragmentation tracking
- Query plan analysis and optimization detection
- Index usage statistics
- Connection pool performance monitoring
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..adapters.sqlite_enterprise import (
    SQLiteConnectionPoolStats,
    SQLiteEnterpriseAdapter,
    SQLiteIndexInfo,
    SQLitePerformanceMetrics,
)
from ..migrations.migration_performance_tracker import (
    MigrationPerformanceTracker,
    PerformanceMetrics,
    RegressionAnalysis,
)

logger = logging.getLogger(__name__)


@dataclass
class SQLiteQueryMetrics:
    """Metrics for individual SQLite queries."""

    query_hash: str
    query_template: str
    execution_count: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    last_executed: str
    query_plan_steps: int
    uses_index: bool
    full_table_scans: int
    temp_btree_usage: int
    result_rows_avg: float


@dataclass
class SQLiteWALMetrics:
    """WAL-specific performance metrics."""

    wal_size_mb: float
    wal_pages: int
    checkpoint_frequency_per_hour: float
    last_checkpoint_time: str
    checkpoint_duration_ms: float
    wal_growth_rate_mb_per_hour: float
    busy_checkpoint_count: int
    successful_checkpoint_count: int


@dataclass
class SQLiteFragmentationAnalysis:
    """Database fragmentation analysis."""

    total_pages: int
    free_pages: int
    fragmentation_ratio: float
    wasted_space_mb: float
    vacuum_recommended: bool
    vacuum_estimated_duration_minutes: float
    auto_vacuum_effectiveness: float
    last_vacuum_date: Optional[str]


@dataclass
class SQLiteIndexPerformanceMetrics:
    """Index-specific performance metrics."""

    index_name: str
    table_name: str
    usage_count: int
    avg_selectivity: float
    size_mb: float
    maintenance_cost_ms: float
    last_used: Optional[str]
    effectiveness_score: float
    recommendation: str


class SQLitePerformanceMonitor:
    """
    Comprehensive SQLite performance monitoring system.

    Integrates with DataFlow's migration performance tracker to provide
    SQLite-specific monitoring capabilities including WAL analysis,
    fragmentation tracking, and index performance monitoring.
    """

    def __init__(
        self,
        adapter: SQLiteEnterpriseAdapter,
        migration_tracker: Optional[MigrationPerformanceTracker] = None,
        monitoring_interval: int = 60,  # seconds
        max_query_history: int = 1000,
        enable_continuous_monitoring: bool = True,
    ):
        """
        Initialize SQLite performance monitor.

        Args:
            adapter: SQLite enterprise adapter instance
            migration_tracker: Migration performance tracker (optional)
            monitoring_interval: Interval for continuous monitoring in seconds
            max_query_history: Maximum number of query metrics to retain
            enable_continuous_monitoring: Whether to run continuous monitoring
        """
        self.adapter = adapter
        self.migration_tracker = migration_tracker
        self.monitoring_interval = monitoring_interval
        self.max_query_history = max_query_history
        self.enable_continuous_monitoring = enable_continuous_monitoring

        # Performance tracking data
        self.query_metrics: Dict[str, SQLiteQueryMetrics] = {}
        self.wal_metrics_history: deque = deque(maxlen=100)
        self.fragmentation_history: deque = deque(maxlen=50)
        self.index_metrics: Dict[str, SQLiteIndexPerformanceMetrics] = {}

        # Monitoring state
        self._monitoring_task: Optional[asyncio.Task] = None
        self._last_monitoring_time = 0
        self._baseline_metrics: Optional[SQLitePerformanceMetrics] = None

        # Alert thresholds
        self.alert_thresholds = {
            "slow_query_ms": 1000,
            "fragmentation_ratio": 0.25,
            "wal_size_mb": 100,
            "connection_pool_wait_ms": 1000,
            "checkpoint_failure_rate": 0.1,
        }

        # Performance insights
        self.performance_insights: Dict[str, Any] = {}
        self.optimization_recommendations: List[str] = []

    async def start_monitoring(self) -> None:
        """Start continuous performance monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("Performance monitoring already running")
            return

        logger.info(
            f"Starting SQLite performance monitoring (interval: {self.monitoring_interval}s)"
        )

        # Collect baseline metrics
        await self._collect_baseline_metrics()

        if self.enable_continuous_monitoring:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def stop_monitoring(self) -> None:
        """Stop continuous performance monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None

        logger.info("SQLite performance monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        try:
            while True:
                start_time = time.time()

                try:
                    await self._collect_performance_snapshot()
                    await self._analyze_performance_trends()
                    await self._generate_optimization_recommendations()
                    await self._check_alert_conditions()

                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")

                # Calculate sleep time to maintain consistent interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.monitoring_interval - elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled")
            raise

    async def _collect_baseline_metrics(self) -> None:
        """Collect baseline performance metrics."""
        try:
            self._baseline_metrics = await self.adapter.get_performance_metrics()
            logger.info("Collected baseline SQLite performance metrics")
        except Exception as e:
            logger.warning(f"Failed to collect baseline metrics: {e}")

    async def _collect_performance_snapshot(self) -> None:
        """Collect a comprehensive performance snapshot."""
        current_time = time.time()

        try:
            # Core SQLite metrics
            sqlite_metrics = await self.adapter.get_performance_metrics()

            # WAL metrics (if WAL mode is enabled)
            if self.adapter.enable_wal:
                wal_metrics = await self._collect_wal_metrics()
                self.wal_metrics_history.append(wal_metrics)

            # Fragmentation analysis
            fragmentation_metrics = await self._analyze_fragmentation()
            self.fragmentation_history.append(fragmentation_metrics)

            # Index performance metrics
            await self._collect_index_metrics()

            # Connection pool metrics
            pool_stats = self.adapter.connection_pool_stats

            # Update performance insights
            self.performance_insights.update(
                {
                    "last_snapshot_time": datetime.now().isoformat(),
                    "sqlite_core_metrics": asdict(sqlite_metrics),
                    "connection_pool_stats": asdict(pool_stats),
                    "monitoring_uptime_hours": (
                        current_time - self._last_monitoring_time
                    )
                    / 3600,
                }
            )

            self._last_monitoring_time = current_time

        except Exception as e:
            logger.error(f"Failed to collect performance snapshot: {e}")

    async def _collect_wal_metrics(self) -> SQLiteWALMetrics:
        """Collect WAL-specific performance metrics."""
        try:
            # Get WAL file information
            wal_size_mb = 0.0
            if not self.adapter.is_memory_database:
                db_path = Path(self.adapter.database_path)
                wal_path = db_path.with_suffix(db_path.suffix + "-wal")
                if wal_path.exists():
                    wal_size_mb = wal_path.stat().st_size / (1024 * 1024)

            # Calculate checkpoint frequency
            checkpoint_frequency = 0.0
            if len(self.wal_metrics_history) > 1:
                time_diff = time.time() - self._last_monitoring_time
                if time_diff > 0:
                    checkpoint_frequency = 1.0 / (time_diff / 3600)  # Per hour

            # Get WAL checkpoint info
            async with self.adapter._get_connection() as conn:
                cursor = await conn.execute("PRAGMA wal_checkpoint")
                result = await cursor.fetchone()

                busy_checkpoints = 0
                successful_checkpoints = 1
                checkpoint_duration = 0.0

                if result:
                    busy, log_pages, checkpointed = result
                    if busy > 0:
                        busy_checkpoints = 1

            return SQLiteWALMetrics(
                wal_size_mb=wal_size_mb,
                wal_pages=result[1] if result else 0,
                checkpoint_frequency_per_hour=checkpoint_frequency,
                last_checkpoint_time=datetime.now().isoformat(),
                checkpoint_duration_ms=checkpoint_duration,
                wal_growth_rate_mb_per_hour=self._calculate_wal_growth_rate(),
                busy_checkpoint_count=busy_checkpoints,
                successful_checkpoint_count=successful_checkpoints,
            )

        except Exception as e:
            logger.warning(f"Failed to collect WAL metrics: {e}")
            return SQLiteWALMetrics(
                wal_size_mb=0.0,
                wal_pages=0,
                checkpoint_frequency_per_hour=0.0,
                last_checkpoint_time="",
                checkpoint_duration_ms=0.0,
                wal_growth_rate_mb_per_hour=0.0,
                busy_checkpoint_count=0,
                successful_checkpoint_count=0,
            )

    def _calculate_wal_growth_rate(self) -> float:
        """Calculate WAL file growth rate."""
        if len(self.wal_metrics_history) < 2:
            return 0.0

        recent = self.wal_metrics_history[-1]
        previous = self.wal_metrics_history[-2]

        size_diff = recent.wal_size_mb - previous.wal_size_mb
        time_diff = (
            datetime.fromisoformat(recent.last_checkpoint_time)
            - datetime.fromisoformat(previous.last_checkpoint_time)
        ).total_seconds() / 3600

        return size_diff / max(time_diff, 0.01)  # MB per hour

    async def _analyze_fragmentation(self) -> SQLiteFragmentationAnalysis:
        """Analyze database fragmentation."""
        try:
            async with self.adapter._get_connection() as conn:
                # Get page statistics
                cursor = await conn.execute("PRAGMA page_count")
                total_pages = (await cursor.fetchone())[0]

                cursor = await conn.execute("PRAGMA freelist_count")
                free_pages = (await cursor.fetchone())[0]

                cursor = await conn.execute("PRAGMA page_size")
                page_size = (await cursor.fetchone())[0]

                # Calculate fragmentation metrics
                fragmentation_ratio = free_pages / max(total_pages, 1)
                wasted_space_mb = (free_pages * page_size) / (1024 * 1024)

                # Estimate vacuum duration (rough heuristic)
                db_size_mb = (total_pages * page_size) / (1024 * 1024)
                vacuum_duration_minutes = max(1, db_size_mb / 100)  # 1 minute per 100MB

                # Check auto-vacuum effectiveness
                cursor = await conn.execute("PRAGMA auto_vacuum")
                auto_vacuum_mode = (await cursor.fetchone())[0]
                auto_vacuum_effectiveness = 0.8 if auto_vacuum_mode > 0 else 0.0

                return SQLiteFragmentationAnalysis(
                    total_pages=total_pages,
                    free_pages=free_pages,
                    fragmentation_ratio=fragmentation_ratio,
                    wasted_space_mb=wasted_space_mb,
                    vacuum_recommended=fragmentation_ratio > 0.15,
                    vacuum_estimated_duration_minutes=vacuum_duration_minutes,
                    auto_vacuum_effectiveness=auto_vacuum_effectiveness,
                    last_vacuum_date=None,  # Would need to track this separately
                )

        except Exception as e:
            logger.warning(f"Failed to analyze fragmentation: {e}")
            return SQLiteFragmentationAnalysis(
                total_pages=0,
                free_pages=0,
                fragmentation_ratio=0.0,
                wasted_space_mb=0.0,
                vacuum_recommended=False,
                vacuum_estimated_duration_minutes=0.0,
                auto_vacuum_effectiveness=0.0,
                last_vacuum_date=None,
            )

    async def _collect_index_metrics(self) -> None:
        """Collect index performance metrics."""
        try:
            # Get all indexes from the adapter
            all_indexes = await self.adapter.get_all_indexes()

            for index_info in all_indexes:
                index_name = index_info["name"]

                # Get usage statistics from adapter
                usage_stats = self.adapter.get_index_usage_statistics()
                index_usage = usage_stats.get(index_name, {})

                # Calculate effectiveness score
                usage_count = index_usage.get("usage_count", 0)
                size_kb = index_usage.get("estimated_size_kb", 0)

                # Simple effectiveness heuristic
                if size_kb > 0:
                    effectiveness_score = min(
                        10.0, usage_count / (size_kb / 1024)
                    )  # Usage per MB
                else:
                    effectiveness_score = float(usage_count)

                # Generate recommendation
                if usage_count == 0:
                    recommendation = "Consider dropping - unused index"
                elif effectiveness_score < 1.0:
                    recommendation = "Low effectiveness - review necessity"
                elif effectiveness_score > 5.0:
                    recommendation = "Highly effective - keep"
                else:
                    recommendation = "Moderate effectiveness - monitor"

                self.index_metrics[index_name] = SQLiteIndexPerformanceMetrics(
                    index_name=index_name,
                    table_name=index_info.get("table", "unknown"),
                    usage_count=usage_count,
                    avg_selectivity=0.5,  # Would need query analysis to determine
                    size_mb=(size_kb or 100) / 1024,  # Estimate if not available
                    maintenance_cost_ms=0.0,  # Would need to measure during updates
                    last_used=None,  # Would need to track
                    effectiveness_score=effectiveness_score,
                    recommendation=recommendation,
                )

        except Exception as e:
            logger.warning(f"Failed to collect index metrics: {e}")

    async def track_query_performance(
        self,
        query: str,
        execution_time_ms: float,
        result_count: int = 0,
        query_plan: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Track performance metrics for a specific query."""
        try:
            # Generate query hash for grouping similar queries
            query_template = self._normalize_query(query)
            query_hash = str(hash(query_template))

            # Analyze query plan if provided
            uses_index = False
            full_table_scans = 0
            temp_btree_usage = 0
            plan_steps = 0

            if query_plan:
                plan_steps = len(query_plan.get("plan_steps", []))
                for step in query_plan.get("plan_steps", []):
                    if step.get("operation") == "index_search":
                        uses_index = True
                    elif step.get("operation") == "table_scan":
                        full_table_scans += 1
                    elif step.get("operation") in ["temp_btree", "temp_sort"]:
                        temp_btree_usage += 1

            # Update or create query metrics
            if query_hash in self.query_metrics:
                metrics = self.query_metrics[query_hash]
                metrics.execution_count += 1
                metrics.total_time_ms += execution_time_ms
                metrics.avg_time_ms = metrics.total_time_ms / metrics.execution_count
                metrics.min_time_ms = min(metrics.min_time_ms, execution_time_ms)
                metrics.max_time_ms = max(metrics.max_time_ms, execution_time_ms)
                metrics.last_executed = datetime.now().isoformat()

                # Update average result count
                prev_avg = metrics.result_rows_avg
                metrics.result_rows_avg = (
                    prev_avg * (metrics.execution_count - 1) + result_count
                ) / metrics.execution_count

            else:
                self.query_metrics[query_hash] = SQLiteQueryMetrics(
                    query_hash=query_hash,
                    query_template=query_template,
                    execution_count=1,
                    total_time_ms=execution_time_ms,
                    avg_time_ms=execution_time_ms,
                    min_time_ms=execution_time_ms,
                    max_time_ms=execution_time_ms,
                    last_executed=datetime.now().isoformat(),
                    query_plan_steps=plan_steps,
                    uses_index=uses_index,
                    full_table_scans=full_table_scans,
                    temp_btree_usage=temp_btree_usage,
                    result_rows_avg=float(result_count),
                )

            # Maintain size limit
            if len(self.query_metrics) > self.max_query_history:
                # Remove oldest entries (by last_executed)
                sorted_metrics = sorted(
                    self.query_metrics.items(), key=lambda x: x[1].last_executed
                )

                for query_hash, _ in sorted_metrics[
                    : len(self.query_metrics) - self.max_query_history
                ]:
                    del self.query_metrics[query_hash]

        except Exception as e:
            logger.warning(f"Failed to track query performance: {e}")

    def _normalize_query(self, query: str) -> str:
        """Normalize query for template grouping."""
        # Simple normalization - replace literals with placeholders
        normalized = query.strip()

        # Replace string literals
        normalized = re.sub(r"'[^']*'", "'?'", normalized)

        # Replace numeric literals
        normalized = re.sub(r"\b\d+\b", "?", normalized)

        # Replace IN clauses with multiple values
        normalized = re.sub(
            r"IN\s*\([^)]+\)", "IN (?)", normalized, flags=re.IGNORECASE
        )

        # Normalize whitespace
        normalized = " ".join(normalized.split())

        return normalized.upper()

    async def _analyze_performance_trends(self) -> None:
        """Analyze performance trends and detect regressions."""
        try:
            # Analyze query performance trends
            slow_queries = [
                metrics
                for metrics in self.query_metrics.values()
                if metrics.avg_time_ms > self.alert_thresholds["slow_query_ms"]
            ]

            # Analyze fragmentation trends
            if len(self.fragmentation_history) >= 2:
                current_frag = self.fragmentation_history[-1]
                previous_frag = self.fragmentation_history[-2]

                frag_trend = (
                    current_frag.fragmentation_ratio - previous_frag.fragmentation_ratio
                )
                if frag_trend > 0.05:  # 5% increase in fragmentation
                    self.optimization_recommendations.append(
                        f"Database fragmentation increasing rapidly: {frag_trend:.2%} in {self.monitoring_interval}s"
                    )

            # Analyze WAL growth trends
            if len(self.wal_metrics_history) >= 2:
                current_wal = self.wal_metrics_history[-1]
                if current_wal.wal_growth_rate_mb_per_hour > 50:  # 50MB/hour growth
                    self.optimization_recommendations.append(
                        f"High WAL growth rate: {current_wal.wal_growth_rate_mb_per_hour:.1f} MB/hour"
                    )

            # Update performance insights
            self.performance_insights.update(
                {
                    "slow_queries_count": len(slow_queries),
                    "top_slow_queries": [
                        {
                            "template": q.query_template[:100],
                            "avg_time_ms": q.avg_time_ms,
                            "execution_count": q.execution_count,
                        }
                        for q in sorted(
                            slow_queries, key=lambda x: x.avg_time_ms, reverse=True
                        )[:5]
                    ],
                    "fragmentation_trend": (
                        "increasing"
                        if len(self.fragmentation_history) >= 2
                        and self.fragmentation_history[-1].fragmentation_ratio
                        > self.fragmentation_history[-2].fragmentation_ratio
                        else "stable"
                    ),
                    "index_effectiveness": {
                        name: metrics.effectiveness_score
                        for name, metrics in self.index_metrics.items()
                    },
                }
            )

        except Exception as e:
            logger.warning(f"Failed to analyze performance trends: {e}")

    async def _generate_optimization_recommendations(self) -> None:
        """Generate optimization recommendations based on current metrics."""
        recommendations = []

        try:
            # Query optimization recommendations
            for metrics in self.query_metrics.values():
                if metrics.avg_time_ms > self.alert_thresholds["slow_query_ms"]:
                    if not metrics.uses_index and metrics.full_table_scans > 0:
                        recommendations.append(
                            f"Slow query without index usage: {metrics.query_template[:50]}... "
                            f"(avg: {metrics.avg_time_ms:.1f}ms)"
                        )

                    if metrics.temp_btree_usage > 0:
                        recommendations.append(
                            f"Query using temporary B-tree: {metrics.query_template[:50]}... "
                            f"Consider adding appropriate index"
                        )

            # Fragmentation recommendations
            if self.fragmentation_history:
                current_frag = self.fragmentation_history[-1]
                if current_frag.vacuum_recommended:
                    recommendations.append(
                        f"High fragmentation detected ({current_frag.fragmentation_ratio:.1%}). "
                        f"VACUUM recommended (estimated duration: {current_frag.vacuum_estimated_duration_minutes:.1f} min)"
                    )

            # WAL recommendations
            if self.wal_metrics_history:
                current_wal = self.wal_metrics_history[-1]
                if current_wal.wal_size_mb > self.alert_thresholds["wal_size_mb"]:
                    recommendations.append(
                        f"Large WAL file ({current_wal.wal_size_mb:.1f}MB). "
                        f"Consider checkpoint or review wal_autocheckpoint setting"
                    )

            # Index recommendations
            unused_indexes = [
                name
                for name, metrics in self.index_metrics.items()
                if metrics.usage_count == 0
            ]

            if unused_indexes:
                recommendations.append(
                    f"Unused indexes detected: {', '.join(unused_indexes[:3])}... "
                    f"Consider dropping to save space"
                )

            # Connection pool recommendations
            pool_stats = self.adapter.connection_pool_stats
            if (
                pool_stats.avg_connection_time_ms
                > self.alert_thresholds["connection_pool_wait_ms"]
            ):
                recommendations.append(
                    f"High connection pool wait time ({pool_stats.avg_connection_time_ms:.1f}ms). "
                    f"Consider increasing pool size"
                )

            # Update recommendations list (keep only recent ones)
            self.optimization_recommendations = (
                recommendations + self.optimization_recommendations
            )[
                :50
            ]  # Keep last 50 recommendations

        except Exception as e:
            logger.warning(f"Failed to generate optimization recommendations: {e}")

    async def _check_alert_conditions(self) -> None:
        """Check for alert conditions and log warnings."""
        try:
            # Check fragmentation threshold
            if self.fragmentation_history:
                current_frag = self.fragmentation_history[-1]
                if (
                    current_frag.fragmentation_ratio
                    > self.alert_thresholds["fragmentation_ratio"]
                ):
                    logger.warning(
                        f"High database fragmentation: {current_frag.fragmentation_ratio:.1%} "
                        f"(threshold: {self.alert_thresholds['fragmentation_ratio']:.1%})"
                    )

            # Check WAL size threshold
            if self.wal_metrics_history:
                current_wal = self.wal_metrics_history[-1]
                if current_wal.wal_size_mb > self.alert_thresholds["wal_size_mb"]:
                    logger.warning(
                        f"Large WAL file: {current_wal.wal_size_mb:.1f}MB "
                        f"(threshold: {self.alert_thresholds['wal_size_mb']}MB)"
                    )

            # Check slow queries
            slow_query_count = len(
                [
                    m
                    for m in self.query_metrics.values()
                    if m.avg_time_ms > self.alert_thresholds["slow_query_ms"]
                ]
            )

            if slow_query_count > 0:
                logger.warning(f"Detected {slow_query_count} slow query patterns")

        except Exception as e:
            logger.warning(f"Failed to check alert conditions: {e}")

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        report = {
            "report_timestamp": datetime.now().isoformat(),
            "monitoring_duration_hours": (time.time() - self._last_monitoring_time)
            / 3600,
            "database_info": {
                "path": self.adapter.database_path,
                "wal_enabled": self.adapter.enable_wal,
                "connection_pooling": self.adapter.enable_connection_pooling,
            },
            "performance_summary": {
                "total_queries_tracked": len(self.query_metrics),
                "slow_queries": len(
                    [
                        m
                        for m in self.query_metrics.values()
                        if m.avg_time_ms > self.alert_thresholds["slow_query_ms"]
                    ]
                ),
                "average_query_time_ms": (
                    sum(m.avg_time_ms for m in self.query_metrics.values())
                    / max(len(self.query_metrics), 1)
                ),
                "total_executions": sum(
                    m.execution_count for m in self.query_metrics.values()
                ),
            },
            "fragmentation_status": (
                asdict(self.fragmentation_history[-1])
                if self.fragmentation_history
                else None
            ),
            "wal_status": (
                asdict(self.wal_metrics_history[-1])
                if self.wal_metrics_history
                else None
            ),
            "index_performance": {
                name: asdict(metrics) for name, metrics in self.index_metrics.items()
            },
            "optimization_recommendations": self.optimization_recommendations[
                -10:
            ],  # Last 10
            "performance_insights": self.performance_insights,
        }

        return report

    def export_performance_data(self, output_file: str) -> bool:
        """Export performance data to JSON file."""
        try:
            import json

            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "query_metrics": {k: asdict(v) for k, v in self.query_metrics.items()},
                "fragmentation_history": [
                    asdict(f) for f in self.fragmentation_history
                ],
                "wal_metrics_history": [asdict(w) for w in self.wal_metrics_history],
                "index_metrics": {k: asdict(v) for k, v in self.index_metrics.items()},
                "performance_insights": self.performance_insights,
                "optimization_recommendations": self.optimization_recommendations,
            }

            with open(output_file, "w") as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"Performance data exported to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to export performance data: {e}")
            return False
