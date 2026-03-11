"""
Approval Agent - Human-in-the-loop for critical decisions.

Demonstrates HumanInLoopStrategy for oversight workflows:
- Request human approval before returning results
- Track approval history with feedback
- Support approve/reject/modify decisions
- Built on BaseAgent + HumanInLoopStrategy

Use Cases:
- Financial transactions requiring approval
- Content moderation before publishing
- Critical decisions with human oversight
- Quality control checkpoints

Performance:
- Synchronous approval (waits for human decision)
- Approval history tracking for audit trails
- Configurable approval callback
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.human_in_loop import HumanInLoopStrategy


class DecisionSignature(Signature):
    """Signature for approval-based decision making."""

    prompt: str = InputField(desc="Decision prompt")
    decision: str = OutputField(desc="Recommended decision")


@dataclass
class ApprovalConfig:
    """Configuration for Approval Agent."""

    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 300
    approval_callback: Optional[Callable[[Dict[str, Any]], Tuple[bool, str]]] = None


class ApprovalAgent(BaseAgent):
    """
    Approval Agent using HumanInLoopStrategy.

    Features:
    - Request human approval before returning results
    - Track approval history for audit trails
    - Support custom approval callbacks (CLI, web form, webhook)
    - Built-in error handling and logging via BaseAgent

    Example:
        >>> import asyncio
        >>> # Define approval callback
        >>> def approve_callback(result):
        ...     print(f"Review: {result}")
        ...     response = input("Approve? (y/n): ")
        ...     return response.lower() == 'y', "User decision"
        >>>
        >>> config = ApprovalConfig(approval_callback=approve_callback)
        >>> agent = ApprovalAgent(config)
        >>>
        >>> # Decision requires approval
        >>> result = asyncio.run(agent.decide_async("Process payment $1000"))
        >>> print(f"Approved: {result['_human_approved']}")
    """

    def __init__(self, config: ApprovalConfig):
        """Initialize Approval Agent with human-in-loop strategy."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Use HumanInLoopStrategy with approval callback
        strategy = HumanInLoopStrategy(approval_callback=config.approval_callback)

        # Initialize BaseAgent
        super().__init__(
            config=config, signature=DecisionSignature(), strategy=strategy
        )

        self.approval_config = config

    async def decide_async(self, prompt: str) -> Dict[str, Any]:
        """
        Make decision with human approval requirement.

        Args:
            prompt: Decision prompt

        Returns:
            Dict with decision and approval metadata

        Raises:
            RuntimeError: If human rejects the decision

        Example:
            >>> result = await agent.decide_async("Transfer funds")
            >>> if result["_human_approved"]:
            ...     print("Proceed with transfer")
        """
        # For demo purposes, generate mock result then request approval
        # In production, strategy would execute agent then request approval
        mock_result = {"prompt": prompt, "decision": f"Placeholder result for {prompt}"}

        # Request human approval
        approved, feedback = self.strategy.approval_callback(mock_result)

        # Record approval decision
        approval_record = {
            "result": mock_result.copy(),
            "approved": approved,
            "feedback": feedback,
        }
        self.strategy.approval_history.append(approval_record)

        if not approved:
            # Rejected - raise error with feedback
            raise RuntimeError(f"Human rejected result: {feedback}")

        # Approved - add approval metadata and return
        mock_result["_human_approved"] = True
        mock_result["_approval_feedback"] = feedback

        return mock_result

    def decide(self, prompt: str) -> str:
        """
        Synchronous decision making (for compatibility).

        Args:
            prompt: Decision prompt

        Returns:
            str: Decision text

        Example:
            >>> decision = agent.decide("Publish content")
        """
        import asyncio

        result = asyncio.run(self.decide_async(prompt))
        return result.get("decision", "No decision")

    def get_approval_history(self) -> List[Dict[str, Any]]:
        """
        Get history of all approval decisions.

        Returns:
            List of approval records with result, approved flag, and feedback

        Example:
            >>> history = agent.get_approval_history()
            >>> for record in history:
            ...     print(f"Approved: {record['approved']}")
            ...     print(f"Feedback: {record['feedback']}")
        """
        return self.strategy.get_approval_history()


def demo_auto_approval():
    """Demo auto-approval (test mode)."""
    import asyncio

    config = ApprovalConfig(llm_provider="mock")
    agent = ApprovalAgent(config)

    async def demo():
        print("Auto-Approval Demo (Test Mode)")
        print("=" * 50)
        print("Note: Auto-approval enabled for testing\n")

        decisions = [
            "Process payment of $100",
            "Publish blog post",
            "Grant admin access",
        ]

        for i, prompt in enumerate(decisions, 1):
            result = await agent.decide_async(prompt)

            print(f"{i}. Decision: {prompt}")
            print(f"   Recommendation: {result.get('decision', 'N/A')}")
            print(f"   Approved: {result.get('_human_approved', False)}")
            print(f"   Feedback: {result.get('_approval_feedback', 'N/A')}\n")

    asyncio.run(demo())


def demo_custom_approval():
    """Demo custom approval callback."""
    import asyncio

    # Simulated approval callback
    approvals = {"Process payment": True, "Delete database": False}

    def custom_callback(result):
        prompt = result.get("prompt", "")
        for key in approvals:
            if key in prompt:
                approved = approvals[key]
                feedback = "Approved by user" if approved else "Rejected by user"
                return approved, feedback
        return True, "Auto-approved"

    config = ApprovalConfig(approval_callback=custom_callback, llm_provider="mock")
    agent = ApprovalAgent(config)

    async def demo():
        print("Custom Approval Demo")
        print("=" * 50)
        print("Pre-configured approvals:")
        for decision, approved in approvals.items():
            status = "✓ Approve" if approved else "✗ Reject"
            print(f"  {status}: {decision}")
        print()

        # Try approved decision
        try:
            result = await agent.decide_async("Process payment of $500")
            print("1. Decision: Process payment")
            print("   Status: ✓ Approved")
            print(f"   Feedback: {result.get('_approval_feedback')}\n")
        except RuntimeError as e:
            print(f"1. Decision rejected: {e}\n")

        # Try rejected decision
        try:
            result = await agent.decide_async("Delete database permanently")
            print("2. Decision: Delete database")
            print("   Status: ✓ Approved")
            print(f"   Feedback: {result.get('_approval_feedback')}\n")
        except RuntimeError as e:
            print("2. Decision: Delete database")
            print("   Status: ✗ Rejected")
            print(f"   Reason: {str(e)}\n")

    asyncio.run(demo())


def demo_approval_history():
    """Demo approval history tracking."""
    import asyncio

    config = ApprovalConfig(llm_provider="mock")
    agent = ApprovalAgent(config)

    async def demo():
        print("Approval History Demo")
        print("=" * 50)

        # Make multiple decisions
        decisions = ["Decision 1", "Decision 2", "Decision 3"]

        for decision in decisions:
            await agent.decide_async(decision)

        # Show history
        history = agent.get_approval_history()

        print(f"Total decisions: {len(history)}\n")

        for i, record in enumerate(history, 1):
            print(f"{i}. Approved: {record['approved']}")
            print(f"   Feedback: {record['feedback']}")
            print(f"   Result: {record['result'].get('decision', 'N/A')}\n")

    asyncio.run(demo())


if __name__ == "__main__":
    # Demo auto-approval
    demo_auto_approval()

    print()

    # Demo custom approval
    demo_custom_approval()

    print()

    # Demo approval history
    demo_approval_history()
