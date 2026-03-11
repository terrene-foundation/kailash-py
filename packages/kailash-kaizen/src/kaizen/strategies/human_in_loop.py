"""
HumanInLoopStrategy - Request human approval during execution.

Use Cases:
- High-stakes decisions requiring human oversight
- Content moderation (review before publishing)
- Financial transactions (approve before executing)
- Quality control checkpoints
- Training/feedback loops
"""

from typing import Any, Callable, Dict, List, Tuple


class HumanInLoopStrategy:
    """
    Strategy that requests human approval before returning results.

    Use Cases:
    - High-stakes decisions requiring human oversight
    - Content moderation (review before publishing)
    - Financial transactions (approve before executing)
    - Quality control checkpoints
    - Training/feedback loops
    """

    def __init__(self, approval_callback: Callable = None):
        """
        Initialize human-in-loop strategy.

        Args:
            approval_callback: Function that requests human approval
                              Signature: (result: Dict) -> (approved: bool, feedback: str)
        """
        self.approval_callback = approval_callback or self._default_callback
        self.approval_history: List[Dict[str, Any]] = []

    def _default_callback(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Default callback for tests (auto-approve).

        Production implementations should override this with actual
        human interaction (CLI prompt, web form, webhook, etc.)

        Args:
            result: Execution result to approve

        Returns:
            Tuple of (approved, feedback)
        """
        return True, "Auto-approved (test mode)"

    async def execute(self, agent, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute with human approval checkpoint.

        Flow:
        1. Execute agent normally
        2. Request human approval
        3. If approved: return result
        4. If rejected: raise error with feedback

        Args:
            agent: Agent instance
            inputs: Input dictionary

        Returns:
            Dict with response and approval metadata

        Raises:
            RuntimeError: If human rejects the result
        """
        # Execute agent
        result = await agent.execute(inputs)

        # Request human approval
        approved, feedback = self.approval_callback(result)

        # Record approval decision
        approval_record = {
            "result": result.copy(),
            "approved": approved,
            "feedback": feedback,
        }
        self.approval_history.append(approval_record)

        if not approved:
            # Rejected - raise error with feedback
            raise RuntimeError(f"Human rejected result: {feedback}")

        # Approved - add approval metadata and return
        result["_human_approved"] = True
        result["_approval_feedback"] = feedback

        return result

    def get_approval_history(self) -> List[Dict[str, Any]]:
        """
        Get history of all approval decisions.

        Returns:
            List of approval records with result, approved flag, and feedback
        """
        return self.approval_history.copy()
