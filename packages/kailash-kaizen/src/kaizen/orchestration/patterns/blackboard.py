"""
Blackboard Pipeline - Iterative Specialist Collaboration with A2A Selection

Implements blackboard pattern with A2A-based specialist selection and iterative convergence.

Pattern:
    User Request → Blackboard → Controller (decide) → A2A Specialist Selection → Update Blackboard → Repeat → Result

Features:
- A2A-based specialist selection for evolving needs
- Controller determines when solution is complete
- Iterative collaboration with blackboard state accumulation
- Graceful fallback when A2A unavailable
- Configurable selection modes (semantic, sequential)
- Max iterations limit for non-convergence safety
- Error handling with configurable fail-fast mode
- Composable via .to_agent()

Usage:
    from kaizen.orchestration.pipeline import Pipeline

    # Semantic specialist selection (A2A)
    pipeline = Pipeline.blackboard(
        specialists=[problem_solver, data_analyst, optimizer, validator],
        controller=controller_agent,
        selection_mode="semantic",
        max_iterations=5
    )
    result = pipeline.run(task="Complex problem solving", input="problem_data")

    # Sequential specialist invocation
    pipeline = Pipeline.blackboard(
        specialists=[specialist1, specialist2, specialist3],
        controller=controller,
        selection_mode="sequential",
        max_iterations=10
    )
    result = pipeline.run(task="Iterative refinement", input="data")

Author: Kaizen Framework Team
Created: 2025-10-27 (Phase 3, Day 2, TODO-174)
Reference: ADR-018, docs/testing/pipeline-edge-case-test-matrix.md
"""

from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.pipeline import Pipeline

# A2A imports for capability-based specialist selection
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard, Capability

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    Capability = None
    A2AAgentCard = None


class BlackboardPipeline(Pipeline):
    """
    Blackboard Pipeline with A2A specialist selection and iterative convergence.

    Maintains shared blackboard state, iteratively selects specialists based on
    evolving needs (via A2A), and uses controller to determine when solution is complete.

    Attributes:
        specialists: List of specialist agents
        controller: Controller agent that determines completion
        selection_mode: "semantic" (A2A) or "sequential"
        max_iterations: Maximum iterations to prevent infinite loops
        error_handling: "graceful" (default) or "fail-fast"

    Example:
        from kaizen.orchestration.pipeline import Pipeline

        pipeline = Pipeline.blackboard(
            specialists=[problem_solver, data_analyst, optimizer, validator],
            controller=controller_agent,
            selection_mode="semantic",
            max_iterations=5
        )

        result = pipeline.run(
            task="Solve complex optimization problem",
            input="problem_definition"
        )
    """

    def __init__(
        self,
        specialists: List[BaseAgent],
        controller: BaseAgent,
        selection_mode: str = "semantic",
        max_iterations: int = 5,
        error_handling: str = "graceful",
    ):
        """
        Initialize Blackboard Pipeline.

        Args:
            specialists: List of specialist agents (must not be empty)
            controller: Controller agent that determines completion
            selection_mode: "semantic" (A2A) or "sequential"
            max_iterations: Maximum iterations to prevent infinite loops (default: 5)
            error_handling: "graceful" (default) or "fail-fast"

        Raises:
            ValueError: If specialists list is empty
        """
        if not specialists:
            raise ValueError("specialists cannot be empty")

        self.specialists = specialists
        self.controller = controller
        self.selection_mode = selection_mode
        self.max_iterations = max_iterations
        self.error_handling = error_handling

        # Sequential selection state
        self._current_specialist_index = 0

    def _select_specialist_via_a2a(
        self, needed_capability: Optional[str]
    ) -> Optional[BaseAgent]:
        """
        Select best specialist using A2A capability matching.

        Args:
            needed_capability: Required capability description

        Returns:
            Optional[BaseAgent]: Specialist with best capability match, or None

        Note:
            Falls back to None if A2A unavailable or no match found
        """
        if not A2A_AVAILABLE or not needed_capability:
            return None

        try:
            # Generate A2A cards for all specialists
            specialist_cards = []
            for specialist in self.specialists:
                try:
                    if hasattr(specialist, "to_a2a_card"):
                        card = specialist.to_a2a_card()
                        specialist_cards.append((specialist, card))
                except Exception:
                    # Skip specialists that can't generate A2A cards
                    continue

            # Find best match using A2A semantic matching
            if specialist_cards:
                best_specialist = None
                best_score = 0.0

                for specialist, card in specialist_cards:
                    # Calculate capability match score
                    score = 0.0
                    for capability in card.primary_capabilities:
                        capability_score = capability.matches_requirement(
                            needed_capability
                        )
                        if capability_score > score:
                            score = capability_score

                    # Track best match
                    if score > best_score:
                        best_score = score
                        best_specialist = specialist

                # Return best match if score above threshold
                if best_specialist and best_score > 0:
                    return best_specialist

        except Exception:
            # Fall through to None
            pass

        # No match found
        return None

    def _select_specialist_sequential(self) -> BaseAgent:
        """
        Select specialist using sequential strategy.

        Returns:
            BaseAgent: Next specialist in round-robin order
        """
        specialist = self.specialists[self._current_specialist_index]
        self._current_specialist_index = (self._current_specialist_index + 1) % len(
            self.specialists
        )
        return specialist

    def _select_specialist(self, needed_capability: Optional[str] = None) -> BaseAgent:
        """
        Select specialist based on selection mode.

        Args:
            needed_capability: Optional capability description for A2A matching

        Returns:
            BaseAgent: Selected specialist

        Selection Modes:
            - "semantic": Use A2A capability matching
            - "sequential": Rotate through specialists
        """
        if self.selection_mode == "semantic":
            # Try A2A matching first
            specialist = self._select_specialist_via_a2a(needed_capability)
            if specialist:
                return specialist
            # Fallback to sequential
            return self._select_specialist_sequential()
        elif self.selection_mode == "sequential":
            return self._select_specialist_sequential()
        else:
            # Unknown mode, default to sequential
            return self._select_specialist_sequential()

    def _execute_specialist(
        self, specialist: BaseAgent, blackboard: Dict[str, Any], **inputs
    ) -> Dict[str, Any]:
        """
        Execute specialist and return insight.

        Args:
            specialist: Specialist agent to execute
            blackboard: Current blackboard state
            **inputs: Original inputs

        Returns:
            Dict[str, Any]: Specialist insight

        Error Handling:
            - graceful: Return error info
            - fail-fast: Raise exception
        """
        try:
            result = specialist.run(blackboard=blackboard, **inputs)

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}

            return result

        except Exception as e:
            if self.error_handling == "fail-fast":
                raise e
            else:
                # Graceful: return error info
                import traceback

                return {
                    "error": str(e),
                    "agent_id": (
                        specialist.agent_id
                        if hasattr(specialist, "agent_id")
                        else "unknown"
                    ),
                    "status": "failed",
                    "traceback": traceback.format_exc(),
                }

    def _execute_controller(
        self, blackboard: Dict[str, Any], **inputs
    ) -> Dict[str, Any]:
        """
        Execute controller to determine completion and next needed capability.

        Args:
            blackboard: Current blackboard state
            **inputs: Original inputs

        Returns:
            Dict[str, Any]: Controller decision
                is_complete: bool - whether solution is complete
                next_needed_capability: Optional[str] - next required capability

        Error Handling:
            - graceful: Return error info (treats as complete to avoid infinite loop)
            - fail-fast: Raise exception
        """
        try:
            result = self.controller.run(blackboard=blackboard, **inputs)

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}

            return result

        except Exception as e:
            if self.error_handling == "fail-fast":
                raise e
            else:
                # Graceful: return error info and treat as complete
                import traceback

                return {
                    "error": str(e),
                    "status": "controller_failed",
                    "traceback": traceback.format_exc(),
                    "is_complete": True,  # Stop iterating to avoid infinite loop
                    "next_needed_capability": None,
                }

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Execute blackboard pipeline: iterative specialist selection and convergence.

        Args:
            **inputs: Inputs for specialist and controller execution
                task (str, optional): Task description
                ... other inputs passed to specialists and controller

        Returns:
            Dict[str, Any]: Final blackboard state with accumulated insights

        Pipeline Flow:
            1. Initialize blackboard with empty insights
            2. Loop (max_iterations):
                a. Execute controller to check completion and get needed capability
                b. If complete, return final blackboard state
                c. Select specialist via A2A (based on needed capability)
                d. Execute specialist, add insight to blackboard
            3. Return final blackboard state (converged or max iterations reached)

        Error Handling:
            - graceful (default): Continue on errors, stop at max_iterations
            - fail-fast: Raise exception on first error

        Blackboard Structure:
            {
                "insights": [insight1, insight2, ...],
                "iteration_count": int,
                "is_complete": bool,
                ... other accumulated data
            }
        """
        # Initialize blackboard
        blackboard = {"insights": [], "iteration_count": 0, "is_complete": False}

        # Iterative collaboration
        for iteration in range(self.max_iterations):
            blackboard["iteration_count"] = iteration + 1

            # Step 1: Execute controller to check completion
            controller_result = self._execute_controller(blackboard, **inputs)

            # Check if controller failed
            if "error" in controller_result:
                # Controller failed, return current state
                blackboard["controller_error"] = controller_result["error"]
                blackboard["is_complete"] = True
                return blackboard

            # Check if solution is complete
            is_complete = controller_result.get("is_complete", False)
            if is_complete:
                blackboard["is_complete"] = True
                return blackboard

            # Step 2: Get needed capability from controller
            needed_capability = controller_result.get("next_needed_capability", None)

            # Step 3: Select specialist based on needed capability
            specialist = self._select_specialist(needed_capability=needed_capability)

            # Step 4: Execute specialist and accumulate insight
            insight = self._execute_specialist(specialist, blackboard, **inputs)
            blackboard["insights"].append(insight)

        # Max iterations reached (non-convergence)
        blackboard["is_complete"] = False  # Did not converge
        blackboard["max_iterations_reached"] = True
        return blackboard


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "BlackboardPipeline",
    "A2A_AVAILABLE",
]
