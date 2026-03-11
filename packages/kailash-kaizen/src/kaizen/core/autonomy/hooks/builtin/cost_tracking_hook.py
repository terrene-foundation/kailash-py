"""
Cost tracking hook for LLM API usage.

Tracks estimated costs per tool invocation and agent execution.
"""

from collections import defaultdict
from typing import ClassVar

from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult


class CostTrackingHook(BaseHook):
    """
    Tracks LLM API costs per tool invocation and agent execution.

    Accumulates costs and provides per-tool and per-agent breakdowns.
    """

    # Define which events this hook handles (POST events only for cost tracking)
    events: ClassVar[list[HookEvent]] = [
        HookEvent.POST_TOOL_USE,
        HookEvent.POST_AGENT_LOOP,
        HookEvent.POST_SPECIALIST_INVOKE,
    ]

    def __init__(self):
        """Initialize cost tracking hook"""
        super().__init__(name="cost_tracking_hook")

        # Cost accumulators
        self.total_cost_usd = 0.0
        self.costs_by_tool: dict[str, float] = defaultdict(float)
        self.costs_by_agent: dict[str, float] = defaultdict(float)
        self.costs_by_specialist: dict[str, float] = defaultdict(float)

    async def handle(self, context: HookContext) -> HookResult:
        """
        Track costs for the event.

        Args:
            context: Hook execution context

        Returns:
            HookResult with cost data
        """
        try:
            # Extract cost from event data (provided by agent)
            estimated_cost = context.data.get("estimated_cost_usd", 0.0)

            if estimated_cost > 0:
                # Accumulate total cost
                self.total_cost_usd += estimated_cost

                # Track per-agent costs
                self.costs_by_agent[context.agent_id] += estimated_cost

                # Track per-tool costs
                if context.event_type == HookEvent.POST_TOOL_USE:
                    tool_name = context.data.get("tool_name", "unknown")
                    self.costs_by_tool[tool_name] += estimated_cost

                # Track per-specialist costs
                elif context.event_type == HookEvent.POST_SPECIALIST_INVOKE:
                    specialist_name = context.data.get("specialist_name", "unknown")
                    self.costs_by_specialist[specialist_name] += estimated_cost

            return HookResult(
                success=True,
                data={
                    "total_cost_usd": self.total_cost_usd,
                    "event_cost_usd": estimated_cost,
                    "agent_cost_usd": self.costs_by_agent[context.agent_id],
                },
            )

        except Exception as e:
            return HookResult(success=False, error=str(e))

    def get_total_cost(self) -> float:
        """
        Get total accumulated cost.

        Returns:
            Total cost in USD
        """
        return self.total_cost_usd

    def get_cost_breakdown(self) -> dict[str, dict[str, float]]:
        """
        Get detailed cost breakdown.

        Returns:
            Dictionary with costs by tool, agent, and specialist
        """
        return {
            "total_cost_usd": self.total_cost_usd,
            "by_tool": dict(self.costs_by_tool),
            "by_agent": dict(self.costs_by_agent),
            "by_specialist": dict(self.costs_by_specialist),
        }

    def reset_costs(self) -> None:
        """Reset all cost counters"""
        self.total_cost_usd = 0.0
        self.costs_by_tool.clear()
        self.costs_by_agent.clear()
        self.costs_by_specialist.clear()
