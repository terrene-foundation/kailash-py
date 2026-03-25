"""
Basic Distributed Agent Coordination with AgentRegistry.

Demonstrates:
- Multi-runtime agent registration
- Cross-runtime agent discovery
- Event broadcasting across runtimes
- Basic distributed coordination patterns

Use case: Distributed multi-agent systems spanning multiple processes/machines.
Cost: $0 (uses Ollama)
"""

import asyncio

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.orchestration import (
    AgentRegistry,
    AgentRegistryConfig,
    AgentStatus,
    RegistryEventType,
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
# Main Coordination
# ============================================================================


async def main():
    """Demonstrate basic distributed agent coordination."""

    # Configure registry
    config = AgentRegistryConfig(
        enable_heartbeat_monitoring=True,
        heartbeat_timeout=30.0,  # seconds
        auto_deregister_timeout=60.0,  # seconds
        enable_event_broadcasting=True,
        event_queue_size=100,
    )

    # Create registry
    registry = AgentRegistry(config=config)
    await registry.start()

    try:
        # Create agents
        code_agent = create_code_agent()
        data_agent = create_data_agent()
        writing_agent = create_writing_agent()

        # Simulate distributed registration from multiple runtimes
        print("=" * 70)
        print("Registering agents from different runtimes...")
        print("=" * 70)

        # Runtime 1: Code and Data agents
        code_id = await registry.register_agent(code_agent, runtime_id="runtime_1")
        data_id = await registry.register_agent(data_agent, runtime_id="runtime_1")

        # Runtime 2: Writing agent
        writing_id = await registry.register_agent(
            writing_agent, runtime_id="runtime_2"
        )

        print(f"\n✓ Registered {len(registry.agents)} agents across 2 runtimes:")
        print(
            f"  Runtime 1: {code_agent._a2a_card['name']}, {data_agent._a2a_card['name']}"
        )
        print(f"  Runtime 2: {writing_agent._a2a_card['name']}")

        # Verify multi-runtime registration
        print("\n" + "=" * 70)
        print("Runtime Distribution:")
        print("=" * 70)
        for runtime_id, agent_ids in registry.runtime_agents.items():
            print(f"\n{runtime_id}: {len(agent_ids)} agents")
            for agent_id in agent_ids:
                metadata = registry.agents[agent_id]
                print(f"  - {metadata.agent._a2a_card['name']} ({agent_id})")

        # Cross-runtime capability discovery
        print("\n" + "=" * 70)
        print("Cross-Runtime Capability Discovery:")
        print("=" * 70)

        # Find code agents across all runtimes
        code_agents = await registry.find_agents_by_capability(
            "code generation",
            status_filter=AgentStatus.ACTIVE,
        )

        print("\nSearching for 'code generation':")
        print(f"  Found {len(code_agents)} agents")
        for metadata in code_agents:
            agent_name = metadata.agent._a2a_card["name"]
            runtime = metadata.runtime_id
            print(f"  - {agent_name} on {runtime}")

        # Find data agents
        data_agents = await registry.find_agents_by_capability(
            "data analysis",
            status_filter=AgentStatus.ACTIVE,
        )

        print("\nSearching for 'data analysis':")
        print(f"  Found {len(data_agents)} agents")
        for metadata in data_agents:
            agent_name = metadata.agent._a2a_card["name"]
            runtime = metadata.runtime_id
            print(f"  - {agent_name} on {runtime}")

        # Find writing agents
        writing_agents = await registry.find_agents_by_capability(
            "content writing",
            status_filter=AgentStatus.ACTIVE,
        )

        print("\nSearching for 'content writing':")
        print(f"  Found {len(writing_agents)} agents")
        for metadata in writing_agents:
            agent_name = metadata.agent._a2a_card["name"]
            runtime = metadata.runtime_id
            print(f"  - {agent_name} on {runtime}")

        # Event broadcasting demonstration
        print("\n" + "=" * 70)
        print("Event Broadcasting Across Runtimes:")
        print("=" * 70)

        # Track events
        events_received = []

        async def event_subscriber():
            """Subscribe to registry events."""
            while len(events_received) < 6:  # Wait for expected events
                event = await registry.get_event()
                if event:
                    events_received.append(event)
                else:
                    await asyncio.sleep(0.1)

        # Start event subscriber
        subscriber_task = asyncio.create_task(event_subscriber())

        # Perform operations that generate events
        await registry.update_agent_heartbeat(code_id)
        await asyncio.sleep(0.1)

        await registry.update_agent_status(data_id, AgentStatus.DEGRADED)
        await asyncio.sleep(0.1)

        await registry.update_agent_status(data_id, AgentStatus.ACTIVE)
        await asyncio.sleep(0.1)

        # Wait for events
        await asyncio.sleep(1.0)

        # Cancel subscriber
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        # Display events
        print(f"\nReceived {len(events_received)} events:")
        for i, event in enumerate(events_received, 1):
            print(f"{i}. {event.event_type.value}: {event.metadata}")

        # Registry statistics
        print("\n" + "=" * 70)
        print("Registry Statistics:")
        print("=" * 70)
        print(f"  Total agents: {len(registry.agents)}")
        print(f"  Active runtimes: {len(registry.runtime_agents)}")
        print(f"  Event queue size: {registry._event_queue.qsize()}")

        # Cleanup
        print("\n" + "=" * 70)
        print("Cleanup:")
        print("=" * 70)

        # Deregister agents
        await registry.deregister_agent(code_id, runtime_id="runtime_1")
        await registry.deregister_agent(data_id, runtime_id="runtime_1")
        await registry.deregister_agent(writing_id, runtime_id="runtime_2")

        print(f"✓ Deregistered all agents (remaining: {len(registry.agents)})")

    finally:
        # Shutdown registry
        await registry.shutdown()
        print("\n✓ Registry shutdown complete")


if __name__ == "__main__":
    print("=" * 70)
    print("Basic Distributed Agent Coordination Demo")
    print("=" * 70)
    print("\nThis demo uses Ollama llama3.2:1b (free)")
    print("Cost: $0")
    print("\nRequires Ollama running with llama3.2:1b model")
    print("=" * 70)
    print()

    asyncio.run(main())
