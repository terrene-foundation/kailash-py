"""KaizenSessionManager for session persistence.

Provides session management for Enterprise-App integration:
- Start/end sessions with state tracking
- Pause/resume capability
- Persistence to filesystem or DataFlow

See: TODO-204 Enterprise-App Streaming Integration
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state import (
    Message,
    SessionState,
    SessionStatus,
    SessionSummary,
    SubagentCall,
    ToolInvocation,
)

logger = logging.getLogger(__name__)


class SessionStorage(ABC):
    """Abstract base class for session storage backends."""

    @abstractmethod
    async def save(self, session_id: str, state: SessionState) -> None:
        """Save session state."""
        pass

    @abstractmethod
    async def load(self, session_id: str) -> Optional[SessionState]:
        """Load session state."""
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Delete session state."""
        pass

    @abstractmethod
    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        limit: int = 100,
    ) -> List[str]:
        """List session IDs with optional filters."""
        pass


class FilesystemSessionStorage(SessionStorage):
    """Filesystem-based session storage.

    Stores session state as JSON files in a directory.

    Example:
        >>> storage = FilesystemSessionStorage("./sessions")
        >>> await storage.save("session-123", state)
    """

    def __init__(self, directory: str):
        """Initialize with storage directory."""
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def _get_path(self, session_id: str) -> Path:
        """Get file path for session."""
        return self._directory / f"{session_id}.json"

    async def save(self, session_id: str, state: SessionState) -> None:
        """Save session state to JSON file."""
        path = self._get_path(session_id)
        data = state.to_dict()

        # Write atomically using temp file
        temp_path = path.with_suffix(".tmp")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: temp_path.write_text(json.dumps(data, indent=2)),
        )
        await loop.run_in_executor(None, lambda: temp_path.rename(path))

    async def load(self, session_id: str) -> Optional[SessionState]:
        """Load session state from JSON file."""
        path = self._get_path(session_id)
        if not path.exists():
            return None

        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, path.read_text)
            data = json.loads(text)
            return SessionState.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    async def delete(self, session_id: str) -> bool:
        """Delete session file."""
        path = self._get_path(session_id)
        if path.exists():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, path.unlink)
            return True
        return False

    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        limit: int = 100,
    ) -> List[str]:
        """List session IDs matching filters."""
        sessions = []

        for path in self._directory.glob("*.json"):
            if len(sessions) >= limit:
                break

            session_id = path.stem

            # Apply filters if provided
            if agent_id or status:
                state = await self.load(session_id)
                if state is None:
                    continue
                if agent_id and state.agent_id != agent_id:
                    continue
                if status and state.status != status:
                    continue

            sessions.append(session_id)

        return sessions


class InMemorySessionStorage(SessionStorage):
    """In-memory session storage for testing.

    Does not persist across restarts.
    """

    def __init__(self):
        """Initialize empty storage."""
        self._sessions: Dict[str, SessionState] = {}

    async def save(self, session_id: str, state: SessionState) -> None:
        """Save session state to memory."""
        self._sessions[session_id] = state

    async def load(self, session_id: str) -> Optional[SessionState]:
        """Load session state from memory."""
        return self._sessions.get(session_id)

    async def delete(self, session_id: str) -> bool:
        """Delete session from memory."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        limit: int = 100,
    ) -> List[str]:
        """List session IDs matching filters."""
        sessions = []
        for session_id, state in self._sessions.items():
            if len(sessions) >= limit:
                break
            if agent_id and state.agent_id != agent_id:
                continue
            if status and state.status != status:
                continue
            sessions.append(session_id)
        return sessions


class KaizenSessionManager:
    """
    Session manager for Enterprise-App integration.

    Provides:
    - Start/end session lifecycle
    - State persistence
    - Pause/resume capability
    - Metrics tracking

    Example:
        >>> manager = KaizenSessionManager()
        >>> session_id = await manager.start_session(
        ...     agent=my_agent,
        ...     trust_chain_id="chain-123",
        ...     metadata={"user_id": "user-456"},
        ... )
        >>>
        >>> # During execution
        >>> state = await manager.get_session_state(session_id)
        >>> state.add_message(Message(role="user", content="Hello"))
        >>> await manager.update_session(session_id, state)
        >>>
        >>> # End session
        >>> summary = await manager.end_session(session_id, "completed")
        >>> print(f"Total tokens: {summary.total_tokens}")
    """

    def __init__(
        self,
        storage: Optional[SessionStorage] = None,
        storage_directory: Optional[str] = None,
    ):
        """
        Initialize session manager.

        Args:
            storage: Optional storage backend. If None, uses filesystem storage.
            storage_directory: Directory for filesystem storage (default: ./sessions)
        """
        if storage is not None:
            self._storage = storage
        elif storage_directory:
            self._storage = FilesystemSessionStorage(storage_directory)
        else:
            # Default to temp directory
            default_dir = os.path.join(os.getcwd(), ".kaizen", "sessions")
            self._storage = FilesystemSessionStorage(default_dir)

    async def start_session(
        self,
        agent: Any,
        trust_chain_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        task: Optional[str] = None,
    ) -> str:
        """
        Start a new tracked session.

        Args:
            agent: The agent being executed
            trust_chain_id: Trust chain ID for delegation tracking
            metadata: Optional metadata to include in session
            session_id: Optional session ID (auto-generated if None)
            task: Optional task description

        Returns:
            session_id: The session ID for future reference
        """
        # Generate session ID if not provided
        session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"

        # Extract agent info
        agent_id = getattr(agent, "agent_id", None) or f"agent-{uuid.uuid4().hex[:8]}"
        agent_name = getattr(agent, "name", None) or agent.__class__.__name__

        # Create session state
        state = SessionState(
            session_id=session_id,
            agent_id=agent_id,
            trust_chain_id=trust_chain_id,
            status=SessionStatus.ACTIVE,
            metadata=metadata or {},
            agent_name=agent_name,
            task=task,
        )

        # Save initial state
        await self._storage.save(session_id, state)

        logger.info(f"Started session {session_id} for agent {agent_id}")
        return session_id

    async def get_session_state(self, session_id: str) -> Optional[SessionState]:
        """
        Get current session state.

        Args:
            session_id: The session ID

        Returns:
            SessionState or None if session not found
        """
        return await self._storage.load(session_id)

    async def update_session(self, session_id: str, state: SessionState) -> None:
        """
        Update session state.

        Args:
            session_id: The session ID
            state: The updated session state
        """
        await self._storage.save(session_id, state)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a message to the session.

        Args:
            session_id: The session ID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata
        """
        state = await self._storage.load(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        message = Message(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        state.add_message(message)
        await self._storage.save(session_id, state)

    async def add_tool_invocation(
        self,
        session_id: str,
        tool_name: str,
        tool_call_id: str,
        input: Dict[str, Any],
        output: Any = None,
        error: Optional[str] = None,
        duration_ms: int = 0,
    ) -> None:
        """
        Add a tool invocation record to the session.

        Args:
            session_id: The session ID
            tool_name: Name of the tool
            tool_call_id: Unique ID for this tool call
            input: Tool input parameters
            output: Tool output (optional)
            error: Error message if failed (optional)
            duration_ms: Execution duration in milliseconds
        """
        state = await self._storage.load(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        invocation = ToolInvocation(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            input=input,
            output=output,
            error=error,
            ended_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
        )
        state.add_tool_invocation(invocation)
        await self._storage.save(session_id, state)

    async def add_subagent_call(
        self,
        session_id: str,
        subagent_id: str,
        subagent_name: str,
        task: str,
        parent_agent_id: str,
        trust_chain_id: str,
        capabilities: Optional[List[str]] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Add a subagent call record to the session.

        Args:
            session_id: The session ID
            subagent_id: Subagent unique ID
            subagent_name: Subagent name
            task: Delegated task description
            parent_agent_id: Parent agent ID
            trust_chain_id: Trust chain ID
            capabilities: Subagent capabilities
            model: Model used by subagent
        """
        state = await self._storage.load(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        call = SubagentCall(
            subagent_id=subagent_id,
            subagent_name=subagent_name,
            task=task,
            parent_agent_id=parent_agent_id,
            trust_chain_id=trust_chain_id,
            capabilities=capabilities or [],
            model=model,
        )
        state.add_subagent_call(call)
        await self._storage.save(session_id, state)

    async def update_metrics(
        self,
        session_id: str,
        tokens_added: int = 0,
        cost_added_usd: float = 0.0,
        cycles_added: int = 0,
    ) -> None:
        """
        Update session metrics.

        Args:
            session_id: The session ID
            tokens_added: Tokens to add
            cost_added_usd: Cost to add in USD
            cycles_added: Cycles to add
        """
        state = await self._storage.load(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        state.update_metrics(
            tokens_added=tokens_added,
            cost_added_usd=cost_added_usd,
            cycles_added=cycles_added,
        )
        await self._storage.save(session_id, state)

    async def pause_session(self, session_id: str) -> None:
        """
        Pause a session.

        Args:
            session_id: The session ID
        """
        state = await self._storage.load(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        state.status = SessionStatus.PAUSED
        state.last_activity_at = datetime.now(timezone.utc).isoformat()
        await self._storage.save(session_id, state)

        logger.info(f"Paused session {session_id}")

    async def resume_session(self, session_id: str) -> SessionState:
        """
        Resume a paused session.

        Args:
            session_id: The session ID

        Returns:
            The session state
        """
        state = await self._storage.load(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        if state.status != SessionStatus.PAUSED:
            raise ValueError(
                f"Session {session_id} is not paused (status: {state.status})"
            )

        state.status = SessionStatus.ACTIVE
        state.last_activity_at = datetime.now(timezone.utc).isoformat()
        await self._storage.save(session_id, state)

        logger.info(f"Resumed session {session_id}")
        return state

    async def end_session(
        self,
        session_id: str,
        status: str,
        final_output: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> SessionSummary:
        """
        End a session and return summary.

        Args:
            session_id: The session ID
            status: Final status (completed, failed, interrupted)
            final_output: Optional final output text
            error_message: Optional error message

        Returns:
            SessionSummary with totals and metrics
        """
        state = await self._storage.load(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        # Update state
        state.status = SessionStatus(status)
        state.ended_at = datetime.now(timezone.utc).isoformat()
        await self._storage.save(session_id, state)

        # Create summary
        summary = SessionSummary.from_session_state(
            state,
            final_output=final_output,
            error_message=error_message,
        )

        logger.info(
            f"Ended session {session_id} with status {status}, "
            f"tokens: {summary.total_tokens}, cost: ${summary.total_cost_usd:.4f}"
        )

        return summary

    async def list_sessions(
        self,
        agent_id: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        limit: int = 100,
    ) -> List[str]:
        """
        List session IDs with optional filters.

        Args:
            agent_id: Filter by agent ID
            status: Filter by status
            limit: Maximum number of sessions to return

        Returns:
            List of session IDs
        """
        return await self._storage.list_sessions(
            agent_id=agent_id,
            status=status,
            limit=limit,
        )

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: The session ID

        Returns:
            True if deleted, False if not found
        """
        return await self._storage.delete(session_id)


__all__ = [
    "SessionStorage",
    "FilesystemSessionStorage",
    "InMemorySessionStorage",
    "KaizenSessionManager",
]
