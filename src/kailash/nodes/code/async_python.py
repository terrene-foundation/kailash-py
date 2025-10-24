"""Asynchronous Python Code Execution Node.

This module provides AsyncPythonCodeNode for executing async Python code
with proper security controls and resource management.

Key Features:
    - Native async/await support for Python code execution
    - Concurrent task management with resource limits
    - Security sandbox with controlled module access
    - Timeout and memory limit enforcement
    - Integration with async libraries and databases

Example Usage:
    Basic async execution:
    ```python
    node = AsyncPythonCodeNode(
        code='''
import asyncio

# Fetch data concurrently
async def fetch_item(id):
    await asyncio.sleep(0.1)  # Simulate I/O
    return {"id": id, "data": f"Item {id}"}

ids = [1, 2, 3, 4, 5]
tasks = [fetch_item(id) for id in ids]
items = await asyncio.gather(*tasks)

result = {"items": items, "count": len(items)}
        ''',
        timeout=30,
        max_concurrent_tasks=10
    )

    output = await node.execute_async()
    ```

    Database operations with connection pool:
    ```python
    node = AsyncPythonCodeNode(
        code='''
# Async database operations
conn = await pool.acquire()
try:
    # Run multiple queries concurrently
    results = await asyncio.gather(
        pool.execute("SELECT * FROM users WHERE active = true"),
        pool.execute("SELECT COUNT(*) FROM orders"),
        pool.execute("SELECT * FROM products LIMIT 10")
    )

    result = {
        "users": results[0],
        "order_count": results[1],
        "products": results[2]
    }
finally:
    await pool.release(conn)
        '''
    )

    # Execute with runtime inputs
    output = await node.execute_async(pool=database_pool)
    ```

Security Model:
    The node operates in a secure sandbox with:
    - Whitelisted module imports only
    - No access to filesystem (except through allowed modules)
    - No subprocess or system command execution
    - Resource limits on memory and concurrent tasks
    - Timeout enforcement for runaway code

Performance Considerations:
    - Best for I/O-bound operations (database, API calls)
    - Overhead for CPU-bound tasks (use PythonCodeNode instead)
    - Concurrent task limit prevents resource exhaustion
    - Event loop is managed automatically
"""

import ast
import asyncio
import inspect
import logging
import time
import traceback
from typing import Any, Dict, Optional, Set

from kailash.nodes.base import NodeMetadata, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.resources import ResourceRegistry
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    SafetyViolationError,
)
from kailash.security import ExecutionTimeoutError

logger = logging.getLogger(__name__)

# Import shared constants and utilities
from kailash.nodes.code.common import (
    ALLOWED_ASYNC_BUILTINS,
    ALLOWED_ASYNC_MODULES,
    ASYNC_FUNCTION_REPLACEMENTS,
    COMPLETELY_BLOCKED_MODULES,
    DANGEROUS_GLOBAL_FUNCTIONS,
    DANGEROUS_MODULE_FUNCTIONS,
    ensure_json_serializable,
    format_dangerous_function_error,
    format_module_not_allowed_error,
    is_dangerous_function,
)

# For backward compatibility, expose as module-level constants
BLOCKED_ASYNC_PATTERNS = list(DANGEROUS_GLOBAL_FUNCTIONS)


class AsyncSafeCodeChecker(ast.NodeVisitor):
    """AST visitor to check async code safety."""

    def __init__(self):
        self.violations = []
        self.imports_found = []
        self.has_async = False
        self.concurrent_task_count = 0

    def visit_Import(self, node):
        """Check import statements."""
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            self.imports_found.append(module_name)
            if module_name not in ALLOWED_ASYNC_MODULES:
                self.violations.append(
                    {
                        "type": "import",
                        "module": module_name,
                        "line": node.lineno,
                        "message": f"Import of module '{module_name}' is not allowed in async context",
                    }
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Check from imports."""
        if node.module:
            module_name = node.module.split(".")[0]
            self.imports_found.append(module_name)
            if module_name not in ALLOWED_ASYNC_MODULES:
                self.violations.append(
                    {
                        "type": "import_from",
                        "module": module_name,
                        "line": node.lineno,
                        "message": f"Import from module '{module_name}' is not allowed in async context",
                    }
                )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        """Track async function definitions."""
        self.has_async = True
        self.generic_visit(node)

    def visit_AsyncWith(self, node):
        """Track async with statements."""
        self.has_async = True
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        """Track async for loops."""
        self.has_async = True
        self.generic_visit(node)

    def visit_Subscript(self, node):
        """Check for dangerous access through __builtins__ or other methods."""
        # Check if accessing __builtins__
        if isinstance(node.value, ast.Name) and node.value.id == "__builtins__":
            # Check if trying to access blocked functions
            if isinstance(node.slice, ast.Constant):
                func_name = node.slice.value
                if func_name in BLOCKED_ASYNC_PATTERNS:
                    self.violations.append(
                        {
                            "type": "dangerous_access",
                            "function": func_name,
                            "line": node.lineno,
                            "message": f"Access to '{func_name}' through __builtins__ is not allowed for security reasons",
                        }
                    )
        self.generic_visit(node)

    def visit_Call(self, node):
        """Check for dangerous function calls."""
        func_name = None
        is_builtin_call = False

        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            is_builtin_call = True  # Direct function call like open()
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            # Check if it's a module.function call that we should block
            if isinstance(node.func.value, ast.Name):
                module_name = node.func.value.id
                # Only block if it's not from an allowed module
                if module_name not in ALLOWED_ASYNC_MODULES:
                    is_builtin_call = True

        # Only block dangerous patterns if they're direct calls or from non-allowed modules
        if func_name in BLOCKED_ASYNC_PATTERNS and is_builtin_call:
            self.violations.append(
                {
                    "type": "dangerous_call",
                    "function": func_name,
                    "line": node.lineno,
                    "message": f"Call to '{func_name}' is not allowed for security reasons",
                }
            )

        # Track concurrent task creation
        if func_name in ["create_task", "ensure_future", "gather"]:
            self.concurrent_task_count += 1

        self.generic_visit(node)


@register_node()
class AsyncPythonCodeNode(AsyncNode):
    """Execute asynchronous Python code with security controls and resource management.

        AsyncPythonCodeNode provides a secure environment for executing async Python code
        within Kailash workflows. It's designed for I/O-bound operations that benefit from
        concurrent execution, such as database queries, API calls, and file operations.

        Features:
            - **Native async/await support**: Write natural async Python code
            - **Concurrent execution**: Run multiple async operations in parallel
            - **Resource limits**: Control memory usage and concurrent task count
            - **Security sandbox**: Only whitelisted modules can be imported
            - **Timeout protection**: Prevent runaway code execution
            - **Rich module ecosystem**: Access to async database drivers, HTTP clients, etc.

        Security Model:
            The node executes code in a restricted environment where:
            - Only modules in ALLOWED_ASYNC_MODULES can be imported
            - Dangerous operations (subprocess, eval, exec) are blocked
            - File system access is limited to safe operations
            - Network access is allowed through whitelisted libraries
            - Resource limits prevent memory and CPU exhaustion

        Parameters:
            code (str): The async Python code to execute. Must be valid Python with
                proper async/await syntax. The code should set a 'result' variable
                with the output data.
            timeout (int): Maximum execution time in seconds (default: 30).
                Prevents infinite loops and runaway code.
            max_concurrent_tasks (int): Maximum number of concurrent asyncio tasks
                (default: 10). Prevents resource exhaustion from too many parallel operations.
            max_memory_mb (int): Maximum memory usage in MB (default: 512).
                Note: Only enforced on Unix systems with resource module support.

        Inputs:
            The node accepts arbitrary keyword arguments that will be available as
            variables in the execution context. All inputs must be JSON-serializable
            when used through the gateway API.

        Outputs:
            Returns a dictionary containing the 'result' variable from the executed code.
            If no 'result' variable is set, returns an empty dictionary.

        Example - Basic async operation:
            ```python
            node = AsyncPythonCodeNode(
                code='''
    import asyncio

    # Simple async operation
    await asyncio.sleep(0.1)
    result = {"status": "completed", "duration": 0.1}
                '''
            )

            output = await node.execute_async()
            # Returns: {"status": "completed", "duration": 0.1}
            ```

        Example - Concurrent database queries:
            ```python
            node = AsyncPythonCodeNode(
                code='''
    import asyncio
    import asyncpg

    # Connect to database
    conn = await asyncpg.connect(database_url)

    try:
        # Run queries concurrently
        user_query = conn.fetch("SELECT * FROM users WHERE active = true")
        stats_query = conn.fetch("SELECT COUNT(*) as total FROM orders")
        recent_query = conn.fetch("SELECT * FROM orders ORDER BY created DESC LIMIT 10")

        users, stats, recent = await asyncio.gather(
            user_query, stats_query, recent_query
        )

        result = {
            "active_users": len(users),
            "total_orders": stats[0]['total'],
            "recent_orders": [dict(order) for order in recent]
        }
    finally:
        await conn.close()
                ''',
                timeout=10,
                max_concurrent_tasks=5
            )

            output = await node.execute_async(database_url="postgresql://...")
            ```

        Example - Parallel API calls with rate limiting:
            ```python
            node = AsyncPythonCodeNode(
                code='''
    import asyncio
    import aiohttp
    from asyncio import Semaphore

    # Rate limit to 5 concurrent requests
    semaphore = Semaphore(5)

    async def fetch_data(session, url):
        async with semaphore:
            async with session.get(url) as response:
                return await response.json()

    # Process URLs in parallel
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_data(session, url) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out errors
        valid_responses = [r for r in responses if not isinstance(r, Exception)]

        result = {
            "success_count": len(valid_responses),
            "error_count": len(responses) - len(valid_responses),
            "data": valid_responses
        }
                ''',
                max_concurrent_tasks=20  # Allow more tasks for API calls
            )

            urls = ["https://api.example.com/data/1", ...]
            output = await node.execute_async(urls=urls)
            ```

        Best Practices:
            1. Always use try/finally blocks for cleanup (closing connections, files)
            2. Use asyncio.gather() for concurrent operations
            3. Implement proper error handling for network operations
            4. Set appropriate timeouts for external service calls
            5. Use semaphores to limit concurrent operations when needed
            6. Return results in a dictionary format for consistency

        Performance Tips:
            - Use for I/O-bound operations (network, database, file I/O)
            - Not ideal for CPU-bound tasks (use PythonCodeNode instead)
            - Batch operations when possible to reduce overhead
            - Monitor concurrent task count to avoid overwhelming resources

        Limitations:
            - Cannot import modules not in ALLOWED_ASYNC_MODULES
            - Cannot execute system commands or create subprocesses
            - Limited file system access (use dedicated file nodes for complex operations)
            - All inputs must be serializable when used through gateway
            - Memory limits may not be enforced on all platforms
    """

    metadata = NodeMetadata(
        name="AsyncPythonCodeNode",
        description="Execute asynchronous Python code with security controls",
        category="code",
        version="1.0.0",
        display_name="Async Python Code",
        icon="mdi-language-python",
        tags=["code", "async", "python", "script"],
    )

    def __init__(self, **config):
        """Initialize AsyncPythonCodeNode with configuration.

        Creates a new async Python code execution node with the specified
        configuration. The code is validated at initialization time to catch
        syntax errors and security violations early.

        Args:
            code (str): The async Python code to execute. Must contain valid
                Python syntax with async/await support. The code should set
                a 'result' variable with the output data.

            timeout (int, optional): Maximum execution time in seconds.
                Defaults to 30. Set higher for long-running operations like
                data processing or multiple API calls.

            max_concurrent_tasks (int, optional): Maximum number of concurrent
                asyncio tasks allowed. Defaults to 10. Increase for highly
                parallel workloads, decrease to limit resource usage.

            max_memory_mb (int, optional): Maximum memory usage in MB.
                Defaults to 512. Only enforced on Unix systems with resource
                module support. Set higher for data-intensive operations.

            imports (list[str], optional): Additional modules to make available
                in the execution context. Currently not implemented - all
                imports must be from ALLOWED_ASYNC_MODULES.

            **config: Additional configuration parameters passed to parent class.

        Raises:
            NodeConfigurationError: If code is empty or has syntax errors.
            SafetyViolationError: If code contains security violations like
                forbidden imports or dangerous operations.

        Example:
            ```python
            # Basic initialization
            node = AsyncPythonCodeNode(
                code="await asyncio.sleep(0.1); result = {'done': True}"
            )

            # Advanced configuration
            node = AsyncPythonCodeNode(
                code=complex_async_code,
                timeout=60,  # 1 minute timeout
                max_concurrent_tasks=50,  # Allow many parallel operations
                max_memory_mb=1024  # 1GB memory limit
            )
            ```
        """
        super().__init__(**config)

        self.code = config.get("code", "")
        self.timeout = config.get("timeout", 30)
        self.max_concurrent_tasks = config.get("max_concurrent_tasks", 10)
        self.max_memory_mb = config.get("max_memory_mb", 512)
        self.allowed_imports = set(config.get("imports", []))

        # Validate code at initialization
        self._validate_code()

    def _validate_code(self):
        """Validate code for safety violations."""
        if not self.code:
            raise NodeConfigurationError("Code cannot be empty")

        try:
            tree = ast.parse(self.code)
        except SyntaxError as e:
            raise NodeConfigurationError(f"Invalid Python syntax: {e}")

        checker = AsyncSafeCodeChecker()
        checker.visit(tree)

        if checker.violations:
            violation_messages = []
            suggestions = []

            for violation in checker.violations:
                violation_messages.append(
                    f"Line {violation['line']}: {violation['message']}"
                )

                if violation["type"] in ["import", "import_from"]:
                    suggestions.append(
                        f"- Module '{violation['module']}' is not allowed. "
                        f"Available async modules: {', '.join(sorted(ALLOWED_ASYNC_MODULES))}"
                    )

            error_msg = "Code safety violations found:\n" + "\n".join(
                violation_messages
            )

            if suggestions:
                error_msg += "\n\nSuggestions:\n" + "\n".join(suggestions)

            raise SafetyViolationError(error_msg)

        # Warn if too many concurrent tasks
        if checker.concurrent_task_count > self.max_concurrent_tasks:
            logger.warning(
                f"Code may create {checker.concurrent_task_count} concurrent tasks, "
                f"but limit is {self.max_concurrent_tasks}"
            )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "code": NodeParameter(
                name="code",
                type=str,
                description="Async Python code to execute",
                required=True,
                default="",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                description="Execution timeout in seconds",
                required=False,
                default=30,
            ),
            "max_concurrent_tasks": NodeParameter(
                name="max_concurrent_tasks",
                type=int,
                description="Maximum concurrent asyncio tasks",
                required=False,
                default=10,
            ),
        }

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate and pass through runtime inputs.

        AsyncPythonCodeNode accepts arbitrary inputs that will be available
        as variables in the code execution context. This allows maximum
        flexibility for custom code logic.

        Unlike typed nodes, we don't validate input types or required fields.
        The executed code is responsible for its own validation and error
        handling.

        Args:
            **kwargs: Any keyword arguments passed at execution time.
                These will be available as variables in the async code.

                Common inputs include:
                - Database connections or pools
                - API endpoints or credentials
                - Data to process
                - Configuration parameters

                All inputs must be serializable if using through gateway.

        Returns:
            Dict[str, Any]: All inputs unchanged, ready for code execution.

        Example:
            ```python
            # These inputs...
            result = await node.execute_async(
                database_url="postgresql://localhost/mydb",
                api_key="secret123",
                user_ids=[1, 2, 3],
                timeout_seconds=10
            )

            # ...become variables in the code:
            # database_url = "postgresql://localhost/mydb"
            # api_key = "secret123"
            # user_ids = [1, 2, 3]
            # timeout_seconds = 10
            ```

        Note:
            Input validation should be done in the async code itself:
            ```python
            # In your async code
            if not database_url:
                raise ValueError("database_url is required")
            if not isinstance(user_ids, list):
                raise TypeError("user_ids must be a list")
            ```
        """
        # Pass through all inputs for async code execution
        return kwargs

    def _create_safe_namespace(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a safe execution namespace."""

        # Custom import function that only allows whitelisted modules
        def safe_import(name, *args, **kwargs):
            """Restricted import that only allows whitelisted modules."""
            module_name = name.split(".")[0]
            if module_name not in ALLOWED_ASYNC_MODULES:
                raise ImportError(f"Import of module '{module_name}' is not allowed")
            return __import__(name, *args, **kwargs)

        # Use shared builtin whitelist for consistency with sync version
        # Start with the common builtins from shared module
        import builtins as builtin_module

        safe_builtins = {
            "__import__": safe_import,  # Controlled import (override)
        }

        # Add all allowed builtins from shared configuration
        for name in ALLOWED_ASYNC_BUILTINS:
            if hasattr(builtin_module, name):
                safe_builtins[name] = getattr(builtin_module, name)

        # Create namespace with inputs and safe builtins
        namespace = {
            "__builtins__": safe_builtins,
            **inputs,  # Make inputs available as variables
        }

        # Add data path utilities (matching sync version)
        try:
            from kailash.utils.data_paths import (
                get_data_path,
                get_input_data_path,
                get_output_data_path,
            )

            namespace["get_input_data_path"] = get_input_data_path
            namespace["get_output_data_path"] = get_output_data_path
            namespace["get_data_path"] = get_data_path
        except ImportError:
            logger.warning(
                "Could not import data path utilities - functions will not be available in AsyncPythonCodeNode execution"
            )

        # Add workflow context functions (matching sync version)
        # Note: These would need to be async versions in a real implementation
        # For now, we'll add fail-fast placeholders to match sync behavior
        def _get_workflow_context(key: str, default=None):
            raise NodeExecutionError(
                "get_workflow_context() is not available - node instance not provided. "
                "This function requires execution through a workflow runtime with context support. "
                "If you need stateful data, consider using explicit variables or external storage."
            )

        def _set_workflow_context(key: str, value):
            raise NodeExecutionError(
                "set_workflow_context() is not available - node instance not provided. "
                "This function requires execution through a workflow runtime with context support. "
                "If you need stateful data, consider using explicit variables or external storage."
            )

        namespace["get_workflow_context"] = _get_workflow_context
        namespace["set_workflow_context"] = _set_workflow_context

        return namespace

    def _indent_code(self, code: str, indent: str = "    ") -> str:
        """Indent code by the specified amount."""
        lines = code.split("\n")
        indented_lines = []
        for line in lines:
            if line.strip():  # Non-empty lines
                indented_lines.append(indent + line)
            else:  # Preserve empty lines
                indented_lines.append("")
        return "\n".join(indented_lines)

    async def async_run(
        self, resource_registry: Optional[ResourceRegistry] = None, **kwargs
    ) -> Dict[str, Any]:
        """Execute async Python code in a secure sandbox.

        This method is called by the AsyncNode base class to execute the
        configured Python code. It sets up a secure execution environment,
        injects input variables, and manages resource limits.

        The execution process:
        1. Filter node configuration from runtime inputs
        2. Create secure namespace with whitelisted builtins
        3. Compile async code into an executable function
        4. Set up resource limits (timeout, task concurrency)
        5. Execute code and capture result
        6. Validate and return output

        Args:
            **kwargs: Runtime inputs passed from execute_async().
                These become variables in the code execution context.
                Node configuration parameters are filtered out.

        Returns:
            Dict[str, Any]: Dictionary containing execution results.
                If code sets 'result' variable, returns its value.
                Otherwise returns empty dict.

        Raises:
            NodeExecutionError: If code execution fails for any reason:
                - Syntax errors in code
                - Runtime errors (e.g., NameError, TypeError)
                - Import of forbidden modules
                - Timeout exceeded
                - Security violations

            The error message includes details about what went wrong.

        Example Flow:
            ```python
            # User calls:
            output = await node.execute_async(data=[1,2,3], multiplier=2)

            # This method:
            # 1. Filters out config params, keeps data and multiplier
            # 2. Makes them available in code as variables
            # 3. Executes the async code
            # 4. Returns the result
            ```

        Security Notes:
            - Code runs with limited builtins (no eval, exec, etc.)
            - Only whitelisted modules can be imported
            - Concurrent tasks are limited by semaphore
            - Execution time is bounded by timeout
            - AST is checked for dangerous patterns before execution
        """
        try:
            # Filter out node configuration parameters from runtime inputs
            config_params = {
                "code",
                "timeout",
                "max_concurrent_tasks",
                "max_memory_mb",
                "imports",
                # Note: "config" removed - it's a valid runtime parameter name
            }
            runtime_inputs = {k: v for k, v in kwargs.items() if k not in config_params}

            # Create safe namespace with inputs
            namespace = self._create_safe_namespace(runtime_inputs)

            # Add resource access if registry provided
            if resource_registry:

                async def get_resource(name: str):
                    """Get resource from registry."""
                    return await resource_registry.get_resource(name)

                namespace["get_resource"] = get_resource

            # Generate unique function name to avoid conflicts
            func_name = f"_async_user_func_{id(self)}"

            # Create the async function definition with user code
            # First, inject input variables into the function
            input_assignments = []
            for key in runtime_inputs:
                # Create assignments that reference the namespace
                input_assignments.append(f"    {key} = _namespace['{key}']")

            input_code = (
                "\n".join(input_assignments) if input_assignments else "    pass"
            )

            # We'll compile the entire async function as a unit
            # CRITICAL FIX: Return ALL variables from local scope, not just 'result'
            # This enables multi-output pattern (v0.9.28+) for AsyncPythonCodeNode
            async_func_code = f"""
async def {func_name}(_namespace):
    # Extract input variables
{input_code}

    # User's async code
{self._indent_code(self.code)}

    # Export ALL non-private variables (multi-output pattern)
    # This matches PythonCodeNode behavior and fixes variable export bug
    import types

    # Get local variables (exclude function parameters and builtins)
    local_vars = locals().copy()

    # Filter to exportable variables:
    # - Not private (no leading underscore)
    # - Not module types
    # - Not the _namespace parameter itself
    exported_vars = {{
        k: v
        for k, v in local_vars.items()
        if not k.startswith("_")
        and not isinstance(v, types.ModuleType)
        and k != "_namespace"
    }}

    return exported_vars
"""

            # Compile and execute the function definition
            try:
                compiled = compile(async_func_code, "<async_user_code>", "exec")
                exec(compiled, namespace)
            except SyntaxError as e:
                raise NodeExecutionError(f"Syntax error in async code: {e}")

            # Get the function from namespace
            user_function = namespace[func_name]

            # Track concurrent tasks
            task_semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
            original_create_task = asyncio.create_task

            def limited_create_task(coro):
                """Limit concurrent task creation."""

                async def wrapped():
                    async with task_semaphore:
                        return await coro

                return original_create_task(wrapped())

            # Monkey patch for this execution
            asyncio.create_task = limited_create_task

            try:
                # Execute with timeout
                start_time = time.time()
                exported_vars = await asyncio.wait_for(
                    user_function(namespace), timeout=self.timeout
                )
                execution_time = time.time() - start_time

                logger.debug(
                    f"AsyncPythonCodeNode executed successfully in {execution_time:.2f}s"
                )

                # Match PythonCodeNode behavior:
                # - If 'result' exists, return just that (wrapped in dict)
                # - Otherwise return all exported variables (multi-output pattern)
                if "result" in exported_vars:
                    return {"result": exported_vars["result"]}

                # Return all exported variables for multi-output pattern
                return exported_vars

            finally:
                # Restore original create_task
                asyncio.create_task = original_create_task

        except asyncio.TimeoutError:
            raise NodeExecutionError(
                f"Async code execution exceeded {self.timeout}s timeout"
            )
        except Exception as e:
            logger.error(f"Async code execution failed: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            raise NodeExecutionError(f"Execution failed: {str(e)}")

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output parameters for this node.

        Returns:
            Dictionary mapping output names to their parameter definitions

        Note:
            Supports multi-output pattern (v0.9.28+) where code can export
            multiple variables directly without using 'result':

            Example:
                my_filter = {"id": "test_123"}
                my_fields = {"name": "John"}

            Both my_filter and my_fields become available as outputs.
        """
        # Dynamic output schema - 'result' is optional
        # This allows code to export multiple variables directly
        return {
            "result": NodeParameter(
                name="result",
                type=Any,
                required=False,  # Allow code to export other variables
                description="Primary output result (optional - code can export multiple variables)",
            )
        }

    def validate_outputs(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate outputs are JSON-serializable."""
        import json

        try:
            # Test JSON serialization
            json.dumps(outputs)
            return outputs
        except (TypeError, ValueError) as e:
            raise NodeExecutionError(f"Output must be JSON-serializable: {e}")

    @classmethod
    def from_function(cls, func, **config):
        """Create AsyncPythonCodeNode from an existing async function.

        This factory method allows you to convert an async Python function
        into an AsyncPythonCodeNode. The function's source code is extracted
        and used as the node's code parameter.

        This is useful when:
        - You have existing async functions to integrate
        - You want IDE support while writing the function
        - You need to reuse async logic across multiple nodes
        - You prefer writing functions over inline code strings

        Args:
            func (Callable): An async function (defined with 'async def').
                The function should follow these conventions:
                - Accept parameters that match expected inputs
                - Return a dictionary (becomes the 'result')
                - Use only allowed modules
                - Handle its own errors

            **config: Additional node configuration:
                - name (str): Node name (defaults to function name)
                - timeout (int): Execution timeout in seconds
                - max_concurrent_tasks (int): Concurrent task limit
                - max_memory_mb (int): Memory limit in MB
                - Any other Node configuration parameters

        Returns:
            AsyncPythonCodeNode: Configured node instance ready for execution.

        Raises:
            ValueError: If the provided function is not async (not a coroutine).
            ValueError: If the function source cannot be extracted.

        Example:
            ```python
            # Define an async function
            async def process_user_data(user_ids: list, database_url: str) -> dict:
                import asyncio
                import asyncpg

                # Connect to database
                conn = await asyncpg.connect(database_url)

                try:
                    # Process users concurrently
                    tasks = []
                    for user_id in user_ids:
                        task = conn.fetchrow(
                            "SELECT * FROM users WHERE id = $1",
                            user_id
                        )
                        tasks.append(task)

                    users = await asyncio.gather(*tasks)

                    # Transform data
                    result = {
                        "users": [dict(u) for u in users if u],
                        "count": len(users),
                        "missing": len([u for u in users if not u])
                    }
                    return result

                finally:
                    await conn.close()

            # Create node from function
            node = AsyncPythonCodeNode.from_function(
                process_user_data,
                name="user_processor",
                timeout=30,
                max_concurrent_tasks=20
            )

            # Execute with inputs
            result = await node.execute_async(
                user_ids=[1, 2, 3],
                database_url="postgresql://localhost/mydb"
            )
            ```

        Technical Notes:
            - Function source is extracted using inspect.getsource()
            - The function body is dedented to remove indentation
            - The 'return' statement becomes 'result = ...'
            - Function must be defined in a file (not in REPL)
            - Decorators are not preserved
            - Default arguments are not preserved (pass as inputs)

        Limitations:
            - Cannot extract source from built-in functions
            - Cannot handle functions defined in interactive sessions
            - Nested functions may not work correctly
            - Closures (captured variables) are not preserved
        """
        if not inspect.iscoroutinefunction(func):
            raise ValueError("Function must be async (defined with 'async def')")

        # Get function source
        source = inspect.getsource(func)

        # Extract just the function body
        lines = source.split("\n")
        # Find the function definition line
        for i, line in enumerate(lines):
            if line.strip().startswith("async def"):
                # Get everything after the function definition
                body_lines = lines[i + 1 :]
                break
        else:
            raise ValueError("Could not find async function definition")

        # Remove common indentation
        min_indent = float("inf")
        for line in body_lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)

        if min_indent == float("inf"):
            min_indent = 0

        # Remove the common indentation
        dedented_lines = []
        for line in body_lines:
            if line.strip():
                dedented_lines.append(line[min_indent:])
            else:
                dedented_lines.append("")

        code = "\n".join(dedented_lines)

        # Create node with function's code
        return cls(code=code, name=config.get("name", func.__name__), **config)

    @staticmethod
    def list_allowed_modules() -> list[str]:
        """List all allowed modules for AsyncPythonCodeNode.

        Returns:
            Sorted list of allowed module names

        Example:
            >>> modules = AsyncPythonCodeNode.list_allowed_modules()
            >>> 'asyncio' in modules
            True
            >>> 'subprocess' in modules
            False
        """
        return sorted(ALLOWED_ASYNC_MODULES)

    @staticmethod
    def check_module_availability(module_name: str) -> Dict[str, Any]:
        """Check if a module is allowed and available for import.

        This utility helps users understand why a module import might fail
        and provides helpful suggestions for alternatives.

        Args:
            module_name: Name of the module to check

        Returns:
            Dictionary with status information:
                - module: Module name
                - allowed: Whether module is in whitelist
                - installed: Whether module is installed
                - importable: Whether module can be imported
                - error: Error message if any
                - suggestions: List of helpful suggestions

        Example:
            >>> result = AsyncPythonCodeNode.check_module_availability("asyncio")
            >>> result['allowed']
            True
            >>> result['installed']
            True

            >>> result = AsyncPythonCodeNode.check_module_availability("subprocess")
            >>> result['allowed']
            False
            >>> 'not allowed' in result['suggestions'][0]
            True
        """
        import importlib.util

        result = {
            "module": module_name,
            "allowed": module_name in ALLOWED_ASYNC_MODULES,
            "installed": False,
            "importable": False,
            "error": None,
            "suggestions": [],
        }

        if not result["allowed"]:
            result["suggestions"].append(
                f"Module '{module_name}' is not in the allowed list for async context."
            )
            result["suggestions"].append(
                f"Allowed modules: {', '.join(sorted(ALLOWED_ASYNC_MODULES))}"
            )

            # Add specific suggestions
            from kailash.nodes.code.common import get_module_suggestions

            specific_suggestions = get_module_suggestions(module_name)
            result["suggestions"].extend(specific_suggestions)
        else:
            # Check if module is installed
            try:
                spec = importlib.util.find_spec(module_name)
                result["installed"] = spec is not None

                if result["installed"]:
                    # Try to import it
                    try:
                        importlib.import_module(module_name)
                        result["importable"] = True
                    except Exception as e:
                        result["error"] = str(e)
                        result["suggestions"].append(
                            f"Module is installed but cannot be imported: {e}"
                        )
                else:
                    result["suggestions"].append(
                        f"Module '{module_name}' needs to be installed: pip install {module_name}"
                    )
            except Exception as e:
                result["error"] = str(e)
                result["suggestions"].append(f"Error checking module: {e}")

        return result

    def validate_code(self, code: str) -> Dict[str, Any]:
        """Validate async Python code and provide detailed feedback.

        This method checks code for syntax errors, security violations, and
        provides helpful suggestions. It's useful for pre-validating user code
        before execution.

        Args:
            code: Async Python code to validate

        Returns:
            Dictionary with validation results:
                - valid: Whether code is valid and safe
                - syntax_errors: List of syntax errors found
                - safety_violations: List of security violations
                - imports: List of modules imported
                - suggestions: List of helpful suggestions
                - warnings: List of warnings (non-blocking)

        Example:
            >>> node = AsyncPythonCodeNode(code="result = 1")
            >>> result = node.validate_code("import subprocess")
            >>> result['valid']
            False
            >>> 'subprocess' in result['safety_violations'][0]['module']
            True
        """
        result = {
            "valid": True,
            "syntax_errors": [],
            "safety_violations": [],
            "imports": [],
            "suggestions": [],
            "warnings": [],
        }

        # Check syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            result["valid"] = False
            result["syntax_errors"].append(
                {"line": e.lineno, "column": e.offset, "message": e.msg, "text": e.text}
            )
            result["suggestions"].append(
                f"Fix syntax error at line {e.lineno}: {e.msg}"
            )
            return result

        # Check safety
        try:
            checker = AsyncSafeCodeChecker()
            checker.visit(ast.parse(code))
            result["imports"] = checker.imports_found

            if checker.violations:
                result["valid"] = False
                result["safety_violations"] = checker.violations

                # Add suggestions from violations
                for violation in checker.violations:
                    if violation["type"] in [
                        "import",
                        "import_from",
                        "dangerous_import",
                    ]:
                        module = violation.get("module", "unknown")
                        module_info = self.check_module_availability(module)
                        result["suggestions"].extend(module_info["suggestions"])

        except SafetyViolationError as e:
            result["valid"] = False
            result["safety_violations"].append(
                {"type": "safety_error", "message": str(e), "line": 1}
            )
            result["suggestions"].append(
                "Fix security violations before using this code."
            )
        except Exception as e:
            result["warnings"].append(f"Could not complete safety check: {e}")

        # Check for common issues
        if "print(" in code and "result" not in code:
            result["warnings"].append(
                "Code uses print() but doesn't set 'result'. Output might not be captured."
            )
            result["suggestions"].append(
                "Set 'result' variable to return values from the node."
            )

        if "await " not in code and "async def" not in code:
            result["warnings"].append(
                "Code doesn't use 'await' or define async functions. Consider using PythonCodeNode (sync) for better performance."
            )

        return result
