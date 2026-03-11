"""Workflow binding for DataFlow instances.

Provides convenient API for creating workflows that use DataFlow-generated nodes.
This enables seamless workflow composition with DataFlow models while preserving
backward compatibility with existing WorkflowBuilder patterns.

TODO-154: Workflow Binding Integration
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

if TYPE_CHECKING:
    from .engine import DataFlow

logger = logging.getLogger("dataflow.workflow_binding")


class DataFlowWorkflowBinder:
    """Bind DataFlow instance context to workflow execution.

    Provides convenient methods for building workflows that operate on
    DataFlow models. The underlying nodes already have DataFlow context
    via closures, so this class primarily adds:
    - Model/operation validation before workflow construction
    - Cross-model workflow support
    - Enhanced error messages with DataFlow context
    - Workflow tracking for debugging

    Example:
        >>> db = DataFlow("postgresql://...")
        >>>
        >>> @db.model
        ... class User:
        ...     name: str
        ...     email: str
        >>>
        >>> workflow = db.create_workflow("user_setup")
        >>> db.add_node(workflow, "User", "Create", "create_user", {
        ...     "name": "Alice",
        ...     "email": "alice@example.com"
        ... })
        >>> results, run_id = db.execute_workflow(workflow)
    """

    # Map of user-friendly operation names to node suffixes
    OPERATION_MAP = {
        "Create": "CreateNode",
        "Read": "ReadNode",
        "Update": "UpdateNode",
        "Delete": "DeleteNode",
        "List": "ListNode",
        "Upsert": "UpsertNode",
        "Count": "CountNode",
        "BulkCreate": "BulkCreateNode",
        "BulkUpdate": "BulkUpdateNode",
        "BulkDelete": "BulkDeleteNode",
        "BulkUpsert": "BulkUpsertNode",
    }

    def __init__(self, dataflow_instance: "DataFlow"):
        """Initialize the workflow binder.

        Args:
            dataflow_instance: The DataFlow instance to bind workflows to
        """
        self.dataflow_instance = dataflow_instance
        self._workflows: Dict[str, WorkflowBuilder] = {}

    def create_workflow(self, workflow_id: Optional[str] = None) -> WorkflowBuilder:
        """Create a workflow bound to this DataFlow instance.

        Args:
            workflow_id: Optional identifier for the workflow. If not provided,
                        a unique ID will be generated.

        Returns:
            WorkflowBuilder instance with DataFlow context attached

        Example:
            >>> workflow = binder.create_workflow("my_workflow")
            >>> # or
            >>> workflow = binder.create_workflow()  # auto-generated ID
        """
        if workflow_id is None:
            workflow_id = f"dataflow_{uuid.uuid4().hex[:8]}"

        workflow = WorkflowBuilder()
        # Track which DataFlow instance this workflow belongs to
        workflow._dataflow_context = self.dataflow_instance
        workflow._dataflow_workflow_id = workflow_id
        self._workflows[workflow_id] = workflow

        logger.debug("Created workflow '%s' bound to DataFlow instance", workflow_id)

        return workflow

    def _resolve_node_type(self, model_name: str, operation: str) -> str:
        """Resolve model+operation to node type name.

        Args:
            model_name: Model name (e.g., "User")
            operation: Operation name (e.g., "Create", "Read", "BulkCreate")

        Returns:
            Node type string (e.g., "UserCreateNode")

        Raises:
            ValueError: If model not registered or operation invalid
        """
        # Validate model exists
        models = self.dataflow_instance.get_models()
        if model_name not in models:
            available = list(models.keys())
            raise ValueError(
                f"Model '{model_name}' is not registered with this DataFlow instance. "
                f"Available models: {available}. "
                f"Ensure @db.model is applied to {model_name} before creating workflows."
            )

        # Validate operation
        if operation not in self.OPERATION_MAP:
            available_ops = list(self.OPERATION_MAP.keys())
            raise ValueError(
                f"Invalid operation '{operation}' for model '{model_name}'. "
                f"Available operations: {available_ops}"
            )

        node_suffix = self.OPERATION_MAP[operation]
        node_type = f"{model_name}{node_suffix}"

        # Verify node is actually registered
        nodes = self.dataflow_instance._nodes
        if node_type not in nodes:
            raise ValueError(
                f"Node '{node_type}' not found. Model '{model_name}' may not have "
                f"generated nodes yet. Ensure @db.model is applied first."
            )

        return node_type

    def add_model_node(
        self,
        workflow: WorkflowBuilder,
        model_name: str,
        operation: str,
        node_id: str,
        params: Dict[str, Any],
        connections: Optional[Dict] = None,
    ) -> str:
        """Add a DataFlow model node to a workflow.

        Args:
            workflow: Target workflow builder
            model_name: Model name (e.g., "User")
            operation: Operation (e.g., "Create", "Read", "Update", "Delete",
                      "List", "Upsert", "Count", "BulkCreate", etc.)
            node_id: Unique node ID within the workflow
            params: Node parameters
            connections: Optional connections dict for chaining nodes

        Returns:
            The node_id (for chaining)

        Raises:
            ValueError: If model or operation is invalid

        Example:
            >>> binder.add_model_node(workflow, "User", "Create", "create_user", {
            ...     "name": "Alice",
            ...     "email": "alice@example.com"
            ... })
        """
        node_type = self._resolve_node_type(model_name, operation)

        if connections is not None:
            workflow.add_node(node_type, node_id, params, connections)
        else:
            workflow.add_node(node_type, node_id, params)

        logger.debug(
            "Added %s node '%s' to workflow (model=%s, operation=%s)",
            node_type,
            node_id,
            model_name,
            operation,
        )

        return node_id

    def execute(
        self,
        workflow: WorkflowBuilder,
        inputs: Optional[Dict[str, Any]] = None,
        runtime: Optional[Any] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Execute a DataFlow-bound workflow.

        Args:
            workflow: Workflow to execute
            inputs: Optional workflow inputs/parameters
            runtime: Optional runtime instance (creates LocalRuntime if not provided)

        Returns:
            Tuple of (results_dict, run_id)

        Example:
            >>> results, run_id = binder.execute(workflow, {"user_id": "123"})
            >>> print(results["create_user"])
        """
        if runtime is None:
            runtime = LocalRuntime()

        logger.debug("Executing workflow with %d nodes", len(workflow.nodes))

        return runtime.execute(workflow.build(), inputs or {})

    def get_available_nodes(
        self, model_name: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """Get available DataFlow nodes, optionally filtered by model.

        Args:
            model_name: Optional model name to filter by

        Returns:
            Dict mapping model names to lists of available operations

        Example:
            >>> nodes = binder.get_available_nodes()
            >>> # {'User': ['Create', 'Read', 'Update', 'Delete', 'List', ...]}
            >>>
            >>> nodes = binder.get_available_nodes("User")
            >>> # {'User': ['Create', 'Read', 'Update', 'Delete', 'List', ...]}
        """
        result: Dict[str, List[str]] = {}
        models = self.dataflow_instance.get_models()
        nodes = self.dataflow_instance._nodes

        target_models = [model_name] if model_name else list(models.keys())

        for m_name in target_models:
            if m_name not in models:
                continue
            available_ops = []
            for op_name, suffix in self.OPERATION_MAP.items():
                if f"{m_name}{suffix}" in nodes:
                    available_ops.append(op_name)
            if available_ops:
                result[m_name] = available_ops

        return result

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowBuilder]:
        """Get a previously created workflow by ID.

        Args:
            workflow_id: The workflow identifier

        Returns:
            WorkflowBuilder if found, None otherwise
        """
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[str]:
        """List all workflow IDs created by this binder.

        Returns:
            List of workflow IDs
        """
        return list(self._workflows.keys())
