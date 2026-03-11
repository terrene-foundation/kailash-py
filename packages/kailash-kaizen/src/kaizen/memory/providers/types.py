"""
Core types for Memory Provider interface.

Provides standardized memory types for autonomous agent integration:
- MemorySource: Source categorization for entries
- MemoryEntry: Session-aware memory entry
- MemoryContext: LLM-ready context built from memories
- RetrievalStrategy: How to retrieve and rank memories
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class MemorySource(str, Enum):
    """Source of memory entries.

    Categorizes where memory entries originate from to enable
    source-aware retrieval and prioritization.
    """

    CONVERSATION = "conversation"  # From chat interactions (user/assistant turns)
    LEARNED = "learned"  # Pattern detected/learned by agent during execution
    EXTERNAL = "external"  # Injected from external sources (RAG, tools)
    SYSTEM = "system"  # System-generated (metadata, status)


class RetrievalStrategy(str, Enum):
    """Strategy for retrieving and ranking memories.

    Determines how memories are selected and ordered when
    building context for LLM prompts.
    """

    RECENCY = "recency"  # Sort by timestamp descending (newest first)
    IMPORTANCE = "importance"  # Sort by importance score descending
    RELEVANCE = "relevance"  # Sort by semantic similarity (requires embeddings)
    HYBRID = "hybrid"  # Weighted combination of recency, importance, relevance


@dataclass
class MemoryEntry:
    """Session-aware memory entry for autonomous agents.

    Designed for integration with LocalKaizenAdapter and other
    autonomous agent runtimes that need session-scoped memory
    with conversation role awareness.

    Attributes:
        id: Unique identifier for the memory entry
        session_id: Session this memory belongs to
        content: The actual memory content (text)
        role: Conversation role (user, assistant, system, tool)
        timestamp: When the memory was created
        source: Where this memory came from (MemorySource)
        importance: Importance score (0.0-1.0) for prioritization
        tags: List of tags for filtering
        metadata: Additional metadata dictionary
        embedding: Optional vector embedding for semantic search
    """

    content: str
    session_id: str = ""
    role: str = "assistant"
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: MemorySource = MemorySource.CONVERSATION
    importance: float = 0.5
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None

    def to_message(self) -> Dict[str, str]:
        """Convert to LLM message format.

        Returns:
            Dictionary with 'role' and 'content' keys suitable
            for LLM API calls.
        """
        return {
            "role": self.role,
            "content": self.content,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for persistence.

        Returns:
            Dictionary representation of the entry.
        """
        return {
            "id": self.id,
            "session_id": self.session_id,
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source.value,
            "importance": self.importance,
            "tags": self.tags,
            "metadata": self.metadata,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """Deserialize from dictionary.

        Args:
            data: Dictionary representation of the entry

        Returns:
            MemoryEntry instance
        """
        return cls(
            id=data.get("id", str(uuid4())),
            session_id=data.get("session_id", ""),
            content=data["content"],
            role=data.get("role", "assistant"),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if "timestamp" in data
                else datetime.now(timezone.utc)
            ),
            source=MemorySource(data.get("source", "conversation")),
            importance=data.get("importance", 0.5),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            embedding=data.get("embedding"),
        )

    @classmethod
    def from_message(
        cls,
        message: Dict[str, Any],
        session_id: str = "",
        source: MemorySource = MemorySource.CONVERSATION,
        importance: float = 0.5,
    ) -> "MemoryEntry":
        """Create from LLM message format.

        Args:
            message: Dictionary with 'role' and 'content'
            session_id: Session identifier
            source: Source of the memory
            importance: Importance score

        Returns:
            MemoryEntry instance
        """
        return cls(
            content=message.get("content", ""),
            role=message.get("role", "assistant"),
            session_id=session_id,
            source=source,
            importance=importance,
        )

    def matches_filter(self, filters: Optional[Dict[str, Any]] = None) -> bool:
        """Check if entry matches given filters.

        Args:
            filters: Dictionary of filter criteria

        Returns:
            True if entry matches all filters
        """
        if not filters:
            return True

        for key, value in filters.items():
            if key == "source":
                if isinstance(value, list):
                    if self.source not in [MemorySource(v) for v in value]:
                        return False
                elif self.source != MemorySource(value):
                    return False
            elif key == "role":
                if isinstance(value, list):
                    if self.role not in value:
                        return False
                elif self.role != value:
                    return False
            elif key == "tags":
                if isinstance(value, list):
                    if not any(tag in self.tags for tag in value):
                        return False
                elif value not in self.tags:
                    return False
            elif key == "min_importance":
                if self.importance < value:
                    return False
            elif key == "max_importance":
                if self.importance > value:
                    return False

        return True


@dataclass
class MemoryContext:
    """LLM-ready context built from memory entries.

    Represents a compiled context from retrieved memories,
    optimized for injection into LLM prompts with token
    budget awareness.

    Attributes:
        entries: List of retrieved memory entries
        summary: Optional summary of older/overflow entries
        total_tokens: Estimated token count of context
        entries_retrieved: Number of entries included
        entries_summarized: Number of entries summarized (overflow)
        retrieval_strategy: Strategy used to retrieve entries
        retrieval_query: Query used for retrieval (if any)
    """

    entries: List[MemoryEntry] = field(default_factory=list)
    summary: str = ""
    total_tokens: int = 0
    entries_retrieved: int = 0
    entries_summarized: int = 0
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.RECENCY
    retrieval_query: str = ""

    def to_system_prompt(self) -> str:
        """Convert to system prompt injection format.

        Creates a formatted string suitable for including in
        a system prompt, with summary (if any) followed by
        formatted entries.

        Returns:
            Formatted string for system prompt injection
        """
        parts = []

        if self.summary:
            parts.append("## Previous Context Summary\n")
            parts.append(self.summary)
            parts.append("\n")

        if self.entries:
            parts.append("## Relevant Memory\n")
            for entry in self.entries:
                role_label = entry.role.capitalize()
                parts.append(f"[{role_label}]: {entry.content}\n")

        return "".join(parts)

    def to_messages(self) -> List[Dict[str, str]]:
        """Convert to LLM messages format.

        Creates a list of message dictionaries suitable for
        including in the messages array of an LLM API call.

        Returns:
            List of message dictionaries with 'role' and 'content'
        """
        messages = []

        if self.summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Previous conversation summary: {self.summary}",
                }
            )

        for entry in self.entries:
            messages.append(entry.to_message())

        return messages

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of the context
        """
        return {
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.summary,
            "total_tokens": self.total_tokens,
            "entries_retrieved": self.entries_retrieved,
            "entries_summarized": self.entries_summarized,
            "retrieval_strategy": self.retrieval_strategy.value,
            "retrieval_query": self.retrieval_query,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryContext":
        """Deserialize from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            MemoryContext instance
        """
        return cls(
            entries=[MemoryEntry.from_dict(e) for e in data.get("entries", [])],
            summary=data.get("summary", ""),
            total_tokens=data.get("total_tokens", 0),
            entries_retrieved=data.get("entries_retrieved", 0),
            entries_summarized=data.get("entries_summarized", 0),
            retrieval_strategy=RetrievalStrategy(
                data.get("retrieval_strategy", "recency")
            ),
            retrieval_query=data.get("retrieval_query", ""),
        )

    @classmethod
    def empty(cls) -> "MemoryContext":
        """Create an empty context.

        Returns:
            Empty MemoryContext instance
        """
        return cls()

    @property
    def is_empty(self) -> bool:
        """Check if context is empty.

        Returns:
            True if no entries and no summary
        """
        return len(self.entries) == 0 and not self.summary


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.

    Uses simple character-based estimation: ~4 characters per token.
    This is a rough approximation suitable for budget planning.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    return len(text) // 4
