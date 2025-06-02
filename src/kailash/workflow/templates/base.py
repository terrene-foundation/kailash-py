"""
Core workflow template system implementation.

This module provides the foundation for creating reusable, parameterized workflow
templates that can be instantiated with different configurations.
"""

from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kailash.workflow.graph import Workflow


class TemplateParameter(BaseModel):
    """
    Definition of a template parameter with validation and metadata.

    Template parameters define the configurable aspects of a workflow template,
    including type validation, default values, and choice constraints.
    """

    name: str = Field(..., description="Parameter name")
    type: Type = Field(..., description="Expected parameter type")
    description: str = Field(..., description="Human-readable parameter description")
    required: bool = Field(True, description="Whether parameter is required")
    default: Any = Field(None, description="Default value if not provided")
    choices: Optional[List[Any]] = Field(None, description="Valid parameter choices")
    validation_func: Optional[Callable[[Any], bool]] = Field(
        None, description="Custom validation function"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("default")
    @classmethod
    def validate_default_type(cls, v, info):
        """Validate that default value matches expected type."""
        if v is not None and "type" in info.data:
            expected_type = info.data["type"]
            if not isinstance(v, expected_type):
                raise ValueError(
                    f"Default value {v} does not match expected type {expected_type}"
                )
        return v

    def validate_value(self, value: Any) -> bool:
        """
        Validate a parameter value against constraints.

        Args:
            value: Value to validate

        Returns:
            bool: True if value is valid

        Raises:
            ValueError: If validation fails
        """
        # Type check
        if not isinstance(value, self.type):
            raise ValueError(
                f"Parameter '{self.name}' expects type {self.type}, got {type(value)}"
            )

        # Choice constraint
        if self.choices and value not in self.choices:
            raise ValueError(
                f"Parameter '{self.name}' must be one of {self.choices}, got {value}"
            )

        # Custom validation
        if self.validation_func and not self.validation_func(value):
            raise ValueError(f"Parameter '{self.name}' failed custom validation")

        return True


class WorkflowTemplate:
    """
    Reusable workflow template with parameterization support.

    Workflow templates provide a way to create parameterized workflow factories
    that can be instantiated with different configurations. This enables reuse
    of common workflow patterns across different use cases.

    Design Features:
        1. Parameter validation and type checking
        2. Factory function pattern for workflow creation
        3. Template metadata and categorization
        4. Composition support for building larger workflows
        5. Serialization for distribution and storage

    Usage Patterns:
        1. Define parameters that customize workflow behavior
        2. Implement factory function that builds workflow from parameters
        3. Register template in central registry for discovery
        4. Instantiate template with specific parameter values
        5. Compose with other templates for complex workflows

    Example::

        # Create a data processing template
        template = WorkflowTemplate(
            template_id="etl_pipeline",
            name="ETL Data Pipeline",
            description="Extract, transform, load data processing",
            category="data_processing"
        )

        # Add parameters
        template.add_parameter(TemplateParameter(
            name="input_path",
            type=str,
            description="Path to input data file"
        ))

        template.add_parameter(TemplateParameter(
            name="transform_type",
            type=str,
            description="Type of transformation",
            choices=["filter", "aggregate", "map"],
            default="filter"
        ))

        # Define workflow factory
        def build_etl(input_path: str, transform_type: str) -> Workflow:
            builder = WorkflowBuilder()
            builder.add_node("reader", "CSVReader", config={"file_path": input_path})
            builder.add_node("transform", f"{transform_type}Node")
            builder.add_node("writer", "CSVWriter")
            builder.add_connection("reader", "data", "transform", "input")
            builder.add_connection("transform", "output", "writer", "data")
            return builder.build()

        template.set_workflow_factory(build_etl)

        # Instantiate template
        workflow = template.instantiate(
            input_path="data.csv",
            transform_type="filter"
        )
    """

    def __init__(
        self,
        template_id: str,
        name: str,
        description: str,
        category: str = "general",
        version: str = "1.0.0",
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        """
        Initialize workflow template.

        Args:
            template_id: Unique identifier for the template
            name: Human-readable template name
            description: Detailed template description
            category: Template category for organization
            version: Template version for compatibility tracking
            author: Template author information
            tags: Tags for searchability and categorization
        """
        self.template_id = template_id
        self.name = name
        self.description = description
        self.category = category
        self.version = version
        self.author = author
        self.tags = tags or []

        self.parameters: Dict[str, TemplateParameter] = {}
        self._workflow_factory: Optional[Callable[..., Workflow]] = None
        self._base_config: Dict[str, Any] = {}

    def add_parameter(self, param: TemplateParameter) -> None:
        """
        Add a parameter to the template.

        Args:
            param: Template parameter to add
        """
        self.parameters[param.name] = param

    def remove_parameter(self, param_name: str) -> None:
        """
        Remove a parameter from the template.

        Args:
            param_name: Name of parameter to remove
        """
        if param_name in self.parameters:
            del self.parameters[param_name]

    def set_workflow_factory(self, factory_func: Callable[..., Workflow]) -> None:
        """
        Set the factory function that builds workflows from parameters.

        Args:
            factory_func: Function that takes parameters and returns a Workflow
        """
        self._workflow_factory = factory_func

    def set_base_config(self, config: Dict[str, Any]) -> None:
        """
        Set base configuration that will be merged with parameters.

        Args:
            config: Base configuration dictionary
        """
        self._base_config = config

    def get_parameter_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all template parameters.

        Returns:
            Dict mapping parameter names to their metadata
        """
        return {
            name: {
                "type": param.type.__name__,
                "description": param.description,
                "required": param.required,
                "default": param.default,
                "choices": param.choices,
            }
            for name, param in self.parameters.items()
        }

    def validate_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and process template parameters.

        Args:
            params: Parameter values to validate

        Returns:
            Dict of validated parameters with defaults applied

        Raises:
            ValueError: If parameter validation fails
        """
        validated_params = {}

        # Check all required parameters are provided
        for name, param in self.parameters.items():
            if param.required and name not in params:
                if param.default is not None:
                    validated_params[name] = param.default
                else:
                    raise ValueError(f"Required parameter '{name}' not provided")
            elif name in params:
                # Validate the provided value
                param.validate_value(params[name])
                validated_params[name] = params[name]
            elif param.default is not None:
                validated_params[name] = param.default

        # Check for unexpected parameters
        unexpected = set(params.keys()) - set(self.parameters.keys())
        if unexpected:
            raise ValueError(f"Unexpected parameters: {unexpected}")

        return validated_params

    def instantiate(self, **params) -> Workflow:
        """
        Create a workflow instance from the template with given parameters.

        Args:
            **params: Parameter values for template instantiation

        Returns:
            Workflow instance configured with the parameters

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If no workflow factory is set
        """
        # Validate parameters
        validated_params = self.validate_parameters(params)

        # Merge with base configuration
        final_params = {**self._base_config, **validated_params}

        # Create workflow using factory
        if self._workflow_factory:
            try:
                workflow = self._workflow_factory(**final_params)

                # Set workflow metadata
                if hasattr(workflow, "metadata"):
                    workflow.metadata.update(
                        {
                            "template_id": self.template_id,
                            "template_version": self.version,
                            "instantiation_params": validated_params,
                        }
                    )

                return workflow
            except Exception as e:
                raise RuntimeError(
                    f"Failed to instantiate template '{self.template_id}': {e}"
                )
        else:
            raise RuntimeError(
                f"No workflow factory set for template '{self.template_id}'"
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize template to dictionary format.

        Returns:
            Dict representation of the template
        """
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "parameters": {
                name: {
                    "type": param.type.__name__,
                    "description": param.description,
                    "required": param.required,
                    "default": param.default,
                    "choices": param.choices,
                }
                for name, param in self.parameters.items()
            },
            "base_config": self._base_config,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], factory_func: Optional[Callable] = None
    ) -> "WorkflowTemplate":
        """
        Create template from dictionary representation.

        Args:
            data: Dictionary containing template data
            factory_func: Optional workflow factory function

        Returns:
            WorkflowTemplate instance
        """
        template = cls(
            template_id=data["template_id"],
            name=data["name"],
            description=data["description"],
            category=data.get("category", "general"),
            version=data.get("version", "1.0.0"),
            author=data.get("author"),
            tags=data.get("tags", []),
        )

        # Add parameters
        for name, param_data in data.get("parameters", {}).items():
            # Convert type name back to type
            type_map = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
            }
            param_type = type_map.get(param_data["type"], str)

            param = TemplateParameter(
                name=name,
                type=param_type,
                description=param_data["description"],
                required=param_data.get("required", True),
                default=param_data.get("default"),
                choices=param_data.get("choices"),
            )
            template.add_parameter(param)

        # Set base config
        template.set_base_config(data.get("base_config", {}))

        # Set factory if provided
        if factory_func:
            template.set_workflow_factory(factory_func)

        return template

    def __repr__(self) -> str:
        return f"WorkflowTemplate(id='{self.template_id}', name='{self.name}', category='{self.category}')"
