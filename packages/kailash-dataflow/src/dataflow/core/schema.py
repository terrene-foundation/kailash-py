"""
Schema Parser and Validation System

Provides type-safe schema parsing with automatic validation and migration generation.
This module was migrated from the old core/schema.py to maintain test compatibility.
"""

import inspect
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

from dataflow.exceptions import DataFlowError

from .type_introspection import (  # issue #772: shared union detection
    union_non_none_args,
)

logger = logging.getLogger(__name__)


class FieldType(Enum):
    """Supported field types with database mappings"""

    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    FLOAT = "FLOAT"
    DECIMAL = "DECIMAL"
    STRING = "VARCHAR"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    TIME = "TIME"
    UUID = "UUID"
    JSON = "JSON"
    BINARY = "BLOB"
    ENUM = "ENUM"
    ARRAY = "ARRAY"
    VECTOR = "VECTOR"

    @staticmethod
    def Vector(dim: int) -> "VectorFieldType":
        """Parameterized field type for embedding/pgvector columns.

        Carries the vector dimension (issue #1846). Usage::

            embedding: FieldType.Vector(768)

        Cross-dialect DDL (``FieldMeta.get_sql_type``): PostgreSQL emits
        pgvector's ``vector(N)`` (falls back to ``TEXT`` when the pgvector
        extension is not enabled -- store the ``encode_vector`` literal in
        that case); MySQL emits ``JSON``; SQLite emits ``TEXT``.

        The value literal contract (``encode_vector`` / ``decode_vector``)
        is a byte-pinned cross-SDK contract -- see
        ``cross-sdk-inspection.md`` Rule 4b before changing the rendering.
        """
        return VectorFieldType(dim=dim)


class VectorValueError(DataFlowError):
    """Raised when a ``Vector`` field's dimension or literal value is invalid.

    Fired by:

    - ``VectorFieldType.__post_init__`` -- non-positive / non-``int`` dimension.
    - ``encode_vector`` -- a non-finite (NaN/±Inf) component, or a
      component that is not ``int``/``float``.
    - ``decode_vector`` -- a malformed literal, or a non-finite component.

    Fails closed: no code path silently coerces a non-finite value or an
    invalid dimension into a usable vector.
    """


# Shared bound for how much of a (possibly attacker-supplied) value is
# echoed verbatim into a VectorValueError message, so a huge dimension /
# component / literal cannot blow up a downstream log line. Defined once,
# before every raise site that needs it, and reused by both the
# generic-value truncator below and the literal-string truncator near
# decode_vector.
_TRUNCATED_LITERAL_PREVIEW_LENGTH = 200


def _truncate_repr_for_error(value: object) -> str:
    """Bound how much of an (possibly attacker-supplied) value's repr is
    echoed into an error message."""
    text = repr(value)
    if len(text) <= _TRUNCATED_LITERAL_PREVIEW_LENGTH:
        return text
    return text[:_TRUNCATED_LITERAL_PREVIEW_LENGTH] + "...(truncated)"


@dataclass(frozen=True)
class VectorFieldType:
    """A parameterized ``FieldType.VECTOR`` carrying its dimension.

    Returned by ``FieldType.Vector(dim)``; used as the ``type=`` value on a
    ``FieldMeta`` (or a model field declaration) for an embedding column.
    """

    dim: int

    def __post_init__(self) -> None:
        if isinstance(self.dim, bool) or not isinstance(self.dim, int) or self.dim <= 0:
            raise VectorValueError(
                f"Vector dimension must be a positive integer, got "
                f"{_truncate_repr_for_error(self.dim)}"
            )

    @property
    def base_type(self) -> "FieldType":
        """The discriminator ``FieldType`` member (``FieldType.VECTOR``)."""
        return FieldType.VECTOR


def _vector_sql_type(dim: int, dialect: str) -> str:
    """Per-dialect DDL for a ``FieldType.Vector(dim)`` column.

    - PostgreSQL: pgvector's ``vector(N)``. When the pgvector extension is
      not installed/enabled, declare the column ``TEXT`` instead and store
      the canonical ``encode_vector`` literal (documented fallback).
    - MySQL: ``JSON`` (no native vector column type).
    - SQLite (and any other/unrecognized dialect): ``TEXT``.
    """
    if dialect == "postgresql":
        return f"vector({dim})"
    if dialect == "mysql":
        return "JSON"
    return "TEXT"


_VECTOR_LITERAL_RE = re.compile(r"^\[(.*)\]$", re.DOTALL)


def _format_vector_component(value: Union[int, float]) -> str:
    """Render one vector component per the canonical byte contract.

    Integers and integer-valued floats render WITHOUT a trailing ``.0``
    (``2`` not ``2.0``, ``0`` not ``0.0``); other floats render as EXACT,
    shortest-round-trippable, NON-exponential fixed-decimal (``0.5``,
    ``-1.5``, ``3.25``, ``0.00001``) -- ``repr()`` alone would switch to
    scientific notation for magnitudes outside ~[1e-4, 1e16), which breaks
    the byte-canonical cross-SDK contract for realistic embedding
    components (routinely <1e-4). Raises ``VectorValueError`` on a
    non-finite value or a non-numeric type.
    """
    if isinstance(value, bool):
        raise VectorValueError(
            f"vector component must be int or float, got bool: "
            f"{_truncate_repr_for_error(value)}"
        )
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise VectorValueError(
                f"vector component must be finite, got non-finite value: "
                f"{_truncate_repr_for_error(value)}"
            )
        if value.is_integer():
            return str(int(value))
        # repr(value) is the shortest string that round-trips to this
        # exact float -- Decimal(repr(value)) parses it EXACTLY (no
        # precision loss), and format(..., "f") expands any scientific
        # notation into fixed-point without adding or dropping digits.
        # The rstrip is a defensive no-op in practice (the round-trip
        # repr never carries a spurious trailing zero) but guards
        # against relying on that invariant silently breaking.
        fixed = format(Decimal(repr(value)), "f")
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        return fixed
    raise VectorValueError(
        f"vector component must be int or float, got "
        f"{type(value).__name__}: {_truncate_repr_for_error(value)}"
    )


def encode_vector(values: Sequence[Union[int, float]]) -> str:
    """Encode a sequence of numbers into the canonical Vector literal.

    Canonical form: ``[a,b,c]`` -- no spaces. This is the byte-pinned
    cross-SDK contract for issue #1846: do not change the rendering rule
    without a coordinated cross-SDK re-pin (``cross-sdk-inspection.md``
    Rule 4b). Fails closed (raises ``VectorValueError``) on a non-finite
    (NaN/±Inf) component.
    """
    return "[" + ",".join(_format_vector_component(v) for v in values) + "]"


# Defense-in-depth bounds for decode_vector, which may receive
# externally-supplied literals (a stored DB row, an API payload) rather
# than only SDK-internal encode_vector output. Neither the regex nor
# float() is vulnerable to backtracking/quadratic blowup, but an
# unbounded literal still costs proportional CPU/memory to parse -- cap
# it generously (1 MiB is orders of magnitude beyond any realistic
# embedding dimension) and fail closed rather than silently accepting
# arbitrary-sized input.
_MAX_VECTOR_LITERAL_LENGTH = 1_048_576
# _TRUNCATED_LITERAL_PREVIEW_LENGTH is defined once, near VectorValueError
# above (shared with _truncate_repr_for_error).


def _truncate_for_error(literal: str) -> str:
    """Bound how much of an (possibly attacker-supplied) literal is
    echoed into an error message, so a huge literal cannot blow up a
    downstream log line."""
    if len(literal) <= _TRUNCATED_LITERAL_PREVIEW_LENGTH:
        return literal
    return literal[:_TRUNCATED_LITERAL_PREVIEW_LENGTH] + "...(truncated)"


def decode_vector(literal: str) -> List[float]:
    """Decode a canonical Vector literal (``[a,b,c]``) into a list of floats.

    Round-trips byte-identically through ``encode_vector`` --
    ``encode_vector(decode_vector(s)) == s`` for every canonical ``s``.
    Fails closed (raises ``VectorValueError``) on malformed input, an
    oversized literal, or a non-finite (NaN/±Inf) component.
    """
    if not isinstance(literal, str):
        raise VectorValueError(
            f"vector literal must be a string, got {type(literal).__name__}"
        )
    if len(literal) > _MAX_VECTOR_LITERAL_LENGTH:
        raise VectorValueError(
            f"vector literal exceeds {_MAX_VECTOR_LITERAL_LENGTH}-byte limit "
            f"(len={len(literal)})"
        )
    match = _VECTOR_LITERAL_RE.match(literal.strip())
    if match is None:
        raise VectorValueError(
            f"malformed vector literal: {_truncate_for_error(literal)!r}"
        )
    body = match.group(1)
    if body == "":
        return []
    result: List[float] = []
    for token in body.split(","):
        token = token.strip()
        try:
            component = float(token)
        except ValueError as exc:
            raise VectorValueError(
                f"malformed vector component {token!r} in literal "
                f"{_truncate_for_error(literal)!r}"
            ) from exc
        if math.isnan(component) or math.isinf(component):
            raise VectorValueError(
                f"vector literal contains non-finite component {token!r}: "
                f"{_truncate_for_error(literal)!r}"
            )
        result.append(component)
    return result


@dataclass
class FieldMeta:
    """Metadata for a model field"""

    name: str
    type: Union[FieldType, VectorFieldType]
    python_type: Type
    nullable: bool = True
    default: Any = None
    primary_key: bool = False
    unique: bool = False
    index: bool = False
    max_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    choices: Optional[List[Any]] = None
    array_type: Optional[FieldType] = None
    validators: List[Any] = field(default_factory=list)

    def get_sql_type(
        self, dialect: str = "postgresql", use_native_arrays: bool = False
    ) -> str:
        """Get SQL type for the field based on database dialect.

        Args:
            dialect: Database dialect (postgresql, mysql, sqlite)
            use_native_arrays: Use native PostgreSQL arrays for List types

        Returns:
            SQL type string

        Raises:
            ValueError: If use_native_arrays is True on non-PostgreSQL database
        """
        # Validate native array support
        if use_native_arrays and dialect != "postgresql":
            raise ValueError(
                f"Native arrays only supported on PostgreSQL. "
                f"Current dialect: {dialect}. "
                f"To use List fields on {dialect}, remove 'use_native_arrays' flag."
            )

        # Handle PostgreSQL native arrays
        if (
            self.type == FieldType.ARRAY
            and use_native_arrays
            and dialect == "postgresql"
        ):
            # Map array element type to PostgreSQL array syntax
            array_type_map = {
                FieldType.STRING: "TEXT[]",
                FieldType.INTEGER: "INTEGER[]",
                FieldType.BIGINT: "BIGINT[]",
                FieldType.FLOAT: "REAL[]",
                FieldType.DECIMAL: "DECIMAL[]",
                FieldType.BOOLEAN: "BOOLEAN[]",
                FieldType.DATE: "DATE[]",
                FieldType.DATETIME: "TIMESTAMP[]",
                FieldType.TIME: "TIME[]",
                FieldType.UUID: "UUID[]",
            }

            if self.array_type and self.array_type in array_type_map:
                return array_type_map[self.array_type]
            else:
                # Fallback to JSONB for unsupported element types
                return "JSONB"

        # Handle the parameterized Vector field type (FieldType.Vector(dim)).
        # Dispatched BEFORE the type_mappings dict below because a
        # VectorFieldType instance is never a dict key there (only bare
        # FieldType enum members are) -- issue #1846.
        if isinstance(self.type, VectorFieldType):
            return _vector_sql_type(self.type.dim, dialect)

        # Standard type mappings (backward compatible)
        type_mappings = {
            "postgresql": {
                FieldType.INTEGER: "INTEGER",
                FieldType.BIGINT: "BIGINT",
                FieldType.FLOAT: "REAL",
                FieldType.DECIMAL: "DECIMAL",
                FieldType.STRING: (
                    f"VARCHAR({self.max_length})" if self.max_length else "VARCHAR(255)"
                ),
                FieldType.TEXT: "TEXT",
                FieldType.BOOLEAN: "BOOLEAN",
                FieldType.DATE: "DATE",
                FieldType.DATETIME: "TIMESTAMP",
                FieldType.TIME: "TIME",
                FieldType.UUID: "UUID",
                FieldType.JSON: "JSONB",
                FieldType.BINARY: "BYTEA",
                FieldType.ENUM: "VARCHAR(50)",
                FieldType.ARRAY: "JSONB",
                # Bare FieldType.VECTOR (no dimension) -- normal usage goes
                # through FieldType.Vector(dim), which is dispatched above.
                FieldType.VECTOR: "TEXT",
            },
            "mysql": {
                FieldType.INTEGER: "INTEGER",
                FieldType.BIGINT: "BIGINT",
                FieldType.FLOAT: "FLOAT",
                FieldType.DECIMAL: "DECIMAL",
                FieldType.STRING: (
                    f"VARCHAR({self.max_length})" if self.max_length else "VARCHAR(255)"
                ),
                FieldType.TEXT: "TEXT",
                FieldType.BOOLEAN: "BOOLEAN",
                FieldType.DATE: "DATE",
                FieldType.DATETIME: "DATETIME",
                FieldType.TIME: "TIME",
                FieldType.UUID: "CHAR(36)",
                FieldType.JSON: "JSON",
                FieldType.BINARY: "BLOB",
                FieldType.ENUM: "VARCHAR(50)",
                FieldType.ARRAY: "JSON",
                FieldType.VECTOR: "JSON",
            },
            "sqlite": {
                FieldType.INTEGER: "INTEGER",
                FieldType.BIGINT: "INTEGER",
                FieldType.FLOAT: "REAL",
                FieldType.DECIMAL: "REAL",
                FieldType.STRING: "TEXT",
                FieldType.TEXT: "TEXT",
                FieldType.BOOLEAN: "INTEGER",
                FieldType.DATE: "TEXT",
                FieldType.DATETIME: "TEXT",
                FieldType.TIME: "TEXT",
                FieldType.UUID: "TEXT",
                FieldType.JSON: "TEXT",
                FieldType.BINARY: "BLOB",
                FieldType.ENUM: "TEXT",
                FieldType.ARRAY: "TEXT",
                FieldType.VECTOR: "TEXT",
            },
        }

        mapping = type_mappings.get(dialect, type_mappings["postgresql"])
        return mapping.get(self.type, "TEXT")


@dataclass
class IndexMeta:
    """Metadata for database indexes"""

    name: str
    fields: List[str]
    unique: bool = False
    type: str = "btree"
    where: Optional[str] = None
    table_name: Optional[str] = None  # For compatibility

    @property
    def columns(self) -> List[str]:
        """Alias for fields to maintain compatibility."""
        return self.fields

    @columns.setter
    def columns(self, value: List[str]) -> None:
        """Alias setter for fields."""
        self.fields = value


@dataclass
class ModelMeta:
    """Complete metadata for a model"""

    name: str
    table_name: str
    fields: Union[Dict[str, FieldMeta], List[FieldMeta]] = field(default_factory=dict)
    indexes: List[IndexMeta] = field(default_factory=list)
    primary_key: Optional[str] = None
    unique_constraints: List[List[str]] = field(default_factory=list)
    check_constraints: List[str] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Convert list of fields to dict if needed."""
        if isinstance(self.fields, list):
            # Convert list to dict using field name
            fields_dict = {}
            for field_meta in self.fields:
                fields_dict[field_meta.name] = field_meta
                # Check if this is the primary key
                if field_meta.primary_key and not self.primary_key:
                    self.primary_key = field_meta.name
            self.fields = fields_dict

    def get_primary_key(self) -> Optional[str]:
        """Get the primary key field name."""
        return self.primary_key

    def get_unique_fields(self) -> List[str]:
        """Get list of unique field names."""
        # __post_init__ always normalizes self.fields to a dict; the cast
        # is a mypy-only narrowing (no runtime effect) of the declared
        # Union[Dict[str, FieldMeta], List[FieldMeta]] field type.
        fields = cast(Dict[str, FieldMeta], self.fields)
        unique_fields = []
        for name, field_meta in fields.items():
            if field_meta.unique:
                unique_fields.append(name)
        return unique_fields

    def get_indexed_fields(self) -> List[str]:
        """Get list of indexed field names."""
        fields = cast(Dict[str, FieldMeta], self.fields)
        indexed_fields = []
        for name, field_meta in fields.items():
            if field_meta.index:
                indexed_fields.append(name)
        return indexed_fields


class SchemaParser:
    """Parse Python classes into database schema metadata"""

    # Type mappings from Python to FieldType
    TYPE_MAPPING = {
        int: FieldType.INTEGER,
        float: FieldType.FLOAT,
        Decimal: FieldType.DECIMAL,
        str: FieldType.STRING,
        bool: FieldType.BOOLEAN,
        date: FieldType.DATE,
        datetime: FieldType.DATETIME,
        time: FieldType.TIME,
        UUID: FieldType.UUID,
        bytes: FieldType.BINARY,
        dict: FieldType.JSON,
        list: FieldType.JSON,
    }

    @classmethod
    def parse_model(cls, model_class: Type) -> ModelMeta:
        """Parse a model class into metadata"""
        # Get class name and table name
        class_name = model_class.__name__
        table_name = getattr(model_class, "__tablename__", class_name.lower() + "s")

        # Parse type hints
        type_hints = get_type_hints(model_class)
        fields = {}

        for field_name, field_type in type_hints.items():
            # Skip private fields
            if field_name.startswith("_"):
                continue

            field_meta = cls._parse_field(field_name, field_type, model_class)
            fields[field_name] = field_meta

        # Check for primary key
        primary_key = None
        for name, field_obj in fields.items():
            if field_obj.primary_key:
                primary_key = name
                break

        # Parse indexes
        indexes = cls._parse_indexes(model_class)

        # Parse options
        options = cls._parse_options(model_class)

        return ModelMeta(
            name=class_name,
            table_name=table_name,
            fields=fields,
            indexes=indexes,
            primary_key=primary_key,
            options=options,
        )

    @classmethod
    def _parse_field(
        cls, field_name: str, field_type: Type, model_class: Type
    ) -> FieldMeta:
        """Parse a single field"""
        # Handle Optional types
        origin = get_origin(field_type)
        args = get_args(field_type)
        nullable = False
        actual_type = field_type

        # Two-spelling union detection (typing.Union AND PEP 604 ``T | None``)
        # routes through the shared primitive (issue #772 / #1228); this caller
        # keeps its own policy -- Optional[X] sets nullable + unwraps, other
        # unions become JSON (dict).
        if union_non_none_args(field_type) is not None:
            # Check if it's Optional (Union[X, None])
            if type(None) in args:
                nullable = True
                actual_type = next(arg for arg in args if arg is not type(None))
                # Re-check origin and args for the extracted type
                origin = get_origin(actual_type)
                args = get_args(actual_type)
            else:
                # For now, treat other unions as JSON
                actual_type = dict

        # Handle List types
        array_type = None
        if origin is list or origin is List:
            array_type = cls._get_field_type(args[0] if args else str)
            field_type_enum = FieldType.ARRAY
        else:
            field_type_enum = cls._get_field_type(actual_type)

        # Get default value
        default = getattr(model_class, field_name, None)
        if callable(default):
            default = None

        # Check for special attributes
        field_attrs = getattr(model_class, f"__{field_name}_meta__", {})

        return FieldMeta(
            name=field_name,
            type=field_type_enum,
            python_type=actual_type,
            nullable=nullable or field_attrs.get("nullable", True),
            default=default,
            primary_key=field_attrs.get("primary_key", field_name == "id"),
            unique=field_attrs.get("unique", False),
            index=field_attrs.get("index", False),
            max_length=field_attrs.get("max_length"),
            array_type=array_type,
        )

    @classmethod
    def _get_field_type(cls, python_type: Type) -> FieldType:
        """Get FieldType from Python type"""
        # Direct mapping
        if python_type in cls.TYPE_MAPPING:
            return cls.TYPE_MAPPING[python_type]

        # Check for subclasses
        for base_type, field_type in cls.TYPE_MAPPING.items():
            try:
                if issubclass(python_type, base_type):
                    return field_type
            except TypeError:
                pass

        # Check for Enum types
        try:
            if issubclass(python_type, Enum):
                return FieldType.ENUM
        except TypeError:
            pass

        # Default to JSON for complex types
        return FieldType.JSON

    @classmethod
    def _parse_indexes(cls, model_class: Type) -> List[IndexMeta]:
        """Parse index definitions from model class"""
        indexes: List[IndexMeta] = []

        # Check for __indexes__ attribute
        if hasattr(model_class, "__indexes__"):
            for idx_def in model_class.__indexes__:
                if isinstance(idx_def, dict):
                    indexes.append(
                        IndexMeta(
                            name=idx_def.get("name", f"idx_{len(indexes)}"),
                            fields=idx_def.get("fields", []),
                            unique=idx_def.get("unique", False),
                            type=idx_def.get("type", "btree"),
                        )
                    )

        return indexes

    @classmethod
    def _parse_options(cls, model_class: Type) -> Dict[str, Any]:
        """Parse model options"""
        options = {}

        # Check for __dataflow__ attribute
        if hasattr(model_class, "__dataflow__"):
            options.update(model_class.__dataflow__)

        # Also include other dunder attributes that might be options
        for attr_name in ["__tablename__", "__schema__", "__table_args__"]:
            if hasattr(model_class, attr_name):
                options[attr_name] = getattr(model_class, attr_name)

        return options
