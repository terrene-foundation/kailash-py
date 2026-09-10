"""
Enterprise Access Control for Kailash Middleware

Consolidates existing Kailash access control implementations (RBAC/ABAC)
into the middleware layer for unified authentication and authorization.
"""

import inspect
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
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
from kailash.sdk_exceptions import KailashConfigError

# Import middleware event system
from ..communication.events import EventStream, EventType
from ..core.agent_ui import AgentUIMiddleware

logger = logging.getLogger(__name__)


class MiddlewareAccessControlManager:
    """
    Enterprise access control manager for Kailash middleware.

    Consolidates existing Kailash RBAC/ABAC implementations with
    middleware-specific features like session management, real-time
    events, and multi-tenant isolation.
    """

    def __init__(
        self,
        event_stream: Optional[EventStream] = None,
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
            user_context=user_context,
            resource_type="session",
            resource_id=session_id,
            action=action,
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
        check_fn = getattr(self.access_manager, "check_workflow_access", None)
        if check_fn:
            decision = check_fn(user_context, workflow_id, permission)
        else:
            decision = AccessDecision(
                allowed=False,
                reason="Workflow access check not supported",
                user_id=user_context.user_id,
                resource_id=workflow_id,
                permission=permission.value,
            )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(decision, "workflow", user_context)

        # Audit logging using Kailash audit node
        if self.enable_audit and self.audit_node:
            self.audit_node.execute(
                event_type="workflow_access_check",
                user_id=user_context.user_id,
                resource_id=workflow_id,
                permission=permission.value,
                allowed=decision.allowed,
                reason=decision.reason,
            )

        return decision

    async def check_node_access(
        self, user_context: UserContext, node_id: str, permission: NodePermission
    ) -> AccessDecision:
        """Check node access using existing Kailash RBAC/ABAC."""

        # Use existing Kailash access control
        check_fn = getattr(self.access_manager, "check_node_access", None)
        if check_fn:
            decision = check_fn(user_context, node_id, permission)
        else:
            decision = AccessDecision(
                allowed=False,
                reason="Node access check not supported",
                user_id=user_context.user_id,
                resource_id=node_id,
                permission=permission.value,
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
        get_perms_fn = getattr(self.access_manager, "get_user_permissions", None)
        rules = get_perms_fn(user_context) if get_perms_fn else []

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
            user_id=token_payload.get("sub", ""),
            tenant_id=token_payload.get("tenant_id"),
            email=token_payload.get("email"),
            roles=token_payload.get("roles", []),
            attributes=token_payload.get("attributes", {}),
            session_id=token_payload.get("session_id"),
        )

    async def assign_role_to_user(
        self, user_id: str, role: str, assigned_by: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assign role to user using Kailash role management node."""

        result = self.role_mgmt_node.execute(
            action="assign_role",
            user_id=user_id,
            role=role,
            assigned_by=assigned_by,
            tenant_id=tenant_id,
        )

        # Emit security event
        if self.event_stream:
            from ..communication.events import WorkflowEvent

            event = WorkflowEvent(
                id=str(uuid.uuid4()),
                type=EventType.SYSTEM_STATUS,
                timestamp=datetime.now(timezone.utc),
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
        """Register a permission rule on the access manager.

        Fails CLOSED (issue #2057, site 1). The previous implementation probed
        the manager for ``add_permission_rule`` — a name with zero definitions
        repo-wide — so the rule was never registered, while the
        ``permission_rule_created`` audit event and ``{"success": True}`` were
        emitted unconditionally, outside the guard. An operator saw the rule
        succeed and saw it in the audit trail; it enforced nothing, and the
        returned ``rule_id`` was ``hash(str(rule))`` — an id referring to no
        registered rule. That is a falsified audit record of a security
        control.

        Three defects are fixed together, because the first hid the others:

        1. The real registration API on both shipped managers
           (``AccessControlManager``, ``EnhancedAccessControlManager``) is
           ``add_rule``. It is called directly, and its absence raises
           :class:`KailashConfigError` rather than being silently skipped.
        2. ``PermissionRule`` has no ``resource_pattern`` field and requires
           ``id``/``resource_type``/``resource_id``, so the old constructor
           call raised ``TypeError`` before it ever reached the dead guard —
           this method could not succeed at all. Rule data is now validated
           and mapped onto the real field set (``resource_pattern`` is still
           accepted as the legacy spelling of ``resource_id``).
        3. The audit event and the success response are emitted only AFTER
           ``add_rule`` returns, and ``rule_id`` is the id the rule was
           actually registered under.

        Raises:
            ValueError: If ``rule_data`` omits ``permission`` or the resource
                the rule applies to. A rule missing either matches nothing, so
                registering it would be the same silent no-op in a new place.
            KailashConfigError: If the configured access manager exposes no
                ``add_rule``; the rule cannot be registered and no audit event
                is emitted.
        """
        permission = rule_data.get("permission")
        if not permission:
            raise ValueError(
                "rule_data['permission'] is required: a permission rule with no "
                "permission matches no access check and would enforce nothing."
            )

        # `resource_pattern` was this method's original (never-working) spelling;
        # accept it so existing callers keep working, but store it in the field
        # PermissionRule actually has.
        resource_id = rule_data.get("resource_id") or rule_data.get("resource_pattern")
        if not resource_id:
            raise ValueError(
                "rule_data must name the resource via 'resource_id' (or the "
                "legacy 'resource_pattern'): a rule with no resource matches "
                "no access check and would enforce nothing."
            )

        rule = PermissionRule(
            id=rule_data.get("id") or f"rule-{uuid.uuid4()}",
            resource_type=rule_data.get("resource_type", "api"),
            resource_id=resource_id,
            permission=permission,
            effect=PermissionEffect(rule_data.get("effect", "allow")),
            user_id=rule_data.get("user_id"),
            role=rule_data.get("role"),
            tenant_id=rule_data.get("tenant_id"),
            conditions=rule_data.get("conditions", {}),
            created_by=created_by,
        )

        add_rule_fn = getattr(self.access_manager, "add_rule", None)
        if not callable(add_rule_fn):
            raise KailashConfigError(
                f"{type(self.access_manager).__name__} exposes no callable "
                "add_rule(); permission rules cannot be registered. Configure "
                "MiddlewareAccessControlManager with an access manager that "
                "implements add_rule(PermissionRule) — both "
                "kailash.access_control.AccessControlManager and "
                "kailash.access_control_abac.EnhancedAccessControlManager do."
            )
        add_rule_fn(rule)

        # Audit ONLY after the rule is genuinely registered. Emitting this
        # before/regardless of registration is what made the audit trail lie.
        if self.enable_audit and self.audit_node:
            self.audit_node.execute(
                event_type="permission_rule_created",
                rule_data=rule_data,
                created_by=created_by,
                rule_id=rule.id,
            )

        return {"success": True, "rule_id": rule.id}

    async def get_user_effective_permissions(
        self, user_context: UserContext
    ) -> List[Dict[str, Any]]:
        """Get effective permissions for user using Kailash access control."""

        # Use existing Kailash implementation
        get_perms_fn = getattr(self.access_manager, "get_user_permissions", None)
        rules = get_perms_fn(user_context) if get_perms_fn else []

        # `rule.resource_pattern` does not exist on PermissionRule — reading it
        # raised AttributeError for every registered rule (same #2057 root cause
        # as create_permission_rule: this pair was written against a field set
        # the dataclass never had). The real field is `resource_id`.
        #
        # `permission` is genuinely dual-shape: the middleware's own API rules
        # carry string permissions (check_api_access compares against the
        # string `api.<method>.<path>`), while SDK-registered rules carry
        # WorkflowPermission/NodePermission enums. Dispatch on the type rather
        # than probing for `.value` (zero-tolerance Rule 3d).
        return [
            {
                "permission": (
                    rule.permission.value
                    if isinstance(rule.permission, Enum)
                    else rule.permission
                ),
                "resource_type": rule.resource_type,
                "resource_id": rule.resource_id,
                "effect": (
                    rule.effect.value if isinstance(rule.effect, Enum) else rule.effect
                ),
                "conditions": rule.conditions,
            }
            for rule in rules
        ]

    async def _emit_access_event(
        self, decision: AccessDecision, resource_type: str, user_context: UserContext
    ):
        """Emit access control event to middleware event stream."""

        from ..communication.events import WorkflowEvent

        event = WorkflowEvent(
            id=str(uuid.uuid4()),
            type=(
                EventType.SYSTEM_STATUS
                if decision.allowed
                else EventType.SYSTEM_WARNING
            ),
            timestamp=datetime.now(timezone.utc),
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

        if self.event_stream:
            await self.event_stream.emit(event)

    def get_stats(self) -> Dict[str, Any]:
        """Get access control statistics."""
        base_stats = (
            getattr(self.access_manager, "get_stats", lambda: {})()
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

    Note:
        Token verification is delegated to
        :class:`~kailash.trust.auth.jwt.JWTValidator`, which is where this SDK's
        JWT crypto lives (algorithm-confusion rejection, the ``none``-algorithm
        ban, the RFC 7518 §3.2 key-length floor). This class contributes header
        parsing and the ``UserContext`` mapping and deliberately implements no
        crypto of its own.
    """

    def __init__(
        self,
        access_control_manager: MiddlewareAccessControlManager,
        credential_manager: Optional[CredentialManagerNode] = None,
        token_verifier: Optional[Any] = None,
    ):
        """
        Args:
            access_control_manager: Authorization manager for this middleware.
            credential_manager: Node used to FETCH the JWT signing secret when
                no ``token_verifier`` is supplied. Its declared credential is
                ``jwt_secret``.
            token_verifier: Any object exposing ``verify_token(token)`` -- a
                ``MiddlewareAuthManager``, a ``JWTAuthManager``, or a
                ``JWTValidator``. Supplying one is the recommended wiring: it
                shares the verification policy with the rest of the deployment
                instead of deriving a second one here.
        """
        self.access_manager = access_control_manager
        self.credential_manager = credential_manager or CredentialManagerNode(
            name="middleware_credentials",
            credential_name="jwt_secret",
            credential_type="api_key",
        )
        self._token_verifier = token_verifier
        # Latch so a missing credential is reported once per instance rather
        # than once per unauthenticated request (the #2114 amplification shape).
        self._no_verifier_logged = False

    def _resolve_verifier(self) -> Optional[Any]:
        """Return something that can verify a token, or None.

        Resolution order: the injected verifier, else a
        :class:`~kailash.trust.auth.jwt.JWTValidator` built from the secret the
        credential manager fetches. Built once and cached -- rebuilding per
        request would re-read the environment on every call.
        """
        if self._token_verifier is not None:
            return self._token_verifier

        try:
            result = self.credential_manager.execute()
            credentials = result.get("credentials") or {}
            secret = credentials.get("api_key") or credentials.get("value")
        except Exception as exc:
            secret = None
            logger.debug("jwt_secret credential fetch failed: %s", type(exc).__name__)

        if not secret:
            return None

        from kailash.trust.auth.jwt import JWTConfig, JWTValidator

        self._token_verifier = JWTValidator(JWTConfig(secret=secret))
        return self._token_verifier

    async def authenticate_request(
        self, headers: Dict[str, str], session_id: Optional[str] = None
    ) -> tuple[bool, Optional[UserContext]]:
        """
        Authenticate incoming request using Kailash security patterns.

        This method could not authenticate anyone before issue #2108. It called
        ``credential_manager.execute(action="validate_token", token=token)`` and
        checked ``cred_result.get("valid", False)`` -- but ``CredentialManagerNode``
        FETCHES credentials and has no token-validation operation, its
        ``get_parameters()`` declared neither ``action`` nor ``token`` (so
        ``Node.execute`` stripped both), and its return dict has no ``valid``
        key on any path. The check was therefore unconditionally False and every
        request was refused, with an in-code comment ("For now, simulating with
        credential manager") standing in for the implementation
        (``zero-tolerance.md`` Rule 2).

        Returns:
            Tuple of (authenticated, user_context). ``(False, None)`` for a
            missing/malformed header, an invalid token, or no configured key
            material -- the last of which fails CLOSED and is reported once.
        """

        # Extract token from headers
        auth_header = headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False, None

        token = auth_header[7:]  # Remove "Bearer " prefix

        verifier = self._resolve_verifier()
        if verifier is None:
            # No key material: refuse, and name the OFF protection and its
            # wiring exactly once (``security.md`` § Secure-Default). Silence
            # here would leave an operator debugging blanket 401s with nothing
            # in the log pointing at the cause.
            if not self._no_verifier_logged:
                self._no_verifier_logged = True
                logger.warning(
                    "middleware_auth.no_token_verifier",
                    extra={
                        "exposure": "every request is refused; no token can verify",
                        "wiring": (
                            "pass token_verifier=... , or configure the "
                            "'jwt_secret' credential the credential manager reads"
                        ),
                    },
                )
            return False, None

        try:
            payload = verifier.verify_token(token)
            if inspect.isawaitable(payload):
                # `MiddlewareAuthManager.verify_token` is async while
                # `JWTAuthManager.verify_token` and `JWTValidator.verify_token`
                # are sync. Awaiting unconditionally raises TypeError on the
                # sync ones (measured: "object dict can't be used in 'await'
                # expression"), which the handler below would then read as an
                # authentication failure for a perfectly valid token.
                payload = await payload

            # Create user context from the verified claims. BOTH subject
            # spellings are read: `MiddlewareAuthManager` stamps `user_id`,
            # while `JWTAuthManager` stamps the RFC 7519 registered `sub`.
            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id:
                # A token that verified but names no subject is a BROKEN
                # credential, not an authenticated one. Admitting it would
                # produce a UserContext with no owner.
                raise ValueError("verified token carries no subject claim")

            user_context = UserContext(
                user_id=user_id,
                tenant_id=payload.get("tenant_id"),
                email=payload.get("email"),
                roles=payload.get("roles", []),
                attributes=payload.get("attributes") or payload.get("metadata") or {},
                session_id=session_id,
            )

            return True, user_context

        except Exception as e:
            # Log security event using Kailash security event node -- BEST
            # EFFORT. The auth decision is the `(False, None)` below; the event
            # is a side effect, and `SecurityEventNode` talks to a database it
            # may not have. Letting it raise would convert a clean deny into an
            # exception escaping an authentication call, which callers read as a
            # server fault rather than a refusal. Same disposition as
            # `MiddlewareAuthManager._emit_security_event`.
            try:
                self.access_manager.security_event_node.execute(
                    event_type="authentication_failure",
                    error=str(e),
                    token_preview=token[:10] + "..." if len(token) > 10 else token,
                )
            except Exception:
                logger.warning(
                    "security event logging failed for authentication_failure"
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
