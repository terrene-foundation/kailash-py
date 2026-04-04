"""
Base Adapter Interface

Minimal interface for all DataFlow adapters (SQL, Document, Vector, Graph, Key-Value).
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """
    Minimal base interface for all DataFlow adapters.

    This is the foundation for specialized adapter types:
    - DatabaseAdapter (SQL databases: PostgreSQL, MySQL, SQLite)
    - DocumentAdapter (Document databases: MongoDB, CouchDB)
    - VectorAdapter (Vector databases: Qdrant, Milvus, Weaviate, pgvector)
    - GraphAdapter (Graph databases: Neo4j, ArangoDB)
    - KeyValueAdapter (Key-value stores: Redis, DynamoDB)

    All adapters must implement these minimal methods.
    """

    def __init__(self, connection_string: str, **kwargs):
        """
        Initialize adapter with connection string.

        Args:
            connection_string: Database connection string (format varies by database type)
            **kwargs: Additional configuration options
        """
        self.connection_string = connection_string
        self.is_connected = False
        self._config = kwargs

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """
        Get adapter type category.

        Returns:
            One of: 'sql', 'document', 'vector', 'graph', 'key-value'
        """
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """
        Get specific source type identifier.

        Returns:
            Specific source: 'postgresql', 'mysql', 'sqlite', 'mongodb',
            'neo4j', 'qdrant', 'milvus', 'redis', 'file', 'rest',
            'cache', etc.
        """
        pass

    @property
    def database_type(self) -> str:
        """Deprecated: use source_type instead."""
        import warnings

        warnings.warn(
            "database_type is deprecated, use source_type instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.source_type

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish database connection.

        This should create connection pool or establish persistent connection.
        Sets self.is_connected = True on success.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close database connection.

        This should close connection pool and release all resources.
        Sets self.is_connected = False.
        """
        pass

    async def health_check(self) -> Dict[str, Any]:
        """
        Check database connection health.

        Returns:
            Dict with health status:
            {
                "healthy": bool,
                "source_type": str,
                "connected": bool,
                "error": str (optional)
            }
        """
        try:
            if not self.is_connected:
                await self.connect()

            return {
                "healthy": True,
                "source_type": self.source_type,
                "adapter_type": self.adapter_type,
                "connected": self.is_connected,
            }
        except Exception as e:
            logger.error(f"Health check failed for {self.source_type}: {e}")
            return {
                "healthy": False,
                "source_type": self.source_type,
                "adapter_type": self.adapter_type,
                "connected": self.is_connected,
                "error": str(e),
            }

    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """
        Check if database supports a specific feature.

        Args:
            feature: Feature name (e.g., "transactions", "full_text_search",
                    "vector_search", "graph_traversal", "geospatial")

        Returns:
            True if feature is supported, False otherwise
        """
        pass

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get connection information (safe for logging, no passwords).

        Returns:
            Dict with safe connection details
        """
        return {
            "adapter_type": self.adapter_type,
            "source_type": self.source_type,
            "connected": self.is_connected,
        }

    def __repr__(self) -> str:
        """String representation of adapter."""
        return f"{self.__class__.__name__}(source_type='{self.source_type}', connected={self.is_connected})"
