"""Workflow DAG implementation for the Kailash SDK."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import yaml
from pydantic import BaseModel, Field, ValidationError

from kailash.nodes.base import Node

try:
    # For normal runtime, use the actual registry
    from kailash.nodes.base import NodeRegistry
except ImportError:
    # For tests, use the mock registry
    from kailash.workflow.mock_registry import MockRegistry as NodeRegistry

from kailash.sdk_exceptions import (
    ConnectionError,
    ExportException,
    NodeConfigurationError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.workflow.state import WorkflowStateWrapper

logger = logging.getLogger(__name__)


class NodeInstance(BaseModel):
    """Instance of a node in a workflow."""

    node_id: str = Field(..., description="Unique identifier for this instance")
    node_type: str = Field(..., description="Type of node")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Node configuration"
    )
    position: Tuple[float, float] = Field(default=(0, 0), description="Visual position")


class Connection(BaseModel):
    """Connection between two nodes in a workflow."""

    source_node: str = Field(..., description="Source node ID")
    source_output: str = Field(..., description="Output field from source")
    target_node: str = Field(..., description="Target node ID")
    target_input: str = Field(..., description="Input field on target")


class Workflow:
    """Represents a workflow DAG of nodes."""

    def __init__(
        self,
        workflow_id: str,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        author: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a workflow.

        Args:
            workflow_id: Unique workflow identifier
            name: Workflow name
            description: Workflow description
            version: Workflow version
            author: Workflow author
            metadata: Additional metadata

        Raises:
            WorkflowValidationError: If workflow initialization fails
        """
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.version = version
        self.author = author
        self.metadata = metadata or {}

        # Add standard metadata
        if "author" not in self.metadata and author:
            self.metadata["author"] = author
        if "version" not in self.metadata and version:
            self.metadata["version"] = version
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = datetime.now(timezone.utc).isoformat()

        # Create directed graph for the workflow
        self.graph = nx.DiGraph()

        # Storage for node instances and node metadata
        self._node_instances = {}  # Maps node_id to Node instances
        self.nodes = {}  # Maps node_id to NodeInstance metadata objects
        self.connections = []  # List of Connection objects

        logger.info(f"Created workflow '{name}' (ID: {workflow_id})")

    def add_node(self, node_id: str, node_or_type: Any, **config) -> None:
        """Add a node to the workflow.

        Args:
            node_id: Unique identifier for this node instance
            node_or_type: Either a Node instance, Node class, or node type name
            **config: Configuration for the node

        Raises:
            WorkflowValidationError: If node is invalid
            NodeConfigurationError: If node configuration fails
        """
        if node_id in self.nodes:
            raise WorkflowValidationError(
                f"Node '{node_id}' already exists in workflow. "
                f"Existing nodes: {list(self.nodes.keys())}"
            )

        try:
            # Handle different input types
            if isinstance(node_or_type, str):
                # Node type name provided
                node_class = NodeRegistry.get(node_or_type)
                node_instance = node_class(id=node_id, **config)
                node_type = node_or_type
            elif isinstance(node_or_type, type) and issubclass(node_or_type, Node):
                # Node class provided
                node_instance = node_or_type(id=node_id, **config)
                node_type = node_or_type.__name__
            elif isinstance(node_or_type, Node):
                # Node instance provided
                node_instance = node_or_type
                node_instance.id = node_id
                node_type = node_instance.__class__.__name__
                # Update config - handle nested config case
                if "config" in node_instance.config and isinstance(
                    node_instance.config["config"], dict
                ):
                    # If config is nested, extract it
                    actual_config = node_instance.config["config"]
                    node_instance.config.update(actual_config)
                    # Remove the nested config key
                    del node_instance.config["config"]
                # Now update with provided config
                node_instance.config.update(config)
                node_instance._validate_config()
            else:
                raise WorkflowValidationError(
                    f"Invalid node type: {type(node_or_type)}. "
                    "Expected: str (node type name), Node class, or Node instance"
                )
        except NodeConfigurationError:
            # Re-raise configuration errors with additional context
            raise
        except Exception as e:
            raise NodeConfigurationError(
                f"Failed to create node '{node_id}' of type '{node_or_type}': {e}"
            ) from e

        # Store node instance and metadata
        try:
            node_instance_data = NodeInstance(
                node_id=node_id,
                node_type=node_type,
                config=config,
                position=(len(self.nodes) * 150, 100),
            )
            self.nodes[node_id] = node_instance_data
        except ValidationError as e:
            raise WorkflowValidationError(f"Invalid node instance data: {e}") from e

        self._node_instances[node_id] = node_instance

        # Add to graph
        self.graph.add_node(node_id, node=node_instance, type=node_type, config=config)
        logger.info(f"Added node '{node_id}' of type '{node_type}'")

    def _add_node_internal(
        self, node_id: str, node_type: str, config: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a node to the workflow (internal method).

        Args:
            node_id: Node identifier
            node_type: Node type name
            config: Node configuration
        """
        # This method is used by WorkflowBuilder and from_dict
        config = config or {}
        self.add_node(node_id=node_id, node_or_type=node_type, **config)

    def connect(
        self,
        source_node: str,
        target_node: str,
        mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        """Connect two nodes in the workflow.

        Args:
            source_node: Source node ID
            target_node: Target node ID
            mapping: Dict mapping source outputs to target inputs

        Raises:
            ConnectionError: If connection is invalid
            WorkflowValidationError: If nodes don't exist
        """
        if source_node not in self.nodes:
            available_nodes = ", ".join(self.nodes.keys())
            raise WorkflowValidationError(
                f"Source node '{source_node}' not found in workflow. "
                f"Available nodes: {available_nodes}"
            )
        if target_node not in self.nodes:
            available_nodes = ", ".join(self.nodes.keys())
            raise WorkflowValidationError(
                f"Target node '{target_node}' not found in workflow. "
                f"Available nodes: {available_nodes}"
            )

        # Self-connection check
        if source_node == target_node:
            raise ConnectionError(f"Cannot connect node '{source_node}' to itself")

        # Default mapping if not provided
        if mapping is None:
            mapping = {"output": "input"}

        # Check for existing connections
        existing_connections = [
            c
            for c in self.connections
            if c.source_node == source_node and c.target_node == target_node
        ]
        if existing_connections:
            raise ConnectionError(
                f"Connection already exists between '{source_node}' and '{target_node}'. "
                f"Existing mappings: {[c.model_dump() for c in existing_connections]}"
            )

        # Create connections
        for source_output, target_input in mapping.items():
            try:
                connection = Connection(
                    source_node=source_node,
                    source_output=source_output,
                    target_node=target_node,
                    target_input=target_input,
                )
            except ValidationError as e:
                raise ConnectionError(f"Invalid connection data: {e}") from e

            self.connections.append(connection)

            # Add edge to graph
            self.graph.add_edge(
                source_node,
                target_node,
                from_output=source_output,
                to_input=target_input,
                mapping={
                    source_output: target_input
                },  # Keep for backward compatibility
            )

        logger.info(
            f"Connected '{source_node}' to '{target_node}' with mapping: {mapping}"
        )

    def _add_edge_internal(
        self, from_node: str, from_output: str, to_node: str, to_input: str
    ) -> None:
        """Add an edge between nodes (internal method).

        Args:
            from_node: Source node ID
            from_output: Output field from source
            to_node: Target node ID
            to_input: Input field on target
        """
        # This method is used by WorkflowBuilder and from_dict
        self.connect(
            source_node=from_node, target_node=to_node, mapping={from_output: to_input}
        )

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get node instance by ID.

        Args:
            node_id: Node identifier

        Returns:
            Node instance or None if not found
        """
        if node_id not in self.graph.nodes:
            return None

        # First try to get from graph (for test compatibility)
        graph_node = self.graph.nodes[node_id].get("node")
        if graph_node:
            return graph_node

        # Fallback to _node_instances
        return self._node_instances.get(node_id)

    def get_execution_order(self) -> List[str]:
        """Get topological execution order for nodes.

        Returns:
            List of node IDs in execution order

        Raises:
            WorkflowValidationError: If workflow contains cycles
        """
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible:
            cycles = list(nx.simple_cycles(self.graph))
            raise WorkflowValidationError(
                f"Workflow contains cycles: {cycles}. "
                "Remove circular dependencies to create a valid workflow."
            )

    def validate(self) -> None:
        """Validate the workflow structure.

        Raises:
            WorkflowValidationError: If workflow is invalid
        """
        # Check for cycles
        try:
            self.get_execution_order()
        except WorkflowValidationError:
            raise

        # Check all nodes have required inputs
        for node_id, node_instance in self._node_instances.items():
            try:
                params = node_instance.get_parameters()
            except Exception as e:
                raise WorkflowValidationError(
                    f"Failed to get parameters for node '{node_id}': {e}"
                ) from e

            # Get inputs from connections
            incoming_edges = self.graph.in_edges(node_id, data=True)
            connected_inputs = set()

            for _, _, data in incoming_edges:
                to_input = data.get("to_input")
                if to_input:
                    connected_inputs.add(to_input)
                # For backward compatibility
                mapping = data.get("mapping", {})
                connected_inputs.update(mapping.values())

            # Check required parameters
            missing_inputs = []
            for param_name, param_def in params.items():
                if param_def.required and param_name not in connected_inputs:
                    # Check if it's provided in config
                    # Handle nested config case (for PythonCodeNode and similar)
                    found_in_config = param_name in node_instance.config
                    if not found_in_config and "config" in node_instance.config:
                        # Check nested config
                        found_in_config = param_name in node_instance.config["config"]

                    if not found_in_config:
                        if param_def.default is None:
                            missing_inputs.append(param_name)

            if missing_inputs:
                raise WorkflowValidationError(
                    f"Node '{node_id}' missing required inputs: {missing_inputs}. "
                    f"Provide these inputs via connections or node configuration"
                )

        logger.info(f"Workflow '{self.name}' validated successfully")

    def run(
        self, task_manager: Optional[TaskManager] = None, **overrides
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute the workflow.

        Args:
            task_manager: Optional task manager for tracking
            **overrides: Parameter overrides

        Returns:
            Tuple of (results dict, run_id)

        Raises:
            WorkflowExecutionError: If workflow execution fails
            WorkflowValidationError: If workflow is invalid
        """
        # For backward compatibility with original graph.py's run method
        return self.execute(inputs=overrides, task_manager=task_manager), None

    def execute(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        task_manager: Optional[TaskManager] = None,
    ) -> Dict[str, Any]:
        """Execute the workflow.

        Args:
            inputs: Input data for the workflow (can include node overrides)
            task_manager: Optional task manager for tracking

        Returns:
            Execution results by node

        Raises:
            WorkflowExecutionError: If execution fails
        """
        try:
            self.validate()
        except Exception as e:
            raise WorkflowValidationError(f"Workflow validation failed: {e}") from e

        # Initialize task tracking
        run_id = None
        if task_manager:
            try:
                run_id = task_manager.create_run(
                    workflow_name=self.name, metadata={"inputs": inputs}
                )
            except Exception as e:
                logger.warning(f"Failed to create task run: {e}")
                # Continue without task tracking

        # Get execution order
        try:
            execution_order = self.get_execution_order()
        except Exception as e:
            raise WorkflowExecutionError(
                f"Failed to determine execution order: {e}"
            ) from e

        # Execute nodes in order
        results = {}
        inputs = inputs or {}
        failed_nodes = []

        for node_id in execution_order:
            node_instance = self._node_instances[node_id]

            # Start task tracking
            task = None
            if task_manager and run_id:
                try:
                    task = task_manager.create_task(
                        run_id=run_id,
                        node_id=node_id,
                        node_type=node_instance.__class__.__name__,
                    )
                    task.update_status(TaskStatus.RUNNING)
                except Exception as e:
                    logger.warning(f"Failed to create task for node '{node_id}': {e}")

            try:
                # Gather inputs from previous nodes
                node_inputs = {}

                # Add config values
                node_inputs.update(node_instance.config)

                # Get inputs from connected nodes
                for edge in self.graph.in_edges(node_id, data=True):
                    source_node_id = edge[0]
                    edge_data = self.graph[source_node_id][node_id]

                    # Try both connection formats for backward compatibility
                    from_output = edge_data.get("from_output")
                    to_input = edge_data.get("to_input")
                    mapping = edge_data.get("mapping", {})

                    source_results = results.get(source_node_id, {})

                    # Add connections using from_output/to_input format
                    if from_output and to_input and from_output in source_results:
                        node_inputs[to_input] = source_results[from_output]

                    # Also add connections using mapping format for backward compatibility
                    for source_key, target_key in mapping.items():
                        if source_key in source_results:
                            node_inputs[target_key] = source_results[source_key]

                # Apply overrides
                node_overrides = inputs.get(node_id, {})
                node_inputs.update(node_overrides)

                # Execute node
                logger.info(
                    f"Executing node '{node_id}' with inputs: {list(node_inputs.keys())}"
                )

                # Support both process() and execute() methods
                if hasattr(node_instance, "process") and callable(
                    node_instance.process
                ):
                    node_results = node_instance.process(node_inputs)
                else:
                    node_results = node_instance.execute(**node_inputs)

                results[node_id] = node_results

                if task:
                    task.update_status(TaskStatus.COMPLETED, result=node_results)

                logger.info(f"Node '{node_id}' completed successfully")

            except Exception as e:
                failed_nodes.append(node_id)
                if task:
                    task.update_status(TaskStatus.FAILED, error=str(e))

                # Include previous failures in error message
                error_msg = f"Node '{node_id}' failed: {e}"
                if len(failed_nodes) > 1:
                    error_msg += f" (Previously failed nodes: {failed_nodes[:-1]})"

                raise WorkflowExecutionError(error_msg) from e

        logger.info(
            f"Workflow '{self.name}' completed successfully. "
            f"Executed {len(execution_order)} nodes"
        )
        return results

    def export_to_kailash(
        self, output_path: str, format: str = "yaml", **config
    ) -> None:
        """Export workflow to Kailash-compatible format.

        Args:
            output_path: Path to write file
            format: Export format (yaml, json, manifest)
            **config: Additional export configuration

        Raises:
            ExportException: If export fails
        """
        try:
            from kailash.utils.export import export_workflow

            export_workflow(self, format=format, output_path=output_path, **config)
        except ImportError as e:
            raise ExportException(f"Failed to import export utilities: {e}") from e
        except Exception as e:
            raise ExportException(
                f"Failed to export workflow to '{output_path}': {e}"
            ) from e

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary.

        Returns:
            Dictionary representation
        """
        # Build nodes dictionary
        nodes_dict = {}
        for node_id, node_data in self.nodes.items():
            nodes_dict[node_id] = node_data.model_dump()

        # Build connections list
        connections_list = [conn.model_dump() for conn in self.connections]

        # Build workflow dictionary
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "metadata": self.metadata,
            "nodes": nodes_dict,
            "connections": connections_list,
        }

    def to_json(self) -> str:
        """Convert workflow to JSON string.

        Returns:
            JSON representation
        """
        return json.dumps(self.to_dict(), indent=2)

    def to_yaml(self) -> str:
        """Convert workflow to YAML string.

        Returns:
            YAML representation
        """
        return yaml.dump(self.to_dict(), default_flow_style=False)

    def save(self, path: str, format: str = "json") -> None:
        """Save workflow to file.

        Args:
            path: Output file path
            format: Output format (json or yaml)

        Raises:
            ValueError: If format is invalid
        """
        if format == "json":
            with open(path, "w") as f:
                f.write(self.to_json())
        elif format == "yaml":
            with open(path, "w") as f:
                f.write(self.to_yaml())
        else:
            raise ValueError(f"Unsupported format: {format}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        """Create workflow from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            Workflow instance

        Raises:
            WorkflowValidationError: If data is invalid
        """
        try:
            # Extract basic data
            workflow_id = data.get("workflow_id", str(uuid.uuid4()))
            name = data.get("name", "Unnamed Workflow")
            description = data.get("description", "")
            version = data.get("version", "1.0.0")
            author = data.get("author", "")
            metadata = data.get("metadata", {})

            # Create workflow
            workflow = cls(
                workflow_id=workflow_id,
                name=name,
                description=description,
                version=version,
                author=author,
                metadata=metadata,
            )

            # Add nodes
            nodes_data = data.get("nodes", {})
            for node_id, node_data in nodes_data.items():
                # Handle both formats of node data
                if isinstance(node_data, dict):
                    # Get node type
                    node_type = node_data.get("node_type") or node_data.get("type")
                    if not node_type:
                        raise WorkflowValidationError(
                            f"Node type not specified for node '{node_id}'"
                        )

                    # Get node config
                    config = node_data.get("config", {})

                    # Add the node
                    workflow._add_node_internal(node_id, node_type, config)
                else:
                    raise WorkflowValidationError(
                        f"Invalid node data format for node '{node_id}': {type(node_data)}"
                    )

            # Add connections
            connections = data.get("connections", [])
            for conn_data in connections:
                # Handle both connection formats
                if "source_node" in conn_data and "target_node" in conn_data:
                    # Original format
                    source_node = conn_data.get("source_node")
                    source_output = conn_data.get("source_output")
                    target_node = conn_data.get("target_node")
                    target_input = conn_data.get("target_input")
                    workflow._add_edge_internal(
                        source_node, source_output, target_node, target_input
                    )
                elif "from_node" in conn_data and "to_node" in conn_data:
                    # Updated format
                    from_node = conn_data.get("from_node")
                    from_output = conn_data.get("from_output", "output")
                    to_node = conn_data.get("to_node")
                    to_input = conn_data.get("to_input", "input")
                    workflow._add_edge_internal(
                        from_node, from_output, to_node, to_input
                    )
                else:
                    raise WorkflowValidationError(
                        f"Invalid connection data: {conn_data}"
                    )

            return workflow

        except Exception as e:
            if isinstance(e, WorkflowValidationError):
                raise
            raise WorkflowValidationError(
                f"Failed to create workflow from dict: {e}"
            ) from e

    def __repr__(self) -> str:
        """Get string representation."""
        return f"Workflow(id='{self.workflow_id}', name='{self.name}', nodes={len(self.graph.nodes)}, connections={len(self.graph.edges)})"

    def __str__(self) -> str:
        """Get readable string."""
        return f"Workflow '{self.name}' (ID: {self.workflow_id}) with {len(self.graph.nodes)} nodes and {len(self.graph.edges)} connections"

    def create_state_wrapper(self, state_model: BaseModel) -> WorkflowStateWrapper:
        """Create a state manager wrapper for a workflow.

        This wrapper provides convenient methods for updating state immutably,
        making it easier to manage state in workflow nodes.

        Args:
            state_model: The Pydantic model state object to wrap

        Returns:
            A WorkflowStateWrapper instance

        Raises:
            TypeError: If state_model is not a Pydantic BaseModel
        """
        if not isinstance(state_model, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_model)}")

        return WorkflowStateWrapper(state_model)

    def execute_with_state(
        self,
        state_model: BaseModel,
        wrap_state: bool = True,
        task_manager: Optional[TaskManager] = None,
        **overrides,
    ) -> Tuple[BaseModel, Dict[str, Any]]:
        """Execute the workflow with state management.

        This method provides a simplified interface for executing workflows
        with automatic state management, making it easier to manage state
        transitions.

        Args:
            state_model: The initial state for workflow execution
            wrap_state: Whether to wrap state in WorkflowStateWrapper
            task_manager: Optional task manager for tracking
            **overrides: Additional parameter overrides

        Returns:
            Tuple of (final state, all results)

        Raises:
            WorkflowExecutionError: If execution fails
            WorkflowValidationError: If workflow is invalid
        """
        # Validate input
        if not isinstance(state_model, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_model)}")

        # Prepare inputs
        inputs = {}

        # Wrap the state if needed
        if wrap_state:
            state_wrapper = self.create_state_wrapper(state_model)
            # Find entry nodes (nodes with no incoming edges) and provide state_wrapper to them
            for node_id in self.nodes:
                if self.graph.in_degree(node_id) == 0:  # Entry node
                    inputs[node_id] = {"state_wrapper": state_wrapper}
        else:
            # Find entry nodes and provide unwrapped state to them
            for node_id in self.nodes:
                if self.graph.in_degree(node_id) == 0:  # Entry node
                    inputs[node_id] = {"state": state_model}

        # Add any additional overrides
        for key, value in overrides.items():
            if key in self.nodes:
                inputs.setdefault(key, {}).update(value)

        # Execute the workflow
        results = self.execute(inputs=inputs, task_manager=task_manager)

        # Find the final state
        # First try to find state_wrapper in the last node's outputs
        execution_order = self.get_execution_order()
        if execution_order:
            last_node_id = execution_order[-1]
            last_node_results = results.get(last_node_id, {})

            if wrap_state:
                final_state_wrapper = last_node_results.get("state_wrapper")
                if final_state_wrapper and isinstance(
                    final_state_wrapper, WorkflowStateWrapper
                ):
                    return final_state_wrapper.get_state(), results

                # Try to find another key with a WorkflowStateWrapper
                for key, value in last_node_results.items():
                    if isinstance(value, WorkflowStateWrapper):
                        return value.get_state(), results
            else:
                final_state = last_node_results.get("state")
                if final_state and isinstance(final_state, BaseModel):
                    return final_state, results

                # Try to find another key with a BaseModel
                for key, value in last_node_results.items():
                    if isinstance(value, BaseModel) and isinstance(
                        value, type(state_model)
                    ):
                        return value, results

        # Fallback to original state
        logger.warning(
            "Failed to find final state in workflow results, returning original state"
        )
        return state_model, results
