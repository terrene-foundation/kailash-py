"""Asynchronous PostgreSQL vector database node for pgvector operations.

This module provides async nodes for working with PostgreSQL's pgvector extension,
enabling high-performance vector similarity search and embedding storage for AI/ML
workflows.

Design Philosophy:
1. Optimized for AI/ML workflows with embeddings
2. Support for all pgvector distance metrics
3. Efficient batch operations
4. Index management utilities
5. Hybrid search capabilities
6. Compatible with external repositories

Key Features:
- Vector similarity search with multiple distance metrics
- Batch embedding insertion for efficiency
- HNSW and IVFFlat index support
- Metadata filtering with vector search
- Query optimization helpers
- Connection pooling via AsyncConnectionManager
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import numpy as np

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.data.async_connection import PoolConfig, get_connection_manager
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

logger = logging.getLogger(__name__)


class DistanceMetric(Enum):
    """Supported distance metrics for vector similarity."""

    L2 = "l2"  # Euclidean distance
    COSINE = "cosine"  # Cosine distance
    IP = "ip"  # Inner product (dot product)


class IndexType(Enum):
    """Supported vector index types."""

    HNSW = "hnsw"  # Hierarchical Navigable Small World
    IVFFLAT = "ivfflat"  # Inverted File Flat
    NONE = "none"  # No index (exact search)


@dataclass
class VectorSearchResult:
    """Result from vector similarity search."""

    id: Any
    distance: float
    vector: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None


@register_node()
class AsyncPostgreSQLVectorNode(AsyncNode):
    """Asynchronous PostgreSQL pgvector node for vector operations.

    This node provides high-performance vector similarity search and embedding
    storage using PostgreSQL's pgvector extension. It supports multiple distance
    metrics, index types, and hybrid search with metadata filtering.

    Parameters:
        connection_string: PostgreSQL connection string
        host: Database host (if no connection_string)
        port: Database port (default: 5432)
        database: Database name
        user: Database user
        password: Database password
        table_name: Table to operate on
        vector_column: Column name for vectors (default: "embedding")
        dimension: Vector dimension (required for table creation)
        distance_metric: Distance metric (l2, cosine, ip)
        index_type: Index type (hnsw, ivfflat, none)
        operation: Operation to perform (search, insert, create_table, create_index)
        vector: Vector for search or insert
        vectors: Batch of vectors for bulk insert
        metadata: Metadata for insert operations
        metadata_filter: SQL WHERE clause for hybrid search
        limit: Number of results to return
        ef_search: HNSW ef parameter for search
        probes: IVFFlat probes parameter

    Example:
        >>> # Vector similarity search
        >>> node = AsyncPostgreSQLVectorNode(
        ...     name="vector_search",
        ...     connection_string="postgresql://localhost/vectordb",
        ...     table_name="documents",
        ...     operation="search",
        ...     vector=[0.1, 0.2, 0.3, ...],
        ...     distance_metric="cosine",
        ...     limit=10
        ... )
        >>> results = await node.async_run()
        >>> similar_docs = results["matches"]

        >>> # Batch insert embeddings
        >>> node = AsyncPostgreSQLVectorNode(
        ...     name="insert_embeddings",
        ...     connection_string="postgresql://localhost/vectordb",
        ...     table_name="documents",
        ...     operation="insert",
        ...     vectors=embeddings,  # List of vectors
        ...     metadata=[{"doc_id": 1}, {"doc_id": 2}, ...]
        ... )
    """

    def __init__(self, **config):
        self._connection_manager = None
        super().__init__(**config)
        self._connection_manager = get_connection_manager()

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        params = [
            # Connection parameters
            NodeParameter(
                name="connection_string",
                type=str,
                required=False,
                description="PostgreSQL connection string",
            ),
            NodeParameter(
                name="host", type=str, required=False, description="Database host"
            ),
            NodeParameter(
                name="port",
                type=int,
                required=False,
                default=5432,
                description="Database port",
            ),
            NodeParameter(
                name="database", type=str, required=False, description="Database name"
            ),
            NodeParameter(
                name="user", type=str, required=False, description="Database user"
            ),
            NodeParameter(
                name="password",
                type=str,
                required=False,
                description="Database password",
            ),
            # Table configuration
            NodeParameter(
                name="table_name",
                type=str,
                required=True,
                description="Table name for vector operations",
            ),
            NodeParameter(
                name="vector_column",
                type=str,
                required=False,
                default="embedding",
                description="Column name for vectors",
            ),
            NodeParameter(
                name="dimension",
                type=int,
                required=False,
                description="Vector dimension (required for table creation)",
            ),
            # Operation parameters
            NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation: search, insert, create_table, create_index",
            ),
            NodeParameter(
                name="distance_metric",
                type=str,
                required=False,
                default="l2",
                description="Distance metric: l2, cosine, ip",
            ),
            NodeParameter(
                name="index_type",
                type=str,
                required=False,
                default="hnsw",
                description="Index type: hnsw, ivfflat, none",
            ),
            # Search parameters
            NodeParameter(
                name="vector",
                type=list,
                required=False,
                description="Query vector for search or single insert",
            ),
            NodeParameter(
                name="limit",
                type=int,
                required=False,
                default=10,
                description="Number of results to return",
            ),
            NodeParameter(
                name="metadata_filter",
                type=str,
                required=False,
                description="SQL WHERE clause for metadata filtering",
            ),
            NodeParameter(
                name="ef_search",
                type=int,
                required=False,
                description="HNSW ef parameter for search",
            ),
            NodeParameter(
                name="probes",
                type=int,
                required=False,
                description="IVFFlat probes parameter",
            ),
            # Insert parameters
            NodeParameter(
                name="vectors",
                type=list,
                required=False,
                description="Batch of vectors for bulk insert",
            ),
            NodeParameter(
                name="metadata",
                type=Any,
                required=False,
                description="Metadata for insert (dict or list of dicts)",
            ),
            # Index parameters
            NodeParameter(
                name="m",
                type=int,
                required=False,
                default=16,
                description="HNSW M parameter",
            ),
            NodeParameter(
                name="ef_construction",
                type=int,
                required=False,
                default=64,
                description="HNSW ef_construction parameter",
            ),
            NodeParameter(
                name="lists",
                type=int,
                required=False,
                default=100,
                description="IVFFlat lists parameter",
            ),
            # Pool configuration
            NodeParameter(
                name="pool_size",
                type=int,
                required=False,
                default=10,
                description="Connection pool size",
            ),
            NodeParameter(
                name="tenant_id",
                type=str,
                required=False,
                default="default",
                description="Tenant ID for connection isolation",
            ),
        ]

        # Convert list to dict as required by base class
        return {param.name: param for param in params}

    def validate_config(self):
        """Validate node configuration."""
        super().validate_config()

        # Validate connection parameters
        if not self.config.get("connection_string"):
            if not all(
                [
                    self.config.get("host"),
                    self.config.get("database"),
                    self.config.get("user"),
                ]
            ):
                raise NodeValidationError(
                    "Either connection_string or host/database/user required"
                )

        # Validate operation
        operation = self.config.get("operation", "").lower()
        if operation not in ["search", "insert", "create_table", "create_index"]:
            raise NodeValidationError(
                f"Invalid operation: {operation}. "
                "Must be one of: search, insert, create_table, create_index"
            )

        # Validate operation-specific requirements
        if operation == "search":
            if not self.config.get("vector"):
                raise NodeValidationError("vector required for search operation")
        elif operation == "insert":
            if not (self.config.get("vector") or self.config.get("vectors")):
                raise NodeValidationError("vector or vectors required for insert")
        elif operation == "create_table":
            if not self.config.get("dimension"):
                raise NodeValidationError("dimension required for create_table")

        # Validate distance metric
        metric = self.config.get("distance_metric", "l2").lower()
        if metric not in ["l2", "cosine", "ip"]:
            raise NodeValidationError(
                f"Invalid distance_metric: {metric}. " "Must be one of: l2, cosine, ip"
            )

        # Validate index type
        index_type = self.config.get("index_type", "hnsw").lower()
        if index_type not in ["hnsw", "ivfflat", "none"]:
            raise NodeValidationError(
                f"Invalid index_type: {index_type}. "
                "Must be one of: hnsw, ivfflat, none"
            )

    def _get_db_config(self) -> dict:
        """Get database configuration."""
        if self.config.get("connection_string"):
            return {
                "type": "postgresql",
                "connection_string": self.config["connection_string"],
            }
        else:
            return {
                "type": "postgresql",
                "host": self.config["host"],
                "port": self.config.get("port", 5432),
                "database": self.config["database"],
                "user": self.config["user"],
                "password": self.config.get("password", ""),
            }

    def _get_distance_operator(self, metric: str) -> str:
        """Get pgvector distance operator for metric."""
        operators = {"l2": "<->", "cosine": "<=>", "ip": "<#>"}
        return operators.get(metric, "<->")

    async def _ensure_extension(self, conn):
        """Ensure pgvector extension is installed."""
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as e:
            # Extension might already exist or user lacks permissions
            logger.debug(f"pgvector extension check: {e}")

    async def _create_table(self, conn) -> dict[str, Any]:
        """Create vector table."""
        table_name = self.config["table_name"]
        vector_column = self.config.get("vector_column", "embedding")
        dimension = self.config["dimension"]

        await self._ensure_extension(conn)

        # Create table with vector column
        query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            {vector_column} vector({dimension}),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        await conn.execute(query)

        return {
            "result": {
                "status": "success",
                "table": table_name,
                "dimension": dimension,
                "message": f"Table {table_name} created successfully",
            }
        }

    async def _create_index(self, conn) -> dict[str, Any]:
        """Create vector index."""
        table_name = self.config["table_name"]
        vector_column = self.config.get("vector_column", "embedding")
        index_type = self.config.get("index_type", "hnsw").lower()
        distance_metric = self.config.get("distance_metric", "l2").lower()

        # Get distance function for index
        distance_func = {
            "l2": "vector_l2_ops",
            "cosine": "vector_cosine_ops",
            "ip": "vector_ip_ops",
        }.get(distance_metric, "vector_l2_ops")

        index_name = f"{table_name}_{vector_column}_{index_type}_idx"

        if index_type == "hnsw":
            m = self.config.get("m", 16)
            ef_construction = self.config.get("ef_construction", 64)
            query = f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name}
            USING hnsw ({vector_column} {distance_func})
            WITH (m = {m}, ef_construction = {ef_construction})
            """
        elif index_type == "ivfflat":
            lists = self.config.get("lists", 100)
            query = f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name}
            USING ivfflat ({vector_column} {distance_func})
            WITH (lists = {lists})
            """
        else:
            return {
                "result": {
                    "status": "skipped",
                    "message": "No index created (exact search mode)",
                }
            }

        await conn.execute(query)

        return {
            "result": {
                "status": "success",
                "index": index_name,
                "type": index_type,
                "message": f"Index {index_name} created successfully",
            }
        }

    async def _insert_vectors(self, conn, **inputs) -> dict[str, Any]:
        """Insert vectors into table."""
        table_name = self.config["table_name"]
        vector_column = self.config.get("vector_column", "embedding")

        # Get vectors and metadata
        vectors = inputs.get("vectors") or self.config.get("vectors")
        single_vector = inputs.get("vector") or self.config.get("vector")
        metadata = inputs.get("metadata") or self.config.get("metadata")

        if single_vector and not vectors:
            vectors = [single_vector]
            if metadata and not isinstance(metadata, list):
                metadata = [metadata]

        if not vectors:
            raise NodeExecutionError("No vectors provided for insert")

        # Prepare batch insert
        inserted_count = 0

        if metadata:
            # Insert with metadata
            query = f"""
            INSERT INTO {table_name} ({vector_column}, metadata)
            VALUES ($1, $2)
            """

            for i, vector in enumerate(vectors):
                meta = metadata[i] if i < len(metadata) else {}
                await conn.execute(query, vector, json.dumps(meta))
                inserted_count += 1
        else:
            # Insert vectors only
            query = f"""
            INSERT INTO {table_name} ({vector_column})
            VALUES ($1)
            """

            for vector in vectors:
                await conn.execute(query, vector)
                inserted_count += 1

        return {
            "result": {
                "status": "success",
                "inserted_count": inserted_count,
                "message": f"Inserted {inserted_count} vectors",
            }
        }

    async def _search_vectors(self, conn, **inputs) -> dict[str, Any]:
        """Search for similar vectors."""
        table_name = self.config["table_name"]
        vector_column = self.config.get("vector_column", "embedding")

        # Get search parameters
        query_vector = inputs.get("vector") or self.config.get("vector")
        limit = inputs.get("limit") or self.config.get("limit", 10)
        metadata_filter = inputs.get("metadata_filter") or self.config.get(
            "metadata_filter"
        )
        distance_metric = self.config.get("distance_metric", "l2").lower()

        if not query_vector:
            raise NodeExecutionError("No query vector provided for search")

        # Set search parameters if provided
        if self.config.get("ef_search"):
            await conn.execute(f"SET hnsw.ef_search = {self.config['ef_search']}")
        if self.config.get("probes"):
            await conn.execute(f"SET ivfflat.probes = {self.config['probes']}")

        # Build search query
        distance_op = self._get_distance_operator(distance_metric)

        base_query = f"""
        SELECT
            id,
            {vector_column} AS vector,
            metadata,
            {vector_column} {distance_op} $1 AS distance
        FROM {table_name}
        """

        if metadata_filter:
            base_query += f" WHERE {metadata_filter}"

        base_query += f"""
        ORDER BY {vector_column} {distance_op} $1
        LIMIT {limit}
        """

        # Execute search
        rows = await conn.fetch(base_query, query_vector)

        # Format results
        matches = []
        for row in rows:
            matches.append(
                {
                    "id": row["id"],
                    "distance": float(row["distance"]),
                    "vector": list(row["vector"]) if row["vector"] else None,
                    "metadata": row["metadata"],
                }
            )

        return {
            "result": {
                "matches": matches,
                "count": len(matches),
                "distance_metric": distance_metric,
            }
        }

    async def async_run(self, **inputs) -> dict[str, Any]:
        """Execute vector database operation."""
        try:
            operation = (inputs.get("operation") or self.config["operation"]).lower()
            tenant_id = inputs.get("tenant_id") or self.config.get(
                "tenant_id", "default"
            )

            # Get database connection
            db_config = self._get_db_config()
            pool_config = PoolConfig(
                min_size=1, max_size=self.config.get("pool_size", 10)
            )

            async with self._connection_manager.get_connection(
                tenant_id=tenant_id, db_config=db_config, pool_config=pool_config
            ) as conn:
                if operation == "create_table":
                    return await self._create_table(conn)
                elif operation == "create_index":
                    return await self._create_index(conn)
                elif operation == "insert":
                    return await self._insert_vectors(conn, **inputs)
                elif operation == "search":
                    return await self._search_vectors(conn, **inputs)
                else:
                    raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            raise NodeExecutionError(f"Vector operation failed: {str(e)}")

    def run(self, **inputs) -> dict[str, Any]:
        """Synchronous run method - delegates to async_run."""
        import asyncio

        return asyncio.run(self.async_run(**inputs))
