"""Rule evaluator interfaces and implementations for access control.

This module provides a composition-based approach to access control rule evaluation,
replacing the problematic inheritance pattern with clear, testable interfaces.
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Union

# Import base access control components - use absolute imports to avoid circular import
try:
    from kailash.access_control import (
        AccessDecision,
        NodePermission,
        PermissionEffect,
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


logger = logging.getLogger(__name__)


class RuleEvaluator(ABC):
    """Abstract base class for rule evaluation strategies."""

    @abstractmethod
    def evaluate_rules(
        self,
        rules: List[PermissionRule],
        user: UserContext,
        resource_type: str,
        resource_id: str,
        permission: Union[NodePermission, WorkflowPermission],
        runtime_context: Dict[str, Any],
    ) -> AccessDecision:
        """Evaluate a set of rules for a user's access request.

        Args:
            rules: List of applicable permission rules
            user: User making the request
            resource_type: Type of resource (node/workflow)
            resource_id: Specific resource identifier
            permission: Permission being requested
            runtime_context: Additional runtime context

        Returns:
            AccessDecision with allow/deny and reasoning
        """
        pass

    @abstractmethod
    def supports_conditions(self) -> bool:
        """Return whether this evaluator supports conditional rules."""
        pass


class RBACRuleEvaluator(RuleEvaluator):
    """Role-Based Access Control rule evaluator.

    This evaluator handles traditional RBAC rules based on:
    - User roles
    - Direct user assignments
    - Tenant-based permissions
    """

    def __init__(self):
        """Initialize RBAC evaluator."""
        self.logger = logging.getLogger(f"{__name__}.RBACRuleEvaluator")

    def evaluate_rules(
        self,
        rules: List[PermissionRule],
        user: UserContext,
        resource_type: str,
        resource_id: str,
        permission: Union[NodePermission, WorkflowPermission],
        runtime_context: Dict[str, Any],
    ) -> AccessDecision:
        """Evaluate RBAC rules."""
        # Filter applicable rules (only those that apply to this user)
        applicable_rules = [
            rule for rule in rules if self._rule_applies_to_user(rule, user)
        ]

        if not applicable_rules:
            return AccessDecision(
                allowed=False,
                reason="No applicable RBAC rules found",
                applied_rules=[],
            )

        # Sort by priority (higher first)
        applicable_rules.sort(key=lambda r: r.priority, reverse=True)

        # Evaluate rules in priority order
        for rule in applicable_rules:
            # RBAC doesn't support complex conditions
            if rule.conditions:
                self.logger.warning(
                    f"RBAC evaluator ignoring conditions in rule {rule.id}"
                )

            # Apply effect
            if rule.effect == PermissionEffect.ALLOW:
                return AccessDecision(
                    allowed=True,
                    reason=f"RBAC rule {rule.id} granted access",
                    applied_rules=[rule.id],
                )
            elif rule.effect == PermissionEffect.DENY:
                return AccessDecision(
                    allowed=False,
                    reason=f"RBAC rule {rule.id} denied access",
                    applied_rules=[rule.id],
                )

        # Default deny
        return AccessDecision(
            allowed=False,
            reason="No matching RBAC allow rules",
            applied_rules=[rule.id for rule in applicable_rules],
        )

    def supports_conditions(self) -> bool:
        """RBAC evaluator does not support complex conditions."""
        return False

    def _rule_applies_to_user(self, rule: PermissionRule, user: UserContext) -> bool:
        """Check if a rule applies to a user based on RBAC criteria."""
        # Direct user assignment
        if rule.user_id and rule.user_id == user.user_id:
            return True

        # Role-based assignment
        if rule.role and rule.role in user.roles:
            return True

        # Tenant-based assignment
        if rule.tenant_id and rule.tenant_id == user.tenant_id:
            return True

        # No restrictions means applies to all
        if not rule.user_id and not rule.role and not rule.tenant_id:
            return True

        return False


class ABACRuleEvaluator(RuleEvaluator):
    """Attribute-Based Access Control rule evaluator.

    This evaluator handles advanced ABAC rules with:
    - Complex attribute expressions
    - Dynamic condition evaluation
    - Hierarchical attribute matching
    """

    def __init__(self):
        """Initialize ABAC evaluator."""
        self.logger = logging.getLogger(f"{__name__}.ABACRuleEvaluator")
        # Import here to avoid circular dependencies
        from kailash.access_control_abac import EnhancedConditionEvaluator

        self.condition_evaluator = EnhancedConditionEvaluator()

    def evaluate_rules(
        self,
        rules: List[PermissionRule],
        user: UserContext,
        resource_type: str,
        resource_id: str,
        permission: Union[NodePermission, WorkflowPermission],
        runtime_context: Dict[str, Any],
    ) -> AccessDecision:
        """Evaluate ABAC rules with complex attribute conditions."""
        # Build evaluation context
        context = self._build_context(user, runtime_context)

        # Filter applicable rules (basic RBAC filtering + condition evaluation)
        applicable_rules = []
        for rule in rules:
            # First check basic RBAC criteria
            if not self._rule_applies_to_user(rule, user):
                continue

            applicable_rules.append(rule)

        if not applicable_rules:
            return AccessDecision(
                allowed=False,
                reason="No applicable ABAC rules found",
                applied_rules=[],
            )

        # Sort by priority (higher first)
        applicable_rules.sort(key=lambda r: r.priority, reverse=True)

        # Evaluate rules with conditions
        for rule in applicable_rules:
            if rule.conditions:
                try:
                    # Evaluate ABAC conditions
                    cond_type = rule.conditions.get("type", "")
                    cond_value = rule.conditions.get("value", {})

                    result = self.condition_evaluator.evaluate(
                        cond_type, cond_value, context
                    )

                    if result:
                        # Conditions met - apply rule effect
                        if rule.effect == PermissionEffect.ALLOW:
                            return AccessDecision(
                                allowed=True,
                                reason=f"ABAC rule {rule.id} granted access",
                                applied_rules=[rule.id],
                            )
                        elif rule.effect == PermissionEffect.DENY:
                            return AccessDecision(
                                allowed=False,
                                reason=f"ABAC rule {rule.id} denied access",
                                applied_rules=[rule.id],
                            )
                except Exception as e:
                    self.logger.warning(f"Error evaluating ABAC rule {rule.id}: {e}")
                    continue
            else:
                # No conditions - basic RBAC-style rule
                if rule.effect == PermissionEffect.ALLOW:
                    return AccessDecision(
                        allowed=True,
                        reason=f"ABAC rule {rule.id} granted access (no conditions)",
                        applied_rules=[rule.id],
                    )
                elif rule.effect == PermissionEffect.DENY:
                    return AccessDecision(
                        allowed=False,
                        reason=f"ABAC rule {rule.id} denied access (no conditions)",
                        applied_rules=[rule.id],
                    )

        # Default deny
        return AccessDecision(
            allowed=False,
            reason="No matching ABAC allow rules",
            applied_rules=[rule.id for rule in applicable_rules],
        )

    def supports_conditions(self) -> bool:
        """ABAC evaluator fully supports complex conditions."""
        return True

    def _rule_applies_to_user(self, rule: PermissionRule, user: UserContext) -> bool:
        """Check if a rule applies to a user (same as RBAC for basic filtering)."""
        # Direct user assignment
        if rule.user_id and rule.user_id == user.user_id:
            return True

        # Role-based assignment
        if rule.role and rule.role in user.roles:
            return True

        # Tenant-based assignment
        if rule.tenant_id and rule.tenant_id == user.tenant_id:
            return True

        # No restrictions means applies to all
        if not rule.user_id and not rule.role and not rule.tenant_id:
            return True

        return False

    def _build_context(
        self, user: UserContext, runtime_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build evaluation context for ABAC."""
        now = datetime.now(UTC)
        context = {
            "user": {
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "email": user.email,
                "roles": user.roles,
                "attributes": user.attributes,
            },
            "runtime": runtime_context,
            "timestamp": now,
        }
        return context


class HybridRuleEvaluator(RuleEvaluator):
    """Hybrid evaluator that combines RBAC and ABAC evaluation.

    This evaluator:
    1. Uses RBAC for basic rules without conditions
    2. Uses ABAC for complex conditional rules
    3. Provides seamless transition between evaluation strategies
    """

    def __init__(self):
        """Initialize hybrid evaluator with both RBAC and ABAC."""
        self.rbac_evaluator = RBACRuleEvaluator()
        self.abac_evaluator = ABACRuleEvaluator()
        self.logger = logging.getLogger(f"{__name__}.HybridRuleEvaluator")

    def evaluate_rules(
        self,
        rules: List[PermissionRule],
        user: UserContext,
        resource_type: str,
        resource_id: str,
        permission: Union[NodePermission, WorkflowPermission],
        runtime_context: Dict[str, Any],
    ) -> AccessDecision:
        """Evaluate rules using appropriate strategy based on rule complexity."""
        # Separate rules by complexity
        simple_rules = [rule for rule in rules if not rule.conditions]
        complex_rules = [rule for rule in rules if rule.conditions]

        # Track all decisions for final reasoning
        all_decisions = []

        # First evaluate complex ABAC rules (higher precedence)
        if complex_rules:
            abac_decision = self.abac_evaluator.evaluate_rules(
                complex_rules,
                user,
                resource_type,
                resource_id,
                permission,
                runtime_context,
            )
            all_decisions.append(("ABAC", abac_decision))

            # If ABAC explicitly allows or denies, use that decision
            if abac_decision.allowed:
                return abac_decision
            elif any("denied access" in abac_decision.reason for _ in [abac_decision]):
                return abac_decision

        # Then evaluate simple RBAC rules
        if simple_rules:
            rbac_decision = self.rbac_evaluator.evaluate_rules(
                simple_rules,
                user,
                resource_type,
                resource_id,
                permission,
                runtime_context,
            )
            all_decisions.append(("RBAC", rbac_decision))

            if rbac_decision.allowed:
                return rbac_decision

        # Combine reasoning from all evaluations
        combined_reason = "; ".join(
            [f"{eval_type}: {decision.reason}" for eval_type, decision in all_decisions]
        )

        combined_applied_rules = [
            rule_id
            for _, decision in all_decisions
            for rule_id in decision.applied_rules
        ]

        return AccessDecision(
            allowed=False,
            reason=f"Hybrid evaluation - {combined_reason or 'No applicable rules'}",
            applied_rules=combined_applied_rules,
        )

    def supports_conditions(self) -> bool:
        """Hybrid evaluator supports conditions via ABAC component."""
        return True


# Factory function for easy evaluator creation
def create_rule_evaluator(strategy: str = "hybrid") -> RuleEvaluator:
    """Create a rule evaluator based on strategy.

    Args:
        strategy: One of 'rbac', 'abac', or 'hybrid'

    Returns:
        Appropriate RuleEvaluator instance

    Raises:
        ValueError: If strategy is not recognized
    """
    strategy = strategy.lower()

    if strategy == "rbac":
        return RBACRuleEvaluator()
    elif strategy == "abac":
        return ABACRuleEvaluator()
    elif strategy == "hybrid":
        return HybridRuleEvaluator()
    else:
        raise ValueError(
            f"Unknown strategy: {strategy}. Use 'rbac', 'abac', or 'hybrid'"
        )


# Export components
__all__ = [
    "RuleEvaluator",
    "RBACRuleEvaluator",
    "ABACRuleEvaluator",
    "HybridRuleEvaluator",
    "create_rule_evaluator",
]
