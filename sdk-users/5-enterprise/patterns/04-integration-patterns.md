# Integration Patterns

Patterns for connecting Kailash workflows with external services, APIs, and systems.

## 1. API Gateway Pattern

**Purpose**: Create a unified REST API interface for multiple workflows

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.api.middleware import create_gateway
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode

# Create workflows
data_workflow = WorkflowBuilder()
data_workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
data_workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'record_count': len(data), 'processed': True}"
})
data_workflow.add_connection("reader", "data", "processor", "data")

ml_workflow = WorkflowBuilder()
# Workflow setup goes here  # ... define ML workflow nodes ...

report_workflow = WorkflowBuilder()
# Workflow setup goes here  # ... define report workflow nodes ...

# Create API Gateway with middleware
gateway = create_gateway(
    title="Kailash Workflow API",
    version="1.0.0",
    cors_origins=["http://localhost:3000"]
)

# Note: With the new middleware approach, workflows are created
# dynamically via API calls, not pre-registered. This provides
# better flexibility and session-based isolation.
# See middleware documentation for dynamic workflow creation patterns.
# For simple single-workflow APIs, you can still use WorkflowAPI:
from kailash.api.workflow_api import WorkflowAPI
api = WorkflowAPI(data_workflow)
api.run(port=8001)

# For enterprise multi-workflow applications, use the middleware approach
# which provides dynamic workflow creation, real-time updates, and more.

# Authentication is built into the gateway
from kailash.middleware.auth import JWTAuthManager
auth = JWTAuthManager(secret_key="your-secret-key")
gateway_with_auth = create_gateway(
    title="Secured API",
    auth_manager=auth,
    enable_auth=True
)

# CORS is configured during gateway creation
# Rate limiting can be added via external middleware like slowapi

# Start the gateway
if __name__ == "__main__":
    gateway.run()  # Serves at http://localhost:8000
    # Auto-generated docs at http://localhost:8000/docs

```

**Usage Example**:
```bash
# Call workflow via REST API
curl -X POST http://localhost:8000/process-data \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "sales_data.csv"}'

# Response
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "results": {
    "processor": {
      "record_count": 1523,
      "processed": true
    }
  },
  "execution_time": 1.23
}
```

## 2. External API Integration Pattern

**Purpose**: Integrate with third-party APIs using authentication and error handling

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.api import RESTClientNode, OAuth2Node
from kailash.nodes.code import PythonCodeNode
import os

workflow = WorkflowBuilder()

# OAuth2 Authentication
workflow.add_node("OAuth2Node", "oauth", {
    "client_id": os.getenv("CLIENT_ID"),
    "client_secret": os.getenv("CLIENT_SECRET"),
    "token_url": "https://auth.example.com/oauth/token",
    "scope": "read:data write:data"
})

# REST API Client with authentication
workflow.add_node("RESTClientNode", "api_client", {
    "base_url": "https://api.example.com/v2",
    "timeout": 30,
    "retry_count": 3,
    "retry_delay": 1.0,
    "rate_limit": 100  # requests per minute
})

# Data transformer
workflow.add_node("PythonCodeNode", "transformer", {
    "code": """
# Transform external API response to internal format
transformed_data = []
for item in api_response.get('data', []):
    transformed = {
        'id': item['external_id'],
        'name': item['display_name'],
        'value': item['metrics']['value'],
        'timestamp': item['created_at'],
        'source': 'external_api'
    }
    transformed_data.append(transformed)

result = {
    'data': transformed_data,
    'count': len(transformed_data),
    'source_api': api_response.get('api_version', 'unknown')
}
"""
})

# Error handler
workflow.add_node("PythonCodeNode", "error_handler", {
    "code": """
import json

error_type = error.get('type', 'unknown')
status_code = error.get('status_code', 0)

if status_code == 429:
    # Rate limit exceeded
    result = {
        'action': 'retry',
        'wait_time': int(error.get('headers', {}).get('Retry-After', 60)),
        'message': 'Rate limit exceeded, will retry'
    }
elif status_code >= 500:
    # Server error
    result = {
        'action': 'retry',
        'wait_time': 30,
        'message': 'Server error, will retry'
    }
elif status_code == 401:
    # Authentication error
    result = {
        'action': 'reauthenticate',
        'message': 'Authentication failed, refreshing token'
    }
else:
    # Other errors
    result = {
        'action': 'fail',
        'message': f'Unrecoverable error: {error_type}',
        'details': json.dumps(error, indent=2)
    }
"""
})

# Connect with error handling
workflow.add_connection("oauth", "access_token", "api_client", "auth_token")

# API calls with error routing
workflow.add_node("SwitchNode", "api_switch", {
    "condition": "success == True",
    "true_path": "transformer",
    "false_path": "error_handler"
})

workflow.add_connection("api_client", "response", "api_switch", "input")
workflow.add_connection("api_switch", "true_output", "transformer", "api_response")
workflow.add_connection("api_switch", "false_output", "error_handler", "error")

```

## 3. Webhook Integration Pattern

**Purpose**: Receive and process webhook events from external systems

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.api import HTTPServerNode

# For webhooks, use the middleware gateway which supports
# webhook endpoints natively, or use HTTPServerNode for simple cases

# Define webhook processing workflow
webhook_workflow = WorkflowBuilder()

# Event validator
webhook_workflow.add_node("PythonCodeNode", "validator", {
    "code": """
import hmac
import hashlib

# Validate webhook signature
expected_signature = hmac.new(
    config['webhook_secret'].encode(),
    raw_body.encode(),
    hashlib.sha256
).hexdigest()

is_valid = hmac.compare_digest(
    expected_signature,
    headers.get('X-Webhook-Signature', '')
)

if not is_valid:
    raise ValueError("Invalid webhook signature")

# Parse event
import json
event = json.loads(raw_body)

result = {
    'event_type': event.get('type'),
    'event_id': event.get('id'),
    'data': event.get('data', {}),
    'timestamp': event.get('timestamp'),
    'valid': True
}
""",
    "config": {"webhook_secret": os.getenv("WEBHOOK_SECRET")}
})

# Event router
webhook_workflow.add_node("SwitchNode", "event_router", {
    "condition": "event_type in ['order.created', 'payment.received', 'user.updated']",
    "routes": {
        "order.created": "order_processor",
        "payment.received": "payment_processor",
        "user.updated": "user_processor",
        "default": "unknown_event_handler"
    }
})

# Specific event processors
webhook_workflow.add_node("PythonCodeNode", "order_processor", {
    "code": """
# Process new order event
order = data.get('order', {})
result = {
    'action': 'process_order',
    'order_id': order.get('id'),
    'customer_id': order.get('customer_id'),
    'total': order.get('total'),
    'items': order.get('items', [])
}

# Trigger order fulfillment workflow
print(f"New order received: {order.get('id')}")
"""
})

# Connect webhook receiver to workflow
webhook.register_handler(
    event_type="*",  # Handle all events
    workflow=webhook_workflow,
    async_execution=True  # Don't block webhook response
)

# Configure webhook endpoints
webhook.add_endpoint(
    path="/webhooks/stripe",
    workflow=webhook_workflow,
    validator="stripe_signature"
)

webhook.add_endpoint(
    path="/webhooks/github",
    workflow=webhook_workflow,
    validator="github_signature"
)

# Start webhook server
if __name__ == "__main__":
    webhook.start()

```

## 4. Database Integration Pattern

**Purpose**: Connect workflows to various databases with production-grade connection pooling

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data import SQLDatabaseNode, MongoNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Production PostgreSQL with connection pooling
workflow.add_node("SQLDatabaseNode", "pg_pool", {
    "connection_string": f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', 5432)}/{os.getenv('POSTGRES_DB', 'production')}",
    "min_connections": 10,
    "max_connections": 50,
    "health_threshold": 70,
    "pre_warm": True
})

# Initialize pool
workflow.add_node("PythonCodeNode", "init_pool", {
    "code": "result = {'operation': 'initialize'}"
})
workflow.add_connection("init_pool", "result", "pg_pool", "input")

# Read customer data with connection pool
workflow.add_node("PythonCodeNode", "read_customers", {
    "code": """
# Acquire connection from pool
conn_result = await pool.execute({"operation": "acquire"})
conn_id = conn_result["connection_id"]

try:
    # Execute query
    result = await pool.execute({
        "operation": "execute",
        "connection_id": conn_id,
        "query": '''
            SELECT
                c.id,
                c.name,
                c.email,
                COUNT(o.id) as order_count,
                SUM(o.total) as total_spent
            FROM customers c
            LEFT JOIN orders o ON c.id = o.customer_id
            WHERE c.created_at > $1
            GROUP BY c.id, c.name, c.email
            ORDER BY total_spent DESC
            LIMIT $2
        ''',
        "params": [start_date, limit],
        "fetch_mode": "all"
    })
    customers = result["data"]
finally:
    # Always release connection
    await pool.execute({
        "operation": "release",
        "connection_id": conn_id
    })

result = {"customers": customers}
""",
    "inputs": {
        "pool": "{{pg_pool}}",
        "start_date": "2024-01-01",
        "limit": 100
    }
})

# MongoDB aggregation
workflow.add_node("MongoNode", "mongo_aggregator", {
    "connection_string": os.getenv("MONGO_URL"),
    "database": "analytics",
    "collection": "events",
    "operation": "aggregate",
    "pipeline": [
        {"$match": {"timestamp": {"$gte": "$$start_date"}}},
        {"$group": {
            "_id": "$user_id",
            "event_count": {"$sum": 1},
            "last_event": {"$max": "$timestamp"}
        }},
        {"$sort": {"event_count": -1}},
        {"$limit": 100}
    ],
    "options": {"allowDiskUse": True}
})

# Join data from multiple databases
workflow.add_node("PythonCodeNode", "data_joiner", {
    "code": """
# Create lookup dictionary from MongoDB data
user_events = {str(event['_id']): event for event in mongo_data}

# Enrich PostgreSQL data with MongoDB events
enriched_customers = []
for customer in postgres_data:
    customer_id = str(customer['id'])
    events = user_events.get(customer_id, {})

    enriched = {
        **customer,
        'event_count': events.get('event_count', 0),
        'last_event': events.get('last_event', None),
        'engagement_score': calculate_engagement_score(
            customer['order_count'],
            events.get('event_count', 0)
        )
    }
    enriched_customers.append(enriched)

result = {
    'customers': enriched_customers,
    'total': len(enriched_customers),
    'sources': ['postgresql', 'mongodb']
}

def calculate_engagement_score(orders, events):
    return min(100, (orders * 10) + (events * 2))
"""
})

# Write results back using connection pool (transactional)
workflow.add_node("PythonCodeNode", "write_analytics", {
    "code": """
# Use connection pool for transactional write
conn_result = await pool.execute({"operation": "acquire"})
conn_id = conn_result["connection_id"]

try:
    # Start transaction
    await pool.execute({
        "operation": "execute",
        "connection_id": conn_id,
        "query": "BEGIN",
        "fetch_mode": "one"
    })

    # Batch insert/update customer analytics
    for customer in enriched_customers:
        await pool.execute({
            "operation": "execute",
            "connection_id": conn_id,
            "query": '''
                INSERT INTO customer_analytics (
                    customer_id, engagement_score, event_count,
                    last_event, last_updated
                ) VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (customer_id)
                DO UPDATE SET
                    engagement_score = EXCLUDED.engagement_score,
                    event_count = EXCLUDED.event_count,
                    last_event = EXCLUDED.last_event,
                    last_updated = NOW()
            ''',
            "params": [
                customer["id"],
                customer["engagement_score"],
                customer["event_count"],
                customer["last_event"]
            ],
            "fetch_mode": "one"
        })

    # Commit transaction
    await pool.execute({
        "operation": "execute",
        "connection_id": conn_id,
        "query": "COMMIT",
        "fetch_mode": "one"
    })

    result = {"written": len(enriched_customers), "status": "success"}

except Exception as e:
    # Rollback on error
    await pool.execute({
        "operation": "execute",
        "connection_id": conn_id,
        "query": "ROLLBACK",
        "fetch_mode": "one"
    })
    result = {"error": str(e), "status": "failed"}
    raise
finally:
    # Always release connection
    await pool.execute({
        "operation": "release",
        "connection_id": conn_id
    })
""",
    "inputs": {
        "pool": "{{pg_pool}}",
        "enriched_customers": "{{data_joiner.result.customers}}"
    }
})

# Monitor pool performance
workflow.add_node("PythonCodeNode", "monitor_pool", {
    "code": """
# Get pool statistics
stats = await pool.execute({"operation": "stats"})

# Log performance metrics
result = {
    "pool_name": stats["pool_name"],
    "total_queries": stats["queries"]["executed"],
    "error_rate": stats["queries"]["error_rate"],
    "pool_efficiency": stats["queries"]["executed"] / stats["connections"]["created"],
    "active_connections": stats["current_state"]["active_connections"],
    "health_scores": stats["current_state"]["health_scores"]
}

# Alert if issues detected
if stats["queries"]["error_rate"] > 0.05:
    print(f"WARNING: High error rate: {stats['queries']['error_rate']:.2%}")

if stats["current_state"]["available_connections"] == 0:
    print("WARNING: Connection pool exhausted!")
""",
    "inputs": {"pool": "{{pg_pool}}"}
})

# Connect the workflow
workflow.add_connection("read_customers", "customers", "data_joiner", "postgres_data")
workflow.add_connection("mongo_aggregator", "result", "data_joiner", "mongo_data")
workflow.add_connection("data_joiner", "customers", "write_analytics", "enriched_customers")
workflow.add_connection("write_analytics", "result", "monitor_pool", "input")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### Advanced Database Patterns

#### Connection Pool Management Service
```python
from kailash.nodes.data import WorkflowConnectionPool
import asyncio

class DatabasePoolManager:
    """Centralized database connection pool management."""

    def __init__(self):
        self.pools = {}
        self.monitoring_task = None

    async def create_pool(self, name, config):
        """Create a new connection pool."""
        pool = WorkflowConnectionPool(
            name=name,
            **config
        )
        await pool.execute({"operation": "initialize"})
        self.pools[name] = pool

        # Start monitoring if not already running
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_pools())

        return pool

    async def get_pool(self, name):
        """Get an existing pool by name."""
        return self.pools.get(name)

    async def _monitor_pools(self):
        """Monitor all pools for health and performance."""
        while True:
            for name, pool in self.pools.items():
                try:
                    stats = await pool.execute({"operation": "stats"})

                    # Check for issues
                    if stats["queries"]["error_rate"] > 0.1:
                        logger.error(f"Pool {name}: High error rate {stats['queries']['error_rate']:.2%}")

                    if stats["current_state"]["available_connections"] == 0:
                        logger.warning(f"Pool {name}: No available connections")

                    # Check individual connection health
                    unhealthy = [
                        conn_id for conn_id, score in stats["current_state"]["health_scores"].items()
                        if score < 60
                    ]
                    if unhealthy:
                        logger.warning(f"Pool {name}: {len(unhealthy)} unhealthy connections")

                except Exception as e:
                    logger.error(f"Error monitoring pool {name}: {e}")

            await asyncio.sleep(30)  # Check every 30 seconds

# Usage in workflows
db_manager = DatabasePoolManager()

# Create pools for different purposes
await db_manager.create_pool("analytics", {
    "database_type": "postgresql",
    "host": "analytics-db.internal",
    "database": "analytics",
    "min_connections": 5,
    "max_connections": 20
})

await db_manager.create_pool("transactional", {
    "database_type": "postgresql",
    "host": "main-db.internal",
    "database": "production",
    "min_connections": 20,
    "max_connections": 100,
    "health_threshold": 60  # More aggressive for transactional
})

```

## 5. Message Queue Integration Pattern

**Purpose**: Integrate with message queues for async processing

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.integration import KafkaNode, RabbitMQNode
from kailash.nodes.code import PythonCodeNode

workflow = WorkflowBuilder()

# Kafka consumer
workflow.add_node("KafkaNode", "kafka_consumer", {
    "bootstrap_servers": os.getenv("KAFKA_BROKERS"),
    "topic": "orders",
    "consumer_group": "order_processor",
    "auto_offset_reset": "earliest",
    "batch_size": 100,
    "batch_timeout": 5000  # 5 seconds
})

# Process messages
workflow.add_node("PythonCodeNode", "message_processor", {
    "code": """
import json

processed_messages = []
failed_messages = []

for message in messages:
    try:
        # Parse message
        data = json.loads(message['value'])

        # Process based on message type
        if data.get('type') == 'order':
            result = process_order(data)
            processed_messages.append({
                'offset': message['offset'],
                'result': result
            })
        else:
            failed_messages.append({
                'offset': message['offset'],
                'error': 'Unknown message type'
            })

    except Exception as e:
        failed_messages.append({
            'offset': message['offset'],
            'error': str(e)
        })

result = {
    'processed': processed_messages,
    'failed': failed_messages,
    'total': len(messages)
}

def process_order(order_data):
    # Business logic here
    return {'order_id': order_data['id'], 'status': 'processed'}
"""
})

# RabbitMQ publisher for results
workflow.add_node("RabbitMQNode", "rabbitmq_publisher", {
    "connection_url": os.getenv("RABBITMQ_URL"),
    "exchange": "results",
    "routing_key": "order.processed",
    "operation": "publish"
})

# Dead letter queue for failures
workflow.add_node("RabbitMQNode", "dlq_publisher", {
    "connection_url": os.getenv("RABBITMQ_URL"),
    "exchange": "dlq",
    "routing_key": "order.failed",
    "operation": "publish"
})

# Route successes and failures
workflow.add_connection("kafka_consumer", "messages", "message_processor", "messages")
workflow.add_connection("message_processor", "processed", "rabbitmq_publisher", "messages")
workflow.add_connection("message_processor", "failed", "dlq_publisher", "messages")

```

## Best Practices

1. **Authentication & Security**:
   - Store credentials in environment variables
   - Use OAuth2 for API authentication
   - Validate webhook signatures
   - Implement SSL/TLS for all connections

2. **Error Handling**:
   - Implement retry logic with exponential backoff
   - Use circuit breakers for external services
   - Log all integration errors with context
   - Have fallback mechanisms

3. **Performance**:
   - Use connection pooling for databases
   - Implement caching for frequently accessed data
   - Batch API requests when possible
   - Use async operations for I/O

4. **Monitoring**:
   - Track API rate limits
   - Monitor response times
   - Log all external calls
   - Set up alerts for failures

## See Also
- [Error Handling Patterns](05-error-handling-patterns.md) - Resilient integrations
- [Security Patterns](10-security-patterns.md) - Secure API connections
- [Performance Patterns](06-performance-patterns.md) - Optimize integrations
