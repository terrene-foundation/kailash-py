"""Access control package with composition-based architecture.

This package provides clean, testable access control components:
- Rule evaluators for RBAC, ABAC, and hybrid strategies
- Composable access control managers
- Backward compatibility with existing code
"""

import os

# Import core types first (avoiding circular imports)
import sys
from typing import Any, Dict, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import core access control components directly
import importlib.util
import os

# Load the original access_control module to avoid import conflicts
_spec = importlib.util.spec_from_file_location(
    "original_access_control",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "access_control.py"),
)
_original_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original_module)

# Import core types from original module
NodePermission = _original_module.NodePermission
WorkflowPermission = _original_module.WorkflowPermission
PermissionEffect = _original_module.PermissionEffect
PermissionRule = _original_module.PermissionRule
UserContext = _original_module.UserContext
AccessDecision = _original_module.AccessDecision
ConditionEvaluator = _original_module.ConditionEvaluator

# Import utility functions from original module
get_access_control_manager = _original_module.get_access_control_manager
set_access_control_manager = _original_module.set_access_control_manager

# Import new composition-based components
from kailash.access_control.managers import AccessControlManager  # noqa: E402
from kailash.access_control.rule_evaluators import ABACRuleEvaluator  # noqa: E402
from kailash.access_control.rule_evaluators import (  # noqa: E402
    HybridRuleEvaluator,
    RBACRuleEvaluator,
    RuleEvaluator,
    create_rule_evaluator,
)

# ABAC components are available directly from kailash.access_control_abac
# Not imported here to avoid circular import issues

# Export all components
__all__ = [
    # Core types
    "NodePermission",
    "WorkflowPermission",
    "PermissionEffect",
    "PermissionRule",
    "UserContext",
    "AccessDecision",
    "ConditionEvaluator",
    # Composition-based components
    "AccessControlManager",
    "RuleEvaluator",
    "RBACRuleEvaluator",
    "ABACRuleEvaluator",
    "HybridRuleEvaluator",
    "create_rule_evaluator",
    # ABAC components available from kailash.access_control_abac
    # Utility functions
    "get_access_control_manager",
    "set_access_control_manager",
    # ABAC helper functions
    "create_attribute_condition",
    "create_complex_condition",
]


# Helper functions for creating ABAC conditions
def create_attribute_condition(
    path: str, operator: str, value: Any, case_sensitive: bool = True
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
            "case_sensitive": case_sensitive,
        },
    }


def create_complex_condition(
    operator: str, conditions: List[Dict[str, Any]]
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
        "value": {"operator": operator, "conditions": conditions},
    }
