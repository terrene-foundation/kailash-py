"""
DataFlow Models for Nexus Session Persistence.

Defines database schemas for cross-channel session storage using DataFlow.
Uses DataFlow @db.model decorator for automatic node generation.

Note: These are DataFlow model definitions, NOT traditional dataclasses.
DataFlow models:
- Use string IDs (not UUID types)
- Auto-generate 11 workflow nodes per model
- Use dict for complex types (JSON in database)
- Auto-manage created_at and updated_at fields

Example:
    from dataflow import DataFlow
    from kaizen.integrations.nexus.models import register_session_models

    db = DataFlow("postgresql://...")
    models = register_session_models(db)

    # Now you can use:
    # - CrossChannelSessionCreateNode
    # - CrossChannelSessionReadNode
    # - CrossChannelSessionUpdateNode
    # - CrossChannelSessionDeleteNode
    # - CrossChannelSessionListNode
    # - etc.
"""

from typing import Any, Dict, Optional, Type


def register_session_models(db: "DataFlow") -> Dict[str, Type]:
    """
    Register session-related DataFlow models with a DataFlow instance.

    This function registers the CrossChannelSession model with the
    provided DataFlow instance, which automatically generates 11
    workflow nodes for database operations.

    Args:
        db: DataFlow instance to register models with

    Returns:
        Dictionary mapping model names to model classes:
        - "CrossChannelSession": The session model

    Generated Nodes (11 per model):
        - CrossChannelSessionCreateNode: Create single record
        - CrossChannelSessionReadNode: Read by ID
        - CrossChannelSessionUpdateNode: Update record
        - CrossChannelSessionDeleteNode: Delete record
        - CrossChannelSessionListNode: List with filters
        - CrossChannelSessionUpsertNode: Insert or update
        - CrossChannelSessionCountNode: Count records
        - CrossChannelSessionBulkCreateNode: Bulk insert
        - CrossChannelSessionBulkUpdateNode: Bulk update
        - CrossChannelSessionBulkDeleteNode: Bulk delete
        - CrossChannelSessionBulkUpsertNode: Bulk upsert

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("sqlite:///sessions.db")
        >>> models = register_session_models(db)
        >>> print(models.keys())
        dict_keys(['CrossChannelSession'])
    """

    @db.model
    class CrossChannelSession:
        """
        Persistent cross-channel session for Nexus deployments.

        Stores session state shared across API, CLI, and MCP channels.
        Uses JSONB for complex nested structures (state, channel_activity).

        Attributes:
            id: Unique session ID (UUID string, primary key)
            user_id: User identifier
            created_at: Session creation timestamp (auto-managed)
            last_accessed: Last access timestamp (ISO string)
            expires_at: Session expiration timestamp (ISO string)
            state_json: JSON session state (stored as str)
            channel_activity_json: JSON channel activity tracking (stored as str)
            memory_pool_id: Optional memory pool binding

        Database Schema (PostgreSQL):
            - id: TEXT PRIMARY KEY
            - user_id: TEXT NOT NULL
            - created_at: TIMESTAMP (auto-managed)
            - updated_at: TIMESTAMP (auto-managed)
            - last_accessed: TEXT (ISO datetime string)
            - expires_at: TEXT (ISO datetime string)
            - state_json: TEXT (JSON object as string)
            - channel_activity_json: TEXT (JSON object as string)
            - memory_pool_id: TEXT NULL

        Note on JSON Fields:
            DataFlow stores complex types (list, dict) as JSON strings.
            Use json.dumps() when saving and json.loads() when reading.
            The storage backend handles this conversion automatically.
        """

        # Primary key - must be named 'id' for DataFlow
        id: str

        # User identification
        user_id: str = ""

        # Timestamps stored as ISO strings
        # (created_at and updated_at are auto-managed by DataFlow)
        last_accessed: str = ""  # ISO format datetime string
        expires_at: str = ""  # ISO format datetime string

        # JSON fields stored as strings (DataFlow serialization)
        # Use json.dumps(dict) to store, json.loads(str) to read
        state_json: str = "{}"  # Session state as JSON object
        channel_activity_json: str = "{}"  # Channel activity as JSON object

        # Memory pool binding (optional)
        memory_pool_id: Optional[str] = None

    return {
        "CrossChannelSession": CrossChannelSession,
    }


# Export model registration function
__all__ = [
    "register_session_models",
]
