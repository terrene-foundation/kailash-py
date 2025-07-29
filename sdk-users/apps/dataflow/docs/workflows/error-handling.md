# DataFlow Error Handling

Comprehensive guide to error handling in DataFlow workflows.

## Overview

DataFlow provides robust error handling mechanisms at multiple levels:
- Node-level error handling
- Workflow-level error recovery
- Transaction rollback on errors
- Custom error handlers
- Retry strategies

## Node-Level Error Handling

### Basic Error Handling

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Create user with potential error
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "invalid-email"  # Will fail validation
})

# Handle error
workflow.add_node("PythonCodeNode", "handle_error", {
    "code": """
error = get_input_data("create_user").get("error")
if error:
    result = {
        "error_type": error.get("type", "unknown"),
        "message": error.get("message", "Unknown error"),
        "action": "notify_admin"
    }
else:
    result = {"success": True}
"""
})

# Connect with error handling
workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern
```

### Validation Errors

```python
# Model with validation
@db.model
class User:
    name: str
    email: str
    age: int

    __dataflow__ = {
        'validators': [
            {'field': 'email', 'type': 'email'},
            {'field': 'age', 'type': 'range', 'min': 18, 'max': 120}
        ]
    }

# Handle validation errors
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "not-an-email",  # Will fail
    "age": 200  # Will fail
})

workflow.add_node("PythonCodeNode", "handle_validation", {
    "code": """
result = get_input_data("create_user")
if not result["success"]:
    validation_errors = result.get("validation_errors", [])
    for error in validation_errors:
        print(f"Field {error['field']}: {error['message']}")
    result = {"retry": False, "notify": True}
"""
})
```

## Workflow-Level Error Recovery

### Try-Catch Pattern

```python
workflow = WorkflowBuilder()

# Try block
workflow.add_node("TryNode", "try_block", {
    "nodes": ["risky_operation_1", "risky_operation_2"]
})

# Risky operations
workflow.add_node("ExternalAPINode", "risky_operation_1", {
    "url": "https://api.external.com/data",
    "timeout": 5.0
})

workflow.add_node("DatabaseNode", "risky_operation_2", {
    "query": "UPDATE users SET status = 'active' WHERE last_login > NOW() - INTERVAL '30 days'"
})

# Catch block
workflow.add_node("CatchNode", "catch_block", {
    "error_types": ["APIError", "DatabaseError"],
    "handler": "error_handler"
})

# Error handler
workflow.add_node("PythonCodeNode", "error_handler", {
    "code": """
error_info = get_input_data("_error")
error_type = error_info.get("type")
error_message = error_info.get("message")

# Log error
print(f"Error caught: {error_type} - {error_message}")

# Determine recovery action
if error_type == "APIError":
    result = {"action": "use_cache", "retry": True}
elif error_type == "DatabaseError":
    result = {"action": "rollback", "notify_dba": True}
else:
    result = {"action": "fail", "message": "Unrecoverable error"}
"""
})

# Finally block (always executes)
workflow.add_node("FinallyNode", "cleanup", {
    "actions": ["close_connections", "release_locks", "log_completion"]
})
```

### Circuit Breaker Pattern

```python
# Circuit breaker for external services
workflow.add_node("CircuitBreakerNode", "api_breaker", {
    "failure_threshold": 5,  # Open after 5 failures
    "timeout": 30.0,  # Try again after 30 seconds
    "half_open_requests": 1  # Test with 1 request when half-open
})

# Protected operation
workflow.add_node("ExternalAPINode", "call_api", {
    "url": "https://api.service.com/endpoint",
    "circuit_breaker": "api_breaker"
})

# Fallback when circuit is open
workflow.add_node("PythonCodeNode", "fallback_handler", {
    "code": """
if get_input_data("circuit_status") == "open":
    # Use cached data or default response
    result = {"data": get_cached_data(), "from_cache": True}
else:
    result = get_input_data("call_api")
"""
})
```

## Database Error Handling

### Transaction Rollback

```python
workflow = WorkflowBuilder()

# Start transaction
workflow.add_node("TransactionContextNode", "start_tx", {
    "isolation_level": "READ_COMMITTED"
})

# Database operations
workflow.add_node("UserCreateNode", "create_user", {
    "name": "New User",
    "email": "user@example.com"
})

workflow.add_node("AccountCreateNode", "create_account", {
    "user_id": ":user_id",
    "balance": -100.00  # Invalid: negative balance
})

# Error handler with rollback
workflow.add_node("TransactionRollbackNode", "rollback_tx", {
    "reason": ":error_message"
})

# Connect with error handling
workflow.add_connection("start_tx", "result", "create_user", "input")
workflow.add_connection("create_user", "create_account", "id", "user_id")
workflow.add_connection("create_account", "rollback_tx", on_error=True)
```

### Deadlock Handling

```python
# Automatic deadlock retry
workflow.add_node("TransactionContextNode", "tx_with_retry", {
    "deadlock_retry": True,
    "max_retries": 3,
    "retry_delay": 0.5  # exponential backoff
})

# Operations that might deadlock
workflow.add_node("AccountUpdateNode", "update_account_1", {
    "id": account_1_id,
    "balance": ":new_balance_1"
})

workflow.add_node("AccountUpdateNode", "update_account_2", {
    "id": account_2_id,
    "balance": ":new_balance_2"
})

# Handle persistent deadlock
workflow.add_node("PythonCodeNode", "handle_deadlock", {
    "code": """
if get_input_data("retry_count") >= 3:
    # Max retries reached
    result = {
        "action": "queue_for_later",
        "priority": "high",
        "reason": "Persistent deadlock"
    }
else:
    result = {"retry": True}
"""
})
```

## Retry Strategies

### Simple Retry

```python
# Retry failed operations
workflow.add_node("RetryNode", "retry_wrapper", {
    "target_node": "unreliable_operation",
    "max_attempts": 3,
    "delay": 1.0  # 1 second between attempts
})

workflow.add_node("HTTPRequestNode", "unreliable_operation", {
    "url": "https://flaky-api.com/data",
    "timeout": 5.0
})
```

### Exponential Backoff

```python
workflow.add_node("RetryNode", "smart_retry", {
    "target_node": "api_call",
    "max_attempts": 5,
    "backoff": "exponential",
    "initial_delay": 1.0,  # 1, 2, 4, 8, 16 seconds
    "max_delay": 30.0,
    "jitter": True  # Add randomness to prevent thundering herd
})
```

### Conditional Retry

```python
workflow.add_node("PythonCodeNode", "check_retry", {
    "code": """
error = get_input_data("error")
error_code = error.get("status_code", 0)

# Retry on specific errors
retryable_codes = [429, 502, 503, 504]  # Rate limit, gateway errors
if error_code in retryable_codes:
    result = {"should_retry": True, "delay": 5.0}
elif error_code == 401:  # Authentication error
    result = {"should_retry": True, "action": "refresh_token"}
else:
    result = {"should_retry": False, "action": "fail"}
"""
})

workflow.add_node("ConditionalRetryNode", "conditional_retry", {
    "target_node": "api_call",
    "condition_node": "check_retry",
    "max_attempts": 3
})
```

## Custom Error Handlers

### Global Error Handler

```python
# Define global error handler
@db.error_handler
def global_error_handler(error, context):
    """Handle all unhandled errors."""
    error_type = type(error).__name__

    # Log error
    logger.error(f"Unhandled error: {error_type}", exc_info=True)

    # Notify monitoring
    monitoring.alert({
        "error_type": error_type,
        "workflow_id": context.get("workflow_id"),
        "node_id": context.get("node_id"),
        "timestamp": datetime.utcnow()
    })

    # Determine action
    if error_type in ["DatabaseError", "OperationalError"]:
        return {"action": "retry", "delay": 5.0}
    elif error_type == "ValidationError":
        return {"action": "fail", "user_message": "Invalid input data"}
    else:
        return {"action": "fail", "user_message": "An error occurred"}
```

### Node-Specific Handlers

```python
# Custom error handler for specific node
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "test@example.com",
    "error_handler": "handle_user_error"
})

workflow.add_node("PythonCodeNode", "handle_user_error", {
    "code": """
error = get_input_data("_error")

# Check for duplicate email
if "duplicate key" in str(error):
    # Try to find existing user
    result = {
        "action": "find_existing",
        "email": get_input_data("email")
    }
elif "connection" in str(error):
    # Database connection error
    result = {
        "action": "retry",
        "delay": 10.0,
        "notify_ops": True
    }
else:
    # Unknown error
    result = {
        "action": "fail",
        "log_level": "error"
    }
"""
})
```

## Error Aggregation

### Bulk Operation Error Handling

```python
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "data": users_list,
    "continue_on_error": True,  # Don't stop on first error
    "error_threshold": 0.1  # Fail if >10% errors
})

workflow.add_node("PythonCodeNode", "process_bulk_errors", {
    "code": """
result = get_input_data("bulk_create")
errors = result.get("errors", [])

if errors:
    # Group errors by type
    error_groups = {}
    for error in errors:
        error_type = error.get("type", "unknown")
        if error_type not in error_groups:
            error_groups[error_type] = []
        error_groups[error_type].append(error)

    # Process each error type
    for error_type, error_list in error_groups.items():
        if error_type == "validation":
            # Save to error queue for manual review
            save_to_error_queue(error_list)
        elif error_type == "duplicate":
            # Update existing records
            update_existing_records(error_list)

    result = {
        "total_errors": len(errors),
        "error_groups": error_groups,
        "action": "partial_success"
    }
else:
    result = {"action": "complete_success"}
"""
})
```

## Error Monitoring

### Error Metrics

```python
workflow.add_node("ErrorMetricsNode", "track_errors", {
    "metrics": [
        "error_count",
        "error_rate",
        "error_types",
        "recovery_success_rate"
    ],
    "window": "5m",  # 5-minute window
    "alert_threshold": {
        "error_rate": 0.05,  # Alert if >5% error rate
        "error_count": 100   # Alert if >100 errors in window
    }
})
```

### Error Logging

```python
workflow.add_node("ErrorLoggingNode", "log_error", {
    "log_level": "error",
    "include_context": True,
    "include_stack_trace": True,
    "destinations": ["file", "elasticsearch", "sentry"],
    "sensitive_fields": ["password", "ssn", "credit_card"]  # Redact
})
```

## Best Practices

### 1. Fail Fast for Critical Errors

```python
# Don't retry critical errors
workflow.add_node("PythonCodeNode", "check_critical", {
    "code": """
error = get_input_data("error")
critical_errors = [
    "AuthenticationError",
    "PermissionDenied",
    "InvalidConfiguration"
]

if error.get("type") in critical_errors:
    result = {"action": "fail_immediately", "alert": True}
else:
    result = {"action": "retry"}
"""
})
```

### 2. Graceful Degradation

```python
# Provide fallback functionality
workflow.add_node("PythonCodeNode", "degraded_service", {
    "code": """
try:
    # Try primary service
    result = call_primary_service()
except ServiceUnavailable:
    # Fall back to secondary
    result = call_secondary_service()
except AllServicesDown:
    # Provide cached or default data
    result = get_cached_response()
    result["degraded"] = True
"""
})
```

### 3. Error Context Preservation

```python
# Preserve error context for debugging
workflow.add_node("ErrorContextNode", "capture_context", {
    "include": [
        "workflow_id",
        "node_id",
        "input_data",
        "timestamp",
        "user_id",
        "request_id"
    ],
    "sanitize": True  # Remove sensitive data
})
```

## Next Steps

- **Monitoring**: [Monitoring Guide](../advanced/monitoring.md)
- **Performance**: [Performance Guide](../production/performance.md)
- **Troubleshooting**: [Troubleshooting Guide](../production/troubleshooting.md)

Proper error handling is crucial for building resilient DataFlow applications. Implement appropriate strategies based on your use case and requirements.
