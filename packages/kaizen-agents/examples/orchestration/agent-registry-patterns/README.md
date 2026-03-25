# Agent Registry Patterns

Production-ready patterns demonstrating distributed multi-agent coordination with the AgentRegistry system.

## Overview

AgentRegistry provides centralized agent lifecycle management for distributed multi-agent systems with:
- Multi-runtime agent coordination
- O(1) capability-based discovery with semantic matching
- Event broadcasting for cross-runtime communication
- Heartbeat monitoring and automatic failure detection
- Status management (ACTIVE, UNHEALTHY, DEGRADED, OFFLINE)
- Automatic agent deregistration on timeout

## Patterns

### 1. Basic Distributed Agent Coordination

**File**: `1_basic_distributed_coordination.py`

Demonstrates fundamental distributed coordination patterns with multi-runtime agent management.

**Features**:
- Agent registration from multiple runtimes
- Cross-runtime capability discovery
- Event broadcasting across distributed systems
- Basic lifecycle management

**Use Case**: Distributed multi-agent systems spanning multiple processes or machines

**Cost**: $0 (uses Ollama llama3.2:1b)

```bash
python 1_basic_distributed_coordination.py
```

**Expected Output**:
```
======================================================================
Registering agents from different runtimes...
======================================================================

✓ Registered 3 agents across 2 runtimes:
  Runtime 1: CodeAgent, DataAgent
  Runtime 2: WritingAgent

======================================================================
Runtime Distribution:
======================================================================

runtime_1: 2 agents
  - CodeAgent (agent_123456)
  - DataAgent (agent_234567)

runtime_2: 1 agents
  - WritingAgent (agent_345678)

======================================================================
Cross-Runtime Capability Discovery:
======================================================================

Searching for 'code generation':
  Found 1 agents
  - CodeAgent on runtime_1

Searching for 'data analysis':
  Found 1 agents
  - DataAgent on runtime_1

Searching for 'content writing':
  Found 1 agents
  - WritingAgent on runtime_2
```

---

### 2. Advanced Capability Discovery and Event-Driven Coordination

**File**: `2_capability_discovery.py`

Demonstrates intelligent agent discovery using O(1) capability indexing and event-driven coordination.

**Features**:
- Semantic capability-based discovery
- O(1) capability lookups via indexing
- Event subscription and monitoring
- Status-based agent filtering
- Runtime join/leave event detection
- Concurrent capability searches

**Use Case**: Large-scale multi-agent systems requiring intelligent agent selection

**Cost**: $0 (uses Ollama llama3.2:1b)

```bash
python 2_capability_discovery.py
```

**Expected Output**:
```
======================================================================
Registering Specialized Agents...
======================================================================
[EVENT] RUNTIME_JOINED: dev_runtime_1
[EVENT] AGENT_REGISTERED: agent_123456
[EVENT] AGENT_REGISTERED: agent_234567
[EVENT] RUNTIME_JOINED: analytics_runtime_2
[EVENT] AGENT_REGISTERED: agent_345678

✓ Registered 4 specialized agents across 3 runtimes

======================================================================
Capability-Based Agent Discovery (O(1) Lookup):
======================================================================

Task: 'Python code generation'
  Query: 'python'
  ✓ Found: PythonExpert
    - Capability: Python code generation and debugging
    - Runtime: dev_runtime_1

Task: 'JavaScript development'
  Query: 'javascript'
  ✓ Found: JavaScriptExpert
    - Capability: JavaScript and frontend development
    - Runtime: dev_runtime_1

======================================================================
Status-Based Filtering:
======================================================================

✓ Marked PythonExpert as DEGRADED
[EVENT] AGENT_STATUS_CHANGED: agent_123456

Searching for 'python' with ACTIVE filter:
  Found 0 ACTIVE agents

Searching for 'python' with DEGRADED filter:
  Found 1 DEGRADED agents

Searching for 'python' with no status filter:
  Found 1 total agents
```

**How Capability Discovery Works**:
1. Registry maintains O(1) capability index mapping capabilities to agents
2. Semantic substring matching (e.g., "python" matches "Python code generation")
3. Status filtering excludes unhealthy agents automatically
4. Concurrent searches leverage async parallelism
5. Events broadcast all discovery operations

---

### 3. Fault Tolerance and Health Monitoring

**File**: `3_fault_tolerance.py`

Demonstrates production-grade fault tolerance with health monitoring and recovery patterns.

**Features**:
- Heartbeat monitoring with configurable timeouts
- Agent status management (ACTIVE → UNHEALTHY → DEGRADED → OFFLINE)
- Automatic agent deregistration on failure
- Health-based agent filtering for failover
- Graceful recovery patterns
- Event-driven health monitoring

**Use Case**: Production multi-agent systems requiring high reliability

**Cost**: ~$0.01 (uses OpenAI gpt-5-nano-2025-08-07)

**Requirements**: `OPENAI_API_KEY` in `.env` file

```bash
python 3_fault_tolerance.py
```

**Expected Output**:
```
======================================================================
Registering Production Agents...
======================================================================
✓ Registered 3 agents across 3 runtimes

======================================================================
Heartbeat Monitoring:
======================================================================

Sending heartbeats...
[EVENT] AGENT_HEARTBEAT: agent_123456
[EVENT] AGENT_HEARTBEAT: agent_234567
[EVENT] AGENT_HEARTBEAT: agent_345678
✓ All agents sent heartbeats

Agent Health Status:
  - PrimaryAgent: active (last heartbeat: 2025-01-06 12:00:00)
  - BackupAgent: active (last heartbeat: 2025-01-06 12:00:00)
  - MonitoringAgent: active (last heartbeat: 2025-01-06 12:00:00)

======================================================================
Simulating Agent Failure:
======================================================================

✗ Simulating PrimaryAgent failure (marking as UNHEALTHY)
[EVENT] AGENT_STATUS_CHANGED: agent_123456 → unhealthy

Agent Status After Failure:
  - PrimaryAgent: unhealthy
  - BackupAgent: active
  - MonitoringAgent: active

======================================================================
Health-Based Agent Filtering:
======================================================================

Searching for 'task processing' with ACTIVE filter:
  Found 1 healthy agents:
    - BackupAgent on prod_runtime_2

Searching for 'task processing' with UNHEALTHY filter:
  Found 1 unhealthy agents:
    - PrimaryAgent on prod_runtime_1

======================================================================
Failover Pattern:
======================================================================

Attempting to route task to healthy agent...
  ✓ Selected: BackupAgent
  Note: PrimaryAgent bypassed due to UNHEALTHY status

======================================================================
Agent Recovery:
======================================================================

✓ Recovering PrimaryAgent (marking as ACTIVE)
[EVENT] AGENT_STATUS_CHANGED: agent_123456 → active

Agent Status After Recovery:
  - PrimaryAgent: active
  - BackupAgent: active
  - MonitoringAgent: active

✓ 2 healthy agents available
```

**Health Monitoring Process**:
1. Registry monitors agent heartbeats at configured intervals (10s default)
2. Agents must send heartbeats within timeout window (10s default)
3. Missed heartbeats trigger status change to UNHEALTHY
4. Auto-deregistration occurs after extended timeout (20s default)
5. Unhealthy agents excluded from capability discovery (ACTIVE filter)
6. Recovery possible by updating status back to ACTIVE

---

## Running the Examples

### Prerequisites

1. **Install dependencies**:
   ```bash
   pip install kailash-kaizen
   ```

2. **Set up environment**:
   - Copy `.env.example` to `.env`
   - Add `OPENAI_API_KEY` for pattern 3

3. **Install Ollama** (for patterns 1 and 2):
   ```bash
   # macOS
   brew install ollama

   # Pull required model
   ollama pull llama3.2:1b
   ```

### Running Patterns

```bash
# Pattern 1: Basic coordination (free)
python 1_basic_distributed_coordination.py

# Pattern 2: Capability discovery (free)
python 2_capability_discovery.py

# Pattern 3: Fault tolerance (~$0.01)
python 3_fault_tolerance.py
```

---

## Key Concepts

### AgentRegistry

Centralized registry for distributed agent coordination:

```python
from kaizen.orchestration import (
    AgentRegistry,
    AgentRegistryConfig,
    RegistryEventType,
    AgentStatus,
)

# Configure registry
config = AgentRegistryConfig(
    enable_heartbeat_monitoring=True,
    heartbeat_timeout=30.0,              # Heartbeat timeout (seconds)
    auto_deregister_timeout=60.0,        # Auto-deregister timeout (seconds)
    enable_event_broadcasting=True,      # Enable event broadcasting
    event_queue_size=100,                # Event queue capacity
)

# Create registry
registry = AgentRegistry(config=config)
await registry.start()

# Register agents from different runtimes
agent_id = await registry.register_agent(my_agent, runtime_id="runtime_1")

# Discover agents by capability
agents = await registry.find_agents_by_capability(
    "code generation",
    status_filter=AgentStatus.ACTIVE
)

# Subscribe to events
async def event_handler():
    event = await registry.get_event()
    print(f"Event: {event.event_type}")

# Update agent status
await registry.update_agent_status(agent_id, AgentStatus.UNHEALTHY)

# Send heartbeat
await registry.update_agent_heartbeat(agent_id)

# Deregister agent
await registry.deregister_agent(agent_id, runtime_id="runtime_1")

# Shutdown
await registry.shutdown()
```

### Capability Discovery

**Semantic Matching**:
- Substring-based matching (e.g., "python" matches "Python code generation")
- Case-insensitive search
- O(1) lookup via capability index

**Status Filtering**:
- `AgentStatus.ACTIVE` - Only healthy agents
- `AgentStatus.UNHEALTHY` - Failed health checks
- `AgentStatus.DEGRADED` - Partial functionality
- `AgentStatus.OFFLINE` - Disconnected agents
- `None` - All agents regardless of status

### Event Types

- **AGENT_REGISTERED**: Agent added to registry
- **AGENT_DEREGISTERED**: Agent removed from registry
- **AGENT_STATUS_CHANGED**: Agent status updated
- **AGENT_HEARTBEAT**: Agent sent heartbeat
- **RUNTIME_JOINED**: First agent from runtime registered
- **RUNTIME_LEFT**: Last agent from runtime deregistered

### Multi-Runtime Coordination

**Runtime Tracking**:
```python
# Each agent associated with a runtime
agent_id = await registry.register_agent(agent, runtime_id="runtime_1")

# Query agents by runtime
runtime_agents = registry.runtime_agents["runtime_1"]

# Track runtime joins/leaves
# RUNTIME_JOINED event when first agent registers
# RUNTIME_LEFT event when last agent deregisters
```

---

## Production Deployment

### Best Practices

1. **Use appropriate heartbeat intervals** based on workload
   - Fast: 10-30s for critical systems
   - Normal: 30-60s for standard workloads
   - Slow: 60-300s for long-running agents

2. **Set auto-deregister timeout** 2-3x heartbeat timeout
   - Allows missed heartbeats before deregistration
   - Prevents premature removal of healthy agents

3. **Enable event broadcasting** for observability
   - Monitor agent health in real-time
   - Track runtime joins/leaves
   - Audit agent lifecycle events

4. **Use status filtering** for production routing
   - Always filter by `AgentStatus.ACTIVE` for task routing
   - Exclude unhealthy agents from critical workloads
   - Monitor degraded agents for recovery

5. **Implement graceful recovery** patterns
   - Detect failures via events
   - Route to healthy agents automatically
   - Restore failed agents when recovered

### Scaling Considerations

- **10-100 agents**: Single OrchestrationRuntime per process
- **100-1000 agents**: Single AgentRegistry across multiple runtimes
- **1000+ agents**: Multiple AgentRegistry instances with sharding

### Monitoring

Track these metrics:
- Agent registration/deregistration rates
- Heartbeat success rates
- Status distribution (active/unhealthy/degraded)
- Event queue depth
- Capability search latency (should be O(1))
- Runtime join/leave frequency

---

## Comparison with OrchestrationRuntime

### OrchestrationRuntime (10-100 agents)
- **Scope**: Single-process multi-agent orchestration
- **Routing**: Semantic, round-robin, random task routing
- **Health**: Agent-level health checks with real LLM inference
- **Budget**: Per-agent and runtime-wide budget tracking
- **Use Case**: Task distribution within a single runtime

### AgentRegistry (100+ agents)
- **Scope**: Distributed multi-runtime coordination
- **Discovery**: O(1) capability-based agent discovery
- **Health**: Heartbeat monitoring with automatic deregistration
- **Events**: Cross-runtime event broadcasting
- **Use Case**: Centralized coordination across distributed systems

**Integration**:
```python
# Use both together for distributed orchestration
runtime = OrchestrationRuntime(config=runtime_config)
registry = AgentRegistry(config=registry_config)

# Register agents in both
agent_id = await runtime.register_agent(agent)  # Runtime tracking
await registry.register_agent(agent, runtime_id="runtime_1")  # Global discovery

# Route tasks locally via runtime
selected_agent = await runtime.route_task(task, strategy=RoutingStrategy.SEMANTIC)

# Discover agents globally via registry
all_agents = await registry.find_agents_by_capability("code generation")
```

---

## Next Steps

1. **Review test suites**:
   - Unit tests: `tests/unit/orchestration/test_agent_registry.py`
   - Integration tests: `tests/integration/orchestration/test_agent_registry_integration.py`
   - E2E tests: `tests/e2e/orchestration/test_agent_registry_e2e.py`

2. **Explore OrchestrationRuntime patterns**:
   - `examples/orchestration/orchestration-patterns/`

3. **Check documentation**:
   - AgentRegistry architecture
   - Event broadcasting design
   - Distributed coordination patterns

---

## Support

For issues or questions:
- GitHub Issues: [kailash-kaizen/issues](https://github.com/kailash/kailash-kaizen/issues)
- Documentation: `docs/features/agent-registry.md` (TODO)
- Test examples: `tests/e2e/orchestration/test_agent_registry_e2e.py`
