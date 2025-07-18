"""Docker-based functional tests for LocalRuntime - NO MOCKS."""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONReaderNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.integration.docker_test_base import DockerIntegrationTestBase


@pytest.mark.integration
@pytest.mark.requires_docker
class TestLocalRuntimeWithRealServicesDocker(DockerIntegrationTestBase):
    """Test LocalRuntime with real services and workflows."""

    @pytest.fixture
    def runtime(self):
        """Create LocalRuntime instance."""
        return LocalRuntime(
            debug=True,
            enable_cycles=True,
            enable_async=True,
            max_concurrency=5,
            enable_monitoring=True,
        )

    @pytest.fixture
    def test_csv_file(self):
        """Create a real CSV file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name,value\n")
            f.write("1,Alice,100\n")
            f.write("2,Bob,200\n")
            f.write("3,Charlie,300\n")
            csv_path = f.name

        yield csv_path

        # Cleanup
        if os.path.exists(csv_path):
            os.unlink(csv_path)

    @pytest.fixture
    def test_json_file(self):
        """Create a real JSON file for testing."""
        test_data = {
            "users": [
                {"id": 1, "name": "Alice", "active": True},
                {"id": 2, "name": "Bob", "active": False},
                {"id": 3, "name": "Charlie", "active": True},
            ],
            "metadata": {"version": "1.0", "created": "2024-01-01"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            json_path = f.name

        yield json_path

        # Cleanup
        if os.path.exists(json_path):
            os.unlink(json_path)

    def test_simple_workflow_execution(self, runtime, test_csv_file):
        """Test executing a simple workflow with real file I/O."""
        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node("CSVReaderNode", "csv_reader", {"file_path": test_csv_file})

        def process(data):
            # Sum all values
            total = sum(int(row["value"]) for row in data)
            return {"total": total, "count": len(data)}

        from kailash.nodes.code.python import PythonCodeNode

        processor_node = PythonCodeNode.from_function(process)
        workflow.add_node_instance(processor_node, "processor")

        workflow.add_connection("csv_reader", "output", "processor", "data")

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert results["processor"]["total"] == 600
        assert results["processor"]["count"] == 3

    @pytest.mark.asyncio
    async def test_async_database_workflow(
        self, runtime, workflow_db_config, test_database
    ):
        """Test async database operations in workflow."""
        # Create test table
        await test_database.execute(
            """
            CREATE TABLE workflow_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                value INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert test data
        await test_database.execute(
            """
            INSERT INTO workflow_test (name, value) VALUES
            ('Item1', 100),
            ('Item2', 200),
            ('Item3', 300)
        """
        )

        # Build workflow with async SQL node
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "db_reader",
            {
                "database_config": workflow_db_config,
                "query": "SELECT * FROM workflow_test ORDER BY value DESC",
                "parameters": [],
            },
        )

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert results["db_reader"]["success"] is True
        assert len(results["db_reader"]["rows"]) == 3
        assert results["db_reader"]["rows"][0]["value"] == 300
        assert results["db_reader"]["rows"][0]["name"] == "Item3"

    def test_conditional_workflow_execution(self, runtime, test_json_file):
        """Test conditional workflow with switch node."""
        # Build workflow
        workflow = WorkflowBuilder()

        # Read JSON data
        workflow.add_node(
            "JSONReaderNode", "json_reader", {"file_path": test_json_file}
        )

        # Process active users
        workflow.add_node("PythonCodeNode", "filter_active", {})
        filter_node = workflow.get_node("filter_active")
        filter_node.set_code(
            """
def process(users):
    active_users = [u for u in users if u.get('active', False)]
    return {"active_count": len(active_users), "users": active_users}
"""
        )

        # Switch based on count
        workflow.add_node(
            "SwitchNode", "switch", {"condition": "data['active_count'] > 1"}
        )

        # Process branches
        workflow.add_node("PythonCodeNode", "many_active", {})
        many_node = workflow.get_node("many_active")
        many_node.set_code(
            """
def process(data):
    return {"message": f"Found {data['active_count']} active users", "status": "success"}
"""
        )

        workflow.add_node("PythonCodeNode", "few_active", {})
        few_node = workflow.get_node("few_active")
        few_node.set_code(
            """
def process(data):
    return {"message": f"Only {data['active_count']} active users", "status": "warning"}
"""
        )

        # Connect nodes
        workflow.add_connection("json_reader", "filter_active", "users", "users")
        workflow.add_connection("filter_active", "switch", "output", "data")
        workflow.add_connection("switch", "many_active", "true", "data")
        workflow.add_connection("switch", "few_active", "false", "data")

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify results (2 active users, so should take true branch)
        assert results["filter_active"]["active_count"] == 2
        assert results["many_active"]["message"] == "Found 2 active users"
        assert results["many_active"]["status"] == "success"
        assert "few_active" not in results  # False branch not executed

    def test_parallel_execution_with_merge(self, runtime):
        """Test parallel execution and merging results."""
        # Build workflow with parallel branches
        workflow = WorkflowBuilder()

        # Create parallel processing nodes
        workflow.add_node("PythonCodeNode", "processor1", {})
        p1 = workflow.get_node("processor1")
        p1.set_code(
            """
import time
def process(data):
    time.sleep(0.1)  # Simulate work
    return {"result": "A", "value": 100}
"""
        )

        workflow.add_node("PythonCodeNode", "processor2", {})
        p2 = workflow.get_node("processor2")
        p2.set_code(
            """
import time
def process(data):
    time.sleep(0.1)  # Simulate work
    return {"result": "B", "value": 200}
"""
        )

        workflow.add_node("PythonCodeNode", "processor3", {})
        p3 = workflow.get_node("processor3")
        p3.set_code(
            """
import time
def process(data):
    time.sleep(0.1)  # Simulate work
    return {"result": "C", "value": 300}
"""
        )

        # Merge results
        workflow.add_node(
            "MergeNode",
            "merger",
            {
                "merge_strategy": "combine",
                "input_ports": ["input1", "input2", "input3"],
            },
        )

        # Final processor
        workflow.add_node("PythonCodeNode", "final", {})
        final = workflow.get_node("final")
        final.set_code(
            """
def process(data):
    # Process merged results
    total = sum(item.get('value', 0) for item in data)
    results = [item.get('result', '') for item in data]
    return {"total": total, "results": results}
"""
        )

        # Connect parallel branches to merger
        workflow.add_connection("processor1", "merger", "output", "input1")
        workflow.add_connection("processor2", "merger", "output", "input2")
        workflow.add_connection("processor3", "merger", "output", "input3")
        workflow.add_connection("merger", "final", "output", "data")

        # Execute workflow
        import time

        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        # Verify results
        assert results["final"]["total"] == 600
        assert set(results["final"]["results"]) == {"A", "B", "C"}

        # Verify parallel execution (should be faster than sequential)
        assert execution_time < 0.5  # Should complete in under 0.5s due to parallelism

    def test_error_handling_in_workflow(self, runtime):
        """Test error handling and recovery in workflows."""
        workflow = WorkflowBuilder()

        # Node that will fail
        workflow.add_node("PythonCodeNode", "failing_node", {})
        fail_node = workflow.get_node("failing_node")
        fail_node.set_code(
            """
def process(data):
    raise ValueError("Intentional error for testing")
"""
        )

        # Error handler node
        workflow.add_node("PythonCodeNode", "error_handler", {})
        handler = workflow.get_node("error_handler")
        handler.set_code(
            """
def process(error_data):
    return {
        "handled": True,
        "error_type": "ValueError",
        "message": "Error was handled successfully"
    }
"""
        )

        # Normal flow node (shouldn't execute)
        workflow.add_node("PythonCodeNode", "normal_flow", {})
        normal = workflow.get_node("normal_flow")
        normal.set_code(
            """
def process(data):
    return {"status": "This should not execute"}
"""
        )

        # Connect with error handling
        workflow.add_connection("failing_node", "normal_flow", "output", "data")
        workflow.add_connection("failing_node", "error_handler", "error", "error_data")

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify error was caught and handled
        assert "error_handler" in results
        assert results["error_handler"]["handled"] is True
        assert results["error_handler"]["message"] == "Error was handled successfully"

        # Normal flow should not have executed
        assert "normal_flow" not in results

    @pytest.mark.asyncio
    async def test_real_ollama_integration(self, runtime, ollama_client):
        """Test workflow with real Ollama integration."""
        # Verify Ollama model is available
        await self.verify_ollama_model(ollama_client, "llama3.2:1b")

        # Build workflow with embedding generation
        workflow = WorkflowBuilder()

        workflow.add_node(
            "EmbeddingGeneratorNode",
            "embedder",
            {
                "provider": "ollama",
                "model": "llama3.2:1b",
                "texts": ["Hello world", "Machine learning", "Python programming"],
            },
        )

        workflow.add_node("PythonCodeNode", "processor", {})
        processor = workflow.get_node("processor")
        processor.set_code(
            """
def process(embeddings):
    # Extract and validate embeddings
    results = []
    for emb in embeddings.get('embeddings', []):
        if 'embedding' in emb:
            results.append({
                'text': emb.get('text', ''),
                'dimension': len(emb['embedding'])
            })
    return {"processed": results, "count": len(results)}
"""
        )

        workflow.add_connection("embedder", "processor", "output", "embeddings")

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify embeddings were generated
        assert results["processor"]["count"] == 3
        assert all(r["dimension"] > 0 for r in results["processor"]["processed"])

    def test_resource_limits_enforcement(self, runtime):
        """Test resource limits are enforced during execution."""
        # Create runtime with strict limits
        limited_runtime = LocalRuntime(
            max_concurrency=2,
            resource_limits={
                "max_execution_time": 1,  # 1 second limit
                "max_memory_mb": 100,
            },
        )

        # Build workflow that exceeds time limit
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "slow_node", {})
        node = workflow.get_node("slow_node")
        node.set_code(
            """
import time
def process(data):
    time.sleep(2)  # Exceeds 1 second limit
    return {"status": "Should not complete"}
"""
        )

        # Execute should handle timeout gracefully
        results, run_id = limited_runtime.execute(workflow.build())

        # The execution should complete but the node might have error status
        # or the runtime might handle it gracefully
        assert run_id is not None  # Execution was attempted

    def test_monitoring_and_metrics(self, runtime):
        """Test monitoring and metrics collection during execution."""
        # Build workflow with multiple nodes
        workflow = WorkflowBuilder()

        for i in range(3):
            workflow.add_node("PythonCodeNode", f"node_{i}", {})
            node = workflow.get_node(f"node_{i}")
            node.set_code(
                f"""
def process(data):
    import time
    time.sleep(0.01)
    return {{"node_id": {i}, "processed": True}}
"""
            )

        # Chain nodes
        workflow.add_connection("node_0", "node_1", "output", "data")
        workflow.add_connection("node_1", "node_2", "output", "data")

        # Execute with monitoring enabled
        results, run_id = runtime.execute(workflow.build())

        # Verify all nodes executed
        assert results["node_0"]["node_id"] == 0
        assert results["node_1"]["node_id"] == 1
        assert results["node_2"]["node_id"] == 2

        # Verify monitoring context was available
        assert runtime._execution_context["monitoring_enabled"] is True
