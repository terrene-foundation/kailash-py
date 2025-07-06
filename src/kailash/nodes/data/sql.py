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
6. Enterprise-grade concurrency control with optimistic locking
7. Advanced retry mechanisms and conflict resolution
"""

import base64
import os
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError

# Import optimistic locking for enterprise concurrency control
try:
    from kailash.nodes.data.optimistic_locking import (
        ConflictResolution,
        OptimisticLockingNode,
    )

    OPTIMISTIC_LOCKING_AVAILABLE = True
except ImportError:
    OPTIMISTIC_LOCKING_AVAILABLE = False


@register_node()
class SQLDatabaseNode(Node):

    class _DatabaseConfigManager:
        """Internal manager for database configurations from project settings."""

        def __init__(self, project_config_path: str):
            """Initialize with project configuration file path."""
            self.config_path = project_config_path
            self.config = self._load_project_config()

        def _load_project_config(self) -> dict[str, Any]:
            """Load project configuration from YAML file."""
            if not os.path.exists(self.config_path):
                raise NodeExecutionError(
                    f"Project configuration file not found: {self.config_path}"
                )

            try:
                with open(self.config_path) as f:
                    config = yaml.safe_load(f)
                    return config or {}
            except yaml.YAMLError as e:
                raise NodeExecutionError(f"Invalid YAML in project configuration: {e}")
            except Exception as e:
                raise NodeExecutionError(f"Failed to load project configuration: {e}")

        def get_database_config(
            self, connection_name: str
        ) -> tuple[str, dict[str, Any]]:
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
        >>> result1 = sql_node.execute(
        ...     query='SELECT * FROM customers WHERE active = ?',
        ...     parameters=[True]
        ... )
        >>> result2 = sql_node.execute(
        ...     query='SELECT COUNT(*) as total FROM orders'
        ... )
        >>> # result1['data'] = [
        >>> #     {'id': 1, 'name': 'John', 'active': True},
        >>> #     {'id': 2, 'name': 'Jane', 'active': True}
        >>> # ]
    """

    # Class-level shared resources for connection pooling
    _shared_pools: dict[tuple[str, frozenset], Any] = {}
    _pool_metrics: dict[tuple[str, frozenset], dict[str, Any]] = {}
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

        # Extract access control manager before passing to parent
        self.access_control_manager = kwargs.pop("access_control_manager", None)

        # Call parent constructor
        super().__init__(**kwargs)

    def get_parameters(self) -> dict[str, NodeParameter]:
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
                type=Any,  # Allow both list and dict for parameters
                required=False,
                default=None,
                description="Query parameters for parameterized queries (list for positional, dict for named)",
            ),
            "result_format": NodeParameter(
                name="result_format",
                type=str,
                required=False,
                default="dict",
                description="Result format: 'dict', 'list', or 'raw'",
            ),
            "user_context": NodeParameter(
                name="user_context",
                type=Any,
                required=False,
                description="User context for access control",
            ),
            # Optimistic Locking Parameters
            "optimistic_locking": NodeParameter(
                name="optimistic_locking",
                type=bool,
                required=False,
                default=False,
                description="Enable optimistic locking for updates",
            ),
            "version_field": NodeParameter(
                name="version_field",
                type=str,
                required=False,
                default="version",
                description="Name of the version field for optimistic locking",
            ),
            "expected_version": NodeParameter(
                name="expected_version",
                type=int,
                required=False,
                description="Expected version for optimistic locking (required for updates with locking)",
            ),
            "conflict_resolution": NodeParameter(
                name="conflict_resolution",
                type=str,
                required=False,
                default="retry",
                description="Conflict resolution strategy (fail_fast, retry, merge, last_writer_wins)",
            ),
            "max_retries": NodeParameter(
                name="max_retries",
                type=int,
                required=False,
                default=3,
                description="Maximum retry attempts for optimistic locking conflicts",
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

    def run(self, **kwargs) -> dict[str, Any]:
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
        parameters = kwargs.get("parameters")
        result_format = kwargs.get("result_format", "dict")
        user_context = kwargs.get("user_context")

        # Validate required parameters
        if not query:
            raise NodeExecutionError("query parameter is required")

        # Check access control if enabled
        if self.access_control_manager and user_context:
            from kailash.access_control import NodePermission

            decision = self.access_control_manager.check_node_access(
                user_context, self.metadata.name, NodePermission.EXECUTE
            )
            if not decision.allowed:
                raise NodeExecutionError(f"Access denied: {decision.reason}")

        # Validate query safety
        self._validate_query_safety(query)

        # Check if optimistic locking should be used
        if self._should_use_optimistic_locking(kwargs):
            return self._execute_with_optimistic_locking(kwargs)

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

        # Apply data masking if access control is enabled
        if self.access_control_manager and user_context and formatted_data:
            if result_format == "dict" and isinstance(formatted_data, list):
                masked_data = []
                for row in formatted_data:
                    if isinstance(row, dict):
                        masked_row = self.access_control_manager.apply_data_masking(
                            user_context, self.metadata.name, row
                        )
                        masked_data.append(masked_row)
                    else:
                        masked_data.append(row)
                formatted_data = masked_data

        return {
            "data": formatted_data,
            "row_count": row_count,
            "columns": columns,
            "execution_time": execution_time,
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """
        Async wrapper for the run method to maintain backward compatibility.

        This method provides an async interface while maintaining the same
        functionality as the synchronous run method. The underlying SQLAlchemy
        operations are still synchronous but wrapped for async compatibility.

        Args:
            **kwargs: Same parameters as run()

        Returns:
            Same return format as run()

        Note:
            This is a compatibility method. The actual database operations
            are still synchronous underneath.
        """
        import asyncio

        # Run the synchronous method in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.execute(**kwargs))

    @classmethod
    def get_pool_status(cls) -> dict[str, Any]:
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

        # Remove potential passwords from error messages, but be more selective
        patterns_to_mask = [
            # Connection string passwords
            (r"://[^:]+:[^@]+@", "://***:***@"),
            # Password fields in SQL (case insensitive)
            (r"password\s*=\s*['\"][^'\"]*['\"]", "password='***'", re.IGNORECASE),
            # API keys and tokens in SQL
            (
                r"(api_key|token|secret)\s*=\s*['\"][^'\"]*['\"]",
                r"\1='***'",
                re.IGNORECASE,
            ),
        ]

        sanitized = error_message
        for pattern_info in patterns_to_mask:
            if len(pattern_info) == 3:
                pattern, replacement, flags = pattern_info
                sanitized = re.sub(pattern, replacement, sanitized, flags=flags)
            else:
                pattern, replacement = pattern_info
                sanitized = re.sub(pattern, replacement, sanitized)

        return sanitized

    def _convert_to_named_parameters(self, query: str, parameters: list) -> tuple:
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

    def _serialize_value(self, value: Any) -> Any:
        """Convert database-specific types to JSON-serializable types.

        Args:
            value: Value to serialize

        Returns:
            JSON-serializable value
        """
        if value is None:
            return None
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif isinstance(value, timedelta):
            return value.total_seconds()
        elif isinstance(value, UUID):
            return str(value)
        elif isinstance(value, bytes):
            return base64.b64encode(value).decode("utf-8")
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return value

    def _format_results(
        self, rows: list, columns: list[str], result_format: str
    ) -> list[Any]:
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
            result = []
            for row in rows:
                row_dict = dict(row._mapping)
                # Serialize values for JSON compatibility
                serialized_dict = {
                    k: self._serialize_value(v) for k, v in row_dict.items()
                }
                result.append(serialized_dict)
            return result

        elif result_format == "list":
            # List of lists (raw rows)
            result = []
            for row in rows:
                serialized_row = [self._serialize_value(value) for value in row]
                result.append(serialized_row)
            return result

        elif result_format == "raw":
            # Raw SQLAlchemy row objects (converted to list for JSON serialization)
            result = []
            for row in rows:
                serialized_row = [self._serialize_value(value) for value in row]
                result.append(serialized_row)
            return result

        else:
            # Default to dict format
            self.logger.warning(
                f"Unknown result_format '{result_format}', defaulting to 'dict'"
            )
            result = []
            for row in rows:
                row_dict = dict(zip(columns, row, strict=False))
                serialized_dict = {
                    k: self._serialize_value(v) for k, v in row_dict.items()
                }
                result.append(serialized_dict)
            return result

    def _should_use_optimistic_locking(self, kwargs: dict) -> bool:
        """Check if optimistic locking should be used for this operation."""
        return (
            OPTIMISTIC_LOCKING_AVAILABLE
            and kwargs.get("optimistic_locking", False)
            and self._is_update_query(kwargs.get("query", ""))
        )

    def _is_update_query(self, query: str) -> bool:
        """Check if the query is an UPDATE statement."""
        query_upper = query.strip().upper()
        return query_upper.startswith("UPDATE")

    def _execute_with_optimistic_locking(self, **kwargs) -> dict[str, Any]:
        """Execute query with optimistic locking support."""
        if not OPTIMISTIC_LOCKING_AVAILABLE:
            raise NodeExecutionError(
                "Optimistic locking requested but OptimisticLockingNode not available"
            )

        query = kwargs.get("query", "")
        expected_version = kwargs.get("expected_version")

        if expected_version is None:
            raise NodeExecutionError(
                "expected_version parameter is required when optimistic_locking=True"
            )

        # Extract table name and record ID from UPDATE query
        table_info = self._extract_update_info(query, kwargs.get("parameters"))

        if not table_info:
            raise NodeExecutionError(
                "Could not extract table and record information from UPDATE query for optimistic locking"
            )

        # Create optimistic locking node
        locking_node = OptimisticLockingNode(
            version_field=kwargs.get("version_field", "version"),
            max_retries=kwargs.get("max_retries", 3),
            default_conflict_resolution=kwargs.get("conflict_resolution", "retry"),
        )

        # Get database connection for the locking node
        engine = self._get_shared_engine()

        try:
            with engine.connect() as conn:
                with conn.begin() as trans:
                    # Use optimistic locking node to handle the update
                    locking_result = locking_node.run(
                        action="update_with_version",
                        connection=conn,
                        table_name=table_info["table_name"],
                        record_id=table_info["record_id"],
                        update_data=table_info["update_data"],
                        expected_version=expected_version,
                        conflict_resolution=kwargs.get("conflict_resolution", "retry"),
                        version_field=kwargs.get("version_field", "version"),
                        id_field=table_info.get("id_field", "id"),
                    )

                    if not locking_result.get("success", False):
                        # Handle optimistic locking conflicts
                        status = locking_result.get("status", "unknown_error")
                        if status == "version_conflict":
                            raise NodeExecutionError(
                                f"Version conflict: expected version {expected_version}, "
                                f"current version {locking_result.get('current_version', 'unknown')}"
                            )
                        elif status == "retry_exhausted":
                            raise NodeExecutionError(
                                f"Maximum retries exhausted for optimistic locking. "
                                f"Conflict resolution: {kwargs.get('conflict_resolution', 'retry')}"
                            )
                        else:
                            raise NodeExecutionError(
                                f"Optimistic locking failed: {locking_result.get('error', 'Unknown error')}"
                            )

                    # Return enhanced result with locking information
                    return {
                        "data": [],  # UPDATE queries typically don't return data
                        "row_count": locking_result.get("rows_affected", 0),
                        "columns": [],
                        "execution_time": locking_result.get("execution_time", 0),
                        "optimistic_locking": {
                            "used": True,
                            "old_version": expected_version,
                            "new_version": locking_result.get("new_version"),
                            "retry_count": locking_result.get("retry_count", 0),
                            "conflict_resolution": kwargs.get(
                                "conflict_resolution", "retry"
                            ),
                            "status": locking_result.get("status", "success"),
                        },
                    }

        except Exception as e:
            if "Version conflict" in str(e) or "retry exhausted" in str(e):
                # Re-raise optimistic locking specific errors
                raise
            else:
                # Wrap other database errors
                raise NodeExecutionError(
                    f"Database error during optimistic locking: {str(e)}"
                )

    def _extract_update_info(self, query: str, parameters: Any) -> Optional[dict]:
        """Extract table name, record ID, and update data from UPDATE query.

        This is a simplified parser for common UPDATE patterns.
        For production use, consider using a proper SQL parser.
        """
        import re

        # Simple regex to extract UPDATE table_name SET ... WHERE id = ?
        # This is a basic implementation - for production, use a proper SQL parser
        update_pattern = r"UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+(\w+)\s*=\s*[?$:]"

        match = re.search(update_pattern, query.upper(), re.IGNORECASE | re.DOTALL)
        if not match:
            return None

        table_name = match.group(1).lower()
        set_clause = match.group(2)
        id_field = match.group(3).lower()

        # Extract update data from SET clause
        # This is simplified - assumes basic "field = ?" patterns
        update_data = {}
        set_parts = [part.strip() for part in set_clause.split(",")]

        param_index = 0
        for part in set_parts:
            if "=" in part:
                field_name = part.split("=")[0].strip()
                # Skip version field as it's handled by optimistic locking
                if field_name.lower() != "version":
                    if isinstance(parameters, list) and param_index < len(parameters):
                        update_data[field_name] = parameters[param_index]
                        param_index += 1
                    elif isinstance(parameters, dict):
                        # For named parameters, this gets more complex
                        # For now, we'll skip this case
                        pass

        # Extract record ID from parameters
        # Assume the WHERE clause parameter is the last one for positional params
        record_id = None
        if isinstance(parameters, list) and parameters:
            record_id = parameters[-1]  # Assume last parameter is the ID
        elif isinstance(parameters, dict):
            # Look for common ID field names in parameters
            for id_candidate in ["id", id_field, "record_id"]:
                if id_candidate in parameters:
                    record_id = parameters[id_candidate]
                    break

        if record_id is None:
            return None

        return {
            "table_name": table_name,
            "record_id": record_id,
            "update_data": update_data,
            "id_field": id_field,
        }

    def _execute_with_optimistic_locking(self, kwargs: dict) -> dict:
        """Execute query using optimistic locking for enhanced concurrency control."""
        if not OPTIMISTIC_LOCKING_AVAILABLE:
            raise NodeExecutionError(
                "OptimisticLockingNode not available. Cannot use optimistic locking."
            )

        query = kwargs.get("query")
        parameters = kwargs.get("parameters")

        # Extract update information from the query
        update_info = self._extract_update_info(query, parameters)
        if not update_info:
            raise NodeExecutionError(
                "Could not extract update information for optimistic locking. "
                "Query might be too complex or not an UPDATE statement."
            )

        # Get database connection
        engine = self._get_shared_engine()

        try:
            with engine.connect() as conn:
                # Create optimistic locking node instance
                locking_node = OptimisticLockingNode(
                    version_field=kwargs.get("version_field", "version"),
                    max_retries=kwargs.get("max_retries", 3),
                    default_conflict_resolution=ConflictResolution(
                        kwargs.get("conflict_resolution", "retry")
                    ),
                )

                # First, read the current record with version
                read_kwargs = {
                    "action": "read_with_version",
                    "connection": conn,
                    "table_name": update_info["table_name"],
                    "record_id": update_info["record_id"],
                    "version_field": kwargs.get("version_field", "version"),
                    "id_field": update_info["id_field"],
                }

                # Execute synchronously by calling async_run directly
                import asyncio

                read_result = asyncio.run(locking_node.async_run(**read_kwargs))

                if not read_result.get("success"):
                    raise NodeExecutionError(
                        f"Failed to read record for optimistic locking: {read_result.get('error')}"
                    )

                current_version = read_result["version"]

                # Now perform the update with version check
                update_kwargs = {
                    "action": "update_with_version",
                    "connection": conn,
                    "table_name": update_info["table_name"],
                    "record_id": update_info["record_id"],
                    "update_data": update_info["update_data"],
                    "expected_version": current_version,
                    "conflict_resolution": kwargs.get("conflict_resolution", "retry"),
                    "version_field": kwargs.get("version_field", "version"),
                    "id_field": update_info["id_field"],
                }

                # Execute the update with optimistic locking
                update_result = asyncio.run(locking_node.async_run(**update_kwargs))

                if not update_result.get("success"):
                    raise NodeExecutionError(
                        f"Optimistic locking update failed: {update_result.get('error')}"
                    )

                # Return result in SQLDatabaseNode format
                return {
                    "data": [],  # UPDATE queries don't return data
                    "row_count": update_result.get("rows_affected", 1),
                    "columns": [],
                    "execution_time": update_result.get("execution_time", 0.0),
                    "optimistic_locking_used": True,
                    "version_before": current_version,
                    "version_after": update_result.get("new_version"),
                    "retry_count": update_result.get("retry_count", 0),
                }

        except Exception as e:
            raise NodeExecutionError(f"Optimistic locking execution failed: {str(e)}")
