"""
Audit Store — thin adapter importing shared types from kailash.trust.

Shared types (AuditStore ABC, AuditStoreError, AuditAnchorNotFoundError,
AuditStoreImmutabilityError, AuditRecord, IntegrityVerificationResult,
AppendOnlyAuditStore) live in ``kailash.trust.audit_store``.  This file re-exports
them for backwards compatibility and keeps the Kaizen-specific DataFlow-backed
``PostgresAuditStore`` which depends on ``kailash.runtime`` and ``dataflow``.
"""

import os
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ---------- shared types (from kailash.trust) ----------
from kailash.trust.audit_store import (  # noqa: F401
    AppendOnlyAuditStore,
    AuditAnchorNotFoundError,
    AuditRecord,
    AuditStore,
    AuditStoreError,
    AuditStoreImmutabilityError,
    IntegrityVerificationResult,
)

from kaizen.trust.chain import ActionResult, AuditAnchor
from kaizen.trust.exceptions import TrustStoreDatabaseError


class PostgresAuditStore(AuditStore):
    """
    PostgreSQL-backed audit store using DataFlow.

    Provides append-only storage for audit records with efficient
    querying capabilities. Uses JSONB for flexible storage.

    Performance Characteristics:
    - append(): ~5-10ms
    - get(): <5ms with caching
    - get_agent_history(): ~10-50ms depending on filters
    - get_action_chain(): ~20-100ms depending on chain depth

    Example:
        >>> store = PostgresAuditStore()
        >>> await store.initialize()
        >>>
        >>> # Append audit record
        >>> anchor = AuditAnchor(
        ...     id="aud-001",
        ...     agent_id="agent-001",
        ...     action="analyze_data",
        ...     timestamp=datetime.now(timezone.utc),
        ...     trust_chain_hash="abc123",
        ...     result=ActionResult.SUCCESS,
        ...     signature="sig",
        ... )
        >>> await store.append(anchor)
        >>>
        >>> # Query history
        >>> history = await store.get_agent_history("agent-001")
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        enable_cache: bool = True,
        cache_ttl_seconds: int = 60,  # Short TTL for audit data
        runtime: Optional[AsyncLocalRuntime] = None,
    ):
        """
        Initialize PostgresAuditStore.

        Args:
            database_url: PostgreSQL connection string
            enable_cache: Enable caching for get operations
            cache_ttl_seconds: Cache TTL in seconds
            runtime: Optional shared AsyncLocalRuntime (avoids pool leak)
        """
        self.database_url = database_url or os.getenv("POSTGRES_URL")
        if not self.database_url:
            raise TrustStoreDatabaseError(
                "No database URL provided. Set POSTGRES_URL environment variable "
                "or pass database_url parameter."
            )

        self.enable_cache = enable_cache
        self.cache_ttl_seconds = cache_ttl_seconds

        # Initialize DataFlow instance
        self.db = DataFlow(
            self.database_url,
            enable_caching=enable_cache,
            cache_ttl=cache_ttl_seconds,
        )

        # Define the AuditRecord model
        @self.db.model
        class AuditRecord:
            """Database model for audit anchors."""

            id: str  # Anchor ID
            agent_id: str  # Agent that performed action
            action: str  # Action performed
            resource: Optional[str] = None  # Resource affected
            timestamp: datetime  # When action occurred
            trust_chain_hash: str  # Hash at action time
            result: str  # ActionResult value
            parent_anchor_id: Optional[str] = None  # Parent action link
            anchor_data: Dict[str, Any]  # Full serialized AuditAnchor
            signature: str  # Cryptographic signature

        self._AuditRecord = AuditRecord

        # Runtime for workflow execution
        if runtime is not None:
            self.runtime = runtime.acquire()
            self._owns_runtime = False
        else:
            self.runtime = AsyncLocalRuntime()
            self._owns_runtime = True

        # In-memory cache for frequently accessed anchors
        self._cache: Dict[str, tuple[AuditAnchor, datetime]] = {}

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the audit store."""
        if self._initialized:
            return
        self._initialized = True

    async def append(self, anchor: AuditAnchor) -> str:
        """
        Append an audit anchor to the store.

        This is the only write operation allowed - no updates or deletes.

        Args:
            anchor: The audit anchor to store

        Returns:
            The anchor ID

        Raises:
            AuditStoreError: If storage fails
        """
        try:
            # Serialize anchor to dictionary using to_dict() which includes
            # all fields (reasoning trace, human origin, etc.), not just the
            # signing payload which intentionally excludes reasoning fields.
            anchor_dict = anchor.to_dict()

            # Build workflow using AuditRecord_Create node
            # Note: We use Create, not Upsert, to enforce append-only
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AuditRecord_Create",
                "create_audit",
                {
                    "id": anchor.id,
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "timestamp": anchor.timestamp,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "result": anchor.result.value,
                    "parent_anchor_id": anchor.parent_anchor_id,
                    "anchor_data": anchor_dict,
                    "signature": anchor.signature,
                },
            )

            # Execute workflow
            await self.runtime.execute_workflow_async(workflow.build(), inputs={})

            # Cache the anchor
            if self.enable_cache:
                self._cache[anchor.id] = (anchor, datetime.now(timezone.utc))

            return anchor.id

        except Exception as e:
            raise AuditStoreError(
                f"Failed to append audit anchor {anchor.id}: {str(e)}"
            ) from e

    async def get(self, anchor_id: str) -> AuditAnchor:
        """
        Retrieve an audit anchor by ID.

        Args:
            anchor_id: The anchor ID to retrieve

        Returns:
            The AuditAnchor

        Raises:
            AuditAnchorNotFoundError: If not found
        """
        try:
            # Check cache first
            if self.enable_cache and anchor_id in self._cache:
                cached_anchor, cached_time = self._cache[anchor_id]
                cache_age = (datetime.now(timezone.utc) - cached_time).total_seconds()
                if cache_age < self.cache_ttl_seconds:
                    return cached_anchor

            # Build workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AuditRecord_Read",
                "read_audit",
                {"id": anchor_id},
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            record = results.get("read_audit", {}).get("result")

            if not record:
                raise AuditAnchorNotFoundError(anchor_id)

            # Deserialize anchor
            anchor = self._deserialize_anchor(record)

            # Cache it
            if self.enable_cache:
                self._cache[anchor_id] = (anchor, datetime.now(timezone.utc))

            return anchor

        except AuditAnchorNotFoundError:
            raise
        except Exception as e:
            raise AuditStoreError(
                f"Failed to retrieve audit anchor {anchor_id}: {str(e)}"
            ) from e

    async def get_agent_history(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        actions: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditAnchor]:
        """
        Get audit history for an agent.

        Args:
            agent_id: Agent to query
            start_time: Filter by start time
            end_time: Filter by end time
            actions: Filter by action types
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of AuditAnchors ordered by timestamp descending
        """
        try:
            # Build filter
            filters = {"agent_id": agent_id}

            # Build workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AuditRecord_List",
                "list_audits",
                {
                    "filter": filters,
                    "limit": limit,
                    "offset": offset,
                    "order_by": ["-timestamp"],  # Descending
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            records = results.get("list_audits", {}).get("records", [])

            # Deserialize and apply additional filters
            anchors = []
            for record in records:
                anchor = self._deserialize_anchor(record)

                # Apply time filters (DataFlow may not support all filters)
                if start_time and anchor.timestamp < start_time:
                    continue
                if end_time and anchor.timestamp > end_time:
                    continue
                if actions and anchor.action not in actions:
                    continue

                anchors.append(anchor)

            return anchors

        except Exception as e:
            raise AuditStoreError(
                f"Failed to get agent history for {agent_id}: {str(e)}"
            ) from e

    async def get_action_chain(
        self,
        anchor_id: str,
    ) -> List[AuditAnchor]:
        """
        Get the full chain of related actions.

        Traverses parent_anchor_id links to build the complete
        causal chain from root action to the specified anchor.

        Args:
            anchor_id: Starting anchor ID

        Returns:
            List of AuditAnchors from root to anchor_id (oldest first)
        """
        try:
            chain = []
            current_id = anchor_id

            # Traverse up the chain
            while current_id:
                anchor = await self.get(current_id)
                chain.append(anchor)
                current_id = anchor.parent_anchor_id

            # Reverse to get oldest first
            return list(reversed(chain))

        except AuditAnchorNotFoundError:
            raise
        except Exception as e:
            raise AuditStoreError(
                f"Failed to get action chain for {anchor_id}: {str(e)}"
            ) from e

    async def query_by_action(
        self,
        action: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        result: Optional[ActionResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditAnchor]:
        """
        Query audit records by action type.

        Args:
            action: Action type to query
            start_time: Filter by start time
            end_time: Filter by end time
            result: Filter by action result
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of matching AuditAnchors
        """
        try:
            # Build filter
            filters = {"action": action}
            if result:
                filters["result"] = result.value

            # Build workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AuditRecord_List",
                "list_by_action",
                {
                    "filter": filters,
                    "limit": limit,
                    "offset": offset,
                    "order_by": ["-timestamp"],
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            records = results.get("list_by_action", {}).get("records", [])

            # Deserialize and apply time filters
            anchors = []
            for record in records:
                anchor = self._deserialize_anchor(record)

                if start_time and anchor.timestamp < start_time:
                    continue
                if end_time and anchor.timestamp > end_time:
                    continue

                anchors.append(anchor)

            return anchors

        except Exception as e:
            raise AuditStoreError(
                f"Failed to query audits by action {action}: {str(e)}"
            ) from e

    async def count_by_agent(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """
        Count audit records for an agent.

        Args:
            agent_id: Agent to count
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            Number of matching records
        """
        try:
            # Build filter
            filters = {"agent_id": agent_id}

            # Build workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AuditRecord_Count",
                "count_audits",
                {"filter": filters},
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            count = results.get("count_audits", {}).get("count", 0)

            # Note: Time filtering may need to be done differently
            # if DataFlow doesn't support range queries
            return count

        except Exception as e:
            raise AuditStoreError(
                f"Failed to count audits for agent {agent_id}: {str(e)}"
            ) from e

    def _deserialize_anchor(self, record: Dict[str, Any]) -> AuditAnchor:
        """
        Deserialize an AuditAnchor from a database record.

        Preserves reasoning trace fields when present (backward compatible).

        Args:
            record: Database record

        Returns:
            AuditAnchor instance
        """
        anchor_data = record.get("anchor_data", {})

        # Reasoning trace deserialization (backward compatible — None if absent)
        reasoning_trace = None
        reasoning_trace_dict = anchor_data.get("reasoning_trace")
        if reasoning_trace_dict:
            from kailash.trust.reasoning.traces import ReasoningTrace

            reasoning_trace = ReasoningTrace.from_dict(reasoning_trace_dict)

        return AuditAnchor(
            id=record["id"],
            agent_id=record["agent_id"],
            action=record["action"],
            resource=record.get("resource"),
            timestamp=(
                record["timestamp"]
                if isinstance(record["timestamp"], datetime)
                else datetime.fromisoformat(record["timestamp"])
            ),
            trust_chain_hash=record["trust_chain_hash"],
            result=ActionResult(record["result"]),
            parent_anchor_id=record.get("parent_anchor_id"),
            signature=record["signature"],
            context=anchor_data.get("context", {}),
            # Reasoning trace extension (preserved from anchor_data)
            reasoning_trace=reasoning_trace,
            reasoning_trace_hash=anchor_data.get("reasoning_trace_hash"),
            reasoning_signature=anchor_data.get("reasoning_signature"),
        )

    # Explicitly prevent update and delete operations

    async def update(self, *args, **kwargs):
        """Update is not allowed - audit records are immutable."""
        raise AuditStoreImmutabilityError("update")

    async def delete(self, *args, **kwargs):
        """Delete is not allowed - audit records are immutable."""
        raise AuditStoreImmutabilityError("delete")

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()

    async def close(self) -> None:
        """Close database connections and release runtime."""
        self._cache.clear()
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.release()
            self.runtime = None

    def __del__(self, _warnings=warnings):
        if getattr(self, "runtime", None) is not None:
            _warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() explicitly.",
                ResourceWarning,
                source=self,
            )
            try:
                self.runtime.release()
                self.runtime = None
            except Exception:
                pass
