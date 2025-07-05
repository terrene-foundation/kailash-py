"""
Workflow Input Handling Enhancement

This module provides a solution for properly passing workflow-level parameters
to nodes, especially those without incoming connections.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class WorkflowInputHandler:
    """Handles workflow input parameter distribution to nodes"""

    @staticmethod
    def inject_workflow_parameters(
        workflow: Workflow, parameters: Dict[str, Any]
    ) -> None:
        """
        Inject workflow parameters into nodes that need them.

        This method identifies nodes without incoming connections and ensures
        they receive necessary parameters from the workflow input.

        Args:
            workflow: The workflow to process
            parameters: Parameters passed to the workflow
        """
        # Find nodes without incoming connections
        nodes_with_inputs = set()
        for edge in workflow._graph.edges():
            nodes_with_inputs.add(edge[1])  # target node

        all_nodes = set(workflow._graph.nodes())
        entry_nodes = all_nodes - nodes_with_inputs

        logger.debug(f"Found entry nodes without inputs: {entry_nodes}")

        # Process each entry node
        for node_id in entry_nodes:
            if node_id not in workflow._nodes:
                continue

            node_instance = workflow._nodes[node_id]
            node_type = type(node_instance).__name__

            logger.debug(f"Processing entry node '{node_id}' of type {node_type}")

            # Get node's required parameters
            if hasattr(node_instance, "get_parameters"):
                node_params = node_instance.get_parameters()

                for param_name, param_def in node_params.items():
                    if param_def.required:
                        # Check if parameter is already in node config
                        if param_name not in node_instance.config:
                            # Try to find it in workflow parameters
                            if param_name in parameters:
                                logger.info(
                                    f"Injecting parameter '{param_name}' "
                                    f"into node '{node_id}'"
                                )
                                node_instance.config[param_name] = parameters[
                                    param_name
                                ]
                            # Special handling for common parameters
                            elif (
                                param_name == "tenant_id"
                                and "tenant_id" not in parameters
                            ):
                                # Use default tenant if not specified
                                node_instance.config[param_name] = "default"
                                logger.info(
                                    f"Using default tenant_id for node '{node_id}'"
                                )
                            elif param_name == "database_config":
                                # Try to find database config in various places
                                db_config = (
                                    parameters.get("database_config")
                                    or parameters.get("db_config")
                                    or workflow._metadata.get("database_config")
                                )
                                if db_config:
                                    node_instance.config[param_name] = db_config
                                    logger.info(
                                        f"Injecting database_config into node '{node_id}'"
                                    )

    @staticmethod
    def create_input_mappings(
        workflow: Workflow, mappings: Dict[str, Dict[str, str]]
    ) -> None:
        """
        Create explicit mappings from workflow inputs to node parameters.

        Args:
            workflow: The workflow to configure
            mappings: Dict of node_id -> {workflow_param: node_param} mappings
        """
        for node_id, param_mappings in mappings.items():
            if node_id not in workflow._nodes:
                logger.warning(f"Node '{node_id}' not found in workflow")
                continue

            node_instance = workflow._nodes[node_id]

            # Store mappings in node metadata for runtime use
            if "_input_mappings" not in node_instance.config:
                node_instance.config["_input_mappings"] = {}

            node_instance.config["_input_mappings"].update(param_mappings)
            logger.info(
                f"Created input mappings for node '{node_id}': {param_mappings}"
            )


def enhance_workflow_execution(original_execute):
    """
    Decorator to enhance workflow execution with parameter injection.

    This wraps the workflow execution to ensure parameters are properly
    distributed to nodes before execution begins.
    """

    def enhanced_execute(self, parameters: Dict[str, Any] = None, **kwargs):
        # Inject parameters before execution
        if parameters:
            WorkflowInputHandler.inject_workflow_parameters(self, parameters)

        # Call original execution
        return original_execute(self, parameters, **kwargs)

    return enhanced_execute


# Example usage for fixing the login workflow
def fix_login_workflow(workflow: Workflow, config: Dict[str, Any]) -> None:
    """
    Fix the login workflow to properly handle parameters.

    Args:
        workflow: The login workflow to fix
        config: Application configuration
    """
    # Define input mappings for the user_fetcher node
    mappings = {
        "user_fetcher": {
            "email": "identifier",  # Map workflow 'email' to node 'identifier'
            "tenant_id": "tenant_id",
            "database_config": "database_config",
        }
    }

    # Apply mappings
    WorkflowInputHandler.create_input_mappings(workflow, mappings)

    # Set default values for common parameters
    if "user_fetcher" in workflow._nodes:
        node = workflow._nodes["user_fetcher"]
        if "tenant_id" not in node.config:
            node.config["tenant_id"] = "default"
        if "database_config" not in node.config:
            node.config["database_config"] = {
                "connection_string": config.get("DATABASE_URL"),
                "database_type": "postgresql",
            }
