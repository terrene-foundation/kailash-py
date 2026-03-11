# Agent Registry - Discovery & Registration

The Agent Registry provides centralized agent discovery and registration
for multi-agent systems with trust verification.

## What It Is

The Agent Registry is the **address book for AI agents** in a multi-agent system.
It tracks which agents exist, what they can do, and whether they can be trusted.

Key concepts:
- **Registration**: Agents register themselves with their capabilities
- **Discovery**: Other agents find suitable workers by capability
- **Trust Verification**: Registration validates the agent's trust chain
- **Health Monitoring**: Background detection of stale agents

## Core Components

### AgentMetadata

Complete information about a registered agent:

```python
from kaizen.trust.registry import AgentMetadata, AgentStatus

metadata = AgentMetadata(
    agent_id="agent-001",
    agent_type="worker",
    capabilities=["analyze_data", "generate_report"],
    constraints=["read_only"],
    status=AgentStatus.ACTIVE,
    trust_chain_hash="abc123...",
    registered_at=datetime.utcnow(),
    last_seen=datetime.utcnow(),
    metadata={"version": "1.0"},
    endpoint="localhost:8080",  # Optional
    public_key="ssh-rsa ...",   # Optional
)
```

### AgentStatus

Agent availability states:

| Status | Meaning | Available? |
|--------|---------|------------|
| `ACTIVE` | Agent is running and ready | Yes |
| `INACTIVE` | Agent stopped normally | No |
| `SUSPENDED` | Temporarily disabled (e.g., stale) | No |
| `REVOKED` | Trust has been revoked | No |
| `UNKNOWN` | State cannot be determined | No |

```python
# Check if agent can accept work
if metadata.status.is_available():
    # Safe to use this agent
```

### RegistrationRequest

Request to register an agent:

```python
from kaizen.trust.registry import RegistrationRequest

request = RegistrationRequest(
    agent_id="agent-001",
    agent_type="worker",
    capabilities=["analyze_data"],
    constraints=["read_only"],  # Optional
    metadata={"version": "1.0"},  # Optional
    trust_chain_hash=chain.compute_hash(),
    verify_trust=True,  # Default: True for security
)

# Validation catches problems early
errors = request.validate()
if errors:
    print(f"Invalid request: {errors}")
```

## AgentRegistry

Central registry for agent operations.

### Initialization

```python
from kaizen.trust.registry import (
    AgentRegistry,
    PostgresAgentRegistryStore,
)
from kaizen.trust import TrustOperations

# Initialize store
store = PostgresAgentRegistryStore(connection_string)
await store.initialize()

# Create registry with trust verification
registry = AgentRegistry(
    store=store,
    trust_operations=trust_ops,
    verify_on_registration=True,  # Verify trust before registration
)
```

For testing without trust verification:

```python
registry = AgentRegistry(
    store=InMemoryAgentRegistryStore(),
    verify_on_registration=False,
)
```

### Registration with Trust Verification

When `verify_on_registration=True`, registration:
1. Validates the request
2. Verifies the agent's trust chain exists
3. Checks the trust chain hash matches
4. Confirms all requested capabilities are in the trust chain
5. Creates and stores the agent metadata

```python
request = RegistrationRequest(
    agent_id="agent-001",
    agent_type="worker",
    capabilities=["analyze_data"],
    trust_chain_hash=chain.compute_hash(),
)

try:
    metadata = await registry.register(request)
    print(f"Agent registered: {metadata.agent_id}")
except TrustVerificationError as e:
    print(f"Registration blocked: {e}")
```

### Discovery by Capability

Find agents that can perform a task:

```python
# Simple capability search
analysts = await registry.find_by_capability("analyze_data")

# Multi-capability search (must have ALL)
specialists = await registry.find_by_capabilities(
    ["analyze_data", "generate_report"],
    match_all=True,
)

# Multi-capability search (must have ANY)
workers = await registry.find_by_capabilities(
    ["analyze_data", "generate_report"],
    match_all=False,
)
```

### Complex Discovery with DiscoveryQuery

Advanced discovery with multiple criteria:

```python
from kaizen.trust.registry import DiscoveryQuery

query = DiscoveryQuery(
    capabilities=["analyze_data"],
    match_all=True,
    agent_type="worker",
    status=AgentStatus.ACTIVE,
    exclude_constraints=["network_access"],
    min_last_seen=datetime.utcnow() - timedelta(minutes=5),
)

results = await registry.discover(query)
# Results are ranked by:
# 1. Capability match count
# 2. Recency (last_seen)
# 3. Type match
```

### Heartbeat and Status Management

```python
# Send heartbeat to indicate agent is alive
await registry.heartbeat("agent-001")

# Update agent status
await registry.update_status(
    "agent-001",
    AgentStatus.SUSPENDED,
    reason="Maintenance window",
)

# Find stale agents (no heartbeat in timeout)
stale = await registry.get_stale_agents(timeout=300)
```

## Health Monitoring

Automatic detection and handling of unresponsive agents.

### AgentHealthMonitor

```python
from kaizen.trust.registry import AgentHealthMonitor, HealthStatus

monitor = AgentHealthMonitor(
    registry=registry,
    check_interval=60,      # Check every 60 seconds
    stale_timeout=300,      # 5 minutes without heartbeat = stale
    auto_suspend_stale=True,  # Automatically suspend stale agents
)

# Start background monitoring
await monitor.start()

# Check individual agent health
health = await monitor.check_agent("agent-001")
if health == HealthStatus.STALE:
    print("Agent has not sent heartbeats recently")

# Run immediate check (outside regular cycle)
stale_count = await monitor.run_immediate_check()

# Reactivate a suspended agent
success = await monitor.reactivate_agent("agent-001")

# Stop monitoring
await monitor.stop()
```

### HealthStatus Values

| Status | Meaning |
|--------|---------|
| `HEALTHY` | Active and recently seen |
| `STALE` | Active but no recent heartbeats |
| `SUSPENDED` | Agent has been suspended |
| `UNKNOWN` | Agent not found or other status |

## Storage Backends

### PostgresAgentRegistryStore

Production storage with optimized queries:

```python
store = PostgresAgentRegistryStore(
    connection_string="postgresql://user:pass@host/db"
)
await store.initialize()  # Creates tables and indexes

# Features:
# - JSONB for capabilities (GIN indexed for fast queries)
# - Optimized indexes for capability and status queries
# - Stale agent detection with SQL
```

### InMemoryAgentRegistryStore

For testing:

```python
store = InMemoryAgentRegistryStore()
# No initialization needed
# All operations in-memory
```

## Complete Example

```python
from kaizen.trust import TrustOperations, TrustKeyManager
from kaizen.trust.registry import (
    AgentRegistry,
    PostgresAgentRegistryStore,
    RegistrationRequest,
    DiscoveryQuery,
    AgentHealthMonitor,
    AgentStatus,
)

# Setup
store = PostgresAgentRegistryStore(connection_string)
await store.initialize()

registry = AgentRegistry(
    store=store,
    trust_operations=trust_ops,
    verify_on_registration=True,
)

# Start health monitoring
monitor = AgentHealthMonitor(registry)
await monitor.start()

# Register agents
for i in range(5):
    request = RegistrationRequest(
        agent_id=f"worker-{i}",
        agent_type="worker",
        capabilities=["process_data"],
        trust_chain_hash=chains[i].compute_hash(),
    )
    await registry.register(request)

# Discover available workers
query = DiscoveryQuery(
    capabilities=["process_data"],
    status=AgentStatus.ACTIVE,
    min_last_seen=datetime.utcnow() - timedelta(minutes=5),
)
workers = await registry.discover(query)

# Select best worker (first result is highest ranked)
if workers:
    best_worker = workers[0]
    print(f"Selected worker: {best_worker.agent_id}")

# Cleanup
await monitor.stop()
await store.close()
```

## Error Handling

```python
from kaizen.trust.registry import (
    AgentNotFoundError,
    AgentAlreadyRegisteredError,
    ValidationError,
    TrustVerificationError,
)

try:
    await registry.register(request)
except ValidationError as e:
    # Invalid request fields
    print(f"Validation failed: {e.errors}")
except TrustVerificationError as e:
    # Trust chain invalid or missing capabilities
    print(f"Trust verification failed: {e}")
except AgentAlreadyRegisteredError as e:
    # Agent already registered
    print(f"Agent already exists: {e.agent_id}")
```

## Architectural Decisions

**Why separate Trust and Registration?**

Registration tracks *what agents exist*. Trust tracks *what agents can do*.
An agent can be unregistered but still have a valid trust chain.
They're managed separately because:
- Registration is about discovery (operational)
- Trust is about authorization (security)

**Why trust-verified registration?**

Prevents:
- Agents claiming capabilities they don't have
- Agents with revoked trust from re-registering
- Stale trust chain hashes from being used

**Why GIN indexes for capabilities?**

PostgreSQL's GIN indexes on JSONB enable efficient capability queries:
- Find agents with specific capability: O(log n)
- Find agents with multiple capabilities: Uses index intersection
- Scales to thousands of agents without full table scans
