"""
Basic Multi-Agent Task Distribution with OrchestrationRuntime.

Demonstrates:
- Agent registration and lifecycle management
- Round-robin task distribution across multiple agents
- Concurrent task routing
- Basic orchestration patterns

Use case: Simple workload balancing across a pool of agents.
Cost: $0 (uses Ollama)
"""

import asyncio

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.orchestration import (
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
# Create Specialized Agents
# ============================================================================


def create_code_agent():
    """Create code generation agent with Ollama."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # Set A2A capability card
    agent._a2a_card = {
        "name": "CodeAgent",
        "capability": "Code generation and software development",
        "description": "Generate Python, JavaScript, and other programming code",
    }

    return agent


def create_data_agent():
    """Create data analysis agent with Ollama."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # Set A2A capability card
    agent._a2a_card = {
        "name": "DataAgent",
        "capability": "Data analysis and visualization",
        "description": "Analyze datasets and create visualizations",
    }

    return agent


def create_writing_agent():
    """Create content writing agent with Ollama."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    # Set A2A capability card
    agent._a2a_card = {
        "name": "WritingAgent",
        "capability": "Content writing and editing",
        "description": "Write articles, documentation, and marketing content",
    }

    return agent


# ============================================================================
# Main Orchestration
# ============================================================================


async def main():
    """Demonstrate basic multi-agent task distribution."""

    # Configure runtime
    config = OrchestrationRuntimeConfig(
        max_concurrent_agents=5,
        enable_health_monitoring=True,
        health_check_interval=10.0,  # seconds
    )

    # Create runtime
    runtime = OrchestrationRuntime(config=config)
    await runtime.start()

    try:
        # Create agents
        code_agent = create_code_agent()
        data_agent = create_data_agent()
        writing_agent = create_writing_agent()

        # Register agents
        print("Registering agents...")
        code_id = await runtime.register_agent(code_agent)
        data_id = await runtime.register_agent(data_agent)
        writing_id = await runtime.register_agent(writing_agent)

        print(f"✓ Registered {len(runtime.agents)} agents")
        print(f"  - {code_agent._a2a_card['name']}")
        print(f"  - {data_agent._a2a_card['name']}")
        print(f"  - {writing_agent._a2a_card['name']}")

        # Route tasks using round-robin strategy
        print("\nRouting tasks with round-robin strategy...")
        tasks = [
            "Generate hello world program",
            "Analyze sales data",
            "Write blog post introduction",
            "Create sorting algorithm",
            "Calculate statistics",
            "Edit article for clarity",
        ]

        routing_tasks = [
            runtime.route_task(task, strategy=RoutingStrategy.ROUND_ROBIN)
            for task in tasks
        ]

        # Execute all routing concurrently
        selected_agents = await asyncio.gather(*routing_tasks)

        # Display routing results
        print("\nRouting Results:")
        for i, (task, agent) in enumerate(zip(tasks, selected_agents), 1):
            agent_name = agent._a2a_card["name"]
            print(f"{i}. '{task}' → {agent_name}")

        # Verify round-robin distribution
        print("\nDistribution Summary:")
        from collections import Counter

        distribution = Counter(agent._a2a_card["name"] for agent in selected_agents)
        for agent_name, count in distribution.items():
            print(f"  {agent_name}: {count} tasks")

        # Clean up: deregister agents
        print("\nDeregistering agents...")
        await runtime.deregister_agent(code_id)
        await runtime.deregister_agent(data_id)
        await runtime.deregister_agent(writing_id)

        print(f"✓ Deregistered all agents (remaining: {len(runtime.agents)})")

    finally:
        # Shutdown runtime
        await runtime.shutdown()
        print("\n✓ Runtime shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
