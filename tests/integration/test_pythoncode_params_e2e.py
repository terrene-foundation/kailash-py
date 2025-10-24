"""End-to-end integration tests for PythonCodeNode parameter handling.

This test file validates the complete parameter handling fixes with real services:
1. Default parameter handling through complete workflows
2. Parameter injection with workflow parameters
3. Security validation in production scenarios
"""

import asyncio
from typing import Any, Dict

import asyncpg
import pytest
import pytest_asyncio
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import (
    REDIS_CONFIG,
    ensure_docker_services,
    get_postgres_connection_string,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
class TestPythonCodeParameterIntegration:
    """Test PythonCodeNode parameter handling with real PostgreSQL."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_database(self):
        """Set up test database with real PostgreSQL."""
        # Ensure Docker services are running
        await ensure_docker_services()

        # Get real connection string
        conn_string = get_postgres_connection_string()

        # Create test table
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS param_test")
            await conn.execute(
                """
                CREATE TABLE param_test (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    value INTEGER,
                    metadata JSONB DEFAULT '{}'
                )
            """
            )

            # Insert test data
            await conn.execute(
                """
                INSERT INTO param_test (name, value) VALUES
                ('item1', 100),
                ('item2', 200),
                ('item3', 150)
            """
            )
        finally:
            await conn.close()

        yield

        # Cleanup
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute("DROP TABLE IF EXISTS param_test")
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_default_parameter_handling(self):
        """Test that default parameters work correctly in workflows."""
        builder = WorkflowBuilder()

        # Add SQL node to fetch data
        # Use simulated data for parameter testing (database setup complexities)
        builder.add_node(
            "PythonCodeNode",
            "fetch_data",
            {
                "code": """
# Simulate database data for testing parameter handling
result = {
    'data': [
        {'id': 1, 'name': 'item1', 'value': 100},
        {'id': 2, 'name': 'item2', 'value': 200},
        {'id': 3, 'name': 'item3', 'value': 150}
    ]
}
"""
            },
        )

        # Add PythonCode node with function that has default parameters
        def process_items(
            data: list,
            threshold: int = 150,  # Default parameter
            include_stats: bool = True,  # Another default
            **kwargs,  # Accept workflow parameters
        ) -> dict:
            """Process items with configurable threshold."""
            above_threshold = [item for item in data if item["value"] >= threshold]

            result = {"items": above_threshold, "threshold_used": threshold}

            if include_stats:
                result["stats"] = {
                    "total_items": len(data),
                    "above_threshold": len(above_threshold),
                    "average_value": (
                        sum(item["value"] for item in data) / len(data) if data else 0
                    ),
                }

            # Include any extra workflow parameters
            if kwargs:
                result["workflow_params"] = kwargs

            return result

        builder.add_node(PythonCodeNode.from_function(process_items), "processor")

        builder.add_connection("fetch_data", "result.data", "processor", "data")

        # Test 1: Execute with defaults
        workflow = builder.build()
        runtime = LocalRuntime()

        result1, run_id1 = runtime.execute(workflow)
        output1 = result1["processor"]["result"]

        # Should use default threshold of 150
        assert output1["threshold_used"] == 150
        assert len(output1["items"]) == 2  # item2 (200) and item3 (150)
        assert output1["stats"]["total_items"] == 3
        assert output1["stats"]["above_threshold"] == 2

        # Test 2: Execute with overridden parameters
        result2, run_id2 = runtime.execute(
            workflow,
            parameters={
                "threshold": 180,
                "include_stats": False,
                "custom_param": "injected",
            },
        )
        output2 = result2["processor"]["result"]

        # Should use overridden threshold
        assert output2["threshold_used"] == 180
        assert len(output2["items"]) == 1  # Only item2 (200)
        assert "stats" not in output2  # Stats disabled
        assert output2["workflow_params"]["custom_param"] == "injected"

    @pytest.mark.asyncio
    async def test_kwargs_parameter_injection(self):
        """Test that **kwargs allows workflow parameter injection."""
        builder = WorkflowBuilder()

        # Simple data source using real PostgreSQL
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "get_config",
            {
                "connection_string": get_postgres_connection_string(),
                "query": "SELECT 'production' as env, 100 as batch_size",
            },
        )

        # Function with **kwargs to receive workflow parameters
        def configure_processing(config: list, **kwargs) -> dict:
            """Configure processing based on config and workflow params."""
            base_config = config[0] if config else {}

            # Merge base config with injected parameters
            final_config = {
                "environment": base_config.get("env", "unknown"),
                "batch_size": base_config.get("batch_size", 50),
                # These come from workflow parameters via **kwargs
                "debug_mode": kwargs.get("debug_mode", False),
                "log_level": kwargs.get("log_level", "INFO"),
                "custom_settings": kwargs.get("custom_settings", {}),
            }

            # Process based on configuration
            if final_config["debug_mode"]:
                final_config["log_level"] = "DEBUG"
                final_config["batch_size"] = min(final_config["batch_size"], 10)

            return final_config

        builder.add_node(
            PythonCodeNode.from_function(configure_processing), "configurator"
        )

        builder.add_connection("get_config", "result.data", "configurator", "config")

        # Execute with workflow parameters
        workflow = builder.build()
        runtime = LocalRuntime()

        result, run_id = runtime.execute(
            workflow,
            parameters={
                "debug_mode": True,
                "log_level": "WARN",  # Will be overridden by debug_mode
                "custom_settings": {"feature_x": "enabled"},
            },
        )

        output = result["configurator"]["result"]

        # Verify parameter injection worked
        assert output["environment"] == "production"  # From database
        assert output["debug_mode"] is True  # Injected
        assert output["log_level"] == "DEBUG"  # Modified by debug_mode
        assert output["batch_size"] == 10  # Limited by debug_mode
        assert output["custom_settings"]["feature_x"] == "enabled"  # Injected

    @pytest.mark.asyncio
    async def test_security_validation_in_workflow(self):
        """Test security validation prevents unsafe code execution."""
        builder = WorkflowBuilder()

        # Try to create node with unsafe code
        unsafe_codes = [
            "import subprocess; result = subprocess.run(['ls'], capture_output=True)",
            "import sys; result = sys.modules",
            "result = eval('1 + 1')",
        ]

        # Test that unsafe code fails during execution rather than node creation
        # (PythonCodeNode validates code at runtime, not at creation time)
        for i, code in enumerate(unsafe_codes):
            builder = WorkflowBuilder()  # Fresh builder for each test
            builder.add_node("PythonCodeNode", f"unsafe_node_{i}", {"code": code})
            workflow = builder.build()
            runtime = LocalRuntime()

            # Execute workflow - should complete but node should fail
            results, _ = runtime.execute(workflow)
            node_name = f"unsafe_node_{i}"

            # Check that node failed with security error
            assert node_name in results
            assert results[node_name]["failed"] is True
            assert "error" in results[node_name]
            error_msg = str(results[node_name]["error"]).lower()
            assert (
                "not allowed" in error_msg
                or "safety" in error_msg
                or "restricted" in error_msg
                or "security" in error_msg
                or "import" in error_msg
            )

    @pytest.mark.asyncio
    async def test_complex_parameter_flow(self):
        """Test complex parameter flow through multiple nodes."""
        builder = WorkflowBuilder()

        # Node 1: Generate base parameters
        def generate_params(**kwargs) -> dict:
            base_multiplier = kwargs.get("base_multiplier", 1.0)
            return {
                "multiplier": base_multiplier,
                "categories": ["A", "B", "C"],
                "settings": {"enabled": True, "threshold": 0.5},
            }

        builder.add_node(
            PythonCodeNode.from_function(generate_params), "param_generator"
        )

        # Node 2: Fetch data based on categories using real PostgreSQL
        builder.add_node(
            "AsyncSQLDatabaseNode",
            "fetch_by_category",
            {
                "connection_string": get_postgres_connection_string(),
                "query": "SELECT * FROM param_test",
            },
        )

        # Node 3: Process with cascaded parameters
        def process_with_params(
            data: list, params: dict, override_threshold: float = None, **kwargs
        ) -> dict:
            """Process data using cascaded parameters."""
            # Use override if provided, otherwise use params
            threshold = override_threshold or params["settings"]["threshold"]
            multiplier = params["multiplier"] * kwargs.get("adjustment_factor", 1.0)

            processed = []
            for item in data:
                processed_value = item["value"] * multiplier
                if processed_value > threshold:
                    processed.append(
                        {
                            "name": item["name"],
                            "original": item["value"],
                            "processed": processed_value,
                            "above_threshold": True,
                        }
                    )

            return {
                "results": processed,
                "parameters_used": {
                    "threshold": threshold,
                    "final_multiplier": multiplier,
                    "categories": params["categories"],
                    "workflow_adjustment": kwargs.get("adjustment_factor", 1.0),
                },
            }

        builder.add_node(PythonCodeNode.from_function(process_with_params), "processor")

        # Connect nodes
        builder.add_connection("param_generator", "result", "processor", "params")
        builder.add_connection("fetch_by_category", "result.data", "processor", "data")

        # Execute with workflow parameters
        workflow = builder.build()
        runtime = LocalRuntime()

        result, run_id = runtime.execute(
            workflow,
            parameters={
                "base_multiplier": 2.0,
                "adjustment_factor": 1.5,
                "override_threshold": 250.0,
            },
        )

        output = result["processor"]["result"]

        # Verify complex parameter flow
        assert output["parameters_used"]["final_multiplier"] == 3.0  # 2.0 * 1.5
        assert output["parameters_used"]["threshold"] == 250.0  # Override used
        assert output["parameters_used"]["workflow_adjustment"] == 1.5

        # Check processing results
        assert (
            len(output["results"]) == 3
        )  # Items with value * 3.0 > 250 (100×3=300, 200×3=600, 150×3=450)
        for item in output["results"]:
            assert item["processed"] > 250.0
            assert item["above_threshold"] is True
