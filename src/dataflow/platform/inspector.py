"""
Introspection API for debugging DataFlow without reading source code.

Provides detailed information about:
- Models and their schemas
- Generated nodes and parameters
- DataFlow instance configuration
- Workflows using DataFlow nodes
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ModelInfo:
    """Information about a DataFlow model."""

    name: str
    table_name: str
    schema: dict[str, Any]
    generated_nodes: list[str]
    parameters: dict[str, dict[str, Any]]  # node_type -> parameters
    primary_key: Optional[str] = None

    def show(self, color: bool = True) -> str:
        """Format model information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Model: {self.name}{RESET}")
        parts.append(f"Table: {self.table_name}")
        if self.primary_key:
            parts.append(f"Primary Key: {self.primary_key}")
        parts.append("")

        # Schema
        parts.append(f"{GREEN}Schema:{RESET}")
        for field_name, field_info in self.schema.items():
            parts.append(f"  {field_name}: {field_info}")
        parts.append("")

        # Generated nodes
        parts.append(f"{GREEN}Generated Nodes ({len(self.generated_nodes)}):{RESET}")
        for node_type in self.generated_nodes:
            parts.append(f"  - {node_type}")
        parts.append("")

        # Parameters per node
        parts.append(f"{GREEN}Parameters per Node:{RESET}")
        for node_type, params in self.parameters.items():
            parts.append(f"  {node_type}:")
            for param_name, param_info in params.items():
                parts.append(f"    - {param_name}: {param_info}")

        return "\n".join(parts)


@dataclass
class NodeInfo:
    """Information about a specific DataFlow node."""

    node_id: str
    node_type: str
    model_name: str
    expected_params: dict[str, Any]
    output_params: dict[str, Any]
    connections_in: list[dict[str, str]] = field(default_factory=list)
    connections_out: list[dict[str, str]] = field(default_factory=list)
    usage_example: str = ""

    def show(self, color: bool = True) -> str:
        """Format node information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Node: {self.node_id}{RESET}")
        parts.append(f"Type: {self.node_type}")
        parts.append(f"Model: {self.model_name}")
        parts.append("")

        # Expected parameters
        parts.append(f"{GREEN}Expected Input Parameters:{RESET}")
        if self.expected_params:
            for param_name, param_info in self.expected_params.items():
                required = param_info.get("required", False)
                param_type = param_info.get("type", "any")
                req_marker = f"{YELLOW}*{RESET}" if required else " "
                parts.append(f"  {req_marker} {param_name}: {param_type}")
                if "description" in param_info:
                    parts.append(f"      {param_info['description']}")
        else:
            parts.append("  (none)")
        parts.append("")

        # Output parameters
        parts.append(f"{GREEN}Output Parameters:{RESET}")
        if self.output_params:
            for param_name, param_info in self.output_params.items():
                parts.append(f"  - {param_name}: {param_info}")
        else:
            parts.append("  (none)")
        parts.append("")

        # Connections
        if self.connections_in:
            parts.append(f"{GREEN}Incoming Connections:{RESET}")
            for conn in self.connections_in:
                parts.append(
                    f"  {conn['source']}.{conn['source_param']} -> {conn['target_param']}"
                )
            parts.append("")

        if self.connections_out:
            parts.append(f"{GREEN}Outgoing Connections:{RESET}")
            for conn in self.connections_out:
                parts.append(
                    f"  {conn['source_param']} -> {conn['target']}.{conn['target_param']}"
                )
            parts.append("")

        # Usage example
        if self.usage_example:
            parts.append(f"{GREEN}Usage Example:{RESET}")
            parts.append(self.usage_example)

        return "\n".join(parts)

    def show_expected_params(self) -> str:
        """Show only expected parameters (compact format)."""
        parts = []
        parts.append(f"Expected parameters for '{self.node_id}':")
        for param_name, param_info in self.expected_params.items():
            required = " (required)" if param_info.get("required") else " (optional)"
            parts.append(f"  - {param_name}: {param_info.get('type', 'any')}{required}")
        return "\n".join(parts)


@dataclass
class InstanceInfo:
    """Information about a DataFlow instance."""

    name: str
    config: dict[str, Any]
    models: dict[str, Any]
    migrations: dict[str, Any]
    health: dict[str, Any]
    database_url: str

    def show(self, color: bool = True) -> str:
        """Format instance information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}DataFlow Instance: {self.name}{RESET}")
        parts.append(f"Database: {self.database_url}")
        parts.append("")

        # Health status
        health_status = self.health.get("status", "unknown")
        health_color = GREEN if health_status == "healthy" else RED
        parts.append(f"Health: {health_color}{health_status}{RESET}")
        if self.health.get("issues"):
            parts.append("Issues:")
            for issue in self.health["issues"]:
                parts.append(f"  - {issue}")
        parts.append("")

        # Models
        parts.append(f"{GREEN}Registered Models ({len(self.models)}):{RESET}")
        for model_name in self.models:
            parts.append(f"  - {model_name}")
        parts.append("")

        # Configuration
        parts.append(f"{GREEN}Configuration:{RESET}")
        for key, value in self.config.items():
            parts.append(f"  {key}: {value}")
        parts.append("")

        # Migrations
        parts.append(f"{GREEN}Migrations:{RESET}")
        for key, value in self.migrations.items():
            parts.append(f"  {key}: {value}")

        return "\n".join(parts)


@dataclass
class WorkflowInfo:
    """Information about a workflow using DataFlow nodes."""

    workflow_id: str
    dataflow_nodes: list[str]
    parameter_flow: dict[str, list[str]]  # node_id -> [connected_nodes]
    validation_issues: list[str] = field(default_factory=list)

    def show(self, color: bool = True) -> str:
        """Format workflow information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Workflow: {self.workflow_id}{RESET}")
        parts.append("")

        # DataFlow nodes
        parts.append(f"{GREEN}DataFlow Nodes ({len(self.dataflow_nodes)}):{RESET}")
        for node_id in self.dataflow_nodes:
            parts.append(f"  - {node_id}")
        parts.append("")

        # Parameter flow
        parts.append(f"{GREEN}Parameter Flow:{RESET}")
        for node_id, connected_nodes in self.parameter_flow.items():
            parts.append(f"  {node_id}:")
            for connected in connected_nodes:
                parts.append(f"    -> {connected}")
        parts.append("")

        # Validation issues
        if self.validation_issues:
            parts.append(f"{YELLOW}Validation Issues:{RESET}")
            for issue in self.validation_issues:
                parts.append(f"  - {issue}")

        return "\n".join(parts)


class Inspector:
    """
    Introspection API for debugging DataFlow without reading source code.

    Provides detailed information about models, nodes, instance state,
    and workflows without requiring users to navigate large source files.
    """

    def __init__(self, studio: Any):
        """
        Initialize inspector.

        Args:
            studio: DataFlowStudio instance or DataFlow instance
        """
        self.studio = studio
        # Handle both DataFlowStudio and raw DataFlow instances
        self.db = getattr(studio, "db", studio)

    def model(self, model_name: str) -> ModelInfo:
        """
        Get detailed information about a model.

        Args:
            model_name: Name of the model

        Returns:
            ModelInfo instance with schema, nodes, and parameters

        Example:
            >>> info = inspector.model("User")
            >>> print(info.show())
            >>> print(info.schema)
            >>> print(info.generated_nodes)
        """
        # Get model from DataFlow
        models = getattr(self.db, "_models", {})
        model_class = models.get(model_name)

        if not model_class:
            raise ValueError(f"Model '{model_name}' not found")

        # Extract schema information
        schema = {}
        table_name = ""
        primary_key = None

        if hasattr(model_class, "__table__"):
            table = model_class.__table__
            table_name = table.name

            for column in table.columns:
                schema[column.name] = {
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                }
                if column.primary_key:
                    primary_key = column.name

        # Generate list of nodes
        generated_nodes = [
            f"{model_name}CreateNode",
            f"{model_name}ReadNode",
            f"{model_name}ReadByIdNode",
            f"{model_name}UpdateNode",
            f"{model_name}DeleteNode",
            f"{model_name}ListNode",
            f"{model_name}CountNode",
            f"{model_name}UpsertNode",
            f"{model_name}BulkCreateNode",
        ]

        # Generate parameter information for each node type
        parameters = {
            "create": {
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Dictionary with model fields",
                }
            },
            "read": {
                "filters": {
                    "required": False,
                    "type": "dict",
                    "description": "Filter conditions",
                }
            },
            "read_by_id": {
                f"{primary_key}": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                }
            },
            "update": {
                f"{primary_key}": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                },
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Fields to update",
                },
            },
            "delete": {
                f"{primary_key}": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                }
            },
        }

        return ModelInfo(
            name=model_name,
            table_name=table_name,
            schema=schema,
            generated_nodes=generated_nodes,
            parameters=parameters,
            primary_key=primary_key,
        )

    def node(self, node_id: str) -> NodeInfo:
        """
        Get detailed information about a specific node.

        Args:
            node_id: Node identifier

        Returns:
            NodeInfo instance with parameters and connections

        Example:
            >>> info = inspector.node("user_create")
            >>> print(info.show())
            >>> print(info.expected_params)
        """
        # Parse node ID to extract model and type
        # This is simplified - real implementation would query DataFlow
        parts = node_id.split("_")
        if len(parts) >= 2:
            model_name = parts[0].title()
            node_type = "_".join(parts[1:])
        else:
            model_name = "Unknown"
            node_type = "unknown"

        # Get expected parameters based on node type
        expected_params = {}
        if node_type == "create":
            expected_params = {
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Dictionary containing model fields",
                }
            }
        elif node_type == "read_by_id":
            expected_params = {
                "id": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                }
            }
        elif node_type == "update":
            expected_params = {
                "id": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                },
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Fields to update",
                },
            }

        # Output parameters
        output_params = {}
        if node_type in ["create", "read", "read_by_id", "update"]:
            output_params = {
                "result": {"type": "dict", "description": f"{model_name} instance"}
            }
        elif node_type == "delete":
            output_params = {
                "success": {"type": "bool", "description": "Whether deletion succeeded"}
            }

        # Usage example
        usage_example = f"""
# Add node to workflow
workflow.add_node("{model_name}{node_type.title().replace('_', '')}Node", "{node_id}", {{}})

# Connect parameter
workflow.add_connection("source_node", "output", "{node_id}", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
"""

        return NodeInfo(
            node_id=node_id,
            node_type=node_type,
            model_name=model_name,
            expected_params=expected_params,
            output_params=output_params,
            usage_example=usage_example.strip(),
        )

    def instance(self) -> InstanceInfo:
        """
        Get information about the DataFlow instance.

        Returns:
            InstanceInfo with configuration and status

        Example:
            >>> info = inspector.instance()
            >>> print(info.show())
            >>> print(info.health)
        """
        # Get configuration
        config = {}
        config_attrs = [
            "enable_audit",
            "migration_strategy",
            "debug_mode",
            "pool_size",
            "max_overflow",
            "connection_validation",
        ]
        for attr in config_attrs:
            if hasattr(self.db, attr):
                config[attr] = getattr(self.db, attr)

        # Get models
        models = getattr(self.db, "_models", {})

        # Get migration info
        migrations = {
            "strategy": getattr(self.db, "migration_strategy", "unknown"),
            "pending": 0,  # This would query actual pending migrations
            "applied": 0,  # This would query applied migrations
        }

        # Get health status
        health = {"status": "healthy", "issues": []}

        # Get database URL
        database_url = getattr(self.db, "database_url", "unknown")

        # Get instance name
        name = getattr(self.studio, "name", "DataFlow")

        return InstanceInfo(
            name=name,
            config=config,
            models=models,
            migrations=migrations,
            health=health,
            database_url=database_url,
        )

    def workflow(self, workflow: Any) -> WorkflowInfo:
        """
        Get information about a workflow using DataFlow nodes.

        Args:
            workflow: WorkflowBuilder instance

        Returns:
            WorkflowInfo with nodes and parameter flow

        Example:
            >>> info = inspector.workflow(my_workflow)
            >>> print(info.show())
            >>> print(info.dataflow_nodes)
        """
        # This would analyze the workflow to find DataFlow nodes
        # and trace parameter flow
        workflow_id = getattr(workflow, "workflow_id", "unknown")

        # Extract DataFlow nodes (simplified)
        dataflow_nodes = []

        # Build parameter flow graph (simplified)
        parameter_flow = {}

        # Validation issues (simplified)
        validation_issues = []

        return WorkflowInfo(
            workflow_id=workflow_id,
            dataflow_nodes=dataflow_nodes,
            parameter_flow=parameter_flow,
            validation_issues=validation_issues,
        )

    def interactive(self):
        """
        Launch interactive debugging session.

        This starts an interactive Python shell with the inspector
        and useful utilities pre-loaded.

        Example:
            >>> inspector.interactive()
            # Interactive shell opens with inspector available
        """
        import code
        import readline  # noqa: F401 - enables history

        banner = """
DataFlow Inspector - Interactive Mode
======================================

Available objects:
  inspector - Inspector instance
  studio    - DataFlowStudio instance
  db        - DataFlow instance

Commands:
  inspector.model('ModelName')  - Inspect a model
  inspector.node('node_id')     - Inspect a node
  inspector.instance()          - Inspect DataFlow instance

Press Ctrl+D to exit.
"""

        local_vars = {"inspector": self, "studio": self.studio, "db": self.db}

        code.interact(banner=banner, local=local_vars)
