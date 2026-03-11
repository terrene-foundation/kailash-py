"""
Journey State Manager for Journey Orchestration.

Provides session persistence with pluggable storage backends for
development (memory), testing (memory), and production (DataFlow).

Components:
    - StateBackend: Abstract base class for storage backends
    - MemoryStateBackend: In-memory storage (development/testing)
    - DataFlowStateBackend: DataFlow-backed storage (production)
    - JourneyStateManager: Main state management class

Architecture:
    JourneyStateManager
    - Serialization/deserialization logic
    - TTL-based expiration
    - Backend abstraction

    StateBackend (Abstract)
    - save(session_id, data)
    - load(session_id)
    - delete(session_id)
    - list_sessions()

Usage:
    from kaizen.journey.state import JourneyStateManager, MemoryStateBackend

    # Development/testing with memory backend
    config = JourneyConfig(context_persistence="memory")
    state_manager = JourneyStateManager(config)

    # Production with DataFlow backend
    from dataflow import DataFlow
    db = DataFlow("postgresql://...")
    state_manager.set_backend(DataFlowStateBackend(db))

    # Save/load sessions
    await state_manager.save_session(session)
    restored = await state_manager.load_session("session-123")

References:
    - docs/plans/03-journey/05-runtime.md
    - TODO-JO-004: Runtime Components
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from kaizen.journey.errors import StateError

if TYPE_CHECKING:
    from kaizen.journey.core import Journey, JourneyConfig

logger = logging.getLogger(__name__)


# ============================================================================
# JourneySession (moved here to avoid circular imports)
# ============================================================================


@dataclass
class JourneySession:
    """
    Active journey session state.

    Contains all state needed to restore and continue a journey session,
    including navigation history, conversation history, and accumulated context.

    Attributes:
        session_id: Unique identifier for this session
        journey_class: Journey class (for deserialization reference)
        current_pathway_id: Current active pathway
        pathway_stack: Navigation stack for ReturnToPrevious behavior
        conversation_history: List of conversation turns
        accumulated_context: Cross-pathway accumulated state
        created_at: Session creation timestamp
        updated_at: Last update timestamp
    """

    session_id: str
    journey_class: Optional[Type["Journey"]]
    current_pathway_id: str
    pathway_stack: List[str] = field(default_factory=list)
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    accumulated_context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# StateBackend Abstract Interface (REQ-PM-003)
# ============================================================================


class StateBackend(ABC):
    """
    Abstract backend for session persistence.

    Implementations must handle:
    - Session CRUD operations
    - Serialization/deserialization of dict data
    - Thread-safety for concurrent access

    Subclasses:
        - MemoryStateBackend: In-memory (development/testing)
        - DataFlowStateBackend: DataFlow/database (production)
    """

    @abstractmethod
    async def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        Save session data.

        Args:
            session_id: Unique session identifier
            data: Serialized session data (must be JSON-serializable)

        Raises:
            StateError: If save operation fails
        """
        pass

    @abstractmethod
    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load session data.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data dict, or None if not found

        Raises:
            StateError: If load operation fails
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """
        Delete session data.

        Args:
            session_id: Unique session identifier

        Raises:
            StateError: If delete operation fails
        """
        pass

    @abstractmethod
    async def list_sessions(self) -> List[str]:
        """
        List all session IDs.

        Returns:
            List of session IDs

        Raises:
            StateError: If list operation fails
        """
        pass

    async def exists(self, session_id: str) -> bool:
        """
        Check if session exists.

        Default implementation loads and checks for None.
        Subclasses may override for efficiency.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists, False otherwise
        """
        data = await self.load(session_id)
        return data is not None


# ============================================================================
# MemoryStateBackend (Development/Testing)
# ============================================================================


class MemoryStateBackend(StateBackend):
    """
    In-memory session storage for development and testing.

    Fast and simple, but data is lost when the process ends.
    Thread-safe for concurrent access using asyncio.Lock.

    Attributes:
        _storage: Dict mapping session_id -> session data
        _lock: asyncio.Lock for thread-safe operations

    Example:
        >>> backend = MemoryStateBackend()
        >>> await backend.save("session-1", {"key": "value"})
        >>> data = await backend.load("session-1")
        >>> data
        {'key': 'value'}
    """

    def __init__(self):
        """Initialize MemoryStateBackend with thread-safe lock."""
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        Save session data to memory (thread-safe).

        Args:
            session_id: Unique session identifier
            data: Session data (copied to prevent external mutation)
        """
        async with self._lock:
            # Deep copy to prevent external mutation
            self._storage[session_id] = json.loads(json.dumps(data))

    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load session data from memory (thread-safe).

        Args:
            session_id: Unique session identifier

        Returns:
            Copy of session data, or None if not found
        """
        async with self._lock:
            data = self._storage.get(session_id)
            if data:
                # Return copy to prevent external mutation
                return json.loads(json.dumps(data))
            return None

    async def delete(self, session_id: str) -> None:
        """
        Delete session data from memory (thread-safe).

        Args:
            session_id: Unique session identifier
        """
        async with self._lock:
            self._storage.pop(session_id, None)

    async def list_sessions(self) -> List[str]:
        """
        List all session IDs in memory (thread-safe).

        Returns:
            List of session IDs
        """
        async with self._lock:
            return list(self._storage.keys())

    async def exists(self, session_id: str) -> bool:
        """
        Check if session exists in memory (thread-safe).

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists
        """
        async with self._lock:
            return session_id in self._storage

    def clear(self) -> None:
        """Clear all sessions from memory (not async, use with caution)."""
        self._storage.clear()

    def get_size(self) -> int:
        """
        Get number of sessions in memory.

        Returns:
            Number of stored sessions
        """
        return len(self._storage)


# ============================================================================
# DataFlowStateBackend (Production)
# ============================================================================


class DataFlowStateBackend(StateBackend):
    """
    DataFlow-backed session storage for production use.

    Uses DataFlow Express API for fast CRUD operations.
    Requires a JourneySession model to be registered with DataFlow.

    Model Schema:
        @db.model
        class JourneySession:
            id: str
            journey_class: str
            current_pathway_id: str
            pathway_stack: str  # JSON serialized
            conversation_history: str  # JSON serialized
            accumulated_context: str  # JSON serialized
            created_at: str
            updated_at: str

    Attributes:
        db: DataFlow instance
        model_name: Name of the session model (default: "JourneySession")

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("postgresql://...")
        >>> @db.model
        ... class JourneySession:
        ...     id: str
        ...     journey_class: str
        ...     current_pathway_id: str
        ...     pathway_stack: str
        ...     conversation_history: str
        ...     accumulated_context: str
        >>> backend = DataFlowStateBackend(db)
        >>> await backend.save("session-1", data)
    """

    def __init__(
        self,
        db: Any,  # DataFlow instance
        model_name: str = "JourneySession",
    ):
        """
        Initialize DataFlowStateBackend.

        Args:
            db: DataFlow instance
            model_name: Name of the session model
        """
        self.db = db
        self.model_name = model_name

    async def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        Save session data to DataFlow.

        Uses upsert semantics (create if not exists, update if exists).

        Args:
            session_id: Unique session identifier
            data: Session data (JSON fields will be serialized)

        Raises:
            StateError: If save operation fails
        """
        try:
            # Serialize JSON fields
            serialized = {
                "id": session_id,
                "journey_class": data.get("journey_class", ""),
                "current_pathway_id": data.get("current_pathway_id", ""),
                "pathway_stack": json.dumps(data.get("pathway_stack", [])),
                "conversation_history": json.dumps(
                    data.get("conversation_history", [])
                ),
                "accumulated_context": json.dumps(data.get("accumulated_context", {})),
                "created_at": data.get(
                    "created_at", datetime.now(timezone.utc).isoformat()
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            # Check if session exists
            existing = await self.db.express.read(self.model_name, session_id)

            if existing:
                # Update existing - remove id from fields
                update_fields = {k: v for k, v in serialized.items() if k != "id"}
                await self.db.express.update(self.model_name, session_id, update_fields)
            else:
                # Create new
                await self.db.express.create(self.model_name, serialized)

        except Exception as e:
            logger.error(f"DataFlow save failed: {e}")
            raise StateError("save", session_id, str(e))

    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load session data from DataFlow.

        Args:
            session_id: Unique session identifier

        Returns:
            Deserialized session data, or None if not found

        Raises:
            StateError: If load operation fails (other than not found)
        """
        try:
            record = await self.db.express.read(self.model_name, session_id)

            if not record:
                return None

            # Deserialize JSON fields
            return {
                "session_id": record.get("id"),
                "journey_class": record.get("journey_class", ""),
                "current_pathway_id": record.get("current_pathway_id", ""),
                "pathway_stack": json.loads(record.get("pathway_stack", "[]")),
                "conversation_history": json.loads(
                    record.get("conversation_history", "[]")
                ),
                "accumulated_context": json.loads(
                    record.get("accumulated_context", "{}")
                ),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
            }

        except Exception as e:
            logger.error(f"DataFlow load failed: {e}")
            raise StateError("load", session_id, str(e))

    async def delete(self, session_id: str) -> None:
        """
        Delete session data from DataFlow.

        Args:
            session_id: Unique session identifier

        Raises:
            StateError: If delete operation fails
        """
        try:
            await self.db.express.delete(self.model_name, session_id)
        except Exception as e:
            logger.error(f"DataFlow delete failed: {e}")
            raise StateError("delete", session_id, str(e))

    async def list_sessions(self) -> List[str]:
        """
        List all session IDs from DataFlow.

        Returns:
            List of session IDs

        Raises:
            StateError: If list operation fails
        """
        try:
            records = await self.db.express.list(
                self.model_name,
                filter={},
                limit=10000,  # Reasonable limit
            )

            return [r.get("id") for r in records if r.get("id")]

        except Exception as e:
            logger.error(f"DataFlow list failed: {e}")
            raise StateError("list", reason=str(e))


# ============================================================================
# JourneyStateManager (REQ-PM-003)
# ============================================================================


class JourneyStateManager:
    """
    Manages journey session persistence.

    The JourneyStateManager is responsible for:
    - Session CRUD operations
    - Serialization/deserialization
    - Backend abstraction
    - TTL-based expiration (future)

    Features:
    - Multiple backend support (memory, DataFlow)
    - Session serialization/deserialization
    - Journey class restoration (by string reference)
    - Recovery from crashes (via persistent backends)

    Attributes:
        config: Journey configuration
        _backend: Active storage backend

    Example:
        >>> config = JourneyConfig(context_persistence="memory")
        >>> state_manager = JourneyStateManager(config)
        >>> await state_manager.save_session(session)
        >>> restored = await state_manager.load_session("session-123")
    """

    def __init__(self, config: "JourneyConfig"):
        """
        Initialize JourneyStateManager.

        Args:
            config: Journey configuration (determines default backend)
        """
        self.config = config
        self._backend = self._create_backend()

    def _create_backend(self) -> StateBackend:
        """
        Create appropriate backend based on config.

        Returns:
            StateBackend instance
        """
        persistence = self.config.context_persistence

        if persistence == "memory":
            return MemoryStateBackend()
        elif persistence == "dataflow":
            # DataFlow backend requires db instance to be passed via set_backend
            # CRITICAL: Do NOT silently fallback to memory - could cause data loss!
            raise ValueError(
                "DataFlow persistence requires DataFlowStateBackend to be set "
                "via set_backend(db) after initialization. Either:\n"
                "  1. Use context_persistence='memory' for in-memory storage, or\n"
                "  2. Call manager.set_backend(DataFlowStateBackend(db)) with your DataFlow instance.\n"
                "Example:\n"
                "  from kaizen.journey import DataFlowStateBackend\n"
                "  manager = RuntimePathwayManager(...)\n"
                "  manager.set_backend(DataFlowStateBackend(db))"
            )
        else:
            # Raise error for unknown persistence types instead of silently falling back
            valid_options = ["memory", "dataflow"]
            raise ValueError(
                f"Unknown persistence type '{persistence}'. "
                f"Valid options: {valid_options}"
            )

    def set_backend(self, backend: StateBackend) -> None:
        """
        Set a custom backend.

        Use this to inject DataFlow backend or custom backends.

        Args:
            backend: StateBackend instance

        Example:
            >>> from dataflow import DataFlow
            >>> db = DataFlow("postgresql://...")
            >>> state_manager.set_backend(DataFlowStateBackend(db))
        """
        self._backend = backend

    def get_backend(self) -> StateBackend:
        """
        Get the current backend.

        Returns:
            Current StateBackend instance
        """
        return self._backend

    async def save_session(self, session: JourneySession) -> None:
        """
        Save session to backend.

        Args:
            session: JourneySession to save

        Raises:
            StateError: If save operation fails
        """
        data = self._serialize_session(session)
        await self._backend.save(session.session_id, data)

    async def load_session(
        self,
        session_id: str,
    ) -> Optional[JourneySession]:
        """
        Load session from backend.

        Note: The journey_class field will be None after loading.
        The PathwayManager must set it during restoration.

        Args:
            session_id: Session ID to load

        Returns:
            JourneySession if found, None otherwise

        Raises:
            StateError: If load operation fails
        """
        data = await self._backend.load(session_id)
        if data:
            return self._deserialize_session(data)
        return None

    async def delete_session(self, session_id: str) -> None:
        """
        Delete session from backend.

        Args:
            session_id: Session ID to delete

        Raises:
            StateError: If delete operation fails
        """
        await self._backend.delete(session_id)

    async def list_sessions(self) -> List[str]:
        """
        List all active session IDs.

        Returns:
            List of session IDs

        Raises:
            StateError: If list operation fails
        """
        return await self._backend.list_sessions()

    async def session_exists(self, session_id: str) -> bool:
        """
        Check if session exists.

        Args:
            session_id: Session ID to check

        Returns:
            True if session exists
        """
        return await self._backend.exists(session_id)

    def _serialize_session(self, session: JourneySession) -> Dict[str, Any]:
        """
        Serialize session to storable format.

        Journey class is stored as module.classname string for restoration.

        Args:
            session: JourneySession to serialize

        Returns:
            Dict suitable for storage
        """
        journey_class_str = ""
        if session.journey_class:
            journey_class_str = (
                f"{session.journey_class.__module__}."
                f"{session.journey_class.__name__}"
            )

        return {
            "session_id": session.session_id,
            "journey_class": journey_class_str,
            "current_pathway_id": session.current_pathway_id,
            "pathway_stack": session.pathway_stack,
            "conversation_history": session.conversation_history,
            "accumulated_context": session.accumulated_context,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }

    def _deserialize_session(self, data: Dict[str, Any]) -> JourneySession:
        """
        Deserialize session from stored format.

        Note: journey_class is set to None. The caller (PathwayManager)
        must set the correct journey class based on context.

        Args:
            data: Stored session data

        Returns:
            JourneySession instance
        """
        # Parse timestamps
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now(timezone.utc)

        return JourneySession(
            session_id=data.get("session_id", ""),
            journey_class=None,  # Set by PathwayManager during restore
            current_pathway_id=data.get("current_pathway_id", ""),
            pathway_stack=data.get("pathway_stack", []),
            conversation_history=data.get("conversation_history", []),
            accumulated_context=data.get("accumulated_context", {}),
            created_at=created_at,
            updated_at=updated_at,
        )


__all__ = [
    "JourneySession",
    "StateBackend",
    "MemoryStateBackend",
    "DataFlowStateBackend",
    "JourneyStateManager",
]
