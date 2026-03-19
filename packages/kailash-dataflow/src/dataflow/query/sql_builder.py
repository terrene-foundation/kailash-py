from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
SQL query builder for aggregation operations.

Generates parameterized SQL strings with strict identifier validation.
All column/table names are validated against _VALID_IDENTIFIER_RE before
interpolation. Values are ALWAYS passed as ? parameters — never interpolated.

The ? placeholder is the canonical Kailash format. ConnectionManager
translates to dialect-specific format ($1, %s) automatically.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from dataflow.query.models import AggregateOp, AggregateSpec, validate_identifier

logger = logging.getLogger(__name__)

__all__ = ["build_count_by", "build_sum_by", "build_aggregate"]

# Supported filter operator suffixes and their SQL equivalents
_FILTER_OPERATORS: Dict[str, str] = {
    "__gt": ">",
    "__gte": ">=",
    "__lt": "<",
    "__lte": "<=",
    "__ne": "!=",
}


def _build_where_clause(
    filter_dict: Dict[str, Any],
) -> Tuple[str, List[Any]]:
    """Build a WHERE clause from a filter dictionary.

    Each key in the filter dict is a column name, optionally suffixed with
    an operator (__gt, __lt, __gte, __lte, __ne). Values become parameterized
    ? placeholders.

    Args:
        filter_dict: Mapping of column names (with optional operator suffix) to values.

    Returns:
        Tuple of (where_clause_without_WHERE_keyword, param_list).
        If filter_dict is empty, returns ("", []).

    Raises:
        ValueError: If any column name in the filter is invalid.
        TypeError: If filter_dict is not a dict.

    Examples:
        >>> _build_where_clause({"status": "active"})
        ("status = ?", ["active"])

        >>> _build_where_clause({"age__gt": 18, "status": "active"})
        ("age > ? AND status = ?", [18, "active"])
    """
    if not isinstance(filter_dict, dict):
        raise TypeError(
            f"filter must be a dict, got {type(filter_dict).__name__}: {filter_dict!r}"
        )

    if not filter_dict:
        return "", []

    conditions: List[str] = []
    params: List[Any] = []

    for key, value in filter_dict.items():
        if not isinstance(key, str):
            raise TypeError(
                f"Filter key must be a string, got {type(key).__name__}: {key!r}"
            )

        # Check for operator suffix
        column = key
        operator = "="

        for suffix, sql_op in _FILTER_OPERATORS.items():
            if key.endswith(suffix):
                column = key[: -len(suffix)]
                operator = sql_op
                break

        # Validate the column name (after stripping operator suffix)
        validate_identifier(column)

        # Handle NULL values: generate IS NULL / IS NOT NULL instead of
        # parameterized comparison (SQL `column = NULL` is always false).
        if value is None:
            if operator == "=":
                conditions.append(f"{column} IS NULL")
            elif operator in ("!=", "<>"):
                conditions.append(f"{column} IS NOT NULL")
            else:
                raise ValueError(
                    f"Cannot use operator '{operator}' with NULL value "
                    f"for column '{column}'"
                )
        else:
            conditions.append(f"{column} {operator} ?")
            params.append(value)

    return " AND ".join(conditions), params


def build_count_by(
    table: str,
    group_by: str,
    filter: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Any]]:
    """Build a COUNT(*) GROUP BY query.

    Args:
        table: Table name (validated as SQL identifier).
        group_by: Column to group by (validated as SQL identifier).
        filter: Optional filter conditions as {column: value} dict.

    Returns:
        Tuple of (sql_string, param_list).

    Raises:
        ValueError: If table or group_by contain invalid characters.

    Example:
        >>> build_count_by("orders", "status")
        ("SELECT status, COUNT(*) AS count FROM orders GROUP BY status", [])

        >>> build_count_by("orders", "status", {"region": "US"})
        ("SELECT status, COUNT(*) AS count FROM orders WHERE region = ? GROUP BY status", ["US"])
    """
    validate_identifier(table)
    validate_identifier(group_by)

    parts = [f"SELECT {group_by}, COUNT(*) AS count FROM {table}"]
    params: List[Any] = []

    if filter:
        where_clause, where_params = _build_where_clause(filter)
        if where_clause:
            parts.append(f"WHERE {where_clause}")
            params.extend(where_params)

    parts.append(f"GROUP BY {group_by}")

    sql = " ".join(parts)
    logger.debug("Built count_by query: %s with params: %s", sql, params)
    return sql, params


def build_sum_by(
    table: str,
    sum_field: str,
    group_by: str,
    filter: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Any]]:
    """Build a SUM() GROUP BY query.

    Args:
        table: Table name (validated as SQL identifier).
        sum_field: Column to sum (validated as SQL identifier).
        group_by: Column to group by (validated as SQL identifier).
        filter: Optional filter conditions as {column: value} dict.

    Returns:
        Tuple of (sql_string, param_list).

    Raises:
        ValueError: If any identifier contains invalid characters.

    Example:
        >>> build_sum_by("orders", "amount", "category")
        ("SELECT category, SUM(amount) AS sum_amount FROM orders GROUP BY category", [])
    """
    validate_identifier(table)
    validate_identifier(sum_field)
    validate_identifier(group_by)

    alias = f"sum_{sum_field}"
    parts = [f"SELECT {group_by}, SUM({sum_field}) AS {alias} FROM {table}"]
    params: List[Any] = []

    if filter:
        where_clause, where_params = _build_where_clause(filter)
        if where_clause:
            parts.append(f"WHERE {where_clause}")
            params.extend(where_params)

    parts.append(f"GROUP BY {group_by}")

    sql = " ".join(parts)
    logger.debug("Built sum_by query: %s with params: %s", sql, params)
    return sql, params


def build_aggregate(
    table: str,
    specs: List[AggregateSpec],
    group_by: Optional[str] = None,
    filter: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Any]]:
    """Build a multi-aggregate SQL query.

    Generates a SELECT with one or more aggregate expressions, optional
    GROUP BY, and optional WHERE clause. All identifiers are validated.

    Args:
        table: Table name (validated as SQL identifier).
        specs: List of AggregateSpec defining the aggregate expressions.
        group_by: Optional column to group by (validated as SQL identifier).
        filter: Optional filter conditions as {column: value} dict.

    Returns:
        Tuple of (sql_string, param_list).

    Raises:
        ValueError: If any identifier is invalid or specs is empty.
        TypeError: If specs is not a list or contains non-AggregateSpec items.

    Example:
        >>> specs = [
        ...     AggregateSpec(op=AggregateOp.COUNT, field="*"),
        ...     AggregateSpec(op=AggregateOp.SUM, field="amount"),
        ... ]
        >>> build_aggregate("orders", specs, group_by="category")
        (
            "SELECT category, COUNT(*) AS count_all, SUM(amount) AS sum_amount FROM orders GROUP BY category",
            []
        )
    """
    validate_identifier(table)

    if not isinstance(specs, list):
        raise TypeError(f"specs must be a list, got {type(specs).__name__}: {specs!r}")
    if not specs:
        raise ValueError("specs must contain at least one AggregateSpec")

    for i, spec in enumerate(specs):
        if not isinstance(spec, AggregateSpec):
            raise TypeError(
                f"specs[{i}] must be an AggregateSpec, got {type(spec).__name__}: {spec!r}"
            )

    if group_by is not None:
        validate_identifier(group_by)

    # Build SELECT columns
    select_columns: List[str] = []

    if group_by is not None:
        select_columns.append(group_by)

    for spec in specs:
        op_name = spec.op.value.upper()
        field_expr = spec.field  # Already validated in AggregateSpec.__post_init__
        alias = spec.effective_alias()
        select_columns.append(f"{op_name}({field_expr}) AS {alias}")

    parts = [f"SELECT {', '.join(select_columns)} FROM {table}"]
    params: List[Any] = []

    if filter:
        where_clause, where_params = _build_where_clause(filter)
        if where_clause:
            parts.append(f"WHERE {where_clause}")
            params.extend(where_params)

    if group_by is not None:
        parts.append(f"GROUP BY {group_by}")

    sql = " ".join(parts)
    logger.debug("Built aggregate query: %s with params: %s", sql, params)
    return sql, params
