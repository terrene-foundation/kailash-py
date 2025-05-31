"""Base node class and node system implementation.

This module provides the foundation for all nodes in the Kailash system. It defines
the abstract base class that all nodes must inherit from, along with supporting
classes for metadata, configuration, and registration.

The node system is designed to be:
1. Type-safe through parameter validation
2. Discoverable through the node registry
3. Composable in workflows
4. Serializable for export/import
5. Extensible for custom implementations

Key Components:
- Node: Abstract base class for all nodes
- NodeMetadata: Metadata about nodes for discovery and documentation
- NodeParameter: Type definitions for node inputs/outputs
- NodeRegistry: Global registry for node discovery
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Type

from pydantic import BaseModel, Field, ValidationError

from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeValidationError,
)


class NodeMetadata(BaseModel):
    """Metadata for a node.

    This class stores descriptive information about a node that is used for:

    1. Discovery in the UI/CLI (name, description, tags)
    2. Version tracking and compatibility checks
    3. Documentation and tooltips
    4. Workflow export metadata

    Upstream consumers:
    - Node.__init__: Creates metadata during node instantiation
    - NodeRegistry: Uses metadata for discovery and filtering
    - WorkflowExporter: Includes metadata in exported workflows

    Downstream usage:
    - Workflow visualization: Shows node names and descriptions
    - CLI help: Displays available nodes with their metadata
    - Kailash UI: Node palette and property panels
    """

    id: str = Field("", description="Node ID")
    name: str = Field(..., description="Node name")
    description: str = Field("", description="Node description")
    version: str = Field("1.0.0", description="Node version")
    author: str = Field("", description="Node author")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Node creation date"
    )
    tags: Set[str] = Field(default_factory=set, description="Node tags")


class NodeParameter(BaseModel):
    """Definition of a node parameter.

    This class defines the schema for node inputs and outputs, providing:

    1. Type information for validation
    2. Default values for optional parameters
    3. Documentation for users
    4. Requirements specification

    Design Purpose:
    - Enables static analysis of workflow connections
    - Provides runtime validation of data types
    - Supports automatic UI generation for node configuration
    - Facilitates workflow validation before execution

    Upstream usage:
    - Node.get_parameters(): Returns dict of parameters
    - Custom nodes: Define their input/output schemas

    Downstream consumers:
    - Node._validate_config(): Validates configuration against parameters
    - Node.validate_inputs(): Validates runtime inputs
    - Workflow.connect(): Validates connections between nodes
    - WorkflowExporter: Exports parameter schemas
    """

    name: str
    type: Type
    required: bool = True
    default: Any = None
    description: str = ""


class Node(ABC):
    """Base class for all nodes in the Kailash system.

    This abstract class defines the contract that all nodes must implement.
    It provides the foundation for:

    1. Parameter validation and type checking
    2. Execution lifecycle management
    3. Error handling and reporting
    4. Serialization for workflow export
    5. Configuration management

    Design Philosophy:
    - Nodes are stateless processors of data
    - All configuration is provided at initialization
    - Runtime inputs are validated against schemas
    - Outputs must be JSON-serializable
    - Errors are wrapped in appropriate exception types

    Inheritance Pattern:
    All concrete nodes must:

    1. Implement get_parameters() to define inputs
    2. Implement run() to process data
    3. Call super().__init__() with configuration
    4. Use self.logger for logging

    Upstream components:
    - Workflow: Creates and manages node instances
    - NodeRegistry: Provides node classes for instantiation
    - CLI/UI: Configures nodes based on user input

    Downstream usage:
    - LocalRuntime: Executes nodes in workflows
    - TaskManager: Tracks node execution status
    - WorkflowExporter: Serializes nodes for export
    """

    def __init__(self, **kwargs):
        """Initialize the node with configuration parameters.

        This method performs the following initialization steps:

        1. Sets the node ID (defaults to class name)
        2. Creates metadata from provided arguments
        3. Sets up logging for the node
        4. Stores configuration in self.config
        5. Validates configuration against parameters

        The configuration is validated by calling _validate_config(), which
        checks that all required parameters are present and of the correct type.

        Args:
            **kwargs: Configuration parameters including:
                - id: Optional custom node ID
                - name: Display name for the node
                - description: Node description
                - version: Node version
                - author: Node author
                - tags: Set of tags for discovery
                - Any parameters defined in get_parameters()

        Raises:
            NodeConfigurationError: If configuration is invalid or
                                 if metadata validation fails

        Downstream effects:
            - Creates self.metadata for discovery
            - Sets up self.logger for execution logging
            - Stores self.config for runtime access
            - Validates parameters are correctly specified
        """
        try:
            self.id = kwargs.get("id", self.__class__.__name__)
            self.metadata = kwargs.get(
                "metadata",
                NodeMetadata(
                    id=self.id,
                    name=kwargs.get("name", self.__class__.__name__),
                    description=kwargs.get("description", self.__doc__ or ""),
                    version=kwargs.get("version", "1.0.0"),
                    author=kwargs.get("author", ""),
                    tags=kwargs.get("tags", set()),
                ),
            )
            self.logger = logging.getLogger(f"kailash.nodes.{self.id}")
            self.config = kwargs
            self._validate_config()
        except ValidationError as e:
            raise NodeConfigurationError(f"Invalid node metadata: {e}") from e
        except Exception as e:
            raise NodeConfigurationError(
                f"Failed to initialize node '{self.id}': {e}"
            ) from e

    @abstractmethod
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        This abstract method must be implemented by all concrete nodes to
        specify their input schema. The parameters define:

        1. What inputs the node expects
        2. Type requirements for each input
        3. Whether inputs are required or optional
        4. Default values for optional inputs
        5. Documentation for each parameter

        The returned dictionary is used throughout the node lifecycle:

        - During initialization: _validate_config() checks configuration
        - During execution: validate_inputs() validates runtime data
        - During workflow creation: Used for connection validation
        - During export: Included in workflow manifests

        Example::

            def get_parameters(self):
                return {
                    'input_file': NodeParameter(
                        name='input_file',
                        type=str,
                        required=True,
                        description='Path to input CSV file'
                    ),
                    'delimiter': NodeParameter(
                        name='delimiter',
                        type=str,
                        required=False,
                        default=',',
                        description='CSV delimiter character'
                    )
                }

        Returns:
            Dictionary mapping parameter names to their definitions

        Used by:
            - _validate_config(): Validates configuration matches parameters
            - validate_inputs(): Validates runtime inputs
            - to_dict(): Includes parameters in serialization
            - Workflow.connect(): Validates compatible connections
        """
        pass

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output parameters for this node.

        This optional method allows nodes to specify their output schema for
        validation.
        If not overridden, outputs will only be validated for
        JSON-serializability.

        Design purpose:
        - Enables static analysis of node outputs
        - Provides runtime validation of output types
        - Supports automatic documentation of outputs
        - Facilitates workflow validation and type checking

        The output schema serves similar purposes as input parameters:

        1. Type validation during execution
        2. Documentation for downstream consumers
        3. Workflow connection validation
        4. Export manifest generation

        Example::

            def get_output_schema(self):
                return {
                    'dataframe': NodeParameter(
                        name='dataframe',
                        type=dict,
                        required=True,
                        description='Processed data as dictionary'
                    ),
                    'row_count': NodeParameter(
                        name='row_count',
                        type=int,
                        required=True,
                        description='Number of rows processed'
                    ),
                    'processing_time': NodeParameter(
                        name='processing_time',
                        type=float,
                        required=False,
                        description='Time taken to process in seconds'
                    )
                }

        Returns:
            Dictionary mapping output names to their parameter definitions
            Empty dict by default (no schema validation)

        Used by:
            - validate_outputs(): Validates runtime outputs
            - Workflow.connect(): Validates connections between nodes
            - Documentation generators: Create output documentation
            - Export systems: Include output schemas in manifests
        """
        return {}

    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic.

        This is the core method that implements the node's data processing
        logic.
        It receives validated inputs and must return a dictionary of outputs.

        Design requirements:

        1. Must be stateless - no side effects between runs
        2. All inputs are provided as keyword arguments
        3. Must return a dictionary (JSON-serializable)
        4. Should handle errors gracefully
        5. Can use self.config for configuration values
        6. Should use self.logger for status reporting

        The method is called by execute() which handles:

        - Input validation before calling run()
        - Output validation after run() completes
        - Error wrapping and logging
        - Execution timing and metrics

        Example::

            def run(self, input_file, delimiter=','):
                df = pd.read_csv(input_file, delimiter=delimiter)
                return {
                    'dataframe': df.to_dict(),
                    'row_count': len(df),
                    'columns': list(df.columns)
                }

        Args:
            **kwargs: Validated input parameters matching get_parameters()

        Returns:
            Dictionary of outputs that will be validated and passed
            to downstream nodes

        Raises:
            NodeExecutionError: If execution fails (will be caught and
                              re-raised by execute())

        Called by:
            - execute(): Wraps with validation and error handling
            - LocalRuntime: During workflow execution
            - TestRunner: During unit testing
        """
        pass

    def _validate_config(self):
        """Validate node configuration against defined parameters.

        This internal method is called during __init__ to ensure that the
        provided configuration matches the node's parameter requirements.

        Validation process:

        1. Calls get_parameters() to get schema
        2. For each parameter, checks if:

           - Required parameters are present
           - Values match expected types
           - Type conversion is possible if needed

        3. Sets default values for missing optional parameters
        4. Updates self.config with validated values

        Type conversion:

        - If a value doesn't match the expected type, attempts conversion
        - For example: string "123" -> int 123
        - Conversion failures result in descriptive errors

        Called by:
            - __init__(): During node initialization

        Modifies:
            - self.config: Updates with defaults and converted values

        Raises:
            NodeConfigurationError: If configuration is invalid, including:
                - Missing required parameters
                - Type mismatches that can't be converted
                - get_parameters() implementation errors
        """
        try:
            params = self.get_parameters()
        except Exception as e:
            raise NodeConfigurationError(f"Failed to get node parameters: {e}") from e

        for param_name, param_def in params.items():
            if param_name not in self.config:
                if param_def.required and param_def.default is None:
                    raise NodeConfigurationError(
                        f"Required parameter '{param_name}' not provided in configuration"
                    )
                elif param_def.default is not None:
                    self.config[param_name] = param_def.default

            if param_name in self.config:
                value = self.config[param_name]
                # Skip type checking for Any type
                if param_def.type is Any:
                    continue
                if not isinstance(value, param_def.type):
                    try:
                        self.config[param_name] = param_def.type(value)
                    except (ValueError, TypeError) as e:
                        raise NodeConfigurationError(
                            f"Configuration parameter '{param_name}' must be of type "
                            f"{param_def.type.__name__}, got {type(value).__name__}. "
                            f"Conversion failed: {e}"
                        ) from e

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate runtime inputs against node requirements.

        This method validates inputs provided at execution time against the
        node's parameter schema. It ensures type safety and provides helpful
        error messages for invalid inputs.

        Validation steps:

        1. Gets parameter definitions from get_parameters()
        2. Checks each parameter for:

           - Presence (if required)
           - Type compatibility
           - Null handling for optional parameters

        3. Attempts type conversion if needed
        4. Applies default values for missing optional parameters

        Key behaviors:

        - Required parameters must be provided or have defaults
        - Optional parameters can be None
        - Type mismatches attempt conversion before failing
        - Error messages include parameter descriptions

        Example flow:
            # Node expects: {'count': int, 'name': str (optional)}
            inputs = {'count': '42', 'name': None}
            validated = validate_inputs(\**inputs)
            # Returns: {'count': 42}  # Converted and None removed

        Args:
            **kwargs: Runtime inputs to validate

        Returns:
            Dictionary of validated inputs with:

            - Type conversions applied
            - Defaults for missing optional parameters
            - None values removed for optional parameters

        Raises:
            NodeValidationError: If inputs are invalid:

                - Missing required parameters
                - Type conversion failures
                - get_parameters() errors

        Called by:
            - execute(): Before passing inputs to run()
            - Workflow validation: During connection checks
        """
        try:
            params = self.get_parameters()
        except Exception as e:
            raise NodeValidationError(
                f"Failed to get node parameters for validation: {e}"
            ) from e

        validated = {}

        for param_name, param_def in params.items():
            if param_def.required and param_name not in kwargs:
                if param_def.default is not None:
                    validated[param_name] = param_def.default
                else:
                    raise NodeValidationError(
                        f"Required input '{param_name}' not provided. "
                        f"Description: {param_def.description or 'No description available'}"
                    )

            if param_name in kwargs:
                value = kwargs[param_name]
                if value is None and not param_def.required:
                    continue

                # Skip type checking for Any type
                if param_def.type is Any:
                    validated[param_name] = value
                elif not isinstance(value, param_def.type):
                    try:
                        validated[param_name] = param_def.type(value)
                    except (ValueError, TypeError) as e:
                        raise NodeValidationError(
                            f"Input '{param_name}' must be of type {param_def.type.__name__}, "
                            f"got {type(value).__name__}. Conversion failed: {e}"
                        ) from e
                else:
                    validated[param_name] = value

        return validated

    def validate_outputs(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate outputs against schema and JSON-serializability.

        This enhanced method validates outputs in two ways:

        1. Schema validation: If get_output_schema() is defined, validates
           types and required fields
        2. JSON serialization: Ensures all outputs can be serialized

        Validation process:

        1. Check outputs is a dictionary
        2. If output schema exists:

           - Validate required fields are present
           - Check type compatibility
           - Attempt type conversion if needed

        3. Verify JSON-serializability
        4. Return validated outputs

        Schema validation features:

        - Required outputs must be present
        - Optional outputs can be None or missing
        - Type mismatches attempt conversion
        - Clear error messages with field details

        Args:
            outputs: Outputs to validate from run() method

        Returns:
            The same outputs dictionary if valid

        Raises:
            NodeValidationError: If outputs are invalid:

                - Not a dictionary
                - Missing required outputs
                - Type validation failures
                - Non-serializable values

        Called by:
            - execute(): After run() completes
            - Test utilities: For output validation
        """
        if not isinstance(outputs, dict):
            raise NodeValidationError(
                f"Node outputs must be a dictionary, got {type(outputs).__name__}"
            )

        # First, validate against output schema if defined
        output_schema = self.get_output_schema()
        if output_schema:
            validated_outputs = {}

            for param_name, param_def in output_schema.items():
                if param_def.required and param_name not in outputs:
                    raise NodeValidationError(
                        f"Required output '{param_name}' not provided. "
                        f"Description: {param_def.description or 'No description available'}"
                    )

                if param_name in outputs:
                    value = outputs[param_name]
                    if value is None and not param_def.required:
                        continue  # Optional outputs can be None

                    if value is not None:
                        # Skip type checking for Any type
                        if param_def.type is Any:
                            validated_outputs[param_name] = value
                        elif not isinstance(value, param_def.type):
                            try:
                                # Attempt type conversion
                                converted_value = param_def.type(value)
                                validated_outputs[param_name] = converted_value
                            except (ValueError, TypeError) as e:
                                raise NodeValidationError(
                                    f"Output '{param_name}' must be of type {param_def.type.__name__}, "
                                    f"got {type(value).__name__}. Conversion failed: {e}"
                                ) from e
                        else:
                            validated_outputs[param_name] = value
                    else:
                        validated_outputs[param_name] = None

            # Include any additional outputs not in schema (for flexibility)
            for key, value in outputs.items():
                if key not in validated_outputs:
                    validated_outputs[key] = value

            outputs = validated_outputs

        # Then validate JSON-serializability
        # Skip JSON validation for state management objects
        from pydantic import BaseModel

        from kailash.workflow.state import WorkflowStateWrapper

        non_serializable = []
        for k, v in outputs.items():
            # Allow WorkflowStateWrapper objects to pass through
            if isinstance(v, WorkflowStateWrapper):
                continue
            # Allow Pydantic models (they can be serialized with .model_dump())
            if isinstance(v, BaseModel):
                continue
            if not self._is_json_serializable(v):
                non_serializable.append(k)

        if non_serializable:
            raise NodeValidationError(
                f"Node outputs must be JSON-serializable. Failed keys: {non_serializable}"
            )

        return outputs

    def _is_json_serializable(self, obj: Any) -> bool:
        """Check if an object is JSON-serializable.

        Helper method that attempts JSON serialization to determine
        if an object can be serialized. Used by validate_outputs()
        to identify problematic values.

        Args:
            obj: Any object to test for JSON serializability

        Returns:
            True if object can be JSON serialized, False otherwise

        Used by:
            - validate_outputs(): To identify non-serializable keys
        """
        try:
            json.dumps(obj)
            return True
        except (TypeError, ValueError):
            return False

    def execute(self, **runtime_inputs) -> Dict[str, Any]:
        """Execute the node with validation and error handling.

        This is the main entry point for node execution that orchestrates
        the complete execution lifecycle:

        1. Input validation (validate_inputs)
        2. Execution (run)
        3. Output validation (validate_outputs)
        4. Error handling and logging
        5. Performance metrics

        Execution flow:

        1. Logs execution start
        2. Validates inputs against parameter schema
        3. Calls run() with validated inputs
        4. Validates outputs are JSON-serializable
        5. Logs execution time
        6. Returns validated outputs

        Error handling strategy:

        - NodeValidationError: Re-raised as-is (input/output issues)
        - NodeExecutionError: Re-raised as-is (run() failures)
        - Other exceptions: Wrapped in NodeExecutionError

        Performance tracking:

        - Records execution start/end times
        - Logs total execution duration
        - Includes timing in execution logs

        Returns:
            Dictionary of validated outputs from run()

        Raises:
            NodeExecutionError: If execution fails in run()
            NodeValidationError: If input/output validation fails

        Called by:
            - LocalRuntime: During workflow execution
            - TaskManager: With execution tracking
            - Unit tests: For node testing

        Downstream effects:
            - Logs provide execution history
            - Metrics enable performance monitoring
            - Validation ensures data integrity
        """
        start_time = datetime.now(timezone.utc)
        try:
            self.logger.info(f"Executing node {self.id}")

            # Merge runtime inputs with config (runtime inputs take precedence)
            merged_inputs = {**self.config, **runtime_inputs}

            # Handle nested config case (for nodes that store parameters in config['config'])
            if "config" in merged_inputs and isinstance(merged_inputs["config"], dict):
                # Extract nested config
                nested_config = merged_inputs["config"]
                merged_inputs.update(nested_config)
                # Don't remove the config key as some nodes might need it

            # Validate inputs
            validated_inputs = self.validate_inputs(**merged_inputs)
            self.logger.debug(f"Validated inputs for {self.id}: {validated_inputs}")

            # Execute node logic
            outputs = self.run(**validated_inputs)

            # Validate outputs
            validated_outputs = self.validate_outputs(outputs)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.info(
                f"Node {self.id} executed successfully in {execution_time:.3f}s"
            )
            return validated_outputs

        except NodeValidationError:
            # Re-raise validation errors as-is
            raise
        except NodeExecutionError:
            # Re-raise execution errors as-is
            raise
        except Exception as e:
            # Wrap any other exception in NodeExecutionError
            self.logger.error(f"Node {self.id} execution failed: {e}", exc_info=True)
            raise NodeExecutionError(
                f"Node '{self.id}' execution failed: {type(e).__name__}: {e}"
            ) from e

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary representation.

        Serializes the node instance to a dictionary format suitable for:

        1. Workflow export
        2. Node persistence
        3. API responses
        4. Configuration sharing

        The serialized format includes:

        - id: Unique node identifier
        - type: Node class name
        - metadata: Complete node metadata
        - config: Current configuration
        - parameters: Parameter definitions with types

        Type serialization:

        - Python types are converted to string names
        - Complex types may require custom handling
        - Parameter defaults are included

        Returns:
            Dictionary representation containing:

            - Node identification and type
            - Complete metadata
            - Configuration values
            - Parameter schemas

        Raises:
            NodeExecutionError: If serialization fails due to:

                - get_parameters() errors
                - Metadata serialization issues
                - Type conversion problems

        Used by:
            - WorkflowExporter: For workflow serialization
            - CLI: For node inspection
            - API: For node information endpoints
            - Debugging: For node state inspection
        """
        try:
            return {
                "id": self.id,
                "type": self.__class__.__name__,
                "metadata": self.metadata.model_dump(),
                "config": self.config,
                "parameters": {
                    name: {
                        "type": param.type.__name__,
                        "required": param.required,
                        "default": param.default,
                        "description": param.description,
                    }
                    for name, param in self.get_parameters().items()
                },
            }
        except Exception as e:
            raise NodeExecutionError(
                f"Failed to serialize node '{self.id}': {e}"
            ) from e


# Node Registry
class NodeRegistry:
    """Registry for discovering and managing available nodes.

    This singleton class provides a global registry for node types,
    enabling:

    1. Dynamic node discovery
    2. Node class registration
    3. Workflow deserialization
    4. CLI/UI node palettes

    Design pattern: Singleton

    - Single global instance (_instance)
    - Shared registry of node classes (_nodes)
    - Thread-safe through class methods

    Registration flow:

    1. Nodes register via @register_node decorator
    2. Registry validates node inheritance
    3. Stores class reference by name/alias
    4. Available for instantiation

    Usage patterns:

    - Automatic: @register_node decorator
    - Manual: NodeRegistry.register(NodeClass)
    - Discovery: NodeRegistry.list_nodes()
    - Instantiation: NodeRegistry.get('NodeName')

    Upstream components:
    - Node implementations: Register themselves
    - Module imports: Trigger registration
    - Setup scripts: Bulk registration

    Downstream consumers:
    - Workflow: Creates nodes by name
    - CLI: Lists available nodes
    - UI: Populates node palette
    - WorkflowImporter: Deserializes nodes
    """

    _instance = None
    _nodes: Dict[str, Type[Node]] = {}

    def __new__(cls):
        """Ensure singleton instance.

        Implements the singleton pattern to maintain a single
        global registry of nodes.

        Returns:
            The single NodeRegistry instance
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, node_class: Type[Node], alias: Optional[str] = None):
        """Register a node class.

        Adds a node class to the global registry, making it available
        for discovery and instantiation.

        Registration process:

        1. Validates node_class inherits from Node
        2. Determines registration name (alias or class name)
        3. Warns if overwriting existing registration
        4. Stores class reference in registry

        Thread safety:

        - Class method ensures single registry
        - Dictionary operations are atomic
        - Safe for concurrent registration

        Example usage:
            NodeRegistry.register(CSVReaderNode)
            NodeRegistry.register(CustomNode, alias='MyNode')

        Args:
            node_class: Node class to register (must inherit from Node)
            alias: Optional alias for the node (defaults to class name)

        Raises:
            NodeConfigurationError: If registration fails:

                - node_class doesn't inherit from Node
                - Invalid class type provided

        Side effects:

            - Updates cls._nodes dictionary
            - Logs registration success/warnings
            - Overwrites existing registrations

        Used by:
            - @register_node decorator
            - Manual registration in setup
            - Plugin loading systems
        """
        if not issubclass(node_class, Node):
            raise NodeConfigurationError(
                f"Cannot register {node_class.__name__}: must be a subclass of Node"
            )

        node_name = alias or node_class.__name__

        if node_name in cls._nodes:
            logging.warning(f"Overwriting existing node registration for '{node_name}'")

        cls._nodes[node_name] = node_class
        logging.info(f"Registered node '{node_name}'")

    @classmethod
    def get(cls, node_name: str) -> Type[Node]:
        """Get a registered node class by name.

        Retrieves a node class from the registry for instantiation.
        Used during workflow creation and deserialization.

        Lookup process:

        1. Searches registry by exact name match
        2. Returns class reference if found
        3. Provides helpful error with available nodes

        Example usage:
            NodeClass = NodeRegistry.get('CSVReader')
            node = NodeClass(config={'file': 'data.csv'})

        Args:
            node_name: Name of the node (class name or alias)

        Returns:
            Node class ready for instantiation

        Raises:
            NodeConfigurationError: If node is not registered:

                - Includes list of available nodes
                - Suggests similar names if possible

        Used by:
            - Workflow.add_node(): Creates nodes by name
            - WorkflowImporter: Deserializes nodes
            - CLI commands: Instantiates nodes
            - Factory methods: Dynamic node creation
        """
        if node_name not in cls._nodes:
            available_nodes = ", ".join(sorted(cls._nodes.keys()))
            raise NodeConfigurationError(
                f"Node '{node_name}' not found in registry. "
                f"Available nodes: {available_nodes}"
            )
        return cls._nodes[node_name]

    @classmethod
    def list_nodes(cls) -> Dict[str, Type[Node]]:
        """List all registered nodes.

        Returns a copy of the registry for discovery purposes.
        Used by CLI help, UI node palettes, and documentation.

        Returns:
            Dictionary mapping node names to their classes:

            - Keys: Node names/aliases
            - Values: Node class references
            - Safe copy prevents registry modification

        Used by:
            - CLI 'list-nodes' command
            - UI node palette population
            - Documentation generators
            - Testing and debugging
        """
        return cls._nodes.copy()

    @classmethod
    def clear(cls):
        """Clear all registered nodes.

        Removes all nodes from the registry. Primarily used for:

        1. Testing - Clean state between tests
        2. Reloading - Before re-registering nodes
        3. Cleanup - Memory management

        Side effects:

            - Empties the _nodes dictionary
            - Logs the clearing action
            - Existing node instances remain valid

        Warning::

        - Subsequent get() calls will fail
        - Workflows may not deserialize
        - Should re-register needed nodes
        """
        cls._nodes.clear()
        logging.info("Cleared all registered nodes")


def register_node(alias: Optional[str] = None):
    """Decorator to register a node class.

    Provides a convenient decorator pattern for automatic node
    registration when the module is imported.

    Usage patterns:
        @register_node()
        class MyNode(Node):
            pass

        @register_node(alias='CustomName')
        class MyNode(Node):
            pass

    Registration timing:

    - Occurs when module is imported
    - Before any workflow creation
    - Enables automatic discovery

    Error handling:

    - Wraps registration errors
    - Provides clear error messages
    - Preserves original class

    Args:
        alias: Optional alias for the node (defaults to class name)

    Returns:
        Decorator function that:

        - Registers the node class
        - Returns the unmodified class
        - Handles registration errors

    Example::

        @register_node(alias='CSV')
        class CSVReaderNode(Node):
            def get_parameters(self):
                return {'file': NodeParameter(...)}

            def run(self, file):
                return pd.read_csv(file)
    """

    def decorator(node_class: Type[Node]):
        """Inner decorator that performs registration.

        Args:
            node_class: The node class to register

        Returns:
            The unmodified node class

        Raises:
            NodeConfigurationError: If registration fails
        """
        try:
            NodeRegistry.register(node_class, alias)
        except Exception as e:
            raise NodeConfigurationError(
                f"Failed to register node {node_class.__name__}: {e}"
            ) from e
        return node_class

    return decorator
