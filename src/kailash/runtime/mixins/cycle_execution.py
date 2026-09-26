"""
Cycle execution mixin for runtime cyclic workflow execution.

Provides shared cycle execution logic for LocalRuntime and AsyncLocalRuntime.
Delegates actual cycle orchestration to CyclicWorkflowExecutor.

EXTRACTION SOURCE: LocalRuntime (local.py lines 958-979)
SHARED LOGIC: 100% - Pure delegation and validation

Design Pattern:
    This mixin uses the delegation pattern to provide a unified interface
    for cycle execution while delegating the actual work to CyclicWorkflowExecutor.

Dependencies:
    - BaseRuntime: Reads enable_cycles, cyclic_executor, logger, debug
    - ConditionalExecutionMixin: Uses _workflow_has_cycles() for detection
    - CyclicWorkflowExecutor: Composition - handles actual cycle execution

Version:
    Added in: v0.10.0
    Part of: Runtime parity remediation (Phase 3)
"""

import asyncio
import concurrent.futures
import contextvars
import logging
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Dict, Optional, Tuple

from kailash.sdk_exceptions import RuntimeExecutionError
from kailash.utils.secure_logging import safe_exception_frames
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)
_cycle_attempt_executor = contextvars.ContextVar("cycle_attempt_executor", default=None)


class CycleExecutionMixin:
    """
    Cycle execution capabilities for workflow runtimes.

    Provides a unified interface for executing cyclic workflows by delegating
    to CyclicWorkflowExecutor. This mixin is 100% shared logic - no sync/async
    variants needed as it only validates and delegates.

    Key Features:
        - Validates enable_cycles configuration
        - Delegates to CyclicWorkflowExecutor
        - Wraps executor errors with runtime context
        - Debug logging for cycle detection
        - Backward compatible with LocalRuntime behavior

    Design Pattern (Delegation):
        1. Validate: Check enable_cycles, cyclic_executor exists
        2. Detect: Use ConditionalExecutionMixin._workflow_has_cycles()
        3. Delegate: Call cyclic_executor.execute()
        4. Wrap Errors: Add runtime context to executor exceptions

    State Ownership (Stateless):
        This mixin creates NO state attributes. It reads from BaseRuntime:
        - self.enable_cycles: Configuration flag
        - self.cyclic_executor: CyclicWorkflowExecutor instance
        - self.logger: Logging instance
        - self.debug: Debug mode flag

    Dependencies:
        - BaseRuntime: Provides enable_cycles, cyclic_executor, logger, debug
        - ConditionalExecutionMixin: Provides _workflow_has_cycles() method
        - CyclicWorkflowExecutor: External component that handles actual cycles

    Example:
        .. code-block:: python

            class LocalRuntime(
                BaseRuntime,
                ValidationMixin,
                ParameterHandlingMixin,
                ConditionalExecutionMixin,
                CycleExecutionMixin  # Phase 3
            ):
                def execute(self, workflow, **kwargs):
                    if self._workflow_has_cycles(workflow):
                        return self._execute_cyclic_workflow(workflow, kwargs.get('inputs'))
                    # ... other execution paths
    """

    # Declare attributes provided by BaseRuntime (used by mixin methods)
    logger: logging.Logger
    debug: bool
    enable_cycles: bool
    cyclic_executor: Any

    @contextmanager
    def _cycle_executor_scope(self, executor):
        """Select a wrapper's policy for exactly one attempt on this owner."""
        token = _cycle_attempt_executor.set((self, executor))
        try:
            yield
        finally:
            _cycle_attempt_executor.reset(token)

    def _cycle_executor_for_attempt(self):
        selection = _cycle_attempt_executor.get()
        # Clear even a foreign selection before any node can start nested work.
        # The outer scope restores its caller's context on exit.
        _cycle_attempt_executor.set(None)
        if selection is not None and selection[0] is self:
            return selection[1]
        return self.cyclic_executor if self.enable_cycles else None

    def __init__(self, *args, **kwargs):
        """Initialize mixin via super() for proper MRO chain.

        This mixin creates NO state attributes (stateless design).
        All state is owned by BaseRuntime.
        """
        super().__init__(*args, **kwargs)
        # NO attributes created - mixin is stateless

    def _execute_cyclic_workflow(
        self,
        workflow: Workflow,
        parameters: Optional[Dict[str, Any]] = None,
        task_manager=None,
        run_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Execute workflow with cycles using CyclicWorkflowExecutor.

        Template method that:
        1. Validates enable_cycles configuration
        2. Logs cycle detection (if debug mode)
        3. Delegates to cyclic_executor.execute()
        4. Wraps errors with runtime context
        5. Returns results and run_id

        Args:
            workflow: Workflow to execute (must have cycles)
            parameters: Initial parameters/overrides
            task_manager: Optional task tracking
            run_id: Execution run ID

        Returns:
            Tuple of (results dict, run_id string)

        Raises:
            RuntimeExecutionError: If enable_cycles=False or cyclic_executor missing
            RuntimeExecutionError: If executor raises exception (wrapped with context)

        Design:
            This method follows the delegation pattern - it validates and logs,
            then delegates the actual cycle execution to CyclicWorkflowExecutor.

            No I/O operations occur in this method - only validation, logging,
            and delegation. This makes it 100% shared logic (no sync/async variants).

        Example:
            ```python
            runtime = LocalRuntime(enable_cycles=True)
            workflow = create_workflow_with_cycles()
            results, run_id = runtime._execute_cyclic_workflow(workflow, {"input": "value"})
            ```
        """
        # Phase 1: Validation - Check enable_cycles configuration
        if not self.enable_cycles:
            raise RuntimeExecutionError(
                "Cyclic workflow execution attempted but enable_cycles=False. "
                "Set enable_cycles=True in runtime configuration to execute cyclic workflows."
            )

        # Phase 2: Validation - Check cyclic_executor exists
        if not hasattr(self, "cyclic_executor") or self.cyclic_executor is None:
            raise RuntimeExecutionError(
                "CyclicWorkflowExecutor not initialized. "
                "This should not happen - enable_cycles=True but executor is missing."
            )

        # Phase 3: Debug Logging - Log cycle detection if debug mode enabled
        if self.debug:
            self.logger.info(f"Executing cyclic workflow: {workflow.workflow_id}")
            self.logger.debug("Delegating to CyclicWorkflowExecutor")

        # Phase 4: Delegation - Delegate to CyclicWorkflowExecutor (composition pattern)
        try:
            # Convert None to empty dict for parameters (CyclicWorkflowExecutor expects dict)
            params = parameters if parameters is not None else {}

            # Delegate to executor
            results, result_run_id = self.cyclic_executor.execute(
                workflow=workflow,
                parameters=params,
                task_manager=task_manager,
                run_id=run_id,
                runtime=self,  # Pass runtime for enterprise features
            )

            # Phase 5: Debug Logging - Log completion
            if self.debug:
                self.logger.debug(
                    f"Cyclic workflow completed: {len(results)} node results"
                )

            return results, result_run_id

        except Exception as e:
            # Phase 6: Error Handling - Wrap executor exceptions with context
            from kailash.runtime.resource_manager import (
                _is_retry_observer_failure,
                _raise_if_runtime_terminal,
            )

            _raise_if_runtime_terminal(e)
            if _is_retry_observer_failure(e):
                raise
            self.logger.error(
                "Cyclic workflow execution failed: %s", safe_exception_frames(e)
            )
            raise RuntimeExecutionError(f"Cycle execution failed: {str(e)}") from e

    async def _execute_cyclic_workflow_async(
        self,
        workflow,
        parameters,
        task_manager,
        run_id,
        *,
        workflow_context,
        execution_state,
        cyclic_executor,
    ):
        """Keep graph traversal off-loop, and node work on the attempt's loop.

        The traversal worker owns no async resources. Every node dispatch and
        completion runs on the originating runtime loop and carries its context.
        Cancellation drains that worker before the attempt releases its resources.
        """
        loop = asyncio.get_running_loop()
        stopped = threading.Event()
        active = []
        active_lock = threading.Lock()
        node_tasks = set()

        def iteration_state(cycle_id, iteration):
            tracker = execution_state.execution_tracker
            if tracker is not None and cycle_id is not None:
                tracker = tracker.for_cycle_iteration(cycle_id, iteration)
            return replace(execution_state, execution_tracker=tracker)

        async def replay_node(node_id, cycle_id, iteration):
            state = iteration_state(cycle_id, iteration)
            self._check_execution_cancelled(node_id, state)
            if stopped.is_set():
                raise asyncio.CancelledError()
            tracker = state.execution_tracker
            if tracker is not None and tracker.is_completed(node_id):
                result = tracker.get_output(node_id)
                self._check_node_result(node_id, result)
                return True, result
            return False, None

        async def execute_node(node, node_id, inputs, cycle_id, iteration):
            task = asyncio.current_task()
            node_tasks.add(task)
            try:
                state = iteration_state(cycle_id, iteration)
                self._check_execution_cancelled(node_id, state)
                if stopped.is_set():
                    raise asyncio.CancelledError()
                started_at = datetime.now(UTC)
                if workflow_context is not None:
                    node._workflow_context = workflow_context
                result = await self.execute_node_with_enterprise_features(
                    node, node_id, inputs
                )
                self._check_node_result(node_id, result)
                await self._publish_node_completion(
                    workflow=workflow,
                    node_id=node_id,
                    node_instance=node,
                    outputs=result,
                    run_id=run_id,
                    started_at=started_at,
                    execution_state=state,
                )
                return result
            finally:
                node_tasks.remove(task)

        def on_owner(function, *args):
            if stopped.is_set():
                raise asyncio.CancelledError()
            coroutine = function(*args)
            try:
                future = asyncio.run_coroutine_threadsafe(coroutine, loop)
            except BaseException:
                coroutine.close()
                raise
            # Scheduling can race with cancellation before registration. Do not
            # hold this lock while scheduling or waiting on the owner loop.
            with active_lock:
                active.append(future)
                cancel_after_admission = stopped.is_set()
            if cancel_after_admission:
                future.cancel()
            try:
                return future.result()
            except concurrent.futures.CancelledError:
                raise asyncio.CancelledError() from None
            finally:
                with active_lock:
                    active.remove(future)

        def dispatch(*args):
            return on_owner(execute_node, *args)

        def replay(*args):
            return on_owner(replay_node, *args)

        executor = cyclic_executor._fork_for_execution()
        worker = asyncio.create_task(
            asyncio.to_thread(
                executor.execute,
                workflow,
                parameters,
                task_manager,
                run_id,
                self,
                node_executor=dispatch,
                node_replayer=replay,
            )
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            with active_lock:
                stopped.set()
                pending = list(active)
            for future in pending:
                future.cancel()

            async def drain_owner():
                await asyncio.gather(worker, return_exceptions=True)
                # Concurrent Future cancellation precedes the asyncio task's
                # async finally blocks; wait for actual node tasks as well.
                await asyncio.sleep(0)
                await asyncio.gather(*node_tasks, return_exceptions=True)

            drain = asyncio.create_task(drain_owner())
            while not drain.done():
                try:
                    await asyncio.shield(drain)
                except asyncio.CancelledError:
                    continue
            drain.result()
            raise
        except Exception as error:
            from kailash.runtime.resource_manager import (
                _is_retry_observer_failure,
                _raise_if_runtime_terminal,
            )

            _raise_if_runtime_terminal(error)
            if _is_retry_observer_failure(error):
                raise
            self.logger.error(
                "Cyclic workflow execution failed: %s", safe_exception_frames(error)
            )
            raise RuntimeExecutionError(f"Cycle execution failed: {error}") from error
