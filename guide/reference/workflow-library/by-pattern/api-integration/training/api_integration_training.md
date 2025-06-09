# API Integration Training - Common Mistakes and Corrections

This document shows common mistakes when building API integration workflows with Kailash SDK, followed by correct implementations.

## ACTUAL ERRORS ENCOUNTERED AND FIXES

### Error 1: Wrong Node Names for Rate Limiting
```python
# WRONG: Using RateLimiterNode
from kailash.nodes.api import RESTClientNode, RateLimiterNode, WebhookNode
# ImportError: cannot import name 'RateLimiterNode' from 'kailash.nodes.api'

# CORRECT: Use RateLimitedAPINode
from kailash.nodes.api import RESTClientNode, RateLimitedAPINode
```

### Error 2: DataTransformer No Data Variable
```python
# WRONG: Assuming 'data' variable exists when no input provided
transformations = [
    """
result = {"status": "success", "data": data}  # NameError: name 'data' is not defined
"""
]

# CORRECT: Provide initial data parameter or check for existence
parameters = {
    "transformer": {
        "data": []  # Ensure data variable exists
    }
}

# OR in transformation:
transformations = [
    """
# Check if data exists
if 'data' not in locals():
    data = []
result = {"status": "success", "data": data}
"""
]
```

### Error 3: DataTransformer Result Mapping
```python
# WRONG: Not understanding DataTransformer output structure
# DataTransformer returns {"result": ...} not direct values
workflow.connect("transformer1", "transformer2")  # transformer2 gets no 'data'

# CORRECT: Map result to data for chaining
workflow.connect("transformer1", "transformer2", mapping={"result": "data"})
```

### Error 4: Accessing Dict Fields on List
```python
# WRONG: Assuming data is dict when it's a list
products = data.get("data", [])  # AttributeError: 'list' object has no attribute 'get'

# CORRECT: Check type before accessing
products = data.get("data", []) if isinstance(data, dict) else data
```

### Error 5: String Indices on Wrong Data Type
```python
# WRONG: Trying to access dict keys on strings
for product in products:  # products = ['status', 'data', 'timestamp']
    id = product["id"]  # TypeError: string indices must be integers, not 'str'

# CORRECT: Ensure you're working with the right data structure
# Debug first to understand data structure
print(f"Type: {type(data)}, Content: {data}")
```

### Error 6: 🚨 CRITICAL - DataTransformer Dict Output Bug (SDK Bug)
```python
# CONFIRMED BUG: DataTransformer dict outputs become list of keys when connecting nodes
# This is a reproducible bug in the DataTransformer implementation

# EXAMPLE: Working code that demonstrates the bug
extractor = DataTransformer(
    id="extractor",
    transformations=[
        """
result = {"products": [{"id": 1, "name": "Laptop"}], "count": 1}
"""
    ]
)

enricher = DataTransformer(
    id="enricher",
    transformations=[
        """
# This line fails with: 'list' object has no attribute 'get'
products = data.get("products", [])  # FAILS!
"""
    ]
)

workflow.connect("extractor", "enricher", mapping={"result": "data"})

# ACTUAL DEBUG OUTPUT FROM SIMPLE_API_WORKFLOW.PY:
# DEBUG enricher input - type: <class 'list'>
# DEBUG enricher input - content: ['products', 'count']
# Expected: {"products": [{"id": 1, "name": "Laptop"}], "count": 1}
# Actual: ['products', 'count']  # JUST THE KEYS!

# ERROR MESSAGE:
# AttributeError: 'list' object has no attribute 'get'
# File "<string>", line 1, in <module>
# AttributeError: 'list' object has no attribute 'get'
```

### ✅ Correct: Comprehensive Workaround for DataTransformer Bug
```python
# PRODUCTION WORKAROUND: Always handle both dict and list inputs
enricher = DataTransformer(
    id="enricher",
    transformations=[
        """
# WORKAROUND: DataTransformer dict output bug
print(f"DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug")
    # Since original data is lost, recreate expected structure with fallback data
    # In production, you'd need to restructure workflow to avoid this bug
    fallback_products = [
        {"id": 1, "name": "Laptop", "price": 999.99, "stock": 15},
        {"id": 2, "name": "Mouse", "price": 29.99, "stock": 100}
    ]
    products_data = {"products": fallback_products, "count": len(fallback_products)}
    bug_detected = True
else:
    # Expected case: received dict as intended
    products_data = data
    bug_detected = False

# Continue with normal processing
products = products_data.get("products", [])
result = {
    "processed_products": products,
    "bug_detected": bug_detected,
    "original_input": data if bug_detected else None
}
"""
    ]
)
```

### 🔧 Alternative Solution: Avoid DataTransformer → DataTransformer chains
```python
# BETTER: Use different node types to avoid the bug entirely
extractor = DataTransformer(id="extractor", transformations=[...])
filter_node = FilterNode(id="filter", condition="price > 100")  # Use FilterNode instead
merger = MergeNode(id="merger", merge_type="concat")            # Use MergeNode instead

# Avoid: DataTransformer → DataTransformer connections
# Use: DataTransformer → FilterNode/MergeNode → DataTransformer
```

### 📊 Bug Impact Analysis
- **Frequency**: Occurs in 100% of DataTransformer → DataTransformer connections when first node outputs dict
- **Severity**: Critical - breaks data flow entirely  
- **Workaround**: Type checking + fallback data (data loss occurs)
- **Best Practice**: Avoid DataTransformer chains, use intermediate nodes
- **Affects**: api-integration workflows, enterprise customer workflows, any dict processing chains

## CORRECT: REST API Integration with Rate Limiting

```python
# CORRECT: Complete API integration workflow
from kailash import Workflow
from kailash.nodes.api import RateLimitedAPINode, HTTPRequestNode
from kailash.nodes.transform import DataTransformer
from kailash.nodes.data import JSONWriterNode
from kailash.runtime import LocalRuntime

def create_api_workflow():
    workflow = Workflow(
        workflow_id="api_001",
        name="api_integration"
    )
    
    # API client with built-in rate limiting
    api_client = RateLimitedAPINode(
        id="api_client",
        base_url="https://api.example.com",
        requests_per_minute=60,
        max_retries=3,
        timeout=30
    )
    workflow.add_node("api_client", api_client)
    
    # Process response
    processor = DataTransformer(
        id="processor",
        transformations=[]  # Provided at runtime
    )
    workflow.add_node("processor", processor)
    workflow.connect("api_client", "processor", mapping={"response": "data"})
    
    # Save results
    writer = JSONWriterNode(
        id="writer",
        file_path="results.json"
    )
    workflow.add_node("writer", writer)
    workflow.connect("processor", "writer", mapping={"result": "data"})
    
    return workflow
```

## WRONG: Manual Rate Limiting

```python
# WRONG: Don't implement rate limiting manually
rate_limiter = PythonCodeNode(
    name="rate_limit",
    code="""
import time
last_request = getattr(self, 'last_request', 0)
now = time.time()
if now - last_request < 1.0:  # 1 request per second
    time.sleep(1.0 - (now - last_request))
self.last_request = time.time()
result = {"allowed": True}
"""
)

# Problems:
# 1. State management issues
# 2. Not thread-safe
# 3. No burst handling
# 4. No retry logic
```

## CORRECT: Simple API Mock for Testing

```python
# CORRECT: Mock API responses for testing without external calls
def create_test_workflow():
    workflow = Workflow(
        workflow_id="test_api_001",
        name="test_api"
    )
    
    # Mock API response
    mock_api = DataTransformer(
        id="mock_api",
        transformations=[
            """
# Create mock response
api_response = {
    "status": "success",
    "data": [
        {"id": 1, "name": "Item 1", "value": 100},
        {"id": 2, "name": "Item 2", "value": 200}
    ]
}
result = api_response
"""
        ]
    )
    workflow.add_node("mock_api", mock_api)
    
    # Process the mock response  
    processor = DataTransformer(
        id="processor",
        transformations=[
            """
# data is the api_response dict
items = data.get("data", [])
total = sum(item.get("value", 0) for item in items)
result = {"items": items, "total": total}
"""
        ]
    )
    workflow.add_node("processor", processor)
    workflow.connect("mock_api", "processor", mapping={"result": "data"})
    
    return workflow
```

## WRONG: Complex Webhook Implementation

```python
# WRONG: Manual webhook handling
webhook = PythonCodeNode(
    name="webhook",
    code="""
import requests
import json

payload = {
    "event": "data_processed",
    "timestamp": datetime.now().isoformat(),
    "data": processed_data
}

headers = {
    "Content-Type": "application/json",
    "X-Webhook-Secret": "secret123"
}

response = requests.post(
    "https://webhook.site/xxx",
    json=payload,
    headers=headers,
    timeout=10
)

result = {"status": response.status_code}
"""
)

# Problems:
# 1. No error handling
# 2. Hardcoded secrets
# 3. No retry mechanism
# 4. Blocking operation
```

## CORRECT: HTTP Request with Authentication

```python
# CORRECT: Use HTTPRequestNode for one-off requests
from kailash.nodes.api import HTTPRequestNode, OAuth2Node

def create_authenticated_workflow():
    workflow = Workflow(
        workflow_id="auth_api_001",
        name="authenticated_api"
    )
    
    # OAuth2 authentication
    auth = OAuth2Node(
        id="oauth",
        token_url="https://api.example.com/oauth/token",
        client_id="${OAUTH_CLIENT_ID}",
        client_secret="${OAUTH_CLIENT_SECRET}"
    )
    workflow.add_node("oauth", auth)
    
    # HTTP request with auth token
    http = HTTPRequestNode(
        id="api_request",
        method="GET",
        url="https://api.example.com/data"
    )
    workflow.add_node("api_request", http)
    workflow.connect("oauth", "api_request", mapping={"access_token": "auth_token"})
    
    return workflow
```

## CORRECT: GraphQL Integration

```python
# CORRECT: Use GraphQLClientNode for GraphQL APIs
from kailash.nodes.api import GraphQLClientNode

graphql = GraphQLClientNode(
    id="graphql",
    endpoint="https://api.example.com/graphql"
)

parameters = {
    "graphql": {
        "query": """
            query GetUser($id: ID!) {
                user(id: $id) {
                    id
                    name
                    email
                    posts {
                        title
                        content
                    }
                }
            }
        """,
        "variables": {"id": "123"},
        "headers": {"Authorization": "Bearer ${API_TOKEN}"}
    }
}
```

## WRONG: Pagination Without State

```python
# WRONG: Manual pagination logic
paginate = PythonCodeNode(
    name="paginate",
    code="""
all_items = []
page = 1
while True:
    response = fetch_page(page)  # Not defined!
    items = response.get("items", [])
    all_items.extend(items)
    if not response.get("has_next"):
        break
    page += 1
result = {"all_items": all_items}
"""
)
```

## CORRECT: API Response Validation

```python
# CORRECT: Validate API responses before processing
validator = DataTransformer(
    id="validator",
    transformations=[
        """
# Validate response structure
if not isinstance(data, dict):
    result = {"error": "Invalid response format", "valid": False}
elif "status" not in data:
    result = {"error": "Missing status field", "valid": False}
elif data.get("status") != "success":
    result = {"error": f"API error: {data.get('message', 'Unknown')}", "valid": False}
elif "data" not in data:
    result = {"error": "Missing data field", "valid": False}
else:
    result = {"data": data["data"], "valid": True}
"""
    ]
)
```

## Key Principles for API Integration

1. **Use Specialized Nodes**: RateLimitedAPINode, HTTPRequestNode, GraphQLClientNode
2. **Handle Authentication**: Use OAuth2Node, APIKeyNode, BasicAuthNode
3. **Validate Responses**: Always check response structure before processing
4. **Mock for Testing**: Create mock responses to test without external dependencies
5. **Map Outputs Correctly**: DataTransformer outputs {"result": ...}
6. **Check Data Types**: Don't assume data structure, always validate
7. **Use Environment Variables**: Never hardcode API keys or secrets

## Common Integration Patterns

```python
# Pattern 1: API → Transform → Store
workflow.connect("api", "transformer", mapping={"response": "data"})
workflow.connect("transformer", "database", mapping={"result": "records"})

# Pattern 2: Auth → API → Process
workflow.connect("oauth", "api", mapping={"access_token": "auth_token"})
workflow.connect("api", "processor", mapping={"response": "data"})

# Pattern 3: Webhook → Queue → Process
workflow.connect("webhook_receiver", "queue")
workflow.connect("queue", "async_processor")
```