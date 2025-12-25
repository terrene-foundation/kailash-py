"""
Unit tests for AsyncLocalRuntime MRO and mixin inheritance verification.

Tests verify that AsyncLocalRuntime correctly inherits from LocalRuntime
and has access to all BaseRuntime attributes and mixin methods through
the inheritance chain.

Expected MRO:
AsyncLocalRuntime → LocalRuntime → BaseRuntime → ABC → CycleExecutionMixin
→ ValidationMixin → ConditionalExecutionMixin → object
"""

from abc import ABC

import pytest
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.runtime.base import BaseRuntime
from kailash.runtime.mixins import (
    ConditionalExecutionMixin,
    CycleExecutionMixin,
    ValidationMixin,
)
from kailash.workflow.builder import WorkflowBuilder


class TestAsyncLocalRuntimeMRO:
    """Test AsyncLocalRuntime Method Resolution Order and inheritance."""

    def test_async_local_runtime_mro(self) -> None:
        """
        Verify AsyncLocalRuntime has correct MRO chain.

        Expected MRO:
        AsyncLocalRuntime → LocalRuntime → BaseRuntime → ABC →
        CycleExecutionMixin → ValidationMixin → ConditionalExecutionMixin → object
        """
        # Get MRO
        mro = AsyncLocalRuntime.__mro__

        # Convert to class names for easier assertion
        mro_names = [cls.__name__ for cls in mro]

        # Verify critical classes in MRO
        assert "AsyncLocalRuntime" in mro_names
        assert "LocalRuntime" in mro_names
        assert "BaseRuntime" in mro_names
        assert "CycleExecutionMixin" in mro_names
        assert "ValidationMixin" in mro_names
        assert "ConditionalExecutionMixin" in mro_names
        assert "ABC" in mro_names
        assert "object" in mro_names

        # Verify order: AsyncLocalRuntime comes before LocalRuntime
        async_idx = mro_names.index("AsyncLocalRuntime")
        local_idx = mro_names.index("LocalRuntime")
        assert (
            async_idx < local_idx
        ), "AsyncLocalRuntime should come before LocalRuntime"

        # Verify order: LocalRuntime comes before BaseRuntime
        base_idx = mro_names.index("BaseRuntime")
        assert local_idx < base_idx, "LocalRuntime should come before BaseRuntime"

        # Verify order: BaseRuntime comes before mixins
        cycle_idx = mro_names.index("CycleExecutionMixin")
        validation_idx = mro_names.index("ValidationMixin")
        conditional_idx = mro_names.index("ConditionalExecutionMixin")
        assert (
            base_idx < cycle_idx
        ), "BaseRuntime should come before CycleExecutionMixin"
        assert (
            base_idx < validation_idx
        ), "BaseRuntime should come before ValidationMixin"
        assert (
            base_idx < conditional_idx
        ), "BaseRuntime should come before ConditionalExecutionMixin"

    def test_async_runtime_has_baseruntime_attributes(self) -> None:
        """
        Verify AsyncLocalRuntime has access to BaseRuntime configuration.

        Tests that core BaseRuntime configuration attributes are accessible
        through the inheritance chain.
        """
        runtime = AsyncLocalRuntime()

        # Verify BaseRuntime configuration attributes exist
        assert hasattr(runtime, "debug"), "Missing debug attribute from BaseRuntime"
        assert hasattr(
            runtime, "enable_cycles"
        ), "Missing enable_cycles attribute from BaseRuntime"
        assert hasattr(
            runtime, "enable_async"
        ), "Missing enable_async attribute from BaseRuntime"
        assert hasattr(
            runtime, "enable_monitoring"
        ), "Missing enable_monitoring attribute from BaseRuntime"

        # Verify attributes have correct types
        assert isinstance(runtime.debug, bool), "debug should be bool"
        assert isinstance(runtime.enable_cycles, bool), "enable_cycles should be bool"
        assert isinstance(runtime.enable_async, bool), "enable_async should be bool"
        assert isinstance(
            runtime.enable_monitoring, bool
        ), "enable_monitoring should be bool"

    def test_async_runtime_can_validate(self) -> None:
        """
        Verify AsyncLocalRuntime can access ValidationMixin methods.

        Tests that validation methods are accessible and can be called
        through the inheritance chain. ValidationMixin provides validate_workflow()
        as a public method and several private validation methods.
        """
        runtime = AsyncLocalRuntime()

        # Verify ValidationMixin public method exists
        assert hasattr(
            runtime, "validate_workflow"
        ), "Missing validate_workflow from ValidationMixin"

        # Verify ValidationMixin private methods exist
        assert hasattr(
            runtime, "_validate_connection_contracts"
        ), "Missing _validate_connection_contracts from ValidationMixin"
        assert hasattr(
            runtime, "_validate_conditional_execution_prerequisites"
        ), "Missing _validate_conditional_execution_prerequisites from ValidationMixin"
        assert hasattr(
            runtime, "_validate_switch_results"
        ), "Missing _validate_switch_results from ValidationMixin"

        # Verify methods are callable
        assert callable(
            runtime.validate_workflow
        ), "validate_workflow should be callable"
        assert callable(
            runtime._validate_connection_contracts
        ), "_validate_connection_contracts should be callable"

        # Test validation with simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test_node", {"code": "result = 42"})
        built_workflow = workflow.build()

        # Should not raise exception for valid workflow
        try:
            warnings = runtime.validate_workflow(built_workflow)
            assert isinstance(
                warnings, list
            ), "validate_workflow should return list of warnings"
        except Exception as e:
            pytest.fail(
                f"validate_workflow raised unexpected exception for valid workflow: {e}"
            )

    def test_async_runtime_has_cycle_execution(self) -> None:
        """
        Verify AsyncLocalRuntime can access CycleExecutionMixin methods.

        Tests that cycle execution methods are accessible through
        the inheritance chain. CycleExecutionMixin provides _execute_cyclic_workflow()
        as a private method that delegates to CyclicWorkflowExecutor.
        """
        runtime = AsyncLocalRuntime()

        # Verify CycleExecutionMixin method exists
        assert hasattr(
            runtime, "_execute_cyclic_workflow"
        ), "Missing _execute_cyclic_workflow from CycleExecutionMixin"

        # Verify method is callable
        assert callable(
            runtime._execute_cyclic_workflow
        ), "_execute_cyclic_workflow should be callable"

        # Verify cycle-related attributes from configuration
        assert hasattr(
            runtime, "enable_cycles"
        ), "Missing enable_cycles from BaseRuntime configuration"
        assert isinstance(runtime.enable_cycles, bool), "enable_cycles should be bool"

        # Verify cyclic executor is initialized when cycles enabled
        runtime_with_cycles = AsyncLocalRuntime(enable_cycles=True)
        assert hasattr(
            runtime_with_cycles, "cyclic_executor"
        ), "Missing cyclic_executor when enable_cycles=True"
        assert (
            runtime_with_cycles.cyclic_executor is not None
        ), "cyclic_executor should be initialized when enable_cycles=True"

    def test_async_runtime_has_conditional_execution(self) -> None:
        """
        Verify AsyncLocalRuntime can access ConditionalExecutionMixin methods.

        Tests that conditional execution methods are accessible through
        the inheritance chain. ConditionalExecutionMixin provides various private
        methods for handling conditional workflows (SwitchNode, BranchNode patterns).
        """
        runtime = AsyncLocalRuntime()

        # Verify ConditionalExecutionMixin private methods exist
        assert hasattr(
            runtime, "_has_conditional_patterns"
        ), "Missing _has_conditional_patterns from ConditionalExecutionMixin"
        assert hasattr(
            runtime, "_workflow_has_cycles"
        ), "Missing _workflow_has_cycles from ConditionalExecutionMixin"
        assert hasattr(
            runtime, "_should_use_hierarchical_execution"
        ), "Missing _should_use_hierarchical_execution from ConditionalExecutionMixin"
        assert hasattr(
            runtime, "_should_skip_conditional_node"
        ), "Missing _should_skip_conditional_node from ConditionalExecutionMixin"

        # Verify async execution methods exist
        assert hasattr(
            runtime, "_execute_conditional_approach"
        ), "Missing _execute_conditional_approach from ConditionalExecutionMixin"
        assert hasattr(
            runtime, "_execute_switch_nodes"
        ), "Missing _execute_switch_nodes from ConditionalExecutionMixin"

        # Verify methods are callable
        assert callable(
            runtime._has_conditional_patterns
        ), "_has_conditional_patterns should be callable"
        assert callable(
            runtime._workflow_has_cycles
        ), "_workflow_has_cycles should be callable"
        assert callable(
            runtime._should_use_hierarchical_execution
        ), "_should_use_hierarchical_execution should be callable"

        # Verify ConditionalExecutionMixin attribute exists
        assert hasattr(
            runtime, "conditional_execution"
        ), "Missing conditional_execution attribute from ConditionalExecutionMixin"
        assert isinstance(
            runtime.conditional_execution, str
        ), "conditional_execution should be str (routing strategy)"
        assert runtime.conditional_execution in [
            "route_data",
            "hierarchical",
        ], "conditional_execution should be valid routing strategy"


class TestAsyncLocalRuntimeInheritanceChain:
    """Test AsyncLocalRuntime inherits correctly from parent classes."""

    def test_async_runtime_is_instance_of_local_runtime(self) -> None:
        """Verify AsyncLocalRuntime is instance of LocalRuntime."""
        runtime = AsyncLocalRuntime()
        assert isinstance(
            runtime, LocalRuntime
        ), "AsyncLocalRuntime should be instance of LocalRuntime"

    def test_async_runtime_is_instance_of_base_runtime(self) -> None:
        """Verify AsyncLocalRuntime is instance of BaseRuntime."""
        runtime = AsyncLocalRuntime()
        assert isinstance(
            runtime, BaseRuntime
        ), "AsyncLocalRuntime should be instance of BaseRuntime"

    def test_async_runtime_is_instance_of_mixins(self) -> None:
        """Verify AsyncLocalRuntime is instance of all mixins."""
        runtime = AsyncLocalRuntime()

        assert isinstance(
            runtime, CycleExecutionMixin
        ), "AsyncLocalRuntime should be instance of CycleExecutionMixin"
        assert isinstance(
            runtime, ValidationMixin
        ), "AsyncLocalRuntime should be instance of ValidationMixin"
        assert isinstance(
            runtime, ConditionalExecutionMixin
        ), "AsyncLocalRuntime should be instance of ConditionalExecutionMixin"

    def test_async_runtime_issubclass_relationships(self) -> None:
        """Verify AsyncLocalRuntime subclass relationships."""
        assert issubclass(
            AsyncLocalRuntime, LocalRuntime
        ), "AsyncLocalRuntime should be subclass of LocalRuntime"
        assert issubclass(
            AsyncLocalRuntime, BaseRuntime
        ), "AsyncLocalRuntime should be subclass of BaseRuntime"
        assert issubclass(
            AsyncLocalRuntime, CycleExecutionMixin
        ), "AsyncLocalRuntime should be subclass of CycleExecutionMixin"
        assert issubclass(
            AsyncLocalRuntime, ValidationMixin
        ), "AsyncLocalRuntime should be subclass of ValidationMixin"
        assert issubclass(
            AsyncLocalRuntime, ConditionalExecutionMixin
        ), "AsyncLocalRuntime should be subclass of ConditionalExecutionMixin"
