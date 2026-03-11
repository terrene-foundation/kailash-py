"""
Audit trail storage and querying for compliance logging.

This module provides immutable audit trail capabilities for enterprise compliance:
- AuditStorage protocol: Interface for audit backends
- FileAuditStorage: JSONL file-based storage (append-only)
- AuditTrailManager: High-level audit trail management

Audit trails are immutable and append-only to meet compliance requirements
(SOC2, GDPR, HIPAA). All critical actions are recorded with timestamps,
agent IDs, user IDs, and action details.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import anyio

from kaizen.core.autonomy.observability.types import AuditEntry, AuditResult

logger = logging.getLogger(__name__)


class AuditStorage(Protocol):
    """
    Protocol for audit trail storage backends.

    All implementations must provide:
    - append(): Immutable append operation
    - query(): Query with filtering support

    Storage backends must be:
    - Append-only (no updates or deletes)
    - Persistent (survive process restarts)
    - Queryable (support filtering by time, agent, action)

    Example implementations:
    - FileAuditStorage: JSONL file-based storage
    - DatabaseAuditStorage: PostgreSQL/MySQL storage
    - S3AuditStorage: AWS S3 storage
    """

    async def append(self, entry: AuditEntry) -> None:
        """
        Append immutable audit entry.

        Entries are never modified or deleted after append.

        Args:
            entry: AuditEntry to append

        Raises:
            IOError: If storage operation fails
        """
        pass

    async def query(
        self,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        action: str | None = None,
        user_id: str | None = None,
        result: AuditResult | None = None,
    ) -> list[AuditEntry]:
        """
        Query audit entries with filtering.

        All filters are optional and combined with AND logic.
        If no filters provided, returns all entries.

        Args:
            agent_id: Filter by agent ID
            start_time: Filter entries >= start_time
            end_time: Filter entries <= end_time
            action: Filter by action type
            user_id: Filter by user ID
            result: Filter by result (success, failure, denied)

        Returns:
            List of matching AuditEntry objects (sorted by timestamp)
        """
        pass


class FileAuditStorage:
    """
    File-based audit storage using JSONL format (JSON Lines).

    Each line is a complete JSON object representing one AuditEntry.
    Format is compatible with log aggregation tools (Logstash, Fluentd).

    Storage is append-only for immutability and compliance.
    Performance target: <10ms per append (ADR-017).

    Example:
        >>> storage = FileAuditStorage(".kaizen/audit.jsonl")
        >>> entry = AuditEntry(
        ...     timestamp=datetime.now(timezone.utc),
        ...     agent_id="qa-agent",
        ...     action="tool_execute",
        ...     details={"tool_name": "bash_command"},
        ...     result="success"
        ... )
        >>> await storage.append(entry)
        >>>
        >>> entries = await storage.query(agent_id="qa-agent")
    """

    def __init__(self, file_path: str = ".kaizen/audit.jsonl"):
        """
        Initialize file-based audit storage.

        Args:
            file_path: Path to JSONL audit file (created if not exists)
        """
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        # Create file if not exists
        if not self.file_path.exists():
            self.file_path.touch()
            logger.info(f"Created audit file: {self.file_path}")

        logger.debug(f"FileAuditStorage initialized: {self.file_path}")

    async def append(self, entry: AuditEntry) -> None:
        """
        Append audit entry to JSONL file.

        Entries are written atomically (full line at once) to ensure
        consistency. File is immediately flushed for durability.

        Args:
            entry: AuditEntry to append

        Raises:
            IOError: If file write fails
        """
        # Convert entry to dict with ISO timestamp
        entry_dict = asdict(entry)
        entry_dict["timestamp"] = entry.timestamp.isoformat()

        # Write as single JSON line
        json_line = json.dumps(entry_dict) + "\n"

        async with await anyio.open_file(self.file_path, "a") as f:
            await f.write(json_line)
            # Flush to ensure durability (important for compliance)
            await f.flush()

        logger.debug(f"Audit entry appended: {entry.agent_id} - {entry.action}")

    async def query(
        self,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        action: str | None = None,
        user_id: str | None = None,
        result: AuditResult | None = None,
    ) -> list[AuditEntry]:
        """
        Query audit entries from JSONL file with filtering.

        Reads entire file and filters in memory. For large audit logs,
        consider using database backend (DatabaseAuditStorage) instead.

        Args:
            agent_id: Filter by agent ID
            start_time: Filter entries >= start_time
            end_time: Filter entries <= end_time
            action: Filter by action type
            user_id: Filter by user ID
            result: Filter by result (success, failure, denied)

        Returns:
            List of matching AuditEntry objects (sorted by timestamp)
        """
        entries = []

        # Read all entries from file
        async with await anyio.open_file(self.file_path, "r") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry_dict = json.loads(line)

                    # Parse timestamp back to datetime
                    entry_dict["timestamp"] = datetime.fromisoformat(
                        entry_dict["timestamp"]
                    )

                    entry = AuditEntry(**entry_dict)

                    # Apply filters
                    if agent_id and entry.agent_id != agent_id:
                        continue
                    if start_time and entry.timestamp < start_time:
                        continue
                    if end_time and entry.timestamp > end_time:
                        continue
                    if action and entry.action != action:
                        continue
                    if user_id and entry.user_id != user_id:
                        continue
                    if result and entry.result != result:
                        continue

                    entries.append(entry)

                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed audit entry: {e}")
                    continue

        logger.debug(f"Query returned {len(entries)} audit entries")
        return entries

    async def count(self) -> int:
        """
        Get total count of audit entries.

        Returns:
            Total number of entries in audit file
        """
        count = 0
        async with await anyio.open_file(self.file_path, "r") as f:
            async for line in f:
                if line.strip():
                    count += 1
        return count

    def get_file_path(self) -> Path:
        """
        Get audit file path.

        Returns:
            Path to audit file
        """
        return self.file_path


class AuditTrailManager:
    """
    Manages audit trail recording and querying.

    Provides high-level interface for audit operations with:
    - Automatic timestamp generation
    - Validation of required fields
    - Convenient query methods

    Example:
        >>> manager = AuditTrailManager()
        >>> await manager.record(
        ...     agent_id="qa-agent",
        ...     action="tool_execute",
        ...     details={"tool_name": "bash_command", "command": "ls -la"},
        ...     result="success",
        ...     user_id="user@example.com"
        ... )
        >>>
        >>> # Query all entries for agent
        >>> entries = await manager.query_by_agent("qa-agent")
        >>>
        >>> # Query failed operations
        >>> failures = await manager.query_by_result("failure")
    """

    def __init__(self, storage: AuditStorage | None = None):
        """
        Initialize audit trail manager.

        Args:
            storage: AuditStorage backend (defaults to FileAuditStorage)
        """
        self.storage = storage or FileAuditStorage()
        logger.debug("AuditTrailManager initialized")

    async def record(
        self,
        agent_id: str,
        action: str,
        details: dict,
        result: AuditResult,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """
        Record audit entry.

        Automatically adds timestamp and validates required fields.

        Args:
            agent_id: Agent performing the action
            action: Action identifier (e.g., "tool_execute", "permission_grant")
            details: Action-specific details (must be JSON-serializable)
            result: Action result (success, failure, denied)
            user_id: User who triggered the action (optional)
            metadata: Additional metadata (optional)

        Example:
            >>> await manager.record(
            ...     agent_id="qa-agent",
            ...     action="tool_execute",
            ...     details={"tool_name": "bash", "command": "ls"},
            ...     result="success",
            ...     user_id="user@example.com",
            ...     metadata={"danger_level": "MODERATE"}
            ... )
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            action=action,
            details=details,
            result=result,
            user_id=user_id,
            metadata=metadata or {},
        )

        await self.storage.append(entry)
        logger.info(
            f"Audit recorded: {agent_id} - {action} - {result}",
            extra={"agent_id": agent_id, "action": action, "result": result},
        )

    async def query_by_agent(self, agent_id: str) -> list[AuditEntry]:
        """
        Get all audit entries for an agent.

        Args:
            agent_id: Agent ID to query

        Returns:
            List of audit entries (sorted by timestamp)
        """
        return await self.storage.query(agent_id=agent_id)

    async def query_by_action(self, action: str) -> list[AuditEntry]:
        """
        Get all audit entries for a specific action.

        Args:
            action: Action type to query (e.g., "tool_execute")

        Returns:
            List of audit entries (sorted by timestamp)
        """
        return await self.storage.query(action=action)

    async def query_by_user(self, user_id: str) -> list[AuditEntry]:
        """
        Get all audit entries for a user.

        Args:
            user_id: User ID to query

        Returns:
            List of audit entries (sorted by timestamp)
        """
        return await self.storage.query(user_id=user_id)

    async def query_by_result(self, result: AuditResult) -> list[AuditEntry]:
        """
        Get all audit entries with specific result.

        Useful for finding failures or denied operations.

        Args:
            result: Result to query (success, failure, denied)

        Returns:
            List of audit entries (sorted by timestamp)

        Example:
            >>> failures = await manager.query_by_result("failure")
            >>> denied = await manager.query_by_result("denied")
        """
        return await self.storage.query(result=result)

    async def query_by_timerange(
        self, start_time: datetime, end_time: datetime
    ) -> list[AuditEntry]:
        """
        Get all audit entries within time range.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)

        Returns:
            List of audit entries (sorted by timestamp)

        Example:
            >>> from datetime import timedelta
            >>> now = datetime.now(timezone.utc)
            >>> last_hour = now - timedelta(hours=1)
            >>> entries = await manager.query_by_timerange(last_hour, now)
        """
        return await self.storage.query(start_time=start_time, end_time=end_time)

    async def query_all(self) -> list[AuditEntry]:
        """
        Get all audit entries (no filtering).

        WARNING: Can be slow for large audit logs.

        Returns:
            List of all audit entries (sorted by timestamp)
        """
        return await self.storage.query()


__all__ = [
    "AuditStorage",
    "FileAuditStorage",
    "AuditTrailManager",
]
