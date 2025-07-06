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

import inspect
import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from collections import OrderedDict
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

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
        default_factory=lambda: datetime.now(UTC),
        description="Node creation date",
    )
    tags: set[str] = Field(default_factory=set, description="Node tags")


class NodeParameter(BaseModel):
    """Definition of a node parameter with enhanced auto-mapping capabilities.

    This class defines the schema for node inputs and outputs, providing:

    1. Type information for validation
    2. Default values for optional parameters
    3. Documentation for users
    4. Requirements specification
    5. Auto-mapping from workflow connections (NEW)

    Enhanced Features (v0.2.0):
    - auto_map_from: Alternative parameter names for flexible mapping
    - auto_map_primary: Designates primary input for automatic data routing
    - workflow_alias: Preferred name in workflow connections
    - These features enable robust parameter resolution across all node types

    Design Purpose:
    - Enables static analysis of workflow connections
    - Provides runtime validation of data types
    - Supports automatic UI generation for node configuration
    - Facilitates workflow validation before execution
    - Resolves parameter mapping issues between workflow data and node inputs

    Upstream usage:
    - Node.get_parameters(): Returns dict of parameters
    - Custom nodes: Define their input/output schemas

    Downstream consumers:
    - Node._validate_config(): Validates configuration against parameters
    - Node.validate_inputs(): Validates runtime inputs with auto-mapping
    - Workflow.connect(): Validates connections between nodes
    - WorkflowExporter: Exports parameter schemas
    """

    name: str
    type: type
    required: bool = True
    default: Any = None
    description: str = ""

    # Enhanced auto-mapping capabilities
    auto_map_from: list[str] = Field(
        default_factory=list, description="Alternative parameter names for auto-mapping"
    )
    auto_map_primary: bool = Field(
        default=False, description="Use as primary input for automatic data routing"
    )
    workflow_alias: str = Field(
        default="", description="Preferred name in workflow connections"
    )


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

    # Class-level configuration
    _DEFAULT_CACHE_SIZE = 128
    _SPECIAL_PARAMS = {"context"}  # Parameters excluded from cache key

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

            # Filter out internal fields from config
            internal_fields = {
                "id",
                "name",
                "description",
                "version",
                "author",
                "tags",
                "metadata",
            }
            self.config = {k: v for k, v in kwargs.items() if k not in internal_fields}

            # Parameter resolution cache - initialize before validation
            cache_size = int(
                os.environ.get("KAILASH_PARAM_CACHE_SIZE", self._DEFAULT_CACHE_SIZE)
            )
            self._cache_enabled = (
                os.environ.get("KAILASH_DISABLE_PARAM_CACHE", "").lower() != "true"
            )

            # Use OrderedDict for LRU implementation
            self._param_cache = OrderedDict()
            self._param_cache_lock = threading.Lock()
            self._cache_max_size = cache_size
            self._cached_params = None

            # Cache statistics
            self._cache_hits = 0
            self._cache_misses = 0
            self._cache_evictions = 0

            self._validate_config()
        except ValidationError as e:
            raise NodeConfigurationError(f"Invalid node metadata: {e}") from e
        except Exception as e:
            raise NodeConfigurationError(
                f"Failed to initialize node '{self.id}': {e}"
            ) from e

    @abstractmethod
    def get_parameters(self) -> dict[str, NodeParameter]:
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

        Example:
            >>> def get_parameters(self):
            ...     return {
            ...         'input_file': NodeParameter(
            ...             name='input_file',
            ...             type=str,
            ...             required=True,
            ...             description='Path to input CSV file'
            ...         ),
            ...         'delimiter': NodeParameter(
            ...             name='delimiter',
            ...             type=str,
            ...             required=False,
            ...             default=',',
            ...             description='CSV delimiter character'
            ...         )
            ...     }

        Returns:
            Dictionary mapping parameter names to their definitions

        Used by:
            - _validate_config(): Validates configuration matches parameters
            - validate_inputs(): Validates runtime inputs
            - to_dict(): Includes parameters in serialization
            - Workflow.connect(): Validates compatible connections
        """

    def get_output_schema(self) -> dict[str, NodeParameter]:
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

        Example:
            >>> def get_output_schema(self):
            ...     return {
            ...         'dataframe': NodeParameter(
            ...             name='dataframe',
            ...             type=dict,
            ...             required=True,
            ...             description='Processed data as dictionary'
            ...         ),
            ...         'row_count': NodeParameter(
            ...             name='row_count',
            ...             type=int,
            ...             required=True,
            ...             description='Number of rows processed'
            ...         ),
            ...         'processing_time': NodeParameter(
            ...             name='processing_time',
            ...             type=float,
            ...             required=False,
            ...             description='Time taken to process in seconds'
            ...         )
            ...     }

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

    def run(self, **kwargs) -> dict[str, Any]:
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

        Example:
            >>> def run(self, input_file, delimiter=','):
            ...     df = pd.read_csv(input_file, delimiter=delimiter)
            ...     return {
            ...         'dataframe': df.to_dict(),
            ...         'row_count': len(df),
            ...         'columns': list(df.columns)
            ...     }

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
        # This is a synchronous node - subclass must override this method
        raise NotImplementedError(
            f"Node '{self.__class__.__name__}' must implement run() method"
        )

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
            params = self._get_cached_parameters()
        except Exception as e:
            raise NodeConfigurationError(f"Failed to get node parameters: {e}") from e

        for param_name, param_def in params.items():
            if param_name not in self.config:
                if param_def.required and param_def.default is None:
                    # During node construction, we may not have all parameters yet
                    # Skip validation for required parameters - they will be validated at execution time
                    continue
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

    def _get_cached_parameters(self) -> dict[str, NodeParameter]:
        """Get cached parameter definitions.

        Returns:
            Dictionary of parameter definitions, cached for performance
        """
        if self._cached_params is None:
            try:
                self._cached_params = self.get_parameters()
            except Exception as e:
                raise NodeValidationError(
                    f"Failed to get node parameters for validation: {e}"
                ) from e
        return self._cached_params

    def validate_inputs(self, **kwargs) -> dict[str, Any]:
        r"""Validate runtime inputs against node requirements.

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
        # Use cached parameters for better performance
        params = self._get_cached_parameters()

        # Check if caching is enabled
        if not self._cache_enabled:
            resolved = self._resolve_parameters(kwargs, params)
        else:
            # Check if we have a cached resolution for this input pattern
            cache_key = self._get_cache_key(kwargs)

            with self._param_cache_lock:
                if cache_key in self._param_cache:
                    # Move to end for LRU
                    self._param_cache.move_to_end(cache_key)
                    self._cache_hits += 1

                    # Use cached resolution and apply values
                    cached_mapping = self._param_cache[cache_key]
                    resolved = self._apply_cached_mapping(kwargs, cached_mapping)
                else:
                    self._cache_misses += 1

                    # Phase 1: Resolve parameters using enhanced mapping
                    resolved = self._resolve_parameters(kwargs, params)

                    # Cache the mapping pattern for future use
                    mapping = self._extract_mapping_pattern(kwargs, resolved)
                    self._param_cache[cache_key] = mapping

                    # Evict oldest if cache is full (LRU)
                    if len(self._param_cache) > self._cache_max_size:
                        self._param_cache.popitem(last=False)  # Remove oldest
                        self._cache_evictions += 1

        # Phase 2: Validate resolved parameters
        validated = self._validate_resolved_parameters(resolved, params)

        # Preserve special runtime parameters that are not in schema
        for special_param in self._SPECIAL_PARAMS:
            if special_param in kwargs:
                validated[special_param] = kwargs[special_param]

        return validated

    def _get_cached_parameters(self) -> dict[str, NodeParameter]:
        """Get node parameters with caching for performance.

        Returns:
            Cached parameter definitions
        """
        if self._cached_params is None:
            self._cached_params = self.get_parameters()
        return self._cached_params

    def _get_cache_key(self, inputs: dict) -> str:
        """Generate a cache key based on input parameter names.

        Args:
            inputs: Runtime inputs dictionary

        Returns:
            Cache key string based on sorted parameter names
        """
        # Exclude special parameters from cache key
        cache_params = [k for k in inputs.keys() if k not in self._SPECIAL_PARAMS]
        return "|".join(sorted(cache_params))

    def _apply_cached_mapping(self, inputs: dict, mapping: dict) -> dict:
        """Apply cached mapping pattern to current inputs.

        Args:
            inputs: Current runtime inputs
            mapping: Cached mapping pattern

        Returns:
            Resolved parameters dictionary
        """
        resolved = {}
        for param_name, source_key in mapping.items():
            if source_key in inputs:
                resolved[param_name] = inputs[source_key]
        return resolved

    def _extract_mapping_pattern(self, inputs: dict, resolved: dict) -> dict:
        """Extract the mapping pattern for caching.

        The cache stores which input keys map to which parameter names,
        allowing fast resolution for repeated input patterns.

        Args:
            inputs: Original runtime inputs
            resolved: Resolved parameters

        Returns:
            Mapping pattern dictionary {param_name: input_key}
        """
        mapping = {}

        # Build reverse mapping from resolved params to input keys
        # This tracks the resolution decisions made by _resolve_parameters
        for param_name in resolved:
            # Direct match - parameter name exists in inputs
            if param_name in inputs and self._safe_compare(
                inputs[param_name], resolved[param_name]
            ):
                mapping[param_name] = param_name
            else:
                # Search for which input key provided this parameter value
                # Must match exact resolution logic from _resolve_parameters
                params = self._get_cached_parameters()
                param_def = params.get(param_name)

                if param_def:
                    # Check workflow alias
                    if param_def.workflow_alias and param_def.workflow_alias in inputs:
                        if self._safe_compare(
                            inputs[param_def.workflow_alias], resolved[param_name]
                        ):
                            mapping[param_name] = param_def.workflow_alias
                            continue

                    # Check auto_map_from alternatives
                    if param_def.auto_map_from:
                        for alt_name in param_def.auto_map_from:
                            if alt_name in inputs and self._safe_compare(
                                inputs[alt_name], resolved[param_name]
                            ):
                                mapping[param_name] = alt_name
                                break

        return mapping

    def _safe_compare(self, value1: Any, value2: Any) -> bool:
        """Safely compare two values, handling special cases like DataFrames.

        Args:
            value1: First value to compare
            value2: Second value to compare

        Returns:
            True if values are equal, False otherwise
        """
        # Handle pandas DataFrame and Series
        try:
            import pandas as pd

            if isinstance(value1, (pd.DataFrame, pd.Series)) or isinstance(
                value2, (pd.DataFrame, pd.Series)
            ):
                # For DataFrames/Series, use identity comparison
                # This is safe for caching since we're tracking object references
                return value1 is value2
        except ImportError:
            pass

        # Handle numpy arrays
        try:
            import numpy as np

            if isinstance(value1, np.ndarray) or isinstance(value2, np.ndarray):
                # For numpy arrays, use identity comparison
                return value1 is value2
        except ImportError:
            pass

        # For all other types, use standard equality
        try:
            return value1 == value2
        except (ValueError, TypeError):
            # If comparison fails, they're not equal
            return False

    def _resolve_parameters(self, runtime_inputs: dict, params: dict) -> dict:
        """Enhanced parameter resolution with auto-mapping.

        This method implements the core parameter mapping logic that resolves
        workflow inputs to node parameters using multiple strategies:

        1. Direct parameter matches (existing behavior)
        2. Workflow alias mapping
        3. Auto-mapping from alternative names
        4. Primary input auto-detection

        Args:
            runtime_inputs: Inputs provided by workflow runtime
            params: Node parameter definitions from get_parameters()

        Returns:
            Dict mapping parameter names to resolved values
        """
        resolved = {}
        used_inputs = set()

        # Optimized single-pass resolution combining all phases
        for param_name, param_def in params.items():
            # Skip if already resolved
            if param_name in resolved:
                continue

            # Phase 1: Direct match (highest priority)
            if param_name in runtime_inputs:
                resolved[param_name] = runtime_inputs[param_name]
                used_inputs.add(param_name)
                continue

            # Phase 2: Workflow alias
            if param_def.workflow_alias and param_def.workflow_alias in runtime_inputs:
                resolved[param_name] = runtime_inputs[param_def.workflow_alias]
                used_inputs.add(param_def.workflow_alias)
                continue

            # Phase 3: Auto-mapping alternatives
            if param_def.auto_map_from:
                for alt_name in param_def.auto_map_from:
                    if alt_name in runtime_inputs and alt_name not in used_inputs:
                        resolved[param_name] = runtime_inputs[alt_name]
                        used_inputs.add(alt_name)
                        break

        # Phase 4: Primary input auto-mapping (handled separately for efficiency)
        primary_params = []
        for param_name, param_def in params.items():
            if param_def.auto_map_primary and param_name not in resolved:
                primary_params.append((param_name, param_def))

        if len(primary_params) == 1:
            param_name, param_def = primary_params[0]
            # Find the main data input (usually the largest unused input)
            remaining_inputs = {
                k: v
                for k, v in runtime_inputs.items()
                if k not in used_inputs and not k.startswith("_")
            }
            if remaining_inputs:
                # Use the input with the most substantial data as primary
                main_input = max(
                    remaining_inputs.items(),
                    key=lambda x: len(str(x[1])) if x[1] is not None else 0,
                )
                resolved[param_name] = main_input[1]
                used_inputs.add(main_input[0])

        return resolved

    def _validate_resolved_parameters(self, resolved: dict, params: dict) -> dict:
        """Validate resolved parameters against their definitions.

        Args:
            resolved: Parameters resolved by _resolve_parameters
            params: Node parameter definitions

        Returns:
            Dict of validated parameters with type conversions applied

        Raises:
            NodeValidationError: If validation fails
        """
        validated = {}

        for param_name, param_def in params.items():
            if param_name in resolved:
                value = resolved[param_name]
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

            elif param_def.required:
                if param_def.default is not None:
                    validated[param_name] = param_def.default
                else:
                    # Enhanced error message with suggestions
                    available = list(resolved.keys()) if resolved else ["none"]
                    suggestions = self._suggest_parameter_mapping(
                        param_name, list(resolved.keys())
                    )
                    raise NodeValidationError(
                        f"Required parameter '{param_name}' not provided. "
                        f"Available resolved inputs: {available}. "
                        f"Mapping suggestions: {suggestions}. "
                        f"Description: {param_def.description or 'No description available'}"
                    )

        return validated

    def _suggest_parameter_mapping(
        self, param_name: str, available: list[str]
    ) -> list[str]:
        """Suggest likely parameter mappings based on name similarity.

        Args:
            param_name: The parameter name we're trying to map
            available: List of available input names

        Returns:
            List of suggested parameter names
        """
        try:
            import difflib

            return difflib.get_close_matches(param_name, available, n=3, cutoff=0.3)
        except ImportError:
            # Fallback if difflib is not available
            return [
                name
                for name in available
                if param_name.lower() in name.lower()
                or name.lower() in param_name.lower()
            ]

    def validate_outputs(self, outputs: dict[str, Any]) -> dict[str, Any]:
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

    def execute(self, **runtime_inputs) -> dict[str, Any]:
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
        start_time = datetime.now(UTC)
        try:
            self.logger.info(f"Executing node {self.id}")

            # Merge runtime inputs with config (runtime inputs take precedence)
            merged_inputs = {**self.config, **runtime_inputs}

            # Handle nested config case (for nodes that store parameters in config['config'])
            if "config" in merged_inputs and isinstance(merged_inputs["config"], dict):
                # Extract nested config but preserve runtime input precedence
                nested_config = merged_inputs["config"]
                # ENTERPRISE PARAMETER INJECTION FIX: Runtime inputs should take precedence over config dict
                # First apply config dict values, then re-apply runtime inputs to ensure they override
                for key, value in nested_config.items():
                    if (
                        key not in runtime_inputs
                    ):  # Only use config values if not overridden by runtime
                        merged_inputs[key] = value
                # Don't remove the config key as some nodes might need it

            # Validate inputs
            validated_inputs = self.validate_inputs(**merged_inputs)
            self.logger.debug(f"Validated inputs for {self.id}: {validated_inputs}")

            # Execute node logic
            outputs = self.run(**validated_inputs)

            # Validate outputs
            validated_outputs = self.validate_outputs(outputs)

            execution_time = (datetime.now(UTC) - start_time).total_seconds()
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

    def get_cache_stats(self) -> dict[str, Any]:
        """Get parameter cache statistics.

        Returns:
            Dictionary containing cache statistics:
            - enabled: Whether caching is enabled
            - size: Current cache size
            - max_size: Maximum cache size
            - hits: Number of cache hits
            - misses: Number of cache misses
            - evictions: Number of cache evictions
            - hit_rate: Cache hit rate (0-1)
        """
        with self._param_cache_lock:
            total_requests = self._cache_hits + self._cache_misses
            hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0

            return {
                "enabled": self._cache_enabled,
                "size": len(self._param_cache),
                "max_size": self._cache_max_size,
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "evictions": self._cache_evictions,
                "hit_rate": hit_rate,
            }

    def clear_cache(self) -> None:
        """Clear the parameter resolution cache and reset statistics."""
        with self._param_cache_lock:
            self._param_cache.clear()
            self._cache_hits = 0
            self._cache_misses = 0
            self._cache_evictions = 0

    def warm_cache(self, patterns: list[dict[str, Any]]) -> None:
        """Warm the cache with known parameter patterns.

        Args:
            patterns: List of parameter dictionaries to pre-cache
        """
        if not self._cache_enabled:
            return

        for pattern in patterns:
            # Simulate parameter resolution to populate cache
            try:
                self.validate_inputs(**pattern)
            except Exception:
                # Ignore validation errors during warmup
                pass

    def to_dict(self) -> dict[str, Any]:
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
    _nodes: dict[str, type[Node]] = {}

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
    def register(cls, node_class: type[Node], alias: str | None = None):
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

        # Validate constructor signature (Core SDK improvement)
        cls._validate_node_constructor(node_class)

        node_name = alias or node_class.__name__

        if node_name in cls._nodes:
            logging.warning(f"Overwriting existing node registration for '{node_name}'")

        cls._nodes[node_name] = node_class
        logging.info(f"Registered node '{node_name}'")

    @classmethod
    def _validate_node_constructor(cls, node_class: type[Node]):
        """Validate that node constructor follows SDK patterns.

        This is a core SDK improvement to ensure all nodes have consistent
        constructor signatures that work with WorkflowBuilder.from_dict().

        Validates that the node constructor either:
        1. Accepts 'name' parameter (like PythonCodeNode)
        2. Accepts 'id' parameter (traditional pattern)
        3. Uses **kwargs to accept both

        Args:
            node_class: Node class to validate

        Raises:
            NodeConfigurationError: If constructor signature is incompatible
        """
        try:
            sig = inspect.signature(node_class.__init__)
            params = list(sig.parameters.keys())

            # Skip 'self' parameter
            if "self" in params:
                params.remove("self")

            # Check if constructor accepts required parameters
            has_name = "name" in params
            has_id = "id" in params
            has_kwargs = any(
                param.kind == param.VAR_KEYWORD for param in sig.parameters.values()
            )

            if not (has_name or has_id or has_kwargs):
                logging.warning(
                    f"Node {node_class.__name__} constructor may not work with WorkflowBuilder.from_dict(). "
                    f"Constructor should accept 'name', 'id', or **kwargs parameter. "
                    f"Current parameters: {params}"
                )

        except Exception as e:
            # Don't fail registration for signature inspection issues
            logging.warning(
                f"Could not validate constructor for {node_class.__name__}: {e}"
            )

    @classmethod
    def get(cls, node_name: str) -> type[Node]:
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
    def list_nodes(cls) -> dict[str, type[Node]]:
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

        Warning:
            >>> # Warning: This affects all future operations
            >>> # - Subsequent get() calls will fail
            >>> # - Workflows may not deserialize
            >>> # - Should re-register needed nodes
        """
        cls._nodes.clear()
        logging.info("Cleared all registered nodes")


def register_node(alias: str | None = None):
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

    Example:
        >>> @register_node(alias='CSV')
        ... class CSVReaderNode(Node):
        ...     def get_parameters(self):
        ...         return {'file': NodeParameter(...)}
        ...
        ...     def run(self, file):
        ...         return pd.read_csv(file)
    """

    def decorator(node_class: type[Node]):
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
