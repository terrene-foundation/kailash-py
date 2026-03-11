# Auto-Discovery Routing MCP Pattern

**Production implementation using Kailash SDK's ServiceRegistry and ServiceMesh**

---

## Overview

Demonstrates automatic service discovery and intelligent routing across multiple MCP servers using production-ready infrastructure from Kailash SDK. This pattern enables agents to automatically find, evaluate, and route requests to the most suitable MCP services with load balancing and failover.

## Key Features

✅ **Automatic Service Discovery** - Uses `ServiceRegistry` and `discover_mcp_servers()`
✅ **Intelligent Routing** - Routes based on capabilities, performance, or load balancing
✅ **Load Balancing** - `ServiceMesh` provides round-robin, least-loaded, and random strategies
✅ **Automatic Failover** - Circuit breaker pattern with configurable retry attempts
✅ **Performance Tracking** - Real-time metrics for routing optimization
✅ **Health Checking** - Continuous service health monitoring

---

## Architecture

```
┌─────────────────────────────────────────┐
│  AutoDiscoveryRoutingAgent              │
│  (Kaizen Agent)                         │
├─────────────────────────────────────────┤
│  • ServiceRegistry                       │
│  • ServiceMesh (load balancing)         │
│  • MCPClient (with circuit breaker)     │
├─────────────────────────────────────────┤
│  Routing Strategies:                    │
│  • capability_match (by capabilities)   │
│  • load_balance (round-robin/weighted)  │
│  • performance (lowest latency)         │
└─────────────────────────────────────────┘
          ↓
    ┌─────┴─────┬─────────────┬──────────┐
    ↓           ↓             ↓          ↓
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│Search  │  │Search  │  │Compute │  │Database│
│Server 1│  │Server 2│  │Server  │  │Server  │
└────────┘  └────────┘  └────────┘  └────────┘
```

---

## Use Cases

### 1. Multi-Server Search
Route search requests across multiple search servers with automatic load balancing:
```python
result = await agent.route_request(
    request_type="search",
    tool_name="web_search",
    arguments={"query": "AI research"},
    required_capabilities=["search"]
)
# Automatically routes to least-loaded search server
```

### 2. Capability-Based Routing
Route specialized requests to servers with specific capabilities:
```python
result = await agent.route_request(
    request_type="compute",
    tool_name="calculate",
    arguments={"expression": "complex_calculation"},
    required_capabilities=["compute", "high_precision"]
)
# Routes to compute server with high_precision capability
```

### 3. Performance-Optimized Routing
Route to the fastest-responding server based on historical performance:
```python
config = AutoDiscoveryAgentConfig(
    routing_strategy="performance",  # Route to lowest latency server
    prefer_low_latency=True
)
```

### 4. Automatic Failover
Automatically fail over to backup servers when primary fails:
```python
result = await agent.route_request(
    request_type="search",
    tool_name="web_search",
    arguments={"query": "test"}
)
# If primary search server fails, automatically tries backup servers
# Result includes: failover_attempts, service_used, primary_service_failed
```

---

## Quick Start

### 1. Installation

```bash
pip install kailash  # Includes kailash.mcp_server
```

### 2. Run the Example

```bash
python workflow.py
```

### 3. Expected Output

```
=== Auto-Discovery Routing Agent Example ===

✅ Discovered 3 services
   - search-server-1: ['search', 'web_search']
   - search-server-2: ['search', 'web_search']
   - compute-server: ['compute', 'calculate']

=== Routing Requests ===

Request 1: service=search-server-1
Request 2: service=compute-server

=== Service Health ===

search-server-1: ✅ Healthy
  Success rate: 100.0%
  Avg latency: 0.125s
search-server-2: ✅ Healthy
  Success rate: 100.0%
  Avg latency: 0.130s
compute-server: ✅ Healthy
  Success rate: 100.0%
  Avg latency: 0.095s

=== Performance Report ===

Total routing decisions: 2
Discovery age: 1.2s

✅ Auto-discovery routing example complete
```

---

## Implementation Details

### Configuration

```python
@dataclass
class AutoDiscoveryAgentConfig(BaseAgentConfig):
    # Service discovery
    discovery_interval_seconds: int = 60
    enable_auto_refresh: bool = True
    discovery_timeout: float = 30.0

    # Routing strategy
    routing_strategy: str = "capability_match"  # or "load_balance" or "performance"
    max_failover_attempts: int = 3
    health_check_interval: int = 30

    # Performance tracking
    enable_performance_tracking: bool = True
    prefer_low_latency: bool = True

    # Service mesh
    enable_service_mesh: bool = True
    load_balancing_strategy: str = "round_robin"  # or "least_loaded" or "random"

    # Initial servers
    initial_servers: List[Dict[str, Any]] = field(default_factory=list)
```

### Routing Strategies

#### 1. Capability Match (Default)
Routes to first server matching required capabilities:
```python
config = AutoDiscoveryAgentConfig(
    routing_strategy="capability_match"
)
```

#### 2. Load Balance
Uses ServiceMesh for load balancing across servers:
```python
config = AutoDiscoveryAgentConfig(
    routing_strategy="load_balance",
    enable_service_mesh=True,
    load_balancing_strategy="round_robin"  # or "least_loaded" or "random"
)
```

#### 3. Performance
Routes to server with lowest average latency:
```python
config = AutoDiscoveryAgentConfig(
    routing_strategy="performance",
    prefer_low_latency=True
)
```

### Server Configuration

```python
initial_servers = [
    {
        "name": "search-server-1",
        "transport": "http",
        "url": "http://localhost:8080",
        "capabilities": ["search", "web_search"]
    },
    {
        "name": "compute-server",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "compute_server"],
        "capabilities": ["compute", "calculate"]
    },
    {
        "name": "db-server",
        "transport": "websocket",
        "url": "ws://localhost:3001/mcp",
        "capabilities": ["database", "query"]
    }
]
```

---

## API Reference

### Core Methods

#### `initialize()`
Initialize service discovery infrastructure:
```python
await agent.initialize()
```

Creates ServiceRegistry, ServiceMesh, and MCPClient. Registers initial servers and performs initial discovery.

#### `discover_services()`
Discover available MCP services:
```python
services = await agent.discover_services()
# Returns: Dict[str, ServerInfo]
```

Uses network discovery and service registry to find all available services.

#### `route_request()`
Route request to optimal service:
```python
result = await agent.route_request(
    request_type="search",
    tool_name="web_search",
    arguments={"query": "test"},
    required_capabilities=["search"]
)
```

**Parameters**:
- `request_type` - Type of request (used for capability matching)
- `tool_name` - MCP tool to invoke
- `arguments` - Tool arguments
- `required_capabilities` - List of required capabilities

**Returns**:
```python
{
    "success": True/False,
    "result": {...},  # Tool result
    "latency": 0.125,  # Seconds
    "service_used": "search-server-1",
    "failover_attempts": 0,
    "routing_metadata": {
        "selected_service": "search-server-1",
        "routing_strategy": "capability_match",
        "alternatives_available": 1,
        "discovery_age_seconds": 15.3
    }
}
```

#### `get_service_health()`
Get health status of all services:
```python
health = await agent.get_service_health()
# Returns health status per service
```

Returns:
```python
{
    "search-server-1": {
        "healthy": True,
        "success_rate": 0.98,
        "total_requests": 100,
        "average_latency": 0.125
    },
    ...
}
```

#### `get_performance_report()`
Get comprehensive performance report:
```python
report = agent.get_performance_report()
```

Returns:
```python
{
    "services": {
        "search-server-1": {
            "total_requests": 50,
            "successful_requests": 49,
            "failed_requests": 1,
            "average_latency": 0.125
        },
        ...
    },
    "total_routing_decisions": 50,
    "discovery_age_seconds": 120.5
}
```

---

## Production Deployment

### 1. Multiple Data Centers

Deploy search servers across multiple data centers with automatic routing:

```python
servers = [
    {
        "name": "search-us-east",
        "transport": "http",
        "url": "https://search-us-east.example.com",
        "capabilities": ["search"],
        "metadata": {"region": "us-east-1"}
    },
    {
        "name": "search-us-west",
        "transport": "http",
        "url": "https://search-us-west.example.com",
        "capabilities": ["search"],
        "metadata": {"region": "us-west-2"}
    },
    {
        "name": "search-eu",
        "transport": "http",
        "url": "https://search-eu.example.com",
        "capabilities": ["search"],
        "metadata": {"region": "eu-west-1"}
    }
]

config = AutoDiscoveryAgentConfig(
    routing_strategy="performance",  # Route to lowest latency
    prefer_low_latency=True,
    max_failover_attempts=3,
    initial_servers=servers
)
```

### 2. Service Mesh with Authentication

```python
from kailash.mcp_server.auth import APIKeyAuth

# Configure agent with auth
config = AutoDiscoveryAgentConfig(
    routing_strategy="load_balance",
    enable_service_mesh=True,
    initial_servers=[...]
)

# Each server can have authentication
servers = [
    {
        "name": "secure-server",
        "transport": "http",
        "url": "https://api.example.com",
        "headers": {"Authorization": "Bearer token"},
        "capabilities": ["search"]
    }
]
```

### 3. Health Monitoring

Set up periodic health checks:

```python
import asyncio

async def monitor_services(agent):
    """Continuously monitor service health."""
    while True:
        await asyncio.sleep(30)  # Every 30 seconds

        # Check health
        health = await agent.get_service_health()

        for service, status in health.items():
            if not status["healthy"]:
                logger.warning(f"Service {service} unhealthy: {status}")

        # Refresh discovery
        if agent.config.enable_auto_refresh:
            await agent.refresh_discovery()

# Run monitoring in background
asyncio.create_task(monitor_services(agent))
```

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Discovery Latency** | ~100-500ms (network discovery) |
| **Routing Decision** | <1ms (local decision) |
| **Failover Time** | 1-3s (depends on timeout) |
| **Memory Overhead** | ~1-2MB per 100 services |
| **Throughput** | >1000 routing decisions/sec |

---

## Error Handling

### Service Unavailable

```python
result = await agent.route_request(...)

if not result["success"]:
    print(f"Error: {result['error']}")
    # All services failed or no suitable services
```

### Failover Scenarios

```python
result = await agent.route_request(...)

if result.get("failover_attempts", 0) > 0:
    print(f"Primary service {result['primary_service_failed']} failed")
    print(f"Used failover service: {result['service_used']}")
    print(f"Failover attempts: {result['failover_attempts']}")
```

---

## Testing

See [testing-guide.md](../../../docs/integrations/mcp/testing-guide.md) for comprehensive testing patterns.

### Unit Test
```python
def test_routing_strategy_selection():
    config = AutoDiscoveryAgentConfig(routing_strategy="performance")
    agent = AutoDiscoveryRoutingAgent(config)
    assert agent.config.routing_strategy == "performance"
```

### Integration Test
```python
@pytest.mark.integration
async def test_real_service_discovery():
    config = AutoDiscoveryAgentConfig(initial_servers=[...])
    agent = AutoDiscoveryRoutingAgent(config)

    await agent.initialize()

    services = await agent.discover_services()
    assert len(services) > 0
```

---

## Comparison with Previous Implementation

| Feature | Deprecated kaizen.mcp | Production kailash.mcp_server |
|---------|----------------------|-------------------------------|
| Service Discovery | String matching | Real network discovery + registry |
| Load Balancing | Manual | ServiceMesh with strategies |
| Failover | Not implemented | Circuit breaker + retry |
| Health Checking | Not implemented | Real-time monitoring |
| Performance Tracking | Not implemented | Latency + success rate metrics |
| Protocol | Mocked | Real JSON-RPC 2.0 |

---

## See Also

- **[MCP Integration README](../../../docs/integrations/mcp/README.md)** - Main MCP guide
- **[Quick Reference](../../../docs/integrations/mcp/quick-reference.md)** - Common patterns
- **[Testing Guide](../../../docs/integrations/mcp/testing-guide.md)** - Testing strategies
- **[Agent-as-Client](../agent-as-client/)** - Basic MCP client pattern
- **[Agent-as-Server](../agent-as-server/)** - Basic MCP server pattern

---

**Status**: ✅ Production-Ready
**Last Updated**: 2025-10-04
**Implementation**: Kailash SDK v0.9.19+
