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

import logging
from typing import Any, Dict, Optional, Tuple

from kailash.sdk_exceptions import RuntimeExecutionError
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


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
        ```python
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
        ```
    """

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
            self.logger.error(f"Cyclic workflow execution failed: {str(e)}")
            raise RuntimeExecutionError(f"Cycle execution failed: {str(e)}") from e
