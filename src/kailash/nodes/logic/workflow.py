"""Workflow node for wrapping workflows as reusable components.

This module provides the WorkflowNode class that enables hierarchical workflow
composition by wrapping entire workflows as single nodes. This allows complex
workflows to be reused as building blocks in larger workflows.

Design Philosophy:
- Workflows as first-class components
- Hierarchical composition patterns
- Clean abstraction of complexity
- Consistent node interface

Key Features:
- Dynamic parameter discovery from entry nodes
- Multiple loading methods (instance, file, dict)
- Automatic output mapping from exit nodes
- Full compatibility with existing runtime
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError
from kailash.workflow.graph import Workflow


@register_node()
class WorkflowNode(Node):
    """A node that encapsulates and executes an entire workflow.

    This node allows workflows to be composed hierarchically, where a complex
    workflow can be used as a single node within another workflow. This enables
    powerful composition patterns and reusability.

    Design Philosophy:
    - Workflows become reusable components
    - Complex logic hidden behind simple interface
    - Hierarchical composition of workflows
    - Consistent with standard node behavior

    Upstream Components:
    - Parent workflows that use this node
    - Workflow builders creating composite workflows
    - CLI/API creating nested workflow structures

    Downstream Usage:
    - The wrapped workflow and all its nodes
    - Runtime executing the inner workflow
    - Results passed to subsequent nodes

    Usage Patterns:
    1. Direct workflow wrapping:
       ```python
       inner_workflow = Workflow("data_processing")
       # ... build workflow ...
       node = WorkflowNode(workflow=inner_workflow)
       ```

    2. Loading from file:
       ```python
       node = WorkflowNode(workflow_path="workflows/processor.yaml")
       ```

    3. Loading from dictionary:
       ```python
       workflow_dict = {"nodes": {...}, "connections": [...]}
       node = WorkflowNode(workflow_dict=workflow_dict)
       ```

    Implementation Details:
    - Parameters derived from workflow entry nodes
    - Outputs mapped from workflow exit nodes
    - Uses LocalRuntime for execution
    - Validates workflow structure on load

    Error Handling:
    - Configuration errors for invalid workflows
    - Execution errors wrapped with context
    - Clear error messages for debugging

    Side Effects:
    - Executes entire workflow when run
    - May create temporary files/state
    - Logs execution progress
    """

    def __init__(self, workflow: Optional[Workflow] = None, **kwargs):
        """Initialize the WorkflowNode.

        Args:
            workflow: Optional workflow instance to wrap
            **kwargs: Additional configuration including:
                - workflow_path: Path to load workflow from file
                - workflow_dict: Dictionary representation of workflow
                - name: Display name for the node
                - description: Node description
                - input_mapping: Map node inputs to workflow inputs
                - output_mapping: Map workflow outputs to node outputs

        Raises:
            NodeConfigurationError: If no workflow source provided or
                                  if workflow loading fails
        """
        # Store workflow configuration before parent init
        self._workflow = workflow
        self._workflow_path = kwargs.get("workflow_path")
        self._workflow_dict = kwargs.get("workflow_dict")
        self._input_mapping = kwargs.get("input_mapping", {})
        self._output_mapping = kwargs.get("output_mapping", {})

        # Initialize parent
        super().__init__(**kwargs)

        # Runtime will be created lazily to avoid circular imports
        self._runtime = None

        # Load workflow if not provided directly
        if not self._workflow:
            self._load_workflow()

    def _validate_config(self):
        """Override validation for WorkflowNode.

        WorkflowNode has dynamic parameters based on the wrapped workflow,
        so we skip the strict validation that base Node does.
        """
        # Skip parameter validation for WorkflowNode since parameters
        # are dynamically determined from the wrapped workflow
        pass

    def _load_workflow(self):
        """Load workflow from path or dictionary.

        Attempts to load the workflow from configured sources:
        1. From file path (JSON or YAML)
        2. From dictionary representation

        Raises:
            NodeConfigurationError: If no valid source or loading fails
        """
        if self._workflow_path:
            path = Path(self._workflow_path)
            if not path.exists():
                raise NodeConfigurationError(
                    f"Workflow file not found: {self._workflow_path}"
                )

            try:
                if path.suffix == ".json":
                    with open(path, "r") as f:
                        data = json.load(f)
                    self._workflow = Workflow.from_dict(data)
                elif path.suffix in [".yaml", ".yml"]:
                    with open(path, "r") as f:
                        data = yaml.safe_load(f)
                    self._workflow = Workflow.from_dict(data)
                else:
                    raise NodeConfigurationError(
                        f"Unsupported workflow file format: {path.suffix}"
                    )
            except Exception as e:
                raise NodeConfigurationError(
                    f"Failed to load workflow from {path}: {e}"
                ) from e

        elif self._workflow_dict:
            try:
                self._workflow = Workflow.from_dict(self._workflow_dict)
            except Exception as e:
                raise NodeConfigurationError(
                    f"Failed to load workflow from dictionary: {e}"
                ) from e
        else:
            raise NodeConfigurationError(
                "WorkflowNode requires either 'workflow', 'workflow_path', "
                "or 'workflow_dict' parameter"
            )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters based on workflow entry nodes.

        Analyzes the wrapped workflow to determine required inputs:
        1. Finds entry nodes (no incoming connections)
        2. Aggregates their parameters
        3. Adds generic 'inputs' parameter for overrides

        Returns:
            Dictionary of parameters derived from workflow structure
        """
        if not self._workflow:
            # Default parameters if workflow not loaded yet
            return {
                "inputs": NodeParameter(
                    name="inputs",
                    type=dict,
                    required=False,
                    default={},
                    description="Input data for the workflow",
                )
            }

        params = {}

        # Find entry nodes (nodes with no incoming edges)
        entry_nodes = []
        for node_id in self._workflow.nodes:
            if self._workflow.graph.in_degree(node_id) == 0:
                entry_nodes.append(node_id)

        # If custom input mapping provided, use that
        if self._input_mapping:
            for param_name, mapping in self._input_mapping.items():
                params[param_name] = NodeParameter(
                    name=param_name,
                    type=mapping.get("type", Any),
                    required=mapping.get("required", True),
                    default=mapping.get("default"),
                    description=mapping.get("description", f"Input for {param_name}"),
                )
        else:
            # Auto-discover from entry nodes
            for node_id in entry_nodes:
                node = self._workflow.get_node(node_id)
                if node:
                    node_params = node.get_parameters()
                    for param_name, param_def in node_params.items():
                        # Create flattened parameter name
                        full_param_name = f"{node_id}_{param_name}"
                        params[full_param_name] = NodeParameter(
                            name=full_param_name,
                            type=param_def.type,
                            required=False,  # Make all workflow parameters optional
                            default=param_def.default,
                            description=f"{node_id}: {param_def.description}",
                        )

        # Always include generic inputs parameter
        params["inputs"] = NodeParameter(
            name="inputs",
            type=dict,
            required=False,
            default={},
            description="Additional input overrides for workflow nodes",
        )

        return params

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output schema based on workflow exit nodes.

        Analyzes the wrapped workflow to determine outputs:
        1. Finds exit nodes (no outgoing connections)
        2. Aggregates their output schemas
        3. Includes general 'results' output

        Returns:
            Dictionary of output parameters from workflow structure
        """
        if not self._workflow:
            return {
                "results": NodeParameter(
                    name="results",
                    type=dict,
                    required=True,
                    description="Workflow execution results",
                )
            }

        output_schema = {
            "results": NodeParameter(
                name="results",
                type=dict,
                required=True,
                description="Complete workflow execution results by node",
            )
        }

        # If custom output mapping provided, use that
        if self._output_mapping:
            for output_name, mapping in self._output_mapping.items():
                output_schema[output_name] = NodeParameter(
                    name=output_name,
                    type=mapping.get("type", Any),
                    required=mapping.get("required", False),
                    description=mapping.get("description", f"Output {output_name}"),
                )
        else:
            # Auto-discover from exit nodes
            exit_nodes = []
            for node_id in self._workflow.nodes:
                if self._workflow.graph.out_degree(node_id) == 0:
                    exit_nodes.append(node_id)

            for node_id in exit_nodes:
                node = self._workflow.get_node(node_id)
                if node and hasattr(node, "get_output_schema"):
                    try:
                        node_outputs = node.get_output_schema()
                        for output_name, output_def in node_outputs.items():
                            full_output_name = f"{node_id}_{output_name}"
                            output_schema[full_output_name] = NodeParameter(
                                name=full_output_name,
                                type=output_def.type,
                                required=False,
                                description=f"{node_id}: {output_def.description}",
                            )
                    except Exception:
                        # Skip nodes that fail to provide output schema
                        pass

        return output_schema

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the wrapped workflow.

        Executes the inner workflow with proper input mapping:
        1. Maps node inputs to workflow node inputs
        2. Executes workflow using LocalRuntime
        3. Maps workflow outputs to node outputs

        Args:
            **kwargs: Input parameters for the workflow

        Returns:
            Dictionary containing:
            - results: Complete workflow execution results
            - Mapped outputs from exit nodes

        Raises:
            NodeExecutionError: If workflow execution fails
        """
        if not self._workflow:
            raise NodeExecutionError("No workflow loaded")

        # Prepare inputs for the workflow
        workflow_inputs = {}

        # Handle custom input mapping
        if self._input_mapping:
            for param_name, mapping in self._input_mapping.items():
                if param_name in kwargs:
                    # mapping should specify target node and parameter
                    target_node = mapping.get("node")
                    target_param = mapping.get("parameter", param_name)
                    if target_node:
                        workflow_inputs.setdefault(target_node, {})[target_param] = (
                            kwargs[param_name]
                        )
        else:
            # Auto-map inputs based on parameter names
            for key, value in kwargs.items():
                if "_" in key and key != "inputs":
                    # Split node_id and param_name
                    parts = key.split("_", 1)
                    if len(parts) == 2:
                        node_id, param_name = parts
                        if node_id in self._workflow.nodes:
                            workflow_inputs.setdefault(node_id, {})[param_name] = value

        # Add any additional inputs
        if "inputs" in kwargs and isinstance(kwargs["inputs"], dict):
            for node_id, node_inputs in kwargs["inputs"].items():
                if node_id in self._workflow.nodes:
                    workflow_inputs.setdefault(node_id, {}).update(node_inputs)

        try:
            # Create runtime lazily to avoid circular imports
            if self._runtime is None:
                from kailash.runtime.local import LocalRuntime

                self._runtime = LocalRuntime()

            # Execute the workflow
            self.logger.info(f"Executing wrapped workflow: {self._workflow.name}")
            results, _ = self._runtime.execute(
                self._workflow, parameters=workflow_inputs
            )

            # Process results
            output = {"results": results}

            # Handle custom output mapping
            if self._output_mapping:
                for output_name, mapping in self._output_mapping.items():
                    source_node = mapping.get("node")
                    source_output = mapping.get("output", output_name)
                    if source_node and source_node in results:
                        node_results = results[source_node]
                        if (
                            isinstance(node_results, dict)
                            and source_output in node_results
                        ):
                            output[output_name] = node_results[source_output]
            else:
                # Auto-map outputs from exit nodes
                for node_id in self._workflow.nodes:
                    if self._workflow.graph.out_degree(node_id) == 0:
                        if node_id in results:
                            node_results = results[node_id]
                            if isinstance(node_results, dict):
                                for key, value in node_results.items():
                                    output[f"{node_id}_{key}"] = value

            return output

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}")
            raise NodeExecutionError(f"Failed to execute wrapped workflow: {e}") from e

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary representation.

        Serializes the WorkflowNode including its wrapped workflow
        for persistence and export.

        Returns:
            Dictionary containing node configuration and workflow
        """
        base_dict = super().to_dict()

        # Add workflow information
        if self._workflow:
            base_dict["wrapped_workflow"] = self._workflow.to_dict()
        elif self._workflow_path:
            base_dict["workflow_path"] = str(self._workflow_path)
        elif self._workflow_dict:
            base_dict["workflow_dict"] = self._workflow_dict

        # Add mappings if present
        if self._input_mapping:
            base_dict["input_mapping"] = self._input_mapping
        if self._output_mapping:
            base_dict["output_mapping"] = self._output_mapping

        return base_dict
