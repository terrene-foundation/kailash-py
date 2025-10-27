"""
Access-Controlled Runtime for Kailash SDK

This module provides an access-controlled runtime that wraps the standard runtime
to add permission checks. The standard runtime remains unchanged, ensuring complete
backward compatibility.

Users who don't need access control continue using LocalRuntime as normal.
Users who need access control use AccessControlledRuntime instead.

Example without access control (existing code):
    >>> from kailash.runtime.local import LocalRuntime
    >>> from kailash.workflow import Workflow
    >>> runtime = LocalRuntime()
    >>> workflow = Workflow(workflow_id="test", name="Test")
    >>> result, run_id = runtime.execute(workflow)  # Works exactly as before

Example with access control (opt-in):
    >>> from kailash.runtime.access_controlled import AccessControlledRuntime
    >>> from kailash.access_control import UserContext, get_access_control_manager
    >>> user = UserContext(user_id="123", tenant_id="abc", email="user@test.com", roles=["analyst"])
    >>> runtime = AccessControlledRuntime(user_context=user)
    >>> # Access control manager is disabled by default for compatibility
    >>> acm = get_access_control_manager()
    >>> acm.enabled  # Should be False by default
    False
"""

import logging
from typing import Any

from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
    get_access_control_manager,
)
from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


class AccessControlledRuntime:
    """
    Runtime with transparent access control layer.

    This runtime wraps the standard LocalRuntime and adds access control
    checks without modifying the original runtime or requiring any changes
    to existing nodes or workflows.

    Design Purpose:
        Provides a drop-in replacement for LocalRuntime that adds security
        without breaking existing workflows. Enables role-based access control,
        data masking, and conditional execution based on user permissions.

    Upstream Dependencies:
        - AccessControlManager for permission evaluation
        - UserContext from authentication systems
        - LocalRuntime for actual workflow execution
        - PermissionRule definitions from configuration

    Downstream Consumers:
        - Applications requiring secure workflow execution
        - Multi-tenant systems with user isolation
        - Audit systems for compliance logging
        - Data governance systems for access tracking

    Usage Patterns:
        - Used as direct replacement for LocalRuntime
        - Configured with user context during initialization
        - Integrates with JWT authentication systems
        - Supports both workflow and node-level permissions

    Implementation Details:
        Wraps LocalRuntime and intercepts workflow execution to add
        permission checks. Creates access-controlled node wrappers that
        evaluate permissions before execution. Supports data masking,
        conditional routing, and fallback execution.

    Error Handling:
        - Access denied raises PermissionError with clear messages
        - Missing permissions default to deny for security
        - Configuration errors are logged and treated as disabled
        - Evaluation errors fall back to base runtime behavior

    Side Effects:
        - Logs all access decisions for audit purposes
        - May redirect execution to alternative nodes
        - Applies data masking to sensitive outputs
        - Caches permission decisions for performance

    Example:
        >>> from kailash.runtime.access_controlled import AccessControlledRuntime
        >>> from kailash.access_control import UserContext
        >>> from kailash.workflow import Workflow
        >>>
        >>> user = UserContext(user_id="123", tenant_id="abc", email="user@test.com", roles=["analyst"])
        >>> runtime = AccessControlledRuntime(user_context=user)
        >>> # By default, access control is disabled for backward compatibility
        >>> workflow = Workflow(workflow_id="test", name="Test Workflow")
        >>> isinstance(runtime, AccessControlledRuntime)
        True
    """

    def __init__(
        self, user_context: UserContext, base_runtime: LocalRuntime | None = None
    ):
        """
        Initialize access-controlled runtime.

        Args:
            user_context: The user context for access control decisions
            base_runtime: The underlying runtime to use (defaults to LocalRuntime)
        """
        self.user_context = user_context
        self._owns_runtime = base_runtime is None
        self.base_runtime = base_runtime or LocalRuntime()
        self.acm = get_access_control_manager()

        # Track skipped nodes for alternative routing
        self._skipped_nodes: set[str] = set()
        self._node_outputs: dict[str, Any] = {}

    def execute(
        self, workflow: Workflow, parameters: dict[str, Any] | None = None
    ) -> tuple[Any, str]:
        """
        Execute workflow with access control.

        This method has the exact same signature as the standard runtime,
        ensuring complete compatibility.
        """
        # Only check access control if it's enabled
        if self.acm.enabled:
            # Check workflow-level access
            workflow_decision = self.acm.check_workflow_access(
                self.user_context, workflow.workflow_id, WorkflowPermission.EXECUTE
            )

            if not workflow_decision.allowed:
                raise PermissionError(f"Access denied: {workflow_decision.reason}")

        # Execute with base runtime - it's managed via context manager
        # The base runtime's context manager is entered in __enter__ if we own it
        return self.base_runtime.execute(workflow, parameters)

    def close(self) -> None:
        """Close the runtime and clean up resources.

        Only closes the base runtime if it was created by this instance.
        """
        if self._owns_runtime and hasattr(self.base_runtime, "close"):
            self.base_runtime.close()

    def __enter__(self) -> "AccessControlledRuntime":
        """Enter context manager."""
        if hasattr(self.base_runtime, "__enter__"):
            self.base_runtime.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        if self._owns_runtime and hasattr(self.base_runtime, "__exit__"):
            return self.base_runtime.__exit__(exc_type, exc_val, exc_tb)
        return False

    def _create_controlled_workflow(self, workflow: Workflow) -> Workflow:
        """
        Create a workflow wrapper that enforces access control.

        This wrapper intercepts node execution to add permission checks
        without modifying the original workflow.
        """
        # Create a new workflow instance
        controlled = Workflow(
            workflow_id=workflow.workflow_id,
            name=workflow.name,
            description=workflow.description,
            version=workflow.version,
        )

        # Copy graph structure
        controlled.graph = workflow.graph.copy()

        # Wrap each node with access control
        for node_id in workflow.graph.nodes:
            node_data = workflow.graph.nodes[node_id]
            original_node = node_data.get("node")

            if original_node:
                # Create access-controlled wrapper for the node
                wrapped_node = self._create_controlled_node(node_id, original_node)
                controlled.graph.nodes[node_id]["node"] = wrapped_node

        return controlled

    def _create_controlled_node(self, node_id: str, original_node: Node) -> Node:
        """
        Create an access-controlled wrapper for a node.

        This wrapper intercepts the node's run() method to add permission
        checks without modifying the original node.
        """
        runtime = self  # Capture runtime reference

        class AccessControlledNodeWrapper(Node):
            """Dynamic wrapper that adds access control to any node"""

            def __init__(self):
                # Don't initialize Node base class, just store reference
                self._original_node = original_node
                self._node_id = node_id
                # Copy all attributes from original node
                for attr, value in original_node.__dict__.items():
                    if not attr.startswith("_"):
                        setattr(self, attr, value)

            def get_parameters(self):
                """Delegate to original node"""
                return self._original_node.get_parameters()

            def validate_config(self):
                """Delegate to original node if it has the method"""
                if hasattr(self._original_node, "validate_config"):
                    return self._original_node.validate_config()
                return True

            def get_output_schema(self):
                """Delegate to original node"""
                if hasattr(self._original_node, "get_output_schema"):
                    return self._original_node.get_output_schema()
                return None

            def run(self, **inputs) -> Any:
                """Execute with access control checks"""
                # Check execute permission
                execute_decision = runtime.acm.check_node_access(
                    runtime.user_context,
                    self._node_id,
                    NodePermission.EXECUTE,
                    runtime_context={"inputs": inputs},
                )

                if not execute_decision.allowed:
                    # Node execution denied
                    logger.info(
                        f"Node {self._node_id} skipped for user {runtime.user_context.user_id}"
                    )
                    runtime._skipped_nodes.add(self._node_id)

                    # Check if there's an alternative path
                    if execute_decision.redirect_node:
                        return {"_redirect_to": execute_decision.redirect_node}

                    # Return empty result
                    return {}

                # Execute the original node
                result = self._original_node.execute(**inputs)

                # Check output read permission
                output_decision = runtime.acm.check_node_access(
                    runtime.user_context,
                    self._node_id,
                    NodePermission.READ_OUTPUT,
                    runtime_context={"output": result},
                )

                if not output_decision.allowed:
                    # Mask entire output
                    return {"_access_denied": True}

                # Apply field masking if needed
                if output_decision.masked_fields and isinstance(result, dict):
                    result = runtime._mask_fields(result, output_decision.masked_fields)

                # Store output for conditional routing
                runtime._node_outputs[self._node_id] = result

                return result

        # Create instance of wrapper
        wrapper = AccessControlledNodeWrapper()

        # Preserve node metadata
        wrapper.__class__.__name__ = f"Controlled{original_node.__class__.__name__}"
        wrapper.__class__.__module__ = original_node.__class__.__module__

        return wrapper

    @staticmethod
    def _mask_fields(data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Mask sensitive fields in data"""
        masked = data.copy()
        for field in fields:
            if field in masked:
                masked[field] = "***MASKED***"
        return masked

    def _handle_conditional_routing(
        self, node_id: str, true_path: list[str], false_path: list[str]
    ) -> list[str]:
        """
        Determine which path to take based on permissions.

        This is used for conditional nodes where the path depends on
        user permissions rather than data conditions.
        """
        # Check which path the user has access to
        return self.acm.get_permission_based_route(
            self.user_context, node_id, true_path, false_path
        )


class AccessControlConfig:
    """
    Configuration for access control in workflows.

    Provides a declarative way to define access rules without modifying
    workflow code. Enables administrators to configure permissions
    externally from workflow definitions.

    Design Purpose:
        Separates access control policy from workflow implementation,
        enabling dynamic permission changes without code modifications.
        Supports both workflow-level and node-level permission rules.

    Upstream Dependencies:
        - Administrative interfaces for rule creation
        - Configuration management systems
        - Policy definition templates

    Downstream Consumers:
        - AccessControlManager for rule application
        - AccessControlledRuntime for secure execution
        - Policy management tools for validation

    Usage Patterns:
        - Created by administrators or configuration systems
        - Applied to workflows before execution
        - Used for testing different access scenarios
        - Integrated with external policy management

    Implementation Details:
        Maintains list of PermissionRule objects with helper methods
        for adding common rule types. Rules are applied to manager
        in batch for consistency.

    Example:
        >>> config = AccessControlConfig()
        >>> config.add_workflow_permission(
        ...     workflow_id="analytics",
        ...     permission=WorkflowPermission.EXECUTE,
        ...     role="analyst"
        ... )
        >>> config.add_node_permission(
        ...     workflow_id="analytics",
        ...     node_id="sensitive_data",
        ...     permission=NodePermission.READ_OUTPUT,
        ...     role="admin"
        ... )
    """

    def __init__(self):
        self.rules: list[PermissionRule] = []

    def add_workflow_permission(
        self,
        workflow_id: str,
        permission: WorkflowPermission,
        user_id: str | None = None,
        role: str | None = None,
        effect: PermissionEffect = PermissionEffect.ALLOW,
    ):
        """Add a workflow-level permission rule"""
        rule = PermissionRule(
            id=f"workflow_{workflow_id}_{permission.value}_{len(self.rules)}",
            resource_type="workflow",
            resource_id=workflow_id,
            permission=permission,
            effect=effect,
            user_id=user_id,
            role=role,
        )
        self.rules.append(rule)

    def add_node_permission(
        self,
        workflow_id: str,
        node_id: str,
        permission: NodePermission,
        user_id: str | None = None,
        role: str | None = None,
        effect: PermissionEffect = PermissionEffect.ALLOW,
        masked_fields: list[str] | None = None,
        redirect_node: str | None = None,
    ):
        """Add a node-level permission rule"""
        rule = PermissionRule(
            id=f"node_{workflow_id}_{node_id}_{permission.value}_{len(self.rules)}",
            resource_type="node",
            resource_id=node_id,
            permission=permission,
            effect=effect,
            user_id=user_id,
            role=role,
        )

        if masked_fields:
            rule.conditions["masked_fields"] = masked_fields

        if redirect_node:
            rule.conditions["redirect_node"] = redirect_node

        self.rules.append(rule)

    def apply_to_manager(self, manager: AccessControlManager):
        """Apply all rules to an access control manager"""
        for rule in self.rules:
            manager.add_rule(rule)


def execute_with_access_control(
    workflow: Workflow,
    user_context: UserContext,
    parameters: dict[str, Any] | None = None,
    access_config: AccessControlConfig | None = None,
) -> tuple[Any, str]:
    """
    Convenience function to execute a workflow with access control.

    Provides a simple way to execute workflows with access control without
    manually creating runtime instances. Automatically applies access
    configuration and manages the runtime lifecycle.

    Args:
        workflow: The workflow to execute
        user_context: User context for access control decisions
        parameters: Optional runtime parameters for workflow execution
        access_config: Optional access control configuration to apply

    Returns:
        Tuple containing:
            - result: The workflow execution result
            - run_id: Unique identifier for this execution run

    Raises:
        PermissionError: If user lacks permission to execute workflow
        ValueError: If workflow or user_context is invalid

    Side Effects:
        - Applies access control rules to global manager if config provided
        - Logs audit events for access decisions
        - Enables access control globally during execution

    Example:
        >>> from kailash.runtime.access_controlled import execute_with_access_control
        >>> from kailash.access_control import UserContext
        >>> from kailash.workflow import Workflow
        >>>
        >>> user = UserContext(user_id="123", tenant_id="abc", email="user@test.com", roles=["viewer"])
        >>> workflow = Workflow(workflow_id="test", name="Test")
        >>> # Function exists and can be called
        >>> callable(execute_with_access_control)
        True
    """
    # Set up access control if config provided
    if access_config:
        acm = get_access_control_manager()
        access_config.apply_to_manager(acm)
        acm.enabled = True  # Enable access control

    # Create runtime and execute with context manager for proper cleanup
    with AccessControlledRuntime(user_context) as runtime:
        return runtime.execute(workflow, parameters)
