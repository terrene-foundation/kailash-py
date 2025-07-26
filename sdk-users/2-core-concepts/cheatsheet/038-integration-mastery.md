# Integration Mastery

*Complete guide for integrating Kailash SDK with external systems*

## 🔗 API Integration Patterns

### REST API Integration
```python
from kailash.nodes.api import HTTPRequestNode, RESTClientNode

# Simple HTTP Request
workflow.add_node("HTTPRequestNode", "api_call", {}),
    url="https://api.example.com/data",
    method="GET",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)

# REST Client with Auth
workflow.add_node("RESTClientNode", "rest_client", {}),
    base_url="https://api.example.com",
    auth_type="bearer",
    auth_config={"token": "YOUR_TOKEN"}
)

# Execute with dynamic parameters
runtime.execute(workflow, parameters={
    "api_call": {
        "url": "https://api.example.com/users/123",
        "headers": {"X-Custom": "value"}
    }
})

```

### GraphQL Integration
```python
from kailash.nodes.api import GraphQLClientNode

workflow.add_node("GraphQLClientNode", "graphql", {}),
    endpoint="https://api.github.com/graphql",
    headers={"Authorization": "Bearer github_token"}
)

runtime.execute(workflow, parameters={
    "graphql": {
        "query": """
        query GetUser($login: String!) {
            user(login: $login) {
                name
                repositories(first: 10) {
                    nodes { name }
                }
            }
        }
        """,
        "variables": {"login": "username"}
    }
})

```

### OAuth2 Integration
```python
from kailash.nodes.api import OAuth2Node

# OAuth2 flow
workflow.add_node("oauth", OAuth2Node(),
    client_id="your_client_id",
    client_secret="your_client_secret",
    authorization_url="https://provider.com/oauth/authorize",
    token_url="https://provider.com/oauth/token",
    scopes=["read", "write"]
)

# Use OAuth token in subsequent calls
workflow.add_connection("oauth", "api_call", "access_token", "auth_token")

```

## 📊 Database Integration

### SQL Database Integration
```python
from kailash.nodes.data import SQLDatabaseNode, AsyncSQLDatabaseNode

# Synchronous database operations
workflow.add_node("SQLDatabaseNode", "db_query", {}),
    connection_string="postgresql://user:pass@localhost/db",
    query="SELECT * FROM customers WHERE status = :status",
    parameters={"status": "active"}
)

# Asynchronous for better performance
workflow.add_node("AsyncSQLDatabaseNode", "async_db", {}),
    connection_string="postgresql://user:pass@localhost/db",
    pool_size=10,
    max_overflow=20
)

runtime.execute(workflow, parameters={
    "async_db": {
        "query": "INSERT INTO logs (message, timestamp) VALUES (:msg, :ts)",
        "parameters": {
            "msg": "Workflow executed",
            "ts": "2024-01-01T10:00:00Z"
        }
    }
})

```

### Database Transactions
```python
# Multi-operation transaction
workflow.add_node("AsyncSQLDatabaseNode", "transaction", {}),
    connection_string="postgresql://user:pass@localhost/db",
    transaction_mode=True
)

runtime.execute(workflow, parameters={
    "transaction": {
        "operations": [
            {
                "query": "UPDATE accounts SET balance = balance - :amount WHERE id = :from_id",
                "parameters": {"amount": 100, "from_id": 1}
            },
            {
                "query": "UPDATE accounts SET balance = balance + :amount WHERE id = :to_id",
                "parameters": {"amount": 100, "to_id": 2}
            }
        ]
    }
})

```

## 🗂️ File System Integration

### File Processing Patterns
```python
from kailash.nodes.data import DirectoryReaderNode, CSVReaderNode, JSONReaderNode

# Directory scanning with filtering
workflow.add_node("DirectoryReaderNode", "scanner", {}),
    directory_path="/data/inputs",
    file_pattern="*.csv",
    recursive=True,
    include_metadata=True
)

# Batch file processing
batch_processor = PythonCodeNode.from_function(
    name="batch_processor",
    func=lambda file_list: {
        "processed": [
            {"file": f, "status": "processed", "type": "csv"}
            for f in file_list if f.endswith('.csv')
        ]
    }
)

workflow.add_connection("scanner", "batch_processor", "file_paths", "file_list")

```

### Cloud Storage Integration
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# S3/Cloud storage pattern
s3_reader = PythonCodeNode.from_function(
    name="s3_reader",
    func=lambda bucket_name, object_key, access_key, secret_key: {
        'content': read_s3_object(bucket_name, object_key, access_key, secret_key),
        'success': True
    }
)

def read_s3_object(bucket_name, object_key, access_key, secret_key):
    import boto3
    try:
        s3 = boto3.client('s3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        response = s3.get_object(Bucket=bucket_name, Key=object_key)
        return response['Body'].read().decode('utf-8')
    except Exception as e:
        return f"Error: {str(e)}"

```

## 🔐 Authentication Integration

### JWT Integration
```python
from kailash.nodes.security import JWTAuthNode

workflow.add_node("JWTAuthNode", "jwt_auth", {}),
    secret_key="your-secret-key",
    algorithm="HS256",
    expire_minutes=60
)

# Generate token
runtime.execute(workflow, parameters={
    "jwt_auth": {
        "action": "generate",
        "payload": {
            "user_id": "123",
            "role": "admin",
            "permissions": ["read", "write"]
        }
    }
})

# Verify token
runtime.execute(workflow, parameters={
    "jwt_auth": {
        "action": "verify",
        "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    }
})

```

### LDAP/Active Directory Integration
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

ldap_auth = PythonCodeNode.from_function(
    name="ldap_auth",
    func=lambda username, password, ldap_server, domain, search_base: {
        'authenticated': authenticate_ldap(username, password, ldap_server, domain, search_base)
    }
)

def authenticate_ldap(username, password, ldap_server, domain, search_base):
    import ldap3
    try:
        server = ldap3.Server(ldap_server)
        conn = ldap3.Connection(
            server,
            user=f"{username}@{domain}",
            password=password,
            auto_bind=True
        )

        # Search for user
        conn.search(
            search_base,
            f'(sAMAccountName={username})',
            attributes=['displayName', 'mail', 'memberOf']
        )

        if conn.entries:
            user_info = conn.entries[0]
            return {
                "authenticated": True,
                "user": {
                    "name": str(user_info.displayName),
                    "email": str(user_info.mail),
                    "groups": [str(group) for group in user_info.memberOf]
                }
            }
        else:
            return {"authenticated": False, "error": "User not found"}

    except Exception as e:
        return {"authenticated": False, "error": str(e)}

```

## 📧 Messaging Integration

### Email Integration
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

email_sender = PythonCodeNode.from_function(
    name="email_sender",
    func=lambda sender_email, recipient_email, subject, body, smtp_config: {
        'sent': send_email(sender_email, recipient_email, subject, body, smtp_config)
    }
)

def send_email(sender_email, recipient_email, subject, body, smtp_config):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html' if smtp_config.get('html') else 'plain'))

        server = smtplib.SMTP(smtp_config['server'], smtp_config['port'])
        if smtp_config.get('use_tls'):
            server.starttls()
        if smtp_config.get('username') and smtp_config.get('password'):
            server.login(smtp_config['username'], smtp_config['password'])

        server.send_message(msg)
        server.quit()

        return {"sent": True, "message": "Email sent successfully"}
    except Exception as e:
        return {"sent": False, "error": str(e)}

```

### Slack Integration
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

slack_notify = PythonCodeNode.from_function(
    name="slack_notify",
    func=lambda webhook_url, channel, message, bot_name: {
        'sent': send_slack_message(webhook_url, channel, message, bot_name)
    }
)

def send_slack_message(webhook_url, channel, message, bot_name):
    import requests

    payload = {
        "channel": channel,
        "text": message,
        "username": bot_name,
        "icon_emoji": ":robot_face:"
    }

    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        return {"sent": True, "response": response.json()}
    except Exception as e:
        return {"sent": False, "error": str(e)}

```

## 🚀 Microservices Integration

### Service Discovery Pattern
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Service registry lookup
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "service_discovery", {}),
    url="http://consul:8500/v1/health/service/user-service",
    method="GET"
)

# Dynamic service call
service_caller = PythonCodeNode.from_function(
    name="service_caller",
    func=lambda services, params: call_healthy_service(services, params)
)

def call_healthy_service(services, params):
    import requests

    # Get healthy service instance
    healthy_services = [s for s in services if len(s['Checks']) > 0
                       and all(c['Status'] == 'passing' for c in s['Checks'])]

    if not healthy_services:
        return {"error": "No healthy service instances"}

    service = healthy_services[0]['Service']
    service_url = f"http://{service['Address']}:{service['Port']}/api/users"

    try:
        response = requests.get(service_url, params=params)
        response.raise_for_status()
        return {"data": response.json(), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Event Streaming Integration
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Kafka integration
kafka_producer = PythonCodeNode.from_function(
    name="kafka_producer",
    func=lambda bootstrap_servers, topic, message: send_kafka_message(bootstrap_servers, topic, message)
)

def send_kafka_message(bootstrap_servers, topic, message):
    from kafka import KafkaProducer
    import json

    try:
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )

        # Send message
        future = producer.send(topic, message)
        record_metadata = future.get(timeout=10)

        return {
            "sent": True,
            "topic": record_metadata.topic,
            "partition": record_metadata.partition,
            "offset": record_metadata.offset
        }
    except Exception as e:
        return {"sent": False, "error": str(e)}
    finally:
        producer.close()

```

## 🌐 Web Integration Patterns

### Webhook Integration
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Webhook receiver workflow
webhook_processor = PythonCodeNode.from_function(
    name="webhook_processor",
    func=lambda payload, signature, webhook_secret, headers: process_webhook(payload, signature, webhook_secret, headers)
)

def process_webhook(payload, signature, webhook_secret, headers):
    import hashlib
    import hmac
    import json

    # Verify webhook signature
    expected_signature = hmac.new(
        webhook_secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    if signature != f"sha256={expected_signature}":
        return {"error": "Invalid signature", "verified": False}

    # Process webhook data
    event_type = headers.get('X-Event-Type', 'unknown')

    return {
        "verified": True,
        "event_type": event_type,
        "processed": True,
        "data": json.loads(payload)
    }

```

### WebSocket Integration
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# WebSocket client
websocket_client = PythonCodeNode.from_function(
    name="websocket_client",
    func=lambda websocket_url, message: connect_websocket(websocket_url, message)
)

def connect_websocket(websocket_url, message):
    import asyncio
    import websockets
    import json

    async def connect_and_send():
        try:
            async with websockets.connect(websocket_url) as websocket:
                # Send message
                await websocket.send(json.dumps(message))

                # Receive response
                response = await websocket.recv()
                return json.loads(response)
        except Exception as e:
            return {"error": str(e)}

    # Run async operation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(connect_and_send())
        return result
    finally:
        loop.close()

```

## 🔧 Error Handling Patterns

### Retry with Exponential Backoff
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

resilient_api = PythonCodeNode.from_function(
    name="resilient_api",
    func=lambda api_url, headers, params, max_retries: call_with_retry(api_url, headers, params, max_retries)
)

def call_with_retry(api_url, headers, params, max_retries):
    import time
    import requests

    def exponential_backoff(attempt):
        return min(2 ** attempt, 60)  # Max 60 seconds

    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.get(
                api_url,
                headers=headers,
                timeout=30,
                params=params
            )
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "attempts": attempt + 1
            }
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait_time = exponential_backoff(attempt)
                time.sleep(wait_time)
            continue

    return {
        "success": False,
        "error": last_error,
        "attempts": max_retries
    }

```

### Circuit Breaker Pattern
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

circuit_breaker = PythonCodeNode.from_function(
    name="circuit_breaker",
    func=lambda api_url, params, circuit_state, failure_count, failure_threshold: handle_circuit_breaker(
        api_url, params, circuit_state, failure_count, failure_threshold
    )
)

def handle_circuit_breaker(api_url, params, circuit_state, failure_count, failure_threshold):
    import time
    import requests

    current_time = time.time()

    # Circuit breaker logic
    if circuit_state == "open":
        return {
            "success": False,
            "error": "Circuit breaker is OPEN",
            "circuit_state": "open"
        }
    elif circuit_state == "half_open":
        # Try one request
        try:
            response = requests.get(api_url, params=params, timeout=10)
            response.raise_for_status()
            return {"success": True, "data": response.json(), "circuit_state": "closed"}
        except Exception as e:
            return {"success": False, "error": str(e), "circuit_state": "open"}
    else:  # closed
        try:
            response = requests.get(api_url, params=params, timeout=10)
            response.raise_for_status()
            return {"success": True, "data": response.json(), "circuit_state": "closed"}
        except Exception as e:
            failure_count += 1
            new_state = "open" if failure_count >= failure_threshold else "closed"
            return {"success": False, "error": str(e), "circuit_state": new_state}

```

## 📚 Quick Reference

### Integration Checklist
1. **Authentication** - Use proper auth patterns (JWT, OAuth2, API keys)
2. **Error Handling** - Implement retry logic and circuit breakers
3. **Rate Limiting** - Respect API limits with proper delays
4. **Data Validation** - Validate all external data inputs
5. **Monitoring** - Log all integration attempts and responses
6. **Security** - Never log sensitive data (tokens, passwords)

### Common Integration Nodes
- `HTTPRequestNode` - Simple HTTP calls
- `RESTClientNode` - Full REST client with auth
- `GraphQLClientNode` - GraphQL queries
- `OAuth2Node` - OAuth2 authentication flow
- `SQLDatabaseNode` - Database operations
- `PythonCodeNode.from_function()` - Custom integration logic

### Best Practices
- Use environment variables for configuration
- Implement proper error handling and retries
- Validate all external inputs
- Monitor integration health
- Use connection pooling for databases
- Implement circuit breakers for external services

---
*Related: [035-production-readiness.md](035-production-readiness.md), [007-error-handling.md](007-error-handling.md)*
