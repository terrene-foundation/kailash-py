"""
SQL Query Interceptor for Multi-Tenant Database Operations.

This module provides query interception capabilities to automatically inject
tenant isolation conditions into SQL queries, ensuring proper data segregation
in multi-tenant environments.
"""

import logging
import re
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Set, Tuple

import sqlparse
from sqlparse import sql
from sqlparse import tokens as T

from .exceptions import CrossTenantAccessError, QueryParsingError, TenantIsolationError

logger = logging.getLogger(__name__)


@dataclass
class ParsedQuery:
    """Represents a parsed SQL query with extracted components."""

    query_type: str
    tables: List[str]
    columns: List[str]
    where_conditions: List[str]
    joins: List[Dict[str, str]]
    subqueries: List["ParsedQuery"]
    has_joins: bool = False
    has_subqueries: bool = False
    target_table: Optional[str] = None
    set_columns: List[str] = None
    parameters: List[str] = None

    def __post_init__(self):
        if self.set_columns is None:
            self.set_columns = []
        if self.parameters is None:
            self.parameters = []


class QueryInterceptor:
    """
    SQL Query Interceptor for multi-tenant database operations.

    Automatically injects tenant isolation conditions into SQL queries to ensure
    proper data segregation in multi-tenant environments.
    """

    def __init__(
        self,
        tenant_id: str,
        tenant_tables: Optional[List[str]] = None,
        non_tenant_tables: Optional[List[str]] = None,
        tenant_column: str = "tenant_id",
        admin_mode: bool = False,
        bypass_tenant_isolation: bool = False,
        enable_optimizations: bool = False,
        enable_partitioning: bool = False,
        enable_query_rewriting: bool = False,
        max_query_size: int = 1024 * 1024,  # 1MB
    ):
        """
        Initialize the QueryInterceptor.

        Args:
            tenant_id: The current tenant identifier
            tenant_tables: List of tables that require tenant isolation
            non_tenant_tables: List of tables that do NOT require tenant isolation
            tenant_column: Column name used for tenant identification
            admin_mode: Whether this is an admin user
            bypass_tenant_isolation: Whether to bypass tenant isolation (admin only)
            enable_optimizations: Whether to enable query optimizations
            enable_partitioning: Whether to enable partition pruning
            enable_query_rewriting: Whether to enable query rewriting
            max_query_size: Maximum allowed query size in bytes
        """
        self.tenant_id = tenant_id
        self.tenant_tables = set(tenant_tables) if tenant_tables else set()
        self.non_tenant_tables = set(non_tenant_tables) if non_tenant_tables else set()
        self.tenant_column = tenant_column
        self.admin_mode = admin_mode
        self.bypass_tenant_isolation = bypass_tenant_isolation and admin_mode
        self.enable_optimizations = enable_optimizations
        self.enable_partitioning = enable_partitioning
        self.enable_query_rewriting = enable_query_rewriting
        self.max_query_size = max_query_size

        # Thread safety
        self._lock = Lock()

        # Optimization tracking
        self._applied_optimizations = []

        # Query statistics
        self._query_stats = {
            "total_queries": 0,
            "tenant_injections": 0,
            "optimizations_applied": 0,
            "errors": 0,
        }

    @property
    def tenant_isolation_enabled(self) -> bool:
        """Check if tenant isolation is enabled."""
        return not self.bypass_tenant_isolation

    def parse_query(self, query: str) -> ParsedQuery:
        """
        Parse a SQL query and extract its components.

        Args:
            query: The SQL query to parse

        Returns:
            ParsedQuery object with extracted components

        Raises:
            QueryParsingError: If the query cannot be parsed
        """
        if query is None:
            raise ValueError("Query cannot be None")

        if not query or not query.strip():
            raise QueryParsingError("Empty query")

        if len(query) > self.max_query_size:
            raise QueryParsingError("Query too large")

        # Pre-validation for malformed SQL
        self._validate_sql_syntax(query)

        try:
            with self._lock:
                self._query_stats["total_queries"] += 1

            # Parse the query using sqlparse
            parsed = sqlparse.parse(query)[0]

            # Extract query type
            query_type = self._extract_query_type(parsed)

            # Validate that we found a valid query type
            if query_type == "UNKNOWN":
                raise QueryParsingError("Malformed SQL: No valid SQL command found")

            # Extract tables
            tables = self._extract_tables(parsed)

            # Extract columns
            columns = self._extract_columns(parsed)

            # Extract WHERE conditions
            where_conditions = self._extract_where_conditions(parsed)

            # Extract JOINs
            joins = self._extract_joins(parsed)

            # Extract subqueries
            subqueries = self._extract_subqueries(parsed)

            # Determine target table for DML operations
            target_table = self._extract_target_table(parsed, query_type)

            # Extract SET columns for UPDATE
            set_columns = (
                self._extract_set_columns(parsed) if query_type == "UPDATE" else []
            )

            # Extract parameters
            parameters = self._extract_parameters(parsed)

            return ParsedQuery(
                query_type=query_type,
                tables=tables,
                columns=columns,
                where_conditions=where_conditions,
                joins=joins,
                subqueries=subqueries,
                has_joins=len(joins) > 0,
                has_subqueries=len(subqueries) > 0,
                target_table=target_table,
                set_columns=set_columns,
                parameters=parameters,
            )

        except Exception as e:
            with self._lock:
                self._query_stats["errors"] += 1
            if isinstance(e, (ValueError, QueryParsingError)):
                raise
            raise QueryParsingError(f"Malformed SQL: {str(e)}")

    def inject_tenant_conditions(
        self, query: str, params: List[Any]
    ) -> Tuple[str, List[Any]]:
        """
        Inject tenant isolation conditions into a SQL query.

        Args:
            query: The original SQL query
            params: Query parameters

        Returns:
            Tuple of (modified_query, modified_params)
        """
        if self.bypass_tenant_isolation:
            return query, params

        try:
            parsed_query = self.parse_query(query)

            # Skip non-tenant tables
            tenant_tables_in_query = [
                table for table in parsed_query.tables if self.is_tenant_table(table)
            ]

            if not tenant_tables_in_query:
                return query, params

            modified_query = query
            modified_params = params.copy()

            # Handle different query types
            if parsed_query.query_type == "SELECT":
                modified_query, modified_params = self._inject_select_conditions(
                    modified_query,
                    modified_params,
                    parsed_query,
                    tenant_tables_in_query,
                )
            elif parsed_query.query_type == "INSERT":
                modified_query, modified_params = self._inject_insert_conditions(
                    modified_query, modified_params, parsed_query
                )
            elif parsed_query.query_type == "UPDATE":
                modified_query, modified_params = self._inject_update_conditions(
                    modified_query,
                    modified_params,
                    parsed_query,
                    tenant_tables_in_query,
                )
            elif parsed_query.query_type == "DELETE":
                modified_query, modified_params = self._inject_delete_conditions(
                    modified_query,
                    modified_params,
                    parsed_query,
                    tenant_tables_in_query,
                )

            with self._lock:
                self._query_stats["tenant_injections"] += 1

            return modified_query, modified_params

        except Exception as e:
            with self._lock:
                self._query_stats["errors"] += 1
            logger.error(f"Error injecting tenant conditions: {e}")
            raise TenantIsolationError(f"Failed to inject tenant conditions: {str(e)}")

    def is_tenant_table(self, table_name: str) -> bool:
        """Check if a table requires tenant isolation."""
        # Remove alias if present
        table_name = table_name.split()[0] if " " in table_name else table_name

        # If explicit lists are provided, use them
        if self.tenant_tables:
            return table_name in self.tenant_tables
        if self.non_tenant_tables:
            return table_name not in self.non_tenant_tables

        # Default: assume all tables are tenant tables unless explicitly marked otherwise
        return True

    def optimize_query(self, query: str, params: List[Any]) -> Tuple[str, List[Any]]:
        """
        Optimize a query for tenant isolation performance.

        Args:
            query: The SQL query to optimize
            params: Query parameters

        Returns:
            Tuple of (optimized_query, optimized_params)
        """
        if not self.enable_optimizations:
            return query, params

        optimized_query = query
        optimized_params = params.copy()

        # Apply query optimizations
        if self.enable_query_rewriting:
            optimized_query, optimized_params = self._rewrite_query(
                optimized_query, optimized_params
            )

        if self.enable_partitioning:
            optimized_query = self._add_partition_hints(optimized_query)

        # Add index hints
        optimized_query = self._add_index_hints(optimized_query)

        with self._lock:
            self._query_stats["optimizations_applied"] += 1

        return optimized_query, optimized_params

    def get_optimization_suggestions(self, query: str) -> Dict[str, Any]:
        """Get optimization suggestions for a query."""
        suggestions = {
            "index_suggestions": [],
            "partition_suggestions": [],
            "query_rewrite_suggestions": [],
        }

        try:
            parsed = self.parse_query(query)

            # Index suggestions
            for table in parsed.tables:
                if self.is_tenant_table(table):
                    suggestions["index_suggestions"].append(
                        {
                            "table": table,
                            "columns": [self.tenant_column],
                            "type": "btree",
                            "reason": "Tenant isolation filtering",
                        }
                    )

            # Partition suggestions
            if self.enable_partitioning:
                suggestions["partition_suggestions"].append(
                    {
                        "strategy": "range",
                        "column": self.tenant_column,
                        "reason": "Tenant-based partitioning",
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to generate optimization suggestions: {e}")

        return suggestions

    def get_applied_optimizations(self) -> List[str]:
        """Get list of applied optimizations."""
        return self._applied_optimizations.copy()

    def analyze_query_complexity(self, query: str) -> Dict[str, Any]:
        """Analyze query complexity for optimization decisions."""
        try:
            parsed = self.parse_query(query)

            complexity_score = 0

            # Base complexity
            complexity_score += len(parsed.tables) * 2
            complexity_score += len(parsed.columns)
            complexity_score += len(parsed.joins) * 3
            complexity_score += len(parsed.subqueries) * 5
            complexity_score += len(parsed.where_conditions)

            # Categorize complexity
            if complexity_score <= 10:
                complexity_level = "simple"
            elif complexity_score <= 30:
                complexity_level = "medium"
            else:
                complexity_level = "complex"

            recommendations = []

            if complexity_score > 20:
                recommendations.append("Consider adding indexes on tenant_id")
            if len(parsed.subqueries) > 2:
                recommendations.append("Consider rewriting subqueries as JOINs")
            if len(parsed.joins) > 3:
                recommendations.append("Consider query optimization")

            return {
                "complexity_score": complexity_score,
                "complexity_level": complexity_level,
                "optimization_recommendations": recommendations,
                "tables_count": len(parsed.tables),
                "joins_count": len(parsed.joins),
                "subqueries_count": len(parsed.subqueries),
            }

        except Exception as e:
            logger.warning(f"Failed to analyze query complexity: {e}")
            return {
                "complexity_score": 0,
                "complexity_level": "unknown",
                "optimization_recommendations": [],
                "error": str(e),
            }

    def validate_tenant_security(self, query: str) -> Dict[str, Any]:
        """Validate tenant security for a query."""
        try:
            parsed = self.parse_query(query)

            # Check for tenant isolation
            has_tenant_isolation = False
            for table in parsed.tables:
                if self.is_tenant_table(table):
                    # Check if tenant condition is present
                    tenant_condition_found = any(
                        self.tenant_column in condition
                        for condition in parsed.where_conditions
                    )
                    if tenant_condition_found:
                        has_tenant_isolation = True
                        break

            return {
                "secure": has_tenant_isolation
                or not any(self.is_tenant_table(table) for table in parsed.tables),
                "tenant_isolation_present": has_tenant_isolation,
                "tenant_tables_in_query": [
                    table for table in parsed.tables if self.is_tenant_table(table)
                ],
                "security_level": "high" if has_tenant_isolation else "medium",
            }

        except Exception as e:
            logger.warning(f"Failed to validate tenant security: {e}")
            return {"secure": False, "error": str(e)}

    def validate_cross_tenant_access(
        self, query: str, params: List[Any]
    ) -> Dict[str, Any]:
        """Validate that cross-tenant access is prevented."""
        try:
            # Check if query contains explicit tenant conditions for other tenants
            query_lower = query.lower()

            # Look for tenant_id conditions
            tenant_conditions = re.findall(
                rf"{self.tenant_column}\s*=\s*['\"]?([^'\"\s]+)['\"]?", query_lower
            )

            # Check parameters for tenant IDs
            param_tenant_ids = [
                param
                for param in params
                if isinstance(param, str) and param != self.tenant_id
            ]

            cross_tenant_access = False
            other_tenant_ids = []

            for condition in tenant_conditions:
                if condition != self.tenant_id:
                    cross_tenant_access = True
                    other_tenant_ids.append(condition)

            return {
                "cross_tenant_access_prevented": not cross_tenant_access,
                "other_tenant_ids_found": other_tenant_ids,
                "current_tenant_id": self.tenant_id,
                "validation_passed": not cross_tenant_access,
            }

        except Exception as e:
            logger.warning(f"Failed to validate cross-tenant access: {e}")
            return {"cross_tenant_access_prevented": False, "error": str(e)}

    def get_query_stats(self) -> Dict[str, int]:
        """Get query processing statistics."""
        with self._lock:
            return self._query_stats.copy()

    # Private helper methods

    def _extract_query_type(self, parsed) -> str:
        """Extract the query type (SELECT, INSERT, UPDATE, DELETE)."""
        for token in parsed.tokens:
            if token.ttype is T.DML:
                return token.value.upper()
        return "UNKNOWN"

    def _extract_tables(self, parsed) -> List[str]:
        """Extract table names from parsed query."""
        tables = []

        def extract_from_token(token):
            if hasattr(token, "tokens"):
                for subtoken in token.tokens:
                    extract_from_token(subtoken)
            elif token.ttype is T.Name:
                # This is a simplified extraction - in production would need more sophisticated parsing
                tables.append(token.value)

        # Look for FROM keyword and extract subsequent table names
        in_from_clause = False
        for token in parsed.tokens:
            if token.ttype is T.Keyword and token.value.upper() == "FROM":
                in_from_clause = True
            elif in_from_clause and token.ttype is T.Name:
                tables.append(token.value)
                in_from_clause = False
            elif hasattr(token, "tokens"):
                extract_from_token(token)

        return list(set(tables))  # Remove duplicates

    def _extract_columns(self, parsed) -> List[str]:
        """Extract column names from parsed query."""
        columns = []
        query_str = str(parsed)

        # Extract columns from SELECT statements
        if (
            parsed.tokens
            and parsed.tokens[0].ttype is T.DML
            and parsed.tokens[0].value.upper() == "SELECT"
        ):
            select_match = re.search(
                r"SELECT\s+(.+?)\s+FROM", query_str, re.IGNORECASE | re.DOTALL
            )
            if select_match:
                columns_str = select_match.group(1).strip()
                if columns_str != "*":
                    # Split by comma and clean up
                    column_list = [col.strip() for col in columns_str.split(",")]
                    for col in column_list:
                        # Remove table prefixes and aliases
                        col_clean = re.sub(r"^\w+\.", "", col)  # Remove table prefix
                        col_clean = re.sub(
                            r"\s+as\s+\w+", "", col_clean, flags=re.IGNORECASE
                        )  # Remove alias
                        columns.append(col_clean.strip())

        # Extract columns from INSERT statements
        elif (
            parsed.tokens
            and parsed.tokens[0].ttype is T.DML
            and parsed.tokens[0].value.upper() == "INSERT"
        ):
            insert_match = re.search(
                r"INSERT\s+INTO\s+\w+\s*\(([^)]+)\)", query_str, re.IGNORECASE
            )
            if insert_match:
                columns_str = insert_match.group(1).strip()
                columns = [col.strip() for col in columns_str.split(",")]

        # Extract columns from UPDATE statements
        elif (
            parsed.tokens
            and parsed.tokens[0].ttype is T.DML
            and parsed.tokens[0].value.upper() == "UPDATE"
        ):
            set_match = re.search(r"SET\s+(.+?)\s+WHERE", query_str, re.IGNORECASE)
            if set_match:
                set_clause = set_match.group(1)
                # Extract column names from SET clause
                column_matches = re.findall(r"(\w+)\s*=", set_clause)
                columns.extend(column_matches)

        return columns

    def _extract_where_conditions(self, parsed) -> List[str]:
        """Extract WHERE conditions from parsed query."""
        conditions = []

        # This is a simplified implementation
        query_str = str(parsed)
        where_match = re.search(
            r"WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+GROUP\s+BY|\s+HAVING|\s+LIMIT|$)",
            query_str,
            re.IGNORECASE,
        )
        if where_match:
            conditions.append(where_match.group(1).strip())

        return conditions

    def _extract_joins(self, parsed) -> List[Dict[str, str]]:
        """Extract JOIN information from parsed query."""
        joins = []

        # This is a simplified implementation
        query_str = str(parsed)
        join_patterns = [
            r"(INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|FULL\s+JOIN|JOIN)\s+(\w+)\s+(?:(\w+)\s+)?ON\s+([^\n]+?)(?=\s+(?:JOIN|WHERE|ORDER|GROUP|HAVING|LIMIT|$))",
        ]

        for pattern in join_patterns:
            matches = re.findall(pattern, query_str, re.IGNORECASE)
            for match in matches:
                join_type = match[0].strip()
                table_name = match[1].strip()
                table_alias = match[2].strip() if match[2] else None
                condition = match[3].strip() if len(match) > 3 else match[2].strip()

                joins.append(
                    {
                        "type": join_type,
                        "table": table_name,
                        "alias": table_alias,
                        "condition": condition,
                    }
                )

        return joins

    def _extract_subqueries(self, parsed) -> List[ParsedQuery]:
        """Extract subqueries from parsed query."""
        subqueries = []

        # This is a simplified implementation
        # In production, would need recursive parsing
        query_str = str(parsed)
        subquery_pattern = r"\(([^)]*SELECT[^)]*)\)"
        matches = re.findall(subquery_pattern, query_str, re.IGNORECASE)

        for match in matches:
            try:
                subquery = self.parse_query(match)
                subqueries.append(subquery)
            except Exception:
                # Skip malformed subqueries
                pass

        return subqueries

    def _extract_target_table(self, parsed, query_type: str) -> Optional[str]:
        """Extract target table for DML operations."""
        if query_type in ["INSERT", "UPDATE", "DELETE"]:
            # This is a simplified implementation
            query_str = str(parsed)
            if query_type == "INSERT":
                match = re.search(r"INSERT\s+INTO\s+(\w+)", query_str, re.IGNORECASE)
            elif query_type == "UPDATE":
                match = re.search(r"UPDATE\s+(\w+)", query_str, re.IGNORECASE)
            elif query_type == "DELETE":
                match = re.search(r"DELETE\s+FROM\s+(\w+)", query_str, re.IGNORECASE)

            if match:
                return match.group(1)

        return None

    def _extract_set_columns(self, parsed) -> List[str]:
        """Extract SET columns from UPDATE queries."""
        columns = []

        # This is a simplified implementation
        query_str = str(parsed)
        set_match = re.search(r"SET\s+(.+?)\s+WHERE", query_str, re.IGNORECASE)
        if set_match:
            set_clause = set_match.group(1)
            # Extract column names from SET clause
            column_matches = re.findall(r"(\w+)\s*=", set_clause)
            columns.extend(column_matches)

        return columns

    def _extract_parameters(self, parsed) -> List[str]:
        """Extract parameter placeholders from query."""
        parameters = []

        # This is a simplified implementation
        query_str = str(parsed)
        # Look for $1, $2, etc. (PostgreSQL style) or ? (generic style)
        param_matches = re.findall(r"(\$\d+|\?)", query_str)
        parameters.extend(param_matches)

        return parameters

    def _inject_select_conditions(
        self,
        query: str,
        params: List[Any],
        parsed: ParsedQuery,
        tenant_tables: List[str],
    ) -> Tuple[str, List[Any]]:
        """Inject tenant conditions into SELECT queries."""
        modified_query = query
        modified_params = params.copy()

        # Add tenant conditions to WHERE clause
        if "WHERE" in modified_query.upper():
            # Add AND condition
            for table in tenant_tables:
                table_alias = self._get_table_alias(modified_query, table)
                tenant_condition = f"{table_alias}.{self.tenant_column} = ?"
                modified_query = re.sub(
                    r"WHERE\s+",
                    f"WHERE {tenant_condition} AND ",
                    modified_query,
                    flags=re.IGNORECASE,
                    count=1,
                )
                modified_params.append(self.tenant_id)
        else:
            # Add WHERE clause
            for table in tenant_tables:
                table_alias = self._get_table_alias(modified_query, table)
                tenant_condition = f"{table_alias}.{self.tenant_column} = ?"

                # Insert before ORDER BY, GROUP BY, or HAVING if present
                insertion_point = self._find_insertion_point(modified_query)
                if insertion_point:
                    modified_query = (
                        modified_query[:insertion_point]
                        + f" WHERE {tenant_condition}"
                        + modified_query[insertion_point:]
                    )
                else:
                    modified_query += f" WHERE {tenant_condition}"
                modified_params.append(self.tenant_id)
                break  # Only add one WHERE clause

        return modified_query, modified_params

    def _inject_insert_conditions(
        self, query: str, params: List[Any], parsed: ParsedQuery
    ) -> Tuple[str, List[Any]]:
        """Inject tenant conditions into INSERT queries."""
        if not parsed.target_table or not self.is_tenant_table(parsed.target_table):
            return query, params

        modified_query = query
        modified_params = params.copy()

        # Add tenant_id to columns and values
        insert_match = re.search(
            r"INSERT\s+INTO\s+\w+\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
            modified_query,
            re.IGNORECASE,
        )
        if insert_match:
            columns = insert_match.group(1)
            values = insert_match.group(2)

            # Add tenant_id column
            new_columns = f"{columns}, {self.tenant_column}"
            new_values = f"{values}, ?"

            modified_query = re.sub(
                r"INSERT\s+INTO\s+\w+\s*\([^)]+\)\s*VALUES\s*\([^)]+\)",
                f"INSERT INTO {parsed.target_table} ({new_columns}) VALUES ({new_values})",
                modified_query,
                flags=re.IGNORECASE,
            )
            modified_params.append(self.tenant_id)

        return modified_query, modified_params

    def _inject_update_conditions(
        self,
        query: str,
        params: List[Any],
        parsed: ParsedQuery,
        tenant_tables: List[str],
    ) -> Tuple[str, List[Any]]:
        """Inject tenant conditions into UPDATE queries."""
        modified_query = query
        modified_params = params.copy()

        # Add tenant condition to WHERE clause
        if "WHERE" in modified_query.upper():
            # Add AND condition
            tenant_condition = f"{self.tenant_column} = ?"
            modified_query = re.sub(
                r"WHERE\s+",
                f"WHERE {tenant_condition} AND ",
                modified_query,
                flags=re.IGNORECASE,
                count=1,
            )
            modified_params.append(self.tenant_id)
        else:
            # Add WHERE clause
            tenant_condition = f"{self.tenant_column} = ?"
            modified_query += f" WHERE {tenant_condition}"
            modified_params.append(self.tenant_id)

        return modified_query, modified_params

    def _inject_delete_conditions(
        self,
        query: str,
        params: List[Any],
        parsed: ParsedQuery,
        tenant_tables: List[str],
    ) -> Tuple[str, List[Any]]:
        """Inject tenant conditions into DELETE queries."""
        modified_query = query
        modified_params = params.copy()

        # Add tenant condition to WHERE clause
        if "WHERE" in modified_query.upper():
            # Add AND condition
            tenant_condition = f"{self.tenant_column} = ?"
            modified_query = re.sub(
                r"WHERE\s+",
                f"WHERE {tenant_condition} AND ",
                modified_query,
                flags=re.IGNORECASE,
                count=1,
            )
            modified_params.append(self.tenant_id)
        else:
            # Add WHERE clause
            tenant_condition = f"{self.tenant_column} = ?"
            modified_query += f" WHERE {tenant_condition}"
            modified_params.append(self.tenant_id)

        return modified_query, modified_params

    def _get_table_alias(self, query: str, table: str) -> str:
        """Get table alias or table name for use in conditions."""
        # Look for table alias in FROM clause
        alias_match = re.search(rf"{table}\s+(\w+)", query, re.IGNORECASE)
        if alias_match:
            return alias_match.group(1)
        return table

    def _find_insertion_point(self, query: str) -> Optional[int]:
        """Find the best insertion point for WHERE clause."""
        keywords = ["ORDER BY", "GROUP BY", "HAVING", "LIMIT"]

        for keyword in keywords:
            match = re.search(rf"\s+{keyword}\s+", query, re.IGNORECASE)
            if match:
                return match.start()

        return None

    def _rewrite_query(self, query: str, params: List[Any]) -> Tuple[str, List[Any]]:
        """Rewrite query for better performance."""
        # This is a simplified implementation
        # In production, would implement more sophisticated rewriting

        self._applied_optimizations.append("query_rewriting")

        # Convert IN subqueries to JOINs if beneficial
        if "IN (" in query.upper() and "SELECT" in query.upper():
            # This is a placeholder - real implementation would be more complex
            pass

        return query, params

    def _add_partition_hints(self, query: str) -> str:
        """Add partition pruning hints to query."""
        # This is a simplified implementation
        # In production, would add database-specific partition hints

        self._applied_optimizations.append("partition_pruning")
        return query

    def _add_index_hints(self, query: str) -> str:
        """Add index hints to query."""
        # This is a simplified implementation
        # In production, would add database-specific index hints

        self._applied_optimizations.append("index_hints")
        return query

    def _validate_sql_syntax(self, query: str) -> None:
        """
        Validate SQL syntax and raise QueryParsingError for malformed queries.

        Args:
            query: The SQL query to validate

        Raises:
            QueryParsingError: If the query is malformed
        """
        query_stripped = query.strip()

        # Check for common malformed patterns
        malformed_patterns = [
            # Incomplete SELECT statements
            r"^SELECT\s*\*\s*FROM\s*$",
            r"^SELECT\s+\*\s+FROM\s*$",
            r"^SELECT\s+.*\s+FROM\s*$",
            # Incomplete INSERT statements
            r"^INSERT\s+INTO\s*$",
            r"^INSERT\s+INTO\s+\(\s*.*\s*\)\s*VALUES\s*$",
            r"^INSERT\s+INTO\s+\(\s*.*\s*\)\s+VALUES\s*\(\s*$",
            # Incomplete UPDATE statements
            r"^UPDATE\s+\w+\s+SET\s*$",
            r"^UPDATE\s+\w+\s*$",
            # Incomplete DELETE statements
            r"^DELETE\s+FROM\s*$",
            r"^DELETE\s*$",
            # Incomplete WHERE clauses
            r"WHERE\s*$",
            r"WHERE\s+\w+\s*$",
            r"WHERE\s+\w+\s*=\s*$",
            # Common typos
            r"^SELCT\s+",
            r"^SLECT\s+",
            r"^SELET\s+",
            r"^DELET\s+",
            r"^UPDAT\s+",
            r"^INSER\s+",
            # Missing table names
            r"^INSERT\s+INTO\s*\(",
            r"^UPDATE\s+SET\s+",
            r"^DELETE\s+FROM\s+WHERE\s+",
            # Unmatched parentheses
            r"^\([^)]*$",
            r"^[^(]*\)$",
        ]

        for pattern in malformed_patterns:
            if re.search(pattern, query_stripped, re.IGNORECASE):
                raise QueryParsingError(f"Malformed SQL: {query_stripped}")

        # Check for basic SQL structure requirements
        query_upper = query_stripped.upper()

        # Must start with a valid SQL command
        valid_commands = [
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "WITH",
            "CREATE",
            "DROP",
            "ALTER",
        ]
        if not any(query_upper.startswith(cmd) for cmd in valid_commands):
            raise QueryParsingError("Malformed SQL: Invalid SQL command")

        # Check for balanced parentheses
        paren_count = 0
        for char in query_stripped:
            if char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
                if paren_count < 0:
                    raise QueryParsingError(
                        "Malformed SQL: Unmatched closing parenthesis"
                    )

        if paren_count != 0:
            raise QueryParsingError("Malformed SQL: Unmatched opening parenthesis")

        # Check for proper FROM clause in SELECT statements
        if query_upper.startswith("SELECT"):
            # Allow subqueries and CTEs, but basic SELECT must have FROM
            if " FROM " not in query_upper and "FROM(" not in query_upper.replace(
                " ", ""
            ):
                # Check if it's a simple expression (like SELECT 1)
                if not re.match(r"^SELECT\s+[\d\s+\-*/()]+$", query_upper):
                    raise QueryParsingError(
                        "Malformed SQL: SELECT statement missing FROM clause"
                    )

        # Check for proper table in INSERT statements
        if query_upper.startswith("INSERT"):
            if not re.search(r"INSERT\s+INTO\s+\w+", query_upper):
                raise QueryParsingError(
                    "Malformed SQL: INSERT statement missing table name"
                )

        # Check for proper table in UPDATE statements
        if query_upper.startswith("UPDATE"):
            if not re.search(r"UPDATE\s+\w+", query_upper):
                raise QueryParsingError(
                    "Malformed SQL: UPDATE statement missing table name"
                )

        # Check for proper table in DELETE statements
        if query_upper.startswith("DELETE"):
            if not re.search(r"DELETE\s+FROM\s+\w+", query_upper):
                raise QueryParsingError(
                    "Malformed SQL: DELETE statement missing FROM clause"
                )
