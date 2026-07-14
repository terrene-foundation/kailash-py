"""
DataFlow Node Generation

Dynamic node generation for database operations.
"""

from typing import Any, Dict, List, Optional, Type

from .type_introspection import strip_annotated, union_non_none_args

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
from .exceptions import sanitize_db_error  # Issue #1552: redact driver-error VALUES
from .exceptions import (  # Issue #1519/#1520: typed conflict-target error propagation
    BulkUpsertConflictTargetError,
    UpsertConflictTargetError,
)
from .exceptions import is_conflict_target_error as _is_conflict_target_error
from .logging_config import mask_sensitive_values  # Phase 7: Sensitive value masking


def _resolve_scope_transaction(node: Any) -> Optional[Any]:
    """Return the active transaction-scope handle for a generated node, or ``None``.

    ``TransactionScopeNode`` stores an ``_AdapterTransactionScope`` under the
    workflow-context key ``active_transaction`` (the runtime injects the SAME
    ``_workflow_context`` dict onto every node in the workflow). This helper
    reads that scope and returns ``scope.transaction`` — the raw adapter txn
    handle ``(conn, tx)`` — so the caller can thread it into
    ``async_run(transaction=...)`` / ``bulk_*(transaction=...)``. Because the
    handle carries its OWN connection, the borrow branch in
    ``AsyncSQLDatabaseNode`` runs the statement ON the scope's connection
    regardless of which node/adapter issues it — the mechanism that makes both
    single-record CRUD (#1581) and bulk writes (#1585) join the scope.

    Fail-closed (#1581/#1585): an active scope that exposes no ``.transaction``
    handle raises ``NodeExecutionError`` rather than letting the write
    auto-commit and escape the scope. Returns ``None`` when no scope is active
    (``db.express`` calls, or a workflow with no transaction node) so the caller
    preserves the prior auto-commit behavior byte-for-byte.
    """
    scope = node.get_workflow_context("active_transaction")
    if scope is None:
        return None
    txn = getattr(scope, "transaction", None)
    if txn is None:
        from kailash.sdk_exceptions import NodeExecutionError

        raise NodeExecutionError(
            "active_transaction present in workflow context but exposes no "
            f"'.transaction' handle (got {type(scope).__name__}); refusing to "
            "run a write auto-commit and escape the transaction scope "
            "(#1581/#1585). The scope must be an _AdapterTransactionScope."
        )
    return txn


async def _run_sql_in_scope(node: Any, sql_node: Any, **kwargs: Any) -> Dict[str, Any]:
    """Run an ``AsyncSQLDatabaseNode`` call, joining an active transaction scope.

    Issue #1581: generated DataFlow CRUD nodes ran every statement on their own
    cached ``AsyncSQLDatabaseNode`` in ``transaction_mode="auto"`` (per-statement
    autocommit), so a CRUD write inside a ``TransactionScopeNode`` workflow
    committed independently and survived a later rollback.

    When a scope is present, this helper passes ``scope.transaction`` — the raw
    adapter txn handle — into ``async_run`` so the statement runs ON the scope's
    connection. The scope's ``TransactionCommitNode`` / ``TransactionRollbackNode``
    then governs the CRUD write. Reads (LIST/READ/COUNT) join too, giving
    read-your-writes inside the scope. Scope resolution + the fail-closed guard
    live in :func:`_resolve_scope_transaction` (shared with the #1585 bulk path).

    When no scope is active the call is byte-identical to the prior direct
    ``sql_node.async_run(**kwargs)`` — auto-commit behavior is preserved. An
    explicit ``transaction`` already present in ``kwargs`` is never overridden.
    """
    if "transaction" not in kwargs:
        txn = _resolve_scope_transaction(node)
        if txn is not None:
            kwargs["transaction"] = txn
            import logging

            logging.getLogger(__name__).debug(
                "nodes.crud_joined_transaction_scope",
                extra={"node": type(node).__name__},
            )
    return await sql_node.async_run(**kwargs)


def _normalize_field_specs(fields: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Normalize a model-fields dict into the canonical {"type": <type>, ...} shape.

    The canonical ``@db.model`` path produces dict-form values
    (``{"type": <type>, "required": True}``) — see engine.py
    ``_register_model_fields``. The public ``NodeGenerator`` API also accepts
    bare-type form (``{"name": str, "active": bool}``) for direct callers.
    Without this helper, downstream lookups
    ``self.model_fields.get(name, {}).get("type")`` raise
    ``AttributeError: type object 'str' has no attribute 'get'`` on the
    bare-type branch (issue #774).

    Single point of normalization at the constructor boundary makes the
    contract explicit: ``self.model_fields`` is dict-form everywhere
    downstream regardless of caller-supplied shape.
    """
    if not fields:
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for name, spec in fields.items():
        if isinstance(spec, dict):
            normalized[name] = spec
        else:
            normalized[name] = {"type": spec, "required": True}
    return normalized


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


def _coerce_record_id(model_fields: Dict[str, Any], id_value: Any) -> Any:
    """Coerce record_id to match the model's primary key type.

    Handles Optional[int], Union[int, None], and other wrapped types
    by normalizing the type annotation before comparison. Fixes #439:
    express_sync.update/read/delete reject integer record IDs on PostgreSQL
    when callers pass string IDs for integer primary key columns.

    Issue #774: defense-in-depth — accept both canonical dict-form and
    bare-type model_fields shapes; normalize on entry.
    """
    if id_value is None:
        return None

    id_field_info = model_fields.get("id", {})
    if not isinstance(id_field_info, dict):
        # bare-type form: id_field_info IS the type
        id_type = id_field_info
    else:
        id_type = id_field_info.get("type")

    if id_type is None:
        # No type info — try int conversion for backward compatibility
        if isinstance(id_value, str):
            try:
                return int(id_value)
            except (ValueError, TypeError):
                return id_value
        return id_value

    # Normalize type annotation to handle Optional[int], Union[int, None], etc.
    normalized = _normalize_id_type(id_type)

    if normalized == int:
        if isinstance(id_value, int):
            return id_value
        try:
            return int(id_value)
        except (ValueError, TypeError):
            return id_value
    elif normalized == str:
        return str(id_value) if not isinstance(id_value, str) else id_value
    else:
        # Other types (UUID, custom) — preserve as-is
        return id_value


def _normalize_id_type(type_annotation: Any) -> Any:
    """Normalize a type annotation for ID coercion, stripping Optional/Union wrappers."""
    # Strip a single Annotated[T, ...] layer first (issue #772 consolidation).
    type_annotation = strip_annotated(type_annotation)

    # Two-spelling union detection (typing.Union / Optional[T] AND PEP 604
    # ``T | None``) routes through the shared primitive (issue #772 / #1207 / #1228).
    non_none_types = union_non_none_args(type_annotation)
    if non_none_types is not None:
        if non_none_types:
            return _normalize_id_type(non_none_types[0])
        return str  # all-None union edge -> fallback

    if isinstance(type_annotation, type):
        return type_annotation

    return str  # fallback for unknown


def _unwrap_optional_type(type_annotation: Any) -> Any:
    """Unwrap ``Optional[T]`` / ``Union[T, None]`` / ``T | None`` to bare ``T``.

    Covers BOTH union spellings (issue #1207):

    1. ``typing.Optional[list]`` / ``typing.Union[list, None]`` —
       ``typing.get_origin(x) is typing.Union``.
    2. PEP 604 ``list | None`` (Python 3.10+) — produces a
       ``types.UnionType`` whose ``typing.get_origin(x)`` returns
       ``types.UnionType`` (NOT ``typing.Union``).

    Only single-non-None-arg unions collapse (e.g. ``Optional[list]`` -> ``list``).
    Multi-arg unions (``Union[list, dict]``) and non-union annotations are
    returned unchanged so the downstream ``in (dict, list)`` membership check
    behaves identically to a bare annotation.

    Two-spelling detection routes through the shared primitive (issue #772 /
    #1207); this caller keeps its collapse-only policy (single-non-None-arg
    unions collapse; multi-arg and all-None unions return unchanged).
    """
    non_none = union_non_none_args(type_annotation)
    if non_none is not None and len(non_none) == 1:
        return non_none[0]
    return type_annotation


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

        # Check if this field is defined as datetime in the model.
        # Issue #774: accept both dict-form ({"type": <type>}) and bare-type
        # ({"name": <type>}) shapes for defense-in-depth.
        field_info = model_fields.get(field_name, {})
        if not isinstance(field_info, dict):
            field_type = field_info
        else:
            field_type = field_info.get("type")

        # Handle Optional[datetime] AND PEP 604 ``datetime | None`` (#1207
        # sibling: the prior ``__origin__ is typing.Union`` check missed PEP 604
        # unions — a ``types.UnionType`` has no ``__origin__`` — so nullable
        # datetime fields declared ``datetime | None`` skipped parsing). Routing
        # through the shared helper covers both union spellings.
        field_type = _unwrap_optional_type(field_type)

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


def _make_append_only_forbidden_node(model_name: str, operation: str) -> Type[Node]:
    """Build a node class that rejects append-only mutation attempts.

    Issue #839: when ``@db.model(append_only=True)`` is declared, the
    Update / Delete / Upsert / BulkUpdate / BulkDelete / BulkUpsert
    surfaces are replaced with stubs that raise
    :class:`AppendOnlyViolationError` at construction time. This makes
    ``WorkflowBuilder.add_node("<Model>UpdateNode", ...)`` fail loudly
    with a typed, grep-able error AT add-node time — the rejection
    comes from the framework, not from application code monkey-patching
    ``WorkflowBuilder``.

    The class name carries the ``AppendOnlyForbiddenNode`` suffix in
    ``__qualname__`` so post-incident audits can grep for the pattern,
    but is registered under the original ``<Model><Op>Node`` alias so
    the user-facing error message references the name the caller used.
    """
    from dataflow.exceptions import AppendOnlyViolationError

    op_human = operation.replace("_", " ").capitalize()

    class AppendOnlyForbiddenNode(Node):
        """Stub registered for forbidden mutations on append-only models.

        Raises :class:`AppendOnlyViolationError` at construction time so
        every workflow path that attempts to add the node fails before
        any side effect.

        :class:`Node` is an ABC with abstract :meth:`get_parameters` and
        :meth:`run`. CPython checks abstract method satisfaction BEFORE
        calling ``__init__``; without concrete implementations Python
        raises ``TypeError: Can't instantiate abstract class …`` and the
        construction-time AppendOnlyViolationError never fires. We
        provide trivial concrete bodies so the ABC gate passes; the
        bodies are unreachable because ``__init__`` raises before any
        method is invoked.
        """

        def __init__(self, **kwargs):
            raise AppendOnlyViolationError(
                f"{op_human} rejected on append-only model "
                f"'{model_name}'. Models declared with "
                f"@db.model(append_only=True) only accept "
                f"Create / BulkCreate / Read / List / Count. Remove "
                f"`append_only=True` from the @db.model() decorator "
                f"to permit mutations. See issue #839."
            )

        # Concrete stubs for the Node ABC. ``__init__`` raises so the
        # happy path never reaches these bodies; required so Python's
        # abstract-method gate (CPython 3.11+ enforces the gate before
        # __init__) does not raise TypeError and shadow the typed
        # AppendOnlyViolationError.
        #
        # Issue #857: ``run()`` is reachable IF an attacker bypasses
        # __init__ via ``NodeClass.__new__(NodeClass)``. Defense in
        # depth: also raise from run() so __new__-bypassed instances
        # fail closed with the same typed error class — the security
        # promise of @db.model(append_only=True) holds regardless of
        # how the node was constructed.
        def get_parameters(self):  # pragma: no cover — unreachable on __init__ path
            return {}

        def run(self, **kwargs):
            raise AppendOnlyViolationError(
                f"{op_human} rejected on append-only model "
                f"'{model_name}'. Models declared with "
                f"@db.model(append_only=True) only accept "
                f"Create / BulkCreate / Read / List / Count. Remove "
                f"`append_only=True` from the @db.model() decorator "
                f"to permit mutations. See issue #839."
            )

    AppendOnlyForbiddenNode.__name__ = f"{model_name}{operation.capitalize()}Forbidden"
    AppendOnlyForbiddenNode.__qualname__ = AppendOnlyForbiddenNode.__name__
    return AppendOnlyForbiddenNode


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
        # Strip a single Annotated[T, ...] layer first (issue #772 consolidation):
        # Annotated annotations now resolve to their wrapped type instead of
        # falling through to the str fallback at the end of this method.
        type_annotation = strip_annotated(type_annotation)

        # Two-spelling union detection routes through the shared primitive
        # (issue #772 / #1207 / #1228): typing.Union / Optional[T] AND PEP 604
        # ``T | None``. This subsumes BOTH the prior standalone types.UnionType
        # block AND the ``origin is Union`` branch inside the __origin__ check.
        # Every non-empty union collapses to its first non-None arg (Optional,
        # single-arg union, and multi-arg union all normalize to the first
        # non-None member); an all-None union falls back to str. The Optional
        # wrapper itself is detected SEPARATELY for required=False in parameter
        # generation (see get_parameters); this method only returns the inner type.
        non_none_types = union_non_none_args(type_annotation)
        if non_none_types is not None:
            if non_none_types:
                return self._normalize_type_annotation(non_none_types[0])
            return str

        # Handle typing constructs
        if hasattr(type_annotation, "__origin__"):
            origin = type_annotation.__origin__

            # Handle List[T], Dict[K, V], etc. - return base container type
            if origin in (list, List):
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

    def generate_crud_nodes(
        self,
        model_name: str,
        fields: Dict[str, Any],
        *,
        append_only: bool = False,
    ):
        """Generate CRUD workflow nodes for a model.

        Issue #839: when ``append_only=True``, Update / Delete / Upsert
        are NOT generated as functional nodes; instead an
        ``AppendOnlyForbiddenNode`` stub is registered at each name so
        ``WorkflowBuilder.add_node("<Model>UpdateNode", ...)`` raises
        ``AppendOnlyViolationError`` at construction time.
        """
        # Read-side surfaces are always generated.
        nodes = {
            f"{model_name}CreateNode": self._create_node_class(
                model_name, "create", fields
            ),
            f"{model_name}ReadNode": self._create_node_class(
                model_name, "read", fields
            ),
            f"{model_name}ListNode": self._create_node_class(
                model_name, "list", fields
            ),
            # NEW v0.8.1: CountNode (efficient count queries)
            f"{model_name}CountNode": self._create_node_class(
                model_name, "count", fields
            ),
        }

        # Mutation-side surfaces — generated normally OR replaced with
        # AppendOnlyForbiddenNode stubs when append_only=True.
        mutation_ops = ("update", "delete", "upsert")
        for op in mutation_ops:
            node_name = f"{model_name}{op.capitalize()}Node"
            if append_only:
                nodes[node_name] = _make_append_only_forbidden_node(model_name, op)
            else:
                nodes[node_name] = self._create_node_class(model_name, op, fields)

        # Register nodes with Kailash's NodeRegistry system
        for node_name, node_class in nodes.items():
            # allow_override: @db.model regenerates CRUD node classes per
            # decoration; their names may coincide with static nodes — the
            # overwrite is intentional, exempt from the issue-#891 guard.
            NodeRegistry.register(node_class, alias=node_name, allow_override=True)
            # Also register in module namespace for direct imports
            globals()[node_name] = node_class
            # Store in DataFlow instance for testing
            self.dataflow_instance._nodes[node_name] = node_class

        return nodes

    def generate_bulk_nodes(
        self,
        model_name: str,
        fields: Dict[str, Any],
        *,
        append_only: bool = False,
    ):
        """Generate bulk operation nodes for a model.

        Issue #839: when ``append_only=True``, BulkUpdate / BulkDelete /
        BulkUpsert are replaced with ``AppendOnlyForbiddenNode`` stubs.
        Only ``BulkCreate`` is functional on append-only models.
        """
        nodes = {
            f"{model_name}BulkCreateNode": self._create_node_class(
                model_name, "bulk_create", fields
            ),
        }
        bulk_mutation_ops = ("bulk_update", "bulk_delete", "bulk_upsert")
        for op in bulk_mutation_ops:
            # bulk_update -> BulkUpdateNode (not Bulk_updateNode)
            camel = "".join(part.capitalize() for part in op.split("_"))
            node_name = f"{model_name}{camel}Node"
            if append_only:
                nodes[node_name] = _make_append_only_forbidden_node(model_name, op)
            else:
                nodes[node_name] = self._create_node_class(model_name, op, fields)

        # Register nodes with Kailash's NodeRegistry system
        for node_name, node_class in nodes.items():
            # allow_override: @db.model regenerates CRUD node classes per
            # decoration; their names may coincide with static nodes — the
            # overwrite is intentional, exempt from the issue-#891 guard.
            NodeRegistry.register(node_class, alias=node_name, allow_override=True)
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

                    # Issue #1207: a field declared Optional[list]/Optional[dict]
                    # (or PEP 604 ``list | None``) carries a Union annotation, NOT
                    # the bare ``list``/``dict`` type, so the membership check below
                    # was False and the raw JSON string leaked back to the caller.
                    # Unwrap the Optional wrapper so JSONB round-trips deserialize.
                    field_type = _unwrap_optional_type(field_type)

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
                # Issue #774: normalize bare-type field specs to canonical
                # {"type": <type>, "required": True} dict-form. Without this,
                # downstream lookups (.get(name, {}).get("type"), field_info["type"])
                # crash with AttributeError on bare-type values like {"name": str}.
                # Single point of normalization keeps the contract explicit.
                self.model_fields = _normalize_field_specs(fields)
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

                from .tenant_context import get_current_tenant_id

                # DDL operations bypass tenant isolation (auto-migrate and schema
                # bootstrap run with no tenant bound).
                query_upper = query.strip().upper()
                if query_upper.startswith(("CREATE ", "ALTER ", "DROP ")):
                    return query, params

                # Non-tenant models carry no tenant_id field — nothing to isolate.
                if "tenant_id" not in self.model_fields:
                    return query, params

                # Issue #1249 — FAIL CLOSED on a tenant-isolated model with no
                # bound tenant under multi_tenant. The legacy ``return query,
                # params`` here was a silent fail-OPEN: a write persisted a
                # tenant_id=NULL row and a read returned every tenant's rows
                # (the original cross-tenant leak class). Per tenant-isolation.md
                # MUST-2 + zero-tolerance.md Rule 3, refuse rather than execute an
                # unscoped statement. Single-tenant DataFlow (multi_tenant=False)
                # keeps the pass-through — there is no tenant to scope by.
                tenant_id = get_current_tenant_id()
                if not tenant_id:
                    multi_tenant = bool(
                        getattr(
                            getattr(
                                getattr(self.dataflow_instance, "config", None),
                                "security",
                                None,
                            ),
                            "multi_tenant",
                            False,
                        )
                    )
                    if multi_tenant:
                        raise RuntimeError(
                            f"Tenant isolation failed for {self.model_name}: "
                            f"multi_tenant=True but no tenant is bound to the current "
                            f"context. Bind one via db.tenant_context.switch(tenant_id) "
                            f"before this operation. Refusing to execute an unscoped "
                            f"query (potential cross-tenant leak)."
                        )
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

                        # Safe types that don't need sanitization (including
                        # dict/list/set/tuple). These are returned UNCHANGED
                        # so the downstream type-confusion gate (see the
                        # ``isinstance(value, (dict, list, set, tuple))`` check
                        # in the create/update + bulk_ branches of
                        # validate_inputs below) sees the real container type
                        # and raises ``ValueError("parameter type mismatch")``
                        # for a declared-``str`` field. ``set``/``tuple`` MUST
                        # be in this tuple: without them they fall through to
                        # ``value = str(value)`` BEFORE the gate runs, the gate
                        # then sees a ``str`` (isinstance False) and the
                        # confusion bypass goes undetected — the exact
                        # rules/security.md § Sanitizer Contract Rule 2
                        # violation issue #1047 closes. The gate (not this
                        # passthrough) is what enforces the raise; this list is
                        # "don't pre-coerce away the type the gate needs".
                        # Declared-dict / declared-list JSON / array columns
                        # (bug #515) also rely on dict/list passing through
                        # unchanged here — do NOT remove any entry.
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
                            set,
                            tuple,
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
                    # Issue #493 — declared-string fields MUST NOT receive
                    # dict / list / set / tuple values. Without this gate, a
                    # malicious upstream node can pass a nested structure that
                    # bypasses the string-only sanitizer. Sanitizer contract:
                    # token-replace for display + raise on a type mismatch.
                    # See ``rules/security.md`` § Sanitizer Contract.
                    for field_name, field_info in self.model_fields.items():
                        if field_name not in protected_inputs:
                            continue
                        declared_type = field_info.get("type")
                        value = protected_inputs[field_name]
                        if declared_type is str and isinstance(
                            value, (dict, list, set, tuple)
                        ):
                            raise ValueError(
                                "parameter type mismatch: field "
                                f"'{field_name}' declared as 'str' but received "
                                f"'{type(value).__name__}' — type confusion "
                                "blocked per rules/security.md § Sanitizer Contract"
                            )
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
                    # Validate bulk data doesn't contain injection.
                    # rules/security.md § Sanitizer Contract: declared-string
                    # fields MUST raise on dict / list / set / tuple inputs in
                    # bulk_create / bulk_update / bulk_upsert paths too — the
                    # same type-confusion guard as the create / update path.
                    bulk_data = protected_inputs.get("data", [])
                    if isinstance(bulk_data, list):
                        for i, record in enumerate(bulk_data):
                            if isinstance(record, dict):
                                for field_name, value in record.items():
                                    declared = self.model_fields.get(
                                        field_name, {}
                                    ).get("type")
                                    if declared is str and isinstance(
                                        value, (dict, list, set, tuple)
                                    ):
                                        raise ValueError(
                                            "parameter type mismatch: bulk "
                                            f"record[{i}].{field_name} declared as "
                                            f"'str' but received "
                                            f"'{type(value).__name__}' — type "
                                            "confusion blocked per "
                                            "rules/security.md § Sanitizer Contract"
                                        )
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
                            from typing import get_args

                            is_optional = False
                            field_type = field_info["type"]

                            # Two-spelling union detection routes through the shared
                            # primitive (issue #772 / #1228: typing.Union AND PEP 604
                            # ``T | None``). This is the SEPARATE Optional-detection
                            # contract (required=False from Optional[T]); it keeps its
                            # own policy -- a union is optional iff its args contained
                            # NoneType -- distinct from the type-normalization sites.
                            if union_non_none_args(field_type) is not None:
                                if type(None) in get_args(field_type):
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
                        # Issue #759 (DPI-A): the engine raises
                        # DDLFailedError from _check_failed_ddl /
                        # _execute_ddl[_async] when auto_migrate is in
                        # fail-fast mode. That typed exception is the
                        # documented circuit-breaker (issue #696) and
                        # MUST propagate to the caller — swallowing it
                        # here defeats the express layer's typed-error
                        # propagation and re-introduces the silent
                        # retry-storm failure mode.
                        # Other exceptions continue legacy
                        # log-and-continue semantics (e.g. "table
                        # already exists" races, transient adapter
                        # connect errors that the create operation
                        # itself can recover from).
                        from .exceptions import DDLFailedError as _DDLFailedError

                        if isinstance(e, _DDLFailedError):
                            logger.error(
                                "nodes.ensure_table_exists_failed_ddl_propagating",
                                extra={
                                    "model_name": self.model_name,
                                    "error": str(e),
                                },
                            )
                            raise
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

                        # Issue #480: quote identifiers via the dialect helper
                        # so reserved-word and mixed-case field names survive
                        # PostgreSQL's unquoted-identifier lowercasing rule.
                        # See rules/dataflow-identifier-safety.md MUST Rule 1.
                        from ..adapters.dialect import DialectManager

                        dialect = DialectManager.get_dialect(database_type)
                        quoted_table = dialect.quote_identifier(table_name)
                        columns = ", ".join(
                            dialect.quote_identifier(name) for name in field_names
                        )

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
                            quoted_returning = ", ".join(
                                dialect.quote_identifier(f) for f in returning_fields
                            )
                            query = (
                                f"INSERT INTO {quoted_table} ({columns}) "
                                f"VALUES ({placeholders}) RETURNING {quoted_returning}"
                            )
                        elif database_type.lower() == "mysql":
                            placeholders = ", ".join(["%s"] * len(field_names))
                            query = f"INSERT INTO {quoted_table} ({columns}) VALUES ({placeholders})"
                        else:  # sqlite
                            placeholders = ", ".join(["?"] * len(field_names))
                            query = f"INSERT INTO {quoted_table} ({columns}) VALUES ({placeholders})"

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

                        # Type-aware field validation
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
                        result = await _run_sql_in_scope(
                            self,
                            sql_node,
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
                                        f"SELECT * FROM {quoted_table} "
                                        f"WHERE {dialect.quote_identifier('id')} = ?"
                                    )
                                    readback_result = await _run_sql_in_scope(
                                        self,
                                        sql_node,
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
                        # Issue #759 (DPI-A): if the DDL circuit breaker
                        # raised, propagate without converting to the
                        # legacy ``{"success": False}`` dict — that
                        # conversion is exactly what swallowed the
                        # documented fail-fast surface end-to-end.
                        from .exceptions import DDLFailedError as _DDLFailedError

                        if isinstance(e, _DDLFailedError):
                            raise
                        # Issue #1552: sanitize at the source so the driver
                        # error's column VALUES (PG "DETAIL: Key(col)=(value)",
                        # MySQL "Duplicate entry 'value' for key") never reach a
                        # log line or the returned error dict. The param-mismatch
                        # detector substrings ("could not determine data type of
                        # parameter", "parameter $N") are NOT touched by
                        # sanitize_db_error, so the $11 detection below still fires.
                        original_error = sanitize_db_error(str(e))
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

                                    # #1581: inside a workflow transaction scope the
                                    # retry MUST run on the POOLED node that joins the
                                    # scope's connection. A fresh non-pooled node uses a
                                    # different connection and would silently escape the
                                    # transaction — the create would commit independently
                                    # and survive a rollback (the exact bug #1581 fixes).
                                    scope = self.get_workflow_context(
                                        "active_transaction"
                                    )
                                    if scope is not None:
                                        pooled_node = self.dataflow_instance._get_or_create_async_sql_node(
                                            database_type
                                        )
                                        result = await _run_sql_in_scope(
                                            self,
                                            pooled_node,
                                            query=fixed_sql,
                                            params=values,
                                            fetch_mode="one",  # RETURNING clause should return one record
                                            validate_queries=False,
                                        )
                                    else:
                                        # No scope: retry on a fresh (non-pooled) node.
                                        from kailash.nodes.data.async_sql import (
                                            AsyncSQLDatabaseNode,
                                        )

                                        sql_node = AsyncSQLDatabaseNode(
                                            connection_string=connection_string,
                                            database_type=database_type,
                                            # Issue #1741: the in-scope branch above
                                            # already rides credential_provider via
                                            # _get_or_create_async_sql_node; the no-scope
                                            # retry fallback opens its OWN fresh pool, so
                                            # it must carry the callback too or token auth
                                            # fails intermittently on the retry path.
                                            credential_provider=self.dataflow_instance.config.database.credential_provider,
                                        )
                                        # Fresh node — clean it up after the query so its
                                        # connection does not leak a ResourceWarning on GC
                                        # (issue #1560; same class as the 2.13.15
                                        # bulk_upsert._execute_query and
                                        # BulkCreatePoolNode._process_direct fixes). The
                                        # result dict is fully materialized by async_run,
                                        # so cleanup after is safe.
                                        try:
                                            result = await sql_node.async_run(
                                                query=fixed_sql,
                                                params=values,
                                                fetch_mode="one",  # RETURNING clause should return one record
                                                validate_queries=False,
                                                transaction_mode="auto",  # Ensure auto-commit for create operations
                                            )
                                        finally:
                                            await sql_node.cleanup()

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
                            # Issue #1552: log + return the SANITIZED driver
                            # error (one value for both surfaces) so a constraint
                            # violation cannot leak a column VALUE into the ERROR
                            # log or the returned error dict.
                            sanitized_error = sanitize_db_error(str(e))
                            logger.error(
                                "nodes.create_operation_failed",
                                extra={"error": sanitized_error},
                            )
                            error_msg = sanitized_error

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
                        record_id = _coerce_record_id(
                            self.model_fields, conditions["id"]
                        )
                    else:
                        # Fall back to direct parameters for backward compatibility
                        # Prioritize record_id over id to avoid conflicts with node's own id
                        record_id = kwargs.get("record_id")
                        if record_id is not None:
                            record_id = _coerce_record_id(self.model_fields, record_id)
                        else:
                            id_param = kwargs.get("id")
                            if id_param is not None:
                                record_id = _coerce_record_id(
                                    self.model_fields, id_param
                                )

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

                    # Use DataFlow's select SQL generation (Issue #1564: async
                    # twin — the sync detector returns [] inside the async_run
                    # event loop, degrading the SELECT column list).
                    select_templates = (
                        await self.dataflow_instance._generate_select_sql_async(
                            self.model_name, database_type
                        )
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

                    result = await _run_sql_in_scope(
                        self,
                        sql_node,
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
                        record_id = _coerce_record_id(
                            self.model_fields, conditions["id"]
                        )
                    else:
                        # Fall back to record_id parameter - prioritize this over 'id'
                        # since 'id' often contains the node ID which is not a record ID
                        record_id = kwargs.get("record_id")
                        if record_id is not None:
                            record_id = _coerce_record_id(self.model_fields, record_id)
                        else:
                            # Only use 'id' parameter if no record_id is available and 'id' looks like a record ID
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
                                record_id = _coerce_record_id(
                                    self.model_fields, id_param
                                )

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

                        # Type-aware field validation
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

                        # Issue #1564: resolve the physical column set via the
                        # async path. The sync _get_table_columns returns [] from
                        # inside the async_run event loop, which silently disabled
                        # the updated_at bump on PostgreSQL/SQLite.
                        try:
                            actual_columns = await self.dataflow_instance._resolve_table_columns_async(
                                self.model_name
                            )
                            has_updated_at = (
                                actual_columns and "updated_at" in actual_columns
                            )
                        except Exception as _e:
                            logger.debug(
                                "nodes.updated_at_detection_fallback",
                                extra={
                                    "model": self.model_name,
                                    "error_type": type(_e).__name__,
                                },
                            )
                            has_updated_at = False

                        # Issue #480: quote identifiers via the dialect
                        # helper so reserved-word and mixed-case field names
                        # survive PostgreSQL's unquoted-identifier lowercasing
                        # rule. See rules/dataflow-identifier-safety.md MUST
                        # Rule 1.
                        from ..adapters.dialect import DialectManager

                        dialect = DialectManager.get_dialect(database_type)
                        quoted_table = dialect.quote_identifier(table_name)
                        quoted_id = dialect.quote_identifier("id")
                        quoted_updated_at = dialect.quote_identifier("updated_at")

                        # Build dynamic UPDATE query for only the fields being updated
                        field_names = list(updates.keys())
                        if database_type.lower() == "postgresql":
                            set_clauses = [
                                f"{dialect.quote_identifier(name)} = ${i + 1}"
                                for i, name in enumerate(field_names)
                            ]
                            where_clause = (
                                f"WHERE {quoted_id} = ${len(field_names) + 1}"
                            )
                            updated_at_clause = (
                                f"{quoted_updated_at} = CURRENT_TIMESTAMP"
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

                            returning_str = ", ".join(
                                dialect.quote_identifier(c) for c in all_columns
                            )
                            query = (
                                f"UPDATE {quoted_table} "
                                f"SET {', '.join(all_set_clauses)} "
                                f"{where_clause} RETURNING {returning_str}"
                            )
                        elif database_type.lower() == "mysql":
                            set_clauses = [
                                f"{dialect.quote_identifier(name)} = %s"
                                for name in field_names
                            ]
                            where_clause = f"WHERE {quoted_id} = %s"
                            updated_at_clause = (
                                f"{quoted_updated_at} = NOW()"
                                if has_updated_at
                                else None
                            )

                            # Build SET clause (only include updated_at if column exists)
                            all_set_clauses = set_clauses
                            if updated_at_clause:
                                all_set_clauses.append(updated_at_clause)

                            query = f"UPDATE {quoted_table} SET {', '.join(all_set_clauses)} {where_clause}"
                        else:  # sqlite
                            set_clauses = [
                                f"{dialect.quote_identifier(name)} = ?"
                                for name in field_names
                            ]
                            where_clause = f"WHERE {quoted_id} = ?"
                            updated_at_clause = (
                                f"{quoted_updated_at} = CURRENT_TIMESTAMP"
                                if has_updated_at
                                else None
                            )

                            # Build SET clause (only include updated_at if column exists)
                            all_set_clauses = set_clauses
                            if updated_at_clause:
                                all_set_clauses.append(updated_at_clause)

                            query = f"UPDATE {quoted_table} SET {', '.join(all_set_clauses)} {where_clause}"

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

                        result = await _run_sql_in_scope(
                            self,
                            sql_node,
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
                        record_id = _coerce_record_id(
                            self.model_fields, conditions["id"]
                        )
                    else:
                        # Fall back to direct parameters for backward compatibility
                        # Prioritize record_id over id to avoid conflicts with node's own id
                        record_id = kwargs.get("record_id")
                        if record_id is not None:
                            record_id = _coerce_record_id(self.model_fields, record_id)
                        else:
                            id_param = kwargs.get("id")
                            if id_param is not None:
                                record_id = _coerce_record_id(
                                    self.model_fields, id_param
                                )

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

                    # Issue #480: quote identifiers via the dialect helper.
                    from ..adapters.dialect import DialectManager

                    dialect = DialectManager.get_dialect(database_type)
                    quoted_table = dialect.quote_identifier(table_name)
                    quoted_id = dialect.quote_identifier("id")

                    # SOFT DELETE (v0.10.6+ completion)
                    # If the model declares soft_delete: True, a DELETE is a
                    # tombstone UPDATE (deleted_at = now) rather than a physical
                    # row removal — matching the read-path auto-filter
                    # (list/read exclude deleted_at IS NOT NULL) and industry
                    # convention (Django, Rails, Laravel). The config-access
                    # pattern mirrors the list/read soft-delete blocks above.
                    model_config = getattr(self, "_dataflow_config", {})
                    if not model_config:
                        model_info = self.dataflow_instance._models.get(model_name)
                        if isinstance(model_info, dict):
                            model_config = model_info.get("config", {})
                        # Fall through (NOT elif) when the config dict is present
                        # but EMPTY — the soft_delete flag may live only on the
                        # registered class's _dataflow_config. Without this,
                        # DeleteNode would hard-delete a soft_delete model whose
                        # schema path DID create deleted_at → silent data loss
                        # (matches engine._model_has_soft_delete's independent checks).
                        if not model_config:
                            model_cls = self.dataflow_instance._registered_models.get(
                                model_name
                            )
                            if model_cls and hasattr(model_cls, "_dataflow_config"):
                                model_config = getattr(
                                    model_cls, "_dataflow_config", {}
                                )
                    has_soft_delete = model_config.get("soft_delete", False)

                    if has_soft_delete:
                        # Tombstone UPDATE. The ``AND deleted_at IS NULL`` guard
                        # makes a repeat delete a no-op (0 rows affected → not
                        # found), so an already-deleted row is not re-stamped.
                        quoted_deleted_at = dialect.quote_identifier("deleted_at")
                        if database_type.lower() == "mysql":
                            query = (
                                f"UPDATE {quoted_table} SET {quoted_deleted_at} = CURRENT_TIMESTAMP "
                                f"WHERE {quoted_id} = %s AND {quoted_deleted_at} IS NULL"
                            )
                        elif database_type.lower() == "postgresql":
                            query = (
                                f"UPDATE {quoted_table} SET {quoted_deleted_at} = CURRENT_TIMESTAMP "
                                f"WHERE {quoted_id} = $1 AND {quoted_deleted_at} IS NULL "
                                f"RETURNING {quoted_id}"
                            )
                        else:  # sqlite
                            query = (
                                f"UPDATE {quoted_table} SET {quoted_deleted_at} = CURRENT_TIMESTAMP "
                                f"WHERE {quoted_id} = ? AND {quoted_deleted_at} IS NULL "
                                f"RETURNING {quoted_id}"
                            )
                    # Database-specific DELETE query (hard delete)
                    # PostgreSQL/SQLite support RETURNING, MySQL does not
                    elif database_type.lower() == "mysql":
                        query = f"DELETE FROM {quoted_table} WHERE {quoted_id} = %s"
                    elif database_type.lower() == "postgresql":
                        query = f"DELETE FROM {quoted_table} WHERE {quoted_id} = $1 RETURNING {quoted_id}"
                    else:  # sqlite
                        query = f"DELETE FROM {quoted_table} WHERE {quoted_id} = ? RETURNING {quoted_id}"

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

                    result = await _run_sql_in_scope(
                        self,
                        sql_node,
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

                        select_templates = (
                            await self.dataflow_instance._generate_select_sql_async(
                                self.model_name, database_type
                            )
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
                            "nodes.list_operation_connection",
                            extra={"db_type": db_type},
                        )

                        # Get or create cached AsyncSQLDatabaseNode for connection pooling
                        sql_node = self.dataflow_instance._get_or_create_async_sql_node(
                            db_type
                        )
                        sql_result = await _run_sql_in_scope(
                            self,
                            sql_node,
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

                    # Type-aware field validation
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

                    # Issue #1564: resolve the physical column set via the async
                    # path. The sync _get_table_columns returns [] from inside the
                    # async_run event loop, which silently disabled the updated_at
                    # bump on PostgreSQL/SQLite.
                    try:
                        actual_columns = (
                            await self.dataflow_instance._resolve_table_columns_async(
                                self.model_name
                            )
                        )
                        has_updated_at = (
                            actual_columns and "updated_at" in actual_columns
                        )
                    except Exception as _e:
                        logger.debug(
                            "nodes.upsert_updated_at_detection_fallback",
                            extra={
                                "model": self.model_name,
                                "error_type": type(_e).__name__,
                            },
                        )
                        has_updated_at = False

                    # Determine conflict columns
                    conflict_columns = kwargs_fixed.get("conflict_on") or list(
                        where.keys()
                    )

                    # rules/dataflow-identifier-safety.md MUST-1 (redteam, #1519
                    # sibling class on the single-record path): the dialect
                    # builders interpolate table_name + column names (conflict
                    # target, INSERT/UPDATE columns, WHERE-precheck keys) as bare
                    # identifiers — drivers cannot bind identifiers. Record keys
                    # come from user-supplied create/update payloads and are NOT
                    # constrained to declared model fields upstream, so validate
                    # every interpolated identifier against the strict allowlist
                    # BEFORE the dialect builds SQL (same defense as the bulk
                    # path in features/bulk.py::bulk_upsert).
                    from kailash.db.dialect import _validate_identifier as _vid

                    _vid(table_name)
                    for _col in (
                        set(conflict_columns)
                        | set(where.keys())
                        | set(insert_data.keys())
                        | set(update_data.keys())
                    ):
                        _vid(_col)

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
                    # Issue #1546: resolved in the MySQL branch below to non-MariaDB
                    # MySQL >= 8.0.19 (the row-alias upsert form); default False keeps
                    # the deprecated-but-required VALUES() form for every other backend.
                    mysql_use_row_alias = False
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

                        check_result = await _run_sql_in_scope(
                            self,
                            sql_node,
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

                    elif database_type.lower() == "mysql":
                        # Issue #1537: MySQL's ON DUPLICATE KEY UPDATE has NO
                        # explicit conflict target — MySQL auto-detects whichever
                        # UNIQUE/PRIMARY key a candidate row violates. DataFlow
                        # mandates an `id` PK and generates a fresh id on the
                        # create branch, so a conflict_on=[non_unique_field]
                        # upsert hits no key violation → a plain INSERT lands a
                        # DUPLICATE row and conflict_on is silently ignored. This
                        # is the MySQL analog of #1520 (PostgreSQL), but a
                        # SILENT-wrong-result failure mode: MySQL raises no error,
                        # so the reactive `_is_conflict_target_error` catch below
                        # (which converts PostgreSQL's opaque driver message) can
                        # never fire. The complement is a PROACTIVE precheck:
                        # verify a UNIQUE/PRIMARY index whose column set is
                        # EXACTLY set(conflict_columns) backs the target BEFORE
                        # building the ON DUPLICATE KEY UPDATE; if absent, raise
                        # the same typed UpsertConflictTargetError (#1520) naming
                        # conflict_on + the remedy.
                        mysql_precheck_node = (
                            self.dataflow_instance._get_or_create_async_sql_node(
                                database_type
                            )
                        )

                        # Issue #1545: cache the per-table UNIQUE/PRIMARY index
                        # column-sets on the DataFlow instance. The #1537 precheck
                        # otherwise re-queries information_schema.statistics on
                        # EVERY single-record MySQL upsert. Populate once per table
                        # per process; the cache is invalidated by
                        # clear_schema_cache / clear_table_cache on any
                        # index-altering schema change (same hooks the schema cache
                        # uses). Correctness-neutral: the precheck below still
                        # raises UpsertConflictTargetError when no matching unique
                        # index backs conflict_on.
                        _ui_cache = self.dataflow_instance._unique_index_cache
                        _db_url = (
                            getattr(self.dataflow_instance.config.database, "url", "")
                            or ""
                        )
                        # Hash the db_url portion so no credential sits in the
                        # in-memory cache key (observability.md Rule 6.3). The
                        # ``:{table_name}`` suffix stays verbatim so
                        # ``engine.clear_table_cache``'s ``endswith(f":{table}")``
                        # invalidation still matches.
                        import hashlib as _hashlib

                        _db_url_hash = _hashlib.sha256(
                            _db_url.encode("utf-8")
                        ).hexdigest()[:16]
                        _ui_key = f"{_db_url_hash}:{table_name}"
                        unique_index_columns: Optional[Dict[str, set]] = _ui_cache.get(
                            _ui_key
                        )
                        if unique_index_columns is None:
                            # information_schema.statistics.table_schema / table_name
                            # are string VALUES, not SQL identifiers — bind them as
                            # parameters (DATABASE() for the live schema, %s for the
                            # table) so the lookup is injection-safe. table_name is
                            # ALSO validated by _vid above; this binding is the
                            # defense-in-depth for the information_schema lookup
                            # itself (rules/security.md § Parameterized Queries,
                            # rules/dataflow-identifier-safety.md). non_unique = 0
                            # selects UNIQUE and PRIMARY indexes only.
                            index_query = (
                                "SELECT index_name, column_name "
                                "FROM information_schema.statistics "
                                "WHERE table_schema = DATABASE() "
                                "AND table_name = %s "
                                "AND non_unique = 0"
                            )
                            index_result = await _run_sql_in_scope(
                                self,
                                mysql_precheck_node,
                                query=index_query,
                                params=[table_name],
                                fetch_mode="all",
                                validate_queries=False,
                                transaction_mode="auto",
                            )

                            # Group the fetched rows into {index_name: {columns}}.
                            unique_index_columns = {}
                            if (
                                index_result
                                and "result" in index_result
                                and "data" in index_result["result"]
                            ):
                                index_rows = index_result["result"]["data"]
                                if isinstance(index_rows, list):
                                    for _row in index_rows:
                                        if not isinstance(_row, dict):
                                            continue
                                        _idx = _row.get("index_name") or _row.get(
                                            "INDEX_NAME"
                                        )
                                        _col = _row.get("column_name") or _row.get(
                                            "COLUMN_NAME"
                                        )
                                        if _idx is None or _col is None:
                                            continue
                                        unique_index_columns.setdefault(
                                            _idx, set()
                                        ).add(_col)

                            _ui_cache[_ui_key] = unique_index_columns

                        # Issue #1546: resolve once whether this MySQL server
                        # supports the 8.0.19+ ``VALUES (...) AS alias`` row-alias
                        # upsert form (``VALUES(col)`` is deprecated on 8.0.20+).
                        # Centralized on the DataFlow instance — ONE cached
                        # SELECT VERSION() round-trip shared with the bulk paths.
                        mysql_use_row_alias = await self.dataflow_instance._resolve_mysql_row_alias_support(
                            mysql_precheck_node
                        )

                        # ON DUPLICATE KEY UPDATE behaves as upsert-on-conflict_on
                        # ONLY when conflict_on is ITSELF a unique/primary key.
                        # Require an EXACT column-set match: a unique index over a
                        # superset/subset of conflict_columns would trigger on a
                        # DIFFERENT conflict and silently ignore the caller's
                        # intent. A conflict_on that IS the `id` PK matches the
                        # PRIMARY index here and correctly proceeds.
                        target_columns = set(conflict_columns)
                        has_matching_unique_index = any(
                            cols == target_columns
                            for cols in unique_index_columns.values()
                        )
                        if not has_matching_unique_index:
                            logger.debug(
                                "upsert.mysql.conflict_target_not_unique",
                                extra={
                                    "model": self.model_name,
                                    "conflict_on": list(conflict_columns),
                                },
                            )
                            raise UpsertConflictTargetError(
                                conflict_on=conflict_columns,
                                model_name=self.model_name,
                            )

                    # Build upsert query using dialect abstraction.
                    # SQLite: emit an explicit INSERT/UPDATE from the pre-check
                    # result (row_exists) instead of INSERT ... ON CONFLICT, which
                    # requires the conflict target to be backed by a UNIQUE
                    # constraint. A conflict_on field that is not declared unique
                    # would otherwise fail with "ON CONFLICT clause does not match
                    # any PRIMARY KEY or UNIQUE constraint" (issue #1508).
                    if database_type.lower() == "sqlite":
                        upsert_query = dialect.build_precheck_upsert_query(
                            table_name=table_name,
                            insert_data=insert_data,
                            update_data=update_data,
                            where=where,
                            row_exists=row_exists,
                            has_updated_at=has_updated_at,
                        )
                    else:
                        # Cross-tenant WRITE breach fix (rules/tenant-isolation.md):
                        # for a multi_tenant model with a bound tenant, pass the
                        # tenant id so the native ON CONFLICT DO UPDATE carries a
                        # ``WHERE {table}.tenant_id = <bound>`` guard (PG/SQLite) /
                        # ``IF()`` guard (MySQL). A cross-tenant ``id`` collision
                        # then leaves the row untouched (0 rows returned), which
                        # the empty-RETURNING branch below converts into the
                        # actionable TenantNaturalKeyCollisionError. SQLite's
                        # single-record path (above) uses the tenant-scoped
                        # WHERE-precheck and is already fail-closed.
                        _tenant_guard_value = None
                        if "tenant_id" in self.model_fields:
                            from .tenant_context import get_current_tenant_id

                            _tenant_guard_value = get_current_tenant_id()
                        upsert_query = dialect.build_upsert_query(
                            table_name=table_name,
                            insert_data=insert_data,
                            update_data=update_data,
                            conflict_columns=conflict_columns,
                            has_updated_at=has_updated_at,
                            use_row_alias=mysql_use_row_alias,  # #1546
                            tenant_guard=_tenant_guard_value,
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

                    try:
                        result = await _run_sql_in_scope(
                            self,
                            sql_node,
                            query=query,
                            params=params,
                            fetch_mode="one",
                            validate_queries=False,
                            transaction_mode="auto",
                        )
                    except Exception as exec_err:
                        # Issue #1520: on the native ON CONFLICT path, a conflict
                        # target that is not a PK/UNIQUE key is a caller error,
                        # not a transient DB failure. PostgreSQL raises the opaque
                        # "there is no unique or exclusion constraint matching the
                        # ON CONFLICT specification"; convert it into the
                        # actionable typed error naming conflict_on + the remedy,
                        # mirroring the bulk path (#1519). In practice only the
                        # PostgreSQL builder reaches this matcher: SQLite's
                        # single-record upsert enters this same execute but runs
                        # the WHERE-precheck INSERT/UPDATE (#1508) — never an
                        # ON CONFLICT clause — so it cannot emit the trigger
                        # string; MySQL emits ON DUPLICATE KEY UPDATE (no
                        # ON-CONFLICT-target error). Non-matching errors re-raise
                        # unchanged below.
                        if _is_conflict_target_error(str(exec_err)):
                            raise UpsertConflictTargetError(
                                conflict_on=conflict_columns,
                                model_name=self.model_name,
                                original_error=exec_err,
                            ) from exec_err
                        raise

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

                            # Issue #1538: invalidate the node-level query cache
                            # (``_cache_integration``) after a successful upsert,
                            # exactly as the create/update/delete branches do
                            # (see the ``update`` branch above). Without this the
                            # UPDATE branch of an upsert leaves a previously-primed
                            # list/count entry in the node cache; a subsequent
                            # ``db.express.list(..., cache_ttl=0)`` bypasses the
                            # Express cache but still hits the stale node-cache
                            # entry and returns the pre-update row. The Express
                            # layer's ``_invalidate_model_cache`` only clears the
                            # Express cache manager, a DIFFERENT backend from
                            # ``_cache_integration`` — so this node-side call is
                            # the only thing that clears the node query cache on
                            # the upsert path. Paired with the ``upsert`` pattern
                            # registered in
                            # ``list_node_integration._setup_invalidation_patterns``
                            # (without a matching pattern this call would no-op).
                            cache_integration = getattr(
                                self.dataflow_instance, "_cache_integration", None
                            )
                            if cache_integration:
                                cache_integration.invalidate_model_cache(
                                    self.model_name, "upsert", row
                                )

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

                    # Cross-tenant WRITE breach fix (rules/tenant-isolation.md):
                    # a PostgreSQL native-ON-CONFLICT upsert on a multi_tenant
                    # model that returned 0 rows means the tenant-scoped
                    # DO-UPDATE guard suppressed a cross-tenant ``id`` collision
                    # (a same-tenant conflict updates + returns its row; a new
                    # row inserts + returns). Fail closed with the SAME actionable
                    # diagnostic the bulk path surfaces — never a silent no-op.
                    if (
                        database_type.lower() == "postgresql"
                        and "tenant_id" in self.model_fields
                    ):
                        from .tenant_context import get_current_tenant_id

                        _tid = get_current_tenant_id()
                        if _tid is not None:
                            from .exceptions import TenantNaturalKeyCollisionError

                            _cid = None
                            if isinstance(create_data, dict):
                                _cid = create_data.get("id")
                            if _cid is None and isinstance(where, dict):
                                _cid = where.get("id")
                            raise TenantNaturalKeyCollisionError(
                                model_name=self.model_name,
                                tenant_id=_tid,
                                colliding_id=_cid,
                            )

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

                        select_templates = (
                            await self.dataflow_instance._generate_select_sql_async(
                                self.model_name, database_type
                            )
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
                    result = await _run_sql_in_scope(
                        self,
                        sql_node,
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

                    # #1585: resolve the active transaction scope ONCE for every
                    # bulk op so bulk writes join a TransactionScopeNode and are
                    # governed by its commit/rollback (parity with single-record
                    # CRUD's _run_sql_in_scope). Fail-closed if a scope is present
                    # but exposes no `.transaction` handle. ``None`` when no scope
                    # is active → bulk_*() preserves prior auto-commit behavior.
                    scope_txn = _resolve_scope_transaction(self)

                    if operation == "bulk_create" and (data or "data" in kwargs_fixed):
                        # Use DataFlow's bulk create operations
                        try:
                            bulk_result = await self.dataflow_instance.bulk.bulk_create(
                                model_name=self.model_name,
                                data=data,
                                batch_size=batch_size,
                                transaction=scope_txn,  # #1585: join active scope
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
                            # Issue #1552: sanitize once, use for BOTH the ERROR
                            # log and the returned error dict so a constraint
                            # violation cannot leak a column VALUE.
                            sanitized = sanitize_db_error(str(e))
                            logger.error(
                                "nodes.bulk_create_operation_failed",
                                extra={"error": sanitized},
                            )
                            return {
                                "processed": 0,
                                "inserted": 0,
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": sanitized,
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
                                transaction=scope_txn,  # #1585: join active scope
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
                            # Issue #1552: sanitize once, use for BOTH the ERROR
                            # log and the returned error dict so a constraint
                            # violation cannot leak a column VALUE.
                            sanitized = sanitize_db_error(str(e))
                            logger.error(
                                "nodes.bulk_update_operation_failed",
                                extra={"error": sanitized},
                            )
                            return {
                                "processed": 0,
                                "updated": 0,
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": sanitized,
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
                                transaction=scope_txn,  # #1585: join active scope
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
                            # Issue #1552: sanitize once, use for BOTH the ERROR
                            # log and the returned error dict so a constraint
                            # violation cannot leak a column VALUE.
                            sanitized = sanitize_db_error(str(e))
                            logger.error(
                                "nodes.bulk_delete_operation_failed",
                                extra={"error": sanitized},
                            )
                            return {
                                "processed": 0,
                                "deleted": 0,  # Alias for compatibility
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": sanitized,
                            }
                    elif operation == "bulk_upsert" and (
                        data or "data" in kwargs_fixed
                    ):
                        # Use DataFlow's bulk upsert operations
                        try:
                            # Issue #1519: the express layer sets
                            # ``node.conflict_columns`` as an instance attribute
                            # (features/express.py); the workflow layer passes
                            # ``conflict_on`` in kwargs. Resolve from either.
                            conflict_on = kwargs_fixed.get("conflict_on") or getattr(
                                self, "conflict_columns", None
                            )
                            # Issue #1519: the express/generated bulk_upsert
                            # contract is insert-or-UPDATE. Default to "update"
                            # (DO UPDATE), NOT "skip" (DO NOTHING) — a PK conflict
                            # under the old "skip" default silently dropped the
                            # row instead of updating it.
                            conflict_resolution = (
                                kwargs_fixed.get("conflict_resolution")
                                or getattr(self, "conflict_resolution", None)
                                or "update"
                            )
                            bulk_result = await self.dataflow_instance.bulk.bulk_upsert(
                                model_name=self.model_name,
                                data=data,
                                conflict_resolution=conflict_resolution,
                                conflict_on=conflict_on,
                                batch_size=batch_size,
                                transaction=scope_txn,  # #1585: join active scope
                                **{
                                    k: v
                                    for k, v in kwargs_fixed.items()
                                    if k
                                    not in [
                                        "data",
                                        "batch_size",
                                        "conflict_resolution",
                                        "conflict_on",
                                        "conflict_columns",
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

                            records_processed = bulk_result.get("records_processed", 0)
                            result = {
                                "processed": records_processed,
                                "upserted": records_processed,  # Alias for compatibility
                                # Issue #1519: express reads ``total`` for the
                                # user-facing count; expose it from the real
                                # records_processed.
                                "total": records_processed,
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": bulk_result.get("success", True),
                            }

                            # Issue #1519: expose the real per-row counts derived
                            # by the bulk engine (PG xmax / SQLite pre-count /
                            # MySQL row_count). No longer a stub.
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
                            # Cross-tenant WRITE breach fix: propagate the
                            # structured cross-tenant-collision signal so the
                            # express layer surfaces the actionable #1526
                            # diagnostic (rules/tenant-isolation.md).
                            if bulk_result.get("cross_tenant_conflict"):
                                result["cross_tenant_conflict"] = True
                                result["skipped"] = bulk_result.get("skipped", 0)
                            return result
                        except BulkUpsertConflictTargetError:
                            # Issue #1519: caller-actionable conflict-target error
                            # MUST propagate as a typed raise, not flatten into a
                            # {"success": False} dict the express layer ignores.
                            raise
                        except Exception as e:
                            # Issue #1552: sanitize once, use for BOTH the ERROR
                            # log and the returned error dict so a constraint
                            # violation cannot leak a column VALUE.
                            sanitized = sanitize_db_error(str(e))
                            logger.error(
                                "nodes.bulk_upsert_operation_failed",
                                extra={"error": sanitized},
                            )
                            return {
                                "processed": 0,
                                "upserted": 0,  # Alias for compatibility
                                "batch_size": batch_size,
                                "operation": operation,
                                "success": False,
                                "error": sanitized,
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
