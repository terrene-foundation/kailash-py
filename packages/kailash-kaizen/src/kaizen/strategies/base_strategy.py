"""
ExecutionStrategy - Base protocol for agent execution strategies.

This module defines the ExecutionStrategy Protocol that all execution
strategies must implement. Uses structural typing (Protocol) rather than
abstract base classes for flexibility.

Strategy Pattern:
- SingleShotStrategy: One-pass execution
- MultiCycleStrategy: Multi-cycle execution with feedback loops

References:
- ADR-006: Agent Base Architecture design (Strategy Pattern section)
- TODO-157: Task 1.4 (ExecutionStrategy protocol definition)

Author: Kaizen Framework Team
Created: 2025-10-01
"""

from typing import Any, Dict, Protocol, runtime_checkable

from kailash.workflow.builder import WorkflowBuilder


@runtime_checkable
class ExecutionStrategy(Protocol):
    """
    Base protocol for agent execution strategies.

    All execution strategies must implement this protocol to be compatible
    with BaseAgent. Uses structural typing (Protocol) for maximum flexibility.

    Methods:
        execute: Execute the strategy with given inputs
        build_workflow: Build a workflow for this strategy

    Example Implementation:
        >>> class CustomStrategy:
        ...     def execute(self, agent: Any, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        ...         # Custom execution logic
        ...         return {"result": "custom"}
        ...
        ...     def build_workflow(self, agent: Any) -> WorkflowBuilder:
        ...         # Custom workflow building
        ...         workflow = WorkflowBuilder()
        ...         workflow.add_node('LLMAgentNode', 'agent', {...})
        ...         return workflow
        >>>
        >>> # Use with BaseAgent
        >>> strategy = CustomStrategy()
        >>> agent = BaseAgent(config=config, strategy=strategy)

    Notes:
    - This is a Protocol (structural type), not an ABC
    - Implementations don't need to inherit from this class
    - Type checking via isinstance() is supported (@runtime_checkable)
    - Implementation details in Phase 2 (Tasks 2.1-2.8)
    """

    def execute(
        self,
        agent: Any,  # BaseAgent when fully implemented
        inputs: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute the strategy with given inputs.

        Args:
            agent: The agent instance executing this strategy
            inputs: Input parameters for execution
            **kwargs: Additional strategy-specific parameters

        Returns:
            Dict[str, Any]: Execution results

        Raises:
            RuntimeError: If execution fails

        Example:
            >>> result = strategy.execute(agent, {'question': 'What is 2+2?'})
            >>> print(result)
            {'answer': '4', 'confidence': 0.99}
        """
        ...

    def build_workflow(self, agent: Any) -> WorkflowBuilder:
        """
        Build a workflow for this strategy.

        Args:
            agent: The agent instance for workflow building

        Returns:
            WorkflowBuilder: Workflow for this strategy

        Example:
            >>> workflow = strategy.build_workflow(agent)
            >>> built = workflow.build()
            >>> runtime.execute(built)
        """
        ...
