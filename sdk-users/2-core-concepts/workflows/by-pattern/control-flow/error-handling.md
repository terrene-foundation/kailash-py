# Error Handling Patterns

**Resilient workflows with graceful error recovery** - Build fault-tolerant systems that handle failures intelligently.

## 📋 Pattern Overview

Error handling patterns ensure workflows can recover from failures, provide meaningful feedback, and maintain system stability. These patterns cover retry logic, fallback mechanisms, error aggregation, and compensation strategies for building production-ready workflows.

## 🚀 Working Examples

### Basic Try-Catch Pattern
**Script**: [scripts/error_handling_basic.py](scripts/error_handling_basic.py)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.api import RestClientNode
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime

def create_basic_error_handling():
    """Basic error handling with fallback."""
    workflow = WorkflowBuilder()

    # Primary API call
    api_call = RestClientNode(
        id="api_call",
        url="https://api.example.com/data",
        timeout=5000,
        retry_count=0  # Handle retries manually
    )
    workflow.add_node("api_call", api_call)

    # Error checker
    error_checker = PythonCodeNode(
        name="error_checker",
        code='''
# Check for various error conditions
api_response = api_result.get('response', {})
status_code = api_result.get('status_code', 0)
error_message = api_result.get('error', '')

error_info = {
    'has_error': False,
    'error_type': None,
    'error_message': None,
    'is_recoverable': True,
    'suggested_action': None
}

# Categorize errors
if status_code == 0 or error_message:
    error_info.update({
        'has_error': True,
        'error_type': 'network_error',
        'error_message': error_message or 'Connection failed',
        'is_recoverable': True,
        'suggested_action': 'retry'
    })
elif status_code == 429:
    error_info.update({
        'has_error': True,
        'error_type': 'rate_limit',
        'error_message': 'Rate limit exceeded',
        'is_recoverable': True,
        'suggested_action': 'backoff'
    })
elif status_code >= 500:
    error_info.update({
        'has_error': True,
        'error_type': 'server_error',
        'error_message': f'Server error: {status_code}',
        'is_recoverable': True,
        'suggested_action': 'retry'
    })
elif status_code >= 400:
    error_info.update({
        'has_error': True,
        'error_type': 'client_error',
        'error_message': f'Client error: {status_code}',
        'is_recoverable': False,
        'suggested_action': 'fix_request'
    })
elif status_code != 200:
    error_info.update({
        'has_error': True,
        'error_type': 'unexpected_status',
        'error_message': f'Unexpected status: {status_code}',
        'is_recoverable': False,
        'suggested_action': 'investigate'
    })

result = {
    'error_info': error_info,
    'original_response': api_response,
    'should_use_fallback': error_info['has_error']
}
'''
    )
    workflow.add_node("error_checker", error_checker)

    # Error router
    error_router = SwitchNode(
        id="error_router",
        condition="should_use_fallback == True"
    )
    workflow.add_node("error_router", error_router)

    # Fallback handler
    fallback_handler = PythonCodeNode(
        name="fallback_handler",
        code='''
# Provide fallback data based on error type
error_type = error_check_result['error_info']['error_type']
error_message = error_check_result['error_info']['error_message']

fallback_data = {
    'source': 'fallback',
    'timestamp': datetime.now().isoformat(),
    'reason': error_message,
    'data': []  # Default empty data
}

# Provide appropriate fallback based on error
if error_type == 'rate_limit':
    fallback_data['data'] = get_cached_data()  # Use cached version
    fallback_data['cache_age_minutes'] = 15
elif error_type in ['network_error', 'server_error']:
    fallback_data['data'] = get_default_data()  # Use defaults
    fallback_data['is_default'] = True
else:
    # For client errors, provide error details
    fallback_data['error_details'] = {
        'type': error_type,
        'message': error_message,
        'suggested_fix': error_check_result['error_info']['suggested_action']
    }

def get_cached_data():
    """Return cached data (simulated)."""
    return [
        {'id': 1, 'value': 100, 'cached': True},
        {'id': 2, 'value': 200, 'cached': True}
    ]

def get_default_data():
    """Return default data set."""
    return [
        {'id': 0, 'value': 0, 'default': True}
    ]

result = fallback_data
'''
    )
    workflow.add_node("fallback_handler", fallback_handler)

    # Success processor (for successful API calls)
    success_processor = DataTransformer(
        id="success_processor",
        transformations=[
            "lambda x: {'source': 'api', 'data': x.get('original_response', {}), 'success': True}"
        ]
    )
    workflow.add_node("success_processor", success_processor)

    # Connect error handling flow
    workflow.add_connection("api_call", "error_checker", "response", "api_result")
    workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
    workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
    workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping

    return workflow

```

### Retry with Exponential Backoff
**Script**: [scripts/error_handling_retry.py](scripts/error_handling_retry.py)

```python
def create_retry_pattern():
    """Sophisticated retry with exponential backoff and jitter."""
    workflow = WorkflowBuilder()

    # Retry coordinator
    retry_coordinator = PythonCodeNode(
        name="retry_coordinator",
        code='''
import time
import random

# Initialize or update retry state
if 'retry_state' not in globals():
    retry_state = {
        'attempt': 0,
        'max_attempts': 5,
        'base_delay': 1,  # Base delay in seconds
        'max_delay': 60,  # Maximum delay in seconds
        'total_elapsed': 0,
        'errors': []
    }

retry_state['attempt'] += 1

# Calculate delay with exponential backoff and jitter
if retry_state['attempt'] > 1:
    # Exponential backoff: delay = base * 2^(attempt-1)
    delay = retry_state['base_delay'] * (2 ** (retry_state['attempt'] - 2))

    # Cap at maximum delay
    delay = min(delay, retry_state['max_delay'])

    # Add jitter (±25%) to avoid thundering herd
    jitter = delay * 0.25 * (2 * random.random() - 1)
    delay = delay + jitter

    # Wait
    time.sleep(delay)
    retry_state['total_elapsed'] += delay
else:
    delay = 0

result = {
    'retry_state': retry_state,
    'current_attempt': retry_state['attempt'],
    'waited': delay,
    'should_continue': retry_state['attempt'] <= retry_state['max_attempts']
}
'''
    )
    workflow.add_node("retry_coordinator", retry_coordinator)

    # Operation to retry (e.g., API call)
    retryable_operation = RestClientNode(
        id="retryable_operation",
        url="https://flaky-api.example.com/data",
        timeout=5000
    )
    workflow.add_node("retryable_operation", retryable_operation)

    # Retry decision maker
    retry_decider = PythonCodeNode(
        name="retry_decider",
        code='''
# Analyze result and decide on retry
operation_result = operation_response.get('response', {})
status_code = operation_response.get('status_code', 0)
error = operation_response.get('error', '')

# Update retry state with error info
retry_info = retry_context['retry_state']
current_attempt = retry_context['current_attempt']

# Decision logic
should_retry = False
retry_reason = None

if status_code == 200:
    # Success - no retry needed
    should_retry = False
    retry_reason = 'success'
elif status_code == 429:  # Rate limit
    # Always retry rate limits if attempts remaining
    should_retry = current_attempt < retry_info['max_attempts']
    retry_reason = 'rate_limit'
    retry_info['errors'].append({
        'attempt': current_attempt,
        'error': 'rate_limit',
        'status': status_code
    })
elif status_code >= 500 or status_code == 0:  # Server error or network issue
    # Retry server errors and network issues
    should_retry = current_attempt < retry_info['max_attempts']
    retry_reason = 'server_error' if status_code >= 500 else 'network_error'
    retry_info['errors'].append({
        'attempt': current_attempt,
        'error': retry_reason,
        'status': status_code
    })
elif status_code >= 400:  # Client error
    # Don't retry client errors (except rate limits)
    should_retry = False
    retry_reason = 'client_error_no_retry'
else:
    # Unknown error - retry with caution
    should_retry = current_attempt < retry_info['max_attempts'] - 2  # More conservative
    retry_reason = 'unknown_error'

result = {
    'should_retry': should_retry,
    'retry_reason': retry_reason,
    'retry_state': retry_info,
    'final_result': operation_result if not should_retry else None,
    'success': status_code == 200
}
'''
    )
    workflow.add_node("retry_decider", retry_decider)

    # Connect retry loop
    workflow.add_connection("retry_coordinator", "retryable_operation", "result", "retry_context")
    workflow.add_connection("retryable_operation", "retry_decider", "response", "operation_response")

    return workflow

```

### Circuit Breaker Pattern
**Script**: [scripts/error_handling_circuit_breaker.py](scripts/error_handling_circuit_breaker.py)

```python
def create_circuit_breaker():
    """Circuit breaker to prevent cascade failures."""
    workflow = WorkflowBuilder()

    # Circuit breaker state manager
    circuit_breaker = PythonCodeNode(
        name="circuit_breaker",
        code='''
from datetime import datetime, timedelta
import json

# Circuit breaker states
CLOSED = 'closed'  # Normal operation
OPEN = 'open'      # Failing, reject requests
HALF_OPEN = 'half_open'  # Testing recovery

# Load or initialize circuit state
if 'circuit_state' not in globals():
    circuit_state = {
        'state': CLOSED,
        'failure_count': 0,
        'success_count': 0,
        'last_failure_time': None,
        'last_success_time': None,
        'last_state_change': datetime.now().isoformat()
    }

# Configuration
failure_threshold = 5  # Failures before opening
success_threshold = 3  # Successes to close from half-open
timeout_seconds = 30   # Time before trying half-open

current_time = datetime.now()
time_since_last_failure = timedelta(seconds=timeout_seconds + 1)  # Default to expired

if circuit_state['last_failure_time']:
    last_failure = datetime.fromisoformat(circuit_state['last_failure_time'])
    time_since_last_failure = current_time - last_failure

# State machine logic
allow_request = False
state_changed = False

if circuit_state['state'] == CLOSED:
    # Normal operation - allow request
    allow_request = True

    # Check if we should open circuit
    if circuit_state['failure_count'] >= failure_threshold:
        circuit_state['state'] = OPEN
        circuit_state['last_state_change'] = current_time.isoformat()
        state_changed = True
        allow_request = False  # Reject this request

elif circuit_state['state'] == OPEN:
    # Circuit is open - check timeout
    if time_since_last_failure > timedelta(seconds=timeout_seconds):
        # Try half-open
        circuit_state['state'] = HALF_OPEN
        circuit_state['last_state_change'] = current_time.isoformat()
        circuit_state['failure_count'] = 0
        circuit_state['success_count'] = 0
        state_changed = True
        allow_request = True  # Allow one test request
    else:
        # Still in timeout
        allow_request = False

elif circuit_state['state'] == HALF_OPEN:
    # Testing recovery - allow limited requests
    allow_request = True

    # Check if we should close (recovered) or open (still failing)
    if circuit_state['success_count'] >= success_threshold:
        # Recovery successful
        circuit_state['state'] = CLOSED
        circuit_state['failure_count'] = 0
        circuit_state['last_state_change'] = current_time.isoformat()
        state_changed = True
    elif circuit_state['failure_count'] > 0:
        # Still failing - reopen
        circuit_state['state'] = OPEN
        circuit_state['last_state_change'] = current_time.isoformat()
        state_changed = True
        allow_request = False

result = {
    'allow_request': allow_request,
    'circuit_state': circuit_state,
    'state_changed': state_changed,
    'rejection_reason': None if allow_request else f'Circuit breaker is {circuit_state["state"]}'
}
'''
    )
    workflow.add_node("circuit_breaker", circuit_breaker)

    # Request router based on circuit state
    request_router = SwitchNode(
        id="request_router",
        condition="allow_request == True"
    )
    workflow.add_node("request_router", request_router)

    # Protected operation
    protected_operation = RestClientNode(
        id="protected_operation",
        url="https://protected-service.example.com/api",
        timeout=3000
    )
    workflow.add_node("protected_operation", protected_operation)

    # Circuit breaker response handler
    response_handler = PythonCodeNode(
        name="response_handler",
        code='''
# Update circuit breaker based on response
operation_response = response_data.get('response', {})
status_code = response_data.get('status_code', 0)
circuit_info = breaker_state['circuit_state']

# Determine success/failure
is_success = status_code == 200
is_failure = status_code >= 500 or status_code == 0

# Update circuit state
if is_success:
    circuit_info['success_count'] += 1
    circuit_info['failure_count'] = 0  # Reset on success
    circuit_info['last_success_time'] = datetime.now().isoformat()
elif is_failure:
    circuit_info['failure_count'] += 1
    circuit_info['last_failure_time'] = datetime.now().isoformat()

# Prepare result
result = {
    'response': operation_response,
    'circuit_state': circuit_info,
    'request_successful': is_success,
    'circuit_status': {
        'state': circuit_info['state'],
        'health': 'healthy' if circuit_info['state'] == CLOSED else 'degraded',
        'consecutive_failures': circuit_info['failure_count']
    }
}
'''
    )
    workflow.add_node("response_handler", response_handler)

    # Fast fail response for circuit open
    fast_fail = PythonCodeNode(
        name="fast_fail",
        code='''
# Return cached/default response when circuit is open
result = {
    'response': {
        'source': 'circuit_breaker_cache',
        'data': get_cached_response(),
        'circuit_open': True
    },
    'circuit_state': breaker_state['circuit_state'],
    'request_successful': False,
    'circuit_status': {
        'state': breaker_state['circuit_state']['state'],
        'health': 'circuit_open',
        'message': breaker_state['rejection_reason']
    }
}

def get_cached_response():
    """Return cached or default data."""
    return {
        'cached': True,
        'data': [],
        'timestamp': datetime.now().isoformat()
    }
'''
    )
    workflow.add_node("fast_fail", fast_fail)

    # Connect circuit breaker flow
    workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
    workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
    workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
    workflow.add_connection("protected_operation", "response_handler", "response", "response_data")

    return workflow

```

### Error Aggregation and Reporting
**Script**: [scripts/error_handling_aggregation.py](scripts/error_handling_aggregation.py)

```python
def create_error_aggregation():
    """Aggregate errors from multiple sources for comprehensive reporting."""
    workflow = WorkflowBuilder()

    # Multiple operations that might fail
    operations = ["database", "api", "file_system", "cache"]

    # Create parallel operations
    for op in operations:
        if op == "database":
            node = SQLReaderNode(id=f"{op}_operation")
        elif op == "api":
            node = RestClientNode(id=f"{op}_operation")
        elif op == "file_system":
            node = CSVReaderNode(id=f"{op}_operation")
        else:  # cache
            node = PythonCodeNode(
                name=f"{op}_operation",
                code="result = {'data': read_from_cache()}"
            )

        workflow.add_node(f"{op}_operation", node)

    # Error collector for each operation
    for op in operations:
        error_collector = PythonCodeNode(
            name=f"{op}_error_collector",
            code=f'''
# Collect and categorize errors from {op}
operation_result = {op}_result
error_report = {{
    'source': '{op}',
    'timestamp': datetime.now().isoformat(),
    'has_error': False,
    'error_details': None,
    'severity': 'info',
    'impact': 'none',
    'recovery_action': None
}}

# Check for errors based on operation type
if '{op}' == 'database':
    if 'error' in operation_result or not operation_result.get('data'):
        error_report.update({{
            'has_error': True,
            'error_details': operation_result.get('error', 'Database query failed'),
            'severity': 'critical',
            'impact': 'data_unavailable',
            'recovery_action': 'retry_or_use_cache'
        }})
elif '{op}' == 'api':
    status_code = operation_result.get('status_code', 0)
    if status_code != 200:
        error_report.update({{
            'has_error': True,
            'error_details': f'API returned status {{status_code}}',
            'severity': 'high' if status_code >= 500 else 'medium',
            'impact': 'feature_degraded',
            'recovery_action': 'use_fallback_api'
        }})
elif '{op}' == 'file_system':
    if 'error' in operation_result:
        error_report.update({{
            'has_error': True,
            'error_details': operation_result.get('error', 'File read failed'),
            'severity': 'medium',
            'impact': 'batch_processing_delayed',
            'recovery_action': 'retry_later'
        }})
elif '{op}' == 'cache':
    if not operation_result.get('data'):
        error_report.update({{
            'has_error': True,
            'error_details': 'Cache miss or connection failed',
            'severity': 'low',
            'impact': 'performance_degraded',
            'recovery_action': 'fetch_from_source'
        }})

result = error_report
'''
        )
        workflow.add_node(f"{op}_error_collector", error_collector)
        workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern

    # Central error aggregator
    error_aggregator = PythonCodeNode(
        name="error_aggregator",
        code='''
# Aggregate all error reports
all_errors = []
critical_errors = []
degraded_services = []

# Collect from all sources
for source in ["database", "api", "file_system", "cache"]:
    error_report = globals().get(f'{source}_error_report', {})
    if error_report.get('has_error'):
        all_errors.append(error_report)

        if error_report['severity'] == 'critical':
            critical_errors.append(error_report)

        if error_report['impact'] != 'none':
            degraded_services.append({
                'service': error_report['source'],
                'impact': error_report['impact']
            })

# Calculate system health
total_services = 4
failed_services = len(all_errors)
critical_count = len(critical_errors)

if critical_count > 0:
    system_health = 'critical'
elif failed_services >= total_services / 2:
    system_health = 'degraded'
elif failed_services > 0:
    system_health = 'partial'
else:
    system_health = 'healthy'

# Generate action plan
action_plan = []
for error in all_errors:
    if error['recovery_action']:
        action_plan.append({
            'service': error['source'],
            'action': error['recovery_action'],
            'priority': 'immediate' if error['severity'] == 'critical' else 'normal'
        })

# Create comprehensive error report
result = {
    'system_health': system_health,
    'total_errors': len(all_errors),
    'critical_errors': critical_count,
    'errors_by_source': all_errors,
    'degraded_services': degraded_services,
    'action_plan': action_plan,
    'report_timestamp': datetime.now().isoformat(),
    'recommended_response': get_recommended_response(system_health)
}

def get_recommended_response(health):
    responses = {
        'healthy': 'Continue normal operation',
        'partial': 'Monitor closely, prepare fallbacks',
        'degraded': 'Activate fallback systems',
        'critical': 'Emergency protocols, notify on-call'
    }
    return responses.get(health, 'Unknown state')
'''
    )
    workflow.add_node("error_aggregator", error_aggregator)

    # Connect all error collectors to aggregator
    for op in operations:
        workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern

    return workflow

```

## 🎯 Common Use Cases

### 1. API Resilience
```python
# Retry transient failures
retry_config = {
    'max_attempts': 3,
    'backoff_multiplier': 2,
    'retry_on': [429, 500, 502, 503, 504]
}

```

### 2. Data Pipeline Recovery
```python
# Continue processing despite partial failures
error_handler = ErrorHandler(
    strategy='continue_on_error',
    log_errors=True,
    error_threshold=0.1  # Fail if >10% errors
)

```

### 3. Service Degradation
```python
# Graceful degradation
fallback_chain = [
    'primary_service',
    'secondary_service',
    'cache_lookup',
    'default_response'
]

```

### 4. Batch Processing
```python
# Handle individual item failures
batch_processor = BatchProcessor(
    continue_on_item_error=True,
    max_failed_items=100,
    error_file='failed_items.json'
)

```

## 📊 Best Practices

### 1. **Categorize Errors**
```python
# GOOD: Specific error handling
if status_code == 429:
    handle_rate_limit()
elif status_code >= 500:
    handle_server_error()
elif status_code >= 400:
    handle_client_error()

```

### 2. **Implement Timeouts**
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

# GOOD: Always set timeouts
api_call = RestClientNode(
    timeout=5000,  # 5 seconds
    connect_timeout=1000  # 1 second
)

```

### 3. **Log Comprehensively**
```python
# GOOD: Detailed error context
error_log = {
    'timestamp': datetime.now().isoformat(),
    'error_type': type(e).__name__,
    'error_message': str(e),
    'stack_trace': traceback.format_exc(),
    'context': {'user_id': user_id, 'request_id': request_id}
}

```

### 4. **Plan Recovery Strategies**
```python
# GOOD: Multiple recovery options
recovery_strategies = {
    'network_error': 'retry_with_backoff',
    'data_error': 'use_default_values',
    'auth_error': 'refresh_token',
    'unknown_error': 'fail_gracefully'
}

```

## 🔗 Related Examples

- **Examples Directory**: `/examples/workflow_examples/workflow_error_handling.py`
- **With Retries**: `/examples/workflow_examples/workflow_resilient.py`
- **Circuit Breaker**: See monitoring patterns
- **In Cycles**: See cyclic workflow error handling

## ⚠️ Common Pitfalls

1. **Catching Too Broadly**
   - Catch specific exceptions
   - Let unexpected errors propagate

2. **Infinite Retry Loops**
   - Always set maximum attempts
   - Implement backoff strategies

3. **Silent Failures**
   - Always log errors
   - Return meaningful error responses

4. **Resource Leaks**
   - Clean up in finally blocks
   - Close connections on error

---

*Robust error handling is essential for production workflows. Use these patterns to build resilient, self-healing systems.*
