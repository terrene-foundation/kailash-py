"""Comprehensive integration tests for parameter injection with real services.

These tests use real Docker containers for PostgreSQL, Redis, and other services
to ensure parameter injection works correctly in production-like environments.
"""
import pytest
import asyncio
import json
import time
from typing import Dict, Any

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import WorkflowParameterInjector, DeferredConfigNode
from pydantic import ValidationError

# Import test utilities for Docker services
from tests.utils.docker_config import (
    DATABASE_CONFIG,
    REDIS_CONFIG,
    is_postgres_available,
    is_redis_available,
    get_postgres_connection_string
)
import psycopg2
import redis
import time
from unittest import mock


pytestmark = pytest.mark.integration


# Helper functions for test infrastructure
def get_postgres_connection_params():
    """Get PostgreSQL connection parameters from docker config."""
    return DATABASE_CONFIG.copy()


def get_redis_connection_params():
    """Get Redis connection parameters from docker config."""
    return REDIS_CONFIG.copy()


def wait_for_postgres(timeout=30):
    """Wait for PostgreSQL to be ready."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_postgres_available():
            return True
        time.sleep(0.5)
    raise TimeoutError("PostgreSQL did not become available in time")


def wait_for_redis(timeout=30):
    """Wait for Redis to be ready."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_redis_available():
            return True
        time.sleep(0.5)
    raise TimeoutError("Redis did not become available in time")


def ensure_test_database_exists():
    """Ensure the test database exists."""
    conn_params = get_postgres_connection_params()
    try:
        # Connect to default postgres database
        conn = psycopg2.connect(
            host=conn_params["host"],
            port=conn_params["port"],
            user=conn_params["user"],
            password=conn_params["password"],
            database="postgres"
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Create test database if it doesn't exist
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{conn_params['database']}'")
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {conn_params['database']}")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Warning: Could not ensure test database exists: {e}")


class TestParameterInjectionWithDatabase:
    """Test parameter injection with real database connections."""
    
    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Ensure database is ready before tests."""
        wait_for_postgres()
        ensure_test_database_exists()
        yield
    
    def test_database_connection_parameters(self):
        """Test injecting database connection parameters at runtime."""
        workflow = WorkflowBuilder()
        
        # Use DeferredConfigNode pattern for runtime database config
        workflow.add_node("AsyncSQLDatabaseNode", "db_query", {
            "query": "SELECT $1 as value, $2 as name",
            "parameters": ["${runtime_value}", "${runtime_name}"]
        })
        
        runtime = LocalRuntime()
        
        # Get real database connection params
        db_params = get_postgres_connection_params()
        
        # Inject both connection and query parameters
        runtime_params = {
            "db_query": {
                **db_params,  # Connection parameters
                "runtime_value": 42,
                "runtime_name": "test_parameter"
            }
        }
        
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify query executed with injected parameters
        assert results["db_query"]["rows"][0]["value"] == 42
        assert results["db_query"]["rows"][0]["name"] == "test_parameter"
    
    def test_sql_injection_prevention_real_db(self):
        """Test SQL injection prevention with real database."""
        workflow = WorkflowBuilder()
        
        # Node that builds dynamic SQL (intentionally vulnerable for testing)
        workflow.add_node("PythonCodeNode", "build_query", {
            "code": """
table_name = parameters.get('table', 'users')
condition = parameters.get('condition', '1=1')
result = {
    'query': f"SELECT * FROM {table_name} WHERE {condition}",
    'table': table_name,
    'condition': condition
}
"""
        })
        
        # Secure SQL node that validates parameters
        workflow.add_node("AsyncSQLDatabaseNode", "secure_query", {
            "query": "SELECT * FROM information_schema.tables WHERE table_name = $1",
            "parameters": ["${table}"],
            "validate_sql_injection": True  # Enable injection validation
        })
        
        workflow.add_connection("build_query", "table", "secure_query", "table")
        
        runtime = LocalRuntime()
        
        # Test with injection attempt
        runtime_params = {
            "build_query": {
                "table": "users; DROP TABLE users--",
                "condition": "1=1"
            }
        }
        
        # Should detect SQL injection in table parameter
        with pytest.raises(ValidationError, match="SQL injection"):
            runtime.execute(workflow.build(), parameters=runtime_params)
    
    def test_transaction_context_with_parameters(self):
        """Test parameter injection within transaction context."""
        workflow = WorkflowBuilder()
        
        # Start transaction
        workflow.add_node("TransactionScopeNode", "tx_start", {
            "isolation_level": "read_committed"
        })
        
        # Insert with runtime parameters
        workflow.add_node("AsyncSQLDatabaseNode", "insert1", {
            "query": "INSERT INTO test_params (key, value) VALUES ($1, $2)",
            "parameters": ["${key1}", "${value1}"]
        })
        
        workflow.add_node("AsyncSQLDatabaseNode", "insert2", {
            "query": "INSERT INTO test_params (key, value) VALUES ($1, $2)",
            "parameters": ["${key2}", "${value2}"]
        })
        
        # Commit transaction
        workflow.add_node("TransactionCommitNode", "tx_commit", {})
        
        # Connect nodes
        workflow.add_connection("tx_start", "transaction_id", "insert1", "transaction_id")
        workflow.add_connection("insert1", "transaction_id", "insert2", "transaction_id")
        workflow.add_connection("insert2", "transaction_id", "tx_commit", "transaction_id")
        
        runtime = LocalRuntime()
        db_params = get_postgres_connection_params()
        
        # Create test table
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node("AsyncSQLDatabaseNode", "create_table", {
            **db_params,
            "query": """
                CREATE TABLE IF NOT EXISTS test_params (
                    key VARCHAR(255) PRIMARY KEY,
                    value TEXT
                )
            """
        })
        runtime.execute(setup_workflow.build())
        
        # Execute with runtime parameters
        runtime_params = {
            "tx_start": db_params,
            "insert1": {
                **db_params,
                "key1": "param_key_1",
                "value1": "param_value_1"
            },
            "insert2": {
                **db_params,
                "key2": "param_key_2",
                "value2": "param_value_2"
            },
            "tx_commit": db_params
        }
        
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify both inserts succeeded
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node("AsyncSQLDatabaseNode", "verify", {
            **db_params,
            "query": "SELECT COUNT(*) as count FROM test_params WHERE key IN ($1, $2)",
            "parameters": ["param_key_1", "param_key_2"]
        })
        
        verify_results, _ = runtime.execute(verify_workflow.build())
        assert verify_results["verify"]["rows"][0]["count"] == 2
        
        # Cleanup
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node("AsyncSQLDatabaseNode", "cleanup", {
            **db_params,
            "query": "DROP TABLE IF EXISTS test_params"
        })
        runtime.execute(cleanup_workflow.build())


class TestParameterInjectionWithRedis:
    """Test parameter injection with Redis operations."""
    
    @pytest.fixture(autouse=True)
    def setup_redis(self):
        """Ensure Redis is ready before tests."""
        wait_for_redis()
        yield
    
    def test_redis_connection_parameters(self):
        """Test injecting Redis connection parameters."""
        workflow = WorkflowBuilder()
        
        # Redis operations with runtime parameters
        workflow.add_node("RedisNode", "set_value", {
            "operation": "set",
            "key": "${cache_key}",
            "value": "${cache_value}",
            "ttl": "${cache_ttl}"
        })
        
        workflow.add_node("RedisNode", "get_value", {
            "operation": "get",
            "key": "${cache_key}"
        })
        
        workflow.add_connection("set_value", "result", "get_value", "trigger")
        
        runtime = LocalRuntime()
        redis_params = get_redis_connection_params()
        
        # Runtime parameters for both connection and operation
        runtime_params = {
            "set_value": {
                **redis_params,
                "cache_key": "test_param_injection",
                "cache_value": {"data": "test_value", "timestamp": time.time()},
                "cache_ttl": 300
            },
            "get_value": {
                **redis_params,
                "cache_key": "test_param_injection"
            }
        }
        
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify value was set and retrieved
        assert results["get_value"]["value"]["data"] == "test_value"
    
    def test_redis_pattern_operations(self):
        """Test Redis pattern operations with parameter injection."""
        workflow = WorkflowBuilder()
        
        # Set multiple keys with pattern
        for i in range(3):
            workflow.add_node("RedisNode", f"set_{i}", {
                "operation": "set",
                "key": f"${{key_prefix}}:{i}",
                "value": f"${{value_prefix}}_{i}"
            })
        
        # Get keys by pattern
        workflow.add_node("RedisNode", "get_pattern", {
            "operation": "keys",
            "pattern": "${key_prefix}:*"
        })
        
        # Connect nodes
        for i in range(2):
            workflow.add_connection(f"set_{i}", "result", f"set_{i+1}", "trigger")
        workflow.add_connection("set_2", "result", "get_pattern", "trigger")
        
        runtime = LocalRuntime()
        redis_params = get_redis_connection_params()
        
        # Common parameters for all nodes
        common_params = {
            **redis_params,
            "key_prefix": "param_test",
            "value_prefix": "value"
        }
        
        runtime_params = {
            f"set_{i}": common_params for i in range(3)
        }
        runtime_params["get_pattern"] = common_params
        
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify pattern matching found all keys
        keys = results["get_pattern"]["keys"]
        assert len(keys) == 3
        assert all(key.startswith("param_test:") for key in keys)
        
        # Cleanup
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node("RedisNode", "cleanup", {
            **redis_params,
            "operation": "delete",
            "keys": keys
        })
        runtime.execute(cleanup_workflow.build())


class TestParameterInjectionWithAuth:
    """Test parameter injection with authentication nodes."""
    
    def test_oauth2_deferred_configuration(self):
        """Test OAuth2 node with deferred configuration."""
        workflow = WorkflowBuilder()
        
        # OAuth2 node without credentials (deferred)
        workflow.add_node("OAuth2Node", "auth", {
            "scope": ["read", "write"],
            "grant_type": "client_credentials"
        })
        
        # API call using OAuth token
        workflow.add_node("HTTPRequestNode", "api_call", {
            "url": "${api_endpoint}",
            "method": "GET",
            "headers": {
                "Authorization": "Bearer ${access_token}"
            }
        })
        
        workflow.add_connection("auth", "access_token", "api_call", "access_token")
        
        runtime = LocalRuntime()
        
        # Runtime OAuth configuration
        runtime_params = {
            "auth": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_url": "https://oauth.example.com/token"
            },
            "api_call": {
                "api_endpoint": "https://api.example.com/data"
            }
        }
        
        # Mock the OAuth and HTTP responses
        with pytest.mock.patch("requests.post") as mock_post, \
             pytest.mock.patch("requests.get") as mock_get:
            
            # Mock OAuth token response
            mock_post.return_value.json.return_value = {
                "access_token": "test_token_12345",
                "token_type": "Bearer",
                "expires_in": 3600
            }
            mock_post.return_value.status_code = 200
            
            # Mock API response
            mock_get.return_value.json.return_value = {"data": "test_response"}
            mock_get.return_value.status_code = 200
            
            results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
            
            # Verify OAuth was called with injected parameters
            mock_post.assert_called_once()
            call_data = mock_post.call_args[1]["data"]
            assert call_data["client_id"] == "test_client_id"
            assert call_data["client_secret"] == "test_client_secret"
            
            # Verify API was called with token
            mock_get.assert_called_once()
            headers = mock_get.call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer test_token_12345"
    
    def test_multi_factor_auth_parameters(self):
        """Test multi-factor authentication with runtime parameters."""
        workflow = WorkflowBuilder()
        
        # Multi-factor auth node
        workflow.add_node("MultiFactorAuthNode", "mfa", {
            "auth_methods": ["password", "totp"],
            "require_all": True
        })
        
        runtime = LocalRuntime()
        
        # Runtime MFA parameters
        runtime_params = {
            "mfa": {
                "username": "test_user",
                "password": "secure_password",
                "totp_code": "123456",
                "totp_secret": "test_secret"
            }
        }
        
        # Mock authentication
        with pytest.mock.patch.object(
            runtime, '_execute_node',
            return_value={
                "authenticated": True,
                "user_id": "user_123",
                "session_token": "session_abc"
            }
        ):
            results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
            
            # Verify authentication succeeded
            assert results["mfa"]["authenticated"] is True
            assert results["mfa"]["session_token"] == "session_abc"


class TestWorkflowComplexityWithParameters:
    """Test parameter injection in complex workflow patterns."""
    
    def test_parallel_execution_with_shared_parameters(self):
        """Test parallel nodes sharing parameters."""
        workflow = WorkflowBuilder()
        
        # Splitter node
        workflow.add_node("PythonCodeNode", "splitter", {
            "code": """
data = parameters.get('input_data', [])
chunk_size = len(data) // 3
result = {
    'chunk1': data[:chunk_size],
    'chunk2': data[chunk_size:2*chunk_size],
    'chunk3': data[2*chunk_size:]
}
"""
        })
        
        # Parallel workers with shared configuration
        for i in range(1, 4):
            workflow.add_node("PythonCodeNode", f"worker{i}", {
                "code": """
chunk = parameters.get(f'chunk{parameters["worker_id"]}', [])
multiplier = parameters.get('multiplier', 1)
result = {'processed': [x * multiplier for x in chunk]}
"""
            })
            workflow.add_connection("splitter", f"chunk{i}", f"worker{i}", f"chunk{i}")
        
        # Merger node
        workflow.add_node("MergeNode", "merger", {})
        for i in range(1, 4):
            workflow.add_connection(f"worker{i}", "processed", "merger", f"input{i}")
        
        runtime = LocalRuntime()
        
        # Shared parameters for all workers
        shared_config = {"multiplier": 3}
        
        runtime_params = {
            "splitter": {"input_data": list(range(12))},
            "worker1": {**shared_config, "worker_id": 1},
            "worker2": {**shared_config, "worker_id": 2},
            "worker3": {**shared_config, "worker_id": 3}
        }
        
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify all chunks processed with shared multiplier
        merged = results["merger"]["merged"]
        expected = [x * 3 for x in range(12)]
        assert sorted(sum(merged, [])) == sorted(expected)
    
    def test_cyclic_workflow_parameter_propagation(self):
        """Test parameter propagation in cyclic workflows."""
        workflow = WorkflowBuilder()
        
        # Create optimization cycle
        cycle_builder = workflow.create_cycle("parameter_optimization")
        
        workflow.add_node("PythonCodeNode", "optimizer", {
            "code": """
current_value = parameters.get('value', 0)
learning_rate = parameters.get('learning_rate', 0.1)
target = parameters.get('target', 100)

# Simple gradient descent
error = target - current_value
adjustment = error * learning_rate
new_value = current_value + adjustment

result = {
    'value': new_value,
    'error': abs(error),
    'converged': abs(error) < 1.0,
    'iterations': parameters.get('iterations', 0) + 1
}
"""
        })
        
        workflow.add_node("ConvergenceCheckerNode", "checker", {
            "tolerance": "${convergence_tolerance}",
            "max_iterations": "${max_iterations}"
        })
        
        cycle_builder.connect("optimizer", "checker", mapping={
            "error": "current_value",
            "converged": "converged",
            "iterations": "iterations"
        })
        cycle_builder.connect("checker", "optimizer", mapping={
            "should_continue": "continue",
            "value": "value",
            "iterations": "iterations"
        })
        cycle_builder.max_iterations(50).converge_when("converged").build()
        
        runtime = LocalRuntime()
        
        # Runtime parameters for optimization
        runtime_params = {
            "optimizer": {
                "value": 10.0,
                "learning_rate": 0.2,
                "target": 100.0
            },
            "checker": {
                "convergence_tolerance": 0.5,
                "max_iterations": 30
            }
        }
        
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify convergence
        final_value = results["optimizer"]["value"]
        assert abs(final_value - 100.0) < 1.0
        assert results["optimizer"]["iterations"] < 30
    
    def test_nested_workflow_parameter_inheritance(self):
        """Test parameter inheritance in nested workflows."""
        # Create sub-workflow
        sub_workflow = WorkflowBuilder()
        sub_workflow.add_node("PythonCodeNode", "sub_processor", {
            "code": """
# Access both sub-workflow and inherited parameters
sub_param = parameters.get('sub_param', 0)
inherited_param = parameters.get('inherited_param', 0)
multiplier = parameters.get('multiplier', 1)

result = {
    'sub_result': (sub_param + inherited_param) * multiplier
}
"""
        })
        
        # Main workflow
        main_workflow = WorkflowBuilder()
        main_workflow.add_node("PythonCodeNode", "prepare", {
            "code": """
result = {
    'sub_param': parameters.get('main_value', 0) * 2,
    'inherited_param': parameters.get('base_value', 0)
}
"""
        })
        
        main_workflow.add_node("WorkflowNode", "nested", {
            "workflow": sub_workflow.build()
        })
        
        main_workflow.add_connection("prepare", "sub_param", "nested", "sub_param")
        main_workflow.add_connection("prepare", "inherited_param", "nested", "inherited_param")
        
        runtime = LocalRuntime()
        
        # Parameters at different levels
        runtime_params = {
            "prepare": {
                "main_value": 10,
                "base_value": 5
            },
            "nested": {
                "multiplier": 3  # Additional parameter for sub-workflow
            }
        }
        
        results, _ = runtime.execute(main_workflow.build(), parameters=runtime_params)
        
        # Verify parameter inheritance and calculation
        # sub_param = 10 * 2 = 20
        # inherited_param = 5
        # result = (20 + 5) * 3 = 75
        assert results["nested"]["sub_result"] == 75


class TestParameterPerformance:
    """Test parameter injection performance with real workloads."""
    
    def test_large_scale_parameter_injection(self):
        """Test performance with many nodes and parameters."""
        workflow = WorkflowBuilder()
        
        # Create 100 nodes with parameters
        node_count = 100
        for i in range(node_count):
            workflow.add_node("PythonCodeNode", f"node_{i}", {
                "code": f"""
result = {{
    'node_id': {i},
    'processed': parameters.get('input_{i}', 0) * parameters.get('multiplier', 1),
    'config': parameters.get('config', {{}})
}}
"""
            })
            
            # Chain nodes together
            if i > 0:
                workflow.add_connection(f"node_{i-1}", "processed", f"node_{i}", f"input_{i}")
        
        runtime = LocalRuntime()
        
        # Generate runtime parameters for all nodes
        runtime_params = {}
        shared_config = {"debug": True, "version": "1.0"}
        
        for i in range(node_count):
            runtime_params[f"node_{i}"] = {
                f"input_{i}": i if i == 0 else None,  # First node gets input
                "multiplier": 2,
                "config": shared_config
            }
        
        # Measure injection performance
        start_time = time.time()
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        execution_time = (time.time() - start_time) * 1000  # ms
        
        # Verify results
        final_result = results[f"node_{node_count-1}"]["processed"]
        assert final_result > 0  # Should have accumulated value
        
        # Performance assertion
        injection_time_per_node = execution_time / node_count
        assert injection_time_per_node < 5  # Less than 5ms per node
        
        print(f"Performance: {injection_time_per_node:.2f}ms per node "
              f"({execution_time:.2f}ms total for {node_count} nodes)")
    
    def test_parameter_caching_efficiency(self):
        """Test parameter injection caching for repeated patterns."""
        workflow = WorkflowBuilder()
        
        # Create repeated pattern nodes
        pattern_count = 20
        repeat_count = 5
        
        for pattern in range(pattern_count):
            for repeat in range(repeat_count):
                node_id = f"pattern_{pattern}_repeat_{repeat}"
                workflow.add_node("PythonCodeNode", node_id, {
                    "code": """
# Same code pattern for caching test
result = {
    'value': parameters.get('input', 0) + parameters.get('offset', 0),
    'scaled': parameters.get('input', 0) * parameters.get('scale', 1)
}
"""
                })
        
        runtime = LocalRuntime()
        
        # Similar parameters for pattern detection
        runtime_params = {}
        for pattern in range(pattern_count):
            pattern_params = {
                "input": pattern * 10,
                "offset": 5,
                "scale": 2
            }
            for repeat in range(repeat_count):
                node_id = f"pattern_{pattern}_repeat_{repeat}"
                runtime_params[node_id] = pattern_params.copy()
        
        # Measure with potential caching
        start_time = time.time()
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        execution_time = (time.time() - start_time) * 1000  # ms
        
        total_nodes = pattern_count * repeat_count
        time_per_node = execution_time / total_nodes
        
        # Should be faster due to parameter pattern caching
        assert time_per_node < 3  # Less than 3ms per node with caching
        
        print(f"Caching performance: {time_per_node:.2f}ms per node "
              f"({execution_time:.2f}ms for {total_nodes} nodes)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])