"""
WorkflowBuilder Improvements for Parameter Passing

This module contains improvements to the WorkflowBuilder to handle
parameter passing to nodes without incoming connections.
"""

from typing import Any, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class ImprovedWorkflowBuilder(WorkflowBuilder):
    """Enhanced WorkflowBuilder that automatically handles parameter passing"""

    def __init__(self):
        super().__init__()
        self.workflow_parameters: Dict[str, Any] = {}
        self.parameter_mappings: Dict[str, Dict[str, str]] = {}

    def set_workflow_parameters(self, **parameters) -> "ImprovedWorkflowBuilder":
        """
        Set default parameters that will be passed to all nodes.

        Args:
            **parameters: Key-value pairs of workflow-level parameters

        Returns:
            Self for chaining
        """
        self.workflow_parameters.update(parameters)
        return self

    def add_parameter_mapping(
        self, node_id: str, mappings: Dict[str, str]
    ) -> "ImprovedWorkflowBuilder":
        """
        Add parameter mappings for a specific node.

        Args:
            node_id: Node to configure
            mappings: Dict mapping workflow param names to node param names

        Returns:
            Self for chaining
        """
        if node_id not in self.parameter_mappings:
            self.parameter_mappings[node_id] = {}
        self.parameter_mappings[node_id].update(mappings)
        return self

    def add_input_connection(
        self, to_node: str, to_input: str, from_workflow_param: str
    ) -> "ImprovedWorkflowBuilder":
        """
        Connect a workflow parameter directly to a node input.

        Args:
            to_node: Target node ID
            to_input: Input parameter name on the node
            from_workflow_param: Workflow parameter name

        Returns:
            Self for chaining
        """
        # Add a special connection type for workflow inputs
        connection = {
            "from_node": "__workflow_input__",
            "from_output": from_workflow_param,
            "to_node": to_node,
            "to_input": to_input,
            "is_workflow_input": True,
        }
        self.connections.append(connection)
        return self

    def build(self, workflow_id: str | None = None, **kwargs) -> Workflow:
        """
        Build the workflow with automatic parameter injection.

        Returns:
            Enhanced Workflow instance
        """
        # First, build the base workflow
        workflow = super().build(workflow_id, **kwargs)

        # Find nodes without incoming connections
        nodes_with_inputs = set()
        for conn in self.connections:
            if not conn.get("is_workflow_input"):
                nodes_with_inputs.add(conn["to_node"])

        nodes_without_inputs = set(self.nodes.keys()) - nodes_with_inputs

        # For each node without inputs, check if it needs workflow parameters
        for node_id in nodes_without_inputs:
            node = self.nodes[node_id]
            node_instance = workflow.get_node(node_id)

            if hasattr(node_instance, "get_parameters"):
                params = node_instance.get_parameters()

                # Check which required parameters are missing from config
                for param_name, param_def in params.items():
                    if param_def.required and param_name not in node["config"]:
                        # Check if this parameter should come from workflow parameters
                        if param_name in self.workflow_parameters:
                            # Add to node config
                            node["config"][param_name] = self.workflow_parameters[
                                param_name
                            ]
                        elif node_id in self.parameter_mappings:
                            # Check parameter mappings
                            mapping = self.parameter_mappings[node_id]
                            if param_name in mapping:
                                workflow_param = mapping[param_name]
                                if workflow_param in self.workflow_parameters:
                                    node["config"][param_name] = (
                                        self.workflow_parameters[workflow_param]
                                    )

        # Store workflow parameters in metadata for runtime reference
        workflow._metadata["workflow_parameters"] = self.workflow_parameters
        workflow._metadata["parameter_mappings"] = self.parameter_mappings

        return workflow


def create_user_login_workflow_improved(config: Dict[str, Any]) -> Workflow:
    """
    Example of creating a login workflow with proper parameter handling.
    """
    workflow = ImprovedWorkflowBuilder()

    # Set workflow-level parameters that will be shared
    workflow.set_workflow_parameters(
        tenant_id="default", database_config=config["database_config"]
    )

    # Add user fetcher node
    workflow.add_node(
        "UserManagementNode",
        "user_fetcher",
        {
            "operation": "get_user",
            "identifier": "$.email",
            "identifier_type": "email",
            # tenant_id and database_config will be auto-injected
        },
    )

    # Map workflow inputs to the first node
    workflow.add_input_connection("user_fetcher", "email", "email")
    workflow.add_input_connection("user_fetcher", "password", "password")

    # Add other nodes...
    workflow.add_node(
        "PythonCodeNode",
        "password_verifier",
        {"code": "# Password verification code here"},
    )

    # Connect nodes
    workflow.add_connection("user_fetcher", "result", "password_verifier", "input")

    return workflow.build(name="user_login_improved")


# Alternative approach: Fix in the existing WorkflowBuilder
def patch_workflow_builder():
    """
    Monkey patch the existing WorkflowBuilder to handle parameters better.
    """
    original_build = WorkflowBuilder.build

    def enhanced_build(self, workflow_id: str | None = None, **kwargs) -> Workflow:
        # Build the workflow normally
        workflow = original_build(self, workflow_id, **kwargs)

        # Enhanced parameter handling
        # Find nodes without incoming connections and inject common parameters
        nodes_with_inputs = set()
        for edge in workflow._graph.edges():
            nodes_with_inputs.add(edge[1])  # target node

        # Get all nodes
        all_nodes = set(workflow._graph.nodes())
        nodes_without_inputs = all_nodes - nodes_with_inputs

        # Common parameters that should be injected
        common_params = {
            "tenant_id": "default",
            "database_config": kwargs.get("database_config", {}),
        }

        for node_id in nodes_without_inputs:
            if node_id in workflow._nodes:
                node_instance = workflow._nodes[node_id]
                # Update node config with common parameters if not already set
                for param, value in common_params.items():
                    if param not in node_instance.config:
                        node_instance.config[param] = value

        return workflow

    WorkflowBuilder.build = enhanced_build
