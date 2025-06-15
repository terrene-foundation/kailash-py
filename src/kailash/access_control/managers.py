"""Composition-based access control managers.

This module provides clean, testable access control managers using composition
instead of inheritance, solving the architectural issues with the previous design.
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Union

# Import base access control components
try:
    from kailash.access_control import (
        AccessDecision,
        NodePermission,
        PermissionRule,
        UserContext,
        WorkflowPermission,
    )
except ImportError:
    # Local definitions to handle circular import during initial setup
    from dataclasses import dataclass
    from datetime import datetime
    from enum import Enum

    class NodePermission(Enum):
        EXECUTE = "execute"
        READ_OUTPUT = "read_output"
        WRITE_INPUT = "write_input"

    class WorkflowPermission(Enum):
        VIEW = "view"
        EXECUTE = "execute"
        MODIFY = "modify"

    class PermissionEffect(Enum):
        ALLOW = "allow"
        DENY = "deny"
        CONDITIONAL = "conditional"

    @dataclass
    class UserContext:
        user_id: str
        tenant_id: str
        email: str
        roles: List[str]
        attributes: Dict[str, Any]

    @dataclass
    class AccessDecision:
        allowed: bool
        reason: str
        applied_rules: List[str]
        conditions_met: Optional[Dict[str, bool]] = None
        masked_fields: Optional[List[str]] = None

    @dataclass
    class PermissionRule:
        id: str
        resource_type: str
        resource_id: str
        permission: Union[NodePermission, WorkflowPermission]
        effect: PermissionEffect
        user_id: Optional[str] = None
        role: Optional[str] = None
        tenant_id: Optional[str] = None
        conditions: Optional[Dict[str, Any]] = None
        priority: int = 0
        expires_at: Optional[datetime] = None


from kailash.access_control.rule_evaluators import RuleEvaluator, create_rule_evaluator

logger = logging.getLogger(__name__)


class AccessControlManager:
    """Access control manager using composition pattern.

    This manager separates rule storage from rule evaluation, allowing:
    - Easy testing with mock evaluators
    - Flexible evaluation strategies (RBAC, ABAC, Hybrid)
    - Clear separation of concerns
    - No inheritance-related bugs

    Example:
        >>> # Create with hybrid evaluation (RBAC + ABAC)
        >>> manager = AccessControlManager()

        >>> # Or specify evaluation strategy
        >>> rbac_manager = AccessControlManager(strategy="rbac")
        >>> abac_manager = AccessControlManager(strategy="abac")

        >>> # Add rules
        >>> manager.add_rule(PermissionRule(...))

        >>> # Check access
        >>> decision = manager.check_node_access(user, "node_id", NodePermission.EXECUTE)
    """

    def __init__(
        self,
        rule_evaluator: Optional[RuleEvaluator] = None,
        strategy: str = "hybrid",
        enabled: bool = True,
    ):
        """Initialize access control manager.

        Args:
            rule_evaluator: Custom rule evaluator (overrides strategy)
            strategy: Evaluation strategy ('rbac', 'abac', 'hybrid')
            enabled: Whether access control is enabled
        """
        self.enabled = enabled
        self.rules: List[PermissionRule] = []

        # Use provided evaluator or create one based on strategy
        if rule_evaluator:
            self.rule_evaluator = rule_evaluator
        else:
            self.rule_evaluator = create_rule_evaluator(strategy)

        # Cache for performance
        self._cache: Dict[str, AccessDecision] = {}
        self._cache_lock = threading.Lock()

        # Audit logging
        self.audit_logger = logging.getLogger("kailash.access_control.audit")

        # Data masking for ABAC (only needed for abac/hybrid strategies)
        self._masking_rules: Dict[str, List[Any]] = {}
        if strategy in ["abac", "hybrid"]:
            self._init_abac_components()

        logger.info(
            f"Initialized AccessControlManager with {type(self.rule_evaluator).__name__}"
        )

    def _init_abac_components(self) -> None:
        """Initialize ABAC-specific components."""
        try:
            from kailash.access_control_abac import AttributeEvaluator, DataMasker

            self.attribute_evaluator = AttributeEvaluator()
            self.data_masker = DataMasker(self.attribute_evaluator)
        except ImportError:
            logger.warning("ABAC components not available, data masking disabled")
            self.attribute_evaluator = None
            self.data_masker = None

    def add_rule(self, rule: PermissionRule) -> None:
        """Add a permission rule.

        Args:
            rule: Permission rule to add
        """
        self.rules.append(rule)
        self._clear_cache()
        logger.debug(
            f"Added rule {rule.id} for {rule.resource_type}:{rule.resource_id}"
        )

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a permission rule.

        Args:
            rule_id: ID of rule to remove

        Returns:
            True if rule was found and removed
        """
        initial_count = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        removed = len(self.rules) < initial_count

        if removed:
            self._clear_cache()
            logger.debug(f"Removed rule {rule_id}")

        return removed

    def check_workflow_access(
        self,
        user: UserContext,
        workflow_id: str,
        permission: WorkflowPermission,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> AccessDecision:
        """Check if user has permission on workflow.

        Args:
            user: User requesting access
            workflow_id: Workflow to access
            permission: Permission being requested
            runtime_context: Additional runtime context

        Returns:
            AccessDecision with allow/deny and reasoning
        """
        if not self.enabled:
            return AccessDecision(
                allowed=True,
                reason="Access control disabled",
                applied_rules=[],
            )

        cache_key = f"workflow:{workflow_id}:{user.user_id}:{permission.value}"

        # Check cache (if no runtime context)
        if not runtime_context:
            with self._cache_lock:
                if cache_key in self._cache:
                    cached_decision = self._cache[cache_key]
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached_decision

        # Get applicable rules
        applicable_rules = self._get_applicable_rules(
            "workflow", workflow_id, permission
        )

        # Evaluate using configured strategy
        decision = self.rule_evaluator.evaluate_rules(
            applicable_rules,
            user,
            "workflow",
            workflow_id,
            permission,
            runtime_context or {},
        )

        # Cache decision (if no runtime context)
        if not runtime_context:
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
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> AccessDecision:
        """Check if user has permission on node.

        Args:
            user: User requesting access
            node_id: Node to access
            permission: Permission being requested
            runtime_context: Additional runtime context

        Returns:
            AccessDecision with allow/deny and reasoning
        """
        if not self.enabled:
            return AccessDecision(
                allowed=True,
                reason="Access control disabled",
                applied_rules=[],
            )

        cache_key = f"node:{node_id}:{user.user_id}:{permission.value}"

        # Check cache (if no runtime context)
        if not runtime_context:
            with self._cache_lock:
                if cache_key in self._cache:
                    cached_decision = self._cache[cache_key]
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached_decision

        # Get applicable rules
        applicable_rules = self._get_applicable_rules("node", node_id, permission)

        # Evaluate using configured strategy
        decision = self.rule_evaluator.evaluate_rules(
            applicable_rules,
            user,
            "node",
            node_id,
            permission,
            runtime_context or {},
        )

        # Cache decision (if no runtime context)
        if not runtime_context:
            with self._cache_lock:
                self._cache[cache_key] = decision

        # Audit log
        self._audit_log(user, "node", node_id, permission, decision)

        return decision

    def get_accessible_nodes(
        self, user: UserContext, workflow_id: str, permission: NodePermission
    ) -> set[str]:
        """Get all nodes user can access in a workflow.

        Args:
            user: User to check access for
            workflow_id: Workflow containing nodes
            permission: Permission type to check

        Returns:
            Set of accessible node IDs
        """
        # Get all node rules for this workflow
        node_rules = [
            rule
            for rule in self.rules
            if rule.resource_type == "node" and rule.permission == permission
        ]

        accessible = set()

        for rule in node_rules:
            decision = self.check_node_access(user, rule.resource_id, permission)
            if decision.allowed:
                accessible.add(rule.resource_id)

        return accessible

    def add_masking_rule(self, node_id: str, rule: Any) -> None:
        """Add attribute-based masking rule for a node."""
        if not hasattr(self, "data_masker") or self.data_masker is None:
            logger.warning("Data masking not available - use ABAC or hybrid strategy")
            return

        if node_id not in self._masking_rules:
            self._masking_rules[node_id] = []

        self._masking_rules[node_id].append(rule)
        logger.info(f"Added masking rule for node {node_id}")

    def apply_data_masking(
        self, user: UserContext, node_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply attribute-based data masking to node output."""
        # Check if ABAC components are available
        if not hasattr(self, "data_masker") or self.data_masker is None:
            logger.warning("Data masking not available - returning original data")
            return data

        # Get masking rules for node
        rules = self._masking_rules.get(node_id, [])
        if not rules:
            return data

        # Build context for evaluation
        context = {"user": user, "node_id": node_id, "data": data}

        # Apply masking
        return self.data_masker.apply_masking(data, rules, context)

    def supports_conditions(self) -> bool:
        """Check if current evaluator supports conditional rules.

        Returns:
            True if complex conditions are supported
        """
        return self.rule_evaluator.supports_conditions()

    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about the current evaluation strategy.

        Returns:
            Dictionary with strategy details
        """
        return {
            "evaluator_type": type(self.rule_evaluator).__name__,
            "supports_conditions": self.supports_conditions(),
            "enabled": self.enabled,
            "rule_count": len(self.rules),
        }

    def _get_applicable_rules(
        self,
        resource_type: str,
        resource_id: str,
        permission: Union[NodePermission, WorkflowPermission],
    ) -> List[PermissionRule]:
        """Get rules that apply to a specific resource and permission.

        Args:
            resource_type: Type of resource (node/workflow)
            resource_id: Specific resource ID
            permission: Permission being checked

        Returns:
            List of applicable rules
        """
        applicable_rules = []

        for rule in self.rules:
            # Check resource type, ID, and permission match
            if (
                rule.resource_type == resource_type
                and rule.resource_id == resource_id
                and rule.permission == permission
            ):

                # Check expiration
                if rule.expires_at:
                    from datetime import UTC, datetime

                    if rule.expires_at < datetime.now(UTC):
                        continue

                applicable_rules.append(rule)

        return applicable_rules

    def _clear_cache(self) -> None:
        """Clear the access decision cache."""
        with self._cache_lock:
            self._cache.clear()
        logger.debug("Cleared access control cache")

    def _audit_log(
        self,
        user: UserContext,
        resource_type: str,
        resource_id: str,
        permission: Union[NodePermission, WorkflowPermission],
        decision: AccessDecision,
    ) -> None:
        """Log access control decision for auditing.

        Args:
            user: User who made the request
            resource_type: Type of resource accessed
            resource_id: ID of resource accessed
            permission: Permission that was checked
            decision: Access control decision
        """
        self.audit_logger.info(
            "Access decision",
            extra={
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "permission": permission.value,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "applied_rules": decision.applied_rules,
                "evaluator": type(self.rule_evaluator).__name__,
            },
        )


# Export components
__all__ = [
    "AccessControlManager",
]
