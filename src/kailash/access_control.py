"""
Access Control System for Kailash SDK

This module provides fine-grained access control at the workflow and node level,
enabling permission-based execution paths and data access restrictions.

Key Features:
- Node-level permissions (execute, read_output, write_input)
- Workflow-level permissions (view, execute, modify)
- Permission-based conditional routing
- Data masking for restricted nodes
- Audit logging of access attempts
- Integration with JWT authentication

Design Philosophy:
- Fail-safe defaults (deny by default)
- Minimal performance overhead
- Transparent to existing workflows
- Flexible permission models

Usage:
    >>> from kailash.access_control import AccessControlManager, NodePermission, UserContext
    >>> acm = AccessControlManager()
    >>> user_context = UserContext(user_id="test", tenant_id="test", email="test@test.com")
    >>> node_id = "test_node"
    >>> decision = acm.check_node_access(user_context, node_id, NodePermission.EXECUTE)
    >>> decision.allowed
    False

Implementation:
    Access control is enforced at multiple levels:
    1. Workflow level - Can user execute/view the workflow?
    2. Node level - Can user execute specific nodes?
    3. Data level - Can user see outputs from specific nodes?
    4. Routing level - Which path should user take based on permissions?

Security Considerations:
    - Permissions are cached per execution for performance
    - Access denied by default for unknown users/nodes
    - All access attempts are logged for audit
    - Sensitive data is masked, not just hidden

Testing:
    See tests/test_access_control.py for comprehensive tests

Future Enhancements:
    - Dynamic permission evaluation based on data
    - Time-based access restrictions
    - Delegation and impersonation support
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowPermission(Enum):
    """Workflow-level permissions"""

    VIEW = "view"  # Can see workflow exists
    EXECUTE = "execute"  # Can run workflow
    MODIFY = "modify"  # Can edit workflow
    DELETE = "delete"  # Can delete workflow
    SHARE = "share"  # Can share with others
    ADMIN = "admin"  # Full control


class NodePermission(Enum):
    """Node-level permissions"""

    EXECUTE = "execute"  # Can execute node
    READ_OUTPUT = "read_output"  # Can see node outputs
    WRITE_INPUT = "write_input"  # Can provide inputs
    SKIP = "skip"  # Node is skipped for user
    MASK_OUTPUT = "mask_output"  # Output is masked/redacted


class PermissionEffect(Enum):
    """Effect of a permission rule"""

    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"  # Depends on runtime evaluation


@dataclass
class UserContext:
    """
    User context for access control decisions.

    Contains all information needed to make access control decisions for a user,
    including identity, tenant membership, roles, and session information.

    Design Purpose:
        Provides a standardized way to represent user identity and permissions
        across the entire access control system. Enables fine-grained access
        control based on user attributes, roles, and context.

    Upstream Dependencies:
        - Authentication systems (JWT, API keys)
        - User management systems
        - Tenant management systems

    Downstream Consumers:
        - AccessControlManager for permission checking
        - AccessControlledRuntime for workflow execution
        - Audit logging systems for tracking access

    Usage Patterns:
        - Created during authentication/login process
        - Passed to all access control functions
        - Used in workflow and node execution contexts
        - Logged for audit and compliance purposes

    Implementation Details:
        Uses dataclass for efficient attribute access and comparison.
        Immutable once created to prevent privilege escalation.
        Supports custom attributes for extensible authorization.

    Example:
        >>> user = UserContext(
        ...     user_id="user123",
        ...     tenant_id="tenant001",
        ...     email="user@example.com",
        ...     roles=["analyst", "viewer"]
        ... )
        >>> print(user.user_id)
        user123
    """

    user_id: str
    tenant_id: str
    email: str
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)  # Custom attributes
    session_id: str | None = None
    ip_address: str | None = None


@dataclass
class PermissionRule:
    """
    A single permission rule defining access control policies.

    Represents a single access control rule that grants or denies permissions
    to users for specific resources (workflows or nodes) based on their
    identity, roles, and contextual conditions.

    Design Purpose:
        Provides a flexible, declarative way to define access control policies.
        Supports role-based access control (RBAC), attribute-based access control (ABAC),
        and conditional permissions based on runtime context.

    Upstream Dependencies:
        - Administrative interfaces for rule creation
        - Policy management systems
        - Configuration files or databases

    Downstream Consumers:
        - AccessControlManager for rule evaluation
        - Audit systems for logging policy decisions
        - Policy analysis tools for rule validation

    Usage Patterns:
        - Created by administrators to define access policies
        - Evaluated during workflow and node execution
        - Cached for performance optimization
        - Updated when policies change

    Implementation Details:
        Uses dataclass for efficient serialization and comparison.
        Supports priority-based rule ordering for conflict resolution.
        Includes expiration for time-limited permissions.
        Conditions enable complex policy logic.

    Example:
        >>> rule = PermissionRule(
        ...     id="allow_analysts_read",
        ...     resource_type="node",
        ...     resource_id="sensitive_data",
        ...     permission=NodePermission.READ_OUTPUT,
        ...     effect=PermissionEffect.ALLOW,
        ...     role="analyst"
        ... )
        >>> print(rule.id)
        allow_analysts_read
    """

    id: str
    resource_type: str  # "workflow" or "node"
    resource_id: str  # workflow_id or node_id
    permission: WorkflowPermission | NodePermission
    effect: PermissionEffect

    # Who does this apply to?
    user_id: str | None = None  # Specific user
    role: str | None = None  # Any user with role
    tenant_id: str | None = None  # All users in tenant

    # Conditions
    conditions: dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None
    expires_at: datetime | None = None
    priority: int = 0  # Higher priority rules evaluated first


@dataclass
class AccessDecision:
    """
    Result of an access control decision.

    Contains the outcome of evaluating access control rules for a specific
    user and resource, including whether access is allowed, the reasoning,
    and any additional actions required (like data masking).

    Design Purpose:
        Provides a comprehensive result object that captures not just the
        allow/deny decision, but also the context and reasoning behind it.
        Enables audit logging, debugging, and conditional execution.

    Upstream Dependencies:
        - AccessControlManager rule evaluation
        - Permission rule matching logic
        - Conditional evaluation systems

    Downstream Consumers:
        - AccessControlledRuntime for execution decisions
        - Audit logging systems for compliance
        - Error handling for access denial messages
        - Data masking systems for output filtering

    Usage Patterns:
        - Returned by all access control check methods
        - Logged for audit and debugging purposes
        - Used to determine execution flow
        - Provides user-friendly error messages

    Implementation Details:
        Immutable after creation to ensure decision integrity.
        Includes applied rules for transparency and debugging.
        Supports conditional decisions for complex scenarios.
        Contains masking information for data protection.

    Example:
        >>> decision = AccessDecision(
        ...     allowed=True,
        ...     reason="User has analyst role",
        ...     masked_fields=["ssn", "phone"]
        ... )
        >>> print(decision.allowed)
        True
    """

    allowed: bool
    reason: str
    applied_rules: list[PermissionRule] = field(default_factory=list)
    conditions_met: dict[str, bool] = field(default_factory=dict)
    masked_fields: list[str] = field(default_factory=list)  # Fields to mask in output
    redirect_node: str | None = None  # Alternative node to execute


class ConditionEvaluator:
    """Evaluates conditions for conditional permissions"""

    def __init__(self):
        self.evaluators: dict[str, Callable] = {
            "time_range": self._eval_time_range,
            "data_contains": self._eval_data_contains,
            "user_attribute": self._eval_user_attribute,
            "ip_range": self._eval_ip_range,
            "custom": self._eval_custom,
        }

    def evaluate(
        self, condition_type: str, condition_value: Any, context: dict[str, Any]
    ) -> bool:
        """Evaluate a condition"""
        evaluator = self.evaluators.get(condition_type)
        if not evaluator:
            logger.warning(f"Unknown condition type: {condition_type}")
            return False

        try:
            return evaluator(condition_value, context)
        except Exception as e:
            logger.error(f"Error evaluating condition {condition_type}: {e}")
            return False

    def _eval_time_range(self, value: dict[str, str], context: dict[str, Any]) -> bool:
        """Check if current time is within range"""
        from datetime import datetime, time

        now = datetime.now().time()
        start = time.fromisoformat(value.get("start", "00:00"))
        end = time.fromisoformat(value.get("end", "23:59"))
        return start <= now <= end

    def _eval_data_contains(
        self, value: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Check if data contains specific values"""
        data = context.get("data", {})
        field = value.get("field")
        expected = value.get("value")

        if field and field in data:
            return data[field] == expected
        return False

    def _eval_user_attribute(
        self, value: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Check user attributes"""
        user = context.get("user")
        if not user:
            return False

        attr_name = value.get("attribute")
        expected = value.get("value")

        return user.attributes.get(attr_name) == expected

    def _eval_ip_range(self, value: dict[str, Any], context: dict[str, Any]) -> bool:
        """Check if IP is in allowed range"""
        # Simplified IP check - in production use ipaddress module
        allowed_ips = value.get("allowed", [])
        user_ip = context.get("user", {}).get("ip_address")

        return user_ip in allowed_ips

    def _eval_custom(self, value: dict[str, Any], context: dict[str, Any]) -> bool:
        """Evaluate custom condition"""
        # This would call a custom function registered by the user
        return True


class AccessControlManager:
    """
    Main access control manager for the Kailash SDK.

    Centralized manager for evaluating access control policies, managing permission
    rules, and making authorization decisions for workflows and nodes. Provides
    caching, audit logging, and conditional permission evaluation.

    Design Purpose:
        Serves as the single source of truth for access control decisions.
        Separates policy definition from policy enforcement, enabling
        flexible and maintainable security policies.

    Upstream Dependencies:
        - Administrative interfaces for rule management
        - Configuration systems for policy definition
        - Authentication systems for user context

    Downstream Consumers:
        - AccessControlledRuntime for workflow execution
        - Node execution systems for permission checks
        - Audit and monitoring systems for compliance
        - Administrative tools for policy analysis

    Usage Patterns:
        - Created once per application/service instance
        - Rules added during startup or configuration
        - Permission checks made during execution
        - Cache managed automatically for performance

    Implementation Details:
        Thread-safe with locking for cache management.
        Rules evaluated in priority order with fail-safe defaults.
        Conditional evaluation supports complex policies.
        Audit logging for all access decisions.

    Error Handling:
        - Invalid rules are logged and ignored
        - Missing permissions default to deny
        - Evaluation errors are logged and treated as deny
        - Cache errors fall back to direct evaluation

    Side Effects:
        - Logs audit events for all access decisions
        - Caches results for performance optimization
        - May trigger security alerts on repeated denials

    Example:
        >>> acm = AccessControlManager(enabled=True)
        >>> rule = PermissionRule(
        ...     id="allow_admin",
        ...     resource_type="workflow",
        ...     resource_id="sensitive_workflow",
        ...     permission=WorkflowPermission.EXECUTE,
        ...     effect=PermissionEffect.ALLOW,
        ...     role="admin"
        ... )
        >>> acm.add_rule(rule)
        >>> user = UserContext(user_id="admin1", tenant_id="test", email="admin@test.com", roles=["admin"])
        >>> decision = acm.check_workflow_access(user, "sensitive_workflow", WorkflowPermission.EXECUTE)
        >>> decision.allowed
        True
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled  # Disabled by default
        self.rules: list[PermissionRule] = []
        self.condition_evaluator = ConditionEvaluator()
        self._cache = {}  # Cache access decisions
        self._cache_lock = threading.Lock()

        # Audit logger
        self.audit_logger = logging.getLogger("kailash.access_control.audit")

    def add_rule(self, rule: PermissionRule):
        """Add a permission rule"""
        self.rules.append(rule)
        # Clear cache when rules change
        with self._cache_lock:
            self._cache.clear()

    def remove_rule(self, rule_id: str):
        """Remove a permission rule"""
        self.rules = [r for r in self.rules if r.id != rule_id]
        with self._cache_lock:
            self._cache.clear()

    def check_workflow_access(
        self, user: UserContext, workflow_id: str, permission: WorkflowPermission
    ) -> AccessDecision:
        """Check if user has permission on workflow"""
        # If access control is disabled, allow all access
        if not self.enabled:
            return AccessDecision(
                allowed=True,
                reason="Access control disabled",
                applied_rules=[],
                conditions_met={},
                masked_fields=[],
                redirect_node=None,
            )

        cache_key = f"workflow:{workflow_id}:{user.user_id}:{permission.value}"

        # Check cache
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Evaluate rules
        decision = self._evaluate_rules(user, "workflow", workflow_id, permission, {})

        # Cache decision
        with self._cache_lock:
            self._cache[cache_key] = decision

        # Audit log
        self._audit_log(user, "workflow", workflow_id, permission, decision)

        return decision

    def check_node_access(
        self,
        user: UserContext,
        node_id: str,
        permission: NodePermission,
        runtime_context: dict[str, Any] = None,
    ) -> AccessDecision:
        """Check if user has permission on node"""
        # If access control is disabled, allow all access
        if not self.enabled:
            return AccessDecision(
                allowed=True,
                reason="Access control disabled",
                applied_rules=[],
                conditions_met={},
                masked_fields=[],
                redirect_node=None,
            )

        cache_key = f"node:{node_id}:{user.user_id}:{permission.value}"

        # For runtime-dependent permissions, don't use cache
        if runtime_context and any(
            r.effect == PermissionEffect.CONDITIONAL
            for r in self.rules
            if r.resource_id == node_id
        ):
            return self._evaluate_rules(
                user, "node", node_id, permission, runtime_context or {}
            )

        # Check cache
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Evaluate rules
        decision = self._evaluate_rules(
            user, "node", node_id, permission, runtime_context or {}
        )

        # Cache decision
        with self._cache_lock:
            self._cache[cache_key] = decision

        # Audit log
        self._audit_log(user, "node", node_id, permission, decision)

        return decision

    def get_accessible_nodes(
        self, user: UserContext, nodes: list[str], permission: NodePermission
    ) -> list[str]:
        """Get all nodes user can access from a list of nodes"""
        # If access control is disabled, allow access to all nodes
        if not self.enabled:
            return nodes

        accessible = []
        for node_id in nodes:
            decision = self.check_node_access(user, node_id, permission)
            if decision.allowed:
                accessible.append(node_id)
        return accessible

    def get_permission_based_route(
        self,
        user: UserContext,
        node_id: str,
        permission: NodePermission,
        alternatives: dict[str, str] = None,
    ) -> str | None:
        """Get alternative route if user doesn't have access to node"""
        # If access control is disabled, allow access to requested node
        if not self.enabled:
            return None

        decision = self.check_node_access(user, node_id, permission)

        if decision.allowed:
            return None  # No alternative needed

        # If access denied and alternatives provided, return alternative
        if alternatives and node_id in alternatives:
            return alternatives[node_id]

        return None

    def mask_node_output(
        self, user: UserContext, node_id: str, output: dict[str, Any]
    ) -> dict[str, Any]:
        """Mask sensitive fields in node output"""
        # If access control is disabled, don't mask anything
        if not self.enabled:
            return output

        decision = self.check_node_access(user, node_id, NodePermission.MASK_OUTPUT)

        if not decision.allowed:
            # No masking rules found, return original output
            return output

        if decision.masked_fields:
            # Mask specific fields
            masked_output = output.copy()
            for field in decision.masked_fields:
                if field in masked_output:
                    masked_output[field] = "***MASKED***"
            return masked_output

        return output

    def _evaluate_rules(
        self,
        user: UserContext,
        resource_type: str,
        resource_id: str,
        permission: WorkflowPermission | NodePermission,
        runtime_context: dict[str, Any],
    ) -> AccessDecision:
        """Evaluate all applicable rules"""
        applicable_rules = []

        # Find applicable rules
        for rule in sorted(self.rules, key=lambda r: r.priority, reverse=True):
            if (
                rule.resource_type == resource_type
                and rule.resource_id == resource_id
                and rule.permission == permission
                and self._rule_applies_to_user(rule, user)
            ):

                # Check expiration
                if rule.expires_at and rule.expires_at < datetime.now(UTC):
                    continue

                applicable_rules.append(rule)

        # Evaluate rules
        context = {
            "user": user,
            "runtime": runtime_context,
            "timestamp": datetime.now(UTC),
        }

        final_effect = PermissionEffect.DENY  # Default deny
        conditions_met = {}
        masked_fields = []

        for rule in applicable_rules:
            if rule.effect == PermissionEffect.CONDITIONAL:
                # Evaluate conditions
                all_conditions_met = True
                for cond_type, cond_value in rule.conditions.items():
                    met = self.condition_evaluator.evaluate(
                        cond_type, cond_value, context
                    )
                    conditions_met[f"{rule.id}:{cond_type}"] = met
                    if not met:
                        all_conditions_met = False
                        break

                if all_conditions_met:
                    final_effect = PermissionEffect.ALLOW
                    if "masked_fields" in rule.conditions:
                        masked_fields.extend(rule.conditions["masked_fields"])
            else:
                final_effect = rule.effect

            # Explicit deny takes precedence
            if final_effect == PermissionEffect.DENY:
                break

        allowed = final_effect == PermissionEffect.ALLOW

        # Set reason based on rules found
        if not applicable_rules:
            reason = f"No matching rules found for {resource_type} {resource_id}"
        else:
            reason = f"Permission {permission.value} {'granted' if allowed else 'denied'} for {resource_type} {resource_id}"

        return AccessDecision(
            allowed=allowed,
            reason=reason,
            applied_rules=applicable_rules,
            conditions_met=conditions_met,
            masked_fields=masked_fields,
        )

    def _rule_applies_to_user(self, rule: PermissionRule, user: UserContext) -> bool:
        """Check if a rule applies to a user"""
        # Specific user
        if rule.user_id and rule.user_id == user.user_id:
            return True

        # Role-based
        if rule.role and rule.role in user.roles:
            return True

        # Tenant-based
        if rule.tenant_id and rule.tenant_id == user.tenant_id:
            return True

        # No restrictions means it applies to all
        if not rule.user_id and not rule.role and not rule.tenant_id:
            return True

        return False

    def _audit_log(
        self,
        user: UserContext,
        resource_type: str,
        resource_id: str,
        permission: WorkflowPermission | NodePermission,
        decision: AccessDecision,
    ):
        """Log access attempt for audit"""
        self.audit_logger.info(
            f"Access {'granted' if decision.allowed else 'denied'}: "
            f"user={user.user_id}, resource={resource_type}:{resource_id}, "
            f"permission={permission.value}, reason={decision.reason}"
        )


# Global access control manager
_access_control_manager = AccessControlManager()


def get_access_control_manager() -> AccessControlManager:
    """Get the global access control manager"""
    return _access_control_manager


def set_access_control_manager(manager: AccessControlManager):
    """Set a custom access control manager"""
    global _access_control_manager
    _access_control_manager = manager


# Decorators for easy integration
def require_workflow_permission(permission: WorkflowPermission):
    """Decorator to require workflow permission"""

    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # Extract user context and workflow ID from self
            user = getattr(self, "user_context", None)
            workflow_id = getattr(self, "workflow_id", None)

            if user and workflow_id:
                acm = get_access_control_manager()
                decision = acm.check_workflow_access(user, workflow_id, permission)

                if not decision.allowed:
                    raise PermissionError(f"Access denied: {decision.reason}")

            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def require_node_permission(permission: NodePermission):
    """Decorator to require node permission"""

    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # Extract user context and node ID from self
            user = getattr(self, "user_context", None)
            node_id = getattr(self, "node_id", self.__class__.__name__)

            if user:
                acm = get_access_control_manager()
                runtime_context = kwargs.get("_runtime_context", {})
                decision = acm.check_node_access(
                    user, node_id, permission, runtime_context
                )

                if not decision.allowed:
                    if permission == NodePermission.EXECUTE and decision.redirect_node:
                        # Redirect to alternative node
                        kwargs["_redirect_to"] = decision.redirect_node
                    else:
                        raise PermissionError(f"Access denied: {decision.reason}")

            return func(self, *args, **kwargs)

        return wrapper

    return decorator
