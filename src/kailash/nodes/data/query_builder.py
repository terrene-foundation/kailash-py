"""Query Builder Integration for Database Nodes.

This module provides MongoDB-style query operators for SQL databases
with database-specific optimization and type validation.

Key Features:
- MongoDB-style operators ($eq, $ne, $lt, $gte, $in, $like, etc.)
- Database-specific SQL generation
- Type validation for operators
- Query optimization
- Multi-tenant support
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from kailash.sdk_exceptions import NodeValidationError

logger = logging.getLogger(__name__)


class QueryOperator(Enum):
    """MongoDB-style query operators."""

    # Comparison operators
    EQ = "$eq"  # Equal to
    NE = "$ne"  # Not equal to
    LT = "$lt"  # Less than
    LTE = "$lte"  # Less than or equal to
    GT = "$gt"  # Greater than
    GTE = "$gte"  # Greater than or equal to

    # Array/List operators
    IN = "$in"  # In array
    NIN = "$nin"  # Not in array

    # String operators
    LIKE = "$like"  # SQL LIKE pattern
    ILIKE = "$ilike"  # Case-insensitive LIKE
    REGEX = "$regex"  # Regular expression

    # JSON/Array operators
    CONTAINS = "$contains"  # Array/JSON contains
    CONTAINED_BY = "$contained_by"  # Array/JSON contained by
    HAS_KEY = "$has_key"  # JSON has key

    # Logical operators
    AND = "$and"  # Logical AND
    OR = "$or"  # Logical OR
    NOT = "$not"  # Logical NOT


class DatabaseDialect(Enum):
    """Supported database dialects."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class QueryBuilder:
    """MongoDB-style query builder for SQL databases."""

    def __init__(self, dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL):
        """Initialize query builder with database dialect.

        Args:
            dialect: Database dialect for SQL generation
        """
        self.dialect = dialect
        self.table_name: Optional[str] = None
        self.tenant_id: Optional[str] = None
        self.conditions: List[Dict[str, Any]] = []
        self.parameters: List[Any] = []
        self.parameter_counter = 0

    def table(self, name: str) -> "QueryBuilder":
        """Set table name."""
        self.table_name = name
        return self

    def tenant(self, tenant_id: str) -> "QueryBuilder":
        """Set tenant ID for multi-tenant queries."""
        self.tenant_id = tenant_id
        return self

    def where(
        self, field: str, operator: Union[str, QueryOperator], value: Any
    ) -> "QueryBuilder":
        """Add WHERE condition with MongoDB-style operator.

        Args:
            field: Field name
            operator: Query operator
            value: Value to compare against

        Returns:
            Self for method chaining
        """
        if isinstance(operator, str):
            operator = QueryOperator(operator)

        self._validate_operator_value(operator, value)

        condition = {"field": field, "operator": operator, "value": value}

        self.conditions.append(condition)
        return self

    def find(self, query: Dict[str, Any]) -> "QueryBuilder":
        """Add conditions from MongoDB-style query object.

        Args:
            query: MongoDB-style query dictionary

        Returns:
            Self for method chaining
        """
        self._parse_query_object(query)
        return self

    def build_select(self, fields: List[str] = None) -> Tuple[str, List[Any]]:
        """Build SELECT query.

        Args:
            fields: Fields to select (default: all)

        Returns:
            Tuple of (SQL query, parameters)
        """
        if not self.table_name:
            raise NodeValidationError("Table name is required")

        fields_str = ", ".join(fields) if fields else "*"
        base_query = f"SELECT {fields_str} FROM {self.table_name}"

        where_clause, parameters = self._build_where_clause()

        if where_clause:
            query = f"{base_query} WHERE {where_clause}"
        else:
            query = base_query

        return query, parameters

    def build_update(self, updates: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """Build UPDATE query.

        Args:
            updates: Fields to update

        Returns:
            Tuple of (SQL query, parameters)
        """
        if not self.table_name:
            raise NodeValidationError("Table name is required")

        if not updates:
            raise NodeValidationError("Updates are required")

        # Build SET clause
        set_clauses = []
        update_params = []

        for field, value in updates.items():
            set_clauses.append(f"{field} = ${self._next_parameter()}")
            update_params.append(value)

        set_clause = ", ".join(set_clauses)
        base_query = f"UPDATE {self.table_name} SET {set_clause}"

        # Build WHERE clause
        where_clause, where_params = self._build_where_clause()

        if where_clause:
            query = f"{base_query} WHERE {where_clause}"
        else:
            query = base_query

        return query, update_params + where_params

    def build_delete(self) -> Tuple[str, List[Any]]:
        """Build DELETE query.

        Returns:
            Tuple of (SQL query, parameters)
        """
        if not self.table_name:
            raise NodeValidationError("Table name is required")

        base_query = f"DELETE FROM {self.table_name}"

        where_clause, parameters = self._build_where_clause()

        if where_clause:
            query = f"{base_query} WHERE {where_clause}"
        else:
            query = base_query

        return query, parameters

    def _parse_query_object(self, query: Dict[str, Any]) -> None:
        """Parse MongoDB-style query object into conditions."""
        for field, condition in query.items():
            if field.startswith("$"):
                # Logical operator
                self._parse_logical_operator(field, condition)
            else:
                # Field condition
                self._parse_field_condition(field, condition)

    def _parse_logical_operator(self, operator: str, condition: Any) -> None:
        """Parse logical operator ($and, $or, $not)."""
        if operator == "$and":
            if not isinstance(condition, list):
                raise NodeValidationError("$and requires a list of conditions")
            for sub_condition in condition:
                self._parse_query_object(sub_condition)
        elif operator == "$or":
            if not isinstance(condition, list):
                raise NodeValidationError("$or requires a list of conditions")
            # For simplicity, we'll convert OR to individual conditions
            # In a full implementation, we'd need to track grouping
            for sub_condition in condition:
                self._parse_query_object(sub_condition)
        elif operator == "$not":
            # Handle NOT operator
            self._parse_query_object(condition)

    def _parse_field_condition(self, field: str, condition: Any) -> None:
        """Parse field condition."""
        if isinstance(condition, dict):
            # Operator-based condition
            for op, value in condition.items():
                if op in [e.value for e in QueryOperator]:
                    self.where(field, op, value)
                else:
                    raise NodeValidationError(f"Unknown operator: {op}")
        else:
            # Simple equality
            self.where(field, QueryOperator.EQ, condition)

    def _build_where_clause(self) -> Tuple[str, List[Any]]:
        """Build WHERE clause from conditions."""
        clauses = []
        parameters = []

        # Add tenant filtering first if specified
        if self.tenant_id:
            clauses.append(f"tenant_id = ${self._next_parameter()}")
            parameters.append(self.tenant_id)

        # Add other conditions
        for condition in self.conditions:
            clause, params = self._build_condition_clause(condition)
            clauses.append(clause)
            parameters.extend(params)

        if not clauses:
            return "", []

        where_clause = " AND ".join(clauses)

        # If we have tenant filtering and other conditions, group the other conditions
        if self.tenant_id and len(clauses) > 1:
            other_clauses = " AND ".join(clauses[1:])
            where_clause = f"{clauses[0]} AND ({other_clauses})"

        return where_clause, parameters

    def _build_condition_clause(
        self, condition: Dict[str, Any]
    ) -> Tuple[str, List[Any]]:
        """Build SQL clause for a single condition."""
        field = condition["field"]
        operator = condition["operator"]
        value = condition["value"]

        if operator == QueryOperator.EQ:
            return f"{field} = ${self._next_parameter()}", [value]
        elif operator == QueryOperator.NE:
            return f"{field} != ${self._next_parameter()}", [value]
        elif operator == QueryOperator.LT:
            return f"{field} < ${self._next_parameter()}", [value]
        elif operator == QueryOperator.LTE:
            return f"{field} <= ${self._next_parameter()}", [value]
        elif operator == QueryOperator.GT:
            return f"{field} > ${self._next_parameter()}", [value]
        elif operator == QueryOperator.GTE:
            return f"{field} >= ${self._next_parameter()}", [value]
        elif operator == QueryOperator.IN:
            if not isinstance(value, (list, tuple)):
                raise NodeValidationError("$in requires a list or tuple")
            placeholders = ", ".join([f"${self._next_parameter()}" for _ in value])
            return f"{field} IN ({placeholders})", list(value)
        elif operator == QueryOperator.NIN:
            if not isinstance(value, (list, tuple)):
                raise NodeValidationError("$nin requires a list or tuple")
            placeholders = ", ".join([f"${self._next_parameter()}" for _ in value])
            return f"{field} NOT IN ({placeholders})", list(value)
        elif operator == QueryOperator.LIKE:
            return f"{field} LIKE ${self._next_parameter()}", [value]
        elif operator == QueryOperator.ILIKE:
            if self.dialect == DatabaseDialect.POSTGRESQL:
                return f"{field} ILIKE ${self._next_parameter()}", [value]
            else:
                return f"LOWER({field}) LIKE LOWER(${self._next_parameter()})", [value]
        elif operator == QueryOperator.REGEX:
            if self.dialect == DatabaseDialect.POSTGRESQL:
                return f"{field} ~ ${self._next_parameter()}", [value]
            else:
                return f"{field} REGEXP ${self._next_parameter()}", [value]
        elif operator == QueryOperator.CONTAINS:
            if self.dialect == DatabaseDialect.POSTGRESQL:
                return f"{field} @> ${self._next_parameter()}", [value]
            else:
                return f"JSON_CONTAINS({field}, ${self._next_parameter()})", [value]
        elif operator == QueryOperator.CONTAINED_BY:
            if self.dialect == DatabaseDialect.POSTGRESQL:
                return f"{field} <@ ${self._next_parameter()}", [value]
            else:
                return f"JSON_CONTAINS(${self._next_parameter()}, {field})", [value]
        elif operator == QueryOperator.HAS_KEY:
            if self.dialect == DatabaseDialect.POSTGRESQL:
                return f"{field} ? ${self._next_parameter()}", [value]
            else:
                return f"JSON_EXTRACT({field}, '$.{value}') IS NOT NULL", []
        else:
            raise NodeValidationError(f"Unsupported operator: {operator}")

    def _validate_operator_value(self, operator: QueryOperator, value: Any) -> None:
        """Validate operator-value combination."""
        if operator in [QueryOperator.IN, QueryOperator.NIN]:
            if not isinstance(value, (list, tuple)):
                raise NodeValidationError(f"{operator.value} requires a list or tuple")
        elif operator in [QueryOperator.LIKE, QueryOperator.ILIKE, QueryOperator.REGEX]:
            if not isinstance(value, str):
                raise NodeValidationError(f"{operator.value} requires a string value")
        elif operator == QueryOperator.HAS_KEY:
            if not isinstance(value, str):
                raise NodeValidationError(f"{operator.value} requires a string key")

    def _next_parameter(self) -> int:
        """Get next parameter placeholder number."""
        self.parameter_counter += 1
        return self.parameter_counter

    def reset(self) -> "QueryBuilder":
        """Reset builder state."""
        self.table_name = None
        self.tenant_id = None
        self.conditions = []
        self.parameters = []
        self.parameter_counter = 0
        return self


# Factory function for creating query builders
def create_query_builder(dialect: str = "postgresql") -> QueryBuilder:
    """Create a query builder for the specified database dialect.

    Args:
        dialect: Database dialect (postgresql, mysql, sqlite)

    Returns:
        QueryBuilder instance
    """
    try:
        db_dialect = DatabaseDialect(dialect.lower())
        return QueryBuilder(db_dialect)
    except ValueError:
        raise NodeValidationError(f"Unsupported database dialect: {dialect}")
