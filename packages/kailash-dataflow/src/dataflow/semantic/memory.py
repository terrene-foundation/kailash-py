"""
Semantic memory implementation with vector storage.

Provides persistent storage and retrieval of embeddings integrated
with DataFlow's database operations.
"""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import asyncpg
import numpy as np

from ..database.connection_builder import ConnectionStringBuilder
from .embeddings import EmbeddingProvider, EmbeddingResult


@dataclass
class MemoryItem:
    """A single item in semantic memory."""

    id: str
    content: str
    embedding: np.ndarray
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    collection: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding.tolist(),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "collection": self.collection,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            embedding=np.array(data["embedding"]),
            metadata=data["metadata"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            collection=data.get("collection", "default"),
        )


class VectorStore:
    """Vector storage backend for semantic memory."""

    def __init__(
        self,
        connection_builder: ConnectionStringBuilder,
        table_name: str = "semantic_memory",
    ):
        """
        Initialize vector store.

        Args:
            connection_builder: Database connection builder
            table_name: Name of the table for storing vectors
        """
        self.connection_builder = connection_builder
        self.table_name = table_name
        self._initialized = False

    async def initialize(self):
        """Initialize the vector store schema."""
        if self._initialized:
            return

        async with self.connection_builder.get_connection() as conn:
            # Create table with pgvector extension if PostgreSQL
            if self.connection_builder.adapter.dialect_type == "postgresql":
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        collection VARCHAR(255) DEFAULT 'default',
                        content TEXT NOT NULL,
                        embedding vector,
                        metadata JSONB DEFAULT '{{}}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Create indexes
                await conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_name}_collection
                    ON {self.table_name}(collection)
                """
                )

                await conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_name}_created_at
                    ON {self.table_name}(created_at DESC)
                """
                )

                # Create GIN index for metadata
                await conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_name}_metadata
                    ON {self.table_name} USING GIN(metadata)
                """
                )
            else:
                # For non-PostgreSQL, store embeddings as JSON
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id VARCHAR(36) PRIMARY KEY,
                        collection VARCHAR(255) DEFAULT 'default',
                        content TEXT NOT NULL,
                        embedding TEXT,
                        metadata TEXT DEFAULT '{{}}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                await conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_name}_collection
                    ON {self.table_name}(collection)
                """
                )

        self._initialized = True

    async def add(self, items: Union[MemoryItem, List[MemoryItem]]) -> List[str]:
        """Add items to the vector store."""
        await self.initialize()

        if isinstance(items, MemoryItem):
            items = [items]

        ids = []
        async with self.connection_builder.get_connection() as conn:
            for item in items:
                if self.connection_builder.adapter.dialect_type == "postgresql":
                    # Use pgvector for PostgreSQL
                    result = await conn.fetchrow(
                        f"""
                        INSERT INTO {self.table_name}
                        (collection, content, embedding, metadata, created_at, updated_at)
                        VALUES ($1, $2, $3::vector, $4, $5, $6)
                        RETURNING id
                    """,
                        item.collection,
                        item.content,
                        item.embedding.tolist(),
                        json.dumps(item.metadata),
                        item.created_at,
                        item.updated_at,
                    )
                    ids.append(str(result["id"]))
                else:
                    # Store as JSON for other databases
                    item_id = str(uuid4())
                    await conn.execute(
                        f"""
                        INSERT INTO {self.table_name}
                        (id, collection, content, embedding, metadata, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        item_id,
                        item.collection,
                        item.content,
                        json.dumps(item.embedding.tolist()),
                        json.dumps(item.metadata),
                        item.created_at,
                        item.updated_at,
                    )
                    ids.append(item_id)

        return ids

    async def search_similar(
        self,
        embedding: np.ndarray,
        collection: Optional[str] = None,
        limit: int = 10,
        threshold: Optional[float] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[MemoryItem, float]]:
        """Search for similar items using vector similarity."""
        await self.initialize()

        results = []
        async with self.connection_builder.get_connection() as conn:
            if self.connection_builder.adapter.dialect_type == "postgresql":
                # Use pgvector similarity search
                query = f"""
                    SELECT id, collection, content, embedding, metadata,
                           created_at, updated_at,
                           1 - (embedding <=> $1::vector) as similarity
                    FROM {self.table_name}
                    WHERE 1=1
                """
                params = [embedding.tolist()]
                param_count = 2

                if collection:
                    query += f" AND collection = ${param_count}"
                    params.append(collection)
                    param_count += 1

                if metadata_filter:
                    query += f" AND metadata @> ${param_count}::jsonb"
                    params.append(json.dumps(metadata_filter))
                    param_count += 1

                if threshold:
                    query += f" AND 1 - (embedding <=> $1::vector) >= ${param_count}"
                    params.append(threshold)
                    param_count += 1

                query += f" ORDER BY embedding <=> $1::vector LIMIT ${param_count}"
                params.append(limit)

                rows = await conn.fetch(query, *params)

                for row in rows:
                    item = MemoryItem(
                        id=str(row["id"]),
                        content=row["content"],
                        embedding=np.array(row["embedding"]),
                        metadata=json.loads(row["metadata"]),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        collection=row["collection"],
                    )
                    similarity = row["similarity"]
                    results.append((item, similarity))
            else:
                # Fallback for non-PostgreSQL: fetch all and compute similarity
                query = f"SELECT * FROM {self.table_name} WHERE 1=1"
                if collection:
                    query += f" AND collection = '{collection}'"

                rows = await conn.fetch(query)

                # Compute similarities
                similarities = []
                for row in rows:
                    stored_embedding = np.array(json.loads(row["embedding"]))
                    # Cosine similarity
                    similarity = np.dot(embedding, stored_embedding) / (
                        np.linalg.norm(embedding) * np.linalg.norm(stored_embedding)
                    )

                    if threshold and similarity < threshold:
                        continue

                    if metadata_filter:
                        row_metadata = json.loads(row["metadata"])
                        if not all(
                            row_metadata.get(k) == v for k, v in metadata_filter.items()
                        ):
                            continue

                    item = MemoryItem(
                        id=row["id"],
                        content=row["content"],
                        embedding=stored_embedding,
                        metadata=json.loads(row["metadata"]),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        collection=row["collection"],
                    )
                    similarities.append((item, similarity))

                # Sort by similarity and limit
                similarities.sort(key=lambda x: x[1], reverse=True)
                results = similarities[:limit]

        return results

    async def delete(self, ids: Union[str, List[str]]):
        """Delete items by ID."""
        await self.initialize()

        if isinstance(ids, str):
            ids = [ids]

        async with self.connection_builder.get_connection() as conn:
            if self.connection_builder.adapter.dialect_type == "postgresql":
                await conn.execute(
                    f"DELETE FROM {self.table_name} WHERE id = ANY($1::uuid[])", ids
                )
            else:
                placeholders = ",".join(["?" for _ in ids])
                await conn.execute(
                    f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})", *ids
                )

    async def update_metadata(self, id: str, metadata: Dict[str, Any]):
        """Update metadata for an item."""
        await self.initialize()

        async with self.connection_builder.get_connection() as conn:
            if self.connection_builder.adapter.dialect_type == "postgresql":
                await conn.execute(
                    f"""
                    UPDATE {self.table_name}
                    SET metadata = metadata || $1::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2::uuid
                """,
                    json.dumps(metadata),
                    id,
                )
            else:
                # Fetch existing metadata
                row = await conn.fetchrow(
                    f"SELECT metadata FROM {self.table_name} WHERE id = ?", id
                )
                if row:
                    existing = json.loads(row["metadata"])
                    existing.update(metadata)
                    await conn.execute(
                        f"""
                        UPDATE {self.table_name}
                        SET metadata = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        json.dumps(existing),
                        id,
                    )


class SemanticMemory:
    """High-level semantic memory interface."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        default_collection: str = "default",
    ):
        """
        Initialize semantic memory.

        Args:
            embedding_provider: Provider for generating embeddings
            vector_store: Storage backend for vectors
            default_collection: Default collection name
        """
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.default_collection = default_collection

    async def remember(
        self,
        content: Union[str, List[str]],
        metadata: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        collection: Optional[str] = None,
    ) -> List[str]:
        """
        Store content in semantic memory.

        Args:
            content: Text content to remember
            metadata: Optional metadata to attach
            collection: Collection to store in

        Returns:
            List of IDs for stored items
        """
        if isinstance(content, str):
            contents = [content]
            metadatas = [metadata] if metadata else [{}]
        else:
            contents = content
            if metadata is None:
                metadatas = [{}] * len(contents)
            elif isinstance(metadata, dict):
                metadatas = [metadata] * len(contents)
            else:
                metadatas = metadata

        # Generate embeddings
        result = await self.embedding_provider.embed_text(contents)

        # Create memory items
        items = []
        now = datetime.utcnow()
        for i, (text, embed, meta) in enumerate(
            zip(contents, result.embeddings, metadatas)
        ):
            item = MemoryItem(
                id=str(uuid4()),
                content=text,
                embedding=embed,
                metadata=meta,
                created_at=now,
                updated_at=now,
                collection=collection or self.default_collection,
            )
            items.append(item)

        # Store in vector store
        ids = await self.vector_store.add(items)
        return ids

    async def recall(
        self,
        query: str,
        limit: int = 10,
        threshold: Optional[float] = None,
        collection: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Recall similar content from memory.

        Args:
            query: Query text to search for
            limit: Maximum number of results
            threshold: Minimum similarity threshold
            collection: Collection to search in
            metadata_filter: Filter by metadata fields

        Returns:
            List of (item, similarity_score) tuples
        """
        # Generate query embedding
        result = await self.embedding_provider.embed_text(query)
        query_embedding = result.embeddings[0]

        # Search vector store
        results = await self.vector_store.search_similar(
            query_embedding,
            collection=collection,
            limit=limit,
            threshold=threshold,
            metadata_filter=metadata_filter,
        )

        return results

    async def forget(self, ids: Union[str, List[str]]):
        """Remove items from memory by ID."""
        await self.vector_store.delete(ids)

    async def update_context(self, id: str, metadata: Dict[str, Any]):
        """Update metadata context for a memory item."""
        await self.vector_store.update_metadata(id, metadata)

    async def create_collection(self, name: str, description: str = ""):
        """Create a new collection (logical grouping)."""
        # Collections are logical - no schema changes needed
        # Could store collection metadata separately if needed
        pass

    async def list_collections(self) -> List[str]:
        """List all collections in memory."""
        async with self.vector_store.connection_builder.get_connection() as conn:
            rows = await conn.fetch(
                f"SELECT DISTINCT collection FROM {self.vector_store.table_name}"
            )
            return [row["collection"] for row in rows]
