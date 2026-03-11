"""
Session management for Nexus multi-channel deployments.

Provides cross-channel session consistency, state synchronization, and
memory pool integration for Kaizen agents deployed via Nexus.

Phase 3 of TODO-149: Unified Session Management
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4


@dataclass
class CrossChannelSession:
    """
    Represents a user session across multiple Nexus channels.

    A session maintains consistent state whether accessed via API, CLI, or MCP.
    Enables:
    - State persistence across channels
    - Conversation continuity
    - Agent memory coordination
    - Multi-channel collaboration

    Attributes:
        session_id: Unique session identifier
        user_id: User identifier
        created_at: Session creation timestamp
        last_accessed: Last access timestamp
        expires_at: Session expiration timestamp
        state: Session state dictionary (shared across channels)
        channel_activity: Channel-specific activity tracking
        memory_pool_id: Optional memory pool binding

    Example:
        >>> session = CrossChannelSession(user_id="user-123")
        >>> session.update_state({"message": "Hello"}, channel="api")
        >>> state = session.get_state(channel="cli")
        >>> print(state["message"])
        "Hello"
    """

    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    # Session state (shared across channels)
    state: Dict[str, Any] = field(default_factory=dict)

    # Channel-specific activity tracking
    channel_activity: Dict[str, datetime] = field(default_factory=dict)

    # Memory pool binding (optional)
    memory_pool_id: Optional[str] = None

    def __post_init__(self):
        """Initialize session with expiration."""
        if self.expires_at is None:
            # Default 1 hour session expiration
            self.expires_at = self.created_at + timedelta(hours=1)

    def is_expired(self) -> bool:
        """
        Check if session has expired.

        Returns:
            True if session has expired, False otherwise
        """
        return datetime.now() > self.expires_at

    def refresh(self, channel: str = None):
        """
        Refresh session (extend expiration).

        Updates last_accessed timestamp and extends expiration by 1 hour.
        Optionally tracks channel activity.

        Args:
            channel: Optional channel name (api/cli/mcp)
        """
        self.last_accessed = datetime.now()
        self.expires_at = datetime.now() + timedelta(hours=1)

        if channel:
            self.channel_activity[channel] = datetime.now()

    def update_state(self, updates: Dict[str, Any], channel: str = None):
        """
        Update session state from a specific channel.

        Merges updates into existing state and refreshes session.

        Args:
            updates: State updates to apply
            channel: Optional channel making the update (api/cli/mcp)
        """
        self.state.update(updates)
        self.refresh(channel)

    def get_state(self, channel: str = None) -> Dict[str, Any]:
        """
        Get session state for a specific channel.

        Returns a copy of the state to prevent external modification.
        Refreshes session and tracks channel activity.

        Args:
            channel: Optional channel requesting state (api/cli/mcp)

        Returns:
            Copy of session state dictionary
        """
        self.refresh(channel)
        return self.state.copy()


class NexusSessionManager:
    """
    Manages sessions across all Nexus channels.

    Provides:
    - Session creation and lifecycle management
    - Cross-channel state synchronization
    - Session expiration and cleanup
    - Memory pool coordination
    - Optional DataFlow persistence

    The session manager maintains a registry of active sessions and
    automatically cleans up expired sessions at regular intervals.
    When a storage backend is configured, sessions are persisted to
    the database for durability across restarts.

    Attributes:
        sessions: Dictionary mapping session IDs to CrossChannelSession instances
        cleanup_interval: Seconds between automatic cleanup cycles
        storage: Optional DataFlow storage backend

    Example:
        >>> manager = NexusSessionManager()
        >>> session = manager.create_session(user_id="user-123")
        >>> manager.update_session_state(session.session_id, {"key": "value"})
        >>> state = manager.get_session_state(session.session_id)
        >>> print(state["key"])
        "value"

    Example with persistence:
        >>> from kaizen.integrations.nexus.storage import SessionStorage
        >>> from dataflow import DataFlow
        >>> db = DataFlow("postgresql://...")
        >>> storage = SessionStorage(db)
        >>> manager = NexusSessionManager(storage_backend=storage)
        >>> session = await manager.create_session_async(user_id="user-123")
    """

    def __init__(self, cleanup_interval: int = 300, storage_backend=None):
        """
        Initialize session manager.

        Args:
            cleanup_interval: Seconds between cleanup cycles (default: 5 minutes)
            storage_backend: Optional SessionStorage backend for DataFlow persistence
                           (uses in-memory storage if None)
        """
        self.sessions: Dict[str, CrossChannelSession] = {}
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = datetime.now()
        self.storage = storage_backend

    def create_session(
        self, session_id: str = None, user_id: str = "", ttl_hours: int = 1
    ) -> CrossChannelSession:
        """
        Create a new cross-channel session.

        Args:
            session_id: Optional session ID (auto-generated if not provided)
            user_id: User identifier
            ttl_hours: Session time-to-live in hours (default: 1)

        Returns:
            Created CrossChannelSession instance

        Example:
            >>> manager = NexusSessionManager()
            >>> session = manager.create_session(user_id="user-123", ttl_hours=2)
            >>> print(session.user_id)
            "user-123"
        """
        session = CrossChannelSession(
            session_id=session_id or str(uuid4()),
            user_id=user_id,
            expires_at=datetime.now() + timedelta(hours=ttl_hours),
        )

        self.sessions[session.session_id] = session
        self._maybe_cleanup()

        return session

    def get_session(self, session_id: str) -> Optional[CrossChannelSession]:
        """
        Get existing session by ID.

        Automatically removes expired sessions.

        Args:
            session_id: Session identifier

        Returns:
            CrossChannelSession if found and not expired, None otherwise

        Example:
            >>> manager = NexusSessionManager()
            >>> session = manager.create_session(user_id="user-123")
            >>> retrieved = manager.get_session(session.session_id)
            >>> print(retrieved.user_id)
            "user-123"
        """
        session = self.sessions.get(session_id)

        if session and session.is_expired():
            # Clean up expired session
            del self.sessions[session_id]
            return None

        return session

    def update_session_state(
        self, session_id: str, updates: Dict[str, Any], channel: str = None
    ) -> bool:
        """
        Update session state from a specific channel.

        Args:
            session_id: Session identifier
            updates: State updates to apply
            channel: Channel making the update (api/cli/mcp)

        Returns:
            True if update successful, False if session not found

        Example:
            >>> manager = NexusSessionManager()
            >>> session = manager.create_session(user_id="user-123")
            >>> success = manager.update_session_state(
            ...     session.session_id,
            ...     {"message": "Hello"},
            ...     channel="api"
            ... )
            >>> print(success)
            True
        """
        session = self.get_session(session_id)

        if not session:
            return False

        session.update_state(updates, channel)
        return True

    def get_session_state(
        self, session_id: str, channel: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get session state for a specific channel.

        Args:
            session_id: Session identifier
            channel: Channel requesting state (api/cli/mcp)

        Returns:
            Session state dict if found, None otherwise

        Example:
            >>> manager = NexusSessionManager()
            >>> session = manager.create_session(user_id="user-123")
            >>> manager.update_session_state(session.session_id, {"key": "value"})
            >>> state = manager.get_session_state(session.session_id, channel="cli")
            >>> print(state["key"])
            "value"
        """
        session = self.get_session(session_id)

        if not session:
            return None

        return session.get_state(channel)

    def bind_memory_pool(self, session_id: str, memory_pool_id: str) -> bool:
        """
        Bind session to a SharedMemoryPool.

        Enables memory sharing across agents within the same session.

        Args:
            session_id: Session identifier
            memory_pool_id: Memory pool identifier

        Returns:
            True if binding successful, False if session not found

        Example:
            >>> manager = NexusSessionManager()
            >>> session = manager.create_session(user_id="user-123")
            >>> success = manager.bind_memory_pool(session.session_id, "pool-456")
            >>> print(success)
            True
        """
        session = self.get_session(session_id)

        if not session:
            return False

        session.memory_pool_id = memory_pool_id
        return True

    def cleanup_expired_sessions(self) -> int:
        """
        Remove all expired sessions.

        Called automatically at regular intervals based on cleanup_interval.

        Returns:
            Number of sessions cleaned up

        Example:
            >>> manager = NexusSessionManager()
            >>> session = manager.create_session(user_id="user-123", ttl_hours=0)
            >>> session.expires_at = datetime.now() - timedelta(seconds=1)
            >>> count = manager.cleanup_expired_sessions()
            >>> print(count)
            1
        """
        expired = [
            sid for sid, session in self.sessions.items() if session.is_expired()
        ]

        for session_id in expired:
            del self.sessions[session_id]

        self._last_cleanup = datetime.now()
        return len(expired)

    def _maybe_cleanup(self):
        """Run cleanup if interval has passed."""
        if self.cleanup_interval and datetime.now() - self._last_cleanup > timedelta(
            seconds=self.cleanup_interval
        ):
            self.cleanup_expired_sessions()

    def get_session_metrics(self) -> Dict[str, Any]:
        """
        Get session metrics for monitoring.

        Returns:
            Dictionary with session statistics:
            - active_sessions: Number of active sessions
            - total_sessions: Total sessions created (active + expired)
            - average_ttl_seconds: Average session TTL
            - channels_used: Set of channels with activity

        Example:
            >>> manager = NexusSessionManager()
            >>> session = manager.create_session(user_id="user-123")
            >>> metrics = manager.get_session_metrics()
            >>> print(metrics['active_sessions'])
            1
        """
        active_sessions = [s for s in self.sessions.values() if not s.is_expired()]

        # Collect channel usage
        channels_used = set()
        total_ttl = 0

        for session in active_sessions:
            channels_used.update(session.channel_activity.keys())
            ttl_seconds = (session.expires_at - session.created_at).total_seconds()
            total_ttl += ttl_seconds

        avg_ttl = total_ttl / len(active_sessions) if active_sessions else 0

        return {
            "active_sessions": len(active_sessions),
            "total_sessions": len(self.sessions),
            "average_ttl_seconds": avg_ttl,
            "channels_used": list(channels_used),
        }

    # =========================================================================
    # Async methods for persistence (when storage backend is configured)
    # =========================================================================

    async def create_session_async(
        self, session_id: str = None, user_id: str = "", ttl_hours: int = 1
    ) -> CrossChannelSession:
        """
        Create a new cross-channel session with optional persistence.

        Async version that persists to storage backend if configured.

        Args:
            session_id: Optional session ID (auto-generated if not provided)
            user_id: User identifier
            ttl_hours: Session time-to-live in hours (default: 1)

        Returns:
            Created CrossChannelSession instance

        Example:
            >>> manager = NexusSessionManager(storage_backend=storage)
            >>> session = await manager.create_session_async(user_id="user-123")
        """
        session = self.create_session(session_id, user_id, ttl_hours)

        if self.storage:
            await self.storage.save(session)

        return session

    async def update_session_state_async(
        self, session_id: str, updates: Dict[str, Any], channel: str = None
    ) -> bool:
        """
        Update session state with optional persistence.

        Async version that persists to storage backend if configured.

        Args:
            session_id: Session identifier
            updates: State updates to apply
            channel: Channel making the update (api/cli/mcp)

        Returns:
            True if update successful, False if session not found
        """
        success = self.update_session_state(session_id, updates, channel)

        if success and self.storage:
            session = self.get_session(session_id)
            if session:
                await self.storage.update(session)

        return success

    async def bind_memory_pool_async(
        self, session_id: str, memory_pool_id: str
    ) -> bool:
        """
        Bind session to a SharedMemoryPool with optional persistence.

        Async version that persists to storage backend if configured.

        Args:
            session_id: Session identifier
            memory_pool_id: Memory pool identifier

        Returns:
            True if binding successful, False if session not found
        """
        success = self.bind_memory_pool(session_id, memory_pool_id)

        if success and self.storage:
            session = self.get_session(session_id)
            if session:
                await self.storage.update(session)

        return success

    async def delete_session_async(self, session_id: str) -> bool:
        """
        Delete a session with optional persistence.

        Async version that removes from storage backend if configured.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not found
        """
        if session_id in self.sessions:
            del self.sessions[session_id]

            if self.storage:
                await self.storage.delete(session_id)

            return True

        return False

    async def load_session_async(
        self, session_id: str
    ) -> Optional[CrossChannelSession]:
        """
        Load a session from storage backend.

        Checks in-memory cache first, then falls back to storage.
        Caches loaded session in memory.

        Args:
            session_id: Session identifier

        Returns:
            CrossChannelSession if found, None otherwise
        """
        # Check in-memory cache first
        session = self.get_session(session_id)
        if session:
            return session

        # Load from storage if available
        if self.storage:
            session = await self.storage.load(session_id)
            if session and not session.is_expired():
                # Cache in memory
                self.sessions[session_id] = session
                return session
            elif session and session.is_expired():
                # Clean up expired session from storage
                await self.storage.delete(session_id)

        return None

    async def cleanup_expired_sessions_async(self) -> int:
        """
        Remove expired sessions with optional persistence.

        Async version that cleans up from storage backend if configured.

        Returns:
            Number of sessions cleaned up
        """
        count = self.cleanup_expired_sessions()

        if self.storage:
            # Also cleanup from persistent storage
            storage_count = await self.storage.cleanup_expired()
            count = max(count, storage_count)  # Return higher count

        return count
