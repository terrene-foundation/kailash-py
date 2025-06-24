"""
AsyncPatterns - Common async workflow patterns for the AsyncWorkflowBuilder.

This module provides reusable patterns for common async scenarios like
retry with backoff, rate limiting, timeout with fallback, and batch processing.
"""

from typing import Any, Callable, Dict, List, Optional, Union

from .async_builder import AsyncWorkflowBuilder


class AsyncPatterns:
    """Common async workflow patterns."""

    @staticmethod
    def retry_with_backoff(
        builder: AsyncWorkflowBuilder,
        node_id: str,
        operation_code: str,
        *,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        backoff_factor: float = 2.0,
        max_backoff: float = 60.0,
        retry_on: List[str] = None,
        description: str = None,
    ) -> AsyncWorkflowBuilder:
        """Add node with exponential backoff retry logic."""
        # Build retry exception list
        if retry_on:
            exception_checks = " or ".join(f"isinstance(e, {exc})" for exc in retry_on)
        else:
            exception_checks = "True"  # Retry on any exception

        # Indent the operation code properly
        indented_operation = "\n".join(
            f"        {line}" if line.strip() else ""
            for line in operation_code.strip().split("\n")
        )

        code = f"""
import asyncio
import random
import time

max_retries = {max_retries}
initial_backoff = {initial_backoff}
backoff_factor = {backoff_factor}
max_backoff = {max_backoff}

result = None
last_error = None
attempts = []

for attempt in range(max_retries):
    attempt_start = time.time()
    try:
        # Attempt operation
{indented_operation}

        # Record successful attempt
        attempts.append({{
            "attempt": attempt + 1,
            "success": True,
            "duration": time.time() - attempt_start
        }})
        break  # Success, exit retry loop

    except Exception as e:
        last_error = e

        # Check if we should retry this exception
        should_retry = {exception_checks}

        if not should_retry:
            # Don't retry this exception type
            raise

        # Record failed attempt
        attempts.append({{
            "attempt": attempt + 1,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "duration": time.time() - attempt_start
        }})

        if attempt == max_retries - 1:
            # Final attempt failed
            result = {{
                "success": False,
                "error": str(last_error),
                "error_type": type(last_error).__name__,
                "attempts": attempts,
                "total_attempts": len(attempts)
            }}
            raise RuntimeError(f"Operation failed after {{max_retries}} attempts: {{last_error}}")
        else:
            # Calculate backoff with jitter
            backoff = min(
                initial_backoff * (backoff_factor ** attempt) + random.uniform(0, 1),
                max_backoff
            )
            await asyncio.sleep(backoff)

# If we get here, operation succeeded
# Merge retry metadata with user result
if result is None:
    result = {{}}
elif not isinstance(result, dict):
    result = {{"value": result}}

# Always add retry metadata
result["success"] = True
result["attempts"] = attempts
result["total_attempts"] = len(attempts)
"""

        return builder.add_async_code(
            node_id,
            code,
            description=description
            or f"Retry operation with exponential backoff (max {max_retries} attempts)",
        )

    @staticmethod
    def rate_limited(
        builder: AsyncWorkflowBuilder,
        node_id: str,
        operation_code: str,
        *,
        requests_per_second: float = 10,
        burst_size: int = None,
        description: str = None,
    ) -> AsyncWorkflowBuilder:
        """Add node with rate limiting using token bucket algorithm."""
        if burst_size is None:
            burst_size = int(requests_per_second * 2)

        # Indent the operation code properly
        indented_operation = "\n".join(
            f"{line}" if line.strip() else ""
            for line in operation_code.strip().split("\n")
        )

        code = f"""
import asyncio
import time
from collections import deque

# Rate limiting configuration
requests_per_second = {requests_per_second}
burst_size = {burst_size}
min_interval = 1.0 / requests_per_second

# Initialize rate limiter state (global for persistence across calls)
if '_rate_limiter_state' not in globals():
    globals()['_rate_limiter_state'] = {{
        'tokens': burst_size,
        'last_update': time.time(),
        'request_times': deque(maxlen=100)
    }}

state = globals()['_rate_limiter_state']

# Update tokens based on time passed
current_time = time.time()
time_passed = current_time - state['last_update']
state['tokens'] = min(burst_size, state['tokens'] + time_passed * requests_per_second)
state['last_update'] = current_time

# Wait if no tokens available
while state['tokens'] < 1:
    wait_time = (1 - state['tokens']) / requests_per_second
    await asyncio.sleep(wait_time)

    # Update tokens again
    current_time = time.time()
    time_passed = current_time - state['last_update']
    state['tokens'] = min(burst_size, state['tokens'] + time_passed * requests_per_second)
    state['last_update'] = current_time

# Consume a token
state['tokens'] -= 1
state['request_times'].append(current_time)

# Execute operation
operation_start = time.time()
{indented_operation}
operation_duration = time.time() - operation_start

# Add rate limiting info to result
if isinstance(result, dict):
    result['_rate_limit_info'] = {{
        'tokens_remaining': state['tokens'],
        'requests_in_window': len([t for t in state['request_times'] if current_time - t < 1]),
        'operation_duration': operation_duration
    }}
"""

        return builder.add_async_code(
            node_id,
            code,
            description=description
            or f"Rate-limited operation ({requests_per_second} req/s)",
        )

    @staticmethod
    def timeout_with_fallback(
        builder: AsyncWorkflowBuilder,
        primary_node_id: str,
        fallback_node_id: str,
        primary_code: str,
        fallback_code: str,
        *,
        timeout_seconds: float = 5.0,
        description: str = None,
    ) -> AsyncWorkflowBuilder:
        """Add primary operation with timeout and fallback."""
        # Indent the primary code properly
        indented_primary = "\n".join(
            f"        {line}" if line.strip() else ""
            for line in primary_code.strip().split("\n")
        )

        # Primary node with timeout
        primary_with_timeout = f"""
import asyncio

try:
    # Run primary operation with timeout
    async def primary_operation():
{indented_primary}
        return result

    result = await asyncio.wait_for(primary_operation(), timeout={timeout_seconds})
    if isinstance(result, dict):
        result['_source'] = 'primary'
    else:
        result = {{"value": result, "_source": "primary"}}

except asyncio.TimeoutError:
    # Primary timed out, will use fallback
    result = {{
        "_timeout": True,
        "_source": "timeout",
        "_timeout_seconds": {timeout_seconds}
    }}
except Exception as e:
    # Primary failed with error
    result = {{
        "_error": True,
        "_source": "error",
        "_error_message": str(e),
        "_error_type": type(e).__name__
    }}
"""

        builder.add_async_code(
            primary_node_id,
            primary_with_timeout,
            timeout=int(timeout_seconds) + 5,  # Add buffer to node timeout
            description=f"Primary operation with {timeout_seconds}s timeout",
        )

        # Indent the fallback code properly
        indented_fallback = "\n".join(
            f"    {line}" if line.strip() else ""
            for line in fallback_code.strip().split("\n")
        )

        # Fallback node
        fallback_with_check = f"""
# Check if we need fallback
primary_failed = False
if isinstance(primary_result, dict):
    primary_failed = primary_result.get("_timeout", False) or primary_result.get("_error", False)

if primary_failed:
    # Execute fallback
{indented_fallback}
    if isinstance(result, dict):
        result['_source'] = 'fallback'
        result['_primary_timeout'] = primary_result.get("_timeout", False)
        result['_primary_error'] = primary_result.get("_error", False)
    else:
        result = {{
            "value": result,
            "_source": "fallback",
            "_primary_timeout": primary_result.get("_timeout", False),
            "_primary_error": primary_result.get("_error", False)
        }}
else:
    # Primary succeeded, pass through
    result = primary_result
"""

        builder.add_async_code(
            fallback_node_id, fallback_with_check, description="Fallback operation"
        )

        # Connect primary to fallback
        builder.add_connection(
            primary_node_id, "result", fallback_node_id, "primary_result"
        )

        return builder

    @staticmethod
    def batch_processor(
        builder: AsyncWorkflowBuilder,
        node_id: str,
        process_batch_code: str,
        *,
        batch_size: int = 100,
        flush_interval: float = 5.0,
        description: str = None,
    ) -> AsyncWorkflowBuilder:
        """Add batch processing node with time-based flushing."""
        # Indent the process batch code properly
        indented_batch_code = "\n".join(
            f"    {line}" if line.strip() else ""
            for line in process_batch_code.strip().split("\n")
        )

        code = f"""
import asyncio
import time
from typing import List

# Batch configuration
batch_size = {batch_size}
flush_interval = {flush_interval}

# Initialize batch state (global for persistence)
if '_batch_state' not in globals():
    globals()['_batch_state'] = {{
        'items': [],
        'last_flush': time.time()
    }}

batch_state = globals()['_batch_state']

# Add items to batch
new_items = items if 'items' in locals() else []
if isinstance(new_items, (list, tuple)):
    batch_state['items'].extend(new_items)
elif new_items is not None:
    batch_state['items'].append(new_items)

# Check if we should process batch
should_process = False
reason = None

if len(batch_state['items']) >= batch_size:
    should_process = True
    reason = "batch_full"
elif time.time() - batch_state['last_flush'] >= flush_interval and batch_state['items']:
    should_process = True
    reason = "time_based"
elif locals().get('force_flush', False) and batch_state['items']:  # Allow forced flush
    should_process = True
    reason = "forced"

results = []
if should_process:
    # Process batch
    batch_to_process = batch_state['items'][:batch_size]
    remaining_items = batch_state['items'][batch_size:]

    # User-defined batch processing
    items = batch_to_process  # Make available to process code
{indented_batch_code}

    # Update state
    batch_state['items'] = remaining_items
    batch_state['last_flush'] = time.time()

    # Results should be set by process_batch_code
    if 'batch_results' in locals():
        results = batch_results

result = {{
    "processed_count": len(results),
    "results": results,
    "remaining_in_batch": len(batch_state['items']),
    "flush_reason": reason,
    "next_flush_in": max(0, flush_interval - (time.time() - batch_state['last_flush']))
}}
"""

        return builder.add_async_code(
            node_id,
            code,
            description=description
            or f"Batch processor (size={batch_size}, interval={flush_interval}s)",
        )

    @staticmethod
    def circuit_breaker(
        builder: AsyncWorkflowBuilder,
        node_id: str,
        operation_code: str,
        *,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        description: str = None,
    ) -> AsyncWorkflowBuilder:
        """Add circuit breaker pattern for fault tolerance."""
        # Indent the operation code properly
        indented_operation = "\n".join(
            f"        {line}" if line.strip() else ""
            for line in operation_code.strip().split("\n")
        )

        code = f"""
import time

# Use string constants instead of Enum to avoid __build_class__ issues
CIRCUIT_CLOSED = "closed"
CIRCUIT_OPEN = "open"
CIRCUIT_HALF_OPEN = "half_open"

# Initialize circuit breaker state
if '_circuit_breaker_state' not in globals():
    globals()['_circuit_breaker_state'] = {{
        'state': CIRCUIT_CLOSED,
        'failure_count': 0,
        'last_failure_time': None,
        'success_count': 0
    }}

cb_state = globals()['_circuit_breaker_state']
failure_threshold = {failure_threshold}
reset_timeout = {reset_timeout}

# Check if we should attempt reset
current_time = time.time()
if (cb_state['state'] == CIRCUIT_OPEN and
    cb_state['last_failure_time'] and
    current_time - cb_state['last_failure_time'] >= reset_timeout):
    cb_state['state'] = CIRCUIT_HALF_OPEN
    cb_state['success_count'] = 0

# Handle circuit breaker states
if cb_state['state'] == CIRCUIT_OPEN:
    result = {{
        "success": False,
        "error": "Circuit breaker is OPEN",
        "circuit_state": cb_state['state'],
        "failure_count": cb_state['failure_count'],
        "time_until_retry": reset_timeout - (current_time - cb_state['last_failure_time']) if cb_state['last_failure_time'] else 0
    }}
else:
    try:
        # Execute operation
        operation_start = time.time()
{indented_operation}
        operation_duration = time.time() - operation_start

        # Operation succeeded
        cb_state['failure_count'] = 0
        if cb_state['state'] == CIRCUIT_HALF_OPEN:
            cb_state['success_count'] += 1
            if cb_state['success_count'] >= 3:  # Require multiple successes to fully close
                cb_state['state'] = CIRCUIT_CLOSED

        # Add circuit breaker info to result
        if isinstance(result, dict):
            result['_circuit_breaker_info'] = {{
                'state': cb_state['state'],
                'failure_count': cb_state['failure_count'],
                'operation_duration': operation_duration
            }}

    except Exception as e:
        # Operation failed
        cb_state['failure_count'] += 1
        cb_state['last_failure_time'] = current_time

        if cb_state['failure_count'] >= failure_threshold:
            cb_state['state'] = CIRCUIT_OPEN

        result = {{
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "circuit_state": cb_state['state'],
            "failure_count": cb_state['failure_count']
        }}

        # Re-raise the exception unless circuit is now open
        if cb_state['state'] != CIRCUIT_OPEN:
            raise
"""

        return builder.add_async_code(
            node_id,
            code,
            description=description
            or f"Circuit breaker protected operation (threshold={failure_threshold})",
        )

    @staticmethod
    def parallel_fetch(
        builder: AsyncWorkflowBuilder,
        node_id: str,
        fetch_operations: Dict[str, str],
        *,
        timeout_per_operation: float = 10.0,
        continue_on_error: bool = True,
        description: str = None,
    ) -> AsyncWorkflowBuilder:
        """Add node that performs multiple async operations in parallel."""
        # Build the fetch operations
        operations = []
        for key, operation_code in fetch_operations.items():
            # Indent the operation code properly
            indented_op_code = "\n".join(
                f"        {line}" if line.strip() else ""
                for line in operation_code.strip().split("\n")
            )
            operations.append(
                f"""
async def fetch_{key}():
    try:
{indented_op_code}
        return ("{key}", True, result, None)
    except Exception as e:
        return ("{key}", False, None, str(e))
"""
            )

        code = f"""
import asyncio

# Define all fetch operations
{chr(10).join(operations)}

# Get all fetch functions
fetch_functions = []
local_vars = list(locals().keys())  # Create a copy to avoid modification during iteration
for name in local_vars:
    if name.startswith('fetch_') and callable(locals().get(name)):
        fetch_functions.append(locals()[name])

# Execute all operations in parallel with timeout
try:
    results = await asyncio.wait_for(
        asyncio.gather(*[func() for func in fetch_functions]),
        timeout={timeout_per_operation}
    )
except asyncio.TimeoutError:
    # Handle timeout
    results = [(f"operation_{{i}}", False, None, "timeout") for i in range(len(fetch_functions))]

# Process results
successful = {{}}
failed = {{}}

for key, success, data, error in results:
    if success:
        successful[key] = data
    else:
        failed[key] = error

# Check if we should fail on any errors
if not {continue_on_error} and failed:
    raise RuntimeError(f"{{len(failed)}} operations failed: {{list(failed.keys())}}")

result = {{
    "successful": successful,
    "failed": failed,
    "statistics": {{
        "total_operations": len(results),
        "successful_count": len(successful),
        "failed_count": len(failed),
        "success_rate": len(successful) / len(results) if results else 0
    }}
}}
"""

        return builder.add_async_code(
            node_id,
            code,
            timeout=int(timeout_per_operation) + 10,
            description=description
            or f"Parallel fetch of {len(fetch_operations)} operations",
        )

    @staticmethod
    def cache_aside(
        builder: AsyncWorkflowBuilder,
        cache_check_id: str,
        data_fetch_id: str,
        cache_store_id: str,
        fetch_code: str,
        *,
        cache_resource: str = "cache",
        cache_key_template: str = "key_{item_id}",
        ttl_seconds: int = 3600,
        description: str = None,
    ) -> AsyncWorkflowBuilder:
        """Add cache-aside pattern with cache check, fetch, and store."""

        # Cache check node
        builder.add_async_code(
            cache_check_id,
            f"""
import json

# Get cache resource
if 'get_resource' in globals():
    cache = await get_resource("{cache_resource}")
else:
    # Fallback for testing
    cache = locals().get("{cache_resource}")
    if cache is None:
        raise RuntimeError(f"Cache resource '{cache_resource}' not available")

# Get variables for cache key generation
cache_key_vars = {{k: v for k, v in locals().items() if not k.startswith('_')}}
# Generate cache key
cache_key = "{cache_key_template}".format(**cache_key_vars)

# Try to get from cache
try:
    cached_data = await cache.get(cache_key)
    if cached_data:
        if isinstance(cached_data, (str, bytes)):
            try:
                data = json.loads(cached_data)
            except (json.JSONDecodeError, TypeError):
                data = cached_data
        else:
            data = cached_data

        result = {{
            "found_in_cache": True,
            "cache_key": cache_key,
            "data": data
        }}
    else:
        result = {{
            "found_in_cache": False,
            "cache_key": cache_key,
            "data": None
        }}
except Exception as e:
    # Cache error, proceed without cache
    result = {{
        "found_in_cache": False,
        "cache_key": cache_key,
        "data": None,
        "cache_error": str(e)
    }}
""",
            required_resources=[cache_resource],
            description="Check cache for existing data",
        )

        # Data fetch node (only runs if cache miss)
        # Indent the fetch code properly
        indented_fetch = "\n".join(
            f"    {line}" if line.strip() else ""
            for line in fetch_code.strip().split("\n")
        )

        builder.add_async_code(
            data_fetch_id,
            f"""
# Only fetch if not found in cache
if not cache_result.get("found_in_cache", False):
    # Get all variables that were passed to cache_check (like item_id)
    # Extract them from cache_key if needed
    cache_key = cache_result.get("cache_key", "")

    # Try to extract variables from the cache key
    # This is a simple approach - in production you'd want more robust parsing
    import re
    matches = re.findall(r'(\\d+)', cache_key)
    if matches and 'item_id' not in locals():
        item_id = int(matches[0])

    # Execute fetch operation
{indented_fetch}

    fetch_result = {{
        "needs_caching": True,
        "cache_key": cache_result.get("cache_key"),
        "data": result
    }}
else:
    # Use cached data
    fetch_result = {{
        "needs_caching": False,
        "cache_key": cache_result.get("cache_key"),
        "data": cache_result.get("data")
    }}

result = fetch_result
""",
            description="Fetch data if cache miss",
        )

        # Cache store node
        builder.add_async_code(
            cache_store_id,
            f"""
import json

# Store in cache if needed
if fetch_data.get("needs_caching", False):
    try:
        # Get cache resource
        if 'get_resource' in globals():
            cache = await get_resource("{cache_resource}")
        else:
            # Fallback for testing
            cache = locals().get("{cache_resource}")
            if cache is None:
                raise RuntimeError(f"Cache resource '{cache_resource}' not available")

        cache_key = fetch_data.get("cache_key")
        data_to_cache = fetch_data.get("data")

        # Serialize data for caching
        if isinstance(data_to_cache, (dict, list)):
            cache_value = json.dumps(data_to_cache)
        else:
            cache_value = data_to_cache

        # Store with TTL
        await cache.setex(cache_key, {ttl_seconds}, cache_value)

        result = {{
            "data": data_to_cache,
            "cached": True,
            "cache_key": cache_key,
            "ttl": {ttl_seconds}
        }}
    except Exception as e:
        # Cache store failed, return data anyway
        result = {{
            "data": fetch_data.get("data"),
            "cached": False,
            "cache_error": str(e)
        }}
else:
    # Data was from cache
    result = {{
        "data": fetch_data.get("data"),
        "cached": False,
        "from_cache": True
    }}
""",
            required_resources=[cache_resource],
            description="Store fetched data in cache",
        )

        # Connect the nodes
        builder.add_connection(cache_check_id, "result", data_fetch_id, "cache_result")
        builder.add_connection(data_fetch_id, "result", cache_store_id, "fetch_data")

        return builder
