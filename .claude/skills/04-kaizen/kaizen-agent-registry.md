# AgentRegistry - Distributed Agent Coordination

Centralized lifecycle management for distributed multi-agent systems (100+ agents). O(1) capability discovery, event broadcasting, heartbeat health monitoring, automatic failover.

**Location**: `kaizen.orchestration.registry` | **Tests**: 27 unit + 12 integration + 6 E2E (100% coverage)

## Quick Start

```python
from kaizen_agents.patterns import AgentRegistry, AgentRegistryConfig, RegistryEventType, AgentStatus

config = AgentRegistryConfig(
    enable_heartbeat_monitoring=True,
    heartbeat_timeout=30.0,
    auto_deregister_timeout=60.0,
    enable_event_broadcasting=True,
    event_queue_size=100,
)

registry = AgentRegistry(config=config)
await registry.start()

agent_id = await registry.register_agent(my_agent, runtime_id="runtime_1")

# O(1) capability discovery
agents = await registry.find_agents_by_capability("code generation", status_filter=AgentStatus.ACTIVE)

# Event-driven coordination
async def event_callback(event):
    print(f"Event: {event.event_type} for agent {event.agent_id}")

registry.subscribe(RegistryEventType.AGENT_STATUS_CHANGED, event_callback)

await registry.update_agent_heartbeat(agent_id)
await registry.deregister_agent(agent_id, runtime_id="runtime_1")
await registry.shutdown()
```

## Runtime Tracking

```python
agent_id_1 = await registry.register_agent(agent1, runtime_id="runtime_1")
agent_id_2 = await registry.register_agent(agent2, runtime_id="runtime_1")
agent_id_3 = await registry.register_agent(agent3, runtime_id="runtime_2")

runtime_1_agents = registry.runtime_agents["runtime_1"]  # {agent_id_1, agent_id_2}
runtime_2_agents = registry.runtime_agents["runtime_2"]  # {agent_id_3}
```

Events: `RUNTIME_JOINED` on first agent from runtime, `RUNTIME_LEFT` on last deregister.

## Capability Discovery

O(1) semantic substring matching (case-insensitive) with status filtering:

```python
code_agents = await registry.find_agents_by_capability("code generation")
healthy_only = await registry.find_agents_by_capability("code generation", status_filter=AgentStatus.ACTIVE)
all_statuses = await registry.find_agents_by_capability("code generation", status_filter=None)
```

Returns `List[AgentMetadata]`:

```python
for m in agents:
    m.agent_id       # Unique ID
    m.agent           # BaseAgent instance
    m.status          # AgentStatus
    m.last_heartbeat  # datetime
    m.agent._a2a_card # A2A capability card
```

## Event Broadcasting

6 event types for cross-runtime coordination:

| Event                  | Trigger                  |
| ---------------------- | ------------------------ |
| `AGENT_REGISTERED`     | Agent added              |
| `AGENT_DEREGISTERED`   | Agent removed            |
| `AGENT_STATUS_CHANGED` | Status updated           |
| `AGENT_HEARTBEAT`      | Heartbeat sent           |
| `RUNTIME_JOINED`       | First agent from runtime |
| `RUNTIME_LEFT`         | Last agent from runtime  |

```python
async def handler(event):
    print(f"{event.event_type} | agent={event.agent_id} | runtime={event.runtime_id}")

registry.subscribe(RegistryEventType.AGENT_REGISTERED, handler)
registry.subscribe(RegistryEventType.AGENT_STATUS_CHANGED, handler)
```

## Health Monitoring

| Status      | Meaning               |
| ----------- | --------------------- |
| `ACTIVE`    | Healthy, available    |
| `UNHEALTHY` | Failed health checks  |
| `DEGRADED`  | Partial functionality |
| `OFFLINE`   | Disconnected          |

```python
await registry.update_agent_heartbeat(agent_id)
await registry.update_agent_status(agent_id, AgentStatus.DEGRADED)
```

Auto-deregistration flow: missed heartbeat (30s default) -> `UNHEALTHY` -> deregister (60s default). Unhealthy agents excluded from `ACTIVE`-filtered discovery. Recovery: update status back to `ACTIVE`.

## Production Patterns

### Distributed Coordination

```python
code_id = await registry.register_agent(code_agent, runtime_id="runtime_1")
data_id = await registry.register_agent(data_agent, runtime_id="runtime_1")
writing_id = await registry.register_agent(writing_agent, runtime_id="runtime_2")

agents = await registry.find_agents_by_capability("code generation")  # Cross-runtime
```

### Fault Tolerance & Failover

```python
config = AgentRegistryConfig(
    enable_heartbeat_monitoring=True,
    heartbeat_timeout=10.0,
    auto_deregister_timeout=20.0,
)
registry = AgentRegistry(config=config)
await registry.start()

primary_id = await registry.register_agent(primary, runtime_id="prod_1")
backup_id = await registry.register_agent(backup, runtime_id="prod_2")

# Primary fails
await registry.update_agent_status(primary_id, AgentStatus.UNHEALTHY)

# Failover: only backup returned
healthy = await registry.find_agents_by_capability("task processing", status_filter=AgentStatus.ACTIVE)
result = healthy[0].agent.run(task="Process critical task")

# Recovery
await registry.update_agent_status(primary_id, AgentStatus.ACTIVE)
```

## Heartbeat Intervals

| Interval | Use Case                                 |
| -------- | ---------------------------------------- |
| 10-30s   | Critical systems, fast failure detection |
| 30-60s   | Standard production                      |
| 60-300s  | Long-running, infrequent tasks           |

Rule: `auto_deregister_timeout` = 2-3x `heartbeat_timeout`.

## OrchestrationRuntime vs AgentRegistry

| Aspect  | OrchestrationRuntime        | AgentRegistry             |
| ------- | --------------------------- | ------------------------- |
| Scale   | 10-100 agents               | 100+ agents               |
| Scope   | Single-process              | Distributed multi-runtime |
| Routing | Semantic/round-robin/random | O(1) capability index     |
| Health  | Real LLM inference          | Heartbeat-based           |
| Budget  | Per-agent + runtime-wide    | N/A                       |

Use both together:

```python
runtime = OrchestrationRuntime(config=runtime_config)
registry = AgentRegistry(config=registry_config)

agent_id = await runtime.register_agent(agent)
await registry.register_agent(agent, runtime_id="runtime_1")

selected = await runtime.route_task(task, strategy=RoutingStrategy.SEMANTIC)  # Local
all_agents = await registry.find_agents_by_capability("code generation")       # Global
```

## Resources

- **Examples**: `examples/orchestration/agent-registry-patterns/` (3 patterns)
- **Tests**: `tests/e2e/orchestration/test_agent_registry_e2e.py`
- **Source**: `src/kaizen/orchestration/registry.py`
- **Related**: [kaizen-supervisor-worker](kaizen-supervisor-worker.md), [kaizen-multi-agent-setup](kaizen-multi-agent-setup.md), [kaizen-a2a-protocol](kaizen-a2a-protocol.md), [kaizen-observability-hooks](kaizen-observability-hooks.md)
