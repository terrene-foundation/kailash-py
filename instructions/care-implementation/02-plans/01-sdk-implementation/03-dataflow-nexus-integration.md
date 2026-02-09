# DataFlow and Nexus Trust Integration Plan

## Overview

This document details the integration of EATP trust verification into the DataFlow and Nexus frameworks, enabling trust-aware database operations and multi-channel API security.

**Target Modules**:

- DataFlow: `apps/kailash-dataflow/src/dataflow/`
- Nexus: `apps/kailash-nexus/src/nexus/`
- Shared: New `TrustContext` type used across all frameworks

---

## Part 1: DataFlow Trust Integration

### 1.1 Trust-Aware Query Execution

**Goal**: Wrap database queries with EATP constraint envelopes for fine-grained access control.

**File**: `apps/kailash-dataflow/src/dataflow/trust/__init__.py` (NEW)

```python
"""
Trust integration for DataFlow database operations.

Provides trust-aware query execution with:
- Constraint envelope wrapping
- Cross-tenant delegation
- Cryptographically signed audit records
"""

from dataflow.trust.query_wrapper import (
    TrustAwareQueryExecutor,
    ConstraintEnvelopeWrapper,
    QueryAccessResult,
)
from dataflow.trust.audit import (
    SignedAuditRecord,
    DataFlowAuditStore,
)
from dataflow.trust.multi_tenant import (
    TenantTrustManager,
    CrossTenantDelegation,
)

__all__ = [
    "TrustAwareQueryExecutor",
    "ConstraintEnvelopeWrapper",
    "QueryAccessResult",
    "SignedAuditRecord",
    "DataFlowAuditStore",
    "TenantTrustManager",
    "CrossTenantDelegation",
]
```

**File**: `apps/kailash-dataflow/src/dataflow/trust/query_wrapper.py` (NEW)

```python
"""
Trust-aware query execution wrapper for DataFlow.

Applies EATP constraint envelopes to database queries,
ensuring agents can only access authorized data.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from kaizen.trust.chain import ConstraintEnvelope
    from kailash.runtime.trust.context import RuntimeTrustContext

logger = logging.getLogger(__name__)


@dataclass
class QueryAccessResult:
    """
    Result of query access verification.

    Attributes:
        allowed: Whether query is allowed
        filtered_columns: Columns agent can access
        filtered_rows: Row filter to apply
        denied_reason: Reason for denial (if any)
        applied_constraints: Constraints that were applied
    """
    allowed: bool
    filtered_columns: Optional[List[str]] = None
    filtered_rows: Optional[Dict[str, Any]] = None
    denied_reason: Optional[str] = None
    applied_constraints: List[str] = field(default_factory=list)


class ConstraintEnvelopeWrapper:
    """
    Wraps database queries with EATP constraint envelopes.

    Translates EATP constraints to SQL/ORM query filters:
    - data_scope constraints -> WHERE clauses
    - column_access constraints -> SELECT column filtering
    - time_window constraints -> Timestamp filters
    - row_limit constraints -> LIMIT clauses

    Example:
        >>> envelope = ConstraintEnvelope(
        ...     active_constraints=[
        ...         Constraint(type=DATA_SCOPE, value="department:finance"),
        ...         Constraint(type=ACTION_RESTRICTION, value="read_only"),
        ...     ]
        ... )
        >>> wrapper = ConstraintEnvelopeWrapper(envelope)
        >>>
        >>> # Apply to query
        >>> filtered_query = wrapper.apply_to_query(
        ...     table="transactions",
        ...     operation="SELECT",
        ...     columns=["id", "amount", "ssn"],
        ... )
        >>> # Result: SELECT id, amount FROM transactions WHERE department = 'finance'
    """

    # PII columns that require explicit access
    PII_COLUMNS = {"ssn", "social_security", "tax_id", "dob", "date_of_birth"}

    # Sensitive columns that require audit
    SENSITIVE_COLUMNS = {"salary", "password", "api_key", "secret"}

    def __init__(
        self,
        envelope: "ConstraintEnvelope",
        strict_mode: bool = True,
    ):
        self._envelope = envelope
        self._strict_mode = strict_mode
        self._parsed_constraints = self._parse_constraints()

    def _parse_constraints(self) -> Dict[str, Any]:
        """Parse constraint envelope into actionable rules."""
        rules = {
            "data_scopes": [],
            "column_restrictions": [],
            "row_filters": {},
            "operation_restrictions": set(),
            "row_limit": None,
            "time_window": None,
        }

        for constraint in self._envelope.active_constraints:
            value = str(constraint.value).lower()

            # Data scope constraints
            if constraint.constraint_type.value == "data_scope":
                rules["data_scopes"].append(value)

            # Column restrictions
            elif "column:" in value or "no_pii" in value:
                rules["column_restrictions"].append(value)

            # Operation restrictions
            elif value == "read_only":
                rules["operation_restrictions"].add("read_only")
            elif "no_" in value:
                rules["operation_restrictions"].add(value)

            # Row limits
            elif value.startswith("row_limit:"):
                try:
                    limit = int(value.split(":")[1])
                    rules["row_limit"] = limit
                except ValueError:
                    pass

        return rules

    def verify_access(
        self,
        table: str,
        operation: str,
        columns: Optional[List[str]] = None,
    ) -> QueryAccessResult:
        """
        Verify if query is allowed under constraints.

        Args:
            table: Table being accessed
            operation: SQL operation (SELECT, INSERT, UPDATE, DELETE)
            columns: Columns being accessed

        Returns:
            QueryAccessResult with access decision
        """
        columns = columns or []
        applied_constraints = []

        # Check operation restrictions
        if "read_only" in self._parsed_constraints["operation_restrictions"]:
            if operation.upper() in ("INSERT", "UPDATE", "DELETE"):
                return QueryAccessResult(
                    allowed=False,
                    denied_reason=f"Operation {operation} denied: read_only constraint",
                    applied_constraints=["read_only"],
                )
            applied_constraints.append("read_only")

        # Check column restrictions
        filtered_columns = list(columns)
        column_restrictions = self._parsed_constraints["column_restrictions"]

        # Remove PII columns unless explicitly allowed
        if "no_pii" in column_restrictions:
            pii_in_query = set(columns) & self.PII_COLUMNS
            if pii_in_query:
                if self._strict_mode:
                    return QueryAccessResult(
                        allowed=False,
                        denied_reason=f"PII columns denied: {pii_in_query}",
                        applied_constraints=["no_pii"],
                    )
                else:
                    filtered_columns = [c for c in columns if c not in self.PII_COLUMNS]
                    applied_constraints.append("no_pii:filtered")

        # Apply data scope filters
        row_filters = {}
        for scope in self._parsed_constraints["data_scopes"]:
            if ":" in scope:
                key, value = scope.split(":", 1)
                row_filters[key] = value
                applied_constraints.append(f"data_scope:{scope}")

        return QueryAccessResult(
            allowed=True,
            filtered_columns=filtered_columns if filtered_columns != columns else None,
            filtered_rows=row_filters if row_filters else None,
            applied_constraints=applied_constraints,
        )

    def apply_to_query_params(
        self,
        table: str,
        operation: str,
        columns: Optional[List[str]] = None,
        existing_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Apply constraints to query parameters.

        Returns modified query parameters suitable for DataFlow nodes.

        Args:
            table: Table being accessed
            operation: SQL operation
            columns: Columns in query
            existing_filters: Existing filter conditions

        Returns:
            Modified query parameters with constraints applied
        """
        result = self.verify_access(table, operation, columns)

        if not result.allowed:
            raise PermissionError(result.denied_reason)

        params = {}

        # Apply column filtering
        if result.filtered_columns:
            params["columns"] = result.filtered_columns

        # Apply row filtering
        if result.filtered_rows:
            combined_filters = {**(existing_filters or {}), **result.filtered_rows}
            params["filter"] = combined_filters

        # Apply row limit
        if self._parsed_constraints["row_limit"]:
            params["limit"] = min(
                self._parsed_constraints["row_limit"],
                params.get("limit", float("inf")),
            )

        return params


class TrustAwareQueryExecutor:
    """
    Executes DataFlow queries with trust verification.

    Integrates with Kaizen TrustOperations for verification and
    wraps queries with constraint envelopes.

    Example:
        >>> from kaizen.trust.operations import TrustOperations
        >>> from dataflow import DataFlow
        >>>
        >>> trust_ops = TrustOperations(...)
        >>> db = DataFlow("postgres://...")
        >>>
        >>> executor = TrustAwareQueryExecutor(
        ...     dataflow=db,
        ...     trust_operations=trust_ops,
        ... )
        >>>
        >>> # Execute with trust verification
        >>> results = await executor.execute_read(
        ...     model="User",
        ...     filter={"active": True},
        ...     agent_id="agent-123",
        ... )
    """

    def __init__(
        self,
        dataflow,
        trust_operations=None,
        audit_store=None,
        enforcement_mode: str = "enforcing",
    ):
        self._db = dataflow
        self._trust_ops = trust_operations
        self._audit_store = audit_store
        self._mode = enforcement_mode

    async def execute_read(
        self,
        model: str,
        filter: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
        trust_context: Optional["RuntimeTrustContext"] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a read query with trust verification.

        Args:
            model: DataFlow model name
            filter: Query filter
            columns: Columns to select
            agent_id: Agent making request
            trust_context: Trust context for verification

        Returns:
            Query results (potentially filtered by constraints)
        """
        # Get agent ID from context if not provided
        if agent_id is None and trust_context:
            agent_id = trust_context.delegation_chain[-1] if trust_context.delegation_chain else None

        # Verify trust if enabled
        if self._trust_ops and agent_id:
            verification = await self._trust_ops.verify(
                agent_id=agent_id,
                action=f"read:{model}",
            )

            if not verification.valid:
                if self._mode == "enforcing":
                    raise PermissionError(f"Access denied: {verification.reason}")
                else:
                    logger.warning(f"Trust verification failed: {verification.reason}")

            # Get constraint envelope
            chain = await self._trust_ops.trust_store.get_chain(agent_id)
            wrapper = ConstraintEnvelopeWrapper(chain.constraint_envelope)

            # Apply constraints to query
            modified_params = wrapper.apply_to_query_params(
                table=model,
                operation="SELECT",
                columns=columns,
                existing_filters=filter,
            )

            filter = modified_params.get("filter", filter)
            columns = modified_params.get("columns", columns)

        # Execute query via DataFlow
        # (Implementation depends on DataFlow's internal API)
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime import AsyncLocalRuntime

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{model}_List",
            "query",
            {
                "filter": filter or {},
                "columns": columns,
            },
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build())

        # Audit the query
        if self._audit_store:
            await self._audit_store.record_query(
                agent_id=agent_id,
                model=model,
                operation="SELECT",
                row_count=len(results.get("query", {}).get("records", [])),
                trust_context=trust_context,
            )

        return results.get("query", {}).get("records", [])

    async def execute_write(
        self,
        model: str,
        operation: str,  # CREATE, UPDATE, DELETE
        data: Dict[str, Any],
        agent_id: Optional[str] = None,
        trust_context: Optional["RuntimeTrustContext"] = None,
    ) -> Dict[str, Any]:
        """
        Execute a write query with trust verification.

        Args:
            model: DataFlow model name
            operation: Write operation type
            data: Data to write
            agent_id: Agent making request
            trust_context: Trust context

        Returns:
            Operation result
        """
        if agent_id is None and trust_context:
            agent_id = trust_context.delegation_chain[-1] if trust_context.delegation_chain else None

        if self._trust_ops and agent_id:
            verification = await self._trust_ops.verify(
                agent_id=agent_id,
                action=f"{operation.lower()}:{model}",
            )

            if not verification.valid:
                if self._mode == "enforcing":
                    raise PermissionError(f"Access denied: {verification.reason}")
                else:
                    logger.warning(f"Trust verification failed: {verification.reason}")

            # Check for read_only constraint
            chain = await self._trust_ops.trust_store.get_chain(agent_id)
            wrapper = ConstraintEnvelopeWrapper(chain.constraint_envelope)
            result = wrapper.verify_access(model, operation)

            if not result.allowed:
                raise PermissionError(result.denied_reason)

        # Execute write operation
        node_type = f"{model}_{operation.title()}"
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime import AsyncLocalRuntime

        workflow = WorkflowBuilder()
        workflow.add_node(node_type, "operation", data)

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build())

        # Audit the operation
        if self._audit_store:
            await self._audit_store.record_write(
                agent_id=agent_id,
                model=model,
                operation=operation,
                trust_context=trust_context,
            )

        return results.get("operation", {})
```

### 1.2 Cryptographically Signed Audit Records

**File**: `apps/kailash-dataflow/src/dataflow/trust/audit.py` (NEW)

```python
"""
Cryptographically signed audit records for DataFlow operations.

Replaces plain JSON audit logs with cryptographically signed records
that provide tamper evidence and non-repudiation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import hashlib
from uuid import uuid4


@dataclass
class SignedAuditRecord:
    """
    Cryptographically signed audit record.

    Attributes:
        record_id: Unique record identifier
        timestamp: When operation occurred
        agent_id: Agent that performed operation
        human_origin_id: Human who authorized
        model: DataFlow model accessed
        operation: Operation type (SELECT, INSERT, etc.)
        row_count: Number of rows affected
        query_hash: Hash of query parameters
        constraints_applied: Constraints that were applied
        result: Operation result (success, failure)
        signature: Ed25519 signature
        previous_record_hash: Hash of previous record (chain linking)
    """
    record_id: str
    timestamp: datetime
    agent_id: str
    model: str
    operation: str
    row_count: int = 0
    human_origin_id: Optional[str] = None
    query_hash: Optional[str] = None
    constraints_applied: List[str] = field(default_factory=list)
    result: str = "success"
    signature: str = ""
    previous_record_hash: Optional[str] = None

    def compute_hash(self) -> str:
        """Compute hash of this record for chain linking."""
        data = {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "model": self.model,
            "operation": self.operation,
            "row_count": self.row_count,
            "human_origin_id": self.human_origin_id,
            "query_hash": self.query_hash,
            "constraints_applied": sorted(self.constraints_applied),
            "result": self.result,
            "previous_record_hash": self.previous_record_hash,
        }
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def to_signing_payload(self) -> str:
        """Get payload for signing."""
        return json.dumps({
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "model": self.model,
            "operation": self.operation,
            "row_count": self.row_count,
            "query_hash": self.query_hash,
            "result": self.result,
        }, sort_keys=True)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "human_origin_id": self.human_origin_id,
            "model": self.model,
            "operation": self.operation,
            "row_count": self.row_count,
            "query_hash": self.query_hash,
            "constraints_applied": self.constraints_applied,
            "result": self.result,
            "signature": self.signature,
            "previous_record_hash": self.previous_record_hash,
        }


class DataFlowAuditStore:
    """
    Persistent audit store for DataFlow operations.

    Stores cryptographically signed, chain-linked audit records.
    Integrates with Kaizen AuditStore when available.

    Features:
    - Append-only (immutable)
    - Cryptographic signatures
    - Chain linking for tamper detection
    - Async-safe operation
    """

    def __init__(
        self,
        dataflow,
        key_manager=None,
        kaizen_audit_store=None,
    ):
        self._db = dataflow
        self._key_manager = key_manager
        self._kaizen_store = kaizen_audit_store
        self._last_record_hash: Optional[str] = None

    async def record_query(
        self,
        agent_id: str,
        model: str,
        operation: str,
        row_count: int = 0,
        query_params: Optional[Dict] = None,
        trust_context=None,
    ) -> SignedAuditRecord:
        """
        Record a database query.

        Args:
            agent_id: Agent that executed query
            model: DataFlow model queried
            operation: Query type
            row_count: Number of rows returned
            query_params: Query parameters (hashed for privacy)
            trust_context: Trust context

        Returns:
            Signed audit record
        """
        # Hash query params for privacy
        query_hash = None
        if query_params:
            query_hash = hashlib.sha256(
                json.dumps(query_params, sort_keys=True).encode()
            ).hexdigest()[:16]

        record = SignedAuditRecord(
            record_id=f"adr-{uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            human_origin_id=(
                trust_context.human_origin.human_id
                if trust_context and trust_context.human_origin
                else None
            ),
            model=model,
            operation=operation,
            row_count=row_count,
            query_hash=query_hash,
            previous_record_hash=self._last_record_hash,
        )

        # Sign the record
        if self._key_manager:
            payload = record.to_signing_payload()
            record.signature = await self._key_manager.sign(
                payload, "dataflow-audit-key"
            )

        # Update chain link
        self._last_record_hash = record.compute_hash()

        # Store record
        await self._store_record(record)

        return record

    async def record_write(
        self,
        agent_id: str,
        model: str,
        operation: str,
        affected_ids: Optional[List[str]] = None,
        trust_context=None,
    ) -> SignedAuditRecord:
        """Record a database write operation."""
        record = SignedAuditRecord(
            record_id=f"adr-{uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            human_origin_id=(
                trust_context.human_origin.human_id
                if trust_context and trust_context.human_origin
                else None
            ),
            model=model,
            operation=operation,
            row_count=len(affected_ids) if affected_ids else 1,
            previous_record_hash=self._last_record_hash,
        )

        if self._key_manager:
            record.signature = await self._key_manager.sign(
                record.to_signing_payload(), "dataflow-audit-key"
            )

        self._last_record_hash = record.compute_hash()
        await self._store_record(record)

        return record

    async def _store_record(self, record: SignedAuditRecord) -> None:
        """Store audit record in database."""
        # Store via DataFlow
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime import AsyncLocalRuntime

        # Would use a DataFlow model for audit records
        # This is a simplified example
        pass

    async def verify_chain_integrity(
        self,
        start_record_id: Optional[str] = None,
        end_record_id: Optional[str] = None,
    ) -> bool:
        """
        Verify integrity of audit chain.

        Checks that each record's previous_record_hash matches
        the computed hash of the actual previous record.

        Returns:
            True if chain is valid, False if tampering detected
        """
        # Implementation would iterate through records
        # and verify hash chain
        pass
```

### 1.3 Trust-Aware Multi-Tenancy

**File**: `apps/kailash-dataflow/src/dataflow/trust/multi_tenant.py` (NEW)

```python
"""
Trust-aware multi-tenancy for DataFlow.

Ensures cross-tenant data access requires explicit EATP delegation,
preventing unauthorized data leakage between tenants.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class CrossTenantDelegation:
    """
    Record of a cross-tenant data access delegation.

    When one tenant needs to access another tenant's data,
    an explicit delegation must be created with constraints.
    """
    delegation_id: str
    source_tenant_id: str
    target_tenant_id: str
    delegating_agent_id: str
    receiving_agent_id: str
    allowed_models: List[str]
    allowed_operations: Set[str]  # {"SELECT", "INSERT", "UPDATE", "DELETE"}
    row_filter: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def allows_access(
        self,
        model: str,
        operation: str,
    ) -> bool:
        """Check if this delegation allows the specified access."""
        if self.is_expired():
            return False
        if model not in self.allowed_models and "*" not in self.allowed_models:
            return False
        if operation not in self.allowed_operations:
            return False
        return True


class TenantTrustManager:
    """
    Manages trust relationships between tenants.

    Enforces that cross-tenant data access requires explicit
    EATP delegation chains.

    Example:
        >>> manager = TenantTrustManager(trust_operations=trust_ops)
        >>>
        >>> # Create cross-tenant delegation
        >>> delegation = await manager.create_cross_tenant_delegation(
        ...     source_tenant="tenant-a",
        ...     target_tenant="tenant-b",
        ...     delegating_agent="agent-a",
        ...     receiving_agent="agent-b",
        ...     allowed_models=["SharedReport"],
        ...     allowed_operations={"SELECT"},
        ... )
        >>>
        >>> # Verify cross-tenant access
        >>> allowed = await manager.verify_cross_tenant_access(
        ...     source_tenant="tenant-a",
        ...     target_tenant="tenant-b",
        ...     agent_id="agent-b",
        ...     model="SharedReport",
        ...     operation="SELECT",
        ... )
    """

    def __init__(
        self,
        trust_operations=None,
        strict_mode: bool = True,
    ):
        self._trust_ops = trust_operations
        self._strict_mode = strict_mode
        self._delegations: Dict[str, CrossTenantDelegation] = {}

    async def create_cross_tenant_delegation(
        self,
        source_tenant: str,
        target_tenant: str,
        delegating_agent: str,
        receiving_agent: str,
        allowed_models: List[str],
        allowed_operations: Set[str],
        row_filter: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> CrossTenantDelegation:
        """
        Create a cross-tenant delegation.

        This creates an EATP delegation record that allows one tenant's
        agent to access another tenant's data with constraints.

        Args:
            source_tenant: Tenant providing data access
            target_tenant: Tenant receiving data access
            delegating_agent: Agent in source tenant delegating access
            receiving_agent: Agent in target tenant receiving access
            allowed_models: Models that can be accessed
            allowed_operations: Operations allowed (SELECT, INSERT, etc.)
            row_filter: Optional row-level filter
            expires_at: Delegation expiry

        Returns:
            CrossTenantDelegation record
        """
        from uuid import uuid4

        delegation = CrossTenantDelegation(
            delegation_id=f"ctd-{uuid4().hex[:12]}",
            source_tenant_id=source_tenant,
            target_tenant_id=target_tenant,
            delegating_agent_id=delegating_agent,
            receiving_agent_id=receiving_agent,
            allowed_models=allowed_models,
            allowed_operations=allowed_operations,
            row_filter=row_filter,
            expires_at=expires_at,
        )

        # Create corresponding EATP delegation
        if self._trust_ops:
            for model in allowed_models:
                for op in allowed_operations:
                    await self._trust_ops.delegate(
                        delegator_id=delegating_agent,
                        delegatee_id=receiving_agent,
                        task_id=delegation.delegation_id,
                        capabilities=[f"{op.lower()}:{model}"],
                        additional_constraints=[
                            f"source_tenant:{source_tenant}",
                            f"target_tenant:{target_tenant}",
                        ],
                        expires_at=expires_at,
                    )

        self._delegations[delegation.delegation_id] = delegation
        return delegation

    async def verify_cross_tenant_access(
        self,
        source_tenant: str,
        target_tenant: str,
        agent_id: str,
        model: str,
        operation: str,
    ) -> bool:
        """
        Verify if cross-tenant access is allowed.

        Args:
            source_tenant: Tenant whose data is being accessed
            target_tenant: Tenant whose agent is accessing
            agent_id: Agent making the access request
            model: Model being accessed
            operation: Operation being performed

        Returns:
            True if access is allowed, False otherwise
        """
        # If same tenant, no cross-tenant check needed
        if source_tenant == target_tenant:
            return True

        # Find applicable delegation
        for delegation in self._delegations.values():
            if (
                delegation.source_tenant_id == source_tenant
                and delegation.target_tenant_id == target_tenant
                and delegation.receiving_agent_id == agent_id
                and delegation.allows_access(model, operation)
            ):
                # Verify via EATP
                if self._trust_ops:
                    result = await self._trust_ops.verify(
                        agent_id=agent_id,
                        action=f"{operation.lower()}:{model}",
                        context={"cross_tenant": True},
                    )
                    return result.valid
                return True

        if self._strict_mode:
            logger.warning(
                f"Cross-tenant access denied: {agent_id} from {target_tenant} "
                f"accessing {model} in {source_tenant}"
            )
        return False
```

---

## Part 2: Nexus Trust Integration

### 2.1 EATP Header Extraction

**File**: `apps/kailash-nexus/src/nexus/trust/__init__.py` (NEW)

```python
"""
Trust integration for Nexus multi-channel platform.

Provides EATP header extraction, trust verification,
and session trust context propagation.
"""

from nexus.trust.headers import (
    EATPHeaderExtractor,
    EATP_HEADERS,
)
from nexus.trust.middleware import (
    TrustMiddleware,
    TrustMiddlewareConfig,
)
from nexus.trust.session import (
    SessionTrustContext,
    TrustContextPropagator,
)

__all__ = [
    "EATPHeaderExtractor",
    "EATP_HEADERS",
    "TrustMiddleware",
    "TrustMiddlewareConfig",
    "SessionTrustContext",
    "TrustContextPropagator",
]
```

**File**: `apps/kailash-nexus/src/nexus/trust/headers.py` (NEW)

```python
"""
EATP header extraction for Nexus API requests.

Extracts trust context from HTTP headers following EATP header conventions.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json
import base64
import logging

logger = logging.getLogger(__name__)


# EATP standard header names
EATP_HEADERS = {
    "trace_id": "X-EATP-Trace-ID",
    "human_origin": "X-EATP-Human-Origin",
    "delegation_chain": "X-EATP-Delegation-Chain",
    "delegation_depth": "X-EATP-Delegation-Depth",
    "constraints": "X-EATP-Constraints",
    "agent_id": "X-EATP-Agent-ID",
    "session_id": "X-EATP-Session-ID",
    "signature": "X-EATP-Signature",
}


@dataclass
class ExtractedEATPContext:
    """
    Trust context extracted from EATP headers.

    Attributes:
        trace_id: Request correlation ID
        agent_id: Authenticated agent ID
        human_origin: Human origin JSON
        delegation_chain: List of agent IDs
        delegation_depth: Delegation depth
        constraints: Constraint JSON
        session_id: Session ID for revocation
        signature: Request signature
        raw_headers: Original headers
    """
    trace_id: Optional[str] = None
    agent_id: Optional[str] = None
    human_origin: Optional[Dict[str, Any]] = None
    delegation_chain: List[str] = None
    delegation_depth: int = 0
    constraints: Dict[str, Any] = None
    session_id: Optional[str] = None
    signature: Optional[str] = None
    raw_headers: Dict[str, str] = None

    def is_valid(self) -> bool:
        """Check if minimum required fields are present."""
        return self.trace_id is not None and self.agent_id is not None

    def has_human_origin(self) -> bool:
        """Check if human origin is present."""
        return self.human_origin is not None


class EATPHeaderExtractor:
    """
    Extracts EATP trust context from HTTP headers.

    Supports both standard EATP headers and compact JWT-like encoding.

    Example:
        >>> extractor = EATPHeaderExtractor()
        >>>
        >>> # Extract from FastAPI request
        >>> ctx = extractor.extract(request.headers)
        >>> if ctx.is_valid():
        ...     print(f"Request from agent: {ctx.agent_id}")
        ...     if ctx.has_human_origin():
        ...         print(f"Authorized by: {ctx.human_origin['human_id']}")
    """

    def __init__(
        self,
        require_signature: bool = False,
        allow_legacy_headers: bool = True,
    ):
        self._require_signature = require_signature
        self._allow_legacy = allow_legacy_headers

    def extract(
        self,
        headers: Dict[str, str],
    ) -> ExtractedEATPContext:
        """
        Extract EATP context from headers.

        Args:
            headers: HTTP headers dictionary

        Returns:
            ExtractedEATPContext with parsed values
        """
        # Normalize header names
        normalized = {k.lower(): v for k, v in headers.items()}
        header_map = {k.lower(): v for k, v in EATP_HEADERS.items()}

        result = ExtractedEATPContext(raw_headers=dict(headers))

        # Extract trace ID
        trace_header = header_map["trace_id"].lower()
        if trace_header in normalized:
            result.trace_id = normalized[trace_header]

        # Extract agent ID
        agent_header = header_map["agent_id"].lower()
        if agent_header in normalized:
            result.agent_id = normalized[agent_header]

        # Extract session ID
        session_header = header_map["session_id"].lower()
        if session_header in normalized:
            result.session_id = normalized[session_header]

        # Extract human origin (JSON)
        origin_header = header_map["human_origin"].lower()
        if origin_header in normalized:
            try:
                origin_value = normalized[origin_header]
                # Try base64 decoding first
                try:
                    decoded = base64.b64decode(origin_value).decode("utf-8")
                    result.human_origin = json.loads(decoded)
                except Exception:
                    # Try direct JSON
                    result.human_origin = json.loads(origin_value)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse human origin header: {e}")

        # Extract delegation chain
        chain_header = header_map["delegation_chain"].lower()
        if chain_header in normalized:
            try:
                chain_value = normalized[chain_header]
                if "," in chain_value:
                    result.delegation_chain = [s.strip() for s in chain_value.split(",")]
                else:
                    result.delegation_chain = json.loads(chain_value)
            except json.JSONDecodeError:
                result.delegation_chain = [chain_value]

        # Extract delegation depth
        depth_header = header_map["delegation_depth"].lower()
        if depth_header in normalized:
            try:
                result.delegation_depth = int(normalized[depth_header])
            except ValueError:
                pass

        # Extract constraints
        constraints_header = header_map["constraints"].lower()
        if constraints_header in normalized:
            try:
                constraints_value = normalized[constraints_header]
                try:
                    decoded = base64.b64decode(constraints_value).decode("utf-8")
                    result.constraints = json.loads(decoded)
                except Exception:
                    result.constraints = json.loads(constraints_value)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse constraints header: {e}")

        # Extract signature
        sig_header = header_map["signature"].lower()
        if sig_header in normalized:
            result.signature = normalized[sig_header]

        # Validate signature if required
        if self._require_signature and not result.signature:
            logger.warning("EATP signature required but not present")

        return result

    def to_headers(
        self,
        context: ExtractedEATPContext,
    ) -> Dict[str, str]:
        """
        Convert context back to headers for forwarding.

        Args:
            context: EATP context to convert

        Returns:
            Dictionary of HTTP headers
        """
        headers = {}

        if context.trace_id:
            headers[EATP_HEADERS["trace_id"]] = context.trace_id

        if context.agent_id:
            headers[EATP_HEADERS["agent_id"]] = context.agent_id

        if context.session_id:
            headers[EATP_HEADERS["session_id"]] = context.session_id

        if context.human_origin:
            encoded = base64.b64encode(
                json.dumps(context.human_origin).encode()
            ).decode()
            headers[EATP_HEADERS["human_origin"]] = encoded

        if context.delegation_chain:
            headers[EATP_HEADERS["delegation_chain"]] = ",".join(context.delegation_chain)

        headers[EATP_HEADERS["delegation_depth"]] = str(context.delegation_depth)

        if context.constraints:
            encoded = base64.b64encode(
                json.dumps(context.constraints).encode()
            ).decode()
            headers[EATP_HEADERS["constraints"]] = encoded

        if context.signature:
            headers[EATP_HEADERS["signature"]] = context.signature

        return headers
```

### 2.2 Trust Verification Middleware

**File**: `apps/kailash-nexus/src/nexus/trust/middleware.py` (NEW)

```python
"""
Trust verification middleware for Nexus API.

Integrates EATP verification into the Nexus request lifecycle.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from kaizen.trust.operations import TrustOperations

logger = logging.getLogger(__name__)


@dataclass
class TrustMiddlewareConfig:
    """
    Configuration for trust middleware.

    Attributes:
        enabled: Enable trust verification
        mode: Verification mode (disabled, permissive, enforcing)
        exempt_paths: Paths that bypass verification
        require_human_origin: Require human origin for all requests
        audit_all_requests: Log all requests to audit trail
        reject_expired_sessions: Reject requests with expired sessions
    """
    enabled: bool = True
    mode: str = "permissive"  # disabled, permissive, enforcing
    exempt_paths: List[str] = field(default_factory=lambda: [
        "/health",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
    ])
    require_human_origin: bool = False
    audit_all_requests: bool = True
    reject_expired_sessions: bool = True


class TrustMiddleware:
    """
    ASGI middleware for EATP trust verification.

    Integrates with FastAPI/Starlette to verify trust
    before workflow execution.

    Example:
        >>> from fastapi import FastAPI
        >>> from nexus.trust import TrustMiddleware, TrustMiddlewareConfig
        >>>
        >>> app = FastAPI()
        >>> trust_middleware = TrustMiddleware(
        ...     trust_operations=trust_ops,
        ...     config=TrustMiddlewareConfig(mode="enforcing"),
        ... )
        >>> app.add_middleware(trust_middleware)
    """

    def __init__(
        self,
        trust_operations: Optional["TrustOperations"] = None,
        config: Optional[TrustMiddlewareConfig] = None,
        header_extractor=None,
    ):
        self._trust_ops = trust_operations
        self._config = config or TrustMiddlewareConfig()
        self._extractor = header_extractor or EATPHeaderExtractor()

    async def __call__(
        self,
        request: "Request",
        call_next: Callable,
    ) -> "Response":
        """
        Process request through trust verification.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from handler or 403/401 on trust failure
        """
        from starlette.responses import JSONResponse

        # Check exempt paths
        if self._is_exempt(request.url.path):
            return await call_next(request)

        # Extract EATP context
        eatp_context = self._extractor.extract(dict(request.headers))

        # Store context in request state for handlers
        request.state.eatp_context = eatp_context

        # Skip verification if disabled
        if not self._config.enabled or self._config.mode == "disabled":
            return await call_next(request)

        # Verify trust
        verification_result = await self._verify_request(request, eatp_context)

        if not verification_result["allowed"]:
            if self._config.mode == "enforcing":
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "Trust verification failed",
                        "reason": verification_result["reason"],
                        "trace_id": eatp_context.trace_id,
                    },
                )
            else:
                # Permissive mode - log but continue
                logger.warning(
                    f"Trust verification failed (permissive): "
                    f"{verification_result['reason']}"
                )

        # Audit request
        if self._config.audit_all_requests:
            await self._audit_request(request, eatp_context, verification_result)

        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from verification."""
        return any(path.startswith(exempt) for exempt in self._config.exempt_paths)

    async def _verify_request(
        self,
        request: "Request",
        context: "ExtractedEATPContext",
    ) -> Dict[str, Any]:
        """
        Verify trust for request.

        Returns:
            Dict with 'allowed' bool and 'reason' string
        """
        # Check for required context
        if not context.is_valid():
            return {
                "allowed": False,
                "reason": "Missing required EATP headers (trace_id, agent_id)",
            }

        # Check human origin requirement
        if self._config.require_human_origin and not context.has_human_origin():
            return {
                "allowed": False,
                "reason": "Human origin required but not present",
            }

        # Verify with Kaizen TrustOperations
        if self._trust_ops:
            try:
                result = await self._trust_ops.verify(
                    agent_id=context.agent_id,
                    action=f"{request.method}:{request.url.path}",
                    context={
                        "http_method": request.method,
                        "path": request.url.path,
                        "session_id": context.session_id,
                    },
                )

                return {
                    "allowed": result.valid,
                    "reason": result.reason,
                    "capability_used": result.capability_used,
                }
            except Exception as e:
                logger.error(f"Trust verification error: {e}")
                return {
                    "allowed": False,
                    "reason": str(e),
                }

        # No trust ops configured - allow with warning
        logger.warning("No TrustOperations configured for middleware")
        return {"allowed": True, "reason": "No verification backend"}

    async def _audit_request(
        self,
        request: "Request",
        context: "ExtractedEATPContext",
        verification_result: Dict[str, Any],
    ) -> None:
        """Audit the request."""
        if self._trust_ops:
            try:
                await self._trust_ops.audit(
                    agent_id=context.agent_id or "unknown",
                    action=f"{request.method}:{request.url.path}",
                    context_data={
                        "http_method": request.method,
                        "path": request.url.path,
                        "verified": verification_result["allowed"],
                        "trace_id": context.trace_id,
                    },
                )
            except Exception as e:
                logger.error(f"Audit failed: {e}")
```

### 2.3 MCP + EATP Integration

**File**: `apps/kailash-nexus/src/nexus/trust/mcp_eatp.py` (NEW)

```python
"""
MCP + EATP integration for Agent-to-Agent patterns.

Combines Model Context Protocol (MCP) with EATP trust for
secure agent-to-agent communication.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class MCPEATPContext:
    """
    Combined MCP + EATP context for A2A communication.

    Attributes:
        mcp_session_id: MCP session identifier
        eatp_trace_id: EATP trace ID
        agent_id: Calling agent ID
        target_agent_id: Target agent ID
        human_origin: Human who authorized chain
        delegated_capabilities: Capabilities being delegated
        constraints: Combined MCP + EATP constraints
    """
    mcp_session_id: str
    eatp_trace_id: str
    agent_id: str
    target_agent_id: str
    human_origin: Optional[Dict[str, Any]] = None
    delegated_capabilities: List[str] = None
    constraints: Dict[str, Any] = None


class MCPEATPHandler:
    """
    Handles MCP tool calls with EATP trust verification.

    When one agent calls another via MCP, this handler ensures:
    1. The calling agent has appropriate EATP capabilities
    2. Delegation is properly created for the target agent
    3. The target agent's response is within delegated scope

    Example:
        >>> handler = MCPEATPHandler(trust_operations=trust_ops)
        >>>
        >>> # Before MCP tool call
        >>> delegation = await handler.prepare_mcp_call(
        ...     calling_agent="agent-a",
        ...     target_agent="agent-b",
        ...     tool_name="data_analysis",
        ...     mcp_session_id="sess-123",
        ... )
        >>>
        >>> # After MCP tool response
        >>> verified = await handler.verify_mcp_response(
        ...     delegation=delegation,
        ...     response=tool_response,
        ... )
    """

    def __init__(
        self,
        trust_operations=None,
        mcp_server=None,
    ):
        self._trust_ops = trust_operations
        self._mcp = mcp_server

    async def prepare_mcp_call(
        self,
        calling_agent: str,
        target_agent: str,
        tool_name: str,
        mcp_session_id: str,
        trust_context=None,
    ) -> MCPEATPContext:
        """
        Prepare an MCP call with EATP delegation.

        Creates the appropriate delegation from calling agent
        to target agent for the specified tool.

        Args:
            calling_agent: Agent making the call
            target_agent: Agent providing the tool
            tool_name: MCP tool being called
            mcp_session_id: MCP session ID
            trust_context: Current trust context

        Returns:
            MCPEATPContext with delegation info
        """
        from uuid import uuid4

        # Verify calling agent can use this tool
        if self._trust_ops:
            result = await self._trust_ops.verify(
                agent_id=calling_agent,
                action=f"mcp_call:{tool_name}",
            )

            if not result.valid:
                raise PermissionError(f"Agent cannot call tool: {result.reason}")

            # Create delegation to target agent
            delegation = await self._trust_ops.delegate(
                delegator_id=calling_agent,
                delegatee_id=target_agent,
                task_id=f"mcp-{mcp_session_id}-{uuid4().hex[:8]}",
                capabilities=[f"mcp_execute:{tool_name}"],
                context=trust_context,
            )

            return MCPEATPContext(
                mcp_session_id=mcp_session_id,
                eatp_trace_id=trust_context.trace_id if trust_context else str(uuid4()),
                agent_id=calling_agent,
                target_agent_id=target_agent,
                human_origin=(
                    trust_context.human_origin.to_dict()
                    if trust_context and trust_context.human_origin
                    else None
                ),
                delegated_capabilities=[f"mcp_execute:{tool_name}"],
                constraints=dict(result.effective_constraints),
            )

        # No trust ops - return basic context
        return MCPEATPContext(
            mcp_session_id=mcp_session_id,
            eatp_trace_id=str(uuid4()),
            agent_id=calling_agent,
            target_agent_id=target_agent,
        )

    async def verify_mcp_response(
        self,
        context: MCPEATPContext,
        response: Dict[str, Any],
    ) -> bool:
        """
        Verify MCP response is within delegated scope.

        Checks that the target agent's response doesn't
        exceed the delegated capabilities.

        Args:
            context: MCP + EATP context from prepare_mcp_call
            response: Tool response from target agent

        Returns:
            True if response is valid, False otherwise
        """
        # Audit the response
        if self._trust_ops:
            await self._trust_ops.audit(
                agent_id=context.target_agent_id,
                action=f"mcp_response:{context.mcp_session_id}",
                context_data={
                    "response_keys": list(response.keys()),
                    "calling_agent": context.agent_id,
                },
            )

        # TODO: Add response validation logic
        return True
```

### 2.4 Session Trust Context Propagation

**File**: `apps/kailash-nexus/src/nexus/trust/session.py` (NEW)

```python
"""
Session trust context propagation for Nexus.

Maintains trust context across session boundaries,
enabling stateful trust verification.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from contextvars import ContextVar
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionTrustContext:
    """
    Trust context for a Nexus session.

    Persists across multiple requests in the same session,
    maintaining the trust chain established at session start.

    Attributes:
        session_id: Unique session identifier
        human_origin: Human who initiated session
        agent_id: Primary agent for session
        delegation_chain: Full delegation chain
        constraints: Accumulated constraints
        created_at: Session creation time
        expires_at: Session expiry
        workflow_count: Number of workflows executed
        last_activity: Last activity timestamp
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

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(timezone.utc)

    def increment_workflow(self) -> None:
        """Increment workflow count."""
        self.workflow_count += 1
        self.touch()


# Context variable for session trust
_session_trust: ContextVar[Optional[SessionTrustContext]] = ContextVar(
    "nexus_session_trust", default=None
)


class TrustContextPropagator:
    """
    Propagates trust context through Nexus sessions.

    Handles:
    - Session creation with trust establishment
    - Trust context retrieval during requests
    - Session revocation
    - Cross-channel trust propagation (API, CLI, MCP)

    Example:
        >>> propagator = TrustContextPropagator(trust_operations=trust_ops)
        >>>
        >>> # Create session with trust
        >>> session = await propagator.create_session(
        ...     human_origin={"human_id": "alice@corp.com", ...},
        ...     agent_id="alice-assistant",
        ... )
        >>>
        >>> # Get trust context for request
        >>> ctx = propagator.get_session_context(session.session_id)
        >>>
        >>> # Revoke session
        >>> await propagator.revoke_session(session.session_id)
    """

    def __init__(
        self,
        trust_operations=None,
        session_store=None,
        default_ttl_hours: int = 8,
    ):
        self._trust_ops = trust_operations
        self._store = session_store or {}  # Simple dict store for demo
        self._default_ttl = timedelta(hours=default_ttl_hours)

    async def create_session(
        self,
        human_origin: Dict[str, Any],
        agent_id: str,
        constraints: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = None,
    ) -> SessionTrustContext:
        """
        Create a new trusted session.

        Args:
            human_origin: Human origin information
            agent_id: Primary agent for session
            constraints: Initial constraints
            ttl_hours: Session TTL in hours

        Returns:
            SessionTrustContext for the new session
        """
        from uuid import uuid4

        ttl = timedelta(hours=ttl_hours) if ttl_hours else self._default_ttl
        now = datetime.now(timezone.utc)

        session = SessionTrustContext(
            session_id=f"nxs-{uuid4().hex[:12]}",
            human_origin=human_origin,
            agent_id=agent_id,
            delegation_chain=[f"pseudo:{human_origin['human_id']}", agent_id],
            constraints=constraints or {},
            created_at=now,
            expires_at=now + ttl,
        )

        # Establish trust chain in Kaizen
        if self._trust_ops:
            from kaizen.trust.execution_context import HumanOrigin, ExecutionContext

            origin = HumanOrigin.from_dict(human_origin)
            ctx = ExecutionContext(
                human_origin=origin,
                delegation_chain=session.delegation_chain,
            )

            # Store context for later use
            session.constraints["_eatp_context"] = ctx.to_dict()

        self._store[session.session_id] = session
        return session

    def get_session_context(
        self,
        session_id: str,
    ) -> Optional[SessionTrustContext]:
        """
        Get trust context for a session.

        Args:
            session_id: Session to retrieve

        Returns:
            SessionTrustContext or None if not found/expired
        """
        session = self._store.get(session_id)

        if session is None:
            return None

        if session.is_expired():
            del self._store[session_id]
            return None

        session.touch()
        return session

    async def revoke_session(
        self,
        session_id: str,
        reason: str = "Session revoked",
    ) -> bool:
        """
        Revoke a session and associated trust.

        Args:
            session_id: Session to revoke
            reason: Reason for revocation

        Returns:
            True if session was revoked, False if not found
        """
        session = self._store.get(session_id)
        if session is None:
            return False

        # Revoke trust chain in Kaizen
        if self._trust_ops and session.agent_id:
            try:
                await self._trust_ops.revoke_cascade(
                    session.agent_id, reason
                )
            except Exception as e:
                logger.error(f"Failed to revoke trust chain: {e}")

        del self._store[session_id]
        logger.info(f"Revoked session {session_id}: {reason}")
        return True

    async def revoke_by_human(
        self,
        human_id: str,
        reason: str = "Human access revoked",
    ) -> List[str]:
        """
        Revoke all sessions for a human.

        Args:
            human_id: Human whose sessions to revoke
            reason: Reason for revocation

        Returns:
            List of revoked session IDs
        """
        revoked = []

        for session_id, session in list(self._store.items()):
            if (
                session.human_origin
                and session.human_origin.get("human_id") == human_id
            ):
                await self.revoke_session(session_id, reason)
                revoked.append(session_id)

        return revoked


def get_current_session_trust() -> Optional[SessionTrustContext]:
    """Get current session trust context from context variable."""
    return _session_trust.get()


def set_current_session_trust(ctx: SessionTrustContext) -> None:
    """Set current session trust context."""
    _session_trust.set(ctx)
```

---

## Shared TrustContext Type

Both DataFlow and Nexus use `RuntimeTrustContext` from the Core SDK (defined in `02-core-sdk-trust-integration.md`), ensuring consistent trust context across all frameworks.

**Import pattern**:

```python
from kailash.runtime.trust import RuntimeTrustContext
```

---

## Testing Requirements

### DataFlow Tests

```python
# tests/integration/dataflow/test_trust_aware_queries.py

@pytest.mark.asyncio
async def test_constraint_envelope_filtering():
    """Constraints should filter query results."""
    # Setup
    executor = TrustAwareQueryExecutor(...)

    # Create agent with data_scope constraint
    await trust_ops.establish(
        agent_id="analyst",
        constraints=["data_scope:department:finance"],
    )

    # Query should only return finance department data
    results = await executor.execute_read(
        model="Transaction",
        filter={"year": 2025},
        agent_id="analyst",
    )

    for result in results:
        assert result["department"] == "finance"


@pytest.mark.asyncio
async def test_cross_tenant_blocked_without_delegation():
    """Cross-tenant access requires explicit delegation."""
    manager = TenantTrustManager(strict_mode=True)

    # Agent from tenant-b tries to access tenant-a data
    allowed = await manager.verify_cross_tenant_access(
        source_tenant="tenant-a",
        target_tenant="tenant-b",
        agent_id="agent-b",
        model="Invoice",
        operation="SELECT",
    )

    assert not allowed
```

### Nexus Tests

```python
# tests/integration/nexus/test_eatp_headers.py

def test_eatp_header_extraction():
    """Headers should be correctly extracted."""
    extractor = EATPHeaderExtractor()

    headers = {
        "X-EATP-Trace-ID": "trace-123",
        "X-EATP-Agent-ID": "agent-456",
        "X-EATP-Delegation-Chain": "pseudo:alice,agent-456",
    }

    ctx = extractor.extract(headers)

    assert ctx.trace_id == "trace-123"
    assert ctx.agent_id == "agent-456"
    assert ctx.delegation_chain == ["pseudo:alice", "agent-456"]


@pytest.mark.asyncio
async def test_trust_middleware_blocks_untrusted():
    """Middleware should block requests without valid trust."""
    from fastapi.testclient import TestClient

    # Create app with enforcing middleware
    app = create_test_app(trust_mode="enforcing")

    client = TestClient(app)

    # Request without EATP headers
    response = client.get("/api/data")

    assert response.status_code == 403
    assert "Trust verification failed" in response.json()["error"]
```

---

## Migration Path

### DataFlow Migration

1. **Phase 1**: Add trust types without enforcement
   - Install `dataflow.trust` module
   - Existing queries unchanged

2. **Phase 2**: Enable audit logging
   - All queries logged to audit store
   - No access restrictions

3. **Phase 3**: Enable constraint enforcement
   - Queries filtered by constraints
   - Unauthorized access blocked

### Nexus Migration

1. **Phase 1**: Add header extraction
   - Extract EATP headers when present
   - Store in request state

2. **Phase 2**: Enable permissive verification
   - Log verification results
   - Don't block requests

3. **Phase 3**: Enable enforcing mode
   - Block untrusted requests
   - Full EATP compliance

---

## References

- Core SDK Trust: `02-core-sdk-trust-integration.md`
- Kaizen Trust: `01-kaizen-trust-enhancements.md`
- DataFlow: `apps/kailash-dataflow/`
- Nexus: `apps/kailash-nexus/`
