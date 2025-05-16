"""Workflow DAG implementation for the Kailash SDK."""
import json
import yaml
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime

import networkx as nx
from pydantic import BaseModel, Field

from kailash.nodes import Node, NodeRegistry
from kailash.sdk_exceptions import (
    WorkflowValidationError,
    WorkflowExecutionError,
    NodeExecutionError
)
from kailash.tracking import TaskManager, TaskStatus


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
        """
        self.metadata = WorkflowMetadata(
            name=name,
            description=kwargs.get('description', ''),
            version=kwargs.get('version', '1.0.0'),
            author=kwargs.get('author', ''),
            tags=kwargs.get('tags', set())
        )
        
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, NodeInstance] = {}
        self.connections: List[Connection] = []
        self._node_instances: Dict[str, Node] = {}
    
    def add_node(self, node_id: str, node_or_type: Any, **config) -> None:
        """Add a node to the workflow.
        
        Args:
            node_id: Unique identifier for this node instance
            node_or_type: Either a Node instance or node type name
            **config: Configuration for the node
        """
        if node_id in self.nodes:
            raise WorkflowValidationError(f"Node '{node_id}' already exists")
        
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
            # Update config
            node_instance.config.update(config)
            node_instance._validate_config()
        else:
            raise WorkflowValidationError(
                f"Invalid node type: {type(node_or_type)}"
            )
        
        # Store node instance and metadata
        self.nodes[node_id] = NodeInstance(
            node_id=node_id,
            node_type=node_instance.__class__.__name__,
            config=config,
            position=(len(self.nodes) * 150, 100)
        )
        self._node_instances[node_id] = node_instance
        
        # Add to graph
        self.graph.add_node(node_id, node=node_instance)
    
    def connect(self, source_node: str, target_node: str, 
                mapping: Optional[Dict[str, str]] = None) -> None:
        """Connect two nodes in the workflow.
        
        Args:
            source_node: Source node ID
            target_node: Target node ID
            mapping: Dict mapping source outputs to target inputs
        """
        if source_node not in self.nodes:
            raise WorkflowValidationError(f"Source node '{source_node}' not found")
        if target_node not in self.nodes:
            raise WorkflowValidationError(f"Target node '{target_node}' not found")
        
        # Default mapping if not provided
        if mapping is None:
            mapping = {"output": "input"}
        
        # Create connections
        for source_output, target_input in mapping.items():
            connection = Connection(
                source_node=source_node,
                source_output=source_output,
                target_node=target_node,
                target_input=target_input
            )
            self.connections.append(connection)
            
            # Add edge to graph
            self.graph.add_edge(
                source_node, 
                target_node, 
                mapping={source_output: target_input}
            )
    
    def validate(self) -> None:
        """Validate the workflow structure.
        
        Raises:
            WorkflowValidationError: If workflow is invalid
        """
        # Check for cycles
        if not nx.is_directed_acyclic_graph(self.graph):
            raise WorkflowValidationError("Workflow contains cycles")
        
        # Check all nodes have required inputs
        for node_id, node_instance in self._node_instances.items():
            params = node_instance.get_parameters()
            
            # Get inputs from connections
            incoming_edges = self.graph.in_edges(node_id, data=True)
            connected_inputs = set()
            
            for _, _, data in incoming_edges:
                mapping = data.get('mapping', {})
                connected_inputs.update(mapping.values())
            
            # Check required parameters
            for param_name, param_def in params.items():
                if param_def.required and param_name not in connected_inputs:
                    # Check if it's provided in config
                    if param_name not in node_instance.config:
                        raise WorkflowValidationError(
                            f"Node '{node_id}' missing required input '{param_name}'"
                        )
    
    def run(self, task_manager: Optional[TaskManager] = None, 
            **overrides) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute the workflow.
        
        Args:
            task_manager: Optional task manager for tracking
            **overrides: Parameter overrides
            
        Returns:
            Tuple of (results dict, run_id)
        """
        self.validate()
        
        # Initialize task tracking
        run_id = None
        if task_manager:
            run_id = task_manager.create_run(
                workflow_name=self.metadata.name,
                metadata={"overrides": overrides}
            )
        
        # Execute in topological order
        execution_order = list(nx.topological_sort(self.graph))
        results = {}
        
        for node_id in execution_order:
            node_instance = self._node_instances[node_id]
            
            # Start task tracking
            task = None
            if task_manager and run_id:
                task = task_manager.create_task(
                    run_id=run_id,
                    node_id=node_id,
                    node_type=node_instance.__class__.__name__
                )
            
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
                
                # Apply overrides
                node_overrides = overrides.get(node_id, {})
                inputs.update(node_overrides)
                
                # Execute node
                if task:
                    task.update_status(TaskStatus.RUNNING)
                
                node_results = node_instance.execute(**inputs)
                results[node_id] = node_results
                
                if task:
                    task.update_status(TaskStatus.COMPLETED, result=node_results)
                
            except Exception as e:
                if task:
                    task.update_status(TaskStatus.FAILED, error=str(e))
                raise WorkflowExecutionError(
                    f"Node '{node_id}' failed: {e}"
                ) from e
        
        return results, run_id
    
    def export_to_kailash(self, output_path: str) -> None:
        """Export workflow to Kailash-compatible YAML format.
        
        Args:
            output_path: Path to write YAML file
        """
        kailash_workflow = {
            "metadata": self.metadata.model_dump(),
            "nodes": {},
            "connections": []
        }
        
        # Export nodes
        for node_id, node_instance in self.nodes.items():
            kailash_workflow["nodes"][node_id] = {
                "type": node_instance.node_type,
                "config": node_instance.config,
                "position": node_instance.position
            }
        
        # Export connections
        for connection in self.connections:
            kailash_workflow["connections"].append({
                "from": f"{connection.source_node}.{connection.source_output}",
                "to": f"{connection.target_node}.{connection.target_input}"
            })
        
        # Write YAML
        with open(output_path, 'w') as f:
            yaml.dump(kailash_workflow, f, default_flow_style=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary representation."""
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
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        """Create workflow from dictionary representation."""
        # Create workflow
        metadata = data.get("metadata", {})
        workflow = cls(
            name=metadata.get("name", "unnamed"),
            description=metadata.get("description", ""),
            version=metadata.get("version", "1.0.0"),
            author=metadata.get("author", "")
        )
        
        # Add nodes
        nodes = data.get("nodes", {})
        for node_id, node_data in nodes.items():
            workflow.add_node(
                node_id=node_id,
                node_or_type=node_data["node_type"],
                **node_data.get("config", {})
            )
        
        # Add connections
        connections = data.get("connections", [])
        for conn_data in connections:
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
        
        return workflow