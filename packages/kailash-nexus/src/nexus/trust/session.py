"""Session Trust Context Propagation for Kailash Nexus.

This module provides components for managing trust context across Nexus unified sessions.
It enables trust propagation from EATP headers through the session lifecycle, supporting
workflow execution tracking and session management.

Components:
    - SessionTrustContext: Dataclass holding session trust state
    - TrustContextPropagator: Manages session creation, retrieval, and revocation
    - Context variables: Thread-safe access to current session trust

Usage:
    from nexus.trust.session import (
        SessionTrustContext,
        TrustContextPropagator,
        get_current_session_trust,
        set_current_session_trust,
    )

    # Create a propagator instance
    propagator = TrustContextPropagator(default_ttl_hours=8.0)

    # Create a session with trust context
    session = await propagator.create_session(
        human_origin={"user_id": "user-123"},
        agent_id="agent-456",
    )

    # Set as current context for the request/task
    set_current_session_trust(session)

    # Retrieve in other parts of the code
    current = get_current_session_trust()
    if current and current.is_active():
        current.increment_workflow()
"""

import logging
import threading
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TrustOperationsProtocol(Protocol):
    """Protocol for TrustOperations to avoid hard Kaizen dependency."""

    async def verify(
        self,
        agent_id: str,
        action: str,
        resource: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Verify agent trust for an action."""
        ...


@dataclass
class SessionTrustContext:
    """Structured representation of session trust context.

    This dataclass holds all trust context information for a Nexus session,
    including human origin, agent identity, delegation chain, and constraints.
    It tracks session activity and supports expiration and revocation.

    Attributes:
        session_id: Unique identifier for the session (nxs-{uuid})
        human_origin: Decoded JSON object with human origin information
        agent_id: Identifier of the requesting agent
        delegation_chain: List of agent IDs in the delegation chain
        constraints: Decoded JSON object with operation constraints
        created_at: UTC timestamp when session was created
        expires_at: UTC timestamp when session expires (None = no expiry)
        workflow_count: Number of workflows executed in this session
        last_activity: UTC timestamp of last activity
        revoked: Whether the session has been revoked
        revoked_reason: Reason for revocation if revoked
    """

    session_id: str
    human_origin: Optional[Dict[str, Any]] = None
    agent_id: Optional[str] = None
    delegation_chain: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    workflow_count: int = 0
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revoked: bool = False
    revoked_reason: Optional[str] = None

    def is_expired(self) -> bool:
        """Check if the session has expired.

        Returns:
            True if expires_at is set and current time is past it, False otherwise.
        """
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_active(self) -> bool:
        """Check if the session is currently active.

        A session is active if it has not been revoked and has not expired.

        Returns:
            True if session is not revoked AND not expired, False otherwise.
        """
        return not self.revoked and not self.is_expired()

    def touch(self) -> None:
        """Update the last_activity timestamp to current UTC time."""
        self.last_activity = datetime.now(timezone.utc)

    def increment_workflow(self) -> None:
        """Increment the workflow count and update last_activity.

        This should be called each time a workflow is executed in this session.
        """
        self.workflow_count += 1
        self.touch()


class TrustContextPropagator:
    """Manages session trust context creation, retrieval, and revocation.

    This class provides the core session management functionality for Nexus,
    allowing creation of sessions with trust context, retrieval of active
    sessions, and revocation of sessions by session ID or human ID.

    The propagator maintains an in-memory store of sessions. For production
    use with multiple workers, consider using a shared session store like Redis.

    Thread Safety (CARE-053):
        All operations that mutate the internal session store are protected
        by a threading.Lock to prevent race conditions during concurrent
        access from multiple threads (e.g., concurrent session creation
        and cleanup).

    Attributes:
        _trust_operations: Optional TrustOperations for verification
        _default_ttl_hours: Default session TTL in hours
        _sessions: Internal session store (session_id -> SessionTrustContext)
        _lock: Threading lock for thread-safe access to _sessions

    Example:
        >>> propagator = TrustContextPropagator(default_ttl_hours=8.0)
        >>> session = await propagator.create_session(
        ...     human_origin={"user_id": "user-123"},
        ... )
        >>> print(session.session_id)
        nxs-a1b2c3d4-...
    """

    def __init__(
        self,
        trust_operations: Optional[TrustOperationsProtocol] = None,
        default_ttl_hours: float = 8.0,
    ) -> None:
        """Initialize the TrustContextPropagator.

        Args:
            trust_operations: Optional TrustOperations instance for verification.
                If not provided, the propagator works standalone without
                external trust verification.
            default_ttl_hours: Default session TTL in hours. Set to 0 for
                immediate expiry (useful for testing).
        """
        self._trust_operations = trust_operations
        self._default_ttl_hours = default_ttl_hours
        self._sessions: Dict[str, SessionTrustContext] = {}
        # CARE-053: Lock for thread-safe access to _sessions dict
        # Prevents race conditions during concurrent create/cleanup operations
        self._lock = threading.Lock()

    async def create_session(
        self,
        human_origin: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> SessionTrustContext:
        """Create a new session with trust context.

        Generates a unique session ID with "nxs-" prefix, sets expiry based
        on the default TTL, and stores the session in the internal store.

        Thread-safe: Uses lock to protect _sessions mutation (CARE-053).

        Args:
            human_origin: Optional human origin information from EATP headers.
            agent_id: Optional identifier of the requesting agent.
            constraints: Optional operation constraints for the session.

        Returns:
            SessionTrustContext with generated session_id and timestamps.
        """
        session_id = f"nxs-{uuid.uuid4()}"
        now = datetime.now(timezone.utc)

        expires_at = now + timedelta(hours=self._default_ttl_hours)

        context = SessionTrustContext(
            session_id=session_id,
            human_origin=human_origin,
            agent_id=agent_id,
            constraints=constraints if constraints is not None else {},
            created_at=now,
            expires_at=expires_at,
            last_activity=now,
        )

        # CARE-053: Thread-safe session storage
        with self._lock:
            self._sessions[session_id] = context

        logger.debug(
            f"Created session {session_id} for agent {agent_id}, "
            f"expires at {expires_at}"
        )

        return context

    def get_session_context(self, session_id: str) -> Optional[SessionTrustContext]:
        """Retrieve a session context by session ID.

        Only returns active sessions (not expired, not revoked).

        Thread-safe: Uses lock to protect _sessions access (CARE-053).

        Args:
            session_id: The session ID to look up.

        Returns:
            SessionTrustContext if found and active, None otherwise.
        """
        # CARE-053: Thread-safe session retrieval
        with self._lock:
            context = self._sessions.get(session_id)

        if context is None:
            return None

        if not context.is_active():
            logger.debug(
                f"Session {session_id} is not active "
                f"(revoked={context.revoked}, expired={context.is_expired()})"
            )
            return None

        return context

    async def revoke_session(
        self, session_id: str, reason: Optional[str] = None
    ) -> bool:
        """Revoke a session by session ID.

        Marks the session as revoked, preventing further use.

        Thread-safe: Uses lock to protect _sessions access and modification
        (CARE-053, ROUND5-003).

        Args:
            session_id: The session ID to revoke.
            reason: Optional reason for revocation.

        Returns:
            True if session was found and revoked, False if not found.
        """
        # ROUND5-003: Atomic retrieval and modification under single lock
        with self._lock:
            context = self._sessions.get(session_id)
            if context is None:
                return False
            context.revoked = True
            context.revoked_reason = reason

        logger.info(f"Revoked session {session_id}: {reason}")

        return True

    async def revoke_by_human(self, human_id: str) -> int:
        """Revoke all sessions associated with a human ID.

        Searches all sessions for those with matching human_origin["user_id"]
        and revokes them.

        Thread-safe: Uses lock to protect _sessions iteration and modification
        (CARE-053, ROUND5-004).

        Args:
            human_id: The human ID to match in human_origin["user_id"].

        Returns:
            Number of sessions revoked.
        """
        revoked_count = 0
        revoked_session_ids = []

        # ROUND5-004: Atomic iteration and modification under single lock
        with self._lock:
            for context in self._sessions.values():
                if context.human_origin is None:
                    continue

                if context.human_origin.get("user_id") == human_id:
                    if not context.revoked:
                        context.revoked = True
                        context.revoked_reason = (
                            f"Revoked by human ID revocation: {human_id}"
                        )
                        revoked_count += 1
                        revoked_session_ids.append(context.session_id)

        # Logging outside lock (non-critical)
        for session_id in revoked_session_ids:
            logger.debug(f"Revoked session {session_id} for human {human_id}")

        logger.info(f"Revoked {revoked_count} sessions for human {human_id}")

        return revoked_count

    def list_active_sessions(self) -> List[SessionTrustContext]:
        """List all active (non-expired, non-revoked) sessions.

        Thread-safe: Uses lock to protect _sessions access (CARE-053).

        Returns:
            List of active SessionTrustContext objects.
        """
        # CARE-053: Thread-safe iteration over sessions
        with self._lock:
            return [ctx for ctx in self._sessions.values() if ctx.is_active()]

    def cleanup_expired(self) -> int:
        """Remove expired sessions from the internal store.

        This should be called periodically to prevent memory growth.

        Thread-safe: Uses lock to protect _sessions mutation (CARE-053).

        CARE-053: Previously this method iterated over _sessions while deleting
        entries without thread-safety, causing potential race conditions when
        concurrent create/get operations modified the dict during cleanup.
        Now protected by self._lock.

        Returns:
            Number of sessions removed.
        """
        # CARE-053: Thread-safe cleanup - hold lock during entire operation
        # to prevent race condition between identifying expired sessions
        # and deleting them
        with self._lock:
            expired_ids = [
                session_id
                for session_id, ctx in self._sessions.items()
                if ctx.is_expired()
            ]

            for session_id in expired_ids:
                del self._sessions[session_id]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")

        return len(expired_ids)


# Context variable for thread-safe access to current session trust
_session_trust: ContextVar[Optional[SessionTrustContext]] = ContextVar(
    "nexus_session_trust", default=None
)


def get_current_session_trust() -> Optional[SessionTrustContext]:
    """Get the current session trust context from the context variable.

    This function retrieves the session trust context that was set for the
    current execution context (request, task, etc.).

    Returns:
        SessionTrustContext if set, None otherwise.
    """
    return _session_trust.get()


def set_current_session_trust(ctx: SessionTrustContext) -> None:
    """Set the current session trust context in the context variable.

    This function sets the session trust context for the current execution
    context. It should be called at the start of request/task processing
    after session validation.

    Args:
        ctx: The SessionTrustContext to set as current.
    """
    _session_trust.set(ctx)
