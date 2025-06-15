"""
Dynamic Schema Generation for Kailash Middleware

Provides schema generation for nodes, workflows, and UI components to enable
dynamic frontend form generation and validation.
"""

import inspect
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union, get_type_hints

from ...nodes.base import Node, NodeParameter
from ...workflow import Workflow

logger = logging.getLogger(__name__)


class SchemaType(str, Enum):
    """Schema field types for frontend UI generation."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ENUM = "enum"
    FILE = "file"
    COLOR = "color"
    DATE = "date"
    DATETIME = "datetime"
    EMAIL = "email"
    URL = "url"
    PASSWORD = "password"
    TEXTAREA = "textarea"
    SELECT = "select"
    MULTISELECT = "multiselect"
    SLIDER = "slider"
    TOGGLE = "toggle"


class UIWidget(str, Enum):
    """UI widget types for enhanced form rendering."""

    INPUT = "input"
    TEXTAREA = "textarea"
    SELECT = "select"
    MULTISELECT = "multiselect"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    SLIDER = "slider"
    TOGGLE = "toggle"
    FILE_UPLOAD = "file_upload"
    COLOR_PICKER = "color_picker"
    DATE_PICKER = "date_picker"
    DATETIME_PICKER = "datetime_picker"
    JSON_EDITOR = "json_editor"
    CODE_EDITOR = "code_editor"


class FieldSchema:
    """Schema for a single form field."""

    def __init__(
        self,
        name: str,
        type: SchemaType,
        widget: UIWidget = None,
        label: str = None,
        description: str = None,
        required: bool = False,
        default: Any = None,
        options: List[Dict[str, Any]] = None,
        validation: Dict[str, Any] = None,
        ui_hints: Dict[str, Any] = None,
    ):
        self.name = name
        self.type = type
        self.widget = widget or self._default_widget_for_type(type)
        self.label = label or name.replace("_", " ").title()
        self.description = description
        self.required = required
        self.default = default
        self.options = options or []
        self.validation = validation or {}
        self.ui_hints = ui_hints or {}

    def _default_widget_for_type(self, schema_type: SchemaType) -> UIWidget:
        """Get default widget for schema type."""
        widget_map = {
            SchemaType.STRING: UIWidget.INPUT,
            SchemaType.INTEGER: UIWidget.INPUT,
            SchemaType.FLOAT: UIWidget.INPUT,
            SchemaType.BOOLEAN: UIWidget.TOGGLE,
            SchemaType.ARRAY: UIWidget.MULTISELECT,
            SchemaType.OBJECT: UIWidget.JSON_EDITOR,
            SchemaType.ENUM: UIWidget.SELECT,
            SchemaType.FILE: UIWidget.FILE_UPLOAD,
            SchemaType.COLOR: UIWidget.COLOR_PICKER,
            SchemaType.DATE: UIWidget.DATE_PICKER,
            SchemaType.DATETIME: UIWidget.DATETIME_PICKER,
            SchemaType.EMAIL: UIWidget.INPUT,
            SchemaType.URL: UIWidget.INPUT,
            SchemaType.PASSWORD: UIWidget.INPUT,
            SchemaType.TEXTAREA: UIWidget.TEXTAREA,
        }
        return widget_map.get(schema_type, UIWidget.INPUT)

    def to_dict(self) -> Dict[str, Any]:
        """Convert field schema to dictionary."""
        return {
            "name": self.name,
            "type": self.type.value,
            "widget": self.widget.value,
            "label": self.label,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "options": self.options,
            "validation": self.validation,
            "ui_hints": self.ui_hints,
        }


class NodeSchemaGenerator:
    """Generates schemas for nodes to enable dynamic UI creation."""

    def __init__(self):
        self.type_mapping = {
            str: SchemaType.STRING,
            int: SchemaType.INTEGER,
            float: SchemaType.FLOAT,
            bool: SchemaType.BOOLEAN,
            list: SchemaType.ARRAY,
            dict: SchemaType.OBJECT,
        }

    def generate_node_schema(self, node_class: Type[Node]) -> Dict[str, Any]:
        """Generate complete schema for a node class."""
        try:
            # Get node metadata
            node_metadata = self._extract_node_metadata(node_class)

            # Generate parameter schemas
            parameter_schemas = self._generate_parameter_schemas(node_class)

            # Generate input/output schemas
            input_schemas = self._generate_input_schemas(node_class)
            output_schemas = self._generate_output_schemas(node_class)

            # Combine into complete schema
            schema = {
                "node_type": node_class.__name__,
                "category": getattr(node_class, "category", "general"),
                "description": node_metadata["description"],
                "version": node_metadata["version"],
                "tags": node_metadata["tags"],
                "parameters": parameter_schemas,
                "inputs": input_schemas,
                "outputs": output_schemas,
                "ui_config": self._generate_ui_config(node_class),
                "validation_rules": self._generate_validation_rules(node_class),
                "examples": self._extract_examples(node_class),
            }

            return schema

        except Exception as e:
            logger.error(f"Error generating schema for {node_class.__name__}: {e}")
            return self._fallback_schema(node_class)

    def _extract_node_metadata(self, node_class: Type[Node]) -> Dict[str, Any]:
        """Extract metadata from node class."""
        doc = inspect.getdoc(node_class) or ""

        # Parse docstring for structured metadata
        description = doc.split("\n")[0] if doc else node_class.__name__

        return {
            "description": description,
            "version": getattr(node_class, "__version__", "1.0.0"),
            "tags": getattr(node_class, "tags", []),
            "author": getattr(node_class, "__author__", ""),
            "documentation": doc,
        }

    def _generate_parameter_schemas(
        self, node_class: Type[Node]
    ) -> List[Dict[str, Any]]:
        """Generate schemas for node parameters."""
        schemas = []

        try:
            # Try to get parameters from node class
            if hasattr(node_class, "get_parameters"):
                # Create a temporary instance to get parameters
                try:
                    temp_instance = node_class("temp")
                    parameters = temp_instance.get_parameters()

                    for param_name, param in parameters.items():
                        if isinstance(param, NodeParameter):
                            field_schema = self._convert_node_parameter_to_schema(
                                param_name, param
                            )
                            schemas.append(field_schema.to_dict())
                except Exception as e:
                    logger.warning(
                        f"Could not instantiate {node_class.__name__} for parameter extraction: {e}"
                    )

            # Fallback: extract from __init__ signature
            if not schemas:
                schemas = self._extract_from_init_signature(node_class)

        except Exception as e:
            logger.error(
                f"Error generating parameter schemas for {node_class.__name__}: {e}"
            )

        return schemas

    def _convert_node_parameter_to_schema(
        self, name: str, param: NodeParameter
    ) -> FieldSchema:
        """Convert NodeParameter to FieldSchema."""
        # Map NodeParameter type to SchemaType
        schema_type = self._map_type_to_schema_type(param.type)

        # Determine widget based on parameter properties
        widget = None
        if hasattr(param, "widget"):
            widget = param.widget
        elif param.type is bool:
            widget = UIWidget.TOGGLE
        elif hasattr(param, "choices") and param.choices:
            widget = UIWidget.SELECT

        # Extract validation rules
        validation = {}
        if hasattr(param, "min_value") and param.min_value is not None:
            validation["min"] = param.min_value
        if hasattr(param, "max_value") and param.max_value is not None:
            validation["max"] = param.max_value
        if hasattr(param, "pattern") and param.pattern:
            validation["pattern"] = param.pattern

        # Extract options for enums/choices
        options = []
        if hasattr(param, "choices") and param.choices:
            options = [
                {"value": choice, "label": str(choice)} for choice in param.choices
            ]

        return FieldSchema(
            name=name,
            type=schema_type,
            widget=widget,
            label=getattr(param, "label", None),
            description=getattr(param, "description", None),
            required=param.required,
            default=param.default,
            options=options,
            validation=validation,
        )

    def _map_type_to_schema_type(self, python_type: Type) -> SchemaType:
        """Map Python type to SchemaType."""
        if python_type in self.type_mapping:
            return self.type_mapping[python_type]

        # Handle special types
        if python_type is str:
            return SchemaType.STRING
        elif python_type in (int, float):
            return SchemaType.INTEGER if python_type is int else SchemaType.FLOAT
        elif python_type is bool:
            return SchemaType.BOOLEAN
        elif hasattr(python_type, "__origin__"):
            # Handle generic types like List[str], Dict[str, Any]
            origin = python_type.__origin__
            if origin in (list, List):
                return SchemaType.ARRAY
            elif origin in (dict, Dict):
                return SchemaType.OBJECT

        # Default to string for unknown types
        return SchemaType.STRING

    def _extract_from_init_signature(
        self, node_class: Type[Node]
    ) -> List[Dict[str, Any]]:
        """Extract parameter schemas from __init__ signature as fallback."""
        schemas = []

        try:
            sig = inspect.signature(node_class.__init__)
            type_hints = get_type_hints(node_class.__init__)

            for param_name, param in sig.parameters.items():
                if param_name in ("self", "name"):  # Skip self and name parameters
                    continue

                param_type = type_hints.get(param_name, str)
                schema_type = self._map_type_to_schema_type(param_type)

                field_schema = FieldSchema(
                    name=param_name,
                    type=schema_type,
                    required=param.default == param.empty,
                    default=param.default if param.default != param.empty else None,
                )

                schemas.append(field_schema.to_dict())

        except Exception as e:
            logger.error(f"Error extracting from init signature: {e}")

        return schemas

    def _generate_input_schemas(self, node_class: Type[Node]) -> List[Dict[str, Any]]:
        """Generate schemas for node inputs."""
        # This would analyze the node's process method to determine inputs
        # For now, return a generic input schema
        return [
            {
                "name": "input",
                "type": "object",
                "description": "Input data for the node",
                "required": True,
            }
        ]

    def _generate_output_schemas(self, node_class: Type[Node]) -> List[Dict[str, Any]]:
        """Generate schemas for node outputs."""
        # This would analyze the node's process method to determine outputs
        # For now, return a generic output schema
        return [
            {
                "name": "output",
                "type": "object",
                "description": "Output data from the node",
            }
        ]

    def _generate_ui_config(self, node_class: Type[Node]) -> Dict[str, Any]:
        """Generate UI configuration for the node."""
        return {
            "icon": getattr(node_class, "icon", "🔧"),
            "color": getattr(node_class, "color", "#3498db"),
            "size": getattr(node_class, "size", {"width": 200, "height": 100}),
            "ports": {
                "input": {"position": "left", "color": "#2ecc71"},
                "output": {"position": "right", "color": "#e74c3c"},
            },
        }

    def _generate_validation_rules(self, node_class: Type[Node]) -> Dict[str, Any]:
        """Generate validation rules for the node."""
        return {
            "required_parameters": [],
            "parameter_dependencies": {},
            "custom_validation": None,
        }

    def _extract_examples(self, node_class: Type[Node]) -> List[Dict[str, Any]]:
        """Extract usage examples from node documentation."""
        # This would parse docstrings or look for example attributes
        return []

    def _fallback_schema(self, node_class: Type[Node]) -> Dict[str, Any]:
        """Generate minimal fallback schema when normal generation fails."""
        return {
            "node_type": node_class.__name__,
            "category": "unknown",
            "description": f"Node: {node_class.__name__}",
            "version": "1.0.0",
            "tags": [],
            "parameters": [],
            "inputs": [{"name": "input", "type": "object"}],
            "outputs": [{"name": "output", "type": "object"}],
            "ui_config": {"icon": "❓", "color": "#95a5a6"},
            "validation_rules": {},
            "examples": [],
        }


class WorkflowSchemaGenerator:
    """Generates schemas for workflows."""

    def __init__(self, node_schema_generator: NodeSchemaGenerator = None):
        self.node_generator = node_schema_generator or NodeSchemaGenerator()

    def generate_workflow_schema(self, workflow: Workflow) -> Dict[str, Any]:
        """Generate schema for a workflow."""
        try:
            # Get workflow metadata
            workflow_metadata = {
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "description": workflow.description,
                "version": workflow.version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tags": getattr(workflow, "tags", []),
            }

            # Generate node schemas
            node_schemas = {}
            for node_id, node in workflow.nodes.items():
                node_schemas[node_id] = self.node_generator.generate_node_schema(
                    type(node)
                )
                node_schemas[node_id]["instance_id"] = node_id
                node_schemas[node_id]["instance_name"] = getattr(node, "name", node_id)

            # Generate connection schemas
            connection_schemas = []
            for connection in workflow.connections:
                connection_schemas.append(
                    {
                        "source_node": connection.source_node,
                        "source_output": connection.source_output,
                        "target_node": connection.target_node,
                        "target_input": connection.target_input,
                        "mapping": getattr(connection, "mapping", {}),
                    }
                )

            # Generate execution schema
            execution_schema = {
                "input_parameters": self._extract_workflow_inputs(workflow),
                "output_parameters": self._extract_workflow_outputs(workflow),
                "execution_order": self._determine_execution_order(workflow),
            }

            return {
                "metadata": workflow_metadata,
                "nodes": node_schemas,
                "connections": connection_schemas,
                "execution": execution_schema,
                "ui_layout": self._generate_ui_layout(workflow),
            }

        except Exception as e:
            logger.error(f"Error generating workflow schema: {e}")
            return self._fallback_workflow_schema(workflow)

    def _extract_workflow_inputs(self, workflow: Workflow) -> List[Dict[str, Any]]:
        """Extract input parameters for the workflow."""
        # Find nodes with no incoming connections
        input_nodes = []
        for node_id, node in workflow.nodes.items():
            has_incoming = any(
                conn.target_node == node_id for conn in workflow.connections
            )
            if not has_incoming:
                input_nodes.append(
                    {
                        "node_id": node_id,
                        "node_type": type(node).__name__,
                        "parameters": [],  # Would extract from node schema
                    }
                )
        return input_nodes

    def _extract_workflow_outputs(self, workflow: Workflow) -> List[Dict[str, Any]]:
        """Extract output parameters for the workflow."""
        # Find nodes with no outgoing connections
        output_nodes = []
        for node_id, node in workflow.nodes.items():
            has_outgoing = any(
                conn.source_node == node_id for conn in workflow.connections
            )
            if not has_outgoing:
                output_nodes.append(
                    {
                        "node_id": node_id,
                        "node_type": type(node).__name__,
                        "outputs": [],  # Would extract from node schema
                    }
                )
        return output_nodes

    def _determine_execution_order(self, workflow: Workflow) -> List[str]:
        """Determine execution order of nodes."""
        # Simple topological sort (would be more sophisticated in practice)
        order = []
        remaining_nodes = set(workflow.nodes.keys())

        while remaining_nodes:
            # Find nodes with no pending dependencies
            ready_nodes = []
            for node_id in remaining_nodes:
                dependencies = [
                    conn.source_node
                    for conn in workflow.connections
                    if conn.target_node == node_id
                    and conn.source_node in remaining_nodes
                ]
                if not dependencies:
                    ready_nodes.append(node_id)

            if not ready_nodes:
                # Circular dependency - add remaining arbitrarily
                ready_nodes = list(remaining_nodes)

            for node_id in ready_nodes:
                order.append(node_id)
                remaining_nodes.remove(node_id)

        return order

    def _generate_ui_layout(self, workflow: Workflow) -> Dict[str, Any]:
        """Generate UI layout information for the workflow."""
        return {
            "type": "directed_graph",
            "auto_layout": True,
            "node_spacing": {"x": 250, "y": 150},
            "grid": {"enabled": True, "size": 20},
            "zoom": {"min": 0.1, "max": 3.0, "default": 1.0},
        }

    def _fallback_workflow_schema(self, workflow: Workflow) -> Dict[str, Any]:
        """Generate minimal fallback schema for workflow."""
        return {
            "metadata": {
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "description": workflow.description
                or "Workflow schema generation failed",
                "version": "1.0.0",
            },
            "nodes": {},
            "connections": [],
            "execution": {
                "input_parameters": [],
                "output_parameters": [],
                "execution_order": [],
            },
            "ui_layout": {"type": "directed_graph"},
        }


class DynamicSchemaRegistry:
    """Registry for managing and caching generated schemas."""

    def __init__(self):
        self.node_generator = NodeSchemaGenerator()
        self.workflow_generator = WorkflowSchemaGenerator(self.node_generator)
        self.node_schemas_cache: Dict[str, Dict[str, Any]] = {}
        self.workflow_schemas_cache: Dict[str, Dict[str, Any]] = {}
        self.schema_metadata = {
            "created_at": datetime.now(timezone.utc),
            "schemas_generated": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def get_node_schema(
        self, node_class: Type[Node], use_cache: bool = True
    ) -> Dict[str, Any]:
        """Get schema for a node class with caching."""
        class_name = node_class.__name__

        if use_cache and class_name in self.node_schemas_cache:
            self.schema_metadata["cache_hits"] += 1
            return self.node_schemas_cache[class_name]

        self.schema_metadata["cache_misses"] += 1
        schema = self.node_generator.generate_node_schema(node_class)

        if use_cache:
            self.node_schemas_cache[class_name] = schema

        self.schema_metadata["schemas_generated"] += 1
        return schema

    def get_workflow_schema(
        self, workflow: Workflow, use_cache: bool = True
    ) -> Dict[str, Any]:
        """Get schema for a workflow with caching."""
        workflow_id = workflow.workflow_id

        if use_cache and workflow_id in self.workflow_schemas_cache:
            self.schema_metadata["cache_hits"] += 1
            return self.workflow_schemas_cache[workflow_id]

        self.schema_metadata["cache_misses"] += 1
        schema = self.workflow_generator.generate_workflow_schema(workflow)

        if use_cache:
            self.workflow_schemas_cache[workflow_id] = schema

        self.schema_metadata["schemas_generated"] += 1
        return schema

    def get_all_node_schemas(
        self, node_classes: List[Type[Node]]
    ) -> Dict[str, Dict[str, Any]]:
        """Get schemas for multiple node classes."""
        schemas = {}
        for node_class in node_classes:
            schemas[node_class.__name__] = self.get_node_schema(node_class)
        return schemas

    def invalidate_cache(self, node_class: Type[Node] = None, workflow_id: str = None):
        """Invalidate cached schemas."""
        if node_class:
            class_name = node_class.__name__
            if class_name in self.node_schemas_cache:
                del self.node_schemas_cache[class_name]

        if workflow_id:
            if workflow_id in self.workflow_schemas_cache:
                del self.workflow_schemas_cache[workflow_id]

        if node_class is None and workflow_id is None:
            # Clear all caches
            self.node_schemas_cache.clear()
            self.workflow_schemas_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get schema registry statistics."""
        return {
            **self.schema_metadata,
            "cached_node_schemas": len(self.node_schemas_cache),
            "cached_workflow_schemas": len(self.workflow_schemas_cache),
            "cache_hit_rate": (
                self.schema_metadata["cache_hits"]
                / (
                    self.schema_metadata["cache_hits"]
                    + self.schema_metadata["cache_misses"]
                )
                if (
                    self.schema_metadata["cache_hits"]
                    + self.schema_metadata["cache_misses"]
                )
                > 0
                else 0
            ),
        }
