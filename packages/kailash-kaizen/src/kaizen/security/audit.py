"""Audit trail system for Kaizen AI framework."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class AuditTrailProvider:
    """Audit trail provider with pluggable storage backends.

    Supports:
    - memory: In-memory storage (Tier 1 testing)
    - postgresql: PostgreSQL database (Tier 2+ production)
    """

    def __init__(
        self, storage: str = "memory", connection_string: Optional[str] = None
    ):
        """Initialize audit trail provider.

        Args:
            storage: Storage backend ("memory" or "postgresql")
            connection_string: Database connection string (required for postgresql)

        Raises:
            ValueError: If storage backend is unknown or connection_string missing for postgresql
        """
        self.storage = storage
        self.connection_string = connection_string
        self._conn = None

        if storage == "memory":
            # In-memory storage for Tier 1 tests
            self._events: Dict[str, Dict[str, Any]] = {}
        elif storage == "postgresql":
            if not connection_string:
                raise ValueError("connection_string required for postgresql storage")
            self._events = None  # Not used for postgresql
        else:
            raise ValueError(f"Unknown storage backend: {storage}")

    def initialize(self):
        """Initialize storage backend (create tables for postgresql).

        For memory backend: no-op
        For postgresql backend: creates audit_events table
        """
        if self.storage == "postgresql":
            import psycopg2

            self._conn = psycopg2.connect(self.connection_string)
            cursor = self._conn.cursor()

            # Create audit_events table (immutable/append-only design)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id VARCHAR(36) PRIMARY KEY,
                    user_name VARCHAR(255) NOT NULL,
                    action VARCHAR(255) NOT NULL,
                    result VARCHAR(50) NOT NULL,
                    metadata JSONB,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL
                )
            """
            )

            # Create index for common queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_name)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)
            """
            )

            self._conn.commit()
            cursor.close()
        # Memory backend doesn't need initialization

    def cleanup(self):
        """Cleanup resources (close connection, drop test tables).

        For memory backend: clears in-memory storage
        For postgresql backend: drops tables and closes connection
        """
        if self.storage == "postgresql" and self._conn:
            cursor = self._conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS audit_events CASCADE")
            self._conn.commit()
            cursor.close()
            self._conn.close()
            self._conn = None
        elif self.storage == "memory":
            self._events.clear()

    def log_event(
        self,
        user: str,
        action: str,
        result: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Log an audit event.

        Args:
            user: Username performing the action
            action: Action being audited
            result: Result of the action (success/failure)
            metadata: Additional event metadata

        Returns:
            Event ID (UUID string)
        """
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)

        if self.storage == "memory":
            event = {
                "user": user,
                "action": action,
                "result": result,
                "metadata": metadata or {},
                "timestamp": timestamp,
            }
            self._events[event_id] = event

        elif self.storage == "postgresql":
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_events (event_id, user_name, action, result, metadata, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (event_id, user, action, result, json.dumps(metadata or {}), timestamp),
            )
            self._conn.commit()
            cursor.close()

        return event_id

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an audit event by ID.

        Args:
            event_id: Event ID to retrieve

        Returns:
            Event data or None if not found
        """
        if self.storage == "memory":
            return self._events.get(event_id)

        elif self.storage == "postgresql":
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT user_name, action, result, metadata, timestamp FROM audit_events WHERE event_id = %s",
                (event_id,),
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                return {
                    "user": row[0],
                    "action": row[1],
                    "result": row[2],
                    "metadata": row[3],  # JSONB auto-converted to dict by psycopg2
                    "timestamp": row[4],
                }
            return None

    def query_events(
        self,
        user: Optional[str] = None,
        action: Optional[str] = None,
        result: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: str = "timestamp",
        order: str = "desc",
    ) -> list[Dict[str, Any]]:
        """
        Query audit events with filters, pagination, and sorting.

        Args:
            user: Filter by username
            action: Filter by action
            result: Filter by result (success/failure)
            start_time: Filter by start timestamp
            end_time: Filter by end timestamp
            limit: Maximum number of results to return
            offset: Number of results to skip (for pagination)
            sort_by: Field to sort by (timestamp, user, action, result)
            order: Sort order (asc or desc)

        Returns:
            List of matching events
        """
        if self.storage == "memory":
            results = []

            for event in self._events.values():
                # Apply filters
                if user is not None and event["user"] != user:
                    continue
                if action is not None and event["action"] != action:
                    continue
                if result is not None and event["result"] != result:
                    continue
                if start_time is not None and event["timestamp"] < start_time:
                    continue
                if end_time is not None and event["timestamp"] > end_time:
                    continue

                results.append(event)

            # Sort results
            reverse = order == "desc"
            results.sort(key=lambda e: e[sort_by], reverse=reverse)

            # Apply pagination
            if offset is not None:
                results = results[offset:]
            if limit is not None:
                results = results[:limit]

            return results

        elif self.storage == "postgresql":
            # Build dynamic query with filters
            query = "SELECT user_name, action, result, metadata, timestamp FROM audit_events WHERE 1=1"
            params = []

            if user is not None:
                query += " AND user_name = %s"
                params.append(user)
            if action is not None:
                query += " AND action = %s"
                params.append(action)
            if result is not None:
                query += " AND result = %s"
                params.append(result)
            if start_time is not None:
                query += " AND timestamp >= %s"
                params.append(start_time)
            if end_time is not None:
                query += " AND timestamp <= %s"
                params.append(end_time)

            # Add sorting
            sort_column = {
                "timestamp": "timestamp",
                "user": "user_name",
                "action": "action",
                "result": "result",
            }.get(sort_by, "timestamp")

            order_dir = "DESC" if order == "desc" else "ASC"
            query += f" ORDER BY {sort_column} {order_dir}"

            # Add pagination
            if limit is not None:
                query += f" LIMIT {limit}"
            if offset is not None:
                query += f" OFFSET {offset}"

            cursor = self._conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()

            results = []
            for row in rows:
                results.append(
                    {
                        "user": row[0],
                        "action": row[1],
                        "result": row[2],
                        "metadata": row[3],
                        "timestamp": row[4],
                    }
                )

            return results

    def count_events(
        self,
        user: Optional[str] = None,
        action: Optional[str] = None,
        result: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """
        Count audit events matching filters.

        Args:
            user: Filter by username
            action: Filter by action
            result: Filter by result (success/failure)
            start_time: Filter by start timestamp
            end_time: Filter by end timestamp

        Returns:
            Count of matching events
        """
        if self.storage == "memory":
            count = 0
            for event in self._events.values():
                # Apply filters
                if user is not None and event["user"] != user:
                    continue
                if action is not None and event["action"] != action:
                    continue
                if result is not None and event["result"] != result:
                    continue
                if start_time is not None and event["timestamp"] < start_time:
                    continue
                if end_time is not None and event["timestamp"] > end_time:
                    continue
                count += 1
            return count

        elif self.storage == "postgresql":
            # Build dynamic query with filters
            query = "SELECT COUNT(*) FROM audit_events WHERE 1=1"
            params = []

            if user is not None:
                query += " AND user_name = %s"
                params.append(user)
            if action is not None:
                query += " AND action = %s"
                params.append(action)
            if result is not None:
                query += " AND result = %s"
                params.append(result)
            if start_time is not None:
                query += " AND timestamp >= %s"
                params.append(start_time)
            if end_time is not None:
                query += " AND timestamp <= %s"
                params.append(end_time)

            cursor = self._conn.cursor()
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            cursor.close()
            return count
