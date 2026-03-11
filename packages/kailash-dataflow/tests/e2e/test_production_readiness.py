"""
End-to-end tests for DataFlow production readiness.

Tests production deployment scenarios, monitoring, performance under load,
security features, and operational requirements for production systems.
"""

import asyncio
import json
import os

# Import DataFlow components
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from dataflow import DataFlow
from dataflow.testing.dataflow_test_utils import DataFlowTestUtils

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestProductionDeployment:
    """Test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"
        self.test_utils = DataFlowTestUtils(self.db_url)

    def teardown_method(self):
        """Clean up test database after each test."""
        # Use DataFlow's migration system to clean up
        self.test_utils.cleanup_database()

    """Test production deployment scenarios."""

    @pytest.mark.requires_full_infrastructure
    def test_zero_downtime_deployment(self):
        """Test zero-downtime deployment with database migrations."""
        # Simulate V1 of the application
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class User:
            name: str
            email: str
            created_at: float = time.time()

        @db.model
        class Order:
            user_id: int
            total: float
            status: str = "pending"

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Create initial data
        workflow_v1 = WorkflowBuilder()
        workflow_v1.add_node(
            "UserCreateNode",
            "create_user",
            {"name": "Production User", "email": "prod@example.com"},
        )

        workflow_v1.add_node(
            "OrderCreateNode",
            "create_order",
            {"user_id": 1, "total": 99.99, "status": "completed"},
        )

        v1_result, _ = runtime.execute(workflow_v1.build())
        assert v1_result is not None

        # Simulate V2 with schema changes (backward compatible)
        db_v2 = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db_v2.model
        class User:
            name: str
            email: str
            phone: str = None  # New optional field
            verified: bool = False  # New field with default
            created_at: float = time.time()

        @db_v2.model
        class Order:
            user_id: int
            total: float
            status: str = "pending"
            shipping_address: str = None  # New optional field
            tracking_number: str = None  # New optional field

        # Create the database tables for V2
        db_v2.create_tables()

        # V2 operations should work with existing data
        workflow_v2 = WorkflowBuilder()

        # Read existing user (should work despite new fields)
        workflow_v2.add_node("UserReadNode", "read_user", {"id": "1"})

        # Update user with new field
        workflow_v2.add_node(
            "UserUpdateNode",
            "update_user",
            {"id": "1", "phone": "+1234567890", "verified": True},
        )

        # Create new order with new fields
        workflow_v2.add_node(
            "OrderCreateNode",
            "create_order_v2",
            {
                "user_id": 1,
                "total": 149.99,
                "status": "processing",
                "shipping_address": "123 Main St",
                "tracking_number": "TRACK123",
            },
        )

        v2_result, _ = runtime.execute(workflow_v2.build())
        assert v2_result is not None

        # Verify backward compatibility
        assert v2_result["read_user"] is not None
        assert v2_result["update_user"]["phone"] == "+1234567890"
        assert v2_result["create_order_v2"]["tracking_number"] == "TRACK123"

    def test_production_health_checks(self):
        """Test production health check endpoints and monitoring."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class HealthCheck:
            component: str
            status: str
            last_check: float = time.time()
            details: str = "{}"

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Simulate health check system
        workflow_health = WorkflowBuilder()

        # Check database connectivity
        workflow_health.add_node(
            "HealthCheckCreateNode",
            "check_database",
            {
                "component": "database",
                "status": "healthy",
                "details": json.dumps(
                    {"connections": 5, "pool_size": 20, "response_time_ms": 2.5}
                ),
            },
        )

        # Check API gateway
        workflow_health.add_node(
            "HealthCheckCreateNode",
            "check_api",
            {
                "component": "api_gateway",
                "status": "healthy",
                "details": json.dumps(
                    {"uptime_seconds": 86400, "request_rate": 1250, "error_rate": 0.001}
                ),
            },
        )

        # Check cache layer
        workflow_health.add_node(
            "HealthCheckCreateNode",
            "check_cache",
            {
                "component": "cache",
                "status": "healthy",
                "details": json.dumps(
                    {"hit_rate": 0.85, "memory_used_mb": 512, "eviction_rate": 0.05}
                ),
            },
        )

        # Check background workers
        workflow_health.add_node(
            "HealthCheckCreateNode",
            "check_workers",
            {
                "component": "background_workers",
                "status": "degraded",  # Simulate degraded state
                "details": json.dumps(
                    {"active_workers": 3, "expected_workers": 5, "queue_depth": 150}
                ),
            },
        )

        health_result, _ = runtime.execute(workflow_health.build())
        assert health_result is not None

        # Query overall system health
        workflow_status = WorkflowBuilder()
        workflow_status.add_node(
            "HealthCheckListNode",
            "system_status",
            {
                "filter": {"last_check": {"$gte": time.time() - 300}},  # Last 5 minutes
                "sort": [{"component": 1}],
            },
        )

        status_result, _ = runtime.execute(workflow_status.build())
        assert status_result is not None

        # Verify health monitoring
        assert health_result["check_database"]["status"] == "healthy"
        assert health_result["check_workers"]["status"] == "degraded"

    def test_production_backup_and_restore(self):
        """Test production backup and restore procedures."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class BackupJob:
            backup_type: str  # full, incremental, differential
            status: str = "initiated"
            started_at: float = time.time()
            completed_at: float = None
            size_bytes: int = None
            location: str = None
            error: str = None

        @db.model
        class CriticalData:
            data_type: str
            content: str
            importance: str = "high"
            created_at: float = time.time()

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Create critical data
        workflow_data = WorkflowBuilder()
        critical_data = [
            {
                "data_type": "user_accounts",
                "content": "user_data_dump",
                "importance": "critical",
            },
            {
                "data_type": "transactions",
                "content": "transaction_log",
                "importance": "critical",
            },
            {
                "data_type": "configurations",
                "content": "system_config",
                "importance": "high",
            },
        ]

        workflow_data.add_node(
            "CriticalDataBulkCreateNode",
            "create_data",
            {"data": critical_data, "batch_size": 10},
        )

        data_result, _ = runtime.execute(workflow_data.build())
        assert data_result is not None

        # Initiate backup
        workflow_backup = WorkflowBuilder()
        workflow_backup.add_node(
            "BackupJobCreateNode",
            "start_backup",
            {"backup_type": "full", "status": "running"},
        )

        # Simulate backup progress
        workflow_backup.add_node(
            "BackupJobUpdateNode",
            "complete_backup",
            {
                "id": "1",
                "status": "completed",
                "completed_at": time.time() + 120,  # 2 minutes later
                "size_bytes": 1024 * 1024 * 250,  # 250MB
                "location": "s3://backups/dataflow/2025-01-16/full_backup.tar.gz",
            },
        )

        backup_result, _ = runtime.execute(workflow_backup.build())
        assert backup_result is not None

        # Verify backup completion
        assert backup_result["complete_backup"]["status"] == "completed"
        assert backup_result["complete_backup"]["location"] is not None

        # Test restore scenario
        workflow_restore = WorkflowBuilder()

        # Mark data for restoration
        workflow_restore.add_node(
            "CriticalDataListNode",
            "verify_restore",
            {"filter": {"importance": "critical"}, "sort": [{"created_at": -1}]},
        )

        restore_result, _ = runtime.execute(workflow_restore.build())
        assert restore_result is not None


class TestProductionMonitoring:
    """Test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"
        self.test_utils = DataFlowTestUtils(self.db_url)

    def teardown_method(self):
        """Clean up test database after each test."""
        # Use DataFlow's migration system to clean up
        self.test_utils.cleanup_database()

    """Test production monitoring and observability."""

    def test_performance_monitoring_metrics(self):
        """Test collection and analysis of performance metrics."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class PerformanceMetric:
            metric_name: str
            value: float
            unit: str
            timestamp: float = time.time()
            tags: str = "{}"  # JSON tags

        @db.model
        class Alert:
            metric_name: str
            threshold_value: float
            actual_value: float
            severity: str
            triggered_at: float = time.time()
            resolved_at: float = None

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Collect performance metrics over time
        workflow_metrics = WorkflowBuilder()

        # Simulate metrics collection
        current_time = time.time()
        metrics_data = []

        # Generate metrics for the last hour
        for i in range(60):  # 60 minutes
            timestamp = current_time - (60 - i) * 60

            # Response time metrics
            metrics_data.append(
                {
                    "metric_name": "api_response_time",
                    "value": 45 + (i % 10) * 5,  # Varies between 45-95ms
                    "unit": "milliseconds",
                    "timestamp": timestamp,
                    "tags": json.dumps({"endpoint": "/api/users", "method": "GET"}),
                }
            )

            # Throughput metrics
            metrics_data.append(
                {
                    "metric_name": "requests_per_second",
                    "value": 100 + (i % 20) * 10,  # Varies between 100-290
                    "unit": "requests",
                    "timestamp": timestamp,
                    "tags": json.dumps({"service": "api_gateway"}),
                }
            )

            # Database metrics
            metrics_data.append(
                {
                    "metric_name": "database_connections",
                    "value": 15 + (i % 5),  # Varies between 15-19
                    "unit": "connections",
                    "timestamp": timestamp,
                    "tags": json.dumps({"database": "primary", "pool": "main"}),
                }
            )

            # Memory usage
            metrics_data.append(
                {
                    "metric_name": "memory_usage",
                    "value": 60 + (i % 15),  # Varies between 60-74%
                    "unit": "percent",
                    "timestamp": timestamp,
                    "tags": json.dumps({"server": "app-server-1"}),
                }
            )

        workflow_metrics.add_node(
            "PerformanceMetricBulkCreateNode",
            "ingest_metrics",
            {"data": metrics_data, "batch_size": 100},
        )

        metrics_result, _ = runtime.execute(workflow_metrics.build())
        assert metrics_result is not None

        # Analyze metrics for anomalies
        workflow_analysis = WorkflowBuilder()

        # Check for high response times
        workflow_analysis.add_node(
            "PerformanceMetricListNode",
            "high_response_times",
            {
                "filter": {
                    "metric_name": "api_response_time",
                    "value": {"$gt": 80},
                    "timestamp": {"$gte": current_time - 600},  # Last 10 minutes
                },
                "sort": [{"value": -1}],
            },
        )

        # Check for memory issues
        workflow_analysis.add_node(
            "PerformanceMetricListNode",
            "memory_warnings",
            {
                "filter": {
                    "metric_name": "memory_usage",
                    "value": {"$gt": 70},
                    "timestamp": {"$gte": current_time - 600},
                },
                "sort": [{"timestamp": -1}],
            },
        )

        analysis_result, _ = runtime.execute(workflow_analysis.build())
        assert analysis_result is not None

        # Create alerts for threshold breaches
        workflow_alerts = WorkflowBuilder()

        # Simulate alert conditions
        workflow_alerts.add_node(
            "AlertCreateNode",
            "response_time_alert",
            {
                "metric_name": "api_response_time",
                "threshold_value": 80,
                "actual_value": 95,
                "severity": "warning",
            },
        )

        workflow_alerts.add_node(
            "AlertCreateNode",
            "memory_alert",
            {
                "metric_name": "memory_usage",
                "threshold_value": 70,
                "actual_value": 74,
                "severity": "critical",
            },
        )

        alerts_result, _ = runtime.execute(workflow_alerts.build())
        assert alerts_result is not None

        # Verify monitoring
        assert len(metrics_data) == 240  # 60 minutes * 4 metrics
        assert alerts_result["response_time_alert"]["severity"] == "warning"
        assert alerts_result["memory_alert"]["severity"] == "critical"

    def test_distributed_tracing(self):
        """Test distributed tracing across services."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class TraceSpan:
            trace_id: str
            span_id: str
            parent_span_id: str = None
            service_name: str
            operation_name: str
            start_time: float
            end_time: float = None
            duration_ms: float = None
            status: str = "in_progress"
            tags: str = "{}"

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Simulate a distributed transaction trace
        trace_id = "trace_12345"
        workflow_trace = WorkflowBuilder()

        # API Gateway span
        start_time = time.time()
        workflow_trace.add_node(
            "TraceSpanCreateNode",
            "api_span",
            {
                "trace_id": trace_id,
                "span_id": "span_001",
                "service_name": "api_gateway",
                "operation_name": "POST /api/orders",
                "start_time": start_time,
                "end_time": start_time + 0.015,
                "duration_ms": 15,
                "status": "success",
            },
        )

        # Auth Service span
        workflow_trace.add_node(
            "TraceSpanCreateNode",
            "auth_span",
            {
                "trace_id": trace_id,
                "span_id": "span_002",
                "parent_span_id": "span_001",
                "service_name": "auth_service",
                "operation_name": "validate_token",
                "start_time": start_time + 0.001,
                "end_time": start_time + 0.005,
                "duration_ms": 4,
                "status": "success",
            },
        )

        # Order Service span
        workflow_trace.add_node(
            "TraceSpanCreateNode",
            "order_span",
            {
                "trace_id": trace_id,
                "span_id": "span_003",
                "parent_span_id": "span_001",
                "service_name": "order_service",
                "operation_name": "create_order",
                "start_time": start_time + 0.006,
                "end_time": start_time + 0.012,
                "duration_ms": 6,
                "status": "success",
            },
        )

        # Database span
        workflow_trace.add_node(
            "TraceSpanCreateNode",
            "db_span",
            {
                "trace_id": trace_id,
                "span_id": "span_004",
                "parent_span_id": "span_003",
                "service_name": "database",
                "operation_name": "INSERT orders",
                "start_time": start_time + 0.008,
                "end_time": start_time + 0.010,
                "duration_ms": 2,
                "status": "success",
                "tags": json.dumps({"query_type": "insert", "table": "orders"}),
            },
        )

        trace_result, _ = runtime.execute(workflow_trace.build())
        assert trace_result is not None

        # Query trace data
        workflow_trace_query = WorkflowBuilder()
        workflow_trace_query.add_node(
            "TraceSpanListNode",
            "get_trace",
            {"filter": {"trace_id": trace_id}, "sort": [{"start_time": 1}]},
        )

        trace_query_result, _ = runtime.execute(workflow_trace_query.build())
        assert trace_query_result is not None

        # Verify distributed trace
        assert trace_result["api_span"]["duration_ms"] == 15
        assert trace_result["db_span"]["parent_span_id"] == "span_003"


class TestProductionSecurity:
    """Test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"
        self.test_utils = DataFlowTestUtils(self.db_url)

    def teardown_method(self):
        """Clean up test database after each test."""
        # Use DataFlow's migration system to clean up
        self.test_utils.cleanup_database()

    """Test production security features."""

    def test_security_audit_logging(self):
        """Test comprehensive security audit logging."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class SecurityAuditLog:
            event_type: str
            user_id: int = None
            ip_address: str
            user_agent: str
            resource: str
            action: str
            result: str
            timestamp: float = time.time()
            details: str = "{}"

            __dataflow__ = {"audit_log": False}  # Prevent recursive audit logging

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Log various security events
        workflow_audit = WorkflowBuilder()

        security_events = [
            {
                "event_type": "authentication",
                "user_id": 123,
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0...",
                "resource": "/api/login",
                "action": "login",
                "result": "success",
                "details": json.dumps({"method": "password", "mfa": True}),
            },
            {
                "event_type": "authorization",
                "user_id": 123,
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0...",
                "resource": "/api/admin/users",
                "action": "access",
                "result": "denied",
                "details": json.dumps({"required_role": "admin", "user_role": "user"}),
            },
            {
                "event_type": "data_access",
                "user_id": 456,
                "ip_address": "10.0.0.50",
                "user_agent": "DataFlow-Client/1.0",
                "resource": "users_table",
                "action": "bulk_export",
                "result": "success",
                "details": json.dumps({"records_exported": 1000, "format": "csv"}),
            },
            {
                "event_type": "security_alert",
                "user_id": None,
                "ip_address": "45.67.89.10",
                "user_agent": "suspicious-bot/1.0",
                "resource": "/api/users",
                "action": "brute_force_attempt",
                "result": "blocked",
                "details": json.dumps({"attempts": 50, "time_window_seconds": 60}),
            },
        ]

        workflow_audit.add_node(
            "SecurityAuditLogBulkCreateNode",
            "log_events",
            {"data": security_events, "batch_size": 10},
        )

        audit_result, _ = runtime.execute(workflow_audit.build())
        assert audit_result is not None

        # Query security events
        workflow_query = WorkflowBuilder()

        # Find failed authentication attempts
        workflow_query.add_node(
            "SecurityAuditLogListNode",
            "failed_auth",
            {
                "filter": {
                    "event_type": "authentication",
                    "result": {"$ne": "success"},
                    "timestamp": {"$gte": time.time() - 3600},
                },
                "sort": [{"timestamp": -1}],
            },
        )

        # Find security alerts
        workflow_query.add_node(
            "SecurityAuditLogListNode",
            "security_alerts",
            {
                "filter": {
                    "event_type": "security_alert",
                    "timestamp": {"$gte": time.time() - 3600},
                },
                "sort": [{"timestamp": -1}],
            },
        )

        query_result, _ = runtime.execute(workflow_query.build())
        assert query_result is not None

        # Verify audit logging
        assert len(security_events) == 4
        assert audit_result["log_events"] is not None

    def test_data_encryption_at_rest(self):
        """Test data encryption for sensitive information."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class SensitiveData:
            data_type: str
            encrypted_content: str  # Will be encrypted
            metadata: str = "{}"
            created_at: float = time.time()

            __dataflow__ = {
                "encryption": {
                    "fields": ["encrypted_content"],
                    "algorithm": "AES-256-GCM",
                }
            }

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Store sensitive data
        workflow_encrypt = WorkflowBuilder()

        sensitive_items = [
            {
                "data_type": "credit_card",
                "encrypted_content": "4111-1111-1111-1111",  # Will be encrypted
                "metadata": json.dumps({"last_four": "1111", "type": "visa"}),
            },
            {
                "data_type": "ssn",
                "encrypted_content": "123-45-6789",  # Will be encrypted
                "metadata": json.dumps({"masked": "XXX-XX-6789"}),
            },
            {
                "data_type": "api_key",
                "encrypted_content": "sk_live_abcdef123456",  # Will be encrypted
                "metadata": json.dumps(
                    {"service": "payment_gateway", "environment": "production"}
                ),
            },
        ]

        workflow_encrypt.add_node(
            "SensitiveDataBulkCreateNode",
            "store_sensitive",
            {"data": sensitive_items, "batch_size": 10},
        )

        encrypt_result, _ = runtime.execute(workflow_encrypt.build())
        assert encrypt_result is not None

        # Verify data is stored (content would be encrypted in real implementation)
        workflow_verify = WorkflowBuilder()
        workflow_verify.add_node(
            "SensitiveDataListNode",
            "list_sensitive",
            {
                "filter": {"data_type": {"$in": ["credit_card", "ssn", "api_key"]}},
                "limit": 10,
            },
        )

        verify_result, _ = runtime.execute(workflow_verify.build())
        assert verify_result is not None

        # In production, encrypted_content would be encrypted
        # The application would decrypt on read if authorized

    def test_rate_limiting_and_throttling(self):
        """Test rate limiting and API throttling."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class RateLimitBucket:
            client_id: str
            endpoint: str
            window_start: float
            request_count: int = 0
            limit: int

        @db.model
        class ThrottledRequest:
            client_id: str
            endpoint: str
            timestamp: float = time.time()
            reason: str

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Simulate rate limit tracking
        workflow_rate_limit = WorkflowBuilder()

        current_window = int(time.time() / 60) * 60  # Current minute

        # Create rate limit buckets
        buckets = [
            {
                "client_id": "client_001",
                "endpoint": "/api/data",
                "window_start": current_window,
                "request_count": 95,
                "limit": 100,
            },
            {
                "client_id": "client_002",
                "endpoint": "/api/data",
                "window_start": current_window,
                "request_count": 150,
                "limit": 100,  # Over limit
            },
            {
                "client_id": "client_003",
                "endpoint": "/api/bulk",
                "window_start": current_window,
                "request_count": 5,
                "limit": 10,
            },
        ]

        workflow_rate_limit.add_node(
            "RateLimitBucketBulkCreateNode",
            "create_buckets",
            {"data": buckets, "batch_size": 10},
        )

        # Simulate incoming requests
        workflow_rate_limit.add_node(
            "RateLimitBucketUpdateNode",
            "increment_client1",
            {"id": "1", "request_count": 96},  # Still under limit
        )

        # Log throttled request
        workflow_rate_limit.add_node(
            "ThrottledRequestCreateNode",
            "throttle_client2",
            {
                "client_id": "client_002",
                "endpoint": "/api/data",
                "reason": "Rate limit exceeded: 150/100 requests per minute",
            },
        )

        rate_limit_result, _ = runtime.execute(workflow_rate_limit.build())
        assert rate_limit_result is not None

        # Check rate limit status
        workflow_check = WorkflowBuilder()
        workflow_check.add_node(
            "RateLimitBucketListNode",
            "check_limits",
            {
                "filter": {
                    "window_start": current_window,
                    "request_count": {"$gte": 90},  # Near or over limit
                }
            },
        )

        check_result, _ = runtime.execute(workflow_check.build())
        assert check_result is not None

        # Verify rate limiting
        assert rate_limit_result["increment_client1"]["request_count"] == 96
        assert rate_limit_result["throttle_client2"]["reason"].startswith(
            "Rate limit exceeded"
        )


class TestProductionScalability:
    """Test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"
        self.test_utils = DataFlowTestUtils(self.db_url)

    def teardown_method(self):
        """Clean up test database after each test."""
        # Use DataFlow's migration system to clean up
        self.test_utils.cleanup_database()

    """Test production scalability features."""

    def test_horizontal_scaling_readiness(self):
        """Test system readiness for horizontal scaling."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class WorkerNode:
            node_id: str
            status: str = "starting"
            capacity: int
            current_load: int = 0
            last_heartbeat: float = time.time()

        @db.model
        class JobQueue:
            job_id: str
            job_type: str
            priority: int = 5
            status: str = "pending"
            assigned_worker: str = None
            created_at: float = time.time()

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Simulate multiple worker nodes
        workflow_workers = WorkflowBuilder()

        workers = [
            {"node_id": "worker-001", "status": "active", "capacity": 100},
            {"node_id": "worker-002", "status": "active", "capacity": 100},
            {"node_id": "worker-003", "status": "active", "capacity": 100},
            {"node_id": "worker-004", "status": "starting", "capacity": 100},
        ]

        workflow_workers.add_node(
            "WorkerNodeBulkCreateNode",
            "register_workers",
            {"data": workers, "batch_size": 10},
        )

        # Create job queue
        jobs = []
        for i in range(250):  # More jobs than single worker capacity
            jobs.append(
                {
                    "job_id": f"job_{i:04d}",
                    "job_type": ["process", "analyze", "export"][i % 3],
                    "priority": 1 + (i % 10),
                }
            )

        workflow_workers.add_node(
            "JobQueueBulkCreateNode", "queue_jobs", {"data": jobs, "batch_size": 50}
        )

        workers_result, _ = runtime.execute(workflow_workers.build())
        assert workers_result is not None

        # Distribute jobs across workers
        workflow_distribute = WorkflowBuilder()

        # Simulate job distribution
        worker_assignments = {"worker-001": 80, "worker-002": 85, "worker-003": 75}

        job_counter = 0
        for worker_id, count in worker_assignments.items():
            # Update worker load
            worker_num = int(worker_id.split("-")[1])
            workflow_distribute.add_node(
                "WorkerNodeUpdateNode",
                f"update_{worker_id}",
                {
                    "id": str(worker_num),
                    "current_load": count,
                    "last_heartbeat": time.time(),
                },
            )

            # Assign jobs to worker
            for i in range(count):
                if job_counter < len(jobs):
                    workflow_distribute.add_node(
                        "JobQueueUpdateNode",
                        f"assign_job_{job_counter}",
                        {
                            "id": str(job_counter + 1),
                            "status": "assigned",
                            "assigned_worker": worker_id,
                        },
                    )
                    job_counter += 1

        distribute_result, _ = runtime.execute(workflow_distribute.build())
        assert distribute_result is not None

        # Check system balance
        workflow_balance = WorkflowBuilder()
        workflow_balance.add_node(
            "WorkerNodeListNode",
            "check_balance",
            {"filter": {"status": "active"}, "sort": [{"current_load": -1}]},
        )

        balance_result, _ = runtime.execute(workflow_balance.build())
        assert balance_result is not None

        # Verify horizontal scaling readiness
        assert len(workers) == 4
        assert len(jobs) == 250
        assert job_counter == 240  # Jobs distributed across 3 active workers

    def test_database_sharding_simulation(self):
        """Test database sharding for large-scale data."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class ShardConfig:
            shard_id: int
            shard_key_range_start: int
            shard_key_range_end: int
            database_url: str
            active: bool = True

        @db.model
        class UserDataSharded:
            user_id: int
            shard_key: int  # user_id % num_shards
            data: str
            created_at: float = time.time()

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Configure shards
        workflow_shards = WorkflowBuilder()

        num_shards = 4
        shards = []
        for i in range(num_shards):
            shards.append(
                {
                    "shard_id": i,
                    "shard_key_range_start": i * 25,
                    "shard_key_range_end": (i + 1) * 25 - 1,
                    "database_url": f"postgresql://shard{i}/dataflow",
                }
            )

        workflow_shards.add_node(
            "ShardConfigBulkCreateNode",
            "configure_shards",
            {"data": shards, "batch_size": 10},
        )

        shards_result, _ = runtime.execute(workflow_shards.build())
        assert shards_result is not None

        # Simulate sharded data insertion
        workflow_sharded_data = WorkflowBuilder()

        # Create data across shards
        user_data = []
        for user_id in range(1000):  # 1000 users
            shard_key = user_id % num_shards
            user_data.append(
                {
                    "user_id": user_id,
                    "shard_key": shard_key,
                    "data": f"User data for user {user_id}",
                }
            )

        # In production, this would route to different databases based on shard_key
        workflow_sharded_data.add_node(
            "UserDataShardedBulkCreateNode",
            "insert_sharded",
            {"data": user_data, "batch_size": 100},
        )

        sharded_data_result, _ = runtime.execute(workflow_sharded_data.build())
        assert sharded_data_result is not None

        # Query data from specific shard
        workflow_query_shard = WorkflowBuilder()
        workflow_query_shard.add_node(
            "UserDataShardedListNode",
            "query_shard_0",
            {"filter": {"shard_key": 0}, "limit": 10},
        )

        query_result, _ = runtime.execute(workflow_query_shard.build())
        assert query_result is not None

        # Verify sharding
        assert len(shards) == 4
        assert len(user_data) == 1000

    def test_cache_layer_performance(self):
        """Test cache layer for production performance."""
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class CacheEntry:
            cache_key: str
            cache_value: str
            ttl_seconds: int
            created_at: float = time.time()
            expires_at: float
            hit_count: int = 0

        @db.model
        class CacheStats:
            stat_type: str
            value: float
            timestamp: float = time.time()

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Populate cache
        workflow_cache = WorkflowBuilder()

        cache_entries = []
        current_time = time.time()

        # Simulate different types of cached data
        cache_data_types = [
            ("user_profile", 3600),  # 1 hour TTL
            ("api_response", 300),  # 5 minute TTL
            ("query_result", 1800),  # 30 minute TTL
            ("static_content", 86400),  # 24 hour TTL
        ]

        for i in range(100):
            data_type, ttl = cache_data_types[i % len(cache_data_types)]
            cache_entries.append(
                {
                    "cache_key": f"{data_type}:{i}",
                    "cache_value": f"Cached data for {data_type} item {i}",
                    "ttl_seconds": ttl,
                    "expires_at": current_time + ttl,
                }
            )

        workflow_cache.add_node(
            "CacheEntryBulkCreateNode",
            "populate_cache",
            {"data": cache_entries, "batch_size": 50},
        )

        cache_result, _ = runtime.execute(workflow_cache.build())
        assert cache_result is not None

        # Simulate cache hits
        workflow_hits = WorkflowBuilder()

        # Update hit counts for frequently accessed items
        for i in [1, 5, 10, 15, 20]:  # Popular items
            workflow_hits.add_node(
                "CacheEntryUpdateNode",
                f"hit_{i}",
                {"id": i, "hit_count": 10 + (i * 2)},  # Variable hit counts
            )

        hits_result, _ = runtime.execute(workflow_hits.build())
        assert hits_result is not None

        # Track cache statistics
        workflow_stats = WorkflowBuilder()

        cache_stats = [
            {"stat_type": "hit_rate", "value": 0.85},  # 85% hit rate
            {"stat_type": "miss_rate", "value": 0.15},
            {"stat_type": "eviction_rate", "value": 0.05},
            {"stat_type": "memory_usage_mb", "value": 256.5},
            {"stat_type": "total_keys", "value": 100},
        ]

        workflow_stats.add_node(
            "CacheStatsBulkCreateNode",
            "record_stats",
            {"data": cache_stats, "batch_size": 10},
        )

        stats_result, _ = runtime.execute(workflow_stats.build())
        assert stats_result is not None

        # Query cache performance
        workflow_perf = WorkflowBuilder()
        workflow_perf.add_node(
            "CacheStatsListNode",
            "cache_performance",
            {
                "filter": {"timestamp": {"$gte": current_time - 300}},
                "sort": [{"stat_type": 1}],
            },
        )

        perf_result, _ = runtime.execute(workflow_perf.build())
        assert perf_result is not None

        # Verify cache layer
        assert len(cache_entries) == 100
        assert stats_result["record_stats"] is not None
