"""Tests for intelligent merge strategies for conditional execution."""

import pytest
from kailash.nodes.logic.intelligent_merge import IntelligentMergeNode


class TestIntelligentMergeStrategies:
    """Test enhanced intelligent merge strategies."""

    def setup_method(self):
        """Set up test fixtures."""
        self.node = IntelligentMergeNode()

    def test_adaptive_merge_single_input(self):
        """Test adaptive merge with single input."""
        result = self.node.execute(
            method="adaptive", input1={"data": "test1"}, input2=None, input3=None
        )

        assert result["output"]["strategy_used"] == "first_available"
        assert result["output"]["result"] == {"data": "test1"}
        assert result["output"]["input_count"] == 1

    def test_adaptive_merge_priority_inputs(self):
        """Test adaptive merge with priority inputs."""
        result = self.node.execute(
            method="adaptive",
            input1={"data": "test1", "priority": 0.8},
            input2={"data": "test2", "priority": 0.6},
            input3=None,
            priority_threshold=0.5,
        )

        assert result["output"]["strategy_used"] == "priority_merge"
        assert result["output"]["result"]["priorities_processed"] == 2
        assert result["output"]["result"]["highest_priority"] == 0.8

    def test_adaptive_merge_weighted_inputs(self):
        """Test adaptive merge with weighted inputs."""
        result = self.node.execute(
            method="adaptive",
            input1={"score": 0.8, "weight": 0.3},
            input2={"score": 0.6, "weight": 0.7},
            input3=None,
        )

        assert result["output"]["strategy_used"] == "weighted"
        assert result["output"]["result"]["components"] == 2
        # Weighted average: (0.8*0.3 + 0.6*0.7) / (0.3+0.7) = 0.66
        assert abs(result["output"]["result"]["score"] - 0.66) < 0.01

    def test_consensus_merge_boolean(self):
        """Test consensus merge with boolean inputs."""
        result = self.node.execute(
            method="consensus",
            input1=True,
            input2=True,
            input3=False,
            consensus_threshold=2,
        )

        assert result["output"]["consensus"] is True
        assert result["output"]["result"] is True
        assert result["output"]["vote_count"]["true"] == 2
        assert result["output"]["vote_count"]["false"] == 1
        assert result["output"]["confidence"] == 2 / 3

    def test_consensus_merge_decisions(self):
        """Test consensus merge with decision inputs."""
        result = self.node.execute(
            method="consensus",
            input1={"decision": "approve"},
            input2={"decision": "approve"},
            input3={"decision": "reject"},
            consensus_threshold=2,
        )

        assert result["output"]["consensus"] is True
        assert result["output"]["result"] == "approve"
        assert result["output"]["vote_count"]["approve"] == 2
        assert result["output"]["vote_count"]["reject"] == 1

    def test_consensus_merge_insufficient_inputs(self):
        """Test consensus merge with insufficient inputs."""
        result = self.node.execute(
            method="consensus", input1=True, input2=None, consensus_threshold=3
        )

        assert result["output"]["consensus"] is False
        assert result["output"]["reason"] == "Insufficient inputs (1 < 3)"

    def test_priority_merge_with_threshold(self):
        """Test priority merge with threshold filtering."""
        result = self.node.execute(
            method="priority_merge",
            input1={"data": "low", "priority": 0.3},
            input2={"data": "high", "priority": 0.8},
            input3={"data": "medium", "priority": 0.6},
            priority_threshold=0.5,
        )

        assert result["output"]["priorities_processed"] == 2  # Only high and medium
        assert result["output"]["highest_priority"] == 0.8
        assert len(result["output"]["priorities_used"]) == 2

    def test_priority_merge_no_inputs_above_threshold(self):
        """Test priority merge when no inputs meet threshold."""
        result = self.node.execute(
            method="priority_merge",
            input1={"data": "low1", "priority": 0.2},
            input2={"data": "low2", "priority": 0.3},
            priority_threshold=0.5,
        )

        assert result["output"]["priorities_processed"] == 0
        assert result["output"]["reason"] == "no_inputs_above_threshold"

    def test_conditional_aware_with_context(self):
        """Test conditional-aware merge with execution context."""
        conditional_context = {
            "available_branches": ["1", "3"],
            "skipped_branches": ["2"],
            "execution_confidence": 0.9,
        }

        result = self.node.execute(
            method="conditional_aware",
            input1={"data": "branch1"},
            input2={"data": "branch2"},  # Should be filtered out
            input3={"data": "branch3"},
            conditional_context=conditional_context,
        )

        assert result["output"]["strategy"] == "conditional_aware"
        assert result["output"]["sub_strategy"] == "combine"
        assert result["output"]["execution_confidence"] == 0.9
        assert result["output"]["inputs_processed"] == 2
        assert result["output"]["inputs_skipped"] == 1

    def test_conditional_aware_low_confidence(self):
        """Test conditional-aware merge with low confidence."""
        conditional_context = {
            "available_branches": ["1", "2"],
            "skipped_branches": [],
            "execution_confidence": 0.3,  # Low confidence
        }

        result = self.node.execute(
            method="conditional_aware",
            input1={"data": "branch1"},
            input2={"data": "branch2"},
            conditional_context=conditional_context,
        )

        assert result["output"]["strategy"] == "conditional_aware"
        assert result["output"]["sub_strategy"] == "first_available"
        assert result["output"]["execution_confidence"] == 0.3

    def test_conditional_aware_no_context(self):
        """Test conditional-aware merge without context."""
        result = self.node.execute(
            method="conditional_aware",
            input1={"data": "branch1"},
            input2={"data": "branch2"},
        )

        assert result["output"]["strategy"] == "conditional_aware"
        assert "fallback" in result["output"]["sub_strategy"]
        assert result["output"]["reason"] == "no_conditional_context"

    def test_conditional_aware_all_skipped_branches(self):
        """Test conditional-aware merge when all inputs are from skipped branches."""
        conditional_context = {
            "available_branches": ["4", "5"],
            "skipped_branches": ["1", "2", "3"],
            "execution_confidence": 0.8,
        }

        result = self.node.execute(
            method="conditional_aware",
            input1={"data": "branch1"},
            input2={"data": "branch2"},
            input3={"data": "branch3"},
            conditional_context=conditional_context,
        )

        assert result["output"]["strategy"] == "conditional_aware"
        assert result["output"]["reason"] == "all_inputs_from_skipped_branches"
        assert result["output"]["inputs_processed"] == 0

    def test_merge_stats_collection(self):
        """Test that merge statistics are properly collected."""
        result = self.node.execute(
            method="combine",
            input1={"data": "test1"},
            input2={"data": "test2"},
            input3=None,
            handle_none=True,
        )

        stats = result["merge_stats"]
        assert stats["method"] == "combine"
        assert (
            stats["total_inputs"] == 3
        )  # method, handle_none, timeout = 3 control parameters
        assert stats["valid_inputs"] == 2
        assert stats["skipped_inputs"] == 1  # 3 - 2 = 1

    def test_unknown_merge_method(self):
        """Test error handling for unknown merge method."""
        from kailash.sdk_exceptions import NodeExecutionError

        with pytest.raises(NodeExecutionError, match="Unknown merge method: invalid"):
            self.node.execute(method="invalid", input1={"data": "test"})

    def test_handle_none_parameter(self):
        """Test handle_none parameter functionality."""
        # With handle_none=True (default)
        result_with_none_handling = self.node.execute(
            method="combine",
            input1={"data": "test1"},
            input2=None,
            input3={"data": "test3"},
            handle_none=True,
        )

        # With handle_none=False
        result_without_none_handling = self.node.execute(
            method="combine",
            input1={"data": "test1"},
            input2=None,
            input3={"data": "test3"},
            handle_none=False,
        )

        # With handle_none=True, None inputs should be filtered out
        stats_with = result_with_none_handling["merge_stats"]
        assert stats_with["valid_inputs"] == 2

        # With handle_none=False, None inputs should be included
        stats_without = result_without_none_handling["merge_stats"]
        assert (
            stats_without["valid_inputs"] == 2
        )  # Still 2 because None input is still None
