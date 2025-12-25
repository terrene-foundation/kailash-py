"""
Integration test for debugging the nested conditional execution bug.

This test executes the actual LocalRuntime with detailed logging to trace
where the bug occurs in the execution pipeline.
"""

import asyncio

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestNestedConditionalExecutionDebug:
    """Integration test to debug the nested conditional execution bug."""

    @pytest.fixture
    def complex_workflow(self):
        """Create the complex workflow that demonstrates the bug."""
        workflow = WorkflowBuilder()

        # Data source
        workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {
                "code": "result = {'user_type': 'premium', 'region': 'US', 'value': 1000}"
            },
        )

        # User type switch
        workflow.add_node(
            "SwitchNode",
            "user_type_switch",
            {"condition_field": "user_type", "operator": "==", "value": "premium"},
        )

        # Region switch (nested under premium branch)
        workflow.add_node(
            "SwitchNode",
            "region_switch",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        # Premium processors
        workflow.add_node(
            "PythonCodeNode",
            "premium_validator",
            {
                "code": """
# Preserve original input data and add validation
input_data = input if isinstance(input, dict) else {}
result = input_data.copy()
result.update({'validated': True, 'tier': 'premium'})
            """
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "us_premium_processor",
            {"code": "result = {'processed': True, 'region': 'US', 'discount': 0.20}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "intl_premium_processor",
            {
                "code": "result = {'processed': True, 'region': 'international', 'discount': 0.15}"
            },
        )

        # Basic processors (unreachable in this test)
        workflow.add_node(
            "PythonCodeNode",
            "basic_validator",
            {
                "code": """
# Preserve original input data and add validation
input_data = input if isinstance(input, dict) else {}
result = input_data.copy()
result.update({'validated': True, 'tier': 'basic'})
            """
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "basic_processor",
            {"code": "result = {'processed': True, 'discount': 0.05}"},
        )

        # Final aggregator
        workflow.add_node(
            "PythonCodeNode",
            "aggregator",
            {"code": "result = {'final': True, 'timestamp': 'now'}"},
        )

        # Connect the workflow
        workflow.add_connection("data_source", "result", "user_type_switch", "input")

        # Premium branch connections
        workflow.add_connection(
            "user_type_switch", "true_output", "premium_validator", "input"
        )
        workflow.add_connection("premium_validator", "result", "region_switch", "input")
        workflow.add_connection(
            "region_switch", "true_output", "us_premium_processor", "input"
        )
        workflow.add_connection(
            "region_switch", "false_output", "intl_premium_processor", "input"
        )

        # Basic branch connections (unreachable)
        workflow.add_connection(
            "user_type_switch", "false_output", "basic_validator", "input"
        )
        workflow.add_connection("basic_validator", "result", "basic_processor", "input")

        # Aggregator connections
        workflow.add_connection(
            "us_premium_processor", "result", "aggregator", "premium_input"
        )
        workflow.add_connection(
            "intl_premium_processor", "result", "aggregator", "premium_input"
        )
        workflow.add_connection(
            "basic_processor", "result", "aggregator", "basic_input"
        )

        return workflow.build()

    @pytest.mark.asyncio
    async def test_skip_branches_execution_detailed_trace(self, complex_workflow):
        """
        Test skip_branches mode with detailed tracing to identify the bug.

        This test should demonstrate that:
        1. The DynamicExecutionPlanner creates the correct plan
        2. The LocalRuntime receives this correct plan
        3. But somehow still executes intl_premium_processor incorrectly
        """
        runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)

        # Patch the _execute_pruned_plan method to capture debug info
        original_execute_pruned_plan = runtime._execute_pruned_plan
        captured_execution_plan = None
        captured_switch_results = None

        async def debug_execute_pruned_plan(
            workflow,
            switch_results,
            parameters,
            task_manager,
            run_id,
            workflow_context,
            existing_results,
        ):
            nonlocal captured_execution_plan, captured_switch_results

            # Import DynamicExecutionPlanner to check what plan it creates
            from kailash.planning.dynamic_execution_planner import (
                DynamicExecutionPlanner,
            )

            planner = DynamicExecutionPlanner(workflow)
            captured_execution_plan = planner.create_execution_plan(switch_results)
            captured_switch_results = switch_results

            print(f"DEBUG PATCH: Switch results: {switch_results}")
            print(f"DEBUG PATCH: Execution plan: {captured_execution_plan}")

            # Call original method
            return await original_execute_pruned_plan(
                workflow,
                switch_results,
                parameters,
                task_manager,
                run_id,
                workflow_context,
                existing_results,
            )

        # Apply the patch
        runtime._execute_pruned_plan = debug_execute_pruned_plan

        # Execute the workflow
        results, run_id = await runtime.execute_async(complex_workflow)

        # Debug: Print all results
        print("DEBUG: Final execution results:")
        for node_id, result in results.items():
            if result is not None:
                print(f"  {node_id}: {result}")
            else:
                print(f"  {node_id}: None (skipped)")

        # Verify the captured execution plan was correct
        assert captured_execution_plan is not None, "Failed to capture execution plan"
        assert captured_switch_results is not None, "Failed to capture switch results"

        print(f"DEBUG: Captured execution plan: {captured_execution_plan}")
        print(f"DEBUG: Captured switch results: {captured_switch_results}")

        # The execution plan should be correct
        assert "us_premium_processor" in captured_execution_plan
        assert "intl_premium_processor" not in captured_execution_plan

        # But let's check what actually executed
        executed_nodes = [k for k, v in results.items() if v is not None]
        print(f"DEBUG: Actually executed nodes: {executed_nodes}")

        # CRITICAL TEST: The bug - intl_premium_processor should NOT have executed
        if "intl_premium_processor" in executed_nodes:
            print(
                "❌ BUG CONFIRMED: intl_premium_processor incorrectly executed despite correct execution plan"
            )
            print(f"   Execution plan said: {captured_execution_plan}")
            print(f"   But executed nodes: {executed_nodes}")

            # This should fail to document the bug
            assert (
                False
            ), "intl_premium_processor incorrectly executed - this is the bug we need to fix"

        # Expected behavior
        assert (
            "us_premium_processor" in executed_nodes
        ), "us_premium_processor should have executed"
        assert (
            "intl_premium_processor" not in executed_nodes
        ), "intl_premium_processor should NOT have executed"

    @pytest.mark.asyncio
    async def test_switch_result_inspection(self, complex_workflow):
        """
        Test to inspect the actual switch results produced during execution.

        This will help us understand if the switches are producing the correct outputs.
        """
        runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)

        # Patch the _execute_switch_nodes method to capture switch results
        original_execute_switch_nodes = runtime._execute_switch_nodes
        captured_switch_results = None

        async def debug_execute_switch_nodes(
            workflow, parameters, task_manager, run_id, workflow_context
        ):
            result = await original_execute_switch_nodes(
                workflow, parameters, task_manager, run_id, workflow_context
            )

            nonlocal captured_switch_results
            captured_switch_results = result

            print("DEBUG PATCH: Switch execution results:")
            for node_id, node_result in result.items():
                print(f"  {node_id}: {node_result}")

            # Extract just switch results
            from kailash.analysis.conditional_branch_analyzer import (
                ConditionalBranchAnalyzer,
            )

            analyzer = ConditionalBranchAnalyzer(workflow)
            switch_node_ids = analyzer._find_switch_nodes()
            switch_only_results = {
                node_id: result[node_id]
                for node_id in switch_node_ids
                if node_id in result
            }

            print("DEBUG PATCH: Switch-only results for planning:")
            for switch_id, switch_result in switch_only_results.items():
                print(f"  {switch_id}: {switch_result}")

            return result

        runtime._execute_switch_nodes = debug_execute_switch_nodes

        # Execute the workflow
        results, run_id = await runtime.execute_async(complex_workflow)

        # Analyze the captured switch results
        assert (
            captured_switch_results is not None
        ), "Failed to capture switch execution results"

        # Check user_type_switch result
        user_type_result = captured_switch_results.get("user_type_switch")
        print(f"DEBUG: user_type_switch result: {user_type_result}")

        # Check region_switch result
        region_switch_result = captured_switch_results.get("region_switch")
        print(f"DEBUG: region_switch result: {region_switch_result}")

        # Verify switch results are as expected
        # user_type_switch should have true_output active (premium user)
        assert user_type_result is not None
        if (
            "true_output" in user_type_result
            and user_type_result["true_output"] is not None
        ):
            print(
                "✅ user_type_switch correctly activated true_output for premium user"
            )
        else:
            print("❌ user_type_switch did not activate true_output for premium user")

        # region_switch should have true_output active (US region)
        assert region_switch_result is not None
        if (
            "true_output" in region_switch_result
            and region_switch_result["true_output"] is not None
        ):
            print("✅ region_switch correctly activated true_output for US region")
        else:
            print("❌ region_switch did not activate true_output for US region")
            print(f"   region_switch result details: {region_switch_result}")
