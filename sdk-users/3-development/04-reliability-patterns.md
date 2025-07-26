# Reliability Patterns - Rate Limiting, Retry & Circuit Breakers

*Build resilient workflows with production-grade reliability patterns*

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Completed [Production](04-production.md) - Core production patterns
- Understanding of resilience patterns

## Rate Limiting & Throttling

### Rate Limited API Calls

```python
from kailash.nodes.api import RateLimitedAPINode
from kailash.workflow.builder import WorkflowBuilder

# Configure rate-limited API node
workflow = WorkflowBuilder()

workflow.add_node("RateLimitedAPINode", "api_client", {
    "base_url": "https://api.example.com",
    "rate_limit_per_second": 10,     # Max 10 requests per second
    "rate_limit_per_minute": 100,    # Max 100 requests per minute
    "rate_limit_per_hour": 1000,     # Max 1000 requests per hour

    # Throttling behavior
    "throttle_strategy": "adaptive",  # adaptive, fixed, exponential
    "backoff_multiplier": 1.5,       # For exponential backoff
    "max_wait_time": 60.0,           # Maximum wait time in seconds

    # Queue management
    "queue_size": 1000,              # Max queued requests
    "queue_timeout": 300,            # Queue timeout in seconds
    "priority_queue": True,          # Enable priority-based processing

    # Error handling
    "retry_on_rate_limit": True,
    "max_retries": 3,
    "retry_delay": 5.0
})

# Execute rate-limited requests
result = await runtime.execute(workflow.build(), parameters={
    "api_client": {
        "requests": [
            {"endpoint": "/data/1", "priority": "high"},
            {"endpoint": "/data/2", "priority": "normal"},
            {"endpoint": "/data/3", "priority": "low"}
        ]
    }
})
```

### Custom Throttling Implementation

```python
import asyncio
import time
from collections import defaultdict
from typing import Dict, List

class ProductionRateLimiter:
    """Production-grade rate limiter with multiple time windows."""

    def __init__(self):
        self.requests = defaultdict(list)
        self.limits = {}

    def configure(self, client_id: str, limits: Dict[str, int]):
        """Configure rate limits for a client."""
        self.limits[client_id] = limits

    async def acquire(self, client_id: str, operation: str = "default") -> bool:
        """Acquire permission to make a request."""
        current_time = time.time()
        client_key = f"{client_id}:{operation}"

        # Clean old requests
        self.requests[client_key] = [
            req_time for req_time in self.requests[client_key]
            if current_time - req_time < 3600  # Keep last hour
        ]

        # Check all configured limits
        limits = self.limits.get(client_id, {})

        for window, max_requests in limits.items():
            window_seconds = self._parse_window(window)
            recent_requests = [
                req_time for req_time in self.requests[client_key]
                if current_time - req_time < window_seconds
            ]

            if len(recent_requests) >= max_requests:
                wait_time = window_seconds - (current_time - min(recent_requests))
                await asyncio.sleep(max(0, wait_time))

        # Record this request
        self.requests[client_key].append(current_time)
        return True

    def _parse_window(self, window: str) -> int:
        """Parse time window string to seconds."""
        if window.endswith('s'):
            return int(window[:-1])
        elif window.endswith('m'):
            return int(window[:-1]) * 60
        elif window.endswith('h'):
            return int(window[:-1]) * 3600
        return int(window)

# Use in workflow
def rate_limited_operation(data: List[Dict], client_id: str = "default") -> Dict:
    """Perform operations with rate limiting."""
    import asyncio

    async def process_with_limits():
        limiter = ProductionRateLimiter()
        limiter.configure(client_id, {
            "1s": 5,    # 5 requests per second
            "1m": 100,  # 100 requests per minute
            "1h": 1000  # 1000 requests per hour
        })

        results = []

        for item in data:
            await limiter.acquire(client_id, "api_call")

            try:
                # Your actual operation here
                result = {"id": item.get("id"), "processed": True}
                results.append(result)
            except Exception as e:
                results.append({"id": item.get("id"), "error": str(e)})

        return results

    # Run async operation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        processed_results = loop.run_until_complete(process_with_limits())
        return {
            "result": {
                "processed": processed_results,
                "total": len(data),
                "success_count": len([r for r in processed_results if "error" not in r])
            }
        }
    finally:
        loop.close()

# Use in workflow
from kailash.nodes.code import PythonCodeNode

rate_limited_processor = PythonCodeNode.from_function(
    name="rate_limited_processor",
    func=rate_limited_operation
)
```

## Retry Patterns & Backoff

### Exponential Backoff with Retry

```python
from typing import Optional, Dict, Any
import time
import random

def robust_external_call(
    endpoint: str,
    data: Dict[str, Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0
) -> Dict[str, Any]:
    """Make external API call with exponential backoff retry logic."""

    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            # Calculate delay with exponential backoff and jitter
            if attempt > 0:
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                # Add jitter to prevent thundering herd
                jitter = random.uniform(0, delay * 0.1)
                time.sleep(delay + jitter)

            # Your actual API call here
            # response = requests.post(endpoint, json=data)
            # response.raise_for_status()

            # Simulated success after retries
            if attempt == 0 and random.random() < 0.7:  # 70% chance of initial failure
                raise ConnectionError("Simulated connection error")

            return {
                'result': {'status': 'processed', 'data': data},
                'attempts': attempt + 1,
                'status': 'success'
            }

        except ConnectionError as e:
            last_error = e
            print(f"Connection failed (attempt {attempt + 1}/{max_retries}): {e}")

        except TimeoutError as e:
            last_error = e
            print(f"Request timeout (attempt {attempt + 1}/{max_retries}): {e}")

        except Exception as e:
            # Non-retryable error
            return {
                'result': None,
                'status': 'error',
                'error': str(e),
                'attempts': attempt + 1
            }

    # All retries exhausted
    return {
        'result': None,
        'status': 'error',
        'error': f"Failed after {max_retries} attempts: {str(last_error)}",
        'attempts': max_retries
    }

# Use in workflow
api_caller = PythonCodeNode.from_function(
    name="robust_api_caller",
    func=robust_external_call
)
```

### Retry Node with Circuit Breaker

```python
from kailash.nodes.resilience import RetryNode, CircuitBreakerNode
from kailash.workflow.builder import WorkflowBuilder

# Create resilient workflow with retry and circuit breaker
workflow = WorkflowBuilder()

# Add circuit breaker for external service
workflow.add_node("CircuitBreakerNode", "circuit_breaker", {
    "failure_threshold": 5,        # Open after 5 failures
    "recovery_timeout": 30,        # Wait 30s before trying half-open
    "error_rate_threshold": 0.5,   # Open at 50% error rate
    "min_calls": 10               # Minimum calls before calculating error rate
})

# Add retry logic
workflow.add_node("RetryNode", "retry_handler", {
    "max_attempts": 3,
    "base_delay": 1.0,             # Initial delay in seconds
    "max_delay": 10.0,             # Maximum delay in seconds
    "backoff_strategy": "exponential",  # exponential, linear, fixed
    "jitter": True,                # Add randomness to prevent thundering herd
    "retry_exceptions": [          # Only retry these exceptions
        "ConnectionError",
        "TimeoutError",
        "HTTPError"
    ]
})

# Add the actual operation
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://external-api.com/data",
    "method": "POST",
    "timeout": 30.0
})

# Connect with resilience patterns
workflow.add_connection("circuit_breaker", "retry_handler", "status", "circuit_status")
workflow.add_connection("retry_handler", "api_call", "execute", "trigger")
```

## Circuit Breaker Patterns

### Advanced Circuit Breaker Configuration

```python
from kailash.core.resilience.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig

# Setup circuit breaker for external services
cb_manager = CircuitBreakerManager()

# Configure different circuit breakers for different services
configs = {
    "external_api": CircuitBreakerConfig(
        failure_threshold=5,        # Open after 5 failures
        recovery_timeout=30,        # Wait 30s before trying half-open
        error_rate_threshold=0.5,   # Open at 50% error rate
        min_calls=10               # Minimum calls before calculating error rate
    ),
    "database": CircuitBreakerConfig(
        failure_threshold=3,        # More sensitive for DB
        recovery_timeout=60,        # Longer recovery for DB
        error_rate_threshold=0.3,   # Lower threshold for DB
        min_calls=5
    ),
    "cache": CircuitBreakerConfig(
        failure_threshold=10,       # Less sensitive for cache
        recovery_timeout=10,        # Quick recovery for cache
        error_rate_threshold=0.7,   # Higher threshold for cache
        min_calls=20
    )
}

# Create circuit breakers
circuit_breakers = {}
for service, config in configs.items():
    circuit_breakers[service] = cb_manager.get_or_create(service, config)

# Use circuit breaker with operations
async def protected_operation(service_name: str, operation_func, *args, **kwargs):
    """Execute operation with circuit breaker protection."""
    circuit_breaker = circuit_breakers.get(service_name)

    if not circuit_breaker:
        raise ValueError(f"No circuit breaker configured for service: {service_name}")

    try:
        result = await circuit_breaker.call(lambda: operation_func(*args, **kwargs))
        return {
            "status": "success",
            "result": result,
            "circuit_state": circuit_breaker.get_status()["state"]
        }
    except Exception as e:
        if "Circuit breaker is OPEN" in str(e):
            return {
                "status": "circuit_open",
                "error": "Service temporarily unavailable",
                "circuit_state": "OPEN",
                "retry_after": circuit_breaker.get_status().get("recovery_timeout", 30)
            }
        else:
            return {
                "status": "error",
                "error": str(e),
                "circuit_state": circuit_breaker.get_status()["state"]
            }

# Example usage in workflow function
def resilient_data_processor(data: List[Dict]) -> Dict:
    """Process data with circuit breaker protection."""
    import asyncio

    async def process_with_protection():
        results = []

        # Database operation with circuit breaker
        db_result = await protected_operation(
            "database",
            lambda: {"processed": len(data), "timestamp": time.time()}
        )

        if db_result["status"] == "success":
            results.append(db_result["result"])
        elif db_result["status"] == "circuit_open":
            # Fallback when circuit is open
            results.append({"fallback": True, "message": "Using cached data"})

        return {
            "results": results,
            "circuit_states": {
                name: cb.get_status()["state"]
                for name, cb in circuit_breakers.items()
            }
        }

    # Execute with circuit breaker protection
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        processed_results = loop.run_until_complete(process_with_protection())
        return {"result": processed_results}
    finally:
        loop.close()

# Create protected processor node
protected_processor = PythonCodeNode.from_function(
    name="protected_processor",
    func=resilient_data_processor
)
```

## Bulkhead Pattern

### Resource Isolation

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Callable

class BulkheadExecutor:
    """Isolate different types of operations to prevent cascade failures."""

    def __init__(self):
        self.executors = {}
        self.semaphores = {}

    def configure_bulkhead(self, operation_type: str, max_workers: int, max_concurrent: int):
        """Configure resource limits for operation type."""
        self.executors[operation_type] = ThreadPoolExecutor(max_workers=max_workers)
        self.semaphores[operation_type] = asyncio.Semaphore(max_concurrent)

    async def execute(self, operation_type: str, func: Callable, *args, **kwargs) -> Any:
        """Execute operation with bulkhead isolation."""
        if operation_type not in self.executors:
            raise ValueError(f"Bulkhead not configured for: {operation_type}")

        executor = self.executors[operation_type]
        semaphore = self.semaphores[operation_type]

        async with semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(executor, func, *args, **kwargs)

    def shutdown(self):
        """Shutdown all executors."""
        for executor in self.executors.values():
            executor.shutdown(wait=True)

# Use bulkhead pattern in workflow
def bulkhead_data_processor(data: List[Dict], config: Dict = None) -> Dict:
    """Process data with bulkhead isolation."""
    import asyncio

    async def process_with_bulkheads():
        # Configure bulkheads for different operation types
        bulkhead = BulkheadExecutor()
        bulkhead.configure_bulkhead("database", max_workers=5, max_concurrent=3)
        bulkhead.configure_bulkhead("api_calls", max_workers=10, max_concurrent=5)
        bulkhead.configure_bulkhead("file_ops", max_workers=3, max_concurrent=2)

        try:
            # Process different types of operations in isolation
            db_task = bulkhead.execute("database", lambda: len(data))
            api_task = bulkhead.execute("api_calls", lambda: {"status": "processed"})
            file_task = bulkhead.execute("file_ops", lambda: {"written": True})

            # Wait for all operations
            db_result = await db_task
            api_result = await api_task
            file_result = await file_task

            return {
                "database_result": db_result,
                "api_result": api_result,
                "file_result": file_result,
                "total_processed": len(data)
            }

        finally:
            bulkhead.shutdown()

    # Execute with bulkhead isolation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(process_with_bulkheads())
        return {"result": results}
    finally:
        loop.close()

# Create bulkhead processor node
bulkhead_processor = PythonCodeNode.from_function(
    name="bulkhead_processor",
    func=bulkhead_data_processor
)
```

## Timeout Patterns

### Adaptive Timeout Management

```python
import asyncio
import time
from statistics import mean, stdev

class AdaptiveTimeout:
    """Dynamically adjust timeouts based on response patterns."""

    def __init__(self, initial_timeout: float = 30.0):
        self.base_timeout = initial_timeout
        self.response_times = []
        self.max_history = 100

    def record_response_time(self, response_time: float):
        """Record a response time for timeout calculation."""
        self.response_times.append(response_time)
        if len(self.response_times) > self.max_history:
            self.response_times.pop(0)  # Remove oldest

    def get_adaptive_timeout(self) -> float:
        """Calculate adaptive timeout based on response history."""
        if len(self.response_times) < 5:
            return self.base_timeout

        avg_time = mean(self.response_times)
        std_time = stdev(self.response_times) if len(self.response_times) > 1 else 0

        # Set timeout to mean + 2 standard deviations, minimum base timeout
        adaptive_timeout = max(avg_time + (2 * std_time), self.base_timeout)

        # Cap at 5x base timeout to prevent excessive waits
        return min(adaptive_timeout, self.base_timeout * 5)

async def adaptive_timeout_operation(operation_func, timeout_manager: AdaptiveTimeout, *args, **kwargs):
    """Execute operation with adaptive timeout."""
    timeout = timeout_manager.get_adaptive_timeout()
    start_time = time.time()

    try:
        result = await asyncio.wait_for(operation_func(*args, **kwargs), timeout=timeout)
        response_time = time.time() - start_time
        timeout_manager.record_response_time(response_time)

        return {
            "status": "success",
            "result": result,
            "response_time": response_time,
            "timeout_used": timeout
        }

    except asyncio.TimeoutError:
        response_time = time.time() - start_time
        # Don't record timeout as normal response time
        return {
            "status": "timeout",
            "error": f"Operation timed out after {timeout:.2f}s",
            "timeout_used": timeout
        }

# Use adaptive timeout in workflow
def adaptive_timeout_processor(data: List[Dict]) -> Dict:
    """Process data with adaptive timeouts."""
    import asyncio

    async def process_with_adaptive_timeouts():
        timeout_manager = AdaptiveTimeout(initial_timeout=10.0)
        results = []

        for item in data:
            # Simulated async operation
            async def mock_operation():
                # Simulate variable response time
                await asyncio.sleep(random.uniform(1, 8))
                return {"processed": item.get("id", "unknown")}

            result = await adaptive_timeout_operation(mock_operation, timeout_manager)
            results.append(result)

        return {
            "results": results,
            "final_timeout": timeout_manager.get_adaptive_timeout(),
            "avg_response_time": mean(timeout_manager.response_times) if timeout_manager.response_times else 0
        }

    # Execute with adaptive timeouts
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        processed_results = loop.run_until_complete(process_with_adaptive_timeouts())
        return {"result": processed_results}
    finally:
        loop.close()

# Create adaptive timeout processor
adaptive_processor = PythonCodeNode.from_function(
    name="adaptive_timeout_processor",
    func=adaptive_timeout_processor
)
```

## Best Practices

### 1. Reliability Strategy

```python
# Comprehensive reliability configuration
reliability_config = {
    "rate_limiting": {
        "per_second": 10,
        "per_minute": 100,
        "per_hour": 1000,
        "strategy": "adaptive"
    },

    "circuit_breaker": {
        "failure_threshold": 5,
        "recovery_timeout": 30,
        "error_rate_threshold": 0.5
    },

    "retry": {
        "max_attempts": 3,
        "backoff_strategy": "exponential",
        "base_delay": 1.0,
        "max_delay": 10.0,
        "jitter": True
    },

    "timeout": {
        "base_timeout": 30.0,
        "adaptive": True,
        "max_timeout": 120.0
    }
}
```

### 2. Monitoring Integration

```python
# Monitor reliability patterns
def monitor_reliability_metrics(operation_name: str, result: Dict):
    """Monitor and log reliability metrics."""

    metrics = {
        "operation": operation_name,
        "timestamp": time.time(),
        "status": result.get("status"),
        "response_time": result.get("response_time", 0),
        "attempts": result.get("attempts", 1),
        "circuit_state": result.get("circuit_state", "unknown")
    }

    # Log to monitoring system
    print(f"RELIABILITY_METRIC: {json.dumps(metrics)}")

    # Alert on patterns
    if result.get("status") == "circuit_open":
        print(f"ALERT: Circuit breaker open for {operation_name}")

    if result.get("attempts", 1) > 2:
        print(f"WARNING: Multiple retries for {operation_name}")
```

### 3. Fallback Strategies

```python
def with_fallback(primary_func, fallback_func, *args, **kwargs):
    """Execute primary function with fallback on failure."""

    try:
        result = primary_func(*args, **kwargs)
        if result.get("status") in ["success"]:
            return result
    except Exception as e:
        print(f"Primary function failed: {e}")

    # Execute fallback
    try:
        fallback_result = fallback_func(*args, **kwargs)
        fallback_result["used_fallback"] = True
        return fallback_result
    except Exception as e:
        return {
            "status": "error",
            "error": f"Both primary and fallback failed: {str(e)}",
            "used_fallback": True
        }
```

## Related Guides

**Prerequisites:**
- [Production](04-production.md) - Core production patterns
- [Fundamentals](01-fundamentals.md) - Core SDK concepts
- [Workflows](02-workflows.md) - Basic patterns

**Next Steps:**
- [Streaming Patterns](04-streaming-patterns.md) - Real-time data processing
- [Troubleshooting](05-troubleshooting.md) - Debug reliability issues

---

**Build resilient workflows that gracefully handle failures and maintain performance under load!**
