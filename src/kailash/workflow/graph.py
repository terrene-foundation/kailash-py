"""Workflow DAG implementation for the Kailash SDK."""
import json
import yaml
import logging
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime

import networkx as nx
from pydantic import BaseModel, Field, ValidationError

from kailash.nodes import Node, NodeRegistry
from kailash.sdk_exceptions import (
    WorkflowValidationError,
    WorkflowExecutionError,
    NodeExecutionError,
    CyclicDependencyError,
    ConnectionError,
    NodeConfigurationError,
    ImportException,
    ExportException
)
from kailash.tracking import TaskManager, TaskStatus


logger = logging.getLogger(__name__)


class NodeInstance(BaseModel):
    """Instance of a node in a workflow."""
    node_id: str = Field(..., description="Unique identifier for this instance")
    node_type: str = Field(..., description="Type of node")
    config: Dict[str, Any] = Field(default_factory=dict, description="Node configuration")
    position: Tuple[float, float] = Field(default=(0, 0), description="Visual position")


class Connection(BaseModel):
    """Connection between two nodes in a workflow."""
    source_node: str = Field(..., description="Source node ID")
    source_output: str = Field(..., description="Output field from source")
    target_node: str = Field(..., description="Target node ID")
    target_input: str = Field(..., description="Input field on target")


class WorkflowMetadata(BaseModel):
    """Metadata for a workflow."""
    name: str = Field(..., description="Workflow name")
    description: str = Field("", description="Workflow description")
    version: str = Field("1.0.0", description="Workflow version")
    author: str = Field("", description="Workflow author")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tags: Set[str] = Field(default_factory=set)


class Workflow:
    """Represents a workflow DAG of nodes."""
    
    def __init__(self, name: str, **kwargs):
        """Initialize a workflow.
        
        Args:
            name: Workflow name
            **kwargs: Additional metadata
            
        Raises:
            WorkflowValidationError: If workflow initialization fails
        """
        try:
            self.metadata = WorkflowMetadata(
                name=name,
                description=kwargs.get('description', ''),
                version=kwargs.get('version', '1.0.0'),
                author=kwargs.get('author', ''),
                tags=kwargs.get('tags', set())
            )
        except ValidationError as e:
            raise WorkflowValidationError(
                f"Invalid workflow metadata: {e}"
            ) from e
        
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, NodeInstance] = {}
        self.connections: List[Connection] = []
        self._node_instances: Dict[str, Node] = {}
        
        logger.info(f"Created workflow '{name}'")
    
    def add_node(self, node_id: str, node_or_type: Any, **config) -> None:
        """Add a node to the workflow.
        
        Args:
            node_id: Unique identifier for this node instance
            node_or_type: Either a Node instance or node type name
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
            elif isinstance(node_or_type, type) and issubclass(node_or_type, Node):
                # Node class provided
                node_instance = node_or_type(id=node_id, **config)
            elif isinstance(node_or_type, Node):
                # Node instance provided
                node_instance = node_or_type
                node_instance.id = node_id
                # Update config - handle nested config case
                if 'config' in node_instance.config and isinstance(node_instance.config['config'], dict):
                    # If config is nested, extract it
                    actual_config = node_instance.config['config']
                    node_instance.config.update(actual_config)
                    # Remove the nested config key
                    del node_instance.config['config']
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
            self.nodes[node_id] = NodeInstance(
                node_id=node_id,
                node_type=node_instance.__class__.__name__,
                config=config,
                position=(len(self.nodes) * 150, 100)
            )
        except ValidationError as e:
            raise WorkflowValidationError(
                f"Invalid node instance data: {e}"
            ) from e
            
        self._node_instances[node_id] = node_instance
        
        # Add to graph
        self.graph.add_node(node_id, node=node_instance)
        logger.info(f"Added node '{node_id}' of type '{node_instance.__class__.__name__}'")
    
    def connect(self, source_node: str, target_node: str, 
                mapping: Optional[Dict[str, str]] = None) -> None:
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
            raise ConnectionError(
                f"Cannot connect node '{source_node}' to itself"
            )
        
        # Default mapping if not provided
        if mapping is None:
            mapping = {"output": "input"}
        
        # Check for existing connections
        existing_connections = [
            c for c in self.connections 
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
                    target_input=target_input
                )
            except ValidationError as e:
                raise ConnectionError(
                    f"Invalid connection data: {e}"
                ) from e
                
            self.connections.append(connection)
            
            # Add edge to graph
            self.graph.add_edge(
                source_node, 
                target_node, 
                mapping={source_output: target_input}
            )
        
        logger.info(
            f"Connected '{source_node}' to '{target_node}' with mapping: {mapping}"
        )
    
    def validate(self) -> None:
        """Validate the workflow structure.
        
        Raises:
            CyclicDependencyError: If workflow contains cycles
            WorkflowValidationError: If workflow structure is invalid
        """
        # Check for cycles
        if not nx.is_directed_acyclic_graph(self.graph):
            cycles = list(nx.simple_cycles(self.graph))
            raise CyclicDependencyError(
                f"Workflow contains cycles: {cycles}. "
                "Remove circular dependencies to create a valid workflow"
            )
        
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
                mapping = data.get('mapping', {})
                connected_inputs.update(mapping.values())
            
            # Check required parameters
            missing_inputs = []
            for param_name, param_def in params.items():
                if param_def.required and param_name not in connected_inputs:
                    # Check if it's provided in config
                    # Handle nested config case (for PythonCodeNode and similar)
                    found_in_config = param_name in node_instance.config
                    if not found_in_config and 'config' in node_instance.config:
                        # Check nested config
                        found_in_config = param_name in node_instance.config['config']
                    
                    if not found_in_config:
                        if param_def.default is None:
                            missing_inputs.append(param_name)
                            
            if missing_inputs:
                raise WorkflowValidationError(
                    f"Node '{node_id}' missing required inputs: {missing_inputs}. "
                    f"Provide these inputs via connections or node configuration"
                )
        
        logger.info(f"Workflow '{self.metadata.name}' validated successfully")
    
    def run(self, task_manager: Optional[TaskManager] = None, 
            **overrides) -> Tuple[Dict[str, Any], Optional[str]]:
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
        try:
            self.validate()
        except Exception as e:
            raise WorkflowValidationError(
                f"Workflow validation failed: {e}"
            ) from e
        
        # Initialize task tracking
        run_id = None
        if task_manager:
            try:
                run_id = task_manager.create_run(
                    workflow_name=self.metadata.name,
                    metadata={"overrides": overrides}
                )
            except Exception as e:
                logger.warning(f"Failed to create task run: {e}")
                # Continue without task tracking
        
        # Execute in topological order
        try:
            execution_order = list(nx.topological_sort(self.graph))
        except nx.NetworkXError as e:
            raise WorkflowExecutionError(
                f"Failed to determine execution order: {e}"
            ) from e
            
        results = {}
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
                        node_type=node_instance.__class__.__name__
                    )
                except Exception as e:
                    logger.warning(f"Failed to create task for node '{node_id}': {e}")
            
            try:
                # Gather inputs from previous nodes
                inputs = {}
                
                # Add config values
                inputs.update(node_instance.config)
                
                # Add connected inputs
                for edge in self.graph.in_edges(node_id, data=True):
                    source_node_id = edge[0]
                    mapping = edge[2].get('mapping', {})
                    
                    source_results = results.get(source_node_id, {})
                    
                    for source_key, target_key in mapping.items():
                        if source_key in source_results:
                            inputs[target_key] = source_results[source_key]
                        else:
                            logger.warning(
                                f"Output '{source_key}' not found in results "
                                f"from node '{source_node_id}'"
                            )
                
                # Apply overrides
                node_overrides = overrides.get(node_id, {})
                inputs.update(node_overrides)
                
                # Execute node
                if task:
                    task.update_status(TaskStatus.RUNNING)
                
                logger.info(f"Executing node '{node_id}' with inputs: {list(inputs.keys())}")
                node_results = node_instance.execute(**inputs)
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
            f"Workflow '{self.metadata.name}' completed successfully. "
            f"Executed {len(execution_order)} nodes"
        )
        return results, run_id
    
    def export_to_kailash(self, output_path: str, format: str = "yaml", **config) -> None:
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
            raise ExportException(
                f"Failed to import export utilities: {e}"
            ) from e
        except Exception as e:
            raise ExportException(
                f"Failed to export workflow to '{output_path}': {e}"
            ) from e
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary representation.
        
        Returns:
            Dictionary representation of the workflow
            
        Raises:
            WorkflowExecutionError: If serialization fails
        """
        try:
            return {
                "metadata": self.metadata.model_dump(),
                "nodes": {
                    node_id: node.model_dump() 
                    for node_id, node in self.nodes.items()
                },
                "connections": [
                    conn.model_dump() for conn in self.connections
                ]
            }
        except Exception as e:
            raise WorkflowExecutionError(
                f"Failed to serialize workflow: {e}"
            ) from e
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        """Create workflow from dictionary representation.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Workflow instance
            
        Raises:
            ImportException: If import fails
            WorkflowValidationError: If data is invalid
        """
        try:
            # Create workflow
            metadata = data.get("metadata", {})
            workflow = cls(
                name=metadata.get("name", "unnamed"),
                description=metadata.get("description", ""),
                version=metadata.get("version", "1.0.0"),
                author=metadata.get("author", "")
            )
        except Exception as e:
            raise ImportException(
                f"Failed to create workflow from metadata: {e}"
            ) from e
        
        # Add nodes
        nodes = data.get("nodes", {})
        if not nodes:
            logger.warning("No nodes found in workflow data")
            
        for node_id, node_data in nodes.items():
            try:
                workflow.add_node(
                    node_id=node_id,
                    node_or_type=node_data["node_type"],
                    **node_data.get("config", {})
                )
            except Exception as e:
                raise ImportException(
                    f"Failed to import node '{node_id}': {e}"
                ) from e
        
        # Add connections
        connections = data.get("connections", [])
        for i, conn_data in enumerate(connections):
            try:
                workflow.connections.append(Connection(**conn_data))
                
                # Add to graph
                source_node = conn_data["source_node"]
                target_node = conn_data["target_node"]
                source_output = conn_data["source_output"]
                target_input = conn_data["target_input"]
                
                workflow.graph.add_edge(
                    source_node,
                    target_node,
                    mapping={source_output: target_input}
                )
            except Exception as e:
                raise ImportException(
                    f"Failed to import connection {i}: {e}"
                ) from e
        
        return workflow