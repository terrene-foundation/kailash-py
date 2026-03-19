from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Aggregation query models.

Provides validated data structures for SQL aggregation operations.
All identifiers are validated against a strict regex to prevent
SQL injection. AggregateOp is a fixed enum — never accept raw
user strings as SQL function names.
"""

import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["AggregateOp", "AggregateSpec", "AggregationResult", "validate_identifier"]

# Strict SQL identifier pattern: letters/underscore start, then letters/digits/underscore.
# This prevents ALL injection vectors including path traversal, semicolons, quotes, etc.
_VALID_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_identifier(name: str) -> None:
    """Validate a SQL identifier (table or column name).

    Args:
        name: The identifier to validate.

    Raises:
        ValueError: If the identifier contains invalid characters.
        TypeError: If name is not a string.
    """
    if not isinstance(name, str):
        raise TypeError(
            f"SQL identifier must be a string, got {type(name).__name__}: {name!r}"
        )
    if not name:
        raise ValueError("SQL identifier must not be empty")
    if not _VALID_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid SQL identifier: {name!r}. "
            f"Must match [a-zA-Z_][a-zA-Z0-9_]* (no spaces, dashes, quotes, "
            f"semicolons, or special characters allowed)"
        )


class AggregateOp(str, enum.Enum):
    """Fixed set of SQL aggregate operations.

    NEVER accept raw user input as an aggregate function name.
    Always use this enum to restrict to known-safe operations.
    """

    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


@dataclass
class AggregateSpec:
    """Specification for a single aggregate expression in a query.

    Attributes:
        op: The aggregate operation (COUNT, SUM, AVG, MIN, MAX).
        field: The column to aggregate. Use "*" for COUNT(*).
        alias: Optional alias for the result column. Auto-generated if not provided.
    """

    op: AggregateOp
    field: str
    alias: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.op, AggregateOp):
            raise TypeError(
                f"op must be an AggregateOp enum value, got {type(self.op).__name__}: {self.op!r}"
            )
        if not isinstance(self.field, str):
            raise TypeError(
                f"field must be a string, got {type(self.field).__name__}: {self.field!r}"
            )
        # "*" is only valid for COUNT
        if self.field == "*":
            if self.op != AggregateOp.COUNT:
                raise ValueError(
                    f"Wildcard '*' is only valid with COUNT, not {self.op.value.upper()}"
                )
        else:
            validate_identifier(self.field)

        if self.alias is not None:
            validate_identifier(self.alias)

    def effective_alias(self) -> str:
        """Return the alias to use in SQL output.

        If an explicit alias was provided, returns that.
        Otherwise generates a default: '{op}_{field}' or '{op}_all' for COUNT(*).
        """
        if self.alias:
            return self.alias
        if self.field == "*":
            return f"{self.op.value}_all"
        return f"{self.op.value}_{self.field}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "op": self.op.value,
            "field": self.field,
            "alias": self.alias,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AggregateSpec:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with 'op', 'field', and optional 'alias' keys.

        Raises:
            KeyError: If required keys are missing.
            ValueError: If op is not a valid AggregateOp value.
        """
        if "op" not in data:
            raise KeyError("Missing required key 'op' in AggregateSpec data")
        if "field" not in data:
            raise KeyError("Missing required key 'field' in AggregateSpec data")
        return cls(
            op=AggregateOp(data["op"]),
            field=data["field"],
            alias=data.get("alias"),
        )


@dataclass
class AggregationResult:
    """Result of an aggregation query.

    Attributes:
        data: List of row dictionaries from the query result.
        query: The SQL query that was executed (for debugging/logging).
        params: The parameter values used in the query.
        row_count: Number of result rows.
    """

    data: List[Dict[str, Any]] = field(default_factory=list)
    query: str = ""
    params: List[Any] = field(default_factory=list)
    row_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "data": self.data,
            "query": self.query,
            "row_count": self.row_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AggregationResult:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with optional 'data', 'query', and 'row_count' keys.
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"AggregationResult.from_dict expects a dict, got {type(data).__name__}"
            )
        return cls(
            data=data.get("data", []),
            query=data.get("query", ""),
            row_count=data.get("row_count", 0),
        )
