"""
Tests for the state management functionality in the Kailash SDK.

This module tests the functionality of the StateManager and WorkflowStateWrapper
classes to ensure they correctly handle immutable state updates.
"""

import pytest
from kailash.workflow.state import StateManager, WorkflowStateWrapper
from pydantic import BaseModel, Field


# Test model classes
class NestedModel(BaseModel):
    """Test nested model."""

    value: str = "default"
    count: int = 0
    items: list[str] = Field(default_factory=list)


class StateTestModel(BaseModel):
    """Test state model for state management tests."""

    name: str = "test"
    enabled: bool = True
    count: int = 0
    tags: list[str] = Field(default_factory=list)
    nested: NestedModel = Field(default_factory=NestedModel)
    optional: str | None = None
    data: dict[str, str] = Field(default_factory=dict)


class StateTestModelManager:
    """Tests for the StateManager class."""

    def test_update_in_top_level(self):
        """Test updating a top-level property."""
        # Arrange
        state = StateTestModel()

        # Act
        new_state = StateManager.update_in(state, ["name"], "updated")

        # Assert
        assert new_state.name == "updated"
        assert state.name == "test"  # Original unchanged
        assert new_state is not state  # New instance

    def test_update_in_nested(self):
        """Test updating a nested property."""
        # Arrange
        state = StateTestModel()

        # Act
        new_state = StateManager.update_in(state, ["nested", "value"], "updated_nested")

        # Assert
        assert new_state.nested.value == "updated_nested"
        assert state.nested.value == "default"  # Original unchanged
        assert new_state.nested is not state.nested  # New nested instance

    def test_update_in_list(self):
        """Test updating a list property."""
        # Arrange
        state = StateTestModel(tags=["tag1", "tag2"])

        # Act
        new_state = StateManager.update_in(state, ["tags"], ["tag3", "tag4"])

        # Assert
        assert new_state.tags == ["tag3", "tag4"]
        assert state.tags == ["tag1", "tag2"]  # Original unchanged

    def test_update_in_nested_list(self):
        """Test updating a nested list property."""
        # Arrange
        state = StateTestModel(nested=NestedModel(items=["item1", "item2"]))

        # Act
        new_state = StateManager.update_in(
            state, ["nested", "items"], ["item3", "item4"]
        )

        # Assert
        assert new_state.nested.items == ["item3", "item4"]
        assert state.nested.items == ["item1", "item2"]  # Original unchanged

    def test_batch_update(self):
        """Test batch updating multiple properties."""
        # Arrange
        state = StateTestModel()

        # Act
        new_state = StateManager.batch_update(
            state,
            [
                (["name"], "batch_updated"),
                (["count"], 42),
                (["nested", "value"], "nested_batch_updated"),
            ],
        )

        # Assert
        assert new_state.name == "batch_updated"
        assert new_state.count == 42
        assert new_state.nested.value == "nested_batch_updated"
        assert state.name == "test"  # Original unchanged
        assert state.count == 0  # Original unchanged
        assert state.nested.value == "default"  # Original unchanged

    def test_get_in_top_level(self):
        """Test getting a top-level property."""
        # Arrange
        state = StateTestModel(name="test_get")

        # Act
        value = StateManager.get_in(state, ["name"])

        # Assert
        assert value == "test_get"

    def test_get_in_nested(self):
        """Test getting a nested property."""
        # Arrange
        state = StateTestModel(nested=NestedModel(value="nested_value"))

        # Act
        value = StateManager.get_in(state, ["nested", "value"])

        # Assert
        assert value == "nested_value"

    def test_get_in_invalid_path(self):
        """Test getting an invalid path raises KeyError."""
        # Arrange
        state = StateTestModel()

        # Act / Assert
        with pytest.raises(KeyError):
            StateManager.get_in(state, ["non_existent"])

        with pytest.raises(KeyError):
            StateManager.get_in(state, ["nested", "non_existent"])

    def test_merge(self):
        """Test merging updates."""
        # Arrange
        state = StateTestModel()

        # Act
        new_state = StateManager.merge(state, name="merged", count=99)

        # Assert
        assert new_state.name == "merged"
        assert new_state.count == 99
        assert state.name == "test"  # Original unchanged
        assert state.count == 0  # Original unchanged


@pytest.mark.requires_isolation
class TestWorkflowStateWrapper:
    """Tests for the WorkflowStateWrapper class."""

    def test_create_wrapper(self):
        """Test creating a wrapper."""
        # Arrange
        state = StateTestModel()

        # Act
        wrapper = WorkflowStateWrapper(state)

        # Assert
        assert wrapper.get_state() is state

    def test_update_in(self):
        """Test updating state through wrapper."""
        # Arrange
        state = StateTestModel()
        wrapper = WorkflowStateWrapper(state)

        # Act
        new_wrapper = wrapper.update_in(["name"], "wrapped_update")

        # Assert
        assert new_wrapper.get_state().name == "wrapped_update"
        assert wrapper.get_state().name == "test"  # Original unchanged
        assert new_wrapper is not wrapper  # New wrapper
        assert new_wrapper.get_state() is not wrapper.get_state()  # New state

    def test_batch_update(self):
        """Test batch updating through wrapper."""
        # Arrange
        state = StateTestModel()
        wrapper = WorkflowStateWrapper(state)

        # Act
        new_wrapper = wrapper.batch_update(
            [(["name"], "wrapped_batch"), (["nested", "value"], "wrapped_nested")]
        )

        # Assert
        assert new_wrapper.get_state().name == "wrapped_batch"
        assert new_wrapper.get_state().nested.value == "wrapped_nested"
        assert wrapper.get_state().name == "test"  # Original unchanged
        assert wrapper.get_state().nested.value == "default"  # Original unchanged

    def test_get_in(self):
        """Test getting value through wrapper."""
        # Arrange
        state = StateTestModel(
            name="wrapper_test", nested=NestedModel(value="wrapper_nested")
        )
        wrapper = WorkflowStateWrapper(state)

        # Act
        name = wrapper.get_in(["name"])
        nested_value = wrapper.get_in(["nested", "value"])

        # Assert
        assert name == "wrapper_test"
        assert nested_value == "wrapper_nested"

    def test_merge(self):
        """Test merging through wrapper."""
        # Arrange
        state = StateTestModel()
        wrapper = WorkflowStateWrapper(state)

        # Act
        new_wrapper = wrapper.merge(name="wrapped_merge", enabled=False)

        # Assert
        assert new_wrapper.get_state().name == "wrapped_merge"
        assert new_wrapper.get_state().enabled is False
        assert wrapper.get_state().name == "test"  # Original unchanged
        assert wrapper.get_state().enabled is True  # Original unchanged
