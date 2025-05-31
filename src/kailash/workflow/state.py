"""State management for workflow execution.

This module provides tools for managing immutable state throughout workflow execution,
making it easier to handle state transitions in a predictable manner.
"""

import logging
from copy import deepcopy
from typing import Any, Generic, List, Tuple, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Type variable for the state model
StateT = TypeVar("StateT", bound=BaseModel)


class StateManager:
    """Manages immutable state operations for workflow execution.

    This class provides utilities for updating state objects immutably,
    focusing on Pydantic models to ensure type safety and validation.
    """

    @staticmethod
    def update_in(state_obj: BaseModel, path: List[str], value: Any) -> BaseModel:
        """Update a nested property in the state and return a new state object.

        Args:
            state_obj: The Pydantic model state object
            path: List of attribute names forming a path to the property to update
            value: The new value to set

        Returns:
            A new state object with the update applied

        Raises:
            TypeError: If state_obj is not a Pydantic BaseModel
            KeyError: If the path is invalid
        """
        if not isinstance(state_obj, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_obj)}")

        # Create deep copy
        new_state = state_obj.model_copy(deep=True)

        # For simple top-level updates
        if len(path) == 1:
            setattr(new_state, path[0], value)
            return new_state

        # For nested updates
        current = new_state
        for i, key in enumerate(path[:-1]):
            if not hasattr(current, key):
                raise KeyError(f"Invalid path: {'.'.join(path[:i+1])}")

            # Get the next level object and ensure we're working with a copy
            next_obj = getattr(current, key)
            if isinstance(next_obj, BaseModel):
                next_obj = next_obj.model_copy(deep=True)
                setattr(current, key, next_obj)
            elif isinstance(next_obj, dict):
                next_obj = deepcopy(next_obj)
                setattr(current, key, next_obj)
            elif isinstance(next_obj, list):
                next_obj = deepcopy(next_obj)
                setattr(current, key, next_obj)

            current = next_obj

        # Set the final value
        if hasattr(current, path[-1]):
            setattr(current, path[-1], value)
        else:
            raise KeyError(f"Invalid path: {'.'.join(path)}")

        return new_state

    @staticmethod
    def batch_update(
        state_obj: BaseModel, updates: List[Tuple[List[str], Any]]
    ) -> BaseModel:
        """Apply multiple updates to the state atomically.

        Args:
            state_obj: The Pydantic model state object
            updates: List of (path, value) tuples with updates to apply

        Returns:
            A new state object with all updates applied

        Raises:
            TypeError: If state_obj is not a Pydantic BaseModel
            KeyError: If any path is invalid
        """
        if not isinstance(state_obj, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_obj)}")

        # Create deep copy
        new_state = state_obj.model_copy(deep=True)

        # Apply each update
        for path, value in updates:
            new_state = StateManager.update_in(new_state, path, value)

        return new_state

    @staticmethod
    def get_in(state_obj: BaseModel, path: List[str]) -> Any:
        """Get the value at a nested path.

        Args:
            state_obj: The Pydantic model state object
            path: List of attribute names forming a path to the property to retrieve

        Returns:
            The value at the specified path

        Raises:
            TypeError: If state_obj is not a Pydantic BaseModel
            KeyError: If the path is invalid
        """
        if not isinstance(state_obj, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_obj)}")

        # For simple top-level properties
        if len(path) == 1:
            if not hasattr(state_obj, path[0]):
                raise KeyError(f"Invalid path: {path[0]}")
            return getattr(state_obj, path[0])

        # For nested properties
        current = state_obj
        for i, key in enumerate(path):
            if not hasattr(current, key):
                raise KeyError(f"Invalid path: {'.'.join(path[:i+1])}")
            current = getattr(current, key)

        return current

    @staticmethod
    def merge(state_obj: BaseModel, **updates) -> BaseModel:
        """Merge flat updates into state and return a new state.

        Args:
            state_obj: The Pydantic model state object
            **updates: Attribute updates to apply to the top level

        Returns:
            A new state object with the updates applied

        Raises:
            TypeError: If state_obj is not a Pydantic BaseModel
        """
        if not isinstance(state_obj, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_obj)}")

        return state_obj.model_copy(update=updates)


class WorkflowStateWrapper(Generic[StateT]):
    """Wraps a state object with convenient update methods for use in workflows.

    This wrapper provides a clean interface for immutable state updates
    within workflow nodes, simplifying state management.
    """

    def __init__(self, state: StateT):
        """Initialize the state wrapper.

        Args:
            state: The Pydantic model state object to wrap
        """
        self._state = state

    def update_in(self, path: List[str], value: Any) -> "WorkflowStateWrapper[StateT]":
        """Update state at path and return new wrapper.

        Args:
            path: List of attribute names forming a path to the property to update
            value: The new value to set

        Returns:
            A new state wrapper with the update applied
        """
        new_state = StateManager.update_in(self._state, path, value)
        return WorkflowStateWrapper(new_state)

    def batch_update(
        self, updates: List[Tuple[List[str], Any]]
    ) -> "WorkflowStateWrapper[StateT]":
        """Apply multiple updates to the state atomically.

        Args:
            updates: List of (path, value) tuples with updates to apply

        Returns:
            A new state wrapper with all updates applied
        """
        new_state = StateManager.batch_update(self._state, updates)
        return WorkflowStateWrapper(new_state)

    def get_in(self, path: List[str]) -> Any:
        """Get the value at a nested path.

        Args:
            path: List of attribute names forming a path to the property to retrieve

        Returns:
            The value at the specified path
        """
        return StateManager.get_in(self._state, path)

    def merge(self, **updates) -> "WorkflowStateWrapper[StateT]":
        """Merge flat updates into state and return a new wrapper.

        Args:
            **updates: Attribute updates to apply to the top level

        Returns:
            A new state wrapper with the updates applied
        """
        new_state = StateManager.merge(self._state, **updates)
        return WorkflowStateWrapper(new_state)

    def get_state(self) -> StateT:
        """Get the wrapped state object.

        Returns:
            The current state object
        """
        return self._state

    def __repr__(self) -> str:
        """Get string representation."""
        return f"WorkflowStateWrapper({self._state})"
