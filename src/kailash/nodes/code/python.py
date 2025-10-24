"""Advanced Python Code Execution Node with Cycle Support.

This module provides sophisticated nodes for executing arbitrary Python code,
allowing users to create custom processing logic without defining new node classes.
It supports both function-based and class-based code execution with automatic type
inference, comprehensive error handling, and advanced cycle-aware capabilities.

Examples:
    Basic code execution:

    >>> node = PythonCodeNode(
    ...     name="processor",
    ...     code="result = {'value': input_value * 2, 'status': 'processed'}"
    ... )

    Cycle-aware execution:

    >>> cycle_node = PythonCodeNode(
    ...     name="accumulator",
    ...     code='''
    ...     # Safe cycle parameter access
    ...     try:
    ...         count = count
    ...         total = total
    ...     except NameError:
    ...         count = 0
    ...         total = 0
    ...
    ...     count += 1
    ...     total += input_value
    ...     average = total / count
    ...
    ...     result = {
    ...         'count': count,
    ...         'total': total,
    ...         'average': average,
    ...         'converged': average > 10.0
    ...     }
    ...     '''
    ... )

    Function integration:

    >>> def custom_processor(data: dict) -> dict:
    ...     return {'processed': data['value'] * 2}
    >>> node = PythonCodeNode.from_function(custom_processor)
"""

import ast
import importlib.util
import inspect
import json
import logging
import os
import resource
import traceback
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, get_type_hints

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    SafetyViolationError,
)
from kailash.security import (
    ExecutionTimeoutError,
    MemoryLimitError,
    SecurityConfig,
    execution_timeout,
    get_security_config,
    validate_node_parameters,
)

logger = logging.getLogger(__name__)

# Import shared constants and utilities
from kailash.nodes.code.common import (
    ALLOWED_BUILTINS,
    ALLOWED_MODULES,
    COMPLETELY_BLOCKED_MODULES,
    DANGEROUS_GLOBAL_FUNCTIONS,
    DANGEROUS_MODULE_FUNCTIONS,
    ensure_json_serializable,
    format_dangerous_function_error,
    format_module_not_allowed_error,
    is_dangerous_function,
)


class SafeCodeChecker(ast.NodeVisitor):
    """AST visitor to check code safety.

    This class analyzes Python code to detect potentially dangerous operations
    before execution. It helps prevent security vulnerabilities and system abuse.
    """

    def __init__(self):
        self.violations = []
        self.imports_found = []

    def visit_Import(self, node):
        """Check import statements."""
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            self.imports_found.append(module_name)
            if module_name not in ALLOWED_MODULES:
                self.violations.append(
                    {
                        "type": "import",
                        "module": module_name,
                        "line": node.lineno,
                        "message": f"Import of module '{module_name}' is not allowed",
                    }
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Check from imports."""
        if node.module:
            module_name = node.module.split(".")[0]
            self.imports_found.append(module_name)
            if module_name not in ALLOWED_MODULES:
                self.violations.append(
                    {
                        "type": "import_from",
                        "module": module_name,
                        "line": node.lineno,
                        "message": f"Import from module '{module_name}' is not allowed",
                    }
                )
            else:
                # Check for dangerous function imports from allowed modules
                dangerous_imports = {
                    "os": {"system", "popen", "execv", "execl", "spawn"},
                    "subprocess": {"run", "call", "check_call", "Popen"},
                    "__builtin__": {"eval", "exec", "compile", "__import__"},
                    "builtins": {"eval", "exec", "compile", "__import__"},
                }

                if module_name in dangerous_imports:
                    for alias in node.names:
                        import_name = alias.name
                        if import_name in dangerous_imports[module_name]:
                            self.violations.append(
                                {
                                    "type": "dangerous_import",
                                    "module": module_name,
                                    "function": import_name,
                                    "line": node.lineno,
                                    "message": f"Import of dangerous function '{import_name}' from module '{module_name}' is not allowed",
                                }
                            )
        self.generic_visit(node)

    def visit_Call(self, node):
        """Check function calls."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            # Check for dangerous built-in functions and imported dangerous functions
            dangerous_functions = {
                "eval",
                "exec",
                "compile",  # Built-in dangerous functions
                "system",
                "popen",  # os module dangerous functions
                "__import__",  # Dynamic import function
            }
            if func_name in dangerous_functions:
                self.violations.append(
                    {
                        "type": "function_call",
                        "function": func_name,
                        "line": node.lineno,
                        "message": f"Call to '{func_name}' is not allowed",
                    }
                )
        elif isinstance(node.func, ast.Attribute):
            # Check for dangerous method calls
            if node.func.attr in {"system", "popen"}:
                self.violations.append(
                    {
                        "type": "method_call",
                        "method": node.func.attr,
                        "line": node.lineno,
                        "message": f"Call to method '{node.func.attr}' is not allowed",
                    }
                )
        self.generic_visit(node)


class CodeExecutor:
    """Safe executor for Python code.

    This class provides a sandboxed environment for executing arbitrary Python code
    with proper error handling and resource management. It supports both string-based
    code and function/class objects.

    Design Purpose:
    - Isolate code execution from the main system
    - Provide comprehensive error reporting
    - Support dynamic code loading and execution
    - Enable code inspection and analysis

    Security Considerations:
    - Limited module imports (configurable whitelist)
    - AST-based code safety checking
    - Restricted built-in functions
    - Execution timeout (future enhancement)
    - Memory limits (future enhancement)
    """

    def __init__(
        self,
        allowed_modules: list[str] | None = None,
        security_config: SecurityConfig | None = None,
    ):
        """Initialize the code executor.

        Args:
            allowed_modules: List of module names allowed for import.
                           Defaults to common data processing modules.
            security_config: Security configuration for execution limits.
        """
        self.allowed_modules = set(allowed_modules or ALLOWED_MODULES)
        self.security_config = security_config or get_security_config()
        # Use shared builtin whitelist for consistency
        self.allowed_builtins = ALLOWED_BUILTINS
        self._execution_namespace = {}

    def check_code_safety(self, code: str) -> tuple[bool, list[dict], list[str]]:
        """Check if code is safe to execute.

        Args:
            code: Python code to check

        Returns:
            Tuple of (is_safe, violations, imports_found)

        Raises:
            SafetyViolationError: If code contains unsafe operations
        """
        try:
            tree = ast.parse(code)
            checker = SafeCodeChecker()
            checker.visit(tree)

            if checker.violations:
                # Create detailed error message with suggestions
                error_parts = []
                suggestions = []

                for violation in checker.violations:
                    error_parts.append(
                        f"Line {violation['line']}: {violation['message']}"
                    )

                    # Add suggestions based on violation type
                    if violation["type"] in ["import", "import_from"]:
                        module = violation["module"]
                        suggestions.append(
                            f"Module '{module}' is not allowed. Available modules: {', '.join(sorted(ALLOWED_MODULES))}"
                        )

                        # Suggest alternatives for common cases
                        if module == "subprocess":
                            suggestions.append(
                                "For file operations, use 'os' or 'pathlib' modules instead"
                            )
                        elif module == "requests":
                            suggestions.append(
                                "For HTTP requests, use HTTPRequestNode instead of importing requests"
                            )
                        elif module == "sqlite3" or module == "psycopg2":
                            suggestions.append(
                                "For database operations, use SQLDatabaseNode instead"
                            )
                        elif module == "boto3":
                            suggestions.append(
                                "For AWS operations, create a custom node or use existing cloud nodes"
                            )

                    elif violation["type"] == "function_call":
                        func = violation["function"]
                        if func in ["eval", "exec"]:
                            suggestions.append(
                                f"'{func}' is dangerous. Write explicit code instead of dynamic execution"
                            )
                        elif func == "compile":
                            suggestions.append(
                                "'compile' is not allowed. Use standard Python code instead"
                            )

                error_msg = "Code safety violations found:\n" + "\n".join(error_parts)
                if suggestions:
                    error_msg += "\n\nSuggestions:\n" + "\n".join(
                        f"- {s}" for s in suggestions
                    )

                raise SafetyViolationError(error_msg)

            return True, checker.violations, checker.imports_found

        except SyntaxError as e:
            raise NodeExecutionError(
                f"Invalid Python syntax at line {e.lineno}: {e.msg}\n"
                f"Text: {e.text}\n"
                f"Error position: {' ' * (e.offset - 1) if e.offset else ''}^"
            )

    def execute_code(
        self, code: str, inputs: dict[str, Any], node_instance=None
    ) -> dict[str, Any]:
        """Execute Python code with given inputs.

        Args:
            code: Python code to execute
            inputs: Dictionary of input variables

        Returns:
            Dictionary of variables after execution

        Raises:
            NodeExecutionError: If code execution fails
            ExecutionTimeoutError: If execution exceeds timeout
            MemoryLimitError: If memory usage exceeds limit
        """
        # Check code safety first
        is_safe, violations, imports_found = self.check_code_safety(code)

        # Sanitize inputs with python_exec context
        # Python code execution via exec() does not need shell metacharacter sanitization
        sanitized_inputs = validate_node_parameters(
            inputs, self.security_config, context="python_exec"
        )

        # Create isolated namespace
        import builtins

        namespace = {
            "__builtins__": {
                name: getattr(builtins, name)
                for name in self.allowed_builtins
                if hasattr(builtins, name)
            }
        }

        # Add allowed modules
        # Check if we're running under coverage to avoid instrumentation conflicts
        import sys

        if "coverage" in sys.modules:
            # Under coverage, use lazy loading for problematic modules
            problematic_modules = {
                "numpy",
                "scipy",
                "sklearn",
                "pandas",
                "matplotlib",
                "seaborn",
                "plotly",
                "array",
            }
            safe_modules = self.allowed_modules - problematic_modules

            # Eagerly load safe modules
            for module_name in safe_modules:
                try:
                    module = importlib.import_module(module_name)
                    namespace[module_name] = module
                except ImportError:
                    logger.warning(f"Module {module_name} not available")

            # Add lazy loader for problematic modules
            class LazyModuleLoader:
                def __getattr__(self, name):
                    if name in problematic_modules:
                        return importlib.import_module(name)
                    raise AttributeError(f"Module {name} not found")

            # Make problematic modules available through lazy loading
            for module_name in problematic_modules:
                try:
                    # Try to import the module directly
                    module = importlib.import_module(module_name)
                    namespace[module_name] = module
                except ImportError:
                    # If import fails, use lazy loader as fallback
                    namespace[module_name] = LazyModuleLoader()
        else:
            # Normal operation - eagerly load all modules
            for module_name in self.allowed_modules:
                try:
                    # Skip scipy in CI due to version conflicts
                    if module_name == "scipy" and os.environ.get("CI"):
                        logger.warning("Skipping scipy import in CI environment")
                        continue
                    module = importlib.import_module(module_name)
                    namespace[module_name] = module
                except ImportError:
                    logger.warning(f"Module {module_name} not available")

        # Add global utility functions to namespace
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
                "Could not import data path utilities - functions will not be available in PythonCodeNode execution"
            )

        # Add workflow context functions if node instance is available
        if node_instance and hasattr(node_instance, "get_workflow_context"):
            # Bind the actual node methods
            namespace["get_workflow_context"] = node_instance.get_workflow_context
            namespace["set_workflow_context"] = node_instance.set_workflow_context
        else:
            # Fail fast instead of silent defaults - prevents subtle bugs
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

        # NOTE: Inputs are NOT added to global namespace
        # They are added to local_namespace below to prevent variable persistence

        try:
            # Set memory limit if supported (Unix systems)
            if hasattr(resource, "RLIMIT_AS") and self.security_config.memory_limit:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (
                            self.security_config.memory_limit,
                            self.security_config.memory_limit,
                        ),
                    )
                except (OSError, ValueError):
                    logger.warning(
                        "Could not set memory limit - continuing without limit"
                    )

            # Execute with timeout using separate global and local namespaces
            # This prevents variable persistence across executions (CRITICAL FIX)
            # See: SDK Bug Report - PythonCodeNode Variable Persistence
            local_namespace = {}
            local_namespace.update(sanitized_inputs)

            with execution_timeout(
                self.security_config.execution_timeout, self.security_config
            ):
                # Use separate globals (namespace) and locals (local_namespace)
                # This ensures complete variable isolation between executions
                exec(code, namespace, local_namespace)

            # Return all non-private variables from LOCAL namespace only
            # Variables from previous executions cannot leak through
            # NEW: Also filter out imported modules to prevent serialization errors
            import types

            return {
                k: v
                for k, v in local_namespace.items()
                if not k.startswith("_") and not isinstance(v, types.ModuleType)
            }
        except ExecutionTimeoutError:
            raise
        except MemoryLimitError:
            raise
        except Exception as e:
            error_msg = f"Code execution failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise NodeExecutionError(error_msg)

    def execute_function(self, func: Callable, inputs: dict[str, Any]) -> Any:
        """Execute a Python function with given inputs.

        Args:
            func: Function to execute
            inputs: Dictionary of input arguments

        Returns:
            Function return value

        Raises:
            NodeExecutionError: If function execution fails
        """
        # Sanitize inputs for security with python_exec context
        # Python function execution does not need shell metacharacter sanitization
        sanitized_inputs = validate_node_parameters(
            inputs, self.security_config, context="python_exec"
        )

        try:
            # Get function signature
            sig = inspect.signature(func)

            # Map inputs to function parameters
            kwargs = {}
            extra_kwargs = {}

            # Check if function accepts **kwargs
            accepts_var_keyword = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in sig.parameters.values()
            )

            for param_name, param in sig.parameters.items():
                if param.kind == inspect.Parameter.VAR_KEYWORD:
                    # This is **kwargs parameter, skip it
                    continue
                elif param_name in sanitized_inputs:
                    kwargs[param_name] = sanitized_inputs[param_name]
                elif param.default is not param.empty:
                    # Use default value
                    continue
                else:
                    raise NodeExecutionError(
                        f"Missing required parameter: {param_name}"
                    )

            # Collect extra parameters if function accepts **kwargs
            if accepts_var_keyword:
                for key, value in sanitized_inputs.items():
                    if key not in kwargs:
                        extra_kwargs[key] = value

                # Merge regular kwargs and extra kwargs
                kwargs.update(extra_kwargs)

            # Execute function
            return func(**kwargs)

        except Exception as e:
            error_msg = f"Function execution failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise NodeExecutionError(error_msg)

    def _ensure_serializable(self, data: Any) -> Any:
        """Ensure data is JSON-serializable following AsyncSQL pattern."""
        if data is None:
            return None
        elif isinstance(data, (str, int, float, bool)):
            return data
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, dict):
            return {k: self._ensure_serializable(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._ensure_serializable(item) for item in data]
        else:
            try:
                json.dumps(data)
                return data
            except (TypeError, ValueError):
                # Check if object has .to_dict() method for enhanced validation
                if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
                    try:
                        # Convert object to dict using its to_dict() method
                        dict_result = data.to_dict()
                        # Recursively ensure the dict result is also serializable
                        return self._ensure_json_serializable(dict_result)
                    except (TypeError, ValueError, AttributeError):
                        # If .to_dict() exists but fails, fall back to string
                        return str(data)
                return str(data)


class FunctionWrapper:
    """Wrapper for converting Python functions to nodes.

    This class analyzes a Python function's signature and creates a node
    that can execute the function within a workflow. It handles type inference,
    parameter validation, and error management.

    Example:
        def process(data: pd.DataFrame) -> pd.DataFrame:
            return data.dropna()

        wrapper = FunctionWrapper(process)
        node = wrapper.to_node(name="dropna_processor")
    """

    def __init__(self, func: Callable, executor: CodeExecutor | None = None):
        """Initialize the function wrapper.

        Args:
            func: Python function to wrap
            executor: Code executor instance (optional)
        """
        self.func = func
        self.executor = executor or CodeExecutor()
        self.signature = inspect.signature(func)
        self.name = func.__name__
        self.doc = inspect.getdoc(func) or ""
        try:
            self.type_hints = get_type_hints(func)
        except (NameError, TypeError):
            # Handle cases where type hints can't be resolved
            self.type_hints = {}

    def _ensure_serializable(self, data: Any) -> Any:
        """Ensure data is JSON-serializable."""
        if data is None:
            return None
        elif isinstance(data, (str, int, float, bool)):
            return data
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, dict):
            return {k: self._ensure_serializable(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._ensure_serializable(item) for item in data]
        else:
            try:
                json.dumps(data)
                return data
            except (TypeError, ValueError):
                # Check if object has .to_dict() method for enhanced validation
                if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
                    try:
                        # Convert object to dict using its to_dict() method
                        dict_result = data.to_dict()
                        # Recursively ensure the dict result is also serializable
                        return self._ensure_json_serializable(dict_result)
                    except (TypeError, ValueError, AttributeError):
                        # If .to_dict() exists but fails, fall back to string
                        return str(data)
                return str(data)

    def get_input_types(self) -> dict[str, type]:
        """Extract input types from function signature.

        Returns:
            Dictionary mapping parameter names to types
        """
        input_types = {}
        for param_name, param in self.signature.parameters.items():
            # Skip self parameter for class methods
            if param_name == "self":
                continue

            # Skip **kwargs parameter - it's handled separately
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue

            param_type = self.type_hints.get(param_name, Any)
            input_types[param_name] = param_type
        return input_types

    def get_parameter_info(self) -> dict[str, dict[str, Any]]:
        """Extract detailed parameter information including defaults.

        Returns:
            Dictionary mapping parameter names to info dict with 'type' and 'has_default'
        """
        param_info = {}
        for param_name, param in self.signature.parameters.items():
            # Skip self parameter for class methods
            if param_name == "self":
                continue

            # Skip **kwargs parameter - it's handled separately
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue

            param_info[param_name] = {
                "type": self.type_hints.get(param_name, Any),
                "has_default": param.default is not param.empty,
                "default": param.default if param.default is not param.empty else None,
            }
        return param_info

    def accepts_var_keyword(self) -> bool:
        """Check if function accepts **kwargs."""
        return any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in self.signature.parameters.values()
        )

    def get_output_type(self) -> type:
        """Extract output type from function signature.

        Returns:
            Return type annotation or Any.
        """
        return self.type_hints.get("return", Any)

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the wrapped function with proper serialization."""
        result = self.executor.execute_function(self.func, inputs)

        # Ensure JSON serializability inline
        result = self._ensure_json_serializable(result)

        # Smart wrapping: only wrap if result doesn't already have expected structure
        # If function already returns {"result": value}, don't double-wrap
        if isinstance(result, dict) and len(result) == 1 and "result" in result:
            # Function already returned properly formatted result
            return result
        else:
            # Wrap result for consistent schema validation
            return {"result": result}

    def _ensure_json_serializable(self, data: Any) -> Any:
        """Convert data to JSON-serializable format."""
        if data is None:
            return None
        elif isinstance(data, (str, int, float, bool)):
            return data
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, dict):
            return {k: self._ensure_json_serializable(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._ensure_json_serializable(item) for item in data]
        else:
            try:
                json.dumps(data)
                return data
            except (TypeError, ValueError):
                # Check if object has .to_dict() method for enhanced validation
                if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
                    try:
                        # Convert object to dict using its to_dict() method
                        dict_result = data.to_dict()
                        # Recursively ensure the dict result is also serializable
                        return self._ensure_json_serializable(dict_result)
                    except (TypeError, ValueError, AttributeError):
                        # If .to_dict() exists but fails, fall back to string
                        return str(data)
                return str(data)

    def to_node(
        self,
        name: str | None = None,
        description: str | None = None,
        input_schema: dict[str, "NodeParameter"] | None = None,
        output_schema: dict[str, "NodeParameter"] | None = None,
    ) -> "PythonCodeNode":
        """Convert function to a PythonCodeNode.

        Args:
            name: Node name (defaults to function name)
            description: Node description (defaults to function docstring)
            input_schema: Explicit input parameter schema for validation
            output_schema: Explicit output parameter schema for validation

        Returns:
            PythonCodeNode instance
        """
        return PythonCodeNode(
            name=name or self.name,
            function=self.func,
            description=description or self.doc,
            input_types=self.get_input_types(),
            output_type=self.get_output_type(),
            input_schema=input_schema,
            output_schema=output_schema,
        )


class ClassWrapper:
    """Wrapper for converting Python classes to stateful nodes.

    This class analyzes a Python class and creates a node that maintains
    state between executions. Useful for complex processing that requires
    initialization or accumulated state.

    Example:
        class Accumulator:
            def __init__(self):
                self.total = 0

            def process(self, value: float) -> float:
                self.total += value
                return self.total

        wrapper = ClassWrapper(Accumulator)
        node = wrapper.to_node(name="accumulator")
    """

    def __init__(
        self,
        cls: type,
        method_name: str | None = None,
        executor: CodeExecutor | None = None,
    ):
        """Initialize the class wrapper.

        Args:
            cls: Python class to wrap
            method_name: Method name to call (auto-detected if not provided)
            executor: Code executor instance (optional)
        """
        self.cls = cls
        self.method_name = method_name
        self.executor = executor or CodeExecutor()
        self.name = cls.__name__
        self.doc = inspect.getdoc(cls) or ""
        self.instance = None
        self._analyze_class()

    def _analyze_class(self):
        """Analyze class structure to find processing method."""
        if self.method_name:
            # Use provided method name
            if not hasattr(self.cls, self.method_name):
                raise NodeConfigurationError(
                    f"Class {self.name} has no method '{self.method_name}'"
                )
            self.process_method = self.method_name
        else:
            # Look for common method names
            process_methods = ["process", "execute", "run", "transform", "__call__"]

            self.process_method = None
            for method_name in process_methods:
                if hasattr(self.cls, method_name):
                    method = getattr(self.cls, method_name)
                    if callable(method) and not method_name.startswith("_"):
                        self.process_method = method_name
                        break

            if not self.process_method:
                raise NodeConfigurationError(
                    f"Class {self.name} must have a process method "
                    f"(one of: {', '.join(process_methods)})"
                )

        # Get method and signature
        method = getattr(self.cls, self.process_method)
        if not method:
            raise NodeConfigurationError(
                f"Class {self.name} does not have method '{self.process_method}'"
            )

        self.method = method
        self.signature = inspect.signature(method)

        # Get type hints
        try:
            self.type_hints = get_type_hints(method)
        except (TypeError, NameError):
            # Handle descriptor objects like properties
            self.type_hints = {}

    def _ensure_serializable(self, data: Any) -> Any:
        """Ensure data is JSON-serializable."""
        if data is None:
            return None
        elif isinstance(data, (str, int, float, bool)):
            return data
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, dict):
            return {k: self._ensure_serializable(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._ensure_serializable(item) for item in data]
        else:
            try:
                json.dumps(data)
                return data
            except (TypeError, ValueError):
                # Check if object has .to_dict() method for enhanced validation
                if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
                    try:
                        # Convert object to dict using its to_dict() method
                        dict_result = data.to_dict()
                        # Recursively ensure the dict result is also serializable
                        return self._ensure_json_serializable(dict_result)
                    except (TypeError, ValueError, AttributeError):
                        # If .to_dict() exists but fails, fall back to string
                        return str(data)
                return str(data)

    def get_input_types(self) -> dict[str, type]:
        """Extract input types from method signature."""
        input_types = {}
        for param_name, param in self.signature.parameters.items():
            # Skip self parameter
            if param_name == "self":
                continue

            param_type = self.type_hints.get(param_name, Any)
            input_types[param_name] = param_type
        return input_types

    def get_parameter_info(self) -> dict[str, dict[str, Any]]:
        """Extract detailed parameter information including defaults.

        Returns:
            Dictionary mapping parameter names to info dict with 'type' and 'has_default'
        """
        param_info = {}
        for param_name, param in self.signature.parameters.items():
            # Skip self parameter
            if param_name == "self":
                continue

            # Skip **kwargs parameter - it's handled separately
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue

            param_info[param_name] = {
                "type": self.type_hints.get(param_name, Any),
                "has_default": param.default is not param.empty,
                "default": param.default if param.default is not param.empty else None,
            }
        return param_info

    def accepts_var_keyword(self) -> bool:
        """Check if method accepts **kwargs."""
        return any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in self.signature.parameters.values()
        )

    def get_output_type(self) -> type:
        """Extract output type from method signature."""
        return self.type_hints.get("return", Any)

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the wrapped method."""
        # Create instance if needed
        if self.instance is None:
            try:
                self.instance = self.cls()
            except Exception as e:
                raise NodeExecutionError(
                    f"Failed to create instance of {self.cls.__name__}: {e}"
                ) from e

        # Get the method from the instance
        method = getattr(self.instance, self.process_method)

        # Execute the method
        result = self.executor.execute_function(method, inputs)

        # Ensure JSON serializability inline
        result = self._ensure_json_serializable(result)

        # Smart wrapping: only wrap non-dict results in "result" key
        # Dict results are returned as-is to avoid double wrapping
        if not isinstance(result, dict):
            result = {"result": result}
        # Dict results are already properly structured, no wrapping needed

        return result

    def _ensure_json_serializable(self, data: Any) -> Any:
        """Convert data to JSON-serializable format."""
        if data is None:
            return None
        elif isinstance(data, (str, int, float, bool)):
            return data
        elif isinstance(data, (datetime, date)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, dict):
            return {k: self._ensure_json_serializable(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._ensure_json_serializable(item) for item in data]
        else:
            try:
                json.dumps(data)
                return data
            except (TypeError, ValueError):
                # Check if object has .to_dict() method for enhanced validation
                if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
                    try:
                        # Convert object to dict using its to_dict() method
                        dict_result = data.to_dict()
                        # Recursively ensure the dict result is also serializable
                        return self._ensure_json_serializable(dict_result)
                    except (TypeError, ValueError, AttributeError):
                        # If .to_dict() exists but fails, fall back to string
                        return str(data)
                return str(data)

    def to_node(
        self,
        name: str | None = None,
        description: str | None = None,
        input_schema: dict[str, "NodeParameter"] | None = None,
        output_schema: dict[str, "NodeParameter"] | None = None,
    ) -> "PythonCodeNode":
        """Convert class to a PythonCodeNode.

        Args:
            name: Node name (defaults to class name)
            description: Node description (defaults to class docstring)
            input_schema: Explicit input parameter schema for validation
            output_schema: Explicit output parameter schema for validation

        Returns:
            PythonCodeNode instance
        """
        return PythonCodeNode(
            name=name or self.name,
            class_type=self.cls,
            process_method=self.process_method,
            description=description or self.doc,
            input_schema=input_schema,
            output_schema=output_schema,
        )


@register_node()
class PythonCodeNode(Node):
    """Node for executing arbitrary Python code.

    This node allows users to execute custom Python code within a workflow.
    It supports multiple input methods:
    1. Direct code string execution
    2. Function wrapping
    3. Class wrapping
    4. File-based code loading

    Design Purpose:
    - Provide maximum flexibility for custom logic
    - Bridge gap between predefined nodes and custom requirements
    - Enable rapid prototyping without node development
    - Support both stateless and stateful processing

    Key Features:
    - Type inference from function signatures
    - Safe code execution with error handling
    - Support for external libraries
    - State management for class-based nodes
    - AST-based security validation

    IMPORTANT - Variable Access Pattern:
    When using PythonCodeNode with code strings, input parameters are directly
    available as variables in the execution namespace. Do NOT try to access them
    through an 'inputs' dictionary or use locals()/dir() to check for them.

    Correct pattern:
        # If 'query' is passed as an input parameter, it's directly available
        result = {'processed': query.upper()}  # Direct access to 'query'

    Incorrect patterns:
        # These will NOT work:
        query = inputs.get('query', '')  # 'inputs' dict doesn't exist
        query = locals().get('query', '')  # locals() is restricted
        if 'query' in dir():  # dir() is restricted

    The node supports two output patterns:
    1. Single output: Set a 'result' variable with your output data
    2. Multiple outputs: Define multiple variables - all become available as outputs

    Examples:
        # Single output (traditional pattern)
        result = {"processed_data": data}

        # Multiple outputs (NEW - more flexible!)
        filter_data = {"id": "user-123"}
        fields_data = {"name": "Updated"}
        status = "success"

    Example:
        >>> # Function-based node
        >>> def custom_filter(data: pd.DataFrame, threshold: float) -> pd.DataFrame:
        ...     return data[data['value'] > threshold]

        >>> node = PythonCodeNode.from_function(
        ...     func=custom_filter,
        ...     name="threshold_filter"
        ... )

        >>> # Class-based stateful node
        >>> class MovingAverage:
        ...     def __init__(self, window_size: int = 3):
        ...         self.window_size = window_size
        ...         self.values = []
        ...
        ...     def process(self, value: float) -> float:
        ...         self.values.append(value)
        ...         if len(self.values) > self.window_size:
        ...             self.values.pop(0)
        ...         return sum(self.values) / len(self.values)

        >>> node = PythonCodeNode.from_class(
        ...     cls=MovingAverage,
        ...     name="moving_avg"
        ... )

        >>> # Code string node
        >>> code = '''
        ... result = []
        ... for item in data:
        ...     if item > threshold:
        ...         result.append(item * 2)
        ... '''

        >>> node = PythonCodeNode(
        ...     name="custom_processor",
        ...     code=code,
        ...     input_types={'data': list, 'threshold': float},
        ...     output_type=list
        ... )
    """

    def __init__(
        self,
        name: str,
        code: str | None = None,
        function: Callable | None = None,
        class_type: type | None = None,
        process_method: str | None = None,
        input_types: dict[str, type] | None = None,
        output_type: type | None = None,
        input_schema: dict[str, "NodeParameter"] | None = None,
        output_schema: dict[str, "NodeParameter"] | None = None,
        description: str | None = None,
        max_code_lines: int = 10,
        validate_security: bool = False,
        **kwargs,
    ):
        """Initialize a Python code node.

        Args:
            name: Node name
            code: Python code string to execute
            function: Python function to wrap
            class_type: Python class to instantiate
            process_method: Method name for class-based execution
            input_types: Dictionary of input names to types
            output_type: Expected output type
            input_schema: Explicit input parameter schema for validation
            output_schema: Explicit output parameter schema for validation
            description: Node description
            max_code_lines: Maximum lines before warning (default: 10)
            validate_security: If True, validate code security at creation time (default: False)
            **kwargs: Additional node parameters
        """
        # Validate inputs
        if not any([code, function, class_type]):
            raise NodeConfigurationError(
                "Must provide either code string, function, or class"
            )

        if sum([bool(code), bool(function), bool(class_type)]) > 1:
            raise NodeConfigurationError(
                "Can only provide one of: code, function, or class"
            )

        self.code = code
        self.function = function
        self.class_type = class_type
        self.process_method = process_method
        self.input_types = input_types or {}
        self.output_type = output_type or Any
        self._input_schema = input_schema
        self._output_schema = output_schema
        self.max_code_lines = max_code_lines

        # Check code length and warn if exceeds threshold
        if self.code and self.max_code_lines > 0:
            code_lines = [
                line for line in self.code.strip().split("\n") if line.strip()
            ]
            if len(code_lines) > self.max_code_lines:
                logger.warning(
                    f"PythonCodeNode '{name}' contains {len(code_lines)} lines of code, "
                    f"exceeding the recommended maximum of {self.max_code_lines} lines. "
                    "Consider using PythonCodeNode.from_function() or from_file() for better "
                    "code organization and IDE support."
                )

        # For class-based nodes, maintain instance
        self.instance = None
        if self.class_type:
            self.instance = self.class_type()

        # Initialize executor
        self.executor = CodeExecutor()

        # Validate code security if requested
        if validate_security and self.code:
            self.executor.check_code_safety(self.code)

        # Create metadata (avoiding conflicts with kwargs)
        if "metadata" not in kwargs:
            kwargs["metadata"] = NodeMetadata(
                id=name.replace(" ", "_").lower(),
                name=name,
                description=description or "Custom Python code node",
                tags={"custom", "python", "code"},
                version="1.0.0",
            )

        # Pass kwargs to parent
        super().__init__(**kwargs)

    def _validate_config(self):
        """Override config validation for dynamic parameters.

        PythonCodeNode has dynamic parameters based on the wrapped function/class,
        so we skip the base class validation at initialization time.
        """
        # Skip validation for python code nodes to avoid complex type issues
        if not hasattr(self, "_skip_validation"):
            self._skip_validation = True

    def get_parameters(self) -> dict[str, "NodeParameter"]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary mapping parameter names to their definitions
        """
        # Use explicit input schema if provided
        if self._input_schema:
            return self._input_schema

        # Otherwise, generate schema from input types or function/class analysis
        parameters = {}

        # Add parameters from input_types
        for name, type_ in self.input_types.items():
            # Use Any type for complex types to avoid validation issues
            param_type = Any if hasattr(type_, "__origin__") else type_

            parameters[name] = NodeParameter(
                name=name,
                type=param_type,
                required=True,
                description=f"Input parameter {name}",
            )

        # If we have a function/class, extract parameter info
        # This overrides the basic input_types to include default parameter information
        if self.function:
            wrapper = FunctionWrapper(self.function, self.executor)
            for name, param_info in wrapper.get_parameter_info().items():
                # Use Any type for complex types to avoid validation issues
                param_type = param_info["type"]
                param_type = Any if hasattr(param_type, "__origin__") else param_type

                # Override existing parameter or add new one with correct required flag
                parameters[name] = NodeParameter(
                    name=name,
                    type=param_type,
                    required=not param_info[
                        "has_default"
                    ],  # Fixed: respect default values
                    description=f"Input parameter {name}",
                    default=(
                        param_info["default"] if param_info["has_default"] else None
                    ),
                )
        elif self.class_type and self.process_method:
            wrapper = ClassWrapper(
                self.class_type, self.process_method or "process", self.executor
            )
            for name, param_info in wrapper.get_parameter_info().items():
                # Use Any type for complex types to avoid validation issues
                param_type = param_info["type"]
                param_type = Any if hasattr(param_type, "__origin__") else param_type

                # Override existing parameter or add new one with correct required flag
                parameters[name] = NodeParameter(
                    name=name,
                    type=param_type,
                    required=not param_info[
                        "has_default"
                    ],  # Fixed: respect default values
                    description=f"Input parameter {name}",
                    default=(
                        param_info["default"] if param_info["has_default"] else None
                    ),
                )

        return parameters

    def validate_inputs(self, **kwargs) -> dict[str, Any]:
        """Validate runtime inputs.

        For code-based nodes, we accept any inputs since the code
        can use whatever variables it needs.

        Args:
            **kwargs: Runtime inputs

        Returns:
            All inputs as-is for code nodes, validated inputs for function/class nodes
        """
        # If using code string, pass through all inputs
        if self.code:
            return kwargs

        # Check if function/class accepts **kwargs
        accepts_var_keyword = False
        if self.function:
            wrapper = FunctionWrapper(self.function, self.executor)
            accepts_var_keyword = wrapper.accepts_var_keyword()
        elif self.class_type:
            wrapper = ClassWrapper(
                self.class_type, self.process_method or "process", self.executor
            )
            accepts_var_keyword = wrapper.accepts_var_keyword()

        # If function accepts **kwargs, pass through all inputs
        if accepts_var_keyword:
            return kwargs

        # Otherwise use standard validation for function/class nodes
        return super().validate_inputs(**kwargs)

    def get_output_schema(self) -> dict[str, "NodeParameter"]:
        """Define output parameters for this node.

        Returns:
            Dictionary mapping output names to their parameter definitions
        """
        # Return explicit output schema if provided
        if self._output_schema:
            return self._output_schema

        # NEW: Dynamic output schema - 'result' is optional
        # This allows code to export multiple variables directly
        # Example: filter_data = {...}; fields_data = {...}
        # Both filter_data and fields_data become available outputs
        return {
            "result": NodeParameter(
                name="result",
                type=Any,  # Use Any instead of self.output_type to avoid validation issues
                required=False,  # CHANGED: Allow code to export other variables
                description="Primary output result (optional - code can export multiple variables)",
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic.

        Args:
            **kwargs: Validated input data

        Returns:
            Dictionary of outputs
        """
        try:
            if self.code:
                # Execute code string
                outputs = self.executor.execute_code(
                    self.code, kwargs, node_instance=self
                )
                # Return 'result' variable if it exists, otherwise all outputs
                if "result" in outputs:
                    return {"result": outputs["result"]}
                return outputs

            elif self.function:
                # Execute function
                wrapper = FunctionWrapper(self.function, self.executor)
                result = wrapper.execute(kwargs)
                # FunctionWrapper.execute() already handles result wrapping
                return result

            elif self.class_type:
                # Execute class method
                wrapper = ClassWrapper(
                    self.class_type, self.process_method or "process", self.executor
                )
                return wrapper.execute(kwargs)

            else:
                raise NodeExecutionError("No execution method available")

        except NodeExecutionError:
            raise
        except ImportError as e:
            # Enhanced import error handling
            module_name = str(e).split("'")[1] if "'" in str(e) else "unknown"
            error_msg = f"Import error: {str(e)}\n\n"

            # Check if module is in allowed list
            if module_name not in ALLOWED_MODULES:
                error_msg += f"Module '{module_name}' is not in the allowed list.\n"
                error_msg += (
                    f"Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}\n\n"
                )

                # Suggest alternatives
                if module_name == "requests":
                    error_msg += "Suggestion: Use HTTPRequestNode for HTTP requests instead of importing requests.\n"
                elif module_name in ["sqlite3", "psycopg2", "pymongo"]:
                    error_msg += (
                        "Suggestion: Use SQLDatabaseNode for database operations.\n"
                    )
                elif module_name == "boto3":
                    error_msg += "Suggestion: Create a custom node for AWS operations or use cloud-specific nodes.\n"
            else:
                error_msg += f"Module '{module_name}' is allowed but not installed.\n"
                error_msg += "Suggestion: Install the module using pip or check your environment.\n"

            raise NodeExecutionError(error_msg)
        except Exception as e:
            logger.error(f"Python code execution failed: {e}")
            raise NodeExecutionError(f"Execution failed: {str(e)}")

    @classmethod
    def from_function(
        cls,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        input_schema: dict[str, "NodeParameter"] | None = None,
        output_schema: dict[str, "NodeParameter"] | None = None,
        **kwargs,
    ) -> "PythonCodeNode":
        """Create a node from a Python function.

        Args:
            func: Python function to wrap
            name: Node name (defaults to function name)
            description: Node description
            input_schema: Explicit input parameter schema for validation
            output_schema: Explicit output parameter schema for validation
            **kwargs: Additional node parameters

        Returns:
            PythonCodeNode instance
        """
        # Extract type information
        wrapper = FunctionWrapper(func, CodeExecutor())
        input_types = wrapper.get_input_types()
        output_type = wrapper.get_output_type()

        return cls(
            name=name or func.__name__,
            function=func,
            input_types=input_types,
            output_type=output_type,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description or func.__doc__,
            **kwargs,
        )

    @classmethod
    def from_class(
        cls,
        class_type: type,
        process_method: str | None = None,
        name: str | None = None,
        description: str | None = None,
        input_schema: dict[str, "NodeParameter"] | None = None,
        output_schema: dict[str, "NodeParameter"] | None = None,
        **kwargs,
    ) -> "PythonCodeNode":
        """Create a node from a Python class.

        Args:
            class_type: Python class to wrap
            process_method: Method name for processing (auto-detected if not provided)
            name: Node name (defaults to class name)
            description: Node description
            input_schema: Explicit input parameter schema for validation
            output_schema: Explicit output parameter schema for validation
            **kwargs: Additional node parameters

        Returns:
            PythonCodeNode instance
        """
        # Extract type information
        wrapper = ClassWrapper(class_type, process_method, CodeExecutor())
        input_types = wrapper.get_input_types()
        output_type = wrapper.get_output_type()

        return cls(
            name=name or class_type.__name__,
            class_type=class_type,
            process_method=wrapper.process_method,
            input_types=input_types,
            output_type=output_type,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description or class_type.__doc__,
            **kwargs,
        )

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        function_name: str | None = None,
        class_name: str | None = None,
        name: str | None = None,
        description: str | None = None,
        input_schema: dict[str, "NodeParameter"] | None = None,
        output_schema: dict[str, "NodeParameter"] | None = None,
    ) -> "PythonCodeNode":
        """Create a node from a Python file.

        Args:
            file_path: Path to Python file
            function_name: Function to use from file
            class_name: Class to use from file
            name: Node name
            description: Node description

        Returns:
            PythonCodeNode instance

        Raises:
            NodeConfigurationError: If file cannot be loaded
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise NodeConfigurationError(f"File not found: {file_path}")

        # Load module from file
        spec = importlib.util.spec_from_file_location("custom_module", file_path)
        if not spec or not spec.loader:
            raise NodeConfigurationError(f"Cannot load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Extract function or class
        if function_name:
            if not hasattr(module, function_name):
                raise NodeConfigurationError(
                    f"Function {function_name} not found in {file_path}"
                )
            func = getattr(module, function_name)
            return cls.from_function(
                func,
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
            )

        elif class_name:
            if not hasattr(module, class_name):
                raise NodeConfigurationError(
                    f"Class {class_name} not found in {file_path}"
                )
            class_type = getattr(module, class_name)
            return cls.from_class(
                class_type,
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
            )

        else:
            # Look for main function or first function
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and not attr_name.startswith("_"):
                    return cls.from_function(
                        attr,
                        name=name,
                        description=description,
                        input_schema=input_schema,
                        output_schema=output_schema,
                    )

            raise NodeConfigurationError(
                f"No suitable function or class found in {file_path}"
            )

    def execute_code(self, inputs: dict[str, Any]) -> Any:
        """Execute the code with given inputs.

        This is a convenience method that directly executes the code
        without going through the base node validation.

        Args:
            inputs: Dictionary of input values

        Returns:
            Result of code execution
        """
        # Execute directly based on execution type
        if self.code:
            outputs = self.executor.execute_code(self.code, inputs, node_instance=self)
            return outputs.get("result", outputs)
        elif self.function:
            wrapper = FunctionWrapper(self.function, self.executor)
            result = wrapper.execute(inputs)
            return result.get("result", result)
        elif self.class_type:
            wrapper = ClassWrapper(
                self.class_type, self.process_method or "process", self.executor
            )
            # Use the same instance for stateful behavior
            wrapper.instance = self.instance
            result = wrapper.execute(inputs)
            return result.get("result", result)
        else:
            raise NodeExecutionError("No execution method available")

    def get_config(self) -> dict[str, Any]:
        """Get node configuration for serialization.

        Returns:
            Configuration dictionary
        """
        # Get base config from parent class
        config = {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "version": self.metadata.version,
            "tags": list(self.metadata.tags) if self.metadata.tags else [],
        }

        # Add code-specific config
        config.update(
            {
                "code": self.code,
                "input_types": {
                    name: type_.__name__ if hasattr(type_, "__name__") else str(type_)
                    for name, type_ in self.input_types.items()
                },
                "output_type": (
                    self.output_type.__name__
                    if hasattr(self.output_type, "__name__")
                    else str(self.output_type)
                ),
            }
        )

        # For function/class nodes, include source code
        if self.function:
            config["function_source"] = inspect.getsource(self.function)
        elif self.class_type:
            config["class_source"] = inspect.getsource(self.class_type)
            config["process_method"] = self.process_method

        return config

    @staticmethod
    def list_allowed_modules() -> list[str]:
        """List all allowed modules for import in PythonCodeNode.

        Returns:
            Sorted list of allowed module names
        """
        return sorted(ALLOWED_MODULES)

    @staticmethod
    def check_module_availability(module_name: str) -> dict[str, Any]:
        """Check if a module is allowed and available for import.

        Args:
            module_name: Name of the module to check

        Returns:
            Dictionary with status information
        """
        result = {
            "module": module_name,
            "allowed": module_name in ALLOWED_MODULES,
            "installed": False,
            "importable": False,
            "error": None,
            "suggestions": [],
        }

        if not result["allowed"]:
            result["suggestions"].append(
                f"Module '{module_name}' is not in the allowed list."
            )
            result["suggestions"].append(
                f"Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}"
            )

            # Add specific suggestions for common modules
            if module_name == "requests":
                result["suggestions"].append(
                    "Use HTTPRequestNode for HTTP requests instead."
                )
            elif module_name in ["sqlite3", "psycopg2", "pymongo", "mysql"]:
                result["suggestions"].append(
                    "Use SQLDatabaseNode for database operations."
                )
            elif module_name == "boto3":
                result["suggestions"].append(
                    "Use cloud-specific nodes or create a custom node."
                )
            elif module_name == "subprocess":
                result["suggestions"].append(
                    "For security reasons, subprocess is not allowed. Use os or pathlib for file operations."
                )
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

    def validate_code(self, code: str) -> dict[str, Any]:
        """Validate Python code and provide detailed feedback.

        Args:
            code: Python code to validate

        Returns:
            Dictionary with validation results
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
            is_safe, violations, imports_found = self.executor.check_code_safety(code)
            result["imports"] = imports_found

            if violations:
                result["valid"] = False
                result["safety_violations"] = violations

                # Add suggestions from violations
                for violation in violations:
                    if violation["type"] in [
                        "import",
                        "import_from",
                        "dangerous_import",
                    ]:
                        module = violation.get("module", "unknown")
                        module_info = self.check_module_availability(module)
                        result["suggestions"].extend(module_info["suggestions"])

        except SafetyViolationError as e:
            # Safety violations should mark code as invalid, not just warnings
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

        if "input(" in code:
            result["warnings"].append("Code uses input() which will block execution.")
            result["suggestions"].append(
                "Use node parameters instead of input() for user input."
            )

        return result
