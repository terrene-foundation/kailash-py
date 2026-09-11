"""
Enterprise Access Control for Kailash Middleware

Consolidates existing Kailash access control implementations (RBAC/ABAC)
into the middleware layer for unified authentication and authorization.
"""

import inspect
import logging
import uuid
from dataclasses import replace
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

# `AuditEventType`/`AuditSeverity` are not re-exported from `kailash.nodes.admin`,
# so they come from the defining module. They are imported as ENUMS rather than
# spelled as string literals on purpose: `AuditLogNode` resolves
# `event_data["event_type"]` through `AuditEventType(...)`, so an invented name
# raises at log time, deep inside the node. Issue #2222 shipped exactly that --
# `permission_rule_created`, which is not a member (measured: 28 members, that
# string absent). Naming the member here moves the failure to import time.
from kailash.nodes.admin.audit_log import AuditEventType, AuditSeverity

# Import Kailash security nodes
from kailash.nodes.security import CredentialManagerNode, RotatingCredentialNode
from kailash.sdk_exceptions import KailashConfigError

# Import middleware event system
from ..communication.events import EventStream, EventType
from ..core.agent_ui import AgentUIMiddleware

logger = logging.getLogger(__name__)


def _decision_context(user_id: str, resource_id: str, permission: Any) -> str:
    """Render the identifying context an access decision was made in.

    ``AccessDecision`` (``kailash/access_control.py``) has exactly six fields --
    ``allowed``, ``reason``, ``applied_rules``, ``conditions_met``,
    ``masked_fields``, ``redirect_node`` -- and no place to put the subject, the
    resource, or the permission. Every call site in this module passed them as
    ``user_id=``/``resource_id=``/``permission=`` anyway, so every one raised
    ``TypeError`` (issue #2222).

    That information is preserved in ``reason``, the field that exists, rather
    than by widening the public dataclass: which ``AccessDecision`` shape is
    canonical is a schema decision belonging to the owners of that public type,
    not to this middleware. Structured consumers are served instead by passing
    these values explicitly to :meth:`_emit_access_event`, which is the only
    place they were ever read back out.
    """
    permission_text = permission.value if isinstance(permission, Enum) else permission
    return f"user={user_id!r} resource={resource_id!r} permission={permission_text!r}"


def _with_context(decision: AccessDecision, context: str) -> AccessDecision:
    """Return ``decision`` with the identifying context folded into ``reason``.

    Applied to decisions DELEGATED to the underlying access manager, which is
    the common path -- the manager computes a verdict and a reason but knows
    nothing about the middleware's need to report who asked for what. Without
    this, the subject/resource/permission would be present only on the branches
    this module builds itself, i.e. the rare ones.

    ``dataclasses.replace`` rather than a fresh construction, so
    ``applied_rules``, ``conditions_met``, ``masked_fields`` and
    ``redirect_node`` survive; rebuilding by hand would silently drop the
    masking instructions a caller is required to honour. A manager returning a
    non-dataclass is a contract violation and is allowed to raise here rather
    than be quietly passed through.
    """
    return replace(decision, reason=f"{decision.reason} [{context}]")


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

        # Latches so a missing manager capability / a failing audit sink is
        # reported ONCE per instance rather than once per request (the #2114
        # log-amplification shape this module already guards against in
        # `MiddlewareAuthenticationMiddleware`).
        self._missing_capabilities_logged: set[str] = set()
        self._audit_failures_logged: set[str] = set()

    def _warn_missing_capability(self, capability: str, consequence: str) -> None:
        """Report ONCE that the configured access manager lacks ``capability``.

        These paths fail CLOSED -- they deny. Until issue #2222 they did not
        even get that far: they raised ``TypeError`` from a malformed
        ``AccessDecision`` construction. That crash was at least LOUD, so
        repairing only the construction would have converted a loud failure
        into a silent, permanent deny that no operator could distinguish from
        a correctly-evaluated refusal. This warning is what keeps the
        fail-closed path observable (``security.md`` Secure-Default: when a
        protection is off, name it and name its wiring).

        Args:
            capability: Method name the configured manager does not expose.
            consequence: What is refused for as long as it is missing.
        """
        if capability in self._missing_capabilities_logged:
            return
        self._missing_capabilities_logged.add(capability)
        logger.warning(
            "middleware_access_control.missing_capability",
            extra={
                "capability": capability,
                "access_manager": type(self.access_manager).__name__,
                "exposure": consequence,
                "wiring": (
                    f"configure MiddlewareAccessControlManager with an access "
                    f"manager implementing {capability}(), or register the "
                    f"equivalent rules on a manager that does"
                ),
            },
        )

    def _audit(
        self,
        event_type: AuditEventType,
        action: str,
        description: str,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Write one audit event. Returns whether it was persisted.

        ``AuditLogNode`` is ``EnterpriseAuditLogNode`` (measured: the name in
        ``kailash.nodes.admin`` is an alias for it). It declares exactly one
        required parameter, ``operation``, and carries the event payload in
        ``event_data``; ``Node.execute`` STRIPS undeclared kwargs. The calls
        this module shipped passed ``event_type=``/``resource_id=``/
        ``permission=``/``allowed=``/``reason=`` as top-level kwargs, so every
        one of them was stripped and the call then died on the missing
        ``operation`` (issue #2222).

        BEST EFFORT, deliberately, and matching the disposition already taken
        for ``SecurityEventNode`` in ``MiddlewareAuthenticationMiddleware``:
        this node writes to a database it may not have (measured without one:
        ``NodeExecutionError: ... password authentication failed``). Letting
        that raise would turn a correctly-computed authorization DENY into an
        exception escaping an authorization call, which callers read as a
        server fault rather than a refusal -- strictly worse than a recorded
        failure. The failure is LOGGED, never swallowed: an audit trail that
        goes missing quietly is the #2057 defect this module was already
        repaired for.
        """
        if not (self.enable_audit and self.audit_node):
            return False

        try:
            self.audit_node.execute(
                operation="log_event",
                event_data={
                    "event_type": event_type.value,
                    "severity": severity.value,
                    "action": action,
                    "description": description,
                    "user_id": user_id,
                    "resource_id": resource_id,
                    "metadata": metadata or {},
                },
            )
            return True
        except Exception as exc:
            # Latch on the ACTION so a persistently-unconfigured sink does not
            # emit one warning per authorization check, while a new failing
            # event type still reports.
            if action not in self._audit_failures_logged:
                self._audit_failures_logged.add(action)
                logger.warning(
                    "middleware_access_control.audit_write_failed",
                    extra={
                        "event_type": event_type.value,
                        "action": action,
                        "user_id": user_id,
                        "resource_id": resource_id,
                        "error": f"{type(exc).__name__}: {exc}",
                        "exposure": (
                            "this event is NOT in the audit trail; the "
                            "authorization decision itself was unaffected"
                        ),
                    },
                )
            return False

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

        permission = f"session.{action}"
        context = _decision_context(user_context.user_id, session_id, permission)
        decision = AccessDecision(
            allowed=result.get("allowed", False),
            reason=f"{result.get('reason', 'Session access denied')} [{context}]",
        )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(
                decision, "session", user_context, session_id, permission
            )

        return decision

    async def check_workflow_access(
        self,
        user_context: UserContext,
        workflow_id: str,
        permission: WorkflowPermission,
    ) -> AccessDecision:
        """Check workflow access using existing Kailash RBAC/ABAC."""

        context = _decision_context(user_context.user_id, workflow_id, permission)

        # Use existing Kailash access control
        check_fn = getattr(self.access_manager, "check_workflow_access", None)
        if check_fn:
            decision = _with_context(
                check_fn(user_context, workflow_id, permission), context
            )
        else:
            # `EnhancedAccessControlManager` (the enable_abac=True default)
            # genuinely does not define check_workflow_access -- so this deny is
            # reached in the shipped default configuration, not just in theory.
            self._warn_missing_capability(
                "check_workflow_access",
                "every workflow access check is DENIED regardless of rules",
            )
            decision = AccessDecision(
                allowed=False,
                reason=f"Workflow access check not supported [{context}]",
            )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(
                decision, "workflow", user_context, workflow_id, permission
            )

        # Audit logging using Kailash audit node
        self._audit(
            event_type=(
                AuditEventType.PERMISSION_CHECKED
                if decision.allowed
                else AuditEventType.PERMISSION_DENIED
            ),
            action="workflow_access_check",
            description=(
                f"Workflow access {'granted' if decision.allowed else 'denied'}: "
                f"{decision.reason}"
            ),
            user_id=user_context.user_id,
            resource_id=workflow_id,
            severity=AuditSeverity.MEDIUM if decision.allowed else AuditSeverity.HIGH,
            metadata={
                "permission": permission.value,
                "allowed": decision.allowed,
                "resource_type": "workflow",
                "tenant_id": user_context.tenant_id,
            },
        )

        return decision

    async def check_node_access(
        self, user_context: UserContext, node_id: str, permission: NodePermission
    ) -> AccessDecision:
        """Check node access using existing Kailash RBAC/ABAC."""

        context = _decision_context(user_context.user_id, node_id, permission)

        # Use existing Kailash access control
        check_fn = getattr(self.access_manager, "check_node_access", None)
        if check_fn:
            decision = _with_context(
                check_fn(user_context, node_id, permission), context
            )
        else:
            self._warn_missing_capability(
                "check_node_access",
                "every node access check is DENIED regardless of rules",
            )
            decision = AccessDecision(
                allowed=False,
                reason=f"Node access check not supported [{context}]",
            )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(
                decision, "node", user_context, node_id, permission
            )

        return decision

    async def check_api_access(
        self, user_context: UserContext, endpoint: str, method: str = "GET"
    ) -> AccessDecision:
        """Check API endpoint access (middleware-specific)."""

        # Create custom permission for API endpoints
        api_permission = f"api.{method.lower()}.{endpoint.replace('/', '.')}"
        context = _decision_context(user_context.user_id, endpoint, api_permission)

        # Use existing Kailash permission rules.
        #
        # `get_user_permissions` is defined on NEITHER shipped manager
        # (measured: the only definition repo-wide is
        # `kailash/trust/auth/rbac.py`, an unrelated class over
        # `AuthenticatedUser`). So this probe resolves to None and `rules` is
        # ALWAYS empty -- the #2057 dead-guard shape, in a second place.
        #
        # The deny is left in place rather than substituted with a rule scan
        # invented here: this is an authorization surface, and fabricating a
        # matching rule would risk manufacturing an ALLOW. But it is no longer
        # SILENT. Before issue #2222 this method raised `TypeError` on the
        # construction below, which at least failed loudly; repairing only the
        # construction would have left an endpoint that refuses everyone with
        # no signal saying why.
        get_perms_fn = getattr(self.access_manager, "get_user_permissions", None)
        if not callable(get_perms_fn):
            self._warn_missing_capability(
                "get_user_permissions",
                "every API endpoint check is DENIED; no API permission rule "
                "can be consulted",
            )
            rules = []
        else:
            rules = get_perms_fn(user_context)

        allowed = any(
            rule.permission == api_permission and rule.effect == PermissionEffect.ALLOW
            for rule in rules
        )

        decision = AccessDecision(
            allowed=allowed,
            reason=(
                f"API access {'granted' if allowed else 'denied'} for "
                f"{endpoint} [{context}]"
            ),
        )

        # Emit middleware event
        if self.event_stream:
            await self._emit_access_event(
                decision, "api", user_context, endpoint, api_permission
            )

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
        #
        # `permission_rule_created` was not an AuditEventType member (issue
        # #2222; measured against the 28 that exist), and `rule_data=`/
        # `created_by=`/`rule_id=` are not declared parameters of
        # `AuditLogNode`, so they were stripped and the call died on the
        # missing `operation`. Registering a permission rule is a change to the
        # authorization configuration, which is what SYSTEM_CONFIG_CHANGED
        # names; PERMISSION_GRANTED would have been wrong, since a rule may
        # carry effect=deny.
        self._audit(
            event_type=AuditEventType.SYSTEM_CONFIG_CHANGED,
            action="permission_rule_created",
            description=(
                f"Permission rule {rule.id} registered: "
                f"{rule.effect.value} {permission} on "
                f"{rule.resource_type}:{resource_id}"
            ),
            user_id=created_by,
            resource_id=rule.id,
            severity=AuditSeverity.HIGH,
            metadata={
                "rule_id": rule.id,
                "created_by": created_by,
                "effect": rule.effect.value,
                "resource_type": rule.resource_type,
                "resource_id": resource_id,
                "role": rule.role,
                "tenant_id": rule.tenant_id,
            },
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
        self,
        decision: AccessDecision,
        resource_type: str,
        user_context: UserContext,
        resource_id: str,
        permission: Any,
    ):
        """Emit access control event to middleware event stream.

        ``resource_id`` and ``permission`` are parameters rather than reads off
        ``decision``. This method used to do ``decision.user_id``,
        ``decision.resource_id`` and ``decision.permission`` -- three fields
        ``AccessDecision`` does not have -- so wiring an event stream raised
        ``AttributeError`` on EVERY decision, including the ones whose
        construction succeeded (issue #2222; measured on ``check_node_access``,
        which delegates to the manager and never touched the broken
        constructor). Repairing only the constructors would have left this
        second failure live one line later. The caller already knows both
        values, so passing them keeps the emitted payload identical.
        """

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
                    "user_id": user_context.user_id,
                    "resource_id": resource_id,
                    "permission": (
                        permission.value if isinstance(permission, Enum) else permission
                    ),
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
            # Default deny for unknown resource types.
            #
            # This is the fail-closed branch, and until issue #2222 it could
            # not execute: it raised `TypeError` from the same rejected-kwarg
            # construction as the checks above, so the ONE path whose entire
            # job is to refuse safely was the one that could not produce a
            # refusal. A caller wrapping this in `except Exception` and
            # treating the error as "not denied" would have inverted it.
            context = _decision_context(
                user_context.user_id, resource_id, f"{resource_type}.{action}"
            )
            return AccessDecision(
                allowed=False,
                reason=f"Unknown resource type: {resource_type} [{context}]",
            )
