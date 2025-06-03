# 0016. Immutable State Management

Date: 2025-05-21

## Status

Accepted

## Context

In the Kailash Python SDK, workflow execution requires maintaining state between nodes.
The initial implementation used a simple passing approach where each node receives a
state object and returns an updated state object (often using Pydantic's `model_copy()`
with updates). This has several drawbacks:

1. **Cognitive Overhead**: Developers must manually track which parts of the state they're
   updating, leading to verbose and error-prone code.

2. **Error-Prone**: Without careful attention, developers might modify state in place
   rather than creating immutable copies, leading to unexpected side effects.

3. **Verbosity**: Updating nested state structures requires multiple lines of code with
   intermediate variables, making node implementations harder to read and maintain.

4. **Testing Challenges**: The manual state handling complicates testing since it's
   challenging to isolate state transformations.

5. **Code Duplication**: Similar state copying patterns appear throughout the codebase.

This issue was identified during the adaptation of the HMI project, where state management
involved numerous nested fields and transformations that made node implementations longer
and more complex than necessary.

## Decision

We will implement a robust immutable state management system for workflows with the
following components:

1. **StateManager**: A utility class with static methods for working with state objects:
   - `update_in()`: Update a nested path in a state object and return a new state
   - `batch_update()`: Apply multiple updates atomically
   - `get_in()`: Get a value from a nested path
   - `merge()`: MergeNode top-level updates into a state

2. **WorkflowStateWrapper**: A wrapper class that provides a friendly API for the state
   management methods and maintains immutability throughout updates.

3. **Workflow Integration**: Extend the `Workflow` class to support state management:
   - `create_state_wrapper()`: Create a state wrapper for a workflow
   - `execute_with_state()`: Execute a workflow with automatic state management

4. **WorkflowRunner**: A new class for managing execution across multiple workflows,
   with state passing between workflows.

The approach is inspired by immutable state management patterns in frontend frameworks
like Redux/React, adapted for Python's type system and Pydantic models.

## Consequences

### Positive

1. **Cleaner Node Implementation**: Nodes can update state with concise, declarative
   statements, reducing boilerplate.

2. **Improved Immutability**: The system ensures immutability at all levels, preventing
   accidental state modification.

3. **Better Testability**: State transformations are isolated and explicit, making them
   easier to test.

4. **Composability**: State updates can be composed through method chaining.

5. **Enhanced Developer Experience**: Reduces cognitive overhead and makes state
   management more intuitive.

6. **Multi-Workflow Support**: Enables connecting multiple workflows with state passing.

### Negative

1. **Learning Curve**: Developers familiar with the previous approach will need to
   learn the new state management patterns.

2. **Increased Abstraction**: Adds another layer of abstraction to the codebase.

3. **Performance Overhead**: Deep copying for immutability has some performance cost,
   though negligible for most use cases.

4. **Backward Compatibility**: Existing code using the previous pattern needs updates
   to take advantage of the new system.

## Alternatives Considered

1. **Enhanced copy_with_updates Methods**: Extending the current pattern with
   better helper methods. Rejected because it would still require manual state copying
   and wouldn't address the core issues.

2. **Mutable State with Proxies**: Using proxy objects to track state changes.
   Rejected due to complexity and potential for side effects.

3. **Event-Sourced State**: Modeling state changes as events. Rejected as overly
   complex for our use case.

4. **External State Management Library**: Using an existing state management library.
   Rejected to avoid external dependencies and better integrate with our workflow system.

## Implementation

The implementation includes:

1. New module: `kailash.workflow.state`
2. Extended workflow execution in `kailash.workflow.graph`
3. New module: `kailash.workflow.runner`
4. Updated example nodes to demonstrate usage

## Implementation Status

As of 2025-05-30, immutable state management has been fully implemented:
- StateManager utility class with all planned methods in `kailash.workflow.state`
- WorkflowStateWrapper providing friendly API for state operations
- Workflow integration with `create_state_wrapper()` and `execute_with_state()`
- WorkflowRunner for multi-workflow state management in `kailash.workflow.runner`
- Comprehensive test coverage in `tests/test_workflow/test_state_management.py`
- Working example in `state_management_example.py`
- Full backward compatibility maintained

## References

- React/Redux immutable state patterns
- Pydantic's model_copy functionality
- HMI project adaptation observations
