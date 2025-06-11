"""Enhanced ABAC (Attribute-Based Access Control) extensions for Kailash SDK.

This module extends the existing access control system with sophisticated
attribute-based access control capabilities, enabling fine-grained permissions
based on user attributes, resource attributes, and environmental context.

Key Features:
- Hierarchical attribute matching (department trees, security levels)
- Complex attribute expressions with AND/OR logic
- Attribute-based data masking and transformation
- Dynamic permission evaluation based on runtime attributes
- Backward compatible with existing RBAC rules
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from kailash.access_control import (
    UserContext,
    PermissionRule,
    AccessDecision,
    ConditionEvaluator,
    NodePermission,
    WorkflowPermission,
    PermissionEffect
)


class AttributeOperator(Enum):
    """Operators for attribute comparisons."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_OR_EQUAL = "less_or_equal"
    MATCHES = "matches"  # Regex match
    HIERARCHICAL_MATCH = "hierarchical_match"  # For department trees


class LogicalOperator(Enum):
    """Logical operators for combining conditions."""
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class AttributeCondition:
    """Single attribute condition for ABAC evaluation."""
    attribute_path: str  # Dot notation path e.g., "user.department.level"
    operator: AttributeOperator
    value: Any
    case_sensitive: bool = True
    
    def __post_init__(self):
        """Validate condition."""
        if not self.attribute_path:
            raise ValueError("attribute_path cannot be empty")


@dataclass
class AttributeExpression:
    """Complex attribute expression with logical operators."""
    operator: LogicalOperator
    conditions: List[Union[AttributeCondition, "AttributeExpression"]]
    
    def __post_init__(self):
        """Validate expression."""
        if not self.conditions:
            raise ValueError("conditions cannot be empty")
        if self.operator == LogicalOperator.NOT and len(self.conditions) != 1:
            raise ValueError("NOT operator requires exactly one condition")


@dataclass
class AttributeMaskingRule:
    """Rule for attribute-based data masking."""
    field_path: str  # Field to mask in output
    mask_type: str  # "redact", "partial", "hash", "replace"
    mask_value: Optional[Any] = None  # Replacement value for "replace" type
    condition: Optional[AttributeExpression] = None  # When to apply masking


class AttributeEvaluator:
    """Enhanced attribute evaluator for ABAC."""
    
    def __init__(self):
        """Initialize evaluator with operator handlers."""
        self.operators = {
            AttributeOperator.EQUALS: self._eval_equals,
            AttributeOperator.NOT_EQUALS: self._eval_not_equals,
            AttributeOperator.CONTAINS: self._eval_contains,
            AttributeOperator.NOT_CONTAINS: self._eval_not_contains,
            AttributeOperator.IN: self._eval_in,
            AttributeOperator.NOT_IN: self._eval_not_in,
            AttributeOperator.GREATER_THAN: self._eval_greater_than,
            AttributeOperator.LESS_THAN: self._eval_less_than,
            AttributeOperator.GREATER_OR_EQUAL: self._eval_greater_or_equal,
            AttributeOperator.LESS_OR_EQUAL: self._eval_less_or_equal,
            AttributeOperator.MATCHES: self._eval_matches,
            AttributeOperator.HIERARCHICAL_MATCH: self._eval_hierarchical_match,
        }
    
    def evaluate_expression(
        self,
        expression: Union[AttributeCondition, AttributeExpression],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate an attribute expression."""
        if isinstance(expression, AttributeCondition):
            return self._evaluate_condition(expression, context)
        elif isinstance(expression, AttributeExpression):
            return self._evaluate_logical_expression(expression, context)
        else:
            raise ValueError(f"Unknown expression type: {type(expression)}")
    
    def _evaluate_condition(
        self,
        condition: AttributeCondition,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate a single attribute condition."""
        # Extract value from context using attribute path
        value = self._extract_value(condition.attribute_path, context)
        
        # Get operator handler
        operator_func = self.operators.get(condition.operator)
        if not operator_func:
            raise ValueError(f"Unknown operator: {condition.operator}")
        
        # Evaluate condition
        return operator_func(value, condition.value, condition.case_sensitive)
    
    def _evaluate_logical_expression(
        self,
        expression: AttributeExpression,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate a logical expression."""
        if expression.operator == LogicalOperator.AND:
            return all(
                self.evaluate_expression(cond, context)
                for cond in expression.conditions
            )
        elif expression.operator == LogicalOperator.OR:
            return any(
                self.evaluate_expression(cond, context)
                for cond in expression.conditions
            )
        elif expression.operator == LogicalOperator.NOT:
            return not self.evaluate_expression(expression.conditions[0], context)
        else:
            raise ValueError(f"Unknown logical operator: {expression.operator}")
    
    def _extract_value(self, path: str, context: Dict[str, Any]) -> Any:
        """Extract value from context using dot notation path."""
        parts = path.split(".")
        value = context
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
            
            if value is None:
                return None
        
        return value
    
    # Operator implementations
    def _eval_equals(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate equals operator."""
        if not case_sensitive and isinstance(value, str) and isinstance(expected, str):
            return value.lower() == expected.lower()
        return value == expected
    
    def _eval_not_equals(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate not equals operator."""
        return not self._eval_equals(value, expected, case_sensitive)
    
    def _eval_contains(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate contains operator."""
        if value is None:
            return False
        
        if isinstance(value, (list, set, tuple)):
            return expected in value
        elif isinstance(value, str) and isinstance(expected, str):
            if not case_sensitive:
                return expected.lower() in value.lower()
            return expected in value
        elif isinstance(value, dict):
            return expected in value
        
        return False
    
    def _eval_not_contains(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate not contains operator."""
        return not self._eval_contains(value, expected, case_sensitive)
    
    def _eval_in(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate in operator."""
        if not isinstance(expected, (list, set, tuple)):
            return False
        
        if not case_sensitive and isinstance(value, str):
            expected_lower = [e.lower() if isinstance(e, str) else e for e in expected]
            return value.lower() in expected_lower
        
        return value in expected
    
    def _eval_not_in(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate not in operator."""
        return not self._eval_in(value, expected, case_sensitive)
    
    def _eval_greater_than(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate greater than operator."""
        try:
            return value > expected
        except TypeError:
            return False
    
    def _eval_less_than(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate less than operator."""
        try:
            return value < expected
        except TypeError:
            return False
    
    def _eval_greater_or_equal(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate greater or equal operator."""
        try:
            return value >= expected
        except TypeError:
            return False
    
    def _eval_less_or_equal(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate less or equal operator."""
        try:
            return value <= expected
        except TypeError:
            return False
    
    def _eval_matches(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate regex match operator."""
        if not isinstance(value, str) or not isinstance(expected, str):
            return False
        
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            return bool(re.match(expected, value, flags))
        except re.error:
            return False
    
    def _eval_hierarchical_match(self, value: Any, expected: Any, case_sensitive: bool) -> bool:
        """Evaluate hierarchical match (e.g., department trees)."""
        if not isinstance(value, str) or not isinstance(expected, str):
            return False
        
        # Support paths like "engineering.backend.api"
        # Match if value is equal to or child of expected
        if not case_sensitive:
            value = value.lower()
            expected = expected.lower()
        
        return value == expected or value.startswith(expected + ".")


class DataMasker:
    """Handles attribute-based data masking."""
    
    def __init__(self, attribute_evaluator: AttributeEvaluator):
        """Initialize with attribute evaluator."""
        self.attribute_evaluator = attribute_evaluator
        self.mask_functions = {
            "redact": self._mask_redact,
            "partial": self._mask_partial,
            "hash": self._mask_hash,
            "replace": self._mask_replace,
        }
    
    def apply_masking(
        self,
        data: Dict[str, Any],
        rules: List[AttributeMaskingRule],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply masking rules to data."""
        masked_data = data.copy()
        
        for rule in rules:
            # Check if rule applies
            if rule.condition:
                if not self.attribute_evaluator.evaluate_expression(rule.condition, context):
                    continue
            
            # Apply masking
            masked_data = self._apply_mask_to_field(
                masked_data,
                rule.field_path,
                rule.mask_type,
                rule.mask_value
            )
        
        return masked_data
    
    def _apply_mask_to_field(
        self,
        data: Dict[str, Any],
        field_path: str,
        mask_type: str,
        mask_value: Any
    ) -> Dict[str, Any]:
        """Apply mask to specific field."""
        parts = field_path.split(".")
        
        # Navigate to parent of target field
        current = data
        for part in parts[:-1]:
            if part not in current:
                return data  # Field doesn't exist
            current = current[part]
        
        # Apply mask
        field_name = parts[-1]
        if field_name in current:
            mask_func = self.mask_functions.get(mask_type, self._mask_redact)
            current[field_name] = mask_func(current[field_name], mask_value)
        
        return data
    
    def _mask_redact(self, value: Any, mask_value: Any) -> str:
        """Completely redact value."""
        return "[REDACTED]"
    
    def _mask_partial(self, value: Any, mask_value: Any) -> str:
        """Partially mask value (show first/last few characters)."""
        if not isinstance(value, str):
            value = str(value)
        
        if len(value) <= 4:
            return "*" * len(value)
        
        # Show first and last 2 characters
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    
    def _mask_hash(self, value: Any, mask_value: Any) -> str:
        """Replace with hash of value."""
        import hashlib
        value_str = str(value).encode('utf-8')
        return hashlib.sha256(value_str).hexdigest()[:16]
    
    def _mask_replace(self, value: Any, mask_value: Any) -> Any:
        """Replace with specified value."""
        return mask_value if mask_value is not None else "[MASKED]"


class EnhancedConditionEvaluator(ConditionEvaluator):
    """Enhanced condition evaluator with ABAC support."""
    
    def __init__(self):
        """Initialize with enhanced evaluators."""
        super().__init__()
        self.attribute_evaluator = AttributeEvaluator()
        
        # Add ABAC-specific evaluators
        self.evaluators.update({
            "attribute_expression": self._eval_attribute_expression,
            "department_hierarchy": self._eval_department_hierarchy,
            "security_clearance": self._eval_security_clearance,
            "geographic_region": self._eval_geographic_region,
            "time_of_day": self._eval_time_of_day,
            "day_of_week": self._eval_day_of_week,
        })
    
    def _eval_attribute_expression(
        self,
        value: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate complex attribute expression."""
        # Build expression from dict representation
        expression = self._build_expression(value)
        return self.attribute_evaluator.evaluate_expression(expression, context)
    
    def _build_expression(self, config: Dict[str, Any]) -> Union[AttributeCondition, AttributeExpression]:
        """Build expression from configuration."""
        if "operator" in config and config["operator"] in ["and", "or", "not"]:
            # Logical expression
            conditions = []
            for cond_config in config.get("conditions", []):
                conditions.append(self._build_expression(cond_config))
            
            return AttributeExpression(
                operator=LogicalOperator(config["operator"]),
                conditions=conditions
            )
        else:
            # Attribute condition
            return AttributeCondition(
                attribute_path=config.get("attribute_path", ""),
                operator=AttributeOperator(config.get("operator", "equals")),
                value=config.get("value"),
                case_sensitive=config.get("case_sensitive", True)
            )
    
    def _eval_department_hierarchy(
        self,
        value: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate department hierarchy condition."""
        user = context.get("user")
        if not user or not hasattr(user, "attributes"):
            return False
        
        user_dept = user.attributes.get("department", "")
        allowed_dept = value.get("department", "")
        include_children = value.get("include_children", True)
        
        if include_children:
            # Use hierarchical matching
            return (user_dept == allowed_dept or 
                    user_dept.startswith(allowed_dept + "."))
        else:
            return user_dept == allowed_dept
    
    def _eval_security_clearance(
        self,
        value: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate security clearance level."""
        user = context.get("user")
        if not user or not hasattr(user, "attributes"):
            return False
        
        # Define clearance hierarchy
        clearance_levels = {
            "public": 0,
            "internal": 1,
            "confidential": 2,
            "secret": 3,
            "top_secret": 4
        }
        
        user_clearance = user.attributes.get("security_clearance", "public")
        required_clearance = value.get("minimum_clearance", "public")
        
        user_level = clearance_levels.get(user_clearance, 0)
        required_level = clearance_levels.get(required_clearance, 0)
        
        return user_level >= required_level
    
    def _eval_geographic_region(
        self,
        value: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate geographic region condition."""
        user = context.get("user")
        if not user or not hasattr(user, "attributes"):
            return False
        
        user_region = user.attributes.get("region", "")
        allowed_regions = value.get("allowed_regions", [])
        
        if isinstance(allowed_regions, str):
            allowed_regions = [allowed_regions]
        
        return user_region in allowed_regions
    
    def _eval_time_of_day(
        self,
        value: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate time of day condition."""
        from datetime import datetime, time
        
        now = datetime.now().time()
        start_time = time.fromisoformat(value.get("start", "00:00"))
        end_time = time.fromisoformat(value.get("end", "23:59"))
        
        # Handle overnight ranges
        if start_time <= end_time:
            return start_time <= now <= end_time
        else:
            return now >= start_time or now <= end_time
    
    def _eval_day_of_week(
        self,
        value: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate day of week condition."""
        from datetime import datetime
        
        allowed_days = value.get("allowed_days", [])
        if isinstance(allowed_days, str):
            allowed_days = [allowed_days]
        
        # Convert to lowercase for comparison
        allowed_days = [day.lower() for day in allowed_days]
        
        current_day = datetime.now().strftime("%A").lower()
        return current_day in allowed_days


# Export enhanced components
__all__ = [
    "AttributeOperator",
    "LogicalOperator",
    "AttributeCondition",
    "AttributeExpression",
    "AttributeMaskingRule",
    "AttributeEvaluator",
    "DataMasker",
    "EnhancedConditionEvaluator",
]