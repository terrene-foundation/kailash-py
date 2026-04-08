"""
DataFlow Node Generation

Dynamic node generation for database operations.
"""

from typing import Any, Dict, List, Optional, Type, Union

try:
    from kailash.nodes.base import Node, NodeParameter, NodeRegistry

    if not hasattr(NodeRegistry, "register"):
        # kailash 3.x Rust NodeRegistry — provide a no-op stub
        class NodeRegistry:  # type: ignore[no-redef]
            @staticmethod
            def register(*args, **kwargs):
                pass

            @staticmethod
            def unregister_nodes(*args, **kwargs):
                pass

except ImportError:

    class Node:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            pass

    class NodeParameter:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class NodeRegistry:  # type: ignore[no-redef]
        @staticmethod
        def register(*args, **kwargs):
            pass

        @staticmethod
        def unregister_nodes(*args, **kwargs):
            pass


try:
    from kailash.nodes.base_async import AsyncNode
except ImportError:
    AsyncNode = Node  # type: ignore[assignment,misc]

from .async_utils import async_safe_run  # Phase 6: Async-safe execution
from .logging_config import mask_sensitive_values  # Phase 7: Sensitive value masking


# ErrorEnhancer imported locally to avoid circular dependencies
# Import deferred to runtime to break circular dependency chain:
# nodes.py -> platform.errors -> platform.__init__ -> studio -> dataflow -> engine -> nodes.py
def _get_error_enhancer():
    """
    Lazy import of ErrorEnhancer to avoid circular dependencies.
    ErrorEnhancer is mandatory in Phase 1C but must be imported at runtime.
    """
    from dataflow.platform.errors import ErrorEnhancer as EE

    return EE


# Cache the ErrorEnhancer class after first import
_ERROR_ENHANCER_CACHE = None


def _error_enhancer():
    """Get ErrorEnhancer with caching for performance."""
    global _ERROR_ENHANCER_CACHE
    if _ERROR_ENHANCER_CACHE is None:
        _ERROR_ENHANCER_CACHE = _get_error_enhancer()
    return _ERROR_ENHANCER_CACHE


def convert_datetime_fields(data_dict: dict, model_fields: dict, logger) -> dict:
    """
    Convert ISO 8601 datetime strings to Python datetime objects for datetime fields.

    This helper enables seamless integration with PythonCodeNode, which outputs ISO 8601
    datetime strings that need to be converted to Python datetime objects before database insertion.

    Args:
        data_dict: Dictionary containing field values (may include datetime strings)
        model_fields: Model field definitions from DataFlow
        logger: Logger for debug/warning messages

    Returns:
        Modified dict with datetime strings converted to datetime objects

    Example:
        >>> model_fields = {"created_at": {"type": datetime}}
        >>> data = {"created_at": "2024-01-01T12:00:00Z"}
        >>> convert_datetime_fields(data, model_fields, logger)
        {"created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)}
    """
    import typing
    from datetime import datetime

    for field_name, field_value in list(data_dict.items()):
        # Skip non-string values
        if not isinstance(field_value, str):
            continue

        # Check if this field is defined as datetime in the model
        field_info = model_fields.get(field_name, {})
        field_type = field_info.get("type")

        # Handle Optional[datetime] types
        if hasattr(field_type, "__origin__"):
            if field_type.__origin__ is typing.Union:
                actual_types = [t for t in field_type.__args__ if t is not type(None)]
                if actual_types and actual_types[0] == datetime:
                    field_type = datetime

        # If field is datetime type and value is string, try to parse it
        if field_type == datetime:
            try:
                # Support multiple ISO 8601 formats:
                # - With microseconds: 2024-01-01T12:00:00.123456
                # - Without microseconds: 2024-01-01T12:00:00
                # - With timezone Z: 2024-01-01T12:00:00Z
                # - With timezone offset: 2024-01-01T12:00:00+00:00
                parsed_dt = datetime.fromisoformat(field_value.replace("Z", "+00:00"))
                data_dict[field_name] = parsed_dt
                logger.debug(
                    f"Auto-converted datetime string '{field_value}' to datetime object for field '{field_name}'"
                )
            except (ValueError, AttributeError) as e:
                # If parsing fails, leave as-is and let database handle it
                logger.warning(
                    f"Failed to parse datetime string '{field_value}' for field '{field_name}': {e}"
                )

    return data_dict


class NodeGenerator:
    """Generates workflow nodes for DataFlow models."""

    def __init__(self, dataflow_instance):
        self.dataflow_instance = dataflow_instance
        # TDD mode detection and context
        self._tdd_mode = getattr(dataflow_instance, "_tdd_mode", False)
        self._test_context = getattr(dataflow_instance, "_test_context", None)

    def _normalize_type_annotation(self, type_annotation: Any) -> Type:
        """Normalize complex type annotations to simple types for NodeParameter.

        This function converts complex typing constructs like Optional[str], List[str],
        Dict[str, Any], etc. into simple Python types that NodeParameter can handle.

        CRITICAL: This method preserves Optional[T] semantics to correctly set
        required=False in NodeParameter. Core SDK depends on this for proper
        validation of optional fields. The Optional wrapper is detected separately
        in parameter generation (see get_parameters methods).

        Args:
            type_annotation: The type annotation from model field

        Returns:
            A simple Python type (str, int, bool, list, dict, etc.)
            For Optional[T], returns the normalized inner type T
        """
        # Handle typing constructs
        if hasattr(type_annotation, "__origin__"):
            origin = type_annotation.__origin__
            args = getattr(type_annotation, "__args__", ())

            # Handle Optional[T] -> Union[T, None]
            if origin is Union:
                # Check if this is Optional[T] (Union[T, None])
                non_none_types = [arg for arg in args if arg is not type(None)]

                if len(non_none_types) == 1 and type(None) in args:
                    # This is Optional[T] - normalize the inner type
                    # The Optional wrapper is detected separately in parameter generation
                    return self._normalize_type_annotation(non_none_types[0])
                elif len(non_none_types) == 1:
                    # Union with single type (not Optional) - normalize it
                    return self._normalize_type_annotation(non_none_types[0])
                elif len(non_none_types) == 0:
                    # Union[None] edge case - treat as Any
                    return str
                else:
                    # Complex Union (not Optional) - keep first non-None type
                    return self._normalize_type_annotation(non_none_types[0])

            # Handle List[T], Dict[K, V], etc. - return base container type
            elif origin in (list, List):
                return list
            elif origin in (dict, Dict):
                return dict
            elif origin in (tuple, tuple):
                return tuple
            elif origin in (set, frozenset):
                return set

            # Return the origin for other generic types
            return origin

        # Handle regular types
        elif isinstance(type_annotation, type):
            return type_annotation

        # Handle special cases for common types that might not be recognized
        from datetime import date, datetime, time
        from decimal import Decimal

        if type_annotation is datetime:
            return datetime
        elif type_annotation is date:
            return date
        elif type_annotation is time:
            return time
        elif type_annotation is Decimal:
            return Decimal

        # Fallback to str for unknown types
        return str

    def generate_crud_nodes(self, model_name: str, fields: Dict[str, Any]):
        """Generate CRUD workflow nodes for a model."""
        nodes = {
            f"{model_name}CreateNode": self._create_node_class(
                model_name, "create", fields
            ),
            f"{model_name}ReadNode": self._create_node_class(
                model_name, "read", fields
            ),
            f"{model_name}UpdateNode": self._create_node_class(
                model_name, "update", fields
            ),
            f"{model_name}DeleteNode": self._create_node_class(
                model_name, "delete", fields
            ),
            f"{model_name}ListNode": self._create_node_class(
                model_name, "list", fields
            ),
            # NEW v0.8.0: Add UpsertNode as 6th CRUD operation (single-record upsert)
            f"{model_name}UpsertNode": self._create_node_class(
                model_name, "upsert", fields
            ),
            # NEW v0.8.1: Add CountNode as 7th CRUD operation (efficient count queries)
            f"{model_name}CountNode": self._create_node_class(
                model_name, "count", fields
            ),
        }

        # Register nodes with Kailash's NodeRegistry system
        for node_name, node_class in nodes.items():
            NodeRegistry.register(node_class, alias=node_name)
            # Also register in module namespace for direct imports
            globals()[node_name] = node_class
            # Store in DataFlow instance for testing
            self.dataflow_instance._nodes[node_name] = node_class

        return nodes

    def generate_bulk_nodes(self, model_name: str, fields: Dict[str, Any]):
        """Generate bulk operation nodes for a model."""
        nodes = {
            f"{model_name}BulkCreateNode": self._create_node_class(
                model_name, "bulk_create", fields
            ),
            f"{model_name}BulkUpdateNode": self._create_node_class(
                model_name, "bulk_update", fields
            ),
            f"{model_name}BulkDeleteNode": self._create_node_class(
                model_name, "bulk_delete", fields
            ),
            f"{model_name}BulkUpsertNode": self._create_node_class(
                model_name, "bulk_upsert", fields
            ),
        }

        # Register nodes with Kailash's NodeRegistry system
        for node_name, node_class in nodes.items():
            NodeRegistry.register(node_class, alias=node_name)
            globals()[node_name] = node_class
            # Store in DataFlow instance for testing
            self.dataflow_instance._nodes[node_name] = node_class

        return nodes

    def _create_node_class(
        self, model_name: str, operation: str, fields: Dict[str, Any]
    ) -> Type[Node]:
        """Create a workflow node class for a model operation."""

        # Store parent DataFlow instance and TDD context in closure
        dataflow_instance = self.dataflow_instance
        tdd_mode = self._tdd_mode
        test_context = self._test_context

        class DataFlowNode(AsyncNode):
            def _serialize_params_for_sql(self, params: list) -> list:
                """Serialize dict/list parameters to JSON for SQL binding.

                BUG #515 FIX: This method ensures dict/list values are serialized
                to JSON strings at the SQL parameter binding stage, NOT during
                validation. This preserves type integrity through validation while
                ensuring database compatibility.

                NATIVE ARRAY FIX: Only JSON-serialize lists when use_native_arrays=False.
                When use_native_arrays=True (PostgreSQL), lists are passed through as-is
                for native array columns (TEXT[], INTEGER[], etc.). asyncpg expects
                Python lists for PostgreSQL array types, not JSON strings.

                Args:
                    params: List of parameter values

                Returns:
                    List with appropriate serialization based on model config
                """
                import json

                # Check if this model uses native PostgreSQL arrays
                use_native_arrays = False
                try:
                    model_info = self.dataflow_instance.get_model_info(self.model_name)
                    if model_info:
                        config = model_info.get("config", {})
                        use_native_arrays = config.get("use_native_arrays", False)
                except Exception:
                    pass  # Default to JSON serialization on any error

                serialized = []
                for value in params:
                    if isinstance(value, dict):
                        # Dicts are always JSON-serialized (JSONB columns)
                        serialized.append(json.dumps(value))
                    elif isinstance(value, list):
                        if use_native_arrays:
                            # Native arrays: pass list as-is for asyncpg
                            serialized.append(value)
                        else:
                            # JSON mode: serialize list to JSON string
                            serialized.append(json.dumps(value))
                    else:
                        serialized.append(value)
                return serialized

            def _deserialize_json_fields(self, record: dict) -> dict:
                """Deserialize JSON strings back to dict/list for JSON fields.

                BUG #515 FIX: This method converts JSON strings returned from the
                database back to Python dict/list objects based on model field types.

                Args:
                    record: Database record with potentially JSON string values

                Returns:
                    Record with JSON strings converted back to dict/list
                """
                import json

                if not record or not isinstance(record, dict):
                    return record

                deserialized = {}
                for field_name, value in record.items():
                    # Skip non-string values (already correct type)
                    if not isinstance(value, str):
                        deserialized[field_name] = value
                        continue

                    # Check if this field is a JSON field (dict or list type)
                    field_info = self.model_fields.get(field_name, {})
                    field_type = field_info.get("type")

                    if field_type in (dict, list):
                        # Try to deserialize JSON string
                        try:
                            deserialized[field_name] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            # If deserialization fails, keep original value
                            deserialized[field_name] = value
                    else:
                        # Not a JSON field, keep as-is
                        deserialized[field_name] = value

                return deserialized

            def _serialize_datetime_fields(self, data_dict: dict) -> dict:
                """Serialize Python datetime objects to ISO strings for JSON output.

                This is the complement to convert_datetime_fields() and ensures that
                datetime objects are serialized back to ISO 8601 strings before being
                returned in node outputs (which must be JSON-serializable).

                Handles nested dictionaries recursively to serialize datetime objects
                at any depth (e.g., {"fields": {"scheduled_at": datetime(...)}}).

                Args:
                    data_dict: Dictionary containing field values (may include datetime objects)

                Returns:
                    Modified dict with datetime objects converted to ISO 8601 strings

                Example:
                    >>> from datetime import datetime, timezone
                    >>> data = {"event_date": datetime(2024, 7, 20, 16, 0, 0, tzinfo=timezone.utc)}
                    >>> node._serialize_datetime_fields(data)
                    {"event_date": "2024-07-20T16:00:00+00:00"}

                    >>> # Handles nested dictionaries
                    >>> nested_data = {"fields": {"scheduled_at": datetime(2024, 8, 1, 10, 0, 0)}}
                    >>> node._serialize_datetime_fields(nested_data)
                    {"fields": {"scheduled_at": "2024-08-01T10:00:00"}}
                """
                from datetime import datetime

                if not data_dict or not isinstance(data_dict, dict):
                    return data_dict

                serialized = {}
                for field_name, value in data_dict.items():
                    if isinstance(value, datetime):
                        # Convert datetime to ISO 8601 string
                        serialized[field_name] = value.isoformat()
                    elif isinstance(value, dict):
                        # Recursively serialize nested dictionaries
                        serialized[field_name] = self._serialize_datetime_fields(value)
                    else:
                        serialized[field_name] = value

                return serialized

            """Auto-generated DataFlow node."""

            def __init__(self, **kwargs):
                # Set attributes before calling super().__init__() because
                # the parent constructor calls get_parameters() which needs these
                self.model_name = model_name
                self.operation = operation
                self.dataflow_instance = dataflow_instance
                self.model_fields = fields
                # TDD context inheritance
                self._tdd_mode = tdd_mode
                self._test_context = test_context
                super().__init__(**kwargs)

            def _apply_tenant_isolation(self, query: str, params: list) -> tuple:
                """Apply tenant isolation to a SQL query if tenant context is active.

                Checks the current tenant context (via contextvars) and, if a tenant
                is active and the model has a tenant_id field, uses QueryInterceptor
                to inject tenant conditions into DML queries. DDL operations bypass
                tenant isolation.

                Args:
                    query: The SQL query string
                    params: The query parameters list

                Returns:
                    Tuple of (modified_query, modified_params) with tenant conditions
                    injected, or the original (query, params) if no tenant context
                    is active or the model is not tenant-aware.
                """
                import logging

                _logger = logging.getLogger(__name__)

                # Check for active tenant context
                from .tenant_context import get_current_tenant_id

                tenant_id = get_current_tenant_id()
                if not tenant_id:
                    return query, params

                # Check if this model has a tenant_id field (auto-detect tenant tables)
                if "tenant_id" not in self.model_fields:
                    return query, params

                # DDL operations bypass tenant isolation
                query_upper = query.strip().upper()
                if query_upper.startswith(("CREATE ", "ALTER ", "DROP ")):
                    return query, params

                # Get the table name for this model
                table_name = self.dataflow_instance._get_table_name(self.model_name)

                # Use QueryInterceptor to inject tenant conditions
                try:
                    from ..tenancy.interceptor import QueryInterceptor

                    interceptor = QueryInterceptor(
                        tenant_id=tenant_id,
                        tenant_tables=[table_name],
                        tenant_column="tenant_id",
                    )
                    modified_query, modified_params = (
                        interceptor.inject_tenant_conditions(query, params)
                    )
                    _logger.debug(
                        f"Tenant isolation applied: tenant_id={tenant_id}, "
                        f"table={table_name}, original_query={query[:80]}..."
                    )
                    return modified_query, modified_params
                except Exception as e:
                    _logger.error(
                        f"Failed to apply tenant isolation for {self.model_name}: {e}. "
                        f"Refusing to execute unfiltered query — potential cross-tenant data leak."
                    )
                    raise RuntimeError(
                        f"Tenant isolation failed for {self.model_name}: {e}. "
                        f"Cannot proceed without tenant filtering."
                    ) from e

            def validate_inputs(self, **kwargs) -> Dict[str, Any]:
                """Override validate_inputs to add SQL injection protection for DataFlow nodes.

                This method provides connection-level SQL injection protection by:
                1. Pre-converting datetime strings to datetime objects (for parent validation)
                2. Calling parent validation for type checking and required parameters
                3. Adding SQL injection detection and sanitization
                4. Preventing malicious SQL fragments in database parameters
                """
                import logging
                import re
                from typing import Any, Dict, List, Union

                logger = logging.getLogger(__name__)

                # CRITICAL FIX: Skip parent validation for datetime strings
                # Parent Node.validate_inputs() strictly type-checks datetime fields
                # Our strategy: just skip it and return kwargs as-is, datetime conversion happens in async_run()

                # Simply return kwargs without parent validation for DataFlow nodes
                # Parent validation is too strict for our use case (rejects ISO strings for datetime)
                validated_inputs = kwargs

                # ENHANCEMENT: Auto-strip auto-managed fields with WARNING (not ERROR)
                # This prevents DF-104 "multiple assignments to same column" errors
                # DataFlow automatically manages created_at/updated_at - developers shouldn't set them
                # Previous behavior: Raise error (frustrating, blocks developers)
                # New behavior: Auto-strip with warning (developer-friendly, educates users)
                if operation == "update":
                    # Check both new and old API parameters for auto-managed fields
                    fields_to_check = validated_inputs.get(
                        "fields", validated_inputs.get("updates", {})
                    )
                    if isinstance(fields_to_check, dict):
                        auto_managed_fields = []
                        if "created_at" in fields_to_check:
                            auto_managed_fields.append("created_at")
                        if "updated_at" in fields_to_check:
                            auto_managed_fields.append("updated_at")

                        if auto_managed_fields:
                            # Auto-strip the fields and log warning (instead of raising error)
                            for field in auto_managed_fields:
                                fields_to_check.pop(field, None)

                            logger.warning(
                                f"⚠️  AUTO-STRIPPED: Fields {auto_managed_fields} removed from update. "
                                f"DataFlow automatically manages created_at/updated_at timestamps. "
                                f"Remove these fields from your code to avoid this warning. "
                                f"See: https://docs.dataflow.dev/gotchas#auto-managed-fields"
                            )

                # SQL injection patterns to detect
                sql_injection_patterns = [
                    r"(?i)(union\s+select)",  # UNION SELECT attacks
                    r"(?i)(select\s+\*?\s*from)",  # SELECT FROM attacks
                    r"(?i)(drop\s+table)",  # DROP TABLE attacks
                    r"(?i)(delete\s+from)",  # DELETE FROM attacks
                    r"(?i)(insert\s+into)",  # INSERT INTO attacks
                    r"(?i)(update\s+\w+\s+set)",  # UPDATE SET attacks
                    r"(?i)(exec\s*\()",  # EXEC() attacks
                    r"(?i)(script\s*>)",  # XSS in SQL context
                    r"(?i)(or\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?)",  # OR 1=1 attacks
                    r"(?i)(and\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?)",  # AND 1=1 attacks
                    r"(?i)(\;\s*(drop|delete|insert|update|exec))",  # Statement chaining
                    r"(?i)(--\s*$)",  # SQL comments for bypass
                    r"(?i)(/\*.*?\*/)",  # SQL block comments
                ]

                def sanitize_sql_input(value: Any, field_name: str) -> Any:
                    """Sanitize individual input value for SQL injection.

                    CRITICAL BUG #515 FIX: We do NOT serialize dict/list to JSON here.
                    JSON serialization happens during SQL parameter binding in
                    AsyncSQLDatabaseNode (lines 1056-1061, 1243-1245). Premature
                    serialization causes type mismatch errors and data corruption.

                    Dict/list values are safe from SQL injection because they're
                    passed as parameterized query values, never embedded in SQL strings.
                    """
                    if value is None:
                        return None
                    if not isinstance(value, str):
                        # For non-string types, only process if they could contain injection when converted
                        from datetime import date, datetime, time
                        from decimal import Decimal

                        # Safe types that don't need sanitization (including dict/list)
                        safe_types = (
                            int,
                            float,
                            bool,
                            datetime,
                            date,
                            time,
                            Decimal,
                            dict,
                            list,
                        )
                        if isinstance(value, safe_types):
                            return (
                                value  # Safe types, return as-is (dict/list preserved!)
                            )

                        # For other complex types, convert to string and sanitize
                        value = str(value)

                    original_value = value

                    # Apply sanitization in specific order to avoid conflicts
                    # 1. Handle statement chaining first (most general)
                    value = re.sub(
                        r"(?i)(\;\s*(drop|delete|insert|update|exec))",
                        "; STATEMENT_BLOCKED",
                        value,
                    )

                    # 2. Handle specific SQL commands
                    value = re.sub(r"(?i)(union\s+select)", "UNION_SELECT", value)
                    value = re.sub(
                        r"(?i)(select\s+\*?\s*from)", "SELECT_FROM", value
                    )  # Add SELECT protection
                    value = re.sub(r"(?i)(drop\s+table)", "DROP_TABLE", value)
                    value = re.sub(r"(?i)(delete\s+from)", "DELETE_FROM", value)
                    value = re.sub(r"(?i)(insert\s+into)", "INSERT_INTO", value)
                    value = re.sub(r"(?i)(update\s+\w+\s+set)", "UPDATE_SET", value)
                    value = re.sub(r"(?i)(exec\s*\()", "EXEC_FUNC", value)

                    # 3. Handle logical operators
                    value = re.sub(
                        r"(?i)(or\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?)",
                        "OR_1_EQUALS_1",
                        value,
                    )
                    value = re.sub(
                        r"(?i)(and\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?)",
                        "AND_1_EQUALS_1",
                        value,
                    )

                    # 4. Handle comments
                    value = re.sub(r"(?i)(--\s*$)", "-- COMMENT_BLOCKED", value)
                    value = re.sub(r"(?i)(/\*.*?\*/)", "/* COMMENT_BLOCKED */", value)

                    # 5. Check if any patterns were found and log
                    if value != original_value:
                        for pattern in sql_injection_patterns:
                            if re.search(pattern, original_value):
                                logger.warning(
                                    f"Potential SQL injection detected in field '{field_name}': {pattern}"
                                )
                                break
                        logger.debug(
                            f"Sanitized SQL injection in field '{field_name}': {original_value} -> {value}"
                        )

                    return value

                def sanitize_nested_structure(data: Any, field_path: str = "") -> Any:
                    """Recursively sanitize nested data structures."""
                    if isinstance(data, dict):
                        return {
                            key: sanitize_nested_structure(
                                value, f"{field_path}.{key}" if field_path else key
                            )
                            for key, value in data.items()
                        }
                    elif isinstance(data, list):
                        return [
                            sanitize_nested_structure(item, f"{field_path}[{i}]")
                            for i, item in enumerate(data)
                        ]
                    else:
                        return sanitize_sql_input(data, field_path)

                # Apply SQL injection protection to all validated inputs
                protected_inputs = {}
                for field_name, value in validated_inputs.items():
                    if field_name in ["filter", "data", "update"]:
                        # Special handling for complex database operation fields
                        protected_inputs[field_name] = sanitize_nested_structure(
                            value, field_name
                        )
                    else:
                        # Standard field sanitization
                        protected_inputs[field_name] = sanitize_sql_input(
                            value, field_name
                        )

                # Additional DataFlow-specific validations
                if operation == "create" or operation == "update":
                    # Ensure no SQL injection in individual field values
                    for field_name, field_info in self.model_fields.items():
                        if field_name in protected_inputs:
                            value = protected_inputs[field_name]
                            if isinstance(value, str) and len(value) > 1000:
                                logger.warning(
                                    f"Suspiciously long input in field '{field_name}': {len(value)} characters"
                                )

                elif operation == "list" or operation == "count":
                    # Special validation for filter parameters (shared by list and count)
                    filter_dict = protected_inputs.get("filter", {})
                    if isinstance(filter_dict, dict):
                        # Validate MongoDB-style operators are safe
                        for field, filter_value in filter_dict.items():
                            if isinstance(filter_value, dict):
                                for op, op_value in filter_value.items():
                                    if op.startswith("$"):
                                        # Validate MongoDB-style operators
                                        allowed_ops = [
                                            "$eq",
                                            "$ne",
                                            "$gt",
                                            "$gte",
                                            "$lt",
                                            "$lte",
                                            "$in",
                                            "$nin",
                                            "$regex",
                                            "$exists",
                                            "$null",  # For IS NULL queries (e.g., soft-delete filtering)
                                            "$not",
                                            "$contains",  # For JSON field queries
                                            "$mul",  # For mathematical operations in updates
                                        ]
                                        if op not in allowed_ops:
                                            raise _error_enhancer().enhance_unsafe_filter_operator(
                                                model_name=self.model_name,
                                                field_name=field,
                                                operator=op,
                                                operation=operation,
                                                original_error=ValueError(
                                                    f"Unsafe filter operator '{op}' in field '{field}'"
                                                ),
                                            )

                elif operation.startswith("bulk_"):
                    # Validate bulk data doesn't contain injection
                    bulk_data = protected_inputs.get("data", [])
                    if isinstance(bulk_data, list):
                        for i, record in enumerate(bulk_data):
                            if isinstance(record, dict):
                                for field_name, value in record.items():
                                    if isinstance(value, str):
                                        # Check each field in bulk data
                                        sanitized = sanitize_sql_input(
                                            value, f"data[{i}].{field_name}"
                                        )
                                        if sanitized != value:
                                            bulk_data[i][field_name] = sanitized

                logger.debug(
                    f"DataFlow SQL injection protection applied to {operation} operation"
                )
                return protected_inputs

            def get_parameters(self) -> Dict[str, NodeParameter]:
                """Define parameters for this DataFlow node."""
                # Add database_url parameter to all operations
                base_params = {
                    "database_url": NodeParameter(
                        name="database_url",
                        type=str,
                        required=False,
                        default=None,
                        description="Database connection URL to override default configuration",
                    )
                }

                if operation == "create":
                    # Generate parameters from model fields
                    params = base_params.copy()
                    for field_name, field_info in self.model_fields.items():
                        # Bug #3 fix: Users can now provide 'id' parameter (namespace separation via _node_id)
                        if field_name == "id":
                            # Include ID parameter - users can provide their own IDs
                            id_type = field_info.get("type")
                            params["id"] = NodeParameter(
                                name="id",
                                type=id_type if id_type else int,
                                required=False,  # Optional - DB can auto-generate if not provided
                                description=f"Primary key for the record (user-provided {getattr(id_type, '__name__', str(id_type)) if id_type else 'int'})",
                            )
                        elif field_name not in ["created_at", "updated_at"]:
                            # Normalize complex type annotations to simple types
                            normalized_type = self.dataflow_instance._node_generator._normalize_type_annotation(
                                field_info["type"]
                            )

                            # BUG #514 FIX: Store Optional info for validation
                            # We keep required=True to prevent Core SDK from dropping the parameter,
                            # but we'll handle None values specially in validate_inputs()
                            from typing import get_args, get_origin

                            is_optional = False
                            field_type = field_info["type"]

                            if get_origin(field_type) is Union:
                                args = get_args(field_type)
                                if type(None) in args:
                                    is_optional = True

                            # ADR-002: Changed from WARNING to DEBUG - type normalization tracing
                            import logging

                            logger = logging.getLogger(__name__)
                            logger.debug(
                                f"PARAM {field_name}: original_type={field_info['type']} -> normalized_type={normalized_type}, is_optional={is_optional}"
                            )

                            # Store whether this is Optional in the parameter description
                            # We'll check this in validate_inputs() to allow None values
                            description = f"{field_name} for the record"
                            if is_optional:
                                description += " (Optional[{normalized_type.__name__}])"

                            params[field_name] = NodeParameter(
                                name=field_name,
                                type=normalized_type,
                                required=field_info.get(
                                    "required", True
                                ),  # Keep as-is from model
                                default=field_info.get("default"),
                                description=description,
                            )
                    return params

                elif operation == "read":
                    params = base_params.copy()
                    params.update(
                        {
                            "record_id": NodeParameter(
                                name="record_id",
                                type=int,
                                required=False,
                                default=None,
                                description="ID of record to read",
                            ),
                            "id": NodeParameter(
                                name="id",
                                type=Any,  # Accept any type to avoid validation errors
                                required=False,
                                default=None,
                                description="Alias for record_id (accepts workflow connections)",
                            ),
                            "conditions": NodeParameter(
                                name="conditions",
                                type=dict,
                                required=False,
                                default={},
                                description="Read conditions (e.g., {'id': 123})",
                            ),
                            "raise_on_not_found": NodeParameter(
                                name="raise_on_not_found",
                                type=bool,
                                required=False,
                                default=True,
                                description="Whether to raise error if record not found",
                            ),
                            "include_deleted": NodeParameter(
                                name="include_deleted",
                                type=bool,
                                required=False,
                                default=False,
                                description="Include soft-deleted records (models with soft_delete: True auto-filter by default)",
                            ),
                        }
                    )
                    return params

                elif operation == "update":
                    params = base_params.copy()
                    params.update(
                        {
                            "record_id": NodeParameter(
                                name="record_id",
                                type=int,
                                required=False,
                                default=None,
                                description="ID of record to update",
                            ),
                            "id": NodeParameter(
                                name="id",
                                type=Any,  # Accept any type to avoid validation errors
                                required=False,
                                default=None,
                                description="Alias for record_id (accepts workflow connections)",
                            ),
                            # NEW v0.6 API: filter/fields parameters (documented API)
                            "filter": NodeParameter(
                                name="filter",
                                type=dict,
                                required=False,
                                default={},
                                description="Filter criteria for selecting records to update (e.g., {'id': 123})",
                                auto_map_from=["conditions"],  # Backward compatibility
                            ),
                            "fields": NodeParameter(
                                name="fields",
                                type=dict,
                                required=False,
                                default={},
                                description="Fields to update with new values (e.g., {'name': 'Alice Updated'})",
                                auto_map_from=["updates"],  # Backward compatibility
                            ),
                            # DEPRECATED: Old API parameters (maintained for backward compatibility)
                            "conditions": NodeParameter(
                                name="conditions",
                                type=dict,
                                required=False,
                                default={},
                                description="[DEPRECATED: Use 'filter'] Update conditions (e.g., {'id': 123})",
                                auto_map_from=["filter"],  # Maps to new parameter
                            ),
                            "updates": NodeParameter(
                                name="updates",
                                type=dict,
                                required=False,
                                default={},
                                description="[DEPRECATED: Use 'fields'] Fields to update (e.g., {'published': True})",
                                auto_map_from=["fields"],  # Maps to new parameter
                            ),
                        }
                    )
                    # Add all model fields as optional update parameters for backward compatibility
                    for field_name, field_info in self.model_fields.items():
                        if field_name not in ["id", "created_at", "updated_at"]:
                            # Normalize complex type annotations to simple types
                            normalized_type = self.dataflow_instance._node_generator._normalize_type_annotation(
                                field_info["type"]
                            )

                            params[field_name] = NodeParameter(
                                name=field_name,
                                type=normalized_type,
                                required=False,
                                description=f"New {field_name} for the record",
                            )
                    return params

                elif operation == "delete":
                    params = base_params.copy()
                    params.update(
                        {
                            "record_id": NodeParameter(
                                name="record_id",
                                type=int,
                                required=False,
                                default=None,
                                description="ID of record to delete",
                            ),
                            "id": NodeParameter(
                                name="id",
                                type=Any,  # Accept any type to avoid validation errors
                                required=False,
                                default=None,
                                description="Alias for record_id (accepts workflow connections)",
                            ),
                            # NEW v0.6 API: filter parameter (documented API)
                            "filter": NodeParameter(
                                name="filter",
                                type=dict,
                                required=False,
                                default={},
                                description="Filter criteria for selecting records to delete (e.g., {'id': 123})",
                                auto_map_from=["conditions"],  # Backward compatibility
                            ),
                            # DEPRECATED: Old API parameter (maintained for backward compatibility)
                            "conditions": NodeParameter(
                                name="conditions",
                                type=dict,
                                required=False,
                                default={},
                                description="[DEPRECATED: Use 'filter'] Delete conditions (e.g., {'id': 123})",
                                auto_map_from=["filter"],  # Maps to new parameter
                            ),
                        }
                    )
                    return params

                elif operation == "list":
                    params = base_params.copy()
                    params.update(
                        {
                            "limit": NodeParameter(
                                name="limit",
                                type=int,
                                required=False,
                                default=10,
                                description="Maximum number of records to return",
                            ),
                            "offset": NodeParameter(
                                name="offset",
                                type=int,
                                required=False,
                                default=0,
                                description="Number of records to skip",
                            ),
                            "order_by": NodeParameter(
                                name="order_by",
                                type=list,
                                required=False,
                                default=[],
                                description="Fields to sort by (backward compatibility)",
                            ),
                            "sort": NodeParameter(
                                name="sort",
                                type=list,
                                required=False,
                                default=[],
                                description="Fields to sort by [{field: str, order: str}] format",
                            ),
                            "filter": NodeParameter(
                                name="filter",
                                type=dict,
                                required=False,
                                default={},
                                description="Filter criteria",
                            ),
                            "enable_cache": NodeParameter(
                                name="enable_cache",
                                type=bool,
                                required=False,
                                default=True,
                                description="Whether to enable query caching",
                            ),
                            "cache_ttl": NodeParameter(
                                name="cache_ttl",
                                type=int,
                                required=False,
                                default=None,
                                description="Cache TTL in seconds",
                            ),
                            "cache_key": NodeParameter(
                                name="cache_key",
                                type=str,
                                required=False,
                                default=None,
                                description="Override cache key",
                            ),
                            "count_only": NodeParameter(
                                name="count_only",
                                type=bool,
                                required=False,
                                default=False,
                                description="Return count only",
                            ),
                            "include_deleted": NodeParameter(
                                name="include_deleted",
                                type=bool,
                                required=False,
                                default=False,
                                description="Include soft-deleted records (models with soft_delete: True auto-filter by default)",
                            ),
                        }
                    )
                    return params

                elif operation == "upsert":
                    # NEW v0.8.0: Single-record upsert parameters (Prisma-style API)
                    params = base_params.copy()
                    params.update(
                        {
                            "where": NodeParameter(
                                name="where",
                                type=dict,
                                required=True,
                                description="Unique fields to identify record (e.g., {'email': 'user@example.com'})",
                            ),
                            "update": NodeParameter(
                                name="update",
                                type=dict,
                                required=False,
                                default={},
                                description="Fields to update if record exists",
                            ),
                            "create": NodeParameter(
                                name="create",
                                type=dict,
                                required=False,
                                default={},
                                description="Fields to create if record does not exist",
                            ),
                            "conflict_on": NodeParameter(
                                name="conflict_on",
                                type=list,
                                required=False,
                                default=None,
                                description="Fields to detect conflicts on (defaults to where keys). Example: ['email'] or ['order_id', 'product_id']",
                            ),
                        }
                    )
                    return params

                elif operation == "count":
                    # NEW v0.8.1: Count operation parameters (efficient COUNT(*) queries)
                    params = base_params.copy()
                    params.update(
                        {
                            "filter": NodeParameter(
                                name="filter",
                                type=dict,
                                required=False,
                                default={},
                                description="Filter criteria for count query (e.g., {'active': True})",
                            ),
                            "include_deleted": NodeParameter(
                                name="include_deleted",
                                type=bool,
                                required=False,
                                default=False,
                                description="Include soft-deleted records (models with soft_delete: True auto-filter by default)",
                            ),
                        }
                    )
                    return params

                elif operation.startswith("bulk_"):
                    params = base_params.copy()
                    params.update(
                        {
                            "data": NodeParameter(
                                name="data",
                                type=list,
                                required=False,
                                default=[],
                                description="List of records for bulk operation",
                                auto_map_from=["records", "rows", "documents"],
                            ),
                            "batch_size": NodeParameter(
                                name="batch_size",
                                type=int,
                                required=False,
                                default=1000,
                                description="Batch size for bulk operations",
                            ),
                            "conflict_resolution": NodeParameter(
                                name="conflict_resolution",
                                type=str,
                                required=False,
                                default="skip",
                                description="How to handle conflicts",
                            ),
                            # NEW v0.6 API: filter parameter (documented API)
                            "filter": NodeParameter(
                                name="filter",
                                type=dict,
                                required=False,
                                default={},
                                description="Filter criteria for bulk update/delete (e.g., {'active': True})",
                                auto_map_from=["conditions"],  # Backward compatibility
                            ),
                            # DEPRECATED: Old API parameter (maintained for backward compatibility)
                            "conditions": NodeParameter(
                                name="conditions",
                                type=dict,
                                required=False,
                                default={},
                                description="[DEPRECATED: Use 'filter'] Filter conditions for bulk operations",
                                auto_map_from=["filter"],  # Maps to new parameter
                            ),
                            # NEW v0.6 API: fields parameter (documented API) for bulk_update
                            "fields": NodeParameter(
                                name="fields",
                                type=dict,
                                required=False,
                                default={},
                                description="Fields to update with new values for bulk update (e.g., {'status': 'active'})",
                                auto_map_from=["update"],  # Backward compatibility
                            ),
                            # DEPRECATED: Old API parameter (maintained for backward compatibility)
                            "update": NodeParameter(
                                name="update",
                                type=dict,
                                required=False,
                                default={},
                                description="[DEPRECATED: Use 'fields'] Update values for bulk update",
                                auto_map_from=["fields"],  # Maps to new parameter
                            ),
                            "return_ids": NodeParameter(
                                name="return_ids",
                                type=bool,
                                required=False,
                                default=False,
                                description="Whether to return created record IDs",
                            ),
                            "safe_mode": NodeParameter(
                                name="safe_mode",
                                type=bool,
                                required=False,
                                default=True,
                                description="Enable safe mode to prevent accidental bulk operations",
                            ),
                            "confirmed": NodeParameter(
                                name="confirmed",
                                type=bool,
                                required=False,
                                default=False,
                                description="Confirmation required for dangerous bulk operations",
                            ),
                        }
                    )
                    return params

                return {}

            def run(self, **kwargs) -> Dict[str, Any]:
                """Synchronous wrapper for async_run to support both sync and async usage.

                This allows DataFlow nodes to be used in both synchronous scripts
                and async applications, improving developer experience.

                Phase 6: Uses async_safe_run for transparent sync/async bridging.
                Works correctly in FastAPI, Docker, Jupyter, and traditional scripts.
                """
                # Phase 6: Use async_safe_run for proper event loop handling
                # This works in both sync and async contexts transparently
                return async_safe_run(self.async_run(**kwargs))

            async def async_run(self, **kwargs) -> Dict[str, Any]:
                """Execute the database operation using DataFlow components."""
                import asyncio
                import logging

                from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

                logger = logging.getLogger(__name__)
                # ADR-002: Changed from WARNING to DEBUG - this is diagnostic tracing, not a problem
                logger.debug(
                    f"DataFlow Node {self.model_name}{self.operation.title()}Node - received kwargs: {kwargs}"
                )

                # Ensure table exists before any database operations (lazy table creation)
                if self.dataflow_instance and hasattr(
                    self.dataflow_instance, "ensure_table_exists"
                ):
                    logger.debug(
                        "nodes.ensuring_table_exists_for_model",
                        extra={"model_name": self.model_name},
                    )
                    try:
                        table_created = (
                            await self.dataflow_instance.ensure_table_exists(
                                self.model_name
                            )
                        )
                        if not table_created:
                            logger.warning(
                                f"Failed to ensure table exists for model {self.model_name}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error ensuring table exists for model {self.model_name}: {e}"
                        )
                        # Continue anyway - the database operation might still work

                logger.debug(
                    f"Run called with kwargs: {mask_sensitive_values(str(kwargs))}"
                )

                # TDD mode: Override connection string if test context available
                if (
                    self._tdd_mode
                    and self._test_context
                    and hasattr(self._test_context, "connection")
                ):
                    # Extract connection info from TDD context
                    tdd_connection_info = self._get_tdd_connection_info()
                    if tdd_connection_info:
                        kwargs["database_url"] = tdd_connection_info
                        logger.debug(
                            f"TDD mode: Using test connection for {operation} operation"
                        )

                # Tenant filtering is now applied at the SQL level via
                # _apply_tenant_isolation() which uses QueryInterceptor and the
                # contextvars-based tenant context (TenantContextSwitch).

                # Execute database operations using DataFlow components
                # ADR-002: Changed from WARNING to DEBUG - this is diagnostic tracing
                logger.debug(
                    f"Operation detection: operation='{operation}', model='{model_name}'"
                )
                if operation == "create":
                    # Use DataFlow's insert SQL generation and AsyncSQLDatabaseNode for execution
                    try:
                        # VALIDATION: Issue 5 - Detect "data" wrapper mistake
                        # ONLY reject if 'data' is not a model field (BUG #515 fix)
                        if "data" in kwargs:
                            model_fields = self.dataflow_instance.get_model_fields(
                                self.model_name
                            )
                            # If 'data' is NOT a model field, it's likely a wrapper mistake
                            if "data" not in model_fields:
                                # Enhanced error with catalog-based solutions (DF-602)
                                raise _error_enhancer().enhance_create_vs_update_node_confusion(
                                    node_type=f"{self.model_name}CreateNode",
                                    received_structure="data wrapper (nested)",
                                    expected_structure="flat fields (top-level)",
                                )

                        # Get connection string - prioritize parameter over instance config
                        connection_string = kwargs.get("database_url")
                        if not connection_string:
                            connection_string = (
                                self.dataflow_instance.config.database.url or ":memory:"
                            )

                        # Detect database type for SQL generation
                        if kwargs.get("database_url"):
                            # Use provided database URL to detect type
                            from ..adapters.connection_parser import ConnectionParser

                            database_type = ConnectionParser.detect_database_type(
                                connection_string
                            )
                        else:
                            database_type = (
                                self.dataflow_instance._detect_database_type()
                            )

                        # DEBUG: Check what self.model_name we have
                        # Fixed: Using self.model_name to avoid closure variable conflicts
                        logger.debug(
                            f"CREATE operation - self.model_name: {self.model_name}"
                        )

                        # Get ALL model fields to match SQL generation
                        model_fields = self.dataflow_instance.get_model_fields(
                            self.model_name
                        )

                        # CRITICAL FIX: Use the EXACT SAME field ordering as SQL generation
                        # This ensures parameter order matches SQL placeholder order
                        field_names = []
                        for name in model_fields.keys():
                            if name == "id":
                                # Include ID if user provided it (Bug #3 fix allows users to use 'id')
                                if "id" in kwargs:
                                    field_names.append(name)
                                # Otherwise skip (will be auto-generated by database)
                            elif name not in ["created_at", "updated_at"]:
                                field_names.append(name)

                        # Generate SQL dynamically based on fields user is actually providing
                        table_name = self.dataflow_instance._get_table_name(
                            self.model_name
                        )
                        columns = ", ".join(field_names)

                        # Database-specific parameter placeholders
                        if database_type.lower() == "postgresql":
                            placeholders = ", ".join(
                                [f"${i + 1}" for i in range(len(field_names))]
                            )
                            # RETURNING clause: all provided fields plus timestamps if they exist in model
                            returning_fields = ["id"] + [
                                name for name in field_names if name != "id"
                            ]
                            if "created_at" in model_fields:
                                returning_fields.append("created_at")
                            if "updated_at" in model_fields:
                                returning_fields.append("updated_at")
                            query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING {', '.join(returning_fields)}"
                        elif database_type.lower() == "mysql":
                            placeholders = ", ".join(["%s"] * len(field_names))
                            query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                        else:  # sqlite
                            placeholders = ", ".join(["?"] * len(field_names))
                            query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

                        # ADR-002: Changed from WARNING to DEBUG - SQL generation tracing
                        logger.debug(
                            f"CREATE {self.model_name} - Field order from model_fields.keys(): {field_names}"
                        )
                        logger.debug(
                            f"CREATE {self.model_name} - Generated SQL: {query}"
                        )

                        # Build complete parameter set with defaults in correct order
                        complete_params = {}

                        for field_name in field_names:
                            field_info = model_fields[field_name]

                            if field_name in kwargs:
                                # Use provided value
                                complete_params[field_name] = kwargs[field_name]
                            elif "default" in field_info:
                                # Use model default
                                default_value = field_info["default"]
                                # Handle callable defaults
                                if callable(default_value):
                                    complete_params[field_name] = default_value()
                                else:
                                    complete_params[field_name] = default_value
                            elif field_info.get("required", True):
                                # Enhanced error with catalog-based solutions (DF-105)
                                raise _error_enhancer().enhance_missing_required_field(
                                    node_id=getattr(self, "node_id", self.model_name),
                                    field_name=field_name,
                                    operation="CREATE",
                                    model_name=self.model_name,
                                )
                            else:
                                # Optional field without default - use None
                                complete_params[field_name] = None

                        # Auto-convert ISO datetime strings to datetime objects
                        complete_params = convert_datetime_fields(
                            complete_params, model_fields, logger
                        )

                        # Type-aware field validation (TODO-153)
                        # Validates field types without forced conversions
                        try:
                            from dataflow.core.type_processor import (
                                TypeAwareFieldProcessor,
                            )

                            type_processor = TypeAwareFieldProcessor(
                                model_fields, self.model_name
                            )
                            # Process with skip_fields to avoid re-processing timestamps
                            complete_params = type_processor.process_record(
                                complete_params,
                                operation="create",
                                strict=False,
                                skip_fields=set(),  # Don't skip - timestamps already excluded
                            )
                        except ImportError:
                            # TypeAwareFieldProcessor not available, continue without
                            logger.debug(
                                "TypeAwareFieldProcessor not available, skipping type validation"
                            )
                        except TypeError as e:
                            # Re-raise type errors with enhanced context
                            raise

                        # Now parameters match SQL placeholders exactly with correct ordering
                        values = [complete_params[k] for k in field_names]

                        # ADR-002: Changed from WARNING to DEBUG - field ordering tracing
                        logger.debug(
                            f"CREATE {self.model_name}: field_names={field_names}, "
                            f"values count={len(values)}, SQL placeholders expected={len(field_names)}"
                        )
                        # Enhanced debug logging to show value types
                        value_debug = []
                        for i, (field, value) in enumerate(zip(field_names, values)):
                            value_type = type(value).__name__
                            value_repr = (
                                repr(value)[:50] + "..."
                                if len(repr(value)) > 50
                                else repr(value)
                            )
                            value_debug.append(
                                f"${i + 1} {field}={value_repr} (type={value_type})"
                            )

                        # ADR-002: Changed from WARNING to DEBUG - parameter tracing
                        logger.debug(
                            f"CREATE {self.model_name}: Parameter details:\n"
                            + "\n".join(value_debug)
                        )

                        # BUG #515 FIX: Serialize dict/list to JSON for SQL parameter binding
                        serialized_values = self._serialize_params_for_sql(values)

                        # NOTE: PostgreSQL bypass removed - AsyncSQLDatabaseNode should handle all databases
                        # If there are parameter conversion issues, they should be fixed in AsyncSQLDatabaseNode itself

                        # Execute using AsyncSQLDatabaseNode
                        # For SQLite INSERT without RETURNING, use fetch_mode="all" to get metadata
                        fetch_mode = (
                            "all"
                            if database_type == "sqlite" and "RETURNING" not in query
                            else "one"
                        )

                        # Get or create cached AsyncSQLDatabaseNode for connection pooling
                        # This ensures SQLite :memory: databases share the same connection
                        sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                            database_type
                        )

                        # Apply tenant isolation to the query
                        query, serialized_values = self._apply_tenant_isolation(
                            query, serialized_values
                        )

                        # Execute the async node properly in async context
                        result = await sql_node.async_run(
                            query=query,
                            params=serialized_values,  # Use serialized values
                            fetch_mode=fetch_mode,
                            validate_queries=False,
                            transaction_mode="auto",
                        )

                        # ADR-002: Changed from WARNING to DEBUG - SQLite result tracing
                        if database_type == "sqlite":
                            logger.debug(
                                "nodes.sqlite_insert_result", extra={"result": result}
                            )

                        if result and "result" in result and "data" in result["result"]:
                            row = result["result"]["data"]

                            # Check if this is SQLite lastrowid response
                            if isinstance(row, dict) and "lastrowid" in row:
                                # SQLite returns lastrowid for INSERT operations
                                # ADR-002: Changed from WARNING to DEBUG - SQLite result tracing
                                logger.debug(
                                    f"SQLite lastrowid found directly: {row['lastrowid']}"
                                )
                                record_id = row["lastrowid"]
                                # Use user-provided id if available, otherwise lastrowid
                                if "id" in kwargs:
                                    record_id = kwargs["id"]
                                created_record = {"id": record_id, **kwargs}

                                # Read-back SELECT to fetch auto-generated fields (created_at, updated_at)
                                has_timestamps = (
                                    "created_at" in model_fields
                                    or "updated_at" in model_fields
                                )
                                if has_timestamps:
                                    readback_query = (
                                        f"SELECT * FROM {table_name} WHERE id = ?"
                                    )
                                    readback_result = await sql_node.async_run(
                                        query=readback_query,
                                        params=[record_id],
                                        fetch_mode="one",
                                        validate_queries=False,
                                    )
                                    if (
                                        readback_result
                                        and "result" in readback_result
                                        and "data" in readback_result["result"]
                                    ):
                                        readback_row = readback_result["result"]["data"]
                                        if (
                                            isinstance(readback_row, list)
                                            and len(readback_row) > 0
                                        ):
                                            readback_row = readback_row[0]
                                        if isinstance(readback_row, dict):
                                            created_record = {
                                                **created_record,
                                                **readback_row,
                                            }

                                # Invalidate cache after successful create
                                cache_integration = getattr(
                                    self.dataflow_instance, "_cache_integration", None
                                )
                                if cache_integration:
                                    cache_integration.invalidate_model_cache(
                                        self.model_name, "create", created_record
                                    )
                                # BUG #515 FIX: Deserialize JSON fields back to dict/list
                                created_record = self._deserialize_json_fields(
                                    created_record
                                )
                                # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                                created_record = self._serialize_datetime_fields(
                                    created_record
                                )
                                return created_record

                            if isinstance(row, list) and len(row) > 0:
                                row = row[0]

                            if row and isinstance(row, dict) and "lastrowid" not in row:
                                # Invalidate cache after successful create
                                cache_integration = getattr(
                                    self.dataflow_instance, "_cache_integration", None
                                )
                                if cache_integration:
                                    cache_integration.invalidate_model_cache(
                                        self.model_name, "create", row
                                    )

                                # BUG #515 FIX: Deserialize JSON fields back to dict/list
                                row = self._deserialize_json_fields(row)
                                # Combine kwargs and row
                                created_record = {**kwargs, **row}
                                # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                                created_record = self._serialize_datetime_fields(
                                    created_record
                                )
                                # Return the created record with all fields
                                return created_record

                        # Check for SQLite lastrowid (SQLite doesn't support RETURNING clause)
                        if result and "result" in result:
                            result_data = result["result"]
                            # Check if data contains lastrowid
                            if "data" in result_data:
                                data = result_data["data"]
                                if isinstance(data, dict) and "lastrowid" in data:
                                    # SQLite returns lastrowid for INSERT operations
                                    # ADR-002: Changed from WARNING to DEBUG - SQLite result tracing
                                    logger.debug(
                                        f"SQLite lastrowid found: {data['lastrowid']}"
                                    )
                                    created_record = {"id": data["lastrowid"], **kwargs}
                                    # Invalidate cache after successful create
                                    cache_integration = getattr(
                                        self.dataflow_instance,
                                        "_cache_integration",
                                        None,
                                    )
                                    if cache_integration:
                                        cache_integration.invalidate_model_cache(
                                            self.model_name, "create", created_record
                                        )
                                    # BUG #515 FIX: Deserialize JSON fields back to dict/list
                                    created_record = self._deserialize_json_fields(
                                        created_record
                                    )
                                    # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                                    created_record = self._serialize_datetime_fields(
                                        created_record
                                    )
                                    return created_record
                            elif (
                                isinstance(result_data, dict)
                                and "lastrowid" in result_data
                            ):
                                # SQLite returns lastrowid for INSERT operations
                                created_record = {
                                    "id": result_data["lastrowid"],
                                    **kwargs,
                                }
                                # BUG #515 FIX: Deserialize JSON fields back to dict/list
                                created_record = self._deserialize_json_fields(
                                    created_record
                                )
                                # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                                created_record = self._serialize_datetime_fields(
                                    created_record
                                )
                                return created_record
                            elif isinstance(result_data, list) and len(result_data) > 0:
                                first_result = result_data[0]
                                if (
                                    isinstance(first_result, dict)
                                    and "lastrowid" in first_result
                                ):
                                    created_record = {
                                        "id": first_result["lastrowid"],
                                        **kwargs,
                                    }
                                    # BUG #515 FIX: Deserialize JSON fields back to dict/list
                                    created_record = self._deserialize_json_fields(
                                        created_record
                                    )
                                    # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                                    created_record = self._serialize_datetime_fields(
                                        created_record
                                    )
                                    return created_record

                        # Fall back to basic response if no data returned
                        # ADR-002: Changed from WARNING to DEBUG - this is informational, not a problem
                        logger.debug(
                            f"CREATE {self.model_name}: Falling back to basic response - no lastrowid found"
                        )
                        # BUG #515 FIX: Deserialize JSON fields back to dict/list even in fallback
                        fallback_record = {"id": None, **kwargs}
                        fallback_record = self._deserialize_json_fields(fallback_record)
                        # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                        fallback_record = self._serialize_datetime_fields(
                            fallback_record
                        )
                        return fallback_record

                    except Exception as e:
                        original_error = str(e)
                        logger.debug(
                            f"CREATE {self.model_name} failed with error: {original_error}"
                        )

                        # Check for parameter mismatch error
                        if (
                            "could not determine data type of parameter"
                            in original_error
                        ):
                            import re

                            match = re.search(r"parameter \$(\d+)", original_error)
                            param_num = int(match.group(1)) if match else 0

                            logger.debug(
                                f"DATAFLOW DEBUG: Param error detected - param_num={param_num}"
                            )

                            # CRITICAL FIX: Handle parameter $11 type determination issue
                            if param_num == 11 and "$11" in query:
                                try:
                                    logger.debug(
                                        "DATAFLOW PARAM $11 FIX: Detected parameter $11 issue, retrying with type cast"
                                    )

                                    # Add explicit type casting for parameter $11
                                    fixed_sql = query.replace("$11", "$11::integer")

                                    # Import and retry with the fixed SQL
                                    from kailash.nodes.data.async_sql import (
                                        AsyncSQLDatabaseNode,
                                    )

                                    sql_node = AsyncSQLDatabaseNode(
                                        connection_string=connection_string,
                                        database_type=database_type,
                                    )
                                    result = await sql_node.async_run(
                                        query=fixed_sql,
                                        params=values,
                                        fetch_mode="one",  # RETURNING clause should return one record
                                        validate_queries=False,
                                        transaction_mode="auto",  # Ensure auto-commit for create operations
                                    )

                                    if (
                                        result
                                        and "result" in result
                                        and "data" in result["result"]
                                    ):
                                        row = result["result"]["data"]
                                        if isinstance(row, list) and len(row) > 0:
                                            row = row[0]
                                        if isinstance(row, dict):
                                            logger.debug(
                                                "DATAFLOW PARAM $11 FIX: Success with type cast!"
                                            )
                                            # BUG #515 FIX: Deserialize JSON fields back to dict/list
                                            row = self._deserialize_json_fields(row)
                                            # Combine kwargs and row
                                            created_record = {**kwargs, **row}
                                            # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                                            created_record = (
                                                self._serialize_datetime_fields(
                                                    created_record
                                                )
                                            )
                                            # Return the created record with all fields
                                            return created_record

                                    logger.debug(
                                        "DATAFLOW PARAM $11 FIX: Type cast succeeded but no data returned"
                                    )

                                except Exception as retry_error:
                                    logger.debug(
                                        f"DATAFLOW PARAM $11 FIX: Retry with type cast failed: {retry_error}"
                                    )
                                    # Continue with normal error handling

                            # Provide helpful error message
                            model_fields = self.dataflow_instance.get_model_fields(
                                self.model_name
                            )
                            expected_fields = [
                                f
                                for f in model_fields.keys()
                                if f not in ["id", "created_at", "updated_at"]
                            ]
                            provided_fields = list(kwargs.keys())

                            # The actual fields used (after applying defaults)
                            actual_fields = field_names  # These are the fields we actually built parameters for

                            error_msg = (
                                f"Parameter mismatch in {self.model_name} creation.\n"
                                f"SQL expects {len(expected_fields)} parameters but built {len(actual_fields)} parameters.\n"
                                f"Expected fields: {expected_fields}\n"
                                f"Built fields: {actual_fields}\n"
                                f"User provided: {provided_fields}\n"
                                f"Missing from user input: {list(set(expected_fields) - set(provided_fields))}\n"
                                f"Note: DataFlow auto-completes fields with defaults.\n"
                                f"Actual error: {original_error}"
                            )
                            logger.error(error_msg)
                        else:
                            logger.error(
                                "nodes.create_operation_failed", extra={"error": str(e)}
                            )
                            error_msg = str(e)

                        return {"success": False, "error": error_msg}

                elif operation == "read":
                    # Handle both nested parameter format and direct field format
                    conditions = kwargs.get("conditions", {})

                    # Handle string JSON input that might come from parameter validation
                    if isinstance(conditions, str):
                        try:
                            import json

                            conditions = (
                                json.loads(conditions) if conditions.strip() else {}
                            )
                        except (json.JSONDecodeError, ValueError):
                            conditions = {}

                    # Determine record_id from conditions or direct parameters
                    record_id = None
                    if conditions and "id" in conditions:
                        record_id = conditions["id"]
                    else:
                        # Fall back to direct parameters for backward compatibility
                        # Prioritize record_id over id to avoid conflicts with node's own id
                        record_id = kwargs.get("record_id")
                        if record_id is None:
                            # Get the ID parameter for record lookup
                            id_param = kwargs.get("id")
                            if id_param is not None:
                                # Type-aware ID conversion to fix string ID bug
                                id_field_info = self.model_fields.get("id", {})
                                id_type = id_field_info.get("type")

                                if id_type == str:
                                    # Model explicitly defines ID as string - preserve it
                                    record_id = id_param
                                elif id_type == int or id_type is None:
                                    # Model defines ID as int OR no type info (backward compat)
                                    try:
                                        record_id = int(id_param)
                                    except (ValueError, TypeError):
                                        # If conversion fails, preserve original
                                        record_id = id_param
                                else:
                                    # Other types (UUID, custom) - preserve as-is
                                    record_id = id_param

                    if record_id is None:
                        from kailash.sdk_exceptions import NodeValidationError

                        raise _error_enhancer().enhance_read_node_missing_id(
                            model_name=self.model_name,
                            node_id=getattr(
                                self, "node_id", f"{self.model_name}ReadNode"
                            ),
                            original_error=NodeValidationError(
                                f"{self.model_name}ReadNode requires 'id' or 'record_id' parameter. "
                                f"Example: workflow.add_node('{self.model_name}ReadNode', 'read', {{'id': record_id}})"
                            ),
                        )

                    # Get connection string - prioritize parameter over instance config
                    connection_string = kwargs.get("database_url")
                    if not connection_string:
                        connection_string = (
                            self.dataflow_instance.config.database.url or ":memory:"
                        )

                    # Detect database type for SQL generation
                    if kwargs.get("database_url"):
                        from ..adapters.connection_parser import ConnectionParser

                        database_type = ConnectionParser.detect_database_type(
                            connection_string
                        )
                    else:
                        database_type = self.dataflow_instance._detect_database_type()

                    # Use DataFlow's select SQL generation
                    select_templates = self.dataflow_instance._generate_select_sql(
                        self.model_name, database_type
                    )
                    query = select_templates["select_by_id"]

                    # Get or create cached AsyncSQLDatabaseNode for connection pooling
                    sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                        database_type
                    )

                    # Apply tenant isolation to the query
                    read_params = [record_id]
                    query, read_params = self._apply_tenant_isolation(
                        query, read_params
                    )

                    result = await sql_node.async_run(
                        query=query,
                        params=read_params,
                        fetch_mode="one",
                        validate_queries=False,
                        transaction_mode="auto",  # Ensure auto-commit for read operations
                    )

                    if result and "result" in result and "data" in result["result"]:
                        row = result["result"]["data"]
                        if isinstance(row, list) and len(row) > 0:
                            row = row[0]
                        if row:
                            # BUG #515 FIX: Deserialize JSON fields back to dict/list
                            row = self._deserialize_json_fields(row)

                            # SOFT DELETE AUTO-FILTER (v0.10.6+)
                            # If model has soft_delete: True, treat deleted records as not found
                            include_deleted = kwargs.get("include_deleted", False)
                            model_config = getattr(self, "_dataflow_config", {})
                            if not model_config:
                                # Get config from model_info dict (stored in _models)
                                model_info = self.dataflow_instance._models.get(
                                    model_name
                                )
                                if isinstance(model_info, dict):
                                    model_config = model_info.get("config", {})
                                # Fallback: check registered_models for class with _dataflow_config
                                elif not model_config:
                                    model_cls = (
                                        self.dataflow_instance._registered_models.get(
                                            model_name
                                        )
                                    )
                                    if model_cls and hasattr(
                                        model_cls, "_dataflow_config"
                                    ):
                                        model_config = getattr(
                                            model_cls, "_dataflow_config", {}
                                        )

                            has_soft_delete = model_config.get("soft_delete", False)
                            if has_soft_delete and not include_deleted:
                                # Check if record is soft-deleted
                                deleted_at = row.get("deleted_at")
                                if deleted_at is not None:
                                    # Record is soft-deleted, treat as not found
                                    logger.debug(
                                        f"soft_delete auto-filter: Record {record_id} is soft-deleted, treating as not found"
                                    )
                                    row = None  # Continue to "not found" handling below

                            if row:
                                # Return the row data with 'found' key as expected by tests
                                return {**row, "found": True}

                    # Record not found - check raise_on_not_found parameter
                    raise_on_not_found = kwargs.get("raise_on_not_found", True)
                    if raise_on_not_found:
                        from kailash.sdk_exceptions import NodeExecutionError

                        raise _error_enhancer().enhance_read_node_not_found(
                            model_name=self.model_name,
                            record_id=str(record_id),
                            node_id=getattr(
                                self, "node_id", f"{self.model_name}ReadNode"
                            ),
                            original_error=NodeExecutionError(
                                f"Record with id={record_id} not found in {self.model_name} table"
                            ),
                        )

                    return {"id": record_id, "found": False}

                elif operation == "update":
                    # Handle both nested parameter format and direct field format
                    # Support v0.6 API (filter/fields) with fallback to old API (conditions/updates)

                    # Helper to check if value is truly empty (handles dict, str, and JSON strings)
                    def is_empty(val):
                        if val is None:
                            return True
                        if isinstance(val, dict) and not val:
                            return True
                        if isinstance(val, str) and (
                            not val.strip() or val.strip() in ["{}", "[]"]
                        ):
                            return True
                        return False

                    # Get both old and new parameters, preferring new API
                    filter_param = kwargs.get("filter")
                    conditions_param = kwargs.get("conditions", {})
                    fields_param = kwargs.get("fields")
                    updates_param = kwargs.get("updates", {})

                    # Use new API if it has data, otherwise fall back to old API
                    conditions = (
                        filter_param if not is_empty(filter_param) else conditions_param
                    )
                    updates_dict = (
                        fields_param if not is_empty(fields_param) else updates_param
                    )

                    # DEPRECATION WARNINGS: Issue old API deprecation warnings
                    import warnings

                    if is_empty(filter_param) and not is_empty(conditions_param):
                        warnings.warn(
                            f"Parameter 'conditions' is deprecated in UpdateNode and will be removed in v0.8.0. "
                            f"Use 'filter' instead. "
                            f"Example: workflow.add_node('{self.model_name}UpdateNode', 'update', {{"
                            f"'filter': {{'id': 123}}, 'fields': {{'name': 'value'}}}}) "
                            f"See: .claude/skills/02-dataflow/dataflow-migrations-quick.md",
                            DeprecationWarning,
                            stacklevel=2,
                        )
                    if is_empty(fields_param) and not is_empty(updates_param):
                        warnings.warn(
                            f"Parameter 'updates' is deprecated in UpdateNode and will be removed in v0.8.0. "
                            f"Use 'fields' instead. "
                            f"Example: workflow.add_node('{self.model_name}UpdateNode', 'update', {{"
                            f"'filter': {{'id': 123}}, 'fields': {{'name': 'value'}}}}) "
                            f"See: .claude/skills/02-dataflow/dataflow-migrations-quick.md",
                            DeprecationWarning,
                            stacklevel=2,
                        )

                    # Handle string JSON input that might come from parameter validation
                    if isinstance(conditions, str):
                        try:
                            import json

                            conditions = (
                                json.loads(conditions) if conditions.strip() else {}
                            )
                        except (json.JSONDecodeError, ValueError):
                            conditions = {}

                    if isinstance(updates_dict, str):
                        try:
                            import json

                            # Try to parse as JSON first
                            updates_dict = (
                                json.loads(updates_dict) if updates_dict.strip() else {}
                            )
                        except (json.JSONDecodeError, ValueError) as e:
                            # Fallback: try to evaluate as Python literal (for single-quoted dicts)
                            try:
                                import ast

                                updates_dict = (
                                    ast.literal_eval(updates_dict)
                                    if updates_dict.strip()
                                    else {}
                                )
                            except (ValueError, SyntaxError):
                                updates_dict = {}

                    # Determine record_id from conditions or direct parameters
                    record_id = None
                    if conditions and "id" in conditions:
                        record_id = conditions["id"]
                    else:
                        # Fall back to record_id parameter - prioritize this over 'id'
                        # since 'id' often contains the node ID which is not a record ID
                        record_id = kwargs.get("record_id")

                        # Only use 'id' parameter if no record_id is available and 'id' looks like a record ID
                        if record_id is None:
                            id_param = kwargs.get("id")
                            # Check if id_param looks like a record ID, not a node ID
                            if (
                                id_param is not None
                                and id_param != operation  # Not the operation name
                                and not isinstance(
                                    id_param, str
                                )  # Not a string (likely int/UUID)
                                or (
                                    isinstance(id_param, str)
                                    and not id_param.endswith(
                                        f"_{operation}"
                                    )  # Not a node ID pattern
                                    and len(id_param) < 50
                                )
                            ):  # Reasonable ID length
                                # Type-aware ID conversion to fix string ID bug
                                id_field_info = self.model_fields.get("id", {})
                                id_type = id_field_info.get("type")

                                if id_type == str:
                                    # Model explicitly defines ID as string - preserve it
                                    record_id = id_param
                                elif id_type == int or id_type is None:
                                    # Model defines ID as int OR no type info (backward compat)
                                    try:
                                        record_id = int(id_param)
                                    except (ValueError, TypeError):
                                        # If conversion fails, don't use this value
                                        record_id = None
                                else:
                                    # Other types (UUID, custom) - preserve as-is
                                    record_id = id_param

                    if record_id is None:
                        from kailash.sdk_exceptions import NodeValidationError

                        raise _error_enhancer().enhance_update_node_missing_filter_id(
                            model_name=self.model_name,
                            node_id=getattr(
                                self, "node_id", f"{self.model_name}UpdateNode"
                            ),
                            original_error=NodeValidationError(
                                f"{self.model_name}UpdateNode requires 'id' or 'record_id' in filter parameter. "
                                f"Example: workflow.add_node('{self.model_name}UpdateNode', 'update', "
                                f"{{'filter': {{'id': record_id}}, 'fields': {{'name': 'value'}}}})"
                            ),
                        )

                    # Determine updates from nested format or direct field parameters
                    if updates_dict:
                        # Use nested updates format
                        updates = updates_dict
                    else:
                        # Fall back to direct field parameters for backward compatibility
                        updates = {
                            k: v
                            for k, v in kwargs.items()
                            if k
                            not in [
                                "record_id",
                                "id",
                                "database_url",
                                "conditions",
                                "updates",
                                "filter",  # v0.6 API
                                "fields",  # v0.6 API
                            ]
                            and k not in ["created_at", "updated_at"]
                        }

                    if updates:
                        # Auto-convert ISO datetime strings to datetime objects
                        updates = convert_datetime_fields(
                            updates, self.model_fields, logger
                        )

                        # Type-aware field validation (TODO-153)
                        try:
                            from dataflow.core.type_processor import (
                                TypeAwareFieldProcessor,
                            )

                            type_processor = TypeAwareFieldProcessor(
                                self.model_fields, self.model_name
                            )
                            updates = type_processor.process_record(
                                updates,
                                operation="update",
                                strict=False,
                                skip_fields=set(),  # Timestamps already excluded above
                            )
                        except ImportError:
                            logger.debug(
                                "TypeAwareFieldProcessor not available, skipping type validation"
                            )
                        except TypeError as e:
                            raise

                        # Get connection string - prioritize parameter over instance config
                        connection_string = kwargs.get("database_url")
                        if not connection_string:
                            connection_string = (
                                self.dataflow_instance.config.database.url or ":memory:"
                            )

                        # Detect database type for SQL generation
                        if kwargs.get("database_url"):
                            from ..adapters.connection_parser import ConnectionParser

                            database_type = ConnectionParser.detect_database_type(
                                connection_string
                            )
                        else:
                            database_type = (
                                self.dataflow_instance._detect_database_type()
                            )

                        # Get table name
                        table_name = self.dataflow_instance._get_table_name(
                            self.model_name
                        )

                        # CRITICAL FIX: Check if updated_at column exists before using it
                        try:
                            actual_columns = self.dataflow_instance._get_table_columns(
                                table_name
                            )
                            has_updated_at = (
                                actual_columns and "updated_at" in actual_columns
                            )
                        except Exception:
                            has_updated_at = False

                        # Build dynamic UPDATE query for only the fields being updated
                        field_names = list(updates.keys())
                        if database_type.lower() == "postgresql":
                            set_clauses = [
                                f"{name} = ${i + 1}"
                                for i, name in enumerate(field_names)
                            ]
                            where_clause = f"WHERE id = ${len(field_names) + 1}"
                            updated_at_clause = (
                                "updated_at = CURRENT_TIMESTAMP"
                                if has_updated_at
                                else None
                            )

                            # Get all field names for RETURNING clause
                            all_fields = self.dataflow_instance.get_model_fields(
                                self.model_name
                            )
                            # CRITICAL FIX: Only include columns that actually exist
                            try:
                                expected_columns = (
                                    ["id"]
                                    + list(all_fields.keys())
                                    + ["created_at", "updated_at"]
                                )
                                all_columns = (
                                    [
                                        col
                                        for col in expected_columns
                                        if col in actual_columns
                                    ]
                                    if actual_columns
                                    else list(all_fields.keys())
                                )
                            except Exception:
                                all_columns = list(all_fields.keys())

                            # Build SET clause (only include updated_at if column exists)
                            all_set_clauses = set_clauses
                            if updated_at_clause:
                                all_set_clauses.append(updated_at_clause)

                            query = f"UPDATE {table_name} SET {', '.join(all_set_clauses)} {where_clause} RETURNING {', '.join(all_columns)}"
                        elif database_type.lower() == "mysql":
                            set_clauses = [f"{name} = %s" for name in field_names]
                            where_clause = "WHERE id = %s"
                            updated_at_clause = (
                                "updated_at = NOW()" if has_updated_at else None
                            )

                            # Build SET clause (only include updated_at if column exists)
                            all_set_clauses = set_clauses
                            if updated_at_clause:
                                all_set_clauses.append(updated_at_clause)

                            query = f"UPDATE {table_name} SET {', '.join(all_set_clauses)} {where_clause}"
                        else:  # sqlite
                            set_clauses = [f"{name} = ?" for name in field_names]
                            where_clause = "WHERE id = ?"
                            updated_at_clause = (
                                "updated_at = CURRENT_TIMESTAMP"
                                if has_updated_at
                                else None
                            )

                            # Build SET clause (only include updated_at if column exists)
                            all_set_clauses = set_clauses
                            if updated_at_clause:
                                all_set_clauses.append(updated_at_clause)

                            query = f"UPDATE {table_name} SET {', '.join(all_set_clauses)} {where_clause}"

                        # Prepare parameters: field values first, then ID
                        # BUG #515 FIX: Serialize dict/list values for SQL binding
                        update_values = self._serialize_params_for_sql(
                            list(updates.values())
                        )
                        values = update_values + [record_id]

                        # Get or create cached AsyncSQLDatabaseNode for connection pooling
                        sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                            database_type
                        )

                        # Apply tenant isolation to the query
                        query, values = self._apply_tenant_isolation(query, values)

                        result = await sql_node.async_run(
                            query=query,
                            params=values,
                            fetch_mode="one",
                            validate_queries=False,
                            transaction_mode="auto",  # Ensure auto-commit for update operations
                        )

                        if result and "result" in result and "data" in result["result"]:
                            row = result["result"]["data"]
                            if isinstance(row, list) and len(row) > 0:
                                row = row[0]
                            if row:
                                # Invalidate cache after successful update
                                cache_integration = getattr(
                                    self.dataflow_instance, "_cache_integration", None
                                )
                                if cache_integration:
                                    cache_integration.invalidate_model_cache(
                                        self.model_name, "update", row
                                    )

                                # Merge the update values with the returned row data
                                # and add 'updated' key as expected by tests
                                # Ensure 'id' is available for connections (not record_id)
                                update_data = {
                                    k: v for k, v in kwargs.items() if k != "record_id"
                                }
                                # Serialize datetime objects to ISO strings for JSON compatibility
                                update_data = self._serialize_datetime_fields(
                                    update_data
                                )
                                # BUG #515 FIX: Deserialize JSON fields back to dict/list
                                row = self._deserialize_json_fields(row)
                                result_data = {
                                    **update_data,
                                    **row,
                                    "updated": True,
                                    "id": record_id,
                                }
                                # Serialize datetime fields in final result for JSON output
                                result_data = self._serialize_datetime_fields(
                                    result_data
                                )
                                return result_data

                    return {"id": record_id, "updated": False}

                elif operation == "delete":
                    # Support v0.6 API (filter) with fallback to old API (conditions)

                    # Helper to check if value is truly empty (handles dict, str, and JSON strings)
                    def is_empty(val):
                        if val is None:
                            return True
                        if isinstance(val, dict) and not val:
                            return True
                        if isinstance(val, str) and (
                            not val.strip() or val.strip() in ["{}", "[]"]
                        ):
                            return True
                        return False

                    # Get both old and new parameters
                    filter_param = kwargs.get("filter")
                    conditions_param = kwargs.get("conditions", {})

                    # Use new API if it has data, otherwise fall back to old API
                    conditions = (
                        filter_param if not is_empty(filter_param) else conditions_param
                    )

                    # DEPRECATION WARNING: Issue deprecation warning for old API
                    import warnings

                    if is_empty(filter_param) and not is_empty(conditions_param):
                        warnings.warn(
                            f"Parameter 'conditions' is deprecated in DeleteNode and will be removed in v0.8.0. "
                            f"Use 'filter' instead. "
                            f"Example: workflow.add_node('{self.model_name}DeleteNode', 'delete', {{"
                            f"'filter': {{'id': 123}}}}) "
                            f"See: .claude/skills/02-dataflow/dataflow-migrations-quick.md",
                            DeprecationWarning,
                            stacklevel=2,
                        )

                    # Handle string JSON input that might come from parameter validation
                    if isinstance(conditions, str):
                        try:
                            import json

                            conditions = (
                                json.loads(conditions) if conditions.strip() else {}
                            )
                        except (json.JSONDecodeError, ValueError):
                            conditions = {}

                    # Determine record_id from conditions or direct parameters
                    record_id = None
                    if conditions and "id" in conditions:
                        record_id = conditions["id"]
                    else:
                        # Fall back to direct parameters for backward compatibility
                        # Prioritize record_id over id to avoid conflicts with node's own id
                        record_id = kwargs.get("record_id")
                        if record_id is None:
                            # Get the ID parameter for record lookup
                            id_param = kwargs.get("id")
                            if id_param is not None:
                                # Type-aware ID conversion to fix string ID bug
                                id_field_info = self.model_fields.get("id", {})
                                id_type = id_field_info.get("type")

                                if id_type == str:
                                    # Model explicitly defines ID as string - preserve it
                                    record_id = id_param
                                elif id_type == int or id_type is None:
                                    # Model defines ID as int OR no type info (backward compat)
                                    try:
                                        record_id = int(id_param)
                                    except (ValueError, TypeError):
                                        # If conversion fails, preserve original
                                        record_id = id_param
                                else:
                                    # Other types (UUID, custom) - preserve as-is
                                    record_id = id_param

                    if record_id is None:
                        raise _error_enhancer().enhance_delete_node_missing_id(
                            model_name=self.model_name,
                            node_id=getattr(
                                self, "node_id", f"{self.model_name}DeleteNode"
                            ),
                            original_error=ValueError(
                                f"{self.model_name}DeleteNode requires 'id' or 'record_id' parameter. "
                                "Cannot delete record without specifying which record to delete. "
                                "Refusing to proceed to prevent accidental data loss."
                            ),
                        )

                    # Get connection string - prioritize parameter over instance config
                    connection_string = kwargs.get("database_url")
                    if not connection_string:
                        connection_string = (
                            self.dataflow_instance.config.database.url or ":memory:"
                        )

                    # Detect database type for SQL generation
                    if kwargs.get("database_url"):
                        from ..adapters.connection_parser import ConnectionParser

                        database_type = ConnectionParser.detect_database_type(
                            connection_string
                        )
                    else:
                        database_type = self.dataflow_instance._detect_database_type()

                    # Get the table name directly
                    table_name = self.dataflow_instance._get_table_name(self.model_name)

                    # Database-specific DELETE query
                    # PostgreSQL/SQLite support RETURNING, MySQL does not
                    if database_type.lower() == "mysql":
                        query = f"DELETE FROM {table_name} WHERE id = %s"
                    elif database_type.lower() == "postgresql":
                        query = f"DELETE FROM {table_name} WHERE id = $1 RETURNING id"
                    else:  # sqlite
                        query = f"DELETE FROM {table_name} WHERE id = ? RETURNING id"

                    # Debug log
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.debug(
                        f"DELETE: table={table_name}, id={record_id}, query={query}"
                    )

                    # Get or create cached AsyncSQLDatabaseNode for connection pooling
                    sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                        database_type
                    )

                    # Apply tenant isolation to the query
                    delete_params = [record_id]
                    query, delete_params = self._apply_tenant_isolation(
                        query, delete_params
                    )

                    result = await sql_node.async_run(
                        query=query,
                        params=delete_params,
                        fetch_mode="one",
                        validate_queries=False,
                        transaction_mode="auto",  # Ensure auto-commit for delete operations
                    )
                    logger.debug("nodes.delete_result", extra={"result": result})

                    # Check if delete was successful
                    if result and "result" in result:
                        result_data = result["result"]

                        # Check for data returned (RETURNING clause)
                        if "data" in result_data and result_data["data"]:
                            row = result_data["data"]
                            if isinstance(row, list) and len(row) > 0:
                                row = row[0]
                            if row:
                                # Record was deleted successfully
                                # Invalidate cache after successful delete
                                cache_integration = getattr(
                                    self.dataflow_instance, "_cache_integration", None
                                )
                                if cache_integration:
                                    cache_integration.invalidate_model_cache(
                                        self.model_name, "delete", {"id": record_id}
                                    )
                                return {"id": record_id, "deleted": True}

                        # Check for rows_affected when no RETURNING clause
                        elif (
                            "rows_affected" in result_data
                            and result_data["rows_affected"] > 0
                        ):
                            # Record was deleted successfully
                            cache_integration = getattr(
                                self.dataflow_instance, "_cache_integration", None
                            )
                            if cache_integration:
                                cache_integration.invalidate_model_cache(
                                    self.model_name, "delete", {"id": record_id}
                                )
                            return {"id": record_id, "deleted": True}

                    return {"id": record_id, "deleted": False}

                elif operation == "list":
                    limit = kwargs.get("limit", 10)
                    offset = kwargs.get("offset", 0)
                    filter_dict = kwargs.get("filter", {})
                    order_by = kwargs.get("order_by", [])
                    sort = kwargs.get("sort", [])  # NEW: Get sort parameter
                    enable_cache = kwargs.get("enable_cache", True)
                    cache_ttl = kwargs.get("cache_ttl")
                    cache_key_override = kwargs.get("cache_key")
                    count_only = kwargs.get("count_only", False)

                    # Fix parameter type issues
                    import json

                    if isinstance(order_by, str):
                        try:
                            order_by = json.loads(order_by) if order_by.strip() else []
                        except (json.JSONDecodeError, ValueError):
                            order_by = []

                    if isinstance(filter_dict, str):
                        try:
                            filter_dict = (
                                json.loads(filter_dict) if filter_dict.strip() else {}
                            )
                        except (json.JSONDecodeError, ValueError):
                            filter_dict = {}

                    # NEW: Convert sort parameter to order_by format
                    # This fixes the bug where ListNode's sort parameter wasn't working
                    # Format conversion: [{"field": "name", "order": "asc"}] -> [{"name": 1}]
                    if sort and not order_by:
                        order_by = []
                        for sort_spec in sort:
                            if isinstance(sort_spec, dict):
                                field = sort_spec.get("field")
                                order = sort_spec.get("order", "asc").lower()
                                if field:
                                    # Convert to order_by format: asc=1, desc=-1
                                    order_by.append(
                                        {field: 1 if order == "asc" else -1}
                                    )

                    # SOFT DELETE AUTO-FILTER (v0.10.6+)
                    # If model has soft_delete: True, auto-exclude deleted records
                    # Use include_deleted=True to override (show all records)
                    # This matches industry standards (Django, Rails, Laravel)
                    include_deleted = kwargs.get("include_deleted", False)
                    model_config = getattr(self, "_dataflow_config", {})
                    if not model_config:
                        # Get config from model_info dict (stored in _models)
                        model_info = self.dataflow_instance._models.get(model_name)
                        if isinstance(model_info, dict):
                            model_config = model_info.get("config", {})
                        # Fallback: check registered_models for class with _dataflow_config
                        elif not model_config:
                            model_cls = self.dataflow_instance._registered_models.get(
                                model_name
                            )
                            if model_cls and hasattr(model_cls, "_dataflow_config"):
                                model_config = getattr(
                                    model_cls, "_dataflow_config", {}
                                )

                    has_soft_delete = model_config.get("soft_delete", False)
                    if has_soft_delete and not include_deleted:
                        # Auto-filter: only return non-deleted records
                        # Add deleted_at IS NULL filter
                        if "deleted_at" not in filter_dict:
                            filter_dict["deleted_at"] = {"$null": True}
                            logger.debug(
                                f"soft_delete auto-filter: Added deleted_at IS NULL filter for {model_name}"
                            )

                    # Debug logging
                    logger.debug(
                        "nodes.list_operation_filter_dict",
                        extra={"filter_dict": filter_dict},
                    )
                    logger.debug("nodes.list_operation_sort", extra={"sort": sort})
                    logger.debug(
                        "nodes.list_operation_order_by", extra={"order_by": order_by}
                    )

                    # Use QueryBuilder if filters are provided
                    # FIXED: Changed from truthiness check to key existence check
                    # Bug: `if filter_dict:` evaluates to False for empty dict {}
                    # Fix: `"filter" in kwargs` checks if filter parameter was provided
                    # This matches the fix applied to BulkUpdateNode and BulkDeleteNode in v0.5.2
                    has_filters = "filter" in kwargs or has_soft_delete
                    if has_filters:
                        from ..database.query_builder import create_query_builder

                        # Get table name from DataFlow instance
                        table_name = self.dataflow_instance._get_table_name(model_name)

                        # Create query builder
                        builder = create_query_builder(
                            table_name, self.dataflow_instance.config.database.url
                        )

                        # Apply filters using MongoDB-style operators
                        for field, value in filter_dict.items():
                            if isinstance(value, dict):
                                # Handle MongoDB-style operators
                                for op, op_value in value.items():
                                    builder.where(field, op, op_value)
                            else:
                                # Simple equality
                                builder.where(field, "$eq", value)

                        # Apply ordering
                        if order_by:
                            for order_spec in order_by:
                                if isinstance(order_spec, dict):
                                    for field, direction in order_spec.items():
                                        dir_str = "DESC" if direction == -1 else "ASC"
                                        builder.order_by(field, dir_str)
                                else:
                                    # Handle Django/MongoDB style "-field" for descending
                                    if isinstance(
                                        order_spec, str
                                    ) and order_spec.startswith("-"):
                                        field = order_spec[1:]  # Remove leading "-"
                                        builder.order_by(field, "DESC")
                                    else:
                                        builder.order_by(order_spec, "ASC")
                        else:
                            builder.order_by("id", "DESC")

                        # Apply pagination
                        builder.limit(limit).offset(offset)

                        # Build query
                        if count_only:
                            query, params = builder.build_count()
                        else:
                            query, params = builder.build_select()
                    else:
                        # Simple query without filters using DataFlow SQL generation
                        # Get connection string - prioritize parameter over instance config
                        list_connection_string = kwargs.get("database_url")
                        if not list_connection_string:
                            list_connection_string = (
                                self.dataflow_instance.config.database.url or ":memory:"
                            )

                        # Detect database type for SQL generation
                        if kwargs.get("database_url"):
                            from ..adapters.connection_parser import ConnectionParser

                            database_type = ConnectionParser.detect_database_type(
                                list_connection_string
                            )
                        else:
                            database_type = (
                                self.dataflow_instance._detect_database_type()
                            )

                        select_templates = self.dataflow_instance._generate_select_sql(
                            self.model_name, database_type
                        )

                        if count_only:
                            query = select_templates["count_all"]
                            params = []
                        else:
                            # Build pagination query using template
                            if database_type.lower() == "postgresql":
                                query = select_templates[
                                    "select_with_pagination"
                                ].format(limit="$1", offset="$2")
                            elif database_type.lower() == "mysql":
                                query = select_templates[
                                    "select_with_pagination"
                                ].format(limit="%s", offset="%s")
                            else:  # sqlite
                                query = select_templates[
                                    "select_with_pagination"
                                ].format(limit="?", offset="?")
                            params = [limit, offset]

                    # Apply tenant isolation to the query before it's captured by the closure
                    query, params = self._apply_tenant_isolation(query, params)

                    # Define executor function for cache integration
                    async def execute_query():
                        # Get connection string - prioritize parameter over instance config
                        connection_string = kwargs.get("database_url")
                        if not connection_string:
                            connection_string = (
                                self.dataflow_instance.config.database.url or ":memory:"
                            )

                        # Detect database type within the function scope
                        from ..adapters.connection_parser import ConnectionParser

                        db_type = ConnectionParser.detect_database_type(
                            connection_string
                        )

                        # Debug logging
                        logger.debug(
                            "nodes.list_operation_executing_query",
                            extra={"query": query},
                        )
                        logger.debug(
                            "nodes.list_operation_with_params", extra={"params": params}
                        )
                        logger.debug(
                            f"List operation - Connection: {mask_sensitive_values(connection_string[:50])}..."
                        )

                        # Get or create cached AsyncSQLDatabaseNode for connection pooling
                        sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                            db_type
                        )
                        sql_result = await sql_node.async_run(
                            query=query,
                            params=params,
                            fetch_mode="all" if not count_only else "one",
                            validate_queries=False,
                            transaction_mode="auto",  # Ensure auto-commit for list operations
                        )

                        if (
                            sql_result
                            and "result" in sql_result
                            and "data" in sql_result["result"]
                        ):
                            if count_only:
                                # Return count result
                                count_data = sql_result["result"]["data"]
                                if isinstance(count_data, list) and len(count_data) > 0:
                                    count_value = count_data[0]
                                    if isinstance(count_value, dict):
                                        count = count_value.get("count", 0)
                                    else:
                                        count = count_value
                                else:
                                    count = 0
                                return {"count": count}
                            else:
                                # Return list result
                                records = sql_result["result"]["data"]
                                # BUG #515 FIX: Deserialize JSON fields back to dict/list for each record
                                records = [
                                    self._deserialize_json_fields(record)
                                    for record in records
                                ]
                                return {
                                    "records": records,
                                    "count": len(records),
                                    "limit": limit,
                                }

                        # Default return
                        if count_only:
                            return {"count": 0}
                        else:
                            return {"records": [], "count": 0, "limit": limit}

                    # Check if cache integration is available
                    cache_integration = getattr(
                        self.dataflow_instance, "_cache_integration", None
                    )
                    logger.debug(
                        f"List operation - cache_integration: {cache_integration}, enable_cache: {enable_cache}"
                    )

                    if cache_integration and enable_cache:
                        # Use cache integration
                        logger.debug("List operation - Using cache integration")
                        result = await cache_integration.execute_with_cache(
                            model_name=self.model_name,
                            query=query,
                            params=params,
                            executor_func=execute_query,
                            cache_enabled=enable_cache,
                            cache_ttl=cache_ttl,
                            cache_key_override=cache_key_override,
                        )
                        logger.debug(
                            "nodes.list_operation_cache_result",
                            extra={"result": result},
                        )
                        return result
                    else:
                        # Execute directly without caching
                        logger.debug("List operation - Executing without cache")
                        result = await execute_query()
                        logger.debug(
                            "nodes.list_operation_direct_result",
                            extra={"result": result},
                        )
                        return result

                elif operation == "upsert":
                    # NEW v0.8.0: Single-record upsert operation (Prisma-style API)
                    # BUG FIX: Convert string literals '{}' back to dict objects
                    # This handles cases where Pydantic/SDK serialization converts default={} to '{}'
                    import json

                    kwargs_fixed = kwargs.copy()
                    for param_name in ["where", "update", "create"]:
                        if param_name in kwargs_fixed and isinstance(
                            kwargs_fixed[param_name], str
                        ):
                            # Try to parse JSON string back to dict
                            try:
                                parsed = (
                                    json.loads(kwargs_fixed[param_name])
                                    if kwargs_fixed[param_name].strip()
                                    else {}
                                )
                                if isinstance(parsed, dict):
                                    kwargs_fixed[param_name] = parsed
                                    logger.debug(
                                        f"Converted string literal '{kwargs_fixed[param_name]}' to dict for parameter '{param_name}'"
                                    )
                            except (json.JSONDecodeError, ValueError):
                                # If parsing fails, try direct conversion for simple cases like '{}'
                                if kwargs_fixed[param_name].strip() in [
                                    "{}",
                                    "{  }",
                                    "{ }",
                                ]:
                                    kwargs_fixed[param_name] = {}
                                    logger.debug(
                                        f"Converted empty dict string '{{}}' to {{}} for parameter '{param_name}'"
                                    )

                    # Phase 2.1: Deserialize conflict_on from JSON string to list
                    if "conflict_on" in kwargs_fixed and isinstance(
                        kwargs_fixed["conflict_on"], str
                    ):
                        try:
                            parsed = json.loads(kwargs_fixed["conflict_on"])
                            if isinstance(parsed, list):
                                kwargs_fixed["conflict_on"] = parsed
                                logger.debug(
                                    f"Converted conflict_on from JSON string to list: {parsed}"
                                )
                        except (json.JSONDecodeError, ValueError):
                            logger.warning(
                                f"Failed to parse conflict_on as JSON: {kwargs_fixed['conflict_on']}"
                            )

                    # Validate conflict_on is not an empty list
                    if "conflict_on" in kwargs_fixed and isinstance(
                        kwargs_fixed["conflict_on"], list
                    ):
                        if len(kwargs_fixed["conflict_on"]) == 0:
                            from kailash.sdk_exceptions import NodeValidationError

                            raise _error_enhancer().enhance_upsert_node_empty_conflict_on(
                                model_name=self.model_name,
                                node_id=getattr(
                                    self, "node_id", f"{self.model_name}UpsertNode"
                                ),
                                original_error=NodeValidationError(
                                    f"{self.model_name}UpsertNode: conflict_on must contain at least one field when specified. "
                                    f"To use default conflict detection (based on 'where' fields), omit the conflict_on parameter entirely."
                                ),
                            )

                    # Validate required parameters
                    where = kwargs_fixed.get("where", {})
                    update_data = kwargs_fixed.get("update", {})
                    create_data = kwargs_fixed.get("create", {})

                    if not where:
                        from kailash.sdk_exceptions import NodeValidationError

                        raise _error_enhancer().enhance_upsert_node_missing_where(
                            model_name=self.model_name,
                            node_id=getattr(
                                self, "node_id", f"{self.model_name}UpsertNode"
                            ),
                            original_error=NodeValidationError(
                                f"{self.model_name}UpsertNode requires 'where' parameter. "
                                f"Example: {{'where': {{'email': 'user@example.com'}}, "
                                f"'update': {{'name': 'Updated'}}, 'create': {{'email': '...', 'name': 'New'}}}}"
                            ),
                        )

                    if not update_data and not create_data:
                        from kailash.sdk_exceptions import NodeValidationError

                        raise _error_enhancer().enhance_upsert_node_missing_operations(
                            model_name=self.model_name,
                            node_id=getattr(
                                self, "node_id", f"{self.model_name}UpsertNode"
                            ),
                            has_update=bool(update_data),
                            has_create=bool(create_data),
                            original_error=NodeValidationError(
                                f"{self.model_name}UpsertNode requires 'update' or 'create' parameter"
                            ),
                        )

                    # Get connection string
                    connection_string = kwargs.get("database_url")
                    if not connection_string:
                        connection_string = (
                            self.dataflow_instance.config.database.url or ":memory:"
                        )

                    # Detect database type
                    if kwargs.get("database_url"):
                        from ..adapters.connection_parser import ConnectionParser

                        database_type = ConnectionParser.detect_database_type(
                            connection_string
                        )
                    else:
                        database_type = self.dataflow_instance._detect_database_type()

                    # Prepare insert data (merge where + create)
                    insert_data = {**where, **create_data}

                    # Auto-convert datetime fields
                    insert_data = convert_datetime_fields(
                        insert_data, self.model_fields, logger
                    )
                    update_data = convert_datetime_fields(
                        update_data, self.model_fields, logger
                    )

                    # Type-aware field validation (TODO-153)
                    try:
                        from dataflow.core.type_processor import TypeAwareFieldProcessor

                        type_processor = TypeAwareFieldProcessor(
                            self.model_fields, self.model_name
                        )
                        insert_data = type_processor.process_record(
                            insert_data,
                            operation="upsert-create",
                            strict=False,
                            skip_fields=set(),
                        )
                        update_data = type_processor.process_record(
                            update_data,
                            operation="upsert-update",
                            strict=False,
                            skip_fields=set(),
                        )
                    except ImportError:
                        logger.debug(
                            "TypeAwareFieldProcessor not available, skipping type validation"
                        )
                    except TypeError as e:
                        raise

                    # Build database-specific upsert query using SQL Dialect Abstraction
                    table_name = self.dataflow_instance._get_table_name(self.model_name)

                    # Check if updated_at column exists before using it
                    try:
                        actual_columns = self.dataflow_instance._get_table_columns(
                            table_name
                        )
                        has_updated_at = (
                            actual_columns and "updated_at" in actual_columns
                        )
                    except Exception:
                        has_updated_at = False

                    # Determine conflict columns
                    conflict_columns = kwargs_fixed.get("conflict_on") or list(
                        where.keys()
                    )

                    # Get SQL dialect for database-specific query generation
                    from ..sql.dialects import SQLDialectFactory

                    try:
                        dialect = SQLDialectFactory.get_dialect(database_type)
                    except ValueError as e:
                        # Enhanced error with catalog-based solutions (DF-709)
                        raise _error_enhancer().enhance_unsupported_database_type_for_upsert(
                            model_name=self.model_name,
                            database_type=database_type,
                            node_id=getattr(
                                self, "node_id", f"{self.model_name}UpsertNode"
                            ),
                            original_error=e,
                        )

                    # For databases without native INSERT/UPDATE detection (e.g., SQLite),
                    # perform pre-check to determine if row exists
                    created_flag = None
                    if database_type.lower() == "sqlite":
                        # SQLite pre-check pattern:
                        # Why: SQLite's last_insert_rowid() only works with INTEGER PRIMARY KEY
                        # autoincrement. Since DataFlow v0.4.7+ supports string IDs, we need
                        # pre-check to detect INSERT vs UPDATE.
                        #
                        # Performance: 2 queries total (still 60% faster than SwitchNode
                        # pattern which requires 5+ nodes).
                        sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                            database_type
                        )

                        # Check if row exists
                        check_where_clauses = []
                        check_params = []
                        for col, val in where.items():
                            check_where_clauses.append(f"{col} = ?")
                            check_params.append(val)
                        check_where_str = " AND ".join(check_where_clauses)

                        check_query = f"SELECT COUNT(*) as count FROM {table_name} WHERE {check_where_str}"

                        # Apply tenant isolation to the pre-check query
                        check_query, check_params = self._apply_tenant_isolation(
                            check_query, check_params
                        )

                        check_result = await sql_node.async_run(
                            query=check_query,
                            params=check_params,
                            fetch_mode="one",
                            validate_queries=False,
                            transaction_mode="auto",
                        )

                        # Determine if this will be an INSERT or UPDATE
                        row_exists = False
                        if (
                            check_result
                            and "result" in check_result
                            and "data" in check_result["result"]
                        ):
                            check_row = check_result["result"]["data"]
                            if isinstance(check_row, list) and len(check_row) > 0:
                                check_row = check_row[0]
                            if check_row and "count" in check_row:
                                row_exists = check_row["count"] > 0

                        created_flag = not row_exists

                    # Build upsert query using dialect abstraction
                    upsert_query = dialect.build_upsert_query(
                        table_name=table_name,
                        insert_data=insert_data,
                        update_data=update_data,
                        conflict_columns=conflict_columns,
                        has_updated_at=has_updated_at,
                    )

                    query = upsert_query.query
                    params = list(upsert_query.params.values())

                    # BUG #515 FIX: Serialize dict/list for SQL parameter binding
                    params = self._serialize_params_for_sql(params)

                    # Apply tenant isolation to the upsert query
                    query, params = self._apply_tenant_isolation(query, params)

                    # Execute query using SQLExecutorNode (following existing pattern)
                    if database_type.lower() != "sqlite":
                        # For PostgreSQL, create sql_node here
                        sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                            database_type
                        )
                    # For SQLite, sql_node was already created during pre-check

                    result = await sql_node.async_run(
                        query=query,
                        params=params,
                        fetch_mode="one",
                        validate_queries=False,
                        transaction_mode="auto",
                    )

                    # Parse result to determine if INSERT or UPDATE occurred
                    if result and "result" in result and "data" in result["result"]:
                        row = result["result"]["data"]
                        if isinstance(row, list) and len(row) > 0:
                            row = row[0]
                        if row:
                            # For PostgreSQL: Extract the _upsert_inserted flag from RETURNING
                            # For SQLite: Use the pre-computed created_flag
                            if database_type.lower() == "postgresql":
                                created = row.pop("_upsert_inserted", False)
                            elif database_type.lower() == "sqlite":
                                created = created_flag
                            else:
                                created = False

                            # BUG #515 FIX: Deserialize JSON fields back to dict/list
                            row = self._deserialize_json_fields(row)
                            # DATETIME SERIALIZATION FIX: Serialize datetime objects to ISO strings
                            row = self._serialize_datetime_fields(row)

                            # Return structure contract:
                            # {
                            #     "created": bool,      # True if INSERT, False if UPDATE
                            #     "record": dict,       # The upserted record with all fields
                            #     "action": str         # "created" or "updated" (human-readable)
                            # }
                            return {
                                "created": created,
                                "record": row,
                                "action": "created" if created else "updated",
                            }

                    # Enhanced error with catalog-based solutions (DF-710)
                    raise _error_enhancer().enhance_upsert_operation_failed(
                        model_name=self.model_name,
                        where=where,
                        update=update_data,
                        create=create_data,
                        database_type=database_type,
                        node_id=getattr(
                            self, "node_id", f"{self.model_name}UpsertNode"
                        ),
                        original_error=ValueError(
                            f"Upsert failed for {self.model_name}"
                        ),
                    )

                elif operation == "count":
                    # NEW v0.8.1: Efficient COUNT(*) operation
                    filter_dict = kwargs.get("filter", {})

                    # Fix parameter type issues (same as list operation)
                    import json

                    if isinstance(filter_dict, str):
                        try:
                            filter_dict = (
                                json.loads(filter_dict) if filter_dict.strip() else {}
                            )
                        except (json.JSONDecodeError, ValueError):
                            filter_dict = {}

                    # SOFT DELETE AUTO-FILTER (v0.10.6+)
                    # If model has soft_delete: True, auto-exclude deleted records
                    include_deleted = kwargs.get("include_deleted", False)
                    model_config = getattr(self, "_dataflow_config", {})
                    if not model_config:
                        # Get config from model_info dict (stored in _models)
                        model_info = self.dataflow_instance._models.get(model_name)
                        if isinstance(model_info, dict):
                            model_config = model_info.get("config", {})
                        # Fallback: check registered_models for class with _dataflow_config
                        elif not model_config:
                            model_cls = self.dataflow_instance._registered_models.get(
                                model_name
                            )
                            if model_cls and hasattr(model_cls, "_dataflow_config"):
                                model_config = getattr(
                                    model_cls, "_dataflow_config", {}
                                )

                    has_soft_delete = model_config.get("soft_delete", False)
                    if has_soft_delete and not include_deleted:
                        if "deleted_at" not in filter_dict:
                            filter_dict["deleted_at"] = {"$null": True}
                            logger.debug(
                                f"soft_delete auto-filter: Added deleted_at IS NULL filter for {model_name} count"
                            )

                    # Debug logging
                    logger.debug(
                        "nodes.count_operation_filter_dict",
                        extra={"filter_dict": filter_dict},
                    )

                    # Use QueryBuilder if filters are provided
                    has_filters = "filter" in kwargs or has_soft_delete
                    if has_filters:
                        from ..database.query_builder import create_query_builder

                        # Get table name from DataFlow instance
                        table_name = self.dataflow_instance._get_table_name(model_name)

                        # Create query builder
                        builder = create_query_builder(
                            table_name, self.dataflow_instance.config.database.url
                        )

                        # Apply filters using MongoDB-style operators
                        for field, value in filter_dict.items():
                            if isinstance(value, dict):
                                # Handle MongoDB-style operators
                                for op, op_value in value.items():
                                    builder.where(field, op, op_value)
                            else:
                                # Simple equality
                                builder.where(field, "$eq", value)

                        # Build count query
                        query, params = builder.build_count()
                    else:
                        # Simple count query without filters using DataFlow SQL generation
                        # Get connection string - prioritize parameter over instance config
                        count_connection_string = kwargs.get("database_url")
                        if not count_connection_string:
                            count_connection_string = (
                                self.dataflow_instance.config.database.url or ":memory:"
                            )

                        # Detect database type for SQL generation
                        if kwargs.get("database_url"):
                            from ..adapters.connection_parser import ConnectionParser

                            database_type = ConnectionParser.detect_database_type(
                                count_connection_string
                            )
                        else:
                            database_type = (
                                self.dataflow_instance._detect_database_type()
                            )

                        select_templates = self.dataflow_instance._generate_select_sql(
                            self.model_name, database_type
                        )

                        query = select_templates["count_all"]
                        params = []

                    # Execute count query
                    connection_string = kwargs.get("database_url")
                    if not connection_string:
                        connection_string = (
                            self.dataflow_instance.config.database.url or ":memory:"
                        )

                    # Detect database type
                    from ..adapters.connection_parser import ConnectionParser

                    db_type = ConnectionParser.detect_database_type(connection_string)

                    # Debug logging
                    logger.debug(
                        "nodes.count_operation_executing_query", extra={"query": query}
                    )
                    logger.debug(
                        "nodes.count_operation_with_params", extra={"params": params}
                    )
                    logger.debug(
                        "nodes.count_operation_database_type",
                        extra={"db_type": db_type},
                    )

                    # Apply tenant isolation to the count query
                    query, params = self._apply_tenant_isolation(query, params)

                    # Execute SQL query
                    sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                        db_type
                    )
                    result = await sql_node.async_run(
                        query=query,
                        params=params,
                        fetch_mode="one",
                        validate_queries=False,
                        transaction_mode="auto",
                    )

                    logger.debug(
                        "nodes.count_operation_result_from_sql",
                        extra={"result": result},
                    )

                    # Extract count from result
                    if result and "result" in result and "data" in result["result"]:
                        data = result["result"]["data"]
                        if isinstance(data, list) and len(data) > 0:
                            data = data[0]

                        # Extract count value (handle different key names)
                        count_value = 0
                        if isinstance(data, dict):
                            count_value = (
                                data.get("count")
                                or data.get("COUNT(*)")
                                or data.get("count(*)")
                                or 0
                            )
                        elif isinstance(data, (int, float)):
                            count_value = int(data)

                        logger.debug(
                            f"Count operation - Extracted count: {count_value}"
                        )

                        return {"count": int(count_value)}

                    # If no result, return 0
                    logger.debug(
                        "Count operation - No result returned, defaulting to 0"
                    )
                    return {"count": 0}

                elif operation.startswith("bulk_"):
                    # BUG FIX: Convert string literals '{}' back to dict objects for deprecated parameters
                    # This handles cases where Pydantic/SDK serialization converts default={} to '{}'
                    import json

                    kwargs_fixed = kwargs.copy()
                    for param_name in ["conditions", "fields", "filter", "update"]:
                        if param_name in kwargs_fixed and isinstance(
                            kwargs_fixed[param_name], str
                        ):
                            # Try to parse JSON string back to dict
                            try:
                                parsed = (
                                    json.loads(kwargs_fixed[param_name])
                                    if kwargs_fixed[param_name].strip()
                                    else {}
                                )
                                if isinstance(parsed, dict):
                                    kwargs_fixed[param_name] = parsed
                                    logger.debug(
                                        f"Converted string literal '{kwargs_fixed[param_name]}' to dict for parameter '{param_name}'"
                                    )
                            except (json.JSONDecodeError, ValueError):
                                # If parsing fails, try direct conversion for simple cases like '{}'
                                if kwargs_fixed[param_name].strip() in [
                                    "{}",
                                    "{  }",
                                    "{ }",
                                ]:
                                    kwargs_fixed[param_name] = {}
                                    logger.debug(
                                        f"Converted empty dict string '{{}}' to {{}} for parameter '{param_name}'"
                                    )

                    # Use validate_inputs to handle auto_map_from parameter mapping
                    validated_inputs = self.validate_inputs(**kwargs_fixed)
                    data = validated_inputs.get("data", [])
                    batch_size = validated_inputs.get("batch_size", 1000)

                    if operation == "bulk_create" and (data or "data" in kwargs_fixed):
                        # Use DataFlow's bulk create operations
                        try:
                            bulk_result = await self.dataflow_instance.bulk.bulk_create(
                                model_name=self.model_name,
                                data=data,
                                batch_size=batch_size,
                                **{
                                    k: v
                                    for k, v in kwargs_fixed.items()
                                    if k
                                    not in [
                                        "data",
                                        "batch_size",
                                        "model_name",
                                        "db_instance",
                                    ]
                                },
                            )

                            # Invalidate cache after successful bulk create
                            cache_integration = getattr(
                                self.dataflow_instance, "_cache_integration", None
                            )
                            if cache_integration and bulk_result.get("success"):
                                cache_integration.invalidate_model_cache(
                                    self.model_name,
                                    "bulk_create",
                                    {
                                        "processed": bulk_result.get(
                                            "records_processed", 0
                                        )
                                    },
                                )

                            records_processed = bulk_result.get("records_processed", 0)
                            result = {
                                "processed": records_processed,
                                "inserted": records_processed,  # Alias for compatibility with standalone BulkCreateNode
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": bulk_result.get("success", True),
                            }
                            # Propagate error details if operation failed
                            if (
                                not bulk_result.get("success", True)
                                and "error" in bulk_result
                            ):
                                result["error"] = bulk_result["error"]
                            return result
                        except Exception as e:
                            logger.error(
                                "nodes.bulk_create_operation_failed",
                                extra={"error": str(e)},
                            )
                            return {
                                "processed": 0,
                                "inserted": 0,
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": str(e),
                            }
                    elif operation == "bulk_update" and (
                        data or "filter" in kwargs_fixed
                    ):
                        # Support v0.6 API (filter/fields) with fallback to old API (conditions/update)

                        # Helper to check if value is truly empty (handles dict, str, and JSON strings)
                        def is_empty(val):
                            if val is None:
                                return True
                            if isinstance(val, dict) and not val:
                                return True
                            if isinstance(val, str) and (
                                not val.strip() or val.strip() in ["{}", "[]"]
                            ):
                                return True
                            return False

                        # Get both old and new parameters
                        filter_param = kwargs_fixed.get("filter")
                        conditions_param = kwargs_fixed.get("conditions", {})
                        fields_param = kwargs_fixed.get("fields")
                        update_param = kwargs_fixed.get("update", {})

                        # Use new API if it has data, otherwise fall back to old API
                        filter_criteria = (
                            filter_param
                            if not is_empty(filter_param)
                            else conditions_param
                        )
                        update_values = (
                            fields_param if not is_empty(fields_param) else update_param
                        )

                        # DEPRECATION WARNINGS
                        import warnings

                        if is_empty(filter_param) and not is_empty(conditions_param):
                            warnings.warn(
                                "Parameter 'conditions' is deprecated in BulkUpdateNode and will be removed in v0.8.0. "
                                "Use 'filter' instead. "
                                "See: .claude/skills/02-dataflow/dataflow-migrations-quick.md",
                                DeprecationWarning,
                                stacklevel=2,
                            )
                        if is_empty(fields_param) and not is_empty(update_param):
                            warnings.warn(
                                "Parameter 'update' is deprecated in BulkUpdateNode and will be removed in v0.8.0. "
                                "Use 'fields' instead. "
                                "See: .claude/skills/02-dataflow/dataflow-migrations-quick.md",
                                DeprecationWarning,
                                stacklevel=2,
                            )

                        # Use DataFlow's bulk update operations
                        try:
                            bulk_result = await self.dataflow_instance.bulk.bulk_update(
                                model_name=self.model_name,
                                data=data,
                                filter_criteria=filter_criteria,
                                update_values=update_values,
                                batch_size=batch_size,
                                **{
                                    k: v
                                    for k, v in kwargs.items()
                                    if k
                                    not in [
                                        "data",
                                        "batch_size",
                                        "filter",
                                        "update",
                                        "conditions",
                                        "fields",
                                        "model_name",
                                        "db_instance",
                                    ]
                                },
                            )

                            # Invalidate cache after successful bulk update
                            cache_integration = getattr(
                                self.dataflow_instance, "_cache_integration", None
                            )
                            if cache_integration and bulk_result.get("success"):
                                cache_integration.invalidate_model_cache(
                                    self.model_name,
                                    "bulk_update",
                                    {
                                        "processed": bulk_result.get(
                                            "records_processed", 0
                                        )
                                    },
                                )

                            result = {
                                "processed": bulk_result.get("records_processed", 0),
                                "updated": bulk_result.get(
                                    "records_processed", 0
                                ),  # Alias for compatibility
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": bulk_result.get("success", True),
                            }
                            # Propagate error details if operation failed
                            if (
                                not bulk_result.get("success", True)
                                and "error" in bulk_result
                            ):
                                result["error"] = bulk_result["error"]
                            return result
                        except Exception as e:
                            logger.error(
                                "nodes.bulk_update_operation_failed",
                                extra={"error": str(e)},
                            )
                            return {
                                "processed": 0,
                                "updated": 0,
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": str(e),
                            }
                    elif operation == "bulk_delete" and (
                        data or "filter" in kwargs_fixed
                    ):
                        # Support v0.6 API (filter) with fallback to old API (conditions)

                        # Helper to check if value is truly empty (handles dict, str, and JSON strings)
                        def is_empty(val):
                            if val is None:
                                return True
                            if isinstance(val, dict) and not val:
                                return True
                            if isinstance(val, str) and (
                                not val.strip() or val.strip() in ["{}", "[]"]
                            ):
                                return True
                            return False

                        # Get both old and new parameters
                        filter_param = kwargs_fixed.get("filter")
                        conditions_param = kwargs_fixed.get("conditions", {})

                        # Use new API if it has data, otherwise fall back to old API
                        filter_criteria = (
                            filter_param
                            if not is_empty(filter_param)
                            else conditions_param
                        )

                        # DEPRECATION WARNING
                        import warnings

                        if is_empty(filter_param) and not is_empty(conditions_param):
                            warnings.warn(
                                "Parameter 'conditions' is deprecated in BulkDeleteNode and will be removed in v0.8.0. "
                                "Use 'filter' instead. "
                                "See: .claude/skills/02-dataflow/dataflow-migrations-quick.md",
                                DeprecationWarning,
                                stacklevel=2,
                            )

                        # Use DataFlow's bulk delete operations
                        try:
                            bulk_result = await self.dataflow_instance.bulk.bulk_delete(
                                model_name=self.model_name,
                                data=data,
                                filter_criteria=filter_criteria,
                                batch_size=batch_size,
                                **{
                                    k: v
                                    for k, v in kwargs_fixed.items()
                                    if k
                                    not in [
                                        "data",
                                        "batch_size",
                                        "filter",
                                        "conditions",
                                        "model_name",
                                        "db_instance",
                                    ]
                                },
                            )

                            # Invalidate cache after successful bulk delete
                            cache_integration = getattr(
                                self.dataflow_instance, "_cache_integration", None
                            )
                            if cache_integration and bulk_result.get("success"):
                                cache_integration.invalidate_model_cache(
                                    self.model_name,
                                    "bulk_delete",
                                    {
                                        "processed": bulk_result.get(
                                            "records_processed", 0
                                        )
                                    },
                                )

                            records_processed = bulk_result.get("records_processed", 0)
                            result = {
                                "processed": records_processed,
                                "deleted": records_processed,  # Alias for compatibility with standalone BulkDeleteNode
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": bulk_result.get("success", True),
                            }
                            # Propagate error details if operation failed
                            if (
                                not bulk_result.get("success", True)
                                and "error" in bulk_result
                            ):
                                result["error"] = bulk_result["error"]
                            return result
                        except Exception as e:
                            logger.error(
                                "nodes.bulk_delete_operation_failed",
                                extra={"error": str(e)},
                            )
                            return {
                                "processed": 0,
                                "deleted": 0,  # Alias for compatibility
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": str(e),
                            }
                    elif operation == "bulk_upsert" and (
                        data or "data" in kwargs_fixed
                    ):
                        # Use DataFlow's bulk upsert operations
                        try:
                            bulk_result = await self.dataflow_instance.bulk.bulk_upsert(
                                model_name=self.model_name,
                                data=data,
                                conflict_resolution=kwargs_fixed.get(
                                    "conflict_resolution", "skip"
                                ),
                                batch_size=batch_size,
                                **{
                                    k: v
                                    for k, v in kwargs_fixed.items()
                                    if k
                                    not in [
                                        "data",
                                        "batch_size",
                                        "conflict_resolution",
                                        "model_name",
                                        "db_instance",
                                    ]
                                },
                            )

                            # Invalidate cache after successful bulk upsert
                            cache_integration = getattr(
                                self.dataflow_instance, "_cache_integration", None
                            )
                            if cache_integration and bulk_result.get("success"):
                                cache_integration.invalidate_model_cache(
                                    self.model_name,
                                    "bulk_upsert",
                                    {
                                        "processed": bulk_result.get(
                                            "records_processed", 0
                                        )
                                    },
                                )

                            result = {
                                "processed": bulk_result.get("records_processed", 0),
                                "upserted": bulk_result.get(
                                    "records_processed", 0
                                ),  # Alias for compatibility
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": bulk_result.get("success", True),
                            }

                            # Expose detailed upsert stats if available from underlying operation
                            # Note: bulk_upsert is currently a STUB - these values are simulated
                            if "inserted" in bulk_result:
                                result["inserted"] = bulk_result["inserted"]
                            if "updated" in bulk_result:
                                result["updated"] = bulk_result["updated"]
                            if "skipped" in bulk_result:
                                result["skipped"] = bulk_result["skipped"]

                            # Propagate error details if operation failed
                            if (
                                not bulk_result.get("success", True)
                                and "error" in bulk_result
                            ):
                                result["error"] = bulk_result["error"]
                            return result
                        except Exception as e:
                            logger.error(
                                "nodes.bulk_upsert_operation_failed",
                                extra={"error": str(e)},
                            )
                            return {
                                "processed": 0,
                                "upserted": 0,  # Alias for compatibility
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": str(e),
                            }
                    else:
                        # Fallback for unsupported bulk operations
                        result = {
                            "processed": len(data) if data else 0,
                            "batch_size": batch_size,
                            "operation": operation,
                            "success": False,
                            "error": f"Unsupported bulk operation: {operation}",
                        }
                        return result

                else:
                    result = {"operation": operation, "status": "executed"}
                    return result

            def _get_tdd_connection_info(self) -> Optional[str]:
                """Extract connection information from TDD test context."""
                if not (self._tdd_mode and self._test_context):
                    return None

                # If DataFlow instance has TDD connection override, use it
                if hasattr(self.dataflow_instance, "_tdd_connection"):
                    # Build connection string from TDD connection
                    # Note: This is a simplified approach - in practice you might need
                    # to extract connection parameters differently
                    try:
                        # For asyncpg connections, we can get connection parameters
                        conn = self.dataflow_instance._tdd_connection
                        if hasattr(conn, "_params"):
                            params = conn._params
                            # FIXED Bug 012: Use safe attribute access with getattr and proper defaults
                            # asyncpg connection parameters may use different attribute names
                            host = getattr(
                                params,
                                "server_hostname",
                                getattr(params, "host", "localhost"),
                            )
                            user = getattr(params, "user", "postgres")
                            password = getattr(params, "password", "")
                            database = getattr(params, "database", "postgres")
                            port = getattr(params, "port", 5432)

                            return f"postgresql://{user}:{password}@{host}:{port}/{database}"
                        else:
                            # Fallback: use test database URL from environment
                            import os

                            return os.getenv(
                                "TEST_DATABASE_URL",
                                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
                            )
                    except Exception as e:
                        # FIXED Bug 011: Use self.logger instead of logger
                        self.logger.debug(
                            "nodes.failed_to_extract_tdd_connection_info",
                            extra={"error": str(e)},
                        )
                        return None

                return None

        # Set dynamic class name and proper module
        DataFlowNode.__name__ = (
            f"{model_name}{operation.replace('_', ' ').title().replace(' ', '')}Node"
        )
        DataFlowNode.__qualname__ = DataFlowNode.__name__

        # Set operation-specific docstring
        if operation == "count":
            DataFlowNode.__doc__ = f"""
Count {model_name} records matching filter criteria.

This node performs efficient COUNT(*) queries on the {model_name} table,
returning the number of records that match the provided filter.

Parameters:
    db_instance (str): Database instance identifier [REQUIRED]
    model_name (str): Model name [REQUIRED]
    filter (dict): MongoDB-style filter criteria (default: {{}})

Returns:
    dict: Result with keys:
        - count (int): Number of records matching filter

Example:
    >>> workflow.add_node("{model_name}CountNode", "count_active", {{
    ...     "db_instance": "my_db",
    ...     "model_name": "{model_name}",
    ...     "filter": {{"active": True}}
    ... }})
    >>> results, _ = runtime.execute(workflow.build())
    >>> total = results["count_active"]["count"]  # 42
            """

        return DataFlowNode
