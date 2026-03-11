"""
Vector Search Nodes for DataFlow

Workflow nodes for vector similarity search using PostgreSQLVectorAdapter.
"""

import logging
from typing import Any, Dict, List, Optional

from dataflow.adapters import PostgreSQLVectorAdapter

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode

logger = logging.getLogger(__name__)


@register_node()
class VectorSearchNode(AsyncNode):
    """
    Semantic similarity search using vector embeddings.

    Performs vector similarity search on a table with vector columns.
    Requires PostgreSQLVectorAdapter with pgvector extension.

    Example:
        workflow.add_node("VectorSearchNode", "search", {
            "table_name": "documents",
            "query_vector": embedding,
            "k": 5,
            "distance": "cosine",
            "filter_conditions": "category = 'tech'"
        })
    """

    def __init__(self, **kwargs):
        """Initialize VectorSearchNode."""
        # Extract DataFlow-specific parameters
        self.table_name = kwargs.pop("table_name", None)
        self.dataflow_instance = kwargs.pop("dataflow_instance", None)

        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define runtime parameters for vector search."""
        return {
            "query_vector": NodeParameter(
                name="query_vector",
                type=list,
                required=True,
                description="Query embedding vector (must match column dimensions)",
            ),
            "k": NodeParameter(
                name="k",
                type=int,
                default=10,
                description="Number of results to return",
            ),
            "column_name": NodeParameter(
                name="column_name",
                type=str,
                default="embedding",
                description="Name of the vector column",
            ),
            "distance": NodeParameter(
                name="distance",
                type=str,
                default="cosine",
                description="Distance metric: 'cosine', 'l2', or 'ip'",
            ),
            "filter_conditions": NodeParameter(
                name="filter_conditions",
                type=str,
                required=False,
                default=None,
                description="Optional WHERE clause filter (e.g., \"category = 'tech'\")",
            ),
            "return_distance": NodeParameter(
                name="return_distance",
                type=bool,
                default=True,
                description="Include distance scores in results",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute vector similarity search.

        Returns:
            Dict with:
                - results: List of matching records
                - count: Number of results returned
                - table_name: Table searched
                - distance_metric: Distance metric used
        """
        # Get adapter from DataFlow instance
        if not self.dataflow_instance:
            raise ValueError(
                "VectorSearchNode requires dataflow_instance. "
                "This node must be used within a DataFlow workflow."
            )

        adapter = self.dataflow_instance.adapter

        # Validate adapter type
        if not isinstance(adapter, PostgreSQLVectorAdapter):
            raise ValueError(
                f"VectorSearchNode requires PostgreSQLVectorAdapter, "
                f"got {type(adapter).__name__}. "
                f"Initialize DataFlow with: "
                f"db = DataFlow(adapter=PostgreSQLVectorAdapter(connection_string))"
            )

        # Validate table_name
        if not self.table_name:
            raise ValueError("table_name is required for VectorSearchNode")

        # Validate and get parameters from kwargs
        validated_inputs = self.validate_inputs(**kwargs)

        query_vector = validated_inputs.get("query_vector")
        k = validated_inputs.get("k", 10)
        column_name = validated_inputs.get("column_name", "embedding")
        distance = validated_inputs.get("distance", "cosine")
        filter_conditions = validated_inputs.get("filter_conditions")
        return_distance = validated_inputs.get("return_distance", True)

        # Execute vector search
        try:
            results = await adapter.vector_search(
                table_name=self.table_name,
                query_vector=query_vector,
                k=k,
                column_name=column_name,
                distance=distance,
                filter_conditions=filter_conditions,
                return_distance=return_distance,
            )

            logger.info(
                f"VectorSearchNode: Found {len(results)} results for table '{self.table_name}'"
            )

            return {
                "results": results,
                "count": len(results),
                "table_name": self.table_name,
                "distance_metric": distance,
            }

        except Exception as e:
            logger.error(
                f"VectorSearchNode failed for table '{self.table_name}': {str(e)}"
            )
            raise RuntimeError(
                f"Vector search failed for table '{self.table_name}': {str(e)}"
            ) from e


@register_node()
class CreateVectorIndexNode(AsyncNode):
    """
    Create vector index for fast similarity search.

    Creates IVFFlat or HNSW index on a vector column for improved query performance.
    Requires PostgreSQLVectorAdapter with pgvector extension.

    Example:
        # IVFFlat index (good performance)
        workflow.add_node("CreateVectorIndexNode", "index", {
            "table_name": "documents",
            "column_name": "embedding",
            "index_type": "ivfflat",
            "distance": "cosine",
            "lists": 100
        })

        # HNSW index (better performance, requires pgvector 0.5.0+)
        workflow.add_node("CreateVectorIndexNode", "index", {
            "table_name": "documents",
            "index_type": "hnsw",
            "distance": "cosine",
            "m": 16,
            "ef_construction": 64
        })
    """

    def __init__(self, **kwargs):
        """Initialize CreateVectorIndexNode."""
        # Extract DataFlow-specific parameters
        self.table_name = kwargs.pop("table_name", None)
        self.dataflow_instance = kwargs.pop("dataflow_instance", None)

        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define runtime parameters for vector index creation."""
        return {
            "column_name": NodeParameter(
                name="column_name",
                type=str,
                default="embedding",
                description="Name of the vector column to index",
            ),
            "index_type": NodeParameter(
                name="index_type",
                type=str,
                default="ivfflat",
                description="Index type: 'ivfflat' or 'hnsw'",
            ),
            "distance": NodeParameter(
                name="distance",
                type=str,
                default="cosine",
                description="Distance metric: 'cosine', 'l2', or 'ip'",
            ),
            "lists": NodeParameter(
                name="lists",
                type=int,
                default=100,
                description="Number of IVF lists (for ivfflat), typically sqrt(rows)",
            ),
            "m": NodeParameter(
                name="m",
                type=int,
                default=16,
                description="Max connections per layer (for hnsw)",
            ),
            "ef_construction": NodeParameter(
                name="ef_construction",
                type=int,
                default=64,
                description="Build time accuracy parameter (for hnsw)",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute vector index creation.

        Returns:
            Dict with:
                - success: True if index created
                - index_created: True
                - table_name: Table indexed
                - column_name: Column indexed
                - index_type: Type of index created
        """
        # Get adapter from DataFlow instance
        if not self.dataflow_instance:
            raise ValueError(
                "CreateVectorIndexNode requires dataflow_instance. "
                "This node must be used within a DataFlow workflow."
            )

        adapter = self.dataflow_instance.adapter

        # Validate adapter type
        if not isinstance(adapter, PostgreSQLVectorAdapter):
            raise ValueError(
                f"CreateVectorIndexNode requires PostgreSQLVectorAdapter, "
                f"got {type(adapter).__name__}. "
                f"Initialize DataFlow with: "
                f"db = DataFlow(adapter=PostgreSQLVectorAdapter(connection_string))"
            )

        # Validate table_name
        if not self.table_name:
            raise ValueError("table_name is required for CreateVectorIndexNode")

        # Validate and get parameters from kwargs
        validated_inputs = self.validate_inputs(**kwargs)

        column_name = validated_inputs.get("column_name", "embedding")
        index_type = validated_inputs.get("index_type", "ivfflat")
        distance = validated_inputs.get("distance", "cosine")
        lists = validated_inputs.get("lists", 100)
        m = validated_inputs.get("m", 16)
        ef_construction = validated_inputs.get("ef_construction", 64)

        # Build index_params based on index_type
        index_params = {}
        if index_type == "hnsw":
            index_params["m"] = m
            index_params["ef_construction"] = ef_construction

        # Execute vector index creation
        try:
            await adapter.create_vector_index(
                table_name=self.table_name,
                column_name=column_name,
                index_type=index_type,
                distance=distance,
                lists=lists,
                **index_params,
            )

            logger.info(
                f"CreateVectorIndexNode: Created {index_type} index on "
                f"'{self.table_name}.{column_name}' with {distance} distance"
            )

            return {
                "success": True,
                "index_created": True,
                "table_name": self.table_name,
                "column_name": column_name,
                "index_type": index_type,
                "distance": distance,
            }

        except Exception as e:
            logger.error(
                f"CreateVectorIndexNode failed for '{self.table_name}.{column_name}': {str(e)}"
            )
            raise RuntimeError(
                f"Vector index creation failed for '{self.table_name}.{column_name}': {str(e)}"
            ) from e


@register_node()
class HybridSearchNode(AsyncNode):
    """
    Hybrid search combining vector similarity and full-text search.

    Uses RRF (Reciprocal Rank Fusion) to combine vector similarity search
    with PostgreSQL full-text search for best of both worlds.

    Requires PostgreSQLVectorAdapter with pgvector extension.

    Example:
        workflow.add_node("HybridSearchNode", "search", {
            "table_name": "documents",
            "query_vector": embedding,
            "text_query": "machine learning",
            "k": 10,
            "vector_weight": 0.7,
            "text_weight": 0.3
        })
    """

    def __init__(self, **kwargs):
        """Initialize HybridSearchNode."""
        # Extract DataFlow-specific parameters
        self.table_name = kwargs.pop("table_name", None)
        self.dataflow_instance = kwargs.pop("dataflow_instance", None)

        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define runtime parameters for hybrid search."""
        return {
            "query_vector": NodeParameter(
                name="query_vector",
                type=list,
                required=True,
                description="Query embedding vector for semantic search",
            ),
            "text_query": NodeParameter(
                name="text_query",
                type=str,
                required=False,
                default=None,
                description="Text query for full-text search (optional)",
            ),
            "k": NodeParameter(
                name="k",
                type=int,
                default=10,
                description="Number of results to return",
            ),
            "vector_weight": NodeParameter(
                name="vector_weight",
                type=float,
                default=0.7,
                description="Weight for vector similarity (0-1)",
            ),
            "text_weight": NodeParameter(
                name="text_weight",
                type=float,
                default=0.3,
                description="Weight for text relevance (0-1)",
            ),
            "column_name": NodeParameter(
                name="column_name",
                type=str,
                default="embedding",
                description="Name of the vector column",
            ),
            "text_column": NodeParameter(
                name="text_column",
                type=str,
                default="content",
                description="Name of the text column for full-text search",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute hybrid search.

        Returns:
            Dict with:
                - results: List of matching records
                - count: Number of results returned
                - table_name: Table searched
                - search_type: "hybrid" or "vector_only"
        """
        # Get adapter from DataFlow instance
        if not self.dataflow_instance:
            raise ValueError(
                "HybridSearchNode requires dataflow_instance. "
                "This node must be used within a DataFlow workflow."
            )

        adapter = self.dataflow_instance.adapter

        # Validate adapter type
        if not isinstance(adapter, PostgreSQLVectorAdapter):
            raise ValueError(
                f"HybridSearchNode requires PostgreSQLVectorAdapter, "
                f"got {type(adapter).__name__}. "
                f"Initialize DataFlow with: "
                f"db = DataFlow(adapter=PostgreSQLVectorAdapter(connection_string))"
            )

        # Validate table_name
        if not self.table_name:
            raise ValueError("table_name is required for HybridSearchNode")

        # Validate and get parameters from kwargs
        validated_inputs = self.validate_inputs(**kwargs)

        query_vector = validated_inputs.get("query_vector")
        text_query = validated_inputs.get("text_query")
        k = validated_inputs.get("k", 10)
        vector_weight = validated_inputs.get("vector_weight", 0.7)
        text_weight = validated_inputs.get("text_weight", 0.3)
        column_name = validated_inputs.get("column_name", "embedding")
        text_column = validated_inputs.get("text_column", "content")

        # Execute hybrid search
        try:
            results = await adapter.hybrid_search(
                table_name=self.table_name,
                query_vector=query_vector,
                text_query=text_query,
                k=k,
                vector_weight=vector_weight,
                text_weight=text_weight,
                column_name=column_name,
                text_column=text_column,
            )

            search_type = "hybrid" if text_query else "vector_only"

            logger.info(
                f"HybridSearchNode: Found {len(results)} results for table "
                f"'{self.table_name}' using {search_type} search"
            )

            return {
                "results": results,
                "count": len(results),
                "table_name": self.table_name,
                "search_type": search_type,
            }

        except Exception as e:
            logger.error(
                f"HybridSearchNode failed for table '{self.table_name}': {str(e)}"
            )
            raise RuntimeError(
                f"Hybrid search failed for table '{self.table_name}': {str(e)}"
            ) from e
