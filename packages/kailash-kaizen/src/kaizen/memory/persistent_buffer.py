"""
Persistent buffer memory with database persistence.

Hybrid architecture: in-memory cache + database persistence for conversation history.
"""

import logging
import time
from threading import Lock
from typing import Any, Dict, Optional

from kaizen.memory.conversation_base import KaizenMemory
from kaizen.memory.persistence_backend import PersistenceBackend

logger = logging.getLogger(__name__)


class PersistentBufferMemory(KaizenMemory):
    """
    Buffer memory with database persistence.

    Architecture:
    - In-memory cache for active conversations (<1ms access)
    - Database persistence via pluggable backend (<50ms)
    - FIFO limiting (keeps last N turns in memory)
    - Thread-safe for concurrent access
    - Session-scoped (conversation_id)

    Features:
    - Survives application restarts
    - Automatic cache management
    - Optional cache invalidation
    - BaseAgent compatible

    Example:
        from kaizen.memory import PersistentBufferMemory
        from kaizen.memory.backends import DataFlowBackend
        from dataflow import DataFlow

        # Setup persistence
        db = DataFlow(db_url="postgresql://localhost/mydb")
        backend = DataFlowBackend(db)

        # Create memory
        memory = PersistentBufferMemory(
            backend=backend,
            max_turns=10,
            cache_ttl_seconds=300  # 5 minutes
        )

        # Use with BaseAgent
        agent = BaseAgent(
            config=config,
            signature=signature,
            memory=memory
        )

        result = agent.run(question="Hi!", session_id="conv_123")
    """

    def __init__(
        self,
        backend: Optional[PersistenceBackend] = None,
        max_turns: int = 10,
        cache_ttl_seconds: Optional[int] = 300,
    ):
        """
        Initialize persistent buffer memory.

        Args:
            backend: Persistence backend (None = in-memory only)
            max_turns: Maximum turns to keep in memory cache (must be >= 1)
            cache_ttl_seconds: Cache TTL in seconds (None = no expiration, 0 = always reload)

        Raises:
            ValueError: If max_turns < 1 or cache_ttl_seconds < 0
        """
        # Validate parameters
        if max_turns < 1:
            raise ValueError(f"max_turns must be >= 1, got {max_turns}")

        if cache_ttl_seconds is not None and cache_ttl_seconds < 0:
            raise ValueError(
                f"cache_ttl_seconds must be >= 0 or None, got {cache_ttl_seconds}"
            )

        self.backend = backend
        self.max_turns = max_turns
        self.cache_ttl_seconds = cache_ttl_seconds

        # Thread-safe cache
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

        logger.debug(
            f"Initialized PersistentBufferMemory: "
            f"max_turns={max_turns}, "
            f"cache_ttl={cache_ttl_seconds}s, "
            f"backend={type(backend).__name__ if backend else 'None'}"
        )

    def load_context(self, session_id: str) -> Dict[str, Any]:
        """
        Load conversation context.

        Loads from cache if available and not stale, otherwise from backend.

        Args:
            session_id: Conversation ID (non-empty string)

        Returns:
            {
                "turns": List[Dict],  # List of turns
                "turn_count": int     # Total turn count
            }

        Raises:
            ValueError: If session_id is None or empty
        """
        # Validate session_id
        if not session_id or not isinstance(session_id, str):
            raise ValueError(
                f"session_id must be a non-empty string, got {repr(session_id)}"
            )

        with self._lock:
            # Check cache
            if self._is_cache_valid(session_id):
                logger.debug(f"Cache hit for session {session_id}")
                return self._cache[session_id]["data"]

            # Cache miss or stale - load from backend
            logger.debug(f"Cache miss for session {session_id}, loading from backend")
            return self._load_from_backend(session_id)

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save turn to cache and backend.

        Args:
            session_id: Conversation ID (non-empty string)
            turn: Turn data with keys:
                - user: User message (str, required)
                - agent: Agent response (str, required)
                - timestamp: ISO format timestamp (str, optional)
                - metadata: Optional metadata (dict, optional)

        Raises:
            ValueError: If session_id or turn data is invalid
        """
        # Validate session_id
        if not session_id or not isinstance(session_id, str):
            raise ValueError(
                f"session_id must be a non-empty string, got {repr(session_id)}"
            )

        # Validate turn data
        if not isinstance(turn, dict):
            raise ValueError(f"turn must be a dict, got {type(turn)}")

        if "user" not in turn or "agent" not in turn:
            raise ValueError(
                f"turn must contain 'user' and 'agent' keys, got {list(turn.keys())}"
            )

        if not isinstance(turn["user"], str) or not isinstance(turn["agent"], str):
            raise ValueError(
                f"turn 'user' and 'agent' must be strings, "
                f"got user={type(turn['user'])}, agent={type(turn['agent'])}"
            )

        with self._lock:
            # Ensure cache exists
            if session_id not in self._cache:
                self._cache[session_id] = {
                    "data": {"turns": [], "turn_count": 0},
                    "last_updated": time.time(),
                }

            # Update cache
            cache_data = self._cache[session_id]["data"]
            cache_data["turns"].append(turn)
            cache_data["turn_count"] += 1

            # Apply FIFO limiting
            if len(cache_data["turns"]) > self.max_turns:
                cache_data["turns"].pop(0)

            # Update timestamp
            self._cache[session_id]["last_updated"] = time.time()

            logger.debug(
                f"Saved turn to cache for session {session_id}: "
                f"{cache_data['turn_count']} total turns"
            )

        # Persist to backend (outside lock for better concurrency)
        if self.backend:
            try:
                self.backend.save_turn(session_id, turn)
                logger.debug(f"Persisted turn to backend for session {session_id}")
            except Exception as e:
                logger.error(f"Failed to persist turn to backend: {e}")
                # Don't raise - cache still has the data

    def clear(self, session_id: str) -> None:
        """
        Clear conversation from cache and backend.

        Args:
            session_id: Conversation ID (non-empty string)

        Raises:
            ValueError: If session_id is invalid
        """
        # Validate session_id
        if not session_id or not isinstance(session_id, str):
            raise ValueError(
                f"session_id must be a non-empty string, got {repr(session_id)}"
            )

        with self._lock:
            # Clear cache
            if session_id in self._cache:
                del self._cache[session_id]
                logger.debug(f"Cleared cache for session {session_id}")

        # Clear backend (outside lock)
        if self.backend:
            try:
                self.backend.clear_session(session_id)
                logger.debug(f"Cleared backend for session {session_id}")
            except Exception as e:
                logger.error(f"Failed to clear backend: {e}")

    # Private methods

    def _is_cache_valid(self, session_id: str) -> bool:
        """Check if cache entry exists and is not stale."""
        if session_id not in self._cache:
            return False

        # No TTL = always valid
        if self.cache_ttl_seconds is None:
            return True

        # Check TTL
        age_seconds = time.time() - self._cache[session_id]["last_updated"]
        return age_seconds < self.cache_ttl_seconds

    def _load_from_backend(self, session_id: str) -> Dict[str, Any]:
        """
        Load from backend and update cache.

        Must be called within self._lock.
        """
        if not self.backend:
            # No backend - return empty
            return {"turns": [], "turn_count": 0}

        try:
            # Load from backend
            turns = self.backend.load_turns(session_id, limit=self.max_turns)

            # Get total count
            metadata = self.backend.get_session_metadata(session_id)
            turn_count = metadata.get("turn_count", len(turns))

            # Update cache
            data = {"turns": turns, "turn_count": turn_count}

            self._cache[session_id] = {"data": data, "last_updated": time.time()}

            return data

        except Exception as e:
            logger.error(f"Failed to load from backend: {e}")
            # Return empty on error
            return {"turns": [], "turn_count": 0}

    def invalidate_cache(self, session_id: Optional[str] = None) -> None:
        """
        Manually invalidate cache.

        Args:
            session_id: Session to invalidate (None = all sessions)
        """
        with self._lock:
            if session_id:
                if session_id in self._cache:
                    del self._cache[session_id]
                    logger.debug(f"Invalidated cache for session {session_id}")
            else:
                self._cache.clear()
                logger.debug("Invalidated all cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get memory statistics.

        Returns:
            {
                "cached_sessions": int,
                "backend_type": str
            }
        """
        with self._lock:
            return {
                "cached_sessions": len(self._cache),
                "backend_type": type(self.backend).__name__ if self.backend else "None",
            }
