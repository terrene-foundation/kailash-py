"""End-to-end tests for parameter injection in production scenarios.

These tests validate complete user workflows with real infrastructure,
ensuring parameter injection works correctly in production use cases.
"""
import pytest
import asyncio
import json
import time
import os
from pathlib import Path
from typing import Dict, Any, List

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from pydantic import ValidationError

# Import test utilities
from tests.utils.docker_config import (
    DATABASE_CONFIG,
    REDIS_CONFIG,
    is_postgres_available,
    is_redis_available,
    get_postgres_connection_string
)
from tests.utils.parameter_test_harness import (
    ParameterTestHarness,
    WorkflowComplexity,
    ParameterSource
)
import psycopg2
import redis as redis_client


pytestmark = pytest.mark.e2e


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


class TestDataPipelineScenarios:
    """Test parameter injection in data pipeline scenarios."""
    
    @pytest.fixture(autouse=True)
    def setup_infrastructure(self):
        """Ensure all infrastructure is ready."""
        wait_for_postgres()
        wait_for_redis()
        ensure_test_database_exists()
        yield
    
    def test_etl_pipeline_with_runtime_config(self):
        """Test ETL pipeline with runtime configuration."""
        workflow = WorkflowBuilder()
        
        # Extract: Read CSV with runtime path
        workflow.add_node("CSVReaderNode", "extract", {
            "has_header": True,
            "delimiter": ","
        })
        
        # Transform: Process data with runtime rules
        workflow.add_node("PythonCodeNode", "transform", {
            "code": """
import pandas as pd

# Get runtime transformation rules
rules = parameters.get('transformation_rules', {})
data = parameters.get('data', [])

# Apply transformations
df = pd.DataFrame(data)

# Apply column mappings
column_mapping = rules.get('column_mapping', {})
if column_mapping:
    df = df.rename(columns=column_mapping)

# Apply filters
filters = rules.get('filters', [])
for filter_rule in filters:
    column = filter_rule['column']
    operator = filter_rule['operator']
    value = filter_rule['value']
    
    if operator == 'gt':
        df = df[df[column] > value]
    elif operator == 'lt':
        df = df[df[column] < value]
    elif operator == 'eq':
        df = df[df[column] == value]

# Apply aggregations
aggregations = rules.get('aggregations', {})
if aggregations:
    df = df.groupby(aggregations['group_by']).agg(aggregations['metrics'])

result = {'transformed_data': df.to_dict('records')}
"""
        })
        
        # Load: Write to database with runtime table
        workflow.add_node("AsyncSQLDatabaseNode", "create_table", {
            "query": """
                CREATE TABLE IF NOT EXISTS ${table_name} (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(255),
                    total_amount DECIMAL(10,2),
                    avg_amount DECIMAL(10,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
        })
        
        workflow.add_node("AsyncSQLDatabaseNode", "load", {
            "query": """
                INSERT INTO ${table_name} (category, total_amount, avg_amount)
                VALUES ($1, $2, $3)
            """,
            "bulk_insert": True
        })
        
        # Connect pipeline
        workflow.add_connection("extract", "data", "transform", "data")
        workflow.add_connection("transform", "transformed_data", "load", "data")
        workflow.add_connection("create_table", "result", "load", "trigger")
        
        runtime = LocalRuntime()
        
        # Create test CSV file
        test_data = """category,amount,quantity
Electronics,1500.00,3
Clothing,250.50,5
Electronics,2200.00,2
Food,45.75,10
Clothing,180.00,3
Electronics,890.00,1
"""
        csv_path = "/tmp/test_etl_data.csv"
        with open(csv_path, "w") as f:
            f.write(test_data)
        
        # Runtime parameters for the entire pipeline
        db_params = get_postgres_connection_params()
        
        runtime_params = {
            "extract": {
                "file_path": csv_path
            },
            "transform": {
                "transformation_rules": {
                    "column_mapping": {
                        "amount": "total_amount",
                        "quantity": "avg_amount"
                    },
                    "filters": [
                        {"column": "total_amount", "operator": "gt", "value": 100}
                    ],
                    "aggregations": {
                        "group_by": "category",
                        "metrics": {
                            "total_amount": "sum",
                            "avg_amount": "mean"
                        }
                    }
                }
            },
            "create_table": {
                **db_params,
                "table_name": "etl_results"
            },
            "load": {
                **db_params,
                "table_name": "etl_results",
                "parameters": lambda row: [
                    row["category"],
                    row["total_amount"],
                    row["avg_amount"]
                ]
            }
        }
        
        # Execute pipeline
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify results
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node("AsyncSQLDatabaseNode", "verify", {
            **db_params,
            "query": "SELECT * FROM etl_results ORDER BY category"
        })
        
        verify_results, _ = runtime.execute(verify_workflow.build())
        loaded_data = verify_results["verify"]["rows"]
        
        # Should have aggregated by category
        assert len(loaded_data) == 2  # Electronics and Clothing (Food filtered out)
        
        # Verify aggregations
        electronics = next(r for r in loaded_data if r["category"] == "Electronics")
        assert electronics["total_amount"] == 4590.00  # 1500 + 2200 + 890
        
        # Cleanup
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node("AsyncSQLDatabaseNode", "cleanup", {
            **db_params,
            "query": "DROP TABLE IF EXISTS etl_results"
        })
        runtime.execute(cleanup_workflow.build())
        
        # Remove test file
        os.remove(csv_path)
    
    def test_real_time_data_processing_pipeline(self):
        """Test real-time data processing with dynamic parameters."""
        workflow = WorkflowBuilder()
        
        # Simulate real-time data ingestion
        workflow.add_node("PythonCodeNode", "data_generator", {
            "code": """
import random
import time

# Generate simulated sensor data
batch_size = parameters.get('batch_size', 10)
sensor_id = parameters.get('sensor_id', 'sensor_001')

data_batch = []
for i in range(batch_size):
    data_batch.append({
        'sensor_id': sensor_id,
        'timestamp': time.time() + i,
        'temperature': random.uniform(20, 30),
        'humidity': random.uniform(40, 60),
        'pressure': random.uniform(1000, 1020)
    })

result = {'sensor_data': data_batch}
"""
        })
        
        # Process with runtime thresholds
        workflow.add_node("PythonCodeNode", "anomaly_detector", {
            "code": """
# Runtime anomaly thresholds
thresholds = parameters.get('thresholds', {})
sensor_data = parameters.get('sensor_data', [])

anomalies = []
for reading in sensor_data:
    is_anomaly = False
    reasons = []
    
    # Check each metric against thresholds
    for metric, limits in thresholds.items():
        if metric in reading:
            value = reading[metric]
            if value < limits.get('min', float('-inf')) or value > limits.get('max', float('inf')):
                is_anomaly = True
                reasons.append(f"{metric}: {value} (limits: {limits})")
    
    if is_anomaly:
        anomalies.append({
            'reading': reading,
            'reasons': reasons,
            'severity': 'high' if len(reasons) > 1 else 'medium'
        })

result = {
    'anomalies': anomalies,
    'anomaly_count': len(anomalies),
    'total_readings': len(sensor_data)
}
"""
        })
        
        # Cache results with runtime TTL
        workflow.add_node("RedisNode", "cache_results", {
            "operation": "set",
            "key": "${cache_key}",
            "ttl": "${cache_ttl}"
        })
        
        # Alert on anomalies
        workflow.add_node("PythonCodeNode", "alert_handler", {
            "code": """
anomalies = parameters.get('anomalies', [])
alert_config = parameters.get('alert_config', {})

alerts = []
for anomaly in anomalies:
    if anomaly['severity'] == 'high' or alert_config.get('alert_all', False):
        alerts.append({
            'sensor_id': anomaly['reading']['sensor_id'],
            'timestamp': anomaly['reading']['timestamp'],
            'severity': anomaly['severity'],
            'reasons': anomaly['reasons'],
            'notification_sent': True  # In real scenario, would send actual notification
        })

result = {'alerts_sent': alerts}
"""
        })
        
        # Connect pipeline
        workflow.add_connection("data_generator", "sensor_data", "anomaly_detector", "sensor_data")
        workflow.add_connection("anomaly_detector", "anomalies", "alert_handler", "anomalies")
        workflow.add_connection("anomaly_detector", "*", "cache_results", "value")
        
        runtime = LocalRuntime()
        redis_params = get_redis_connection_params()
        
        # Runtime parameters for monitoring different sensors
        sensors = ["sensor_001", "sensor_002", "sensor_003"]
        
        for sensor_id in sensors:
            runtime_params = {
                "data_generator": {
                    "batch_size": 20,
                    "sensor_id": sensor_id
                },
                "anomaly_detector": {
                    "thresholds": {
                        "temperature": {"min": 22, "max": 28},
                        "humidity": {"min": 45, "max": 55},
                        "pressure": {"min": 1005, "max": 1015}
                    }
                },
                "cache_results": {
                    **redis_params,
                    "cache_key": f"anomalies:{sensor_id}",
                    "cache_ttl": 3600  # 1 hour
                },
                "alert_handler": {
                    "alert_config": {
                        "alert_all": False,
                        "notification_channels": ["email", "sms"]
                    }
                }
            }
            
            results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
            
            # Verify processing
            assert results["anomaly_detector"]["total_readings"] == 20
            
            if results["anomaly_detector"]["anomaly_count"] > 0:
                # Verify alerts were generated for anomalies
                alerts = results["alert_handler"]["alerts_sent"]
                assert len(alerts) > 0
                assert all(alert["sensor_id"] == sensor_id for alert in alerts)
        
        # Cleanup Redis
        cleanup_workflow = WorkflowBuilder()
        for sensor_id in sensors:
            cleanup_workflow.add_node("RedisNode", f"cleanup_{sensor_id}", {
                **redis_params,
                "operation": "delete",
                "keys": [f"anomalies:{sensor_id}"]
            })
        runtime.execute(cleanup_workflow.build())


class TestMicroservicesIntegration:
    """Test parameter injection in microservices architecture."""
    
    def test_api_gateway_parameter_routing(self):
        """Test API gateway routing with runtime parameters."""
        workflow = WorkflowBuilder()
        
        # API Gateway node - routes to different services
        workflow.add_node("PythonCodeNode", "api_gateway", {
            "code": """
# Runtime routing configuration
request = parameters.get('request', {})
routing_rules = parameters.get('routing_rules', {})

# Determine target service
path = request.get('path', '/')
method = request.get('method', 'GET')

# Find matching route
target_service = None
for rule in routing_rules:
    if path.startswith(rule['path_prefix']) and method in rule['methods']:
        target_service = rule['service']
        break

# Add authentication headers
headers = request.get('headers', {})
if parameters.get('auth_required', True):
    headers['X-Auth-Token'] = parameters.get('auth_token', 'default_token')

result = {
    'target_service': target_service,
    'headers': headers,
    'request_data': request.get('data', {})
}
"""
        })
        
        # Service nodes for different endpoints
        workflow.add_node("SwitchNode", "service_router", {})
        
        # User service
        workflow.add_node("PythonCodeNode", "user_service", {
            "code": """
operation = parameters.get('operation', 'get')
user_id = parameters.get('user_id')
user_data = parameters.get('user_data', {})

# Simulate database operations
if operation == 'get':
    result = {
        'user': {
            'id': user_id,
            'name': f'User {user_id}',
            'email': f'user{user_id}@example.com',
            'created_at': '2024-01-01'
        }
    }
elif operation == 'update':
    result = {
        'user': {
            'id': user_id,
            **user_data,
            'updated_at': '2024-01-15'
        }
    }
else:
    result = {'error': 'Unknown operation'}
"""
        })
        
        # Order service
        workflow.add_node("PythonCodeNode", "order_service", {
            "code": """
operation = parameters.get('operation', 'list')
user_id = parameters.get('user_id')
filters = parameters.get('filters', {})

# Simulate order operations
if operation == 'list':
    orders = [
        {'id': 1, 'user_id': user_id, 'total': 150.00, 'status': 'completed'},
        {'id': 2, 'user_id': user_id, 'total': 75.50, 'status': 'pending'}
    ]
    
    # Apply filters
    if filters.get('status'):
        orders = [o for o in orders if o['status'] == filters['status']]
    
    result = {'orders': orders}
else:
    result = {'error': 'Unknown operation'}
"""
        })
        
        # Connect gateway to services
        workflow.add_connection("api_gateway", "target_service", "service_router", "condition")
        workflow.add_connection("service_router", "user_service", "user_service", "*")
        workflow.add_connection("service_router", "order_service", "order_service", "*")
        
        runtime = LocalRuntime()
        
        # Test different API requests
        test_requests = [
            {
                "request": {
                    "path": "/api/users/123",
                    "method": "GET",
                    "headers": {"Content-Type": "application/json"}
                },
                "expected_service": "user_service"
            },
            {
                "request": {
                    "path": "/api/orders",
                    "method": "GET",
                    "headers": {"Content-Type": "application/json"},
                    "data": {"user_id": "123", "filters": {"status": "completed"}}
                },
                "expected_service": "order_service"
            }
        ]
        
        for test_case in test_requests:
            runtime_params = {
                "api_gateway": {
                    "request": test_case["request"],
                    "routing_rules": [
                        {
                            "path_prefix": "/api/users",
                            "methods": ["GET", "PUT", "DELETE"],
                            "service": "user_service"
                        },
                        {
                            "path_prefix": "/api/orders",
                            "methods": ["GET", "POST"],
                            "service": "order_service"
                        }
                    ],
                    "auth_required": True,
                    "auth_token": "test_jwt_token"
                },
                "user_service": {
                    "operation": "get",
                    "user_id": "123"
                },
                "order_service": {
                    "operation": "list",
                    "user_id": "123",
                    "filters": {"status": "completed"}
                }
            }
            
            results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
            
            # Verify routing
            assert results["api_gateway"]["target_service"] == test_case["expected_service"]
            assert results["api_gateway"]["headers"]["X-Auth-Token"] == "test_jwt_token"
    
    def test_distributed_transaction_parameters(self):
        """Test distributed transaction with runtime parameters."""
        workflow = WorkflowBuilder()
        
        # Transaction coordinator
        workflow.add_node("DistributedTransactionManagerNode", "tx_manager", {
            "transaction_type": "saga",
            "timeout": "${transaction_timeout}"
        })
        
        # Service 1: Update inventory
        workflow.add_node("PythonCodeNode", "inventory_service", {
            "code": """
import random

operation = parameters.get('operation', 'reserve')
items = parameters.get('items', [])
transaction_id = parameters.get('transaction_id')

if operation == 'reserve':
    # Simulate inventory check
    success = random.random() > 0.1  # 90% success rate
    
    if success:
        result = {
            'status': 'reserved',
            'transaction_id': transaction_id,
            'reservation_ids': [f"res_{item['sku']}_{transaction_id}" for item in items]
        }
    else:
        result = {
            'status': 'failed',
            'error': 'Insufficient inventory',
            'transaction_id': transaction_id
        }
elif operation == 'compensate':
    # Rollback reservation
    result = {
        'status': 'compensated',
        'transaction_id': transaction_id
    }
else:
    result = {'error': 'Unknown operation'}
"""
        })
        
        # Service 2: Process payment
        workflow.add_node("PythonCodeNode", "payment_service", {
            "code": """
import random

operation = parameters.get('operation', 'charge')
amount = parameters.get('amount', 0)
payment_method = parameters.get('payment_method', {})
transaction_id = parameters.get('transaction_id')

if operation == 'charge':
    # Simulate payment processing
    success = random.random() > 0.05  # 95% success rate
    
    if success:
        result = {
            'status': 'charged',
            'transaction_id': transaction_id,
            'payment_id': f"pay_{transaction_id}",
            'amount_charged': amount
        }
    else:
        result = {
            'status': 'failed',
            'error': 'Payment declined',
            'transaction_id': transaction_id
        }
elif operation == 'compensate':
    # Refund payment
    result = {
        'status': 'refunded',
        'transaction_id': transaction_id,
        'refund_id': f"ref_{transaction_id}"
    }
else:
    result = {'error': 'Unknown operation'}
"""
        })
        
        # Service 3: Create order
        workflow.add_node("AsyncSQLDatabaseNode", "order_service", {
            "query": """
                INSERT INTO distributed_orders (
                    transaction_id, user_id, total_amount, status, created_at
                ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                RETURNING id
            """,
            "parameters": ["${transaction_id}", "${user_id}", "${total_amount}", "${status}"]
        })
        
        # Connect transaction flow
        workflow.add_connection("tx_manager", "transaction_id", "inventory_service", "transaction_id")
        workflow.add_connection("inventory_service", "*", "payment_service", "*")
        workflow.add_connection("payment_service", "*", "order_service", "*")
        
        runtime = LocalRuntime()
        db_params = get_postgres_connection_params()
        
        # Create orders table
        setup_workflow = WorkflowBuilder()
        setup_workflow.add_node("AsyncSQLDatabaseNode", "create_table", {
            **db_params,
            "query": """
                CREATE TABLE IF NOT EXISTS distributed_orders (
                    id SERIAL PRIMARY KEY,
                    transaction_id VARCHAR(255) UNIQUE,
                    user_id VARCHAR(255),
                    total_amount DECIMAL(10,2),
                    status VARCHAR(50),
                    created_at TIMESTAMP
                )
            """
        })
        runtime.execute(setup_workflow.build())
        
        # Runtime parameters for order processing
        runtime_params = {
            "tx_manager": {
                "transaction_timeout": 30  # 30 seconds
            },
            "inventory_service": {
                "operation": "reserve",
                "items": [
                    {"sku": "PROD-001", "quantity": 2},
                    {"sku": "PROD-002", "quantity": 1}
                ]
            },
            "payment_service": {
                "operation": "charge",
                "amount": 299.99,
                "payment_method": {
                    "type": "credit_card",
                    "last_four": "1234"
                }
            },
            "order_service": {
                **db_params,
                "user_id": "user_456",
                "total_amount": 299.99,
                "status": "completed"
            }
        }
        
        # Execute distributed transaction
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
                
                # Check if all services succeeded
                if (results.get("inventory_service", {}).get("status") == "reserved" and
                    results.get("payment_service", {}).get("status") == "charged"):
                    success = True
                    break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)  # Brief pause before retry
        
        if success:
            # Verify order was created
            verify_workflow = WorkflowBuilder()
            verify_workflow.add_node("AsyncSQLDatabaseNode", "verify", {
                **db_params,
                "query": "SELECT * FROM distributed_orders WHERE user_id = $1",
                "parameters": ["user_456"]
            })
            
            verify_results, _ = runtime.execute(verify_workflow.build())
            assert len(verify_results["verify"]["rows"]) > 0
        
        # Cleanup
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node("AsyncSQLDatabaseNode", "cleanup", {
            **db_params,
            "query": "DROP TABLE IF EXISTS distributed_orders"
        })
        runtime.execute(cleanup_workflow.build())


class TestSecurityScenarios:
    """Test parameter injection security in production scenarios."""
    
    def test_multi_tenant_parameter_isolation(self):
        """Test parameter isolation in multi-tenant environment."""
        workflow = WorkflowBuilder()
        
        # Tenant context validator
        workflow.add_node("PythonCodeNode", "tenant_validator", {
            "code": """
# Validate tenant context
tenant_id = parameters.get('tenant_id')
user_token = parameters.get('user_token')
requested_resource = parameters.get('requested_resource')

# Simulate token validation
token_parts = user_token.split('.')
if len(token_parts) == 3:
    # Extract tenant from token (simplified)
    token_tenant = token_parts[1]
    
    if token_tenant != tenant_id:
        result = {
            'authorized': False,
            'error': 'Tenant mismatch',
            'audit_log': {
                'event': 'unauthorized_access_attempt',
                'tenant_id': tenant_id,
                'token_tenant': token_tenant,
                'resource': requested_resource
            }
        }
    else:
        result = {
            'authorized': True,
            'tenant_id': tenant_id,
            'scoped_parameters': {
                'database_schema': f'tenant_{tenant_id}',
                'cache_prefix': f'cache:{tenant_id}',
                'file_path_prefix': f'/data/tenants/{tenant_id}'
            }
        }
else:
    result = {
        'authorized': False,
        'error': 'Invalid token format'
    }
"""
        })
        
        # Data access with tenant scoping
        workflow.add_node("SwitchNode", "auth_gate", {})
        
        workflow.add_node("AsyncSQLDatabaseNode", "tenant_data_access", {
            "query": "SELECT * FROM ${schema}.user_data WHERE user_id = $1",
            "parameters": ["${user_id}"]
        })
        
        workflow.add_node("PythonCodeNode", "access_denied", {
            "code": "result = {'error': 'Access denied', 'details': parameters.get('error')}"
        })
        
        # Connect with authorization check
        workflow.add_connection("tenant_validator", "authorized", "auth_gate", "condition")
        workflow.add_connection("tenant_validator", "scoped_parameters", "tenant_data_access", "*")
        workflow.add_connection("auth_gate", "true", "tenant_data_access", "*")
        workflow.add_connection("auth_gate", "false", "access_denied", "*")
        workflow.add_connection("tenant_validator", "error", "access_denied", "error")
        
        runtime = LocalRuntime()
        db_params = get_postgres_connection_params()
        
        # Test different tenant access scenarios
        test_cases = [
            {
                "tenant_id": "tenant_001",
                "user_token": "header.tenant_001.signature",
                "should_succeed": True
            },
            {
                "tenant_id": "tenant_001",
                "user_token": "header.tenant_002.signature",
                "should_succeed": False  # Wrong tenant
            },
            {
                "tenant_id": "tenant_003",
                "user_token": "invalid_token",
                "should_succeed": False  # Invalid token
            }
        ]
        
        for test_case in test_cases:
            runtime_params = {
                "tenant_validator": {
                    "tenant_id": test_case["tenant_id"],
                    "user_token": test_case["user_token"],
                    "requested_resource": "user_data"
                },
                "tenant_data_access": {
                    **db_params,
                    "user_id": "user_123"
                }
            }
            
            results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
            
            if test_case["should_succeed"]:
                # Verify tenant scoping was applied
                assert results["tenant_validator"]["authorized"] is True
                scoped_params = results["tenant_validator"]["scoped_parameters"]
                assert scoped_params["database_schema"] == f"tenant_{test_case['tenant_id']}"
                assert scoped_params["cache_prefix"] == f"cache:{test_case['tenant_id']}"
            else:
                # Verify access was denied
                assert results["tenant_validator"]["authorized"] is False
                assert "error" in results["access_denied"]
    
    def test_secure_parameter_encryption(self):
        """Test parameter encryption for sensitive data."""
        workflow = WorkflowBuilder()
        
        # Parameter encryption node
        workflow.add_node("PythonCodeNode", "parameter_encryptor", {
            "code": """
import base64
import json
from cryptography.fernet import Fernet

# Get encryption key (in production, from secure key management)
encryption_key = parameters.get('encryption_key')
if not encryption_key:
    # Generate key for demo (in production, retrieve from KMS)
    encryption_key = Fernet.generate_key()

fernet = Fernet(encryption_key)

# Identify sensitive parameters
sensitive_params = parameters.get('sensitive_params', {})
sensitive_fields = parameters.get('sensitive_fields', [
    'password', 'api_key', 'secret', 'token', 'ssn', 'credit_card'
])

# Encrypt sensitive data
encrypted_params = {}
encryption_map = {}

for key, value in sensitive_params.items():
    if any(field in key.lower() for field in sensitive_fields):
        # Encrypt the value
        encrypted_value = fernet.encrypt(json.dumps(value).encode()).decode()
        encrypted_params[key] = encrypted_value
        encryption_map[key] = 'encrypted'
    else:
        # Keep non-sensitive data as-is
        encrypted_params[key] = value
        encryption_map[key] = 'plain'

result = {
    'encrypted_params': encrypted_params,
    'encryption_map': encryption_map,
    'encryption_key': encryption_key.decode() if isinstance(encryption_key, bytes) else encryption_key
}
"""
        })
        
        # Process with encrypted parameters
        workflow.add_node("PythonCodeNode", "secure_processor", {
            "code": """
import json
from cryptography.fernet import Fernet

# Get encrypted parameters
encrypted_params = parameters.get('encrypted_params', {})
encryption_map = parameters.get('encryption_map', {})
encryption_key = parameters.get('encryption_key')

fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)

# Decrypt parameters for processing
decrypted_params = {}
for key, value in encrypted_params.items():
    if encryption_map.get(key) == 'encrypted':
        # Decrypt the value
        decrypted_value = json.loads(fernet.decrypt(value.encode()).decode())
        decrypted_params[key] = decrypted_value
    else:
        decrypted_params[key] = value

# Simulate secure processing
if decrypted_params.get('api_key') == 'valid_api_key_12345':
    result = {
        'status': 'authenticated',
        'user_id': decrypted_params.get('user_id'),
        'permissions': ['read', 'write']
    }
else:
    result = {
        'status': 'unauthorized',
        'error': 'Invalid API key'
    }

# Never log sensitive data
result['audit'] = {
    'parameters_received': len(encrypted_params),
    'encrypted_fields': sum(1 for v in encryption_map.values() if v == 'encrypted')
}
"""
        })
        
        # Connect encryption flow
        workflow.add_connection("parameter_encryptor", "*", "secure_processor", "*")
        
        runtime = LocalRuntime()
        
        # Test with sensitive data
        runtime_params = {
            "parameter_encryptor": {
                "sensitive_params": {
                    "user_id": "user_789",
                    "api_key": "valid_api_key_12345",
                    "email": "user@example.com",
                    "credit_card_token": "tok_visa_4242",
                    "preferences": {"theme": "dark"}
                }
            }
        }
        
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        
        # Verify encryption happened
        encrypted_params = results["parameter_encryptor"]["encrypted_params"]
        encryption_map = results["parameter_encryptor"]["encryption_map"]
        
        # Sensitive fields should be encrypted
        assert encryption_map["api_key"] == "encrypted"
        assert encryption_map["credit_card_token"] == "encrypted"
        assert encrypted_params["api_key"] != "valid_api_key_12345"  # Should be encrypted
        
        # Non-sensitive fields should be plain
        assert encryption_map["email"] == "plain"
        assert encryption_map["preferences"] == "plain"
        
        # Verify processing succeeded with decrypted params
        assert results["secure_processor"]["status"] == "authenticated"
        assert results["secure_processor"]["user_id"] == "user_789"


class TestPerformanceOptimization:
    """Test parameter injection performance optimization scenarios."""
    
    def test_parameter_caching_production_load(self):
        """Test parameter caching under production load."""
        harness = ParameterTestHarness()
        
        # Create workflow with repeated patterns
        workflow = WorkflowBuilder()
        
        # Simulate production scenario with many similar nodes
        service_count = 50
        instances_per_service = 10
        
        for service in range(service_count):
            for instance in range(instances_per_service):
                node_id = f"service_{service}_instance_{instance}"
                
                # All instances of same service use similar parameters
                workflow.add_node("PythonCodeNode", node_id, {
                    "code": f"""
# Service {service} logic
config = parameters.get('service_config', {{}})
request = parameters.get('request_data', {{}})
cache_key = f"service_{service}:{{request.get('id', 'default')}}"

# Simulate service processing
result = {{
    'service': {service},
    'instance': {instance},
    'processed': True,
    'cache_key': cache_key,
    'response_time': 0.001  # Simulated fast response
}}
"""
                })
        
        runtime = LocalRuntime()
        
        # Generate runtime parameters with patterns
        runtime_params = {}
        
        # Common service configurations (should benefit from caching)
        service_configs = {
            service: {
                "timeout": 30,
                "retry_count": 3,
                "endpoint": f"http://service-{service}.internal",
                "auth_token": f"token_{service}",
                "features": ["logging", "monitoring", "caching"]
            }
            for service in range(service_count)
        }
        
        # Apply same config to all instances of a service
        for service in range(service_count):
            for instance in range(instances_per_service):
                node_id = f"service_{service}_instance_{instance}"
                runtime_params[node_id] = {
                    "service_config": service_configs[service],
                    "request_data": {
                        "id": f"req_{service}_{instance}",
                        "timestamp": time.time()
                    }
                }
        
        # Measure performance
        start_time = time.time()
        results, _ = runtime.execute(workflow.build(), parameters=runtime_params)
        execution_time = (time.time() - start_time) * 1000  # ms
        
        total_nodes = service_count * instances_per_service
        time_per_node = execution_time / total_nodes
        
        # Performance assertions
        assert time_per_node < 5  # Less than 5ms per node
        print(f"Production load test: {time_per_node:.2f}ms per node "
              f"({total_nodes} nodes in {execution_time:.0f}ms)")
        
        # Verify all nodes executed
        assert len(results) == total_nodes
        
        # Verify parameter patterns were preserved
        for service in range(min(5, service_count)):  # Check first 5 services
            for instance in range(min(2, instances_per_service)):  # Check first 2 instances
                node_id = f"service_{service}_instance_{instance}"
                assert results[node_id]["service"] == service
                assert results[node_id]["instance"] == instance
                assert results[node_id]["processed"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])