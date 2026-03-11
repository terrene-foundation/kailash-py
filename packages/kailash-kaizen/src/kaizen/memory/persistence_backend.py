"""
Persistence backend protocol for conversation memory storage.

Provides a pluggable interface for different storage backends (PostgreSQL, Redis, MongoDB, etc.)
to support PersistentBufferMemory and other persistent memory types.
"""

from typing import Any, Dict, List, Optional, Protocol


class PersistenceBackend(Protocol):
    """
    Protocol for persistence backends.

    Implementations provide storage for conversation turns across sessions.
    All methods must be thread-safe.
    """

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save a single conversation turn.

        Args:
            session_id: Unique session identifier
            turn: Turn data with keys:
                - user: User message (str)
                - agent: Agent response (str)
                - timestamp: ISO format timestamp (str)
                - metadata: Optional metadata (dict)

        Raises:
            Exception: If save fails
        """
        ...

    def load_turns(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Load conversation turns for a session.

        Args:
            session_id: Unique session identifier
            limit: Maximum number of turns to load (None = all)

        Returns:
            List of turns in chronological order (oldest first)
            Each turn contains: user, agent, timestamp, metadata

        Returns:
            Empty list if session not found
        """
        ...

    def clear_session(self, session_id: str) -> None:
        """
        Clear all turns for a session.

        Args:
            session_id: Unique session identifier
        """
        ...

    def session_exists(self, session_id: str) -> bool:
        """
        Check if a session exists.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session has any turns, False otherwise
        """
        ...

    def get_session_metadata(self, session_id: str) -> Dict[str, Any]:
        """
        Get metadata about a session.

        Args:
            session_id: Unique session identifier

        Returns:
            Dictionary with keys:
                - turn_count: Total number of turns (int)
                - created_at: First turn timestamp (datetime)
                - updated_at: Last turn timestamp (datetime)

        Returns:
            Empty dict if session not found
        """
        ...
