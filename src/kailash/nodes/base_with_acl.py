"""
Base Node with Optional Access Control Layer

This module extends the base Node class with optional access control capabilities.
The access control is completely transparent and disabled by default, ensuring
no interference with existing SDK usage.

Key Design Principles:
- Access control is OFF by default
- Zero performance impact when disabled
- Fully backward compatible
- Opt-in at workflow or node level
- No changes required to existing code
"""

import logging
from typing import Any

from kailash.access_control import (
    AccessDecision,
    NodePermission,
    UserContext,
    get_access_control_manager,
)
from kailash.nodes.base import Node
from kailash.nodes.base_async import AsyncNode

logger = logging.getLogger(__name__)


class NodeWithAccessControl(Node):
    """
    Base node class with optional access control capabilities.

    Extends the standard Node class with transparent access control features
    that can be enabled on demand without affecting existing functionality.
    Access control is completely disabled by default for backward compatibility.

    Design Purpose:
        Provides a foundation for nodes that need access control while
        maintaining complete backward compatibility. Enables fine-grained
        permissions, data masking, and conditional execution.

    Upstream Dependencies:
        - AccessControlManager for permission evaluation
        - UserContext from authentication systems
        - PermissionRule definitions from configuration

    Downstream Consumers:
        - AccessControlledRuntime for secure execution
        - Audit systems for logging access attempts
        - Data masking systems for output filtering

    Usage Patterns:
        - Extended by nodes requiring access control
        - Configured with permission requirements
        - Used in conjunction with AccessControlledRuntime
        - Transparent to existing node implementations

    Implementation Details:
        Access control is evaluated only when explicitly enabled.
        Permissions checked before node execution.
        Output masking applied based on user roles.
        Fallback execution for denied access scenarios.

    Error Handling:
        - Access denied returns user-friendly error messages
        - Missing permissions default to deny
        - Configuration errors are logged and treated as disabled
        - Execution errors maintain standard Node behavior

    Side Effects:
        - Logs access attempts for audit purposes
        - May redirect execution to fallback nodes
        - Applies data masking to sensitive outputs

    Example:
        >>> class SecureProcessorNode(NodeWithAccessControl):
        ...     def _execute(self, **inputs):
        ...         return {"result": "processed"}
        >>>
        >>> node = SecureProcessorNode(
        ...     enable_access_control=True,
        ...     required_permission=NodePermission.EXECUTE,
        ...     mask_output_fields=["sensitive_data"]
        ... )
    """

    def __init__(self, **config):
        super().__init__(**config)
        # Access control is disabled by default
        self._access_control_enabled = config.get("enable_access_control", False)
        self._required_permission = config.get(
            "required_permission", NodePermission.EXECUTE
        )
        self._fallback_node = config.get("fallback_node", None)
        self._mask_output_fields = config.get("mask_output_fields", [])

    def run(self, **inputs) -> Any:
        """
        Execute node with optional access control checks.

        If access control is disabled or no user context is present,
        this behaves exactly like the standard Node.execute() method.
        """
        # Extract runtime context if present
        runtime_context = inputs.pop("_runtime_context", None)
        user_context = inputs.pop("_user_context", None)

        # If no access control needed, run normally
        if not self._should_check_access(user_context):
            return self._execute(**inputs)

        # Perform access check
        acm = get_access_control_manager()
        decision = acm.check_node_access(
            user_context,
            self._get_node_id(),
            self._required_permission,
            runtime_context or {},
        )

        # Handle access decision
        if decision.allowed:
            # Execute node
            result = self._execute(**inputs)

            # Apply output masking if needed
            if decision.masked_fields and isinstance(result, dict):
                result = self._mask_fields(result, decision.masked_fields)

            return result
        else:
            # Access denied
            return self._handle_access_denied(decision, inputs)

    def _execute(self, **inputs) -> Any:
        """
        The actual node execution logic.
        Override this method in subclasses instead of run().
        """
        # Default implementation calls parent run()
        # This maintains compatibility with existing nodes
        if hasattr(super(), "run"):
            return super().run(**inputs)
        else:
            raise NotImplementedError("Node must implement _execute() method")

    def _should_check_access(self, user_context: UserContext | None) -> bool:
        """
        Determine if access control should be checked.

        Returns False (no check) if:
        - Access control is disabled globally
        - No user context is provided
        - Node has explicitly disabled access control
        """
        # Global check
        acm = get_access_control_manager()
        if not acm or not getattr(acm, "enabled", False):
            return False

        # Node-level check
        if not self._access_control_enabled:
            return False

        # User context check
        if not user_context:
            return False

        return True

    def _get_node_id(self) -> str:
        """Get the node ID for access control checks"""
        # Try to get from config first
        if "node_id" in self.config:
            return self.config["node_id"]

        # Fall back to class name
        return self.__class__.__name__

    def _mask_fields(self, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Mask specified fields in output data"""
        masked_data = data.copy()
        for field in fields:
            if field in masked_data:
                masked_data[field] = "***MASKED***"
        return masked_data

    def _handle_access_denied(
        self, decision: AccessDecision, inputs: dict[str, Any]
    ) -> Any:
        """
        Handle access denied scenarios.

        Can be overridden by subclasses for custom behavior.
        """
        # Log access denial
        logger.warning(
            f"Access denied for node {self._get_node_id()}: {decision.reason}"
        )

        # If a fallback node is configured, return a marker for the runtime
        if self._fallback_node:
            return {
                "_access_denied": True,
                "_redirect_to": self._fallback_node,
                "_original_inputs": inputs,
            }

        # Return empty result by default
        return {}


class AsyncNodeWithAccessControl(AsyncNode):
    """Async version of NodeWithAccessControl"""

    def __init__(self, **config):
        super().__init__(**config)
        self._access_control_enabled = config.get("enable_access_control", False)
        self._required_permission = config.get(
            "required_permission", NodePermission.EXECUTE
        )
        self._fallback_node = config.get("fallback_node", None)
        self._mask_output_fields = config.get("mask_output_fields", [])

    async def async_run(self, **inputs) -> Any:
        """Async execution with optional access control"""
        runtime_context = inputs.pop("_runtime_context", None)
        user_context = inputs.pop("_user_context", None)

        if not self._should_check_access(user_context):
            return await self._execute(**inputs)

        acm = get_access_control_manager()
        decision = acm.check_node_access(
            user_context,
            self._get_node_id(),
            self._required_permission,
            runtime_context or {},
        )

        if decision.allowed:
            result = await self._execute(**inputs)

            if decision.masked_fields and isinstance(result, dict):
                result = self._mask_fields(result, decision.masked_fields)

            return result
        else:
            return self._handle_access_denied(decision, inputs)

    async def _execute(self, **inputs) -> Any:
        """Async execution logic"""
        if hasattr(super(), "run"):
            return await super().run(**inputs)
        else:
            raise NotImplementedError("Node must implement _execute() method")

    # Reuse other methods from sync version
    _should_check_access = NodeWithAccessControl._should_check_access
    _get_node_id = NodeWithAccessControl._get_node_id
    _mask_fields = NodeWithAccessControl._mask_fields
    _handle_access_denied = NodeWithAccessControl._handle_access_denied


def make_node_access_controlled(node_class, **acl_config):
    """
    Factory function to add access control to any existing node class.

    This allows adding access control to nodes without modifying their code:

    >>> from kailash.nodes.data.readers import CSVReaderNode
    >>> SecureCSVReader = make_node_access_controlled(
    ...     CSVReaderNode,
    ...     enable_access_control=True,
    ...     required_permission=NodePermission.READ_OUTPUT
    ... )
    """

    class AccessControlledNode(NodeWithAccessControl, node_class):
        def __init__(self, **config):
            # Merge ACL config with node config
            full_config = {**acl_config, **config}
            super().__init__(**full_config)

        def _execute(self, **inputs):
            # Call the original node's run method
            return node_class.execute(self, **inputs)

    # Preserve the original class name and module
    AccessControlledNode.__name__ = f"Secure{node_class.__name__}"
    AccessControlledNode.__module__ = node_class.__module__

    return AccessControlledNode


def add_access_control(node_instance, **acl_config):
    """
    Add access control to an existing node instance.

    This function adds access control attributes to a node instance.
    For simplicity in this example, we'll just add the attributes
    and let the AccessControlledRuntime handle the actual access control.

    Args:
        node_instance: The node instance to wrap
        **acl_config: Access control configuration
            - enable_access_control: Whether to enable access control (default: True)
            - required_permission: Permission required to execute the node
            - node_id: Unique identifier for access control rules
            - mask_output_fields: List of fields to mask in output for non-admin users
            - fallback_node: Node ID to execute if access is denied

    Returns:
        Node instance with access control capabilities

    Example:
        >>> reader = CSVReaderNode(file_path="data.csv")
        >>> secure_reader = add_access_control(
        ...     reader,
        ...     enable_access_control=True,
        ...     required_permission=NodePermission.EXECUTE,
        ...     node_id="secure_csv_reader"
        ... )
    """
    # If access control is disabled, return the original node
    if not acl_config.get("enable_access_control", True):
        return node_instance

    # Add access control attributes to the node instance
    for key, value in acl_config.items():
        setattr(node_instance, key, value)

    # Mark this node as access-controlled
    node_instance._access_controlled = True

    return node_instance
