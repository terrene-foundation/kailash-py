"""Enhanced AccessControlManager with ABAC integration.

This module extends the existing AccessControlManager to support both
RBAC and ABAC seamlessly, maintaining backward compatibility while
adding powerful attribute-based access control features.
"""

import logging
from typing import Any, Dict, List, Optional

from kailash.access_control import (
    AccessControlManager,
    AccessDecision,
    UserContext,
    PermissionRule,
    NodePermission,
    WorkflowPermission,
    PermissionEffect,
    ConditionEvaluator
)
from kailash.access_control_abac import (
    EnhancedConditionEvaluator,
    AttributeEvaluator,
    DataMasker,
    AttributeMaskingRule,
    AttributeExpression,
    AttributeCondition,
    AttributeOperator
)

logger = logging.getLogger(__name__)


class EnhancedAccessControlManager(AccessControlManager):
    """AccessControlManager enhanced with ABAC capabilities.
    
    This class extends the base AccessControlManager to support attribute-based
    access control while maintaining full backward compatibility with existing
    RBAC rules. It seamlessly integrates both models, allowing gradual migration
    from RBAC to ABAC.
    
    New Features:
        - Attribute-based permission evaluation
        - Complex attribute expressions with AND/OR logic
        - Hierarchical attribute matching (departments, regions)
        - Security clearance levels
        - Attribute-based data masking
        - Enhanced condition evaluation
        
    Example:
        >>> # Create manager with ABAC support
        >>> acm = EnhancedAccessControlManager()
        
        >>> # Add RBAC rule (backward compatible)
        >>> acm.add_rule(PermissionRule(
        ...     id="allow_analysts",
        ...     resource_type="node",
        ...     resource_id="data_node",
        ...     permission=NodePermission.EXECUTE,
        ...     effect=PermissionEffect.ALLOW,
        ...     role="analyst"
        ... ))
        
        >>> # Add ABAC rule with attribute conditions
        >>> acm.add_rule(PermissionRule(
        ...     id="dept_access",
        ...     resource_type="node",
        ...     resource_id="sensitive_data",
        ...     permission=NodePermission.READ_OUTPUT,
        ...     effect=PermissionEffect.ALLOW,
        ...     conditions={
        ...         "type": "attribute_expression",
        ...         "value": {
        ...             "operator": "and",
        ...             "conditions": [
        ...                 {
        ...                     "attribute_path": "user.attributes.department",
        ...                     "operator": "hierarchical_match",
        ...                     "value": "engineering"
        ...                 },
        ...                 {
        ...                     "attribute_path": "user.attributes.security_clearance",
        ...                     "operator": "in",
        ...                     "value": ["secret", "top_secret"]
        ...                 }
        ...             ]
        ...         }
        ...     }
        ... ))
        
        >>> # Check access with user attributes
        >>> user = UserContext(
        ...     user_id="eng123",
        ...     tenant_id="corp",
        ...     email="engineer@corp.com",
        ...     roles=["engineer"],
        ...     attributes={
        ...         "department": "engineering.backend",
        ...         "security_clearance": "secret",
        ...         "region": "us-west"
        ...     }
        ... )
        >>> decision = acm.check_node_access(user, "sensitive_data", NodePermission.READ_OUTPUT)
        >>> decision.allowed
        True
    """
    
    def __init__(self):
        """Initialize enhanced access control manager."""
        super().__init__()
        
        # Replace condition evaluator with enhanced version
        self.condition_evaluator = EnhancedConditionEvaluator()
        
        # Add ABAC components
        self.attribute_evaluator = AttributeEvaluator()
        self.data_masker = DataMasker(self.attribute_evaluator)
        
        # Masking rules cache
        self._masking_rules: Dict[str, List[AttributeMaskingRule]] = {}
    
    def add_masking_rule(self, node_id: str, rule: AttributeMaskingRule):
        """Add attribute-based masking rule for a node.
        
        Args:
            node_id: Node to apply masking to
            rule: Masking rule with conditions
            
        Example:
            >>> rule = AttributeMaskingRule(
            ...     field_path="sensitive_field",
            ...     mask_type="partial",
            ...     condition=AttributeExpression(
            ...         operator=LogicalOperator.NOT,
            ...         conditions=[
            ...             AttributeCondition(
            ...                 attribute_path="user.attributes.department",
            ...                 operator=AttributeOperator.EQUALS,
            ...                 value="finance"
            ...             )
            ...         ]
            ...     )
            ... )
            >>> acm.add_masking_rule("finance_node", rule)
        """
        if node_id not in self._masking_rules:
            self._masking_rules[node_id] = []
        
        self._masking_rules[node_id].append(rule)
        logger.info(f"Added masking rule for node {node_id}")
    
    def apply_data_masking(
        self,
        user: UserContext,
        node_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply attribute-based data masking to node output.
        
        Args:
            user: User context with attributes
            node_id: Node that produced the data
            data: Data to potentially mask
            
        Returns:
            Masked data based on user attributes
        """
        # Get masking rules for node
        rules = self._masking_rules.get(node_id, [])
        if not rules:
            return data
        
        # Build context for evaluation
        context = {
            "user": user,
            "node_id": node_id,
            "data": data
        }
        
        # Apply masking
        return self.data_masker.apply_masking(data, rules, context)
    
    def check_node_access_with_masking(
        self,
        user: UserContext,
        node_id: str,
        permission: NodePermission,
        runtime_context: Optional[Dict[str, Any]] = None
    ) -> tuple[AccessDecision, Optional[List[AttributeMaskingRule]]]:
        """Check node access and return applicable masking rules.
        
        This method extends the standard access check to also return
        any masking rules that should be applied to the node's output.
        
        Args:
            user: User requesting access
            node_id: Node to access
            permission: Permission type requested
            runtime_context: Additional runtime context
            
        Returns:
            Tuple of (access decision, applicable masking rules)
        """
        # Standard access check
        decision = self.check_node_access(user, node_id, permission, runtime_context)
        
        # If access denied or not a read operation, no masking needed
        if not decision.allowed or permission != NodePermission.READ_OUTPUT:
            return decision, None
        
        # Get applicable masking rules
        applicable_rules = []
        context = {
            "user": user,
            "node_id": node_id,
            "runtime": runtime_context or {}
        }
        
        for rule in self._masking_rules.get(node_id, []):
            if rule.condition:
                if self.attribute_evaluator.evaluate_expression(rule.condition, context):
                    applicable_rules.append(rule)
            else:
                # No condition means always apply
                applicable_rules.append(rule)
        
        return decision, applicable_rules
    
    def evaluate_attribute_expression(
        self,
        expression: AttributeExpression,
        user: UserContext,
        runtime_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Evaluate an attribute expression for a user.
        
        Utility method for evaluating attribute expressions outside
        of permission rules, useful for application logic.
        
        Args:
            expression: Attribute expression to evaluate
            user: User context with attributes
            runtime_context: Additional runtime context
            
        Returns:
            True if expression evaluates to true
        """
        context = {
            "user": user,
            "runtime": runtime_context or {}
        }
        
        return self.attribute_evaluator.evaluate_expression(expression, context)
    
    def get_user_effective_permissions(
        self,
        user: UserContext,
        resource_type: str,
        resource_id: str
    ) -> Dict[str, bool]:
        """Get all effective permissions for a user on a resource.
        
        This method evaluates all applicable rules (RBAC and ABAC)
        to determine the complete set of permissions a user has.
        
        Args:
            user: User to check permissions for
            resource_type: Type of resource (workflow/node)
            resource_id: Specific resource ID
            
        Returns:
            Dictionary mapping permission names to allow/deny
        """
        permissions = {}
        
        # Get permission enum based on resource type
        if resource_type == "workflow":
            permission_enum = WorkflowPermission
        else:
            permission_enum = NodePermission
        
        # Check each permission type
        for permission in permission_enum:
            if resource_type == "workflow":
                decision = self.check_workflow_access(user, resource_id, permission)
            else:
                decision = self.check_node_access(user, resource_id, permission)
            
            permissions[permission.value] = decision.allowed
        
        return permissions
    
    def export_rules_for_user(
        self,
        user: UserContext,
        include_conditions: bool = True
    ) -> List[Dict[str, Any]]:
        """Export all rules that could apply to a user.
        
        Useful for debugging and auditing to understand what rules
        might affect a specific user based on their attributes.
        
        Args:
            user: User to check rules for
            include_conditions: Include condition details
            
        Returns:
            List of rules that could apply to the user
        """
        applicable_rules = []
        
        for rule in self.rules:
            # Check if rule could apply to user
            could_apply = False
            
            # Direct user match
            if rule.user_id and rule.user_id == user.user_id:
                could_apply = True
            
            # Role match
            elif rule.role and rule.role in user.roles:
                could_apply = True
            
            # Tenant match
            elif rule.tenant_id and rule.tenant_id == user.tenant_id:
                could_apply = True
            
            # No user/role/tenant means applies to all
            elif not rule.user_id and not rule.role and not rule.tenant_id:
                could_apply = True
            
            if could_apply:
                rule_dict = {
                    "id": rule.id,
                    "resource_type": rule.resource_type,
                    "resource_id": rule.resource_id,
                    "permission": rule.permission.value,
                    "effect": rule.effect.value,
                    "priority": rule.priority
                }
                
                if include_conditions and rule.conditions:
                    rule_dict["conditions"] = rule.conditions
                
                applicable_rules.append(rule_dict)
        
        return applicable_rules


# Helper function for creating attribute conditions
def create_attribute_condition(
    path: str,
    operator: str,
    value: Any,
    case_sensitive: bool = True
) -> Dict[str, Any]:
    """Create an attribute condition configuration.
    
    Helper function to create properly formatted attribute conditions
    for use in permission rules.
    
    Args:
        path: Attribute path (e.g., "user.attributes.department")
        operator: Comparison operator
        value: Value to compare against
        case_sensitive: Whether comparison is case sensitive
        
    Returns:
        Condition configuration dict
    """
    return {
        "type": "attribute_expression",
        "value": {
            "attribute_path": path,
            "operator": operator,
            "value": value,
            "case_sensitive": case_sensitive
        }
    }


def create_complex_condition(
    operator: str,
    conditions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create a complex attribute condition with logical operators.
    
    Helper function to create AND/OR/NOT conditions.
    
    Args:
        operator: Logical operator (and/or/not)
        conditions: List of conditions to combine
        
    Returns:
        Complex condition configuration dict
    """
    return {
        "type": "attribute_expression",
        "value": {
            "operator": operator,
            "conditions": conditions
        }
    }


# Export enhanced components
__all__ = [
    "EnhancedAccessControlManager",
    "create_attribute_condition",
    "create_complex_condition",
]