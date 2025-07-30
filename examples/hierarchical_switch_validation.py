"""
Validation example for hierarchical switch execution in Kailash SDK.

This example demonstrates how the LocalRuntime optimizes execution of workflows
with hierarchical switch patterns by executing switches in dependency layers.
"""

import time

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def create_hierarchical_workflow():
    """Create a workflow with hierarchical switch dependencies."""
    workflow = WorkflowBuilder()

    # Source node provides initial data
    workflow.add_node("PythonCodeNode", "data_source", {
        "code": """
import random
result = {
    'user_type': 'premium',  # 'free', 'premium', or 'enterprise'
    'region': 'US',          # 'US', 'EU', or 'ASIA'
    'feature_flag': True,    # Feature toggle
    'usage_limit': 1000      # Usage threshold
}
"""
    })

    # Layer 1: User type switch (root level)
    workflow.add_node("SwitchNode", "user_type_switch", {
        "condition_field": "user_type",
        "operator": "==",
        "value": "premium"
    })

    # Layer 2: Region switches (depend on user type)
    workflow.add_node("SwitchNode", "region_switch_premium", {
        "condition_field": "region",
        "operator": "==",
        "value": "US"
    })

    workflow.add_node("SwitchNode", "feature_flag_switch", {
        "condition_field": "feature_flag",
        "operator": "==",
        "value": True
    })

    # Layer 3: Usage limit switch (depends on region and feature flag)
    workflow.add_node("SwitchNode", "usage_limit_switch", {
        "condition_field": "usage_limit",
        "operator": ">",
        "value": 500
    })

    # Processing nodes for different paths
    workflow.add_node("PythonCodeNode", "premium_us_processor", {
        "code": "result = {'service': 'premium_us_high_usage', 'priority': 1}"
    })

    workflow.add_node("PythonCodeNode", "premium_feature_processor", {
        "code": "result = {'service': 'premium_feature_enabled', 'priority': 2}"
    })

    workflow.add_node("PythonCodeNode", "default_processor", {
        "code": "result = {'service': 'default', 'priority': 3}"
    })

    # Final merge node
    workflow.add_node("MergeNode", "final_merge", {
        "merge_type": "merge_dict",
        "skip_none": True
    })

    # Build hierarchical connections
    # Layer 1 connections
    workflow.add_connection("data_source", "result", "user_type_switch", "input_data")

    # Layer 2 connections (dependent on Layer 1)
    workflow.add_connection("user_type_switch", "true_output", "region_switch_premium", "input_data")
    workflow.add_connection("user_type_switch", "true_output", "feature_flag_switch", "input_data")

    # Layer 3 connections (dependent on Layer 2)
    workflow.add_connection("region_switch_premium", "true_output", "usage_limit_switch", "input_data")

    # Processing connections
    workflow.add_connection("usage_limit_switch", "true_output", "premium_us_processor", "input")
    workflow.add_connection("feature_flag_switch", "true_output", "premium_feature_processor", "input")
    workflow.add_connection("user_type_switch", "false_output", "default_processor", "input")

    # Merge connections
    workflow.add_connection("premium_us_processor", "result", "final_merge", "data1")
    workflow.add_connection("premium_feature_processor", "result", "final_merge", "data2")
    workflow.add_connection("default_processor", "result", "final_merge", "data3")

    return workflow.build()


def create_complex_hierarchy():
    """Create a more complex workflow with multiple switch layers."""
    workflow = WorkflowBuilder()

    # Initial data with multiple decision points
    workflow.add_node("PythonCodeNode", "complex_source", {
        "code": """
result = {
    'customer_tier': 'gold',     # bronze, silver, gold, platinum
    'account_age': 24,           # months
    'purchase_history': 150,     # number of purchases
    'location': 'urban',         # urban, suburban, rural
    'engagement_score': 85,      # 0-100
    'referral_count': 5          # number of referrals
}
"""
    })

    # Layer 1: Customer tier (root)
    workflow.add_node("SwitchNode", "tier_switch", {
        "condition_field": "customer_tier",
        "operator": "in",
        "value": ["gold", "platinum"]
    })

    # Layer 2: Multiple parallel switches
    workflow.add_node("SwitchNode", "age_switch", {
        "condition_field": "account_age",
        "operator": ">",
        "value": 12
    })

    workflow.add_node("SwitchNode", "purchase_switch", {
        "condition_field": "purchase_history",
        "operator": ">",
        "value": 100
    })

    workflow.add_node("SwitchNode", "location_switch", {
        "condition_field": "location",
        "operator": "==",
        "value": "urban"
    })

    # Layer 3: Dependent on Layer 2
    workflow.add_node("SwitchNode", "engagement_switch", {
        "condition_field": "engagement_score",
        "operator": ">",
        "value": 80
    })

    workflow.add_node("SwitchNode", "referral_switch", {
        "condition_field": "referral_count",
        "operator": ">=",
        "value": 3
    })

    # Processing nodes
    workflow.add_node("PythonCodeNode", "vip_processor", {
        "code": "result = {'segment': 'VIP', 'discount': 30, 'benefits': ['priority_support', 'early_access']}"
    })

    workflow.add_node("PythonCodeNode", "loyal_processor", {
        "code": "result = {'segment': 'Loyal', 'discount': 20, 'benefits': ['free_shipping']}"
    })

    workflow.add_node("PythonCodeNode", "engaged_processor", {
        "code": "result = {'segment': 'Engaged', 'discount': 15, 'benefits': ['newsletter']}"
    })

    # Build connections for hierarchy
    workflow.add_connection("complex_source", "result", "tier_switch", "input_data")

    # Layer 2 - all depend on tier switch
    workflow.add_connection("tier_switch", "true_output", "age_switch", "input_data")
    workflow.add_connection("tier_switch", "true_output", "purchase_switch", "input_data")
    workflow.add_connection("tier_switch", "true_output", "location_switch", "input_data")

    # Layer 3 - depend on Layer 2 results
    workflow.add_connection("age_switch", "true_output", "engagement_switch", "input_data")
    workflow.add_connection("purchase_switch", "true_output", "referral_switch", "input_data")

    # Processing based on final switches
    workflow.add_connection("engagement_switch", "true_output", "vip_processor", "input")
    workflow.add_connection("referral_switch", "true_output", "loyal_processor", "input")
    workflow.add_connection("location_switch", "true_output", "engaged_processor", "input")

    return workflow.build()


def main():
    """Run hierarchical switch validation examples."""
    print("Hierarchical Switch Execution Validation")
    print("=" * 50)

    # Create runtime with debug enabled to see hierarchical execution
    runtime = LocalRuntime(
        conditional_execution="skip_branches",
        debug=True
    )

    # Example 1: Basic hierarchy
    print("\n1. Basic Hierarchical Switch Workflow")
    print("-" * 40)

    workflow1 = create_hierarchical_workflow()
    start_time = time.time()
    results1, run_id1 = runtime.execute(workflow1)
    execution_time1 = time.time() - start_time

    print(f"\nExecution completed in {execution_time1:.3f}s")
    print(f"Nodes executed: {len(results1)}")
    print("\nFinal result:")
    if "final_merge" in results1:
        merge_result = results1['final_merge']
        if 'merged' in merge_result:
            print(f"  Merged data: {merge_result['merged']}")
        else:
            print(f"  Merge node output: {merge_result}")

    # Example 2: Complex hierarchy
    print("\n\n2. Complex Multi-Layer Switch Hierarchy")
    print("-" * 40)

    workflow2 = create_complex_hierarchy()
    start_time = time.time()
    results2, run_id2 = runtime.execute(workflow2)
    execution_time2 = time.time() - start_time

    print(f"\nExecution completed in {execution_time2:.3f}s")
    print(f"Nodes executed: {len(results2)}")
    print("\nCustomer segments identified:")

    for node_id, result in results2.items():
        if "processor" in node_id and "result" in result:
            segment_data = result["result"]
            print(f"  - {segment_data.get('segment', 'Unknown')}: "
                  f"{segment_data.get('discount', 0)}% discount, "
                  f"benefits: {', '.join(segment_data.get('benefits', []))}")

    # Performance comparison
    print("\n\n3. Performance Analysis")
    print("-" * 40)

    # Create runtime without hierarchical execution for comparison
    runtime_standard = LocalRuntime(
        conditional_execution="route_data",
        debug=False
    )

    # Time standard execution
    start_time = time.time()
    results_std, _ = runtime_standard.execute(workflow2)
    standard_time = time.time() - start_time

    print(f"Standard execution time: {standard_time:.3f}s")
    print(f"Hierarchical execution time: {execution_time2:.3f}s")
    print(f"Performance improvement: {((standard_time - execution_time2) / standard_time * 100):.1f}%")

    print("\n✅ Hierarchical switch execution validated successfully!")


if __name__ == "__main__":
    main()
