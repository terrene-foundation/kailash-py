"""DataFlow Security Access Control Node - SDK Compliant Implementation."""

import asyncio
from typing import Any, Dict, List, Optional

from kailash.access_control.managers import AccessControlManager
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class DataFlowAccessControlNode(AsyncNode):
    """Node for access control in DataFlow operations.

    This node extends AsyncNode and leverages the SDK's AccessControlManager
    to provide enterprise-grade access control following SDK patterns.

    Configuration Parameters (set during initialization):
        strategy: Access control strategy (rbac, abac, hybrid)
        cache_ttl: Cache time-to-live in seconds
        audit_enabled: Enable audit logging
        strict_mode: Enable strict permission checking
        default_deny: Deny access by default if no rules match

    Runtime Parameters (provided during execution):
        user_id: User ID to check permissions for
        resource: Resource being accessed
        action: Action being performed
        context: Additional context for evaluation
        permissions: List of permissions to check
        roles: List of roles to verify
    """

    def __init__(self, **kwargs):
        """Initialize the DataFlowAccessControlNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.strategy = kwargs.pop("strategy", "rbac")
        self.cache_ttl = kwargs.pop("cache_ttl", 300)
        self.audit_enabled = kwargs.pop("audit_enabled", True)
        self.strict_mode = kwargs.pop("strict_mode", True)
        self.default_deny = kwargs.pop("default_deny", True)
        self.required_roles = kwargs.pop("required_roles", [])

        # Call parent constructor
        super().__init__(**kwargs)

        # Initialize the SDK AccessControlManager
        self.access_manager = AccessControlManager(strategy=self.strategy, enabled=True)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=True,
                description="User ID to check permissions for",
            ),
            "resource": NodeParameter(
                name="resource",
                type=str,
                required=True,
                description="Resource being accessed (e.g., 'dataflow:bulk_operations')",
            ),
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="Action being performed (e.g., 'create', 'read', 'update', 'delete')",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context for access evaluation",
            ),
            "permissions": NodeParameter(
                name="permissions",
                type=list,
                required=False,
                default=[],
                description="List of permissions to check",
                auto_map_from=["required_permissions", "perms"],
            ),
            "roles": NodeParameter(
                name="roles",
                type=list,
                required=False,
                default=[],
                description="List of roles to verify",
                auto_map_from=["required_roles", "user_roles"],
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute access control check asynchronously."""
        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            user_id = validated_inputs.get("user_id")
            resource = validated_inputs.get("resource")
            action = validated_inputs.get("action")
            context = validated_inputs.get("context", {})
            permissions = validated_inputs.get("permissions", [])
            roles = validated_inputs.get("roles", [])

            # Check access using SDK AccessControlManager
            access_result = await self._check_access(
                user_id, resource, action, context, permissions, roles
            )

            # Build result following SDK patterns
            result = {
                "success": True,
                "allowed": access_result["allowed"],
                "reason": access_result.get("reason", ""),
                "user_id": user_id,
                "resource": resource,
                "action": action,
                "permissions_checked": permissions,
                "roles_checked": roles,
                "metadata": {
                    "strategy": self.strategy,
                    "audit_enabled": self.audit_enabled,
                    "strict_mode": self.strict_mode,
                    "cache_hit": access_result.get("cache_hit", False),
                },
            }

            # Add audit trail if enabled
            if self.audit_enabled:
                result["audit_trail"] = {
                    "timestamp": access_result.get("timestamp"),
                    "decision": "allow" if access_result["allowed"] else "deny",
                    "evaluated_rules": access_result.get("evaluated_rules", []),
                }

            return result

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except (NodeExecutionError, Exception) as e:
            return {"success": False, "error": str(e), "allowed": False}

    async def _check_access(
        self,
        user_id: str,
        resource: str,
        action: str,
        context: Dict[str, Any],
        permissions: List[str],
        roles: List[str],
    ) -> Dict[str, Any]:
        """Check access using SDK AccessControlManager."""
        try:
            # Use SDK AccessControlManager to check access
            # Use the correct SDK method for node access checking
            try:
                # For node-level access control
                access_result = self.access_manager.check_node_access(
                    node_type=resource,
                    context={"user_id": user_id, "action": action, **context},
                )

                # Handle both boolean and AccessDecision returns
                if hasattr(access_result, "allowed"):
                    # AccessDecision object
                    result = {
                        "allowed": access_result.allowed,
                        "reason": getattr(access_result, "reason", ""),
                        "applied_rules": getattr(access_result, "applied_rules", []),
                        "conditions_met": getattr(access_result, "conditions_met", []),
                    }
                else:
                    # Boolean return
                    result = {"allowed": bool(access_result)}

            except Exception as e:
                # Re-raise the original exception to be handled by async_run
                raise NodeExecutionError(f"Access check failed: {str(e)}")

            # If specific permissions are required, check them
            if permissions and self.strict_mode:
                user_permissions = context.get("user_permissions", [])
                for perm in permissions:
                    if perm not in user_permissions:
                        return {
                            "allowed": False,
                            "reason": f"Missing required permission: {perm}",
                            "cache_hit": False,
                        }

            # Only check additional roles if SDK didn't already deny access
            if result.get("allowed", False):
                # If this node has required roles, check if user has them
                required_roles = getattr(self, "required_roles", [])
                if required_roles and self.strict_mode:
                    # User roles come from the 'roles' parameter (mapped from user_roles)
                    user_roles = roles  # This contains the user's actual roles
                    has_required_role = any(
                        role in user_roles for role in required_roles
                    )
                    if not has_required_role:
                        return {
                            "allowed": False,
                            "reason": f"User lacks required roles. Required: {required_roles}, User has: {user_roles}",
                            "cache_hit": False,
                        }

            return result

        except Exception as e:
            # Re-raise exception to be handled by main async_run method
            raise NodeExecutionError(f"Access check error: {str(e)}")
