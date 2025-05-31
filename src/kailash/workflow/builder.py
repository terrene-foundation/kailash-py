"""Workflow builder implementation for the Kailash SDK."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from kailash.sdk_exceptions import ConnectionError, WorkflowValidationError
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class WorkflowBuilder:
    """Builder pattern for creating Workflow instances."""

    def __init__(self):
        """Initialize an empty workflow builder."""
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.connections: List[Dict[str, str]] = []
        self._metadata: Dict[str, Any] = {}

    def add_node(
        self,
        node_type: str,
        node_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a node to the workflow.

        Args:
            node_type: Node type name
            node_id: Unique identifier for this node (auto-generated if not provided)
            config: Configuration for the node

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

        self.nodes[node_id] = {"type": node_type, "config": config or {}}

        logger.info(f"Added node '{node_id}' of type '{node_type}'")
        return node_id

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

    def build(self, workflow_id: Optional[str] = None, **kwargs) -> Workflow:
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
                node_type = node_info["type"]
                node_config = node_info.get("config", {})

                # Add the node to workflow
                workflow._add_node_internal(node_id, node_type, node_config)
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
    def from_dict(cls, config: Dict[str, Any]) -> "WorkflowBuilder":
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
