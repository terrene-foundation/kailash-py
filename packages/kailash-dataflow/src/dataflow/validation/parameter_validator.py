"""
Parameter Validation Layer (Layer 2)

This module implements comprehensive parameter validation for DataFlow's strict mode.
Validates node parameters at workflow.add_node() time to catch configuration errors
early before workflow execution.

Validation Rules:
- CreateNode: Must have 'id', no auto-managed fields, correct types
- UpdateNode: Must have 'filter' and 'fields' structure, no auto-managed fields in 'fields'
- ListNode: Valid filters, limit, offset parameters

Integration: Called during workflow.add_node() when strict_mode enabled
"""

from typing import Any, Dict, List, Optional

from dataflow.validation.strict_mode import StrictModeConfig
from dataflow.validation.validators import ValidationError

# ============================================================================
# Constants
# ============================================================================

# Auto-managed fields that DataFlow handles automatically
AUTO_MANAGED_FIELDS = {"created_at", "updated_at"}


# ============================================================================
# Validation Result Helper
# ============================================================================


class ValidationResult:
    """
    Validation result wrapper for individual validation checks.

    Can represent either success or failure with error details.
    """

    def __init__(
        self,
        success: bool = False,
        error_code: Optional[str] = None,
        message: Optional[str] = None,
        solution: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.error_code = error_code
        self.message = message
        self.solution = solution or {}
        self.context = context or {}


# ============================================================================
# CreateNode Parameter Validation (STRICT_PARAM_101-103)
# ============================================================================


def validate_create_node_parameters(
    node_type: str,
    node_id: str,
    parameters: Dict[str, Any],
    model_fields: Optional[Dict[str, Any]] = None,
) -> List[ValidationResult]:
    """
    Validate CreateNode parameters.

    Validation Rules:
    1. Must have 'id' parameter
    2. Cannot have auto-managed fields (created_at, updated_at)
    3. Parameter types should match model field types (if model_fields provided)

    Args:
        node_type: Node type (e.g., "UserCreateNode")
        node_id: Node ID in workflow
        parameters: Node parameters from workflow.add_node()
        model_fields: Optional model field definitions for type checking

    Returns:
        List of ValidationResult instances (empty if valid)

    Error Codes:
        STRICT_PARAM_101: Missing required 'id' parameter
        STRICT_PARAM_102: Auto-managed field in parameters
        STRICT_PARAM_103: Parameter type mismatch
    """
    results = []

    # Rule 1: Check required 'id' parameter
    if "id" not in parameters:
        results.append(
            ValidationResult(
                success=False,
                error_code="STRICT_PARAM_101",
                message=f"Missing required parameter 'id' for CreateNode '{node_id}'",
                solution={
                    "description": "Add 'id' parameter to CreateNode",
                    "code_example": (
                        f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                        f'    "id": "user-123",  # Add this\n'
                        f"    # ... other parameters\n"
                        f"}})"
                    ),
                },
                context={
                    "node_type": node_type,
                    "node_id": node_id,
                    "provided_parameters": list(parameters.keys()),
                },
            )
        )

    # Rule 2: Check for auto-managed fields
    for field_name in AUTO_MANAGED_FIELDS:
        if field_name in parameters:
            results.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_PARAM_102",
                    message=f"Parameter '{field_name}' is auto-managed and cannot be set manually in CreateNode '{node_id}'",
                    solution={
                        "description": f"Remove '{field_name}' from parameters - DataFlow manages it automatically",
                        "code_example": (
                            f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                            f'    "id": "user-123",\n'
                            f'    # Remove: "{field_name}": ...\n'
                            f"    # DataFlow manages {field_name} automatically\n"
                            f"}})"
                        ),
                    },
                    context={
                        "node_type": node_type,
                        "node_id": node_id,
                        "field_name": field_name,
                        "auto_fields": list(AUTO_MANAGED_FIELDS),
                    },
                )
            )

    # Rule 3: Parameter type checking (if model_fields provided)
    if model_fields:
        for field_name, field_value in parameters.items():
            # Skip 'id' and auto-managed fields (already checked)
            if field_name == "id" or field_name in AUTO_MANAGED_FIELDS:
                continue

            # Check if field is in model definition
            if field_name in model_fields:
                expected_type = model_fields[field_name]
                actual_type = type(field_value)

                # Simple type check (str, int, float, bool)
                type_mismatch = False
                if expected_type == str and not isinstance(field_value, str):
                    type_mismatch = True
                elif expected_type == int and not isinstance(field_value, int):
                    type_mismatch = True
                elif expected_type == float and not isinstance(
                    field_value, (int, float)
                ):
                    type_mismatch = True
                elif expected_type == bool and not isinstance(field_value, bool):
                    type_mismatch = True

                if type_mismatch:
                    expected_type_name = (
                        expected_type.__name__
                        if hasattr(expected_type, "__name__")
                        else str(expected_type)
                    )
                    actual_type_name = (
                        actual_type.__name__
                        if hasattr(actual_type, "__name__")
                        else str(actual_type)
                    )

                    results.append(
                        ValidationResult(
                            success=False,
                            error_code="STRICT_PARAM_103",
                            message=f"Parameter '{field_name}' has wrong type: expected {expected_type_name}, got {actual_type_name} in CreateNode '{node_id}'",
                            solution={
                                "description": f"Change parameter '{field_name}' to {expected_type_name}",
                                "code_example": (
                                    f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                                    f'    "{field_name}": {_get_type_example(expected_type)},  # Correct type\n'
                                    f"}})"
                                ),
                            },
                            context={
                                "node_type": node_type,
                                "node_id": node_id,
                                "field_name": field_name,
                                "expected_type": expected_type_name,
                                "actual_type": actual_type_name,
                                "actual_value": str(field_value),
                            },
                        )
                    )

    # If no errors, return success
    if not results:
        results.append(ValidationResult(success=True))

    return results


# ============================================================================
# UpdateNode Parameter Validation (STRICT_PARAM_104-106)
# ============================================================================


def validate_update_node_parameters(
    node_type: str,
    node_id: str,
    parameters: Dict[str, Any],
    model_fields: Optional[Dict[str, Any]] = None,
) -> List[ValidationResult]:
    """
    Validate UpdateNode parameters.

    Validation Rules:
    1. Must have 'filter' parameter
    2. Must have 'fields' parameter
    3. Cannot have auto-managed fields in 'fields'

    Args:
        node_type: Node type (e.g., "UserUpdateNode")
        node_id: Node ID in workflow
        parameters: Node parameters from workflow.add_node()
        model_fields: Optional model field definitions

    Returns:
        List of ValidationResult instances (empty if valid)

    Error Codes:
        STRICT_PARAM_104: Missing required 'filter' parameter
        STRICT_PARAM_105: Missing required 'fields' parameter
        STRICT_PARAM_106: Auto-managed field in 'fields'
    """
    results = []

    # Rule 1: Check required 'filter' parameter
    if "filter" not in parameters:
        results.append(
            ValidationResult(
                success=False,
                error_code="STRICT_PARAM_104",
                message=f"Missing required parameter 'filter' for UpdateNode '{node_id}'",
                solution={
                    "description": "Add 'filter' parameter to UpdateNode",
                    "code_example": (
                        f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                        f'    "filter": {{"id": "user-123"}},  # Add this\n'
                        f'    "fields": {{"name": "Alice"}}\n'
                        f"}})"
                    ),
                },
                context={
                    "node_type": node_type,
                    "node_id": node_id,
                    "provided_parameters": list(parameters.keys()),
                },
            )
        )

    # Rule 2: Check required 'fields' parameter
    if "fields" not in parameters:
        results.append(
            ValidationResult(
                success=False,
                error_code="STRICT_PARAM_105",
                message=f"Missing required parameter 'fields' for UpdateNode '{node_id}'",
                solution={
                    "description": "Add 'fields' parameter to UpdateNode",
                    "code_example": (
                        f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                        f'    "filter": {{"id": "user-123"}},\n'
                        f'    "fields": {{"name": "Alice"}}  # Add this\n'
                        f"}})"
                    ),
                },
                context={
                    "node_type": node_type,
                    "node_id": node_id,
                    "provided_parameters": list(parameters.keys()),
                },
            )
        )

    # Rule 3: Check for auto-managed fields in 'fields'
    if "fields" in parameters and isinstance(parameters["fields"], dict):
        for field_name in AUTO_MANAGED_FIELDS:
            if field_name in parameters["fields"]:
                results.append(
                    ValidationResult(
                        success=False,
                        error_code="STRICT_PARAM_106",
                        message=f"Cannot update auto-managed field '{field_name}' in UpdateNode '{node_id}'",
                        solution={
                            "description": f"Remove '{field_name}' from fields - DataFlow manages it automatically",
                            "code_example": (
                                f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                                f'    "filter": {{"id": "user-123"}},\n'
                                f'    "fields": {{\n'
                                f'        # Remove: "{field_name}": ...\n'
                                f'        "name": "Alice"  # Other fields OK\n'
                                f"    }}\n"
                                f"}})"
                            ),
                        },
                        context={
                            "node_type": node_type,
                            "node_id": node_id,
                            "field_name": field_name,
                            "auto_fields": list(AUTO_MANAGED_FIELDS),
                        },
                    )
                )

    # If no errors, return success
    if not results:
        results.append(ValidationResult(success=True))

    return results


# ============================================================================
# ListNode Parameter Validation
# ============================================================================


def validate_list_node_parameters(
    node_type: str, node_id: str, parameters: Dict[str, Any]
) -> List[ValidationResult]:
    """
    Validate ListNode parameters.

    Validation Rules:
    1. 'filters' parameter (if present) should be a dict
    2. 'limit' parameter (if present) should be an integer >= 1
    3. 'offset' parameter (if present) should be an integer >= 0

    Args:
        node_type: Node type (e.g., "UserListNode")
        node_id: Node ID in workflow
        parameters: Node parameters from workflow.add_node()

    Returns:
        List of ValidationResult instances (empty if valid)
    """
    results = []

    # Rule 1: Validate 'filters' parameter type
    if "filters" in parameters:
        if not isinstance(parameters["filters"], dict):
            results.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_PARAM_107",
                    message=f"Parameter 'filters' must be a dict in ListNode '{node_id}'",
                    solution={
                        "description": "Change 'filters' to dict type",
                        "code_example": (
                            f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                            f'    "filters": {{"status": "active"}},  # Correct dict format\n'
                            f"}})"
                        ),
                    },
                    context={
                        "node_type": node_type,
                        "node_id": node_id,
                        "actual_type": type(parameters["filters"]).__name__,
                    },
                )
            )

    # Rule 2: Validate 'limit' parameter
    if "limit" in parameters:
        if not isinstance(parameters["limit"], int) or parameters["limit"] < 1:
            results.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_PARAM_108",
                    message=f"Parameter 'limit' must be an integer >= 1 in ListNode '{node_id}'",
                    solution={
                        "description": "Change 'limit' to positive integer",
                        "code_example": (
                            f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                            f'    "limit": 10,  # Positive integer\n'
                            f"}})"
                        ),
                    },
                    context={
                        "node_type": node_type,
                        "node_id": node_id,
                        "actual_value": parameters["limit"],
                    },
                )
            )

    # Rule 3: Validate 'offset' parameter
    if "offset" in parameters:
        if not isinstance(parameters["offset"], int) or parameters["offset"] < 0:
            results.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_PARAM_109",
                    message=f"Parameter 'offset' must be an integer >= 0 in ListNode '{node_id}'",
                    solution={
                        "description": "Change 'offset' to non-negative integer",
                        "code_example": (
                            f'workflow.add_node("{node_type}", "{node_id}", {{\n'
                            f'    "offset": 0,  # Non-negative integer\n'
                            f"}})"
                        ),
                    },
                    context={
                        "node_type": node_type,
                        "node_id": node_id,
                        "actual_value": parameters["offset"],
                    },
                )
            )

    # If no errors, return success
    if not results:
        results.append(ValidationResult(success=True))

    return results


# ============================================================================
# Helper Functions
# ============================================================================


def _get_type_example(expected_type: type) -> str:
    """
    Get example value for a given type.

    Args:
        expected_type: Python type (str, int, float, bool)

    Returns:
        Example value as string
    """
    if expected_type == str:
        return '"example"'
    elif expected_type == int:
        return "123"
    elif expected_type == float:
        return "123.45"
    elif expected_type == bool:
        return "True"
    else:
        return "..."
