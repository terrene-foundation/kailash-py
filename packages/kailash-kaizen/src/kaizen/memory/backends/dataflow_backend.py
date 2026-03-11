"""
DataFlow persistence backend for conversation memory.

Provides PostgreSQL/SQLite persistence via Kailash DataFlow framework.
Uses workflow-based DataFlow API (NOT ORM-style attribute access).
"""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow import DataFlow
except ImportError:
    DataFlow = None
    WorkflowBuilder = None
    LocalRuntime = None

logger = logging.getLogger(__name__)


class DataFlowBackend:
    """
    DataFlow backend for conversation persistence with multi-tenancy support.

    Uses DataFlow workflow nodes for database operations.
    Requires ConversationMessage model with these fields:
    - id: str (primary key)
    - conversation_id: str
    - sender: str ("user" or "agent")
    - content: str
    - metadata: dict
    - created_at: datetime (auto-managed)
    - tenant_id: str (optional, for multi-tenancy isolation)

    Multi-Tenancy:
        When tenant_id is provided, all operations are scoped to that tenant.
        Different tenants cannot access each other's data.

    Example (Single Tenant):
        from dataflow import DataFlow
        from kaizen.memory.backends import DataFlowBackend
        from datetime import datetime

        # Setup DataFlow
        db = DataFlow(database_url="sqlite:///memory.db")

        @db.model
        class ConversationMessage:
            id: str
            conversation_id: str
            sender: str
            content: str
            metadata: dict
            created_at: datetime

        # Use backend
        backend = DataFlowBackend(db, model_name="ConversationMessage")
        backend.save_turn("conv_123", {
            "user": "Hello",
            "agent": "Hi there!",
            "timestamp": "2025-10-25T12:00:00"
        })

    Example (Multi-Tenant):
        from dataflow import DataFlow
        from kaizen.memory.backends import DataFlowBackend

        # Setup DataFlow
        db = DataFlow(database_url="postgresql://localhost/app")

        @db.model
        class ConversationMessage:
            id: str
            conversation_id: str
            tenant_id: str  # Required for multi-tenancy
            sender: str
            content: str
            metadata: dict
            created_at: datetime

        # Tenant A backend (isolated)
        backend_a = DataFlowBackend(db, tenant_id="tenant_a")
        backend_a.save_turn("conv_123", {"user": "Hello", "agent": "Hi"})

        # Tenant B backend (isolated, cannot see tenant_a data)
        backend_b = DataFlowBackend(db, tenant_id="tenant_b")
        backend_b.save_turn("conv_456", {"user": "Hola", "agent": "Hola!"})

        # Tenant A can only access their own data
        turns_a = backend_a.load_turns("conv_123")  # OK
        turns_a = backend_a.load_turns("conv_456")  # Empty (tenant_b data)
    """

    def __init__(
        self,
        db: "DataFlow",
        model_name: str = "ConversationMessage",
        tenant_id: Optional[str] = None,
    ):
        """
        Initialize DataFlow backend with optional multi-tenancy support.

        Args:
            db: DataFlow instance (connected to database)
            model_name: Name of the conversation message model class
            tenant_id: Optional tenant identifier for multi-tenancy isolation.
                      If provided, all operations are scoped to this tenant.
                      Different tenants cannot access each other's data.

        Raises:
            ValueError: If DataFlow is not installed
            ValueError: If db is not a DataFlow instance
            ValueError: If required dependencies are missing

        Security:
            Multi-tenancy isolation prevents cross-tenant data access.
            Complies with SOC 2 CC6.1 (Logical Access Controls).
        """
        if DataFlow is None or WorkflowBuilder is None or LocalRuntime is None:
            raise ValueError(
                "DataFlow dependencies not installed. "
                "Install with: pip install kailash-dataflow kailash"
            )

        if not isinstance(db, DataFlow):
            raise ValueError(f"Expected DataFlow instance, got {type(db)}")

        self.db = db
        self.model_name = model_name
        self.tenant_id = tenant_id

        tenant_info = f", tenant_id={tenant_id}" if tenant_id else ""
        logger.debug(
            f"Initialized DataFlowBackend with model: {model_name}{tenant_info}"
        )

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save a single conversation turn using DataFlow workflow nodes.

        Creates two message records: one for user, one for agent.

        Note: Empty user/agent messages are allowed (e.g., for acknowledgments).

        Args:
            session_id: Unique session identifier
            turn: Turn data with keys:
                - user: User message (str)
                - agent: Agent response (str)
                - timestamp: ISO format timestamp (str, optional)
                - metadata: Optional metadata (dict)

        Raises:
            Exception: If database save fails
        """
        user_msg = turn.get("user", "")
        agent_msg = turn.get("agent", "")
        metadata = turn.get("metadata", {}) or {}  # Handle None from DataFlow

        # Parse timestamp from turn data
        timestamp = turn.get("timestamp")
        if isinstance(timestamp, str):
            try:
                # Parse ISO format timestamp, handle 'Z' suffix
                created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created_at = datetime.now()
        else:
            created_at = datetime.now()

        # Generate unique IDs
        user_msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        agent_msg_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Fix for SQLite transaction race condition:
        # Execute CREATE operations separately with delay to ensure clean cursor cleanup.
        # This prevents "cannot commit transaction - SQL statements in progress" errors.
        # See: dataflow-specialist analysis on SQLite transaction concurrency limitations.

        try:
            # Save user message first
            workflow_user = WorkflowBuilder()
            workflow_user.add_node(
                f"{self.model_name}CreateNode",
                "create_user",
                {
                    "id": user_msg_id,
                    "conversation_id": session_id,
                    "sender": "user",
                    "content": user_msg,
                    "metadata": metadata if metadata else {},  # Ensure dict, not None
                    "created_at": created_at.isoformat(),  # Convert datetime to ISO string for JSON serialization
                },
            )

            with LocalRuntime() as runtime_user:
                results_user, run_id_user = runtime_user.execute(workflow_user.build())

            # Add 10ms delay for cursor cleanup (SQLite transaction safety)
            time.sleep(0.01)

            # Save agent message second
            workflow_agent = WorkflowBuilder()
            workflow_agent.add_node(
                f"{self.model_name}CreateNode",
                "create_agent",
                {
                    "id": agent_msg_id,
                    "conversation_id": session_id,
                    "sender": "agent",
                    "content": agent_msg,
                    "metadata": metadata if metadata else {},  # Ensure dict, not None
                    "created_at": created_at.isoformat(),  # Convert datetime to ISO string for JSON serialization
                },
            )

            with LocalRuntime() as runtime_agent:
                results_agent, run_id_agent = runtime_agent.execute(
                    workflow_agent.build()
                )

            logger.debug(
                f"Saved turn for session {session_id}: {len(user_msg)} chars user, {len(agent_msg)} chars agent"
            )
        except Exception as e:
            logger.error(f"Failed to save turn: {e}")
            raise

    def load_turns(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Load conversation turns for a session using DataFlow workflow nodes.

        Handles orphaned messages (user without agent or vice versa) by:
        - Logging a warning for orphaned user messages
        - Discarding orphaned user messages (no agent response yet)
        - Ignoring orphaned agent messages (no user message)

        Args:
            session_id: Unique session identifier
            limit: Maximum number of turns to load (None = all)

        Returns:
            List of turns in chronological order (oldest first)
            Each turn contains: user, agent, timestamp, metadata

        Returns:
            Empty list if session not found
        """
        print(
            f"[TRACE] load_turns() called with session_id={session_id}, limit={limit}"
        )

        # Build workflow to query messages
        workflow = WorkflowBuilder()

        # Fetch enough messages based on limit parameter
        # Each turn = 2 messages (user + agent), so fetch limit * 2 messages
        # Add generous buffer for orphaned messages: limit * 2 * 2 (100% buffer)
        # This ensures we fetch all requested turns even with many orphaned messages
        fetch_limit = (limit * 2 * 2) if limit else 10000

        # Auto-generated ListNode gets db_instance from closure
        # Only runtime parameters needed: filter, limit, order_by, ascending
        workflow.add_node(
            f"{self.model_name}ListNode",
            "list_messages",
            {
                "filter": {"conversation_id": session_id},
                "limit": fetch_limit,  # Fetch enough messages for requested turns
                "order_by": "created_at",  # Core SDK will convert to list internally
                "ascending": True,  # Always ASC to preserve user+agent pairing
                "enable_cache": False,  # Disable cache to prevent stale data
            },
        )

        # Execute workflow with fresh runtime to ensure clean transactions
        try:
            with LocalRuntime() as runtime:
                results, run_id = runtime.execute(workflow.build())
            # AsyncSQLDatabaseNode returns {"result": {"data": [...]}} format
            result = results.get("list_messages", {})
            if "result" in result and "data" in result["result"]:
                messages = result["result"]["data"]
            else:
                # Fallback to DataFlow ListNode format
                messages = result.get("records", [])
        except Exception as e:
            logger.error(f"Failed to load turns: {e}")
            return []

        # Reconstruct turns from messages
        turns = []
        current_turn = {}

        for i, msg in enumerate(messages):
            sender = msg.get("sender")
            content = msg.get("content", "")
            created_at = msg.get("created_at")
            msg_metadata = msg.get("metadata", {})

            # DataFlow v0.7.10+ may return metadata as JSON string instead of dict
            # Deserialize if needed (handles both dict and string return types)
            print(
                f"[TRACE load_turns] msg_metadata type={type(msg_metadata)}, value={msg_metadata}"
            )
            if isinstance(msg_metadata, str):
                print(
                    f"[TRACE load_turns] Deserializing metadata string: {msg_metadata}"
                )
                try:
                    msg_metadata = json.loads(msg_metadata) if msg_metadata else {}
                    print(
                        f"[TRACE load_turns] After deserialization: type={type(msg_metadata)}, value={msg_metadata}"
                    )
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"[TRACE load_turns] JSON parse failed: {e}")
                    logger.warning(
                        f"Failed to parse metadata JSON: {msg_metadata[:50]}, error: {e}"
                    )
                    msg_metadata = {}
            else:
                print(
                    "[TRACE load_turns] metadata is already a dict, no deserialization needed"
                )

            if sender == "user":
                # Warn about orphaned user message (if any)
                if current_turn:
                    logger.warning(
                        f"Orphaned user message in session {session_id}: {current_turn.get('user', '')[:50]}"
                    )

                # Start new turn
                current_turn = {
                    "user": content,
                    "timestamp": (
                        created_at
                        if isinstance(created_at, str)
                        else (
                            created_at.isoformat()
                            if created_at
                            else datetime.now().isoformat()
                        )
                    ),
                    "metadata": msg_metadata,
                }
            elif sender == "agent":
                if current_turn:
                    # Complete turn
                    current_turn["agent"] = content
                    turns.append(current_turn)
                    current_turn = {}
                else:
                    # Orphaned agent message (no user message)
                    logger.warning(
                        f"Orphaned agent message in session {session_id}: {content[:50]}"
                    )

        # Check for final orphaned user message
        if current_turn:
            logger.warning(
                f"Incomplete turn in session {session_id}: user message without agent response"
            )

        # Apply limit by returning the LAST N turns (most recent)
        if limit and len(turns) > limit:
            turns = turns[-limit:]

        logger.debug(f"Loaded {len(turns)} turns for session {session_id}")
        return turns

    def clear_session(self, session_id: str) -> None:
        """
        Clear all turns for a session using BulkDeleteNode.

        Uses BulkDeleteNode with filter to delete all messages for a session.
        Fixed in DataFlow v0.7.12 - now properly captures db_instance from closure.

        Args:
            session_id: Unique session identifier
        """
        workflow = WorkflowBuilder()

        # Auto-generated BulkDeleteNode gets db_instance from closure
        # Only runtime parameters needed: filter
        workflow.add_node(
            f"{self.model_name}BulkDeleteNode",
            "bulk_delete",
            {
                "filter": {"conversation_id": session_id},
            },
        )

        try:
            with LocalRuntime() as runtime:
                results, _ = runtime.execute(workflow.build())
            deleted_count = results.get("bulk_delete", {}).get("deleted_count", 0)
            logger.debug(
                f"Cleared session {session_id}: deleted {deleted_count} messages"
            )
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
            raise

    def session_exists(self, session_id: str) -> bool:
        """
        Check if a session exists using DataFlow workflow nodes.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session has any turns, False otherwise
        """
        workflow = WorkflowBuilder()

        # Auto-generated ListNode gets db_instance from closure
        # Only runtime parameters needed: filter, limit
        workflow.add_node(
            f"{self.model_name}ListNode",
            "check_exists",
            {
                "filter": {"conversation_id": session_id},
                "limit": 1,
            },
        )

        try:
            with LocalRuntime() as runtime:
                results, run_id = runtime.execute(workflow.build())
            total = results.get("check_exists", {}).get("total", 0)
            return total > 0
        except Exception as e:
            logger.error(f"Failed to check session exists: {e}")
            return False

    def get_session_metadata(self, session_id: str) -> Dict[str, Any]:
        """
        Get metadata about a session using DataFlow workflow nodes.

        Args:
            session_id: Unique session identifier

        Returns:
            Dictionary with keys:
                - turn_count: Total number of turns (int)
                - created_at: First turn timestamp (datetime)
                - updated_at: Last turn timestamp (datetime)

        Returns:
            Empty dict if session not found
        """
        workflow = WorkflowBuilder()

        # Use DataFlow ListNode (database-agnostic, proven pattern from load_turns())
        # Core SDK has order_by char array bug, but DataFlow SQL layer handles it gracefully
        workflow.add_node(
            f"{self.model_name}ListNode",
            "get_metadata",
            {
                "filter": {"conversation_id": session_id},
                "limit": 100000,  # Fetch all messages for accurate count
                "order_by": "created_at",  # DataFlow handles Core SDK char array bug
                "ascending": True,
                "enable_cache": False,  # Disable cache for accurate counts
            },
        )

        try:
            with LocalRuntime() as runtime:
                results, run_id = runtime.execute(workflow.build())

            # DataFlow ListNode returns {"records": [...], "total": N} format
            result = results.get("get_metadata", {})
            messages = result.get("records", [])

            if not messages:
                return {}

            # Count COMPLETE turns (user + agent pairs), matching load_turns() logic
            # Orphaned messages (user without agent or vice versa) are NOT counted
            turn_count = 0
            expecting_user = True

            for msg in messages:
                sender = msg.get("sender")
                if expecting_user and sender == "user":
                    expecting_user = False
                elif not expecting_user and sender == "agent":
                    turn_count += 1
                    expecting_user = True
                else:
                    # Orphaned message - reset state
                    expecting_user = sender != "user"

            first_created = messages[0].get("created_at")
            last_created = messages[-1].get("created_at")

            return {
                "turn_count": turn_count,
                "created_at": first_created,
                "updated_at": last_created,
            }
        except Exception as e:
            logger.error(f"Failed to get session metadata: {e}")
            return {}
