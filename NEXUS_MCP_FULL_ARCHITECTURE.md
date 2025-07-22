# NEXUS FULL MCP ARCHITECTURE: Leveraging Core SDK for Complete Protocol Support

**Date**: 2025-01-15  
**Status**: Architectural Design Document  
**Scope**: Extending Nexus with full Model Context Protocol capabilities using Core SDK

## 🎯 Executive Summary

### Current State
- **Nexus**: Basic MCP implementation with tools support only (~40% complete)
- **Core SDK**: Complete, production-ready MCP implementation with tools, resources, prompts, and enterprise features

### Proposed Solution
Replace Nexus's simple MCP server with the Core SDK's comprehensive MCP infrastructure, enabling:
- ✅ **Tools**: Already working (enhanced with SDK features)
- ✅ **Resources**: Full read/write support for documents, data, files
- ✅ **Prompts**: Complete prompt library and template management
- ✅ **Enterprise**: Authentication, rate limiting, service discovery, monitoring

## 🏗️ Architectural Overview

### Current Nexus MCP Architecture (Limited)
```
┌─────────────────────────────────────────┐
│              Nexus                      │
│  ┌────────────────────────────────┐    │
│  │  Simple MCP Server              │    │
│  │  - Basic WebSocket              │    │
│  │  - Tools only                   │    │
│  │  - No auth/monitoring           │    │
│  └────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### Proposed Architecture (Full MCP via Core SDK)
```
┌──────────────────────────────────────────────────────────────┐
│                        Nexus Platform                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                Core SDK MCP Integration                  │ │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │ │
│  │  │ MCP Server  │  │  MCP Channel │  │ MCP Resources │  │ │
│  │  │ (Full impl) │  │  (Workflow   │  │ (Documents,   │  │ │
│  │  │             │  │   exposure)  │  │  Data, Files) │  │ │
│  │  └─────────────┘  └──────────────┘  └───────────────┘  │ │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │ │
│  │  │   Auth &    │  │  Transport   │  │   Discovery   │  │ │
│  │  │  Security   │  │  (WS, SSE,   │  │   Registry    │  │ │
│  │  │             │  │   HTTP)      │  │               │  │ │
│  │  └─────────────┘  └──────────────┘  └───────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ API Channel  │  │ CLI Channel  │  │ Session Manager    │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## 📦 Core SDK MCP Components to Leverage

### 1. **MCPServer** (`src/kailash/mcp_server/server.py`)
Complete MCP server implementation with:
- Full protocol support (tools, resources, prompts)
- Authentication providers (API Key, JWT, OAuth 2.1)
- Caching, metrics, circuit breaker
- Rate limiting and error aggregation
- Streaming support for large responses

### 2. **MCPChannel** (`src/kailash/channels/mcp_channel.py`)
Channel implementation that:
- Automatically exposes workflows as MCP tools
- Manages MCP server lifecycle
- Integrates with Kailash runtime
- Provides resource management

### 3. **Transport Layer** (`src/kailash/mcp_server/transports.py`)
Multiple transport options:
- WebSocket (current Nexus default)
- Server-Sent Events (SSE)
- HTTP streaming
- STDIO for testing

### 4. **Service Discovery** (`src/kailash/mcp_server/discovery.py`)
Enterprise features:
- Automatic server registration
- Network discovery via UDP
- Load balancing
- Health checking

## 🔧 Implementation Plan

### Phase 1: Replace Simple Server with Core SDK MCPServer

**Step 1.1: Update Nexus Core**
```python
# apps/kailash-nexus/src/nexus/core.py

from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth
from kailash.channels import MCPChannel

class Nexus:
    def __init__(self, ...):
        # Replace simple MCP server with Core SDK server
        self._mcp_server = self._create_sdk_mcp_server()
        
    def _create_sdk_mcp_server(self):
        """Create production-ready MCP server using Core SDK."""
        
        # Configure authentication if enabled
        auth_provider = None
        if self.enable_auth:
            # Use API Key auth as default
            auth_provider = APIKeyAuth(self._get_api_keys())
        
        # Create enhanced MCP server
        server = MCPServer(
            name=f"{self.name}-mcp",
            enable_cache=True,
            enable_metrics=True,
            auth_provider=auth_provider,
            enable_http_transport=self.enable_http_transport,
            enable_sse_transport=self.enable_sse_transport,
            rate_limit_config=self.rate_limit_config,
            circuit_breaker_config={"failure_threshold": 5},
            enable_discovery=self.enable_discovery,
            enable_streaming=True,
        )
        
        return server
```

### Phase 2: Integrate MCPChannel for Workflow Management

**Step 2.1: Use MCPChannel for Workflow Exposure**
```python
# apps/kailash-nexus/src/nexus/core.py

def _setup_mcp_channel(self):
    """Set up MCP channel for workflow management."""
    
    # Create channel config
    from kailash.channels import ChannelConfig, ChannelType
    
    config = ChannelConfig(
        name=f"{self.name}-mcp-channel",
        channel_type=ChannelType.MCP,
        host="0.0.0.0",
        port=self._mcp_port,
        enable_sessions=True,
        enable_auth=self.enable_auth,
        extra_config={
            "server_name": f"{self.name}-mcp",
            "description": f"MCP channel for {self.name}",
        }
    )
    
    # Create MCP channel with our server
    self._mcp_channel = MCPChannel(config, mcp_server=self._mcp_server)
    
    return self._mcp_channel

def register(self, name: str, workflow: Workflow):
    """Register workflow - now with full MCP support."""
    # Existing registration
    self._workflows[name] = workflow
    
    # Register with MCP channel for automatic tool exposure
    if self._mcp_channel:
        self._mcp_channel.register_workflow(name, workflow)
```

### Phase 3: Add Resources Support

**Step 3.1: Implement Resource Providers**
```python
# apps/kailash-nexus/src/nexus/resources.py

from kailash.mcp_server import MCPServer
from typing import Dict, Any, List

class NexusResourceManager:
    """Manage resources for Nexus MCP server."""
    
    def __init__(self, mcp_server: MCPServer):
        self.server = mcp_server
        self._setup_default_resources()
    
    def _setup_default_resources(self):
        """Set up default resource providers."""
        
        # Workflow definitions as resources
        @self.server.resource("workflow://*")
        async def get_workflow_definition(uri: str) -> Dict[str, Any]:
            workflow_name = uri.replace("workflow://", "")
            # Return workflow definition/schema
            return {
                "uri": uri,
                "mimeType": "application/json",
                "content": self._get_workflow_schema(workflow_name)
            }
        
        # Documentation resources
        @self.server.resource("docs://*")
        async def get_documentation(uri: str) -> Dict[str, Any]:
            doc_path = uri.replace("docs://", "")
            # Return documentation content
            return {
                "uri": uri,
                "mimeType": "text/markdown",
                "content": self._get_documentation(doc_path)
            }
        
        # Data resources (databases, files, etc.)
        @self.server.resource("data://*")
        async def get_data_resource(uri: str) -> Dict[str, Any]:
            resource_path = uri.replace("data://", "")
            # Return data content
            return {
                "uri": uri,
                "mimeType": self._get_mime_type(resource_path),
                "content": self._get_data_content(resource_path)
            }
```

### Phase 4: Add Prompts Support

**Step 4.1: Implement Prompt Library**
```python
# apps/kailash-nexus/src/nexus/prompts.py

class NexusPromptLibrary:
    """Manage prompts for Nexus MCP server."""
    
    def __init__(self, mcp_server: MCPServer):
        self.server = mcp_server
        self._setup_default_prompts()
    
    def _setup_default_prompts(self):
        """Set up default prompt templates."""
        
        # Workflow execution prompt
        @self.server.prompt("execute_workflow")
        async def workflow_execution_prompt(
            workflow_name: str,
            description: str = ""
        ) -> str:
            return f"""You are about to execute the '{workflow_name}' workflow.
            
{description or 'This workflow processes data according to its defined logic.'}

Available parameters:
- Provide input parameters as a JSON object
- Use null for optional parameters you want to skip
- All parameters must match the workflow's expected schema

Please provide the parameters for this workflow execution."""

        # Data analysis prompt
        @self.server.prompt("analyze_data")
        async def data_analysis_prompt(
            data_source: str,
            analysis_type: str = "general"
        ) -> str:
            return f"""Analyze the data from '{data_source}'.

Analysis type: {analysis_type}

Please provide insights on:
1. Data patterns and trends
2. Anomalies or outliers
3. Key statistics
4. Recommendations based on findings

Format your response in clear sections."""

        # Error diagnosis prompt
        @self.server.prompt("diagnose_error")
        async def error_diagnosis_prompt(
            error_message: str,
            context: str = ""
        ) -> str:
            return f"""Help diagnose this error:

Error: {error_message}

Context: {context or 'No additional context provided'}

Please provide:
1. Likely causes of this error
2. Step-by-step troubleshooting guide
3. Potential solutions
4. Prevention strategies"""
```

### Phase 5: Enhanced Features Integration

**Step 5.1: Enable Service Discovery**
```python
# apps/kailash-nexus/src/nexus/discovery.py

from kailash.mcp_server import enable_auto_discovery, ServiceRegistry

class NexusDiscovery:
    """Enable service discovery for Nexus MCP servers."""
    
    def __init__(self, nexus_instance):
        self.nexus = nexus_instance
        self.registry = ServiceRegistry()
        
    def enable_discovery(self):
        """Enable auto-discovery for this Nexus instance."""
        
        # Register with service discovery
        registrar = enable_auto_discovery(
            self.nexus._mcp_server,
            enable_network_discovery=True,
            health_check_interval=30,
            capabilities=["workflows", "resources", "prompts"]
        )
        
        # Start registration
        registrar.start_with_registration()
        
        return registrar
```

**Step 5.2: Add Multi-Transport Support**
```python
# apps/kailash-nexus/src/nexus/transports.py

from kailash.mcp_server.transports import TransportManager

def setup_transports(nexus_instance):
    """Set up multiple transport options."""
    
    transport_manager = TransportManager()
    
    # WebSocket (default)
    if nexus_instance._mcp_port:
        transport_manager.add_transport(
            "websocket",
            host="0.0.0.0",
            port=nexus_instance._mcp_port
        )
    
    # HTTP/SSE transport
    if nexus_instance.enable_http_transport:
        transport_manager.add_transport(
            "http",
            host="0.0.0.0",
            port=nexus_instance._mcp_port + 1
        )
    
    # STDIO for testing
    if nexus_instance._debug_mode:
        transport_manager.add_transport("stdio")
    
    return transport_manager
```

## 🔌 Integration Points

### 1. **Backward Compatibility**
Maintain existing Nexus API while enhancing with Core SDK:
```python
# Existing API still works
app = Nexus()
app.register("workflow", workflow)
app.start()

# Enhanced features available
app.mcp.auth.strategy = "jwt"
app.mcp.discovery.enable()
app.mcp.resources.add_provider(FileResourceProvider("/data"))
```

### 2. **Session Synchronization**
Integrate MCP sessions with Nexus unified sessions:
```python
# MCP session events flow to unified session manager
self._mcp_channel.on("session_created", self._session_manager.sync_session)
self._mcp_channel.on("session_updated", self._session_manager.update_session)
```

### 3. **Event Broadcasting**
MCP events broadcast to all channels:
```python
# MCP tool execution broadcasts to API/CLI channels
self._mcp_server.on("tool_executed", lambda e: 
    self._event_bus.broadcast("workflow_executed", e)
)
```

## 📊 Benefits Analysis

### Feature Comparison
| Feature | Current Nexus | With Core SDK MCP |
|---------|--------------|-------------------|
| **Tools** | ✅ Basic | ✅ Full with auth, caching, metrics |
| **Resources** | ⚠️ List only | ✅ Full read/write with streaming |
| **Prompts** | ❌ None | ✅ Complete library with templates |
| **Auth** | ❌ None | ✅ API Key, JWT, OAuth 2.1 |
| **Transports** | ⚠️ WebSocket | ✅ WS, SSE, HTTP, STDIO |
| **Discovery** | ❌ None | ✅ Auto-discovery with registry |
| **Monitoring** | ⚠️ Basic | ✅ Metrics, health checks, alerts |
| **Error Handling** | ⚠️ Basic | ✅ Aggregation, circuit breaker |
| **Caching** | ❌ None | ✅ Multi-backend with TTL |
| **Rate Limiting** | ❌ None | ✅ Configurable per tool/user |

### Performance Impact
- **Minimal overhead**: Core SDK is optimized for production
- **Better performance**: Caching reduces redundant executions
- **Scalability**: Service discovery enables multi-server setups
- **Reliability**: Circuit breaker prevents cascade failures

## 🚀 Migration Path

### Step 1: Update Dependencies
```toml
# apps/kailash-nexus/pyproject.toml
[dependencies]
kailash = ">=0.6.7"  # Ensure Core SDK with MCP support
```

### Step 2: Gradual Migration
1. **Phase 1**: Replace MCP server (tools keep working)
2. **Phase 2**: Add MCPChannel (better workflow integration)
3. **Phase 3**: Enable resources (new capability)
4. **Phase 4**: Enable prompts (new capability)
5. **Phase 5**: Add enterprise features (progressive enhancement)

### Step 3: Testing Strategy
```python
# Test backward compatibility
def test_existing_api_works():
    app = Nexus()
    app.register("test", workflow)
    # Should work exactly as before
    
# Test enhanced features
def test_full_mcp_protocol():
    app = Nexus(enable_full_mcp=True)
    # Test tools, resources, prompts
    assert app.mcp.list_resources()
    assert app.mcp.list_prompts()
```

## 🎯 Success Criteria

1. **100% MCP Protocol Compliance**
   - Tools ✅, Resources ✅, Prompts ✅
   - All transport types supported
   - Full authentication/authorization

2. **Zero Breaking Changes**
   - Existing Nexus API unchanged
   - Current workflows keep working
   - Progressive enhancement model

3. **Enterprise Ready**
   - Production monitoring
   - Service discovery
   - High availability support
   - Security hardened

4. **Developer Experience**
   - Same simple API
   - Optional complexity
   - Clear documentation
   - Migration guide

## 🏁 Conclusion

By leveraging the Core SDK's complete MCP implementation, Nexus can provide:
- **Full MCP protocol support** (tools, resources, prompts)
- **Enterprise-grade features** (auth, monitoring, discovery)
- **Multiple transport options** (WebSocket, SSE, HTTP)
- **Production reliability** (caching, circuit breaker, rate limiting)
- **Backward compatibility** (existing API unchanged)

This architecture positions Nexus as a **comprehensive multi-channel platform** with **complete AI agent integration** capabilities, far beyond the current basic tool support.