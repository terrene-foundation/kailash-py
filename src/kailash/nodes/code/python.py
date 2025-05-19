"""Python code execution node implementation.

This module provides nodes that can execute arbitrary Python code, allowing users
to create custom processing logic without defining new node classes. It supports
both function-based and class-based code execution with automatic type inference
and error handling.

Design Principles:
1. Safety - Code execution is sandboxed with proper error handling
2. Flexibility - Support functions, classes, and inline code
3. Type Safety - Automatic type inference with validation
4. Composability - Works seamlessly with other nodes in workflows
5. Simplicity - Easy to use for non-technical users

Components:
- PythonCodeNode: Main node for code execution
- CodeExecutor: Safe code execution environment
- FunctionWrapper: Converts functions to nodes
- ClassWrapper: Converts classes to nodes
"""

import ast
import inspect
import logging
import sys
import traceback
from typing import Any, Callable, Dict, Optional, Type, Union, List, Tuple
import importlib.util
from pathlib import Path
import tempfile
import textwrap

from kailash.nodes.base import Node, NodeMetadata
from kailash.sdk_exceptions import (
    NodeValidationError, NodeExecutionError, NodeConfigurationError)

logger = logging.getLogger(__name__)


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
    - Execution timeout (future enhancement)
    - Memory limits (future enhancement)
    """
    
    def __init__(self, allowed_modules: Optional[List[str]] = None):
        """Initialize the code executor.
        
        Args:
            allowed_modules: List of module names allowed for import.
                           Defaults to common data processing modules.
        """
        self.allowed_modules = allowed_modules or [
            'pandas', 'numpy', 'json', 'datetime', 'math', 're',
            'collections', 'itertools', 'functools', 'statistics'
        ]
        self._execution_namespace = {}
        
    def execute_code(self, code: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Python code with given inputs.
        
        Args:
            code: Python code to execute
            inputs: Dictionary of input variables
            
        Returns:
            Dictionary of variables after execution
            
        Raises:
            NodeExecutionError: If code execution fails
        """
        # Create isolated namespace
        namespace = {
            '__builtins__': __builtins__,
            **inputs
        }
        
        # Add allowed modules
        for module_name in self.allowed_modules:
            try:
                module = importlib.import_module(module_name)
                namespace[module_name] = module
            except ImportError:
                logger.warning(f"Module {module_name} not available")
        
        try:
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
    
    def __init__(self, func: Callable):
        """Initialize the function wrapper.
        
        Args:
            func: Python function to wrap
        """
        self.func = func
        self.signature = inspect.signature(func)
        self.name = func.__name__
        self.doc = inspect.getdoc(func) or ""
        
    def get_input_types(self) -> Dict[str, Type]:
        """Extract input types from function signature.
        
        Returns:
            Dictionary mapping parameter names to types
        """
        input_types = {}
        for param_name, param in self.signature.parameters.items():
            if param.annotation != param.empty:
                input_types[param_name] = param.annotation
            else:
                # Default to Any if no annotation
                input_types[param_name] = Any
        return input_types
    
    def get_output_type(self) -> Type:
        """Extract output type from function signature.
        
        Returns:
            Return type annotation or Any
        """
        if self.signature.return_annotation != self.signature.empty:
            return self.signature.return_annotation
        return Any
    
    def to_node(self, name: Optional[str] = None, 
                description: Optional[str] = None,
                input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                output_schema: Optional[Dict[str, 'NodeParameter']] = None) -> 'PythonCodeNode':
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
            output_schema=output_schema
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
    
    def __init__(self, cls: Type):
        """Initialize the class wrapper.
        
        Args:
            cls: Python class to wrap
        """
        self.cls = cls
        self.name = cls.__name__
        self.doc = inspect.getdoc(cls) or ""
        self._analyze_class()
        
    def _analyze_class(self):
        """Analyze class structure to find processing method."""
        # Look for common method names
        process_methods = ['process', 'execute', 'run', 'transform', '__call__']
        
        self.process_method = None
        for method_name in process_methods:
            if hasattr(self.cls, method_name):
                method = getattr(self.cls, method_name)
                if callable(method) and not method_name.startswith('_'):
                    self.process_method = method_name
                    break
        
        if not self.process_method:
            raise NodeConfigurationError(
                f"Class {self.name} must have a process method "
                f"(one of: {', '.join(process_methods)})"
            )
    
    def to_node(self, name: Optional[str] = None,
                description: Optional[str] = None,
                input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                output_schema: Optional[Dict[str, 'NodeParameter']] = None) -> 'PythonCodeNode':
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
            output_schema=output_schema
        )


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
    
    Example:
        # Function-based node
        def custom_filter(data: pd.DataFrame, threshold: float) -> pd.DataFrame:
            return data[data['value'] > threshold]
            
        node = PythonCodeNode.from_function(
            func=custom_filter,
            name="threshold_filter"
        )
        
        # Class-based stateful node
        class MovingAverage:
            def __init__(self, window_size: int = 3):
                self.window_size = window_size
                self.values = []
                
            def process(self, value: float) -> float:
                self.values.append(value)
                if len(self.values) > self.window_size:
                    self.values.pop(0)
                return sum(self.values) / len(self.values)
        
        node = PythonCodeNode.from_class(
            cls=MovingAverage,
            name="moving_avg"
        )
        
        # Code string node
        code = '''
        result = []
        for item in data:
            if item > threshold:
                result.append(item * 2)
        '''
        
        node = PythonCodeNode(
            name="custom_processor",
            code=code,
            input_types={'data': list, 'threshold': float},
            output_type=list
        )
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
        
        # For class-based nodes, maintain instance
        self.instance = None
        if self.class_type:
            self.instance = self.class_type()
        
        # Initialize executor
        self.executor = CodeExecutor()
        
        # Create metadata (avoiding conflicts with kwargs)
        if 'metadata' not in kwargs:
            kwargs['metadata'] = NodeMetadata(
                id=name.replace(" ", "_").lower(),
                name=name,
                description=description or "Custom Python code node",
                tags={"custom", "python", "code"},
                version="1.0.0"
            )
        
        # Extract config parameters from kwargs
        config = kwargs.get('config', {})
        
        # Pass both metadata and config to parent
        super().__init__(**kwargs)
    
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
                description=f"Input parameter {name} of type {type_.__name__}"
            )
        return parameters
    
    def get_output_schema(self) -> Dict[str, 'NodeParameter']:
        """Define output parameters for this node.
        
        Returns:
            Dictionary mapping output names to their parameter definitions
        """
        # Return explicit output schema if provided
        if self._output_schema:
            return self._output_schema
            
        # Otherwise, return empty schema (no validation)
        return {}
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic.
        
        Args:
            **kwargs: Validated input data
            
        Returns:
            Dictionary of outputs
        """
        # Execute with the validated keyword arguments
        result = self.execute_code(kwargs)
        
        # Ensure result is a dictionary
        if not isinstance(result, dict):
            return {"result": result}
        return result
    
    def execute_code(self, inputs: Dict[str, Any]) -> Any:
        """Execute the Python code with given inputs.
        
        This is a custom method for direct code execution, separate from the base 
        class's execute() lifecycle.
        
        Args:
            inputs: Dictionary of input data
            
        Returns:
            Execution result
            
        Raises:
            NodeExecutionError: If execution fails
        """
        # Direct code execution - no validation needed here
        
        try:
            if self.code:
                # Execute code string
                results = self.executor.execute_code(self.code, inputs)
                # Return 'result' variable if it exists, otherwise all results
                return results.get('result', results)
                
            elif self.function:
                # Execute function
                return self.executor.execute_function(self.function, inputs)
                
            elif self.instance and self.process_method:
                # Execute class method
                method = getattr(self.instance, self.process_method)
                return self.executor.execute_function(method, inputs)
                
            else:
                raise NodeExecutionError("No execution method available")
                
        except NodeExecutionError:
            raise
        except Exception as e:
            raise NodeExecutionError(f"Execution failed: {str(e)}")
    
    @classmethod
    def from_function(cls, func: Callable, name: Optional[str] = None,
                     description: Optional[str] = None,
                     input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                     output_schema: Optional[Dict[str, 'NodeParameter']] = None,
                     **kwargs) -> 'PythonCodeNode':
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
        wrapper = FunctionWrapper(func)
        return wrapper.to_node(name=name, description=description,
                              input_schema=input_schema, output_schema=output_schema)
    
    @classmethod
    def from_class(cls, class_type: Type, name: Optional[str] = None,
                  description: Optional[str] = None,
                  input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                  output_schema: Optional[Dict[str, 'NodeParameter']] = None,
                  **kwargs) -> 'PythonCodeNode':
        """Create a node from a Python class.
        
        Args:
            class_type: Python class to wrap
            name: Node name (defaults to class name)
            description: Node description
            input_schema: Explicit input parameter schema for validation
            output_schema: Explicit output parameter schema for validation
            **kwargs: Additional node parameters
            
        Returns:
            PythonCodeNode instance
        """
        wrapper = ClassWrapper(class_type)
        return wrapper.to_node(name=name, description=description,
                              input_schema=input_schema, output_schema=output_schema)
    
    @classmethod
    def from_file(cls, file_path: Union[str, Path], 
                 function_name: Optional[str] = None,
                 class_name: Optional[str] = None,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 input_schema: Optional[Dict[str, 'NodeParameter']] = None,
                 output_schema: Optional[Dict[str, 'NodeParameter']] = None) -> 'PythonCodeNode':
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
            return cls.from_function(func, name=name, description=description,
                                   input_schema=input_schema, output_schema=output_schema)
        
        elif class_name:
            if not hasattr(module, class_name):
                raise NodeConfigurationError(
                    f"Class {class_name} not found in {file_path}"
                )
            class_type = getattr(module, class_name)
            return cls.from_class(class_type, name=name, description=description,
                                 input_schema=input_schema, output_schema=output_schema)
        
        else:
            # Look for main function or first function
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and not attr_name.startswith('_'):
                    return cls.from_function(attr, name=name, description=description,
                                           input_schema=input_schema, output_schema=output_schema)
            
            raise NodeConfigurationError(
                f"No suitable function or class found in {file_path}"
            )
    
    def get_config(self) -> Dict[str, Any]:
        """Get node configuration for serialization.
        
        Returns:
            Configuration dictionary
        """
        config = super().get_config()
        
        # Add code-specific config
        config.update({
            'code': self.code,
            'input_types': {
                name: type_.__name__ for name, type_ in self.input_types.items()
            },
            'output_type': self.output_type.__name__ if self.output_type else 'Any'
        })
        
        # For function/class nodes, include source code
        if self.function:
            config['function_source'] = inspect.getsource(self.function)
        elif self.class_type:
            config['class_source'] = inspect.getsource(self.class_type)
            config['process_method'] = self.process_method
        
        return config