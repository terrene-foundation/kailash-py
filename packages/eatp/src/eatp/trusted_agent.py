# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
TrustedAgent - Trust-enhanced agent wrapper.

Provides transparent trust integration for agents, enabling:
- Automatic trust verification before every action
- Automatic audit recording after every action
- Tool constraint enforcement based on trust chain
- Hierarchical delegation for multi-agent systems

Architecture:
- TrustedAgent wraps an agent using composition (not inheritance)
- Uses __getattr__ to delegate all agent methods transparently
- Intercepts execute/execute_async for trust sandwich pattern
- TrustedSupervisorAgent extends for delegation capabilities

Trust Sandwich Pattern:
    1. VERIFY: Check trust before action
    2. EXECUTE: Perform the action
    3. AUDIT: Record action in immutable audit trail

Example:
    from eatp.trusted_agent import TrustedAgent, TrustedAgentConfig
    from eatp.operations import TrustOperations

    # Wrap with trust
    trusted_agent = TrustedAgent(
        agent=base_agent,
        trust_ops=trust_operations,
        config=TrustedAgentConfig(agent_id="worker-001"),
    )

    # Execute with automatic trust verification and audit
    result = await trusted_agent.execute_async(inputs={"question": "What is AI?"})
    # Trust verified before execution, audit recorded after
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from eatp.audit_store import AuditStore
from eatp.chain import ActionResult, VerificationLevel, VerificationResult
from eatp.exceptions import (
    ConstraintViolationError,
    DelegationError,
    TrustChainNotFoundError,
    TrustError,
    VerificationFailedError,
)
from eatp.execution_context import ExecutionContext
from eatp.execution_context import execution_context as set_execution_context
from eatp.execution_context import get_current_context
from eatp.operations import TrustOperations


@dataclass
class TrustedAgentConfig:
    """
    Configuration for TrustedAgent.

    Controls trust verification and audit behavior.

    Attributes:
        agent_id: Unique identifier for this agent's trust chain
        verification_level: Level of trust verification (QUICK, STANDARD, FULL)
        audit_enabled: Whether to record actions in audit trail
        fail_on_verification_failure: If True, raise exception on verification failure
        auto_establish: If True, auto-establish trust when agent_id not found
        authority_id: Authority to use for auto-establishment
        default_capabilities: Capabilities for auto-establishment
        constraint_enforcement: If True, enforce tool constraints from trust chain
        parent_anchor_tracking: If True, track parent audit anchors for action chains
    """

    agent_id: str
    verification_level: VerificationLevel = VerificationLevel.STANDARD
    audit_enabled: bool = True
    fail_on_verification_failure: bool = True
    auto_establish: bool = False
    authority_id: Optional[str] = None
    default_capabilities: List[str] = field(default_factory=list)
    constraint_enforcement: bool = True
    parent_anchor_tracking: bool = True


@dataclass
class TrustContext:
    """
    Context information for a trusted execution.

    Captures the trust state at the time of execution for
    audit and debugging purposes.

    Attributes:
        agent_id: Agent performing the action
        action: Action being performed
        resource: Resource being accessed
        verification_result: Result of trust verification
        parent_anchor_id: Link to parent audit anchor (for action chains)
        start_time: When execution started
        effective_constraints: Constraints in effect for this action
        metadata: Additional context information
    """

    agent_id: str
    action: str
    resource: Optional[str] = None
    verification_result: Optional[VerificationResult] = None
    parent_anchor_id: Optional[str] = None
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    effective_constraints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TrustedAgent:
    """
    Trust-enhanced wrapper for agents.

    TrustedAgent wraps any agent instance with transparent trust
    integration. It intercepts execution to verify trust and record audits
    while preserving all agent functionality.

    Key Features:
    - **Transparent Wrapper**: All agent methods accessible via delegation
    - **Trust Verification**: Automatic verification before every action
    - **Audit Recording**: Automatic audit after every action
    - **Tool Constraint Enforcement**: Validates tool calls against trust chain
    - **Action Chaining**: Links related actions via parent_anchor_id

    Trust Sandwich Pattern:
        VERIFY -> EXECUTE -> AUDIT

    Example:
        >>> trusted_agent = TrustedAgent(
        ...     agent=base_agent,
        ...     trust_ops=trust_ops,
        ...     config=TrustedAgentConfig(agent_id="agent-001"),
        ... )
        >>>
        >>> # Execute with trust (async)
        >>> result = await trusted_agent.execute_async(inputs={"question": "What is AI?"})
    """

    def __init__(
        self,
        agent: Any,  # Agent instance
        trust_ops: TrustOperations,
        config: TrustedAgentConfig,
        audit_store: Optional[AuditStore] = None,
    ):
        """
        Initialize TrustedAgent wrapper.

        Args:
            agent: The agent instance to wrap
            trust_ops: TrustOperations instance for trust operations
            config: TrustedAgentConfig with trust settings
            audit_store: Optional AuditStore for recording audits
        """
        self._agent = agent
        self._trust_ops = trust_ops
        self._config = config
        self._audit_store = audit_store
        self._current_anchor_id: Optional[str] = None
        self._action_stack: List[str] = []

    def __getattr__(self, name: str) -> Any:
        """
        Delegate attribute access to wrapped agent.

        This enables transparent access to all agent methods
        and attributes while allowing TrustedAgent to intercept
        specific methods for trust integration.

        Args:
            name: Attribute name to access

        Returns:
            The attribute from the wrapped agent
        """
        return getattr(self._agent, name)

    @property
    def agent_id(self) -> str:
        """Get the trust agent ID."""
        return self._config.agent_id

    @property
    def wrapped_agent(self) -> Any:
        """Get the wrapped agent instance."""
        return self._agent

    @property
    def trust_operations(self) -> TrustOperations:
        """Get the TrustOperations instance."""
        return self._trust_ops

    @property
    def current_anchor_id(self) -> Optional[str]:
        """Get the current audit anchor ID for action chaining."""
        return self._current_anchor_id

    async def verify_trust(
        self,
        action: str,
        resource: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verify trust for an action.

        Args:
            action: Action to verify
            resource: Optional resource being accessed
            context: Additional context for constraint evaluation

        Returns:
            VerificationResult with verification outcome

        Raises:
            VerificationFailedError: If fail_on_verification_failure and verification fails
        """
        result = await self._trust_ops.verify(
            agent_id=self._config.agent_id,
            action=action,
            resource=resource,
            level=self._config.verification_level,
            context=context or {},
        )

        if not result.valid and self._config.fail_on_verification_failure:
            raise VerificationFailedError(
                action=action,
                agent_id=self._config.agent_id,
                reason=result.reason or "Trust verification failed",
                violations=result.violations,
            )

        return result

    async def record_audit(
        self,
        action: str,
        resource: Optional[str] = None,
        result: ActionResult = ActionResult.SUCCESS,
        audit_context: Optional[Dict[str, Any]] = None,
        parent_anchor_id: Optional[str] = None,
        eatp_context: Optional[ExecutionContext] = None,
    ) -> str:
        """
        Record an action in the audit trail.

        EATP Enhancement: Audit records now include human_origin from
        ExecutionContext for complete traceability.

        Args:
            action: Action that was performed
            resource: Resource that was accessed
            result: Outcome of the action
            audit_context: Additional context dictionary
            parent_anchor_id: Link to parent action
            eatp_context: ExecutionContext with human_origin for EATP traceability

        Returns:
            The audit anchor ID
        """
        if not self._config.audit_enabled:
            return ""

        # Use provided parent or current anchor for chaining
        effective_parent = parent_anchor_id
        if effective_parent is None and self._config.parent_anchor_tracking:
            effective_parent = self._current_anchor_id

        # EATP: Get context from parameter or context variable
        ctx = eatp_context or get_current_context()

        anchor = await self._trust_ops.audit(
            agent_id=self._config.agent_id,
            action=action,
            resource=resource,
            result=result,
            context_data=audit_context or {},
            parent_anchor_id=effective_parent,
            audit_store=self._audit_store,
            context=ctx,  # EATP: Pass ExecutionContext for human_origin
        )

        # Update current anchor for chaining
        self._current_anchor_id = anchor.id

        return anchor.id

    async def execute_async(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        action: str = "execute",
        resource: Optional[str] = None,
        context: Optional[ExecutionContext] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute agent with trust verification and audit.

        Implements the Trust Sandwich Pattern:
        1. VERIFY: Check trust before action
        2. EXECUTE: Perform the action via wrapped agent
        3. AUDIT: Record action in immutable audit trail

        EATP Enhancement: All executions require a valid ExecutionContext
        with human_origin to ensure traceability back to the authorizing human.

        Args:
            inputs: Input data for the agent
            action: Action name for trust verification (default: "execute")
            resource: Resource being accessed
            context: ExecutionContext with human_origin (required for EATP compliance)
            **kwargs: Additional arguments passed to agent.execute_async()

        Returns:
            Execution result from the wrapped agent

        Raises:
            VerificationFailedError: If trust verification fails
            TrustChainNotFoundError: If agent has no trust chain
            RuntimeError: If no ExecutionContext is available (EATP requirement)
        """
        inputs = inputs or {}

        # EATP: Get execution context - required for human traceability
        eatp_context = context or get_current_context()
        if eatp_context is None and self._config.fail_on_verification_failure:
            raise RuntimeError(
                f"No ExecutionContext available for agent {self._config.agent_id}. "
                "EATP requires all executions to have a human_origin. "
                "Use PseudoAgent.delegate_to() to initiate trust chains or "
                "pass context parameter explicitly."
            )

        exec_context_dict: Dict[str, Any] = {
            "inputs": inputs,
            "action": action,
            "resource": resource,
        }

        # Add EATP traceability info if context is available
        if eatp_context:
            exec_context_dict["human_origin"] = eatp_context.human_origin.human_id
            exec_context_dict["delegation_chain"] = eatp_context.delegation_chain
            exec_context_dict["trace_id"] = eatp_context.trace_id

        # 1. VERIFY: Check trust before action
        verification_result = None
        try:
            verification_result = await self.verify_trust(
                action=action,
                resource=resource,
                context=exec_context_dict,
            )
            exec_context_dict["verification"] = {
                "valid": verification_result.valid,
                "level": (
                    verification_result.level.value
                    if verification_result.level
                    else None
                ),
                "capability_used": verification_result.capability_used,
            }
        except TrustChainNotFoundError:
            if self._config.auto_establish:
                # Auto-establish trust if configured
                await self._auto_establish_trust()
                verification_result = await self.verify_trust(
                    action=action,
                    resource=resource,
                    context=exec_context_dict,
                )
            else:
                # EATP: Still record audit even on verification failure
                await self.record_audit(
                    action=action,
                    resource=resource,
                    result=ActionResult.DENIED,
                    audit_context={"error": "Trust chain not found"},
                    eatp_context=eatp_context,
                )
                raise
        except VerificationFailedError as e:
            # EATP: Record audit for verification failures
            await self.record_audit(
                action=action,
                resource=resource,
                result=ActionResult.DENIED,
                audit_context={
                    "error": str(e),
                    "violations": e.violations if hasattr(e, "violations") else [],
                },
                eatp_context=eatp_context,
            )
            raise

        # 2. EXECUTE: Perform the action (with context propagation)
        action_result = ActionResult.SUCCESS
        error_context = None
        result = {}

        try:
            # EATP: Propagate context to wrapped agent execution
            if eatp_context:
                with set_execution_context(eatp_context):
                    result = await self._agent.execute_async(inputs=inputs, **kwargs)
            else:
                result = await self._agent.execute_async(inputs=inputs, **kwargs)
        except Exception as e:
            action_result = ActionResult.FAILURE
            error_context = {"error": str(e), "error_type": type(e).__name__}
            raise
        finally:
            # 3. AUDIT: Record action in immutable audit trail
            audit_context = {
                **exec_context_dict,
                "result_keys": list(result.keys()) if result else [],
            }
            if error_context:
                audit_context["error"] = error_context

            await self.record_audit(
                action=action,
                resource=resource,
                result=action_result,
                audit_context=audit_context,
                eatp_context=eatp_context,
            )

        return result

    def execute(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        action: str = "execute",
        resource: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Synchronous execution with trust verification and audit.

        Note: This runs the async version in a new event loop.
        For async contexts, use execute_async() directly.

        Args:
            inputs: Input data for the agent
            action: Action name for trust verification
            resource: Resource being accessed
            **kwargs: Additional arguments passed to agent.execute()

        Returns:
            Execution result from the wrapped agent
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop — create a new thread to run async code
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.execute_async(
                        inputs=inputs, action=action, resource=resource, **kwargs
                    ),
                )
                return future.result()
        else:
            return asyncio.run(
                self.execute_async(
                    inputs=inputs, action=action, resource=resource, **kwargs
                )
            )

    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: Optional[float] = None,
        context: Optional[ExecutionContext] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool with trust verification.

        Verifies that the agent has permission to use the tool
        based on their trust chain constraints.

        EATP Enhancement: Tool executions now include human_origin traceability.

        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters
            timeout: Optional timeout
            context: ExecutionContext with human_origin for EATP traceability

        Returns:
            Tool execution result

        Raises:
            ConstraintViolationError: If tool violates constraints
            VerificationFailedError: If trust verification fails
        """
        # EATP: Get execution context
        eatp_context = context or get_current_context()

        # Verify trust for tool usage
        tool_action = f"use_tool:{tool_name}"
        await self.verify_trust(
            action=tool_action,
            context={"tool_name": tool_name, "params": params},
        )

        # Check tool against constraints if enforcement enabled
        if self._config.constraint_enforcement:
            await self._enforce_tool_constraints(tool_name, params)

        # Execute tool via wrapped agent
        action_result = ActionResult.SUCCESS
        result = {}

        try:
            # EATP: Propagate context to tool execution
            if eatp_context:
                with set_execution_context(eatp_context):
                    result = await self._agent.execute_tool(tool_name, params, timeout)
            else:
                result = await self._agent.execute_tool(tool_name, params, timeout)
        except Exception as e:
            action_result = ActionResult.FAILURE
            raise
        finally:
            # Record tool usage audit with EATP context
            await self.record_audit(
                action=tool_action,
                audit_context={"tool_name": tool_name, "params": params},
                result=action_result,
                eatp_context=eatp_context,
            )

        return result

    async def _enforce_tool_constraints(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> None:
        """
        Enforce trust chain constraints on tool usage.

        Args:
            tool_name: Tool being used
            params: Tool parameters

        Raises:
            ConstraintViolationError: If tool violates constraints
        """
        # Get agent's constraints
        try:
            constraints = await self._trust_ops.get_agent_constraints(
                self._config.agent_id
            )
        except TrustChainNotFoundError:
            return  # No constraints to enforce

        # Check for read_only constraint
        write_tools = ["file_write", "bash", "database_write", "delete"]
        if "read_only" in constraints:
            for write_tool in write_tools:
                if write_tool in tool_name.lower():
                    raise ConstraintViolationError(
                        message=f"Tool {tool_name} not permitted under read_only constraint",
                        violations=[
                            {
                                "constraint": "read_only",
                                "tool": tool_name,
                                "reason": f"Tool {tool_name} violates read_only constraint",
                            }
                        ],
                        agent_id=self._config.agent_id,
                        action=f"use_tool:{tool_name}",
                    )

        # Check for no_network constraint
        if "no_network" in constraints:
            network_tools = ["http", "fetch", "request", "api"]
            for network_tool in network_tools:
                if network_tool in tool_name.lower():
                    raise ConstraintViolationError(
                        message=f"Tool {tool_name} not permitted under no_network constraint",
                        violations=[
                            {
                                "constraint": "no_network",
                                "tool": tool_name,
                                "reason": f"Tool {tool_name} violates no_network constraint",
                            }
                        ],
                        agent_id=self._config.agent_id,
                        action=f"use_tool:{tool_name}",
                    )

    async def _auto_establish_trust(self) -> None:
        """
        Auto-establish trust for agent if not found.

        Uses config.authority_id and config.default_capabilities.

        Raises:
            TrustError: If auto-establishment fails
        """
        if not self._config.authority_id:
            raise TrustError("Cannot auto-establish trust: no authority_id configured")

        from eatp.chain import CapabilityType
        from eatp.operations import CapabilityRequest

        capabilities = [
            CapabilityRequest(
                capability=cap,
                capability_type=CapabilityType.ACTION,
            )
            for cap in self._config.default_capabilities
        ]

        await self._trust_ops.establish(
            agent_id=self._config.agent_id,
            authority_id=self._config.authority_id,
            capabilities=capabilities,
        )

    @asynccontextmanager
    async def trust_context(
        self,
        action: str,
        resource: Optional[str] = None,
        context: Optional[ExecutionContext] = None,
    ):
        """
        Context manager for trust-aware code blocks.

        Automatically verifies trust and records audit.

        EATP Enhancement: Context now propagates human_origin for traceability.

        Example:
            async with trusted_agent.trust_context("analyze_data", "database", ctx) as trust_ctx:
                # Trust already verified
                result = await some_operation()
                # Audit automatically recorded on exit with human_origin

        Args:
            action: Action being performed
            resource: Resource being accessed
            context: ExecutionContext with human_origin for EATP traceability

        Yields:
            TrustContext with execution information
        """
        # EATP: Get execution context
        eatp_context = context or get_current_context()

        ctx = TrustContext(
            agent_id=self._config.agent_id,
            action=action,
            resource=resource,
        )

        # Add EATP traceability to metadata
        if eatp_context:
            ctx.metadata["human_origin"] = eatp_context.human_origin.human_id
            ctx.metadata["trace_id"] = eatp_context.trace_id

        # Verify trust
        ctx.verification_result = await self.verify_trust(
            action=action,
            resource=resource,
        )
        ctx.effective_constraints = ctx.verification_result.effective_constraints or []

        action_result = ActionResult.SUCCESS
        try:
            # EATP: Propagate context within the block
            if eatp_context:
                with set_execution_context(eatp_context):
                    yield ctx
            else:
                yield ctx
        except Exception:
            action_result = ActionResult.FAILURE
            raise
        finally:
            # Record audit with EATP context
            await self.record_audit(
                action=action,
                resource=resource,
                result=action_result,
                audit_context=ctx.metadata,
                eatp_context=eatp_context,
            )


class TrustedSupervisorAgent(TrustedAgent):
    """
    TrustedAgent with delegation capabilities for hierarchical trust.

    Extends TrustedAgent to enable supervisor agents to delegate
    trust to worker agents with constraint tightening.

    Key Features:
    - **Worker Delegation**: Delegate capabilities to worker agents
    - **Auto-Establishment**: Optionally auto-establish worker trust
    - **Constraint Tightening**: Add constraints when delegating
    - **Worker Supervision**: Track and revoke worker delegations

    Example:
        >>> supervisor = TrustedSupervisorAgent(
        ...     agent=base_agent,
        ...     trust_ops=trust_ops,
        ...     config=TrustedAgentConfig(agent_id="supervisor-001"),
        ... )
        >>>
        >>> # Delegate to worker with additional constraints
        >>> delegation = await supervisor.delegate_to_worker(
        ...     worker_id="worker-001",
        ...     task_id="analyze-q4-data",
        ...     capabilities=["analyze_data"],
        ...     additional_constraints=["q4_data_only"],
        ... )
        >>>
        >>> # Revoke delegation when done
        >>> await supervisor.revoke_worker_delegation(delegation.id, "worker-001")
    """

    def __init__(
        self,
        agent: Any,
        trust_ops: TrustOperations,
        config: TrustedAgentConfig,
        audit_store: Optional[AuditStore] = None,
        auto_establish_workers: bool = False,
    ):
        """
        Initialize TrustedSupervisorAgent.

        Args:
            agent: The agent instance to wrap
            trust_ops: TrustOperations instance
            config: TrustedAgentConfig with trust settings
            audit_store: Optional AuditStore for recording audits
            auto_establish_workers: If True, auto-establish worker trust
        """
        super().__init__(agent, trust_ops, config, audit_store)
        self._auto_establish_workers = auto_establish_workers
        self._active_delegations: Dict[str, Set[str]] = (
            {}
        )  # worker_id -> delegation_ids

    async def delegate_to_worker(
        self,
        worker_id: str,
        task_id: str,
        capabilities: List[str],
        additional_constraints: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        context: Optional[ExecutionContext] = None,
    ) -> Any:
        """
        Delegate trust to a worker agent.

        Creates a delegation record that grants the worker a subset
        of this agent's capabilities with additional constraints.

        EATP Enhancement: Delegation now propagates human_origin to workers,
        ensuring complete traceability from human through all delegation levels.

        Args:
            worker_id: Worker agent ID
            task_id: Unique identifier for the delegated task
            capabilities: Capabilities to delegate (must be subset of supervisor's)
            additional_constraints: Additional constraints for worker (tightening only)
            expires_at: When delegation expires
            context: ExecutionContext with human_origin for EATP traceability

        Returns:
            Tuple of (DelegationRecord, ExecutionContext for the worker)

        Raises:
            CapabilityNotFoundError: If supervisor lacks capability
            DelegationError: If delegation fails
        """
        # EATP: Get execution context - propagates human_origin to worker
        eatp_context = context or get_current_context()

        # Record delegation audit with EATP context
        await self.record_audit(
            action="delegate_trust",
            resource=worker_id,
            audit_context={
                "task_id": task_id,
                "capabilities": capabilities,
                "additional_constraints": additional_constraints or [],
            },
            eatp_context=eatp_context,
        )

        # EATP: Perform delegation with context propagation
        delegation = await self._trust_ops.delegate(
            delegator_id=self._config.agent_id,
            delegatee_id=worker_id,
            task_id=task_id,
            capabilities=capabilities,
            additional_constraints=additional_constraints,
            expires_at=expires_at,
            context=eatp_context,  # EATP: Pass context for human_origin propagation
        )

        # Track active delegation
        if worker_id not in self._active_delegations:
            self._active_delegations[worker_id] = set()
        self._active_delegations[worker_id].add(delegation.id)

        # EATP: Create context for the worker with proper delegation chain
        worker_context = None
        if eatp_context:
            worker_context = eatp_context.with_delegation(
                worker_id, {c: True for c in (additional_constraints or [])}
            )

        return delegation, worker_context

    async def revoke_worker_delegation(
        self,
        delegation_id: str,
        worker_id: str,
        context: Optional[ExecutionContext] = None,
    ) -> None:
        """
        Revoke a delegation to a worker.

        EATP Enhancement: Revocation is audited with human_origin traceability.

        Args:
            delegation_id: Delegation to revoke
            worker_id: Worker agent ID
            context: ExecutionContext with human_origin for EATP traceability

        Raises:
            DelegationError: If delegation not found
        """
        # EATP: Get execution context
        eatp_context = context or get_current_context()

        # Record revocation audit with EATP context
        await self.record_audit(
            action="revoke_delegation",
            resource=worker_id,
            audit_context={"delegation_id": delegation_id},
            eatp_context=eatp_context,
        )

        # Revoke delegation
        await self._trust_ops.revoke_delegation(delegation_id, worker_id)

        # Update tracking
        if worker_id in self._active_delegations:
            self._active_delegations[worker_id].discard(delegation_id)

    async def get_worker_delegations(
        self,
        worker_id: str,
    ) -> List[Any]:
        """
        Get all active delegations to a worker.

        Args:
            worker_id: Worker agent ID

        Returns:
            List of DelegationRecords for the worker
        """
        return await self._trust_ops.get_delegation_chain(worker_id)

    async def create_worker(
        self,
        worker_agent: Any,
        worker_id: str,
        capabilities: List[str],
        constraints: Optional[List[str]] = None,
        context: Optional[ExecutionContext] = None,
    ) -> tuple["TrustedAgent", Optional[ExecutionContext]]:
        """
        Create a trusted worker agent with delegated capabilities.

        Combines worker creation with delegation in a single operation.

        EATP Enhancement: Returns worker ExecutionContext with propagated human_origin.

        Args:
            worker_agent: Agent instance for the worker
            worker_id: Unique ID for the worker
            capabilities: Capabilities to delegate
            constraints: Additional constraints for the worker
            context: ExecutionContext with human_origin for EATP traceability

        Returns:
            Tuple of (TrustedAgent instance for the worker, ExecutionContext for the worker)
        """
        # EATP: Get execution context
        eatp_context = context or get_current_context()

        # Create worker config
        worker_config = TrustedAgentConfig(
            agent_id=worker_id,
            verification_level=self._config.verification_level,
            audit_enabled=self._config.audit_enabled,
        )

        # Create trusted worker
        trusted_worker = TrustedAgent(
            agent=worker_agent,
            trust_ops=self._trust_ops,
            config=worker_config,
            audit_store=self._audit_store,
        )

        # Delegate capabilities with EATP context propagation
        _, worker_context = await self.delegate_to_worker(
            worker_id=worker_id,
            task_id=f"worker-{worker_id}-creation",
            capabilities=capabilities,
            additional_constraints=constraints,
            context=eatp_context,
        )

        return trusted_worker, worker_context


class TrustContextManager:
    """
    Async context manager for trust-aware execution blocks.

    Provides a convenient way to wrap code blocks with trust
    verification and audit recording.

    EATP Enhancement: Now supports ExecutionContext for human_origin traceability.

    Example:
        >>> async with TrustContextManager(trust_ops, "agent-001", eatp_context=ctx) as mgr:
        ...     await mgr.verify("analyze_data", "database")
        ...     # Perform trusted operations
        ...     result = await some_operation()
        ...     await mgr.record_success("analyze_data")
    """

    def __init__(
        self,
        trust_ops: TrustOperations,
        agent_id: str,
        audit_store: Optional[AuditStore] = None,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
        eatp_context: Optional[ExecutionContext] = None,
    ):
        """
        Initialize TrustContextManager.

        EATP Enhancement: Accepts ExecutionContext for human_origin propagation.

        Args:
            trust_ops: TrustOperations instance
            agent_id: Agent ID for trust operations
            audit_store: Optional AuditStore for audits
            verification_level: Level of verification
            eatp_context: ExecutionContext with human_origin for EATP traceability
        """
        self._trust_ops = trust_ops
        self._agent_id = agent_id
        self._audit_store = audit_store
        self._verification_level = verification_level
        self._current_anchor_id: Optional[str] = None
        self._actions: List[str] = []
        self._eatp_context = eatp_context or get_current_context()

    async def __aenter__(self) -> "TrustContextManager":
        """Enter the trust context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit the trust context, recording failure if exception occurred."""
        if exc_type is not None:
            # Record failure for all pending actions
            for action in self._actions:
                await self.record_failure(action, str(exc_val))
        return False  # Don't suppress exceptions

    async def verify(
        self,
        action: str,
        resource: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verify trust for an action.

        Args:
            action: Action to verify
            resource: Resource being accessed
            context: Additional context

        Returns:
            VerificationResult

        Raises:
            VerificationFailedError: If verification fails
        """
        self._actions.append(action)

        result = await self._trust_ops.verify(
            agent_id=self._agent_id,
            action=action,
            resource=resource,
            level=self._verification_level,
            context=context or {},
        )

        if not result.valid:
            raise VerificationFailedError(
                action=action,
                agent_id=self._agent_id,
                reason=result.reason or "Trust verification failed",
                violations=result.violations,
            )

        return result

    async def record_success(
        self,
        action: str,
        resource: Optional[str] = None,
        audit_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record successful action.

        EATP Enhancement: Records human_origin with audit.

        Args:
            action: Action that succeeded
            resource: Resource accessed
            audit_context: Additional context

        Returns:
            Audit anchor ID
        """
        if action in self._actions:
            self._actions.remove(action)

        anchor = await self._trust_ops.audit(
            agent_id=self._agent_id,
            action=action,
            resource=resource,
            result=ActionResult.SUCCESS,
            context_data=audit_context or {},
            parent_anchor_id=self._current_anchor_id,
            audit_store=self._audit_store,
            context=self._eatp_context,  # EATP: Pass context for human_origin
        )

        self._current_anchor_id = anchor.id
        return anchor.id

    async def record_failure(
        self,
        action: str,
        error: str,
        resource: Optional[str] = None,
    ) -> str:
        """
        Record failed action.

        EATP Enhancement: Records human_origin with audit.

        Args:
            action: Action that failed
            error: Error message
            resource: Resource accessed

        Returns:
            Audit anchor ID
        """
        if action in self._actions:
            self._actions.remove(action)

        anchor = await self._trust_ops.audit(
            agent_id=self._agent_id,
            action=action,
            resource=resource,
            result=ActionResult.FAILURE,
            context_data={"error": error},
            parent_anchor_id=self._current_anchor_id,
            audit_store=self._audit_store,
            context=self._eatp_context,  # EATP: Pass context for human_origin
        )

        self._current_anchor_id = anchor.id
        return anchor.id
