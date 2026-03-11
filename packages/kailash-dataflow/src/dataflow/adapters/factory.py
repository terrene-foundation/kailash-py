"""
Database Adapter Factory

Factory for creating database adapters from connection strings.
"""

import logging
from typing import Any, Dict, Type

from .base import DatabaseAdapter
from .connection_parser import ConnectionParser
from .exceptions import UnsupportedDatabaseError
from .mongodb import MongoDBAdapter
from .mysql import MySQLAdapter
from .postgresql import PostgreSQLAdapter
from .sqlite import SQLiteAdapter
from .sqlite_enterprise import SQLiteEnterpriseAdapter

logger = logging.getLogger(__name__)


class AdapterFactory:
    """Factory for creating database adapters."""

    def __init__(self, **default_config):
        """
        Initialize adapter factory.

        Args:
            **default_config: Default configuration for all adapters
        """
        self.default_config = default_config
        self._adapters: Dict[str, Type[DatabaseAdapter]] = {
            "postgresql": PostgreSQLAdapter,
            "postgres": PostgreSQLAdapter,  # Alternative scheme
            "mysql": MySQLAdapter,
            "sqlite": SQLiteEnterpriseAdapter,  # Use enterprise SQLite by default
            "sqlite_basic": SQLiteAdapter,  # Keep basic version available
            "mongodb": MongoDBAdapter,  # MongoDB document database (v0.6.0+)
        }

    def register_adapter(
        self, scheme: str, adapter_class: Type[DatabaseAdapter]
    ) -> None:
        """
        Register a custom adapter.

        Args:
            scheme: URL scheme (e.g., 'postgresql', 'mysql')
            adapter_class: Adapter class to register
        """
        self._adapters[scheme] = adapter_class
        logger.info(f"Registered adapter for scheme: {scheme}")

    def detect_database_type(self, connection_string: str) -> str:
        """
        Detect database type from connection string.

        Args:
            connection_string: Database connection string

        Returns:
            Database type identifier

        Raises:
            UnsupportedDatabaseError: If database type is not supported
        """
        try:
            # Special case: SQLite in-memory database
            if connection_string == ":memory:":
                return "sqlite"

            # Special case: SQLite file paths (no scheme)
            if "://" not in connection_string and (
                connection_string.endswith(".db")
                or connection_string.endswith(".sqlite")
                or connection_string.endswith(".sqlite3")
                or connection_string.startswith("/")
                or connection_string.startswith("./")
                or connection_string.startswith("../")
            ):
                return "sqlite"

            components = ConnectionParser.parse_connection_string(connection_string)
            scheme = components.get("scheme", "").lower()

            # Handle scheme variants
            if scheme in ["postgres", "postgresql"] or scheme.startswith("postgresql+"):
                return "postgresql"
            elif scheme.startswith("mysql"):
                return "mysql"
            elif scheme.startswith("sqlite"):
                return "sqlite"
            elif scheme.startswith("mongodb"):
                return "mongodb"
            elif scheme in self._adapters:
                return scheme
            else:
                raise UnsupportedDatabaseError(f"Unsupported database type: {scheme}")
        except UnsupportedDatabaseError:
            # Re-raise UnsupportedDatabaseError unchanged
            raise
        except Exception as e:
            raise UnsupportedDatabaseError(f"Invalid connection string: {e}")

    def create_adapter(self, connection_string: str, **config) -> DatabaseAdapter:
        """
        Create database adapter from connection string.

        Args:
            connection_string: Database connection string
            **config: Adapter-specific configuration

        Returns:
            Database adapter instance

        Raises:
            UnsupportedDatabaseError: If database type is not supported
        """
        try:
            # Detect database type
            db_type = self.detect_database_type(connection_string)

            # Get adapter class
            adapter_class = self._adapters.get(db_type)
            if not adapter_class:
                raise UnsupportedDatabaseError(f"No adapter registered for: {db_type}")

            # Merge configuration
            final_config = {**self.default_config, **config}

            # Create adapter instance
            adapter = adapter_class(connection_string, **final_config)

            logger.info(f"Created {db_type} adapter for {connection_string}")
            return adapter

        except Exception as e:
            if isinstance(e, UnsupportedDatabaseError):
                raise
            raise UnsupportedDatabaseError(f"Failed to create adapter: {e}")

    def get_supported_databases(self) -> list[str]:
        """Get list of supported database types."""
        return list(set(self._adapters.keys()) - {"postgres"})  # Remove alias

    def get_adapter_class(self, db_type: str) -> Type[DatabaseAdapter]:
        """Get adapter class for database type."""
        return self._adapters.get(db_type)
