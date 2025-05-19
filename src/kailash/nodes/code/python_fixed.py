"""Python code execution node implementation."""
import ast
import inspect
import logging
import re
import textwrap
import traceback
from typing import Any, Callable, Dict, Optional, Type

from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    SafetyViolationError
)


logger = logging.getLogger(__name__)


# Module whitelist for safety
ALLOWED_MODULES = {
    'math', 'statistics', 'datetime', 'json', 'random', 'itertools',
    'collections', 'functools', 'string', 're', 'pandas', 'numpy',
    'scipy', 'sklearn', 'matplotlib', 'seaborn', 'plotly'
}


class SafeCodeChecker(ast.NodeVisitor):
    """AST visitor to check code safety."""
    
    def __init__(self):
        self.violations = []
    
    def visit_Import(self, node):
        """Check import statements."""
        for alias in node.names:
            module_name = alias.name.split('.')[0]
            if module_name not in ALLOWED_MODULES:
                self.violations.append(
                    f"Import of module '{module_name}' is not allowed"
                )
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Check from imports."""
        if node.module:
            module_name = node.module.split('.')[0]
            if module_name not in ALLOWED_MODULES:
                self.violations.append(
                    f"Import from module '{module_name}' is not allowed"
                )
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Check function calls."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            # Check for dangerous built-in functions
            if func_name in {'eval', 'exec', 'compile', '__import__'}:
                self.violations.append(
                    f"Call to '{func_name}' is not allowed"
                )
        elif isinstance(node.func, ast.Attribute):
            # Check for dangerous method calls
            if node.func.attr in {'system', 'popen'}:
                self.violations.append(
                    f"Call to method '{node.func.attr}' is not allowed"
                )
        self.generic_visit(node)


class CodeExecutor:
    """Executes Python code safely."""
    
    def __init__(self):
        self.allowed_builtins = {
            'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'filter',
            'float', 'int', 'len', 'list', 'map', 'max', 'min', 'range',
            'round', 'sorted', 'str', 'sum', 'tuple', 'type', 'zip',
            'print'  # Allow print for debugging
        }
        
    def check_code_safety(self, code: str) -> None:
        """Check if code is safe to execute.
        
        Args:
            code: Python code to check
            
        Raises:
            SafetyViolationError: If code contains unsafe operations
        """
        try:
            tree = ast.parse(code)
            checker = SafeCodeChecker()
            checker.visit(tree)
            
            if checker.violations:
                raise SafetyViolationError(
                    f"Code contains unsafe operations: {'; '.join(checker.violations)}"
                )
        except SyntaxError as e:
            raise NodeExecutionError(f"Invalid Python syntax: {e}")
    
    def execute_code(self, code: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Python code with given inputs.
        
        Args:
            code: Python code to execute
            inputs: Dictionary of input variables
            
        Returns:
            Dictionary of outputs
            
        Raises:
            NodeExecutionError: If code execution fails
        """
        # Check code safety
        self.check_code_safety(code)
        
        # Prepare execution namespace
        namespace = {
            '__builtins__': {
                name: getattr(__builtins__, name)
                for name in self.allowed_builtins
                if hasattr(__builtins__, name)
            }
        }
        
        # Add allowed modules
        for module_name in ALLOWED_MODULES:
            try:
                module = __import__(module_name)
                namespace[module_name] = module
            except ImportError:
                pass  # Module not available
        
        # Add inputs
        namespace.update(inputs)
        
        try:
            # Execute code
            exec(code, namespace)
            # Return all non-private variables
            return {
                k: v for k, v in namespace.items()
                if not k.startswith('_') and k not in inputs
            }
        except Exception as e:
            error_msg = f"Code execution failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise NodeExecutionError(error_msg)
    
    def execute_function(self, func: Callable, inputs: Dict[str, Any]) -> Any:
        """Execute a Python function with given inputs.
        
        Args:
            func: Function to execute
            inputs: Dictionary of input arguments
            
        Returns:
            Function return value
            
        Raises:
            NodeExecutionError: If function execution fails
        """
        try:
            # Get function signature
            sig = inspect.signature(func)
            
            # Map inputs to function parameters
            kwargs = {}
            for param_name, param in sig.parameters.items():
                if param_name in inputs:
                    kwargs[param_name] = inputs[param_name]
                elif param.default is not param.empty:
                    # Use default value
                    continue
                else:
                    raise NodeExecutionError(
                        f"Missing required parameter: {param_name}"
                    )
            
            # Execute function
            return func(**kwargs)
            
        except Exception as e:
            error_msg = f"Function execution failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise NodeExecutionError(error_msg)


class FunctionWrapper:
    """Wraps a Python function for node execution."""
    
    def __init__(self, func: Callable, executor: CodeExecutor):
        self.func = func
        self.executor = executor
        self.signature = inspect.signature(func)
    
    def get_input_types(self) -> Dict[str, Type]:
        """Extract input types from function signature."""
        input_types = {}
        for param_name, param in self.signature.parameters.items():
            if param.annotation != param.empty:
                input_types[param_name] = param.annotation
            else:
                # Default to Any if no annotation
                input_types[param_name] = Any
        return input_types
    
    def get_output_type(self) -> Type:
        """Extract output type from function signature."""
        if self.signature.return_annotation != self.signature.empty:
            return self.signature.return_annotation
        return Any
    
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the wrapped function."""
        result = self.executor.execute_function(self.func, inputs)
        
        # Wrap non-dict results in a dict
        if not isinstance(result, dict):
            result = {"result": result}
            
        return result


class ClassWrapper:
    """Wraps a Python class for node execution."""
    
    def __init__(self, class_type: Type, method_name: str, executor: CodeExecutor):
        self.class_type = class_type
        self.method_name = method_name
        self.executor = executor
        self.instance = class_type()
        
        # Get the method
        if not hasattr(self.instance, method_name):
            raise NodeConfigurationError(
                f"Class {class_type.__name__} has no method '{method_name}'"
            )
        self.method = getattr(self.instance, method_name)
        self.signature = inspect.signature(self.method)
    
    def get_input_types(self) -> Dict[str, Type]:
        """Extract input types from method signature."""
        input_types = {}
        for param_name, param in self.signature.parameters.items():
            if param_name == 'self':
                continue
            if param.annotation != param.empty:
                input_types[param_name] = param.annotation
            else:
                input_types[param_name] = Any
        return input_types
    
    def get_output_type(self) -> Type:
        """Extract output type from method signature."""
        if self.signature.return_annotation != self.signature.empty:
            return self.signature.return_annotation
        return Any
    
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the wrapped method."""
        result = self.executor.execute_function(self.method, inputs)
        
        # Wrap non-dict results in a dict
        if not isinstance(result, dict):
            result = {"result": result}
            
        return result


class PythonCodeNode(Node):
    """Node that executes arbitrary Python code.
    
    This node allows users to write custom Python code for data processing,
    either as:
    1. A code string to execute
    2. A function to call
    3. A class with a processing method
    
    The node provides a safe execution environment with access to common
    data science libraries while preventing potentially dangerous operations.
    """
    
    def __init__(self,
                 name: str,
                 code: Optional[str] = None,
                 function: Optional[Callable] = None,
                 class_type: Optional[Type] = None,
                 process_method: Optional[str] = None,
                 input_types: Optional[Dict[str, Type]] = None,
                 output_type: Optional[Type] = None,
                 input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                 output_schema: Optional[Dict[str, 'NodeParameter']] = None,
                 description: Optional[str] = None,
                 **kwargs):
        """Initialize the Python code node.
        
        Args:
            name: Node instance name
            code: Python code string to execute
            function: Python function to call
            class_type: Python class to instantiate
            process_method: Method name to call on class (default: 'process')
            input_types: Dictionary mapping input names to types
            output_type: Expected output type
            input_schema: Explicit input parameter definitions
            output_schema: Explicit output parameter definitions
            description: Node description
            **kwargs: Additional configuration
        """
        # Validate inputs
        if not any([code, function, class_type]):
            raise NodeConfigurationError(
                "Must provide one of: code, function, or class"
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
        
        # For class-based nodes, maintain instance
        self.instance = None
        if self.class_type:
            self.instance = self.class_type()
        
        # Initialize executor
        self.executor = CodeExecutor()
        
        # Create metadata
        metadata = NodeMetadata(
            id=name.replace(" ", "_").lower(),
            name=name,
            description=description or "Custom Python code node",
            tags={"custom", "python", "code"},
            version="1.0.0"
        )
        
        super().__init__(metadata=metadata, **kwargs)
    
    def _validate_config(self):
        """Override config validation for dynamic parameters.
        
        PythonCodeNode has dynamic parameters based on the wrapped function/class,
        so we skip the base class validation at initialization time.
        """
        # Skip validation - parameters are validated at runtime
        pass
    
    def get_parameters(self) -> Dict[str, 'NodeParameter']:
        """Define the parameters this node accepts.
        
        Returns:
            Dictionary mapping parameter names to their definitions
        """
        from kailash.nodes.base import NodeParameter
        
        # Use explicit input schema if provided
        if self._input_schema:
            return self._input_schema
            
        # Otherwise, generate schema from input types
        parameters = {}
        for name, type_ in self.input_types.items():
            parameters[name] = NodeParameter(
                name=name,
                type=type_,
                required=True,
                description=f"Input {name}"
            )
        
        # If we have a function/class, extract parameter info
        if self.function:
            wrapper = FunctionWrapper(self.function, self.executor)
            for name, type_ in wrapper.get_input_types().items():
                if name not in parameters:
                    parameters[name] = NodeParameter(
                        name=name,
                        type=type_,
                        required=True,
                        description=f"Input {name}"
                    )
        elif self.class_type and self.process_method:
            wrapper = ClassWrapper(
                self.class_type,
                self.process_method or 'process',
                self.executor
            )
            for name, type_ in wrapper.get_input_types().items():
                if name not in parameters:
                    parameters[name] = NodeParameter(
                        name=name,
                        type=type_,
                        required=True,
                        description=f"Input {name}"
                    )
        
        return parameters
    
    def get_output_schema(self) -> Dict[str, 'NodeParameter']:
        """Define the output schema for this node.
        
        Returns:
            Dictionary mapping output names to their definitions
        """
        from kailash.nodes.base import NodeParameter
        
        # Use explicit output schema if provided
        if self._output_schema:
            return self._output_schema
            
        # Otherwise, use default output
        return {
            "result": NodeParameter(
                name="result",
                type=self.output_type,
                required=True,
                description="Output result"
            )
        }
    
    def run(self, **inputs) -> Dict[str, Any]:
        """Execute the Python code with provided inputs.
        
        Args:
            **inputs: Input parameters
            
        Returns:
            Dictionary of outputs
        """
        try:
            if self.code:
                # Execute code string
                outputs = self.executor.execute_code(self.code, inputs)
            elif self.function:
                # Execute function
                wrapper = FunctionWrapper(self.function, self.executor)
                outputs = wrapper.execute(inputs)
            elif self.class_type:
                # Execute class method
                wrapper = ClassWrapper(
                    self.class_type,
                    self.process_method or 'process',
                    self.executor
                )
                outputs = wrapper.execute(inputs)
            else:
                raise NodeExecutionError("No code to execute")
            
            return outputs
            
        except Exception as e:
            logger.error(f"Python code execution failed: {e}")
            raise NodeExecutionError(f"Execution failed: {e}") from e
    
    @classmethod
    def from_function(cls,
                      func: Callable,
                      name: Optional[str] = None,
                      description: Optional[str] = None,
                      input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                      output_schema: Optional[Dict[str, 'NodeParameter']] = None,
                      **kwargs) -> 'PythonCodeNode':
        """Create a node from a Python function.
        
        Args:
            func: Function to wrap
            name: Node name (defaults to function name)
            description: Node description
            input_schema: Explicit input parameter definitions
            output_schema: Explicit output parameter definitions
            **kwargs: Additional configuration
            
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
            **kwargs
        )
    
    @classmethod
    def from_class(cls,
                   class_type: Type,
                   process_method: str = 'process',
                   name: Optional[str] = None,
                   description: Optional[str] = None,
                   input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                   output_schema: Optional[Dict[str, 'NodeParameter']] = None,
                   **kwargs) -> 'PythonCodeNode':
        """Create a node from a Python class.
        
        Args:
            class_type: Class to instantiate
            process_method: Method to call for processing
            name: Node name (defaults to class name)
            description: Node description
            input_schema: Explicit input parameter definitions
            output_schema: Explicit output parameter definitions
            **kwargs: Additional configuration
            
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
            process_method=process_method,
            input_types=input_types,
            output_type=output_type,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description or class_type.__doc__,
            **kwargs
        )
    
    @classmethod
    def from_file(cls,
                  file_path: str,
                  name: Optional[str] = None,
                  description: Optional[str] = None,
                  input_types: Optional[Dict[str, Type]] = None,
                  output_type: Optional[Type] = None,
                  **kwargs) -> 'PythonCodeNode':
        """Create a node from a Python file.
        
        Args:
            file_path: Path to Python file
            name: Node name
            description: Node description
            input_types: Input type definitions
            output_type: Output type definition
            **kwargs: Additional configuration
            
        Returns:
            PythonCodeNode instance
        """
        with open(file_path, 'r') as f:
            code = f.read()
        
        return cls(
            name=name or file_path.split('/')[-1].replace('.py', ''),
            code=code,
            input_types=input_types,
            output_type=output_type,
            description=description,
            **kwargs
        )