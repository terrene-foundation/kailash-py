"""Workflow builder implementation for the Kailash SDK."""

import logging
import uuid
from typing import Any

from kailash.sdk_exceptions import ConnectionError, WorkflowValidationError
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class WorkflowBuilder:
    """Builder pattern for creating Workflow instances."""

    def __init__(self):
        """Initialize an empty workflow builder."""
        self.nodes: dict[str, dict[str, Any]] = {}
        self.connections: list[dict[str, str]] = []
        self._metadata: dict[str, Any] = {}

    def add_node(
        self,
        node_type: str | type | Any,
        node_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a node to the workflow.

        Args:
            node_type: Node type name (string), Node class, or Node instance
            node_id: Unique identifier for this node (auto-generated if not provided)
            config: Configuration for the node (ignored if node_type is an instance)

        Returns:
            Node ID (useful for method chaining)

        Raises:
            WorkflowValidationError: If node_id is already used
        """
        # Generate ID if not provided
        if node_id is None:
            node_id = f"node_{uuid.uuid4().hex[:8]}"

        if node_id in self.nodes:
            raise WorkflowValidationError(
                f"Node ID '{node_id}' already exists in workflow"
            )

        # Import Node here to avoid circular imports
        from kailash.nodes.base import Node

        # Handle different input types
        if isinstance(node_type, str):
            # String node type name
            self.nodes[node_id] = {"type": node_type, "config": config or {}}
            type_name = node_type
        elif isinstance(node_type, type) and issubclass(node_type, Node):
            # Node class
            self.nodes[node_id] = {
                "type": node_type.__name__,
                "config": config or {},
                "class": node_type,
            }
            type_name = node_type.__name__
        elif hasattr(node_type, "__class__") and issubclass(node_type.__class__, Node):
            # Node instance
            self.nodes[node_id] = {
                "instance": node_type,
                "type": node_type.__class__.__name__,
            }
            type_name = node_type.__class__.__name__
        else:
            raise WorkflowValidationError(
                f"Invalid node type: {type(node_type)}. "
                "Expected: str (node type name), Node class, or Node instance"
            )

        logger.info(f"Added node '{node_id}' of type '{type_name}'")
        return node_id

    def add_node_instance(self, node_instance: Any, node_id: str | None = None) -> str:
        """
        Add a node instance to the workflow.

        This is a convenience method for adding pre-configured node instances.

        Args:
            node_instance: Pre-configured node instance
            node_id: Unique identifier for this node (auto-generated if not provided)

        Returns:
            Node ID

        Raises:
            WorkflowValidationError: If node_id is already used or instance is invalid
        """
        return self.add_node(node_instance, node_id)

    def add_node_type(
        self,
        node_type: str,
        node_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a node by type name to the workflow.

        This is the original string-based method, provided for clarity and backward compatibility.

        Args:
            node_type: Node type name as string
            node_id: Unique identifier for this node (auto-generated if not provided)
            config: Configuration for the node

        Returns:
            Node ID

        Raises:
            WorkflowValidationError: If node_id is already used
        """
        return self.add_node(node_type, node_id, config)

    def add_connection(
        self, from_node: str, from_output: str, to_node: str, to_input: str
    ) -> None:
        """
        Connect two nodes in the workflow.

        Args:
            from_node: Source node ID
            from_output: Output field from source
            to_node: Target node ID
            to_input: Input field on target

        Raises:
            WorkflowValidationError: If nodes don't exist
            ConnectionError: If connection is invalid
        """
        if from_node not in self.nodes:
            raise WorkflowValidationError(
                f"Source node '{from_node}' not found in workflow"
            )
        if to_node not in self.nodes:
            raise WorkflowValidationError(
                f"Target node '{to_node}' not found in workflow"
            )

        # Self-connection check
        if from_node == to_node:
            raise ConnectionError(f"Cannot connect node '{from_node}' to itself")

        # Add connection to list
        connection = {
            "from_node": from_node,
            "from_output": from_output,
            "to_node": to_node,
            "to_input": to_input,
        }
        self.connections.append(connection)

        logger.info(f"Connected '{from_node}.{from_output}' to '{to_node}.{to_input}'")

    def connect(
        self,
        from_node: str,
        to_node: str,
        mapping: dict = None,
        from_output: str = None,
        to_input: str = None,
    ) -> None:
        """
        Connect two nodes in the workflow with flexible parameter formats.

        This method provides a more intuitive API for connecting nodes and supports
        both simple connections and complex mapping-based connections.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            mapping: Dict mapping from_output to to_input (e.g., {"data": "input"})
            from_output: Single output field (alternative to mapping)
            to_input: Single input field (alternative to mapping)

        Examples:
            # Simple connection
            workflow.connect("node1", "node2", from_output="data", to_input="input")

            # Mapping-based connection
            workflow.connect("node1", "node2", mapping={"data": "input"})

            # Default data flow
            workflow.connect("node1", "node2")  # Uses "data" -> "data"
        """
        if mapping:
            # Handle mapping-based connections
            for from_out, to_in in mapping.items():
                self.add_connection(from_node, from_out, to_node, to_in)
        elif from_output and to_input:
            # Handle explicit parameter connections
            self.add_connection(from_node, from_output, to_node, to_input)
        else:
            # Default data flow
            self.add_connection(from_node, "data", to_node, "data")

    def set_metadata(self, **kwargs) -> "WorkflowBuilder":
        """
        Set workflow metadata.

        Args:
            **kwargs: Metadata key-value pairs

        Returns:
            Self for chaining
        """
        self._metadata.update(kwargs)
        return self

    def build(self, workflow_id: str | None = None, **kwargs) -> Workflow:
        """
        Build and return a Workflow instance.

        Args:
            workflow_id: Workflow identifier (auto-generated if not provided)
            **kwargs: Additional metadata (name, description, version, etc.)

        Returns:
            Configured Workflow instance

        Raises:
            WorkflowValidationError: If workflow building fails
        """
        # Generate ID if not provided
        if workflow_id is None:
            workflow_id = str(uuid.uuid4())

        # Prepare metadata
        metadata = self._metadata.copy()
        metadata.update(kwargs)
        if "name" not in metadata:
            metadata["name"] = f"Workflow-{workflow_id[:8]}"

        # Get basic workflow properties
        name = metadata.pop("name")
        description = metadata.pop("description", "")
        version = metadata.pop("version", "1.0.0")
        author = metadata.pop("author", "")

        # Create workflow
        workflow = Workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            version=version,
            author=author,
            metadata=metadata,
        )

        # Add nodes to workflow
        for node_id, node_info in self.nodes.items():
            try:
                if "instance" in node_info:
                    # Node instance was provided
                    workflow.add_node(
                        node_id=node_id, node_or_type=node_info["instance"]
                    )
                elif "class" in node_info:
                    # Node class was provided
                    node_class = node_info["class"]
                    node_config = node_info.get("config", {})
                    workflow.add_node(
                        node_id=node_id, node_or_type=node_class, **node_config
                    )
                else:
                    # String node type
                    node_type = node_info["type"]
                    node_config = node_info.get("config", {})
                    workflow.add_node(
                        node_id=node_id, node_or_type=node_type, **node_config
                    )
            except Exception as e:
                raise WorkflowValidationError(
                    f"Failed to add node '{node_id}' to workflow: {e}"
                ) from e

        # Add connections to workflow
        for conn in self.connections:
            try:
                from_node = conn["from_node"]
                from_output = conn["from_output"]
                to_node = conn["to_node"]
                to_input = conn["to_input"]

                # Add the connection to workflow
                workflow._add_edge_internal(from_node, from_output, to_node, to_input)
            except Exception as e:
                raise WorkflowValidationError(
                    f"Failed to connect '{from_node}' to '{to_node}': {e}"
                ) from e

        logger.info(
            f"Built workflow '{workflow_id}' with "
            f"{len(self.nodes)} nodes and {len(self.connections)} connections"
        )
        return workflow

    def clear(self) -> "WorkflowBuilder":
        """
        Clear builder state.

        Returns:
            Self for chaining
        """
        self.nodes = {}
        self.connections = []
        self._metadata = {}
        return self

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "WorkflowBuilder":
        """
        Create builder from dictionary configuration.

        Args:
            config: Dictionary with workflow configuration

        Returns:
            Configured WorkflowBuilder instance

        Raises:
            WorkflowValidationError: If configuration is invalid
        """
        builder = cls()

        # Extract metadata
        for key, value in config.items():
            if key not in ["nodes", "connections"]:
                builder._metadata[key] = value

        # Add nodes
        for node_config in config.get("nodes", []):
            node_id = node_config.get("id")
            node_type = node_config.get("type")
            node_params = node_config.get("config", {})

            if not node_id:
                raise WorkflowValidationError("Node ID is required")
            if not node_type:
                raise WorkflowValidationError(
                    f"Node type is required for node '{node_id}'"
                )

            builder.add_node(node_type, node_id, node_params)

        # Add connections
        for conn in config.get("connections", []):
            from_node = conn.get("from_node")
            from_output = conn.get("from_output")
            to_node = conn.get("to_node")
            to_input = conn.get("to_input")

            if not all([from_node, from_output, to_node, to_input]):
                raise WorkflowValidationError(
                    f"Invalid connection: missing required fields. Connection data: {conn}"
                )

            builder.add_connection(from_node, from_output, to_node, to_input)

        return builder
