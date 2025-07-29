# MCP Service Discovery Guide

*Automatic discovery and management of MCP servers in distributed environments*

## Overview

The MCP Service Discovery system enables automatic discovery, registration, and management of MCP servers across networks and environments. It provides service registry, health monitoring, load balancing, and automatic failover capabilities for production MCP deployments.

## Prerequisites

- Completed [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md)
- Understanding of network concepts
- Basic knowledge of service mesh architectures

## Core Components

### Service Registry

The central registry for all MCP servers in your environment.

```python
from kailash.mcp_server.discovery import ServiceRegistry, ServerInfo

# Create a service registry with file-based backend
from kailash.mcp_server.discovery import FileBasedDiscovery

file_backend = FileBasedDiscovery(
    registry_file="/etc/mcp/servers.json",
    auto_cleanup=True
)
registry = ServiceRegistry(backends=[file_backend])

# Register a server
server_info = ServerInfo(
    name="weather-server",
    transport="http",
    url="http://localhost:8080",
    capabilities=["weather.current", "weather.forecast", "weather.alerts"],
    metadata={
        "region": "us-west-2",
        "priority": 1,
        "max_concurrent": 100
    },
    health_endpoint="/health",
    auth_required=True
)

await registry.register_server(server_info)
```

### Server Discovery

Find and connect to servers based on capabilities.

```python
# Discover servers by capability
weather_servers = await registry.discover_servers(
    capability="weather.current",
    filters={
        "health_status": "healthy",
        "region": "us-west-2"
    }
)

# Discover servers by metadata
high_priority_servers = await registry.discover_servers(
    filters={"metadata.priority": {"$gte": 8}}
)

# Get all servers
all_servers = await registry.list_servers()
for server in all_servers:
    print(f"Server: {server.name}, Status: {server.health_status}")
```

## Network Discovery

Automatically discover MCP servers on the network.

### Network Scanning

```python
from kailash.mcp_server.discovery import NetworkDiscovery

# Create network discoverer
discoverer = NetworkDiscovery(
    scan_ports=[8080, 8081, 8082, 3000],  # Common MCP ports
    timeout=5.0,
    protocols=["http", "sse"]
)

# Scan specific network range
servers = await discoverer.scan_network("192.168.1.0/24")
for server in servers:
    print(f"Found: {server.name} at {server.url}")

# Scan specific hosts
servers = await discoverer.scan_hosts(
    hosts=["192.168.1.100", "192.168.1.101"]
)

# Auto-register discovered servers
for server in servers:
    await registry.register_server(server)
```

### Broadcast Discovery

```python
# Network discovery supports various protocols
# Check actual API for broadcast functionality
discovery_options = {
    "scan_ports": [8080, 8081, 8082],
    "timeout": 5.0,
    "protocols": ["http", "sse"]
}
```

## Service Mesh Integration

Intelligent routing and load balancing for MCP services.

### Basic Service Mesh

```python
from kailash.mcp_server.discovery import ServiceMesh, LoadBalancer

# Create service mesh with load balancing
load_balancer = LoadBalancer()
mesh = ServiceMesh(registry)

# Get client for specific capability
client = await mesh.get_client_for_capability("weather.current")

# Call tool through service mesh
result = await client.call_tool("weather.current", {"city": "San Francisco"})
```

### Advanced Routing

```python
# Capability-based routing with preferences
# Service mesh provides intelligent routing based on server capabilities
mesh = ServiceMesh(registry)

# Get client for specific capability
processor_client = await mesh.get_client_for_capability("data.process")
```

## Health Monitoring

Continuous health checking and status management.

### Health Checker Setup

```python
from kailash.mcp_server.discovery import HealthChecker

# Create health checker
health_checker = HealthChecker()

# Start health monitoring
await health_checker.start()

# Custom health check function
@health_checker.custom_check("database_connection")
async def check_database(server_info: ServerInfo) -> Dict[str, Any]:
    """Custom health check for database connectivity."""
    try:
        # Check if server can connect to its database
        response = await health_checker.call_server_endpoint(
            server_info, "/internal/db-health"
        )
        return {
            "status": "healthy" if response["connected"] else "unhealthy",
            "details": response.get("details", {}),
            "response_time": response.get("response_time", 0)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "response_time": float("inf")
        }
```

### Health Status Management

```python
# Get health status for all servers
health_report = await health_checker.get_health_report()
for server_id, health in health_report.items():
    print(f"Server {server_id}: {health['status']} "
          f"(Response: {health['response_time']:.2f}ms)")

# Handle unhealthy servers
unhealthy_servers = await registry.discover_servers(
    filters={"health_status": "unhealthy"}
)
for server in unhealthy_servers:
    # Attempt recovery or remove from rotation
    if server.metadata.get("auto_restart"):
        await mesh.restart_server(server.id)
    else:
        await registry.mark_server_down(server.id)
```

## Load Balancing Strategies

Configure different load balancing approaches for optimal performance.

### Round Robin

```python
from kailash.mcp_server.discovery import LoadBalancer

# Round robin balancing
lb = LoadBalancer(strategy="round_robin")
mesh = ServiceMesh(registry, load_balancer=lb)

# Each request goes to the next server in rotation
```

### Least Connections

```python
# Least connections balancing
lb = LoadBalancer(
    strategy="least_connections",
    config={
        "connection_tracking": True,
        "max_connections_per_server": 100
    }
)
```

### Weighted Round Robin

```python
# Weighted balancing based on server capacity
lb = LoadBalancer(
    strategy="weighted_round_robin",
    weight_function=lambda server: server.metadata.get("capacity", 1)
)
```

### Health-Based Balancing

```python
# Route based on server health and response time
lb = LoadBalancer(
    strategy="health_weighted",
    config={
        "health_weight": 0.7,      # 70% weight on health
        "response_time_weight": 0.3,  # 30% weight on response time
        "exclude_unhealthy": True
    }
)
```

## Configuration Management

Centralized configuration for discovery and routing.

### File-Based Configuration

```yaml
# mcp-discovery.yaml
service_registry:
  backend: file
  config:
    registry_file: /etc/mcp/servers.json
    auto_cleanup: true
    cleanup_interval: 300

network_discovery:
  enabled: true
  scan_ports: [8080, 8081, 8082]
  scan_interval: 60
  networks:
    - "192.168.1.0/24"
    - "10.0.0.0/8"

health_monitoring:
  enabled: true
  check_interval: 30
  timeout: 10
  max_failures: 3
  checks:
    - endpoint_reachable
    - response_time
    - tool_availability

load_balancing:
  strategy: health_weighted
  config:
    health_weight: 0.7
    response_time_weight: 0.3
    exclude_unhealthy: true

routing_rules:
  "weather.*":
    preferred_regions: ["us-west-2"]
    min_health_score: 0.8
  "data.process":
    required_metadata:
      gpu: true
    timeout: 60
```

### Loading Configuration

```python
from kailash.mcp_server.discovery import DiscoveryConfig

# Load configuration from file
config = DiscoveryConfig.from_file("mcp-discovery.yaml")

# Create components from configuration
registry = ServiceRegistry.from_config(config.service_registry)
health_checker = HealthChecker.from_config(config.health_monitoring, registry)
mesh = ServiceMesh.from_config(config, registry)
```

## Production Deployment Patterns

### Highly Available Registry

```python
# Redis-backed registry for HA
registry = ServiceRegistry(
    backend="redis",
    config={
        "redis_urls": [
            "redis://redis1:6379",
            "redis://redis2:6379",
            "redis://redis3:6379"
        ],
        "cluster_mode": True,
        "sentinel_service": "mcp-registry"
    }
)

# Consul-backed registry
registry = ServiceRegistry(
    backend="consul",
    config={
        "consul_url": "http://consul:8500",
        "key_prefix": "mcp/servers",
        "health_check_ttl": 30
    }
)
```

### Multi-Region Setup

```python
# Regional registries with cross-region discovery
us_west_registry = ServiceRegistry(
    backend="consul",
    config={"datacenter": "us-west-2", "consul_url": "http://consul-west:8500"}
)

us_east_registry = ServiceRegistry(
    backend="consul",
    config={"datacenter": "us-east-1", "consul_url": "http://consul-east:8500"}
)

# Cross-region service mesh
global_mesh = ServiceMesh(
    registries=[us_west_registry, us_east_registry],
    preferred_region="us-west-2",
    cross_region_latency_threshold=100  # ms
)
```

### Auto-Scaling Integration

```python
# Kubernetes auto-scaling integration
from kailash.mcp_server.discovery.k8s import KubernetesDiscovery

k8s_discovery = KubernetesDiscovery(
    namespace="mcp",
    label_selector="app=mcp-server",
    port_name="mcp"
)

# Auto-register Kubernetes services
await k8s_discovery.watch_services(
    callback=lambda server: registry.register_server(server)
)

# Scale based on load
@mesh.load_monitor
async def auto_scale_handler(capability: str, load_metrics: Dict):
    """Auto-scale servers based on load."""
    if load_metrics["avg_response_time"] > 1000:  # > 1 second
        await k8s_discovery.scale_deployment(
            f"{capability}-server",
            replicas=load_metrics["current_replicas"] + 2
        )
```

## Monitoring and Observability

### Metrics Collection

```python
from kailash.mcp_server.discovery import DiscoveryMetrics

# Enable metrics collection
metrics = DiscoveryMetrics(
    registry=registry,
    export_interval=60,  # Export metrics every minute
    exporters=["prometheus", "json"]
)

# Custom metrics
@metrics.gauge("active_servers_by_capability")
def active_servers_metric():
    """Track active servers by capability."""
    servers = await registry.list_servers(filters={"health_status": "healthy"})
    capabilities = {}
    for server in servers:
        for capability in server.capabilities:
            capabilities[capability] = capabilities.get(capability, 0) + 1
    return capabilities

# Request tracking
@metrics.histogram("discovery_request_duration")
async def track_discovery_requests():
    """Track discovery request performance."""
    start_time = time.time()
    try:
        servers = await registry.discover_servers(capability="data.process")
        return {"status": "success", "server_count": len(servers)}
    finally:
        metrics.record_duration(time.time() - start_time)
```

### Health Dashboards

```python
# Web dashboard for service discovery
from kailash.mcp_server.discovery.dashboard import DiscoveryDashboard

dashboard = DiscoveryDashboard(
    registry=registry,
    health_checker=health_checker,
    mesh=mesh,
    port=8090
)

# Features:
# - Real-time server status
# - Health check results
# - Load balancing metrics
# - Network topology view
# - Configuration management UI

await dashboard.start()
```

## Integration Examples

### Workflow Integration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import Node

# MCP Discovery Node
class MCPDiscoveryNode(Node):
    def __init__(self, capability: str, **kwargs):
        super().__init__(**kwargs)
        self.capability = capability
        self.mesh = None

    async def initialize(self):
        registry = ServiceRegistry()
        self.mesh = ServiceMesh(registry)

    async def process(self, data: Dict) -> Dict:
        # Discover and call appropriate MCP server
        client = await self.mesh.get_client_for_capability(self.capability)
        result = await client.call_tool(self.capability, data)
        return {"result": result, "server_used": client.server_info.name}

# Use in workflow
workflow = WorkflowBuilder()
workflow.add_node("MCPDiscoveryNode", "weather", {"capability": "weather.current"})
workflow.add_node("MCPDiscoveryNode", "processor", {"capability": "data.process"})
```

### Client Integration

```python
from kailash.mcp_server.discovery import MCPClient

# Smart MCP client with automatic discovery
client = MCPClient.with_discovery(
    registry=registry,
    preferred_capabilities=["weather.current", "weather.forecast"],
    auto_retry=True,
    circuit_breaker=True
)

# Calls automatically route to best available server
weather = await client.call_tool("weather.current", {"city": "Seattle"})
forecast = await client.call_tool("weather.forecast", {"city": "Seattle", "days": 7})
```

## Best Practices

### 1. Server Registration

```python
# Always provide comprehensive server information
server_info = ServerInfo(
    name="analytics-server-prod-1",
    transport="http",
    url="https://analytics.example.com:8080",
    capabilities=["analytics.query", "analytics.report", "analytics.export"],
    metadata={
        "region": "us-west-2",
        "environment": "production",
        "version": "2.1.0",
        "capacity": 1000,
        "features": ["async", "streaming", "batch"]
    },
    health_endpoint="/health",
    auth_required=True,
    version="1.0.0"
)
```

### 2. Health Monitoring

```python
# Implement comprehensive health checks
@health_checker.custom_check("business_logic")
async def check_business_logic(server_info: ServerInfo) -> Dict:
    """Check server business logic health."""
    try:
        # Test critical functionality
        test_result = await client.call_tool("analytics.query", {
            "query": "SELECT 1",
            "_health_check": True
        })

        return {
            "status": "healthy" if test_result else "unhealthy",
            "details": {"test_query_success": bool(test_result)},
            "response_time": test_result.get("response_time", 0)
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

### 3. Security

```python
# Secure service discovery
registry = ServiceRegistry(
    backend="consul",
    config={
        "consul_url": "https://consul:8500",
        "tls_verify": True,
        "acl_token": os.environ["CONSUL_ACL_TOKEN"],
        "encrypt_server_info": True,
        "allowed_capabilities": ["weather.*", "analytics.*"]
    }
)
```

## Related Guides

**Prerequisites:**
- [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md) - Server setup

**Next Steps:**
- [MCP Transport Layers Guide](26-mcp-transport-layers-guide.md) - Transport configuration
- [MCP Advanced Features Guide](27-mcp-advanced-features-guide.md) - Advanced patterns

---

**Build scalable MCP architectures with automatic service discovery and intelligent routing!**
