"""
Memory Agent - Conversation Continuity with BaseAgent

Demonstrates memory management for multi-turn conversations:
- Conversation history tracking
- Context-aware responses
- Session management
- Memory persistence (demo: in-memory dict)
- Uses async strategy by default for better concurrency
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


@dataclass
class MemoryConfig:
    """Configuration for memory agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 500
    max_history_turns: int = 10
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ConversationSignature(Signature):
    """Signature for conversation with memory."""

    message: str = InputField(desc="User's current message")
    conversation_history: str = InputField(
        desc="Previous conversation context", default=""
    )

    response: str = OutputField(desc="Agent's response considering history")
    memory_updated: bool = OutputField(desc="Whether memory was successfully updated")


class SimpleMemoryStore:
    """In-memory conversation storage."""

    def __init__(self, max_turns: int = 10):
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self.max_turns = max_turns

    def add_turn(self, session_id: str, role: str, content: str):
        """Add a conversation turn."""
        if session_id not in self.conversations:
            self.conversations[session_id] = []

        self.conversations[session_id].append(
            {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        )

        # Keep only last N turns
        if len(self.conversations[session_id]) > self.max_turns * 2:
            self.conversations[session_id] = self.conversations[session_id][
                -(self.max_turns * 2) :
            ]

    def get_history(self, session_id: str) -> str:
        """Get formatted conversation history."""
        if session_id not in self.conversations:
            return ""

        history_lines = []
        for turn in self.conversations[session_id]:
            history_lines.append(f"{turn['role']}: {turn['content']}")

        return "\n".join(history_lines)

    def clear_session(self, session_id: str):
        """Clear a conversation session."""
        if session_id in self.conversations:
            del self.conversations[session_id]


class MemoryAgent(BaseAgent):
    """
    Memory Agent with conversation continuity.

    Features:
    - Multi-turn conversation tracking
    - Context-aware responses
    - Session management
    - Automatic memory updates
    """

    def __init__(
        self, config: MemoryConfig, memory_store: Optional[SimpleMemoryStore] = None
    ):
        """Initialize memory agent."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Initialize BaseAgent with default async strategy (Task 0A.6)
        super().__init__(config=config, signature=ConversationSignature())

        self.memory_config = config
        self.memory_store = memory_store or SimpleMemoryStore(
            max_turns=config.max_history_turns
        )

    def chat(self, message: str, session_id: str = "default") -> Dict[str, Any]:
        """
        Chat with memory continuity.

        Args:
            message: User's message
            session_id: Conversation session identifier

        Returns:
            Dict with response and memory status
        """
        if not message or not message.strip():
            return {
                "response": "Please provide a message.",
                "memory_updated": False,
                "error": "INVALID_INPUT",
            }

        # Get conversation history
        history = self.memory_store.get_history(session_id)

        # Add user message to memory
        self.memory_store.add_turn(session_id, "user", message.strip())

        # Execute with history context
        result = self.run(message=message.strip(), conversation_history=history)

        # Add assistant response to memory
        if "response" in result:
            self.memory_store.add_turn(session_id, "assistant", result["response"])
            result["memory_updated"] = True

        return result

    def clear_memory(self, session_id: str = "default"):
        """Clear conversation memory for a session."""
        self.memory_store.clear_session(session_id)

    def get_conversation_count(self, session_id: str = "default") -> int:
        """Get number of turns in conversation."""
        if session_id not in self.memory_store.conversations:
            return 0
        return len(self.memory_store.conversations[session_id])
