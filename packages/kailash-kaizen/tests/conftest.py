"""
Test configuration and fixtures for Kaizen framework.

Provides shared fixtures and configuration for comprehensive 3-tier testing strategy:
- Tier 1 (Unit): Fast, isolated tests with mocks for external dependencies
- Tier 2 (Integration): Real Core SDK services, NO MOCKING
- Tier 3 (E2E): Complete workflows with real infrastructure
"""

import os

# CRITICAL: Patch MockProvider BEFORE any other imports
# This must happen at module level to catch all provider instantiations
import sys

# Load .env before checking USE_REAL_PROVIDERS
from dotenv import load_dotenv

load_dotenv()

# Check if we should use real providers (for E2E/integration tests)
use_real_providers = os.getenv("USE_REAL_PROVIDERS", "").lower() == "true"

if not use_real_providers:
    # Only patch for unit tests
    try:
        # Import and patch BEFORE anything else
        import kailash.nodes.ai.ai_providers as ai_providers_module
        from tests.utils.kaizen_mock_provider import KaizenMockProvider

        # Store original for potential restore
        _original_mock_provider = ai_providers_module.PROVIDERS.get("mock")

        # CRITICAL: Patch the PROVIDERS registry - this is how providers are instantiated
        ai_providers_module.PROVIDERS["mock"] = KaizenMockProvider

        # Also patch the class itself for direct imports
        ai_providers_module.MockProvider = KaizenMockProvider

        # Update in sys.modules cache
        if "kailash.nodes.ai.ai_providers" in sys.modules:
            sys.modules["kailash.nodes.ai.ai_providers"].PROVIDERS[
                "mock"
            ] = KaizenMockProvider
            sys.modules["kailash.nodes.ai.ai_providers"].MockProvider = (
                KaizenMockProvider
            )

        print(
            "✅ Patched Core SDK PROVIDERS['mock'] with KaizenMockProvider at module level"
        )

        # NOTE: Previously needed to monkey-patch LLMAgentNode._mock_llm_response due to
        # hardcoded path in Core SDK that bypassed the provider registry.
        # This has been FIXED in Core SDK (llm_agent.py lines 665 and 724), so the
        # registry patching above is now sufficient.
        # All providers (including "mock") now use the provider registry consistently.

    except Exception as e:
        print(f"⚠️  Failed to patch MockProvider at module level: {e}")
        import traceback

        traceback.print_exc()
else:
    print("✅ Skipping MockProvider patching at module level (USE_REAL_PROVIDERS=true)")

import json
import logging
import tempfile
import time
from typing import Any, Dict, List, Optional

import pytest
from kaizen.core.config import KaizenConfig
from kaizen.core.framework import Kaizen

# Import new BaseAgent architecture (Phase 1)
from kaizen.signatures import InputField, OutputField, Signature

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import real LLM providers for integration/E2E tests


# Import infrastructure configuration from parent SDK
try:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).parent.parent.parent.parent / "tests" / "utils"))
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


# Test logging configuration
logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def performance_tracker():
    """Fixture to track performance metrics during tests."""

    class PerformanceTracker:
        def __init__(self):
            self.measurements = {}

        def start_timer(self, operation: str):
            """Start timing an operation."""
            self.measurements[operation] = {"start": time.time()}

        def end_timer(self, operation: str) -> float:
            """End timing and return duration in milliseconds."""
            if operation not in self.measurements:
                raise ValueError(f"Timer for '{operation}' was not started")

            duration = (time.time() - self.measurements[operation]["start"]) * 1000
            self.measurements[operation]["duration_ms"] = duration
            return duration

        def assert_performance(self, operation: str, max_duration_ms: float):
            """Assert that operation completed within time limit."""
            if (
                operation not in self.measurements
                or "duration_ms" not in self.measurements[operation]
            ):
                raise ValueError(f"No timing data for operation '{operation}'")

            actual_duration = self.measurements[operation]["duration_ms"]
            assert actual_duration <= max_duration_ms, (
                f"Operation '{operation}' took {actual_duration:.2f}ms, "
                f"exceeding limit of {max_duration_ms}ms"
            )

        def get_measurement(self, operation: str) -> Optional[float]:
            """Get duration measurement for an operation."""
            if (
                operation in self.measurements
                and "duration_ms" in self.measurements[operation]
            ):
                return self.measurements[operation]["duration_ms"]
            return None

    return PerformanceTracker()


# Tier 1 (Unit) Fixtures - Fast, isolated with minimal setup
@pytest.fixture
def default_kaizen_config():
    """Default KaizenConfig for unit tests."""
    return KaizenConfig()


@pytest.fixture
def enterprise_kaizen_config():
    """Enterprise KaizenConfig with all features enabled."""
    return KaizenConfig(
        debug=True,
        memory_enabled=True,
        optimization_enabled=True,
        security_config={"encryption": True, "auth_enabled": True},
        monitoring_enabled=True,
        cache_enabled=True,
        multi_modal_enabled=True,
        signature_validation=True,
        auto_optimization=True,
    )


@pytest.fixture
def basic_agent_config():
    """Basic agent configuration for testing."""
    return {
        "model": "gpt-3.5-turbo",
        "temperature": 0.7,
        "max_tokens": 1000,
        "timeout": 30,
    }


@pytest.fixture
def advanced_agent_config():
    """Advanced agent configuration with enterprise features."""
    return {
        "model": "gpt-4",
        "temperature": 0.3,
        "max_tokens": 2000,
        "timeout": 60,
        "optimization_enabled": True,
        "memory_enabled": True,
        "custom_param": "test_value",
    }


@pytest.fixture
def mock_signature():
    """Mock Signature implementation for unit testing."""

    class MockSignature(Signature):
        prompt: str = InputField(desc="Input prompt")
        temperature: float = InputField(desc="Temperature setting", default=0.7)
        max_tokens: int = InputField(desc="Max tokens", default=1000)

        response: str = OutputField(desc="Response text")
        metadata: dict = OutputField(desc="Response metadata")

    return MockSignature()


# Tier 2 (Integration) Fixtures - Real Core SDK services
@pytest.fixture
def real_kaizen_framework():
    """Real Kaizen framework instance for integration testing."""
    kaizen = Kaizen(debug=True)
    yield kaizen
    # Cleanup
    kaizen._agents.clear()
    kaizen._signatures.clear()


@pytest.fixture
def real_workflow_builder():
    """Real WorkflowBuilder instance for integration testing."""
    return WorkflowBuilder()


@pytest.fixture
def real_local_runtime():
    """Real LocalRuntime instance for integration testing."""
    return LocalRuntime()


@pytest.fixture
def integration_test_data():
    """Test data for integration testing with real services."""
    return {
        "simple_prompt": "Hello, how are you?",
        "complex_prompt": "Analyze the following data and provide insights: [test data]",
        "test_parameters": {"temperature": 0.5, "max_tokens": 500},
        "expected_response_keys": ["response", "metadata"],
    }


# Tier 3 (E2E) Fixtures - Complete scenarios with real infrastructure
@pytest.fixture
def e2e_kaizen_setup():
    """Complete Kaizen setup for E2E testing."""
    # Initialize with enterprise features for comprehensive testing
    kaizen = Kaizen(
        memory_enabled=True,
        optimization_enabled=True,
        monitoring_enabled=True,
        debug=True,
    )

    # Pre-create common agent configurations
    agent_configs = {
        "primary_agent": {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 1000,
        },
        "secondary_agent": {
            "model": "gpt-3.5-turbo",
            "temperature": 0.3,
            "max_tokens": 500,
        },
    }

    yield kaizen, agent_configs

    # Cleanup
    kaizen._agents.clear()
    kaizen._signatures.clear()


@pytest.fixture
def e2e_workflow_scenarios():
    """Complete workflow scenarios for E2E testing."""
    return {
        "single_agent_workflow": {
            "description": "Single agent processing a prompt",
            "agents": ["processor"],
            "inputs": {"prompt": "Generate a short story"},
            "expected_outputs": ["response"],
        },
        "multi_agent_workflow": {
            "description": "Multi-agent coordination workflow",
            "agents": ["analyzer", "generator", "validator"],
            "inputs": {"data": "test data for analysis"},
            "expected_outputs": ["analysis", "generated_content", "validation_result"],
        },
        "signature_based_workflow": {
            "description": "Workflow using signature-based programming",
            "signature_name": "content_processor",
            "inputs": {"content": "test content", "task": "summarize"},
            "expected_outputs": ["summary", "metadata"],
        },
    }


# Error simulation fixtures for robust testing
@pytest.fixture
def error_scenarios():
    """Error scenarios for testing error handling and recovery."""
    return {
        "invalid_config": {
            "model": None,  # Invalid model
            "temperature": 2.0,  # Invalid temperature > 1
            "max_tokens": -1,  # Invalid negative tokens
        },
        "missing_required_params": {},
        "duplicate_agent_id": "duplicate_test_agent",
        "nonexistent_agent_id": "nonexistent_agent_12345",
        "timeout_config": {
            "model": "gpt-3.5-turbo",
            "timeout": 0.001,  # Very short timeout to trigger timeout errors
        },
    }


# Performance baseline constants
PERFORMANCE_BASELINES = {
    "framework_init_ms": 100,  # Framework initialization < 100ms
    "agent_creation_ms": 50,  # Agent creation < 50ms
    "workflow_compilation_ms": 200,  # Workflow compilation < 200ms
    "signature_validation_ms": 10,  # Signature validation < 10ms
}


@pytest.fixture
def performance_baselines():
    """Performance baseline constants for testing."""
    return PERFORMANCE_BASELINES


# ============================================================================
# INFRASTRUCTURE FIXTURES - Database and Docker Services
# ============================================================================


@pytest.fixture(scope="session")
def postgres_connection_string():
    """PostgreSQL connection string for integration/e2e tests."""
    if not INFRASTRUCTURE_AVAILABLE or not is_postgres_available():
        pytest.skip("PostgreSQL not available")
    return get_postgres_connection_string()


@pytest.fixture(scope="session")
def postgres_connection_config():
    """PostgreSQL connection configuration for integration/e2e tests."""
    if not INFRASTRUCTURE_AVAILABLE or not is_postgres_available():
        pytest.skip("PostgreSQL not available")
    return DATABASE_CONFIG


@pytest.fixture(scope="session")
def redis_connection_config():
    """Redis configuration for integration/e2e tests."""
    if not INFRASTRUCTURE_AVAILABLE or not is_redis_available():
        pytest.skip("Redis not available")
    return REDIS_CONFIG


@pytest.fixture(scope="session")
def redis_connection_params():
    """Redis connection parameters for integration/e2e tests."""
    if not INFRASTRUCTURE_AVAILABLE or not is_redis_available():
        pytest.skip("Redis not available")
    return get_redis_connection_params()


@pytest.fixture(scope="session")
def mysql_connection_config():
    """MySQL connection configuration for integration/e2e tests."""
    if not INFRASTRUCTURE_AVAILABLE:
        pytest.skip("Infrastructure configuration not available")
    return MYSQL_CONFIG


@pytest.fixture(scope="session")
def ollama_connection_config():
    """Ollama connection configuration for integration/e2e tests."""
    if not INFRASTRUCTURE_AVAILABLE or not is_ollama_available():
        pytest.skip("Ollama not available")
    return OLLAMA_CONFIG


@pytest.fixture(scope="function")
def docker_services():
    """Docker service management fixture for integration/e2e tests."""
    if not INFRASTRUCTURE_AVAILABLE:
        pytest.skip("Infrastructure configuration not available")

    class DockerServices:
        def __init__(self):
            self.postgres_available = is_postgres_available()
            self.redis_available = is_redis_available()
            self.ollama_available = is_ollama_available()

        def require_postgres(self):
            if not self.postgres_available:
                pytest.skip("PostgreSQL service not available")

        def require_redis(self):
            if not self.redis_available:
                pytest.skip("Redis service not available")

        def require_ollama(self):
            if not self.ollama_available:
                pytest.skip("Ollama service not available")

        def get_service_status(self):
            return {
                "postgres": self.postgres_available,
                "redis": self.redis_available,
                "ollama": self.ollama_available,
            }

    return DockerServices()


@pytest.fixture(scope="function")
def temp_storage():
    """Temporary storage directory for test files."""
    temp_dir = tempfile.mkdtemp(prefix="kaizen_test_")
    yield temp_dir

    # Cleanup
    import shutil

    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


# ============================================================================
# TIER-SPECIFIC DATABASE FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def integration_database_connection():
    """Real database connection for Tier 2 Integration tests."""
    if not INFRASTRUCTURE_AVAILABLE or not is_postgres_available():
        pytest.skip("PostgreSQL not available for integration tests")

    # Import here to avoid import errors if psycopg2 not available
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        pytest.skip("psycopg2 not available")

    conn = psycopg2.connect(
        host=DATABASE_CONFIG["host"],
        port=DATABASE_CONFIG["port"],
        database=DATABASE_CONFIG["database"],
        user=DATABASE_CONFIG["user"],
        password=DATABASE_CONFIG["password"],
        cursor_factory=RealDictCursor,
    )
    conn.autocommit = True

    yield conn

    # Cleanup
    conn.close()


@pytest.fixture(scope="function")
def integration_redis_connection():
    """Real Redis connection for Tier 2 Integration tests."""
    if not INFRASTRUCTURE_AVAILABLE or not is_redis_available():
        pytest.skip("Redis not available for integration tests")

    try:
        import redis
    except ImportError:
        pytest.skip("redis package not available")

    client = redis.Redis(**REDIS_CONFIG, decode_responses=True)

    yield client

    # Cleanup test keys
    try:
        test_keys = client.keys("kaizen_test:*")
        if test_keys:
            client.delete(*test_keys)
    except Exception:
        pass


@pytest.fixture(scope="function")
def e2e_database_setup(integration_database_connection):
    """Complete database setup for Tier 3 E2E tests."""
    conn = integration_database_connection
    cursor = conn.cursor()

    # Create test tables for E2E testing
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS kaizen_test_agents (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            config JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS kaizen_test_executions (
            id SERIAL PRIMARY KEY,
            agent_id INTEGER REFERENCES kaizen_test_agents(id),
            status VARCHAR(50) DEFAULT 'pending',
            results JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """
    )

    yield conn

    # Cleanup test tables
    cursor.execute("DROP TABLE IF EXISTS kaizen_test_executions CASCADE")
    cursor.execute("DROP TABLE IF EXISTS kaizen_test_agents CASCADE")


# Test markers and configuration
pytest_plugins = []


def _generate_mock_json_response(messages: List[Dict], **kwargs) -> Dict[str, Any]:
    """
    Generate realistic JSON responses based on message content.

    This function analyzes the user message to determine what JSON structure
    to return based on the requested output fields.
    """
    # Get the last user message
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    user_lower = user_message.lower()

    # Extract JSON format from system prompt if present
    json_format = {}
    if "```json" in user_message:
        try:
            json_start = user_message.index("```json") + 7
            json_end = user_message.index("```", json_start)
            json_str = user_message[json_start:json_end].strip()
            json_format = json.loads(json_str)
        except:
            pass

    # Generate response based on detected fields or patterns
    response_data = {}

    # Proposal generation (consensus building)
    if "proposal" in json_format:
        response_data["proposal"] = (
            "Implement automated code review checks with AI assistance"
        )
        response_data["reasoning"] = (
            "This approach combines automation with human oversight to improve efficiency while maintaining quality standards"
        )

    # Task delegation (supervisor-worker)
    elif "tasks" in json_format or ("task" in user_lower and "delegate" in user_lower):
        response_data["tasks"] = [
            {
                "task_id": "task_1",
                "description": "Process document 1",
                "assigned_to": "worker",
            },
            {
                "task_id": "task_2",
                "description": "Process document 2",
                "assigned_to": "worker",
            },
            {
                "task_id": "task_3",
                "description": "Process document 3",
                "assigned_to": "worker",
            },
        ]
        response_data["reasoning"] = (
            "Break work into parallel tasks for efficient processing"
        )

    # Review/voting
    elif "vote" in json_format:
        response_data["vote"] = "approve"
        response_data["feedback"] = "The proposal addresses key concerns effectively"
        response_data["confidence"] = "0.85"

    # Facilitation/consensus
    elif "decision" in json_format:
        response_data["decision"] = "ACCEPT"
        response_data["rationale"] = "Majority of reviewers approved the proposal"
        response_data["consensus_level"] = "0.75"

    # Worker task execution
    elif "result" in json_format:
        response_data["result"] = "Task completed successfully"
        response_data["status"] = "completed"
        response_data["details"] = "Processing completed with expected output"

    # Batch processing
    elif "results" in json_format and "items" in user_lower:
        response_data["results"] = [
            "Processed item 1",
            "Processed item 2",
            "Processed item 3",
        ]
        response_data["count"] = "3"

    # Policy parsing (compliance)
    elif "parsed_policies" in json_format:
        response_data["parsed_policies"] = [
            {
                "id": "policy_1",
                "name": "Security Policy",
                "rules": ["Rule 1", "Rule 2"],
            },
            {"id": "policy_2", "name": "Data Privacy", "rules": ["Rule 3", "Rule 4"]},
        ]
        response_data["policy_count"] = "2"

    # Compliance checking
    elif "compliant" in json_format:
        response_data["compliant"] = "true"
        response_data["violations"] = "[]"
        response_data["compliance_score"] = "1.0"

    # Chart generation
    elif "chart" in json_format:
        response_data["chart"] = "Bar chart showing sales trends"
        response_data["chart_type"] = "bar"
        response_data["insights"] = "Sales increased by 20% in Q3"

    # Document analysis
    elif "analysis" in json_format and "documents" in user_lower:
        response_data["analysis"] = (
            "The documents contain key information about market trends"
        )
        response_data["key_points"] = [
            "Market growth",
            "Customer preferences",
            "Competition analysis",
        ]
        response_data["summary"] = (
            "Comprehensive market analysis with actionable insights"
        )

    # Query decomposition (multi-hop RAG)
    elif "sub_questions" in json_format:
        response_data["sub_questions"] = [
            "What is the main topic?",
            "What are the key details?",
            "How do they relate?",
        ]
        response_data["reasoning"] = "Breaking complex question into manageable parts"

    # Source coordination (federated RAG)
    elif "sources" in json_format and "query" in user_lower:
        response_data["sources"] = ["source_1", "source_2", "source_3"]
        response_data["strategy"] = "parallel"
        response_data["reasoning"] = "Query multiple sources for comprehensive results"

    # Agentic RAG - strategy selection
    elif "strategy" in json_format:
        response_data["strategy"] = "semantic"
        response_data["reasoning"] = "Query requires semantic search for best results"

    # Agentic RAG - document retrieval
    elif "documents" in json_format:
        response_data["documents"] = [
            {"id": "doc1", "content": "Relevant document 1", "score": "0.95"},
            {"id": "doc2", "content": "Relevant document 2", "score": "0.85"},
        ]

    # Agentic RAG - quality assessment
    elif "quality_score" in json_format:
        response_data["quality_score"] = "0.9"
        response_data["sufficient"] = "true"
        response_data["feedback"] = "Documents are highly relevant"

    # Generic answer
    elif "answer" in json_format:
        response_data["answer"] = (
            "This is a comprehensive answer based on the provided context"
        )
        if "confidence" in json_format:
            response_data["confidence"] = "0.92"
        if "sources" in json_format:
            response_data["sources"] = ["doc1", "doc2"]

    # If no pattern matched, fill in the expected format with placeholder values
    if not response_data:
        for key, value in json_format.items():
            if isinstance(value, str):
                response_data[key] = f"Mock {key} value"
            elif isinstance(value, (int, float)):
                response_data[key] = value
            elif isinstance(value, bool):
                response_data[key] = True
            elif isinstance(value, list):
                response_data[key] = []
            elif isinstance(value, dict):
                response_data[key] = {}

    return response_data


def _patch_core_sdk_mock_provider():
    """
    Patch Core SDK's MockProvider to return realistic JSON responses.

    This replaces the MockProvider.chat method with one that understands
    signature-based JSON formats and returns appropriate structured data.
    """
    try:
        from kailash.nodes.ai import MockProvider

        # Store original chat method

        def enhanced_chat(
            self, messages: List[Dict[str, Any]], **kwargs
        ) -> Dict[str, Any]:
            """Enhanced chat method that returns proper JSON responses."""
            # Generate JSON response based on message content
            json_data = _generate_mock_json_response(messages, **kwargs)

            # Return in Core SDK's expected format
            return {
                "id": f"mock_{hash(str(messages))}",
                "content": json.dumps(json_data),
                "role": "assistant",
                "model": kwargs.get("model", "gpt-3.5-turbo"),
                "created": 1701234567,
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": len(json.dumps(json_data).split()),
                    "total_tokens": 100 + len(json.dumps(json_data).split()),
                },
                "metadata": {},
            }

        # Patch the method
        MockProvider.chat = enhanced_chat

    except ImportError:
        # Core SDK not available or MockProvider not found
        pass


def pytest_configure(config):
    """Configure pytest markers and settings."""
    import os

    # Check if we should use real providers (for E2E/integration tests)
    use_real_providers = os.getenv("USE_REAL_PROVIDERS", "").lower() == "true"

    if use_real_providers:
        print("✅ Using REAL LLM providers (mock patching DISABLED)")
        # Skip mock provider registration for E2E/integration tests
    else:
        # Register Kaizen mock provider BEFORE any tests import it (unit tests only)
        try:
            import kailash.nodes.ai as ai_module
            from tests.utils.kaizen_mock_provider import KaizenMockProvider

            # Directly replace MockProvider in the kailash.nodes.ai module
            if hasattr(ai_module, "MockProvider"):
                ai_module.MockProvider = KaizenMockProvider
                print("✅ Registered Kaizen MockProvider in pytest_configure")
            else:
                print("⚠️  MockProvider not found in kailash.nodes.ai")

        except Exception as e:
            print(f"⚠️  Could not register Kaizen mock provider: {e}")
            import traceback

            traceback.print_exc()

    # Configure markers
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, isolated, can use mocks)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (real services, no mocking)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (complete workflows, real infrastructure)"
    )
    config.addinivalue_line("markers", "performance: Performance benchmark tests")
    config.addinivalue_line("markers", "slow: Slow running tests (timeout > 5s)")
    config.addinivalue_line("markers", "requires_postgres: Tests requiring PostgreSQL")
    config.addinivalue_line("markers", "requires_redis: Tests requiring Redis")
    config.addinivalue_line(
        "markers", "requires_docker: Tests requiring Docker services"
    )
    config.addinivalue_line(
        "markers", "requires_ollama: Tests requiring Ollama service"
    )
    config.addinivalue_line(
        "markers", "requires_llm: Tests requiring real LLM provider (OpenAI or Ollama)"
    )
    config.addinivalue_line(
        "markers", "mcp: Tests for MCP (Model Context Protocol) integration"
    )
    config.addinivalue_line("markers", "server: Tests for MCP server functionality")


def pytest_collection_modifyitems(config, items):
    """Add markers to tests based on their location and name."""
    for item in items:
        # Add markers based on test file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)

        # Add performance marker for performance tests
        if "performance" in item.name or "benchmark" in item.name:
            item.add_marker(pytest.mark.performance)

        # Add slow marker for tests that might take longer
        if "e2e" in str(item.fspath) or "slow" in item.name:
            item.add_marker(pytest.mark.slow)

        # Add infrastructure requirement markers based on test content
        if hasattr(item, "function") and item.function:
            # Check for database usage in test parameters or names
            if any(
                keyword in str(item.function).lower()
                for keyword in ["postgres", "database", "db"]
            ):
                item.add_marker(pytest.mark.requires_postgres)
            if any(
                keyword in str(item.function).lower() for keyword in ["redis", "cache"]
            ):
                item.add_marker(pytest.mark.requires_redis)
            if any(keyword in str(item.function).lower() for keyword in ["docker"]):
                item.add_marker(pytest.mark.requires_docker)
            if any(
                keyword in str(item.function).lower()
                for keyword in ["ollama", "llm", "ai"]
            ):
                item.add_marker(pytest.mark.requires_ollama)
