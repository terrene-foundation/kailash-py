"""
Validation mixin for runtime parameter and workflow validation.

Provides comprehensive validation capabilities for workflows, nodes,
parameters, and connections. All validation logic is shared between
LocalRuntime and AsyncLocalRuntime as it contains no I/O operations.

EXTRACTION SOURCE: LocalRuntime (local.py)
    - Lines 2054-2119: validate_workflow()
    - Lines 2625-2691: _validate_connection_contracts()
    - Lines 3567-3632: _validate_conditional_execution_prerequisites()
    - Lines 3634-3680: _validate_switch_results()
    - Lines 3682-3730: _validate_conditional_execution_results()

Design Pattern:
    100% shared logic - no sync/async variants needed. All methods
    perform pure validation with no I/O operations.

Version:
    Added in: v0.10.0
    Part of: Runtime parity remediation (Phase 1)
"""

from typing import Any

from kailash.sdk_exceptions import WorkflowValidationError
from kailash.workflow import Workflow


class ValidationMixin:
    """
    Validation capabilities for workflow runtimes.

    This mixin provides comprehensive validation logic for workflows,
    nodes, parameters, and connections. All methods are 100% shared
    between sync and async runtimes as they perform pure validation
    with no I/O operations.

    Shared Logic (100%):
        All validation methods are pure logic with no sync/async
        variants needed. They validate data structures and configurations
        without performing any I/O or execution.

    Dependencies:
        - Requires workflow.graph attribute (from Workflow)
        - Requires self.logger attribute (from BaseRuntime)
        - Requires self.debug attribute (from BaseRuntime)
        - No dependencies on other mixins

    Usage:
        class LocalRuntime(BaseRuntime, ValidationMixin):
            # Inherits all 5 validation methods
            pass

        class AsyncLocalRuntime(BaseRuntime, ValidationMixin):
            # Inherits same 5 validation methods
            pass

    Examples:
        # Validation is called automatically during execution
        runtime = LocalRuntime()
        runtime.execute(workflow)  # Calls validation methods

        # Can also validate manually
        warnings = runtime.validate_workflow(workflow)
        runtime._validate_connection_contracts(workflow, node_id, inputs, outputs)

    See Also:
        - BaseRuntime: Base runtime class
        - ADR-XXX: Runtime Refactoring for Feature Parity

    Version:
        Added in: v0.10.0
        Part of: Runtime parity remediation
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize validation mixin.

        IMPORTANT: Must call super().__init__() to maintain MRO chain.
        Follows SecureGovernedNode pattern for mixin initialization.
        """
        super().__init__(*args, **kwargs)
        # Validation mixin is stateless - no attributes needed

    def validate_workflow(self, workflow: Workflow) -> list[str]:
        """
        Validate a workflow before execution.

        Performs comprehensive validation including:
        - Basic workflow structure validation
        - Disconnected node detection
        - Required parameter checking
        - Connection validation
        - Performance warnings for large workflows

        EXTRACTED FROM: LocalRuntime.validate_workflow() (lines 2054-2119)
        SHARED LOGIC: 100% - Pure validation with no I/O

        Args:
            workflow: Workflow to validate

        Returns:
            List of validation warnings (empty if valid)

        Raises:
            WorkflowValidationError: If workflow is invalid

        Implementation Notes:
            - Calls workflow.validate() for basic structure
            - Checks for disconnected nodes in multi-node workflows
            - Validates required parameters are provided or connected
            - Warns about performance implications for large workflows
            - All logic is synchronous and shared between runtimes

        Examples:
            # Basic validation
            runtime = LocalRuntime()
            warnings = runtime.validate_workflow(workflow)
            if warnings:
                for warning in warnings:
                    print(f"Warning: {warning}")

            # Validation with error handling
            try:
                warnings = runtime.validate_workflow(workflow)
                if not warnings:
                    print("Workflow is valid")
            except WorkflowValidationError as e:
                print(f"Invalid workflow: {e}")
        """
        warnings = []

        try:
            workflow.validate()
        except WorkflowValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            raise WorkflowValidationError(f"Workflow validation failed: {e}") from e

        # Check for disconnected nodes
        for node_id in workflow.graph.nodes():
            if (
                workflow.graph.in_degree(node_id) == 0
                and workflow.graph.out_degree(node_id) == 0
                and len(workflow.graph.nodes()) > 1
            ):
                warnings.append(f"Node '{node_id}' is disconnected from the workflow")

        # Check for missing required parameters
        for node_id, node_instance in workflow._node_instances.items():
            try:
                params = node_instance.get_parameters()
            except Exception as e:
                warnings.append(f"Failed to get parameters for node '{node_id}': {e}")
                continue

            for param_name, param_def in params.items():
                if param_def.required:
                    # Check if provided in config or connected
                    if param_name not in node_instance.config:
                        # Check if connected from another node
                        incoming_params = set()
                        for _, _, data in workflow.graph.in_edges(node_id, data=True):
                            mapping = data.get("mapping", {})
                            incoming_params.update(mapping.values())

                        if (
                            param_name not in incoming_params
                            and param_def.default is None
                        ):
                            warnings.append(
                                f"Node '{node_id}' missing required parameter '{param_name}' "
                                f"(no default value provided)"
                            )

        # Check for potential performance issues
        if len(workflow.graph.nodes()) > 100:
            warnings.append(
                f"Large workflow with {len(workflow.graph.nodes())} nodes "
                f"may have performance implications"
            )

        return warnings

    def _validate_connection_contracts(
        self,
        workflow: Workflow,
        target_node_id: str,
        target_inputs: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        """
        Validate connection contracts for a target node.

        Ensures that all connections between nodes have valid parameter
        mappings, source outputs exist, and target inputs are compatible
        with defined contracts.

        EXTRACTED FROM: LocalRuntime._validate_connection_contracts() (lines 2625-2691)
        SHARED LOGIC: 100% - Pure validation with no I/O

        Args:
            workflow: The workflow being executed
            target_node_id: ID of the target node
            target_inputs: Inputs being passed to the target node
            node_outputs: Outputs from all previously executed nodes

        Returns:
            List of contract violations (empty if all valid)

        Implementation Notes:
            - Uses ContractValidator for validation logic
            - Checks connection contracts from workflow metadata
            - Validates both source and target data against contracts
            - Returns detailed violation information for debugging
            - All logic is synchronous and shared

        Examples:
            # Validate during execution
            violations = runtime._validate_connection_contracts(
                workflow, "processor", inputs, outputs
            )
            if violations:
                for v in violations:
                    print(f"Contract violation: {v}")

            # Check specific connection
            result = runtime._validate_connection_contracts(
                workflow=workflow,
                target_node_id="data_processor",
                target_inputs={"data": [1, 2, 3]},
                node_outputs={"reader": {"output": [1, 2, 3]}}
            )
        """
        violations = []

        # Get connection contracts from workflow metadata
        connection_contracts = workflow.metadata.get("connection_contracts", {})
        if not connection_contracts:
            return violations  # No contracts to validate

        # Create contract validator
        from kailash.workflow.contracts import ConnectionContract, ContractValidator

        validator = ContractValidator()

        # Find all connections targeting this node
        for connection in workflow.connections:
            if connection.target_node == target_node_id:
                connection_id = f"{connection.source_node}.{connection.source_output} → {connection.target_node}.{connection.target_input}"

                # Check if this connection has a contract
                if connection_id in connection_contracts:
                    contract_dict = connection_contracts[connection_id]

                    # Reconstruct contract from dictionary
                    contract = ConnectionContract.from_dict(contract_dict)

                    # Get source data from node outputs
                    source_data = None
                    if connection.source_node in node_outputs:
                        source_outputs = node_outputs[connection.source_node]
                        if connection.source_output in source_outputs:
                            source_data = source_outputs[connection.source_output]

                    # Get target data from inputs
                    target_data = target_inputs.get(connection.target_input)

                    # Validate the connection if we have data
                    if source_data is not None or target_data is not None:
                        is_valid, errors = validator.validate_connection(
                            contract, source_data, target_data
                        )

                        if not is_valid:
                            violations.append(
                                {
                                    "connection": connection_id,
                                    "contract": contract.name,
                                    "error": "; ".join(errors),
                                }
                            )

        return violations

    def _validate_conditional_execution_prerequisites(self, workflow: Workflow) -> bool:
        """
        Validate that workflow meets prerequisites for conditional execution.

        Checks if a workflow is suitable for conditional execution optimization
        which skips unreachable branches based on SwitchNode decisions.

        EXTRACTED FROM: LocalRuntime._validate_conditional_execution_prerequisites()
        (lines 3567-3632)
        SHARED LOGIC: 100% - Pure validation with no I/O

        Args:
            workflow: Workflow to validate

        Returns:
            True if prerequisites are met, False otherwise

        Implementation Notes:
            - Requires at least one SwitchNode for conditional execution
            - Validates workflow size (max 100 nodes recommended)
            - Checks SwitchNode configuration and outputs
            - Uses ConditionalBranchAnalyzer for switch detection
            - All logic is synchronous and shared

        Examples:
            # Check if conditional execution is suitable
            if runtime._validate_conditional_execution_prerequisites(workflow):
                print("Using conditional execution optimization")
            else:
                print("Using standard execution")

            # Use in execution flow
            if self._has_conditional_patterns(workflow):
                if self._validate_conditional_execution_prerequisites(workflow):
                    return await self._execute_conditional_approach(...)
        """
        try:
            # Check if workflow has at least one SwitchNode
            from kailash.analysis import ConditionalBranchAnalyzer

            analyzer = ConditionalBranchAnalyzer(workflow)
            switch_nodes = analyzer._find_switch_nodes()

            if not switch_nodes:
                self.logger.debug(
                    "No SwitchNodes found - cannot use conditional execution"
                )
                return False

            # Check if workflow is too complex for conditional execution
            if len(workflow.graph.nodes) > 100:  # Configurable threshold
                self.logger.warning(
                    "Workflow too large for conditional execution optimization"
                )
                return False

            # Validate that all SwitchNodes have proper outputs
            for switch_id in switch_nodes:
                node_data = workflow.graph.nodes[switch_id]
                node_instance = node_data.get("node") or node_data.get("instance")

                if node_instance is None:
                    self.logger.warning(f"SwitchNode {switch_id} has no instance")
                    return False

                # Check if the SwitchNode has proper output configuration
                # SwitchNode might store condition_field in different ways
                has_condition = (
                    hasattr(node_instance, "condition_field")
                    or hasattr(node_instance, "_condition_field")
                    or (
                        hasattr(node_instance, "parameters")
                        and "condition_field"
                        in getattr(node_instance, "parameters", {})
                    )
                    or "SwitchNode"
                    in str(type(node_instance))  # Type-based validation as fallback
                )

                if not has_condition:
                    self.logger.debug(
                        f"SwitchNode {switch_id} condition validation unclear - allowing execution"
                    )
                    # Don't fail here - let conditional execution attempt and fall back if needed

            return True

        except Exception as e:
            self.logger.warning(
                f"Error validating conditional execution prerequisites: {e}"
            )
            return False

    def _validate_switch_results(
        self, switch_results: dict[str, dict[str, Any]]
    ) -> bool:
        """
        Validate that switch results are valid for conditional execution.

        Checks SwitchNode execution results to ensure they contain valid
        branch information for conditional execution path planning.

        EXTRACTED FROM: LocalRuntime._validate_switch_results() (lines 3634-3680)
        SHARED LOGIC: 100% - Pure validation with no I/O

        Args:
            switch_results: Results from SwitchNode execution

        Returns:
            True if results are valid, False otherwise

        Implementation Notes:
            - Validates result structure (must be dict)
            - Checks for execution failures
            - Ensures required output keys are present (true_output/false_output)
            - All checks are synchronous and shared

        Examples:
            # Validate switch execution results
            switch_results = {"switch1": {"true_output": data1, "false_output": None}}
            if runtime._validate_switch_results(switch_results):
                print("Switch results are valid")

            # Use in conditional execution flow
            if not self._validate_switch_results(switch_results):
                raise WorkflowValidationError("Switch results validation failed")
        """
        try:
            if not switch_results:
                self.logger.debug("No switch results to validate")
                return True

            for switch_id, result in switch_results.items():
                # Check for execution errors
                if isinstance(result, dict) and result.get("failed"):
                    self.logger.warning(
                        f"SwitchNode {switch_id} failed during execution"
                    )
                    return False

                # Validate result structure
                if not isinstance(result, dict):
                    self.logger.warning(
                        f"SwitchNode {switch_id} returned invalid result type: {type(result)}"
                    )
                    return False

                # Check for required output keys (at least one branch should be present)
                has_output = any(
                    key in result for key in ["true_output", "false_output"]
                )
                if not has_output:
                    self.logger.warning(
                        f"SwitchNode {switch_id} missing required output keys"
                    )
                    return False

            return True

        except Exception as e:
            self.logger.warning(f"Error validating switch results: {e}")
            return False

    def _validate_conditional_execution_results(
        self, results: dict[str, dict[str, Any]], workflow: Workflow
    ) -> bool:
        """
        Validate final results from conditional execution.

        Performs post-execution validation to ensure conditional execution
        produced valid results and didn't skip critical nodes or fail
        excessively.

        EXTRACTED FROM: LocalRuntime._validate_conditional_execution_results()
        (lines 3682-3730)
        SHARED LOGIC: 100% - Pure validation with no I/O

        Args:
            results: Execution results
            workflow: Original workflow

        Returns:
            True if results are valid, False otherwise

        Implementation Notes:
            - Ensures at least some nodes executed (not empty)
            - Warns if too few nodes executed (<30% of total)
            - Checks for excessive failures (>50% of executed nodes)
            - All validation is synchronous and shared

        Examples:
            # Validate final execution results
            if runtime._validate_conditional_execution_results(results, workflow):
                print("Conditional execution completed successfully")

            # Use in execution flow
            if not self._validate_conditional_execution_results(results, workflow):
                raise WorkflowValidationError("Conditional execution results invalid")
        """
        try:
            # Check that at least some nodes executed
            if not results:
                self.logger.warning("No results from conditional execution")
                return False

            # Validate that critical nodes (if any) were executed
            # This could be expanded based on workflow metadata
            total_nodes = len(workflow.graph.nodes)
            executed_nodes = len(results)

            # If we executed less than 30% of nodes, might be an issue
            if executed_nodes < (total_nodes * 0.3):
                self.logger.warning(
                    f"Conditional execution only ran {executed_nodes}/{total_nodes} nodes - might indicate an issue"
                )
                # Don't fail here, but log for monitoring

            # Check for excessive failures
            failed_nodes = sum(
                1
                for result in results.values()
                if isinstance(result, dict) and result.get("failed")
            )

            if failed_nodes > (executed_nodes * 0.5):
                self.logger.warning(
                    f"Too many node failures: {failed_nodes}/{executed_nodes}"
                )
                return False

            return True

        except Exception as e:
            self.logger.warning(f"Error validating conditional execution results: {e}")
            return False
