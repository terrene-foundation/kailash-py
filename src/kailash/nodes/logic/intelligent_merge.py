"""Intelligent merge node for handling conditional inputs.

This module provides an enhanced MergeNode that intelligently handles
partial inputs from conditional branches in workflows.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from kailash.nodes import Node, NodeParameter
from kailash.nodes.base import register_node

logger = logging.getLogger(__name__)


@register_node()
class IntelligentMergeNode(Node):
    """Enhanced merge node with intelligent handling of conditional inputs.

    This node extends the basic MergeNode functionality with:
    - Intelligent handling of None/missing inputs from skipped branches
    - Multiple merge strategies (combine, first_available, weighted)
    - Timeout support for async inputs
    - Fallback handling for missing data

    Strategies:
    - combine: Merge all non-None inputs into a single output
    - first_available: Return the first non-None input
    - weighted: Merge inputs with weighted scoring
    - fallback: Try inputs in order until one succeeds
    - adaptive: Automatically choose best strategy based on input patterns
    - consensus: Use majority consensus for decision-making
    - priority_merge: Merge based on priority levels
    - conditional_aware: Conditional execution optimized merge
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "method": NodeParameter(
                name="method",
                type=str,
                required=False,
                default="combine",
                description="Merge strategy: combine, first_available, weighted, fallback, adaptive, consensus, priority_merge, conditional_aware",
            ),
            "handle_none": NodeParameter(
                name="handle_none",
                type=bool,
                required=False,
                default=True,
                description="Whether to intelligently handle None inputs",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=float,
                required=False,
                default=None,
                description="Timeout for waiting on async inputs",
            ),
            "priority_threshold": NodeParameter(
                name="priority_threshold",
                type=float,
                required=False,
                default=0.5,
                description="Minimum priority threshold for priority_merge strategy",
            ),
            "consensus_threshold": NodeParameter(
                name="consensus_threshold",
                type=int,
                required=False,
                default=2,
                description="Minimum number of inputs needed for consensus strategy",
            ),
            "conditional_context": NodeParameter(
                name="conditional_context",
                type=dict,
                required=False,
                default=None,
                description="Context from conditional execution for strategy optimization",
            ),
            # Dynamic inputs - up to 10 for flexibility
            **{
                f"input{i}": NodeParameter(
                    name=f"input{i}",
                    type=Any,
                    required=False,
                    default=None,
                    description=f"Input source {i}",
                )
                for i in range(1, 11)
            },
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output schema."""
        return {
            "output": NodeParameter(
                name="output", type=Any, description="Merged result based on strategy"
            ),
            "merge_stats": NodeParameter(
                name="merge_stats",
                type=dict,
                description="Statistics about the merge operation",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute intelligent merge operation."""
        method = kwargs.get("method", "combine")
        handle_none = kwargs.get("handle_none", True)
        timeout = kwargs.get("timeout")

        # Collect all non-parameter inputs
        inputs = {}
        for key, value in kwargs.items():
            if key.startswith("input") and key[5:].isdigit():
                if handle_none and value is not None:
                    inputs[key] = value
                elif not handle_none:
                    inputs[key] = value

        logger.debug(f"Intelligent merge with method={method}, inputs={len(inputs)}")

        # Execute merge based on strategy
        if method == "combine":
            result = self._merge_combine(inputs)
        elif method == "first_available":
            result = self._merge_first_available(inputs)
        elif method == "weighted":
            result = self._merge_weighted(inputs)
        elif method == "fallback":
            result = self._merge_fallback(inputs)
        elif method == "adaptive":
            result = self._merge_adaptive(inputs, kwargs)
        elif method == "consensus":
            result = self._merge_consensus(inputs, kwargs.get("consensus_threshold", 2))
        elif method == "priority_merge":
            result = self._merge_priority(inputs, kwargs.get("priority_threshold", 0.5))
        elif method == "conditional_aware":
            result = self._merge_conditional_aware(
                inputs, kwargs.get("conditional_context")
            )
        else:
            raise ValueError(f"Unknown merge method: {method}")

        # Collect statistics
        stats = {
            "method": method,
            "total_inputs": len(kwargs) - 3,  # Exclude method, handle_none, timeout
            "valid_inputs": len(inputs),
            "skipped_inputs": len(kwargs) - 3 - len(inputs),
        }

        return {"output": result, "merge_stats": stats}

    def _merge_combine(self, inputs: Dict[str, Any]) -> Any:
        """Combine all inputs into a single structure."""
        if not inputs:
            return {}

        # If all inputs are dicts, merge them
        if all(isinstance(v, dict) for v in inputs.values()):
            result = {}
            for input_dict in inputs.values():
                result.update(input_dict)
            return result

        # If all inputs are lists, concatenate them
        if all(isinstance(v, list) for v in inputs.values()):
            result = []
            for input_list in inputs.values():
                result.extend(input_list)
            return result

        # Mixed types - return as dict
        return inputs

    def _merge_first_available(self, inputs: Dict[str, Any]) -> Any:
        """Return the first available (non-None) input."""
        if not inputs:
            return None

        # Sort by input number to maintain order
        sorted_keys = sorted(inputs.keys(), key=lambda x: int(x[5:]))
        for key in sorted_keys:
            if inputs[key] is not None:
                return inputs[key]

        return None

    def _merge_weighted(self, inputs: Dict[str, Any]) -> Any:
        """Merge inputs with weighted scoring."""
        if not inputs:
            return {"score": 0, "components": 0}

        scores = []
        weights = []
        components = []

        for key, value in inputs.items():
            if isinstance(value, dict):
                if "score" in value and "weight" in value:
                    scores.append(value["score"])
                    weights.append(value["weight"])
                    components.append(value)

        if not scores:
            return {"score": 0, "components": 0}

        # Calculate weighted average
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        total_weight = sum(weights)

        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = sum(scores) / len(scores)

        return {
            "score": final_score,
            "components": len(components),
            "details": components,
        }

    def _merge_fallback(self, inputs: Dict[str, Any]) -> Any:
        """Try inputs in order until one succeeds."""
        if not inputs:
            return {"source": "none", "data": None}

        # Sort by input number to maintain order
        sorted_keys = sorted(inputs.keys(), key=lambda x: int(x[5:]))

        for key in sorted_keys:
            value = inputs[key]
            if value is not None:
                # Check if it's a valid response
                if isinstance(value, dict):
                    if value.get("available", True) or value.get("data") is not None:
                        return value
                else:
                    return {"source": key, "data": value}

        # No valid input found
        return {"source": "fallback_failed", "data": None}

    def _merge_adaptive(self, inputs: Dict[str, Any], kwargs: Dict[str, Any]) -> Any:
        """Automatically choose the best merge strategy based on input patterns."""
        if not inputs:
            return {"strategy_used": "adaptive", "result": None, "reason": "no_inputs"}

        input_values = list(inputs.values())

        # Analyze input patterns to choose best strategy
        if len(inputs) == 1:
            # Single input - return directly
            strategy_used = "first_available"
            result = self._merge_first_available(inputs)
        elif all(isinstance(v, dict) and "priority" in v for v in input_values):
            # All inputs have priority - use priority merge
            strategy_used = "priority_merge"
            result = self._merge_priority(inputs, kwargs.get("priority_threshold", 0.5))
        elif all(
            isinstance(v, dict) and "score" in v and "weight" in v for v in input_values
        ):
            # All inputs have scores and weights - use weighted merge
            strategy_used = "weighted"
            result = self._merge_weighted(inputs)
        elif len(inputs) >= kwargs.get("consensus_threshold", 2):
            # Multiple inputs - try consensus
            strategy_used = "consensus"
            result = self._merge_consensus(inputs, kwargs.get("consensus_threshold", 2))
        else:
            # Default to combine
            strategy_used = "combine"
            result = self._merge_combine(inputs)

        return {
            "strategy_used": strategy_used,
            "result": result,
            "input_count": len(inputs),
            "adaptation_reason": f"Selected {strategy_used} based on input analysis",
        }

    def _merge_consensus(self, inputs: Dict[str, Any], threshold: int) -> Any:
        """Use majority consensus for decision-making."""
        if len(inputs) < threshold:
            return {
                "consensus": False,
                "result": None,
                "reason": f"Insufficient inputs ({len(inputs)} < {threshold})",
            }

        # For boolean decisions
        if all(isinstance(v, bool) for v in inputs.values()):
            true_count = sum(1 for v in inputs.values() if v)
            false_count = len(inputs) - true_count
            consensus_result = true_count > false_count

            return {
                "consensus": True,
                "result": consensus_result,
                "vote_count": {"true": true_count, "false": false_count},
                "confidence": max(true_count, false_count) / len(inputs),
            }

        # For dict inputs with decisions
        if all(isinstance(v, dict) and "decision" in v for v in inputs.values()):
            decisions = [v["decision"] for v in inputs.values()]
            decision_counts = {}
            for decision in decisions:
                decision_counts[decision] = decision_counts.get(decision, 0) + 1

            majority_decision = max(decision_counts, key=decision_counts.get)
            majority_count = decision_counts[majority_decision]

            return {
                "consensus": majority_count >= threshold,
                "result": majority_decision,
                "vote_count": decision_counts,
                "confidence": majority_count / len(inputs),
            }

        # For other types, use most common value
        value_counts = {}
        for value in inputs.values():
            value_str = str(value)
            value_counts[value_str] = value_counts.get(value_str, 0) + 1

        if value_counts:
            most_common = max(value_counts, key=value_counts.get)
            most_common_count = value_counts[most_common]

            # Find the actual value (not string representation)
            consensus_value = None
            for value in inputs.values():
                if str(value) == most_common:
                    consensus_value = value
                    break

            return {
                "consensus": most_common_count >= threshold,
                "result": consensus_value,
                "vote_count": value_counts,
                "confidence": most_common_count / len(inputs),
            }

        return {"consensus": False, "result": None, "reason": "no_valid_inputs"}

    def _merge_priority(self, inputs: Dict[str, Any], threshold: float) -> Any:
        """Merge inputs based on priority levels."""
        if not inputs:
            return {"result": None, "priorities_processed": 0}

        prioritized_inputs = []

        for key, value in inputs.items():
            if isinstance(value, dict) and "priority" in value:
                priority = value["priority"]
                if priority >= threshold:
                    prioritized_inputs.append((priority, key, value))
            else:
                # Default priority for non-dict inputs
                prioritized_inputs.append((1.0, key, value))

        if not prioritized_inputs:
            return {
                "result": None,
                "priorities_processed": 0,
                "reason": "no_inputs_above_threshold",
            }

        # Sort by priority (highest first)
        prioritized_inputs.sort(key=lambda x: x[0], reverse=True)

        # Merge high-priority inputs
        high_priority_data = []
        priorities_used = []

        for priority, key, value in prioritized_inputs:
            high_priority_data.append(value)
            priorities_used.append(priority)

        # Combine high-priority inputs
        if len(high_priority_data) == 1:
            result = high_priority_data[0]
        else:
            # Create temporary inputs dict for combining
            temp_inputs = {
                f"input{i}": data for i, data in enumerate(high_priority_data)
            }
            result = self._merge_combine(temp_inputs)

        return {
            "result": result,
            "priorities_processed": len(high_priority_data),
            "priorities_used": priorities_used,
            "highest_priority": max(priorities_used) if priorities_used else 0,
        }

    def _merge_conditional_aware(
        self, inputs: Dict[str, Any], conditional_context: Optional[Dict[str, Any]]
    ) -> Any:
        """Conditional execution optimized merge strategy."""
        if not inputs:
            return {
                "result": None,
                "strategy": "conditional_aware",
                "inputs_processed": 0,
                "conditional_context": conditional_context,
            }

        # Use conditional context to optimize merge
        if conditional_context:
            available_branches = conditional_context.get("available_branches", [])
            skipped_branches = conditional_context.get("skipped_branches", [])
            execution_confidence = conditional_context.get("execution_confidence", 1.0)

            # Filter inputs based on conditional context
            filtered_inputs = {}
            for key, value in inputs.items():
                # Check if this input corresponds to an available branch
                input_branch = key.replace("input", "")
                if not available_branches or input_branch in available_branches:
                    filtered_inputs[key] = value

            if not filtered_inputs:
                return {
                    "result": None,
                    "strategy": "conditional_aware",
                    "reason": "all_inputs_from_skipped_branches",
                    "skipped_branches": skipped_branches,
                    "inputs_processed": 0,
                }

            # Choose merge strategy based on execution confidence
            if execution_confidence >= 0.8:
                # High confidence - use standard combine
                merge_result = self._merge_combine(filtered_inputs)
                strategy_used = "combine"
            elif execution_confidence >= 0.5:
                # Medium confidence - use adaptive merge
                temp_kwargs = {"consensus_threshold": 2, "priority_threshold": 0.5}
                adaptive_result = self._merge_adaptive(filtered_inputs, temp_kwargs)
                merge_result = adaptive_result["result"]
                strategy_used = f"adaptive->{adaptive_result['strategy_used']}"
            else:
                # Low confidence - use first available
                merge_result = self._merge_first_available(filtered_inputs)
                strategy_used = "first_available"

            return {
                "result": merge_result,
                "strategy": "conditional_aware",
                "sub_strategy": strategy_used,
                "execution_confidence": execution_confidence,
                "available_branches": available_branches,
                "inputs_processed": len(filtered_inputs),
                "inputs_skipped": len(inputs) - len(filtered_inputs),
            }
        else:
            # No conditional context - fall back to adaptive merge
            logger.debug(
                "No conditional context provided, falling back to adaptive merge"
            )
            temp_kwargs = {"consensus_threshold": 2, "priority_threshold": 0.5}
            adaptive_result = self._merge_adaptive(inputs, temp_kwargs)

            return {
                "result": adaptive_result["result"],
                "strategy": "conditional_aware",
                "sub_strategy": f"fallback->{adaptive_result['strategy_used']}",
                "reason": "no_conditional_context",
                "inputs_processed": len(inputs),
            }
