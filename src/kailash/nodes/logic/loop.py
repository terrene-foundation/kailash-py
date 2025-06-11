"""Loop control node for creating cycles in workflows."""

from typing import Any

from kailash.nodes.base import Node, NodeParameter


class LoopNode(Node):
    """Node that enables loop control in workflows.

    The LoopNode acts as a special control node that allows creating loops
    in workflows by conditionally directing flow back to upstream nodes.
    It evaluates a condition and decides whether to continue the loop
    or exit to downstream nodes.

    Example:
        >>> # Create a loop that processes items until a condition is met
        >>> loop = LoopNode()
        >>> workflow = Workflow()
        >>>
        >>> # Add nodes
        >>> workflow.add_node("data_processor", DataProcessorNode())
        >>> workflow.add_node("loop_control", loop)
        >>> workflow.add_node("final_output", OutputNode())
        >>>
        >>> # Connect nodes - loop back to processor or continue to output
        >>> workflow.connect("data_processor", "loop_control")
        >>> workflow.connect("loop_control", "data_processor", condition="continue")
        >>> workflow.connect("loop_control", "final_output", condition="exit")
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define loop control parameters."""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=dict,
                required=False,
                default={},
                description="Data to evaluate for loop condition",
            ),
            "condition": NodeParameter(
                name="condition",
                type=str,
                required=True,
                default="counter",
                description="Loop condition type: 'counter', 'expression', 'callback'",
            ),
            "max_iterations": NodeParameter(
                name="max_iterations",
                type=int,
                required=False,
                default=100,
                description="Maximum iterations (for counter mode)",
            ),
            "expression": NodeParameter(
                name="expression",
                type=str,
                required=False,
                description="Boolean expression to evaluate (for expression mode)",
            ),
            "exit_on": NodeParameter(
                name="exit_on",
                type=bool,
                required=False,
                default=True,
                description="Exit when condition evaluates to this value",
            ),
            "loop_state": NodeParameter(
                name="loop_state",
                type=dict,
                required=False,
                default={},
                description="State data to maintain across iterations",
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Execute loop control logic."""
        input_data = kwargs.get("input_data")
        condition_type = kwargs.get("condition", "counter")
        max_iterations = kwargs.get("max_iterations", 100)
        expression = kwargs.get("expression")
        exit_on = kwargs.get("exit_on", True)
        loop_state = kwargs.get("loop_state", {})

        # Update iteration counter
        current_iteration = loop_state.get("iteration", 0) + 1
        loop_state["iteration"] = current_iteration

        # Evaluate condition based on type
        should_exit = False

        if condition_type == "counter":
            should_exit = current_iteration >= max_iterations

        elif condition_type == "expression" and expression:
            # Create evaluation context
            eval_context = {
                "data": input_data,
                "iteration": current_iteration,
                "state": loop_state,
            }
            try:
                # Safely evaluate expression
                result = eval(expression, {"__builtins__": {}}, eval_context)
                should_exit = bool(result) == exit_on
            except Exception as e:
                self.logger.warning(f"Expression evaluation failed: {e}")
                should_exit = True

        elif condition_type == "callback":
            # Check if input_data has a specific flag or condition
            if isinstance(input_data, dict):
                should_exit = input_data.get("exit_loop", False)
            else:
                should_exit = False

        # Return results with loop metadata
        return {
            "data": input_data,
            "should_exit": should_exit,
            "continue_loop": not should_exit,
            "iteration": current_iteration,
            "loop_state": loop_state,
            "_control": {
                "type": "loop",
                "direction": "exit" if should_exit else "continue",
            },
        }

    def get_output_schema(self) -> dict[str, Any] | None:
        """Define output schema for loop control."""
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": ["object", "array", "string", "number", "boolean", "null"]
                },
                "should_exit": {"type": "boolean"},
                "continue_loop": {"type": "boolean"},
                "iteration": {"type": "integer"},
                "loop_state": {"type": "object"},
                "_control": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "const": "loop"},
                        "direction": {"type": "string", "enum": ["exit", "continue"]},
                    },
                },
            },
            "required": ["data", "should_exit", "continue_loop", "iteration"],
        }
