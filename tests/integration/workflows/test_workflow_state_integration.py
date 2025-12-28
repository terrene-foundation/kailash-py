"""
Tests for workflow integration with state management.

This module tests the integration between Workflow and the state management system,
ensuring that workflows correctly handle state throughout execution.
"""

from typing import Any

import pytest
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.workflow.graph import Workflow
from kailash.workflow.state import WorkflowStateWrapper
from pydantic import BaseModel


# Test state model
class WorkflowStateModel(BaseModel):
    """Test state model for workflow state tests."""

    value: int = 0
    text: str = ""
    processed: bool = False


# Test nodes
@register_node(alias="test_inc_node")
class IncrementTestNode(Node):
    """Test node that increments a value in state."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=False,  # Provided by workflow at runtime
                description="State wrapper",
            ),
            "amount": NodeParameter(
                name="amount",
                type=int,
                required=False,
                default=1,
                description="Amount to increment",
            ),
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="Updated state wrapper",
            ),
            "incremented_value": NodeParameter(
                name="incremented_value",
                type=int,
                required=True,
                description="The incremented value",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]
        amount = kwargs.get("amount", 1)

        state = state_wrapper.get_state()
        current_value = state.value
        new_value = current_value + amount

        # Update state
        updated_wrapper = state_wrapper.update_in(["value"], new_value)

        return {"state_wrapper": updated_wrapper, "incremented_value": new_value}


@register_node(alias="test_text_node")
class TextTestNode(Node):
    """Test node that updates text in state."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=False,  # Provided by workflow at runtime
                description="State wrapper",
            ),
            "text": NodeParameter(
                name="text", type=str, required=True, description="Text to set"
            ),
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="Updated state wrapper",
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]
        text = kwargs["text"]

        # Update state
        updated_wrapper = state_wrapper.update_in(["text"], text)

        return {"state_wrapper": updated_wrapper}


@register_node(alias="test_mark_processed")
class MarkProcessedTestNode(Node):
    """Test node that marks state as processed."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=False,  # Provided by workflow at runtime
                description="State wrapper",
            )
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        return {
            "state_wrapper": NodeParameter(
                name="state_wrapper",
                type=WorkflowStateWrapper,
                required=True,
                description="Updated state wrapper",
            ),
            "final_state": NodeParameter(
                name="final_state",
                type=WorkflowStateModel,
                required=True,
                description="Final state",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        state_wrapper = kwargs["state_wrapper"]

        # Batch update to set processed flag and prefix the text
        updated_wrapper = state_wrapper.batch_update(
            [
                (["processed"], True),
                (["text"], f"Processed: {state_wrapper.get_state().text}"),
            ]
        )

        return {
            "state_wrapper": updated_wrapper,
            "final_state": updated_wrapper.get_state(),
        }


class WorkflowStateModelIntegration:
    """Tests for workflow integration with state management."""

    def test_simple_workflow_with_state(self):
        """Test a simple workflow using state management."""
        # Arrange
        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test workflow with state management",
        )

        # Add nodes
        workflow.add_node("increment", TestIncrementNode())
        workflow.add_node("set_text", TestTextNode(text="Test text"))
        workflow.add_node("mark_processed", TestMarkProcessedNode())

        # Connect nodes
        workflow.connect("increment", "set_text", {"state_wrapper": "state_wrapper"})
        workflow.connect(
            "set_text", "mark_processed", {"state_wrapper": "state_wrapper"}
        )

        # Initial state
        initial_state = WorkflowStateModel(value=10)

        # Act
        final_state, results = workflow.execute_with_state(
            state_model=initial_state, wrap_state=True
        )

        # Assert
        assert final_state.value == 11
        assert final_state.text == "Processed: Test text"
        assert final_state.processed is True

        # Check intermediate results
        assert results["increment"]["incremented_value"] == 11
        assert "final_state" in results["mark_processed"]

    def test_workflow_with_custom_amount(self):
        """Test workflow with parameter override."""
        # Arrange
        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test workflow with state management",
        )

        # Add nodes
        workflow.add_node("increment", TestIncrementNode())
        workflow.add_node("set_text", TestTextNode(text="Test text"))

        # Connect nodes
        workflow.connect("increment", "set_text", {"state_wrapper": "state_wrapper"})

        # Initial state
        initial_state = WorkflowStateModel(value=5)

        # Act
        final_state, results = workflow.execute_with_state(
            state_model=initial_state,
            increment={"amount": 5},  # Override amount parameter
        )

        # Assert
        assert final_state.value == 10
        assert final_state.text == "Test text"
        assert results["increment"]["incremented_value"] == 10

    def test_workflow_without_wrapping(self):
        """Test workflow without state wrapping."""
        # Arrange
        workflow = Workflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test workflow without state wrapping",
        )

        # Create a node that works with unwrapped state
        @register_node(alias="test_unwrapped_node")
        class TestUnwrappedNode(Node):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "state": NodeParameter(
                        name="state",
                        type=WorkflowStateModel,
                        required=False,  # Provided by workflow at runtime
                        description="Unwrapped state",
                    )
                }

            def get_output_schema(self) -> dict[str, NodeParameter]:
                return {
                    "state": NodeParameter(
                        name="state",
                        type=WorkflowStateModel,
                        required=True,
                        description="Updated state",
                    )
                }

            def run(self, **kwargs) -> dict[str, Any]:
                state = kwargs["state"]
                # Create a new state object with updates
                new_state = WorkflowStateModel(
                    value=state.value + 1, text="Unwrapped text", processed=True
                )
                return {"state": new_state}

        # Add node
        workflow.add_node("unwrapped", TestUnwrappedNode())

        # Initial state
        initial_state = WorkflowStateModel(value=20)

        # Act
        final_state, results = workflow.execute_with_state(
            state_model=initial_state, wrap_state=False  # Don't wrap state
        )

        # Assert
        assert final_state.value == 21
        assert final_state.text == "Unwrapped text"
        assert final_state.processed is True
