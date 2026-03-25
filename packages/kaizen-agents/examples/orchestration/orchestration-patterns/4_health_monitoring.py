"""
Health Monitoring and Failure Recovery.

Demonstrates:
- Agent health checks with real LLM inference
- Status monitoring (ACTIVE, UNHEALTHY, DEGRADED)
- Error counting and failure detection
- Automatic health monitoring intervals
- Agent recovery and lifecycle management

Use case: Production orchestration with resilience and monitoring.
Cost: ~$0.01 (uses OpenAI gpt-5-nano for reliable health checks)
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

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Task result")


# ============================================================================
# Create Agents for Health Monitoring
# ============================================================================


def create_stable_agent():
    """Create agent with stable configuration (OpenAI gpt-5-nano)."""
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",  # Fast and reliable
        temperature=0.0,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "StableAgent",
        "capability": "Reliable task processing",
        "description": "Stable agent with high uptime and consistent responses",
    }

    return agent


def create_monitored_agent():
    """Create agent for monitoring demonstration."""
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",
        temperature=0.0,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "MonitoredAgent",
        "capability": "Task processing with health monitoring",
        "description": "Agent under active health monitoring",
    }

    return agent


# ============================================================================
# Main Orchestration
# ============================================================================


async def main():
    """Demonstrate health monitoring and failure recovery."""

    # Configure runtime with health monitoring
    config = OrchestrationRuntimeConfig(
        max_concurrent_agents=3,
        enable_health_monitoring=True,  # Enable health checks
        health_check_interval=5.0,  # Check every 5 seconds
        enable_budget_enforcement=True,
    )

    # Create runtime
    runtime = OrchestrationRuntime(config=config)
    await runtime.start()

    try:
        # Create agents
        stable_agent = create_stable_agent()
        monitored_agent = create_monitored_agent()

        # Register agents
        print("=" * 70)
        print("Registering Agents with Health Monitoring")
        print("=" * 70)
        stable_id = await runtime.register_agent(stable_agent)
        monitored_id = await runtime.register_agent(monitored_agent)

        print(f"\n✓ Registered {len(runtime.agents)} agents:")
        print(f"  - {stable_agent._a2a_card['name']}")
        print(f"  - {monitored_agent._a2a_card['name']}")
        print(f"\nHealth check interval: {config.health_check_interval}s")

        # Display initial health state
        print("\n" + "=" * 70)
        print("Initial Health State:")
        print("=" * 70)
        for agent_id, metadata in runtime.agents.items():
            agent_name = metadata.agent._a2a_card["name"]
            print(f"\n{agent_name}:")
            print(f"  Status: {metadata.status.value}")
            print(f"  Error count: {metadata.error_count}")
            print(f"  Active tasks: {metadata.active_tasks}")
            print(f"  Completed tasks: {metadata.completed_tasks}")
            print(f"  Failed tasks: {metadata.failed_tasks}")

        # Perform health checks
        print("\n" + "=" * 70)
        print("Performing Health Checks (Real LLM Inference)")
        print("=" * 70)
        print("Note: Health checks use actual LLM inference to verify agent health")

        for agent_id, metadata in runtime.agents.items():
            agent_name = metadata.agent._a2a_card["name"]
            print(f"\nChecking {agent_name}...")

            # Perform health check (real LLM call)
            health = await runtime.check_agent_health(agent_id)

            # Display results
            print(f"  Health check: {'✓ PASSED' if health else '✗ FAILED'}")
            print(f"  Status: {metadata.status.value}")
            print(f"  Error count: {metadata.error_count}")

            if not health:
                print("  ⚠ Agent marked as UNHEALTHY")
            else:
                print("  ✓ Agent remains ACTIVE")

        # Route tasks and check health
        print("\n" + "=" * 70)
        print("Task Routing with Health Awareness")
        print("=" * 70)
        print("Runtime automatically excludes unhealthy agents from routing")

        tasks = [
            "Process data batch 1",
            "Generate report",
            "Analyze metrics",
            "Create summary",
        ]

        for i, task in enumerate(tasks, 1):
            # Route with round-robin (only healthy agents selected)
            selected_agent = await runtime.route_task(
                task, strategy=RoutingStrategy.ROUND_ROBIN
            )

            if selected_agent:
                agent_name = selected_agent._a2a_card["name"]
                agent_id = next(
                    aid
                    for aid, meta in runtime.agents.items()
                    if meta.agent == selected_agent
                )
                metadata = runtime.agents[agent_id]

                print(f"\n{i}. Task: '{task}'")
                print(f"   Selected: {agent_name}")
                print(f"   Status: {metadata.status.value}")
                print(f"   Error count: {metadata.error_count}")
            else:
                print(f"\n{i}. Task: '{task}'")
                print("   ⚠ No healthy agent available")

        # Display comprehensive health dashboard
        print("\n" + "=" * 70)
        print("Health Monitoring Dashboard:")
        print("=" * 70)

        for agent_id, metadata in runtime.agents.items():
            agent_name = metadata.agent._a2a_card["name"]

            # Calculate health metrics
            total_tasks = (
                metadata.completed_tasks + metadata.failed_tasks + metadata.active_tasks
            )
            success_rate = (
                (metadata.completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            )

            print(f"\n{agent_name}:")
            print(f"  Status: {metadata.status.value}")
            print(
                f"  Health: {'✓ Healthy' if metadata.error_count == 0 else '✗ Unhealthy'}"
            )
            print(f"  Error count: {metadata.error_count}")
            print("  Task metrics:")
            print(f"    - Completed: {metadata.completed_tasks}")
            print(f"    - Failed: {metadata.failed_tasks}")
            print(f"    - Active: {metadata.active_tasks}")
            print(f"    - Success rate: {success_rate:.1f}%")
            print("  Budget:")
            print(
                f"    - Spent: ${metadata.budget_spent_usd:.6f} / ${metadata.budget_limit_usd:.2f}"
            )
            print(f"  Last health check: {metadata.last_health_check or 'Never'}")

        # Demonstrate failure recovery scenario
        print("\n" + "=" * 70)
        print("Failure Recovery Scenario:")
        print("=" * 70)
        print("In production:")
        print("  1. Background health checks run every 5s")
        print("  2. Failed agents marked UNHEALTHY automatically")
        print("  3. Unhealthy agents excluded from routing")
        print("  4. Agents can be deregistered and replaced")
        print("  5. New agents registered without downtime")

        # Simulate agent replacement (deregister unhealthy, register new)
        unhealthy_agents = [
            agent_id
            for agent_id, metadata in runtime.agents.items()
            if metadata.status != AgentStatus.ACTIVE
        ]

        if unhealthy_agents:
            print(f"\nFound {len(unhealthy_agents)} unhealthy agent(s)")
            for agent_id in unhealthy_agents:
                agent_name = runtime.agents[agent_id].agent._a2a_card["name"]
                print(f"  - Deregistering {agent_name}...")
                await runtime.deregister_agent(agent_id)
                print(f"    ✓ {agent_name} removed from pool")

            # Register replacement agent
            print("\n  - Registering replacement agent...")
            replacement_agent = create_stable_agent()
            replacement_agent._a2a_card["name"] = "ReplacementAgent"
            replacement_id = await runtime.register_agent(replacement_agent)
            print("    ✓ ReplacementAgent added to pool")
        else:
            print("\nAll agents healthy - no replacement needed")

        # Final health summary
        print("\n" + "=" * 70)
        print("Final Health Summary:")
        print("=" * 70)
        print(f"Total agents: {len(runtime.agents)}")
        active_count = sum(
            1 for meta in runtime.agents.values() if meta.status == AgentStatus.ACTIVE
        )
        unhealthy_count = sum(
            1
            for meta in runtime.agents.values()
            if meta.status == AgentStatus.UNHEALTHY
        )
        degraded_count = sum(
            1 for meta in runtime.agents.values() if meta.status == AgentStatus.DEGRADED
        )

        print(f"  - Active: {active_count}")
        print(f"  - Unhealthy: {unhealthy_count}")
        print(f"  - Degraded: {degraded_count}")

        # Clean up
        print("\n" + "=" * 70)
        print("Cleanup:")
        print("=" * 70)
        agent_ids = list(runtime.agents.keys())
        for agent_id in agent_ids:
            await runtime.deregister_agent(agent_id)
        print(f"✓ Deregistered all agents (remaining: {len(runtime.agents)})")

    finally:
        # Shutdown runtime
        await runtime.shutdown()
        print("\n✓ Runtime shutdown complete")


if __name__ == "__main__":
    print("=" * 70)
    print("Health Monitoring and Failure Recovery Demo")
    print("=" * 70)
    print("\nThis demo uses OpenAI gpt-5-nano-2025-08-07 for health checks")
    print("Estimated cost: ~$0.01 or less")
    print("\nRequires OPENAI_API_KEY in .env file")
    print("=" * 70)

    asyncio.run(main())
