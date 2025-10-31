"""Integration tests for intelligent merge strategies with conditional execution."""

import pytest
from kailash.nodes.logic.intelligent_merge import IntelligentMergeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestIntelligentMergeIntegration:
    """Test intelligent merge strategies in real workflows."""

    def test_adaptive_merge_with_conditional_execution(self):
        """Test adaptive merge strategy with conditional execution."""
        workflow = WorkflowBuilder()

        # Data source with conditional flags
        workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {
                "code": """
result = {
    'process_a': True,
    'process_b': False,
    'process_c': True,
    'base_data': {'value': 100}
}
"""
            },
        )

        # Conditional processors
        workflow.add_node(
            "SwitchNode",
            "switch_a",
            {"condition_field": "process_a", "operator": "==", "value": True},
        )

        workflow.add_node(
            "SwitchNode",
            "switch_b",
            {"condition_field": "process_b", "operator": "==", "value": True},
        )

        workflow.add_node(
            "SwitchNode",
            "switch_c",
            {"condition_field": "process_c", "operator": "==", "value": True},
        )

        # Processors for each branch
        workflow.add_node(
            "PythonCodeNode",
            "processor_a",
            {
                "code": "result = {'branch': 'a', 'data': {'processed_a': True, 'value': 150}}"
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "processor_b",
            {
                "code": "result = {'branch': 'b', 'data': {'processed_b': True, 'value': 200}}"
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "processor_c",
            {
                "code": "result = {'branch': 'c', 'data': {'processed_c': True, 'value': 250}}"
            },
        )

        # Intelligent merge node with adaptive strategy
        workflow.add_node(
            "IntelligentMergeNode",
            "intelligent_merge",
            {"method": "adaptive", "handle_none": True},
        )

        # Connect workflow
        workflow.add_connection("data_source", "result", "switch_a", "input_data")
        workflow.add_connection("data_source", "result", "switch_b", "input_data")
        workflow.add_connection("data_source", "result", "switch_c", "input_data")

        workflow.add_connection("switch_a", "true_output", "processor_a", "input_data")
        workflow.add_connection("switch_b", "true_output", "processor_b", "input_data")
        workflow.add_connection("switch_c", "true_output", "processor_c", "input_data")

        # Connect to intelligent merge
        workflow.add_connection("processor_a", "result", "intelligent_merge", "input1")
        workflow.add_connection("processor_b", "result", "intelligent_merge", "input2")
        workflow.add_connection("processor_c", "result", "intelligent_merge", "input3")

        # Execute with conditional execution
        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert "intelligent_merge" in results
        merge_result = results["intelligent_merge"]

        # Should have used consensus strategy since 2 valid inputs meet consensus threshold
        assert merge_result["output"]["strategy_used"] == "consensus"
        assert (
            merge_result["output"]["input_count"] == 2
        )  # Only branches A and C should execute

        # Verify only expected processors executed
        assert "processor_a" in results
        assert "processor_b" not in results  # Should be skipped
        assert "processor_c" in results

        # Verify merge stats
        assert merge_result["merge_stats"]["valid_inputs"] == 2
        assert merge_result["merge_stats"]["method"] == "adaptive"

    def test_conditional_aware_merge_with_context(self):
        """Test conditional-aware merge strategy with execution context."""
        workflow = WorkflowBuilder()

        # Simple data source
        workflow.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 'test', 'priority': 'high'}"},
        )

        # Three processors
        workflow.add_node(
            "PythonCodeNode",
            "proc1",
            {"code": "result = {'processor': 1, 'result': 'proc1_result'}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "proc2",
            {"code": "result = {'processor': 2, 'result': 'proc2_result'}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "proc3",
            {"code": "result = {'processor': 3, 'result': 'proc3_result'}"},
        )

        # Conditional-aware merge with execution context
        workflow.add_node(
            "IntelligentMergeNode",
            "conditional_merge",
            {
                "method": "conditional_aware",
                "conditional_context": {
                    "available_branches": ["1", "3"],  # Only proc1 and proc3 available
                    "skipped_branches": ["2"],  # proc2 skipped
                    "execution_confidence": 0.85,
                },
            },
        )

        # Connect workflow
        workflow.add_connection("source", "result", "proc1", "input_data")
        workflow.add_connection("source", "result", "proc2", "input_data")
        workflow.add_connection("source", "result", "proc3", "input_data")

        workflow.add_connection("proc1", "result", "conditional_merge", "input1")
        workflow.add_connection("proc2", "result", "conditional_merge", "input2")
        workflow.add_connection("proc3", "result", "conditional_merge", "input3")

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert "conditional_merge" in results
        merge_result = results["conditional_merge"]

        assert merge_result["output"]["strategy"] == "conditional_aware"
        assert merge_result["output"]["sub_strategy"] == "combine"  # High confidence
        assert merge_result["output"]["execution_confidence"] == 0.85
        assert merge_result["output"]["inputs_processed"] == 2  # Only proc1 and proc3
        assert merge_result["output"]["inputs_skipped"] == 1  # proc2 filtered out

    def test_priority_merge_with_weighted_inputs(self):
        """Test priority merge with weighted priority inputs."""
        workflow = WorkflowBuilder()

        # Create processors that output priority data
        workflow.add_node(
            "PythonCodeNode",
            "high_priority",
            {
                "code": """
result = {
    'data': 'critical_alert',
    'priority': 0.9,
    'source': 'security_system'
}
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "medium_priority",
            {
                "code": """
result = {
    'data': 'warning_alert',
    'priority': 0.6,
    'source': 'monitoring_system'
}
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "low_priority",
            {
                "code": """
result = {
    'data': 'info_alert',
    'priority': 0.3,
    'source': 'logging_system'
}
"""
            },
        )

        # Priority merge node
        workflow.add_node(
            "IntelligentMergeNode",
            "priority_merge",
            {
                "method": "priority_merge",
                "priority_threshold": 0.5,  # Only medium and high priority
            },
        )

        # Connect all to merge
        workflow.add_connection("high_priority", "result", "priority_merge", "input1")
        workflow.add_connection("medium_priority", "result", "priority_merge", "input2")
        workflow.add_connection("low_priority", "result", "priority_merge", "input3")

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert "priority_merge" in results
        merge_result = results["priority_merge"]

        assert (
            merge_result["output"]["priorities_processed"] == 2
        )  # High and medium only
        assert merge_result["output"]["highest_priority"] == 0.9
        assert len(merge_result["output"]["priorities_used"]) == 2

        # Should have filtered out low priority input
        assert 0.3 not in merge_result["output"]["priorities_used"]
        assert 0.9 in merge_result["output"]["priorities_used"]
        assert 0.6 in merge_result["output"]["priorities_used"]

    def test_consensus_merge_for_decision_making(self):
        """Test consensus merge for decision-making scenarios."""
        workflow = WorkflowBuilder()

        # Decision nodes
        workflow.add_node(
            "PythonCodeNode",
            "reviewer_1",
            {
                "code": "result = {'decision': 'approve', 'confidence': 0.8, 'reviewer': 'alice'}"
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "reviewer_2",
            {
                "code": "result = {'decision': 'approve', 'confidence': 0.9, 'reviewer': 'bob'}"
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "reviewer_3",
            {
                "code": "result = {'decision': 'reject', 'confidence': 0.7, 'reviewer': 'charlie'}"
            },
        )

        # Consensus merge
        workflow.add_node(
            "IntelligentMergeNode",
            "consensus_decision",
            {"method": "consensus", "consensus_threshold": 2},
        )

        # Connect reviewers to consensus
        workflow.add_connection("reviewer_1", "result", "consensus_decision", "input1")
        workflow.add_connection("reviewer_2", "result", "consensus_decision", "input2")
        workflow.add_connection("reviewer_3", "result", "consensus_decision", "input3")

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify consensus results
        assert "consensus_decision" in results
        consensus_result = results["consensus_decision"]

        assert consensus_result["output"]["consensus"] is True
        assert consensus_result["output"]["result"] == "approve"  # Majority decision
        assert consensus_result["output"]["vote_count"]["approve"] == 2
        assert consensus_result["output"]["vote_count"]["reject"] == 1
        assert consensus_result["output"]["confidence"] == 2 / 3  # 2 out of 3 votes
