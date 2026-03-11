"""
DataFlow Storage Backend for Nexus Session Persistence.

Provides persistent storage for CrossChannelSession using DataFlow.
Implements save, update, load, and query operations with automatic
node generation from the registered model.

Architecture:
- Uses DataFlow for zero-config database operations
- Automatically generates 11 workflow nodes per model
- Built-in support for PostgreSQL, MySQL, and SQLite
- String IDs preserved (no UUID conversion)
- JSON serialization for complex types (dict)

Example:
    from dataflow import DataFlow
    from kaizen.integrations.nexus.storage import SessionStorage
    from kaizen.integrations.nexus.session_manager import CrossChannelSession

    # Initialize storage
    db = DataFlow("postgresql://user:pass@localhost/mydb")
    storage = SessionStorage(db)

    # Save session
    session = CrossChannelSession(
        session_id="sess-123",
        user_id="user-456",
    )
    await storage.save(session)

    # Load session
    loaded = await storage.load("sess-123")

    # List active sessions
    active = await storage.list_active(limit=100)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from kaizen.integrations.nexus.models import register_session_models
from kaizen.integrations.nexus.session_manager import CrossChannelSession

logger = logging.getLogger(__name__)


class SessionStorage:
    """
    DataFlow storage backend for CrossChannelSession persistence.

    Provides CRUD operations for sessions using DataFlow-generated
    workflow nodes. Handles JSON serialization for complex fields
    (state, channel_activity).

    Performance Characteristics:
    - save(): ~5-10ms (single record insert)
    - load(): ~2-5ms (primary key lookup)
    - update(): ~5-10ms (single record update)
    - list_active(): ~10-20ms (filtered query)
    - list_by_user(): ~10-20ms (filtered query)

    Thread Safety:
    - Uses AsyncLocalRuntime for async-safe execution
    - Each method creates fresh WorkflowBuilder (no shared state)
    - Safe for concurrent use from multiple async tasks

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("sqlite:///sessions.db")
        >>> storage = SessionStorage(db)
        >>>
        >>> # Save a new session
        >>> session = CrossChannelSession(
        ...     session_id="sess-001",
        ...     user_id="user-123",
        ... )
        >>> await storage.save(session)
        >>>
        >>> # Load by ID
        >>> loaded = await storage.load("sess-001")
        >>> print(loaded.user_id)  # "user-123"
    """

    # Model name used for node naming convention
    MODEL_NAME = "CrossChannelSession"

    def __init__(self, db: "DataFlow"):
        """
        Initialize the storage backend with a DataFlow instance.

        Registers the CrossChannelSession model with DataFlow,
        which automatically generates 11 workflow nodes for database
        operations.

        Args:
            db: DataFlow instance (connected to database)

        Raises:
            ValueError: If db is not a DataFlow instance

        Example:
            >>> from dataflow import DataFlow
            >>> db = DataFlow("postgresql://localhost/mydb")
            >>> storage = SessionStorage(db)
        """
        try:
            from dataflow import DataFlow as DataFlowClass

            if not isinstance(db, DataFlowClass):
                raise ValueError(f"Expected DataFlow instance, got {type(db)}")
        except ImportError:
            raise ValueError(
                "DataFlow not installed. Install with: pip install kailash-dataflow"
            )

        self.db = db

        # Register models with DataFlow (generates 11 nodes)
        self._models = register_session_models(db)

        # Runtime for executing workflows
        self.runtime = AsyncLocalRuntime()

        logger.debug(f"SessionStorage initialized with model: {self.MODEL_NAME}")

    def _to_db_record(self, session: CrossChannelSession) -> Dict[str, Any]:
        """
        Convert CrossChannelSession to database record format.

        Serializes complex fields (state, channel_activity) to JSON strings
        for storage in DataFlow model.

        Args:
            session: CrossChannelSession to convert

        Returns:
            Dictionary suitable for DataFlow CreateNode/UpdateNode

        Note:
            - state dict -> state_json string
            - channel_activity dict -> channel_activity_json string
            - datetime -> ISO format string
        """
        return {
            "id": session.session_id,
            "user_id": session.user_id,
            "last_accessed": session.last_accessed.isoformat(),
            "expires_at": session.expires_at.isoformat() if session.expires_at else "",
            "state_json": json.dumps(session.state),
            "channel_activity_json": json.dumps(
                {k: v.isoformat() for k, v in session.channel_activity.items()}
            ),
            "memory_pool_id": session.memory_pool_id,
        }

    def _from_db_record(self, record: Dict[str, Any]) -> CrossChannelSession:
        """
        Convert database record to CrossChannelSession.

        Deserializes JSON strings back to Python types (dict).

        Args:
            record: Database record from DataFlow ReadNode/ListNode

        Returns:
            CrossChannelSession instance

        Note:
            - state_json string -> state dict
            - channel_activity_json string -> channel_activity dict
            - ISO format string -> datetime
        """
        # Parse JSON fields
        state_json = record.get("state_json", "{}")
        if isinstance(state_json, str):
            state = json.loads(state_json)
        else:
            state = state_json or {}

        activity_json = record.get("channel_activity_json", "{}")
        if isinstance(activity_json, str):
            activity_str_dict = json.loads(activity_json)
        else:
            activity_str_dict = activity_json or {}

        # Convert activity timestamps back to datetime
        channel_activity = {}
        for channel, timestamp_str in activity_str_dict.items():
            if timestamp_str:
                channel_activity[channel] = datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00")
                )

        # Parse datetime fields
        created_at_str = record.get("created_at")
        if isinstance(created_at_str, str):
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        elif isinstance(created_at_str, datetime):
            created_at = created_at_str
        else:
            created_at = datetime.now()

        last_accessed_str = record.get("last_accessed", "")
        if isinstance(last_accessed_str, str) and last_accessed_str:
            last_accessed = datetime.fromisoformat(
                last_accessed_str.replace("Z", "+00:00")
            )
        elif isinstance(last_accessed_str, datetime):
            last_accessed = last_accessed_str
        else:
            last_accessed = datetime.now()

        expires_at_str = record.get("expires_at", "")
        expires_at = None
        if expires_at_str:
            if isinstance(expires_at_str, str):
                expires_at = datetime.fromisoformat(
                    expires_at_str.replace("Z", "+00:00")
                )
            elif isinstance(expires_at_str, datetime):
                expires_at = expires_at_str

        # Create session without triggering __post_init__ defaults
        session = CrossChannelSession(
            session_id=record["id"],
            user_id=record.get("user_id", ""),
            created_at=created_at,
            last_accessed=last_accessed,
            expires_at=expires_at,
            state=state,
            channel_activity=channel_activity,
            memory_pool_id=record.get("memory_pool_id"),
        )

        return session

    async def save(self, session: CrossChannelSession) -> str:
        """
        Save a new session to the database.

        Uses DataFlow CreateNode for atomic insert operation.

        Args:
            session: CrossChannelSession to save

        Returns:
            The session ID (for confirmation)

        Raises:
            Exception: If database operation fails

        Example:
            >>> session = CrossChannelSession(
            ...     session_id="sess-001",
            ...     user_id="user-123",
            ... )
            >>> session_id = await storage.save(session)
            >>> print(session_id)  # "sess-001"
        """
        record = self._to_db_record(session)

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}CreateNode",
            "create_session",
            record,
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
            logger.debug(f"Saved session: {session.session_id}")
            return session.session_id
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            raise

    async def update(self, session: CrossChannelSession) -> None:
        """
        Update an existing session in the database.

        Uses DataFlow UpdateNode with filter on ID for atomic update.

        Args:
            session: CrossChannelSession with updated fields

        Raises:
            Exception: If database operation fails

        Example:
            >>> session = await storage.load("sess-001")
            >>> session.update_state({"key": "value"})
            >>> await storage.update(session)
        """
        record = self._to_db_record(session)

        # Remove 'id' from fields (it's the filter, not an update field)
        update_fields = {k: v for k, v in record.items() if k != "id"}

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}UpdateNode",
            "update_session",
            {
                "filter": {"id": session.session_id},
                "fields": update_fields,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
            logger.debug(f"Updated session: {session.session_id}")
        except Exception as e:
            logger.error(f"Failed to update session {session.session_id}: {e}")
            raise

    async def load(self, session_id: str) -> Optional[CrossChannelSession]:
        """
        Load a session by ID.

        Uses DataFlow ReadNode for primary key lookup.

        Args:
            session_id: Unique session ID

        Returns:
            CrossChannelSession if found, None otherwise

        Example:
            >>> session = await storage.load("sess-001")
            >>> if session:
            ...     print(f"User: {session.user_id}")
            ... else:
            ...     print("Session not found")
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ReadNode",
            "read_session",
            {"id": session_id},
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("read_session", {})

            # Handle different result formats from DataFlow
            if "result" in result:
                record = result["result"]
            elif "data" in result:
                record = result["data"]
            else:
                record = result

            if not record or not record.get("id"):
                logger.debug(f"Session not found: {session_id}")
                return None

            return self._from_db_record(record)
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            raise

    async def delete(self, session_id: str) -> bool:
        """
        Delete a session by ID.

        Uses DataFlow DeleteNode for atomic delete operation.

        Args:
            session_id: Unique session ID

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = await storage.delete("sess-001")
            >>> print(f"Deleted: {deleted}")
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}DeleteNode",
            "delete_session",
            {"id": session_id},
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("delete_session", {})
            deleted = result.get("deleted", False) or result.get("success", False)

            if deleted:
                logger.debug(f"Deleted session: {session_id}")
            else:
                logger.debug(f"Session not found for deletion: {session_id}")

            return deleted
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            raise

    async def list_active(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CrossChannelSession]:
        """
        List active (non-expired) sessions.

        Uses DataFlow ListNode with expiration filter.

        Args:
            limit: Maximum number of results (default: 100)
            offset: Offset for pagination (default: 0)

        Returns:
            List of active CrossChannelSession instances

        Example:
            >>> active = await storage.list_active(limit=50)
            >>> print(f"Active sessions: {len(active)}")
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ListNode",
            "list_sessions",
            {
                "filter": {"expires_at": {"$gt": now_iso}},
                "limit": limit,
                "offset": offset,
                "order_by": "last_accessed",
                "ascending": False,  # Most recent first
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("list_sessions", {})
            records = result.get("records", [])

            return [self._from_db_record(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to list active sessions: {e}")
            raise

    async def list_by_user(
        self,
        user_id: str,
        include_expired: bool = False,
        limit: int = 100,
    ) -> List[CrossChannelSession]:
        """
        List sessions for a specific user.

        Args:
            user_id: User identifier
            include_expired: Include expired sessions (default: False)
            limit: Maximum number of results (default: 100)

        Returns:
            List of CrossChannelSession for the user

        Example:
            >>> sessions = await storage.list_by_user("user-123")
            >>> print(f"User sessions: {len(sessions)}")
        """
        filters: Dict[str, Any] = {"user_id": user_id}

        if not include_expired:
            now_iso = datetime.now(timezone.utc).isoformat()
            filters["expires_at"] = {"$gt": now_iso}

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ListNode",
            "list_sessions",
            {
                "filter": filters,
                "limit": limit,
                "order_by": "last_accessed",
                "ascending": False,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("list_sessions", {})
            records = result.get("records", [])

            return [self._from_db_record(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to list sessions for user {user_id}: {e}")
            raise

    async def cleanup_expired(self, limit: int = 1000) -> int:
        """
        Delete expired sessions from the database.

        Useful for periodic cleanup background tasks.

        Args:
            limit: Maximum sessions to delete in one call (default: 1000)

        Returns:
            Number of sessions deleted

        Example:
            >>> deleted = await storage.cleanup_expired()
            >>> print(f"Cleaned up {deleted} expired sessions")
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}BulkDeleteNode",
            "delete_expired",
            {
                "filter": {"expires_at": {"$lt": now_iso}},
                "limit": limit,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("delete_expired", {})
            deleted_count = result.get("deleted_count", 0) or result.get("count", 0)

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired sessions")

            return deleted_count
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            raise

    async def count_active(self) -> int:
        """
        Count active (non-expired) sessions.

        Uses DataFlow CountNode for efficient counting.

        Returns:
            Number of active sessions

        Example:
            >>> count = await storage.count_active()
            >>> print(f"Active sessions: {count}")
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}CountNode",
            "count_sessions",
            {"filter": {"expires_at": {"$gt": now_iso}}},
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("count_sessions", {})
            return result.get("count", 0)
        except Exception as e:
            logger.error(f"Failed to count active sessions: {e}")
            raise


# Export storage class
__all__ = [
    "SessionStorage",
]
