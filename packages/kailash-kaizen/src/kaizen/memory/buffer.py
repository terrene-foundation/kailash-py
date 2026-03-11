"""
BufferMemory: Full conversation history storage.

This is the simplest memory implementation - stores complete conversation
history in a list. Optionally supports max_turns limit with FIFO behavior.

Example:
    >>> from kaizen.memory.buffer import BufferMemory
    >>> memory = BufferMemory(max_turns=10)
    >>> memory.save_turn("session1", {"user": "Hello", "agent": "Hi there!"})
    >>> context = memory.load_context("session1")
    >>> print(context["turn_count"])
    1

Note: This is a Kaizen-owned implementation, inspired by LangChain's
ConversationBufferMemory but NOT integrated with LangChain.
"""

from typing import Any, Dict, List, Optional

from kaizen.memory.conversation_base import KaizenMemory


class BufferMemory(KaizenMemory):
    """
    Full conversation history storage with optional max_turns limit.

    Stores all conversation turns in chronological order. If max_turns is
    specified, enforces FIFO (First-In-First-Out) behavior by removing
    oldest turns when the limit is exceeded.

    Attributes:
        max_turns: Maximum number of turns to keep. None means unlimited.
        _sessions: Internal storage mapping session_id -> list of turns
    """

    def __init__(self, max_turns: Optional[int] = None):
        """
        Initialize BufferMemory.

        Args:
            max_turns: Optional maximum number of turns to keep per session.
                      If None, keeps all turns. If 0, keeps no history.
                      When limit is exceeded, oldest turns are removed (FIFO).
        """
        self.max_turns = max_turns
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    def load_context(self, session_id: str) -> Dict[str, Any]:
        """
        Load conversation context for a specific session.

        Args:
            session_id: Unique identifier for the conversation session

        Returns:
            Dictionary with:
                - "turns": List of conversation turns (chronological order)
                - "turn_count": Number of turns in the buffer
        """
        turns = self._sessions.get(session_id, [])
        return {"turns": turns, "turn_count": len(turns)}

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save a conversation turn to the buffer.

        Args:
            session_id: Unique identifier for the conversation session
            turn: Dictionary containing conversation turn data.
                 Typically includes "user", "agent", "timestamp" keys,
                 but can include any metadata.
        """
        # If max_turns is 0, don't store anything
        if self.max_turns == 0:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            return

        # Initialize session if it doesn't exist
        if session_id not in self._sessions:
            self._sessions[session_id] = []

        # Add the turn
        self._sessions[session_id].append(turn)

        # Apply max_turns limit (FIFO)
        if (
            self.max_turns is not None
            and len(self._sessions[session_id]) > self.max_turns
        ):
            # Remove oldest turns to maintain max_turns limit
            self._sessions[session_id] = self._sessions[session_id][-self.max_turns :]

    def clear(self, session_id: str) -> None:
        """
        Clear all conversation history for a specific session.

        Args:
            session_id: Unique identifier for the conversation session
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
