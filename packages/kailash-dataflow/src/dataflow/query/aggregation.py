from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
High-level aggregation functions for DataFlow.

These functions accept either:
- A raw connection + table name string (direct SQL)
- A DataFlow instance + model class (resolves table name from __tablename__)

SQL generation is delegated to sql_builder. Actual query execution uses
the connection's execute method when available. If the connection does not
support execution (e.g., in test/planning mode), the AggregationResult is
returned with sql and params populated but data empty.
"""

import logging
from typing import Any, Dict, List, Optional

from dataflow.query.models import AggregateOp, AggregateSpec, AggregationResult
from dataflow.query.sql_builder import build_aggregate, build_count_by, build_sum_by

logger = logging.getLogger(__name__)

__all__ = ["count_by", "sum_by", "aggregate"]


def _resolve_table_name(model_or_table: Any) -> str:
    """Resolve a table name from a model class or string.

    Args:
        model_or_table: Either a string table name or a class with __tablename__.

    Returns:
        The resolved table name string.

    Raises:
        TypeError: If model_or_table is neither a string nor has __tablename__.
    """
    if isinstance(model_or_table, str):
        return model_or_table

    if hasattr(model_or_table, "__tablename__"):
        tablename = model_or_table.__tablename__
        if isinstance(tablename, str):
            return tablename
        raise TypeError(
            f"__tablename__ must be a string, got {type(tablename).__name__}: "
            f"{tablename!r} on {model_or_table!r}"
        )

    raise TypeError(
        f"model_or_table must be a string table name or a class with __tablename__, "
        f"got {type(model_or_table).__name__}: {model_or_table!r}"
    )


async def _execute_query(
    connection: Any,
    sql: str,
    params: List[Any],
) -> AggregationResult:
    """Execute an aggregation query and return the result.

    Attempts to call the connection's execute/fetch method. If the connection
    does not support query execution, returns the result with query info only
    (data will be empty).

    Args:
        connection: A database connection object. Expected to have a fetch()
                    or execute() method that returns row results.
        sql: The SQL query string.
        params: The parameter values for the query.

    Returns:
        AggregationResult with data populated from query results.
    """
    result = AggregationResult(query=sql, params=list(params))

    # Try asyncpg-style fetch (returns list of Record)
    if hasattr(connection, "fetch"):
        try:
            rows = await connection.fetch(sql, *params)
            result.data = [dict(row) for row in rows]
            result.row_count = len(result.data)
            logger.debug(
                "Aggregation query returned %d rows: %s", result.row_count, sql
            )
            return result
        except Exception as exc:
            logger.error(
                "Failed to execute aggregation query: %s (error: %s)", sql, exc
            )
            raise

    # Try aiosqlite-style execute + fetchall
    if hasattr(connection, "execute"):
        try:
            cursor = await connection.execute(sql, params)
            if hasattr(cursor, "fetchall"):
                rows = await cursor.fetchall()
                # aiosqlite returns tuples; convert using cursor.description
                if hasattr(cursor, "description") and cursor.description:
                    col_names = [desc[0] for desc in cursor.description]
                    result.data = [dict(zip(col_names, row)) for row in rows]
                else:
                    result.data = [{"value": row[0]} for row in rows]
                result.row_count = len(result.data)
                logger.debug(
                    "Aggregation query returned %d rows: %s",
                    result.row_count,
                    sql,
                )
                return result
        except Exception as exc:
            logger.error(
                "Failed to execute aggregation query: %s (error: %s)", sql, exc
            )
            raise

    # Connection does not support known execution methods — return query-only result
    logger.warning(
        "Connection %r does not support fetch() or execute(). "
        "Returning query-only AggregationResult (no data).",
        type(connection).__name__,
    )
    return result


async def count_by(
    connection: Any,
    model_or_table: Any,
    group_by: str,
    filter: Optional[Dict[str, Any]] = None,
) -> AggregationResult:
    """Count rows grouped by a column.

    Args:
        connection: A database connection or DataFlow instance.
        model_or_table: A string table name or a model class with __tablename__.
        group_by: Column name to group by.
        filter: Optional filter conditions as {column: value} dict.
                Supports operator suffixes: __gt, __lt, __gte, __lte, __ne.

    Returns:
        AggregationResult with count data.

    Raises:
        ValueError: If identifiers are invalid.
        TypeError: If model_or_table cannot be resolved.

    Example:
        >>> result = await count_by(conn, "users", "status")
        >>> # SQL: SELECT status, COUNT(*) AS count FROM users GROUP BY status
        >>> for row in result.data:
        ...     print(f"{row['status']}: {row['count']}")
    """
    table = _resolve_table_name(model_or_table)
    sql, params = build_count_by(table, group_by, filter)
    return await _execute_query(connection, sql, params)


async def sum_by(
    connection: Any,
    model_or_table: Any,
    sum_field: str,
    group_by: str,
    filter: Optional[Dict[str, Any]] = None,
) -> AggregationResult:
    """Sum a numeric column grouped by another column.

    Args:
        connection: A database connection or DataFlow instance.
        model_or_table: A string table name or a model class with __tablename__.
        sum_field: Column name to sum.
        group_by: Column name to group by.
        filter: Optional filter conditions as {column: value} dict.

    Returns:
        AggregationResult with sum data.

    Raises:
        ValueError: If identifiers are invalid.
        TypeError: If model_or_table cannot be resolved.

    Example:
        >>> result = await sum_by(conn, "orders", "amount", "category")
        >>> # SQL: SELECT category, SUM(amount) AS sum_amount FROM orders GROUP BY category
    """
    table = _resolve_table_name(model_or_table)
    sql, params = build_sum_by(table, sum_field, group_by, filter)
    return await _execute_query(connection, sql, params)


async def aggregate(
    connection: Any,
    model_or_table: Any,
    specs: List[AggregateSpec],
    group_by: Optional[str] = None,
    filter: Optional[Dict[str, Any]] = None,
) -> AggregationResult:
    """Execute a multi-aggregate query.

    Args:
        connection: A database connection or DataFlow instance.
        model_or_table: A string table name or a model class with __tablename__.
        specs: List of AggregateSpec defining the aggregate expressions.
        group_by: Optional column name to group by.
        filter: Optional filter conditions as {column: value} dict.

    Returns:
        AggregationResult with aggregate data.

    Raises:
        ValueError: If identifiers are invalid or specs is empty.
        TypeError: If model_or_table cannot be resolved or specs is invalid.

    Example:
        >>> specs = [
        ...     AggregateSpec(op=AggregateOp.COUNT, field="*"),
        ...     AggregateSpec(op=AggregateOp.AVG, field="price", alias="avg_price"),
        ... ]
        >>> result = await aggregate(conn, "products", specs, group_by="category")
    """
    table = _resolve_table_name(model_or_table)
    sql, params = build_aggregate(table, specs, group_by, filter)
    return await _execute_query(connection, sql, params)
