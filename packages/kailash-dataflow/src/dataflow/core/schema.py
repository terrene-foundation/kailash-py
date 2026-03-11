"""
Schema Parser and Validation System

Provides type-safe schema parsing with automatic validation and migration generation.
This module was migrated from the old core/schema.py to maintain test compatibility.
"""

import inspect
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Type,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

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


@dataclass
class FieldMeta:
    """Metadata for a model field"""

    name: str
    type: FieldType
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
        unique_fields = []
        for name, field_meta in self.fields.items():
            if field_meta.unique:
                unique_fields.append(name)
        return unique_fields

    def get_indexed_fields(self) -> List[str]:
        """Get list of indexed field names."""
        indexed_fields = []
        for name, field_meta in self.fields.items():
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

        if origin is Union:
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
        indexes = []

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
