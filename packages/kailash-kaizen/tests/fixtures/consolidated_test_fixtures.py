"""
Consolidated Test Fixtures for Kaizen Framework - All Test Tiers

This module provides standardized, optimized test fixtures for all three test tiers:
- Tier 1 (Unit): Fast, isolated, mocking allowed
- Tier 2 (Integration): Real services, NO MOCKING, <5s
- Tier 3 (E2E): Complete workflows, NO MOCKING, <10s

Eliminates duplication and ensures consistent test data across the entire test suite.
Based on 3-tier testing strategy with real infrastructure requirements.
"""

import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from kailash.runtime.local import LocalRuntime

# Core SDK imports
from kailash.workflow.builder import WorkflowBuilder

# Kaizen imports
try:
    from kaizen.core.config import KaizenConfig
    from kaizen.core.framework import Kaizen

    KAIZEN_AVAILABLE = True
except ImportError:
    KAIZEN_AVAILABLE = False

# Infrastructure imports
try:
    import sys

    sys.path.append("")
    from docker_config import (
        DATABASE_CONFIG,
        MYSQL_CONFIG,
        OLLAMA_CONFIG,
        REDIS_CONFIG,
        get_postgres_connection_string,
        get_redis_connection_params,
        is_ollama_available,
        is_postgres_available,
        is_redis_available,
    )

    INFRASTRUCTURE_AVAILABLE = True
except ImportError:
    INFRASTRUCTURE_AVAILABLE = False


@dataclass
class TestScenario:
    """Standardized test scenario definition."""

    name: str
    description: str
    tier: int  # 1=Unit, 2=Integration, 3=E2E
    inputs: Dict[str, Any]
    expected_outputs: List[str]
    timeout_seconds: float
    requires_memory: bool = False
    requires_docker: bool = False


class ConsolidatedTestFixtures:
    """
    Consolidated test fixtures providing consistent test data across all tiers.

    Design Principles:
    - Single source of truth for test data
    - Tier-appropriate configurations
    - Reusable across unit/integration/e2e tests
    - Performance optimized for each tier
    """

    def __init__(self):
        self._temp_dirs = []
        self._scenarios = {}
        self._configurations = {}
        self._setup_scenarios()
        self._setup_configurations()

    def cleanup(self):
        """Clean up temporary resources."""
        for temp_dir in self._temp_dirs:
            try:
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    # ============================================================================
    # TIER 1 (UNIT) FIXTURES - Fast, Isolated, Mocking Allowed
    # ============================================================================

    @pytest.fixture
    def unit_kaizen_config(self) -> KaizenConfig:
        """Minimal Kaizen config for unit tests - optimized for speed."""
        if not KAIZEN_AVAILABLE:
            pytest.skip("Kaizen not available")

        return KaizenConfig(
            debug=True,
            memory_enabled=False,  # No memory for unit tests
            optimization_enabled=False,  # No optimization for unit tests
            monitoring_enabled=False,  # No monitoring for unit tests
            cache_enabled=False,  # No caching for unit tests
            signature_validation=True,  # Keep validation for unit tests
            # Performance optimizations for unit tests
            lazy_loading=True,
            startup_timeout_seconds=1,  # Very short timeout
            max_concurrent_operations=1,  # Minimal concurrency
        )

    @pytest.fixture
    def unit_performance_config(self) -> Dict[str, Any]:
        """Performance configuration optimized for unit tests."""
        return {
            "max_execution_time_ms": 1000,  # 1 second limit
            "memory_limit_mb": 50,  # Low memory limit
            "enable_profiling": True,
            "fail_on_timeout": True,
            "log_performance_metrics": False,  # Reduce overhead
        }

    @pytest.fixture
    def unit_mock_providers(self) -> Dict[str, Any]:
        """Mock service providers for unit tests (Tier 1 only)."""
        from unittest.mock import MagicMock

        return {
            "database_mock": MagicMock(),
            "redis_mock": MagicMock(),
            "llm_mock": MagicMock(),
            "http_client_mock": MagicMock(),
            "file_system_mock": MagicMock(),
        }

    @pytest.fixture
    def unit_kaizen_framework(self, unit_kaizen_config) -> Kaizen:
        """Fast Kaizen framework instance for unit tests."""
        if not KAIZEN_AVAILABLE:
            pytest.skip("Kaizen not available")

        kaizen = Kaizen(config=unit_kaizen_config)
        yield kaizen
        kaizen.cleanup()

    @pytest.fixture
    def unit_test_signatures(self) -> Dict[str, str]:
        """Basic signatures for unit testing."""
        return {
            "simple_qa": "question -> answer",
            "multi_input": "context, question -> answer",
            "multi_output": "input -> result, confidence",
            "complex": "data, rules, context -> analysis, recommendations, confidence",
        }

    @pytest.fixture
    def unit_mock_responses(self) -> Dict[str, Any]:
        """Mock responses for unit tests (mocking allowed in Tier 1)."""
        return {
            "simple_answer": {"answer": "Unit test response", "confidence": 0.95},
            "analysis_result": {
                "analysis": {"findings": ["test finding"], "score": 0.8},
                "recommendations": ["test recommendation"],
                "confidence": 0.85,
            },
            "error_response": {"error": "Unit test error", "code": "TEST_ERROR"},
        }

    # ============================================================================
    # TIER 2 (INTEGRATION) FIXTURES - Real Services, NO MOCKING
    # ============================================================================

    @pytest.fixture
    def integration_kaizen_config(self) -> KaizenConfig:
        """Integration config with essential features enabled."""
        if not KAIZEN_AVAILABLE:
            pytest.skip("Kaizen not available")

        return KaizenConfig(
            debug=True,
            memory_enabled=True,  # Real memory for integration
            optimization_enabled=True,  # Real optimization
            monitoring_enabled=True,  # Real monitoring
            cache_enabled=True,  # Real caching
            signature_validation=True,
            # Integration test optimizations
            startup_timeout_seconds=5,
            max_concurrent_operations=3,
            retry_attempts=2,
            health_check_interval_seconds=10,
        )

    @pytest.fixture
    def integration_database_config(self) -> Dict[str, Any]:
        """Real database configuration for integration tests."""
        if not INFRASTRUCTURE_AVAILABLE:
            pytest.skip("Infrastructure configuration not available")
        return DATABASE_CONFIG.copy()

    @pytest.fixture
    def integration_redis_config(self) -> Dict[str, Any]:
        """Real Redis configuration for integration tests."""
        if not INFRASTRUCTURE_AVAILABLE:
            pytest.skip("Infrastructure configuration not available")
        return REDIS_CONFIG.copy()

    @pytest.fixture
    def integration_performance_config(self) -> Dict[str, Any]:
        """Performance configuration for integration tests."""
        return {
            "max_execution_time_ms": 5000,  # 5 second limit
            "memory_limit_mb": 200,  # Moderate memory limit
            "enable_profiling": True,
            "fail_on_timeout": True,
            "connection_pool_size": 5,
            "connection_timeout_seconds": 3,
        }

    @pytest.fixture
    def integration_real_database(self):
        """Real database connection for integration tests - NO MOCKING."""
        if not INFRASTRUCTURE_AVAILABLE or not is_postgres_available():
            pytest.skip("PostgreSQL not available for integration tests")

        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError:
            pytest.skip("psycopg2 not available")

        conn = psycopg2.connect(**DATABASE_CONFIG, cursor_factory=RealDictCursor)
        conn.autocommit = True

        yield conn
        conn.close()

    @pytest.fixture
    def integration_real_redis(self):
        """Real Redis connection for integration tests - NO MOCKING."""
        if not INFRASTRUCTURE_AVAILABLE or not is_redis_available():
            pytest.skip("Redis not available for integration tests")

        try:
            import redis
        except ImportError:
            pytest.skip("redis package not available")

        client = redis.Redis(**REDIS_CONFIG, decode_responses=True)

        # Test connection
        client.ping()

        yield client

        # Cleanup integration test keys
        try:
            test_keys = client.keys("integration_test:*")
            if test_keys:
                client.delete(*test_keys)
        except Exception:
            pass

    @pytest.fixture
    def integration_kaizen_framework(self, integration_kaizen_config) -> Kaizen:
        """Real Kaizen framework for integration tests."""
        if not KAIZEN_AVAILABLE:
            pytest.skip("Kaizen not available")

        kaizen = Kaizen(config=integration_kaizen_config)
        yield kaizen
        kaizen.cleanup()

    @pytest.fixture
    def integration_temp_storage(self) -> str:
        """Temporary storage for integration tests."""
        temp_dir = tempfile.mkdtemp(prefix="kaizen_integration_")
        self._temp_dirs.append(temp_dir)
        yield temp_dir

    @pytest.fixture
    def integration_test_data(self) -> Dict[str, Any]:
        """Real test data for integration testing."""
        return {
            "documents": [
                {
                    "id": "doc_1",
                    "content": "Integration test document 1",
                    "type": "text",
                },
                {
                    "id": "doc_2",
                    "content": "Integration test document 2",
                    "type": "text",
                },
            ],
            "conversations": [
                {
                    "id": "conv_1",
                    "messages": [
                        {"role": "user", "content": "Test question 1"},
                        {"role": "assistant", "content": "Test answer 1"},
                    ],
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "workflows": [
                {
                    "name": "integration_test_workflow",
                    "nodes": [
                        {
                            "type": "TextReaderNode",
                            "id": "reader",
                            "config": {"content": "test"},
                        },
                        {
                            "type": "TextWriterNode",
                            "id": "writer",
                            "config": {"path": "/tmp/test.txt"},
                        },
                    ],
                }
            ],
        }

    # ============================================================================
    # TIER 3 (E2E) FIXTURES - Complete Workflows, NO MOCKING
    # ============================================================================

    @pytest.fixture
    def e2e_kaizen_config(self) -> KaizenConfig:
        """Full enterprise config for E2E tests."""
        if not KAIZEN_AVAILABLE:
            pytest.skip("Kaizen not available")

        return KaizenConfig(
            debug=True,
            memory_enabled=True,
            optimization_enabled=True,
            monitoring_enabled=True,
            cache_enabled=True,
            signature_validation=True,
            # Enterprise features
            audit_trail_enabled=True,
            compliance_mode="enterprise",
            security_level="high",
            multi_agent_enabled=True,
            # E2E test optimizations
            startup_timeout_seconds=10,
            max_concurrent_operations=5,
            retry_attempts=3,
            health_check_interval_seconds=5,
            enable_distributed_processing=True,
        )

    @pytest.fixture
    def e2e_performance_config(self) -> Dict[str, Any]:
        """Performance configuration for E2E tests."""
        return {
            "max_execution_time_ms": 10000,  # 10 second limit
            "memory_limit_mb": 500,  # Higher memory limit
            "enable_profiling": True,
            "fail_on_timeout": True,
            "connection_pool_size": 10,
            "connection_timeout_seconds": 5,
            "enable_distributed_tracing": True,
            "collect_detailed_metrics": True,
        }

    @pytest.fixture
    def e2e_complete_infrastructure(self):
        """Complete infrastructure setup for E2E tests - NO MOCKING."""
        if not INFRASTRUCTURE_AVAILABLE:
            pytest.skip("Infrastructure configuration not available")

        infrastructure = {
            "postgres_available": is_postgres_available(),
            "redis_available": is_redis_available(),
            "ollama_available": is_ollama_available(),
        }

        # Ensure critical services are available
        if not infrastructure["postgres_available"]:
            pytest.skip("PostgreSQL required for E2E tests")
        if not infrastructure["redis_available"]:
            pytest.skip("Redis required for E2E tests")

        connections = {}

        # Setup PostgreSQL connection
        if infrastructure["postgres_available"]:
            try:
                import psycopg2

                conn = psycopg2.connect(**DATABASE_CONFIG)
                conn.autocommit = True
                connections["postgres"] = conn
            except ImportError:
                pytest.skip("psycopg2 not available")

        # Setup Redis connection
        if infrastructure["redis_available"]:
            try:
                import redis

                client = redis.Redis(**REDIS_CONFIG)
                client.ping()
                connections["redis"] = client
            except ImportError:
                pytest.skip("redis package not available")

        # Setup Ollama connection (optional)
        if infrastructure["ollama_available"]:
            try:
                import httpx

                connections["ollama"] = {
                    "base_url": OLLAMA_CONFIG["base_url"],
                    "client": httpx.Client(base_url=OLLAMA_CONFIG["base_url"]),
                }
            except ImportError:
                pass

        yield connections

        # Cleanup all connections
        for service, conn in connections.items():
            try:
                if service == "postgres":
                    conn.close()
                elif service == "redis":
                    # Cleanup E2E test keys
                    test_keys = conn.keys("e2e_test:*")
                    if test_keys:
                        conn.delete(*test_keys)
                elif service == "ollama" and "client" in conn:
                    conn["client"].close()
            except Exception:
                pass

    @pytest.fixture
    def e2e_kaizen_framework(self, e2e_kaizen_config) -> Kaizen:
        """Full enterprise Kaizen framework for E2E tests."""
        if not KAIZEN_AVAILABLE:
            pytest.skip("Kaizen not available")

        kaizen = Kaizen(config=e2e_kaizen_config)

        # Initialize enterprise features for E2E
        try:
            kaizen.initialize_enterprise_features()
        except AttributeError:
            pass  # Method may not exist yet

        yield kaizen

        # Cleanup enterprise resources
        try:
            kaizen.cleanup_enterprise_resources()
        except AttributeError:
            pass
        kaizen.cleanup()

    @pytest.fixture
    def e2e_complete_scenarios(self) -> List[TestScenario]:
        """Complete E2E test scenarios."""
        return [
            TestScenario(
                name="document_processing_pipeline",
                description="Complete document processing from ingestion to analysis",
                tier=3,
                inputs={
                    "documents": ["doc1.txt", "doc2.txt"],
                    "processing_rules": ["extract_entities", "analyze_sentiment"],
                    "output_format": "structured_json",
                },
                expected_outputs=[
                    "processed_documents",
                    "analysis_report",
                    "audit_trail",
                ],
                timeout_seconds=10.0,
                requires_memory=True,
                requires_docker=True,
            ),
            TestScenario(
                name="multi_agent_collaboration",
                description="Multiple agents collaborating on complex task",
                tier=3,
                inputs={
                    "task": "Research and analyze market trends",
                    "agent_roles": ["researcher", "analyst", "reporter"],
                    "collaboration_mode": "sequential",
                },
                expected_outputs=[
                    "research_findings",
                    "analysis_report",
                    "final_recommendations",
                ],
                timeout_seconds=10.0,
                requires_memory=True,
                requires_docker=False,
            ),
        ]

    @pytest.fixture
    def e2e_enterprise_data(self) -> Dict[str, Any]:
        """Enterprise-scale test data for E2E scenarios."""
        return {
            "large_dataset": {
                "customers": [{"id": i, "name": f"Customer {i}"} for i in range(1000)],
                "transactions": [{"id": i, "amount": i * 10.5} for i in range(5000)],
                "products": [{"id": i, "name": f"Product {i}"} for i in range(500)],
            },
            "enterprise_workflows": [
                {
                    "name": "customer_onboarding",
                    "steps": [
                        "identity_verification",
                        "compliance_check",
                        "account_creation",
                    ],
                    "sla_minutes": 15,
                },
                {
                    "name": "transaction_processing",
                    "steps": ["validation", "fraud_check", "execution", "notification"],
                    "sla_seconds": 30,
                },
            ],
            "compliance_requirements": {
                "gdpr": True,
                "sox": True,
                "audit_trail": "full",
                "data_retention_days": 2555,
            },
        }

    # ============================================================================
    # CROSS-TIER UTILITIES
    # ============================================================================

    @pytest.fixture
    def core_sdk_runtime(self) -> LocalRuntime:
        """Core SDK runtime for all test tiers."""
        return LocalRuntime()

    @pytest.fixture
    def core_sdk_workflow_builder(self) -> WorkflowBuilder:
        """Core SDK workflow builder for all test tiers."""
        return WorkflowBuilder()

    @pytest.fixture
    def tier_performance_monitor(self):
        """Performance monitoring across all test tiers."""

        class TierPerformanceMonitor:
            def __init__(self):
                self.measurements = {}
                self.tier_limits = {
                    "unit": 1000,  # 1 second
                    "integration": 5000,  # 5 seconds
                    "e2e": 10000,  # 10 seconds
                }

            @contextmanager
            def measure(self, operation: str, tier: str = "unit"):
                start_time = time.perf_counter()
                try:
                    yield
                finally:
                    end_time = time.perf_counter()
                    duration_ms = (end_time - start_time) * 1000
                    self.measurements[operation] = {
                        "duration_ms": duration_ms,
                        "tier": tier,
                        "limit_ms": self.tier_limits.get(tier, 1000),
                    }

            def assert_tier_performance(self, operation: str):
                """Assert operation meets tier performance requirements."""
                if operation not in self.measurements:
                    raise ValueError(f"No measurement found for {operation}")

                measurement = self.measurements[operation]
                actual = measurement["duration_ms"]
                limit = measurement["limit_ms"]
                tier = measurement["tier"]

                assert actual <= limit, (
                    f"Tier {tier} operation '{operation}' took {actual:.2f}ms, "
                    f"exceeding {tier} limit of {limit}ms"
                )

            def get_tier_summary(self) -> Dict[str, Any]:
                """Get performance summary by tier."""
                summary = {"unit": [], "integration": [], "e2e": []}
                for op, data in self.measurements.items():
                    tier = data["tier"]
                    if tier in summary:
                        summary[tier].append(
                            {
                                "operation": op,
                                "duration_ms": data["duration_ms"],
                                "within_limit": data["duration_ms"] <= data["limit_ms"],
                            }
                        )
                return summary

        return TierPerformanceMonitor()

    @pytest.fixture
    def standardized_test_data_factory(self):
        """Factory for creating standardized test data across tiers."""

        class TestDataFactory:
            def create_agent_config(self, tier: str) -> Dict[str, Any]:
                """Create agent config optimized for specific tier."""
                base_config = {
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.7,
                    "max_tokens": 1000,
                }

                tier_optimizations = {
                    "unit": {
                        "timeout": 5,
                        "max_tokens": 100,  # Smaller for unit tests
                        "stream": False,
                    },
                    "integration": {
                        "timeout": 15,
                        "max_tokens": 500,
                        "retry_attempts": 2,
                    },
                    "e2e": {
                        "timeout": 30,
                        "max_tokens": 2000,
                        "retry_attempts": 3,
                        "enable_monitoring": True,
                    },
                }

                base_config.update(tier_optimizations.get(tier, {}))
                return base_config

            def create_test_scenario(
                self, tier: str, scenario_type: str
            ) -> TestScenario:
                """Create test scenarios optimized for specific tier."""
                scenarios = {
                    "unit": {
                        "simple": TestScenario(
                            name="unit_simple_test",
                            description="Fast unit test scenario",
                            tier=1,
                            inputs={"input": "test"},
                            expected_outputs=["output"],
                            timeout_seconds=1.0,
                        )
                    },
                    "integration": {
                        "database": TestScenario(
                            name="integration_database_test",
                            description="Database integration test",
                            tier=2,
                            inputs={"query": "SELECT 1", "connection": "postgres"},
                            expected_outputs=["results", "metadata"],
                            timeout_seconds=5.0,
                            requires_memory=True,
                        )
                    },
                    "e2e": {
                        "complete": TestScenario(
                            name="e2e_complete_workflow",
                            description="Complete E2E workflow test",
                            tier=3,
                            inputs={"workflow_type": "full_pipeline"},
                            expected_outputs=["results", "audit_trail", "metrics"],
                            timeout_seconds=10.0,
                            requires_memory=True,
                            requires_docker=True,
                        )
                    },
                }

                return scenarios.get(tier, {}).get(scenario_type)

        return TestDataFactory()

    @pytest.fixture
    def performance_thresholds(self) -> Dict[str, float]:
        """Enhanced performance thresholds for all test tiers."""
        return {
            # Core tier limits (strict)
            "unit_test_max_ms": 1000,
            "integration_test_max_ms": 5000,
            "e2e_test_max_ms": 10000,
            # Component-specific limits
            "framework_init_max_ms": 100,
            "signature_creation_max_ms": 10,
            "agent_creation_max_ms": 200,
            "memory_operation_max_ms": 100,
            # Infrastructure operation limits
            "database_connection_max_ms": 500,
            "redis_operation_max_ms": 50,
            "ollama_model_load_max_ms": 2000,
            "workflow_compilation_max_ms": 200,
            "workflow_execution_max_ms": 5000,
            # Tier-specific component limits
            "unit_agent_creation_max_ms": 50,  # Faster for unit tests
            "integration_agent_creation_max_ms": 200,  # Standard
            "e2e_agent_creation_max_ms": 500,  # Allows for full setup
            # Memory limits (MB)
            "unit_memory_limit_mb": 50,
            "integration_memory_limit_mb": 200,
            "e2e_memory_limit_mb": 500,
        }

    def _setup_scenarios(self):
        """Setup predefined test scenarios."""
        # Unit test scenarios
        self._scenarios["unit_signature_creation"] = TestScenario(
            name="unit_signature_creation",
            description="Test signature creation in isolation",
            tier=1,
            inputs={"pattern": "input -> output", "name": "test_signature"},
            expected_outputs=["signature_object"],
            timeout_seconds=1.0,
        )

        # Integration test scenarios
        self._scenarios["integration_workflow_execution"] = TestScenario(
            name="integration_workflow_execution",
            description="Test workflow execution with real runtime",
            tier=2,
            inputs={"workflow_nodes": ["TextReaderNode", "TextWriterNode"]},
            expected_outputs=["execution_results", "run_id"],
            timeout_seconds=5.0,
            requires_memory=True,
        )

        # E2E test scenarios
        self._scenarios["e2e_complete_pipeline"] = TestScenario(
            name="e2e_complete_pipeline",
            description="Complete end-to-end pipeline test",
            tier=3,
            inputs={"pipeline_type": "document_analysis", "enterprise_features": True},
            expected_outputs=["pipeline_results", "audit_trail", "compliance_report"],
            timeout_seconds=10.0,
            requires_memory=True,
            requires_docker=True,
        )

    def _setup_configurations(self):
        """Setup configuration presets."""
        self._configurations = {
            "minimal": {
                "debug": True,
                "memory_enabled": False,
                "optimization_enabled": False,
                "monitoring_enabled": False,
                "cache_enabled": False,
            },
            "standard": {
                "debug": True,
                "memory_enabled": True,
                "optimization_enabled": True,
                "monitoring_enabled": True,
                "signature_programming_enabled": True,
            },
            "enterprise": {
                "debug": True,
                "memory_enabled": True,
                "optimization_enabled": True,
                "enterprise_features_enabled": True,
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "monitoring_enabled": True,
                "security_level": "high",
                "multi_agent_enabled": True,
                "transparency_enabled": True,
            },
            "performance_optimized": {
                "debug": False,  # Reduced logging for performance
                "memory_enabled": True,
                "optimization_enabled": True,
                "monitoring_enabled": False,  # Disable for pure performance
                "cache_enabled": True,
                "signature_programming_enabled": True,
            },
        }

    def get_scenario(self, name: str) -> Optional[TestScenario]:
        """Get a test scenario by name."""
        return self._scenarios.get(name)

    def get_configuration(self, name: str) -> Dict[str, Any]:
        """Get a configuration preset by name."""
        return self._configurations.get(name, {})


# ============================================================================
# SPECIALIZED FIXTURES FOR SPECIFIC TEST CATEGORIES
# ============================================================================


class InfrastructureTestFixtures:
    """Specialized fixtures for infrastructure testing."""

    @pytest.fixture
    def infrastructure_health_check(self):
        """Health check fixture for all infrastructure services."""

        class HealthChecker:
            def __init__(self):
                self.services = {
                    "postgres": (
                        is_postgres_available() if INFRASTRUCTURE_AVAILABLE else False
                    ),
                    "redis": (
                        is_redis_available() if INFRASTRUCTURE_AVAILABLE else False
                    ),
                    "ollama": (
                        is_ollama_available() if INFRASTRUCTURE_AVAILABLE else False
                    ),
                }

            def require_service(self, service: str):
                """Require a specific service to be available."""
                if not self.services.get(service, False):
                    pytest.skip(f"{service} service not available")

            def require_tier_services(self, tier: str):
                """Require services based on test tier."""
                tier_requirements = {
                    "unit": [],  # No services required
                    "integration": ["postgres", "redis"],
                    "e2e": ["postgres", "redis"],  # Ollama optional
                }

                for service in tier_requirements.get(tier, []):
                    self.require_service(service)

            def get_available_services(self) -> List[str]:
                """Get list of available services."""
                return [
                    service for service, available in self.services.items() if available
                ]

        return HealthChecker()

    @pytest.fixture
    def infrastructure_cleanup(self):
        """Cleanup fixture for infrastructure resources."""
        cleanup_tasks = []

        def register_cleanup(task):
            cleanup_tasks.append(task)

        yield register_cleanup

        # Execute all cleanup tasks
        for task in cleanup_tasks:
            try:
                task()
            except Exception:
                pass  # Best effort cleanup


class PerformanceTestFixtures:
    """Specialized fixtures for performance testing."""

    @pytest.fixture
    def performance_monitor(self):
        """Performance monitoring context manager."""
        import time

        class PerfMonitor:
            def __init__(self):
                self.start_time = None
                self.end_time = None

            def __enter__(self):
                self.start_time = time.perf_counter()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.end_time = time.perf_counter()

            @property
            def elapsed_ms(self) -> float:
                if self.start_time and self.end_time:
                    return (self.end_time - self.start_time) * 1000
                return 0.0

        return PerfMonitor()

    @pytest.fixture
    def memory_monitor(self):
        """Memory usage monitoring."""
        try:
            import psutil

            class MemoryMonitor:
                def __init__(self):
                    self.process = psutil.Process()
                    self.baseline = None
                    self.peak = None

                def start(self):
                    self.baseline = self.process.memory_info().rss / 1024 / 1024

                def record_peak(self):
                    current = self.process.memory_info().rss / 1024 / 1024
                    if self.peak is None or current > self.peak:
                        self.peak = current

                def get_increase_mb(self) -> float:
                    if self.baseline and self.peak:
                        return self.peak - self.baseline
                    return 0.0

            return MemoryMonitor()
        except ImportError:
            pytest.skip("psutil not available for memory monitoring")


class ErrorTestFixtures:
    """Specialized fixtures for error testing."""

    @pytest.fixture
    def error_scenarios(self) -> Dict[str, Any]:
        """Error scenarios for robust testing."""
        return {
            "invalid_signatures": [
                "missing arrow",
                "input ->",
                "-> output",
                "input > output",
                "",
            ],
            "invalid_configs": [
                {"temperature": -1},
                {"temperature": 3.0},
                {"max_tokens": -100},
                {"timeout": 0},
            ],
            "network_errors": [
                {"base_url": "http://invalid-host:9999"},
                {"timeout": 0.001},
            ],
        }


# ============================================================================
# GLOBAL FIXTURE INSTANCES
# ============================================================================

# Create global fixture instances
consolidated_fixtures = ConsolidatedTestFixtures()
infrastructure_fixtures = InfrastructureTestFixtures()
performance_fixtures = PerformanceTestFixtures()
error_fixtures = ErrorTestFixtures()


# Cleanup registration
@pytest.fixture(scope="session", autouse=True)
def global_cleanup():
    """Global cleanup for all test sessions."""
    yield
    consolidated_fixtures.cleanup()


# Export main fixture classes and functions
__all__ = [
    "ConsolidatedTestFixtures",
    "InfrastructureTestFixtures",
    "PerformanceTestFixtures",
    "ErrorTestFixtures",
    "TestScenario",
    "consolidated_fixtures",
    "infrastructure_fixtures",
    "performance_fixtures",
    "error_fixtures",
]
