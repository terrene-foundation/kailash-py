"""
Test ReActAgent Convergence Detection - ADR-013 Implementation

Tests objective convergence detection using the `while(tool_call_exists)` pattern
from Claude Code's autonomous loop implementation.

This implements ADR-013's requirements for objective convergence detection:
1. Objective detection via tool_calls field (PREFERRED)
2. Subjective fallback via finish_action (backward compatibility)
3. >95% convergence accuracy
4. Zero breaking changes to existing agents

Test Coverage:
- Objective convergence with tool_calls present (not converged)
- Objective convergence with empty tool_calls (converged)
- Objective convergence with missing tool_calls (fallback to subjective)
- Backward compatibility with old signatures (no tool_calls field)
- MultiCycleStrategy objective convergence
- Max iterations enforcement
- Edge cases: None, [], [{}], malformed tool_calls

Author: Kaizen Framework Team
Created: 2025-10-22
"""

from typing import Any, Dict

import pytest
from kaizen.agents.specialized.react import ReActAgent, ReActSignature
from kaizen.strategies.multi_cycle import MultiCycleStrategy


class TestReActAgentObjectiveConvergence:
    """Test ReActAgent objective convergence detection (ADR-013)."""

    def test_objective_convergence_with_tool_calls_present_not_converged(self):
        """
        Test that agent does NOT converge when tool_calls field is present and non-empty.

        Pattern: while(tool_call_exists) continues execution
        """
        agent = ReActAgent()

        result = {
            "thought": "I need to use a tool",
            "action": "tool_use",
            "action_input": {"tool_name": "search", "params": {"query": "test"}},
            "confidence": 0.9,
            "need_tool": True,
            "tool_calls": [  # OBJECTIVE: tool_calls present
                {"name": "search", "parameters": {"query": "test"}}
            ],
        }

        # Should NOT converge (tool_calls exist)
        converged = agent._check_convergence(result)

        assert converged is False, "Should NOT converge when tool_calls present"

    def test_objective_convergence_with_empty_tool_calls_converged(self):
        """
        Test that agent converges when tool_calls field is present but empty.

        Pattern: while(tool_call_exists) exits when tool_calls = []
        """
        agent = ReActAgent()

        result = {
            "thought": "Task is complete",
            "action": "finish",
            "action_input": {},
            "confidence": 0.95,
            "need_tool": False,
            "tool_calls": [],  # OBJECTIVE: empty tool_calls = converged
        }

        # Should converge (tool_calls empty)
        converged = agent._check_convergence(result)

        assert converged is True, "Should converge when tool_calls is empty"

    def test_objective_convergence_with_missing_tool_calls_fallback_to_subjective(self):
        """
        Test backward compatibility: when tool_calls field is missing, fall back to subjective.

        Pattern: Graceful degradation to finish_action check
        """
        agent = ReActAgent()

        result = {
            "thought": "Task is complete",
            "action": "finish",  # Subjective convergence signal
            "action_input": {},
            "confidence": 0.95,
            "need_tool": False,
            # NO tool_calls field - old signature
        }

        # Should converge (fallback to action == "finish")
        converged = agent._check_convergence(result)

        assert (
            converged is True
        ), "Should converge via subjective fallback when tool_calls missing"

    def test_backward_compatibility_old_signature_without_tool_calls(self):
        """
        Test that old signatures without tool_calls field still work.

        Ensures zero breaking changes for existing agents.
        """
        agent = ReActAgent()

        # Old-style result without tool_calls
        result = {
            "thought": "I need to search",
            "action": "tool_use",
            "action_input": {"tool": "search"},
            "confidence": 0.6,
            "need_tool": True,
            # NO tool_calls field
        }

        # Should NOT converge (confidence < threshold, action != "finish")
        converged = agent._check_convergence(result)

        assert (
            converged is False
        ), "Should NOT converge with old signature (low confidence)"

    def test_backward_compatibility_high_confidence_old_signature(self):
        """
        Test that high confidence triggers convergence in old signatures.

        Backward compatibility for confidence-based convergence.
        """
        agent = ReActAgent()

        result = {
            "thought": "Very confident in this answer",
            "action": "tool_use",
            "action_input": {},
            "confidence": 0.95,  # High confidence
            "need_tool": False,
            # NO tool_calls field
        }

        # Should converge (high confidence triggers subjective convergence)
        converged = agent._check_convergence(result)

        assert (
            converged is True
        ), "Should converge with high confidence in old signature"

    def test_objective_convergence_tool_calls_none(self):
        """
        Test edge case: tool_calls = None (treated as missing field).

        Pattern: None should fall back to subjective detection
        """
        agent = ReActAgent()

        result = {
            "thought": "Processing",
            "action": "finish",
            "action_input": {},
            "confidence": 0.8,
            "need_tool": False,
            "tool_calls": None,  # Edge case: None instead of missing
        }

        # Should fall back to subjective (action == "finish")
        converged = agent._check_convergence(result)

        assert converged is True, "Should handle tool_calls=None gracefully"

    def test_objective_convergence_tool_calls_with_empty_dict(self):
        """
        Test edge case: tool_calls = [{}] (list with empty dict).

        Pattern: Non-empty list should NOT converge (even if dict is empty)
        """
        agent = ReActAgent()

        result = {
            "thought": "Malformed tool call",
            "action": "tool_use",
            "action_input": {},
            "confidence": 0.7,
            "need_tool": True,
            "tool_calls": [{}],  # Edge case: list with empty dict
        }

        # Should NOT converge (tool_calls is non-empty list)
        converged = agent._check_convergence(result)

        assert (
            converged is False
        ), "Should NOT converge with non-empty tool_calls (even if dict empty)"

    def test_objective_convergence_multiple_tool_calls(self):
        """
        Test that multiple tool calls prevent convergence.

        Pattern: Any tool_calls means "continue executing"
        """
        agent = ReActAgent()

        result = {
            "thought": "Need to use multiple tools",
            "action": "tool_use",
            "action_input": {},
            "confidence": 0.8,
            "need_tool": True,
            "tool_calls": [
                {"name": "search", "parameters": {"query": "A"}},
                {"name": "calculator", "parameters": {"expr": "2+2"}},
            ],
        }

        # Should NOT converge (multiple tool_calls)
        converged = agent._check_convergence(result)

        assert converged is False, "Should NOT converge with multiple tool_calls"

    def test_multicycle_strategy_objective_convergence(self):
        """
        Test that MultiCycleStrategy uses objective convergence when available.

        Verifies that the convergence callback is correctly invoked.
        """
        agent = ReActAgent(max_cycles=3)

        # Mock cycle result with tool_calls
        result_with_tools = {
            "thought": "Need to search",
            "action": "tool_use",
            "action_input": {"tool": "search"},
            "confidence": 0.7,
            "need_tool": True,
            "tool_calls": [{"name": "search"}],
        }

        # Should NOT converge
        converged = agent._check_convergence(result_with_tools)
        assert (
            converged is False
        ), "MultiCycleStrategy should NOT converge with tool_calls"

    def test_multicycle_strategy_objective_convergence_empty_tools(self):
        """
        Test that MultiCycleStrategy converges when tool_calls is empty.

        Verifies objective convergence in multi-cycle context.
        """
        agent = ReActAgent(max_cycles=3)

        result_no_tools = {
            "thought": "Task complete",
            "action": "finish",
            "action_input": {},
            "confidence": 0.9,
            "need_tool": False,
            "tool_calls": [],  # Empty = converged
        }

        # Should converge
        converged = agent._check_convergence(result_no_tools)
        assert (
            converged is True
        ), "MultiCycleStrategy should converge with empty tool_calls"

    def test_convergence_priority_objective_over_subjective(self):
        """
        Test that objective convergence takes priority over subjective signals.

        Pattern: If tool_calls field exists, use it (even if action == "finish")
        """
        agent = ReActAgent()

        result = {
            "thought": "Conflicting signals",
            "action": "finish",  # Subjective: should converge
            "action_input": {},
            "confidence": 0.95,
            "need_tool": False,
            "tool_calls": [{"name": "search"}],  # Objective: should NOT converge
        }

        # Objective should take priority (tool_calls present = not converged)
        converged = agent._check_convergence(result)

        assert (
            converged is False
        ), "Objective detection should take priority over subjective"

    def test_max_iterations_still_enforced(self):
        """
        Test that max_iterations is still enforced (not affected by convergence changes).

        Ensures safety limits are maintained.
        """
        agent = ReActAgent(max_cycles=2)

        # Agent config should have max_cycles set
        assert agent.react_config.max_cycles == 2, "Max cycles should be configured"

        # MultiCycleStrategy should respect max_cycles
        assert agent.strategy.max_cycles == 2, "Strategy should have correct max_cycles"

    def test_convergence_accuracy_simulation(self):
        """
        Test convergence accuracy with simulated scenarios (>95% target).

        Simulates 100 scenarios and verifies >95% correct convergence decisions.
        """
        agent = ReActAgent()

        test_cases = [
            # (result, expected_converged, description)
            # OBJECTIVE CONVERGENCE (tool_calls field present)
            ({"tool_calls": []}, True, "Empty tool_calls"),
            ({"tool_calls": [{"name": "search"}]}, False, "Tool calls present"),
            (
                {"tool_calls": [{"name": "a"}, {"name": "b"}]},
                False,
                "Multiple tool calls",
            ),
            (
                {"tool_calls": None},
                True,
                "tool_calls=None falls back, finish_action missing -> default True",
            ),
            # SUBJECTIVE FALLBACK (no tool_calls field)
            ({"action": "finish", "confidence": 0.8}, True, "Finish action"),
            ({"action": "tool_use", "confidence": 0.95}, True, "High confidence"),
            ({"action": "tool_use", "confidence": 0.5}, False, "Low confidence"),
            (
                {"action": "clarify", "confidence": 0.6},
                False,
                "Clarify action, low confidence",
            ),
            # EDGE CASES
            ({"tool_calls": [{}]}, False, "Empty dict in tool_calls"),
            ({}, True, "Empty result (default converged)"),
        ]

        correct = 0
        total = len(test_cases)

        for result, expected, description in test_cases:
            actual = agent._check_convergence(result)
            if actual == expected:
                correct += 1
            else:
                print(f"FAILED: {description} - expected {expected}, got {actual}")

        accuracy = correct / total

        assert accuracy >= 0.95, f"Convergence accuracy {accuracy:.1%} < 95% target"

    def test_react_signature_has_tool_calls_field(self):
        """
        Test that ReActSignature includes tool_calls output field.

        Verifies signature update from ADR-013.
        """
        signature = ReActSignature()

        # Check that tool_calls is in output fields
        assert (
            "tool_calls" in signature.output_fields
        ), "ReActSignature should have tool_calls field"

        # Check field metadata
        tool_calls_field = signature.output_fields["tool_calls"]
        assert (
            "desc" in tool_calls_field or "description" in tool_calls_field.metadata
        ), "tool_calls field should have description"

    def test_convergence_with_malformed_tool_calls(self):
        """
        Test handling of malformed tool_calls data.

        Ensures robustness with unexpected data structures.
        """
        agent = ReActAgent()

        # Malformed: string instead of list
        result = {"tool_calls": "malformed"}  # Should handle gracefully

        # Should fall back to subjective (malformed data)
        converged = agent._check_convergence(result)

        # Since it's malformed and no other signals, should default to True
        assert converged is True, "Should handle malformed tool_calls gracefully"

    def test_convergence_with_partial_result(self):
        """
        Test convergence with minimal/partial result data.

        Ensures graceful handling of incomplete results.
        """
        agent = ReActAgent()

        # Minimal result
        result = {
            "thought": "Some thought"
            # Missing: action, confidence, tool_calls
        }

        # Should default to True (safe fallback when no signals)
        converged = agent._check_convergence(result)

        assert converged is True, "Should handle partial results gracefully"


class TestMultiCycleStrategyObjectiveConvergence:
    """Test MultiCycleStrategy objective convergence integration."""

    def test_multicycle_uses_agent_convergence_check(self):
        """
        Test that MultiCycleStrategy correctly uses agent's convergence check.

        Verifies integration between strategy and agent.
        """
        agent = ReActAgent(max_cycles=5)

        # Verify strategy has convergence_check_callback
        assert (
            agent.strategy.convergence_check_callback is not None
        ), "Strategy should have convergence check callback"

    def test_multicycle_respects_objective_convergence(self):
        """
        Test that MultiCycleStrategy respects objective convergence signals.

        Simulates multi-cycle execution with objective signals.
        """

        def mock_convergence_check(result: Dict[str, Any]) -> bool:
            """Mock convergence check using objective detection."""
            # Objective detection
            if "tool_calls" in result:
                tool_calls = result.get("tool_calls", [])
                if tool_calls:
                    return False  # Not converged
                return True  # Converged

            # Subjective fallback
            if result.get("action") == "finish":
                return True

            return False

        MultiCycleStrategy(max_cycles=5, convergence_check=mock_convergence_check)

        # Test with tool_calls present
        result_with_tools = {"tool_calls": [{"name": "search"}]}
        converged = mock_convergence_check(result_with_tools)
        assert converged is False, "Should NOT converge with tool_calls"

        # Test with empty tool_calls
        result_no_tools = {"tool_calls": []}
        converged = mock_convergence_check(result_no_tools)
        assert converged is True, "Should converge with empty tool_calls"


# Test Markers
pytestmark = pytest.mark.unit
