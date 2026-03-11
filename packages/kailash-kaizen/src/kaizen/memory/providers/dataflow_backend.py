"""
DataFlow Memory Backend for MemoryProvider interface.

Provides database persistence for MemoryEntry objects using the
Kailash DataFlow framework. Supports both SQLite and PostgreSQL.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .types import MemoryEntry, MemorySource

try:
    from dataflow import DataFlow
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    DATAFLOW_AVAILABLE = True
except ImportError:
    DataFlow = None
    WorkflowBuilder = None
    LocalRuntime = None
    DATAFLOW_AVAILABLE = False


logger = logging.getLogger(__name__)


class DataFlowMemoryBackend:
    """DataFlow-based storage backend for MemoryEntry.

    Uses DataFlow workflow nodes for database operations.
    The model must be defined externally using the DataFlow @db.model decorator.

    Required model schema:
        @db.model
        class MemoryEntryModel:
            id: str
            session_id: str
            content: str
            role: str
            timestamp: str  # ISO format
            source: str
            importance: float
            tags: str  # JSON array
            metadata: str  # JSON object
            embedding: Optional[str] = None  # JSON array

    Example:
        >>> from dataflow import DataFlow
        >>> from kaizen.memory.providers.dataflow_backend import DataFlowMemoryBackend
        >>>
        >>> db = DataFlow("sqlite:///memory.db")
        >>>
        >>> @db.model
        >>> class MemoryEntryModel:
        ...     id: str
        ...     session_id: str
        ...     content: str
        ...     role: str
        ...     timestamp: str
        ...     source: str
        ...     importance: float
        ...     tags: str
        ...     metadata: str
        ...     embedding: Optional[str] = None
        >>>
        >>> backend = DataFlowMemoryBackend(db, model_name="MemoryEntryModel")
        >>> entry = MemoryEntry(content="Hello", session_id="s1")
        >>> entry_id = backend.store(entry)
    """

    def __init__(
        self,
        db: "DataFlow",
        model_name: str = "MemoryEntryModel",
    ):
        """Initialize the DataFlow memory backend.

        Args:
            db: DataFlow instance connected to database
            model_name: Name of the memory entry model

        Raises:
            ImportError: If DataFlow is not installed
            ValueError: If db is not a DataFlow instance
        """
        if not DATAFLOW_AVAILABLE:
            raise ImportError(
                "DataFlow dependencies not installed. "
                "Install with: pip install kailash-dataflow kailash"
            )

        if not isinstance(db, DataFlow):
            raise ValueError(f"Expected DataFlow instance, got {type(db)}")

        self.db = db
        self.model_name = model_name

        logger.debug(f"Initialized DataFlowMemoryBackend with model: {model_name}")

    def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry in the database.

        Args:
            entry: MemoryEntry to store

        Returns:
            ID of stored entry

        Raises:
            Exception: If database operation fails
        """
        workflow = WorkflowBuilder()

        workflow.add_node(
            f"{self.model_name}CreateNode",
            "create",
            {
                "id": entry.id,
                "session_id": entry.session_id,
                "content": entry.content,
                "role": entry.role,
                "timestamp": entry.timestamp.isoformat(),
                "source": entry.source.value,
                "importance": entry.importance,
                "tags": json.dumps(entry.tags),
                "metadata": json.dumps(entry.metadata),
                "embedding": json.dumps(entry.embedding) if entry.embedding else None,
            },
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())
            logger.debug(f"Stored entry {entry.id} for session {entry.session_id}")
            return entry.id
        except Exception as e:
            logger.error(f"Failed to store entry: {e}")
            raise

    def store_many(self, entries: List[MemoryEntry]) -> List[str]:
        """Store multiple entries using bulk operation.

        Args:
            entries: List of MemoryEntry objects

        Returns:
            List of stored entry IDs
        """
        if not entries:
            return []

        workflow = WorkflowBuilder()

        records = []
        for entry in entries:
            records.append(
                {
                    "id": entry.id,
                    "session_id": entry.session_id,
                    "content": entry.content,
                    "role": entry.role,
                    "timestamp": entry.timestamp.isoformat(),
                    "source": entry.source.value,
                    "importance": entry.importance,
                    "tags": json.dumps(entry.tags),
                    "metadata": json.dumps(entry.metadata),
                    "embedding": (
                        json.dumps(entry.embedding) if entry.embedding else None
                    ),
                }
            )

        workflow.add_node(
            f"{self.model_name}BulkCreateNode",
            "bulk_create",
            {"records": records},
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())
            logger.debug(f"Stored {len(entries)} entries in bulk")
            return [e.id for e in entries]
        except Exception as e:
            logger.error(f"Failed to store entries in bulk: {e}")
            raise

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve a single entry by ID.

        Args:
            entry_id: ID of entry to retrieve

        Returns:
            MemoryEntry if found, None otherwise
        """
        workflow = WorkflowBuilder()

        workflow.add_node(
            f"{self.model_name}ReadNode",
            "read",
            {"id": entry_id},
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())

            record = results.get("read")
            if not record:
                return None

            return self._record_to_entry(record)
        except Exception as e:
            logger.error(f"Failed to get entry {entry_id}: {e}")
            return None

    def list_entries(
        self,
        session_id: str = "",
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "timestamp",
        ascending: bool = False,
    ) -> List[MemoryEntry]:
        """List entries with filtering and pagination.

        Args:
            session_id: Filter by session (optional)
            filters: Additional filters (source, role, etc.)
            limit: Maximum entries to return
            offset: Number of entries to skip
            order_by: Field to sort by
            ascending: Sort direction

        Returns:
            List of MemoryEntry objects
        """
        workflow = WorkflowBuilder()

        # Build filter
        query_filter = {}
        if session_id:
            query_filter["session_id"] = session_id

        if filters:
            if "source" in filters:
                source_val = filters["source"]
                if isinstance(source_val, MemorySource):
                    query_filter["source"] = source_val.value
                else:
                    query_filter["source"] = source_val
            if "role" in filters:
                query_filter["role"] = filters["role"]
            if "min_importance" in filters:
                query_filter["importance"] = {"$gte": filters["min_importance"]}

        workflow.add_node(
            f"{self.model_name}ListNode",
            "list",
            {
                "filter": query_filter,
                "limit": limit,
                "offset": offset,
                "order_by": order_by,
                "ascending": ascending,
            },
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())

            result = results.get("list", {})
            records = result.get("records", [])

            return [self._record_to_entry(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to list entries: {e}")
            return []

    def search(
        self,
        query: str,
        session_id: str = "",
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Search entries by content keyword.

        Note: This is a basic keyword search, not semantic search.
        For semantic search, use embeddings with vector operations.

        Args:
            query: Search query string
            session_id: Filter by session (optional)
            limit: Maximum results

        Returns:
            List of matching entries
        """
        # Get all entries for session and filter in-memory
        # (DataFlow doesn't have LIKE operator in filter)
        entries = self.list_entries(session_id=session_id, limit=1000)

        query_lower = query.lower()
        matching = []

        for entry in entries:
            if query_lower in entry.content.lower():
                matching.append(entry)
            elif any(query_lower in tag.lower() for tag in entry.tags):
                matching.append(entry)

            if len(matching) >= limit:
                break

        return matching

    def delete(self, entry_id: str) -> bool:
        """Delete a single entry by ID.

        Args:
            entry_id: ID of entry to delete

        Returns:
            True if deleted, False if not found
        """
        workflow = WorkflowBuilder()

        workflow.add_node(
            f"{self.model_name}DeleteNode",
            "delete",
            {"id": entry_id},
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())

            deleted = results.get("delete", {}).get("deleted", False)
            logger.debug(f"Deleted entry {entry_id}: {deleted}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete entry {entry_id}: {e}")
            return False

    def delete_many(
        self,
        session_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        """Delete multiple entries by criteria.

        Args:
            session_id: Delete entries for this session
            before: Delete entries before this timestamp

        Returns:
            Number of entries deleted
        """
        workflow = WorkflowBuilder()

        # Build filter
        query_filter = {}
        if session_id:
            query_filter["session_id"] = session_id
        if before:
            query_filter["timestamp"] = {"$lt": before.isoformat()}

        if not query_filter:
            # Delete all
            query_filter = {}

        workflow.add_node(
            f"{self.model_name}BulkDeleteNode",
            "bulk_delete",
            {"filter": query_filter},
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())

            deleted_count = results.get("bulk_delete", {}).get("deleted_count", 0)
            logger.debug(f"Deleted {deleted_count} entries")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete entries: {e}")
            return 0

    def count(
        self,
        session_id: str = "",
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count entries matching criteria.

        Args:
            session_id: Filter by session
            filters: Additional filters

        Returns:
            Count of matching entries
        """
        workflow = WorkflowBuilder()

        query_filter = {}
        if session_id:
            query_filter["session_id"] = session_id
        if filters:
            if "source" in filters:
                query_filter["source"] = filters["source"]
            if "role" in filters:
                query_filter["role"] = filters["role"]

        workflow.add_node(
            f"{self.model_name}CountNode",
            "count",
            {"filter": query_filter},
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())

            return results.get("count", {}).get("count", 0)
        except Exception as e:
            logger.error(f"Failed to count entries: {e}")
            return 0

    def _record_to_entry(self, record: Dict[str, Any]) -> MemoryEntry:
        """Convert database record to MemoryEntry.

        Args:
            record: Database record dict

        Returns:
            MemoryEntry instance
        """
        # Parse JSON fields
        tags = record.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []

        metadata = record.get("metadata", "{}")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        embedding = record.get("embedding")
        if embedding and isinstance(embedding, str):
            try:
                embedding = json.loads(embedding)
            except (json.JSONDecodeError, TypeError):
                embedding = None

        # Parse timestamp
        timestamp = record.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(timezone.utc)
        elif not timestamp:
            timestamp = datetime.now(timezone.utc)

        return MemoryEntry(
            id=record.get("id", ""),
            session_id=record.get("session_id", ""),
            content=record.get("content", ""),
            role=record.get("role", "assistant"),
            timestamp=timestamp,
            source=MemorySource(record.get("source", "conversation")),
            importance=record.get("importance", 0.5),
            tags=tags,
            metadata=metadata,
            embedding=embedding,
        )
