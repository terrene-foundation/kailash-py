"""Consolidated test fixtures and configuration for Kailash SDK tests."""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import requests
import yaml
from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
)
from kailash.manifest import KailashManifest
from kailash.nodes.base import (
    Node,
    NodeMetadata,
    NodeParameter,
    NodeRegistry,
    register_node,
)
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskRun, TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder

# Set up event loop policy for better async cleanup
asyncio.set_event_loop_policy(
    asyncio.WindowsSelectorEventLoopPolicy()
    if os.name == "nt"
    else asyncio.DefaultEventLoopPolicy()
)

# Configure pytest-asyncio to use strict mode
pytest_plugins = ("pytest_asyncio", "pytest_forked")

# ===========================
# SDK Infrastructure Support
# ===========================


def is_sdk_dev_running():
    """Check if SDK development infrastructure is running."""
    try:
        response = requests.get("http://localhost:8889/health", timeout=1)
        return response.status_code == 200
    except:
        return False


def start_sdk_dev_infrastructure():
    """Start SDK development infrastructure if not running."""
    if is_sdk_dev_running():
        print("✓ SDK development infrastructure is already running")
        return True

    print("Starting SDK development infrastructure...")
    project_root = Path(__file__).parent.parent
    docker_dir = project_root / "docker"

    try:
        # Check if Docker is running
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("⚠️  Docker is not running. Please start Docker first.")
        return False

    # Start infrastructure
    cmd = ["docker", "compose", "-f", "docker-compose.sdk-dev.yml", "up", "-d"]
    result = subprocess.run(cmd, cwd=docker_dir, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Failed to start infrastructure: {result.stderr}")
        return False

    # Wait for services to be ready
    print("Waiting for services to be ready...")
    max_retries = 30
    for i in range(max_retries):
        if is_sdk_dev_running():
            print("✓ SDK development infrastructure is ready")
            return True
        time.sleep(0.1)
        if i % 5 == 0:
            print(f"  Still waiting... ({i}/{max_retries})")

    print("⚠️  Timeout waiting for infrastructure to start")
    return False


# ===========================
# Pytest Configuration
# ===========================


def pytest_addoption(parser):
    """Add command-line options."""
    # Add isolation options
    # add_isolation_options(parser)  # Commented out - function not defined
    pass


def pytest_configure(config):
    """Configure pytest with custom settings and markers."""
    # Start SDK infrastructure if needed
    if os.getenv("SDK_DEV_MODE") == "true":
        if not start_sdk_dev_infrastructure():
            pytest.exit("Failed to start SDK development infrastructure", 1)

    # Register all custom markers
    markers = [
        "requires_infrastructure: mark test as requiring SDK development infrastructure",
        "requires_kafka: mark test as requiring Kafka",
        "requires_mongodb: mark test as requiring MongoDB",
        "requires_qdrant: mark test as requiring Qdrant vector database",
        "requires_postgres: mark test as requiring PostgreSQL",
        "requires_ollama: mark test as requiring Ollama",
        "slow: mark test as slow running",
        "integration: mark test as integration test",
        "unit: mark test as unit test",
    ]

    for marker in markers:
        config.addinivalue_line("markers", marker)

    # Also configure isolation markers
    # configure_isolation(config)  # Commented out - function not defined


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle infrastructure requirements and timeouts."""
    # Apply timeout configuration first
    # apply_timeouts(config, items)  # Commented out - function not defined

    # Apply isolation handling
    # apply_isolation(config, items)  # Commented out - function not defined
    pass

    # Check service availability for conditional skipping
    import asyncio

    postgres_available = asyncio.run(check_postgres_connection())
    ollama_available = check_ollama_connection()
    skip_postgres = pytest.mark.skip(reason="PostgreSQL not available")
    skip_ollama = pytest.mark.skip(reason="Ollama not available")

    for item in items:
        # Add infrastructure marker for tests that need specific services
        if any(
            marker in item.keywords
            for marker in ["requires_kafka", "requires_mongodb", "requires_qdrant"]
        ):
            item.add_marker(pytest.mark.requires_infrastructure)

        # Skip tests requiring unavailable services
        if "requires_postgres" in item.keywords and not postgres_available:
            item.add_marker(skip_postgres)
        if "requires_ollama" in item.keywords and not ollama_available:
            item.add_marker(skip_ollama)


async def check_postgres_connection():
    """Check if PostgreSQL is available."""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            port=5434,
            user="test_user",
            password="test_password",
            database="kailash_test",
            timeout=5,
        )
        await conn.close()
        return True
    except Exception:
        return False


def check_ollama_connection():
    """Check if Ollama is available and has models."""
    try:
        import requests

        response = requests.get("http://localhost:11435/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            # For the test to work, we need at least one model
            return len(models) > 0
        return False
    except Exception:
        return False


# ===========================
# Mock Classes
# ===========================


# Register MockNode globally for all tests that need it


@register_node()
class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, name: str = "MockNode", **kwargs):
        """Initialize mock node with metadata."""
        # Handle the id parameter from WorkflowBuilder
        if "id" in kwargs and "name" not in kwargs:
            name = kwargs.get("id", name)

        metadata = NodeMetadata(
            name=name, description="Mock node for testing", tags={"test", "mock"}
        )
        super().__init__(metadata=metadata, **kwargs)

    def get_parameters(self) -> dict[str, Any]:
        """Define input parameters for the mock node."""
        return {
            "value": NodeParameter(
                name="value",
                type=float,
                required=True,
                description="Input value to double",
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic."""
        value = kwargs.get("value", 0)
        return {"result": value * 2}


# ===========================
# Core Fixtures
# ===========================


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def _ensure_test_nodes_registered():
    """Ensure test-specific nodes are registered when needed."""
    # This fixture can be used by tests that need specific node registrations
    pass


@pytest.fixture(autouse=True, scope="function")
def manage_node_registry():
    """Smart node registry management to handle test interdependencies."""
    # This fixture is now handled by isolate_global_state
    # We keep it for backward compatibility but it does nothing
    yield


@pytest.fixture(scope="session")
def sdk_infrastructure():
    """Fixture that ensures SDK infrastructure is available."""
    if os.getenv("SDK_DEV_MODE") != "true":
        pytest.skip(
            "SDK development infrastructure not enabled (set SDK_DEV_MODE=true)"
        )

    if not is_sdk_dev_running():
        pytest.skip("SDK development infrastructure is not running")

    # Load environment variables
    env_file = Path(__file__).parent.parent / "sdk-users" / ".env.sdk-dev"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)

    return {
        "postgres": os.getenv("TRANSACTION_DB"),
        "mongodb": os.getenv("MONGO_URL"),
        "kafka": os.getenv("KAFKA_BROKERS"),
        "qdrant": "http://localhost:6333",
        "ollama": os.getenv("OLLAMA_HOST"),
        "mock_api": os.getenv("WEBHOOK_API"),
        "mcp_server": os.getenv("MCP_SERVER_URL"),
    }


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test data (alias for compatibility)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ===========================
# Node Fixtures
# ===========================


@pytest.fixture
def mock_node():
    """Create a mock node instance."""
    return MockNode(name="Test Node")


@pytest.fixture
def mock_node_with_config():
    """Create a mock node with configuration."""
    node = MockNode(name="Test Node with Config")
    node.config = {
        "version": "1.0.0",
        "description": "A test node",
        "dependencies": ["test-dep"],
    }
    return node


@pytest.fixture
def mock_node_for_access_control():
    """Create a mock node for access control testing."""
    node = Mock()
    node.name = "test_node"
    node.metadata = Mock()
    node.metadata.name = "test_node"
    node.execute = Mock(return_value={"result": "success"})
    node.get_parameters = Mock(return_value={})
    return node


# ===========================
# Data Fixtures
# ===========================


@pytest.fixture
def sample_csv_file(temp_data_dir: Path) -> Path:
    """Create a sample CSV file for testing."""
    csv_path = temp_data_dir / "sample.csv"
    csv_path.write_text("id,name,value\n1,Alice,100\n2,Bob,200\n3,Charlie,300\n")
    return csv_path


@pytest.fixture
def sample_json_file(temp_data_dir: Path) -> Path:
    """Create a sample JSON file for testing."""
    json_path = temp_data_dir / "sample.json"
    data = {
        "items": [
            {"id": 1, "name": "Alice", "value": 100},
            {"id": 2, "name": "Bob", "value": 200},
            {"id": 3, "name": "Charlie", "value": 300},
        ]
    }
    json_path.write_text(json.dumps(data, indent=2))
    return json_path


@pytest.fixture
def large_dataset(temp_data_dir: Path) -> Path:
    """Create a large dataset for performance testing."""
    csv_path = temp_data_dir / "large_dataset.csv"

    # Create a CSV with 10,000 rows
    with open(csv_path, "w") as f:
        f.write("id,name,value,category\n")
        for i in range(10000):
            name = f"User_{i}"
            value = i * 10 % 1000
            category = f"Cat_{i % 10}"
            f.write(f"{i},{name},{value},{category}\n")

    return csv_path


@pytest.fixture
def yaml_workflow_config(temp_data_dir: Path) -> Path:
    """Create a YAML workflow configuration for testing."""
    config = {
        "workflow": {
            "name": "yaml_test_workflow",
            "description": "Workflow loaded from YAML",
            "nodes": [
                {
                    "id": "reader",
                    "type": "CSVReaderNode",
                    "inputs": {"file_path": str(temp_data_dir / "input.csv")},
                },
                {
                    "id": "processor",
                    "type": "FilterNode",
                    "inputs": {"field": "value", "operator": ">", "value": 100},
                },
                {
                    "id": "writer",
                    "type": "CSVWriterNode",
                    "inputs": {"file_path": str(temp_data_dir / "output.csv")},
                },
            ],
            "connections": [
                {
                    "from": "reader",
                    "from_output": "data",
                    "to": "processor",
                    "to_input": "data",
                },
                {
                    "from": "processor",
                    "from_output": "filtered_data",
                    "to": "writer",
                    "to_input": "data",
                },
            ],
        }
    }

    yaml_path = temp_data_dir / "workflow.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(config, f)

    return yaml_path


@pytest.fixture
def invalid_input_data():
    """Sample invalid input data."""
    return {
        "invalid_type": {"value": "not_a_number"},
        "missing_field": {},
        "extra_field": {"value": 42, "extra": "field"},
        "null_value": {"value": None},
    }


@pytest.fixture
def valid_input_data():
    """Sample valid input data."""
    return {
        "simple": {"value": 42},
        "negative": {"value": -10},
        "zero": {"value": 0},
        "float": {"value": 3.14},
    }


@pytest.fixture
def mock_api_data() -> dict:
    """Create mock API response data."""
    return {
        "status": "success",
        "data": [
            {"id": 1, "metric": 42.5},
            {"id": 2, "metric": 37.8},
            {"id": 3, "metric": 55.1},
        ],
    }


@pytest.fixture
def mock_llm_response() -> str:
    """Create a mock LLM response for testing."""
    return """Based on the data analysis:

    1. Total records: 3
    2. Average value: 200
    3. Key insights:
       - Bob has the median value
       - Charlie has the highest value at 300
       - Alice has the lowest value at 100

    Recommendations:
    - Focus on understanding Charlie's high performance
    - Investigate why Alice's value is lower
    """


# ===========================
# Workflow Fixtures
# ===========================


@pytest.fixture
def sample_workflow():
    """Create a sample workflow graph."""
    workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")

    # Add nodes
    node1 = MockNode(name="Node 1")
    node2 = MockNode(name="Node 2")

    workflow.add_node("node1", node1, value=1.0)
    workflow.add_node("node2", node2, value=2.0)
    workflow.connect("node1", "node2", mapping={"result": "value"})

    return workflow


@pytest.fixture
def complex_workflow():
    """Create a complex workflow with multiple nodes."""
    workflow = Workflow(workflow_id="complex_workflow_test", name="Complex Workflow")

    # Create a diamond-shaped workflow
    nodes = {
        "start": MockNode(name="Start Node"),
        "branch1": MockNode(name="Branch 1"),
        "branch2": MockNode(name="Branch 2"),
        "merge": MockNode(name="Merge Node"),
    }

    for node_id, node in nodes.items():
        workflow.add_node(node_id, node, value=1.0)  # Provide required value parameter

    workflow.connect("start", "branch1", mapping={"result": "value"})
    workflow.connect("start", "branch2", mapping={"result": "value"})
    workflow.connect("branch1", "merge", mapping={"result": "value"})
    workflow.connect("branch2", "merge", mapping={"result": "value"})

    return workflow


@pytest.fixture
def simple_workflow(sample_csv_file: Path, temp_data_dir: Path) -> Workflow:
    """Create a simple workflow for testing."""
    builder = WorkflowBuilder()

    # Add nodes
    reader_id = builder.add_node(
        "CSVReaderNode", "reader", config={"file_path": str(sample_csv_file)}
    )

    filter_id = builder.add_node(
        "FilterNode", "filter", config={"field": "value", "operator": ">", "value": 100}
    )

    writer_id = builder.add_node(
        "CSVWriterNode",
        "writer",
        config={"file_path": str(temp_data_dir / "output.csv")},
    )

    # Connect nodes
    builder.add_connection(reader_id, "data", filter_id, "data")
    builder.add_connection(filter_id, "filtered_data", writer_id, "data")

    return builder.build("simple_test_workflow")


@pytest.fixture
def complex_integration_workflow(
    sample_csv_file: Path, sample_json_file: Path, temp_data_dir: Path
) -> Workflow:
    """Create a complex multi-branch workflow for testing."""
    builder = WorkflowBuilder()

    # Add CSV reader
    csv_reader_id = builder.add_node(
        "CSVReaderNode", "csv_reader", config={"file_path": str(sample_csv_file)}
    )

    # Add filter
    filter_id = builder.add_node(
        "FilterNode", "filter", config={"field": "value", "operator": ">", "value": 150}
    )

    # Add AI processor
    ai_processor_id = builder.add_node(
        "TextSummarizer",
        "ai_processor",
        config={"texts": ["Analyze this data and provide insights"], "max_length": 100},
    )

    # Add outputs
    csv_writer_id = builder.add_node(
        "CSVWriterNode",
        "csv_writer",
        config={"file_path": str(temp_data_dir / "processed.csv")},
    )

    json_writer_id = builder.add_node(
        "JSONWriterNode",
        "json_writer",
        config={"file_path": str(temp_data_dir / "processed.json")},
    )

    report_writer_id = builder.add_node(
        "TextWriterNode",
        "report_writer",
        config={
            "file_path": str(temp_data_dir / "report.txt"),
            "text": "Data analysis complete",
        },
    )

    # Connect nodes
    builder.add_connection(csv_reader_id, "data", filter_id, "data")
    builder.add_connection(filter_id, "filtered_data", csv_writer_id, "data")
    builder.add_connection(filter_id, "filtered_data", json_writer_id, "data")
    # AI processor can run independently
    builder.add_connection(ai_processor_id, "summaries", report_writer_id, "data")

    return builder.build("complex_test_workflow")


@pytest.fixture
def error_workflow(temp_data_dir: Path) -> Workflow:
    """Create a workflow that will produce errors for testing."""
    builder = WorkflowBuilder()

    # Add a reader that will fail
    reader_id = builder.add_node(
        "CSVReaderNode",
        "bad_reader",
        config={"file_path": str(temp_data_dir / "nonexistent.csv")},
    )

    # Add a processor that will fail
    processor_id = builder.add_node(
        "FilterNode",
        "bad_filter",
        config={"field": "value", "operator": "invalid_op", "value": 100},
    )

    writer_id = builder.add_node(
        "CSVWriterNode",
        "writer",
        config={"file_path": str(temp_data_dir / "output.csv")},
    )

    builder.add_connection(reader_id, "data", processor_id, "data")
    builder.add_connection(processor_id, "filtered_data", writer_id, "data")

    return builder.build("error_test_workflow")


@pytest.fixture
def parallel_workflow(temp_data_dir: Path) -> Workflow:
    """Create a workflow with parallel execution paths."""
    builder = WorkflowBuilder()

    # Single input
    reader_id = builder.add_node(
        "CSVReaderNode",
        "reader",
        config={"file_path": str(temp_data_dir / "input.csv")},
    )

    # Parallel processing branches
    filter1_id = builder.add_node(
        "FilterNode",
        "filter_high",
        config={"field": "value", "operator": ">", "value": 500},
    )

    filter2_id = builder.add_node(
        "FilterNode",
        "filter_low",
        config={"field": "value", "operator": "<=", "value": 500},
    )

    # Parallel outputs
    writer1_id = builder.add_node(
        "CSVWriterNode",
        "writer_high",
        config={"file_path": str(temp_data_dir / "high_values.csv")},
    )

    writer2_id = builder.add_node(
        "CSVWriterNode",
        "writer_low",
        config={"file_path": str(temp_data_dir / "low_values.csv")},
    )

    # Connect parallel branches
    builder.add_connection(reader_id, "data", filter1_id, "data")
    builder.add_connection(reader_id, "data", filter2_id, "data")
    builder.add_connection(filter1_id, "filtered_data", writer1_id, "data")
    builder.add_connection(filter2_id, "filtered_data", writer2_id, "data")

    return builder.build("parallel_test_workflow")


# ===========================
# Task Management Fixtures
# ===========================


@pytest.fixture
def sample_task():
    """Create a sample task."""
    return TaskRun(
        task_id="test-task",
        run_id="test-run",
        node_id="test-node",
        node_type="MockNode",
        status=TaskStatus.PENDING,
        metadata={"user": "test"},
    )


@pytest.fixture
def task_manager(temp_dir):
    """Create a task manager with filesystem storage."""
    storage = FileSystemStorage(temp_dir)
    return TaskManager(storage)


@pytest.fixture
def sample_manifest(simple_workflow: Workflow) -> KailashManifest:
    """Create a sample manifest for testing."""
    return KailashManifest(
        metadata={
            "id": "test-manifest",
            "name": "Test Manifest",
            "version": "1.0.0",
            "author": "Test Author",
            "description": "Test manifest for integration tests",
        },
        workflow=simple_workflow,
    )


# ===========================
# Access Control Fixtures
# ===========================


@pytest.fixture
def clean_acm():
    """Provide a clean AccessControlManager instance."""
    return AccessControlManager()


@pytest.fixture
def admin_user():
    """Standard admin user for testing."""
    return UserContext(
        user_id="admin-001",
        tenant_id="tenant-001",
        email="admin@test.com",
        roles=["admin"],
    )


@pytest.fixture
def analyst_user():
    """Standard analyst user for testing."""
    return UserContext(
        user_id="analyst-001",
        tenant_id="tenant-001",
        email="analyst@test.com",
        roles=["analyst"],
    )


@pytest.fixture
def viewer_user():
    """Standard viewer user for testing."""
    return UserContext(
        user_id="viewer-001",
        tenant_id="tenant-001",
        email="viewer@test.com",
        roles=["viewer"],
    )


@pytest.fixture
def multi_role_user():
    """User with multiple roles for testing."""
    return UserContext(
        user_id="multi-001",
        tenant_id="tenant-001",
        email="multi@test.com",
        roles=["viewer", "analyst", "reporter"],
    )


@pytest.fixture
def standard_rules():
    """Create a standard set of permission rules."""
    return [
        PermissionRule(
            id="admin_all_nodes",
            resource_type="node",
            resource_id="*",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        ),
        PermissionRule(
            id="admin_all_workflows",
            resource_type="workflow",
            resource_id="*",
            permission=WorkflowPermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        ),
        PermissionRule(
            id="analyst_process_nodes",
            resource_type="node",
            resource_id="process_*",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="analyst",
        ),
        PermissionRule(
            id="viewer_read_nodes",
            resource_type="node",
            resource_id="read_*",
            permission=NodePermission.READ,
            effect=PermissionEffect.ALLOW,
            role="viewer",
        ),
    ]


@pytest.fixture
def acm_with_standard_rules(clean_acm, standard_rules):
    """AccessControlManager with standard rules pre-loaded."""
    for rule in standard_rules:
        clean_acm.add_rule(rule)
    return clean_acm


@pytest.fixture(scope="function", autouse=True)
def cleanup_async_tasks(request):
    """Cleanup async tasks after each test to prevent warnings."""
    yield

    # Only cleanup for async tests
    if hasattr(request.node, "iter_markers"):
        if any(marker.name == "asyncio" for marker in request.node.iter_markers()):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule cleanup
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        if not task.done() and task != asyncio.current_task():
                            task.cancel()
            except RuntimeError:
                pass  # No event loop


# ===========================
# Test Isolation Fixtures
# ===========================


@pytest.fixture(scope="function", autouse=True)
def isolate_global_state():
    """Automatically isolate global state for each test to prevent pollution."""
    # Import modules that have global state
    import kailash.gateway.api as gateway_api
    from kailash.nodes.base import NodeRegistry
    from kailash.nodes.data.async_connection import AsyncConnectionManager

    # In forked processes, we need to ensure nodes are registered first
    if len(NodeRegistry._nodes) == 0:
        from tests.node_registry_utils import ensure_nodes_registered

        ensure_nodes_registered()

    # Don't save/restore node classes - just track what was added
    original_node_names = set(NodeRegistry._nodes.keys())
    original_node_instance = NodeRegistry._instance

    # Save original AsyncConnectionManager state
    original_pool_instance = AsyncConnectionManager._instance

    # Save original gateway instance
    original_gateway = getattr(gateway_api, "_gateway_instance", None)

    yield

    # Clean up only test-added nodes, keep SDK nodes
    current_node_names = set(NodeRegistry._nodes.keys())
    test_added_nodes = current_node_names - original_node_names

    # Remove only the nodes added during the test
    for node_name in test_added_nodes:
        NodeRegistry._nodes.pop(node_name, None)

    # Restore instance
    NodeRegistry._instance = original_node_instance

    # Restore AsyncConnectionManager state
    AsyncConnectionManager._instance = original_pool_instance

    # Restore gateway instance
    gateway_api._gateway_instance = original_gateway

    # Clear any async tasks that might be hanging (only in async context)
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        if hasattr(asyncio, "all_tasks"):
            tasks = asyncio.all_tasks(loop)
        else:
            tasks = asyncio.Task.all_tasks(loop)
        for task in tasks:
            if not task.done() and task != asyncio.current_task():
                task.cancel()
    except RuntimeError:
        # No event loop running, skip async cleanup
        pass


@pytest.fixture
def clean_node_registry():
    """Provide a completely clean NodeRegistry for tests."""
    from kailash.nodes.base import NodeRegistry

    # Save original state
    original_nodes = NodeRegistry._nodes.copy()
    original_instance = NodeRegistry._instance

    # Clear registry completely
    NodeRegistry._nodes.clear()
    NodeRegistry._instance = None

    yield

    # Restore original state
    NodeRegistry._nodes.clear()
    NodeRegistry._nodes.update(original_nodes)
    NodeRegistry._instance = original_instance


@pytest.fixture
def isolated_test_environment():
    """Provide a completely isolated test environment."""
    # Save original state
    original_nodes = NodeRegistry._nodes.copy()
    original_instance = NodeRegistry._instance

    # Clear registry for clean slate
    NodeRegistry._nodes.clear()
    NodeRegistry._instance = None

    yield

    # Restore original state
    NodeRegistry._nodes.clear()
    NodeRegistry._nodes.update(original_nodes)
    NodeRegistry._instance = original_instance


@pytest.fixture
def reset_all_global_state():
    """Reset all global state before and after each test."""
    # Save original state
    original_nodes = NodeRegistry._nodes.copy()
    original_instance = NodeRegistry._instance

    # Clear all global state
    NodeRegistry._nodes.clear()
    NodeRegistry._instance = None

    yield

    # Restore original state
    NodeRegistry._nodes.clear()
    NodeRegistry._nodes.update(original_nodes)
    NodeRegistry._instance = original_instance


# =============================================================================
# Test Isolation Fixtures
# =============================================================================


@pytest.fixture
def clean_node_registry():
    """
    Ensure NodeRegistry is clean before and after each test.

    This fixture provides a clean registry when needed, not automatically.
    Use the centralized node_registry_utils for consistent behavior.
    """
    from tests.node_registry_utils import restore_registry, save_and_clear_registry

    # Store original state and clear
    original_nodes = save_and_clear_registry()

    yield

    # Restore original state
    restore_registry(original_nodes, ensure_sdk_nodes=False)


@pytest.fixture
def mock_node_factory():
    """
    Factory for creating isolated mock node classes.

    This factory creates unique node classes for each test, preventing
    class-level pollution between tests.

    Usage:
        def test_something(mock_node_factory):
            MockNode = mock_node_factory("MyNode", execute_return={"status": "ok"})
            # Use MockNode in test...
    """
    created_nodes = []

    def _create_mock_node(
        name: str = "MockNode",
        base_class: type[Node] | None = None,
        execute_return: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
        **extra_attrs,
    ) -> type[Node]:
        """
        Create an isolated mock node class.

        Args:
            name: Base name for the node class
            base_class: Base class to inherit from (default: Node)
            execute_return: What the execute method should return
            parameters: Node parameters definition
            **extra_attrs: Additional attributes/methods for the class

        Returns:
            Mock node class
        """
        if base_class is None:
            base_class = Node

        if execute_return is None:
            execute_return = {"result": "success"}

        if parameters is None:
            parameters = {}

        # Auto-generate parameter declarations for common test parameters
        # This prevents parameter validation failures in existing tests
        if not parameters:
            # Common test parameters that need declarations
            common_test_params = [
                "value",
                "input",
                "data",
                "config",
                "test_param",
                "node_instance",
                "code",
                "query",
                "host",
                "database",
                "database_type",
            ]
            from kailash.nodes.base import NodeParameter

            parameters = {
                param_name: NodeParameter(
                    name=param_name,
                    type=object,  # Accept any type for test flexibility
                    required=False,
                    description=f"Auto-generated test parameter: {param_name}",
                )
                for param_name in common_test_params
            }

        # Create unique class name to avoid conflicts
        unique_name = f"{name}_{id(name)}_{len(created_nodes)}"

        # Define class methods
        def init_method(self, **kwargs):
            self.config = kwargs
            self.name = kwargs.get("name", unique_name)
            self.id = kwargs.get("id", unique_name)
            super(type(self), self).__init__()

        def get_parameters_method(self):
            return parameters

        def execute_method(self, **kwargs):
            return execute_return

        # Handle special execute_method if provided in extra_attrs
        if "execute_method" in extra_attrs:
            execute_method = extra_attrs.pop("execute_method")

        # Build class attributes
        class_attrs = {
            "__init__": init_method,
            "get_parameters": get_parameters_method,
            "execute": execute_method,
        }

        # Add any extra attributes
        class_attrs.update(extra_attrs)

        # Create the class
        mock_class = type(unique_name, (base_class,), class_attrs)

        # Track for cleanup
        created_nodes.append(unique_name)

        # Register with NodeRegistry using the original name (not unique)
        # This allows tests to use familiar names like "MockNode"
        NodeRegistry.register(mock_class, name)

        return mock_class

    yield _create_mock_node

    # Cleanup all created nodes
    for node_name in created_nodes:
        NodeRegistry._nodes.pop(node_name, None)

    # Also cleanup by the registered names
    standard_names = ["MockNode", "TestNode", "LocalNode"]
    for name in standard_names:
        NodeRegistry._nodes.pop(name, None)


@pytest.fixture
def isolated_workflow_builder():
    """
    Provide an isolated WorkflowBuilder instance with clean state.
    """
    builder = WorkflowBuilder()
    yield builder

    # Cleanup
    builder.clear()


# ===========================
# Infrastructure Fixtures (Consolidated)
# ===========================
# These fixtures eliminate duplication across integration/e2e tests


@pytest.fixture(scope="session")
def postgres_connection_string():
    """Get PostgreSQL connection string from Docker config."""
    from tests.utils.docker_config import get_postgres_connection_string

    return get_postgres_connection_string("kailash_test")


@pytest.fixture(scope="session")
def redis_connection_config():
    """Get Redis connection configuration from Docker config."""
    return {
        "host": REDIS_CONFIG["host"],
        "port": REDIS_CONFIG["port"],
        "db": 0,
        "decode_responses": True,
    }


@pytest.fixture(scope="session")
def mongodb_connection_config():
    """Get MongoDB connection configuration from Docker config."""
    return {
        "host": MONGODB_CONFIG["host"],
        "port": MONGODB_CONFIG["port"],
        "username": MONGODB_CONFIG["username"],
        "password": MONGODB_CONFIG["password"],
        "database": "kailash_test",
    }


@pytest.fixture(scope="session")
def ollama_connection_config():
    """Get Ollama connection configuration from Docker config."""
    return {
        "base_url": f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}",
        "model": "llama3.2:1b",  # Default test model
    }


@pytest.fixture(scope="function")
def health_monitor():
    """Create fresh health monitor for testing."""
    from kailash.core.resilience.health_monitor import HealthMonitor

    return HealthMonitor(check_interval=5.0, alert_threshold=2)


@pytest.fixture(scope="function")
def docker_services():
    """Provide Docker services configuration for integration tests."""
    return {
        "postgres": DATABASE_CONFIG,
        "redis": REDIS_CONFIG,
        "mongodb": MONGODB_CONFIG,
        "ollama": OLLAMA_CONFIG,
    }


# NOTE: These fixtures consolidate duplicate definitions from:
# - tests/integration/core/test_health_monitor_integration.py
# - tests/integration/core/test_bulkhead_integration.py
# - tests/e2e/test_bulkhead_enterprise_scenarios.py
# - tests/e2e/test_health_monitor_enterprise_e2e.py
# - tests/integration/nodes/transaction/test_saga_persistence_integration.py
# - tests/integration/nodes/transaction/test_two_phase_commit_integration.py
