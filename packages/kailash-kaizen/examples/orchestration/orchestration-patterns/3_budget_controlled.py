"""
Budget-Controlled Orchestration with Cost Tracking.

Demonstrates:
- Budget limits per agent
- Cost tracking and enforcement
- Agent budget exhaustion handling
- Runtime budget monitoring

Use case: Cost-controlled production environments with spending limits.
Cost: ~$0.01 (uses OpenAI gpt-5-nano for demonstration)
"""

import asyncio

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.orchestration import (
    AgentStatus,
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
    RoutingStrategy,
)
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Define Signatures
# ============================================================================


class TaskSignature(Signature):
    """Generic task processing signature."""

    task: str = InputField(description="Task description")
    result: str = OutputField(description="Task result")


# ============================================================================
# Create Agents with Budget Constraints
# ============================================================================


def create_cheap_agent():
    """Create agent using gpt-5-nano (very cheap)."""
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",  # Cheap model
        temperature=0.0,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "CheapAgent",
        "capability": "General task processing with low cost",
        "description": "Budget-friendly agent for simple tasks",
    }

    return agent


def create_premium_agent():
    """Create agent using gpt-5-nano (same model, but with higher budget limit)."""
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",
        temperature=0.0,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "PremiumAgent",
        "capability": "General task processing with higher budget",
        "description": "Premium agent with higher budget allocation",
    }

    return agent


# ============================================================================
# Main Orchestration
# ============================================================================


async def main():
    """Demonstrate budget-controlled orchestration."""

    # Configure runtime with budget enforcement
    config = OrchestrationRuntimeConfig(
        max_concurrent_agents=3,
        enable_health_monitoring=True,
        health_check_interval=10.0,
        enable_budget_enforcement=True,  # Enable budget tracking
    )

    # Create runtime
    runtime = OrchestrationRuntime(config=config)
    await runtime.start()

    try:
        # Create agents
        cheap_agent = create_cheap_agent()
        premium_agent = create_premium_agent()

        # Register agents
        print("Registering agents with budget limits...")
        cheap_id = await runtime.register_agent(cheap_agent)
        premium_id = await runtime.register_agent(premium_agent)

        # Set budget limits
        runtime.agents[cheap_id].budget_limit_usd = 0.05  # $0.05 limit
        runtime.agents[premium_id].budget_limit_usd = 0.20  # $0.20 limit

        print(f"✓ Registered {len(runtime.agents)} agents:")
        print("  - CheapAgent: $0.05 budget limit")
        print("  - PremiumAgent: $0.20 budget limit")

        # Display initial budget state
        print("\nInitial Budget State:")
        print(f"  Total runtime budget: ${runtime._total_budget_spent:.6f}")
        for agent_id, metadata in runtime.agents.items():
            print(
                f"  {metadata.agent._a2a_card['name']}: "
                f"${metadata.budget_spent_usd:.6f} / ${metadata.budget_limit_usd:.2f}"
            )

        # Route tasks (routing doesn't execute, so budget doesn't change)
        print("\n" + "=" * 70)
        print("Routing Tasks (budget tracking demonstration)")
        print("=" * 70)

        tasks = [
            "Task 1: Simple query",
            "Task 2: Data processing",
            "Task 3: Code generation",
            "Task 4: Text analysis",
        ]

        for i, task in enumerate(tasks, 1):
            # Use round-robin routing
            selected_agent = await runtime.route_task(
                task, strategy=RoutingStrategy.ROUND_ROBIN
            )

            if selected_agent:
                agent_name = selected_agent._a2a_card["name"]
                print(f"\n{i}. Task: '{task}'")
                print(f"   Selected: {agent_name}")
            else:
                print(f"\n{i}. Task: '{task}'")
                print("   ⚠ No agent available (budget exhausted or unhealthy)")

        # Display budget state after routing
        print("\n" + "=" * 70)
        print("Budget State After Routing:")
        print("=" * 70)
        print(f"  Total runtime budget: ${runtime._total_budget_spent:.6f}")
        for agent_id, metadata in runtime.agents.items():
            agent_name = metadata.agent._a2a_card["name"]
            budget_remaining = metadata.budget_limit_usd - metadata.budget_spent_usd
            budget_pct = (metadata.budget_spent_usd / metadata.budget_limit_usd) * 100

            print(f"\n  {agent_name}:")
            print(
                f"    Spent: ${metadata.budget_spent_usd:.6f} / ${metadata.budget_limit_usd:.2f}"
            )
            print(f"    Remaining: ${budget_remaining:.6f} ({100-budget_pct:.1f}%)")
            print(f"    Status: {metadata.status.value}")
            print(f"    Tasks completed: {metadata.completed_tasks}")

        # Check agent health and status
        print("\n" + "=" * 70)
        print("Agent Health Check:")
        print("=" * 70)

        for agent_id, metadata in runtime.agents.items():
            agent_name = metadata.agent._a2a_card["name"]
            health = await runtime.check_agent_health(agent_id)

            print(f"\n  {agent_name}:")
            print(f"    Health: {'✓ Healthy' if health else '✗ Unhealthy'}")
            print(f"    Status: {metadata.status.value}")
            print(f"    Error count: {metadata.error_count}")

        # Demonstrate budget exhaustion scenario
        print("\n" + "=" * 70)
        print("Budget Exhaustion Scenario:")
        print("=" * 70)
        print("Note: In production, budget would be enforced during actual execution.")
        print("Routing tasks does not consume budget (only execution does).")

        # Clean up
        print("\n" + "=" * 70)
        print("Cleanup:")
        print("=" * 70)
        await runtime.deregister_agent(cheap_id)
        await runtime.deregister_agent(premium_id)
        print(f"✓ Deregistered all agents (remaining: {len(runtime.agents)})")

    finally:
        # Shutdown runtime
        await runtime.shutdown()
        print("\n✓ Runtime shutdown complete")
        print(f"\nFinal total budget spent: ${runtime._total_budget_spent:.6f}")


if __name__ == "__main__":
    print("=" * 70)
    print("Budget-Controlled Orchestration Demo")
    print("=" * 70)
    print("\nThis demo uses OpenAI gpt-5-nano-2025-08-07 (very cheap)")
    print("Estimated cost: ~$0.01 or less")
    print("\nRequires OPENAI_API_KEY in .env file")
    print("=" * 70)

    asyncio.run(main())
