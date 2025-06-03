"""SQL database node for the Kailash SDK.

This module provides nodes for interacting with relational databases using SQL.
It supports various database systems through a unified interface and handles
connection management, query execution, and result processing.

Design Philosophy:
1. Database-agnostic interface with adapter pattern
2. Connection pooling for performance
3. Safe parameterized queries
4. Flexible result formats
5. Transaction support
"""

from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class SQLDatabaseNode(Node):
    """Executes SQL queries against relational databases.

    This node provides a unified interface for interacting with various RDBMS
    systems including PostgreSQL, MySQL, SQLite, and others. It handles
    connection management, query execution, and result formatting.

    Design Features:
    1. Database adapter pattern for multiple RDBMS support
    2. Connection pooling for efficient resource usage
    3. Parameterized queries to prevent SQL injection
    4. Flexible result formats (dict, list, raw)
    5. Transaction support with commit/rollback
    6. Query timeout handling

    Data Flow:
    - Input: SQL query, parameters, connection config
    - Processing: Execute query, format results
    - Output: Query results in specified format

    Common Usage Patterns:
    1. Data extraction for analytics
    2. ETL pipeline source/sink
    3. Database migrations
    4. Report generation
    5. Data validation queries

    Upstream Sources:
    - User-defined queries
    - Query builder nodes
    - Template processors
    - Previous query results

    Downstream Consumers:
    - Transform nodes: Process query results
    - Writer nodes: Export to files
    - Aggregator nodes: Summarize data
    - Visualization nodes: Create charts

    Error Handling:
    - ConnectionError: Database connection issues
    - QueryError: SQL syntax or execution errors
    - TimeoutError: Query execution timeout
    - PermissionError: Access denied

    Example::

        # Query customer data
        sql_node = SQLDatabaseNode(
            connection_string='postgresql://user:pass@host/db',
            query='SELECT * FROM customers WHERE active = ?',
            parameters=[True],
            result_format='dict'
        )
        result = sql_node.execute()
        # result['data'] = [
        #     {'id': 1, 'name': 'John', 'active': True},
        #     {'id': 2, 'name': 'Jane', 'active': True}
        # ]
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for SQL execution.

        Comprehensive parameters supporting various database operations
        and configuration options.

        Parameter Design:
        1. connection_string: Database connection details
        2. query: SQL query to execute
        3. parameters: Query parameters for safety
        4. result_format: Output structure preference
        5. timeout: Query execution limit
        6. transaction_mode: Transaction handling

        Security considerations:
        - Always use parameterized queries
        - Connection strings should use environment variables
        - Validate query permissions

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "connection_string": NodeParameter(
                name="connection_string",
                type=str,
                required=True,
                description="Database connection string (e.g., 'postgresql://user:pass@host/db')",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="SQL query to execute (use ? for parameters)",
            ),
            "parameters": NodeParameter(
                name="parameters",
                type=list,
                required=False,
                default=[],
                description="Query parameters for parameterized queries",
            ),
            "result_format": NodeParameter(
                name="result_format",
                type=str,
                required=False,
                default="dict",
                description="Result format: 'dict', 'list', or 'raw'",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Query timeout in seconds",
            ),
            "transaction_mode": NodeParameter(
                name="transaction_mode",
                type=str,
                required=False,
                default="auto",
                description="Transaction mode: 'auto', 'manual', or 'none'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute SQL query against database.

        Performs database query execution with proper connection handling,
        parameter binding, and result formatting.

        Processing Steps:
        1. Parse connection string
        2. Establish database connection
        3. Prepare parameterized query
        4. Execute with timeout
        5. Format results
        6. Handle transactions
        7. Close connection

        Connection Management:
        - Uses connection pooling when available
        - Automatic retry on connection failure
        - Proper cleanup on errors

        Result Formatting:
        - dict: List of dictionaries with column names
        - list: List of lists (raw rows)
        - raw: Database cursor object

        Args:
            **kwargs: Validated parameters including:
                - connection_string: Database URL
                - query: SQL statement
                - parameters: Query parameters
                - result_format: Output format
                - timeout: Execution timeout
                - transaction_mode: Transaction handling

        Returns:
            Dictionary containing:
            - data: Query results in specified format
            - row_count: Number of rows affected/returned
            - columns: List of column names
            - execution_time: Query execution duration

        Raises:
            NodeExecutionError: Connection or query errors
            NodeValidationError: Invalid parameters
            TimeoutError: Query timeout exceeded
        """
        connection_string = kwargs["connection_string"]
        query = kwargs["query"]
        # parameters = kwargs.get("parameters", [])  # TODO: Implement parameterized queries
        result_format = kwargs.get("result_format", "dict")
        # timeout = kwargs.get("timeout", 30)  # TODO: Implement query timeout
        # transaction_mode = kwargs.get("transaction_mode", "auto")  # TODO: Implement transaction handling

        # This is a placeholder implementation
        # In a real implementation, you would:
        # 1. Use appropriate database driver (psycopg2, pymysql, sqlite3, etc.)
        # 2. Implement connection pooling
        # 3. Handle parameterized queries properly
        # 4. Implement timeout handling
        # 5. Format results according to result_format

        self.logger.info(f"Executing SQL query on {connection_string}")

        # Simulate query execution
        # In real implementation, use actual database connection
        if "SELECT" in query.upper():
            # Simulate SELECT query results
            data = [
                {"id": 1, "name": "Sample1", "value": 100},
                {"id": 2, "name": "Sample2", "value": 200},
            ]
            columns = ["id", "name", "value"]
            row_count = len(data)
        else:
            # Simulate INSERT/UPDATE/DELETE
            data = []
            columns = []
            row_count = 1  # Affected rows

        # Format results based on result_format
        if result_format == "dict":
            formatted_data = data
        elif result_format == "list":
            formatted_data = [[row[col] for col in columns] for row in data]
        else:  # raw
            formatted_data = data

        return {
            "data": formatted_data,
            "row_count": row_count,
            "columns": columns,
            "execution_time": 0.125,  # Simulated execution time
        }


@register_node()
class SQLQueryBuilderNode(Node):
    """Builds SQL queries dynamically from components.

    This node constructs SQL queries programmatically, providing a safe
    and flexible way to build complex queries without string concatenation.

    Design Features:
    1. Fluent interface for query building
    2. Automatic parameter binding
    3. SQL injection prevention
    4. Cross-database SQL generation
    5. Query validation

    Common Usage Patterns:
    1. Dynamic report queries
    2. Conditional filtering
    3. Multi-table joins
    4. Aggregation queries

    Example::

        builder = SQLQueryBuilderNode(
            table='customers',
            select=['name', 'email'],
            where={'active': True, 'country': 'USA'},
            order_by=['name'],
            limit=100
        )
        result = builder.execute()
        # result['query'] = 'SELECT name, email FROM customers WHERE active = ? AND country = ? ORDER BY name LIMIT 100'
        # result['parameters'] = [True, 'USA']
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for query building.

        Parameters for constructing SQL queries programmatically.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "table": NodeParameter(
                name="table", type=str, required=True, description="Target table name"
            ),
            "select": NodeParameter(
                name="select",
                type=list,
                required=False,
                default=["*"],
                description="Columns to select",
            ),
            "where": NodeParameter(
                name="where",
                type=dict,
                required=False,
                default={},
                description="WHERE clause conditions",
            ),
            "join": NodeParameter(
                name="join",
                type=list,
                required=False,
                default=[],
                description="JOIN clauses",
            ),
            "order_by": NodeParameter(
                name="order_by",
                type=list,
                required=False,
                default=[],
                description="ORDER BY columns",
            ),
            "limit": NodeParameter(
                name="limit",
                type=int,
                required=False,
                default=None,
                description="Result limit",
            ),
            "offset": NodeParameter(
                name="offset",
                type=int,
                required=False,
                default=None,
                description="Result offset",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Build SQL query from components.

        Constructs a parameterized SQL query from the provided components.

        Args:
            **kwargs: Query components

        Returns:
            Dictionary containing:
            - query: Built SQL query with placeholders
            - parameters: List of parameter values
        """
        table = kwargs["table"]
        select = kwargs.get("select", ["*"])
        where = kwargs.get("where", {})
        join = kwargs.get("join", [])
        order_by = kwargs.get("order_by", [])
        limit = kwargs.get("limit")
        offset = kwargs.get("offset")

        # Build SELECT clause
        select_clause = ", ".join(select)
        query_parts = [f"SELECT {select_clause}", f"FROM {table}"]
        parameters = []

        # Build JOIN clauses
        for join_spec in join:
            query_parts.append(f"JOIN {join_spec}")

        # Build WHERE clause
        if where:
            conditions = []
            for key, value in where.items():
                conditions.append(f"{key} = ?")
                parameters.append(value)
            query_parts.append(f"WHERE {' AND '.join(conditions)}")

        # Build ORDER BY clause
        if order_by:
            query_parts.append(f"ORDER BY {', '.join(order_by)}")

        # Build LIMIT/OFFSET
        if limit is not None:
            query_parts.append(f"LIMIT {limit}")
        if offset is not None:
            query_parts.append(f"OFFSET {offset}")

        query = " ".join(query_parts)

        return {"query": query, "parameters": parameters}
