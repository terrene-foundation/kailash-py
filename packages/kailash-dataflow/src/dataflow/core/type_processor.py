"""Type-aware field processor for DataFlow model operations.

Ensures all DataFlow operations respect model type annotations without
forced type conversions. Validates field values against declared types.

Related: TODO-153 - Type-Aware Model Processing
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Union, get_args, get_origin
from uuid import UUID

logger = logging.getLogger("dataflow.type_processor")


class TypeAwareFieldProcessor:
    """Process model fields with strict type awareness.

    This processor ensures field values respect model type annotations
    without forced conversions. It validates values against declared types
    and provides clear error messages for mismatches.

    Example:
        >>> fields = {"id": {"type": str, "required": True}}
        >>> processor = TypeAwareFieldProcessor(fields, "User")
        >>> processor.validate_field("id", "user-123")
        'user-123'
    """

    def __init__(
        self, model_fields: Dict[str, Dict[str, Any]], model_name: str = "Unknown"
    ):
        """Initialize with model field metadata.

        Args:
            model_fields: Dict of field_name -> {"type": <Python type>, "required": bool, ...}
            model_name: Name of the model (for error messages)
        """
        self.model_fields = model_fields
        self.model_name = model_name
        # Pre-compute resolved types for efficiency
        self._resolved_types: Dict[str, Any] = {}
        for field_name, field_info in model_fields.items():
            self._resolved_types[field_name] = self._resolve_type(
                field_info.get("type")
            )

    def _resolve_type(self, field_type: Any) -> Any:
        """Resolve a field type, unwrapping Optional and Union types.

        Returns the base type, unwrapping Optional[T] to T.

        Args:
            field_type: The type annotation to resolve

        Returns:
            The resolved base type, or None if no type provided
        """
        if field_type is None:
            return None

        origin = get_origin(field_type)
        if origin is Union:
            args = get_args(field_type)
            non_none_types = [t for t in args if t is not type(None)]
            if len(non_none_types) == 1:
                return non_none_types[0]
            # Multi-type union, return as-is
            return field_type
        return field_type

    def validate_field(self, field_name: str, value: Any, strict: bool = False) -> Any:
        """Validate a field value against its type annotation.

        In non-strict mode (default), performs safe conversions:
        - UUID string -> UUID object for UUID fields
        - ISO string -> datetime for datetime fields
        - ISO string -> date for date fields
        - String/int/float -> Decimal for Decimal fields

        In strict mode, no conversions are performed.

        Args:
            field_name: Name of the field
            value: Value to validate
            strict: If True, no type conversions performed

        Returns:
            Validated (possibly converted) value

        Raises:
            TypeError: If value doesn't match annotation
        """
        if value is None:
            return None

        expected_type = self._resolved_types.get(field_name)
        if expected_type is None:
            # No type annotation, pass through
            return value

        # Handle Union types that weren't simplified (multiple non-None types)
        if get_origin(expected_type) is Union:
            # For complex Union types, pass through
            return value

        # CRITICAL: Check bool->int special case BEFORE isinstance check
        # Python quirk: bool is a subclass of int, so isinstance(True, int) == True
        # But in DataFlow, we explicitly reject bool values for int fields
        if expected_type == int and isinstance(value, bool):
            raise TypeError(
                f"Model {self.model_name}, field '{field_name}': "
                f"expected int, got bool. Booleans are not integers in DataFlow."
            )

        # Check if value already matches expected type
        if isinstance(value, expected_type):
            return value

        if strict:
            if not isinstance(value, expected_type):
                type_name = getattr(expected_type, "__name__", str(expected_type))
                raise TypeError(
                    f"Model {self.model_name}, field '{field_name}': "
                    f"expected {type_name}, got {type(value).__name__}. "
                    f"Value: {repr(value)}"
                )
            return value

        # Non-strict: attempt safe conversions
        return self._safe_convert(field_name, value, expected_type)

    def _safe_convert(self, field_name: str, value: Any, expected_type: Any) -> Any:
        """Attempt safe type conversion.

        Only converts when the conversion is unambiguous and lossless:
        - str UUID -> UUID object
        - str ISO datetime -> datetime object
        - str ISO date -> date object
        - str/int/float -> Decimal

        Args:
            field_name: Name of the field (for error messages)
            value: Value to convert
            expected_type: Expected type for the field

        Returns:
            Converted value, or original value if no conversion needed

        Raises:
            TypeError: If conversion fails or is invalid
        """
        # Already matching type
        if isinstance(value, expected_type):
            return value

        # String -> UUID
        if expected_type == UUID and isinstance(value, str):
            try:
                return UUID(value)
            except ValueError:
                raise TypeError(
                    f"Model {self.model_name}, field '{field_name}': "
                    f"expected valid UUID string, got '{value}'"
                )

        # String -> datetime
        if expected_type == datetime and isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise TypeError(
                    f"Model {self.model_name}, field '{field_name}': "
                    f"expected ISO datetime string, got '{value}'"
                )

        # String -> date
        if expected_type == date and isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise TypeError(
                    f"Model {self.model_name}, field '{field_name}': "
                    f"expected ISO date string, got '{value}'"
                )

        # String/int/float -> Decimal
        if expected_type == Decimal and isinstance(value, (str, int, float)):
            try:
                return Decimal(str(value))
            except Exception:
                raise TypeError(
                    f"Model {self.model_name}, field '{field_name}': "
                    f"expected Decimal-convertible value, got '{value}'"
                )

        # Float with whole value -> int (safe conversion)
        # Note: Bool check is handled in validate_field() before reaching here
        if expected_type == int and isinstance(value, float):
            # Only convert if value is whole number
            if value == int(value):
                return int(value)
            raise TypeError(
                f"Model {self.model_name}, field '{field_name}': "
                f"expected int, got float with decimal part: {value}"
            )

        # For other mismatches, log warning and pass through in non-strict mode
        # This maintains backward compatibility with existing code
        logger.debug(
            "Type mismatch in %s.%s: expected %s, got %s (value: %r). Passing through.",
            self.model_name,
            field_name,
            getattr(expected_type, "__name__", str(expected_type)),
            type(value).__name__,
            value,
        )
        return value

    def process_record(
        self,
        record: Dict[str, Any],
        operation: str = "create",
        strict: bool = False,
        skip_fields: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Process all fields in a record with type validation.

        Args:
            record: Dict of field_name -> value
            operation: Operation name for error messages ("create", "update", etc.)
            strict: If True, raise on type mismatches
            skip_fields: Set of field names to skip (e.g., auto-managed timestamps)

        Returns:
            Processed record with validated values
        """
        skip = skip_fields if skip_fields is not None else {"created_at", "updated_at"}
        processed = {}

        for field_name, value in record.items():
            if field_name in skip:
                continue
            try:
                processed[field_name] = self.validate_field(
                    field_name, value, strict=strict
                )
            except TypeError as e:
                raise TypeError(
                    f"Type error in {operation} operation on {self.model_name}: {e}"
                ) from e

        return processed

    def process_records(
        self,
        records: list,
        operation: str = "bulk_create",
        strict: bool = False,
        skip_fields: Optional[set] = None,
    ) -> list:
        """Process multiple records with type validation.

        Args:
            records: List of record dicts
            operation: Operation name for error messages
            strict: If True, raise on type mismatches
            skip_fields: Set of field names to skip

        Returns:
            List of processed records
        """
        processed = []
        for i, record in enumerate(records):
            try:
                processed.append(
                    self.process_record(
                        record,
                        operation=operation,
                        strict=strict,
                        skip_fields=skip_fields,
                    )
                )
            except TypeError as e:
                raise TypeError(f"Type error in record {i} of {operation}: {e}") from e
        return processed

    def validate_foreign_key(
        self,
        field_name: str,
        value: Any,
        referenced_model_fields: Dict[str, Dict[str, Any]],
        referenced_model_name: str = "Unknown",
    ) -> Any:
        """Validate that a foreign key value matches the referenced model's PK type.

        Args:
            field_name: FK field name
            value: FK value
            referenced_model_fields: Field metadata of referenced model
            referenced_model_name: Name of referenced model

        Returns:
            Validated value

        Raises:
            TypeError: If FK type doesn't match PK type
        """
        pk_field_info = referenced_model_fields.get("id", {})
        pk_type = pk_field_info.get("type")

        if pk_type is None:
            return value

        pk_type_resolved = self._resolve_type(pk_type)

        if pk_type_resolved and not isinstance(value, pk_type_resolved):
            pk_type_name = getattr(pk_type_resolved, "__name__", str(pk_type_resolved))
            raise TypeError(
                f"Foreign key '{field_name}' in {self.model_name}: "
                f"expected type '{pk_type_name}' matching "
                f"{referenced_model_name}.id, got '{type(value).__name__}'"
            )

        return value
