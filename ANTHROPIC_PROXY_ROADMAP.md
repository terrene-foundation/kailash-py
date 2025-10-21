# Anthropic Proxy - Implementation Roadmap

## 🎯 Quick Reference

**Goal**: Add Anthropic-compatible API proxy to Kaizen as a Nexus channel

**Location**: Implement as a new channel in `src/kailash/channels/anthropic_channel.py`

**Integration**: Works like API/CLI/MCP channels - independently activatable

---

## 📋 Phase 1 Implementation Checklist (Week 1)

### Day 1-2: Core Channel Structure

**Files to Create**:
```
src/kailash/channels/
├── anthropic_channel.py         # Main channel (300 lines)
├── anthropic_models.py          # Pydantic models (150 lines)
└── anthropic_config.py          # Configuration (100 lines)
```

**Key Classes**:
```python
# anthropic_channel.py
class AnthropicProxyChannel(Channel):
    """Main proxy channel implementation"""
    
    async def start(self) -> None:
        """Start FastAPI server"""
        
    async def handle_request(self, request: Dict) -> ChannelResponse:
        """Route /v1/messages requests"""
        
    async def _handle_messages_endpoint(self, request: AnthropicRequest):
        """Core message handling logic"""
```

### Day 3-4: Provider Integration

**Files to Create**:
```
src/kailash/channels/
├── anthropic_providers.py       # Provider registry (200 lines)
└── anthropic_translator.py      # Request/response translation (300 lines)
```

**Key Functions**:
- Auto-discover available Kailash providers
- Map Anthropic request → Provider request
- Map Provider response → Anthropic response
- Handle streaming responses

### Day 5: Testing & Documentation

**Files to Create**:
```
tests/unit/channels/
├── test_anthropic_channel.py
├── test_anthropic_translator.py
└── test_anthropic_providers.py

docs/channels/
└── anthropic_proxy_guide.md
```

**Tests to Write**:
- Channel lifecycle (start/stop)
- Request parsing and validation
- Response formatting
- Error handling
- Provider integration

---

## 🚀 Quick Start Implementation

### 1. Minimal Working Example

```python
# src/kailash/channels/anthropic_channel.py
"""Anthropic-compatible API proxy channel."""

import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

from kailash.channels.base import Channel, ChannelConfig, ChannelResponse, ChannelStatus
from kailash.nodes.ai.ai_providers import OllamaProvider
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.async_local import AsyncLocalRuntime

logger = logging.getLogger(__name__)


class AnthropicProxyChannel(Channel):
    """
    Anthropic-compatible API proxy channel.
    
    Translates Claude Code requests to local/cloud LLM providers.
    """
    
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.app = FastAPI(title="Anthropic Proxy")
        self.runtime = AsyncLocalRuntime()
        self.provider = None
        self._server = None
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.post("/v1/messages")
        async def messages_endpoint(request: Dict[str, Any]):
            """Anthropic messages endpoint"""
            try:
                return await self._handle_messages(request)
            except Exception as e:
                logger.error(f"Error handling request: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "provider": "ollama" if self.provider else "none"
            }
    
    async def start(self) -> None:
        """Start the proxy server"""
        try:
            self.status = ChannelStatus.STARTING
            
            # Initialize provider
            self.provider = OllamaProvider()
            if not self.provider.is_available():
                raise RuntimeError("Ollama provider not available")
            
            # Start server
            port = self.config.port or 8082
            config = uvicorn.Config(
                self.app,
                host=self.config.host,
                port=port,
                log_level="info"
            )
            self._server = uvicorn.Server(config)
            
            self.status = ChannelStatus.RUNNING
            logger.info(f"Anthropic proxy started on {self.config.host}:{port}")
            
            # Run server
            await self._server.serve()
            
        except Exception as e:
            self.status = ChannelStatus.ERROR
            logger.error(f"Failed to start proxy: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the proxy server"""
        self.status = ChannelStatus.STOPPING
        if self._server:
            self._server.should_exit = True
        self.status = ChannelStatus.STOPPED
        logger.info("Anthropic proxy stopped")
    
    async def handle_request(self, request: Dict[str, Any]) -> ChannelResponse:
        """Handle generic channel request"""
        return ChannelResponse(
            success=True,
            data={"message": "Use /v1/messages endpoint"}
        )
    
    async def _handle_messages(self, request: Dict[str, Any]) -> Dict:
        """
        Handle Anthropic messages request.
        
        Workflow:
        1. Parse request (model, messages, parameters)
        2. Translate to provider format
        3. Execute via Kailash workflow
        4. Translate response back
        5. Return in Anthropic format
        """
        # Extract parameters
        model = request.get("model", "claude-sonnet-4")
        messages = request.get("messages", [])
        max_tokens = request.get("max_tokens", 4096)
        temperature = request.get("temperature", 0.7)
        
        # Map Anthropic model to Ollama model
        ollama_model = self._map_model(model)
        
        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "agent", {
            "provider": "ollama",
            "model": ollama_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        })
        
        # Execute
        results = await self.runtime.execute_workflow_async(
            workflow.build(),
            inputs={}
        )
        
        # Get response
        agent_output = results.get("agent", {})
        
        # Format as Anthropic response
        return {
            "id": f"msg_{asyncio.current_task().get_name()}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": agent_output.get("content", "")
                }
            ],
            "model": model,
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": agent_output.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": agent_output.get("usage", {}).get("completion_tokens", 0)
            }
        }
    
    def _map_model(self, anthropic_model: str) -> str:
        """Map Anthropic model name to Ollama model"""
        mapping = {
            "claude-haiku": "phi3:mini",
            "claude-sonnet": "qwen2.5-coder:32b",
            "claude-opus": "llama3.1:70b",
            "claude-sonnet-4": "qwen2.5-coder:32b"
        }
        return mapping.get(anthropic_model, "llama3.1")
```

### 2. Configuration Model

```python
# src/kailash/channels/anthropic_config.py
"""Configuration for Anthropic proxy channel."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class AnthropicProxyConfig:
    """Configuration for Anthropic proxy"""
    
    # Server settings
    host: str = "localhost"
    port: int = 8082
    
    # Provider settings
    preferred_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    
    # Model mapping
    model_mapping: Dict[str, str] = field(default_factory=lambda: {
        "claude-haiku": "phi3:mini",
        "claude-sonnet": "qwen2.5-coder:32b", 
        "claude-opus": "llama3.1:70b"
    })
    
    # Routing rules
    context_routing: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "coding": {"provider": "ollama", "model": "qwen2.5-coder:32b"},
        "fileSearch": {"provider": "ollama", "model": "phi3:mini"}
    })
    
    # Timeouts
    request_timeout_ms: int = 600000  # 10 minutes
    
    # Features
    enable_streaming: bool = True
    enable_tool_calling: bool = True
    enable_monitoring: bool = True
    
    # Enterprise
    enable_auth: bool = False
    enable_rate_limiting: bool = False
    api_key: Optional[str] = None


def load_config_from_file(file_path: str) -> AnthropicProxyConfig:
    """Load configuration from YAML/JSON file"""
    import yaml
    with open(file_path, 'r') as f:
        data = yaml.safe_load(f)
    return AnthropicProxyConfig(**data)
```

### 3. Usage Example

```python
# examples/anthropic_proxy_example.py
"""Example of using Anthropic proxy."""

import asyncio
from kailash.channels.anthropic_channel import AnthropicProxyChannel
from kailash.channels.base import ChannelConfig, ChannelType


async def main():
    # Create channel config
    config = ChannelConfig(
        name="anthropic_proxy",
        channel_type=ChannelType.API,  # Extend enum later
        host="localhost",
        port=8082
    )
    
    # Create and start proxy
    proxy = AnthropicProxyChannel(config)
    
    print("Starting Anthropic proxy on http://localhost:8082")
    print("Configure Claude Code:")
    print("  export ANTHROPIC_BASE_URL=http://localhost:8082")
    print("  export ANTHROPIC_API_KEY=dummy")
    print("  claude")
    
    await proxy.start()


if __name__ == "__main__":
    asyncio.run(main())
```

### 4. Integration with Nexus

```python
# apps/kailash-nexus/src/nexus/__init__.py (modification)
"""Add Anthropic proxy support to Nexus"""

from nexus import Nexus

# Option 1: Explicit activation
app = Nexus(
    enable_anthropic_proxy=True,
    anthropic_proxy_port=8082
)

# Option 2: Via configuration
app = Nexus.from_config("nexus_config.yaml")

app.start()
# Now runs: API, CLI, MCP, AND Anthropic Proxy!
```

---

## 🧪 Testing Strategy

### Unit Test Example

```python
# tests/unit/channels/test_anthropic_channel.py
"""Unit tests for Anthropic proxy channel."""

import pytest
from kailash.channels.anthropic_channel import AnthropicProxyChannel
from kailash.channels.base import ChannelConfig, ChannelType


@pytest.fixture
def proxy_config():
    return ChannelConfig(
        name="test_proxy",
        channel_type=ChannelType.API,
        port=8083
    )


@pytest.fixture
def proxy_channel(proxy_config):
    return AnthropicProxyChannel(proxy_config)


def test_channel_initialization(proxy_channel):
    """Test channel initializes correctly"""
    assert proxy_channel.name == "test_proxy"
    assert proxy_channel.config.port == 8083


def test_model_mapping(proxy_channel):
    """Test Anthropic model mapping"""
    assert proxy_channel._map_model("claude-haiku") == "phi3:mini"
    assert proxy_channel._map_model("claude-sonnet") == "qwen2.5-coder:32b"
    assert proxy_channel._map_model("claude-opus") == "llama3.1:70b"


@pytest.mark.asyncio
async def test_messages_endpoint(proxy_channel):
    """Test /v1/messages endpoint"""
    request = {
        "model": "claude-sonnet-4",
        "messages": [
            {"role": "user", "content": "Hello!"}
        ],
        "max_tokens": 100
    }
    
    response = await proxy_channel._handle_messages(request)
    
    assert response["type"] == "message"
    assert response["role"] == "assistant"
    assert "content" in response
```

### Integration Test Example

```python
# tests/integration/channels/test_anthropic_integration.py
"""Integration tests for Anthropic proxy."""

import pytest
import httpx
from kailash.channels.anthropic_channel import AnthropicProxyChannel


@pytest.mark.asyncio
async def test_full_request_flow():
    """Test complete request flow"""
    # Start proxy
    proxy = AnthropicProxyChannel(...)
    await proxy.start()
    
    # Send request
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8082/v1/messages",
            json={
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "Hello"}]
            }
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "message"
    
    await proxy.stop()
```

---

## 📝 Documentation Template

### User Guide

```markdown
# Anthropic Proxy - Quick Start Guide

## Installation

```bash
pip install kailash-kaizen[anthropic-proxy]
```

## Basic Usage

```python
from kaizen.proxy import AnthropicProxy

# Start proxy with zero configuration
proxy = AnthropicProxy()
proxy.start()
```

## Configure Claude Code

```bash
export ANTHROPIC_BASE_URL=http://localhost:8082
export ANTHROPIC_API_KEY=dummy
claude
```

## Advanced Configuration

```python
proxy = AnthropicProxy(
    port=8082,
    preferred_provider="ollama",
    model_mapping={
        "claude-haiku": "phi3:mini",
        "claude-sonnet": "qwen2.5-coder:32b"
    }
)
```

## Troubleshooting

### Ollama not found
- Ensure Ollama is running: `ollama serve`
- Check models are pulled: `ollama list`

### Connection refused
- Verify port is not in use: `lsof -i :8082`
- Check firewall settings
```

---

## ⚡ Performance Targets

| Metric | Target | Current (Est.) |
|--------|--------|----------------|
| Cold Start | <2s | TBD |
| Request Latency | <500ms | TBD |
| Streaming TTFT | <100ms | TBD |
| Memory Usage | <200MB | TBD |
| Concurrent Requests | 100+ | TBD |

---

## 🎯 Acceptance Criteria

### MVP (Phase 1)
- [ ] Proxy starts and stops cleanly
- [ ] Handles `/v1/messages` endpoint
- [ ] Translates requests/responses for Ollama
- [ ] Claude Code successfully connects
- [ ] Simple queries work end-to-end
- [ ] Unit tests pass (90%+ coverage)
- [ ] Basic documentation complete

### Success Metrics
- Setup time < 5 minutes
- Zero-config works out of box
- All basic features functional
- No critical bugs
- Documentation covers 100% of features

---

## 🚀 Next Steps

1. **Review Design Document**: Get team feedback on architecture
2. **Create GitHub Issue**: Track Phase 1 implementation
3. **Setup Dev Environment**: Ensure Ollama, Kailash SDK ready
4. **Implement Core Channel**: Start with `anthropic_channel.py`
5. **Write Tests First**: TDD approach per Kailash standards
6. **Iterate Rapidly**: Get working prototype ASAP
7. **Document Everything**: Keep docs in sync with code
8. **Get User Feedback**: Early testing with real users

---

**Status**: Design phase complete, ready for implementation approval.
