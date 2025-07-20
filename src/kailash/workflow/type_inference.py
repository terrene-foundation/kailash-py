"""
Connection Type Inference for Kailash Workflows.

This module provides automatic type checking and inference for workflow connections,
ensuring type safety while allowing reasonable type coercions. It integrates with
the port system and connection contracts to provide comprehensive validation.

Design Goals:
1. Type Safety: Catch type mismatches early with clear error messages
2. Flexibility: Allow reasonable type coercions (str->int, list->tuple, etc.)
3. Performance: Fast inference with caching for repeated checks
4. Integration: Work seamlessly with port system and contracts
5. Developer Experience: Clear, actionable error messages

Example Usage:
    from kailash.workflow.type_inference import TypeInferenceEngine

    engine = TypeInferenceEngine()

    # Check type compatibility
    is_compatible = engine.check_compatibility(str, int)  # False
    is_compatible = engine.check_compatibility(str, Union[str, int])  # True

    # Infer connection types
    result = engine.infer_connection_type(source_port, target_port)
    if not result.is_compatible:
        print(f"Type error: {result.error_message}")
"""

import inspect
import logging
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from kailash.nodes.ports import InputPort, OutputPort, Port

logger = logging.getLogger(__name__)


class CoercionRule(Enum):
    """Type coercion rules for automatic type conversion."""

    # Numeric coercions
    INT_TO_FLOAT = "int_to_float"
    FLOAT_TO_INT = "float_to_int"  # May lose precision
    STR_TO_INT = "str_to_int"
    STR_TO_FLOAT = "str_to_float"
    STR_TO_BOOL = "str_to_bool"
    INT_TO_STR = "int_to_str"
    FLOAT_TO_STR = "float_to_str"
    BOOL_TO_STR = "bool_to_str"

    # Collection coercions
    LIST_TO_TUPLE = "list_to_tuple"
    TUPLE_TO_LIST = "tuple_to_list"
    STR_TO_LIST = "str_to_list"  # Split string
    LIST_TO_STR = "list_to_str"  # Join list

    # Dict coercions
    DICT_TO_OBJECT = "dict_to_object"  # For JSON-like data

    # None handling
    NONE_TO_OPTIONAL = "none_to_optional"


@dataclass
class TypeCompatibilityResult:
    """Result of type compatibility checking."""

    is_compatible: bool
    confidence: float  # 0.0 to 1.0
    coercion_rule: Optional[CoercionRule] = None
    error_message: Optional[str] = None
    warning_message: Optional[str] = None

    @property
    def requires_coercion(self) -> bool:
        """Check if this compatibility requires type coercion."""
        return self.coercion_rule is not None

    @property
    def is_perfect_match(self) -> bool:
        """Check if types match exactly without coercion."""
        return self.is_compatible and not self.requires_coercion


@dataclass
class ConnectionInferenceResult:
    """Result of connection type inference."""

    source_type: Type
    target_type: Type
    compatibility: TypeCompatibilityResult
    suggested_fixes: List[str]

    @property
    def is_compatible(self) -> bool:
        """Check if connection is type-compatible."""
        return self.compatibility.is_compatible

    @property
    def error_message(self) -> Optional[str]:
        """Get error message if incompatible."""
        return self.compatibility.error_message


class TypeInferenceEngine:
    """Engine for automatic type inference and compatibility checking."""

    def __init__(self):
        """Initialize the type inference engine."""
        self._compatibility_cache: Dict[Tuple[Type, Type], TypeCompatibilityResult] = {}
        self._coercion_rules = self._build_coercion_rules()

    def _build_coercion_rules(self) -> Dict[Tuple[Type, Type], CoercionRule]:
        """Build the type coercion rules mapping."""
        return {
            # Numeric coercions
            (int, float): CoercionRule.INT_TO_FLOAT,
            (float, int): CoercionRule.FLOAT_TO_INT,
            (str, int): CoercionRule.STR_TO_INT,
            (str, float): CoercionRule.STR_TO_FLOAT,
            (str, bool): CoercionRule.STR_TO_BOOL,
            (int, str): CoercionRule.INT_TO_STR,
            (float, str): CoercionRule.FLOAT_TO_STR,
            (bool, str): CoercionRule.BOOL_TO_STR,
            # Collection coercions
            (list, tuple): CoercionRule.LIST_TO_TUPLE,
            (tuple, list): CoercionRule.TUPLE_TO_LIST,
            (str, list): CoercionRule.STR_TO_LIST,
            (list, str): CoercionRule.LIST_TO_STR,
            # Dict coercions
            (dict, object): CoercionRule.DICT_TO_OBJECT,
        }

    def check_compatibility(
        self, source_type: Type, target_type: Type, allow_coercion: bool = True
    ) -> TypeCompatibilityResult:
        """Check if source type is compatible with target type.

        Args:
            source_type: Source port type
            target_type: Target port type
            allow_coercion: Whether to allow type coercion

        Returns:
            TypeCompatibilityResult with compatibility details
        """
        # Check cache first
        cache_key = (source_type, target_type, allow_coercion)
        if cache_key in self._compatibility_cache:
            return self._compatibility_cache[cache_key]

        result = self._check_compatibility_impl(
            source_type, target_type, allow_coercion
        )

        # Cache the result
        self._compatibility_cache[cache_key] = result

        return result

    def _check_compatibility_impl(
        self, source_type: Type, target_type: Type, allow_coercion: bool
    ) -> TypeCompatibilityResult:
        """Implementation of compatibility checking."""

        # Handle None types
        if source_type is type(None):
            if self._is_optional_type(target_type):
                return TypeCompatibilityResult(
                    is_compatible=True,
                    confidence=1.0,
                    coercion_rule=CoercionRule.NONE_TO_OPTIONAL,
                )
            else:
                return TypeCompatibilityResult(
                    is_compatible=False,
                    confidence=0.0,
                    error_message=f"Cannot assign None to non-optional type {self._get_type_name(target_type)}",
                )

        # Handle Any types
        if source_type is Any or target_type is Any:
            return TypeCompatibilityResult(
                is_compatible=True,
                confidence=0.5,  # Lower confidence for Any
                warning_message="Using Any type reduces type safety",
            )

        # Exact match
        if source_type == target_type:
            return TypeCompatibilityResult(is_compatible=True, confidence=1.0)

        # Check if source is subclass of target
        if self._is_subclass_safe(source_type, target_type):
            return TypeCompatibilityResult(is_compatible=True, confidence=0.9)

        # Handle Union types
        if self._is_union_type(target_type):
            return self._check_union_compatibility(source_type, target_type)

        if self._is_union_type(source_type):
            return self._check_source_union_compatibility(source_type, target_type)

        # Handle Optional types (Union[T, None])
        if self._is_optional_type(target_type):
            inner_type = self._get_optional_inner_type(target_type)
            return self.check_compatibility(source_type, inner_type, allow_coercion)

        # Handle generic types (List[T], Dict[K, V], etc.)
        source_origin = get_origin(source_type)
        target_origin = get_origin(target_type)

        if source_origin and target_origin:
            return self._check_generic_compatibility(
                source_type, target_type, allow_coercion
            )

        # Handle type coercion
        if allow_coercion:
            coercion_result = self._check_coercion_compatibility(
                source_type, target_type
            )
            if coercion_result.is_compatible:
                return coercion_result

        # No compatibility found
        if allow_coercion:
            error_msg = f"Type {self._get_type_name(source_type)} is not compatible with {self._get_type_name(target_type)}"
        else:
            error_msg = f"Type coercion not allowed: {self._get_type_name(source_type)} -> {self._get_type_name(target_type)}"

        return TypeCompatibilityResult(
            is_compatible=False, confidence=0.0, error_message=error_msg
        )

    def _check_union_compatibility(
        self, source_type: Type, target_union: Type
    ) -> TypeCompatibilityResult:
        """Check if source type matches any type in the union."""
        union_args = get_args(target_union)

        best_result = None
        best_confidence = 0.0

        for union_type in union_args:
            result = self.check_compatibility(
                source_type, union_type, allow_coercion=True
            )
            if result.is_compatible and result.confidence > best_confidence:
                best_result = result
                best_confidence = result.confidence

                # Perfect match found
                if result.is_perfect_match:
                    break

        if best_result and best_result.is_compatible:
            return best_result

        union_types = ", ".join(self._get_type_name(t) for t in union_args)
        return TypeCompatibilityResult(
            is_compatible=False,
            confidence=0.0,
            error_message=f"Type {self._get_type_name(source_type)} does not match any type in Union[{union_types}]",
        )

    def _check_source_union_compatibility(
        self, source_union: Type, target_type: Type
    ) -> TypeCompatibilityResult:
        """Check if all types in source union are compatible with target."""
        union_args = get_args(source_union)

        incompatible_types = []
        min_confidence = 1.0
        requires_coercion = False

        for union_type in union_args:
            result = self.check_compatibility(
                union_type, target_type, allow_coercion=True
            )
            if not result.is_compatible:
                incompatible_types.append(self._get_type_name(union_type))
            else:
                min_confidence = min(min_confidence, result.confidence)
                if result.requires_coercion:
                    requires_coercion = True

        if incompatible_types:
            return TypeCompatibilityResult(
                is_compatible=False,
                confidence=0.0,
                error_message=f"Types in source union not compatible with {self._get_type_name(target_type)}: {', '.join(incompatible_types)}",
            )

        return TypeCompatibilityResult(
            is_compatible=True,
            confidence=min_confidence,
            warning_message=(
                "Union source type may require runtime type checking"
                if requires_coercion
                else None
            ),
        )

    def _check_generic_compatibility(
        self, source_type: Type, target_type: Type, allow_coercion: bool
    ) -> TypeCompatibilityResult:
        """Check compatibility of generic types (List[T], Dict[K,V], etc.)."""
        source_origin = get_origin(source_type)
        target_origin = get_origin(target_type)
        source_args = get_args(source_type)
        target_args = get_args(target_type)

        # Origins must be compatible
        if source_origin != target_origin:
            # Check for coercible origins (list <-> tuple)
            coercion_rule = self._coercion_rules.get((source_origin, target_origin))
            if not (allow_coercion and coercion_rule):
                return TypeCompatibilityResult(
                    is_compatible=False,
                    confidence=0.0,
                    error_message=f"Generic type origins incompatible: {source_origin} vs {target_origin}",
                )

        # Check type arguments
        if len(source_args) != len(target_args):
            return TypeCompatibilityResult(
                is_compatible=False,
                confidence=0.0,
                error_message=f"Generic type argument count mismatch: {len(source_args)} vs {len(target_args)}",
            )

        min_confidence = 1.0
        requires_coercion = False

        for source_arg, target_arg in zip(source_args, target_args):
            arg_result = self.check_compatibility(
                source_arg, target_arg, allow_coercion
            )
            if not arg_result.is_compatible:
                return TypeCompatibilityResult(
                    is_compatible=False,
                    confidence=0.0,
                    error_message=f"Generic type argument incompatible: {self._get_type_name(source_arg)} vs {self._get_type_name(target_arg)}",
                )

            min_confidence = min(min_confidence, arg_result.confidence)
            if arg_result.requires_coercion:
                requires_coercion = True

        # Determine final coercion rule
        final_coercion = None
        if source_origin != target_origin:
            final_coercion = self._coercion_rules.get((source_origin, target_origin))
        elif requires_coercion:
            final_coercion = CoercionRule.DICT_TO_OBJECT  # Generic placeholder

        return TypeCompatibilityResult(
            is_compatible=True, confidence=min_confidence, coercion_rule=final_coercion
        )

    def _check_coercion_compatibility(
        self, source_type: Type, target_type: Type
    ) -> TypeCompatibilityResult:
        """Check if types are compatible through coercion."""

        # Direct coercion rule
        coercion_rule = self._coercion_rules.get((source_type, target_type))
        if coercion_rule:
            confidence = self._get_coercion_confidence(coercion_rule)
            warning = self._get_coercion_warning(coercion_rule)

            return TypeCompatibilityResult(
                is_compatible=True,
                confidence=confidence,
                coercion_rule=coercion_rule,
                warning_message=warning,
            )

        # Check if target accepts source through inheritance
        if hasattr(target_type, "__origin__"):
            # Handle generic coercions
            return self._check_generic_coercion(source_type, target_type)

        # Check if source is generic and target is base type that could work
        source_origin = get_origin(source_type)
        if source_origin and not hasattr(target_type, "__origin__"):
            # e.g., List[str] -> tuple
            base_coercion = self._coercion_rules.get((source_origin, target_type))
            if base_coercion:
                return TypeCompatibilityResult(
                    is_compatible=True,
                    confidence=0.7,
                    coercion_rule=base_coercion,
                    warning_message="Generic to base type coercion may lose type information",
                )

        return TypeCompatibilityResult(
            is_compatible=False,
            confidence=0.0,
            error_message=f"No coercion rule available for {self._get_type_name(source_type)} -> {self._get_type_name(target_type)}",
        )

    def _check_generic_coercion(
        self, source_type: Type, target_type: Type
    ) -> TypeCompatibilityResult:
        """Check coercion for generic types."""
        target_origin = get_origin(target_type)

        # list -> List[T] coercion
        if source_type is list and target_origin is list:
            return TypeCompatibilityResult(
                is_compatible=True,
                confidence=0.8,
                coercion_rule=CoercionRule.LIST_TO_TUPLE,  # Placeholder
                warning_message="Generic type coercion may lose type information",
            )

        # dict -> Dict[K, V] coercion
        if source_type is dict and target_origin is dict:
            return TypeCompatibilityResult(
                is_compatible=True,
                confidence=0.8,
                coercion_rule=CoercionRule.DICT_TO_OBJECT,
                warning_message="Generic type coercion may lose type information",
            )

        return TypeCompatibilityResult(is_compatible=False, confidence=0.0)

    def _get_coercion_confidence(self, rule: CoercionRule) -> float:
        """Get confidence level for a coercion rule."""
        confidence_map = {
            # High confidence (lossless)
            CoercionRule.INT_TO_FLOAT: 0.9,
            CoercionRule.INT_TO_STR: 0.9,
            CoercionRule.BOOL_TO_STR: 0.9,
            CoercionRule.LIST_TO_TUPLE: 0.9,
            CoercionRule.TUPLE_TO_LIST: 0.9,
            CoercionRule.NONE_TO_OPTIONAL: 1.0,
            # Medium confidence (may have issues)
            CoercionRule.STR_TO_INT: 0.7,
            CoercionRule.STR_TO_FLOAT: 0.7,
            CoercionRule.STR_TO_BOOL: 0.6,
            CoercionRule.STR_TO_LIST: 0.6,
            CoercionRule.LIST_TO_STR: 0.7,
            # Lower confidence (may lose data)
            CoercionRule.FLOAT_TO_INT: 0.5,
            CoercionRule.FLOAT_TO_STR: 0.8,
            CoercionRule.DICT_TO_OBJECT: 0.6,
        }

        return confidence_map.get(rule, 0.5)

    def _get_coercion_warning(self, rule: CoercionRule) -> Optional[str]:
        """Get warning message for a coercion rule."""
        warning_map = {
            CoercionRule.FLOAT_TO_INT: "Converting float to int may lose precision",
            CoercionRule.STR_TO_INT: "String to int conversion may fail at runtime",
            CoercionRule.STR_TO_FLOAT: "String to float conversion may fail at runtime",
            CoercionRule.STR_TO_BOOL: "String to bool conversion uses truthiness rules",
            CoercionRule.DICT_TO_OBJECT: "Dict to object conversion may lose type safety",
        }

        return warning_map.get(rule)

    def infer_connection_type(
        self, source_port: Port, target_port: Port, allow_coercion: bool = True
    ) -> ConnectionInferenceResult:
        """Infer type compatibility for a connection between ports.

        Args:
            source_port: Source output port
            target_port: Target input port
            allow_coercion: Whether to allow type coercion

        Returns:
            ConnectionInferenceResult with detailed analysis
        """
        # Get port types
        source_type = source_port.type_hint or Any
        target_type = target_port.type_hint or Any

        # Check compatibility
        compatibility = self.check_compatibility(
            source_type, target_type, allow_coercion
        )

        # Generate suggested fixes
        suggested_fixes = []
        if not compatibility.is_compatible:
            suggested_fixes = self._generate_fix_suggestions(
                source_type, target_type, source_port, target_port
            )

        return ConnectionInferenceResult(
            source_type=source_type,
            target_type=target_type,
            compatibility=compatibility,
            suggested_fixes=suggested_fixes,
        )

    def _generate_fix_suggestions(
        self, source_type: Type, target_type: Type, source_port: Port, target_port: Port
    ) -> List[str]:
        """Generate suggestions for fixing type incompatibility."""
        suggestions = []

        # Check if coercion is available
        coercion_rule = self._coercion_rules.get((source_type, target_type))
        if coercion_rule:
            suggestions.append(
                f"Add type coercion: {source_type.__name__} -> {target_type.__name__}"
            )

        # Check if making target optional would help
        if source_type is type(None) and not self._is_optional_type(target_type):
            suggestions.append(
                f"Make target port optional: Optional[{self._get_type_name(target_type)}]"
            )

        # Check if union type would help
        if not self._is_union_type(target_type):
            suggestions.append(
                f"Change target to union: Union[{self._get_type_name(target_type)}, {self._get_type_name(source_type)}]"
            )

        # Check for common mistakes
        if source_type is str and target_type in (int, float):
            suggestions.append("Ensure source string contains valid numeric value")

        if source_type is list and target_type is str:
            suggestions.append("Add string join operation between nodes")

        if source_type is dict and target_type is not dict:
            suggestions.append(
                "Extract specific value from dict or serialize to string"
            )

        # Generic suggestions
        suggestions.append(
            f"Change source port type to {self._get_type_name(target_type)}"
        )
        suggestions.append(
            f"Change target port type to {self._get_type_name(source_type)}"
        )
        suggestions.append("Add intermediate transformation node")

        return suggestions[:5]  # Limit to 5 suggestions

    def _is_union_type(self, type_hint: Type) -> bool:
        """Check if type is a Union."""
        return get_origin(type_hint) is Union

    def _is_optional_type(self, type_hint: Type) -> bool:
        """Check if type is Optional (Union[T, None])."""
        if not self._is_union_type(type_hint):
            return False

        args = get_args(type_hint)
        return len(args) == 2 and type(None) in args

    def _get_optional_inner_type(self, optional_type: Type) -> Type:
        """Get the inner type from Optional[T]."""
        args = get_args(optional_type)
        return next(arg for arg in args if arg is not type(None))

    def _is_subclass_safe(self, source_type: Type, target_type: Type) -> bool:
        """Safely check if source is subclass of target."""
        try:
            if not isinstance(source_type, type) or not isinstance(target_type, type):
                return False
            return issubclass(source_type, target_type)
        except TypeError:
            return False

    def _get_type_name(self, type_hint: Type) -> str:
        """Get human-readable name for a type."""
        if hasattr(type_hint, "__name__"):
            return type_hint.__name__

        origin = get_origin(type_hint)
        if origin:
            args = get_args(type_hint)
            if origin is Union:
                arg_names = [self._get_type_name(arg) for arg in args]
                return f"Union[{', '.join(arg_names)}]"
            elif args:
                arg_names = [self._get_type_name(arg) for arg in args]
                return f"{origin.__name__}[{', '.join(arg_names)}]"
            else:
                return origin.__name__

        return str(type_hint)

    def clear_cache(self) -> None:
        """Clear the compatibility cache."""
        self._compatibility_cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cache_size": len(self._compatibility_cache),
            "cache_hits": getattr(self, "_cache_hits", 0),
            "cache_misses": getattr(self, "_cache_misses", 0),
        }


# Global instance for convenience
_default_engine = None


def get_type_inference_engine() -> TypeInferenceEngine:
    """Get the default type inference engine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = TypeInferenceEngine()
    return _default_engine


def check_connection_compatibility(
    source_port: Port, target_port: Port
) -> ConnectionInferenceResult:
    """Convenience function to check connection compatibility.

    Args:
        source_port: Source output port
        target_port: Target input port

    Returns:
        ConnectionInferenceResult with compatibility analysis
    """
    engine = get_type_inference_engine()
    return engine.infer_connection_type(source_port, target_port)


def validate_workflow_connections(
    connections: List[Tuple[Port, Port]],
) -> List[ConnectionInferenceResult]:
    """Validate all connections in a workflow.

    Args:
        connections: List of (source_port, target_port) tuples

    Returns:
        List of ConnectionInferenceResult for each connection
    """
    engine = get_type_inference_engine()
    results = []

    for source_port, target_port in connections:
        result = engine.infer_connection_type(source_port, target_port)
        results.append(result)

    return results
