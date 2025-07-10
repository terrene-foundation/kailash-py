"""Session management for cross-channel communication."""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """Session status states."""

    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    TERMINATED = "terminated"


@dataclass
class CrossChannelSession:
    """Represents a session that can span multiple channels."""

    session_id: str
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: SessionStatus = SessionStatus.ACTIVE

    # Channel tracking
    active_channels: Set[str] = field(default_factory=set)
    channel_contexts: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Session data
    shared_data: Dict[str, Any] = field(default_factory=dict)
    workflow_states: Dict[str, Any] = field(default_factory=dict)

    # Event tracking
    event_history: List[Dict[str, Any]] = field(default_factory=list)
    max_history_size: int = 1000

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()
        if self.status == SessionStatus.IDLE:
            self.status = SessionStatus.ACTIVE

    def add_channel(
        self, channel_name: str, initial_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a channel to this session.

        Args:
            channel_name: Name of the channel to add
            initial_context: Initial context data for the channel
        """
        self.active_channels.add(channel_name)
        if initial_context:
            self.channel_contexts[channel_name] = initial_context.copy()
        else:
            self.channel_contexts[channel_name] = {}
        self.touch()
        logger.debug(f"Added channel {channel_name} to session {self.session_id}")

    def remove_channel(self, channel_name: str) -> None:
        """Remove a channel from this session.

        Args:
            channel_name: Name of the channel to remove
        """
        self.active_channels.discard(channel_name)
        self.channel_contexts.pop(channel_name, None)
        logger.debug(f"Removed channel {channel_name} from session {self.session_id}")

    def update_channel_context(
        self, channel_name: str, context_updates: Dict[str, Any]
    ) -> None:
        """Update context data for a specific channel.

        Args:
            channel_name: Name of the channel
            context_updates: Context updates to apply
        """
        if channel_name not in self.channel_contexts:
            self.channel_contexts[channel_name] = {}

        self.channel_contexts[channel_name].update(context_updates)
        self.touch()

    def get_channel_context(self, channel_name: str) -> Dict[str, Any]:
        """Get context data for a specific channel.

        Args:
            channel_name: Name of the channel

        Returns:
            Channel context data
        """
        return self.channel_contexts.get(channel_name, {}).copy()

    def set_shared_data(self, key: str, value: Any) -> None:
        """Set shared data accessible across all channels.

        Args:
            key: Data key
            value: Data value
        """
        self.shared_data[key] = value
        self.touch()

    def get_shared_data(self, key: str, default: Any = None) -> Any:
        """Get shared data.

        Args:
            key: Data key
            default: Default value if key not found

        Returns:
            Shared data value
        """
        return self.shared_data.get(key, default)

    def add_event(self, event: Dict[str, Any]) -> None:
        """Add an event to the session history.

        Args:
            event: Event data to add
        """
        event_record = {
            "timestamp": time.time(),
            "session_id": self.session_id,
            **event,
        }

        self.event_history.append(event_record)

        # Maintain max history size
        if len(self.event_history) > self.max_history_size:
            self.event_history = self.event_history[-self.max_history_size :]

        self.touch()

    def is_expired(self, timeout: int = 3600) -> bool:
        """Check if the session has expired.

        Args:
            timeout: Session timeout in seconds

        Returns:
            True if session has expired
        """
        if self.expires_at:
            return time.time() > self.expires_at

        return (time.time() - self.last_activity) > timeout

    def extend_expiry(self, additional_seconds: int = 3600) -> None:
        """Extend session expiry time.

        Args:
            additional_seconds: Additional seconds to extend
        """
        if self.expires_at:
            self.expires_at += additional_seconds
        else:
            self.expires_at = time.time() + additional_seconds
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "expires_at": self.expires_at,
            "status": self.status.value,
            "active_channels": list(self.active_channels),
            "channel_contexts": self.channel_contexts,
            "shared_data": self.shared_data,
            "workflow_states": self.workflow_states,
            "event_count": len(self.event_history),
        }


class SessionManager:
    """Manages cross-channel sessions for the Nexus framework."""

    def __init__(self, default_timeout: int = 3600, cleanup_interval: int = 300):
        """Initialize session manager.

        Args:
            default_timeout: Default session timeout in seconds
            cleanup_interval: Interval for cleanup task in seconds
        """
        self.default_timeout = default_timeout
        self.cleanup_interval = cleanup_interval
        self._sessions: Dict[str, CrossChannelSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the session manager."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Session manager stopped")

    def create_session(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> CrossChannelSession:
        """Create a new session.

        Args:
            user_id: Optional user ID for the session
            session_id: Optional custom session ID
            timeout: Optional custom timeout

        Returns:
            New CrossChannelSession instance
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        if session_id in self._sessions:
            raise ValueError(f"Session {session_id} already exists")

        session = CrossChannelSession(session_id=session_id, user_id=user_id)

        if timeout:
            session.extends_at = time.time() + timeout

        self._sessions[session_id] = session
        logger.info(f"Created session {session_id} for user {user_id}")

        return session

    def get_session(self, session_id: str) -> Optional[CrossChannelSession]:
        """Get an existing session.

        Args:
            session_id: Session ID to retrieve

        Returns:
            CrossChannelSession if found, None otherwise
        """
        session = self._sessions.get(session_id)

        if session and session.is_expired(self.default_timeout):
            self.terminate_session(session_id)
            return None

        return session

    def get_or_create_session(
        self, session_id: str, user_id: Optional[str] = None
    ) -> CrossChannelSession:
        """Get existing session or create new one.

        Args:
            session_id: Session ID
            user_id: Optional user ID for new sessions

        Returns:
            CrossChannelSession instance
        """
        session = self.get_session(session_id)
        if session:
            return session

        return self.create_session(user_id=user_id, session_id=session_id)

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a session.

        Args:
            session_id: Session ID to terminate

        Returns:
            True if session was terminated, False if not found
        """
        session = self._sessions.pop(session_id, None)
        if session:
            session.status = SessionStatus.TERMINATED
            logger.info(f"Terminated session {session_id}")
            return True
        return False

    def list_sessions(
        self, user_id: Optional[str] = None, status: Optional[SessionStatus] = None
    ) -> List[CrossChannelSession]:
        """List sessions with optional filtering.

        Args:
            user_id: Filter by user ID
            status: Filter by status

        Returns:
            List of matching sessions
        """
        sessions = []

        for session in self._sessions.values():
            if user_id and session.user_id != user_id:
                continue
            if status and session.status != status:
                continue
            sessions.append(session)

        return sessions

    def get_channel_sessions(self, channel_name: str) -> List[CrossChannelSession]:
        """Get all sessions active on a specific channel.

        Args:
            channel_name: Name of the channel

        Returns:
            List of sessions active on the channel
        """
        return [
            session
            for session in self._sessions.values()
            if channel_name in session.active_channels
        ]

    async def broadcast_to_channel(
        self, channel_name: str, event: Dict[str, Any]
    ) -> int:
        """Broadcast an event to all sessions on a channel.

        Args:
            channel_name: Target channel name
            event: Event data to broadcast

        Returns:
            Number of sessions that received the event
        """
        sessions = self.get_channel_sessions(channel_name)

        for session in sessions:
            session.add_event(
                {"type": "broadcast", "channel": channel_name, "data": event}
            )

        logger.debug(
            f"Broadcasted event to {len(sessions)} sessions on channel {channel_name}"
        )
        return len(sessions)

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")

    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        expired_sessions = []

        for session_id, session in self._sessions.items():
            if session.is_expired(self.default_timeout):
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self.terminate_session(session_id)

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics.

        Returns:
            Dictionary with session statistics
        """
        active_sessions = len(
            [s for s in self._sessions.values() if s.status == SessionStatus.ACTIVE]
        )
        idle_sessions = len(
            [s for s in self._sessions.values() if s.status == SessionStatus.IDLE]
        )

        channel_usage = {}
        for session in self._sessions.values():
            for channel in session.active_channels:
                channel_usage[channel] = channel_usage.get(channel, 0) + 1

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active_sessions,
            "idle_sessions": idle_sessions,
            "channel_usage": channel_usage,
            "default_timeout": self.default_timeout,
            "cleanup_interval": self.cleanup_interval,
        }
