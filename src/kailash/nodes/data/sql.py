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

import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError


@register_node()
class SQLDatabaseNode(Node):

    class _DatabaseConfigManager:
        """Internal manager for database configurations from project settings."""

        def __init__(self, project_config_path: str):
            """Initialize with project configuration file path."""
            self.config_path = project_config_path
            self.config = self._load_project_config()

        def _load_project_config(self) -> Dict[str, Any]:
            """Load project configuration from YAML file."""
            if not os.path.exists(self.config_path):
                raise NodeExecutionError(
                    f"Project configuration file not found: {self.config_path}"
                )

            try:
                with open(self.config_path, "r") as f:
                    config = yaml.safe_load(f)
                    return config or {}
            except yaml.YAMLError as e:
                raise NodeExecutionError(f"Invalid YAML in project configuration: {e}")
            except Exception as e:
                raise NodeExecutionError(f"Failed to load project configuration: {e}")

        def get_database_config(
            self, connection_name: str
        ) -> Tuple[str, Dict[str, Any]]:
            """Get database configuration by connection name.

            Args:
                connection_name: Name of the database connection from project config

            Returns:
                Tuple of (connection_string, db_config)

            Raises:
                NodeExecutionError: If connection not found in configuration
            """
            databases = self.config.get("databases", {})

            if connection_name in databases:
                db_config = databases[connection_name].copy()
                connection_string = db_config.pop("url", None)

                if not connection_string:
                    raise NodeExecutionError(
                        f"No 'url' specified for database connection '{connection_name}'"
                    )

                # Handle environment variable substitution
                connection_string = self._substitute_env_vars(connection_string)

                return connection_string, db_config

            # Fall back to default configuration
            if "default" in databases:
                default_config = databases["default"].copy()
                connection_string = default_config.pop("url", None)

                if connection_string:
                    connection_string = self._substitute_env_vars(connection_string)
                    return connection_string, default_config

            # Ultimate fallback
            raise NodeExecutionError(
                f"Database connection '{connection_name}' not found in project configuration. "
                f"Available connections: {list(databases.keys())}"
            )

        def _substitute_env_vars(self, value: str) -> str:
            """Substitute environment variables in configuration values."""
            if (
                isinstance(value, str)
                and value.startswith("${")
                and value.endswith("}")
            ):
                env_var = value[2:-1]
                env_value = os.getenv(env_var)
                if env_value is None:
                    raise NodeExecutionError(
                        f"Environment variable '{env_var}' not found"
                    )
                return env_value
            return value

        def validate_config(self) -> None:
            """Validate the project configuration."""
            databases = self.config.get("databases", {})

            if not databases:
                raise NodeExecutionError(
                    "No databases configured in project configuration"
                )

            for name, config in databases.items():
                if not isinstance(config, dict):
                    raise NodeExecutionError(
                        f"Database '{name}' configuration must be a dictionary"
                    )

                if "url" not in config and name != "default":
                    raise NodeExecutionError(
                        f"Database '{name}' missing required 'url' field"
                    )

    """Executes SQL queries against relational databases with shared connection pools.

    This node provides a unified interface for interacting with various RDBMS
    systems including PostgreSQL, MySQL, SQLite, and others. It handles
    connection management, query execution, and result formatting using
    shared connection pools for efficient resource utilization.

    Design Features:
    1. Shared connection pools across all node instances
    2. Project-level database configuration
    3. Parameterized queries to prevent SQL injection
    4. Flexible result formats (dict, list, raw)
    5. Transaction support with commit/rollback
    6. Query timeout handling
    7. Connection pool monitoring and metrics

    Data Flow:
    - Input: Connection name (from project config), SQL query, parameters
    - Processing: Execute query using shared pools, format results
    - Output: Query results in specified format

    Common Usage Patterns:
    1. Data extraction for analytics
    2. ETL pipeline source/sink
    3. Database migrations
    4. Report generation
    5. Data validation queries

    Example:
        >>> # Initialize with project configuration
        >>> SQLDatabaseNode.initialize('kailash_project.yaml')
        >>>
        >>> # Create node with database connection configuration
        >>> sql_node = SQLDatabaseNode(connection='customer_db')
        >>>
        >>> # Execute multiple queries with the same node
        >>> result1 = sql_node.run(
        ...     query='SELECT * FROM customers WHERE active = ?',
        ...     parameters=[True]
        ... )
        >>> result2 = sql_node.run(
        ...     query='SELECT COUNT(*) as total FROM orders'
        ... )
        >>> # result1['data'] = [
        >>> #     {'id': 1, 'name': 'John', 'active': True},
        >>> #     {'id': 2, 'name': 'Jane', 'active': True}
        >>> # ]
    """

    # Class-level shared resources for connection pooling
    _shared_pools: Dict[Tuple[str, frozenset], Any] = {}
    _pool_metrics: Dict[Tuple[str, frozenset], Dict[str, Any]] = {}
    _pool_lock = threading.Lock()
    _config_manager: Optional["SQLDatabaseNode._DatabaseConfigManager"] = None

    # NOTE: This method is deprecated in favor of direct configuration in constructor
    @classmethod
    def initialize(cls, project_config_path: str) -> None:
        """Initialize shared resources with project configuration.

        DEPRECATED: Use direct configuration in constructor instead.

        Args:
            project_config_path: Path to the project configuration YAML file
        """
        with cls._pool_lock:
            cls._config_manager = cls._DatabaseConfigManager(project_config_path)
            cls._config_manager.validate_config()

    def __init__(
        self,
        connection_string: str = None,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        echo: bool = False,
        connect_args: dict = None,
        **kwargs,
    ):
        """Initialize SQLDatabaseNode with direct database connection configuration.

        Args:
            connection_string: Database connection URL (e.g., "sqlite:///path/to/db.db")
            pool_size: Number of connections in the pool (default: 5)
            max_overflow: Maximum overflow connections (default: 10)
            pool_timeout: Timeout in seconds to get connection from pool (default: 30)
            pool_recycle: Time in seconds to recycle connections (default: 3600)
            pool_pre_ping: Test connections before use (default: True)
            echo: Enable SQLAlchemy query logging (default: False)
            connect_args: Additional database-specific connection arguments
            **kwargs: Additional node configuration parameters
        """
        if not connection_string:
            raise NodeExecutionError("connection_string parameter is required")

        # Store connection configuration
        self.connection_string = connection_string
        self.db_config = {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": pool_pre_ping,
            "echo": echo,
        }

        if connect_args:
            self.db_config["connect_args"] = connect_args

        # Add connection_string to kwargs for base class validation
        kwargs["connection_string"] = connection_string

        # Call parent constructor
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for SQL execution.

        Configuration parameters (provided to constructor):
        1. connection_string: Database connection URL
        2. pool_size, max_overflow, etc.: Connection pool configuration

        Runtime parameters (passed to run() method):
        3. query: SQL query to execute
        4. parameters: Query parameters for safety
        5. result_format: Output format

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "connection_string": NodeParameter(
                name="connection_string",
                type=str,
                required=True,
                description="Database connection URL (e.g., 'sqlite:///path/to/db.db')",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,  # Not required in constructor, provided at runtime
                description="SQL query to execute (use ? for SQLite, $1 for PostgreSQL, %s for MySQL)",
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
        }

    @staticmethod
    def _make_hashable(obj):
        """Convert nested dictionaries/lists to hashable tuples for cache keys."""
        if isinstance(obj, dict):
            return tuple(
                sorted((k, SQLDatabaseNode._make_hashable(v)) for k, v in obj.items())
            )
        elif isinstance(obj, list):
            return tuple(SQLDatabaseNode._make_hashable(item) for item in obj)
        else:
            return obj

    def _get_shared_engine(self):
        """Get or create shared engine for database connection."""
        cache_key = (self.connection_string, self._make_hashable(self.db_config))

        with self._pool_lock:
            if cache_key not in self._shared_pools:
                self.logger.info(
                    f"Creating shared pool for {SQLDatabaseNode._mask_connection_password(self.connection_string)}"
                )

                # Apply configuration with sensible defaults
                pool_config = {
                    "poolclass": QueuePool,
                    **self.db_config,  # Use the stored db_config
                }

                engine = create_engine(self.connection_string, **pool_config)

                self._shared_pools[cache_key] = engine
                self._pool_metrics[cache_key] = {
                    "created_at": datetime.now(),
                    "total_queries": 0,
                }

            return self._shared_pools[cache_key]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute SQL query using shared connection pool.

        Args:
            **kwargs: Validated parameters including:
                - query: SQL statement
                - parameters: Query parameters (optional)
                - result_format: Output format (optional)

        Returns:
            Dictionary containing:
            - data: Query results in specified format
            - row_count: Number of rows affected/returned
            - columns: List of column names
            - execution_time: Query execution duration

        Raises:
            NodeExecutionError: Connection or query errors
        """
        # Extract validated inputs
        query = kwargs.get("query")
        parameters = kwargs.get("parameters", [])
        result_format = kwargs.get("result_format", "dict")

        # Validate required parameters
        if not query:
            raise NodeExecutionError("query parameter is required")

        # Validate query safety
        self._validate_query_safety(query)

        # Mask password in connection string for logging
        masked_connection = SQLDatabaseNode._mask_connection_password(
            self.connection_string
        )
        self.logger.info(f"Executing SQL query on {masked_connection}")
        self.logger.debug(f"Query: {query}")
        self.logger.debug(f"Parameters: {parameters}")

        # Get shared engine
        engine = self._get_shared_engine()

        # Track metrics - use same cache key generation logic
        cache_key = (self.connection_string, self._make_hashable(self.db_config))
        with self._pool_lock:
            self._pool_metrics[cache_key]["total_queries"] += 1

        # Execute query with shared connection pool
        start_time = time.time()

        try:
            with engine.connect() as conn:
                with conn.begin() as trans:
                    try:
                        # Handle parameterized queries
                        # SQLAlchemy 2.0 with text() requires named parameters for positional values
                        if parameters:
                            if isinstance(parameters, dict):
                                # Named parameters - use as-is
                                result = conn.execute(text(query), parameters)
                            elif isinstance(parameters, (list, tuple)):
                                # Convert positional parameters to named parameters
                                named_query, param_dict = (
                                    self._convert_to_named_parameters(query, parameters)
                                )
                                result = conn.execute(text(named_query), param_dict)
                            else:
                                # Single parameter
                                named_query, param_dict = (
                                    self._convert_to_named_parameters(
                                        query, [parameters]
                                    )
                                )
                                result = conn.execute(text(named_query), param_dict)
                        else:
                            result = conn.execute(text(query))

                        execution_time = time.time() - start_time

                        # Process results
                        if result.returns_rows:
                            rows = result.fetchall()
                            columns = list(result.keys()) if result.keys() else []
                            row_count = len(rows)
                            formatted_data = self._format_results(
                                rows, columns, result_format
                            )
                        else:
                            formatted_data = []
                            columns = []
                            row_count = result.rowcount if result.rowcount != -1 else 0

                        trans.commit()

                    except Exception:
                        trans.rollback()
                        raise

        except SQLAlchemyError as e:
            execution_time = time.time() - start_time
            sanitized_error = self._sanitize_error_message(str(e))
            error_msg = f"Database error: {sanitized_error}"
            self.logger.error(error_msg)
            raise NodeExecutionError(error_msg) from e

        except Exception as e:
            execution_time = time.time() - start_time
            sanitized_error = self._sanitize_error_message(str(e))
            error_msg = f"Unexpected error during query execution: {sanitized_error}"
            self.logger.error(error_msg)
            raise NodeExecutionError(error_msg) from e

        self.logger.info(
            f"Query executed successfully in {execution_time:.3f}s, {row_count} rows affected/returned"
        )

        return {
            "data": formatted_data,
            "row_count": row_count,
            "columns": columns,
            "execution_time": execution_time,
        }

    @classmethod
    def get_pool_status(cls) -> Dict[str, Any]:
        """Get status of all shared connection pools."""
        with cls._pool_lock:
            status = {}
            for key, engine in cls._shared_pools.items():
                pool = engine.pool
                connection_string = key[0]
                masked_string = SQLDatabaseNode._mask_connection_password(
                    connection_string
                )

                status[masked_string] = {
                    "pool_size": pool.size(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                    "total_capacity": pool.size() + pool.overflow(),
                    "utilization": (
                        pool.checkedout() / (pool.size() + pool.overflow())
                        if (pool.size() + pool.overflow()) > 0
                        else 0
                    ),
                    "metrics": cls._pool_metrics.get(key, {}),
                }

            return status

    @classmethod
    def cleanup_pools(cls):
        """Clean up all shared connection pools."""
        with cls._pool_lock:
            for engine in cls._shared_pools.values():
                engine.dispose()
            cls._shared_pools.clear()
            cls._pool_metrics.clear()

    @staticmethod
    def _mask_connection_password(connection_string: str) -> str:
        """Mask password in connection string for secure logging."""
        import re

        pattern = r"(://[^:]+:)[^@]+(@)"
        return re.sub(pattern, r"\1***\2", connection_string)

    def _validate_query_safety(self, query: str) -> None:
        """Validate query for potential security issues.

        Args:
            query: SQL query to validate

        Raises:
            NodeExecutionError: If query contains dangerous operations
        """
        if not query:
            return

        # Convert to uppercase for case-insensitive checks
        query_upper = query.upper().strip()

        # Check for dangerous SQL operations in dynamic queries
        dangerous_keywords = [
            "DROP",
            "DELETE",
            "TRUNCATE",
            "ALTER",
            "CREATE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
            "SHUTDOWN",
            "BACKUP",
            "RESTORE",
        ]

        # Only flag if these appear as standalone words (not within other words)
        import re

        for keyword in dangerous_keywords:
            # Use word boundaries to match standalone keywords
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, query_upper):
                self.logger.warning(
                    f"Query contains potentially dangerous keyword: {keyword}"
                )
                # Note: In production, you might want to block these entirely
                # raise NodeExecutionError(f"Query contains forbidden keyword: {keyword}")

    def _sanitize_identifier(self, identifier: str) -> str:
        """Sanitize table/column names for dynamic SQL.

        Args:
            identifier: Table or column name

        Returns:
            Sanitized identifier

        Raises:
            NodeExecutionError: If identifier contains invalid characters
        """
        if not identifier:
            return identifier

        import re

        # Allow only alphanumeric characters, underscores, and dots
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*$", identifier):
            raise NodeExecutionError(
                f"Invalid identifier '{identifier}': must contain only letters, numbers, underscores, and dots"
            )

        # Check for SQL injection attempts
        dangerous_patterns = [
            r'[\'"`;]',  # Quotes and semicolons
            r"--",  # SQL comments
            r"/\*",  # Block comment start
            r"\*/",  # Block comment end
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, identifier):
                raise NodeExecutionError(
                    f"Invalid identifier '{identifier}': contains potentially dangerous characters"
                )

        return identifier

    def _validate_connection_string(self, connection_string: str) -> None:
        """Validate connection string format and security.

        Args:
            connection_string: Database connection URL

        Raises:
            NodeExecutionError: If connection string is invalid or insecure
        """
        if not connection_string:
            raise NodeExecutionError("Connection string cannot be empty")

        # Check for supported database types (including driver specifications)
        supported_protocols = ["sqlite", "postgresql", "mysql"]
        protocol = (
            connection_string.split("://")[0].lower()
            if "://" in connection_string
            else ""
        )

        # Handle SQLAlchemy driver specifications (e.g., mysql+pymysql, postgresql+psycopg2)
        base_protocol = protocol.split("+")[0] if "+" in protocol else protocol

        if base_protocol not in supported_protocols:
            raise NodeExecutionError(
                f"Unsupported database protocol '{protocol}'. "
                f"Supported protocols: {', '.join(supported_protocols)}"
            )

        # Check for SQL injection in connection string
        if any(char in connection_string for char in ["'", '"', ";", "--"]):
            raise NodeExecutionError(
                "Connection string contains potentially dangerous characters"
            )

    def _implement_connection_retry(
        self,
        connection_string: str,
        timeout: int,
        db_config: dict = None,
        max_retries: int = 3,
    ):
        """Implement connection retry logic with exponential backoff.

        Args:
            connection_string: Database connection URL
            timeout: Connection timeout
            db_config: Database configuration dictionary
            max_retries: Maximum number of retry attempts

        Returns:
            SQLAlchemy engine

        Raises:
            NodeExecutionError: If all connection attempts fail
        """
        import time

        # Handle None db_config
        if db_config is None:
            db_config = {}

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                # Build SQLAlchemy engine configuration with defaults and overrides
                engine_config = {
                    "poolclass": QueuePool,
                    "pool_size": db_config.get("pool_size", 5),
                    "max_overflow": db_config.get("max_overflow", 10),
                    "pool_timeout": db_config.get("pool_timeout", timeout),
                    "pool_recycle": db_config.get("pool_recycle", 3600),
                    "echo": db_config.get("echo", False),
                }

                # Add isolation level if specified
                if "isolation_level" in db_config:
                    engine_config["isolation_level"] = db_config["isolation_level"]

                # Add any additional SQLAlchemy engine parameters from db_config
                for key, value in db_config.items():
                    if key not in [
                        "pool_size",
                        "max_overflow",
                        "pool_timeout",
                        "pool_recycle",
                        "echo",
                        "isolation_level",
                    ]:
                        engine_config[key] = value

                engine = create_engine(connection_string, **engine_config)

                # Test the connection
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                if attempt > 0:
                    self.logger.info(f"Connection established after {attempt} retries")

                return engine

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    # Exponential backoff: 1s, 2s, 4s
                    backoff_time = 2**attempt
                    self.logger.warning(
                        f"Connection attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {backoff_time}s..."
                    )
                    time.sleep(backoff_time)
                else:
                    self.logger.error(
                        f"All connection attempts failed. Last error: {e}"
                    )

        raise NodeExecutionError(
            f"Failed to establish database connection after {max_retries} retries: {last_error}"
        )

    def _sanitize_error_message(self, error_message: str) -> str:
        """Sanitize error messages to prevent sensitive data exposure.

        Args:
            error_message: Original error message

        Returns:
            Sanitized error message
        """
        if not error_message:
            return error_message

        import re

        # Remove potential passwords from error messages
        patterns_to_mask = [
            # Connection string passwords
            (r"://[^:]+:[^@]+@", "://***:***@"),
            # SQL query content (in some error messages)
            (r"'[^']*'", "'***'"),
            # Quoted strings that might contain sensitive data
            (r'"[^"]*"', '"***"'),
        ]

        sanitized = error_message
        for pattern, replacement in patterns_to_mask:
            sanitized = re.sub(pattern, replacement, sanitized)

        return sanitized

    def _convert_to_named_parameters(self, query: str, parameters: List) -> tuple:
        """Convert positional parameters to named parameters for SQLAlchemy 2.0.

        Args:
            query: SQL query with positional placeholders (?, $1, %s)
            parameters: List of parameter values

        Returns:
            Tuple of (modified_query, parameter_dict)
        """
        import re

        # Create parameter dictionary
        param_dict = {}
        for i, value in enumerate(parameters):
            param_dict[f"p{i}"] = value

        # Replace different placeholder formats with named parameters
        modified_query = query

        # Handle SQLite-style ? placeholders
        placeholder_count = 0

        def replace_question_mark(match):
            nonlocal placeholder_count
            replacement = f":p{placeholder_count}"
            placeholder_count += 1
            return replacement

        modified_query = re.sub(r"\?", replace_question_mark, modified_query)

        # Handle PostgreSQL-style $1, $2, etc. placeholders
        def replace_postgres_placeholder(match):
            index = int(match.group(1)) - 1  # PostgreSQL uses 1-based indexing
            return f":p{index}"

        modified_query = re.sub(
            r"\$(\d+)", replace_postgres_placeholder, modified_query
        )

        # Handle MySQL-style %s placeholders
        placeholder_count = 0

        def replace_mysql_placeholder(match):
            nonlocal placeholder_count
            replacement = f":p{placeholder_count}"
            placeholder_count += 1
            return replacement

        modified_query = re.sub(r"%s", replace_mysql_placeholder, modified_query)

        return modified_query, param_dict

    def _format_results(
        self, rows: List, columns: List[str], result_format: str
    ) -> List[Any]:
        """Format query results according to specified format.

        Args:
            rows: Raw database rows
            columns: Column names
            result_format: Desired output format

        Returns:
            Formatted results
        """
        if result_format == "dict":
            # List of dictionaries with column names as keys
            # SQLAlchemy rows can be converted to dict using _asdict() or dict()
            return [dict(row._mapping) for row in rows]

        elif result_format == "list":
            # List of lists (raw rows)
            return [list(row) for row in rows]

        elif result_format == "raw":
            # Raw SQLAlchemy row objects (converted to list for JSON serialization)
            return [list(row) for row in rows]

        else:
            # Default to dict format
            self.logger.warning(
                f"Unknown result_format '{result_format}', defaulting to 'dict'"
            )
            return [dict(zip(columns, row)) for row in rows]
