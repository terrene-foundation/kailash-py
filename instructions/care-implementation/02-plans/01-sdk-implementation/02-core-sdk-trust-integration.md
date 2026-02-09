# Core SDK Trust Integration Plan

## Overview

This document details the integration of EATP trust verification into the Kailash Core SDK, specifically the runtime system. The goal is to propagate trust context through workflow execution while maintaining backward compatibility with existing workflows.

**Target Modules**:

- `src/kailash/runtime/base.py`
- `src/kailash/runtime/local.py`
- `src/kailash/runtime/async_local.py`
- New: `src/kailash/runtime/trust/`

---

## Architecture Overview

### Design Principles

1. **Opt-in Trust**: Trust verification is optional; existing workflows work unchanged
2. **Context Propagation**: Trust context flows through async/sync execution
3. **Backward Compatibility**: No breaking changes to runtime.execute() signature
4. **Framework Agnostic**: Trust layer works with Kaizen, DataFlow, and Nexus

### Integration Points

```
+-------------------+     +-------------------+     +-------------------+
|   Nexus API      |---->|   Core Runtime    |---->|   Kaizen Agent    |
|   (Headers)      |     |   (TrustContext)  |     |   (Verification)  |
+-------------------+     +-------------------+     +-------------------+
         |                        |                         |
         v                        v                         v
+-------------------+     +-------------------+     +-------------------+
| EATP Header      |     | TrustVerifier     |     | TrustOperations  |
| Extraction       |     | Integration       |     | (existing)       |
+-------------------+     +-------------------+     +-------------------+
```

---

## Component 1: TrustContext Type Definition

### File: `src/kailash/runtime/trust/__init__.py` (NEW)

```python
"""
Trust integration for Kailash Core Runtime.

Provides TrustContext propagation through workflow execution,
enabling EATP trust verification for all SDK frameworks.
"""

from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
    get_runtime_trust_context,
    set_runtime_trust_context,
    runtime_trust_context,
)
from kailash.runtime.trust.verifier import (
    TrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)
from kailash.runtime.trust.audit import (
    RuntimeAuditGenerator,
    AuditEvent,
    AuditEventType,
)

__all__ = [
    # Context
    "RuntimeTrustContext",
    "TrustVerificationMode",
    "get_runtime_trust_context",
    "set_runtime_trust_context",
    "runtime_trust_context",
    # Verifier
    "TrustVerifier",
    "TrustVerifierConfig",
    "VerificationResult",
    # Audit
    "RuntimeAuditGenerator",
    "AuditEvent",
    "AuditEventType",
]
```

### File: `src/kailash/runtime/trust/context.py` (NEW)

```python
"""
Runtime Trust Context for workflow execution.

Provides a framework-agnostic trust context that can be propagated
through both sync and async workflow execution.
"""

from __future__ import annotations
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from kaizen.trust.execution_context import HumanOrigin


class TrustVerificationMode(str, Enum):
    """
    Mode for trust verification during workflow execution.

    Modes:
        DISABLED: No trust verification (default for backward compat)
        PERMISSIVE: Verify but don't block on failure (logging only)
        ENFORCING: Verify and block untrusted operations
    """
    DISABLED = "disabled"
    PERMISSIVE = "permissive"
    ENFORCING = "enforcing"


@dataclass
class RuntimeTrustContext:
    """
    Trust context for runtime workflow execution.

    This is the Core SDK's trust context, designed to be framework-agnostic
    while bridging to Kaizen's ExecutionContext when available.

    Attributes:
        trace_id: Unique ID for correlating all operations
        human_origin: The human who authorized this chain (from Kaizen)
        delegation_chain: Agent IDs from human to current
        delegation_depth: Distance from human origin
        constraints: Accumulated constraints (tightened through delegation)
        verification_mode: How to handle trust verification
        workflow_id: ID of current workflow
        node_path: Path of executed nodes (for audit)
        metadata: Additional context data
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    human_origin: Optional["HumanOrigin"] = None
    delegation_chain: List[str] = field(default_factory=list)
    delegation_depth: int = 0
    constraints: Dict[str, Any] = field(default_factory=dict)
    verification_mode: TrustVerificationMode = TrustVerificationMode.DISABLED
    workflow_id: Optional[str] = None
    node_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def with_node(self, node_id: str) -> "RuntimeTrustContext":
        """
        Create new context with node added to execution path.

        Args:
            node_id: ID of node being executed

        Returns:
            New RuntimeTrustContext with node in path
        """
        return RuntimeTrustContext(
            trace_id=self.trace_id,
            human_origin=self.human_origin,
            delegation_chain=self.delegation_chain,
            delegation_depth=self.delegation_depth,
            constraints=self.constraints,
            verification_mode=self.verification_mode,
            workflow_id=self.workflow_id,
            node_path=self.node_path + [node_id],
            metadata=self.metadata,
            created_at=self.created_at,
        )

    def with_constraints(
        self,
        additional_constraints: Dict[str, Any]
    ) -> "RuntimeTrustContext":
        """
        Create new context with additional constraints (tightening only).

        Args:
            additional_constraints: Constraints to add

        Returns:
            New RuntimeTrustContext with merged constraints
        """
        merged = {**self.constraints, **additional_constraints}
        return RuntimeTrustContext(
            trace_id=self.trace_id,
            human_origin=self.human_origin,
            delegation_chain=self.delegation_chain,
            delegation_depth=self.delegation_depth,
            constraints=merged,
            verification_mode=self.verification_mode,
            workflow_id=self.workflow_id,
            node_path=self.node_path,
            metadata=self.metadata,
            created_at=self.created_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for transport (e.g., HTTP headers, message queues)."""
        return {
            "trace_id": self.trace_id,
            "human_origin": self.human_origin.to_dict() if self.human_origin else None,
            "delegation_chain": self.delegation_chain,
            "delegation_depth": self.delegation_depth,
            "constraints": self.constraints,
            "verification_mode": self.verification_mode.value,
            "workflow_id": self.workflow_id,
            "node_path": self.node_path,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeTrustContext":
        """Deserialize from transport format."""
        from kaizen.trust.execution_context import HumanOrigin

        human_origin = None
        if data.get("human_origin"):
            human_origin = HumanOrigin.from_dict(data["human_origin"])

        return cls(
            trace_id=data.get("trace_id", str(uuid.uuid4())),
            human_origin=human_origin,
            delegation_chain=data.get("delegation_chain", []),
            delegation_depth=data.get("delegation_depth", 0),
            constraints=data.get("constraints", {}),
            verification_mode=TrustVerificationMode(
                data.get("verification_mode", "disabled")
            ),
            workflow_id=data.get("workflow_id"),
            node_path=data.get("node_path", []),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(timezone.utc)
            ),
        )

    @classmethod
    def from_kaizen_context(cls, ctx) -> "RuntimeTrustContext":
        """
        Create RuntimeTrustContext from Kaizen ExecutionContext.

        Enables seamless bridging between Kaizen agents and Core SDK.

        Args:
            ctx: kaizen.trust.execution_context.ExecutionContext

        Returns:
            RuntimeTrustContext with Kaizen context data
        """
        return cls(
            trace_id=ctx.trace_id,
            human_origin=ctx.human_origin,
            delegation_chain=ctx.delegation_chain,
            delegation_depth=ctx.delegation_depth,
            constraints=ctx.constraints,
            verification_mode=TrustVerificationMode.ENFORCING,
        )


# Context variable for async-safe propagation
_runtime_trust_context: ContextVar[Optional[RuntimeTrustContext]] = ContextVar(
    "runtime_trust_context", default=None
)


def get_runtime_trust_context() -> Optional[RuntimeTrustContext]:
    """
    Get the current runtime trust context.

    Returns:
        Current RuntimeTrustContext or None if not set
    """
    return _runtime_trust_context.get()


def set_runtime_trust_context(ctx: RuntimeTrustContext) -> None:
    """
    Set the current runtime trust context.

    Args:
        ctx: RuntimeTrustContext to set
    """
    _runtime_trust_context.set(ctx)


@contextmanager
def runtime_trust_context(ctx: RuntimeTrustContext):
    """
    Context manager for setting runtime trust context.

    Ensures proper cleanup after block exits.

    Args:
        ctx: RuntimeTrustContext to set for this block

    Example:
        >>> ctx = RuntimeTrustContext(verification_mode=TrustVerificationMode.ENFORCING)
        >>> with runtime_trust_context(ctx):
        ...     results, run_id = runtime.execute(workflow)
    """
    token = _runtime_trust_context.set(ctx)
    try:
        yield ctx
    finally:
        _runtime_trust_context.reset(token)
```

---

## Component 2: TrustVerifier Integration Layer

### File: `src/kailash/runtime/trust/verifier.py` (NEW)

```python
"""
Trust Verifier integration for Core SDK runtime.

Provides trust verification for workflow and node execution,
bridging to Kaizen's TrustOperations when available.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from kaizen.trust.operations import TrustOperations
    from kaizen.trust.chain import VerificationLevel

logger = logging.getLogger(__name__)


class VerificationResult:
    """
    Result of trust verification.

    Provides a framework-agnostic verification result that can be used
    across Core SDK, DataFlow, and Nexus.
    """

    def __init__(
        self,
        allowed: bool,
        reason: Optional[str] = None,
        constraints: Optional[Dict[str, Any]] = None,
        capability_used: Optional[str] = None,
        trace_id: Optional[str] = None,
    ):
        self.allowed = allowed
        self.reason = reason
        self.constraints = constraints or {}
        self.capability_used = capability_used
        self.trace_id = trace_id

    def __bool__(self) -> bool:
        return self.allowed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "constraints": self.constraints,
            "capability_used": self.capability_used,
            "trace_id": self.trace_id,
        }


class TrustVerifierProtocol(Protocol):
    """
    Protocol for trust verification backends.

    Allows pluggable verification implementations:
    - KaizenTrustVerifier: Full EATP verification via Kaizen
    - MockTrustVerifier: For testing
    - ExternalTrustVerifier: External trust service
    """

    async def verify_workflow_access(
        self,
        workflow_id: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify agent can execute workflow."""
        ...

    async def verify_node_access(
        self,
        node_id: str,
        node_type: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify agent can execute specific node."""
        ...

    async def verify_resource_access(
        self,
        resource: str,
        action: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify agent can access resource."""
        ...


@dataclass
class TrustVerifierConfig:
    """
    Configuration for TrustVerifier.

    Attributes:
        mode: Verification mode (disabled, permissive, enforcing)
        cache_enabled: Enable verification result caching
        cache_ttl_seconds: Cache TTL in seconds
        fallback_allow: Default behavior when verifier unavailable
        audit_denials: Log denied operations
        high_risk_nodes: Node types requiring stricter verification
    """
    mode: str = "disabled"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 60
    fallback_allow: bool = True
    audit_denials: bool = True
    high_risk_nodes: List[str] = field(default_factory=lambda: [
        "BashCommand",
        "HttpRequest",
        "DatabaseQuery",
        "FileWrite",
        "CodeExecution",
    ])


class TrustVerifier:
    """
    Trust verification integration for Core SDK.

    Bridges Core SDK runtime to Kaizen's TrustOperations for
    EATP-compliant trust verification.

    Example:
        >>> from kaizen.trust.operations import TrustOperations
        >>>
        >>> # Initialize with Kaizen backend
        >>> kaizen_ops = TrustOperations(...)
        >>> verifier = TrustVerifier(
        ...     kaizen_backend=kaizen_ops,
        ...     config=TrustVerifierConfig(mode="enforcing")
        ... )
        >>>
        >>> # Verify workflow access
        >>> result = await verifier.verify_workflow_access(
        ...     workflow_id="wf-123",
        ...     agent_id="agent-456",
        ... )
        >>> if result.allowed:
        ...     # Execute workflow
        ...     pass
    """

    def __init__(
        self,
        kaizen_backend: Optional["TrustOperations"] = None,
        config: Optional[TrustVerifierConfig] = None,
    ):
        self._backend = kaizen_backend
        self._config = config or TrustVerifierConfig()
        self._cache: Dict[str, VerificationResult] = {}

    @property
    def is_enabled(self) -> bool:
        """Check if verification is enabled."""
        return self._config.mode != "disabled" and self._backend is not None

    @property
    def is_enforcing(self) -> bool:
        """Check if verification is enforcing (blocking denials)."""
        return self._config.mode == "enforcing"

    async def verify_workflow_access(
        self,
        workflow_id: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verify agent can execute workflow.

        Args:
            workflow_id: ID of workflow to execute
            agent_id: ID of agent requesting access
            context: Additional context for verification

        Returns:
            VerificationResult indicating if access is allowed
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # Check cache
        cache_key = f"wf:{workflow_id}:{agent_id}"
        if self._config.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # Use Kaizen backend for verification
            from kaizen.trust.chain import VerificationLevel

            kaizen_result = await self._backend.verify(
                agent_id=agent_id,
                action=f"execute_workflow:{workflow_id}",
                level=VerificationLevel.STANDARD,
                context=context,
            )

            result = VerificationResult(
                allowed=kaizen_result.valid,
                reason=kaizen_result.reason,
                constraints=kaizen_result.effective_constraints,
                capability_used=kaizen_result.capability_used,
            )

            # Cache result
            if self._config.cache_enabled:
                self._cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Trust verification failed: {e}")

            if self._config.fallback_allow:
                return VerificationResult(
                    allowed=True,
                    reason=f"Verification unavailable, fallback allow: {e}"
                )
            else:
                return VerificationResult(
                    allowed=False,
                    reason=f"Verification unavailable: {e}"
                )

    async def verify_node_access(
        self,
        node_id: str,
        node_type: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verify agent can execute specific node.

        High-risk nodes (file operations, network, code execution)
        receive stricter verification.

        Args:
            node_id: ID of node to execute
            node_type: Type of node
            agent_id: ID of agent requesting access
            context: Additional context

        Returns:
            VerificationResult indicating if access is allowed
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        # Determine verification level based on node type
        from kaizen.trust.chain import VerificationLevel

        if node_type in self._config.high_risk_nodes:
            level = VerificationLevel.FULL
        else:
            level = VerificationLevel.QUICK

        try:
            kaizen_result = await self._backend.verify(
                agent_id=agent_id,
                action=f"execute_node:{node_type}",
                resource=node_id,
                level=level,
                context=context,
            )

            result = VerificationResult(
                allowed=kaizen_result.valid,
                reason=kaizen_result.reason,
                constraints=kaizen_result.effective_constraints,
                capability_used=kaizen_result.capability_used,
            )

            if not result.allowed and self._config.audit_denials:
                logger.warning(
                    f"Node access denied: agent={agent_id}, "
                    f"node={node_id} ({node_type}), reason={result.reason}"
                )

            return result

        except Exception as e:
            logger.error(f"Node verification failed: {e}")
            return VerificationResult(
                allowed=self._config.fallback_allow,
                reason=str(e)
            )

    async def verify_resource_access(
        self,
        resource: str,
        action: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verify agent can access resource.

        Args:
            resource: Resource being accessed
            action: Action on resource
            agent_id: ID of agent requesting access
            context: Additional context

        Returns:
            VerificationResult indicating if access is allowed
        """
        if not self.is_enabled:
            return VerificationResult(allowed=True, reason="Verification disabled")

        try:
            kaizen_result = await self._backend.verify(
                agent_id=agent_id,
                action=action,
                resource=resource,
                context=context,
            )

            return VerificationResult(
                allowed=kaizen_result.valid,
                reason=kaizen_result.reason,
                constraints=kaizen_result.effective_constraints,
            )

        except Exception as e:
            logger.error(f"Resource verification failed: {e}")
            return VerificationResult(
                allowed=self._config.fallback_allow,
                reason=str(e)
            )

    def clear_cache(self) -> None:
        """Clear verification cache."""
        self._cache.clear()


class MockTrustVerifier(TrustVerifier):
    """Mock verifier for testing."""

    def __init__(
        self,
        default_allow: bool = True,
        denied_agents: Optional[List[str]] = None,
        denied_nodes: Optional[List[str]] = None,
    ):
        super().__init__(config=TrustVerifierConfig(mode="enforcing"))
        self._default_allow = default_allow
        self._denied_agents = set(denied_agents or [])
        self._denied_nodes = set(denied_nodes or [])

    async def verify_workflow_access(
        self,
        workflow_id: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        if agent_id in self._denied_agents:
            return VerificationResult(allowed=False, reason="Agent denied")
        return VerificationResult(allowed=self._default_allow)

    async def verify_node_access(
        self,
        node_id: str,
        node_type: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        if agent_id in self._denied_agents:
            return VerificationResult(allowed=False, reason="Agent denied")
        if node_id in self._denied_nodes:
            return VerificationResult(allowed=False, reason="Node denied")
        return VerificationResult(allowed=self._default_allow)
```

---

## Component 3: BaseRuntime Trust Integration

### File: `src/kailash/runtime/base.py` (MODIFY)

**Add to imports (around line 75):**

```python
# Trust integration imports
from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
    get_runtime_trust_context,
)
from kailash.runtime.trust.verifier import TrustVerifier, TrustVerifierConfig
```

**Add to BaseRuntime.**init** (around line 176):**

```python
def __init__(
    self,
    # ... existing parameters ...
    # NEW: Trust integration parameters
    trust_context: Optional[RuntimeTrustContext] = None,
    trust_verifier: Optional[TrustVerifier] = None,
    trust_verification_mode: str = "disabled",
    **kwargs,
):
    """
    Initialize base runtime.

    Args:
        # ... existing args ...

        trust_context: Optional pre-configured trust context
        trust_verifier: Optional trust verification backend
        trust_verification_mode: Verification mode (disabled, permissive, enforcing)
    """
    # ... existing initialization ...

    # Trust integration
    self._trust_context = trust_context
    self._trust_verifier = trust_verifier
    self._trust_verification_mode = TrustVerificationMode(trust_verification_mode)

    # If verifier not provided but mode is enabled, log warning
    if self._trust_verification_mode != TrustVerificationMode.DISABLED:
        if self._trust_verifier is None:
            logger.warning(
                f"Trust verification mode is {trust_verification_mode} but "
                "no trust_verifier provided. Verification will be skipped."
            )
```

**Add trust helper methods to BaseRuntime:**

```python
# Add after line 580

def _get_effective_trust_context(self) -> Optional[RuntimeTrustContext]:
    """
    Get the effective trust context for execution.

    Priority:
    1. Context from runtime_trust_context context manager
    2. Context passed to runtime constructor
    3. None (no trust context)

    Returns:
        RuntimeTrustContext or None
    """
    # Check context variable first (set by context manager)
    ctx = get_runtime_trust_context()
    if ctx is not None:
        return ctx

    # Fall back to constructor-provided context
    return self._trust_context


async def _verify_workflow_trust(
    self,
    workflow: Workflow,
    agent_id: Optional[str] = None,
) -> bool:
    """
    Verify trust for workflow execution.

    Args:
        workflow: Workflow to verify
        agent_id: Agent executing workflow (defaults to context)

    Returns:
        True if allowed, False if denied

    Note:
        In DISABLED mode, always returns True.
        In PERMISSIVE mode, logs but returns True.
        In ENFORCING mode, returns actual verification result.
    """
    if self._trust_verification_mode == TrustVerificationMode.DISABLED:
        return True

    if self._trust_verifier is None:
        return True

    # Get agent ID from context if not provided
    if agent_id is None:
        ctx = self._get_effective_trust_context()
        if ctx and ctx.delegation_chain:
            agent_id = ctx.delegation_chain[-1]
        else:
            agent_id = "unknown"

    workflow_id = getattr(workflow, "workflow_id", None) or "unknown"

    result = await self._trust_verifier.verify_workflow_access(
        workflow_id=workflow_id,
        agent_id=agent_id,
        context={"workflow_nodes": len(workflow.graph.nodes)},
    )

    if not result.allowed:
        if self._trust_verification_mode == TrustVerificationMode.PERMISSIVE:
            logger.warning(
                f"Trust verification failed (permissive mode): {result.reason}"
            )
            return True
        else:
            logger.error(f"Trust verification failed: {result.reason}")
            return False

    return True


async def _verify_node_trust(
    self,
    node_id: str,
    node_type: str,
    agent_id: Optional[str] = None,
) -> bool:
    """
    Verify trust for node execution.

    Args:
        node_id: Node to verify
        node_type: Type of node
        agent_id: Agent executing node

    Returns:
        True if allowed, False if denied
    """
    if self._trust_verification_mode == TrustVerificationMode.DISABLED:
        return True

    if self._trust_verifier is None:
        return True

    if agent_id is None:
        ctx = self._get_effective_trust_context()
        if ctx and ctx.delegation_chain:
            agent_id = ctx.delegation_chain[-1]
        else:
            agent_id = "unknown"

    result = await self._trust_verifier.verify_node_access(
        node_id=node_id,
        node_type=node_type,
        agent_id=agent_id,
    )

    if not result.allowed:
        if self._trust_verification_mode == TrustVerificationMode.PERMISSIVE:
            logger.warning(
                f"Node trust verification failed (permissive): {result.reason}"
            )
            return True
        else:
            return False

    return True
```

---

## Component 4: LocalRuntime Trust Integration

### File: `src/kailash/runtime/local.py` (MODIFY)

**Update execute() method to include trust verification:**

```python
# Modify execute() method (around line 340)

def execute(
    self,
    workflow: Workflow,
    parameters: Optional[Dict[str, Any]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    trust_context: Optional[RuntimeTrustContext] = None,
    **kwargs,
) -> Tuple[Dict[str, Any], str]:
    """
    Execute workflow synchronously.

    Args:
        workflow: Workflow to execute
        parameters: Template parameters (deprecated, use inputs)
        inputs: Input values for workflow
        trust_context: Optional trust context for this execution
        **kwargs: Additional arguments

    Returns:
        Tuple of (results, run_id)

    Raises:
        WorkflowExecutionError: If execution fails
        TrustVerificationError: If trust verification fails in enforcing mode
    """
    # Generate run ID
    run_id = self._generate_run_id()

    # Initialize metadata
    metadata = self._initialize_execution_metadata(workflow, run_id)
    self._execution_metadata[run_id] = metadata

    # Set up trust context for this execution
    effective_trust_ctx = trust_context or self._get_effective_trust_context()

    if effective_trust_ctx:
        effective_trust_ctx = RuntimeTrustContext(
            **{**effective_trust_ctx.to_dict(), "workflow_id": run_id}
        )

    # Verify trust (async call from sync context)
    if self._trust_verification_mode != TrustVerificationMode.DISABLED:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If async loop running, use run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    allowed = pool.submit(
                        asyncio.run,
                        self._verify_workflow_trust(workflow)
                    ).result()
            else:
                allowed = asyncio.run(self._verify_workflow_trust(workflow))

            if not allowed:
                from kailash.sdk_exceptions import WorkflowExecutionError
                raise WorkflowExecutionError(
                    "Trust verification failed",
                    details={"run_id": run_id}
                )
        except RuntimeError:
            # No event loop
            allowed = asyncio.run(self._verify_workflow_trust(workflow))
            if not allowed:
                from kailash.sdk_exceptions import WorkflowExecutionError
                raise WorkflowExecutionError(
                    "Trust verification failed",
                    details={"run_id": run_id}
                )

    # ... rest of existing execute() implementation ...
```

---

## Component 5: EATP-Compliant Audit Trail Generation

### File: `src/kailash/runtime/trust/audit.py` (NEW)

```python
"""
Runtime audit trail generation for EATP compliance.

Generates EATP-compliant audit events from workflow execution,
integrating with Kaizen's AuditStore when available.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import logging
import json

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events from runtime execution."""
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    WORKFLOW_ERROR = "workflow_error"
    NODE_START = "node_start"
    NODE_END = "node_end"
    NODE_ERROR = "node_error"
    TRUST_VERIFICATION = "trust_verification"
    TRUST_DENIED = "trust_denied"
    RESOURCE_ACCESS = "resource_access"
    DELEGATION_USED = "delegation_used"


@dataclass
class AuditEvent:
    """
    An audit event from runtime execution.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event
        timestamp: When event occurred
        trace_id: Correlation ID for request chain
        workflow_id: Associated workflow
        node_id: Associated node (if applicable)
        agent_id: Agent that triggered event
        human_origin_id: Ultimate human authorizer
        action: Action being performed
        resource: Resource being accessed
        result: Outcome (success, failure, denied)
        context: Additional context data
    """
    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    trace_id: str
    workflow_id: Optional[str] = None
    node_id: Optional[str] = None
    agent_id: Optional[str] = None
    human_origin_id: Optional[str] = None
    action: Optional[str] = None
    resource: Optional[str] = None
    result: str = "success"
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
            "workflow_id": self.workflow_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "human_origin_id": self.human_origin_id,
            "action": self.action,
            "resource": self.resource,
            "result": self.result,
            "context": self.context,
        }


class RuntimeAuditGenerator:
    """
    Generates EATP-compliant audit events from runtime execution.

    Integrates with Kaizen AuditStore when available, otherwise
    logs to standard logging.

    Example:
        >>> from kaizen.trust.audit_store import PostgresAuditStore
        >>>
        >>> audit_store = PostgresAuditStore()
        >>> generator = RuntimeAuditGenerator(audit_store=audit_store)
        >>>
        >>> # Record workflow start
        >>> await generator.workflow_started(run_id, workflow, trust_ctx)
        >>>
        >>> # Record node execution
        >>> await generator.node_executed(run_id, node_id, result, trust_ctx)
    """

    def __init__(
        self,
        audit_store=None,
        enabled: bool = True,
        log_to_stdout: bool = False,
    ):
        """
        Initialize audit generator.

        Args:
            audit_store: Optional Kaizen AuditStore for persistence
            enabled: Enable audit generation
            log_to_stdout: Also log to stdout
        """
        self._audit_store = audit_store
        self._enabled = enabled
        self._log_to_stdout = log_to_stdout
        self._events: List[AuditEvent] = []

    async def workflow_started(
        self,
        run_id: str,
        workflow,
        trust_context: Optional["RuntimeTrustContext"] = None,
    ) -> AuditEvent:
        """Record workflow start event."""
        from uuid import uuid4

        event = AuditEvent(
            event_id=f"evt-{uuid4().hex[:12]}",
            event_type=AuditEventType.WORKFLOW_START,
            timestamp=datetime.now(timezone.utc),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            agent_id=(
                trust_context.delegation_chain[-1]
                if trust_context and trust_context.delegation_chain
                else None
            ),
            human_origin_id=(
                trust_context.human_origin.human_id
                if trust_context and trust_context.human_origin
                else None
            ),
            action="execute_workflow",
            context={
                "node_count": len(workflow.graph.nodes),
                "workflow_type": type(workflow).__name__,
            },
        )

        await self._record_event(event)
        return event

    async def workflow_completed(
        self,
        run_id: str,
        duration_ms: float,
        trust_context: Optional["RuntimeTrustContext"] = None,
    ) -> AuditEvent:
        """Record workflow completion event."""
        from uuid import uuid4

        event = AuditEvent(
            event_id=f"evt-{uuid4().hex[:12]}",
            event_type=AuditEventType.WORKFLOW_END,
            timestamp=datetime.now(timezone.utc),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            human_origin_id=(
                trust_context.human_origin.human_id
                if trust_context and trust_context.human_origin
                else None
            ),
            result="success",
            context={
                "duration_ms": duration_ms,
            },
        )

        await self._record_event(event)
        return event

    async def node_executed(
        self,
        run_id: str,
        node_id: str,
        node_type: str,
        result: Dict[str, Any],
        duration_ms: float,
        trust_context: Optional["RuntimeTrustContext"] = None,
    ) -> AuditEvent:
        """Record node execution event."""
        from uuid import uuid4

        event = AuditEvent(
            event_id=f"evt-{uuid4().hex[:12]}",
            event_type=AuditEventType.NODE_END,
            timestamp=datetime.now(timezone.utc),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            node_id=node_id,
            agent_id=(
                trust_context.delegation_chain[-1]
                if trust_context and trust_context.delegation_chain
                else None
            ),
            action=f"execute_node:{node_type}",
            result="success",
            context={
                "node_type": node_type,
                "duration_ms": duration_ms,
                "result_keys": list(result.keys()) if isinstance(result, dict) else [],
            },
        )

        await self._record_event(event)
        return event

    async def trust_verification_performed(
        self,
        run_id: str,
        target: str,
        allowed: bool,
        reason: Optional[str] = None,
        trust_context: Optional["RuntimeTrustContext"] = None,
    ) -> AuditEvent:
        """Record trust verification event."""
        from uuid import uuid4

        event = AuditEvent(
            event_id=f"evt-{uuid4().hex[:12]}",
            event_type=(
                AuditEventType.TRUST_VERIFICATION
                if allowed
                else AuditEventType.TRUST_DENIED
            ),
            timestamp=datetime.now(timezone.utc),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            agent_id=(
                trust_context.delegation_chain[-1]
                if trust_context and trust_context.delegation_chain
                else None
            ),
            human_origin_id=(
                trust_context.human_origin.human_id
                if trust_context and trust_context.human_origin
                else None
            ),
            action="trust_verification",
            resource=target,
            result="allowed" if allowed else "denied",
            context={
                "reason": reason,
                "delegation_depth": (
                    trust_context.delegation_depth if trust_context else 0
                ),
            },
        )

        await self._record_event(event)
        return event

    async def _record_event(self, event: AuditEvent) -> None:
        """Record an audit event."""
        if not self._enabled:
            return

        self._events.append(event)

        if self._log_to_stdout:
            logger.info(f"AUDIT: {json.dumps(event.to_dict())}")

        if self._audit_store:
            try:
                # Convert to Kaizen AuditAnchor if store available
                await self._persist_to_kaizen(event)
            except Exception as e:
                logger.error(f"Failed to persist audit event: {e}")

    async def _persist_to_kaizen(self, event: AuditEvent) -> None:
        """Persist event to Kaizen AuditStore."""
        from kaizen.trust.chain import AuditAnchor, ActionResult

        # Map result to ActionResult enum
        result_map = {
            "success": ActionResult.SUCCESS,
            "failure": ActionResult.FAILURE,
            "denied": ActionResult.DENIED,
        }
        action_result = result_map.get(event.result, ActionResult.SUCCESS)

        anchor = AuditAnchor(
            id=event.event_id,
            agent_id=event.agent_id or "runtime",
            action=event.action or "unknown",
            timestamp=event.timestamp,
            trust_chain_hash="",  # Computed by store
            result=action_result,
            signature="",  # Signed by store
            resource=event.resource,
            parent_anchor_id=None,
            context=event.context,
            human_origin=None,  # Would need to lookup
        )

        await self._audit_store.append(anchor)

    def get_events(self) -> List[AuditEvent]:
        """Get all recorded events."""
        return list(self._events)

    def clear_events(self) -> None:
        """Clear recorded events."""
        self._events.clear()
```

---

## API Design Summary

### Backward Compatible API

```python
# Existing code continues to work
from kailash.runtime import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

### Trust-Enabled API

```python
# New trust-enabled execution
from kailash.runtime import LocalRuntime
from kailash.runtime.trust import (
    RuntimeTrustContext,
    TrustVerifier,
    TrustVerifierConfig,
    runtime_trust_context,
)
from kaizen.trust.operations import TrustOperations

# Initialize Kaizen backend
kaizen_ops = TrustOperations(...)
await kaizen_ops.initialize()

# Create verifier with Kaizen backend
verifier = TrustVerifier(
    kaizen_backend=kaizen_ops,
    config=TrustVerifierConfig(mode="enforcing"),
)

# Create runtime with trust verification
runtime = LocalRuntime(
    trust_verifier=verifier,
    trust_verification_mode="enforcing",
)

# Execute with trust context
ctx = RuntimeTrustContext.from_kaizen_context(kaizen_ctx)
with runtime_trust_context(ctx):
    results, run_id = runtime.execute(workflow)
```

---

## Testing Requirements

### Unit Tests

```python
# tests/unit/runtime/trust/test_trust_context.py

def test_runtime_trust_context_serialization():
    """Context should serialize/deserialize correctly."""
    ctx = RuntimeTrustContext(
        trace_id="trace-123",
        delegation_depth=2,
        constraints={"cost_limit": 1000},
    )

    data = ctx.to_dict()
    restored = RuntimeTrustContext.from_dict(data)

    assert restored.trace_id == ctx.trace_id
    assert restored.delegation_depth == ctx.delegation_depth
    assert restored.constraints == ctx.constraints


def test_context_propagation():
    """Context should propagate through with_node()."""
    ctx = RuntimeTrustContext(node_path=["a", "b"])
    new_ctx = ctx.with_node("c")

    assert new_ctx.node_path == ["a", "b", "c"]
    assert ctx.node_path == ["a", "b"]  # Original unchanged


@pytest.mark.asyncio
async def test_trust_verifier_enabled():
    """Verifier should call backend when enabled."""
    mock_backend = MagicMock()
    mock_backend.verify = AsyncMock(return_value=MockVerificationResult(valid=True))

    verifier = TrustVerifier(
        kaizen_backend=mock_backend,
        config=TrustVerifierConfig(mode="enforcing"),
    )

    result = await verifier.verify_workflow_access("wf-1", "agent-1")

    assert result.allowed
    mock_backend.verify.assert_called_once()


@pytest.mark.asyncio
async def test_trust_verifier_disabled():
    """Disabled verifier should always allow."""
    verifier = TrustVerifier(
        config=TrustVerifierConfig(mode="disabled"),
    )

    result = await verifier.verify_workflow_access("wf-1", "agent-1")

    assert result.allowed
```

### Integration Tests

```python
# tests/integration/runtime/test_trust_integration.py

@pytest.mark.asyncio
async def test_runtime_with_trust_verification():
    """Runtime should verify trust before execution."""
    # Setup Kaizen backend
    trust_ops = await create_test_trust_ops()

    # Establish agent trust
    await trust_ops.establish(
        agent_id="test-agent",
        authority_id="test-authority",
        capabilities=[CapabilityRequest(capability="execute_workflow:*")],
    )

    # Create verified runtime
    verifier = TrustVerifier(
        kaizen_backend=trust_ops,
        config=TrustVerifierConfig(mode="enforcing"),
    )

    runtime = LocalRuntime(
        trust_verifier=verifier,
        trust_verification_mode="enforcing",
    )

    # Should succeed for authorized agent
    ctx = RuntimeTrustContext(
        delegation_chain=["test-agent"],
    )

    with runtime_trust_context(ctx):
        results, run_id = runtime.execute(workflow)

    assert results is not None
```

---

## Migration Path

### Phase 1: Add trust types (no behavior change)

- Add `RuntimeTrustContext`, `TrustVerifier`, `RuntimeAuditGenerator`
- Add parameters to `BaseRuntime.__init__` (all optional, default disabled)
- No existing code affected

### Phase 2: Enable permissive mode

- Enable `trust_verification_mode="permissive"` for new deployments
- Logs verification results but doesn't block
- Identifies trust configuration issues

### Phase 3: Enable enforcing mode

- Switch to `trust_verification_mode="enforcing"` for production
- Blocks untrusted operations
- Full EATP compliance

---

## References

- Kaizen Trust Module: `apps/kailash-kaizen/src/kaizen/trust/`
- Core Runtime: `src/kailash/runtime/`
- EATP Protocol: `docs/plans/eatp-integration/`
