"""
SummaryMemory: LLM-generated conversation summaries with recent verbatim turns.

This memory implementation maintains a rolling summary of conversation history
using LLM summarization, while keeping the most recent N turns verbatim for
immediate context.

Example:
    >>> from kaizen.memory.summary import SummaryMemory
    >>> memory = SummaryMemory(keep_recent=5)
    >>> for i in range(10):
    ...     memory.save_turn("session1", {"user": f"Q{i}", "agent": f"A{i}"})
    >>> context = memory.load_context("session1")
    >>> print(len(context["recent_turns"]))  # 5 (most recent)
    5
    >>> print(context["summary"])  # Summary of first 5 turns
    Summary of 5 conversation turns

Note: This is a Kaizen-owned implementation, inspired by LangChain's
ConversationSummaryMemory but NOT integrated with LangChain.
"""

from typing import Any, Callable, Dict, List, Optional

from kaizen.memory.conversation_base import KaizenMemory


class SummaryMemory(KaizenMemory):
    """
    LLM-generated conversation summaries with recent verbatim turns.

    Maintains a two-tier memory structure:
    1. Summary: LLM-generated summary of older conversation turns
    2. Recent Turns: Last N turns stored verbatim for immediate context

    When new turns exceed the keep_recent limit, the oldest turn is
    removed from recent_turns and incorporated into the summary.

    Attributes:
        keep_recent: Number of recent turns to keep verbatim (default: 5)
        llm_summarizer: Function to generate summaries from turns
        _sessions: Internal storage mapping session_id -> session data
    """

    def __init__(
        self,
        keep_recent: int = 5,
        llm_summarizer: Optional[Callable[[List[Dict[str, Any]]], str]] = None,
    ):
        """
        Initialize SummaryMemory.

        Args:
            keep_recent: Number of recent turns to keep verbatim (default: 5).
                        If 0, all turns are immediately summarized.
            llm_summarizer: Optional custom summarizer function that takes
                           a list of turns and returns a summary string.
                           If None, uses default mock summarizer.
        """
        self.keep_recent = keep_recent
        self.llm_summarizer = llm_summarizer or self._default_summarizer
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _default_summarizer(self, turns: List[Dict[str, Any]]) -> str:
        """
        Default mock summarizer for testing.

        In production, this would call an actual LLM to generate summaries.
        For testing/development, it creates a simple formatted summary.

        Args:
            turns: List of conversation turns to summarize

        Returns:
            Summary string
        """
        if not turns:
            return ""

        # Simple mock summary
        turn_count = len(turns)
        user_messages = [turn.get("user", "") for turn in turns]
        return f"Summary of {turn_count} conversation turns: {', '.join(user_messages[:3])}..."

    def load_context(self, session_id: str) -> Dict[str, Any]:
        """
        Load conversation context for a specific session.

        Args:
            session_id: Unique identifier for the conversation session

        Returns:
            Dictionary with:
                - "summary": LLM-generated summary of older turns
                - "recent_turns": List of most recent turns (verbatim)
                - "turn_count": Total number of turns processed
        """
        session = self._sessions.get(
            session_id, {"summary": "", "recent_turns": [], "turn_count": 0}
        )

        return {
            "summary": session.get("summary", ""),
            "recent_turns": session.get("recent_turns", []),
            "turn_count": session.get("turn_count", 0),
        }

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save a conversation turn, potentially triggering summarization.

        When the number of recent turns exceeds keep_recent, the oldest
        turn is removed and incorporated into the summary via LLM.

        Args:
            session_id: Unique identifier for the conversation session
            turn: Dictionary containing conversation turn data
        """
        # Initialize session if it doesn't exist
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "summary": "",
                "recent_turns": [],
                "turn_count": 0,
            }

        # Add turn to recent_turns
        self._sessions[session_id]["recent_turns"].append(turn)
        self._sessions[session_id]["turn_count"] += 1

        # If recent_turns exceeds keep_recent, summarize oldest and update summary
        if len(self._sessions[session_id]["recent_turns"]) > self.keep_recent:
            # Remove oldest turn
            oldest_turn = self._sessions[session_id]["recent_turns"].pop(0)

            # Generate new summary incorporating the old turn
            # In a real implementation, this would pass the old summary + new turn to LLM
            # For now, we'll append to summary
            old_summary = self._sessions[session_id]["summary"]
            turn_summary = self.llm_summarizer([oldest_turn])

            if old_summary:
                # Combine old summary with new turn summary
                # In production, this would be a smarter LLM-based merge
                self._sessions[session_id][
                    "summary"
                ] = f"{old_summary} | {turn_summary}"
            else:
                self._sessions[session_id]["summary"] = turn_summary

    def clear(self, session_id: str) -> None:
        """
        Clear all conversation history for a specific session.

        Removes both the summary and all recent turns.

        Args:
            session_id: Unique identifier for the conversation session
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
