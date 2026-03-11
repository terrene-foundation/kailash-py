"""
MemoryAgent - Production-Ready Conversation Agent with Memory

Zero-config usage:
    from kaizen.agents import MemoryAgent

    agent = MemoryAgent()
    result = agent.run(message="Hello, how are you?")
    print(result["response"])

Progressive configuration:
    agent = MemoryAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.7,
        max_history_turns=15
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4
    KAIZEN_TEMPERATURE=0.7
    KAIZEN_MAX_HISTORY_TURNS=15
"""

import os
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from kailash.nodes.base import NodeMetadata

if TYPE_CHECKING:
    from kaizen.tools.registry import ToolRegistry
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


@dataclass
class MemoryConfig:
    """
    Configuration for Memory Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.7"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "500"))
    )
    max_history_turns: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_HISTORY_TURNS", "10"))
    )
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ConversationSignature(Signature):
    """Signature for conversation with memory continuity."""

    message: str = InputField(desc="User's current message")
    conversation_history: str = InputField(
        desc="Previous conversation context", default=""
    )

    response: str = OutputField(desc="Agent's response considering history")
    memory_updated: bool = OutputField(desc="Whether memory was successfully updated")


class SimpleMemoryStore:
    """In-memory conversation storage for tracking multi-turn conversations."""

    def __init__(self, max_turns: int = 10):
        """
        Initialize memory store.

        Args:
            max_turns: Maximum number of conversation turns to keep per session
        """
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self.max_turns = max_turns

    def add_turn(self, session_id: str, role: str, content: str):
        """
        Add a conversation turn to session.

        Args:
            session_id: Unique session identifier
            role: Role of speaker ("user" or "assistant")
            content: Message content
        """
        if session_id not in self.conversations:
            self.conversations[session_id] = []

        self.conversations[session_id].append(
            {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        )

        # Keep only last N turns (user + assistant pairs)
        if len(self.conversations[session_id]) > self.max_turns * 2:
            self.conversations[session_id] = self.conversations[session_id][
                -(self.max_turns * 2) :
            ]

    def get_history(self, session_id: str) -> str:
        """
        Get formatted conversation history for session.

        Args:
            session_id: Unique session identifier

        Returns:
            Formatted conversation history as string
        """
        if session_id not in self.conversations:
            return ""

        history_lines = []
        for turn in self.conversations[session_id]:
            history_lines.append(f"{turn['role']}: {turn['content']}")

        return "\n".join(history_lines)

    def clear_session(self, session_id: str):
        """
        Clear conversation history for session.

        Args:
            session_id: Unique session identifier
        """
        if session_id in self.conversations:
            del self.conversations[session_id]


class MemoryAgent(BaseAgent):
    """
    Production-ready Memory Agent with conversation continuity.

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Multi-turn conversation tracking
    - Context-aware responses
    - Session management
    - Automatic memory updates
    - Async-first execution (AsyncSingleShotStrategy)

    Usage:
        # Zero-config (easiest)
        agent = MemoryAgent()
        result = agent.run(message="Hello!")
        print(result["response"])

        # With configuration
        agent = MemoryAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_history_turns=20
        )

        # Multi-turn conversation with session
        result = agent.run(message="My name is Alice", session_id="user_123")
        result = agent.run(message="What is my name?", session_id="user_123")

    Configuration:
        llm_provider: LLM provider (default: "openai", env: KAIZEN_LLM_PROVIDER)
        model: Model name (default: "gpt-3.5-turbo", env: KAIZEN_MODEL)
        temperature: Sampling temperature (default: 0.7, env: KAIZEN_TEMPERATURE)
        max_tokens: Maximum tokens (default: 500, env: KAIZEN_MAX_TOKENS)
        max_history_turns: Memory limit in turns (default: 10, env: KAIZEN_MAX_HISTORY_TURNS)
        timeout: Request timeout seconds (default: 30)
        retry_attempts: Retry count on failure (default: 3)
        provider_config: Additional provider-specific config (default: {})

    Returns:
        Dict with keys:
        - response: str - The agent's response
        - memory_updated: bool - Whether memory was updated
        - error: str (optional) - Error code if validation fails
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="MemoryAgent",
        description="Conversational agent with multi-turn memory and session management",
        version="1.0.0",
        tags={"ai", "kaizen", "memory", "conversation", "session"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_history_turns: Optional[int] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        memory_store: Optional[SimpleMemoryStore] = None,
        config: Optional[MemoryConfig] = None,
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        **kwargs,
    ):
        """
        Initialize Memory agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            max_history_turns: Override default max history turns
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            provider_config: Additional provider-specific configuration
            memory_store: Custom memory store instance (optional)
            config: Full config object (overrides individual params)
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = MemoryConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if max_history_turns is not None:
                config = replace(config, max_history_turns=max_history_turns)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or "timeout" not in config.provider_config
        ):
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # Initialize BaseAgent with auto-config extraction
        super().__init__(
            config=config,
            signature=ConversationSignature(),
            mcp_servers=mcp_servers,
            **kwargs,
            # strategy omitted - uses AsyncSingleShotStrategy by default
        )

        self.memory_config = config
        self.memory_store = memory_store or SimpleMemoryStore(
            max_turns=config.max_history_turns
        )
        self.tool_registry = tool_registry

    def run(
        self,
        message: str,
        session_id: str = "default",
        conversation_history: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Chat with memory continuity.

        Overrides BaseAgent.run() to add memory management and session tracking.

        Maintains conversation history across multiple turns within a session.
        Each session has independent conversation context.

        Args:
            message: User's message
            session_id: Conversation session identifier (default: "default")
            conversation_history: Optional conversation history (auto-loaded if not provided)
            **kwargs: Additional keyword arguments for BaseAgent.run()

        Returns:
            Dictionary containing:
            - response: The agent's response
            - memory_updated: Whether memory was updated
            - error: Optional error code if validation fails

        Example:
            >>> agent = MemoryAgent()
            >>> result = agent.run(message="My name is Bob", session_id="user_1")
            >>> result = agent.run(message="What is my name?", session_id="user_1")
            >>> print(result["response"])
            Your name is Bob.
        """
        # Input validation
        if not message or not message.strip():
            return {
                "response": "Please provide a message.",
                "memory_updated": False,
                "error": "INVALID_INPUT",
            }

        # Get conversation history (only if not provided)
        if not conversation_history:
            conversation_history = self.memory_store.get_history(session_id)

        # Add user message to memory
        self.memory_store.add_turn(session_id, "user", message.strip())

        # Execute with history context via BaseAgent
        result = super().run(
            message=message.strip(), conversation_history=conversation_history, **kwargs
        )

        # Add assistant response to memory
        if "response" in result:
            self.memory_store.add_turn(session_id, "assistant", result["response"])
            result["memory_updated"] = True

        return result

    def clear_memory(self, session_id: str = "default"):
        """
        Clear conversation memory for a session.

        Args:
            session_id: Conversation session identifier to clear (default: "default")

        Example:
            >>> agent = MemoryAgent()
            >>> agent.chat("Hello", session_id="session_1")
            >>> agent.clear_memory("session_1")
            >>> # Conversation history is now empty for session_1
        """
        self.memory_store.clear_session(session_id)

    def get_conversation_count(self, session_id: str = "default") -> int:
        """
        Get number of turns in conversation session.

        Args:
            session_id: Conversation session identifier (default: "default")

        Returns:
            Number of conversation turns (user + assistant messages)

        Example:
            >>> agent = MemoryAgent()
            >>> agent.chat("Hello", session_id="session_1")
            >>> count = agent.get_conversation_count("session_1")
            >>> print(count)  # Output: 2 (1 user + 1 assistant)
        """
        if session_id not in self.memory_store.conversations:
            return 0
        return len(self.memory_store.conversations[session_id])

    def chat(
        self, message: str, session_id: str = "default", **kwargs
    ) -> Dict[str, Any]:
        """
        Convenience method for conversation with memory continuity.

        Alias for run() - provided for API clarity.

        Args:
            message: The message to send
            session_id: Session identifier (default: "default")
            **kwargs: Additional keyword arguments

        Returns:
            Dict containing response and memory_updated fields

        Example:
            >>> agent = MemoryAgent()
            >>> result = agent.chat("Hello, how are you?")
            >>> print(result["response"])
        """
        return self.run(message=message, session_id=session_id, **kwargs)


# Convenience function for quick usage
def chat(message: str, session_id: str = "default", **kwargs) -> str:
    """
    Quick one-liner for conversation without creating an agent instance.

    Note: Creates a new agent for each call, so no memory continuity across calls.
    For multi-turn conversations, create a MemoryAgent instance instead.

    Args:
        message: The message to send
        session_id: Session identifier
        **kwargs: Optional configuration (llm_provider, model, temperature, etc.)

    Returns:
        The response string

    Example:
        >>> from kaizen.agents.specialized.memory_agent import chat
        >>> response = chat("Hello, how are you?")
        >>> print(response)
        I'm doing well, thank you!
    """
    agent = MemoryAgent(**kwargs)
    result = agent.run(message=message, session_id=session_id)
    return result.get("response", "No response generated")
