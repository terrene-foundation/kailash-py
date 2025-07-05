"""
Enterprise Access Control for Kailash Middleware

Consolidates existing Kailash access control implementations (RBAC/ABAC)
into the middleware layer for unified authentication and authorization.
"""

from typing import Any, Dict, List, Optional

# Import existing Kailash access control components
from kailash.access_control import AccessControlManager as BaseAccessControlManager
from kailash.access_control import (
    AccessDecision,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
)
from kailash.access_control_abac import AttributeOperator, EnhancedAccessControlManager
from kailash.nodes.admin import (
    AuditLogNode,
    PermissionCheckNode,
    RoleManagementNode,
    SecurityEventNode,
    UserManagementNode,
)

# Import Kailash security nodes
from kailash.nodes.security import CredentialManagerNode, RotatingCredentialNode

# Import middleware event system
from ..communication.events import EventStream, EventType
from ..core.agent_ui import AgentUIMiddleware


class MiddlewareAccessControlManager:
    """
    Enterprise access control manager for Kailash middleware.

    Consolidates existing Kailash RBAC/ABAC implementations with
    middleware-specific features like session management, real-time
    events, and multi-tenant isolation.
    """

    def __init__(
        self,
        event_stream: EventStream = None,
        enable_abac: bool = True,
        enable_audit: bool = True,
    ):
        # Use existing Kailash access control implementations
        if enable_abac:
            self.access_manager = EnhancedAccessControlManager()
        else:
            self.access_manager = BaseAccessControlManager()

        # Middleware integration
        self.event_stream = event_stream
        self.enable_audit = enable_audit

        # Kailash nodes for operations
        self.user_mgmt_node = UserManagementNode()
        self.role_mgmt_node = RoleManagementNode()
        self.permission_check_node = PermissionCheckNode()
        self.audit_node = AuditLogNode() if enable_audit else None
        self.security_event_node = SecurityEventNode()

    async def check_session_access(
        self, user_context: UserContext, session_id: str, action: str = "access"
    ) -> AccessDecision:
        """Check if user can access a specific session."""

        # Use Kailash permission check node
        result = self.permission_check_node.execute(
            {
                "user_context": user_context,
                "resource_type": "session",
                "resource_id": session_id,
                "action": action,
            }
        )

        decision = AccessDecision(
            allowed=result.get("allowed", False),
            reason=result.get("reason", "Session access denied"),
            user_id=user_context.user_id,
            resource_id=session_id,
            permission=f"session.{action}",
        )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(decision, "session", user_context)

        return decision

    async def check_workflow_access(
        self,
        user_context: UserContext,
        workflow_id: str,
        permission: WorkflowPermission,
    ) -> AccessDecision:
        """Check workflow access using existing Kailash RBAC/ABAC."""

        # Use existing Kailash access control
        decision = self.access_manager.check_workflow_access(
            user_context, workflow_id, permission
        )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(decision, "workflow", user_context)

        # Audit logging using Kailash audit node
        if self.enable_audit and self.audit_node:
            self.audit_node.execute(
                {
                    "event_type": "workflow_access_check",
                    "user_id": user_context.user_id,
                    "resource_id": workflow_id,
                    "permission": permission.value,
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                }
            )

        return decision

    async def check_node_access(
        self, user_context: UserContext, node_id: str, permission: NodePermission
    ) -> AccessDecision:
        """Check node access using existing Kailash RBAC/ABAC."""

        # Use existing Kailash access control
        decision = self.access_manager.check_node_access(
            user_context, node_id, permission
        )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(decision, "node", user_context)

        return decision

    async def check_api_access(
        self, user_context: UserContext, endpoint: str, method: str = "GET"
    ) -> AccessDecision:
        """Check API endpoint access (middleware-specific)."""

        # Create custom permission for API endpoints
        api_permission = f"api.{method.lower()}.{endpoint.replace('/', '.')}"

        # Use existing Kailash permission rules
        rules = self.access_manager.get_user_permissions(user_context)

        allowed = any(
            rule.permission == api_permission and rule.effect == PermissionEffect.ALLOW
            for rule in rules
        )

        decision = AccessDecision(
            allowed=allowed,
            reason=f"API access {'granted' if allowed else 'denied'} for {endpoint}",
            user_id=user_context.user_id,
            resource_id=endpoint,
            permission=api_permission,
        )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(decision, "api", user_context)

        return decision

    async def create_user_context_from_token(
        self, token_payload: Dict[str, Any]
    ) -> UserContext:
        """Create UserContext from JWT token payload."""

        return UserContext(
            user_id=token_payload.get("sub"),
            tenant_id=token_payload.get("tenant_id"),
            email=token_payload.get("email"),
            roles=token_payload.get("roles", []),
            attributes=token_payload.get("attributes", {}),
            session_id=token_payload.get("session_id"),
        )

    async def assign_role_to_user(
        self, user_id: str, role: str, assigned_by: str, tenant_id: str = None
    ) -> Dict[str, Any]:
        """Assign role to user using Kailash role management node."""

        result = self.role_mgmt_node.execute(
            {
                "action": "assign_role",
                "user_id": user_id,
                "role": role,
                "assigned_by": assigned_by,
                "tenant_id": tenant_id,
            }
        )

        # Emit security event
        if self.event_stream:
            from ..events import WorkflowEvent

            event = WorkflowEvent(
                type=EventType.SYSTEM_STATUS,
                workflow_id="access_control",
                data={
                    "action": "role_assigned",
                    "user_id": user_id,
                    "role": role,
                    "assigned_by": assigned_by,
                },
            )
            await self.event_stream.emit(event)

        return result

    async def create_permission_rule(
        self, rule_data: Dict[str, Any], created_by: str
    ) -> Dict[str, Any]:
        """Create permission rule using existing Kailash patterns."""

        # Use existing access control manager
        rule = PermissionRule(
            user_id=rule_data.get("user_id"),
            role=rule_data.get("role"),
            permission=rule_data.get("permission"),
            resource_pattern=rule_data.get("resource_pattern"),
            effect=PermissionEffect(rule_data.get("effect", "allow")),
            conditions=rule_data.get("conditions", {}),
        )

        self.access_manager.add_permission_rule(rule)

        # Audit the rule creation
        if self.enable_audit and self.audit_node:
            self.audit_node.execute(
                {
                    "event_type": "permission_rule_created",
                    "rule_data": rule_data,
                    "created_by": created_by,
                }
            )

        return {"success": True, "rule_id": str(hash(str(rule)))}

    async def get_user_effective_permissions(
        self, user_context: UserContext
    ) -> List[Dict[str, Any]]:
        """Get effective permissions for user using Kailash access control."""

        # Use existing Kailash implementation
        rules = self.access_manager.get_user_permissions(user_context)

        return [
            {
                "permission": rule.permission,
                "resource_pattern": rule.resource_pattern,
                "effect": rule.effect.value,
                "conditions": rule.conditions,
            }
            for rule in rules
        ]

    async def _emit_access_event(
        self, decision: AccessDecision, resource_type: str, user_context: UserContext
    ):
        """Emit access control event to middleware event stream."""

        from ..events import WorkflowEvent

        event = WorkflowEvent(
            type=(
                EventType.SYSTEM_STATUS
                if decision.allowed
                else EventType.SYSTEM_WARNING
            ),
            workflow_id="access_control",
            data={
                "access_decision": {
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "user_id": decision.user_id,
                    "resource_id": decision.resource_id,
                    "permission": decision.permission,
                    "resource_type": resource_type,
                },
                "user_context": {
                    "user_id": user_context.user_id,
                    "tenant_id": user_context.tenant_id,
                    "roles": user_context.roles,
                    "session_id": getattr(user_context, "session_id", None),
                },
            },
        )

        await self.event_stream.emit(event)

    def get_stats(self) -> Dict[str, Any]:
        """Get access control statistics."""
        base_stats = (
            self.access_manager.get_stats()
            if hasattr(self.access_manager, "get_stats")
            else {}
        )

        return {
            **base_stats,
            "middleware_features": {
                "abac_enabled": isinstance(
                    self.access_manager, EnhancedAccessControlManager
                ),
                "audit_enabled": self.enable_audit,
                "event_stream_connected": self.event_stream is not None,
                "kailash_nodes_used": [
                    "UserManagementNode",
                    "RoleManagementNode",
                    "PermissionCheckNode",
                    "AuditLogNode",
                    "SecurityEventNode",
                ],
            },
        }


class MiddlewareAuthenticationMiddleware:
    """
    Authentication middleware that integrates with Kailash security components.
    """

    def __init__(
        self,
        access_control_manager: MiddlewareAccessControlManager,
        credential_manager: CredentialManagerNode = None,
    ):
        self.access_manager = access_control_manager
        self.credential_manager = credential_manager or CredentialManagerNode(
            name="middleware_credentials",
            credential_name="jwt_secret",
            credential_type="api_key",
        )

    async def authenticate_request(
        self, headers: Dict[str, str], session_id: str = None
    ) -> tuple[bool, UserContext]:
        """
        Authenticate incoming request using Kailash security patterns.

        Returns:
            Tuple of (authenticated, user_context)
        """

        # Extract token from headers
        auth_header = headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False, None

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Use Kailash credential manager for token validation
        try:
            # This would typically validate JWT token
            # For now, simulating with credential manager
            cred_result = self.credential_manager.execute(
                {"action": "validate_token", "token": token}
            )

            if not cred_result.get("valid", False):
                return False, None

            # Create user context from token data
            token_data = cred_result.get("token_data", {})
            user_context = UserContext(
                user_id=token_data.get("user_id"),
                tenant_id=token_data.get("tenant_id"),
                email=token_data.get("email"),
                roles=token_data.get("roles", []),
                attributes=token_data.get("attributes", {}),
                session_id=session_id,
            )

            return True, user_context

        except Exception as e:
            # Log security event using Kailash security event node
            self.access_manager.security_event_node.execute(
                {
                    "event_type": "authentication_failure",
                    "error": str(e),
                    "token_preview": token[:10] + "..." if len(token) > 10 else token,
                }
            )

            return False, None

    async def authorize_request(
        self,
        user_context: UserContext,
        resource_type: str,
        resource_id: str,
        action: str,
    ) -> AccessDecision:
        """Authorize request using Kailash access control."""

        if resource_type == "session":
            return await self.access_manager.check_session_access(
                user_context, resource_id, action
            )
        elif resource_type == "workflow":
            permission = WorkflowPermission(action)
            return await self.access_manager.check_workflow_access(
                user_context, resource_id, permission
            )
        elif resource_type == "node":
            permission = NodePermission(action)
            return await self.access_manager.check_node_access(
                user_context, resource_id, permission
            )
        elif resource_type == "api":
            return await self.access_manager.check_api_access(
                user_context, resource_id, action
            )
        else:
            # Default deny for unknown resource types
            return AccessDecision(
                allowed=False,
                reason=f"Unknown resource type: {resource_type}",
                user_id=user_context.user_id,
                resource_id=resource_id,
                permission=f"{resource_type}.{action}",
            )
