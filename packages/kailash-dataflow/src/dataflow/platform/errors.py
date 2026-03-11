"""
Enhanced error handling for DataFlow with actionable guidance.

Transforms cryptic errors into rich, contextual messages that:
- Explain what went wrong
- Identify possible root causes
- Provide actionable solutions
- Link to documentation
- Offer auto-fix capabilities
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class ErrorCode(str, Enum):
    """Standardized error codes for DataFlow issues."""

    # DF-1xx: Parameter Errors
    MISSING_PARAMETER = "DF-101"
    PARAMETER_TYPE_MISMATCH = "DF-102"
    INVALID_PARAMETER_VALUE = "DF-103"
    AUTO_MANAGED_FIELD_CONFLICT = "DF-104"
    PARAMETER_VALIDATION_FAILED = "DF-105"

    # DF-2xx: Connection Errors
    INVALID_CONNECTION_MAPPING = "DF-201"
    CONNECTION_VALIDATION_FAILED = "DF-202"
    CIRCULAR_DEPENDENCY = "DF-203"
    MISSING_CONNECTION = "DF-204"
    CONNECTION_TYPE_MISMATCH = "DF-205"

    # DF-3xx: Migration Errors
    SCHEMA_CONFLICT = "DF-301"
    MIGRATION_FAILED = "DF-302"
    LAZY_LOADING_TIMEOUT = "DF-303"
    MIGRATION_LOCK_FAILED = "DF-304"
    SCHEMA_CACHE_INVALIDATION = "DF-305"

    # DF-4xx: Configuration Errors
    INVALID_DATABASE_URL = "DF-401"
    MULTI_INSTANCE_ISOLATION_VIOLATED = "DF-402"
    INVALID_CONFIGURATION_PARAMETER = "DF-403"
    PROFILE_NOT_FOUND = "DF-404"
    CONFIG_VALIDATION_FAILED = "DF-405"

    # DF-5xx: Runtime Errors
    EVENT_LOOP_CLOSED = "DF-501"
    TRANSACTION_ROLLBACK = "DF-502"
    DATABASE_CONNECTION_LOST = "DF-503"
    NODE_EXECUTION_FAILED = "DF-504"
    WORKFLOW_VALIDATION_FAILED = "DF-505"

    # DF-6xx: Model Errors
    MODEL_NOT_REGISTERED = "DF-601"
    INVALID_MODEL_SCHEMA = "DF-602"
    PRIMARY_KEY_MISSING = "DF-603"
    MODEL_GENERATION_FAILED = "DF-604"

    # DF-7xx: Node Errors
    NODE_NOT_FOUND = (
        "DF-701"  # Previously: Generic node not found (now: Unsafe filter operator)
    )
    NODE_GENERATION_FAILED = "DF-702"  # ReadNode missing ID
    INVALID_NODE_CONFIGURATION = "DF-703"  # ReadNode record not found
    UPDATE_NODE_MISSING_FILTER_ID = "DF-704"  # UpdateNode missing filter id
    DELETE_NODE_MISSING_ID = "DF-705"  # DeleteNode missing id
    UPSERT_NODE_EMPTY_CONFLICT_ON = "DF-706"  # UpsertNode empty conflict_on
    UPSERT_NODE_MISSING_WHERE = "DF-707"  # UpsertNode missing where
    UPSERT_NODE_MISSING_OPERATIONS = "DF-708"  # UpsertNode missing operations
    UNSUPPORTED_DATABASE_TYPE_FOR_UPSERT = (
        "DF-709"  # UpsertNode unsupported database type
    )
    UPSERT_OPERATION_FAILED = "DF-710"  # UpsertNode operation failed


@dataclass
class ErrorSolution:
    """A suggested solution to fix an error."""

    description: str
    code_example: Optional[str] = None
    auto_fixable: bool = False
    fix_function: Optional[Callable] = None


@dataclass
class DataFlowError(Exception):
    """
    Enhanced error with context, documentation, and solutions.

    Attributes:
        error_code: Standardized error code (e.g., DF-101)
        message: User-friendly error description
        context: Contextual information about the error
        causes: Possible root causes
        solutions: Actionable solutions
        docs_url: Link to detailed documentation
        original_error: The original exception that triggered this error
    """

    error_code: ErrorCode
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    causes: list[str] = field(default_factory=list)
    solutions: list[ErrorSolution] = field(default_factory=list)
    docs_url: str = ""
    original_error: Optional[Exception] = None

    def __str__(self) -> str:
        """Format error message for display."""
        return self.enhanced_message()

    def enhanced_message(self, color: bool = True) -> str:
        """
        Generate enhanced error message with context and solutions.

        Args:
            color: Whether to include ANSI color codes

        Returns:
            Formatted error message
        """
        # ANSI color codes
        RED = "\033[91m" if color else ""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []

        # Header
        parts.append(
            f"{RED}❌ DataFlow Error [{self.error_code}]{RESET}: {BOLD}{self.message}{RESET}"
        )
        parts.append("")

        # Context
        if self.context:
            parts.append(f"{BLUE}📍 Context:{RESET}")
            for key, value in self.context.items():
                parts.append(f"   - {key}: {value}")
            parts.append("")

        # Root causes
        if self.causes:
            parts.append(f"{YELLOW}🔍 Possible Root Causes:{RESET}")
            for i, cause in enumerate(self.causes, 1):
                parts.append(f"   {i}. {cause}")
            parts.append("")

        # Solutions
        if self.solutions:
            parts.append(f"{GREEN}💡 Solutions:{RESET}")
            for i, solution in enumerate(self.solutions, 1):
                parts.append(f"   {i}. {solution.description}")
                if solution.code_example:
                    parts.append(f"      {solution.code_example}")
                if solution.auto_fixable:
                    parts.append(f"      {GREEN}✓ Auto-fix available{RESET}")
            parts.append("")

        # Auto-fix command
        auto_fixable_solutions = [s for s in self.solutions if s.auto_fixable]
        if auto_fixable_solutions:
            parts.append(f"{GREEN}🛠️  Auto-Fix Available:{RESET}")
            parts.append(f"   Run: studio.fix_error('{self.error_code}')")
            parts.append("")

        # Documentation
        if self.docs_url:
            parts.append(f"{BLUE}📚 Documentation:{RESET}")
            parts.append(f"   {self.docs_url}")
            parts.append("")

        # Original error
        if self.original_error:
            parts.append(f"{YELLOW}🔧 Original Error:{RESET}")
            parts.append(
                f"   {type(self.original_error).__name__}: {str(self.original_error)}"
            )
            parts.append("")

        return "\n".join(parts)

    def auto_fix(self) -> bool:
        """
        Attempt to automatically fix the error.

        Returns:
            True if auto-fix was successful, False otherwise
        """
        for solution in self.solutions:
            if solution.auto_fixable and solution.fix_function:
                try:
                    solution.fix_function()
                    return True
                except Exception:
                    continue
        return False


@dataclass
class DataFlowWarning:
    """
    Non-critical warning with suggestions for improvement.

    Similar to DataFlowError but for non-blocking issues.
    """

    warning_code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    docs_url: str = ""

    def __str__(self) -> str:
        """Format warning message for display."""
        return self.enhanced_message()

    def enhanced_message(self, color: bool = True) -> str:
        """Generate enhanced warning message."""
        YELLOW = "\033[93m" if color else ""
        BLUE = "\033[94m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []

        # Header
        parts.append(
            f"{YELLOW}⚠️  DataFlow Warning [{self.warning_code}]{RESET}: {BOLD}{self.message}{RESET}"
        )
        parts.append("")

        # Context
        if self.context:
            parts.append(f"{BLUE}📍 Context:{RESET}")
            for key, value in self.context.items():
                parts.append(f"   - {key}: {value}")
            parts.append("")

        # Suggestions
        if self.suggestions:
            parts.append(f"{YELLOW}💡 Suggestions:{RESET}")
            for i, suggestion in enumerate(self.suggestions, 1):
                parts.append(f"   {i}. {suggestion}")
            parts.append("")

        # Documentation
        if self.docs_url:
            parts.append(f"{BLUE}📚 Documentation:{RESET}")
            parts.append(f"   {self.docs_url}")
            parts.append("")

        return "\n".join(parts)


class ErrorEnhancer:
    """
    Enhances standard Python exceptions into DataFlowError instances.

    This class provides methods to catch and transform common DataFlow
    exceptions into rich, actionable error messages.
    """

    BASE_DOCS_URL = "https://docs.kailash.ai/dataflow/errors"
    _error_catalog: Optional[dict] = None  # Lazy-loaded catalog
    _catalog_loaded: bool = False

    @classmethod
    def _load_error_catalog(cls) -> dict:
        """
        Load error catalog from YAML file (lazy loading with caching).

        Returns:
            dict: Error catalog with all error definitions
        """
        if cls._catalog_loaded:
            return cls._error_catalog or {}

        try:
            from pathlib import Path

            import yaml

            # Find error_catalog.yaml in same directory as this file
            catalog_path = Path(__file__).parent / "error_catalog.yaml"

            if not catalog_path.exists():
                print(f"Warning: Error catalog not found at {catalog_path}")
                cls._error_catalog = {}
                cls._catalog_loaded = True
                return {}

            # Load YAML catalog
            with open(catalog_path, "r") as f:
                catalog = yaml.safe_load(f)

            cls._error_catalog = catalog or {}
            cls._catalog_loaded = True

            return cls._error_catalog

        except Exception as e:
            print(f"Warning: Failed to load error catalog: {e}")
            cls._error_catalog = {}
            cls._catalog_loaded = True
            return {}

    @classmethod
    def _get_error_definition(cls, error_code: str) -> Optional[dict]:
        """
        Get error definition from catalog by error code.

        Args:
            error_code: Error code (e.g., "DF-101")

        Returns:
            dict: Error definition or None if not found
        """
        catalog = cls._load_error_catalog()
        return catalog.get(error_code)

    @classmethod
    def _extract_context_from_exception(cls, exc: Exception) -> dict[str, Any]:
        """
        Extract contextual information from exception.

        Args:
            exc: Original exception

        Returns:
            dict: Extracted context information
        """
        import traceback

        context = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }

        # Extract traceback info
        tb = traceback.extract_tb(exc.__traceback__)
        if tb:
            last_frame = tb[-1]
            context["file"] = last_frame.filename
            context["line"] = last_frame.lineno
            context["function"] = last_frame.name

        return context

    @classmethod
    def _build_error_from_catalog(
        cls,
        error_code: str,
        context: dict[str, Any],
        original_error: Optional[Exception] = None,
        custom_message: Optional[str] = None,
    ) -> DataFlowError:
        """
        Build DataFlowError from catalog definition.

        Args:
            error_code: Error code (e.g., "DF-101")
            context: Context dictionary to merge with catalog contexts
            original_error: Original exception
            custom_message: Optional custom message to override catalog title

        Returns:
            DataFlowError: Enhanced error with catalog data
        """
        # Get error definition from catalog
        error_def = cls._get_error_definition(error_code)

        if not error_def:
            # Fallback if catalog not loaded or error not found
            return DataFlowError(
                error_code=ErrorCode.MISSING_PARAMETER,  # Default
                message=custom_message
                or f"Error {error_code}: {context.get('message', 'Unknown error')}",
                context=context,
                causes=[],
                solutions=[],
                docs_url=f"{cls.BASE_DOCS_URL}/{error_code.lower()}",
                original_error=original_error,
            )

        # Extract causes and solutions from catalog
        # Check if they're at top level or nested in contexts
        causes = error_def.get("causes", [])
        solutions_def = error_def.get("solutions", [])

        # If not at top level, try to get from first context
        if not causes and "contexts" in error_def and error_def["contexts"]:
            first_context = error_def["contexts"][0]
            causes = first_context.get("causes", [])
            solutions_def = first_context.get("solutions", [])

        # Build solutions from catalog
        solutions = []
        for sol_def in solutions_def:
            solutions.append(
                ErrorSolution(
                    description=sol_def.get("description", ""),
                    code_example=sol_def.get("code_example")
                    or sol_def.get("code_template", ""),
                    auto_fixable=sol_def.get("auto_fixable", False),
                )
            )

        # Map error code to ErrorCode enum
        error_code_enum = ErrorCode.MISSING_PARAMETER  # Default
        code_mapping = {
            "DF-101": ErrorCode.MISSING_PARAMETER,
            "DF-102": ErrorCode.PARAMETER_TYPE_MISMATCH,
            "DF-103": ErrorCode.INVALID_PARAMETER_VALUE,
            "DF-104": ErrorCode.AUTO_MANAGED_FIELD_CONFLICT,
            "DF-105": ErrorCode.PARAMETER_VALIDATION_FAILED,
            "DF-201": ErrorCode.MISSING_CONNECTION,
            "DF-202": ErrorCode.CONNECTION_TYPE_MISMATCH,
            "DF-203": ErrorCode.INVALID_CONNECTION_MAPPING,
            "DF-204": ErrorCode.CIRCULAR_DEPENDENCY,
            "DF-301": ErrorCode.MIGRATION_FAILED,
            "DF-302": ErrorCode.SCHEMA_CONFLICT,
            "DF-401": ErrorCode.INVALID_DATABASE_URL,
            "DF-402": ErrorCode.MULTI_INSTANCE_ISOLATION_VIOLATED,
            "DF-501": ErrorCode.EVENT_LOOP_CLOSED,
            "DF-601": ErrorCode.MODEL_NOT_REGISTERED,
            "DF-701": ErrorCode.NODE_NOT_FOUND,
            "DF-702": ErrorCode.NODE_GENERATION_FAILED,
            "DF-703": ErrorCode.INVALID_NODE_CONFIGURATION,
            "DF-704": ErrorCode.UPDATE_NODE_MISSING_FILTER_ID,
            "DF-705": ErrorCode.DELETE_NODE_MISSING_ID,
            "DF-706": ErrorCode.UPSERT_NODE_EMPTY_CONFLICT_ON,
            "DF-707": ErrorCode.UPSERT_NODE_MISSING_WHERE,
            "DF-708": ErrorCode.UPSERT_NODE_MISSING_OPERATIONS,
        }
        error_code_enum = code_mapping.get(error_code, ErrorCode.MISSING_PARAMETER)

        return DataFlowError(
            error_code=error_code_enum,
            message=custom_message or error_def.get("title", "Unknown error"),
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=error_def.get(
                "docs_url", f"{cls.BASE_DOCS_URL}/{error_code.lower()}"
            ),
            original_error=original_error,
        )

    # =========================================================================
    # Parameter Error Enhancement Methods (DF-101 to DF-110)
    # =========================================================================

    @classmethod
    def enhance_missing_data_parameter(
        cls,
        node_id: str,
        parameter_name: str,
        node_type: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance missing required parameter error (DF-101).

        Args:
            node_id: Node ID where parameter is missing
            parameter_name: Name of missing parameter
            node_type: Type of node (e.g., "UserCreateNode")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "parameter_name": parameter_name,
        }
        if node_type:
            context["node_type"] = node_type

        # Merge exception context if available
        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-101", context, original_error)

    @classmethod
    def enhance_type_mismatch_error(
        cls,
        node_id: str,
        parameter_name: str,
        expected_type: str,
        received_type: str,
        received_value: Any = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance parameter type mismatch error (DF-102).

        Args:
            node_id: Node ID where type mismatch occurred
            parameter_name: Parameter name with type mismatch
            expected_type: Expected type (e.g., "dict")
            received_type: Received type (e.g., "str")
            received_value: The actual value received
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "parameter_name": parameter_name,
            "expected_type": expected_type,
            "received_type": received_type,
        }
        if received_value is not None:
            context["received_value"] = repr(received_value)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-102", context, original_error)

    @classmethod
    def enhance_invalid_datetime_format(
        cls,
        node_id: str,
        parameter_name: str,
        received_value: str,
        expected_format: str = "ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance invalid datetime format error (DF-103).

        Args:
            node_id: Node ID where datetime format error occurred
            parameter_name: Parameter name with invalid datetime
            received_value: The invalid datetime value
            expected_format: Expected datetime format
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "parameter_name": parameter_name,
            "received_value": received_value,
            "expected_format": expected_format,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-103", context, original_error)

    @classmethod
    def enhance_auto_managed_field_conflict(
        cls,
        node_id: str,
        field_name: str,
        operation: str = "CREATE",
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance auto-managed field conflict error (DF-104).

        Args:
            node_id: Node ID where conflict occurred
            field_name: Auto-managed field name (created_at, updated_at, id)
            operation: Operation type (CREATE, UPDATE)
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions and auto-fix
        """
        context = {
            "node_id": node_id,
            "field_name": field_name,
            "operation": operation,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-104", context, original_error)

    @classmethod
    def enhance_missing_required_field(
        cls,
        node_id: str,
        field_name: str,
        operation: str,
        model_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance missing required field error (DF-105).

        Args:
            node_id: Node ID where field is missing
            field_name: Required field name (often 'id')
            operation: Operation type (CREATE, UPDATE)
            model_name: Model name (e.g., "User")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "field_name": field_name,
            "operation": operation,
        }
        if model_name:
            context["model_name"] = model_name

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-105", context, original_error)

    @classmethod
    def enhance_parameter_name_mismatch(
        cls,
        source_node: str,
        target_node: str,
        parameter_name: str,
        available_params: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance parameter name mismatch error (DF-106).

        Args:
            source_node: Source node ID
            target_node: Target node ID
            parameter_name: Mismatched parameter name
            available_params: List of available parameter names
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "target_node": target_node,
            "parameter_name": parameter_name,
        }
        if available_params:
            context["available_params"] = ", ".join(available_params)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-106", context, original_error)

    @classmethod
    def enhance_empty_parameter_value(
        cls,
        node_id: str,
        parameter_name: str,
        received_value: Any,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance empty parameter value error (DF-107).

        Args:
            node_id: Node ID where empty value occurred
            parameter_name: Parameter name with empty value
            received_value: The empty value (empty string, list, None)
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "parameter_name": parameter_name,
            "received_value": repr(received_value),
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-107", context, original_error)

    @classmethod
    def enhance_invalid_parameter_structure(
        cls,
        node_id: str,
        parameter_name: str,
        expected_structure: str,
        received_structure: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance invalid parameter structure error (DF-108).

        Args:
            node_id: Node ID where structure mismatch occurred
            parameter_name: Parameter with invalid structure
            expected_structure: Expected structure (e.g., "filter + fields")
            received_structure: Received structure (e.g., "flat fields")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "parameter_name": parameter_name,
            "expected_structure": expected_structure,
            "received_structure": received_structure,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-108", context, original_error)

    @classmethod
    def enhance_parameter_validation_failed(
        cls,
        node_id: str,
        parameter_name: str,
        validation_rule: str,
        received_value: Any,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance parameter validation failed error (DF-109).

        Args:
            node_id: Node ID where validation failed
            parameter_name: Parameter that failed validation
            validation_rule: Validation rule that failed (e.g., "email format")
            received_value: The value that failed validation
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "parameter_name": parameter_name,
            "validation_rule": validation_rule,
            "received_value": repr(received_value),
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-109", context, original_error)

    @classmethod
    def enhance_unexpected_parameter(
        cls,
        node_id: str,
        parameter_name: str,
        node_type: str,
        accepted_params: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance unexpected parameter error (DF-110).

        Args:
            node_id: Node ID where unexpected parameter was found
            parameter_name: Unexpected parameter name
            node_type: Node type (e.g., "UserCreateNode")
            accepted_params: List of accepted parameter names
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "parameter_name": parameter_name,
            "node_type": node_type,
        }
        if accepted_params:
            context["accepted_params"] = ", ".join(accepted_params)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-110", context, original_error)

    # =============================================================================
    # Connection Error Enhancement Methods (DF-201 to DF-210)
    # =============================================================================

    @classmethod
    def enhance_missing_connection(
        cls,
        source_node: str,
        target_node: str,
        required_parameter: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance missing connection error (DF-201).

        Args:
            source_node: Source node ID
            target_node: Target node ID
            required_parameter: Required parameter that needs connection
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "target_node": target_node,
            "required_parameter": required_parameter,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-201", context, original_error)

    @classmethod
    def enhance_connection_type_mismatch(
        cls,
        source_node: str,
        source_param: str,
        source_type: str,
        target_node: str,
        target_param: str,
        target_type: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance connection type mismatch error (DF-202).

        Args:
            source_node: Source node ID
            source_param: Source parameter name
            source_type: Source parameter type (e.g., "dict", "list", "str")
            target_node: Target node ID
            target_param: Target parameter name
            target_type: Target parameter type
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "source_param": source_param,
            "source_type": source_type,
            "target_node": target_node,
            "target_param": target_param,
            "target_type": target_type,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-202", context, original_error)

    @classmethod
    def enhance_dot_notation_navigation_failed(
        cls,
        source_node: str,
        source_param: str,
        dot_path: str,
        navigation_error: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance dot notation navigation failed error (DF-203).

        Args:
            source_node: Source node ID
            source_param: Source parameter name
            dot_path: Dot notation path that failed (e.g., "output.user.name")
            navigation_error: Navigation error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "source_param": source_param,
            "dot_path": dot_path,
        }
        if navigation_error:
            context["navigation_error"] = navigation_error

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-203", context, original_error)

    @classmethod
    def enhance_circular_connection(
        cls,
        source_node: str,
        target_node: str,
        cycle_path: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance circular connection error (DF-204).

        Args:
            source_node: Source node ID where cycle detected
            target_node: Target node ID
            cycle_path: Full cycle path (e.g., "A → B → C → A")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "target_node": target_node,
        }
        if cycle_path:
            context["cycle_path"] = cycle_path

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-204", context, original_error)

    @classmethod
    def enhance_invalid_source_parameter(
        cls,
        source_node: str,
        source_param: str,
        available_params: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance invalid source parameter error (DF-205).

        Args:
            source_node: Source node ID
            source_param: Invalid source parameter name
            available_params: List of available source parameters
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "source_param": source_param,
        }
        if available_params:
            context["available_params"] = ", ".join(available_params)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-205", context, original_error)

    @classmethod
    def enhance_invalid_target_parameter(
        cls,
        target_node: str,
        target_param: str,
        available_params: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance invalid target parameter error (DF-206).

        Args:
            target_node: Target node ID
            target_param: Invalid target parameter name
            available_params: List of available target parameters
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "target_node": target_node,
            "target_param": target_param,
        }
        if available_params:
            context["available_params"] = ", ".join(available_params)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-206", context, original_error)

    @classmethod
    def enhance_duplicate_connection(
        cls,
        source_node: str,
        source_param: str,
        target_node: str,
        target_param: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance duplicate connection error (DF-207).

        Args:
            source_node: Source node ID
            source_param: Source parameter name
            target_node: Target node ID
            target_param: Target parameter name
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "source_param": source_param,
            "target_node": target_node,
            "target_param": target_param,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-207", context, original_error)

    @classmethod
    def enhance_incompatible_connection(
        cls,
        source_node: str,
        target_node: str,
        constraint_violated: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance incompatible connection error (DF-208).

        Args:
            source_node: Source node ID
            target_node: Target node ID
            constraint_violated: Description of constraint violated
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "target_node": target_node,
            "constraint_violated": constraint_violated,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-208", context, original_error)

    @classmethod
    def enhance_missing_input_connection(
        cls,
        node_id: str,
        required_inputs: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance missing input connection error (DF-209).

        Args:
            node_id: Node ID missing required input
            required_inputs: List of required input parameter names
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
        }
        if required_inputs:
            context["required_inputs"] = ", ".join(required_inputs)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-209", context, original_error)

    @classmethod
    def enhance_unused_connection(
        cls,
        source_node: str,
        target_node: str,
        unused_param: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance unused connection error (DF-210).

        Args:
            source_node: Source node ID
            target_node: Target node ID
            unused_param: Parameter name that's not being used
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "source_node": source_node,
            "target_node": target_node,
            "unused_param": unused_param,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-210", context, original_error)

    # =============================================================================
    # Runtime Error Enhancement Methods (DF-501 to DF-508)
    # =============================================================================

    @classmethod
    def enhance_event_loop_closed(
        cls,
        node_id: str,
        execution_mode: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance event loop closed error (DF-501).

        Args:
            node_id: Node ID where event loop closed
            execution_mode: Execution mode (sync/async)
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
        }
        if execution_mode:
            context["execution_mode"] = execution_mode

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-501", context, original_error)

    @classmethod
    def enhance_async_runtime_error(
        cls,
        node_id: str,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance async runtime error (DF-502).

        Args:
            node_id: Node ID where async error occurred
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
        }
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-502", context, original_error)

    @classmethod
    def enhance_node_execution_timeout(
        cls,
        node_id: str,
        timeout_seconds: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance node execution timeout error (DF-503).

        Args:
            node_id: Node ID that timed out
            timeout_seconds: Timeout duration in seconds
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
        }
        if timeout_seconds is not None:
            context["timeout_seconds"] = timeout_seconds

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-503", context, original_error)

    @classmethod
    def enhance_workflow_execution_failed(
        cls,
        workflow_id: str,
        failed_node: Optional[str] = None,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance workflow execution failed error (DF-504).

        Args:
            workflow_id: Workflow ID
            failed_node: Node ID where workflow failed
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "workflow_id": workflow_id,
        }
        if failed_node:
            context["failed_node"] = failed_node
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-504", context, original_error)

    @classmethod
    def enhance_resource_exhaustion(
        cls,
        resource_type: str,
        current_usage: Optional[str] = None,
        limit: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance resource exhaustion error (DF-505).

        Args:
            resource_type: Type of resource exhausted (memory, connections, etc.)
            current_usage: Current resource usage
            limit: Resource limit
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "resource_type": resource_type,
        }
        if current_usage:
            context["current_usage"] = current_usage
        if limit:
            context["limit"] = limit

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-505", context, original_error)

    @classmethod
    def enhance_connection_pool_error(
        cls,
        pool_status: Optional[str] = None,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance connection pool error (DF-506).

        Args:
            pool_status: Connection pool status
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {}
        if pool_status:
            context["pool_status"] = pool_status
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-506", context, original_error)

    @classmethod
    def enhance_transaction_error(
        cls,
        operation: str,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance transaction error (DF-507).

        Args:
            operation: Operation that failed (commit, rollback, etc.)
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "operation": operation,
        }
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-507", context, original_error)

    @classmethod
    def enhance_runtime_configuration_error(
        cls,
        parameter_name: str,
        parameter_value: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance runtime configuration error (DF-508).

        Args:
            parameter_name: Configuration parameter name
            parameter_value: Invalid parameter value
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "parameter_name": parameter_name,
        }
        if parameter_value is not None:
            context["parameter_value"] = str(parameter_value)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-508", context, original_error)

    # =============================================================================
    # Migration Error Enhancement Methods (DF-301 to DF-308)
    # =============================================================================

    @classmethod
    def enhance_schema_migration_failed(
        cls,
        model_name: str,
        operation: str,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance schema migration failed error (DF-301).

        Args:
            model_name: Model name
            operation: Migration operation (add_column, drop_table, etc.)
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
            "operation": operation,
        }
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-301", context, original_error)

    @classmethod
    def enhance_table_not_found(
        cls,
        table_name: str,
        model_name: str,
        database_url: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance table not found error (DF-302).

        Args:
            table_name: Table name
            model_name: Model name
            database_url: Database URL (optional, may contain sensitive info)
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "table_name": table_name,
            "model_name": model_name,
        }
        if database_url:
            # Sanitize database URL to hide credentials
            import re

            sanitized_url = re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", database_url)
            context["database_url"] = sanitized_url

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-302", context, original_error)

    @classmethod
    def enhance_column_not_found(
        cls,
        table_name: str,
        column_name: str,
        field_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance column not found error (DF-303).

        Args:
            table_name: Table name
            column_name: Column name
            field_name: Field name in model (if different from column)
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "table_name": table_name,
            "column_name": column_name,
        }
        if field_name:
            context["field_name"] = field_name

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-303", context, original_error)

    @classmethod
    def enhance_constraint_violation(
        cls,
        constraint_type: str,
        column_name: Optional[str] = None,
        value: Optional[str] = None,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance database constraint violation error (DF-304).

        Args:
            constraint_type: Constraint type (unique, not_null, foreign_key, check)
            column_name: Column name
            value: Value that violated constraint
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "constraint_type": constraint_type,
        }
        if column_name:
            context["column_name"] = column_name
        if value is not None:
            context["value"] = str(value)
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-304", context, original_error)

    @classmethod
    def enhance_migration_rollback_failed(
        cls,
        model_name: str,
        migration_step: str,
        rollback_error: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance migration rollback failed error (DF-305).

        Args:
            model_name: Model name
            migration_step: Migration step that failed
            rollback_error: Rollback error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
            "migration_step": migration_step,
        }
        if rollback_error:
            context["rollback_error"] = rollback_error

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-305", context, original_error)

    @classmethod
    def enhance_schema_sync_error(
        cls,
        model_name: str,
        expected_schema: Optional[str] = None,
        actual_schema: Optional[str] = None,
        differences: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance schema sync error (DF-306).

        Args:
            model_name: Model name
            expected_schema: Expected schema definition
            actual_schema: Actual database schema
            differences: Schema differences description
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
        }
        if expected_schema:
            context["expected_schema"] = expected_schema
        if actual_schema:
            context["actual_schema"] = actual_schema
        if differences:
            context["differences"] = differences

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-306", context, original_error)

    @classmethod
    def enhance_alembic_error(
        cls,
        migration_file: Optional[str] = None,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance Alembic migration error (DF-307).

        Args:
            migration_file: Migration file path
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {}
        if migration_file:
            context["migration_file"] = migration_file
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-307", context, original_error)

    @classmethod
    def enhance_database_connection_error(
        cls,
        database_url: Optional[str] = None,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance database connection error (DF-308).

        Args:
            database_url: Database URL (credentials will be sanitized)
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {}
        if database_url:
            # Sanitize database URL to hide credentials
            import re

            sanitized_url = re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", database_url)
            context["database_url"] = sanitized_url
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-308", context, original_error)

    # =============================================================================
    # Configuration Error Enhancement Methods (DF-401 to DF-408)
    # =============================================================================

    @classmethod
    def enhance_invalid_database_url(
        cls,
        database_url: str,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance invalid database URL error (DF-401).

        Args:
            database_url: Invalid database URL (credentials will be sanitized)
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        # Sanitize database URL to hide credentials
        import re

        sanitized_url = re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", database_url)

        context = {
            "database_url": sanitized_url,
        }
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-401", context, original_error)

    @classmethod
    def enhance_multi_instance_isolation_violated(
        cls,
        instance_1: str,
        instance_2: str,
        conflict: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance multi-instance isolation violated error (DF-402).

        Args:
            instance_1: First DataFlow instance identifier
            instance_2: Second DataFlow instance identifier
            conflict: Description of the conflict
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "instance_1": instance_1,
            "instance_2": instance_2,
        }
        if conflict:
            context["conflict"] = conflict

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-402", context, original_error)

    @classmethod
    def enhance_auto_migrate_disabled(
        cls,
        model_name: str,
        operation: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance auto-migrate disabled error (DF-403).

        Args:
            model_name: Model name
            operation: Operation that requires migration
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
        }
        if operation:
            context["operation"] = operation

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-403", context, original_error)

    @classmethod
    def enhance_existing_schema_mode_conflict(
        cls,
        operation: str,
        model_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance existing schema mode conflict error (DF-404).

        Args:
            operation: Operation that conflicts with existing_schema_mode
            model_name: Model name
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "operation": operation,
        }
        if model_name:
            context["model_name"] = model_name

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-404", context, original_error)

    @classmethod
    def enhance_pool_configuration_error(
        cls,
        parameter_name: str,
        parameter_value: Optional[str] = None,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance connection pool configuration error (DF-405).

        Args:
            parameter_name: Pool configuration parameter name
            parameter_value: Invalid parameter value
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "parameter_name": parameter_name,
        }
        if parameter_value is not None:
            context["parameter_value"] = str(parameter_value)
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-405", context, original_error)

    @classmethod
    def enhance_environment_variable_missing(
        cls,
        variable_name: str,
        purpose: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance environment variable missing error (DF-406).

        Args:
            variable_name: Missing environment variable name
            purpose: Purpose of the variable
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "variable_name": variable_name,
        }
        if purpose:
            context["purpose"] = purpose

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-406", context, original_error)

    @classmethod
    def enhance_security_config_error(
        cls, security_issue: str, original_error: Optional[Exception] = None
    ) -> DataFlowError:
        """
        Enhance security configuration error (DF-407).

        Args:
            security_issue: Description of security issue
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "security_issue": security_issue,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-407", context, original_error)

    @classmethod
    def enhance_monitoring_config_error(
        cls,
        monitoring_component: str,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance monitoring configuration error (DF-408).

        Args:
            monitoring_component: Monitoring component (health, metrics, etc.)
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "monitoring_component": monitoring_component,
        }
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-408", context, original_error)

    # =============================================================================
    # Model Error Enhancement Methods (DF-601 to DF-606)
    # =============================================================================

    @classmethod
    def enhance_primary_key_not_id(
        cls,
        model_name: str,
        primary_key_field: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance primary key not named 'id' error (DF-601).

        Args:
            model_name: Model name
            primary_key_field: Current primary key field name (e.g., "user_id")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
            "primary_key_field": primary_key_field,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-601", context, original_error)

    @classmethod
    def enhance_create_vs_update_node_confusion(
        cls,
        node_type: str,
        received_structure: Optional[str] = None,
        expected_structure: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance CreateNode vs UpdateNode pattern confusion error (DF-602).

        Args:
            node_type: Node type (CreateNode, UpdateNode, etc.)
            received_structure: Received parameter structure
            expected_structure: Expected parameter structure
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_type": node_type,
        }
        if received_structure:
            context["received_structure"] = received_structure
        if expected_structure:
            context["expected_structure"] = expected_structure

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-602", context, original_error)

    @classmethod
    def enhance_model_not_registered(
        cls,
        model_name: str,
        dataflow_instance: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance model not registered error (DF-603).

        Args:
            model_name: Model name
            dataflow_instance: DataFlow instance identifier
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
        }
        if dataflow_instance:
            context["dataflow_instance"] = dataflow_instance

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-603", context, original_error)

    @classmethod
    def enhance_invalid_model_definition(
        cls,
        model_name: str,
        validation_error: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance invalid model definition error (DF-604).

        Args:
            model_name: Model name
            validation_error: Validation error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
        }
        if validation_error:
            context["validation_error"] = validation_error

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-604", context, original_error)

    @classmethod
    def enhance_model_relationship_error(
        cls,
        model_name: str,
        relationship_field: str,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance model relationship error (DF-605).

        Args:
            model_name: Model name
            relationship_field: Relationship field name
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
            "relationship_field": relationship_field,
        }
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-605", context, original_error)

    @classmethod
    def enhance_model_field_type_error(
        cls,
        model_name: str,
        field_name: str,
        field_type: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance model field type error (DF-606).

        Args:
            model_name: Model name
            field_name: Field name
            field_type: Invalid field type
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
            "field_name": field_name,
            "field_type": field_type,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-606", context, original_error)

    # =============================================================================
    # Node Error Enhancement Methods (DF-701 to DF-705)
    # =============================================================================

    @classmethod
    def enhance_node_not_found(
        cls,
        node_id: str,
        available_nodes: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance node not found error (DF-701).

        Args:
            node_id: Node ID that wasn't found
            available_nodes: List of available node IDs
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
        }
        if available_nodes:
            context["available_nodes"] = ", ".join(available_nodes)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-701", context, original_error)

    @classmethod
    def enhance_invalid_node_type(
        cls,
        node_type: str,
        available_types: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance invalid node type error (DF-702).

        Args:
            node_type: Invalid node type
            available_types: List of available node types
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_type": node_type,
        }
        if available_types:
            context["available_types"] = ", ".join(available_types)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-702", context, original_error)

    @classmethod
    def enhance_node_generation_failed(
        cls,
        model_name: str,
        generation_error: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance node generation failed error (DF-703).

        Args:
            model_name: Model name
            generation_error: Generation error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "model_name": model_name,
        }
        if generation_error:
            context["generation_error"] = generation_error

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-703", context, original_error)

    @classmethod
    def enhance_duplicate_node_id(
        cls,
        node_id: str,
        node_type_1: str,
        node_type_2: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance duplicate node ID error (DF-704).

        Args:
            node_id: Duplicate node ID
            node_type_1: First node type
            node_type_2: Second node type
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_id": node_id,
            "node_type_1": node_type_1,
            "node_type_2": node_type_2,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-704", context, original_error)

    @classmethod
    def enhance_node_initialization_failed(
        cls,
        node_type: str,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance node initialization failed error (DF-705).

        Args:
            node_type: Node type
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "node_type": node_type,
        }
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-705", context, original_error)

    # =============================================================================
    # Workflow Error Enhancement Methods (DF-801 to DF-805)
    # =============================================================================

    @classmethod
    def enhance_workflow_build_failed(
        cls,
        workflow_id: Optional[str] = None,
        error_message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance workflow build failed error (DF-801).

        Args:
            workflow_id: Workflow ID
            error_message: Error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {}
        if workflow_id:
            context["workflow_id"] = workflow_id
        if error_message:
            context["error_message"] = error_message

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-801", context, original_error)

    @classmethod
    def enhance_workflow_validation_failed(
        cls,
        validation_errors: Optional[list] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance workflow validation failed error (DF-802).

        Args:
            validation_errors: List of validation error messages
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {}
        if validation_errors:
            context["validation_errors"] = "\n".join(validation_errors)

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-802", context, original_error)

    @classmethod
    def enhance_cyclic_dependency(
        cls,
        cycle_path: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance cyclic dependency error (DF-803).

        Args:
            cycle_path: Cycle path (e.g., "A → B → C → A")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {}
        if cycle_path:
            context["cycle_path"] = cycle_path

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-803", context, original_error)

    @classmethod
    def enhance_invalid_workflow_structure(
        cls, structure_issue: str, original_error: Optional[Exception] = None
    ) -> DataFlowError:
        """
        Enhance invalid workflow structure error (DF-804).

        Args:
            structure_issue: Description of structure issue
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {
            "structure_issue": structure_issue,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-804", context, original_error)

    @classmethod
    def enhance_workflow_serialization_failed(
        cls,
        serialization_error: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance workflow serialization failed error (DF-805).

        Args:
            serialization_error: Serialization error message
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with solutions
        """
        context = {}
        if serialization_error:
            context["serialization_error"] = serialization_error

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        return cls._build_error_from_catalog("DF-805", context, original_error)

    @classmethod
    def enhance_parameter_error(
        cls,
        node_id: str,
        parameter_name: str,
        expected_type: Optional[str] = None,
        received_value: Any = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """Enhance a parameter-related error."""
        context = {
            "Node": node_id,
            "Parameter": parameter_name,
        }

        if expected_type:
            context["Expected Type"] = expected_type
        if received_value is not None:
            context["Received"] = repr(received_value)

        causes = [
            "Connection not established from previous node",
            f"Parameter name mismatch in connection (using wrong name instead of '{parameter_name}')",
            "Empty input passed to workflow",
            "Previous node didn't produce expected output",
        ]

        solutions = [
            ErrorSolution(
                description=f"Add connection to provide '{parameter_name}' parameter",
                code_example=f'workflow.add_connection("source_node", "output_field", "{node_id}", "{parameter_name}")',
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Check that source node is producing the expected output",
                code_example='inspector.node("source_node").connections_out',
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Verify workflow inputs contain required data",
                code_example='runtime.execute(workflow.build(), inputs={"field": value})',
                auto_fixable=False,
            ),
        ]

        return DataFlowError(
            error_code=ErrorCode.MISSING_PARAMETER,
            message=f"Missing required parameter '{parameter_name}' in node '{node_id}'",
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{cls.BASE_DOCS_URL}/df-101",
            original_error=original_error,
        )

    @classmethod
    def enhance_connection_error(
        cls,
        source_node: str,
        target_node: str,
        source_param: str,
        target_param: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """Enhance a connection-related error."""
        context = {
            "Source Node": source_node,
            "Source Parameter": source_param,
            "Target Node": target_node,
            "Target Parameter": target_param,
        }

        causes = [
            "Source parameter doesn't exist in source node",
            "Target parameter doesn't exist in target node",
            "Type mismatch between source and target parameters",
            "Circular dependency in workflow",
        ]

        solutions = [
            ErrorSolution(
                description="Verify source node has the specified output parameter",
                code_example=f'inspector.node("{source_node}").output_params',
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Verify target node accepts the specified input parameter",
                code_example=f'inspector.node("{target_node}").input_params',
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Check for circular dependencies in workflow",
                code_example="validator.check_circular_dependencies()",
                auto_fixable=False,
            ),
        ]

        return DataFlowError(
            error_code=ErrorCode.CONNECTION_VALIDATION_FAILED,
            message=f"Invalid connection from '{source_node}.{source_param}' to '{target_node}.{target_param}'",
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{cls.BASE_DOCS_URL}/df-202",
            original_error=original_error,
        )

    @classmethod
    def enhance_migration_error(
        cls, model_name: str, operation: str, original_error: Optional[Exception] = None
    ) -> DataFlowError:
        """Enhance a migration-related error."""
        context = {
            "Model": model_name,
            "Operation": operation,
        }

        causes = [
            "Schema conflict with existing database schema",
            "Migration lock held by another process",
            "Database connection lost during migration",
            "Invalid model schema definition",
        ]

        solutions = [
            ErrorSolution(
                description="Clear schema cache and retry",
                code_example="studio.clear_schema_cache()",
                auto_fixable=True,
            ),
            ErrorSolution(
                description="Check for migration locks",
                code_example="studio.check_migration_locks()",
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Verify database connection",
                code_example="studio.test_connection()",
                auto_fixable=False,
            ),
        ]

        return DataFlowError(
            error_code=ErrorCode.MIGRATION_FAILED,
            message=f"Migration failed for model '{model_name}' during {operation}",
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{cls.BASE_DOCS_URL}/df-302",
            original_error=original_error,
        )

    @classmethod
    def enhance_event_loop_error(
        cls, node_id: str, original_error: Optional[Exception] = None
    ) -> DataFlowError:
        """Enhance event loop closed error."""
        context = {"Node": node_id, "Error": "Event loop closed during node execution"}

        causes = [
            "AsyncLocalRuntime used in synchronous context",
            "Event loop closed prematurely",
            "Sequential workflow execution with async runtime",
            "Mixing sync and async execution patterns",
        ]

        solutions = [
            ErrorSolution(
                description="Use LocalRuntime for synchronous execution",
                code_example="runtime = LocalRuntime()",
                auto_fixable=True,
            ),
            ErrorSolution(
                description="Use AsyncLocalRuntime with proper async context",
                code_example="runtime = AsyncLocalRuntime()\nawait runtime.execute_workflow_async(...)",
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Use get_runtime() helper for automatic selection",
                code_example='runtime = get_runtime("sync")  # or "async"',
                auto_fixable=True,
            ),
        ]

        return DataFlowError(
            error_code=ErrorCode.EVENT_LOOP_CLOSED,
            message=f"Event loop closed during execution of node '{node_id}'",
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{cls.BASE_DOCS_URL}/df-501",
            original_error=original_error,
        )

    @classmethod
    def enhance_configuration_error(
        cls,
        parameter_name: str,
        parameter_value: Any,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """Enhance a configuration-related error."""
        context = {
            "Parameter": parameter_name,
            "Value": repr(parameter_value),
        }

        causes = [
            "Invalid parameter value",
            "Parameter type mismatch",
            "Required parameter missing",
            "Conflicting configuration parameters",
        ]

        solutions = [
            ErrorSolution(
                description="Use configuration profile for best practices",
                code_example='studio = DataFlowStudio.quick_start(profile="production")',
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Validate configuration before initialization",
                code_example="validator.validate_config(config)",
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Check configuration documentation",
                code_example=f"# See: {cls.BASE_DOCS_URL}/configuration",
                auto_fixable=False,
            ),
        ]

        return DataFlowError(
            error_code=ErrorCode.INVALID_CONFIGURATION_PARAMETER,
            message=f"Invalid configuration parameter '{parameter_name}'",
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{cls.BASE_DOCS_URL}/df-403",
            original_error=original_error,
        )

    @classmethod
    def enhance_model_error(
        cls, model_name: str, issue: str, original_error: Optional[Exception] = None
    ) -> DataFlowError:
        """Enhance a model-related error."""
        context = {
            "Model": model_name,
            "Issue": issue,
        }

        causes = [
            "Model not registered with DataFlow",
            "Invalid model schema definition",
            "Missing primary key definition",
            "Model class not properly decorated",
        ]

        solutions = [
            ErrorSolution(
                description="Register model with DataFlow",
                code_example=f"db.register_model({model_name})",
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Verify model schema has primary key",
                code_example="id = Column(Integer, primary_key=True)",
                auto_fixable=False,
            ),
            ErrorSolution(
                description="Check model definition",
                code_example=f'inspector.model("{model_name}").schema',
                auto_fixable=False,
            ),
        ]

        return DataFlowError(
            error_code=ErrorCode.MODEL_NOT_REGISTERED,
            message=f"Model '{model_name}' is not registered or has invalid schema",
            context=context,
            causes=causes,
            solutions=solutions,
            docs_url=f"{cls.BASE_DOCS_URL}/df-601",
            original_error=original_error,
        )

    # ========================================================================
    # Node-Specific Error Enhancements (DF-701 to DF-708)
    # ========================================================================

    @classmethod
    def enhance_unsafe_filter_operator(
        cls,
        model_name: str,
        field_name: str,
        operator: str,
        operation: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance unsafe filter operator error (DF-701).

        Args:
            model_name: Model name (e.g., "User")
            field_name: Field name with unsafe operator
            operator: The unsafe operator used (e.g., "$exec")
            operation: Operation type (e.g., "list", "update")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with SQL injection prevention guidance
        """
        context = {
            "model_name": model_name,
            "field_name": field_name,
            "operator": operator,
            "operation": operation,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = f"Unsafe filter operator '{operator}' on {model_name}.{field_name} in {operation} operation"

        return cls._build_error_from_catalog(
            "DF-701", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_async_context_error(
        cls,
        node_class: str,
        method: str,
        correct_method: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance sync run() in async context error (DF-501).

        Args:
            node_class: Node class name (e.g., "AsyncSQLDatabaseNode")
            method: Method called (e.g., "run")
            correct_method: Correct method to use (e.g., "async_run")
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with async guidance
        """
        context = {
            "node_class": node_class,
            "method": method,
            "correct_method": correct_method,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = f"Cannot use {node_class}.{method}() in async context - use {correct_method}() instead"

        return cls._build_error_from_catalog(
            "DF-501", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_read_node_missing_id(
        cls,
        model_name: str,
        node_id: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance ReadNode missing id/record_id error (DF-702).

        Args:
            model_name: Model name (e.g., "User")
            node_id: Node ID in workflow
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with ReadNode usage guidance
        """
        context = {
            "model_name": model_name,
            "node_id": node_id,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = f"{model_name}ReadNode requires 'id' or 'record_id' parameter (node: {node_id})"

        return cls._build_error_from_catalog(
            "DF-702", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_read_node_not_found(
        cls,
        model_name: str,
        record_id: str,
        node_id: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance ReadNode record not found error (DF-703).

        Args:
            model_name: Model name (e.g., "User")
            record_id: Record ID that wasn't found
            node_id: Node ID in workflow
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with record verification guidance
        """
        context = {
            "model_name": model_name,
            "record_id": record_id,
            "node_id": node_id,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = (
            f"{model_name} record '{record_id}' not found (node: {node_id})"
        )

        return cls._build_error_from_catalog(
            "DF-703", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_update_node_missing_filter_id(
        cls,
        model_name: str,
        node_id: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance UpdateNode missing filter id error (DF-704).

        Args:
            model_name: Model name (e.g., "User")
            node_id: Node ID in workflow
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with UpdateNode filter guidance
        """
        context = {
            "model_name": model_name,
            "node_id": node_id,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = (
            f"{model_name}UpdateNode requires 'id' in filter (node: {node_id})"
        )

        return cls._build_error_from_catalog(
            "DF-704", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_delete_node_missing_id(
        cls,
        model_name: str,
        node_id: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance DeleteNode missing id/record_id error (DF-705).

        Args:
            model_name: Model name (e.g., "User")
            node_id: Node ID in workflow
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with data loss prevention guidance
        """
        context = {
            "model_name": model_name,
            "node_id": node_id,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = f"{model_name}DeleteNode requires 'id' or 'record_id' parameter (node: {node_id})"

        return cls._build_error_from_catalog(
            "DF-705", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_upsert_node_empty_conflict_on(
        cls,
        model_name: str,
        node_id: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance UpsertNode empty conflict_on list error (DF-706).

        Args:
            model_name: Model name (e.g., "User")
            node_id: Node ID in workflow
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with conflict_on guidance
        """
        context = {
            "model_name": model_name,
            "node_id": node_id,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = f"{model_name}UpsertNode requires non-empty 'conflict_on' list (node: {node_id})"

        return cls._build_error_from_catalog(
            "DF-706", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_upsert_node_missing_where(
        cls,
        model_name: str,
        node_id: str,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance UpsertNode missing where error (DF-707).

        Args:
            model_name: Model name (e.g., "User")
            node_id: Node ID in workflow
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with where clause guidance
        """
        context = {
            "model_name": model_name,
            "node_id": node_id,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values
        custom_message = f"{model_name}UpsertNode requires 'where' clause to identify record (node: {node_id})"

        return cls._build_error_from_catalog(
            "DF-707", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_upsert_node_missing_operations(
        cls,
        model_name: str,
        node_id: str,
        has_update: bool,
        has_create: bool,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance UpsertNode missing update/create error (DF-708).

        Args:
            model_name: Model name (e.g., "User")
            node_id: Node ID in workflow
            has_update: Whether update parameter exists
            has_create: Whether create parameter exists
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with upsert operations guidance
        """
        context = {
            "model_name": model_name,
            "node_id": node_id,
            "has_update": has_update,
            "has_create": has_create,
        }

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        # Custom message with dynamic values based on what's missing
        missing_parts = []
        if not has_update:
            missing_parts.append("'update'")
        if not has_create:
            missing_parts.append("'create'")

        missing = " or ".join(missing_parts) if missing_parts else "operations"
        custom_message = (
            f"{model_name}UpsertNode requires {missing} operation (node: {node_id})"
        )

        return cls._build_error_from_catalog(
            "DF-708", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_unsupported_database_type_for_upsert(
        cls,
        model_name: str,
        database_type: str,
        node_id: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance UpsertNode unsupported database type error (DF-709).

        Args:
            model_name: Model name (e.g., "User")
            database_type: Unsupported database type
            node_id: Node ID in workflow (optional)
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with database support guidance
        """
        context = {
            "model_name": model_name,
            "database_type": database_type,
            "supported_types": ["postgresql", "sqlite"],
        }

        if node_id:
            context["node_id"] = node_id

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        custom_message = (
            f"Unsupported database type '{database_type}' for {model_name}UpsertNode. "
            f"Only PostgreSQL and SQLite support atomic upsert operations"
        )

        return cls._build_error_from_catalog(
            "DF-709", context, original_error, custom_message=custom_message
        )

    @classmethod
    def enhance_upsert_operation_failed(
        cls,
        model_name: str,
        where: Optional[dict] = None,
        update: Optional[dict] = None,
        create: Optional[dict] = None,
        database_type: Optional[str] = None,
        node_id: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> DataFlowError:
        """
        Enhance UpsertNode operation failed error (DF-710).

        Args:
            model_name: Model name (e.g., "User")
            where: Where clause used
            update: Update data used
            create: Create data used
            database_type: Database type
            node_id: Node ID in workflow (optional)
            original_error: Original exception

        Returns:
            DataFlowError: Enhanced error with upsert failure guidance
        """
        context = {
            "model_name": model_name,
        }

        if where is not None:
            context["where"] = where
        if update is not None:
            context["update"] = update
        if create is not None:
            context["create"] = create
        if database_type:
            context["database_type"] = database_type
        if node_id:
            context["node_id"] = node_id

        if original_error:
            exc_context = cls._extract_context_from_exception(original_error)
            context.update(exc_context)

        custom_message = (
            f"Upsert operation failed for {model_name} (no record returned)"
        )

        return cls._build_error_from_catalog(
            "DF-710", context, original_error, custom_message=custom_message
        )
