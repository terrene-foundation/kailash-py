"""
Comprehensive Load Testing Framework for Kailash LocalRuntime

This framework provides enterprise-grade load testing capabilities for the enhanced
LocalRuntime, capable of testing 1000+ concurrent workflows with real infrastructure.
Follows the 3-tier testing strategy with real infrastructure (no mocking).

Key Features:
- Concurrent workflow execution testing (1-10000 parallel workflows)
- Real database integration testing with connection pool stress testing
- Performance metrics collection (throughput, latency, resource usage)
- Failure injection testing (database failures, resource exhaustion)
- Performance regression detection and reporting
- Docker-based test infrastructure integration

Test Scenarios:
- Baseline Performance: 100, 500, 1000, 5000 concurrent workflows
- Database Stress: Connection pool exhaustion, query timeouts, failover
- Resource Pressure: Memory limits, CPU saturation, disk I/O
- Failure Recovery: Circuit breaker activation, retry policy effectiveness
- Long-running Stability: 24-hour endurance tests with resource monitoring
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import random
import statistics
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
from unittest.mock import Mock

import docker
import psutil
import pymongo
import pytest
import redis
import sqlalchemy as sa
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from sqlalchemy import create_engine

# Configure logging for performance testing
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics collection."""

    # Execution Metrics
    total_workflows: int
    successful_workflows: int
    failed_workflows: int
    execution_time: float
    throughput: float  # workflows per second

    # Latency Metrics
    avg_latency: float
    min_latency: float
    max_latency: float
    p50_latency: float
    p90_latency: float
    p99_latency: float

    # Resource Metrics
    peak_memory_mb: float
    avg_cpu_percent: float
    peak_cpu_percent: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_io_sent_mb: float
    network_io_recv_mb: float

    # Database Metrics
    active_connections: int
    peak_connections: int
    connection_pool_utilization: float
    database_errors: int

    # Error Metrics
    error_rate: float
    timeout_errors: int
    connection_errors: int
    resource_exhaustion_errors: int

    # Timestamps
    test_start_time: str
    test_end_time: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def __str__(self) -> str:
        """Human-readable performance summary."""
        return f"""
Performance Test Results:
========================
Total Workflows: {self.total_workflows}
Success Rate: {(self.successful_workflows / self.total_workflows) * 100:.2f}%
Error Rate: {self.error_rate:.2f}%
Throughput: {self.throughput:.2f} workflows/sec
Avg Latency: {self.avg_latency:.3f}s
P99 Latency: {self.p99_latency:.3f}s
Peak Memory: {self.peak_memory_mb:.1f} MB
Peak CPU: {self.peak_cpu_percent:.1f}%
Peak DB Connections: {self.peak_connections}
"""


@dataclass
class LoadTestConfig:
    """Configuration for load tests."""

    # Test Scale
    concurrent_workflows: int = 100
    total_workflows: int = 1000
    ramp_up_duration: int = 60  # seconds
    test_duration: int = 300  # seconds (5 minutes)
    cooldown_duration: int = 30  # seconds

    # Workflow Configuration
    workflow_types: List[str] = None
    workflow_complexity: str = "medium"  # simple, medium, complex

    # Database Configuration
    enable_database_stress: bool = True
    max_db_connections: int = 100
    connection_timeout: int = 30

    # Resource Limits
    memory_limit_mb: Optional[int] = None
    cpu_limit_percent: Optional[int] = None

    # Failure Injection
    enable_failure_injection: bool = False
    failure_rate: float = 0.05  # 5% failure rate
    failure_types: List[str] = None

    # Monitoring
    metrics_collection_interval: int = 5  # seconds
    enable_detailed_logging: bool = False

    def __post_init__(self):
        """Set default values for complex fields."""
        if self.workflow_types is None:
            self.workflow_types = ["data_processing", "analytics", "transformation"]

        if self.failure_types is None:
            self.failure_types = [
                "database_timeout",
                "memory_pressure",
                "connection_exhaustion",
            ]


class ResourceMonitor:
    """Real-time resource monitoring during load tests."""

    def __init__(self, collection_interval: int = 5):
        self.collection_interval = collection_interval
        self.monitoring = False
        self.metrics_history = []
        self.monitor_thread = None

        # Initialize psutil process
        self.process = psutil.Process()

        # Database connection monitoring
        self.db_connections = {}

    def start_monitoring(self):
        """Start resource monitoring in background thread."""
        self.monitoring = True
        self.metrics_history.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("Resource monitoring started")

    def stop_monitoring(self):
        """Stop resource monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        logger.info("Resource monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.monitoring:
            try:
                # Collect system metrics
                metrics = {
                    "timestamp": datetime.now().isoformat(),
                    "memory_mb": self.process.memory_info().rss / 1024 / 1024,
                    "cpu_percent": self.process.cpu_percent(),
                    "disk_io": (
                        self.process.io_counters()
                        if hasattr(self.process, "io_counters")
                        else None
                    ),
                    "num_threads": self.process.num_threads(),
                    "open_files": (
                        len(self.process.open_files())
                        if hasattr(self.process, "open_files")
                        else 0
                    ),
                    "connections": (
                        len(self.process.connections())
                        if hasattr(self.process, "connections")
                        else 0
                    ),
                }

                # Collect database connection metrics
                metrics["database_connections"] = self._get_database_connections()

                self.metrics_history.append(metrics)

                # Sleep until next collection
                time.sleep(self.collection_interval)

            except Exception as e:
                logger.warning(f"Error collecting metrics: {e}")
                time.sleep(self.collection_interval)

    def _get_database_connections(self) -> Dict[str, int]:
        """Get database connection counts from test infrastructure."""
        connections = {}

        # PostgreSQL connections
        try:
            pg_engine = create_engine(
                "postgresql://test_user:test_password@localhost:5434/kailash_test"
            )
            with pg_engine.connect() as conn:
                result = conn.execute(
                    sa.text(
                        "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
                    )
                )
                connections["postgresql_active"] = result.scalar()
        except Exception:
            connections["postgresql_active"] = 0

        # MySQL connections
        try:
            mysql_engine = create_engine(
                "mysql://kailash_test:test_password@localhost:3307/kailash_test"
            )
            with mysql_engine.connect() as conn:
                result = conn.execute(sa.text("SHOW STATUS LIKE 'Threads_connected'"))
                row = result.fetchone()
                connections["mysql_active"] = int(row[1]) if row else 0
        except Exception:
            connections["mysql_active"] = 0

        # Redis connections
        try:
            r = redis.Redis(host="localhost", port=6380, decode_responses=True)
            info = r.info()
            connections["redis_connected"] = info.get("connected_clients", 0)
        except Exception:
            connections["redis_connected"] = 0

        return connections

    def get_peak_metrics(self) -> Dict[str, Any]:
        """Get peak resource usage metrics."""
        if not self.metrics_history:
            return {}

        # Extract metric arrays
        memory_values = [m["memory_mb"] for m in self.metrics_history]
        cpu_values = [m["cpu_percent"] for m in self.metrics_history]

        # Database connection peaks
        pg_connections = [
            m["database_connections"].get("postgresql_active", 0)
            for m in self.metrics_history
        ]
        mysql_connections = [
            m["database_connections"].get("mysql_active", 0)
            for m in self.metrics_history
        ]
        redis_connections = [
            m["database_connections"].get("redis_connected", 0)
            for m in self.metrics_history
        ]

        return {
            "peak_memory_mb": max(memory_values) if memory_values else 0,
            "avg_memory_mb": statistics.mean(memory_values) if memory_values else 0,
            "peak_cpu_percent": max(cpu_values) if cpu_values else 0,
            "avg_cpu_percent": statistics.mean(cpu_values) if cpu_values else 0,
            "peak_postgresql_connections": max(pg_connections) if pg_connections else 0,
            "peak_mysql_connections": (
                max(mysql_connections) if mysql_connections else 0
            ),
            "peak_redis_connections": (
                max(redis_connections) if redis_connections else 0
            ),
            "total_samples": len(self.metrics_history),
        }


class FailureInjector:
    """Inject realistic failures during load tests."""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.active_failures = []

    @contextmanager
    def inject_failure(self, failure_type: str):
        """Context manager for failure injection."""
        if not self.config.enable_failure_injection:
            yield
            return

        if random.random() > self.config.failure_rate:
            yield
            return

        logger.info(f"Injecting failure: {failure_type}")

        try:
            if failure_type == "database_timeout":
                yield self._inject_database_timeout()
            elif failure_type == "memory_pressure":
                yield self._inject_memory_pressure()
            elif failure_type == "connection_exhaustion":
                yield self._inject_connection_exhaustion()
            else:
                yield
        finally:
            logger.info(f"Failure injection complete: {failure_type}")

    def _inject_database_timeout(self):
        """Simulate database timeout by introducing delays."""
        time.sleep(random.uniform(1, 5))

    def _inject_memory_pressure(self):
        """Simulate memory pressure by allocating temporary memory."""
        # Allocate 100MB temporarily
        memory_hog = bytearray(100 * 1024 * 1024)
        time.sleep(0.1)
        del memory_hog

    def _inject_connection_exhaustion(self):
        """Simulate connection exhaustion scenarios."""
        # This would typically involve exhausting connection pools
        # For testing, we'll just introduce a delay
        time.sleep(random.uniform(0.5, 2.0))


class WorkflowGenerator:
    """Generate realistic test workflows for load testing."""

    def __init__(self, complexity: str = "medium"):
        self.complexity = complexity

    def generate_data_processing_workflow(self) -> WorkflowBuilder:
        """Generate a data processing workflow."""
        workflow = WorkflowBuilder()

        # Data ingestion
        workflow.add_node(
            "CSVReaderNode",
            "data_source",
            {"file_path": "/tmp/test_data.csv", "skip_header": True},
        )

        # Data validation
        workflow.add_node(
            "DataValidatorNode",
            "validator",
            {"schema": {"id": "int", "name": "str", "value": "float"}},
        )

        # Data transformation
        workflow.add_node(
            "PythonCodeNode",
            "transformer",
            {
                "code": """
def execute(input_data):
    transformed = []
    for row in input_data.get('data', []):
        transformed.append({
            'id': row['id'],
            'name': row['name'].upper(),
            'value': row['value'] * 1.1
        })
    return {'transformed_data': transformed}
"""
            },
        )

        # Connect the workflow
        workflow.add_connection("data_source", "data", "validator", "input_data")
        workflow.add_connection(
            "validator", "validated_data", "transformer", "input_data"
        )

        if self.complexity in ["medium", "complex"]:
            # Add analytics
            workflow.add_node(
                "PythonCodeNode",
                "analytics",
                {
                    "code": """
def execute(input_data):
    data = input_data.get('transformed_data', [])
    total_value = sum(row['value'] for row in data)
    avg_value = total_value / len(data) if data else 0
    return {'total': total_value, 'average': avg_value, 'count': len(data)}
"""
                },
            )
            workflow.add_connection(
                "transformer", "transformed_data", "analytics", "input_data"
            )

        if self.complexity == "complex":
            # Add database storage
            workflow.add_node(
                "AsyncSQLNode",
                "storage",
                {
                    "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                    "query": "INSERT INTO test_results (total_value, avg_value, record_count) VALUES (%(total)s, %(average)s, %(count)s)",
                    "query_type": "insert",
                },
            )
            workflow.add_connection("analytics", "results", "storage", "parameters")

        return workflow

    def generate_analytics_workflow(self) -> WorkflowBuilder:
        """Generate an analytics-focused workflow."""
        workflow = WorkflowBuilder()

        # Data retrieval
        workflow.add_node(
            "AsyncSQLNode",
            "data_retrieval",
            {
                "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test",
                "query": "SELECT * FROM test_data ORDER BY created_at DESC LIMIT 1000",
                "query_type": "select",
            },
        )

        # Statistical analysis
        workflow.add_node(
            "PythonCodeNode",
            "statistics",
            {
                "code": """
import statistics
def execute(input_data):
    data = input_data.get('results', [])
    values = [row.get('value', 0) for row in data if 'value' in row]
    if not values:
        return {'error': 'No data available'}

    return {
        'mean': statistics.mean(values),
        'median': statistics.median(values),
        'std_dev': statistics.stdev(values) if len(values) > 1 else 0,
        'min_value': min(values),
        'max_value': max(values)
    }
"""
            },
        )

        workflow.add_connection("data_retrieval", "results", "statistics", "input_data")

        if self.complexity in ["medium", "complex"]:
            # Add caching
            workflow.add_node(
                "CacheNode",
                "cache_results",
                {
                    "redis_connection": "redis://localhost:6380/0",
                    "key": "analytics_results",
                    "ttl": 300,  # 5 minutes
                },
            )
            workflow.add_connection("statistics", "results", "cache_results", "data")

        return workflow

    def generate_transformation_workflow(self) -> WorkflowBuilder:
        """Generate a data transformation workflow."""
        workflow = WorkflowBuilder()

        # Source data
        workflow.add_node(
            "PythonCodeNode",
            "data_generator",
            {
                "code": """
import random
def execute():
    data = []
    for i in range(100):
        data.append({
            'id': i,
            'name': f'item_{i}',
            'category': random.choice(['A', 'B', 'C']),
            'value': random.randint(1, 1000)
        })
    return {'generated_data': data}
"""
            },
        )

        # Filtering
        workflow.add_node(
            "PythonCodeNode",
            "filter",
            {
                "code": """
def execute(input_data):
    data = input_data.get('generated_data', [])
    filtered = [row for row in data if row['value'] > 500]
    return {'filtered_data': filtered}
"""
            },
        )

        # Grouping
        workflow.add_node(
            "PythonCodeNode",
            "group_by_category",
            {
                "code": """
def execute(input_data):
    data = input_data.get('filtered_data', [])
    groups = {}
    for row in data:
        category = row['category']
        if category not in groups:
            groups[category] = []
        groups[category].append(row)
    return {'grouped_data': groups}
"""
            },
        )

        workflow.add_connection(
            "data_generator", "generated_data", "filter", "input_data"
        )
        workflow.add_connection(
            "filter", "filtered_data", "group_by_category", "input_data"
        )

        return workflow

    def generate_workflow(self, workflow_type: str) -> WorkflowBuilder:
        """Generate a workflow based on type."""
        if workflow_type == "data_processing":
            return self.generate_data_processing_workflow()
        elif workflow_type == "analytics":
            return self.generate_analytics_workflow()
        elif workflow_type == "transformation":
            return self.generate_transformation_workflow()
        else:
            return self.generate_data_processing_workflow()  # default


class LoadTestFramework:
    """Comprehensive load testing framework for LocalRuntime."""

    def __init__(self, config: LoadTestConfig = None):
        self.config = config or LoadTestConfig()
        self.resource_monitor = ResourceMonitor(self.config.metrics_collection_interval)
        self.failure_injector = FailureInjector(self.config)
        self.workflow_generator = WorkflowGenerator(self.config.workflow_complexity)

        # Test state
        self.test_results = []
        self.workflow_latencies = []
        self.error_counts = {
            "timeout_errors": 0,
            "connection_errors": 0,
            "resource_exhaustion_errors": 0,
            "other_errors": 0,
        }

        # Docker client for infrastructure management
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Docker client not available: {e}")
            self.docker_client = None

    @contextmanager
    def test_infrastructure(self):
        """Ensure test infrastructure is available."""
        logger.info("Verifying test infrastructure...")

        # Check Docker services
        required_services = [
            "kailash_sdk_test_postgres",
            "kailash_sdk_test_redis",
            "kailash_sdk_test_mysql",
        ]

        if self.docker_client:
            for service_name in required_services:
                try:
                    container = self.docker_client.containers.get(service_name)
                    if container.status != "running":
                        logger.error(f"Required service {service_name} is not running")
                        raise RuntimeError(f"Service {service_name} not available")
                except docker.errors.NotFound:
                    logger.error(f"Required service {service_name} not found")
                    raise RuntimeError(f"Service {service_name} not found")

        # Create test data tables
        self._setup_test_tables()

        try:
            yield
        finally:
            # Cleanup test data
            self._cleanup_test_tables()

    def _setup_test_tables(self):
        """Setup test database tables."""
        # PostgreSQL setup
        try:
            engine = create_engine(
                "postgresql://test_user:test_password@localhost:5434/kailash_test"
            )
            with engine.connect() as conn:
                # Create test results table
                conn.execute(
                    sa.text(
                        """
                    CREATE TABLE IF NOT EXISTS test_results (
                        id SERIAL PRIMARY KEY,
                        total_value DECIMAL(10,2),
                        avg_value DECIMAL(10,2),
                        record_count INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                    )
                )

                # Create test data table
                conn.execute(
                    sa.text(
                        """
                    CREATE TABLE IF NOT EXISTS test_data (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255),
                        value INTEGER,
                        category VARCHAR(10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                    )
                )

                # Insert sample data
                conn.execute(
                    sa.text(
                        """
                    INSERT INTO test_data (name, value, category)
                    SELECT 'test_' || generate_series,
                           (random() * 1000)::integer,
                           CASE (random() * 2)::integer
                               WHEN 0 THEN 'A'
                               WHEN 1 THEN 'B'
                               ELSE 'C'
                           END
                    FROM generate_series(1, 1000)
                """
                    )
                )

                conn.commit()
                logger.info("PostgreSQL test tables created and populated")
        except Exception as e:
            logger.warning(f"PostgreSQL setup failed: {e}")

        # Create test CSV file
        test_csv_path = "/tmp/test_data.csv"
        with open(test_csv_path, "w") as f:
            f.write("id,name,value\n")
            for i in range(1000):
                f.write(f"{i},test_item_{i},{random.randint(1, 1000)}\n")
        logger.info(f"Test CSV file created: {test_csv_path}")

    def _cleanup_test_tables(self):
        """Cleanup test database tables."""
        try:
            engine = create_engine(
                "postgresql://test_user:test_password@localhost:5434/kailash_test"
            )
            with engine.connect() as conn:
                conn.execute(sa.text("TRUNCATE TABLE test_results"))
                conn.execute(sa.text("TRUNCATE TABLE test_data"))
                conn.commit()
                logger.info("Test tables cleaned up")
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

        # Remove test CSV file
        try:
            os.remove("/tmp/test_data.csv")
        except FileNotFoundError:
            pass

    def execute_single_workflow(
        self, workflow_type: str, runtime: LocalRuntime
    ) -> Tuple[bool, float, str]:
        """Execute a single workflow and return success status, latency, and error message."""
        start_time = time.time()

        try:
            # Generate workflow
            workflow = self.workflow_generator.generate_workflow(workflow_type)

            # Inject failures if enabled
            with self.failure_injector.inject_failure(
                random.choice(self.config.failure_types)
            ):
                # Execute workflow
                results, run_id = runtime.execute(workflow.build())

                execution_time = time.time() - start_time

                # Check for workflow errors
                if any("error" in str(result) for result in results.values()):
                    return False, execution_time, "Workflow execution error"

                return True, execution_time, ""

        except TimeoutError as e:
            self.error_counts["timeout_errors"] += 1
            return False, time.time() - start_time, f"Timeout: {str(e)}"
        except ConnectionError as e:
            self.error_counts["connection_errors"] += 1
            return False, time.time() - start_time, f"Connection: {str(e)}"
        except MemoryError as e:
            self.error_counts["resource_exhaustion_errors"] += 1
            return False, time.time() - start_time, f"Memory: {str(e)}"
        except Exception as e:
            self.error_counts["other_errors"] += 1
            return False, time.time() - start_time, f"Error: {str(e)}"

    async def execute_concurrent_workflows(
        self, num_workflows: int
    ) -> List[Tuple[bool, float, str]]:
        """Execute multiple workflows concurrently."""
        runtime = LocalRuntime(debug=self.config.enable_detailed_logging)

        # Create workflow execution tasks
        tasks = []
        for i in range(num_workflows):
            workflow_type = random.choice(self.config.workflow_types)
            task = asyncio.create_task(
                asyncio.to_thread(self.execute_single_workflow, workflow_type, runtime)
            )
            tasks.append(task)

        # Execute all workflows concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle exceptions
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                self.error_counts["other_errors"] += 1
                processed_results.append((False, 0.0, str(result)))
            else:
                processed_results.append(result)

        return processed_results

    def run_baseline_performance_test(
        self, concurrent_workflows: int
    ) -> PerformanceMetrics:
        """Run baseline performance test with specified concurrency."""
        logger.info(
            f"Running baseline performance test: {concurrent_workflows} concurrent workflows"
        )

        test_start_time = datetime.now()

        # Start resource monitoring
        self.resource_monitor.start_monitoring()

        try:
            # Execute workflows
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            results = loop.run_until_complete(
                self.execute_concurrent_workflows(concurrent_workflows)
            )

        finally:
            # Stop monitoring
            self.resource_monitor.stop_monitoring()
            loop.close()

        test_end_time = datetime.now()
        execution_time = (test_end_time - test_start_time).total_seconds()

        # Process results
        successful_workflows = sum(1 for success, _, _ in results if success)
        failed_workflows = len(results) - successful_workflows
        latencies = [latency for _, latency, _ in results if latency > 0]

        # Calculate metrics
        resource_metrics = self.resource_monitor.get_peak_metrics()

        metrics = PerformanceMetrics(
            total_workflows=concurrent_workflows,
            successful_workflows=successful_workflows,
            failed_workflows=failed_workflows,
            execution_time=execution_time,
            throughput=(
                successful_workflows / execution_time if execution_time > 0 else 0
            ),
            # Latency metrics
            avg_latency=statistics.mean(latencies) if latencies else 0,
            min_latency=min(latencies) if latencies else 0,
            max_latency=max(latencies) if latencies else 0,
            p50_latency=statistics.median(latencies) if latencies else 0,
            p90_latency=(
                statistics.quantiles(latencies, n=10)[8] if len(latencies) >= 10 else 0
            ),
            p99_latency=(
                statistics.quantiles(latencies, n=100)[98]
                if len(latencies) >= 100
                else 0
            ),
            # Resource metrics
            peak_memory_mb=resource_metrics.get("peak_memory_mb", 0),
            avg_cpu_percent=resource_metrics.get("avg_cpu_percent", 0),
            peak_cpu_percent=resource_metrics.get("peak_cpu_percent", 0),
            disk_io_read_mb=0,  # Will be populated from detailed monitoring
            disk_io_write_mb=0,
            network_io_sent_mb=0,
            network_io_recv_mb=0,
            # Database metrics
            active_connections=sum(
                [
                    resource_metrics.get("peak_postgresql_connections", 0),
                    resource_metrics.get("peak_mysql_connections", 0),
                    resource_metrics.get("peak_redis_connections", 0),
                ]
            ),
            peak_connections=max(
                [
                    resource_metrics.get("peak_postgresql_connections", 0),
                    resource_metrics.get("peak_mysql_connections", 0),
                    resource_metrics.get("peak_redis_connections", 0),
                ]
            ),
            connection_pool_utilization=0.0,  # Will be calculated from detailed metrics
            database_errors=self.error_counts.get("connection_errors", 0),
            # Error metrics
            error_rate=(
                (failed_workflows / concurrent_workflows) * 100
                if concurrent_workflows > 0
                else 0
            ),
            timeout_errors=self.error_counts.get("timeout_errors", 0),
            connection_errors=self.error_counts.get("connection_errors", 0),
            resource_exhaustion_errors=self.error_counts.get(
                "resource_exhaustion_errors", 0
            ),
            # Timestamps
            test_start_time=test_start_time.isoformat(),
            test_end_time=test_end_time.isoformat(),
        )

        logger.info(f"Baseline test completed: {metrics}")
        return metrics

    def run_database_stress_test(self) -> PerformanceMetrics:
        """Run database connection pool stress test."""
        logger.info("Running database stress test")

        # Increase database load configuration
        stress_config = LoadTestConfig(
            concurrent_workflows=self.config.max_db_connections
            * 2,  # Exceed connection pool
            total_workflows=self.config.max_db_connections * 5,
            enable_database_stress=True,
            workflow_types=["analytics"],  # Database-heavy workflows
        )

        old_config = self.config
        self.config = stress_config

        try:
            return self.run_baseline_performance_test(
                stress_config.concurrent_workflows
            )
        finally:
            self.config = old_config

    def run_resource_pressure_test(self) -> PerformanceMetrics:
        """Run resource pressure test."""
        logger.info("Running resource pressure test")

        # Enable memory and CPU pressure
        pressure_config = LoadTestConfig(
            concurrent_workflows=500,
            total_workflows=2000,
            memory_limit_mb=512,  # Limit memory
            cpu_limit_percent=80,  # Limit CPU
            workflow_complexity="complex",  # More resource intensive
            enable_failure_injection=True,
            failure_rate=0.1,  # 10% failure rate
        )

        old_config = self.config
        self.config = pressure_config

        try:
            return self.run_baseline_performance_test(
                pressure_config.concurrent_workflows
            )
        finally:
            self.config = old_config

    def run_endurance_test(self, duration_hours: int = 24) -> List[PerformanceMetrics]:
        """Run long-running endurance test."""
        logger.info(f"Starting {duration_hours}-hour endurance test")

        endurance_results = []
        end_time = datetime.now() + timedelta(hours=duration_hours)

        test_interval = 3600  # 1 hour intervals

        while datetime.now() < end_time:
            logger.info(f"Endurance test checkpoint: {len(endurance_results) + 1}")

            # Run baseline test
            metrics = self.run_baseline_performance_test(100)  # Conservative load
            endurance_results.append(metrics)

            # Sleep until next interval
            time.sleep(test_interval)

        logger.info(f"Endurance test completed: {len(endurance_results)} checkpoints")
        return endurance_results

    def analyze_performance_regression(
        self, baseline_metrics: PerformanceMetrics, current_metrics: PerformanceMetrics
    ) -> Dict[str, Any]:
        """Analyze performance regression between baseline and current metrics."""

        def calculate_change(baseline, current):
            if baseline == 0:
                return float("inf") if current > 0 else 0
            return ((current - baseline) / baseline) * 100

        regression_analysis = {
            "throughput_change_percent": calculate_change(
                baseline_metrics.throughput, current_metrics.throughput
            ),
            "latency_change_percent": calculate_change(
                baseline_metrics.avg_latency, current_metrics.avg_latency
            ),
            "memory_change_percent": calculate_change(
                baseline_metrics.peak_memory_mb, current_metrics.peak_memory_mb
            ),
            "error_rate_change_percent": calculate_change(
                baseline_metrics.error_rate, current_metrics.error_rate
            ),
            "performance_regression_detected": False,
            "regression_severity": "none",
            "recommendations": [],
        }

        # Detect regressions
        if (
            regression_analysis["throughput_change_percent"] < -10
        ):  # 10% decrease in throughput
            regression_analysis["performance_regression_detected"] = True
            regression_analysis["recommendations"].append(
                "Investigate throughput degradation"
            )

        if (
            regression_analysis["latency_change_percent"] > 20
        ):  # 20% increase in latency
            regression_analysis["performance_regression_detected"] = True
            regression_analysis["recommendations"].append(
                "Investigate latency increase"
            )

        if regression_analysis["memory_change_percent"] > 30:  # 30% increase in memory
            regression_analysis["performance_regression_detected"] = True
            regression_analysis["recommendations"].append("Investigate memory leak")

        if (
            regression_analysis["error_rate_change_percent"] > 50
        ):  # 50% increase in errors
            regression_analysis["performance_regression_detected"] = True
            regression_analysis["recommendations"].append(
                "Investigate error rate increase"
            )

        # Determine severity
        if regression_analysis["performance_regression_detected"]:
            max_change = max(
                abs(regression_analysis["throughput_change_percent"]),
                regression_analysis["latency_change_percent"],
                regression_analysis["memory_change_percent"],
                regression_analysis["error_rate_change_percent"],
            )

            if max_change > 100:
                regression_analysis["regression_severity"] = "critical"
            elif max_change > 50:
                regression_analysis["regression_severity"] = "major"
            else:
                regression_analysis["regression_severity"] = "minor"

        return regression_analysis

    def generate_performance_report(
        self, metrics: PerformanceMetrics, output_file: str = None
    ) -> str:
        """Generate comprehensive performance report."""

        report = f"""
# Kailash LocalRuntime Load Test Report

## Test Configuration
- **Concurrent Workflows**: {metrics.total_workflows}
- **Test Duration**: {metrics.execution_time:.2f} seconds
- **Workflow Complexity**: {self.config.workflow_complexity}
- **Database Stress Enabled**: {self.config.enable_database_stress}
- **Failure Injection**: {self.config.enable_failure_injection}

## Performance Summary
{str(metrics)}

## Key Performance Indicators
- **Success Rate**: {(metrics.successful_workflows / metrics.total_workflows) * 100:.2f}%
- **Throughput**: {metrics.throughput:.2f} workflows/second
- **Average Latency**: {metrics.avg_latency:.3f} seconds
- **P99 Latency**: {metrics.p99_latency:.3f} seconds
- **Peak Memory Usage**: {metrics.peak_memory_mb:.1f} MB
- **Peak CPU Usage**: {metrics.peak_cpu_percent:.1f}%

## Resource Utilization
- **Memory**: Peak {metrics.peak_memory_mb:.1f} MB
- **CPU**: Peak {metrics.peak_cpu_percent:.1f}%
- **Database Connections**: Peak {metrics.peak_connections}
- **Connection Pool Utilization**: {metrics.connection_pool_utilization:.1f}%

## Error Analysis
- **Total Errors**: {metrics.failed_workflows}
- **Timeout Errors**: {metrics.timeout_errors}
- **Connection Errors**: {metrics.connection_errors}
- **Resource Exhaustion**: {metrics.resource_exhaustion_errors}
- **Error Rate**: {metrics.error_rate:.2f}%

## Recommendations
"""

        # Add recommendations based on metrics
        if metrics.error_rate > 5:
            report += "- **High Error Rate**: Investigate error patterns and consider reducing load\n"

        if metrics.avg_latency > 1.0:
            report += "- **High Latency**: Consider workflow optimization or resource scaling\n"

        if metrics.peak_memory_mb > 1000:
            report += "- **High Memory Usage**: Monitor for memory leaks and optimize workflows\n"

        if metrics.peak_cpu_percent > 80:
            report += (
                "- **High CPU Usage**: Consider CPU scaling or workflow optimization\n"
            )

        report += "\n## Test Execution Details\n"
        report += f"- **Start Time**: {metrics.test_start_time}\n"
        report += f"- **End Time**: {metrics.test_end_time}\n"
        report += f"- **Total Execution Time**: {metrics.execution_time:.2f} seconds\n"

        if output_file:
            with open(output_file, "w") as f:
                f.write(report)
            logger.info(f"Performance report saved to: {output_file}")

        return report


# Convenience functions for common test scenarios


def run_quick_performance_test() -> PerformanceMetrics:
    """Run a quick performance test for CI/CD."""
    config = LoadTestConfig(
        concurrent_workflows=50,
        total_workflows=200,
        test_duration=60,  # 1 minute
        workflow_complexity="simple",
    )

    framework = LoadTestFramework(config)

    with framework.test_infrastructure():
        return framework.run_baseline_performance_test(config.concurrent_workflows)


def run_full_performance_suite() -> Dict[str, PerformanceMetrics]:
    """Run comprehensive performance test suite."""
    results = {}

    # Test different concurrency levels
    concurrency_levels = [100, 500, 1000, 2000]

    for level in concurrency_levels:
        logger.info(f"Testing concurrency level: {level}")

        config = LoadTestConfig(concurrent_workflows=level)
        framework = LoadTestFramework(config)

        with framework.test_infrastructure():
            results[f"baseline_{level}"] = framework.run_baseline_performance_test(
                level
            )
            results[f"database_stress_{level}"] = framework.run_database_stress_test()

    # Resource pressure test
    config = LoadTestConfig()
    framework = LoadTestFramework(config)

    with framework.test_infrastructure():
        results["resource_pressure"] = framework.run_resource_pressure_test()

    return results


if __name__ == "__main__":
    # Example usage
    logger.info("Starting Kailash LocalRuntime Load Test")

    # Run quick test
    metrics = run_quick_performance_test()
    print(metrics)

    # Generate report
    framework = LoadTestFramework()
    report = framework.generate_performance_report(metrics, "load_test_report.md")
    print("\nPerformance report generated successfully!")
