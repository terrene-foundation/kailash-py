"""
Advanced Capability Discovery and Event-Driven Coordination.

Demonstrates:
- Semantic capability-based agent discovery
- O(1) capability indexing for fast lookups
- Event subscription and coordination
- Status filtering for healthy agents
- Runtime join/leave event handling

Use case: Large-scale multi-agent systems requiring intelligent agent selection.
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


def create_python_expert():
    """Create Python code generation expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "PythonExpert",
        "capability": "Python code generation and debugging",
        "description": "Expert in Python programming, data structures, and algorithms",
    }

    return agent


def create_javascript_expert():
    """Create JavaScript code generation expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "JavaScriptExpert",
        "capability": "JavaScript and frontend development",
        "description": "Expert in JavaScript, React, Node.js, and web development",
    }

    return agent


def create_data_scientist():
    """Create data science and ML expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "DataScientist",
        "capability": "Data analysis and machine learning",
        "description": "Expert in statistics, data visualization, and ML algorithms",
    }

    return agent


def create_devops_engineer():
    """Create DevOps and infrastructure expert."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        temperature=0.7,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "DevOpsEngineer",
        "capability": "Infrastructure and deployment automation",
        "description": "Expert in Docker, Kubernetes, CI/CD, and cloud platforms",
    }

    return agent


# ============================================================================
# Main Coordination
# ============================================================================


async def main():
    """Demonstrate advanced capability discovery and event coordination."""

    # Configure registry with capability indexing
    config = AgentRegistryConfig(
        enable_heartbeat_monitoring=True,
        heartbeat_timeout=30.0,
        auto_deregister_timeout=60.0,
        enable_event_broadcasting=True,
        event_queue_size=200,
    )

    # Create registry
    registry = AgentRegistry(config=config)
    await registry.start()

    try:
        # Create specialized agents
        python_expert = create_python_expert()
        js_expert = create_javascript_expert()
        data_scientist = create_data_scientist()
        devops_engineer = create_devops_engineer()

        # Set up event tracking
        events_received = []

        async def event_monitor():
            """Monitor registry events."""
            while True:
                event = await registry.get_event()
                if event:
                    events_received.append(event)
                    print(
                        f"[EVENT] {event.event_type.value}: {event.agent_id or event.runtime_id}"
                    )
                else:
                    await asyncio.sleep(0.1)

        # Start event monitor in background
        monitor_task = asyncio.create_task(event_monitor())

        # Register agents from different runtimes
        print("=" * 70)
        print("Registering Specialized Agents...")
        print("=" * 70)

        # Runtime 1: Development agents
        python_id = await registry.register_agent(
            python_expert, runtime_id="dev_runtime_1"
        )
        js_id = await registry.register_agent(js_expert, runtime_id="dev_runtime_1")

        # Runtime 2: Analytics agents
        data_id = await registry.register_agent(
            data_scientist, runtime_id="analytics_runtime_2"
        )

        # Runtime 3: Infrastructure agents
        devops_id = await registry.register_agent(
            devops_engineer, runtime_id="infra_runtime_3"
        )

        await asyncio.sleep(0.5)  # Allow events to process

        print(
            f"\n✓ Registered {len(registry.agents)} specialized agents across 3 runtimes"
        )

        # Demonstrate capability-based discovery
        print("\n" + "=" * 70)
        print("Capability-Based Agent Discovery (O(1) Lookup):")
        print("=" * 70)

        # Search for code generation capabilities
        code_tasks = [
            ("Python code generation", "python"),
            ("JavaScript development", "javascript"),
            ("Machine learning", "machine learning"),
            ("Docker deployment", "docker"),
        ]

        for task, capability_query in code_tasks:
            # O(1) capability lookup via index
            agents = await registry.find_agents_by_capability(
                capability_query,
                status_filter=AgentStatus.ACTIVE,
            )

            print(f"\nTask: '{task}'")
            print(f"  Query: '{capability_query}'")
            if agents:
                for metadata in agents:
                    agent_name = metadata.agent._a2a_card["name"]
                    capability = metadata.agent._a2a_card["capability"]
                    runtime = metadata.runtime_id
                    print(f"  ✓ Found: {agent_name}")
                    print(f"    - Capability: {capability}")
                    print(f"    - Runtime: {runtime}")
            else:
                print("  ✗ No matching agents found")

        # Demonstrate status-based filtering
        print("\n" + "=" * 70)
        print("Status-Based Filtering:")
        print("=" * 70)

        # Mark one agent as degraded
        await registry.update_agent_status(python_id, AgentStatus.DEGRADED)
        print("\n✓ Marked PythonExpert as DEGRADED")

        await asyncio.sleep(0.2)

        # Search with status filter
        print("\nSearching for 'python' with ACTIVE filter:")
        active_python = await registry.find_agents_by_capability(
            "python",
            status_filter=AgentStatus.ACTIVE,
        )
        print(f"  Found {len(active_python)} ACTIVE agents")

        print("\nSearching for 'python' with DEGRADED filter:")
        degraded_python = await registry.find_agents_by_capability(
            "python",
            status_filter=AgentStatus.DEGRADED,
        )
        print(f"  Found {len(degraded_python)} DEGRADED agents")

        print("\nSearching for 'python' with no status filter:")
        all_python = await registry.find_agents_by_capability(
            "python",
            status_filter=None,
        )
        print(f"  Found {len(all_python)} total agents")

        # Restore agent status
        await registry.update_agent_status(python_id, AgentStatus.ACTIVE)
        print("\n✓ Restored PythonExpert to ACTIVE")

        await asyncio.sleep(0.2)

        # Demonstrate concurrent capability searches
        print("\n" + "=" * 70)
        print("Concurrent Capability Searches:")
        print("=" * 70)

        # Launch multiple searches concurrently
        search_queries = [
            "python",
            "javascript",
            "data",
            "deployment",
            "code",
            "analysis",
        ]

        import time

        start_time = time.time()

        search_tasks = [
            registry.find_agents_by_capability(query, status_filter=AgentStatus.ACTIVE)
            for query in search_queries
        ]

        results = await asyncio.gather(*search_tasks)
        search_time = time.time() - start_time

        print(
            f"\n✓ Completed {len(search_queries)} concurrent searches in {search_time:.3f}s"
        )
        for query, agents in zip(search_queries, results):
            print(f"  '{query}': {len(agents)} agents")

        # Event summary
        print("\n" + "=" * 70)
        print("Event Summary:")
        print("=" * 70)

        # Wait for pending events
        await asyncio.sleep(1.0)

        # Stop monitor
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # Analyze events
        print(f"\nReceived {len(events_received)} events:")

        from collections import Counter

        event_counts = Counter(e.event_type for e in events_received)

        for event_type, count in event_counts.items():
            print(f"  {event_type.value}: {count}")

        # Verify runtime join/leave events
        runtime_joined = [
            e
            for e in events_received
            if e.event_type == RegistryEventType.RUNTIME_JOINED
        ]
        print(f"\n✓ Detected {len(runtime_joined)} runtime joins:")
        for event in runtime_joined:
            print(f"  - {event.runtime_id}")

        # Cleanup
        print("\n" + "=" * 70)
        print("Cleanup:")
        print("=" * 70)

        # Deregister agents
        await registry.deregister_agent(python_id, runtime_id="dev_runtime_1")
        await registry.deregister_agent(js_id, runtime_id="dev_runtime_1")
        await registry.deregister_agent(data_id, runtime_id="analytics_runtime_2")
        await registry.deregister_agent(devops_id, runtime_id="infra_runtime_3")

        await asyncio.sleep(0.5)

        # Verify runtime leave events
        runtime_left = [
            e for e in events_received if e.event_type == RegistryEventType.RUNTIME_LEFT
        ]
        print(f"\n✓ Detected {len(runtime_left)} runtime leaves:")
        for event in runtime_left:
            print(f"  - {event.runtime_id}")

        print(f"\n✓ Deregistered all agents (remaining: {len(registry.agents)})")

    finally:
        # Shutdown registry
        await registry.shutdown()
        print("\n✓ Registry shutdown complete")


if __name__ == "__main__":
    print("=" * 70)
    print("Advanced Capability Discovery Demo")
    print("=" * 70)
    print("\nThis demo uses Ollama llama3.2:1b (free)")
    print("Cost: $0")
    print("\nRequires Ollama running with llama3.2:1b model")
    print("=" * 70)
    print()

    asyncio.run(main())
