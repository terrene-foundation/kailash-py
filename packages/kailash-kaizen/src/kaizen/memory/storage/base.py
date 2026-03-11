"""
Base classes and types for memory storage.

Defines the core abstractions for memory entries and storage backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class MemoryType(str, Enum):
    """Types of memories that can be stored."""

    SHORT_TERM = "short_term"  # Session-based, cleared after session ends
    LONG_TERM = "long_term"  # Persists across sessions
    SEMANTIC = "semantic"  # Extracted concepts and knowledge
    EPISODIC = "episodic"  # Specific events and interactions
    PROCEDURAL = "procedural"  # Learned procedures and patterns
    PREFERENCE = "preference"  # User preferences and settings
    ERROR = "error"  # Error occurrences for learning
    CORRECTION = "correction"  # Corrections applied to errors


@dataclass
class MemoryEntry:
    """
    Represents a single memory entry.

    Attributes:
        id: Unique identifier for the memory
        content: The actual memory content (text, structured data, etc.)
        memory_type: Type of memory (short-term, long-term, etc.)
        metadata: Additional metadata (tags, source, confidence, etc.)
        timestamp: When the memory was created
        importance: Importance score (0.0-1.0, used for pruning)
        access_count: Number of times this memory has been accessed
        last_accessed: When this memory was last accessed
        embedding: Optional vector embedding for semantic search
    """

    content: str
    memory_type: MemoryType = MemoryType.LONG_TERM
    id: str = field(default_factory=lambda: str(uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    importance: float = 0.5  # Default importance
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert memory entry to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": (
                self.last_accessed.isoformat() if self.last_accessed else None
            ),
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """Create memory entry from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
            last_accessed=(
                datetime.fromisoformat(data["last_accessed"])
                if data.get("last_accessed")
                else None
            ),
            embedding=data.get("embedding"),
        )

    def update_access(self) -> None:
        """Update access tracking when memory is retrieved."""
        self.access_count += 1
        self.last_accessed = datetime.now(timezone.utc)

    def calculate_importance(self) -> float:
        """
        Calculate dynamic importance score based on multiple factors.

        Uses Ebbinghaus forgetting curve and access patterns.
        Formula: base_importance * recency_factor * access_factor
        """
        # Time decay (Ebbinghaus forgetting curve)
        days_old = (datetime.now(timezone.utc) - self.timestamp).days
        recency_factor = 1.0 / (1.0 + 0.01 * days_old)  # Decay over time

        # Access frequency boost
        access_factor = 1.0 + (0.1 * min(self.access_count, 10))  # Cap at 2.0x

        # Combined importance
        dynamic_importance = self.importance * recency_factor * access_factor

        return min(dynamic_importance, 1.0)  # Cap at 1.0


class StorageBackend(ABC):
    """
    Abstract base class for memory storage backends.

    All storage implementations must provide these methods.
    """

    @abstractmethod
    def store(self, entry: MemoryEntry) -> str:
        """
        Store a memory entry.

        Args:
            entry: The memory entry to store

        Returns:
            The ID of the stored entry

        Raises:
            StorageError: If storage fails
        """
        pass

    @abstractmethod
    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a memory entry by ID.

        Args:
            entry_id: The ID of the entry to retrieve

        Returns:
            The memory entry if found, None otherwise
        """
        pass

    @abstractmethod
    def update(self, entry: MemoryEntry) -> None:
        """
        Update an existing memory entry.

        Args:
            entry: The updated memory entry

        Raises:
            StorageError: If update fails or entry not found
        """
        pass

    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.

        Args:
            entry_id: The ID of the entry to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    def list_entries(
        self,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryEntry]:
        """
        List memory entries with optional filtering.

        Args:
            memory_type: Filter by memory type (None for all)
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)

        Returns:
            List of memory entries
        """
        pass

    @abstractmethod
    def count(self, memory_type: Optional[MemoryType] = None) -> int:
        """
        Count memory entries.

        Args:
            memory_type: Filter by memory type (None for all)

        Returns:
            Total number of entries
        """
        pass

    @abstractmethod
    def clear(self, memory_type: Optional[MemoryType] = None) -> int:
        """
        Clear memory entries.

        Args:
            memory_type: Clear specific type (None for all)

        Returns:
            Number of entries cleared
        """
        pass

    @abstractmethod
    def search(
        self, query: str, memory_type: Optional[MemoryType] = None, limit: int = 10
    ) -> List[MemoryEntry]:
        """
        Search for memories by keyword/content.

        Args:
            query: Search query string
            memory_type: Filter by memory type
            limit: Maximum results to return

        Returns:
            List of matching memory entries
        """
        pass


class StorageError(Exception):
    """Exception raised when storage operations fail."""

    pass
