"""
Example Test File Demonstrating Standardized Fixture Usage

This file shows how to properly use the available fixtures across all three
test tiers with proper performance monitoring and infrastructure integration.

Key Patterns Demonstrated:
- Tier-specific fixture usage
- Performance monitoring integration
- Infrastructure service management
- Cross-tier configuration patterns
- Error handling and cleanup
"""

import json
import time
from unittest.mock import MagicMock

import pytest


# Tier 1 (Unit) Tests - Fast, isolated, mocking allowed
@pytest.mark.unit
def test_unit_fixture_basic_usage(
    performance_tracker,
):
    """Example unit test with minimal setup and performance tracking."""
    performance_tracker.start_timer("unit_test_execution")

    # Test basic unit functionality with minimal setup
    test_data = {"prompt": "test prompt", "expected": "test response"}

    # Verify the data structure
    assert test_data is not None
    assert "prompt" in test_data
    assert "expected" in test_data

    # Basic processing simulation
    result = {"status": "success", "data": test_data}
    assert result["status"] == "success"

    # Assert performance requirements (Tier 1: <1 second)
    performance_tracker.end_timer("unit_test_execution")
    performance_tracker.assert_performance("unit_test_execution", 1000)


@pytest.mark.unit
def test_unit_mock_usage(performance_tracker):
    """Example unit test using mock providers."""
    # Test with mocked external service (unit tests can use mocks)
    mock_llm_service = MagicMock()
    mock_llm_service.generate.return_value = {
        "response": "This is a mocked response",
        "usage": {"tokens": 10},
    }

    # Execute test with mock
    result = mock_llm_service.generate("test prompt")

    # Verify mocked behavior
    assert result["response"] == "This is a mocked response"
    assert result["usage"]["tokens"] == 10
    mock_llm_service.generate.assert_called_once_with("test prompt")


# Tier 2 (Integration) Tests - Real services, NO MOCKING
@pytest.mark.integration
def test_integration_real_database(
    integration_database_connection,
    performance_tracker,
):
    """Example integration test using REAL PostgreSQL database - NO MOCKING."""
    performance_tracker.start_timer("database_integration")

    # Use REAL PostgreSQL database (no mocking)
    cursor = integration_database_connection.cursor()

    # Test database operations
    cursor.execute("SELECT 1 as test_value")
    result = cursor.fetchone()

    assert result["test_value"] == 1

    # Assert performance requirements (Tier 2: <5 seconds)
    performance_tracker.end_timer("database_integration")
    performance_tracker.assert_performance("database_integration", 5000)


@pytest.mark.integration
def test_integration_redis_operations(
    integration_redis_connection, performance_tracker
):
    """Example integration test using REAL Redis - NO MOCKING."""
    performance_tracker.start_timer("redis_integration")

    # Use REAL Redis instance (no mocking)
    integration_redis_connection.set("integration_test:key", "test_value")
    result = integration_redis_connection.get("integration_test:key")

    assert result == "test_value"

    # Test expiration
    integration_redis_connection.setex("integration_test:expire", 1, "expire_test")
    assert integration_redis_connection.exists("integration_test:expire")

    performance_tracker.end_timer("redis_integration")
    performance_tracker.assert_performance("redis_integration", 5000)


@pytest.mark.integration
def test_integration_multi_service(
    integration_database_connection, integration_redis_connection, performance_tracker
):
    """Example integration test using multiple real services."""
    performance_tracker.start_timer("multi_service_integration")

    # Database operation
    cursor = integration_database_connection.cursor()
    cursor.execute(
        """
        CREATE TEMP TABLE integration_test (
            id SERIAL PRIMARY KEY,
            data TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """
    )

    cursor.execute(
        "INSERT INTO integration_test (data) VALUES (%s) RETURNING id",
        ("integration_test_data",),
    )
    db_result = cursor.fetchone()
    test_id = db_result["id"]

    # Cache the result in Redis
    cache_key = f"integration_test:record:{test_id}"
    integration_redis_connection.setex(
        cache_key, 300, f"cached_data_for_{test_id}"  # 5 minute expiration
    )

    # Verify both services
    cached_result = integration_redis_connection.get(cache_key)
    assert cached_result == f"cached_data_for_{test_id}"

    # Cleanup
    cursor.execute("DELETE FROM integration_test WHERE id = %s", (test_id,))
    integration_redis_connection.delete(cache_key)

    performance_tracker.end_timer("multi_service_integration")
    performance_tracker.assert_performance("multi_service_integration", 5000)


# Tier 3 (E2E) Tests - Complete infrastructure - NO MOCKING
@pytest.mark.e2e
def test_e2e_complete_infrastructure(
    e2e_database_setup,
    performance_tracker,
):
    """Example E2E test with complete infrastructure - NO MOCKING."""
    performance_tracker.start_timer("complete_workflow")

    # Complete E2E workflow with real infrastructure
    cursor = e2e_database_setup.cursor()
    cursor.execute(
        """
        CREATE TEMP TABLE e2e_workflow_executions (
            id SERIAL PRIMARY KEY,
            workflow_name VARCHAR(255),
            status VARCHAR(50) DEFAULT 'pending',
            results JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Simulate complete workflow execution
    cursor.execute(
        """INSERT INTO e2e_workflow_executions (workflow_name)
           VALUES (%s) RETURNING id""",
        ("test_workflow",),
    )
    execution_id = cursor.fetchone()["id"]

    # Simulate workflow processing
    time.sleep(0.1)  # Simulate processing time

    cursor.execute(
        """UPDATE e2e_workflow_executions
           SET status = %s, results = %s
           WHERE id = %s""",
        ("completed", json.dumps({"result": "success"}), execution_id),
    )

    # Verify complete workflow
    cursor.execute(
        "SELECT * FROM e2e_workflow_executions WHERE id = %s", (execution_id,)
    )
    result = cursor.fetchone()

    assert result["status"] == "completed"
    assert result["results"]["result"] == "success"
    assert result["workflow_name"] == "test_workflow"

    # Cleanup
    cursor.execute("DELETE FROM e2e_workflow_executions WHERE id = %s", (execution_id,))

    performance_tracker.end_timer("complete_workflow")
    performance_tracker.assert_performance("complete_workflow", 10000)


@pytest.mark.e2e
def test_e2e_enterprise_workflow(e2e_database_setup, performance_tracker):
    """Example E2E test simulating enterprise workflow."""
    performance_tracker.start_timer("enterprise_workflow")

    # Enterprise workflow simulation
    cursor = e2e_database_setup.cursor()
    cursor.execute(
        """
        CREATE TEMP TABLE e2e_audit_trail (
            id SERIAL PRIMARY KEY,
            operation VARCHAR(255),
            details JSONB,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Simulate multi-step enterprise workflow
    operations = [
        ("data_ingestion", {"source": "csv", "rows": 1000}),
        ("data_validation", {"errors": 0, "warnings": 5}),
        ("data_processing", {"processed": 1000, "skipped": 0}),
        ("result_generation", {"reports": 3, "alerts": 1}),
    ]

    for operation, details in operations:
        cursor.execute(
            """INSERT INTO e2e_audit_trail (operation, details)
               VALUES (%s, %s)""",
            (operation, json.dumps(details)),
        )
        time.sleep(0.01)  # Simulate processing delay

    # Verify enterprise workflow completion
    cursor.execute("SELECT COUNT(*) as audit_count FROM e2e_audit_trail")
    audit_count = cursor.fetchone()["audit_count"]
    assert audit_count == 4

    cursor.execute("SELECT * FROM e2e_audit_trail ORDER BY timestamp")
    audit_trail = cursor.fetchall()

    assert audit_trail[0]["operation"] == "data_ingestion"
    assert audit_trail[-1]["operation"] == "result_generation"
    assert audit_trail[-1]["details"]["reports"] == 3

    # Cleanup
    cursor.execute("DELETE FROM e2e_audit_trail")

    performance_tracker.end_timer("enterprise_workflow")
    performance_tracker.assert_performance("enterprise_workflow", 10000)


# Performance comparison test
@pytest.mark.performance
def test_cross_tier_performance_comparison(
    performance_tracker,
):
    """Validate performance characteristics across all tiers."""
    # Test data sizes appropriate for each tier
    data_sizes = {"unit": 10, "integration": 100, "e2e": 500}

    for tier_name in ["unit", "integration", "e2e"]:
        processed_data = []
        performance_tracker.start_timer(f"data_creation_{tier_name}")
        # Simulate data processing for each tier
        for i in range(data_sizes[tier_name]):
            data = {"id": i, "value": f"test_data_{i}"}
            processed_data.append(data)

        performance_tracker.end_timer(f"data_creation_{tier_name}")
        tier_limits = {"unit": 1000, "integration": 5000, "e2e": 10000}
        performance_tracker.assert_performance(
            f"data_creation_{tier_name}", tier_limits[tier_name]
        )

    # Verify all measurements were recorded
    for tier_name in ["unit", "integration", "e2e"]:
        measurement = performance_tracker.get_measurement(f"data_creation_{tier_name}")
        assert measurement is not None


# Error handling examples
@pytest.mark.unit
def test_fixture_error_handling():
    """Example showing proper error handling with fixtures."""
    # Test error scenarios
    with pytest.raises(KeyError):
        test_data = {"valid_key": "value"}
        _ = test_data["nonexistent_key"]

    # Test recovery patterns
    test_data = {"valid_key": "value"}
    assert test_data.get("valid_key") == "value"
    assert test_data.get("nonexistent_key") is None


# Cleanup testing
@pytest.mark.integration
def test_infrastructure_cleanup(
    integration_database_connection,
):
    """Example showing proper cleanup patterns."""
    cursor = integration_database_connection.cursor()
    cursor.execute(
        """
        CREATE TEMP TABLE cleanup_test (
            id SERIAL PRIMARY KEY,
            data TEXT
        )
    """
    )

    cursor.execute("INSERT INTO cleanup_test (data) VALUES (%s)", ("test",))
    cursor.execute("SELECT COUNT(*) as count FROM cleanup_test")

    count = cursor.fetchone()["count"]
    assert count == 1

    # Cleanup is handled automatically by TEMP table
    # This demonstrates proper resource cleanup patterns


# Example test execution patterns
if __name__ == "__main__":
    # This shows how individual tests can be run for development
    import subprocess

    # Run just this file
    subprocess.run(
        ["python", "-m", "pytest", __file__ + "::test_integration_real_database", "-v"]
    )
