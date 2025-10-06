"""
Test Fixtures for Infrastructure Testing

Provides consistent test data, configurations, and utilities for test validation.
Used across all test tiers to ensure consistent testing environments.
"""

import os
import subprocess
from typing import Any, Dict, List, Optional


def integration_test_config() -> Dict[str, Any]:
    """
    Provide integration test configuration.

    Returns:
        Configuration dictionary for integration testing
    """
    return {
        "framework": {
            "name": "integration_test_framework",
            "version": "1.0.0",
            "description": "Framework for integration testing",
        },
        "agents": [
            {
                "name": "test_agent_1",
                "capabilities": ["workflow_execution", "data_processing"],
            },
            {"name": "test_agent_2", "capabilities": ["analysis", "reporting"]},
        ],
        "workflows": {
            "simple_workflow": {"nodes": 3, "connections": 2},
            "complex_workflow": {"nodes": 5, "connections": 6},
        },
    }


def test_agent_configs() -> Dict[str, Dict[str, Any]]:
    """
    Provide various test agent configurations.

    Returns:
        Dictionary of agent configurations for testing
    """
    return {
        "basic_agent": {
            "name": "basic_test_agent",
            "type": "basic",
            "capabilities": ["basic_processing"],
        },
        "processing_agent": {
            "name": "processing_test_agent",
            "type": "processing",
            "capabilities": ["data_processing", "transformation"],
        },
        "analysis_agent": {
            "name": "analysis_test_agent",
            "type": "analysis",
            "capabilities": ["analysis", "pattern_detection"],
        },
        "reporting_agent": {
            "name": "reporting_test_agent",
            "type": "reporting",
            "capabilities": ["report_generation", "data_export"],
        },
    }


def sample_workflow_nodes() -> List[Dict[str, Any]]:
    """
    Provide sample workflow node configurations for testing.

    Returns:
        List of workflow node configurations
    """
    return [
        {
            "node_type": "PythonCodeNode",
            "node_id": "start_node",
            "parameters": {
                "code": "result = {'message': 'Workflow started', 'status': 'initialized'}"
            },
        },
        {
            "node_type": "PythonCodeNode",
            "node_id": "processing_node",
            "parameters": {
                "code": "result = {'message': 'Data processed', 'data': input_data, 'processed': True}",
                "input_data": {"value": 42, "type": "test"},
            },
        },
        {
            "node_type": "PythonCodeNode",
            "node_id": "analysis_node",
            "parameters": {
                "code": "result = {'analysis': 'complete', 'input_received': bool(input_data)}",
                "input_data": {"processed": True},
            },
        },
        {
            "node_type": "PythonCodeNode",
            "node_id": "output_node",
            "parameters": {
                "code": "result = {'message': 'Workflow completed', 'final_status': 'success'}"
            },
        },
    ]


def test_data_samples() -> Dict[str, Any]:
    """
    Provide sample test data for various testing scenarios.

    Returns:
        Dictionary containing different types of test data
    """
    return {
        "simple_data": {"message": "Hello, test!", "value": 123, "flag": True},
        "complex_data": {
            "records": [
                {"id": 1, "name": "Test Record 1", "data": {"score": 95.5}},
                {"id": 2, "name": "Test Record 2", "data": {"score": 87.3}},
                {"id": 3, "name": "Test Record 3", "data": {"score": 92.1}},
            ],
            "metadata": {
                "source": "test_system",
                "created_at": "2024-01-01T00:00:00Z",
                "version": "1.0",
            },
        },
        "workflow_data": {
            "input": {
                "task": "process_data",
                "parameters": {"threshold": 0.8, "batch_size": 10},
            },
            "expected_output": {
                "status": "completed",
                "processed_items": 10,
                "success_rate": 1.0,
            },
        },
    }


def docker_service_health_check(service_name: str) -> bool:
    """
    Check if a Docker service is healthy and running.

    Args:
        service_name: Name of the Docker service to check

    Returns:
        True if service is healthy, False otherwise
    """
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={service_name}",
                "--format",
                "{{.Status}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            status = result.stdout.strip()
            return "Up" in status and "(healthy)" in status
        else:
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def test_environment_config() -> Dict[str, Any]:
    """
    Provide test environment configuration for Docker services.

    Returns:
        Test environment configuration dictionary
    """
    return {
        "database": {
            "host": "localhost",
            "port": 5434,  # Test-specific PostgreSQL port
            "database": "kailash_test",
            "user": "test_user",
            "password": "test_password",
        },
        "redis": {
            "host": "localhost",
            "port": 6380,  # Test-specific Redis port
            "database": 0,
        },
        "services": {
            "postgresql": "kailash_sdk_test_postgres",
            "redis": "kailash_sdk_test_redis",
            "ollama": "kailash_sdk_test_ollama",
        },
        "timeouts": {"service_startup": 30, "health_check": 10, "test_execution": 300},
    }


def load_test_scenarios() -> List[Dict[str, Any]]:
    """
    Provide load testing scenarios for performance validation.

    Returns:
        List of load testing scenarios
    """
    return [
        {
            "name": "light_load",
            "description": "Light load testing with minimal resources",
            "agents": 2,
            "workflows_per_agent": 1,
            "nodes_per_workflow": 2,
            "expected_max_time": 5.0,
        },
        {
            "name": "medium_load",
            "description": "Medium load testing with moderate resources",
            "agents": 5,
            "workflows_per_agent": 3,
            "nodes_per_workflow": 4,
            "expected_max_time": 10.0,
        },
        {
            "name": "heavy_load",
            "description": "Heavy load testing with significant resources",
            "agents": 10,
            "workflows_per_agent": 5,
            "nodes_per_workflow": 6,
            "expected_max_time": 30.0,
        },
    ]


def enterprise_test_config() -> Dict[str, Any]:
    """
    Provide enterprise feature test configuration.

    Returns:
        Enterprise testing configuration
    """
    return {
        "audit_trail": {"enabled": True, "level": "full", "storage": "database"},
        "compliance": {
            "mode": "enterprise",
            "requirements": ["audit_trail", "access_control", "data_encryption"],
        },
        "security": {"level": "high", "encryption": True, "access_control": True},
        "monitoring": {"enabled": True, "metrics": ["performance", "usage", "errors"]},
    }


def multi_agent_test_scenarios() -> List[Dict[str, Any]]:
    """
    Provide multi-agent testing scenarios.

    Returns:
        List of multi-agent test scenarios
    """
    return [
        {
            "name": "simple_collaboration",
            "description": "Two agents collaborating on simple task",
            "agents": [
                {"name": "agent_a", "role": "data_processor"},
                {"name": "agent_b", "role": "result_analyzer"},
            ],
            "workflow_pattern": "sequential",
            "expected_outcomes": ["data_processed", "analysis_complete"],
        },
        {
            "name": "complex_coordination",
            "description": "Multiple agents with complex coordination",
            "agents": [
                {"name": "agent_1", "role": "data_ingestion"},
                {"name": "agent_2", "role": "data_processing"},
                {"name": "agent_3", "role": "data_analysis"},
                {"name": "agent_4", "role": "report_generation"},
            ],
            "workflow_pattern": "pipeline",
            "expected_outcomes": [
                "ingestion_complete",
                "processing_complete",
                "analysis_complete",
                "report_ready",
            ],
        },
        {
            "name": "parallel_processing",
            "description": "Multiple agents processing in parallel",
            "agents": [
                {"name": "worker_1", "role": "parallel_processor"},
                {"name": "worker_2", "role": "parallel_processor"},
                {"name": "worker_3", "role": "parallel_processor"},
                {"name": "coordinator", "role": "result_aggregator"},
            ],
            "workflow_pattern": "parallel_with_aggregation",
            "expected_outcomes": ["parallel_processing_complete", "results_aggregated"],
        },
    ]


def framework_validation_checklist() -> Dict[str, List[str]]:
    """
    Provide validation checklist for framework testing.

    Returns:
        Dictionary with validation categories and checks
    """
    return {
        "initialization": [
            "Framework creates successfully",
            "Configuration is properly loaded",
            "Runtime is initialized",
            "Default settings are applied",
        ],
        "agent_management": [
            "Agents can be created",
            "Agent configurations are validated",
            "Multiple agents can coexist",
            "Agent lifecycle is managed correctly",
        ],
        "workflow_execution": [
            "Workflows can be created",
            "Nodes can be added and configured",
            "Workflows can be executed",
            "Results are returned correctly",
        ],
        "integration": [
            "Core SDK integration works",
            "WorkflowBuilder integration works",
            "LocalRuntime integration works",
            "Real infrastructure can be used",
        ],
        "performance": [
            "Framework initialization is fast",
            "Agent creation is efficient",
            "Workflow execution meets SLA",
            "Memory usage is reasonable",
        ],
        "error_handling": [
            "Framework handles errors gracefully",
            "Failed workflows don't crash framework",
            "Error messages are informative",
            "Recovery mechanisms work",
        ],
    }
