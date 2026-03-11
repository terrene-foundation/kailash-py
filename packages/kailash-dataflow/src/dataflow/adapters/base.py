"""
Base Database Adapter

Abstract base class for SQL database adapters (PostgreSQL, MySQL, SQLite).
Inherits from BaseAdapter to provide SQL-specific functionality.
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

from .base_adapter import BaseAdapter
from .connection_parser import ConnectionParser

logger = logging.getLogger(__name__)


class DatabaseAdapter(BaseAdapter):
    """
    Abstract base class for SQL database adapters.

    This extends BaseAdapter with SQL-specific methods for table operations,
    transactions, and schema management.

    Concrete implementations: PostgreSQLAdapter, MySQLAdapter, SQLiteAdapter
    """

    def __init__(self, connection_string: str, **kwargs):
        """
        Initialize SQL database adapter.

        Args:
            connection_string: Database connection string
            **kwargs: Additional configuration options
        """
        # Initialize BaseAdapter
        super().__init__(connection_string, **kwargs)

        # SQL-specific attributes
        self.connection_pool = None
        self._connection = None

        # Parse connection string using safe parser that handles special characters
        components = ConnectionParser.parse_connection_string(connection_string)
        self.scheme = components.get("scheme")
        self.host = components.get("host")
        self.port = components.get("port")
        self.database = components.get("database")
        self.username = components.get("username")
        self.password = components.get("password")
        self.query_params = components.get("query_params", {})

        # Common SQL configuration
        self.pool_size = kwargs.get("pool_size", 10)
        self.max_overflow = kwargs.get("max_overflow", 20)
        self.pool_timeout = kwargs.get("pool_timeout", 30)
        self.pool_recycle = kwargs.get("pool_recycle", 3600)
        self.enable_logging = kwargs.get("enable_logging", False)

    @property
    def adapter_type(self) -> str:
        """Get adapter type category."""
        return "sql"

    @property
    @abstractmethod
    def database_type(self) -> str:
        """Get specific database type identifier."""
        pass

    @property
    @abstractmethod
    def default_port(self) -> int:
        """Get default port for database type."""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Establish database connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close database connection."""
        pass

    @abstractmethod
    async def execute_query(self, query: str, params: List[Any] = None) -> List[Dict]:
        """Execute a query and return results."""
        pass

    @abstractmethod
    async def execute_transaction(
        self, queries: List[Tuple[str, List[Any]]]
    ) -> List[Any]:
        """Execute multiple queries in a transaction."""
        pass

    @abstractmethod
    async def get_table_schema(self, table_name: str) -> Dict[str, Dict]:
        """Get table schema information."""
        pass

    @abstractmethod
    async def create_table(self, table_name: str, schema: Dict[str, Dict]) -> None:
        """Create a table with given schema."""
        pass

    @abstractmethod
    async def drop_table(self, table_name: str) -> None:
        """Drop a table."""
        pass

    @abstractmethod
    def get_dialect(self) -> str:
        """Get SQL dialect identifier."""
        pass

    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """Check if database supports a specific feature."""
        pass

    def format_query(
        self, query: str, params: List[Any] = None
    ) -> Tuple[str, List[Any]]:
        """Format query for database-specific parameter style."""
        # Default implementation - override in subclasses
        return query, params or []

    def get_supported_isolation_levels(self) -> List[str]:
        """Get supported transaction isolation levels."""
        return ["READ_UNCOMMITTED", "READ_COMMITTED", "REPEATABLE_READ", "SERIALIZABLE"]

    @property
    def supports_transactions(self) -> bool:
        """Check if database supports transactions."""
        return True

    @property
    def supports_savepoints(self) -> bool:
        """Check if database supports savepoints."""
        return False
