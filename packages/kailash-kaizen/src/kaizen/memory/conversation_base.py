"""
KaizenMemory: Abstract base class for conversation memory systems.

This module provides the foundational interface for all Kaizen conversation
memory implementations. All memory types (Buffer, Summary, Vector, KnowledgeGraph)
inherit from this base class.

Note: These are Kaizen-owned implementations, inspired by LangChain concepts
but NOT integrated with LangChain.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class KaizenMemory(ABC):
    """
    Abstract base class for conversation memory in Kaizen agents.

    All memory implementations must inherit from this class and implement
    the three core methods: load_context, save_turn, and clear.

    Memory implementations provide conversation context management for agents,
    enabling them to maintain conversation history, summaries, semantic search,
    and knowledge graphs across multiple turns.
    """

    @abstractmethod
    def load_context(self, session_id: str) -> Dict[str, Any]:
        """
        Load conversation context for a specific session.

        Args:
            session_id: Unique identifier for the conversation session

        Returns:
            Dictionary containing conversation context. Format varies by
            memory implementation:
            - BufferMemory: {"turns": [...], "turn_count": int}
            - SummaryMemory: {"summary": str, "recent_turns": [...]}
            - VectorMemory: {"relevant_turns": [...], "all_turns": [...]}
            - KnowledgeGraphMemory: {"entities": {...}, "relationships": [...]}

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Subclass must implement load_context()")

    @abstractmethod
    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save a conversation turn (user input + agent response) to memory.

        Args:
            session_id: Unique identifier for the conversation session
            turn: Dictionary containing conversation turn data with keys:
                - "user": User's input message
                - "agent": Agent's response message
                - "timestamp": ISO format timestamp (optional)
                - Additional metadata as needed by implementation

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Subclass must implement save_turn()")

    @abstractmethod
    def clear(self, session_id: str) -> None:
        """
        Clear all conversation history for a specific session.

        Args:
            session_id: Unique identifier for the conversation session

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Subclass must implement clear()")
