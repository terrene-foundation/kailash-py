# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Trust-Aware Orchestration Runtime.

Extends OrchestrationRuntime with trust verification, ensuring all agent
actions in orchestrated workflows are verified before execution and
audited after completion.

Features:
- Pre-execution trust verification for all agents
- Automatic delegation chain creation
- Post-execution audit recording
- Trust context propagation across agent boundaries
- Integration with SecureChannel for inter-agent communication

Example:
    from eatp.orchestration import (
        TrustAwareOrchestrationRuntime,
        TrustExecutionContext,
    )

    # Create trust-aware runtime
    runtime = TrustAwareOrchestrationRuntime(
        trust_operations=trust_ops,
        agent_registry=registry,
        config=TrustAwareRuntimeConfig(max_concurrent_agents=10)
    )
    await runtime.start()

    # Create execution context
    context = TrustExecutionContext.create(
        parent_agent_id="supervisor-001",
        task_id="workflow-123",
        delegated_capabilities=["analyze", "report"],
    )

    # Execute workflow with trust enforcement
    results = await runtime.execute_trusted_workflow(
        tasks=["analyze Q3", "generate report"],
        context=context,
    )

    await runtime.shutdown()
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from eatp.orchestration.exceptions import (
    OrchestrationTrustError,
    PolicyViolationError,
    TrustVerificationFailedError,
)
from eatp.orchestration.execution_context import (
    DelegationEntry,
    TrustExecutionContext,
)
from eatp.orchestration.policy import (
    PolicyResult,
    TrustPolicy,
    TrustPolicyEngine,
)

logger = logging.getLogger(__name__)


@dataclass
class TrustAwareRuntimeConfig:
    """Configuration for TrustAwareOrchestrationRuntime."""

    # Concurrency limits
    max_concurrent_agents: int = 10
    max_queue_size: int = 1000

    # Trust verification
    verify_before_execution: bool = True
    audit_after_execution: bool = True
    fail_on_verification_error: bool = True

    # Policy enforcement
    enable_policy_engine: bool = True
    policy_cache_ttl_seconds: float = 300.0

    # Delegation
    auto_create_delegations: bool = True
    max_delegation_depth: int = 10

    # Timeout
    verification_timeout_seconds: float = 10.0
    execution_timeout_seconds: float = 300.0


@dataclass
class TrustedTaskResult:
    """Result of a trusted task execution."""

    task_id: str
    agent_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    verification_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    audit_anchor_id: Optional[str] = None
    delegation_entry: Optional[DelegationEntry] = None


@dataclass
class TrustedWorkflowStatus:
    """Status of a trusted workflow execution."""

    workflow_id: str
    context: TrustExecutionContext
    total_tasks: int
    completed_tasks: int = 0
    failed_tasks: int = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    results: List[TrustedTaskResult] = field(default_factory=list)
    verification_failures: List[str] = field(default_factory=list)
    policy_violations: List[str] = field(default_factory=list)


class TrustAwareOrchestrationRuntime:
    """
    Orchestration runtime with integrated trust verification.

    Wraps agent execution with trust verification, delegation tracking,
    and audit logging to ensure all actions comply with trust policies.

    Key features:
    - Verifies trust before each agent execution
    - Creates delegation records for supervisor-worker patterns
    - Records audit anchors after execution
    - Propagates trust context across agent boundaries
    - Integrates with TrustPolicyEngine for policy enforcement
    """

    def __init__(
        self,
        trust_operations: Any,
        agent_registry: Optional[Any] = None,
        config: Optional[TrustAwareRuntimeConfig] = None,
        secure_channel_factory: Optional[Callable] = None,
    ):
        """
        Initialize the trust-aware runtime.

        Args:
            trust_operations: TrustOperations instance for trust verification
            agent_registry: Optional AgentRegistry for agent discovery
            config: Runtime configuration
            secure_channel_factory: Optional factory for creating SecureChannels
        """
        self._trust_ops = trust_operations
        self._agent_registry = agent_registry
        self._config = config or TrustAwareRuntimeConfig()
        self._secure_channel_factory = secure_channel_factory

        # Policy engine
        self._policy_engine: Optional[TrustPolicyEngine] = None
        if self._config.enable_policy_engine:
            self._policy_engine = TrustPolicyEngine(
                trust_operations=trust_operations,
                cache_ttl_seconds=self._config.policy_cache_ttl_seconds,
            )

        # Runtime state
        self._running = False
        self._active_workflows: Dict[str, TrustedWorkflowStatus] = {}
        self._agent_contexts: Dict[str, TrustExecutionContext] = {}

        # Metrics
        self._total_executions = 0
        self._total_verifications = 0
        self._verification_failures = 0
        self._policy_violations = 0

    @property
    def policy_engine(self) -> Optional[TrustPolicyEngine]:
        """Get the policy engine."""
        return self._policy_engine

    @property
    def is_running(self) -> bool:
        """Check if runtime is running."""
        return self._running

    async def start(self) -> None:
        """Start the runtime."""
        if self._running:
            return

        logger.info("Starting TrustAwareOrchestrationRuntime")
        self._running = True

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Shutdown the runtime gracefully."""
        if not self._running:
            return

        logger.info("Shutting down TrustAwareOrchestrationRuntime")

        # Wait for active workflows
        if self._active_workflows:
            logger.info(f"Waiting for {len(self._active_workflows)} active workflows")
            await asyncio.sleep(min(timeout, 5.0))

        self._running = False

    def register_policy(self, policy: TrustPolicy) -> None:
        """Register a policy with the policy engine."""
        if self._policy_engine:
            self._policy_engine.register_policy(policy)

    async def verify_agent_trust(
        self,
        agent_id: str,
        context: Optional[TrustExecutionContext] = None,
        action: Optional[str] = None,
    ) -> PolicyResult:
        """
        Verify trust for an agent before execution.

        Args:
            agent_id: Agent to verify
            context: Optional execution context
            action: Optional action being performed

        Returns:
            PolicyResult indicating verification outcome
        """
        start_time = time.perf_counter()
        self._total_verifications += 1

        try:
            # Verify trust chain exists
            chain = await self._trust_ops.get_chain(agent_id)
            if chain is None:
                self._verification_failures += 1
                return PolicyResult.deny(
                    "trust_chain_check",
                    f"Agent '{agent_id}' has no established trust chain",
                )

            # Verify trust chain is valid
            verification = await self._trust_ops.verify(
                agent_id=agent_id,
                action=action,
            )
            if not verification.valid:
                self._verification_failures += 1
                return PolicyResult.deny(
                    "trust_verification",
                    f"Trust verification failed: {verification.reason}",
                )

            # Evaluate policies if engine is enabled
            if self._policy_engine:
                policy_result = await self._policy_engine.evaluate_for_agent(
                    agent_id, context
                )
                if not policy_result.allowed:
                    self._policy_violations += 1
                    return policy_result

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return PolicyResult(
                allowed=True,
                policy_name="trust_verification",
                reason="Trust verification passed",
                evaluation_time_ms=elapsed_ms,
            )

        except Exception as e:
            self._verification_failures += 1
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return PolicyResult(
                allowed=False,
                policy_name="trust_verification",
                reason=f"Verification error: {e}",
                evaluation_time_ms=elapsed_ms,
            )

    async def create_delegation(
        self,
        supervisor_id: str,
        worker_id: str,
        task_id: str,
        capabilities: List[str],
        context: TrustExecutionContext,
        reasoning_trace: Optional[Any] = None,
    ) -> DelegationEntry:
        """
        Create a delegation from supervisor to worker.

        Args:
            supervisor_id: Delegating agent
            worker_id: Agent receiving delegation
            task_id: Task identifier
            capabilities: Capabilities being delegated
            context: Current execution context
            reasoning_trace: Optional ReasoningTrace explaining WHY this
                delegation is being made. Passed through to
                TrustOperations.delegate() for signing and storage.

        Returns:
            DelegationEntry for the delegation
        """
        # Verify supervisor has the capabilities to delegate
        for cap in capabilities:
            if not context.has_capability(cap):
                raise OrchestrationTrustError(
                    f"Supervisor '{supervisor_id}' cannot delegate "
                    f"capability '{cap}' - not in context"
                )

        # Create delegation record in trust store
        try:
            await self._trust_ops.delegate(
                delegator_id=supervisor_id,
                delegatee_id=worker_id,
                capabilities=capabilities,
                task_id=task_id,
                reasoning_trace=reasoning_trace,
            )
        except Exception as e:
            logger.warning(f"Failed to create delegation record: {e}")
            # Continue - delegation entry still valid for tracking

        # Create entry
        entry = DelegationEntry(
            delegator_id=supervisor_id,
            delegatee_id=worker_id,
            task_id=task_id,
            capabilities=capabilities,
            timestamp=datetime.now(timezone.utc),
        )

        logger.debug(
            f"Created delegation: {supervisor_id} -> {worker_id} "
            f"for task {task_id} with capabilities {capabilities}"
        )

        return entry

    async def execute_trusted_task(
        self,
        agent_id: str,
        task: Any,
        context: TrustExecutionContext,
        executor: Callable,
        reasoning_trace: Optional[Any] = None,
    ) -> TrustedTaskResult:
        """
        Execute a task with trust verification.

        Args:
            agent_id: Agent executing the task
            task: Task to execute
            context: Execution context
            executor: Async callable that performs the execution
            reasoning_trace: Optional ReasoningTrace explaining WHY this
                task execution was authorized. Attached to the post-execution
                audit anchor via TrustOperations.audit().

        Returns:
            TrustedTaskResult with execution outcome
        """
        task_id = str(uuid.uuid4())
        self._total_executions += 1

        result = TrustedTaskResult(
            task_id=task_id,
            agent_id=agent_id,
            success=False,
        )

        # Pre-execution verification
        if self._config.verify_before_execution:
            verify_start = time.perf_counter()
            verification = await self.verify_agent_trust(agent_id, context)
            result.verification_time_ms = (time.perf_counter() - verify_start) * 1000

            if not verification.allowed:
                if self._config.fail_on_verification_error:
                    raise TrustVerificationFailedError(
                        agent_id=agent_id,
                        action="execute_task",
                        reason=verification.reason,
                    )
                else:
                    result.error = f"Trust verification failed: {verification.reason}"
                    return result

        # Execute task
        exec_start = time.perf_counter()
        try:
            result.result = await asyncio.wait_for(
                executor(task),
                timeout=self._config.execution_timeout_seconds,
            )
            result.success = True
        except asyncio.TimeoutError:
            result.error = f"Task execution timed out after {self._config.execution_timeout_seconds}s"
        except Exception as e:
            result.error = str(e)
            logger.error(f"Task execution failed for agent {agent_id}: {e}")

        result.execution_time_ms = (time.perf_counter() - exec_start) * 1000

        # Post-execution audit
        if self._config.audit_after_execution:
            try:
                anchor = await self._trust_ops.audit(
                    agent_id=agent_id,
                    action="execute_task",
                    resource=task_id,
                    result="success" if result.success else "failure",
                    metadata={
                        "task": str(task)[:100],
                        "verification_time_ms": result.verification_time_ms,
                        "execution_time_ms": result.execution_time_ms,
                    },
                    reasoning_trace=reasoning_trace,
                )
                result.audit_anchor_id = anchor.anchor_id if anchor else None
            except Exception as e:
                logger.warning(f"Failed to create audit anchor: {e}")

        return result

    async def execute_trusted_workflow(
        self,
        tasks: List[Any],
        context: TrustExecutionContext,
        agent_selector: Optional[Callable[[Any], str]] = None,
        task_executor: Optional[Callable[[str, Any], Any]] = None,
    ) -> TrustedWorkflowStatus:
        """
        Execute a workflow with trust enforcement.

        Args:
            tasks: List of tasks to execute
            context: Execution context
            agent_selector: Function to select agent for task (default: uses context.current_agent_id)
            task_executor: Function to execute task (default: no-op)

        Returns:
            TrustedWorkflowStatus with workflow outcome
        """
        workflow_id = str(uuid.uuid4())
        status = TrustedWorkflowStatus(
            workflow_id=workflow_id,
            context=context,
            total_tasks=len(tasks),
        )
        self._active_workflows[workflow_id] = status

        try:
            for task in tasks:
                # Select agent
                agent_id = (
                    agent_selector(task) if agent_selector else context.current_agent_id
                )

                # Create executor
                async def default_executor(t: Any) -> Any:
                    if task_executor:
                        return await task_executor(agent_id, t)
                    return {"status": "completed", "task": str(t)}

                # Execute with trust
                try:
                    result = await self.execute_trusted_task(
                        agent_id=agent_id,
                        task=task,
                        context=context,
                        executor=default_executor,
                    )
                    status.results.append(result)

                    if result.success:
                        status.completed_tasks += 1
                    else:
                        status.failed_tasks += 1
                        if result.error and "verification" in result.error.lower():
                            status.verification_failures.append(result.error)

                except TrustVerificationFailedError as e:
                    status.verification_failures.append(str(e))
                    status.failed_tasks += 1

                except PolicyViolationError as e:
                    status.policy_violations.append(str(e))
                    status.failed_tasks += 1

        finally:
            status.end_time = datetime.now(timezone.utc)
            del self._active_workflows[workflow_id]

        return status

    async def execute_parallel_trusted_workflow(
        self,
        task_groups: Dict[str, List[Any]],
        context: TrustExecutionContext,
        task_executor: Optional[Callable[[str, Any], Any]] = None,
    ) -> TrustedWorkflowStatus:
        """
        Execute parallel workflow with trust enforcement.

        Args:
            task_groups: Dict mapping agent_id to list of tasks
            context: Execution context
            task_executor: Function to execute task

        Returns:
            TrustedWorkflowStatus with workflow outcome
        """
        workflow_id = str(uuid.uuid4())
        total_tasks = sum(len(tasks) for tasks in task_groups.values())
        status = TrustedWorkflowStatus(
            workflow_id=workflow_id,
            context=context,
            total_tasks=total_tasks,
        )
        self._active_workflows[workflow_id] = status

        try:
            # Create tasks for parallel execution
            async def execute_agent_tasks(agent_id: str, tasks: List[Any]):
                # Create child context for this agent
                child_context = context.propagate_to_child(
                    child_agent_id=agent_id,
                    task_id=f"{workflow_id}-{agent_id}",
                )

                results = []
                for task in tasks:

                    async def executor(t: Any) -> Any:
                        if task_executor:
                            return await task_executor(agent_id, t)
                        return {"status": "completed", "task": str(t)}

                    result = await self.execute_trusted_task(
                        agent_id=agent_id,
                        task=task,
                        context=child_context,
                        executor=executor,
                    )
                    results.append(result)
                return results

            # Execute in parallel
            tasks_coros = [
                execute_agent_tasks(agent_id, tasks)
                for agent_id, tasks in task_groups.items()
            ]
            all_results = await asyncio.gather(*tasks_coros, return_exceptions=True)

            # Process results
            for result_batch in all_results:
                if isinstance(result_batch, Exception):
                    status.failed_tasks += 1
                    if isinstance(result_batch, TrustVerificationFailedError):
                        status.verification_failures.append(str(result_batch))
                    elif isinstance(result_batch, PolicyViolationError):
                        status.policy_violations.append(str(result_batch))
                else:
                    for result in result_batch:
                        status.results.append(result)
                        if result.success:
                            status.completed_tasks += 1
                        else:
                            status.failed_tasks += 1

        finally:
            status.end_time = datetime.now(timezone.utc)
            del self._active_workflows[workflow_id]

        return status

    def get_metrics(self) -> Dict[str, Any]:
        """Get runtime metrics."""
        return {
            "total_executions": self._total_executions,
            "total_verifications": self._total_verifications,
            "verification_failures": self._verification_failures,
            "policy_violations": self._policy_violations,
            "active_workflows": len(self._active_workflows),
            "verification_success_rate": (
                (self._total_verifications - self._verification_failures)
                / self._total_verifications
                if self._total_verifications > 0
                else 1.0
            ),
        }

    def get_policy_cache_stats(self) -> Dict[str, Any]:
        """Get policy engine cache statistics."""
        if self._policy_engine:
            return self._policy_engine.get_cache_stats()
        return {}
