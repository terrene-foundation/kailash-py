"""
PostgreSQL Vector Database Adapter

PostgreSQL adapter with pgvector extension for vector similarity search.
Extends PostgreSQLAdapter with vector operations for RAG and semantic search.
"""

import logging
from typing import Any, Dict, List, Optional

from .postgresql import PostgreSQLAdapter

logger = logging.getLogger(__name__)


class PostgreSQLVectorAdapter(PostgreSQLAdapter):
    """
    PostgreSQL with pgvector extension for vector similarity search.

    Extends PostgreSQLAdapter with:
    - Vector column creation
    - Vector index creation (ivfflat, hnsw)
    - Semantic similarity search
    - Hybrid search (vector + full-text)
    - Integration with AI/ML frameworks

    Use Cases:
    - RAG (Retrieval-Augmented Generation)
    - Semantic search
    - Document similarity
    - Recommendation systems
    - AI/ML feature storage
    """

    def __init__(self, connection_string: str, **kwargs):
        """
        Initialize PostgreSQL vector adapter.

        Args:
            connection_string: PostgreSQL connection string
            vector_dimensions: Default vector dimensions (default: 1536 for OpenAI)
            default_distance: Default distance metric: "cosine", "l2", "ip" (default: "cosine")
            **kwargs: Additional PostgreSQL configuration
        """
        super().__init__(connection_string, **kwargs)

        # Vector-specific configuration
        self.vector_dimensions = kwargs.get("vector_dimensions", 1536)  # OpenAI default
        self.default_distance = kwargs.get("default_distance", "cosine")

        # Track pgvector extension status
        self._pgvector_installed = None

    @property
    def database_type(self) -> str:
        """Get specific database type identifier."""
        return "postgresql_vector"  # Distinguish from base PostgreSQL

    def supports_feature(self, feature: str) -> bool:
        """
        Enhanced feature detection including vector operations.

        Vector-specific features:
        - "vector_search": Semantic similarity search
        - "vector_index": Vector index creation
        - "hybrid_search": Combined vector + full-text search
        - "vector_l2": L2 distance metric
        - "vector_cosine": Cosine similarity
        - "vector_ip": Inner product
        """
        vector_features = {
            "vector_search",
            "vector_index",
            "hybrid_search",
            "vector_l2",
            "vector_cosine",
            "vector_ip",
        }

        if feature in vector_features:
            return True

        return super().supports_feature(feature)

    async def ensure_pgvector_extension(self) -> None:
        """
        Ensure pgvector extension is installed and enabled.

        Raises:
            RuntimeError: If pgvector extension cannot be enabled
        """
        try:
            query = "CREATE EXTENSION IF NOT EXISTS vector"
            await self.execute_query(query)
            self._pgvector_installed = True
            logger.info("pgvector extension enabled successfully")

        except Exception as e:
            self._pgvector_installed = False
            logger.error(f"Failed to enable pgvector extension: {e}")
            raise RuntimeError(
                f"pgvector extension not available. Please install: "
                f"https://github.com/pgvector/pgvector. Error: {e}"
            )

    async def create_vector_column(
        self,
        table_name: str,
        column_name: str = "embedding",
        dimensions: Optional[int] = None,
    ) -> None:
        """
        Add vector column to existing table.

        Args:
            table_name: Table name
            column_name: Vector column name (default: "embedding")
            dimensions: Vector dimensions (default: self.vector_dimensions)

        Example:
            await adapter.create_vector_column("documents", "embedding", 1536)
        """
        dims = dimensions or self.vector_dimensions

        # Ensure pgvector is installed
        if self._pgvector_installed is None:
            await self.ensure_pgvector_extension()

        query = f"""
        ALTER TABLE {table_name}
        ADD COLUMN IF NOT EXISTS {column_name} vector({dims})
        """

        await self.execute_query(query)
        logger.info(
            f"Vector column '{column_name}' ({dims} dimensions) added to '{table_name}'"
        )

    async def create_vector_index(
        self,
        table_name: str,
        column_name: str = "embedding",
        index_type: str = "ivfflat",
        distance: str = "cosine",
        lists: int = 100,
        **index_params,
    ) -> None:
        """
        Create vector index for fast similarity search.

        Args:
            table_name: Table name
            column_name: Vector column name
            index_type: "ivfflat" (good) or "hnsw" (better, pgvector 0.5.0+)
            distance: "cosine", "l2", or "ip" (inner product)
            lists: Number of IVF lists (for ivfflat), typically sqrt(rows)
            **index_params: Additional index parameters (m, ef_construction for hnsw)

        Performance:
            - ivfflat: Good for most use cases, faster build time
            - hnsw: Better recall, slower build but faster query

        Example:
            # Create IVFFlat index
            await adapter.create_vector_index("documents", "embedding", "ivfflat", "cosine", lists=100)

            # Create HNSW index (better performance)
            await adapter.create_vector_index("documents", "embedding", "hnsw", "cosine", m=16, ef_construction=64)
        """
        # Ensure pgvector is installed
        if self._pgvector_installed is None:
            await self.ensure_pgvector_extension()

        # Distance operator mapping
        distance_ops = {
            "cosine": "vector_cosine_ops",
            "l2": "vector_l2_ops",
            "ip": "vector_ip_ops",
        }

        if distance not in distance_ops:
            raise ValueError(
                f"Unknown distance metric: {distance}. "
                f"Must be one of: {list(distance_ops.keys())}"
            )

        ops = distance_ops[distance]
        index_name = f"{table_name}_{column_name}_{index_type}_idx"

        if index_type == "ivfflat":
            query = f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name} USING ivfflat ({column_name} {ops})
            WITH (lists = {lists})
            """

        elif index_type == "hnsw":
            # HNSW requires pgvector 0.5.0+
            m = index_params.get("m", 16)  # Max connections per layer
            ef_construction = index_params.get(
                "ef_construction", 64
            )  # Build time accuracy

            query = f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name} USING hnsw ({column_name} {ops})
            WITH (m = {m}, ef_construction = {ef_construction})
            """

        else:
            raise ValueError(
                f"Unknown index type: {index_type}. Must be 'ivfflat' or 'hnsw'"
            )

        await self.execute_query(query)
        logger.info(
            f"Vector index '{index_name}' created on '{table_name}.{column_name}'"
        )

    async def vector_search(
        self,
        table_name: str,
        query_vector: List[float],
        k: int = 10,
        column_name: str = "embedding",
        distance: str = "cosine",
        filter_conditions: Optional[str] = None,
        return_distance: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Semantic similarity search using vector embeddings.

        Args:
            table_name: Table to search
            query_vector: Query embedding vector (must match column dimensions)
            k: Number of results to return
            column_name: Vector column name
            distance: Distance metric ("cosine", "l2", "ip")
            filter_conditions: Optional WHERE clause (e.g., "category = 'tech'")
            return_distance: Include distance score in results

        Returns:
            List of matching records sorted by similarity, with optional distance scores

        Example:
            results = await adapter.vector_search(
                "documents",
                query_embedding,
                k=5,
                filter_conditions="category = 'AI' AND published = true"
            )
        """
        # Distance operator mapping
        distance_ops = {"cosine": "<=>", "l2": "<->", "ip": "<#>"}

        if distance not in distance_ops:
            raise ValueError(
                f"Unknown distance metric: {distance}. "
                f"Must be one of: {list(distance_ops.keys())}"
            )

        op = distance_ops[distance]

        # Convert Python list to PostgreSQL array format
        vector_str = f"'[{','.join(map(str, query_vector))}]'"

        # Build query
        distance_select = (
            f", {column_name} {op} {vector_str}::vector AS distance"
            if return_distance
            else ""
        )
        where_clause = f"WHERE {filter_conditions}" if filter_conditions else ""

        query = f"""
        SELECT *{distance_select}
        FROM {table_name}
        {where_clause}
        ORDER BY {column_name} {op} {vector_str}::vector
        LIMIT {k}
        """

        results = await self.execute_query(query)

        logger.info(f"Vector search on '{table_name}' returned {len(results)} results")

        return results

    async def hybrid_search(
        self,
        table_name: str,
        query_vector: List[float],
        text_query: Optional[str] = None,
        k: int = 10,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        column_name: str = "embedding",
        text_column: str = "content",
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector similarity and full-text search.

        Uses RRF (Reciprocal Rank Fusion) to combine vector and text results.

        Args:
            table_name: Table to search
            query_vector: Query embedding vector
            text_query: Text search query (optional)
            k: Number of results to return
            vector_weight: Weight for vector similarity (0-1)
            text_weight: Weight for text relevance (0-1)
            column_name: Vector column name
            text_column: Text column for full-text search

        Returns:
            List of matching records sorted by combined score

        Example:
            results = await adapter.hybrid_search(
                "documents",
                query_embedding,
                text_query="machine learning",
                k=10,
                vector_weight=0.7,
                text_weight=0.3
            )
        """
        # Vector search results
        vector_results = await self.vector_search(
            table_name,
            query_vector,
            k=k * 2,  # Get more results for fusion
            column_name=column_name,
            return_distance=True,
        )

        # If no text query, return vector results only
        if not text_query:
            return vector_results[:k]

        # Full-text search results
        text_query_sql = f"""
        SELECT *, ts_rank(to_tsvector('english', {text_column}),
                         to_tsquery('english', '{text_query}')) AS text_score
        FROM {table_name}
        WHERE to_tsvector('english', {text_column}) @@ to_tsquery('english', '{text_query}')
        ORDER BY text_score DESC
        LIMIT {k * 2}
        """

        try:
            text_results = await self.execute_query(text_query_sql)
        except Exception as e:
            logger.warning(f"Text search failed, falling back to vector search: {e}")
            return vector_results[:k]

        # Combine using RRF (Reciprocal Rank Fusion)
        combined_scores = {}

        # Add vector scores
        for rank, result in enumerate(vector_results, 1):
            id_val = result.get("id")
            if id_val:
                combined_scores[id_val] = vector_weight / (60 + rank)

        # Add text scores
        for rank, result in enumerate(text_results, 1):
            id_val = result.get("id")
            if id_val:
                if id_val in combined_scores:
                    combined_scores[id_val] += text_weight / (60 + rank)
                else:
                    combined_scores[id_val] = text_weight / (60 + rank)

        # Get top k by combined score
        top_ids = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:k]

        if not top_ids:
            return []

        # Fetch full records for top results
        id_list = ",".join([f"'{id_val}'" for id_val, _ in top_ids])
        final_query = f"SELECT * FROM {table_name} WHERE id IN ({id_list})"

        final_results = await self.execute_query(final_query)

        logger.info(
            f"Hybrid search on '{table_name}' returned {len(final_results)} results"
        )

        return final_results

    async def get_vector_stats(
        self, table_name: str, column_name: str = "embedding"
    ) -> Dict[str, Any]:
        """
        Get statistics about vector column.

        Args:
            table_name: Table name
            column_name: Vector column name

        Returns:
            Dict with vector column statistics
        """
        query = f"""
        SELECT
            COUNT(*) as total_vectors,
            COUNT({column_name}) as non_null_vectors,
            (SELECT array_length({column_name}, 1) FROM {table_name} WHERE {column_name} IS NOT NULL LIMIT 1) as dimensions
        FROM {table_name}
        """

        results = await self.execute_query(query)

        if results:
            return results[0]
        return {}
