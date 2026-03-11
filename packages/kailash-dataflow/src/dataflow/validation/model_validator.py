"""
Model Validation Layer (Layer 1)

This module implements comprehensive model structure validation for DataFlow's
strict mode. Validates primary key presence, auto-field conflicts, reserved
field names, and field type compatibility.

Validation Rules:
- Primary Key: Model MUST have `id: str` field
- Auto-Fields: Model cannot define created_at/updated_at (DataFlow auto-managed)
- Reserved Fields: Model cannot use DataFlow internal field names
- Field Types: Model fields must use supported types only

Integration: Called during @db.model() decorator when strict_mode enabled
"""

import datetime
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from dataflow.validation.strict_mode import StrictModeConfig
from dataflow.validation.validators import BaseValidator, ValidationError

# ============================================================================
# Constants
# ============================================================================

# Reserved field names that conflict with DataFlow internals
RESERVED_FIELDS = {
    # DataFlow internal fields
    "dataflow_instance",  # Instance identifier
    "_nodes",  # Generated node storage
    "_workflow",  # Generated workflow storage
    "_model_metadata",  # Model metadata storage
    # SQLAlchemy reserved (if using SQLAlchemy backend)
    "metadata",
    "query",
    # Python reserved
    "__dict__",
    "__class__",
    "__init__",
    # Common conflicts
    "type",  # Python builtin
    "id_",  # Avoid id_ (use id instead)
}

# Supported field types for DataFlow models
SUPPORTED_TYPES = {
    # Primitive types
    str,
    int,
    float,
    bool,
    # Collection types
    dict,
    list,
    # Date/time types
    datetime.datetime,
    datetime.date,
    datetime.time,
}


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
# Primary Key Validation (STRICT_MODEL_001-004)
# ============================================================================


def validate_primary_key(model_cls: type) -> ValidationResult:
    """
    Validate model has id: str field.

    Validation Rules:
    1. Model MUST have field named 'id'
    2. 'id' field MUST have type annotation
    3. 'id' field type MUST be str (not int, UUID, etc.)
    4. 'id' field cannot be Optional (must be required)

    Args:
        model_cls: Model class to validate

    Returns:
        ValidationResult with success=True or error details

    Error Codes:
        STRICT_MODEL_001: Missing 'id' field
        STRICT_MODEL_002: 'id' field has wrong type (not str)
        STRICT_MODEL_003: 'id' field is Optional (must be required)
        STRICT_MODEL_004: 'id' field has no type annotation
    """
    model_name = model_cls.__name__

    try:
        # Extract type hints (field type annotations)
        type_hints = get_type_hints(model_cls)
    except Exception as e:
        # Failed to extract type hints
        return ValidationResult(
            success=False,
            error_code="STRICT_MODEL_004",
            message=f"Model '{model_name}' has invalid type annotations: {str(e)}",
            solution={
                "description": "Ensure all field type annotations are valid",
                "example": f"class {model_name}:\n    id: str\n    name: str",
            },
            context={"model": model_name, "error": str(e)},
        )

    # Rule 1: Check 'id' field exists
    if "id" not in type_hints:
        return ValidationResult(
            success=False,
            error_code="STRICT_MODEL_001",
            message=f"Model '{model_name}' missing required 'id' field",
            solution={
                "description": "Add 'id: str' field to model definition",
                "code_example": f"class {model_name}:\n    id: str\n    # other fields...",
            },
            context={"model": model_name, "available_fields": list(type_hints.keys())},
        )

    # Extract id field type
    id_type = type_hints["id"]

    # Rule 4: Check if Optional/Union (id cannot be optional)
    origin = get_origin(id_type)
    if origin is Union:  # Optional is Union[T, None]
        args = get_args(id_type)
        # Check if this is Optional (Union with None)
        if type(None) in args:
            return ValidationResult(
                success=False,
                error_code="STRICT_MODEL_003",
                message=f"Model '{model_name}' field 'id' cannot be Optional",
                solution={
                    "description": "Change 'id: Optional[str]' to 'id: str'",
                    "code_example": f"class {model_name}:\n    id: str  # NOT Optional[str]",
                },
                context={"model": model_name, "current_type": str(id_type)},
            )

    # Rule 3: Check id field type is str
    if id_type != str:
        return ValidationResult(
            success=False,
            error_code="STRICT_MODEL_002",
            message=f"Model '{model_name}' field 'id' must be type 'str', got '{id_type.__name__ if hasattr(id_type, '__name__') else str(id_type)}'",
            solution={
                "description": "Change id field type to 'str'",
                "code_example": f"class {model_name}:\n    id: str  # NOT int, UUID, etc.",
            },
            context={
                "model": model_name,
                "current_type": str(id_type),
                "required_type": "str",
            },
        )

    # All checks passed
    return ValidationResult(success=True)


# ============================================================================
# Auto-Field Conflict Detection (STRICT_MODEL_010-012)
# ============================================================================


def validate_auto_field_conflicts(
    model_cls: type, config: Optional[StrictModeConfig] = None
) -> ValidationResult:
    """
    Detect manual definition of auto-managed fields.

    DataFlow automatically adds created_at and updated_at fields to all models.
    Users should not define these fields manually.

    Validation Rules:
    1. Model cannot define 'created_at' field
    2. Model cannot define 'updated_at' field
    3. If auto-fields disabled in config, skip validation
    4. Clear error message explaining why fields are reserved

    Args:
        model_cls: Model class to validate
        config: Strict mode configuration (optional)

    Returns:
        ValidationResult with success=True or error details

    Error Codes:
        STRICT_MODEL_010: Manual 'created_at' field detected
        STRICT_MODEL_011: Manual 'updated_at' field detected
        STRICT_MODEL_012: Both auto-fields manually defined
    """
    model_name = model_cls.__name__

    # Check if auto-fields are enabled (default: True)
    # If disabled via configuration, skip this validation
    if (
        config
        and hasattr(config, "auto_fields_enabled")
        and not config.auto_fields_enabled
    ):
        return ValidationResult(success=True)

    try:
        type_hints = get_type_hints(model_cls)
    except Exception:
        # If we can't get type hints, skip this validation
        # (primary key validation will catch this)
        return ValidationResult(success=True)

    # Check for manual auto-field definitions
    conflicts = []
    if "created_at" in type_hints:
        conflicts.append("created_at")
    if "updated_at" in type_hints:
        conflicts.append("updated_at")

    if conflicts:
        # Determine error code based on which fields conflict
        if len(conflicts) == 2:
            error_code = "STRICT_MODEL_012"
            field_list = "created_at and updated_at"
        elif "created_at" in conflicts:
            error_code = "STRICT_MODEL_010"
            field_list = "created_at"
        else:
            error_code = "STRICT_MODEL_011"
            field_list = "updated_at"

        return ValidationResult(
            success=False,
            error_code=error_code,
            message=f"Model '{model_name}' cannot define {field_list} - auto-managed by DataFlow",
            solution={
                "description": f"Remove {field_list} field(s) from model definition",
                "explanation": "DataFlow automatically adds created_at and updated_at timestamp fields to all models",
                "references": ["docs/guides/model-design.md#auto-fields"],
            },
            context={"model": model_name, "conflicts": conflicts},
        )

    return ValidationResult(success=True)


# ============================================================================
# Reserved Field Validation (STRICT_MODEL_020-022)
# ============================================================================


def _suggest_alternative_name(field_name: str) -> List[str]:
    """
    Suggest alternative field names for reserved fields.

    Args:
        field_name: Reserved field name

    Returns:
        List of suggested alternative names
    """
    suggestions = []

    # Common alternatives
    if field_name == "type":
        suggestions = ["kind", "category", "model_type"]
    elif field_name == "id_":
        suggestions = ["id"]  # Use id instead of id_
    elif field_name == "metadata":
        suggestions = ["meta", "properties", "attributes"]
    elif field_name == "query":
        suggestions = ["search_query", "filter_query"]
    else:
        # Generic suggestion: add suffix
        suggestions = [
            f"{field_name}_value",
            f"{field_name}_field",
            f"custom_{field_name}",
        ]

    return suggestions


def validate_reserved_fields(model_cls: type) -> List[ValidationResult]:
    """
    Prevent usage of reserved field names.

    Validation Rules:
    1. Model cannot use any field name in RESERVED_FIELDS set
    2. Model cannot use field names starting with '_dataflow_'
    3. Model cannot use field names starting with '__' (dunder methods)
    4. Provide list of reserved names and suggested alternatives

    Args:
        model_cls: Model class to validate

    Returns:
        List of ValidationResult (one per violation, or one success result)

    Error Codes:
        STRICT_MODEL_020: Reserved field name detected
        STRICT_MODEL_021: Internal DataFlow field name pattern (_dataflow_*)
        STRICT_MODEL_022: Python dunder method pattern (__*__)
    """
    model_name = model_cls.__name__
    errors = []

    try:
        type_hints = get_type_hints(model_cls)
    except Exception:
        # If we can't get type hints, skip this validation
        return [ValidationResult(success=True)]

    for field_name in type_hints.keys():
        # Rule 1: Check exact reserved name match
        if field_name in RESERVED_FIELDS:
            errors.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_MODEL_020",
                    message=f"Model '{model_name}' field '{field_name}' is reserved by DataFlow",
                    solution={
                        "description": f"Rename field '{field_name}' to avoid conflict",
                        "suggestions": _suggest_alternative_name(field_name),
                        "example": f"# Instead of '{field_name}', use one of: {', '.join(_suggest_alternative_name(field_name))}",
                    },
                    context={
                        "model": model_name,
                        "field": field_name,
                        "category": "reserved",
                    },
                )
            )

        # Rule 2: Check internal prefix pattern (_dataflow_*)
        elif field_name.startswith("_dataflow_"):
            errors.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_MODEL_021",
                    message=f"Model '{model_name}' field '{field_name}' uses DataFlow internal prefix '_dataflow_'",
                    solution={
                        "description": "Rename field to not start with '_dataflow_'",
                        "example": f"# Rename '{field_name}' to '{field_name.replace('_dataflow_', '')}'",
                    },
                    context={
                        "model": model_name,
                        "field": field_name,
                        "category": "internal_prefix",
                    },
                )
            )

        # Rule 3: Check dunder method pattern (__*__)
        elif field_name.startswith("__") and field_name.endswith("__"):
            errors.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_MODEL_022",
                    message=f"Model '{model_name}' field '{field_name}' uses Python dunder method pattern",
                    solution={
                        "description": "Rename field to not use __name__ pattern",
                        "example": f"# Rename '{field_name}' to '{field_name.strip('_')}'",
                    },
                    context={
                        "model": model_name,
                        "field": field_name,
                        "category": "dunder_pattern",
                    },
                )
            )

    return errors if errors else [ValidationResult(success=True)]


# ============================================================================
# Field Type Validation (STRICT_MODEL_030-032)
# ============================================================================


def validate_field_types(model_cls: type) -> List[ValidationResult]:
    """
    Ensure all fields use supported types.

    Supported Types:
    - Primitive: str, int, float, bool
    - Collections: dict, list
    - Date/Time: datetime, date, time
    - Optional variants: Optional[supported_type]

    Validation Rules:
    1. Field type must be in SUPPORTED_TYPES or Optional[SUPPORTED_TYPES]
    2. Complex types (custom classes) not supported
    3. List/Dict can be untyped or typed with supported types
    4. Provide list of supported types in error message

    Args:
        model_cls: Model class to validate

    Returns:
        List of ValidationResult (one per violation, or one success result)

    Error Codes:
        STRICT_MODEL_030: Unsupported field type
        STRICT_MODEL_031: Complex nested type (e.g., List[CustomClass])
        STRICT_MODEL_032: No type annotation provided
    """
    model_name = model_cls.__name__
    errors = []

    try:
        type_hints = get_type_hints(model_cls)
    except Exception as e:
        # Failed to get type hints
        errors.append(
            ValidationResult(
                success=False,
                error_code="STRICT_MODEL_032",
                message=f"Model '{model_name}' has invalid type annotations: {str(e)}",
                solution={
                    "description": "Ensure all fields have valid type annotations",
                    "supported_types": "str, int, float, bool, dict, list, datetime, date, time",
                },
                context={"model": model_name, "error": str(e)},
            )
        )
        return errors

    for field_name, field_type in type_hints.items():
        # Skip auto-managed fields (validated separately)
        if field_name in ("created_at", "updated_at"):
            continue

        # Unwrap Optional/Union to get base type
        origin = get_origin(field_type)
        if origin is Union:  # Optional is Union[T, None]
            args = get_args(field_type)
            # Find non-None type
            base_type = None
            for arg in args:
                if arg is not type(None):
                    base_type = arg
                    break
            if base_type is None:
                # Only None type? Invalid
                errors.append(
                    ValidationResult(
                        success=False,
                        error_code="STRICT_MODEL_030",
                        message=f"Model '{model_name}' field '{field_name}' has invalid Optional type",
                        solution={
                            "description": "Use Optional[supported_type] or supported_type directly",
                            "supported_types": "str, int, float, bool, dict, list, datetime, date, time",
                        },
                        context={
                            "model": model_name,
                            "field": field_name,
                            "type": str(field_type),
                        },
                    )
                )
                continue
        else:
            base_type = field_type

        # Check if base type is supported
        base_origin = get_origin(base_type)

        if base_origin is not None:  # Generic type (List, Dict, etc.)
            # Check if origin is list or dict
            if base_origin not in (list, dict):
                errors.append(
                    ValidationResult(
                        success=False,
                        error_code="STRICT_MODEL_030",
                        message=f"Model '{model_name}' field '{field_name}' has unsupported generic type '{base_type}'",
                        solution={
                            "description": "Use supported types: str, int, float, bool, dict, list, datetime, date, time",
                            "example": f"{field_name}: list  # or dict, str, int, etc.",
                        },
                        context={
                            "model": model_name,
                            "field": field_name,
                            "type": str(base_type),
                        },
                    )
                )
            # For List and Dict, check type arguments if present
            type_args = get_args(base_type)
            if type_args:
                # Check if type arguments are supported
                for arg in type_args:
                    if arg not in SUPPORTED_TYPES and arg is not type(None):
                        errors.append(
                            ValidationResult(
                                success=False,
                                error_code="STRICT_MODEL_031",
                                message=f"Model '{model_name}' field '{field_name}' has complex nested type '{base_type}'",
                                solution={
                                    "description": "Use simple types in List/Dict",
                                    "example": f"{field_name}: list[str]  # or list[int], dict[str, int], etc.",
                                },
                                context={
                                    "model": model_name,
                                    "field": field_name,
                                    "type": str(base_type),
                                },
                            )
                        )
        elif base_type not in SUPPORTED_TYPES:
            # Not a supported type
            errors.append(
                ValidationResult(
                    success=False,
                    error_code="STRICT_MODEL_030",
                    message=f"Model '{model_name}' field '{field_name}' has unsupported type '{base_type.__name__ if hasattr(base_type, '__name__') else str(base_type)}'",
                    solution={
                        "description": "Use one of: str, int, float, bool, dict, list, datetime, date, time",
                        "example": f"{field_name}: str  # or int, float, etc.",
                        "references": ["docs/guides/model-design.md#supported-types"],
                    },
                    context={
                        "model": model_name,
                        "field": field_name,
                        "type": str(base_type),
                    },
                )
            )

    return errors if errors else [ValidationResult(success=True)]


# ============================================================================
# Main Validation Entry Point
# ============================================================================


def validate_model(
    model_cls: type, config: Optional[StrictModeConfig] = None
) -> List[ValidationError]:
    """
    Main validation entry point for model structure validation.

    Runs all validation layers and returns structured errors.

    Validation Layers:
    1. Primary key validation (id: str required)
    2. Auto-field conflict detection (created_at/updated_at reserved)
    3. Reserved field validation (DataFlow internal names)
    4. Field type validation (supported types only)

    Args:
        model_cls: Model class to validate
        config: Strict mode configuration (optional)

    Returns:
        List of ValidationError instances (empty if valid)

    Usage:
        from dataflow.validation.model_validator import validate_model

        errors = validate_model(MyModel)
        if errors:
            # Handle validation failures
            for error in errors:
                print(f"{error.error_code}: {error.message}")
        else:
            # Model is valid
            pass
    """
    all_errors = []

    # Layer 1: Primary key validation
    pk_result = validate_primary_key(model_cls)
    if not pk_result.success:
        all_errors.append(
            ValidationError(
                error_code=pk_result.error_code,
                category="MODEL_VALIDATION",
                severity="ERROR",
                message=pk_result.message,
                context=pk_result.context,
                solution=pk_result.solution,
            )
        )

    # Layer 2: Auto-field conflict detection
    auto_result = validate_auto_field_conflicts(model_cls, config)
    if not auto_result.success:
        all_errors.append(
            ValidationError(
                error_code=auto_result.error_code,
                category="MODEL_VALIDATION",
                severity="ERROR",
                message=auto_result.message,
                context=auto_result.context,
                solution=auto_result.solution,
            )
        )

    # Layer 3: Reserved field validation
    reserved_results = validate_reserved_fields(model_cls)
    for result in reserved_results:
        if not result.success:
            all_errors.append(
                ValidationError(
                    error_code=result.error_code,
                    category="MODEL_VALIDATION",
                    severity="ERROR",
                    message=result.message,
                    context=result.context,
                    solution=result.solution,
                )
            )

    # Layer 4: Field type validation
    type_results = validate_field_types(model_cls)
    for result in type_results:
        if not result.success:
            all_errors.append(
                ValidationError(
                    error_code=result.error_code,
                    category="MODEL_VALIDATION",
                    severity="ERROR",
                    message=result.message,
                    context=result.context,
                    solution=result.solution,
                )
            )

    return all_errors
