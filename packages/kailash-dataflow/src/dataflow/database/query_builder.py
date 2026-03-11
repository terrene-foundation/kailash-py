"""
DataFlow Query Builder

MongoDB-style query builder that generates SQL for multiple databases.
Provides an intuitive interface for building complex queries with cross-database support.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class DatabaseType(Enum):
    """Supported database types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class QueryBuilder:
    """
    MongoDB-style query builder for DataFlow.

    Supports MongoDB operators like $eq, $gt, $in, etc. and generates
    optimized SQL for PostgreSQL, MySQL, and SQLite.

    Example:
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("age", "$gt", 18)
        builder.where("status", "$in", ["active", "premium"])
        sql, params = builder.build_select(["name", "email"])
    """

    # MongoDB operator mappings to SQL
    OPERATORS = {
        "$eq": "=",
        "$ne": "!=",
        "$gt": ">",
        "$gte": ">=",
        "$lt": "<",
        "$lte": "<=",
        "$in": "IN",
        "$nin": "NOT IN",
        "$like": "LIKE",
        "$regex": "~",  # PostgreSQL regex operator
        "$exists": "IS NOT NULL",
        "$null": "IS NULL",
    }

    def __init__(
        self, table_name: str, database_type: DatabaseType = DatabaseType.POSTGRESQL
    ):
        """
        Initialize query builder.

        Args:
            table_name: Name of the database table
            database_type: Type of database (PostgreSQL, MySQL, SQLite)
        """
        if not isinstance(database_type, DatabaseType):
            raise TypeError(
                f"database_type must be a DatabaseType enum, got {type(database_type)}"
            )

        self.table_name = table_name
        self.database_type = database_type
        self.conditions = []
        self.parameters = []
        self.select_fields = []
        self.order_by_fields = []
        self.limit_value = None
        self.offset_value = None
        self.joins = []
        self.group_by_fields = []
        self.having_conditions = []
        self._parameter_index = 0

    def where(self, field: str, operator: str, value: Any = None) -> "QueryBuilder":
        """
        Add a WHERE condition using MongoDB-style operators.

        Args:
            field: Field name (supports dot notation for nested fields)
            operator: MongoDB operator ($eq, $gt, $in, etc.)
            value: Value to compare (optional for $exists, $null)

        Returns:
            Self for method chaining

        Example:
            builder.where("age", "$gt", 18)
            builder.where("user.email", "$like", "%@example.com")
        """
        if operator not in self.OPERATORS:
            raise ValueError(f"Unsupported operator: {operator}")

        # Handle special operators
        if operator in ["$exists", "$null"]:
            self._add_existence_condition(field, operator)
        elif operator in ["$in", "$nin"]:
            self._add_list_condition(field, operator, value)
        elif operator == "$regex":
            self._add_regex_condition(field, value)
        else:
            self._add_simple_condition(field, operator, value)

        return self

    def _add_simple_condition(self, field: str, operator: str, value: Any):
        """Add a simple comparison condition.

        Special handling for None values:
        - $eq with None generates "field IS NULL" (not "field = NULL" which never matches)
        - $ne with None generates "field IS NOT NULL"
        """
        # Handle None values specially - SQL NULL comparisons require IS NULL syntax
        if value is None:
            if operator == "$eq":
                # None equality should use IS NULL (not = NULL which never matches)
                condition = f"{self._quote_identifier(field)} IS NULL"
                self.conditions.append(condition)
                return
            elif operator == "$ne":
                # None inequality should use IS NOT NULL
                condition = f"{self._quote_identifier(field)} IS NOT NULL"
                self.conditions.append(condition)
                return

        sql_operator = self.OPERATORS[operator]
        param_placeholder = self._get_parameter_placeholder()

        condition = (
            f"{self._quote_identifier(field)} {sql_operator} {param_placeholder}"
        )
        self.conditions.append(condition)
        self.parameters.append(value)

    def _add_list_condition(self, field: str, operator: str, values: List[Any]):
        """Add an IN or NOT IN condition."""
        if not isinstance(values, (list, tuple)):
            raise ValueError(f"{operator} requires a list of values")

        sql_operator = self.OPERATORS[operator]
        placeholders = []

        for value in values:
            placeholder = self._get_parameter_placeholder()
            placeholders.append(placeholder)
            self.parameters.append(value)

        condition = f"{self._quote_identifier(field)} {sql_operator} ({', '.join(placeholders)})"
        self.conditions.append(condition)

    def _add_existence_condition(self, field: str, operator: str):
        """Add an existence check condition."""
        sql_operator = self.OPERATORS[operator]
        condition = f"{self._quote_identifier(field)} {sql_operator}"
        self.conditions.append(condition)

    def _add_regex_condition(self, field: str, pattern: str):
        """Add a regex condition (database-specific)."""
        if self.database_type == DatabaseType.POSTGRESQL:
            param_placeholder = self._get_parameter_placeholder()
            condition = f"{self._quote_identifier(field)} ~ {param_placeholder}"
            self.parameters.append(pattern)
        elif self.database_type == DatabaseType.MYSQL:
            param_placeholder = self._get_parameter_placeholder()
            condition = f"{self._quote_identifier(field)} REGEXP {param_placeholder}"
            self.parameters.append(pattern)
        else:  # SQLite
            # SQLite doesn't have built-in regex, use LIKE as fallback
            param_placeholder = self._get_parameter_placeholder()
            # Convert simple regex to LIKE pattern
            like_pattern = pattern.replace(".*", "%").replace(".", "_")
            condition = f"{self._quote_identifier(field)} LIKE {param_placeholder}"
            self.parameters.append(like_pattern)

        self.conditions.append(condition)

    def select(self, fields: Union[str, List[str]]) -> "QueryBuilder":
        """
        Specify fields to select.

        Args:
            fields: Field name(s) to select, "*" for all fields

        Returns:
            Self for method chaining
        """
        if isinstance(fields, str):
            fields = [fields]
        self.select_fields.extend(fields)
        return self

    def order_by(self, field: str, direction: str = "ASC") -> "QueryBuilder":
        """
        Add ORDER BY clause.

        Args:
            field: Field to order by
            direction: "ASC" or "DESC"

        Returns:
            Self for method chaining
        """
        if direction.upper() not in ["ASC", "DESC"]:
            raise ValueError("Direction must be ASC or DESC")

        self.order_by_fields.append(
            f"{self._quote_identifier(field)} {direction.upper()}"
        )
        return self

    def limit(self, limit: int) -> "QueryBuilder":
        """Set result limit."""
        self.limit_value = limit
        return self

    def offset(self, offset: int) -> "QueryBuilder":
        """Set result offset."""
        self.offset_value = offset
        return self

    def join(
        self, table: str, on_condition: str, join_type: str = "INNER"
    ) -> "QueryBuilder":
        """
        Add a JOIN clause.

        Args:
            table: Table to join
            on_condition: JOIN condition
            join_type: Type of join (INNER, LEFT, RIGHT, FULL)

        Returns:
            Self for method chaining
        """
        valid_joins = ["INNER", "LEFT", "RIGHT", "FULL", "CROSS"]
        if join_type.upper() not in valid_joins:
            raise ValueError(f"Invalid join type: {join_type}")

        self.joins.append(
            f"{join_type.upper()} JOIN {self._quote_identifier(table)} ON {on_condition}"
        )
        return self

    def group_by(self, fields: Union[str, List[str]]) -> "QueryBuilder":
        """Add GROUP BY clause."""
        if isinstance(fields, str):
            fields = [fields]
        self.group_by_fields.extend([self._quote_identifier(f) for f in fields])
        return self

    def having(self, condition: str) -> "QueryBuilder":
        """Add HAVING clause."""
        self.having_conditions.append(condition)
        return self

    def build_select(self, fields: Optional[List[str]] = None) -> Tuple[str, List[Any]]:
        """
        Build a SELECT query.

        Args:
            fields: Optional fields to select (overrides previous select() calls)

        Returns:
            Tuple of (SQL query string, parameters list)
        """
        if fields:
            self.select(fields)

        # Build SELECT clause
        if not self.select_fields:
            select_clause = "SELECT *"
        else:
            quoted_fields = [
                self._quote_identifier(f) if f != "*" else f for f in self.select_fields
            ]
            select_clause = f"SELECT {', '.join(quoted_fields)}"

        # Build FROM clause
        from_clause = f"FROM {self._quote_identifier(self.table_name)}"

        # Build JOIN clauses
        join_clause = " ".join(self.joins) if self.joins else ""

        # Build WHERE clause
        where_clause = ""
        if self.conditions:
            where_clause = f"WHERE {' AND '.join(self.conditions)}"

        # Build GROUP BY clause
        group_by_clause = ""
        if self.group_by_fields:
            group_by_clause = f"GROUP BY {', '.join(self.group_by_fields)}"

        # Build HAVING clause
        having_clause = ""
        if self.having_conditions:
            having_clause = f"HAVING {' AND '.join(self.having_conditions)}"

        # Build ORDER BY clause
        order_by_clause = ""
        if self.order_by_fields:
            order_by_clause = f"ORDER BY {', '.join(self.order_by_fields)}"

        # Build LIMIT/OFFSET clause
        limit_clause = ""
        if self.limit_value is not None:
            limit_clause = f"LIMIT {self.limit_value}"
        if self.offset_value is not None:
            limit_clause += f" OFFSET {self.offset_value}"

        # Combine all clauses
        query_parts = [
            select_clause,
            from_clause,
            join_clause,
            where_clause,
            group_by_clause,
            having_clause,
            order_by_clause,
            limit_clause,
        ]

        # Filter out empty parts and join
        query = " ".join(part for part in query_parts if part)

        return query, self.parameters

    def build_insert(self, data: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Build an INSERT query.

        Args:
            data: Dictionary of field-value pairs

        Returns:
            Tuple of (SQL query string, parameters list)
        """
        fields = []
        placeholders = []
        values = []

        for field, value in data.items():
            fields.append(self._quote_identifier(field))
            placeholders.append(self._get_parameter_placeholder())
            values.append(value)

        query = f"INSERT INTO {self._quote_identifier(self.table_name)} ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"

        # Add RETURNING clause for PostgreSQL
        if self.database_type == DatabaseType.POSTGRESQL:
            query += " RETURNING *"

        return query, values

    def build_update(self, data: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Build an UPDATE query.

        Args:
            data: Dictionary of field-value pairs to update

        Returns:
            Tuple of (SQL query string, parameters list)
        """
        set_clauses = []
        update_params = []

        for field, value in data.items():
            placeholder = self._get_parameter_placeholder()
            set_clauses.append(f"{self._quote_identifier(field)} = {placeholder}")
            update_params.append(value)

        set_clause = f"SET {', '.join(set_clauses)}"

        # Build WHERE clause
        where_clause = ""
        if self.conditions:
            where_clause = f"WHERE {' AND '.join(self.conditions)}"

        query = f"UPDATE {self._quote_identifier(self.table_name)} {set_clause} {where_clause}"

        # Add RETURNING clause for PostgreSQL
        if self.database_type == DatabaseType.POSTGRESQL:
            query += " RETURNING *"

        # Combine update parameters with condition parameters
        all_params = update_params + self.parameters

        return query, all_params

    def build_delete(self) -> Tuple[str, List[Any]]:
        """
        Build a DELETE query.

        Returns:
            Tuple of (SQL query string, parameters list)
        """
        # Build WHERE clause
        where_clause = ""
        if self.conditions:
            where_clause = f"WHERE {' AND '.join(self.conditions)}"

        query = f"DELETE FROM {self._quote_identifier(self.table_name)} {where_clause}"

        # Add RETURNING clause for PostgreSQL
        if self.database_type == DatabaseType.POSTGRESQL:
            query += " RETURNING *"

        return query, self.parameters

    def build_count(self) -> Tuple[str, List[Any]]:
        """
        Build a COUNT query.

        Returns:
            Tuple of (SQL query string, parameters list)
        """
        # Build WHERE clause
        where_clause = ""
        if self.conditions:
            where_clause = f"WHERE {' AND '.join(self.conditions)}"

        query = f"SELECT COUNT(*) FROM {self._quote_identifier(self.table_name)} {where_clause}"

        return query, self.parameters

    def _get_parameter_placeholder(self) -> str:
        """Get database-specific parameter placeholder."""
        if self.database_type == DatabaseType.POSTGRESQL:
            self._parameter_index += 1
            return f"${self._parameter_index}"
        elif self.database_type == DatabaseType.MYSQL:
            return "%s"
        else:  # SQLite
            return "?"

    def _quote_identifier(self, identifier: str) -> str:
        """Quote identifier based on database type."""
        # Handle dot notation (e.g., "user.email")
        parts = identifier.split(".")

        if self.database_type == DatabaseType.POSTGRESQL:
            quoted_parts = [f'"{part}"' for part in parts]
        elif self.database_type == DatabaseType.MYSQL:
            quoted_parts = [f"`{part}`" for part in parts]
        else:  # SQLite
            quoted_parts = [f'"{part}"' for part in parts]

        return ".".join(quoted_parts)

    def reset(self) -> "QueryBuilder":
        """Reset the builder to initial state."""
        self.conditions = []
        self.parameters = []
        self.select_fields = []
        self.order_by_fields = []
        self.limit_value = None
        self.offset_value = None
        self.joins = []
        self.group_by_fields = []
        self.having_conditions = []
        self._parameter_index = 0
        return self


def create_query_builder(
    table_name: str, database_url: Optional[str] = None
) -> QueryBuilder:
    """
    Factory function to create a QueryBuilder with auto-detected database type.

    Args:
        table_name: Name of the database table
        database_url: Optional database URL to auto-detect type

    Returns:
        QueryBuilder instance
    """
    if database_url:
        if database_url.startswith(("postgresql://", "postgres://")):
            db_type = DatabaseType.POSTGRESQL
        elif database_url.startswith(
            ("mysql://", "mysql+pymysql://", "mysql+aiomysql://")
        ):
            db_type = DatabaseType.MYSQL
        elif database_url.startswith("sqlite://"):
            db_type = DatabaseType.SQLITE
        else:
            # Default to PostgreSQL
            db_type = DatabaseType.POSTGRESQL
    else:
        # Default to PostgreSQL
        db_type = DatabaseType.POSTGRESQL

    return QueryBuilder(table_name, db_type)
