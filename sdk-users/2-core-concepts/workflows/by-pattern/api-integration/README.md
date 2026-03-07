# API Integration Workflows

This directory contains comprehensive API integration workflow patterns using the Kailash SDK.

## Overview

API integration workflows demonstrate how to connect with external services, consume REST APIs, handle authentication, and process responses. These patterns use real public APIs and HTTP endpoints, making them immediately applicable to production scenarios.

## Core Pattern: REST API Integration

The REST API workflow demonstrates how to:
- **Call real APIs** using HTTPRequestNode with actual public endpoints
- **Handle authentication** including API keys, OAuth, and bearer tokens
- **Process responses** with proper error handling and data transformation
- **Chain API calls** for complex integration scenarios
- **Generate insights** from API response data

### Key Features

✅ **Real API Integration** - Uses actual public APIs (JSONPlaceholder, GitHub, HTTPBin)
✅ **Authentication Support** - Handles various auth methods and token management
✅ **Error Handling** - Robust handling of rate limits, timeouts, and API errors
✅ **Response Processing** - JSON parsing, data extraction, and transformation
✅ **Production Ready** - Includes logging, monitoring, and retry logic

## Available Scripts

### `scripts/rest_api_workflow.py`

**Purpose**: Comprehensive REST API integration with real public endpoints

**What it does**:
1. Fetches data from JSONPlaceholder API (posts, users, comments)
2. Retrieves repository information from GitHub API
3. Tests HTTP methods and responses using HTTPBin
4. Processes and analyzes API response data
5. Generates comprehensive API integration report

**Usage**:
```bash
# Run the API integration workflow
python sdk-users/workflows/by-pattern/api-integration/scripts/rest_api_workflow.py

# The script will:
# - Call multiple real public APIs
# - Process JSON responses
# - Handle different HTTP methods
# - Generate analysis report in /data/outputs/api-integration/
```

**Integrated APIs**:
- **JSONPlaceholder**: Testing and prototyping REST API
- **GitHub API**: Repository and user information
- **HTTPBin**: HTTP testing service for various scenarios

**Output**:
- API response analysis and statistics
- Data insights from fetched information
- Performance metrics (response times, success rates)
- Comprehensive integration report in JSON format

## Node Usage Patterns

### Basic API Calls
```python
# Fetch data from REST API
api_fetcher = HTTPRequestNode(
    name="api_fetcher",
    method="GET",
    url="https://jsonplaceholder.typicode.com/posts",
    headers={"Content-Type": "application/json"},
    timeout=10.0
)

# POST data to API
api_poster = HTTPRequestNode(
    name="api_poster",
    method="POST",
    url="https://httpbin.org/post",
    data={"key": "value"},
    headers={"Content-Type": "application/json"}
)

```

### Authenticated API Calls
```python
# API with authentication header
authenticated_api = HTTPRequestNode(
    name="authenticated_api",
    method="GET",
    url="https://api.github.com/user/repos",
    headers={
        "Authorization": "Bearer YOUR_TOKEN_HERE",
        "Accept": "application/vnd.github.v3+json"
    }
)

```

### Response Processing
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

# Process API responses
response_processor = PythonCodeNode.from_function(
    func=process_api_response,
    name="response_processor"
)

# Transform and analyze data
data_analyzer = PythonCodeNode.from_function(
    func=analyze_api_data,
    name="data_analyzer"
)

```

## API Integration Patterns

### Sequential API Calls
```python
def process_user_posts(users_data):
    """Process user data and prepare for posts API call"""
    if not users_data or "data" not in users_data:
        return {"user_ids": [], "error": "No user data available"}

    users = users_data["data"]
    if isinstance(users, list) and len(users) > 0:
        # Get first 3 users for posts lookup
        user_ids = [user.get("id") for user in users[:3] if user.get("id")]
        return {"user_ids": user_ids}

    return {"user_ids": [], "error": "Invalid user data format"}

```

### Parallel API Calls
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

# Execute multiple API calls simultaneously
workflow = WorkflowBuilder()
workflow.add_connection("data_source", ["api_call_1", "api_call_2", "api_call_3"])
workflow = WorkflowBuilder()
workflow.add_connection(["api_call_1", "api_call_2", "api_call_3"], "results_aggregator")

```

### Conditional API Routing
```python
# Route API calls based on response data
api_router = SwitchNode(
    name="api_router",
    condition_# mapping removed,
        "retry_path": "status_code in [429, 502, 503]",
        "error_path": "status_code >= 400"
    }
)

```

## Authentication Strategies

### API Key Authentication
```python
# API key in header
headers = {
    "X-API-Key": "your-api-key-here",
    "Content-Type": "application/json"
}

# API key in query parameter
url = "https://api.example.com/data?api_key=your-api-key-here"

```

### Bearer Token Authentication
```python
# JWT or OAuth bearer token
headers = {
    "Authorization": "Bearer your-jwt-token-here",
    "Accept": "application/json"
}

```

### OAuth 2.0 Flow
```python
def get_oauth_token(client_id, client_secret):
    """Implement OAuth 2.0 client credentials flow"""
    token_url = "https://oauth.example.com/token"

    auth_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }

    # Make token request
    token_response = requests.post(token_url, data=auth_data)
    token_data = token_response.json()

    return token_data.get("access_token")

```

## Error Handling and Resilience

### Rate Limiting
```python
def handle_rate_limiting(response_data):
    """Handle API rate limiting with exponential backoff"""
    status_code = response_data.get("status_code")

    if status_code == 429:  # Too Many Requests
        retry_after = response_data.get("headers", {}).get("Retry-After", "60")
        return {
            "should_retry": True,
            "retry_delay": int(retry_after),
            "error": "Rate limit exceeded"
        }

    return {"should_retry": False}

```

### Timeout and Retry Logic
```python
def api_call_with_retry(url, max_retries=3):
    """API call with retry logic for resilience"""
    for attempt in range(max_retries):
        try:
            response = make_api_call(url, timeout=10)
            if response.get("status_code") == 200:
                return response

        except TimeoutError:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff

    raise Exception(f"API call failed after {max_retries} attempts")

```

### Circuit Breaker Pattern
```python
class APICircuitBreaker:
    """Circuit breaker for API calls"""

    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call_api(self, api_function, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = api_function(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result

        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"

            raise e

```

## Integration with Enterprise Systems

### API Gateway Integration
- **AWS API Gateway**: Connect to enterprise API gateway
- **Kong**: Integrate with Kong API management platform
- **Azure API Management**: Use Azure APIM for API orchestration

### Message Queue Integration
- **Apache Kafka**: Publish API responses to Kafka topics
- **RabbitMQ**: Queue API calls for async processing
- **AWS SQS**: Use SQS for reliable API call queuing

### Database Integration
- **Cache API Responses**: Store responses in Redis/Memcached
- **Audit Logging**: Log all API calls to database
- **Data Warehousing**: ETL API data to data warehouse

## Performance Optimization

### Connection Pooling
```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session_with_pooling():
    """Create HTTP session with connection pooling"""
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"]
    )

    # Configure adapter with pooling
    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=retry_strategy
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

```

### Response Caching
```python
def cached_api_call(url, cache_duration=300):
    """API call with response caching"""
    cache_key = f"api_cache:{hash(url)}"

    # Check cache first
    cached_response = cache.get(cache_key)
    if cached_response:
        return cached_response

    # Make API call
    response = make_api_call(url)

    # Cache successful responses
    if response.get("status_code") == 200:
        cache.set(cache_key, response, timeout=cache_duration)

    return response

```

### Parallel Processing
```python
def process_api_calls_parallel(api_endpoints):
    """Process multiple API calls in parallel"""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {
            executor.submit(make_api_call, url): url
            for url in api_endpoints
        }

        results = {}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                results[url] = result
            except Exception as e:
                results[url] = {"error": str(e)}

        return results

```

## Common Use Cases

### Data Integration
- **CRM Integration**: Sync customer data with Salesforce, HubSpot
- **ERP Integration**: Connect with SAP, Oracle, NetSuite
- **Marketing Platforms**: Integrate with Mailchimp, Marketo, Pardot

### External Services
- **Payment Processing**: Stripe, PayPal, Square integration
- **Shipping Services**: UPS, FedEx, DHL tracking and shipping
- **Communication**: Twilio SMS, SendGrid email, Slack messaging

### Business Intelligence
- **Analytics Platforms**: Google Analytics, Adobe Analytics
- **Reporting Services**: Power BI, Tableau, Looker
- **Data Enrichment**: Clearbit, ZoomInfo, FullContact

## Advanced Patterns

### API Composition
```python
# Combine data from multiple APIs
def compose_user_profile(user_id):
    """Compose complete user profile from multiple APIs"""

    # Get basic user info
    user_basic = api_call(f"/users/{user_id}")

    # Get user's posts
    user_posts = api_call(f"/users/{user_id}/posts")

    # Get user's activity
    user_activity = api_call(f"/users/{user_id}/activity")

    # Compose complete profile
    return {
        "basic_info": user_basic["data"],
        "posts": user_posts["data"],
        "activity": user_activity["data"],
        "profile_completeness": calculate_completeness(user_basic, user_posts, user_activity)
    }

```

### Event-Driven API Integration
```python
# Trigger API calls based on events
event_processor = SwitchNode(
    name="event_processor",
    condition_# mapping removed,
        "order_placed": "event_type == 'order.placed'",
        "payment_received": "event_type == 'payment.received'"
    }
)

```

### API Versioning Management
```python
def handle_api_versioning(api_version="v1"):
    """Handle different API versions gracefully"""

    version_configs = {
        "v1": {
            "base_url": "https://api.example.com/v1",
            "auth_method": "api_key",
            "rate_limit": 1000
        },
        "v2": {
            "base_url": "https://api.example.com/v2",
            "auth_method": "oauth2",
            "rate_limit": 5000
        }
    }

    return version_configs.get(api_version, version_configs["v1"])

```

## Related Patterns

- **[Data Processing](../data-processing/)** - For processing API response data
- **[Monitoring](../monitoring/)** - For API performance monitoring
- **[Security](../security/)** - For API security and authentication

## Production Checklist

- [ ] All API calls use real endpoints (no mock responses)
- [ ] Authentication and authorization properly implemented
- [ ] Error handling covers timeouts, rate limits, and service failures
- [ ] Response data validation and transformation implemented
- [ ] API performance monitoring and alerting configured
- [ ] Security best practices for credential management
- [ ] Circuit breaker patterns for external dependency failures
- [ ] Comprehensive logging for API calls and responses
- [ ] Rate limiting and throttling compliance
- [ ] Data privacy and compliance requirements met

---

**Next Steps**:
- Review `scripts/rest_api_workflow.py` for implementation details
- Configure API integration for your specific external services
- Implement authentication and security for your API endpoints
- See the Kailash SDK repository for training examples
