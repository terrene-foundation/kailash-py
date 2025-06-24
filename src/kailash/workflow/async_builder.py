"""
AsyncWorkflowBuilder - Async-first workflow development with enhanced ergonomics.

This module provides an async-optimized workflow builder with built-in patterns,
resource management integration, and type-safe construction helpers.
"""

import ast
import asyncio
import inspect
import textwrap
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union

from ..nodes.base import Node
from ..resources.registry import ResourceFactory, ResourceRegistry
from .builder import WorkflowBuilder
from .graph import Workflow

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """Retry policy configuration for async nodes."""

    max_attempts: int = 3
    initial_delay: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0
    retry_exceptions: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "initial_delay": self.initial_delay,
            "backoff_factor": self.backoff_factor,
            "max_delay": self.max_delay,
            "retry_exceptions": self.retry_exceptions,
        }


@dataclass
class ErrorHandler:
    """Error handler configuration for async nodes."""

    handler_type: str  # 'log', 'ignore', 'fallback', 'custom'
    fallback_value: Optional[Any] = None
    custom_handler: Optional[str] = None  # Code string for custom handler
    log_level: str = "error"


class AsyncWorkflowBuilder(WorkflowBuilder):
    """Async-optimized workflow builder with enhanced features."""

    def __init__(
        self,
        name: str = None,
        resource_registry: ResourceRegistry = None,
        description: str = None,
    ):
        super().__init__()
        self.name = name or f"async_workflow_{uuid.uuid4().hex[:8]}"
        self.description = description
        self._resource_registry = resource_registry or ResourceRegistry()
        self._resource_requirements: Set[str] = set()
        self._error_handlers: Dict[str, ErrorHandler] = {}
        self._retry_policies: Dict[str, RetryPolicy] = {}
        self._node_metadata: Dict[str, Dict[str, Any]] = {}
        self._workflow_metadata: Dict[str, Any] = {
            "async_workflow": True,
            "builder_version": "1.0",
            "name": self.name,
            "description": description,
        }

    def add_async_code(
        self,
        node_id: str,
        code: str,
        *,
        timeout: int = 30,
        max_concurrent_tasks: int = 10,
        retry_policy: RetryPolicy = None,
        error_handler: ErrorHandler = None,
        required_resources: List[str] = None,
        description: str = None,
        **kwargs,
    ) -> "AsyncWorkflowBuilder":
        """Add async Python code node with enhanced configuration."""
        # Clean up code indentation
        code = textwrap.dedent(code).strip()

        # Validate code
        self._validate_async_code(code)

        # Track resource requirements
        if required_resources:
            self._resource_requirements.update(required_resources)
            self._node_metadata.setdefault(node_id, {})[
                "required_resources"
            ] = required_resources

        # Configure node
        config = {
            "code": code,
            "timeout": timeout,
            "max_concurrent_tasks": max_concurrent_tasks,
            **kwargs,
        }

        # Add description if provided
        if description:
            config["description"] = description
            self._node_metadata.setdefault(node_id, {})["description"] = description

        # Add node using base builder
        self.add_node("AsyncPythonCodeNode", node_id, config)

        # Configure error handling
        if retry_policy:
            self._retry_policies[node_id] = retry_policy
            self._node_metadata.setdefault(node_id, {})[
                "retry_policy"
            ] = retry_policy.to_dict()
        if error_handler:
            self._error_handlers[node_id] = error_handler
            self._node_metadata.setdefault(node_id, {})["error_handler"] = {
                "type": error_handler.handler_type,
                "fallback_value": error_handler.fallback_value,
            }

        return self  # Fluent interface

    def add_parallel_map(
        self,
        node_id: str,
        map_function: str,
        *,
        input_field: str = "items",
        output_field: str = "results",
        max_workers: int = 10,
        batch_size: int = None,
        timeout_per_item: int = 5,
        continue_on_error: bool = False,
        description: str = None,
    ) -> "AsyncWorkflowBuilder":
        """Add node that processes items in parallel using asyncio.gather."""
        # Validate function
        self._validate_async_function(map_function)

        code = f"""
import asyncio
from asyncio import Semaphore
import time

# Define processing function
{map_function}

# Validate function is defined
if 'process_item' not in locals():
    raise ValueError("map_function must define 'process_item' function")

# Create semaphore for concurrency control
semaphore = Semaphore({max_workers})

async def process_with_timeout(item, index):
    async with semaphore:
        start_time = time.time()
        try:
            # Check if process_item is async
            if asyncio.iscoroutinefunction(process_item):
                result = await asyncio.wait_for(
                    process_item(item),
                    timeout={timeout_per_item}
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.create_task(asyncio.to_thread(process_item, item)),
                    timeout={timeout_per_item}
                )
            return {{
                "index": index,
                "success": True,
                "result": result,
                "duration": time.time() - start_time
            }}
        except asyncio.TimeoutError:
            return {{
                "index": index,
                "success": False,
                "error": "timeout",
                "item": item,
                "duration": time.time() - start_time
            }}
        except Exception as e:
            return {{
                "index": index,
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "item": item,
                "duration": time.time() - start_time
            }}

# Get input items - check both direct field name and generate_output
input_items = None
if '{input_field}' in locals():
    input_items = {input_field}
elif 'generate_output' in locals() and isinstance(generate_output, dict):
    # When connected from another node, input might be in generate_output
    input_items = generate_output.get('{input_field}')
elif 'generate_output' in locals() and '{input_field}' == 'items':
    # Special case: if the output is directly the items list
    input_items = generate_output

if input_items is None:
    available_vars = list(locals().keys())
    raise ValueError(f"Input field '{input_field}' not found. Available: {{available_vars}}")

if not isinstance(input_items, (list, tuple)):
    raise ValueError(f"'{input_field}' must be a list or tuple, got {{type(input_items).__name__}}")

# Process items
total_start = time.time()
all_results = []

# Process in batches if specified
batch_size_val = {batch_size}
if batch_size_val:
    for i in range(0, len(input_items), batch_size_val):
        batch = input_items[i:i+batch_size_val]
        batch_results = await asyncio.gather(
            *[process_with_timeout(item, i+j) for j, item in enumerate(batch)],
            return_exceptions=True
        )
        # Filter out exceptions and convert to error results
        for j, result in enumerate(batch_results):
            if isinstance(result, Exception):
                all_results.append({{
                    "index": i+j,
                    "success": False,
                    "error": str(result),
                    "error_type": type(result).__name__,
                    "item": batch[j],
                    "duration": 0
                }})
            else:
                all_results.append(result)
else:
    batch_results = await asyncio.gather(
        *[process_with_timeout(item, i) for i, item in enumerate(input_items)],
        return_exceptions=True
    )
    # Filter out exceptions and convert to error results
    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            all_results.append({{
                "index": i,
                "success": False,
                "error": str(result),
                "error_type": type(result).__name__,
                "item": input_items[i],
                "duration": 0
            }})
        else:
            all_results.append(result)

# Organize results
successful = [r for r in all_results if r.get("success", False)]
failed = [r for r in all_results if not r.get("success", False)]

# Extract processed items
processed_items = [r["result"] for r in successful]

# Continue on error flag
if not {continue_on_error} and failed:
    error_summary = {{
        "total_errors": len(failed),
        "error_types": {{}}
    }}
    for f in failed:
        error_type = f.get("error", "unknown")
        error_summary["error_types"][error_type] = error_summary["error_types"].get(error_type, 0) + 1

    raise RuntimeError(f"Processing failed for {{len(failed)}} items: {{error_summary}}")

result = {{
    "{output_field}": processed_items,
    "statistics": {{
        "total": len(input_items),
        "successful": len(successful),
        "failed": len(failed),
        "total_duration": time.time() - total_start,
        "average_duration": sum(r["duration"] for r in all_results) / len(all_results) if all_results else 0
    }},
    "errors": failed if failed else []
}}
"""

        return self.add_async_code(
            node_id,
            code,
            max_concurrent_tasks=max_workers,
            timeout=(
                timeout_per_item * len(input_field)
                if hasattr(input_field, "__len__")
                else 300
            ),
            description=description
            or f"Parallel map processing with {max_workers} workers",
        )

    def add_resource_node(
        self,
        node_id: str,
        resource_name: str,
        operation: str,
        params: Dict[str, Any] = None,
        *,
        output_field: str = "result",
        description: str = None,
        **kwargs,
    ) -> "AsyncWorkflowBuilder":
        """Add node that interacts with a registered resource."""
        # Track resource requirement
        self._resource_requirements.add(resource_name)

        # Build parameter string for operation call
        param_parts = []
        if params:
            for key, value in params.items():
                if isinstance(value, str):
                    param_parts.append(f'{key}="{value}"')
                else:
                    param_parts.append(f"{key}={repr(value)}")

        param_str = ", ".join(param_parts)

        code = f"""
# Access resource (function is provided by runtime)
if 'get_resource' in globals():
    resource = await get_resource("{resource_name}")
else:
    # Fallback for testing - resource should be in inputs
    resource = locals().get("{resource_name}")
    if resource is None:
        raise RuntimeError(f"Resource '{resource_name}' not available")

# Validate resource has the operation
if not hasattr(resource, "{operation}"):
    raise AttributeError(f"Resource '{resource_name}' does not have operation '{operation}'")

# Execute operation
operation_result = await resource.{operation}({param_str})

# Wrap result
result = {{
    "{output_field}": operation_result,
    "resource": "{resource_name}",
    "operation": "{operation}"
}}
"""

        return self.add_async_code(
            node_id,
            code,
            required_resources=[resource_name],
            description=description or f"Execute {operation} on {resource_name}",
            **kwargs,
        )

    def add_scatter_gather(
        self,
        scatter_id: str,
        process_id_prefix: str,
        gather_id: str,
        process_function: str,
        *,
        worker_count: int = 4,
        scatter_field: str = "items",
        gather_field: str = "results",
        description: str = None,
    ) -> "AsyncWorkflowBuilder":
        """Add scatter-gather pattern for parallel processing."""
        # Use parallel_map which is simpler and more reliable
        return self.add_parallel_map(
            scatter_id,
            process_function,
            input_field=scatter_field,
            output_field=gather_field,
            max_workers=worker_count,
            description=description
            or f"Scatter-gather processing with {worker_count} workers",
        )

    def _validate_async_code(self, code: str):
        """Validate async Python code."""
        try:
            # Try to compile the code - but allow module-level await
            # by wrapping in an async function for validation
            wrapped_code = "async def __validate_wrapper():\n"
            for line in code.split("\n"):
                wrapped_code += f"    {line}\n"

            # Try to compile the wrapped version first
            try:
                compile(wrapped_code, "<string>", "exec")
            except SyntaxError:
                # If wrapped version fails, try original (might be valid module-level code)
                compile(code, "<string>", "exec")

        except SyntaxError as e:
            # Only reject if it's a true syntax error, not await-related
            if "await" not in str(e):
                raise ValueError(f"Invalid Python code: {e}")
            # For await-related errors, we'll allow them since AsyncPythonCodeNode handles module-level await

    def _validate_async_function(self, function_code: str):
        """Validate async function definition."""
        # Check if it defines process_item function
        if "def process_item" not in function_code:
            raise ValueError(
                "Function must define 'def process_item(item)' or 'async def process_item(item)'"
            )

        # Validate syntax
        self._validate_async_code(function_code)

    # Resource management methods
    def require_resource(
        self,
        name: str,
        factory: ResourceFactory,
        health_check: Callable = None,
        cleanup_handler: Callable = None,
        description: str = None,
    ) -> "AsyncWorkflowBuilder":
        """Declare a required resource for this workflow."""
        # Register with resource registry
        self._resource_registry.register_factory(
            name, factory, health_check=health_check, cleanup_handler=cleanup_handler
        )

        # Track requirement
        self._resource_requirements.add(name)

        # Add to workflow metadata
        self._workflow_metadata.setdefault("resources", {})[name] = {
            "factory_type": type(factory).__name__,
            "description": description or f"Resource: {name}",
            "has_health_check": health_check is not None,
            "has_cleanup": cleanup_handler is not None,
        }

        return self

    def with_database(
        self,
        name: str = "db",
        host: str = "localhost",
        port: int = 5432,
        database: str = None,
        user: str = None,
        password: str = None,
        min_size: int = 10,
        max_size: int = 20,
        **kwargs,
    ) -> "AsyncWorkflowBuilder":
        """Add database resource requirement."""
        from ..resources.factory import DatabasePoolFactory

        config = {
            "host": host,
            "port": port,
            "min_size": min_size,
            "max_size": max_size,
            **kwargs,
        }

        # Only add non-None values
        if database:
            config["database"] = database
        if user:
            config["user"] = user
        if password:
            config["password"] = password

        factory = DatabasePoolFactory(**config)

        # Health check for PostgreSQL
        async def pg_health_check(pool):
            try:
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                return True
            except Exception:
                return False

        # Cleanup handler
        async def pg_cleanup(pool):
            await pool.close()

        return self.require_resource(
            name,
            factory,
            health_check=pg_health_check,
            cleanup_handler=pg_cleanup,
            description=f"PostgreSQL database connection pool to {host}:{port}/{database or 'default'}",
        )

    def with_http_client(
        self,
        name: str = "http",
        base_url: str = None,
        headers: Dict[str, str] = None,
        timeout: int = 30,
        **kwargs,
    ) -> "AsyncWorkflowBuilder":
        """Add HTTP client resource requirement."""
        from ..resources.factory import HttpClientFactory

        config = {"timeout": timeout, **kwargs}

        if headers:
            config["headers"] = headers

        factory = HttpClientFactory(base_url=base_url, **config)

        # Cleanup handler for aiohttp
        async def http_cleanup(session):
            await session.close()

        return self.require_resource(
            name,
            factory,
            cleanup_handler=http_cleanup,
            description="HTTP client session"
            + (f" for {base_url}" if base_url else ""),
        )

    def with_cache(
        self,
        name: str = "cache",
        backend: str = "redis",
        host: str = "localhost",
        port: int = 6379,
        **kwargs,
    ) -> "AsyncWorkflowBuilder":
        """Add cache resource requirement."""
        if backend == "redis":
            from ..resources.factory import CacheFactory

            factory = CacheFactory(backend=backend, host=host, port=port, **kwargs)

            # Health check for Redis
            async def redis_health_check(cache):
                try:
                    await cache.ping() if hasattr(cache, "ping") else True
                    return True
                except Exception:
                    return False

            # Cleanup handler
            async def redis_cleanup(cache):
                if hasattr(cache, "close"):
                    cache.close()
                if hasattr(cache, "wait_closed"):
                    await cache.wait_closed()

            return self.require_resource(
                name,
                factory,
                health_check=redis_health_check,
                cleanup_handler=redis_cleanup,
                description=f"Redis cache connection to {host}:{port}",
            )
        else:
            raise ValueError(f"Unsupported cache backend: {backend}")

    def build(self) -> Workflow:
        """Build the async workflow with enhanced metadata."""
        # Add resource requirements to workflow metadata
        self._workflow_metadata["required_resources"] = list(
            self._resource_requirements
        )
        self._workflow_metadata["node_metadata"] = self._node_metadata

        # Build base workflow
        workflow = super().build()

        # Enhance workflow with async metadata
        if hasattr(workflow, "metadata"):
            workflow.metadata.update(self._workflow_metadata)
        else:
            workflow.metadata = self._workflow_metadata

        # Attach resource registry to workflow
        workflow.resource_registry = self._resource_registry

        return workflow

    def get_resource_registry(self) -> ResourceRegistry:
        """Get the resource registry for this workflow."""
        return self._resource_registry

    def list_required_resources(self) -> List[str]:
        """List all required resources for this workflow."""
        return list(self._resource_requirements)

    def get_node_metadata(self, node_id: str) -> Dict[str, Any]:
        """Get metadata for a specific node."""
        return self._node_metadata.get(node_id, {})

    def add_connection(
        self, from_node: str, from_output: str, to_node: str, to_input: str
    ) -> "AsyncWorkflowBuilder":
        """Connect two nodes in the workflow (fluent interface version)."""
        super().add_connection(from_node, from_output, to_node, to_input)
        return self
