# Integration Guide

Connect Nexus's workflow-native platform with external systems, APIs, databases, and enterprise infrastructure through comprehensive integration patterns.

## Overview

Nexus's multi-channel architecture makes it naturally suited for integration scenarios. This guide covers REST API integration, database connectivity, message queue integration, webhook systems, and enterprise application patterns.

## REST API Integration

### Advanced HTTP Client with Retry Logic

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import json
import hashlib
from urllib.parse import urljoin

app = Nexus()

class EnterpriseHTTPClient:
    """Enterprise-grade HTTP client with advanced features"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.base_urls = {}
        self.auth_configs = {}
        self.retry_configs = {}
        self.circuit_breakers = {}
        self.request_log = []
        self.default_config = {
            "timeout": 30,
            "max_retries": 3,
            "retry_delay": 1,
            "exponential_backoff": True,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_timeout": 60
        }

    def configure_api_endpoint(self, api_name, config):
        """Configure API endpoint with authentication and retry logic"""

        endpoint_config = {
            "base_url": config.get("base_url"),
            "auth_type": config.get("auth_type", "none"),
            "auth_config": config.get("auth_config", {}),
            "headers": config.get("headers", {}),
            "timeout": config.get("timeout", self.default_config["timeout"]),
            "retry_config": {
                "max_retries": config.get("max_retries", self.default_config["max_retries"]),
                "retry_delay": config.get("retry_delay", self.default_config["retry_delay"]),
                "exponential_backoff": config.get("exponential_backoff", self.default_config["exponential_backoff"]),
                "retry_on_status": config.get("retry_on_status", [429, 500, 502, 503, 504])
            },
            "circuit_breaker": {
                "enabled": config.get("circuit_breaker_enabled", True),
                "failure_threshold": config.get("circuit_breaker_threshold", self.default_config["circuit_breaker_threshold"]),
                "timeout": config.get("circuit_breaker_timeout", self.default_config["circuit_breaker_timeout"]),
                "half_open_requests": config.get("circuit_breaker_half_open", 2)
            }
        }

        self.base_urls[api_name] = endpoint_config["base_url"]
        self.auth_configs[api_name] = {
            "type": endpoint_config["auth_type"],
            "config": endpoint_config["auth_config"]
        }
        self.retry_configs[api_name] = endpoint_config["retry_config"]

        # Initialize circuit breaker
        self.circuit_breakers[api_name] = {
            "state": "closed",  # closed, open, half_open
            "failure_count": 0,
            "last_failure_time": None,
            "last_success_time": None,
            "config": endpoint_config["circuit_breaker"]
        }

        return {
            "api_configured": api_name,
            "base_url": endpoint_config["base_url"],
            "auth_type": endpoint_config["auth_type"],
            "retry_enabled": True,
            "circuit_breaker_enabled": endpoint_config["circuit_breaker"]["enabled"]
        }

    def create_api_workflow(self, workflow_name, api_name, endpoint, method="GET", transform_func=None):
        """Create workflow for API integration"""

        workflow = WorkflowBuilder()

        # Add HTTP request node
        workflow.add_node("HTTPRequestNode", "api_request", {
            "url": f"{self.base_urls.get(api_name, '')}{endpoint}",
            "method": method,
            "headers": self._get_auth_headers(api_name),
            "timeout": self.retry_configs.get(api_name, {}).get("timeout", 30)
        })

        # Add transformation node if specified
        if transform_func:
            workflow.add_node("PythonCodeNode", "transform_response", {
                "code": f"""
def transform_api_response(data):
    response = data.get('api_request', {{}})
    {transform_func}
    return transformed_data
""",
                "function_name": "transform_api_response"
            })

            # Connect nodes
            workflow.add_connection("api_request", "transform_response", "output", "input")

        # Add error handling node
        workflow.add_node("PythonCodeNode", "error_handler", {
            "code": """
def handle_api_error(data):
    error = data.get('error', {})

    # Log error for monitoring
    error_details = {
        'timestamp': __import__('time').time(),
        'error_type': error.get('type', 'unknown'),
        'error_message': error.get('message', 'Unknown error'),
        'api_endpoint': data.get('api_endpoint', 'unknown'),
        'retry_count': data.get('retry_count', 0)
    }

    # Determine if retry is needed
    if error_details['retry_count'] < 3:
        return {
            'should_retry': True,
            'retry_delay': 2 ** error_details['retry_count'],  # Exponential backoff
            'error_details': error_details
        }

    return {
        'should_retry': False,
        'final_error': error_details
    }
""",
            "function_name": "handle_api_error"
        })

        self.app.register(workflow_name, workflow)

        return {
            "workflow_created": workflow_name,
            "api_name": api_name,
            "endpoint": endpoint,
            "method": method,
            "transform_enabled": transform_func is not None
        }

    def execute_with_retry(self, api_name, endpoint, method="GET", data=None, headers=None):
        """Execute API request with retry logic and circuit breaker"""

        # Check circuit breaker
        if not self._check_circuit_breaker(api_name):
            return {
                "success": False,
                "error": "circuit_breaker_open",
                "message": f"Circuit breaker is open for {api_name}"
            }

        retry_config = self.retry_configs.get(api_name, self.default_config)
        max_retries = retry_config["max_retries"]
        retry_delay = retry_config["retry_delay"]

        for attempt in range(max_retries + 1):
            try:
                # Simulate API request
                request_start = time.time()

                # Build full URL
                base_url = self.base_urls.get(api_name, "")
                full_url = urljoin(base_url, endpoint)

                # Prepare headers
                request_headers = self._get_auth_headers(api_name)
                if headers:
                    request_headers.update(headers)

                # Log request
                request_id = self._log_request(api_name, full_url, method, attempt)

                # Simulate successful response
                response = {
                    "status_code": 200,
                    "data": {"message": "Success", "request_id": request_id},
                    "headers": {"content-type": "application/json"},
                    "elapsed_time": time.time() - request_start
                }

                # Record success
                self._record_circuit_breaker_success(api_name)

                return {
                    "success": True,
                    "response": response,
                    "attempts": attempt + 1,
                    "request_id": request_id
                }

            except Exception as e:
                # Record failure
                self._record_circuit_breaker_failure(api_name)

                if attempt < max_retries:
                    # Calculate retry delay with exponential backoff
                    if retry_config["exponential_backoff"]:
                        current_delay = retry_delay * (2 ** attempt)
                    else:
                        current_delay = retry_delay

                    time.sleep(current_delay)
                    continue

                # Final failure
                return {
                    "success": False,
                    "error": str(e),
                    "attempts": attempt + 1,
                    "circuit_breaker_state": self.circuit_breakers[api_name]["state"]
                }

    def _get_auth_headers(self, api_name):
        """Get authentication headers for API"""

        auth_config = self.auth_configs.get(api_name, {})
        headers = {}

        if auth_config.get("type") == "bearer":
            token = auth_config.get("config", {}).get("token", "")
            headers["Authorization"] = f"Bearer {token}"

        elif auth_config.get("type") == "api_key":
            api_key = auth_config.get("config", {}).get("api_key", "")
            key_header = auth_config.get("config", {}).get("header_name", "X-API-Key")
            headers[key_header] = api_key

        elif auth_config.get("type") == "basic":
            username = auth_config.get("config", {}).get("username", "")
            password = auth_config.get("config", {}).get("password", "")
            import base64
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"

        return headers

    def _check_circuit_breaker(self, api_name):
        """Check if circuit breaker allows request"""

        if api_name not in self.circuit_breakers:
            return True

        breaker = self.circuit_breakers[api_name]
        current_time = time.time()

        if breaker["state"] == "closed":
            return True

        elif breaker["state"] == "open":
            # Check if timeout has passed
            if current_time - breaker["last_failure_time"] > breaker["config"]["timeout"]:
                breaker["state"] = "half_open"
                breaker["failure_count"] = 0
                return True
            return False

        elif breaker["state"] == "half_open":
            # Allow limited requests
            return True

        return False

    def _record_circuit_breaker_success(self, api_name):
        """Record successful request for circuit breaker"""

        if api_name not in self.circuit_breakers:
            return

        breaker = self.circuit_breakers[api_name]
        breaker["last_success_time"] = time.time()

        if breaker["state"] == "half_open":
            breaker["state"] = "closed"
            breaker["failure_count"] = 0

    def _record_circuit_breaker_failure(self, api_name):
        """Record failed request for circuit breaker"""

        if api_name not in self.circuit_breakers:
            return

        breaker = self.circuit_breakers[api_name]
        breaker["failure_count"] += 1
        breaker["last_failure_time"] = time.time()

        if breaker["failure_count"] >= breaker["config"]["failure_threshold"]:
            breaker["state"] = "open"

    def _log_request(self, api_name, url, method, attempt):
        """Log API request for monitoring"""

        request_id = hashlib.sha256(f"{api_name}{url}{time.time()}".encode()).hexdigest()[:16]

        log_entry = {
            "request_id": request_id,
            "timestamp": time.time(),
            "api_name": api_name,
            "url": url,
            "method": method,
            "attempt": attempt,
            "circuit_breaker_state": self.circuit_breakers.get(api_name, {}).get("state", "unknown")
        }

        self.request_log.append(log_entry)

        # Keep only last 1000 entries
        if len(self.request_log) > 1000:
            self.request_log = self.request_log[-1000:]

        return request_id

    def get_integration_health(self):
        """Get health status of all API integrations"""

        health_status = {}

        for api_name, breaker in self.circuit_breakers.items():
            health_status[api_name] = {
                "state": breaker["state"],
                "failure_count": breaker["failure_count"],
                "last_success": breaker.get("last_success_time"),
                "last_failure": breaker.get("last_failure_time"),
                "health": "healthy" if breaker["state"] == "closed" else "degraded"
            }

        # Calculate recent request statistics
        recent_requests = [r for r in self.request_log if time.time() - r["timestamp"] < 300]  # Last 5 minutes

        request_stats = {
            "total_requests": len(recent_requests),
            "apis": list(set(r["api_name"] for r in recent_requests)),
            "average_attempts": sum(r["attempt"] for r in recent_requests) / len(recent_requests) if recent_requests else 0
        }

        return {
            "api_health": health_status,
            "request_stats": request_stats,
            "overall_health": "healthy" if all(h["health"] == "healthy" for h in health_status.values()) else "degraded"
        }

# Usage example
http_client = EnterpriseHTTPClient(app)

# Configure external API
api_config = http_client.configure_api_endpoint("payment_api", {
    "base_url": "https://api.payment-provider.com/v1/",
    "auth_type": "bearer",
    "auth_config": {"token": "your_api_token_here"},
    "max_retries": 5,
    "circuit_breaker_enabled": True,
    "circuit_breaker_threshold": 3
})

# Create API integration workflow
workflow_config = http_client.create_api_workflow(
    "payment_processor",
    "payment_api",
    "/payments",
    "POST",
    transform_func="""
    # Transform response to internal format
    transformed_data = {
        'payment_id': response.get('data', {}).get('id'),
        'status': response.get('data', {}).get('status'),
        'amount': response.get('data', {}).get('amount'),
        'processed_at': __import__('time').time()
    }
    """
)

print(f"API Configuration: {api_config}")
print(f"Workflow Configuration: {workflow_config}")

# Execute API request with retry
result = http_client.execute_with_retry("payment_api", "/payments/123", "GET")
print(f"API Request Result: {result}")

# Check integration health
health = http_client.get_integration_health()
print(f"Integration Health: {health}")
```

## Database Integration

### Multi-Database Connection Manager

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import hashlib
from enum import Enum

app = Nexus()

class DatabaseType(Enum):
    """Supported database types"""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"
    ELASTICSEARCH = "elasticsearch"
    SNOWFLAKE = "snowflake"

class EnterpriseDatabaseManager:
    """Enterprise database connection and query management"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.connections = {}
        self.connection_pools = {}
        self.query_cache = {}
        self.query_log = []
        self.data_models = {}
        self.migration_history = {}

    def configure_database(self, db_name, db_type, connection_config):
        """Configure database connection with pooling"""

        if isinstance(db_type, DatabaseType):
            db_type = db_type.value

        db_config = {
            "name": db_name,
            "type": db_type,
            "connection": {
                "host": connection_config.get("host", "localhost"),
                "port": connection_config.get("port", self._get_default_port(db_type)),
                "database": connection_config.get("database"),
                "username": connection_config.get("username"),
                "password": connection_config.get("password"),
                "ssl_enabled": connection_config.get("ssl_enabled", True),
                "connection_timeout": connection_config.get("connection_timeout", 30)
            },
            "pool": {
                "min_connections": connection_config.get("min_connections", 2),
                "max_connections": connection_config.get("max_connections", 10),
                "idle_timeout": connection_config.get("idle_timeout", 300),
                "max_lifetime": connection_config.get("max_lifetime", 3600)
            },
            "query_config": {
                "query_timeout": connection_config.get("query_timeout", 60),
                "enable_cache": connection_config.get("enable_cache", True),
                "cache_ttl": connection_config.get("cache_ttl", 300),
                "slow_query_threshold": connection_config.get("slow_query_threshold", 5)
            }
        }

        # Initialize connection pool (simulation)
        self.connection_pools[db_name] = {
            "type": db_type,
            "config": db_config,
            "active_connections": 0,
            "available_connections": db_config["pool"]["min_connections"],
            "total_connections": db_config["pool"]["min_connections"],
            "created_at": time.time()
        }

        self.connections[db_name] = db_config

        return {
            "database_configured": db_name,
            "type": db_type,
            "host": db_config["connection"]["host"],
            "pool_size": f"{db_config['pool']['min_connections']}-{db_config['pool']['max_connections']}",
            "ssl_enabled": db_config["connection"]["ssl_enabled"]
        }

    def create_database_workflow(self, workflow_name, db_name, operations):
        """Create workflow for database operations"""

        workflow = WorkflowBuilder()

        # Add database connection node
        workflow.add_node("PythonCodeNode", "db_connection", {
            "code": f"""
def establish_db_connection(data):
    # Simulate database connection
    connection_info = {{
        'database': '{db_name}',
        'connected': True,
        'connection_id': __import__('secrets').token_hex(8),
        'timestamp': __import__('time').time()
    }}
    return connection_info
""",
            "function_name": "establish_db_connection"
        })

        # Add query execution nodes for each operation
        for i, operation in enumerate(operations):
            node_name = f"query_{i+1}"

            workflow.add_node("PythonCodeNode", node_name, {
                "code": f"""
def execute_query_{i+1}(data):
    connection = data.get('db_connection', {{}})

    # Simulate query execution
    query_result = {{
        'operation': '{operation['type']}',
        'query': '''{operation.get('query', '')}''',
        'affected_rows': __import__('random').randint(0, 100),
        'execution_time': __import__('random').uniform(0.1, 2.0),
        'success': True
    }}

    return query_result
""",
                "function_name": f"execute_query_{i+1}"
            })

            # Connect to previous node
            if i == 0:
                workflow.add_connection("db_connection", node_name, "output", "input")
            else:
                workflow.add_connection("source", "result", "target", "input")  # Fixed f-string pattern

        # Add transaction management node
        workflow.add_node("PythonCodeNode", "transaction_manager", {
            "code": """
def manage_transaction(data):
    # Collect all query results
    query_results = []
    for key, value in data.items():
        if key.startswith('query_') and isinstance(value, dict):
            query_results.append(value)

    # Check if all queries succeeded
    all_success = all(result.get('success', False) for result in query_results)

    transaction_result = {
        'transaction_id': __import__('secrets').token_hex(8),
        'status': 'committed' if all_success else 'rolled_back',
        'total_queries': len(query_results),
        'success': all_success,
        'timestamp': __import__('time').time()
    }

    return transaction_result
""",
            "function_name": "manage_transaction"
        })

        # Add data validation node
        workflow.add_node("PythonCodeNode", "data_validator", {
            "code": """
def validate_results(data):
    transaction = data.get('transaction_manager', {})

    validation_result = {
        'data_integrity': True,
        'consistency_check': 'passed',
        'validation_timestamp': __import__('time').time(),
        'transaction_valid': transaction.get('success', False)
    }

    return validation_result
""",
            "function_name": "validate_results"
        })

        self.app.register(workflow_name, workflow)

        return {
            "workflow_created": workflow_name,
            "database": db_name,
            "operations_count": len(operations),
            "transaction_enabled": True,
            "validation_enabled": True
        }

    def execute_query(self, db_name, query, params=None, use_cache=True):
        """Execute database query with caching and monitoring"""

        if db_name not in self.connections:
            return {
                "success": False,
                "error": f"Database '{db_name}' not configured"
            }

        # Generate cache key
        cache_key = None
        if use_cache and self.connections[db_name]["query_config"]["enable_cache"]:
            cache_key = self._generate_cache_key(db_name, query, params)

            # Check cache
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                return {
                    "success": True,
                    "data": cached_result["data"],
                    "cached": True,
                    "cache_hit": True,
                    "execution_time": 0
                }

        # Execute query (simulation)
        start_time = time.time()

        try:
            # Simulate query execution
            result_data = {
                "rows": [{"id": i, "data": f"row_{i}"} for i in range(5)],
                "row_count": 5,
                "columns": ["id", "data"]
            }

            execution_time = time.time() - start_time

            # Log query
            self._log_query(db_name, query, execution_time, True)

            # Cache result if enabled
            if cache_key and use_cache:
                self._cache_result(cache_key, result_data,
                                 self.connections[db_name]["query_config"]["cache_ttl"])

            # Check for slow query
            if execution_time > self.connections[db_name]["query_config"]["slow_query_threshold"]:
                self._log_slow_query(db_name, query, execution_time)

            return {
                "success": True,
                "data": result_data,
                "execution_time": execution_time,
                "cached": False,
                "database": db_name
            }

        except Exception as e:
            execution_time = time.time() - start_time
            self._log_query(db_name, query, execution_time, False, str(e))

            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
                "database": db_name
            }

    def create_data_model(self, model_name, schema, db_name):
        """Create data model for ORM-like operations"""

        model = {
            "name": model_name,
            "database": db_name,
            "schema": schema,
            "created_at": time.time(),
            "version": 1,
            "indexes": [],
            "relationships": {}
        }

        # Validate schema
        required_fields = ["table_name", "columns", "primary_key"]
        if not all(field in schema for field in required_fields):
            return {
                "success": False,
                "error": "Invalid schema: missing required fields"
            }

        self.data_models[model_name] = model

        # Generate migration
        migration = self._generate_migration(model_name, schema, "create")

        return {
            "model_created": model_name,
            "database": db_name,
            "table": schema["table_name"],
            "columns": len(schema["columns"]),
            "migration_id": migration["id"]
        }

    def _get_default_port(self, db_type):
        """Get default port for database type"""

        port_mapping = {
            "postgresql": 5432,
            "mysql": 3306,
            "mongodb": 27017,
            "redis": 6379,
            "elasticsearch": 9200,
            "snowflake": 443
        }

        return port_mapping.get(db_type, 5432)

    def _generate_cache_key(self, db_name, query, params):
        """Generate cache key for query"""

        cache_data = {
            "database": db_name,
            "query": query,
            "params": params or {}
        }

        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(cache_string.encode()).hexdigest()

    def _get_cached_result(self, cache_key):
        """Get cached query result"""

        if cache_key in self.query_cache:
            cached = self.query_cache[cache_key]

            # Check if cache is still valid
            if time.time() - cached["cached_at"] < cached["ttl"]:
                return cached
            else:
                # Remove expired cache
                del self.query_cache[cache_key]

        return None

    def _cache_result(self, cache_key, data, ttl):
        """Cache query result"""

        self.query_cache[cache_key] = {
            "data": data,
            "cached_at": time.time(),
            "ttl": ttl
        }

        # Limit cache size
        if len(self.query_cache) > 1000:
            # Remove oldest entries
            sorted_keys = sorted(self.query_cache.keys(),
                               key=lambda k: self.query_cache[k]["cached_at"])
            for key in sorted_keys[:100]:
                del self.query_cache[key]

    def _log_query(self, db_name, query, execution_time, success, error=None):
        """Log query execution"""

        log_entry = {
            "timestamp": time.time(),
            "database": db_name,
            "query": query[:100] + "..." if len(query) > 100 else query,
            "execution_time": execution_time,
            "success": success,
            "error": error
        }

        self.query_log.append(log_entry)

        # Keep only last 1000 entries
        if len(self.query_log) > 1000:
            self.query_log = self.query_log[-1000:]

    def _log_slow_query(self, db_name, query, execution_time):
        """Log slow query for optimization"""

        slow_query_entry = {
            "timestamp": time.time(),
            "database": db_name,
            "query": query,
            "execution_time": execution_time,
            "threshold": self.connections[db_name]["query_config"]["slow_query_threshold"]
        }

        # In production, this would be sent to monitoring system
        print(f"⚠️ Slow query detected: {execution_time:.2f}s - {query[:50]}...")

    def _generate_migration(self, model_name, schema, operation):
        """Generate database migration"""

        migration_id = f"migration_{int(time.time())}_{model_name}"

        migration = {
            "id": migration_id,
            "model": model_name,
            "operation": operation,
            "schema": schema,
            "created_at": time.time(),
            "applied": False,
            "sql": self._generate_sql(operation, schema)
        }

        if model_name not in self.migration_history:
            self.migration_history[model_name] = []

        self.migration_history[model_name].append(migration)

        return migration

    def _generate_sql(self, operation, schema):
        """Generate SQL for migration"""

        if operation == "create":
            columns_sql = []
            for column in schema["columns"]:
                column_def = f"{column['name']} {column['type']}"
                if column.get("not_null"):
                    column_def += " NOT NULL"
                if column.get("default"):
                    column_def += f" DEFAULT {column['default']}"
                columns_sql.append(column_def)

            sql = f"""
CREATE TABLE {schema['table_name']} (
    {', '.join(columns_sql)},
    PRIMARY KEY ({schema['primary_key']})
);
"""
            return sql.strip()

        return ""

    def get_database_health(self):
        """Get health status of all database connections"""

        health_status = {}

        for db_name, pool in self.connection_pools.items():
            health_status[db_name] = {
                "type": pool["type"],
                "active_connections": pool["active_connections"],
                "available_connections": pool["available_connections"],
                "total_connections": pool["total_connections"],
                "uptime": time.time() - pool["created_at"],
                "status": "healthy" if pool["available_connections"] > 0 else "degraded"
            }

        # Query statistics
        recent_queries = [q for q in self.query_log if time.time() - q["timestamp"] < 300]

        query_stats = {
            "total_queries": len(recent_queries),
            "success_rate": (len([q for q in recent_queries if q["success"]]) /
                           len(recent_queries) * 100) if recent_queries else 100,
            "avg_execution_time": (sum(q["execution_time"] for q in recent_queries) /
                                 len(recent_queries)) if recent_queries else 0,
            "cache_size": len(self.query_cache)
        }

        return {
            "database_health": health_status,
            "query_stats": query_stats,
            "total_models": len(self.data_models),
            "pending_migrations": sum(len([m for m in migrations if not m["applied"]])
                                    for migrations in self.migration_history.values())
        }

# Usage example
db_manager = EnterpriseDatabaseManager(app)

# Configure PostgreSQL database
postgres_config = db_manager.configure_database("analytics_db", DatabaseType.POSTGRESQL, {
    "host": "localhost",
    "port": 5432,
    "database": "analytics",
    "username": "postgres",
    "password": "secure_password",
    "min_connections": 5,
    "max_connections": 20,
    "enable_cache": True
})

# Configure MongoDB database
mongo_config = db_manager.configure_database("document_store", DatabaseType.MONGODB, {
    "host": "localhost",
    "port": 27017,
    "database": "documents",
    "username": "mongo_user",
    "password": "mongo_password"
})

print(f"PostgreSQL Configuration: {postgres_config}")
print(f"MongoDB Configuration: {mongo_config}")

# Create database workflow
workflow_config = db_manager.create_database_workflow(
    "data_pipeline",
    "analytics_db",
    [
        {"type": "select", "query": "SELECT * FROM users WHERE active = true"},
        {"type": "update", "query": "UPDATE user_stats SET last_access = NOW()"},
        {"type": "insert", "query": "INSERT INTO audit_log (action, timestamp) VALUES ('access', NOW())"}
    ]
)

print(f"Workflow Configuration: {workflow_config}")

# Execute query
query_result = db_manager.execute_query(
    "analytics_db",
    "SELECT * FROM users LIMIT 10",
    use_cache=True
)

print(f"Query Result: {query_result}")

# Create data model
model_result = db_manager.create_data_model("User", {
    "table_name": "users",
    "columns": [
        {"name": "id", "type": "SERIAL"},
        {"name": "username", "type": "VARCHAR(255)", "not_null": True},
        {"name": "email", "type": "VARCHAR(255)", "not_null": True},
        {"name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"}
    ],
    "primary_key": "id"
}, "analytics_db")

print(f"Model Creation: {model_result}")

# Check database health
health = db_manager.get_database_health()
print(f"Database Health: {health}")
```

## Message Queue Integration

### Enterprise Message Queue System

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import json
import hashlib
from enum import Enum
from collections import defaultdict

app = Nexus()

class MessageQueueType(Enum):
    """Supported message queue types"""
    RABBITMQ = "rabbitmq"
    KAFKA = "kafka"
    AWS_SQS = "aws_sqs"
    REDIS_PUBSUB = "redis_pubsub"
    AZURE_SERVICE_BUS = "azure_service_bus"

class EnterpriseMessageQueue:
    """Enterprise message queue integration and management"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.queue_configs = {}
        self.publishers = {}
        self.consumers = {}
        self.message_log = []
        self.dead_letter_queues = {}
        self.queue_metrics = defaultdict(lambda: {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_failed": 0,
            "last_activity": None
        })

    def configure_message_queue(self, queue_name, queue_type, config):
        """Configure message queue connection"""

        if isinstance(queue_type, MessageQueueType):
            queue_type = queue_type.value

        queue_config = {
            "name": queue_name,
            "type": queue_type,
            "connection": {
                "host": config.get("host", "localhost"),
                "port": config.get("port", self._get_default_port(queue_type)),
                "username": config.get("username"),
                "password": config.get("password"),
                "virtual_host": config.get("virtual_host", "/"),
                "ssl_enabled": config.get("ssl_enabled", True)
            },
            "queue_settings": {
                "durable": config.get("durable", True),
                "auto_delete": config.get("auto_delete", False),
                "exclusive": config.get("exclusive", False),
                "max_retries": config.get("max_retries", 3),
                "retry_delay": config.get("retry_delay", 5),
                "message_ttl": config.get("message_ttl", 3600),
                "max_queue_size": config.get("max_queue_size", 10000)
            },
            "consumer_settings": {
                "prefetch_count": config.get("prefetch_count", 10),
                "auto_ack": config.get("auto_ack", False),
                "consumer_timeout": config.get("consumer_timeout", 300)
            }
        }

        self.queue_configs[queue_name] = queue_config

        # Initialize dead letter queue
        self.dead_letter_queues[queue_name] = {
            "name": f"{queue_name}_dlq",
            "messages": [],
            "max_size": 1000
        }

        return {
            "queue_configured": queue_name,
            "type": queue_type,
            "host": queue_config["connection"]["host"],
            "durable": queue_config["queue_settings"]["durable"],
            "dlq_enabled": True
        }

    def create_publisher_workflow(self, workflow_name, queue_name, message_schema=None):
        """Create workflow for message publishing"""

        workflow = WorkflowBuilder()

        # Add message validation node
        workflow.add_node("PythonCodeNode", "validate_message", {
            "code": f"""
def validate_message(data):
    message = data.get('message', {{}})

    # Validate against schema if provided
    schema = {message_schema or {{}}}

    validation_result = {{
        'valid': True,
        'message': message,
        'validated_at': __import__('time').time()
    }}

    # Basic validation
    if not message:
        validation_result['valid'] = False
        validation_result['error'] = 'Empty message'

    return validation_result
""",
            "function_name": "validate_message"
        })

        # Add message enrichment node
        workflow.add_node("PythonCodeNode", "enrich_message", {
            "code": """
def enrich_message(data):
    validated = data.get('validate_message', {})

    if not validated.get('valid'):
        return validated

    message = validated['message']

    # Add metadata
    enriched_message = {
        'payload': message,
        'metadata': {
            'message_id': __import__('secrets').token_hex(16),
            'timestamp': __import__('time').time(),
            'version': '1.0',
            'source': 'nexus_workflow',
            'correlation_id': data.get('correlation_id', __import__('secrets').token_hex(8))
        }
    }

    return enriched_message
""",
            "function_name": "enrich_message"
        })

        # Add publisher node
        workflow.add_node("PythonCodeNode", "publish_message", {
            "code": f"""
def publish_to_queue(data):
    enriched = data.get('enrich_message', {{}})

    if not enriched or enriched.get('error'):
        return enriched

    # Simulate message publishing
    publish_result = {{
        'queue': '{queue_name}',
        'message_id': enriched['metadata']['message_id'],
        'published': True,
        'timestamp': __import__('time').time(),
        'partition': __import__('random').randint(0, 3),  # For Kafka-like systems
        'delivery_tag': __import__('secrets').token_hex(8)
    }}

    return publish_result
""",
            "function_name": "publish_to_queue"
        })

        # Connect nodes
        workflow.add_connection("validate_message", "enrich_message", "output", "input")
        workflow.add_connection("enrich_message", "publish_message", "output", "input")

        self.app.register(workflow_name, workflow)

        return {
            "workflow_created": workflow_name,
            "queue": queue_name,
            "validation_enabled": True,
            "enrichment_enabled": True
        }

    def create_consumer_workflow(self, workflow_name, queue_name, processor_func):
        """Create workflow for message consumption"""

        workflow = WorkflowBuilder()

        # Add consumer node
        workflow.add_node("PythonCodeNode", "consume_message", {
            "code": f"""
def consume_from_queue(data):
    # Simulate message consumption
    consumed_message = {{
        'queue': '{queue_name}',
        'message': {{
            'payload': {{'test': 'data'}},
            'metadata': {{
                'message_id': __import__('secrets').token_hex(16),
                'timestamp': __import__('time').time()
            }}
        }},
        'delivery_tag': __import__('secrets').token_hex(8),
        'redelivered': False
    }}

    return consumed_message
""",
            "function_name": "consume_from_queue"
        })

        # Add message processor node
        workflow.add_node("PythonCodeNode", "process_message", {
            "code": f"""
def process_consumed_message(data):
    consumed = data.get('consume_message', {{}})
    message = consumed.get('message', {{}})

    # Apply custom processing function
    {processor_func}

    process_result = {{
        'message_id': message.get('metadata', {{}}).get('message_id'),
        'processed': True,
        'result': processed_data,
        'processing_time': __import__('random').uniform(0.1, 1.0)
    }}

    return process_result
""",
            "function_name": "process_consumed_message"
        })

        # Add acknowledgment node
        workflow.add_node("PythonCodeNode", "acknowledge_message", {
            "code": """
def acknowledge_message(data):
    process_result = data.get('process_message', {})
    consumed = data.get('consume_message', {})

    ack_result = {
        'delivery_tag': consumed.get('delivery_tag'),
        'acknowledged': process_result.get('processed', False),
        'ack_time': __import__('time').time()
    }

    if not ack_result['acknowledged']:
        ack_result['requeue'] = True
        ack_result['retry_count'] = consumed.get('retry_count', 0) + 1

    return ack_result
""",
            "function_name": "acknowledge_message"
        })

        # Connect nodes
        workflow.add_connection("consume_message", "process_message", "output", "input")
        workflow.add_connection("process_message", "acknowledge_message", "output", "input")

        self.app.register(workflow_name, workflow)

        return {
            "workflow_created": workflow_name,
            "queue": queue_name,
            "processor_configured": True,
            "auto_acknowledge": False
        }

    def publish_message(self, queue_name, message, priority=0, headers=None):
        """Publish message to queue"""

        if queue_name not in self.queue_configs:
            return {
                "success": False,
                "error": f"Queue '{queue_name}' not configured"
            }

        # Create message envelope
        message_envelope = {
            "id": hashlib.sha256(f"{queue_name}{time.time()}".encode()).hexdigest()[:16],
            "payload": message,
            "headers": headers or {},
            "properties": {
                "priority": priority,
                "timestamp": time.time(),
                "expiration": time.time() + self.queue_configs[queue_name]["queue_settings"]["message_ttl"],
                "content_type": "application/json",
                "delivery_mode": 2  # Persistent
            }
        }

        # Log message
        self._log_message("publish", queue_name, message_envelope["id"], True)

        # Update metrics
        self.queue_metrics[queue_name]["messages_sent"] += 1
        self.queue_metrics[queue_name]["last_activity"] = time.time()

        return {
            "success": True,
            "message_id": message_envelope["id"],
            "queue": queue_name,
            "timestamp": message_envelope["properties"]["timestamp"]
        }

    def consume_messages(self, queue_name, batch_size=1, timeout=30):
        """Consume messages from queue"""

        if queue_name not in self.queue_configs:
            return {
                "success": False,
                "error": f"Queue '{queue_name}' not configured"
            }

        # Simulate message consumption
        messages = []
        for i in range(min(batch_size, 3)):  # Limit to 3 for simulation
            message = {
                "id": hashlib.sha256(f"{queue_name}{time.time()}{i}".encode()).hexdigest()[:16],
                "payload": {"data": f"message_{i}", "index": i},
                "delivery_tag": hashlib.sha256(f"tag_{i}_{time.time()}".encode()).hexdigest()[:8],
                "redelivered": False,
                "timestamp": time.time()
            }
            messages.append(message)

            # Log consumption
            self._log_message("consume", queue_name, message["id"], True)

        # Update metrics
        self.queue_metrics[queue_name]["messages_received"] += len(messages)
        self.queue_metrics[queue_name]["last_activity"] = time.time()

        return {
            "success": True,
            "messages": messages,
            "count": len(messages),
            "queue": queue_name
        }

    def handle_failed_message(self, queue_name, message_id, error_reason):
        """Handle failed message processing"""

        if queue_name not in self.dead_letter_queues:
            return {
                "success": False,
                "error": f"DLQ not configured for queue '{queue_name}'"
            }

        # Add to dead letter queue
        dlq = self.dead_letter_queues[queue_name]

        failed_message = {
            "original_message_id": message_id,
            "failed_at": time.time(),
            "error_reason": error_reason,
            "queue": queue_name,
            "retry_count": 0  # Track retry attempts
        }

        dlq["messages"].append(failed_message)

        # Maintain DLQ size limit
        if len(dlq["messages"]) > dlq["max_size"]:
            dlq["messages"] = dlq["messages"][-dlq["max_size"]:]

        # Update metrics
        self.queue_metrics[queue_name]["messages_failed"] += 1

        # Log failure
        self._log_message("failed", queue_name, message_id, False, error_reason)

        return {
            "success": True,
            "dlq_message_id": f"dlq_{message_id}",
            "dlq_size": len(dlq["messages"])
        }

    def _get_default_port(self, queue_type):
        """Get default port for queue type"""

        port_mapping = {
            "rabbitmq": 5672,
            "kafka": 9092,
            "redis_pubsub": 6379
        }

        return port_mapping.get(queue_type, 5672)

    def _log_message(self, operation, queue_name, message_id, success, error=None):
        """Log message operation"""

        log_entry = {
            "timestamp": time.time(),
            "operation": operation,
            "queue": queue_name,
            "message_id": message_id,
            "success": success,
            "error": error
        }

        self.message_log.append(log_entry)

        # Keep only last 1000 entries
        if len(self.message_log) > 1000:
            self.message_log = self.message_log[-1000:]

    def get_queue_health(self):
        """Get health status of all message queues"""

        health_status = {}

        for queue_name, config in self.queue_configs.items():
            metrics = self.queue_metrics[queue_name]
            dlq = self.dead_letter_queues.get(queue_name, {})

            # Calculate health metrics
            total_messages = metrics["messages_sent"] + metrics["messages_received"]
            failure_rate = (metrics["messages_failed"] / total_messages * 100) if total_messages > 0 else 0

            health_status[queue_name] = {
                "type": config["type"],
                "messages_sent": metrics["messages_sent"],
                "messages_received": metrics["messages_received"],
                "messages_failed": metrics["messages_failed"],
                "failure_rate": round(failure_rate, 2),
                "dlq_size": len(dlq.get("messages", [])),
                "last_activity": metrics["last_activity"],
                "status": "healthy" if failure_rate < 5 else "degraded"
            }

        # Overall statistics
        recent_logs = [log for log in self.message_log if time.time() - log["timestamp"] < 300]

        overall_stats = {
            "total_queues": len(self.queue_configs),
            "recent_operations": len(recent_logs),
            "recent_failures": len([log for log in recent_logs if not log["success"]]),
            "active_queues": len([q for q, m in self.queue_metrics.items()
                                if m["last_activity"] and time.time() - m["last_activity"] < 300])
        }

        return {
            "queue_health": health_status,
            "overall_stats": overall_stats,
            "system_status": "healthy" if all(h["status"] == "healthy" for h in health_status.values()) else "degraded"
        }

# Usage example
mq_manager = EnterpriseMessageQueue(app)

# Configure RabbitMQ
rabbitmq_config = mq_manager.configure_message_queue("events_queue", MessageQueueType.RABBITMQ, {
    "host": "localhost",
    "port": 5672,
    "username": "rabbitmq",
    "password": "rabbitmq_password",
    "virtual_host": "/nexus",
    "durable": True,
    "max_retries": 5
})

# Configure Kafka
kafka_config = mq_manager.configure_message_queue("analytics_stream", MessageQueueType.KAFKA, {
    "host": "localhost",
    "port": 9092,
    "username": "kafka_user",
    "password": "kafka_password",
    "prefetch_count": 20
})

print(f"RabbitMQ Configuration: {rabbitmq_config}")
print(f"Kafka Configuration: {kafka_config}")

# Create publisher workflow
publisher_workflow = mq_manager.create_publisher_workflow(
    "event_publisher",
    "events_queue",
    message_schema={"type": "object", "required": ["event_type", "timestamp"]}
)

# Create consumer workflow
consumer_workflow = mq_manager.create_consumer_workflow(
    "event_consumer",
    "events_queue",
    processor_func="""
    # Process event message
    processed_data = {
        'event_id': message.get('payload', {}).get('event_id'),
        'processed_at': __import__('time').time(),
        'status': 'processed'
    }
    """
)

print(f"Publisher Workflow: {publisher_workflow}")
print(f"Consumer Workflow: {consumer_workflow}")

# Publish message
publish_result = mq_manager.publish_message(
    "events_queue",
    {"event_type": "user_action", "action": "login", "user_id": "12345"},
    priority=1,
    headers={"source": "web_app"}
)

print(f"Publish Result: {publish_result}")

# Consume messages
consume_result = mq_manager.consume_messages("events_queue", batch_size=5)
print(f"Consume Result: {consume_result}")

# Check queue health
queue_health = mq_manager.get_queue_health()
print(f"Queue Health: {queue_health}")
```

## Webhook Integration

### Enterprise Webhook System

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import hashlib
import hmac
import json
from enum import Enum

app = Nexus()

class WebhookEvent(Enum):
    """Webhook event types"""
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    DATA_CREATED = "data.created"
    DATA_UPDATED = "data.updated"
    DATA_DELETED = "data.deleted"
    SYSTEM_ALERT = "system.alert"

class EnterpriseWebhookManager:
    """Enterprise webhook management system"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.webhook_endpoints = {}
        self.webhook_subscriptions = {}
        self.delivery_log = []
        self.retry_queue = []
        self.webhook_secrets = {}
        self.delivery_config = {
            "timeout": 30,
            "max_retries": 3,
            "retry_delay": 60,
            "exponential_backoff": True,
            "signature_algorithm": "sha256",
            "include_timestamp": True,
            "batch_size": 100
        }

    def register_webhook_endpoint(self, endpoint_name, config):
        """Register webhook endpoint"""

        endpoint_config = {
            "name": endpoint_name,
            "url": config.get("url"),
            "method": config.get("method", "POST"),
            "headers": config.get("headers", {}),
            "auth_type": config.get("auth_type", "signature"),
            "auth_config": config.get("auth_config", {}),
            "events": config.get("events", []),
            "active": config.get("active", True),
            "filters": config.get("filters", {}),
            "transformation": config.get("transformation"),
            "rate_limit": config.get("rate_limit", 100),  # per minute
            "created_at": time.time()
        }

        # Generate webhook secret
        webhook_secret = hashlib.sha256(f"{endpoint_name}{time.time()}".encode()).hexdigest()
        self.webhook_secrets[endpoint_name] = webhook_secret

        self.webhook_endpoints[endpoint_name] = endpoint_config

        # Initialize delivery tracking
        for event in endpoint_config["events"]:
            if event not in self.webhook_subscriptions:
                self.webhook_subscriptions[event] = []
            self.webhook_subscriptions[event].append(endpoint_name)

        return {
            "endpoint_registered": endpoint_name,
            "url": endpoint_config["url"],
            "events": endpoint_config["events"],
            "webhook_secret": webhook_secret,
            "active": endpoint_config["active"]
        }

    def create_webhook_workflow(self, workflow_name, trigger_event):
        """Create workflow triggered by webhook"""

        workflow = WorkflowBuilder()

        # Add webhook receiver node
        workflow.add_node("PythonCodeNode", "webhook_receiver", {
            "code": f"""
def receive_webhook(data):
    # Extract webhook payload
    webhook_data = {{
        'event_type': '{trigger_event}',
        'payload': data.get('payload', {{}}),
        'headers': data.get('headers', {{}}),
        'timestamp': __import__('time').time(),
        'webhook_id': __import__('secrets').token_hex(16)
    }}

    # Validate webhook signature if present
    signature = data.get('headers', {{}}).get('X-Webhook-Signature')
    if signature:
        webhook_data['signature_valid'] = True  # Simulate validation

    return webhook_data
""",
            "function_name": "receive_webhook"
        })

        # Add event processor node
        workflow.add_node("PythonCodeNode", "process_event", {
            "code": """
def process_webhook_event(data):
    webhook = data.get('webhook_receiver', {})

    # Process based on event type
    event_type = webhook.get('event_type')
    payload = webhook.get('payload', {})

    processing_result = {
        'event_id': webhook.get('webhook_id'),
        'event_type': event_type,
        'processed_at': __import__('time').time(),
        'status': 'processed'
    }

    # Event-specific processing
    if 'workflow' in event_type:
        processing_result['workflow_id'] = payload.get('workflow_id')
        processing_result['workflow_status'] = payload.get('status')
    elif 'data' in event_type:
        processing_result['data_id'] = payload.get('id')
        processing_result['operation'] = event_type.split('.')[-1]

    return processing_result
""",
            "function_name": "process_webhook_event"
        })

        # Add response node
        workflow.add_node("PythonCodeNode", "webhook_response", {
            "code": """
def generate_webhook_response(data):
    processing = data.get('process_event', {})

    response = {
        'status': 'success' if processing.get('status') == 'processed' else 'error',
        'event_id': processing.get('event_id'),
        'message': 'Webhook processed successfully',
        'timestamp': __import__('time').time()
    }

    return response
""",
            "function_name": "generate_webhook_response"
        })

        # Connect nodes
        workflow.add_connection("webhook_receiver", "process_event", "output", "input")
        workflow.add_connection("process_event", "webhook_response", "output", "input")

        self.app.register(workflow_name, workflow)

        return {
            "workflow_created": workflow_name,
            "trigger_event": trigger_event,
            "processing_enabled": True,
            "response_enabled": True
        }

    def trigger_webhook(self, event_type, payload, metadata=None):
        """Trigger webhook for event"""

        if isinstance(event_type, WebhookEvent):
            event_type = event_type.value

        # Get subscribed endpoints
        subscribed_endpoints = self.webhook_subscriptions.get(event_type, [])

        delivery_results = []

        for endpoint_name in subscribed_endpoints:
            endpoint = self.webhook_endpoints.get(endpoint_name)

            if not endpoint or not endpoint["active"]:
                continue

            # Apply filters
            if not self._apply_filters(payload, endpoint["filters"]):
                continue

            # Prepare webhook payload
            webhook_payload = {
                "event": event_type,
                "data": payload,
                "metadata": metadata or {},
                "timestamp": time.time(),
                "delivery_id": hashlib.sha256(f"{endpoint_name}{event_type}{time.time()}".encode()).hexdigest()[:16]
            }

            # Apply transformation if configured
            if endpoint["transformation"]:
                webhook_payload = self._transform_payload(webhook_payload, endpoint["transformation"])

            # Generate signature
            signature = self._generate_signature(endpoint_name, webhook_payload)

            # Deliver webhook
            delivery_result = self._deliver_webhook(endpoint, webhook_payload, signature)
            delivery_results.append(delivery_result)

        return {
            "event_triggered": event_type,
            "endpoints_notified": len(delivery_results),
            "successful_deliveries": len([r for r in delivery_results if r["success"]]),
            "failed_deliveries": len([r for r in delivery_results if not r["success"]]),
            "delivery_results": delivery_results
        }

    def _apply_filters(self, payload, filters):
        """Apply filters to determine if webhook should be sent"""

        if not filters:
            return True

        for field, condition in filters.items():
            value = payload.get(field)

            if isinstance(condition, dict):
                # Complex condition
                if "equals" in condition and value != condition["equals"]:
                    return False
                if "contains" in condition and condition["contains"] not in str(value):
                    return False
                if "greater_than" in condition and value <= condition["greater_than"]:
                    return False
            else:
                # Simple equality
                if value != condition:
                    return False

        return True

    def _transform_payload(self, payload, transformation):
        """Transform webhook payload"""

        # Simple transformation simulation
        if transformation == "flatten":
            # Flatten nested structure
            flattened = {}

            def flatten_dict(d, parent_key=''):
                for k, v in d.items():
                    new_key = f"{parent_key}.{k}" if parent_key else k
                    if isinstance(v, dict):
                        flatten_dict(v, new_key)
                    else:
                        flattened[new_key] = v

            flatten_dict(payload)
            return flattened

        return payload

    def _generate_signature(self, endpoint_name, payload):
        """Generate webhook signature"""

        secret = self.webhook_secrets.get(endpoint_name, "")

        # Create signature
        payload_string = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            secret.encode(),
            payload_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _deliver_webhook(self, endpoint, payload, signature):
        """Deliver webhook to endpoint"""

        delivery_start = time.time()

        try:
            # Prepare headers
            headers = endpoint["headers"].copy()
            headers["Content-Type"] = "application/json"
            headers["X-Webhook-Signature"] = signature
            headers["X-Webhook-Timestamp"] = str(int(time.time()))
            headers["X-Webhook-Delivery-ID"] = payload["delivery_id"]

            # Add authentication
            if endpoint["auth_type"] == "bearer":
                token = endpoint["auth_config"].get("token", "")
                headers["Authorization"] = f"Bearer {token}"

            # Simulate delivery
            delivery_time = time.time() - delivery_start

            # Simulate success/failure
            import random
            success = random.random() > 0.1  # 90% success rate

            delivery_result = {
                "endpoint": endpoint["name"],
                "url": endpoint["url"],
                "delivery_id": payload["delivery_id"],
                "success": success,
                "status_code": 200 if success else 500,
                "delivery_time": delivery_time,
                "timestamp": time.time()
            }

            # Log delivery
            self._log_delivery(delivery_result)

            # Queue for retry if failed
            if not success:
                self._queue_for_retry(endpoint, payload, signature, 1)

            return delivery_result

        except Exception as e:
            delivery_result = {
                "endpoint": endpoint["name"],
                "url": endpoint["url"],
                "delivery_id": payload["delivery_id"],
                "success": False,
                "error": str(e),
                "delivery_time": time.time() - delivery_start,
                "timestamp": time.time()
            }

            self._log_delivery(delivery_result)
            self._queue_for_retry(endpoint, payload, signature, 1)

            return delivery_result

    def _queue_for_retry(self, endpoint, payload, signature, attempt):
        """Queue failed webhook for retry"""

        if attempt > self.delivery_config["max_retries"]:
            return

        retry_entry = {
            "endpoint": endpoint,
            "payload": payload,
            "signature": signature,
            "attempt": attempt,
            "retry_after": time.time() + (self.delivery_config["retry_delay"] * (2 ** (attempt - 1))),
            "queued_at": time.time()
        }

        self.retry_queue.append(retry_entry)

    def process_retry_queue(self):
        """Process webhooks in retry queue"""

        current_time = time.time()
        processed = 0

        # Process due retries
        due_retries = [r for r in self.retry_queue if r["retry_after"] <= current_time]

        for retry in due_retries:
            # Retry delivery
            delivery_result = self._deliver_webhook(
                retry["endpoint"],
                retry["payload"],
                retry["signature"]
            )

            if not delivery_result["success"]:
                # Queue for next retry
                self._queue_for_retry(
                    retry["endpoint"],
                    retry["payload"],
                    retry["signature"],
                    retry["attempt"] + 1
                )

            processed += 1
            self.retry_queue.remove(retry)

        return {
            "processed": processed,
            "remaining": len(self.retry_queue),
            "next_retry": min([r["retry_after"] for r in self.retry_queue]) if self.retry_queue else None
        }

    def _log_delivery(self, delivery_result):
        """Log webhook delivery"""

        self.delivery_log.append(delivery_result)

        # Keep only last 1000 entries
        if len(self.delivery_log) > 1000:
            self.delivery_log = self.delivery_log[-1000:]

    def get_webhook_analytics(self):
        """Get webhook delivery analytics"""

        # Recent deliveries (last hour)
        recent_cutoff = time.time() - 3600
        recent_deliveries = [d for d in self.delivery_log if d["timestamp"] >= recent_cutoff]

        # Calculate metrics
        total_deliveries = len(recent_deliveries)
        successful_deliveries = len([d for d in recent_deliveries if d["success"]])

        # Group by endpoint
        endpoint_stats = {}
        for delivery in recent_deliveries:
            endpoint = delivery["endpoint"]
            if endpoint not in endpoint_stats:
                endpoint_stats[endpoint] = {"total": 0, "success": 0, "failed": 0}

            endpoint_stats[endpoint]["total"] += 1
            if delivery["success"]:
                endpoint_stats[endpoint]["success"] += 1
            else:
                endpoint_stats[endpoint]["failed"] += 1

        # Average delivery time
        delivery_times = [d["delivery_time"] for d in recent_deliveries if "delivery_time" in d]
        avg_delivery_time = sum(delivery_times) / len(delivery_times) if delivery_times else 0

        return {
            "time_window": "last_hour",
            "total_deliveries": total_deliveries,
            "successful_deliveries": successful_deliveries,
            "success_rate": (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 100,
            "avg_delivery_time": round(avg_delivery_time, 3),
            "endpoint_stats": endpoint_stats,
            "retry_queue_size": len(self.retry_queue),
            "active_endpoints": len([e for e in self.webhook_endpoints.values() if e["active"]]),
            "total_subscriptions": sum(len(endpoints) for endpoints in self.webhook_subscriptions.values())
        }

# Usage example
webhook_manager = EnterpriseWebhookManager(app)

# Register webhook endpoint
webhook_config = webhook_manager.register_webhook_endpoint("external_system", {
    "url": "https://external-system.com/webhooks",
    "method": "POST",
    "headers": {"X-Custom-Header": "nexus-webhook"},
    "auth_type": "bearer",
    "auth_config": {"token": "webhook_token_123"},
    "events": ["workflow.completed", "data.created"],
    "filters": {"status": "success"},
    "rate_limit": 50
})

print(f"Webhook Configuration: {webhook_config}")

# Create webhook-triggered workflow
triggered_workflow = webhook_manager.create_webhook_workflow(
    "webhook_processor",
    "workflow.completed"
)

print(f"Triggered Workflow: {triggered_workflow}")

# Trigger webhook
trigger_result = webhook_manager.trigger_webhook(
    WebhookEvent.WORKFLOW_COMPLETED,
    {
        "workflow_id": "wf_12345",
        "status": "success",
        "execution_time": 15.5,
        "result": {"processed_records": 1000}
    },
    {"source": "nexus_platform", "version": "1.0"}
)

print(f"Trigger Result: {trigger_result}")

# Process retry queue
retry_result = webhook_manager.process_retry_queue()
print(f"Retry Processing: {retry_result}")

# Get webhook analytics
analytics = webhook_manager.get_webhook_analytics()
print(f"Webhook Analytics: {analytics}")
```

## Next Steps

Explore advanced Nexus capabilities:

1. **[Troubleshooting](troubleshooting.md)** - Integration issue diagnosis
2. **[Performance Guide](performance-guide.md)** - Optimize integration performance
3. **[Security Guide](security-guide.md)** - Secure integration patterns
4. **[Production Deployment](../advanced/production-deployment.md)** - Production integration strategies

## Key Takeaways

✅ **REST API Integration** → Advanced HTTP client with retry logic and circuit breakers
✅ **Database Connectivity** → Multi-database support with connection pooling
✅ **Message Queue Integration** → Enterprise messaging with dead letter queues
✅ **Webhook System** → Reliable webhook delivery with retry mechanisms
✅ **Error Handling** → Comprehensive retry strategies and failure recovery
✅ **Monitoring** → Real-time health checks and performance analytics

Nexus's workflow-native architecture makes it naturally suited for complex integration scenarios, providing built-in reliability, monitoring, and error recovery that scales automatically with your integration needs.
