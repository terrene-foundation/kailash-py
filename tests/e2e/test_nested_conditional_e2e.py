"""
End-to-end tests for the nested conditional execution bug fix.

This module tests complete user scenarios with nested conditional workflows
to ensure the entire system works correctly from user perspective.

BUG SCENARIO:
- Complex conditional workflow with hierarchical switches
- Premium user (true) -> US region (true) should only execute us_premium_processor
- But intl_premium_processor is incorrectly executing (false_output path)
- This affects user experience and business logic correctness
"""

import asyncio

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestNestedConditionalE2E:
    """End-to-end tests for nested conditional execution scenarios."""

    @pytest.mark.asyncio
    async def test_complete_premium_us_user_journey(self):
        """
        Complete user journey: Premium US customer processing workflow.

        Business scenario: A premium US customer places an order and should
        receive US-specific premium processing with 20% discount.
        """
        workflow = WorkflowBuilder()

        # Customer data input
        workflow.add_node(
            "PythonCodeNode",
            "customer_data",
            {
                "code": """
result = {
    'customer_id': 'CUST-12345',
    'user_type': 'premium',
    'region': 'US',
    'order_value': 1000,
    'timestamp': '2024-01-15T10:00:00Z'
}
"""
            },
        )

        # Business logic: Determine customer tier
        workflow.add_node(
            "SwitchNode",
            "tier_classifier",
            {"condition_field": "user_type", "operator": "==", "value": "premium"},
        )

        # Premium customer validation
        workflow.add_node(
            "PythonCodeNode",
            "premium_validation",
            {
                "code": """
# Preserve input data and add validation info
result = input.copy() if input else {}
result.update({
    'tier': 'premium',
    'validated': True,
    'benefits': ['priority_support', 'express_shipping', 'discounts'],
    'validation_timestamp': '2024-01-15T10:01:00Z'
})
"""
            },
        )

        # Regional processing switch
        workflow.add_node(
            "SwitchNode",
            "region_processor",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        # US premium processing (SHOULD execute for US customer)
        workflow.add_node(
            "PythonCodeNode",
            "us_premium_handler",
            {
                "code": """
result = {
    'processor': 'US_PREMIUM',
    'discount_rate': 0.20,
    'tax_rate': 0.08,
    'shipping': 'express_free',
    'support_tier': 'platinum',
    'processing_center': 'US-EAST-1',
    'currency': 'USD'
}
"""
            },
        )

        # International premium processing (should NOT execute for US customer)
        workflow.add_node(
            "PythonCodeNode",
            "intl_premium_handler",
            {
                "code": """
result = {
    'processor': 'INTL_PREMIUM',
    'discount_rate': 0.15,
    'tax_rate': 0.12,
    'shipping': 'international_express',
    'support_tier': 'gold',
    'processing_center': 'EU-WEST-1',
    'currency': 'EUR'
}
"""
            },
        )

        # Basic customer processing (should NOT execute for premium customer)
        workflow.add_node(
            "PythonCodeNode",
            "basic_validation",
            {
                "code": """
result = {
    'tier': 'basic',
    'validated': True,
    'benefits': ['standard_support'],
    'validation_timestamp': '2024-01-15T10:01:00Z'
}
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "basic_handler",
            {
                "code": """
result = {
    'processor': 'BASIC',
    'discount_rate': 0.05,
    'tax_rate': 0.10,
    'shipping': 'standard',
    'support_tier': 'bronze'
}
"""
            },
        )

        # Final order processing
        workflow.add_node(
            "PythonCodeNode",
            "order_finalizer",
            {
                "code": """
def execute(**kwargs):
    # Collect all processing results from kwargs
    processing_data = {}
    for key, value in kwargs.items():
        if key not in ['result', 'processing_data'] and value is not None:
            if isinstance(value, dict):
                processing_data[key] = value

    return {
        'order_id': 'ORDER-789',
        'status': 'processed',
        'final_processing_data': processing_data,
        'processed_timestamp': '2024-01-15T10:05:00Z'
    }
"""
            },
        )

        # Connect the workflow
        workflow.add_connection("customer_data", "result", "tier_classifier", "input")

        # Premium path
        workflow.add_connection(
            "tier_classifier", "true_output", "premium_validation", "input"
        )
        workflow.add_connection(
            "premium_validation", "result", "region_processor", "input"
        )
        workflow.add_connection(
            "region_processor", "true_output", "us_premium_handler", "input"
        )
        workflow.add_connection(
            "region_processor", "false_output", "intl_premium_handler", "input"
        )

        # Basic path
        workflow.add_connection(
            "tier_classifier", "false_output", "basic_validation", "input"
        )
        workflow.add_connection("basic_validation", "result", "basic_handler", "input")

        # Final processing
        workflow.add_connection(
            "us_premium_handler", "result", "order_finalizer", "us_processing"
        )
        workflow.add_connection(
            "intl_premium_handler", "result", "order_finalizer", "intl_processing"
        )
        workflow.add_connection(
            "basic_handler", "result", "order_finalizer", "basic_processing"
        )

        built_workflow = workflow.build()

        # Execute with skip_branches mode
        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, run_id = await runtime.execute_async(built_workflow)

        # Verify correct business logic execution
        executed_nodes = set(k for k, v in results.items() if v is not None)

        print(f"Executed nodes: {executed_nodes}")
        print(f"Run ID: {run_id}")

        # CRITICAL BUSINESS LOGIC VERIFICATION

        # 1. US Premium customer should have US processing
        assert "us_premium_handler" in executed_nodes, (
            f"BUG: US Premium customer should get US processing. "
            f"Executed: {executed_nodes}"
        )

        # 2. Should NOT get international processing
        assert "intl_premium_handler" not in executed_nodes, (
            f"BUG: US customer should not get international processing. "
            f"This affects business logic and pricing! Executed: {executed_nodes}"
        )

        # 3. Should NOT get basic processing
        assert "basic_handler" not in executed_nodes, (
            f"Premium customer should not get basic processing. "
            f"Executed: {executed_nodes}"
        )

        # 4. Verify the processing results are correct
        us_processing = results.get("us_premium_handler")
        assert us_processing is not None, "US premium processing should have results"
        # PythonCodeNode wraps output in 'result' key
        us_data = us_processing.get("result", us_processing)
        assert us_data["processor"] == "US_PREMIUM"
        assert us_data["discount_rate"] == 0.20  # US premium discount
        assert us_data["currency"] == "USD"

        # 5. Verify no incorrect processing occurred
        intl_processing = results.get("intl_premium_handler")
        assert (
            intl_processing is None
        ), f"International processing incorrectly executed: {intl_processing}"

        basic_processing = results.get("basic_handler")
        assert (
            basic_processing is None
        ), f"Basic processing incorrectly executed: {basic_processing}"

        print("✅ US Premium customer journey completed correctly")

    @pytest.mark.asyncio
    async def test_complete_premium_international_user_journey(self):
        """
        Complete user journey: Premium International customer processing workflow.

        Business scenario: A premium international customer should receive
        international-specific premium processing with 15% discount.
        """
        workflow = WorkflowBuilder()

        # International customer data
        workflow.add_node(
            "PythonCodeNode",
            "customer_data",
            {
                "code": """
result = {
    'customer_id': 'CUST-67890',
    'user_type': 'premium',
    'region': 'international',
    'country': 'Germany',
    'order_value': 800,
    'timestamp': '2024-01-15T15:00:00Z'
}
"""
            },
        )

        # Same business logic structure as US test
        workflow.add_node(
            "SwitchNode",
            "tier_classifier",
            {"condition_field": "user_type", "operator": "==", "value": "premium"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "premium_validation",
            {
                "code": """
# Preserve input data and add validation info
result = input.copy() if input else {}
result.update({'tier': 'premium', 'validated': True})
"""
            },
        )

        workflow.add_node(
            "SwitchNode",
            "region_processor",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "us_premium_handler",
            {
                "code": "result = {'processor': 'US_PREMIUM', 'discount_rate': 0.20, 'currency': 'USD'}"
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "intl_premium_handler",
            {
                "code": "result = {'processor': 'INTL_PREMIUM', 'discount_rate': 0.15, 'currency': 'EUR'}"
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "order_finalizer",
            {"code": "result = {'order_id': 'ORDER-456', 'status': 'processed'}"},
        )

        # Same connections
        workflow.add_connection("customer_data", "result", "tier_classifier", "input")
        workflow.add_connection(
            "tier_classifier", "true_output", "premium_validation", "input"
        )
        workflow.add_connection(
            "premium_validation", "result", "region_processor", "input"
        )
        workflow.add_connection(
            "region_processor", "true_output", "us_premium_handler", "input"
        )
        workflow.add_connection(
            "region_processor", "false_output", "intl_premium_handler", "input"
        )
        workflow.add_connection(
            "us_premium_handler", "result", "order_finalizer", "us_processing"
        )
        workflow.add_connection(
            "intl_premium_handler", "result", "order_finalizer", "intl_processing"
        )

        built_workflow = workflow.build()

        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, run_id = await runtime.execute_async(built_workflow)

        executed_nodes = set(k for k, v in results.items() if v is not None)

        # CRITICAL BUSINESS LOGIC VERIFICATION for International customer

        # 1. International Premium customer should have international processing
        assert "intl_premium_handler" in executed_nodes, (
            f"International Premium customer should get international processing. "
            f"Executed: {executed_nodes}"
        )

        # 2. Should NOT get US processing
        assert "us_premium_handler" not in executed_nodes, (
            f"International customer should not get US processing. "
            f"Executed: {executed_nodes}"
        )

        # 3. Verify processing results
        intl_processing = results.get("intl_premium_handler")
        assert (
            intl_processing is not None
        ), "International premium processing should have results"
        # PythonCodeNode wraps output in 'result' key
        intl_data = intl_processing.get("result", intl_processing)
        assert intl_data["processor"] == "INTL_PREMIUM"
        assert intl_data["discount_rate"] == 0.15  # International premium discount
        assert intl_data["currency"] == "EUR"

        # 4. Verify no US processing occurred
        us_processing = results.get("us_premium_handler")
        assert (
            us_processing is None
        ), f"US processing incorrectly executed for international customer: {us_processing}"

        print("✅ International Premium customer journey completed correctly")

    @pytest.mark.asyncio
    async def test_performance_and_efficiency_validation(self):
        """
        Validate that conditional execution provides real performance benefits.

        This test ensures that the conditional execution optimization is working
        as intended from a business/performance perspective.
        """
        # Create a complex workflow with many branches
        workflow = WorkflowBuilder()

        # Customer input
        workflow.add_node(
            "PythonCodeNode",
            "customer_input",
            {
                "code": "result = {'user_type': 'premium', 'region': 'US', 'value': 1500}"
            },
        )

        # Multiple tier switches
        workflow.add_node(
            "SwitchNode",
            "tier_switch",
            {"condition_field": "user_type", "operator": "==", "value": "premium"},
        )

        workflow.add_node(
            "SwitchNode",
            "region_switch",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        # Many processing nodes (most should be skipped)
        processing_nodes = [
            ("premium_us_processor", "US Premium Processing"),
            ("premium_intl_processor", "International Premium Processing"),
            ("basic_us_processor", "US Basic Processing"),
            ("basic_intl_processor", "International Basic Processing"),
            ("vip_us_processor", "US VIP Processing"),
            ("vip_intl_processor", "International VIP Processing"),
            ("enterprise_processor", "Enterprise Processing"),
            ("standard_processor", "Standard Processing"),
        ]

        for node_id, description in processing_nodes:
            workflow.add_node(
                "PythonCodeNode",
                node_id,
                {
                    "code": f"result = {{'processor': '{description}', 'executed': True}}"
                },
            )

        workflow.add_node(
            "PythonCodeNode",
            "premium_validator",
            {
                "code": """
# Preserve input data and add validation info
result = input.copy() if input else {}
result.update({'validated': True, 'tier': 'premium'})
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "basic_validator",
            {"code": "result = {'validated': True, 'tier': 'basic'}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "final_aggregator",
            {"code": "result = {'aggregated': True, 'final': True}"},
        )

        # Connect workflow (only some paths are reachable)
        workflow.add_connection("customer_input", "result", "tier_switch", "input")

        # Premium path (reachable)
        workflow.add_connection(
            "tier_switch", "true_output", "premium_validator", "input"
        )
        workflow.add_connection("premium_validator", "result", "region_switch", "input")
        workflow.add_connection(
            "region_switch", "true_output", "premium_us_processor", "input"
        )
        workflow.add_connection(
            "region_switch", "false_output", "premium_intl_processor", "input"
        )

        # Basic path (unreachable)
        workflow.add_connection(
            "tier_switch", "false_output", "basic_validator", "input"
        )
        workflow.add_connection(
            "basic_validator", "result", "basic_us_processor", "input"
        )
        workflow.add_connection(
            "basic_validator", "result", "basic_intl_processor", "input"
        )

        # Other processors (unreachable)
        workflow.add_connection(
            "premium_validator", "result", "vip_us_processor", "input"
        )
        workflow.add_connection(
            "basic_validator", "result", "enterprise_processor", "input"
        )
        workflow.add_connection(
            "customer_input", "result", "standard_processor", "input"
        )

        # Final aggregation
        workflow.add_connection(
            "premium_us_processor", "result", "final_aggregator", "premium_us"
        )
        workflow.add_connection(
            "premium_intl_processor", "result", "final_aggregator", "premium_intl"
        )
        workflow.add_connection(
            "basic_us_processor", "result", "final_aggregator", "basic_us"
        )
        workflow.add_connection(
            "vip_us_processor", "result", "final_aggregator", "vip_us"
        )
        workflow.add_connection(
            "enterprise_processor", "result", "final_aggregator", "enterprise"
        )
        workflow.add_connection(
            "standard_processor", "result", "final_aggregator", "standard"
        )

        built_workflow = workflow.build()
        total_nodes = len(built_workflow.graph.nodes())

        # Test with conditional execution (after Phase 2 refactoring, skip logic works uniformly)
        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, _ = await runtime.execute_async(built_workflow)
        executed_count = len([k for k, v in results.items() if v is not None])

        print(f"Total nodes in workflow: {total_nodes}")
        print(f"Executed nodes: {executed_count}")
        print(f"Skipped nodes: {total_nodes - executed_count}")

        # Performance assertions - verify skip logic works correctly
        # After Phase 2 refactoring, skip logic works uniformly across all modes
        assert (
            executed_count < total_nodes
        ), f"Should skip unreachable nodes. Total: {total_nodes}, Executed: {executed_count}"

        improvement_percentage = ((total_nodes - executed_count) / total_nodes) * 100
        assert (
            improvement_percentage > 20
        ), f"Should have significant node reduction (>20%), got {improvement_percentage:.1f}%"

        # Business logic verification
        executed_nodes = set(k for k, v in results.items() if v is not None)

        print(f"Executed nodes: {executed_nodes}")

        # Should execute the right path: premium US
        assert (
            "premium_us_processor" in executed_nodes
        ), "Should execute premium US processor"

        # Should NOT execute wrong paths
        # Note: Some nodes have direct (non-conditional) connections and WILL execute:
        #   - vip_us_processor: direct connection from premium_validator
        #   - vip_intl_processor: no connections at all (disconnected source node)
        #   - standard_processor: direct connection from customer_input
        # These execute by workflow design, not a skip logic bug
        wrong_processors = {
            "premium_intl_processor",  # Should not execute (US user, not international)
            "basic_us_processor",  # Should not execute (premium user, not basic)
            "basic_intl_processor",  # Should not execute (premium user, not basic)
            "enterprise_processor",  # Should not execute (no connection from premium path)
        }

        executed_wrong = wrong_processors.intersection(executed_nodes)
        assert not executed_wrong, (
            f"BUG: Wrong processors executed: {executed_wrong}. "
            f"This violates business logic and affects performance!"
        )

        print("✅ Performance and efficiency validation completed")

    @pytest.mark.asyncio
    async def test_validation_script_exact_reproduction(self):
        """
        Exact reproduction of the validation script scenario as an E2E test.

        This should demonstrate the exact bug scenario from the validation script.
        """
        # Use exact same workflow as validation script
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

        # Region switch (only for premium users)
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
# Preserve original data and add validation info
result = input.copy() if input else {}
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

        # Basic processors (should NOT execute)
        workflow.add_node(
            "PythonCodeNode",
            "basic_validator",
            {"code": "result = {'validated': True, 'tier': 'basic'}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "basic_processor",
            {"code": "result = {'processed': True, 'discount': 0.05}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "basic_support",
            {"code": "result = {'support': 'standard'}"},
        )

        # Final aggregator
        workflow.add_node(
            "PythonCodeNode",
            "aggregator",
            {"code": "result = {'final': True, 'timestamp': 'now'}"},
        )

        # Connect exactly as validation script
        workflow.add_connection("data_source", "result", "user_type_switch", "input")

        # Premium branch
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

        # Basic branch
        workflow.add_connection(
            "user_type_switch", "false_output", "basic_validator", "input"
        )
        workflow.add_connection("basic_validator", "result", "basic_processor", "input")
        workflow.add_connection("basic_processor", "result", "basic_support", "input")

        # Aggregator
        workflow.add_connection(
            "us_premium_processor", "result", "aggregator", "premium_input"
        )
        workflow.add_connection(
            "intl_premium_processor", "result", "aggregator", "premium_input"
        )
        workflow.add_connection("basic_support", "result", "aggregator", "basic_input")

        built_workflow = workflow.build()

        # Execute with skip_branches (where bug occurs)
        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, _ = await runtime.execute_async(built_workflow)

        executed_nodes = set(k for k, v in results.items() if v is not None)

        print(f"Validation script reproduction - Executed nodes: {executed_nodes}")

        # Expected for Premium US user
        expected_reachable = {
            "data_source",
            "user_type_switch",
            "premium_validator",
            "region_switch",
            "us_premium_processor",
            "aggregator",
        }

        # Verify expected nodes executed
        for expected in expected_reachable:
            assert (
                expected in executed_nodes
            ), f"Expected node {expected} should execute. Executed: {executed_nodes}"

        # BUG CHECK: Critical business logic validation
        unreachable_nodes = {
            "basic_validator",
            "basic_processor",
            "basic_support",
            "intl_premium_processor",
        }
        executed_unreachable = unreachable_nodes.intersection(executed_nodes)

        if executed_unreachable:
            print(
                f"❌ BUG REPRODUCED: Unreachable nodes executed: {executed_unreachable}"
            )
            print(f"Full executed set: {executed_nodes}")

        assert not executed_unreachable, (
            f"❌ CRITICAL BUG: Unreachable nodes incorrectly executed: {executed_unreachable}. "
            f"This reproduces the exact bug from the validation script. "
            f"Premium US user should only get us_premium_processor, not intl_premium_processor!"
        )

        print("✅ All execution guarantees verified - validation script bug is fixed!")
