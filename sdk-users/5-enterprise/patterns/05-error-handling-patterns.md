# Error Handling Patterns

Patterns for building resilient workflows that gracefully handle failures and recover from errors.

## 1. Circuit Breaker Pattern

**Purpose**: Prevent cascading failures by stopping calls to failing services

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.api import RESTClientNode
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Circuit breaker implementation
workflow.add_node("PythonCodeNode", "circuit_breaker", {}),
    code="""
import time
import json

# Initialize circuit breaker state
if not hasattr(self, '_state'):
    self._state = {
        'failures': 0,
        'last_failure': 0,
        'circuit_open': False,
        'success_count': 0,
        'last_success': 0
    }

# Configuration
failure_threshold = config.get('failure_threshold', 5)
timeout_seconds = config.get('timeout_seconds', 60)
success_threshold = config.get('success_threshold', 3)

current_time = time.time()

# Check if circuit should be reset
if self._state['circuit_open']:
    if current_time - self._state['last_failure'] > timeout_seconds:
        print("Circuit breaker: Attempting reset (half-open state)")
        self._state['circuit_open'] = False
        self._state['failures'] = 0
        self._state['success_count'] = 0
    else:
        # Circuit is still open
        time_remaining = timeout_seconds - (current_time - self._state['last_failure'])
        result = {
            'success': False,
            'circuit_status': 'open',
            'error': f'Circuit breaker is open. Retry in {time_remaining:.0f} seconds',
            'should_retry': False
        }
        return result

# Circuit is closed or half-open, attempt operation
try:
    # Call the actual service
    response = call_external_service(request_data)

    # Success - update state
    self._state['success_count'] += 1
    self._state['last_success'] = current_time

    # Reset failure count on success
    if self._state['success_count'] >= success_threshold:
        self._state['failures'] = 0
        self._state['circuit_open'] = False

    result = {
        'success': True,
        'circuit_status': 'closed',
        'response': response,
        'should_retry': False
    }

except Exception as e:
    # Failure - update state
    self._state['failures'] += 1
    self._state['last_failure'] = current_time
    self._state['success_count'] = 0

    # Check if we should open the circuit
    if self._state['failures'] >= failure_threshold:
        self._state['circuit_open'] = True
        print(f"Circuit breaker: Opening circuit after {self._state['failures']} failures")

    result = {
        'success': False,
        'circuit_status': 'open' if self._state['circuit_open'] else 'closed',
        'error': str(e),
        'failures': self._state['failures'],
        'should_retry': not self._state['circuit_open']
    }

# Log circuit breaker status
print(f"Circuit breaker status: {result['circuit_status']}, "
      f"Failures: {self._state['failures']}, "
      f"Successes: {self._state['success_count']}")

def call_external_service(data):
    # Simulate external service call
    import requests
    response = requests.post(
        config['service_url'],
        json=data,
        timeout=config.get('request_timeout', 5)
    )
    response.raise_for_status()
    return response.json()
""",
    imports=["time", "json", "requests"],
    config={
        "service_url": "https://api.example.com/process",
        "failure_threshold": 5,
        "timeout_seconds": 60,
        "success_threshold": 3,
        "request_timeout": 5
    }
)

# Route based on circuit breaker result
workflow.add_node("SwitchNode", "result_handler", {}),
    condition_field="should_retry",
    true_# route removed,
    false_# route removed)

workflow.add_connection("circuit_breaker", "result_handler", "result", "input")

```

## 2. Retry with Exponential Backoff

**Purpose**: Automatically retry failed operations with increasing delays

```python
workflow.add_node("PythonCodeNode", "retry_with_backoff", {}),
    code="""
import time
import random
import json

# Configuration
max_retries = config.get('max_retries', 3)
base_delay = config.get('base_delay', 1.0)
max_delay = config.get('max_delay', 60.0)
jitter_range = config.get('jitter_range', 0.1)

attempts = 0
last_error = None

while attempts < max_retries:
    try:
        # Attempt the operation
        print(f"Attempt {attempts + 1}/{max_retries}")

        # Your actual operation here
        result = perform_risky_operation(data)

        # Success! Return the result
        return {
            'success': True,
            'result': result,
            'attempts': attempts + 1,
            'total_retry_time': time.time() - start_time if attempts > 0 else 0
        }

    except Exception as e:
        last_error = e
        attempts += 1

        if attempts >= max_retries:
            # Max retries exceeded
            print(f"Max retries ({max_retries}) exceeded")
            break

        # Calculate delay with exponential backoff
        delay = min(base_delay * (2 ** (attempts - 1)), max_delay)

        # Add jitter to prevent thundering herd
        jitter = delay * random.uniform(-jitter_range, jitter_range)
        actual_delay = max(0, delay + jitter)

        print(f"Retry {attempts}/{max_retries} failed: {str(e)}")
        print(f"Waiting {actual_delay:.2f} seconds before retry...")

        time.sleep(actual_delay)

# All retries failed
result = {
    'success': False,
    'error': str(last_error),
    'attempts': attempts,
    'max_retries_exceeded': True
}

def perform_risky_operation(data):
    # Simulate operation that might fail
    import random
    if random.random() < 0.7:  # 70% failure rate for demo
        raise Exception("Simulated transient error")
    return {"processed": data}
""",
    imports=["time", "random", "json"],
    config={
        "max_retries": 5,
        "base_delay": 1.0,
        "max_delay": 30.0,
        "jitter_range": 0.1
    }
)

```

## 3. Fallback Pattern

**Purpose**: Provide alternative responses when primary service fails

```python
workflow = WorkflowBuilder()

# Primary service
workflow.add_node("RESTClientNode", "primary_service", {}),
    base_url="https://primary-api.example.com",
    endpoint="/process",
    method="POST",
    timeout=5
)

# Fallback service
workflow.add_node("RESTClientNode", "fallback_service", {}),
    base_url="https://backup-api.example.com",
    endpoint="/process",
    method="POST",
    timeout=10
)

# Cache fallback
workflow.add_node("PythonCodeNode", "cache_fallback", {}),
    code="""
import json
from datetime import datetime, timedelta

# Simple in-memory cache
if not hasattr(self, '_cache'):
    self._cache = {}

# Check cache for recent valid data
cache_key = json.dumps(request_data, sort_keys=True)
cached_entry = self._cache.get(cache_key, {})

if cached_entry:
    cached_time = datetime.fromisoformat(cached_entry['timestamp'])
    if datetime.now() - cached_time < timedelta(minutes=5):
        print("Returning cached response")
        result = {
            'source': 'cache',
            'data': cached_entry['data'],
            'cached_at': cached_entry['timestamp'],
            'success': True
        }
        return result

# Cache miss or expired
result = {
    'source': 'cache',
    'success': False,
    'error': 'No valid cached data available'
}
"""
)

# Static fallback
workflow.add_node("PythonCodeNode", "static_fallback", {}),
    code="""
# Return static/default response as last resort
print("WARNING: All services failed, returning static response")

result = {
    'source': 'static',
    'data': {
        'status': 'degraded',
        'message': 'Service temporarily unavailable',
        'default_values': {
            'processing_time': 'unknown',
            'confidence': 0.0
        }
    },
    'success': True,
    'degraded': True
}
"""
)

# Fallback orchestrator
workflow.add_node("PythonCodeNode", "fallback_orchestrator", {}),
    code="""
# Try services in order of preference
services = [
    {'name': 'primary', 'result': primary_result},
    {'name': 'fallback', 'result': fallback_result},
    {'name': 'cache', 'result': cache_result},
    {'name': 'static', 'result': static_result}
]

for service in services:
    if service['result'].get('success', False):
        print(f"Using response from: {service['name']}")
        result = {
            'final_source': service['name'],
            'response': service['result'],
            'services_tried': [s['name'] for s in services[:services.index(service)+1]],
            'degraded_mode': service['name'] != 'primary'
        }
        break
else:
    # This should not happen if static fallback is configured correctly
    result = {
        'error': 'All fallback options exhausted',
        'services_tried': [s['name'] for s in services]
    }
"""
)

# Connect with parallel execution for fallbacks
workflow.add_connection("request", "result", "primary_service", "input")
workflow.add_connection("request", "result", "fallback_service", "input")
workflow.add_connection("request", "result", "cache_fallback", "input")
workflow.add_connection("request", "result", "static_fallback", "input")

# Merge all results
workflow.add_node("MergeNode", "merger", {}))
workflow.add_connection("primary_service", "merger", "result", "data1")
workflow.add_connection("fallback_service", "merger", "result", "data2")
workflow.add_connection("cache_fallback", "merger", "result", "data3")
workflow.add_connection("static_fallback", "merger", "result", "data4")

workflow.add_connection("merger", "result", "fallback_orchestrator", "input")

```

## 4. Bulkhead Pattern

**Purpose**: Isolate failures to prevent system-wide impact

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

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "bulkhead_processor", {}),
    code="""
import concurrent.futures
import threading
import queue
import time

# Initialize bulkheads if not exists
if not hasattr(self, '_bulkheads'):
    self._bulkheads = {
        'critical': {
            'executor': concurrent.futures.ThreadPoolExecutor(max_workers=5),
            'semaphore': threading.Semaphore(5),
            'queue': queue.Queue(maxsize=10),
            'rejected_count': 0
        },
        'normal': {
            'executor': concurrent.futures.ThreadPoolExecutor(max_workers=10),
            'semaphore': threading.Semaphore(10),
            'queue': queue.Queue(maxsize=50),
            'rejected_count': 0
        },
        'batch': {
            'executor': concurrent.futures.ThreadPoolExecutor(max_workers=3),
            'semaphore': threading.Semaphore(3),
            'queue': queue.Queue(maxsize=100),
            'rejected_count': 0
        }
    }

# Determine bulkhead based on request priority
priority = request.get('priority', 'normal')
bulkhead = self._bulkheads.get(priority, self._bulkheads['normal'])

# Try to acquire semaphore (non-blocking)
if not bulkhead['semaphore'].acquire(blocking=False):
    # Bulkhead is full, try to queue
    try:
        bulkhead['queue'].put_nowait(request)
        bulkhead['rejected_count'] += 1
        result = {
            'status': 'queued',
            'queue_size': bulkhead['queue'].qsize(),
            'rejected_count': bulkhead['rejected_count'],
            'message': f'{priority} bulkhead is full, request queued'
        }
    except queue.Full:
        result = {
            'status': 'rejected',
            'error': f'{priority} bulkhead and queue are full',
            'rejected_count': bulkhead['rejected_count']
        }
    return result

try:
    # Process in isolated bulkhead
    future = bulkhead['executor'].submit(process_in_bulkhead, request, priority)
    result = future.result(timeout=config.get('timeout', 30))

finally:
    # Always release semaphore
    bulkhead['semaphore'].release()

def process_in_bulkhead(request, priority):
    # Simulate processing
    start_time = time.time()

    # Process based on priority
    if priority == 'critical':
        # Fast processing for critical requests
        time.sleep(0.1)
    elif priority == 'batch':
        # Slower processing for batch operations
        time.sleep(1.0)
    else:
        # Normal processing
        time.sleep(0.5)

    return {
        'processed': True,
        'priority': priority,
        'processing_time': time.time() - start_time
    }
"""
)

```

## 5. Dead Letter Queue Pattern

**Purpose**: Handle messages that cannot be processed successfully

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

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "dlq_handler", {}),
    code="""
import json
import datetime

# Initialize DLQ storage
if not hasattr(self, '_dlq'):
    self._dlq = []
    self._dlq_stats = {
        'total_messages': 0,
        'by_error_type': {},
        'by_source': {}
    }

# Configuration
max_dlq_size = config.get('max_dlq_size', 1000)
retry_after_minutes = config.get('retry_after_minutes', 60)

# Check if this is a retry or new failure
is_retry = message.get('retry_count', 0) > 0
max_retries = config.get('max_retries', 3)

if is_retry and message['retry_count'] >= max_retries:
    # Move to permanent DLQ
    dlq_entry = {
        'message': message['original_message'],
        'error': message['error'],
        'retry_count': message['retry_count'],
        'first_failure': message.get('first_failure', datetime.datetime.now().isoformat()),
        'last_failure': datetime.datetime.now().isoformat(),
        'permanent': True
    }

    # Add to DLQ with size limit
    if len(self._dlq) >= max_dlq_size:
        # Remove oldest entry
        self._dlq.pop(0)

    self._dlq.append(dlq_entry)
    self._dlq_stats['total_messages'] += 1

    # Track error types
    error_type = classify_error(message['error'])
    self._dlq_stats['by_error_type'][error_type] = \
        self._dlq_stats['by_error_type'].get(error_type, 0) + 1

    result = {
        'action': 'moved_to_dlq',
        'permanent': True,
        'dlq_size': len(self._dlq),
        'message_id': message.get('id'),
        'stats': self._dlq_stats
    }

else:
    # Schedule for retry
    retry_time = datetime.datetime.now() + datetime.timedelta(minutes=retry_after_minutes)

    retry_message = {
        'original_message': message.get('original_message', message),
        'error': message.get('error', 'Unknown error'),
        'retry_count': message.get('retry_count', 0) + 1,
        'first_failure': message.get('first_failure', datetime.datetime.now().isoformat()),
        'retry_after': retry_time.isoformat()
    }

    result = {
        'action': 'scheduled_retry',
        'retry_count': retry_message['retry_count'],
        'retry_after': retry_message['retry_after'],
        'message': retry_message
    }

# Periodic DLQ analysis
if len(self._dlq) % 10 == 0:
    analyze_dlq_patterns()

def classify_error(error_msg):
    error_str = str(error_msg).lower()
    if 'timeout' in error_str:
        return 'timeout'
    elif 'connection' in error_str:
        return 'connection'
    elif 'validation' in error_str:
        return 'validation'
    elif 'authorization' in error_str:
        return 'auth'
    else:
        return 'other'

def analyze_dlq_patterns():
    # Identify common failure patterns
    print(f"DLQ Analysis: {len(self._dlq)} messages")
    print(f"Error types: {json.dumps(self._dlq_stats['by_error_type'], indent=2)}")
"""
)

```

## 6. Compensation Pattern

**Purpose**: Undo or compensate for failed operations in distributed transactions

```python
workflow.add_node("PythonCodeNode", "compensation_handler", {}),
    code="""
# Track operations for potential compensation
operations_log = []

try:
    # Step 1: Create order
    order_result = create_order(order_data)
    operations_log.append({
        'operation': 'create_order',
        'result': order_result,
        'compensate': lambda: cancel_order(order_result['order_id'])
    })

    # Step 2: Reserve inventory
    inventory_result = reserve_inventory(order_result['order_id'], items)
    operations_log.append({
        'operation': 'reserve_inventory',
        'result': inventory_result,
        'compensate': lambda: release_inventory(inventory_result['reservation_id'])
    })

    # Step 3: Process payment
    payment_result = process_payment(payment_info, order_result['total'])
    operations_log.append({
        'operation': 'process_payment',
        'result': payment_result,
        'compensate': lambda: refund_payment(payment_result['transaction_id'])
    })

    # All operations succeeded
    result = {
        'success': True,
        'order_id': order_result['order_id'],
        'operations': [op['operation'] for op in operations_log]
    }

except Exception as e:
    # Operation failed - compensate in reverse order
    print(f"Operation failed: {str(e)}")
    print("Starting compensation...")

    failed_compensations = []

    # Compensate in reverse order
    for operation in reversed(operations_log):
        try:
            print(f"Compensating: {operation['operation']}")
            operation['compensate']()
        except Exception as comp_error:
            failed_compensations.append({
                'operation': operation['operation'],
                'error': str(comp_error)
            })

    result = {
        'success': False,
        'error': str(e),
        'compensated_operations': [op['operation'] for op in reversed(operations_log)],
        'failed_compensations': failed_compensations
    }

# Simulated operations
def create_order(data):
    return {'order_id': 'ORD-123', 'status': 'created'}

def reserve_inventory(order_id, items):
    return {'reservation_id': 'RES-456', 'items_reserved': len(items)}

def process_payment(payment_info, amount):
    return {'transaction_id': 'TXN-789', 'amount': amount}

def cancel_order(order_id):
    print(f"Cancelled order: {order_id}")

def release_inventory(reservation_id):
    print(f"Released inventory: {reservation_id}")

def refund_payment(transaction_id):
    print(f"Refunded payment: {transaction_id}")
"""
)

```

## Best Practices

1. **Error Classification**:
   - Distinguish between transient and permanent errors
   - Handle different error types appropriately
   - Log all errors with sufficient context

2. **Retry Strategy**:
   - Use exponential backoff to avoid overwhelming services
   - Set reasonable maximum retry limits
   - Add jitter to prevent thundering herd

3. **Circuit Breaker Configuration**:
   - Set appropriate failure thresholds
   - Use reasonable timeout periods
   - Monitor circuit breaker state

4. **Fallback Design**:
   - Order fallbacks from best to worst option
   - Ensure the last fallback always succeeds
   - Mark degraded responses appropriately

5. **Monitoring & Alerting**:
   - Track error rates and patterns
   - Alert on circuit breaker state changes
   - Monitor DLQ size and growth rate

## See Also
- [Integration Patterns](04-integration-patterns.md) - External service connections
- [Performance Patterns](06-performance-patterns.md) - Optimization techniques
- [Security Patterns](10-security-patterns.md) - Secure error handling
