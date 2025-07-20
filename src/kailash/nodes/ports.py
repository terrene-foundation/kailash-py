"""
Type-safe input/output port system for Kailash nodes.

This module provides a type-safe port system that enables:
- Compile-time type checking with IDE support
- Runtime type validation
- Clear port declarations in node definitions
- Automatic type inference for connections
- Better developer experience with autocomplete

Design Goals:
1. Type safety: Catch type mismatches at design time
2. IDE support: Full autocomplete and type hints
3. Runtime validation: Enforce types during execution
4. Backward compatibility: Works with existing nodes
5. Performance: Minimal runtime overhead

Example Usage:
    class MyNode(TypedNode):
        # Input ports
        text_input = InputPort[str]("text_input", description="Text to process")
        count = InputPort[int]("count", default=1, description="Number of iterations")

        # Output ports
        result = OutputPort[str]("result", description="Processed text")
        metadata = OutputPort[Dict[str, Any]]("metadata", description="Processing metadata")

        def run(self, **kwargs) -> Dict[str, Any]:
            text = self.text_input.get()
            count = self.count.get()

            # Process...
            processed = text * count

            return {
                self.result.name: processed,
                self.metadata.name: {"length": len(processed)}
            }
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

logger = logging.getLogger(__name__)

# Type variable for generic port types
T = TypeVar("T")


@dataclass
class PortMetadata:
    """Metadata for input/output ports."""

    name: str
    description: str = ""
    required: bool = True
    default: Any = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    examples: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "constraints": self.constraints,
            "examples": self.examples,
        }


class Port(Generic[T], ABC):
    """Base class for typed input/output ports."""

    def __init__(
        self,
        name: str,
        description: str = "",
        required: bool = True,
        default: Optional[T] = None,
        constraints: Optional[Dict[str, Any]] = None,
        examples: Optional[List[T]] = None,
    ):
        """Initialize a port.

        Args:
            name: Port name (should match parameter name)
            description: Human-readable description
            required: Whether this port is required
            default: Default value if not connected
            constraints: Additional validation constraints
            examples: Example values for documentation
        """
        self.name = name
        self.metadata = PortMetadata(
            name=name,
            description=description,
            required=required,
            default=default,
            constraints=constraints or {},
            examples=examples or [],
        )
        self._type_hint: Optional[Type[T]] = None
        self._value: Optional[T] = None
        self._node_instance: Optional[Any] = None

        # Schedule type hint extraction to happen after __orig_class__ is set
        self._extract_type_hint()

    def _extract_type_hint(self):
        """Extract type hint from __orig_class__ after instance creation."""
        # This will be called again from a delayed context when __orig_class__ is available
        if hasattr(self, "__orig_class__"):
            args = get_args(self.__orig_class__)
            if args:
                self._type_hint = args[0]
                return True
        return False

    def __set_name__(self, owner: Type, name: str) -> None:
        """Called when port is assigned to a class attribute."""
        if self.name != name:
            logger.warning(
                f"Port name '{self.name}' doesn't match attribute name '{name}'. Using '{name}'."
            )
            self.name = name
            self.metadata.name = name

        # Extract type hint from class annotations
        if hasattr(owner, "__annotations__") and name in owner.__annotations__:
            annotation = owner.__annotations__[name]
            # Extract the type argument from Port[T]
            if hasattr(annotation, "__args__") and annotation.__args__:
                self._type_hint = annotation.__args__[0]
            elif hasattr(annotation, "__origin__"):
                # Handle Generic types
                origin = get_origin(annotation)
                args = get_args(annotation)
                if origin and args:
                    self._type_hint = args[0]

        # If no type hint found, try to extract from the port instance itself
        if self._type_hint is None and hasattr(self, "__orig_class__"):
            args = get_args(self.__orig_class__)
            if args:
                self._type_hint = args[0]

    def __get__(self, instance: Any, owner: Type = None) -> "Port[T]":
        """Descriptor protocol - return port instance bound to node."""
        if instance is None:
            return self

        # Cache bound ports per instance to maintain state
        cache_attr = f"_bound_port_{self.name}_{id(self)}"
        if hasattr(instance, cache_attr):
            return getattr(instance, cache_attr)

        # Create a copy bound to this instance
        if isinstance(self, OutputPort):
            bound_port = self.__class__(
                name=self.name,
                description=self.metadata.description,
                constraints=self.metadata.constraints,
                examples=self.metadata.examples,
            )
        else:
            bound_port = self.__class__(
                name=self.name,
                description=self.metadata.description,
                required=self.metadata.required,
                default=self.metadata.default,
                constraints=self.metadata.constraints,
                examples=self.metadata.examples,
            )
        bound_port._type_hint = self._type_hint
        bound_port._node_instance = instance

        # Cache the bound port
        setattr(instance, cache_attr, bound_port)
        return bound_port

    def __set__(self, instance: Any, value: T) -> None:
        """Descriptor protocol - set port value."""
        self._value = value
        self._node_instance = instance

    @property
    def type_hint(self) -> Optional[Type[T]]:
        """Get the type hint for this port."""
        return self._type_hint

    def get_type_name(self) -> str:
        """Get human-readable type name."""
        # Lazy type hint extraction
        if self._type_hint is None:
            self._extract_type_hint()

        if self._type_hint:
            if hasattr(self._type_hint, "__name__"):
                return self._type_hint.__name__
            else:
                return str(self._type_hint)
        return "Any"

    def validate_type(self, value: Any) -> bool:
        """Validate that value matches port type."""
        # Lazy type hint extraction - try again if not set yet
        if self._type_hint is None:
            self._extract_type_hint()

        if self._type_hint is None:
            return True  # No type constraint

        # Handle None values
        if value is None:
            return not self.metadata.required

        # Basic type checking
        try:
            if isinstance(self._type_hint, type):
                return isinstance(value, self._type_hint)
            else:
                # Handle complex types like Union, Optional, etc.
                return self._check_complex_type(value, self._type_hint)
        except Exception as e:
            logger.warning(f"Type validation error for port '{self.name}': {e}")
            return False

    def _check_complex_type(self, value: Any, type_hint: Type) -> bool:
        """Check complex types like Union, Optional, List[str], etc."""
        origin = get_origin(type_hint)
        args = get_args(type_hint)

        if origin is Union:
            # Check if value matches any of the union types
            return any(self._check_complex_type(value, arg) for arg in args)
        elif origin is list and args:
            # Check List[T] - all elements must be of type T
            if not isinstance(value, list):
                return False
            return all(self._check_complex_type(item, args[0]) for item in value)
        elif origin is dict and len(args) >= 2:
            # Check Dict[K, V]
            if not isinstance(value, dict):
                return False
            return all(
                self._check_complex_type(k, args[0]) for k in value.keys()
            ) and all(self._check_complex_type(v, args[1]) for v in value.values())
        else:
            # Fallback to isinstance for basic types
            try:
                return isinstance(value, type_hint)
            except TypeError:
                # Some types can't be used with isinstance
                return True

    def validate_constraints(self, value: Any) -> tuple[bool, Optional[str]]:
        """Validate value against port constraints.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.metadata.constraints:
            return True, None

        for constraint, constraint_value in self.metadata.constraints.items():
            if constraint == "min_length" and hasattr(value, "__len__"):
                if len(value) < constraint_value:
                    return (
                        False,
                        f"Value length {len(value)} is less than minimum {constraint_value}",
                    )
            elif constraint == "max_length" and hasattr(value, "__len__"):
                if len(value) > constraint_value:
                    return (
                        False,
                        f"Value length {len(value)} is greater than maximum {constraint_value}",
                    )
            elif constraint == "min_value" and isinstance(value, (int, float)):
                if value < constraint_value:
                    return (
                        False,
                        f"Value {value} is less than minimum {constraint_value}",
                    )
            elif constraint == "max_value" and isinstance(value, (int, float)):
                if value > constraint_value:
                    return (
                        False,
                        f"Value {value} is greater than maximum {constraint_value}",
                    )
            elif constraint == "pattern" and isinstance(value, str):
                import re

                if not re.match(constraint_value, value):
                    return (
                        False,
                        f"Value '{value}' does not match pattern '{constraint_value}'",
                    )

        return True, None

    @abstractmethod
    def get(self) -> T:
        """Get the value from this port."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert port to dictionary for serialization."""
        return {
            "name": self.name,
            "type": self.get_type_name(),
            "metadata": self.metadata.to_dict(),
            "port_type": self.__class__.__name__,
        }


class InputPort(Port[T]):
    """Input port for receiving data into a node."""

    def __init__(
        self,
        name: str,
        description: str = "",
        required: bool = True,
        default: Optional[T] = None,
        constraints: Optional[Dict[str, Any]] = None,
        examples: Optional[List[T]] = None,
    ):
        """Initialize an input port.

        Args:
            name: Port name
            description: Description of what this port accepts
            required: Whether this port must be connected or have a value
            default: Default value if not connected
            constraints: Validation constraints (min_length, max_length, min_value, max_value, pattern)
            examples: Example values for documentation
        """
        super().__init__(name, description, required, default, constraints, examples)

    def get(self) -> T:
        """Get the value from this input port.

        Returns:
            The input value, or default if not set

        Raises:
            ValueError: If port is required but no value is available
        """
        if self._value is not None:
            return self._value
        elif self.metadata.default is not None:
            return self.metadata.default
        elif not self.metadata.required:
            return None
        else:
            raise ValueError(f"Required input port '{self.name}' has no value")

    def set(self, value: T) -> None:
        """Set the value for this input port.

        Args:
            value: Value to set

        Raises:
            TypeError: If value doesn't match port type
            ValueError: If value doesn't meet constraints
        """
        # Type validation
        if not self.validate_type(value):
            raise TypeError(
                f"Input port '{self.name}' expects {self.get_type_name()}, got {type(value).__name__}"
            )

        # Constraint validation
        is_valid, error = self.validate_constraints(value)
        if not is_valid:
            raise ValueError(f"Input port '{self.name}' constraint violation: {error}")

        self._value = value

    def is_connected(self) -> bool:
        """Check if this input port has a value (connected or default)."""
        return self._value is not None or self.metadata.default is not None


class OutputPort(Port[T]):
    """Output port for sending data from a node."""

    def __init__(
        self,
        name: str,
        description: str = "",
        constraints: Optional[Dict[str, Any]] = None,
        examples: Optional[List[T]] = None,
    ):
        """Initialize an output port.

        Args:
            name: Port name
            description: Description of what this port produces
            constraints: Validation constraints for output values
            examples: Example output values for documentation
        """
        # Output ports are never required (they're always produced by the node)
        super().__init__(
            name,
            description,
            required=False,
            default=None,
            constraints=constraints,
            examples=examples,
        )

    def get(self) -> T:
        """Get the value from this output port.

        Returns:
            The output value

        Raises:
            ValueError: If no value has been set
        """
        if self._value is None:
            raise ValueError(f"Output port '{self.name}' has no value")
        return self._value

    def set(self, value: T) -> None:
        """Set the value for this output port.

        Args:
            value: Value to set

        Raises:
            TypeError: If value doesn't match port type
            ValueError: If value doesn't meet constraints
        """
        # Type validation
        if not self.validate_type(value):
            raise TypeError(
                f"Output port '{self.name}' expects {self.get_type_name()}, got {type(value).__name__}"
            )

        # Constraint validation
        is_valid, error = self.validate_constraints(value)
        if not is_valid:
            raise ValueError(f"Output port '{self.name}' constraint violation: {error}")

        self._value = value

    def has_value(self) -> bool:
        """Check if this output port has been set."""
        return self._value is not None


class PortRegistry:
    """Registry for managing ports in a node class."""

    def __init__(self, node_class: Type):
        """Initialize port registry for a node class.

        Args:
            node_class: The node class to analyze
        """
        self.node_class = node_class
        self._input_ports: Dict[str, InputPort] = {}
        self._output_ports: Dict[str, OutputPort] = {}
        self._scan_ports()

    def _scan_ports(self) -> None:
        """Scan the node class for port definitions."""
        for name, attr in self.node_class.__dict__.items():
            if isinstance(attr, InputPort):
                self._input_ports[name] = attr
            elif isinstance(attr, OutputPort):
                self._output_ports[name] = attr

    @property
    def input_ports(self) -> Dict[str, InputPort]:
        """Get all input ports."""
        return self._input_ports.copy()

    @property
    def output_ports(self) -> Dict[str, OutputPort]:
        """Get all output ports."""
        return self._output_ports.copy()

    def get_port_schema(self) -> Dict[str, Any]:
        """Get JSON schema for all ports."""
        return {
            "input_ports": {
                name: port.to_dict() for name, port in self._input_ports.items()
            },
            "output_ports": {
                name: port.to_dict() for name, port in self._output_ports.items()
            },
        }

    def validate_input_types(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate input types against port definitions.

        Args:
            inputs: Input values to validate

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Check required inputs
        for name, port in self._input_ports.items():
            if (
                port.metadata.required
                and name not in inputs
                and port.metadata.default is None
            ):
                errors.append(f"Required input port '{name}' is missing")
                continue

            if name in inputs:
                value = inputs[name]

                # Type validation
                if not port.validate_type(value):
                    errors.append(
                        f"Input port '{name}' expects {port.get_type_name()}, got {type(value).__name__}"
                    )

                # Constraint validation
                is_valid, error = port.validate_constraints(value)
                if not is_valid:
                    errors.append(f"Input port '{name}': {error}")

        return errors

    def validate_output_types(self, outputs: Dict[str, Any]) -> List[str]:
        """Validate output types against port definitions.

        Args:
            outputs: Output values to validate

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        for name, value in outputs.items():
            if name in self._output_ports:
                port = self._output_ports[name]

                # Type validation
                if not port.validate_type(value):
                    errors.append(
                        f"Output port '{name}' expects {port.get_type_name()}, got {type(value).__name__}"
                    )

                # Constraint validation
                is_valid, error = port.validate_constraints(value)
                if not is_valid:
                    errors.append(f"Output port '{name}': {error}")

        return errors


def get_port_registry(node_class: Type) -> PortRegistry:
    """Get port registry for a node class.

    Args:
        node_class: Node class to analyze

    Returns:
        PortRegistry instance
    """
    if not hasattr(node_class, "_port_registry"):
        node_class._port_registry = PortRegistry(node_class)
    return node_class._port_registry


# Convenience type aliases for common port types
def StringPort(name: str, **kwargs) -> InputPort[str]:
    """Create a string input port."""
    port = InputPort[str](name, **kwargs)
    port._type_hint = str
    return port


def IntPort(name: str, **kwargs) -> InputPort[int]:
    """Create an integer input port."""
    port = InputPort[int](name, **kwargs)
    port._type_hint = int
    return port


def FloatPort(name: str, **kwargs) -> InputPort[float]:
    """Create a float input port."""
    port = InputPort[float](name, **kwargs)
    port._type_hint = float
    return port


def BoolPort(name: str, **kwargs) -> InputPort[bool]:
    """Create a boolean input port."""
    port = InputPort[bool](name, **kwargs)
    port._type_hint = bool
    return port


def ListPort(name: str, **kwargs) -> InputPort[List[Any]]:
    """Create a list input port."""
    port = InputPort[List[Any]](name, **kwargs)
    port._type_hint = List[Any]
    return port


def DictPort(name: str, **kwargs) -> InputPort[Dict[str, Any]]:
    """Create a dict input port."""
    port = InputPort[Dict[str, Any]](name, **kwargs)
    port._type_hint = Dict[str, Any]
    return port


def StringOutput(name: str, **kwargs) -> OutputPort[str]:
    """Create a string output port."""
    port = OutputPort[str](name, **kwargs)
    port._type_hint = str
    return port


def IntOutput(name: str, **kwargs) -> OutputPort[int]:
    """Create an integer output port."""
    port = OutputPort[int](name, **kwargs)
    port._type_hint = int
    return port


def FloatOutput(name: str, **kwargs) -> OutputPort[float]:
    """Create a float output port."""
    port = OutputPort[float](name, **kwargs)
    port._type_hint = float
    return port


def BoolOutput(name: str, **kwargs) -> OutputPort[bool]:
    """Create a boolean output port."""
    port = OutputPort[bool](name, **kwargs)
    port._type_hint = bool
    return port


def ListOutput(name: str, **kwargs) -> OutputPort[List[Any]]:
    """Create a list output port."""
    port = OutputPort[List[Any]](name, **kwargs)
    port._type_hint = List[Any]
    return port


def DictOutput(name: str, **kwargs) -> OutputPort[Dict[str, Any]]:
    """Create a dict output port."""
    port = OutputPort[Dict[str, Any]](name, **kwargs)
    port._type_hint = Dict[str, Any]
    return port
