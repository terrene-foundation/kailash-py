# ADR-009: MCP First-Class Integration Architecture

## Status
**Accepted** - 2025-09-24

## Context

Kaizen aims to make MCP (Model Context Protocol) a first-class citizen, enabling seamless integration between AI agents and external tools/services. Currently, MCP integration is completely missing (BLOCKER-004), preventing agents from exposing capabilities as MCP servers or consuming external MCP services.

### Problem Statement
- Agents need native MCP server capabilities to expose their functionality
- Agents need MCP client capabilities to consume external services
- Current Kailash has basic MCP nodes but no first-class agent integration
- Enterprise deployment requires automated MCP discovery and management
- Security and session management needed for production MCP operations

### Decision Drivers
1. **Native Integration**: MCP as core agent capability, not add-on
2. **Bidirectional Support**: Agents as both MCP servers and clients
3. **Auto-Discovery**: Capability-based tool discovery and registration
4. **Enterprise Security**: Authentication, authorization, session management
5. **Kailash Compatibility**: Leverage existing MCP infrastructure
6. **Performance**: <100ms MCP operation target

### Constraints
- Must work with existing Kailash MCP nodes (MCPClientNode, MCPServerNode)
- Cannot break Core SDK patterns for MCP operations
- Must support both stdio and HTTP transports
- Need backward compatibility with manual MCP configuration
- Enterprise security requirements (encryption, audit, RBAC)

## Decision

Implement a comprehensive MCP-first architecture with four integration layers:

### Layer 1: Agent MCP Capabilities
```python
# Native MCP server capabilities
agent = kaizen.create_agent("research_agent", config={
    "model": "gpt-4",
    "capabilities": ["research", "analyze", "summarize"]
})

# Expose agent as MCP server
server = agent.expose_as_mcp_server(
    port=8080,
    auth="api_key",
    tools=["research", "analyze"],
    description="AI research assistant"
)

# Connect agent to MCP services
agent.connect_to_mcp_servers([
    "search-service",
    "http://data-api:8080",
    {"name": "custom-service", "transport": "stdio", "command": "python -m my_mcp"}
])

# Auto-discover tools by capability
agent.enable_mcp_tools(["search", "calculate", "file_operations"])
```

### Layer 2: MCP Service Management
```python
# Framework-level MCP management
kaizen = Kaizen(config={
    'mcp_integration': {
        'auto_discover': True,
        'registry_url': 'https://mcp-registry.kailash.io',
        'security_policy': 'enterprise',
        'session_management': True
    }
})

# Global MCP service discovery
available_tools = kaizen.discover_mcp_tools(
    capabilities=["search", "calculate", "analyze"],
    location="auto"  # Local network + registry
)

# Enterprise MCP server registry
kaizen.register_mcp_service(
    name="company-data-api",
    capabilities=["data_query", "analytics"],
    security_level="high",
    access_policy="team_leads_only"
)
```

### Layer 3: Workflow Integration
```python
# MCP tools in workflows
workflow = WorkflowBuilder()
workflow.add_node("MCPToolNode", "search", {
    "tool_name": "web_search",
    "auto_discover": True,
    "fallback_tools": ["backup_search"]
})

# Agent MCP integration in workflows
workflow.add_agent_as_mcp_server(agent, "research_service")
workflow.add_mcp_client_connection("external_api")

# Multi-agent MCP coordination
debate_workflow = kaizen.create_debate_workflow(
    agents=["researcher", "analyst", "critic"],
    mcp_tools=["search", "data_query", "fact_check"]
)
```

### Layer 4: Enterprise Management
```python
# Security and monitoring
mcp_monitor = kaizen.get_mcp_monitor()
mcp_monitor.enable_audit_logging()
mcp_monitor.set_rate_limits({"search": 1000, "data_query": 100})

# Performance optimization
mcp_optimizer = kaizen.get_mcp_optimizer()
mcp_optimizer.enable_connection_pooling()
mcp_optimizer.set_cache_policy({"search": "5m", "static_data": "1h"})
```

## Consequences

### Positive
- **Seamless Integration**: MCP becomes native agent capability
- **Enterprise Ready**: Built-in security, monitoring, and management
- **Auto-Discovery**: Reduces configuration complexity by 90%
- **Bidirectional Support**: Agents can be both providers and consumers
- **Performance Optimized**: Connection pooling, caching, async operations
- **Kailash Leverage**: Uses existing MCP infrastructure

### Negative
- **Implementation Complexity**: Four-layer architecture requires careful coordination
- **Performance Overhead**: MCP operations add network latency
- **Security Complexity**: Enterprise security features increase attack surface
- **Dependency Management**: Relies on external MCP services for functionality

### Risks
- **Network Reliability**: MCP operations depend on external service availability
- **Security Vulnerabilities**: Exposing agents as servers increases attack surface
- **Performance Degradation**: Multiple MCP calls may impact workflow performance
- **Version Compatibility**: MCP protocol changes may break integrations

## Alternatives Considered

### Option 1: Manual MCP Configuration Only
- **Pros**: Simple implementation, full control, no auto-discovery complexity
- **Cons**: Poor developer experience, high configuration overhead, no enterprise features
- **Why Rejected**: Doesn't achieve "first-class citizen" goal, poor scalability

### Option 2: Separate MCP Service Layer
- **Pros**: Clean separation of concerns, easier testing, modular architecture
- **Cons**: Not first-class integration, additional abstraction layer, poor developer UX
- **Why Rejected**: Doesn't meet native integration requirement

### Option 3: Wrapper Around Existing MCP Clients
- **Pros**: Leverages existing tools, faster implementation, proven patterns
- **Cons**: Limited customization, poor Kailash integration, missing enterprise features
- **Why Rejected**: Insufficient for enterprise requirements, poor integration

### Option 4: Custom MCP Protocol Implementation
- **Pros**: Complete control, optimized for Kailash, custom features
- **Cons**: Protocol compatibility issues, maintenance burden, ecosystem fragmentation
- **Why Rejected**: Breaks MCP ecosystem compatibility, high maintenance cost

## Implementation Plan

### Phase 1: Foundation (Week 1-2)
```python
# Core MCP integration interfaces
class MCPAgentCapabilities:
    def expose_as_mcp_server(self, port: int, **config) -> MCPServer
    def connect_to_mcp_servers(self, servers: List[Union[str, Dict]]) -> MCPClientManager
    def enable_mcp_tools(self, capabilities: List[str]) -> List[MCPTool]

class MCPServerManager:
    def create_server(self, agent: Agent, config: MCPServerConfig) -> MCPServer
    def register_tools(self, agent: Agent) -> List[MCPToolDefinition]
    def handle_requests(self, request: MCPRequest) -> MCPResponse

class MCPClientManager:
    def connect_to_server(self, server_config: MCPServerConfig) -> MCPConnection
    def discover_tools(self, capabilities: List[str]) -> List[MCPTool]
    def execute_tool(self, tool_name: str, **params) -> MCPToolResult
```

### Phase 2: Agent Integration (Week 3-4)
```python
# Enhanced Agent class with MCP capabilities
class Agent:
    def __init__(self, agent_id: str, **config):
        self.mcp_server_manager = MCPServerManager(self)
        self.mcp_client_manager = MCPClientManager(self)
        self._mcp_tools = {}

    def expose_as_mcp_server(self, **config) -> MCPServer:
        return self.mcp_server_manager.create_server(self, config)

    def connect_to_mcp_servers(self, servers: List) -> MCPClientManager:
        for server in servers:
            self.mcp_client_manager.connect_to_server(server)
        return self.mcp_client_manager

    def execute_with_mcp_tools(self, **inputs) -> Dict[str, Any]:
        # Integrate MCP tools into agent execution
        available_tools = self.mcp_client_manager.get_available_tools()
        result = self._execute_with_tools(inputs, available_tools)
        return result
```

### Phase 3: Auto-Discovery System (Week 5-6)
```python
# MCP service discovery and registry
class MCPServiceRegistry:
    def discover_services(self, capabilities: List[str]) -> List[MCPService]:
        local_services = self._discover_local_services(capabilities)
        registry_services = self._query_service_registry(capabilities)
        return self._merge_and_rank_services(local_services, registry_services)

    def register_service(self, service: MCPService) -> str:
        service_id = self._generate_service_id(service)
        self._local_registry[service_id] = service
        if self.config.publish_to_global_registry:
            self._publish_to_global_registry(service)
        return service_id

class MCPToolDiscovery:
    def auto_discover_tools(self, agent: Agent, capabilities: List[str]) -> List[MCPTool]:
        discovered_services = self.registry.discover_services(capabilities)
        connected_tools = []
        for service in discovered_services:
            try:
                connection = agent.mcp_client_manager.connect_to_server(service)
                tools = connection.list_tools()
                connected_tools.extend(tools)
            except MCPConnectionError:
                continue
        return connected_tools
```

### Phase 4: Enterprise Features (Week 7-8)
```python
# Security and monitoring
class MCPSecurityManager:
    def authenticate_connection(self, connection: MCPConnection) -> bool:
        return self._verify_credentials(connection.credentials)

    def authorize_tool_access(self, user: str, tool: str) -> bool:
        return self._check_rbac_permissions(user, tool)

    def encrypt_communication(self, connection: MCPConnection):
        connection.enable_tls(self.security_config.tls_config)

class MCPMonitor:
    def track_tool_usage(self, tool: str, user: str, duration: float):
        self.metrics_collector.record_tool_usage(tool, user, duration)

    def detect_anomalies(self, usage_pattern: Dict) -> List[Anomaly]:
        return self.anomaly_detector.analyze(usage_pattern)

    def generate_audit_log(self, operation: MCPOperation) -> AuditLogEntry:
        return AuditLogEntry(
            timestamp=datetime.now(),
            user=operation.user,
            tool=operation.tool,
            inputs=operation.inputs,
            outputs=operation.outputs,
            success=operation.success
        )
```

## Implementation Guidance

### Core Components

#### 1. MCP Server Implementation
```python
class KaizenMCPServer(MCPServer):
    def __init__(self, agent: Agent, config: MCPServerConfig):
        super().__init__(transport=config.transport)
        self.agent = agent
        self.config = config
        self._register_agent_tools()

    def _register_agent_tools(self):
        # Convert agent capabilities to MCP tools
        for capability in self.agent.capabilities:
            tool_def = MCPToolDefinition(
                name=capability,
                description=f"Agent {self.agent.id} {capability} capability",
                input_schema=self._generate_input_schema(capability),
                output_schema=self._generate_output_schema(capability)
            )
            self.register_tool(tool_def, self._execute_agent_capability)

    def _execute_agent_capability(self, tool_name: str, **params) -> MCPToolResult:
        try:
            result = self.agent.execute(**params)
            return MCPToolResult(success=True, data=result)
        except Exception as e:
            return MCPToolResult(success=False, error=str(e))
```

#### 2. MCP Client Integration
```python
class AgentMCPClient:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.connections: Dict[str, MCPConnection] = {}
        self.available_tools: Dict[str, MCPTool] = {}

    def connect_to_server(self, server_config: Union[str, Dict]) -> MCPConnection:
        config = self._normalize_server_config(server_config)
        connection = MCPConnection(config)

        # Test connection and discover tools
        tools = connection.list_tools()
        for tool in tools:
            self.available_tools[tool.name] = tool
            # Make tool available to agent
            self._bind_tool_to_agent(tool)

        self.connections[config.name] = connection
        return connection

    def _bind_tool_to_agent(self, tool: MCPTool):
        # Create dynamic method on agent for this tool
        def tool_executor(**kwargs):
            return self._execute_mcp_tool(tool.name, **kwargs)

        setattr(self.agent, f"mcp_{tool.name}", tool_executor)
```

#### 3. Auto-Discovery Engine
```python
class MCPAutoDiscovery:
    def __init__(self, config: MCPDiscoveryConfig):
        self.config = config
        self.local_scanner = LocalServiceScanner()
        self.registry_client = MCPRegistryClient(config.registry_url)

    def discover_by_capabilities(self, capabilities: List[str]) -> List[MCPService]:
        # Multi-source discovery
        discoveries = []

        # Local network scanning
        if self.config.scan_local:
            local_services = self.local_scanner.scan_for_capabilities(capabilities)
            discoveries.extend(local_services)

        # Global registry query
        if self.config.use_registry:
            registry_services = self.registry_client.search_capabilities(capabilities)
            discoveries.extend(registry_services)

        # Agent-provided services (other Kaizen agents)
        agent_services = self._discover_agent_services(capabilities)
        discoveries.extend(agent_services)

        return self._rank_and_filter_services(discoveries)

    def _rank_and_filter_services(self, services: List[MCPService]) -> List[MCPService]:
        # Rank by: 1) Security level, 2) Performance, 3) Reliability, 4) Cost
        ranked = sorted(services, key=lambda s: (
            s.security_score,
            s.performance_score,
            s.reliability_score,
            -s.cost_score
        ), reverse=True)

        # Filter by policy
        filtered = [s for s in ranked if self._meets_policy_requirements(s)]
        return filtered[:self.config.max_services]
```

### Integration Patterns

#### 1. Agent-as-MCP-Server Pattern
```python
# Simple server exposure
agent = kaizen.create_agent("data_processor", config={
    "model": "gpt-4",
    "capabilities": ["analyze_data", "generate_report"]
})

server = agent.expose_as_mcp_server(
    port=8080,
    auth="bearer_token",
    rate_limit=100,
    tools=["analyze_data"]  # Subset of capabilities
)

# Enterprise server with full features
enterprise_server = agent.expose_as_mcp_server(
    port=8443,
    auth="enterprise_sso",
    tls=True,
    monitoring=True,
    audit_logging=True,
    access_control="rbac"
)
```

#### 2. Agent-as-MCP-Client Pattern
```python
# Simple client connection
agent.connect_to_mcp_servers([
    "search-service",  # Local service name
    "http://api.company.com:8080",  # HTTP endpoint
    {"name": "custom", "transport": "stdio", "command": "python -m my_tool"}
])

# Auto-discovery client
agent.enable_mcp_tools(["search", "calculate", "file_operations"])
# Framework automatically discovers and connects to matching services

# Enterprise client with security
agent.connect_to_mcp_servers([{
    "name": "secure-api",
    "url": "https://secure-api.company.com",
    "auth": {"type": "oauth2", "client_id": "...", "client_secret": "..."},
    "tls_verify": True,
    "timeout": 30
}])
```

#### 3. Workflow Integration Pattern
```python
# MCP tools in standard workflows
workflow = WorkflowBuilder()

# Add MCP tool as workflow node
workflow.add_node("MCPToolNode", "search_step", {
    "tool_name": "web_search",
    "tool_params": {"query": "${input.query}", "limit": 10}
})

# Add agent MCP server as workflow service
workflow.add_node("MCPServerNode", "agent_service", {
    "agent": agent,
    "exposed_tools": ["analyze", "summarize"]
})

# Multi-agent workflow with MCP coordination
multi_agent_workflow = WorkflowBuilder()
multi_agent_workflow.add_agent_as_mcp_server(research_agent, "research")
multi_agent_workflow.add_agent_as_mcp_server(analysis_agent, "analysis")
multi_agent_workflow.add_mcp_coordination("research", "analysis", "synthesis")
```

### Performance Considerations

#### 1. Connection Pooling
```python
class MCPConnectionPool:
    def __init__(self, max_connections: int = 10):
        self.pools: Dict[str, Queue] = {}
        self.max_connections = max_connections

    def get_connection(self, server_name: str) -> MCPConnection:
        if server_name not in self.pools:
            self.pools[server_name] = Queue(maxsize=self.max_connections)
            # Pre-populate with initial connections
            for _ in range(min(3, self.max_connections)):
                conn = MCPConnection(self._get_server_config(server_name))
                self.pools[server_name].put(conn)

        try:
            return self.pools[server_name].get_nowait()
        except:
            # Create new connection if pool empty
            return MCPConnection(self._get_server_config(server_name))

    def return_connection(self, server_name: str, connection: MCPConnection):
        if not connection.is_closed():
            try:
                self.pools[server_name].put_nowait(connection)
            except:
                connection.close()  # Pool full, close connection
```

#### 2. Async Operations
```python
class AsyncMCPClient:
    async def execute_tool_async(self, tool_name: str, **params) -> MCPToolResult:
        connection = await self._get_connection_async(tool_name)
        try:
            result = await connection.execute_tool_async(tool_name, **params)
            return result
        finally:
            await self._return_connection_async(connection)

    async def execute_parallel_tools(self, tool_calls: List[MCPToolCall]) -> List[MCPToolResult]:
        tasks = [self.execute_tool_async(call.tool, **call.params) for call in tool_calls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

#### 3. Caching Strategy
```python
class MCPResultCache:
    def __init__(self, config: CacheConfig):
        self.cache = TTLCache(maxsize=config.max_size, ttl=config.default_ttl)
        self.tool_ttls = config.tool_specific_ttls

    def cache_result(self, tool_name: str, params: Dict, result: MCPToolResult):
        cache_key = self._generate_cache_key(tool_name, params)
        ttl = self.tool_ttls.get(tool_name, self.cache.ttl)
        self.cache[cache_key] = (result, time.time() + ttl)

    def get_cached_result(self, tool_name: str, params: Dict) -> Optional[MCPToolResult]:
        cache_key = self._generate_cache_key(tool_name, params)
        cached = self.cache.get(cache_key)
        if cached and cached[1] > time.time():
            return cached[0]
        return None
```

This comprehensive MCP integration architecture provides first-class MCP support that exceeds current capabilities while maintaining perfect Kailash ecosystem integration.
