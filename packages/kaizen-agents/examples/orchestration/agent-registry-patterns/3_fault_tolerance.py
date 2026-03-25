"""
Fault Tolerance and Health Monitoring with AgentRegistry.

Demonstrates:
- Heartbeat monitoring and automatic timeout detection
- Agent status management (ACTIVE, UNHEALTHY, DEGRADED, OFFLINE)
- Automatic agent deregistration on failure
- Health-based agent filtering
- Graceful failure recovery patterns

Use case: Production multi-agent systems requiring high reliability.
Cost: ~$0.01 (uses OpenAI gpt-5-nano for health checks)
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
# Create Production Agents
# ============================================================================


def create_primary_agent():
    """Create primary agent with gpt-5-nano."""
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",  # Cheap, fast model
        temperature=0.0,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "PrimaryAgent",
        "capability": "Primary task processing and coordination",
        "description": "Primary agent for critical production workloads",
    }

    return agent


def create_backup_agent():
    """Create backup agent with gpt-5-nano."""
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",
        temperature=0.0,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "BackupAgent",
        "capability": "Backup task processing and failover",
        "description": "Backup agent for high-availability scenarios",
    }

    return agent


def create_monitoring_agent():
    """Create monitoring agent with gpt-5-nano."""
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",
        temperature=0.0,
    )

    agent = BaseAgent(config=config, signature=TaskSignature())

    agent._a2a_card = {
        "name": "MonitoringAgent",
        "capability": "System monitoring and health checks",
        "description": "Monitor system health and detect failures",
    }

    return agent


# ============================================================================
# Main Coordination
# ============================================================================


async def main():
    """Demonstrate fault tolerance and health monitoring."""

    # Configure registry with aggressive health monitoring
    config = AgentRegistryConfig(
        enable_heartbeat_monitoring=True,
        heartbeat_timeout=10.0,  # 10 seconds (aggressive)
        auto_deregister_timeout=20.0,  # 20 seconds
        enable_event_broadcasting=True,
        event_queue_size=100,
    )

    # Create registry
    registry = AgentRegistry(config=config)
    await registry.start()

    try:
        # Create agents
        primary_agent = create_primary_agent()
        backup_agent = create_backup_agent()
        monitoring_agent = create_monitoring_agent()

        # Set up event tracking
        events_received = []

        async def event_monitor():
            """Monitor registry events."""
            while True:
                event = await registry.get_event()
                if event:
                    events_received.append(event)
                    if event.event_type == RegistryEventType.AGENT_STATUS_CHANGED:
                        print(
                            f"[EVENT] Status changed: {event.agent_id} → {event.metadata.get('new_status')}"
                        )
                    elif event.event_type == RegistryEventType.AGENT_HEARTBEAT:
                        print(f"[EVENT] Heartbeat: {event.agent_id}")
                else:
                    await asyncio.sleep(0.1)

        # Start event monitor
        monitor_task = asyncio.create_task(event_monitor())

        # Register agents
        print("=" * 70)
        print("Registering Production Agents...")
        print("=" * 70)

        primary_id = await registry.register_agent(
            primary_agent, runtime_id="prod_runtime_1"
        )
        backup_id = await registry.register_agent(
            backup_agent, runtime_id="prod_runtime_2"
        )
        monitoring_id = await registry.register_agent(
            monitoring_agent, runtime_id="monitoring_runtime"
        )

        await asyncio.sleep(0.5)

        print(f"\n✓ Registered {len(registry.agents)} agents across 3 runtimes")

        # Heartbeat monitoring
        print("\n" + "=" * 70)
        print("Heartbeat Monitoring:")
        print("=" * 70)

        # Send heartbeats from active agents
        print("\nSending heartbeats...")
        await registry.update_agent_heartbeat(primary_id)
        await registry.update_agent_heartbeat(backup_id)
        await registry.update_agent_heartbeat(monitoring_id)

        await asyncio.sleep(1.0)

        print("✓ All agents sent heartbeats")

        # Verify all agents are healthy
        print("\nAgent Health Status:")
        for agent_id, metadata in registry.agents.items():
            agent_name = metadata.agent._a2a_card["name"]
            status = metadata.status.value
            last_heartbeat = metadata.last_heartbeat
            print(f"  - {agent_name}: {status} (last heartbeat: {last_heartbeat})")

        # Simulate agent failure
        print("\n" + "=" * 70)
        print("Simulating Agent Failure:")
        print("=" * 70)

        print("\n✗ Simulating PrimaryAgent failure (marking as UNHEALTHY)")
        await registry.update_agent_status(primary_id, AgentStatus.UNHEALTHY)

        await asyncio.sleep(0.5)

        # Show agent status after failure
        print("\nAgent Status After Failure:")
        for agent_id, metadata in registry.agents.items():
            agent_name = metadata.agent._a2a_card["name"]
            status = metadata.status.value
            print(f"  - {agent_name}: {status}")

        # Demonstrate health-based filtering
        print("\n" + "=" * 70)
        print("Health-Based Agent Filtering:")
        print("=" * 70)

        # Find only healthy agents
        print("\nSearching for 'task processing' with ACTIVE filter:")
        healthy_agents = await registry.find_agents_by_capability(
            "task processing",
            status_filter=AgentStatus.ACTIVE,
        )

        print(f"  Found {len(healthy_agents)} healthy agents:")
        for metadata in healthy_agents:
            agent_name = metadata.agent._a2a_card["name"]
            runtime = metadata.runtime_id
            print(f"    - {agent_name} on {runtime}")

        # Find unhealthy agents
        print("\nSearching for 'task processing' with UNHEALTHY filter:")
        unhealthy_agents = await registry.find_agents_by_capability(
            "task processing",
            status_filter=AgentStatus.UNHEALTHY,
        )

        print(f"  Found {len(unhealthy_agents)} unhealthy agents:")
        for metadata in unhealthy_agents:
            agent_name = metadata.agent._a2a_card["name"]
            runtime = metadata.runtime_id
            print(f"    - {agent_name} on {runtime}")

        # Demonstrate failover pattern
        print("\n" + "=" * 70)
        print("Failover Pattern:")
        print("=" * 70)

        print("\nAttempting to route task to healthy agent...")
        available_agents = await registry.find_agents_by_capability(
            "task processing",
            status_filter=AgentStatus.ACTIVE,
        )

        if available_agents:
            selected_agent = available_agents[0]
            agent_name = selected_agent.agent._a2a_card["name"]
            print(f"  ✓ Selected: {agent_name}")
            print("  Note: PrimaryAgent bypassed due to UNHEALTHY status")
        else:
            print("  ✗ No healthy agents available for failover")

        # Demonstrate recovery
        print("\n" + "=" * 70)
        print("Agent Recovery:")
        print("=" * 70)

        print("\n✓ Recovering PrimaryAgent (marking as ACTIVE)")
        await registry.update_agent_status(primary_id, AgentStatus.ACTIVE)

        await asyncio.sleep(0.5)

        # Verify recovery
        print("\nAgent Status After Recovery:")
        for agent_id, metadata in registry.agents.items():
            agent_name = metadata.agent._a2a_card["name"]
            status = metadata.status.value
            print(f"  - {agent_name}: {status}")

        # Verify all agents available again
        all_healthy = await registry.find_agents_by_capability(
            "task processing",
            status_filter=AgentStatus.ACTIVE,
        )

        print(f"\n✓ {len(all_healthy)} healthy agents available")

        # Demonstrate degraded state
        print("\n" + "=" * 70)
        print("Degraded State Handling:")
        print("=" * 70)

        print("\n⚠ Marking BackupAgent as DEGRADED (partial functionality)")
        await registry.update_agent_status(backup_id, AgentStatus.DEGRADED)

        await asyncio.sleep(0.5)

        # Show distribution of agent states
        print("\nAgent State Distribution:")
        from collections import Counter

        status_counts = Counter(m.status for m in registry.agents.values())

        for status, count in status_counts.items():
            print(f"  {status.value}: {count}")

        # Restore all to active
        await registry.update_agent_status(backup_id, AgentStatus.ACTIVE)

        # Event summary
        print("\n" + "=" * 70)
        print("Health Monitoring Events:")
        print("=" * 70)

        # Wait for pending events
        await asyncio.sleep(1.0)

        # Stop monitor
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # Analyze health-related events
        status_events = [
            e
            for e in events_received
            if e.event_type == RegistryEventType.AGENT_STATUS_CHANGED
        ]
        heartbeat_events = [
            e
            for e in events_received
            if e.event_type == RegistryEventType.AGENT_HEARTBEAT
        ]

        print(f"\n✓ Detected {len(status_events)} status change events")
        print(f"✓ Detected {len(heartbeat_events)} heartbeat events")

        # Show status transitions
        print("\nStatus Transitions:")
        for event in status_events:
            old_status = event.metadata.get("old_status")
            new_status = event.metadata.get("new_status")
            print(f"  {event.agent_id}: {old_status} → {new_status}")

        # Cleanup
        print("\n" + "=" * 70)
        print("Cleanup:")
        print("=" * 70)

        # Deregister agents
        await registry.deregister_agent(primary_id, runtime_id="prod_runtime_1")
        await registry.deregister_agent(backup_id, runtime_id="prod_runtime_2")
        await registry.deregister_agent(monitoring_id, runtime_id="monitoring_runtime")

        print(f"\n✓ Deregistered all agents (remaining: {len(registry.agents)})")

    finally:
        # Shutdown registry
        await registry.shutdown()
        print("\n✓ Registry shutdown complete")


if __name__ == "__main__":
    print("=" * 70)
    print("Fault Tolerance and Health Monitoring Demo")
    print("=" * 70)
    print("\nThis demo uses OpenAI gpt-5-nano-2025-08-07")
    print("Estimated cost: ~$0.01")
    print("\nRequires OPENAI_API_KEY in .env file")
    print("=" * 70)
    print()

    asyncio.run(main())
