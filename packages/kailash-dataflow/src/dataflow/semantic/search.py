"""
Semantic and hybrid search engines for DataFlow.

Provides both pure semantic search and hybrid search combining
semantic similarity with traditional keyword matching.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import asyncpg
import numpy as np

from ..database.connection_builder import ConnectionStringBuilder
from ..database.query_builder import QueryBuilder
from .memory import MemoryItem, SemanticMemory


@dataclass
class SearchResult:
    """A search result with relevance scoring."""

    id: str
    content: str
    score: float
    semantic_score: Optional[float] = None
    keyword_score: Optional[float] = None
    metadata: Dict[str, Any] = None
    source: str = "hybrid"

    @property
    def relevance_score(self) -> float:
        """Combined relevance score."""
        return self.score


class SemanticSearchEngine:
    """Pure semantic search engine using embeddings."""

    def __init__(self, semantic_memory: SemanticMemory):
        """
        Initialize semantic search engine.

        Args:
            semantic_memory: Semantic memory instance
        """
        self.memory = semantic_memory

    async def search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        collection: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Perform semantic search.

        Args:
            query: Search query
            limit: Maximum results
            threshold: Minimum similarity threshold
            collection: Collection to search
            metadata_filter: Metadata filters

        Returns:
            List of search results
        """
        # Recall from semantic memory
        memories = await self.memory.recall(
            query=query,
            limit=limit,
            threshold=threshold,
            collection=collection,
            metadata_filter=metadata_filter,
        )

        # Convert to search results
        results = []
        for item, similarity in memories:
            result = SearchResult(
                id=item.id,
                content=item.content,
                score=similarity,
                semantic_score=similarity,
                metadata=item.metadata,
                source="semantic",
            )
            results.append(result)

        return results

    async def search_by_example(
        self, example_id: str, limit: int = 10, exclude_self: bool = True
    ) -> List[SearchResult]:
        """
        Find similar items to a given example.

        Args:
            example_id: ID of example item
            limit: Maximum results
            exclude_self: Whether to exclude the example itself

        Returns:
            List of similar items
        """
        # Fetch the example item's embedding
        async with self.memory.vector_store.connection_builder.get_connection() as conn:
            if (
                self.memory.vector_store.connection_builder.adapter.dialect_type
                == "postgresql"
            ):
                row = await conn.fetchrow(
                    f"SELECT embedding, content, metadata FROM {self.memory.vector_store.table_name} WHERE id = $1::uuid",
                    example_id,
                )
            else:
                row = await conn.fetchrow(
                    f"SELECT embedding, content, metadata FROM {self.memory.vector_store.table_name} WHERE id = ?",
                    example_id,
                )

            if not row:
                return []

            embedding = np.array(
                row["embedding"]
                if isinstance(row["embedding"], list)
                else eval(row["embedding"])
            )

        # Search for similar items
        results = await self.memory.vector_store.search_similar(
            embedding=embedding, limit=limit + 1 if exclude_self else limit
        )

        # Convert to search results
        search_results = []
        for item, similarity in results:
            if exclude_self and item.id == example_id:
                continue

            result = SearchResult(
                id=item.id,
                content=item.content,
                score=similarity,
                semantic_score=similarity,
                metadata=item.metadata,
                source="semantic",
            )
            search_results.append(result)

        return search_results[:limit]


class HybridSearchEngine:
    """Hybrid search combining semantic and keyword search."""

    def __init__(
        self,
        semantic_memory: SemanticMemory,
        connection_builder: ConnectionStringBuilder,
        table_name: str = "documents",
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ):
        """
        Initialize hybrid search engine.

        Args:
            semantic_memory: Semantic memory instance
            connection_builder: Database connection
            table_name: Table for keyword search
            semantic_weight: Weight for semantic scores
            keyword_weight: Weight for keyword scores
        """
        self.semantic_memory = semantic_memory
        self.connection_builder = connection_builder
        self.table_name = table_name
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self.semantic_engine = SemanticSearchEngine(semantic_memory)

    async def search(
        self,
        query: str,
        limit: int = 10,
        semantic_threshold: float = 0.5,
        collection: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        fields: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """
        Perform hybrid search.

        Args:
            query: Search query
            limit: Maximum results
            semantic_threshold: Minimum semantic similarity
            collection: Collection to search
            metadata_filter: Metadata filters
            fields: Fields to search in keyword search

        Returns:
            List of search results
        """
        # Perform semantic search
        semantic_task = self.semantic_engine.search(
            query=query,
            limit=limit * 2,  # Get more for merging
            threshold=semantic_threshold,
            collection=collection,
            metadata_filter=metadata_filter,
        )

        # Perform keyword search
        keyword_task = self._keyword_search(
            query=query,
            limit=limit * 2,
            fields=fields or ["content", "title", "description"],
            metadata_filter=metadata_filter,
        )

        # Run both searches in parallel
        semantic_results, keyword_results = await asyncio.gather(
            semantic_task, keyword_task
        )

        # Merge and rank results
        merged_results = self._merge_results(semantic_results, keyword_results, limit)

        return merged_results

    async def _keyword_search(
        self,
        query: str,
        limit: int,
        fields: List[str],
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Perform keyword-based search."""
        # Build full-text search query
        query_builder = QueryBuilder(self.connection_builder.adapter)

        # Tokenize query for better matching
        tokens = self._tokenize_query(query)

        # Build search conditions
        conditions = []
        for field in fields:
            field_conditions = []
            for token in tokens:
                if self.connection_builder.adapter.dialect_type == "postgresql":
                    # Use PostgreSQL full-text search
                    field_conditions.append(
                        f"to_tsvector('english', {field}) @@ plainto_tsquery('english', %s)"
                    )
                else:
                    # Use LIKE for other databases
                    field_conditions.append(f"LOWER({field}) LIKE LOWER(%s)")

            if field_conditions:
                conditions.append(f"({' OR '.join(field_conditions)})")

        where_clause = f"({' OR '.join(conditions)})" if conditions else "1=1"

        # Add metadata filter if provided
        if (
            metadata_filter
            and self.connection_builder.adapter.dialect_type == "postgresql"
        ):
            where_clause += " AND metadata @> %s::jsonb"
            params = tokens + tokens + [json.dumps(metadata_filter)]
        else:
            params = []
            for token in tokens:
                if self.connection_builder.adapter.dialect_type == "postgresql":
                    params.extend([token] * len(fields))
                else:
                    params.extend([f"%{token}%"] * len(fields))

        # Execute search
        async with self.connection_builder.get_connection() as conn:
            query_sql = f"""
                SELECT id, content,
                       {self._build_relevance_score(fields, len(tokens))} as relevance
                FROM {self.table_name}
                WHERE {where_clause}
                ORDER BY relevance DESC
                LIMIT {limit}
            """

            rows = await conn.fetch(query_sql, *params)

            results = []
            for row in rows:
                result = SearchResult(
                    id=str(row["id"]),
                    content=row["content"],
                    score=float(row["relevance"]),
                    keyword_score=float(row["relevance"]),
                    source="keyword",
                )
                results.append(result)

            return results

    def _tokenize_query(self, query: str) -> List[str]:
        """Tokenize query into search terms."""
        # Simple tokenization - can be enhanced with NLP
        tokens = re.findall(r"\w+", query.lower())
        # Remove common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
        }
        tokens = [t for t in tokens if t not in stop_words and len(t) > 2]
        return tokens

    def _build_relevance_score(self, fields: List[str], token_count: int) -> str:
        """Build SQL for relevance scoring."""
        if self.connection_builder.adapter.dialect_type == "postgresql":
            # Use ts_rank for PostgreSQL
            rank_parts = []
            for field in fields:
                rank_parts.append(
                    f"ts_rank(to_tsvector('english', {field}), plainto_tsquery('english', %s))"
                )
            return f"({' + '.join(rank_parts)}) / {len(fields)}"
        else:
            # Simple relevance based on matches
            return "1.0"

    def _merge_results(
        self,
        semantic_results: List[SearchResult],
        keyword_results: List[SearchResult],
        limit: int,
    ) -> List[SearchResult]:
        """Merge and rank results from both searches."""
        # Create a map of all results by ID
        all_results: Dict[str, SearchResult] = {}

        # Add semantic results
        for result in semantic_results:
            all_results[result.id] = SearchResult(
                id=result.id,
                content=result.content,
                score=result.score * self.semantic_weight,
                semantic_score=result.score,
                keyword_score=0.0,
                metadata=result.metadata,
                source="semantic",
            )

        # Add or update with keyword results
        for result in keyword_results:
            if result.id in all_results:
                # Combine scores
                existing = all_results[result.id]
                existing.keyword_score = result.score
                existing.score = (
                    existing.semantic_score * self.semantic_weight
                    + result.score * self.keyword_weight
                )
                existing.source = "hybrid"
            else:
                # Add keyword-only result
                all_results[result.id] = SearchResult(
                    id=result.id,
                    content=result.content,
                    score=result.score * self.keyword_weight,
                    semantic_score=0.0,
                    keyword_score=result.score,
                    metadata=result.metadata,
                    source="keyword",
                )

        # Sort by combined score
        sorted_results = sorted(
            all_results.values(), key=lambda x: x.score, reverse=True
        )

        return sorted_results[:limit]

    async def reindex(
        self,
        table_name: str,
        content_field: str = "content",
        id_field: str = "id",
        metadata_fields: Optional[List[str]] = None,
        batch_size: int = 100,
        collection: str = "default",
    ):
        """
        Reindex existing database content for semantic search.

        Args:
            table_name: Table to reindex
            content_field: Field containing text content
            id_field: Field containing unique ID
            metadata_fields: Fields to include as metadata
            batch_size: Batch size for processing
            collection: Collection to index into
        """
        metadata_fields = metadata_fields or []

        async with self.connection_builder.get_connection() as conn:
            # Count total records
            count_result = await conn.fetchrow(
                f"SELECT COUNT(*) as count FROM {table_name}"
            )
            total_count = count_result["count"]

            print(f"Reindexing {total_count} records from {table_name}...")

            # Process in batches
            offset = 0
            while offset < total_count:
                # Fetch batch
                fields = [id_field, content_field] + metadata_fields
                query = f"""
                    SELECT {', '.join(fields)}
                    FROM {table_name}
                    ORDER BY {id_field}
                    LIMIT {batch_size} OFFSET {offset}
                """

                rows = await conn.fetch(query)

                if not rows:
                    break

                # Prepare content and metadata
                contents = []
                metadatas = []

                for row in rows:
                    contents.append(row[content_field])

                    # Build metadata
                    metadata = {
                        "source_table": table_name,
                        "source_id": str(row[id_field]),
                    }
                    for field in metadata_fields:
                        if field in row:
                            metadata[field] = row[field]

                    metadatas.append(metadata)

                # Store in semantic memory
                await self.semantic_memory.remember(
                    content=contents, metadata=metadatas, collection=collection
                )

                offset += batch_size
                print(f"Indexed {min(offset, total_count)}/{total_count} records...")

        print("Reindexing complete!")
