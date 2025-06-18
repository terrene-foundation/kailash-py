# Integration Patterns

Patterns for connecting Kailash workflows with external services, APIs, and systems.

## 1. API Gateway Pattern

**Purpose**: Create a unified REST API interface for multiple workflows

```python
from kailash import Workflow
from kailash.middleware import create_gateway
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode

# Create workflows
data_workflow = Workflow("example", name="Example")
workflow.data_workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
data_workflow.add_node("processor", PythonCodeNode(),
    code="result = {'record_count': len(data), 'processed': True}"
)
data_workflow.connect("reader", "processor", mapping={"data": "data"})

ml_workflow = Workflow("example", name="Example")
workflow.# ... define ML workflow nodes ...

report_workflow = Workflow("example", name="Example")
workflow.# ... define report workflow nodes ...

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
from kailash import Workflow
from kailash.nodes.api import RESTClientNode, OAuth2Node
from kailash.nodes.code import PythonCodeNode
import os

workflow = Workflow("external_api_integration", "External API Integration")

# OAuth2 Authentication
workflow.add_node("oauth", OAuth2Node(),
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    token_url="https://auth.example.com/oauth/token",
    scope="read:data write:data"
)

# REST API Client with authentication
workflow.add_node("api_client", RESTClientNode(),
    base_url="https://api.example.com/v2",
    timeout=30,
    retry_count=3,
    retry_delay=1.0,
    rate_limit=100  # requests per minute
)

# Data transformer
workflow.add_node("transformer", PythonCodeNode(),
    code="""
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
)

# Error handler
workflow.add_node("error_handler", PythonCodeNode(),
    code="""
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
)

# Connect with error handling
workflow.connect("oauth", "api_client", mapping={"access_token": "auth_token"})

# API calls with error routing
workflow.add_node("api_switch", SwitchNode(),
    condition_field="success",
    true_route="transformer",
    false_route="error_handler"
)

workflow.connect("api_client", "api_switch", mapping={"response": "input"})
workflow.connect("api_switch", "transformer",
    route="transformer",
    mapping={"input.data": "api_response"})
workflow.connect("api_switch", "error_handler",
    route="error_handler",
    mapping={"input.error": "error"})

```

## 3. Webhook Integration Pattern

**Purpose**: Receive and process webhook events from external systems

```python
from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.api import HTTPServerNode

# For webhooks, use the middleware gateway which supports
# webhook endpoints natively, or use HTTPServerNode for simple cases

# Define webhook processing workflow
webhook_workflow = Workflow("webhook_processor", "Webhook Event Processor")

# Event validator
webhook_workflow.add_node("validator", PythonCodeNode(),
    code="""
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
    config={"webhook_secret": os.getenv("WEBHOOK_SECRET")}
)

# Event router
webhook_workflow.add_node("event_router", SwitchNode(),
    condition_field="event_type",
    routes={
        "order.created": "order_processor",
        "payment.received": "payment_processor",
        "user.updated": "user_processor",
        "default": "unknown_event_handler"
    }
)

# Specific event processors
webhook_workflow.add_node("order_processor", PythonCodeNode(),
    code="""
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
)

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

**Purpose**: Connect workflows to various databases with connection pooling

```python
from kailash import Workflow
from kailash.nodes.data import SQLNode, MongoNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("database_integration", "Database Integration")

# PostgreSQL connection with pooling
workflow.add_node("postgres_reader", SQLNode(),
    connection_string=os.getenv("POSTGRES_URL"),
    pool_size=10,
    max_overflow=20,
    query="""
    SELECT
        c.id,
        c.name,
        c.email,
        COUNT(o.id) as order_count,
        SUM(o.total) as total_spent
    FROM customers c
    LEFT JOIN orders o ON c.id = o.customer_id
    WHERE c.created_at > %(start_date)s
    GROUP BY c.id, c.name, c.email
    ORDER BY total_spent DESC
    LIMIT %(limit)s
    """,
    parameters={
        "start_date": "2024-01-01",
        "limit": 100
    }
)

# MongoDB aggregation
workflow.add_node("mongo_aggregator", MongoNode(),
    connection_string=os.getenv("MONGO_URL"),
    database="analytics",
    collection="events",
    operation="aggregate",
    pipeline=[
        {"$match": {"timestamp": {"$gte": "$$start_date"}}},
        {"$group": {
            "_id": "$user_id",
            "event_count": {"$sum": 1},
            "last_event": {"$max": "$timestamp"}
        }},
        {"$sort": {"event_count": -1}},
        {"$limit": 100}
    ],
    options={"allowDiskUse": True}
)

# Join data from multiple databases
workflow.add_node("data_joiner", PythonCodeNode(),
    code="""
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
)

# Write results back to database
workflow.add_node("postgres_writer", SQLNode(),
    connection_string=os.getenv("POSTGRES_URL"),
    operation="execute_many",
    query="""
    INSERT INTO customer_analytics (
        customer_id, engagement_score, last_updated
    ) VALUES (
        %(customer_id)s, %(engagement_score)s, NOW()
    )
    ON CONFLICT (customer_id)
    DO UPDATE SET
        engagement_score = EXCLUDED.engagement_score,
        last_updated = NOW()
    """
)

# Connect the workflow
workflow.connect("postgres_reader", "data_joiner",
    mapping={"result": "postgres_data"})
workflow.connect("mongo_aggregator", "data_joiner",
    mapping={"result": "mongo_data"})
workflow.connect("data_joiner", "postgres_writer",
    mapping={"result.customers": "data"})

```

## 5. Message Queue Integration Pattern

**Purpose**: Integrate with message queues for async processing

```python
from kailash import Workflow
from kailash.nodes.integration import KafkaNode, RabbitMQNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("message_queue_integration", "Message Queue Integration")

# Kafka consumer
workflow.add_node("kafka_consumer", KafkaNode(),
    bootstrap_servers=os.getenv("KAFKA_BROKERS"),
    topic="orders",
    consumer_group="order_processor",
    auto_offset_reset="earliest",
    batch_size=100,
    batch_timeout=5000  # 5 seconds
)

# Process messages
workflow.add_node("message_processor", PythonCodeNode(),
    code="""
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
)

# RabbitMQ publisher for results
workflow.add_node("rabbitmq_publisher", RabbitMQNode(),
    connection_url=os.getenv("RABBITMQ_URL"),
    exchange="results",
    routing_key="order.processed",
    operation="publish"
)

# Dead letter queue for failures
workflow.add_node("dlq_publisher", RabbitMQNode(),
    connection_url=os.getenv("RABBITMQ_URL"),
    exchange="dlq",
    routing_key="order.failed",
    operation="publish"
)

# Route successes and failures
workflow.connect("kafka_consumer", "message_processor",
    mapping={"messages": "messages"})
workflow.connect("message_processor", "rabbitmq_publisher",
    mapping={"result.processed": "messages"})
workflow.connect("message_processor", "dlq_publisher",
    mapping={"result.failed": "messages"})

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
