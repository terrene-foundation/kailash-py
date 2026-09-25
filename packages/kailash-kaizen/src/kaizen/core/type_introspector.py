"""
Type Introspection System for Kaizen

Provides runtime type checking and JSON schema generation for Python type annotations.

Supports:
- Basic types (str, int, float, bool, list, dict)
- Literal types (Literal["A", "B", "C"])
- Union types (Union[str, int])
- Optional types (Optional[str])
- Generic types (List[str], Dict[str, int])
- TypedDict (nested structures)

This module is the foundation for structured output support and validation.
"""

import inspect
from types import UnionType
from typing import (
    Annotated,
    Any,
    Dict,
    ForwardRef,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    get_args,
    get_origin,
)

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

try:
    from typing import NotRequired, Required
except ImportError:
    from typing_extensions import NotRequired, Required


class TypeIntrospector:
    """
    Runtime type introspection and validation for Python type annotations.

    Provides comprehensive support for all Python typing constructs, converting
    them to JSON schemas and performing runtime validation.
    """

    # Basic type mapping
    BASIC_TYPES = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    @staticmethod
    def _unwrap_value_type(type_annotation: Type) -> Type:
        """Metadata and key-presence markers do not change a present value's type."""
        while get_origin(type_annotation) in (Annotated, Required, NotRequired):
            type_annotation = get_args(type_annotation)[0]
        if isinstance(type_annotation, (str, ForwardRef)):
            raise ValueError(f"Unresolved type annotation: {type_annotation!r}")
        return type_annotation

    @classmethod
    def _require_resolved_contract(cls, type_annotation: Type, seen: frozenset) -> None:
        """Check the whole declared contract, including branches absent in a value."""
        type_annotation = cls._unwrap_value_type(type_annotation)
        if cls.is_typeddict(type_annotation):
            if type_annotation in seen:
                return
            seen = seen | {type_annotation}
            annotations, _ = cls._typeddict_fields(type_annotation)
            for annotation in annotations.values():
                cls._require_resolved_contract(annotation, seen)
        elif (
            cls.is_union_type(type_annotation)
            or cls.is_list_type(type_annotation)
            or cls.is_dict_type(type_annotation)
        ):
            for annotation in get_args(type_annotation):
                cls._require_resolved_contract(annotation, seen)

    @classmethod
    def _typeddict_fields(cls, type_annotation: Type) -> Tuple[Dict[str, Any], set]:
        """Resolve nested contracts and correct postponed required-key metadata."""
        from kailash.utils.annotations import get_resolved_type_hints

        try:
            annotations = get_resolved_type_hints(type_annotation, include_extras=True)
        except (NameError, TypeError, RuntimeError) as exc:
            raise ValueError(
                f"Cannot resolve annotations for TypedDict "
                f"'{type_annotation.__name__}': {exc}"
            ) from exc
        required = set(getattr(type_annotation, "__required_keys__", set()))
        for name, annotation in annotations.items():
            while get_origin(annotation) is Annotated:
                annotation = get_args(annotation)[0]
            origin = get_origin(annotation)
            if origin is Required:
                required.add(name)
            elif origin is NotRequired:
                required.discard(name)
        return annotations, required

    @classmethod
    def is_literal_type(cls, type_annotation: Type) -> bool:
        """
        Check if type annotation is a Literal type.

        Args:
            type_annotation: Type to check

        Returns:
            bool: True if Literal type

        Example:
            >>> TypeIntrospector.is_literal_type(Literal["A", "B"])
            True
            >>> TypeIntrospector.is_literal_type(str)
            False
        """
        return get_origin(type_annotation) is Literal

    @classmethod
    def is_union_type(cls, type_annotation: Type) -> bool:
        """
        Check if type annotation is a Union type.

        Args:
            type_annotation: Type to check

        Returns:
            bool: True if Union type

        Example:
            >>> TypeIntrospector.is_union_type(Union[str, int])
            True
            >>> TypeIntrospector.is_union_type(Optional[str])
            True  # Optional is Union[T, None]
        """
        return get_origin(type_annotation) in (Union, UnionType)

    @classmethod
    def is_optional_type(cls, type_annotation: Type) -> bool:
        """
        Check if type annotation is Optional (Union[T, None]).

        Args:
            type_annotation: Type to check

        Returns:
            bool: True if Optional type

        Example:
            >>> TypeIntrospector.is_optional_type(Optional[str])
            True
            >>> TypeIntrospector.is_optional_type(Union[str, None])
            True
            >>> TypeIntrospector.is_optional_type(Union[str, int])
            False
        """
        if not cls.is_union_type(type_annotation):
            return False

        args = get_args(type_annotation)
        return len(args) == 2 and type(None) in args

    @classmethod
    def is_notrequired_type(cls, type_annotation: Type) -> bool:
        """
        Check if type annotation is NotRequired (for TypedDict).

        Args:
            type_annotation: Type to check

        Returns:
            bool: True if NotRequired type

        Example:
            >>> TypeIntrospector.is_notrequired_type(NotRequired[str])
            True
            >>> TypeIntrospector.is_notrequired_type(str)
            False
        """
        return get_origin(type_annotation) is NotRequired

    @classmethod
    def is_list_type(cls, type_annotation: Type) -> bool:
        """
        Check if type annotation is a List type.

        Args:
            type_annotation: Type to check

        Returns:
            bool: True if List type

        Example:
            >>> TypeIntrospector.is_list_type(List[str])
            True
            >>> TypeIntrospector.is_list_type(list)
            False  # Generic list, not typed
        """
        origin = get_origin(type_annotation)
        return origin is list or origin is List

    @classmethod
    def is_dict_type(cls, type_annotation: Type) -> bool:
        """
        Check if type annotation is a Dict type.

        Args:
            type_annotation: Type to check

        Returns:
            bool: True if Dict type

        Example:
            >>> TypeIntrospector.is_dict_type(Dict[str, int])
            True
            >>> TypeIntrospector.is_dict_type(dict)
            False  # Generic dict, not typed
        """
        origin = get_origin(type_annotation)
        return origin is dict or origin is Dict

    @classmethod
    def is_typeddict(cls, type_annotation: Type) -> bool:
        """
        Check if type annotation is a TypedDict.

        Args:
            type_annotation: Type to check

        Returns:
            bool: True if TypedDict

        Example:
            >>> class MyDict(TypedDict):
            ...     name: str
            ...     age: int
            >>> TypeIntrospector.is_typeddict(MyDict)
            True
        """
        try:
            # TypedDict creates a class that inherits from dict
            return (
                inspect.isclass(type_annotation)
                and hasattr(type_annotation, "__annotations__")
                and hasattr(type_annotation, "__total__")
            )
        except Exception:
            return False

    @classmethod
    def validate_value_against_type(
        cls, value: Any, type_annotation: Type
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a value against a type annotation.

        Handles all typing constructs including Literal, Union, Optional, etc.

        Args:
            value: Value to validate
            type_annotation: Expected type

        Returns:
            tuple: (is_valid, error_message)

        Example:
            >>> valid, error = TypeIntrospector.validate_value_against_type("A", Literal["A", "B"])
            >>> assert valid and error is None
            >>>
            >>> valid, error = TypeIntrospector.validate_value_against_type("C", Literal["A", "B"])
            >>> assert not valid and "must be one of" in error
        """
        try:
            cls._require_resolved_contract(type_annotation, frozenset())
            return cls._validate_value_against_type(value, type_annotation, frozenset())
        except ValueError as exc:
            return False, str(exc)

    @classmethod
    def _validate_value_against_type(
        cls, value: Any, type_annotation: Type, seen: frozenset
    ) -> Tuple[bool, Optional[str]]:
        type_annotation = cls._unwrap_value_type(type_annotation)

        # Handle Literal types
        if cls.is_literal_type(type_annotation):
            allowed_values = get_args(type_annotation)
            if any(
                type(value) is type(allowed) and value == allowed
                for allowed in allowed_values
            ):
                return True, None
            else:
                return (
                    False,
                    f"Value '{value}' must be one of {allowed_values}",
                )

        # Handle Union types
        if cls.is_union_type(type_annotation):
            union_types = get_args(type_annotation)
            for union_type in union_types:
                if union_type is type(None) and value is None:
                    return True, None
                valid, _ = cls._validate_value_against_type(value, union_type, seen)
                if valid:
                    return True, None

            type_names = [
                t.__name__ if hasattr(t, "__name__") else str(t) for t in union_types
            ]
            return (
                False,
                f"Value type {type(value).__name__} doesn't match any of {type_names}",
            )

        # Null is valid for the null type or any union containing it.
        if value is None:
            if type_annotation is type(None) or (
                cls.is_union_type(type_annotation)
                and type(None) in get_args(type_annotation)
            ):
                return True, None
            return False, "Value is None but type does not permit null"

        # Handle Optional types (already handled by Union, but explicit for clarity)
        if cls.is_optional_type(type_annotation):
            inner_type = [t for t in get_args(type_annotation) if t is not type(None)][
                0
            ]
            return cls._validate_value_against_type(value, inner_type, seen)

        # Track only containers actually traversed, after Union dispatch. Each
        # child gets its own ancestry, so shared siblings are not cycles.
        if isinstance(value, (list, dict)) and (
            cls.is_list_type(type_annotation)
            or cls.is_dict_type(type_annotation)
            or cls.is_typeddict(type_annotation)
        ):
            if id(value) in seen:
                return False, "Cyclic container values are not valid structured output"
            seen = seen | {id(value)}

        # Handle List types
        if cls.is_list_type(type_annotation):
            if not isinstance(value, list):
                return False, f"Expected list, got {type(value).__name__}"

            # Check item types if specified
            args = get_args(type_annotation)
            if args:
                item_type = args[0]
                for i, item in enumerate(value):
                    valid, error = cls._validate_value_against_type(
                        item, item_type, seen
                    )
                    if not valid:
                        return False, f"List item {i}: {error}"

            return True, None

        # Handle Dict types
        if cls.is_dict_type(type_annotation):
            if not isinstance(value, dict):
                return False, f"Expected dict, got {type(value).__name__}"

            # Check key/value types if specified
            args = get_args(type_annotation)
            if len(args) == 2:
                key_type, value_type = args
                for k, v in value.items():
                    valid_key, error_key = cls._validate_value_against_type(
                        k, key_type, seen
                    )
                    if not valid_key:
                        return False, f"Dict key '{k}': {error_key}"

                    valid_val, error_val = cls._validate_value_against_type(
                        v, value_type, seen
                    )
                    if not valid_val:
                        return False, f"Dict value for key '{k}': {error_val}"

            return True, None

        # Handle TypedDict
        if cls.is_typeddict(type_annotation):
            if not isinstance(value, dict):
                return False, f"Expected dict for TypedDict, got {type(value).__name__}"

            annotations, required_keys = cls._typeddict_fields(type_annotation)

            # Check required keys
            for key in required_keys:
                if key not in value:
                    return False, f"Missing required key: {key}"

            # Validate types for all present keys
            for key, key_type in annotations.items():
                if key in value:
                    valid, error = cls._validate_value_against_type(
                        value[key], key_type, seen
                    )
                    if not valid:
                        return False, f"TypedDict field '{key}': {error}"

            return True, None

        # Handle basic types
        if type_annotation in cls.BASIC_TYPES:
            if isinstance(value, type_annotation):
                return True, None
            # Special case: int/float are interchangeable for numeric types
            if type_annotation == float and isinstance(value, int):
                return True, None
            if type_annotation == int and isinstance(value, float):
                return True, None

            return (
                False,
                f"Expected {type_annotation.__name__}, got {type(value).__name__}",
            )

        # Fallback: try isinstance (may fail for some generic types)
        try:
            if isinstance(value, type_annotation):
                return True, None
            else:
                return (
                    False,
                    f"Value doesn't match type {type_annotation}",
                )
        except TypeError:
            # isinstance doesn't work with this type annotation
            # Allow it through (can't validate)
            return True, None

    @classmethod
    def type_to_json_schema(
        cls, type_annotation: Type, description: str = ""
    ) -> Dict[str, Any]:
        """
        Convert Python type annotation to JSON schema.

        Supports all Python typing constructs including nested structures.

        Args:
            type_annotation: Python type to convert
            description: Field description for documentation

        Returns:
            dict: JSON schema for the type

        Example:
            >>> schema = TypeIntrospector.type_to_json_schema(Literal["A", "B"], "Category")
            >>> assert schema == {"type": "string", "enum": ["A", "B"], "description": "Category"}
            >>>
            >>> schema = TypeIntrospector.type_to_json_schema(List[str], "Tags")
            >>> assert schema == {"type": "array", "items": {"type": "string"}, "description": "Tags"}
        """
        return cls._type_to_json_schema(type_annotation, description, frozenset())

    @classmethod
    def _type_to_json_schema(
        cls, type_annotation: Type, description: str, seen: frozenset
    ) -> Dict[str, Any]:
        type_annotation = cls._unwrap_value_type(type_annotation)
        schema = {}

        if description:
            schema["description"] = description

        # Handle Literal types
        if cls.is_literal_type(type_annotation):
            enum_values = list(get_args(type_annotation))
            enum_types = list(
                dict.fromkeys(
                    cls.BASIC_TYPES.get(type(value), "string") for value in enum_values
                )
            )
            schema.update(
                {
                    "type": enum_types[0] if len(enum_types) == 1 else enum_types,
                    "enum": enum_values,
                }
            )
            return schema

        # Handle Optional types
        if cls.is_optional_type(type_annotation):
            inner_type = [t for t in get_args(type_annotation) if t is not type(None)][
                0
            ]
            inner_schema = cls._type_to_json_schema(inner_type, "", seen)
            if "type" in inner_schema:
                schema.update(inner_schema)
                types = schema["type"]
                types = types if isinstance(types, list) else [types]
                schema["type"] = list(dict.fromkeys([*types, "null"]))
                if "enum" in schema and None not in schema["enum"]:
                    schema["enum"] = [*schema["enum"], None]
            else:
                schema["anyOf"] = [inner_schema, {"type": "null"}]
            return schema

        # Keep every union branch, including null, in the schema contract.
        if cls.is_union_type(type_annotation):
            schema["anyOf"] = [
                cls._type_to_json_schema(t, "", seen) for t in get_args(type_annotation)
            ]
            return schema

        # Handle List types
        if cls.is_list_type(type_annotation):
            schema["type"] = "array"
            args = get_args(type_annotation)
            if args:
                item_type = args[0]
                schema["items"] = cls._type_to_json_schema(item_type, "", seen)
            else:
                # Generic list without item type
                schema["items"] = {"type": "string"}  # Default
            return schema

        # Handle Dict types
        if cls.is_dict_type(type_annotation):
            schema["type"] = "object"
            args = get_args(type_annotation)
            if len(args) == 2:
                key_type, value_type = args
                # JSON schema doesn't directly support typed keys (must be strings)
                # We can only specify the value type via additionalProperties
                value_schema = cls._type_to_json_schema(value_type, "", seen)
                schema["additionalProperties"] = value_schema
            else:
                # Generic dict
                schema["additionalProperties"] = True
            return schema

        # Handle TypedDict
        if cls.is_typeddict(type_annotation):
            if type_annotation in seen:
                raise ValueError(
                    f"Recursive TypedDict '{type_annotation.__name__}' cannot be "
                    "represented by the structured-output schema"
                )
            seen = seen | {type_annotation}
            schema["type"] = "object"
            properties = {}
            required = []

            annotations, required_keys = cls._typeddict_fields(type_annotation)

            for key, key_type in annotations.items():
                properties[key] = cls._type_to_json_schema(key_type, "", seen)
                if key in required_keys:
                    required.append(key)

            schema["properties"] = properties
            if required:
                schema["required"] = required
            schema["additionalProperties"] = False

            return schema

        # Handle basic types
        if type_annotation in cls.BASIC_TYPES:
            json_type = cls.BASIC_TYPES[type_annotation]
            schema["type"] = json_type

            # Add default items for arrays
            if json_type == "array":
                schema["items"] = {"type": "string"}

            return schema

        # Fallback: treat as string
        schema["type"] = "string"
        return schema

    @classmethod
    def is_strict_mode_compatible(cls, type_annotation: Type) -> Tuple[bool, str]:
        """
        Check if a type annotation is compatible with OpenAI strict mode.

        OpenAI strict mode has specific constraints:
        - No additionalProperties: true
        - All nested properties must be defined
        - No oneOf/anyOf (Union types)
        - No recursive references

        Args:
            type_annotation: Type to check

        Returns:
            tuple: (is_compatible, reason_if_not)

        Example:
            >>> compatible, reason = TypeIntrospector.is_strict_mode_compatible(str)
            >>> assert compatible

            >>> compatible, reason = TypeIntrospector.is_strict_mode_compatible(Dict[str, Any])
            >>> assert not compatible and "additionalProperties" in reason
        """
        try:
            return cls._is_strict_mode_compatible(type_annotation, frozenset())
        except ValueError as exc:
            return False, str(exc)

    @classmethod
    def _is_strict_mode_compatible(
        cls, type_annotation: Type, seen: frozenset
    ) -> Tuple[bool, str]:
        type_annotation = cls._unwrap_value_type(type_annotation)

        # Literal types are compatible
        if cls.is_literal_type(type_annotation):
            return True, ""

        # Union types (except Optional) are NOT compatible (oneOf)
        if cls.is_union_type(type_annotation):
            if cls.is_optional_type(type_annotation):
                # Optional is compatible if inner type is
                inner_type = [
                    t for t in get_args(type_annotation) if t is not type(None)
                ][0]
                return cls._is_strict_mode_compatible(inner_type, seen)
            else:
                return (
                    False,
                    "Union types (anyOf) are not supported in strict mode. Use Optional[T] or separate fields instead.",
                )

        # List types are compatible if item type is
        if cls.is_list_type(type_annotation):
            args = get_args(type_annotation)
            if args:
                return cls._is_strict_mode_compatible(args[0], seen)
            return True, ""

        # Dict types with additionalProperties are NOT compatible
        if cls.is_dict_type(type_annotation):
            args = get_args(type_annotation)
            if not args or len(args) != 2:
                return (
                    False,
                    "Dict[str, Any] requires additionalProperties: true, which is not allowed in strict mode. "
                    "Use TypedDict with explicit fields or List[str] instead.",
                )

            # Type expressions (including native unions) need not have __name__.
            key_name = getattr(args[0], "__name__", str(args[0]))
            value_name = getattr(args[1], "__name__", str(args[1]))
            return (
                False,
                f"Dict[{key_name}, {value_name}] requires additionalProperties, "
                "which is not allowed in strict mode. Use TypedDict or List instead.",
            )

        # TypedDict is compatible if all field types are
        if cls.is_typeddict(type_annotation):
            if type_annotation in seen:
                return (
                    False,
                    "Recursive TypedDict references are not supported in strict mode",
                )
            seen = seen | {type_annotation}
            annotations, _ = cls._typeddict_fields(type_annotation)
            for key, key_type in annotations.items():
                compatible, reason = cls._is_strict_mode_compatible(key_type, seen)
                if not compatible:
                    return False, f"TypedDict field '{key}': {reason}"
            return True, ""

        # Basic types are all compatible
        if type_annotation in cls.BASIC_TYPES:
            return True, ""

        # Unknown type: assume compatible (better to try than block)
        return True, ""
