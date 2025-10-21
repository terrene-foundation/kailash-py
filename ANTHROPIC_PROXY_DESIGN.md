# Anthropic API Proxy for Ollama/Local Models - Kaizen Integration

## 🎯 Executive Summary

**Goal**: Add an Anthropic-compatible API proxy to Kaizen that translates Claude Code requests to Ollama/local models, enabling users to run Claude Code with their own infrastructure.

**Architecture**: Built as a **Nexus Channel** (like API, CLI, MCP) that can be independently activated/deactivated.

**Key Features**:
- ✅ Independent activation (like litellm, claude-code-router)
- ✅ Multi-provider support (Ollama, OpenAI, Gemini, Anthropic direct)
- ✅ Dynamic model switching mid-session
- ✅ Context-aware routing (coding, debugging, file search)
- ✅ Streaming support with SSE
- ✅ Tool/function calling translation
- ✅ Enterprise features (rate limiting, monitoring, auth)
- ✅ Built on proven Kailash SDK patterns

---

## 📐 Architecture Analysis

### Current Kaizen/Kailash Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     🎨 Studio UI Layer                          │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│              🏢 Application Framework (Apps)                    │
│  DataFlow  │  Nexus  │  AI Registry  │  User Mgmt  │  Kaizen   │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────────────────────────────────────┐
│                     🎯 Core SDK Foundation                      │
│  Channels │ Workflows │ Runtime │ Nodes │ AI Providers │ MCP   │
└─────────────────────────────────────────────────────────────────┘
```

### Nexus Multi-Channel Architecture (Perfect Fit!)

```python
# From nexus/__init__.py - Zero-config multi-channel platform
app = Nexus()
app.start()  # Automatically starts API, CLI, MCP channels

# Channels are defined in src/kailash/channels/
- api_channel.py     # HTTP/REST API
- cli_channel.py     # Command-line interface
- mcp_channel.py     # Model Context Protocol
- base.py           # Abstract Channel class
```

**Key Insight**: The proxy should be **a new channel type** - `anthropic_channel.py`

---

## 🏗️ Proposed Architecture

### 1. New Channel: AnthropicProxyChannel

```python
# Location: src/kailash/channels/anthropic_channel.py

from kailash.channels.base import Channel, ChannelType, ChannelConfig
from kailash.nodes.ai.ai_providers import BaseAIProvider

class AnthropicChannelType(ChannelType):
    """Extend ChannelType enum"""
    ANTHROPIC_PROXY = "anthropic_proxy"

class AnthropicProxyChannel(Channel):
    """
    Anthropic-compatible API proxy channel.
    
    Translates Anthropic API requests to local/cloud LLM providers.
    Enables Claude Code to use Ollama, OpenAI, Gemini, etc.
    """
    
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.provider_registry = ProviderRegistry()
        self.router = ContextAwareRouter()
        self.translator = RequestTranslator()
        
    async def start(self) -> None:
        """Start FastAPI server on configured port"""
        
    async def handle_request(self, request: Dict[str, Any]) -> ChannelResponse:
        """
        Handle Anthropic API request:
        1. Parse Anthropic format
        2. Route to appropriate provider
        3. Translate request
        4. Execute via Kailash workflow
        5. Translate response
        6. Return in Anthropic format
        """
```

### 2. Integration with Existing Provider System

```python
# Leverage: src/kailash/nodes/ai/ai_providers.py
# Already has: OpenAIProvider, OllamaProvider, GeminiProvider, etc.

class ProviderRegistry:
    """
    Manages multiple AI providers for the proxy.
    Built on existing Kailash AI provider infrastructure.
    """
    
    def __init__(self):
        self.providers = {}
        self._load_available_providers()
    
    def _load_available_providers(self):
        """Auto-discover available providers from Kailash"""
        from kailash.nodes.ai.ai_providers import (
            OllamaProvider,
            OpenAIProvider, 
            GeminiProvider,
            AnthropicProvider
        )
        
        # Register all available providers
        if OllamaProvider().is_available():
            self.register("ollama", OllamaProvider())
        # ... etc
    
    def route_request(self, model_name: str, context: str) -> BaseAIProvider:
        """Route request to appropriate provider based on model and context"""
```

### 3. Request/Response Translation Layer

```python
# Location: src/kailash/channels/anthropic_translator.py

class AnthropicRequestTranslator:
    """
    Translates Anthropic API format to provider-specific format.
    
    Anthropic → OpenAI/Ollama/Gemini format conversion
    """
    
    def translate_messages(self, messages: List[Dict]) -> List[Dict]:
        """Convert Anthropic message format to target format"""
        
    def translate_tools(self, tools: List[Dict]) -> List[Dict]:
        """Convert Anthropic tool format to target format"""
        
    def translate_parameters(self, params: Dict) -> Dict:
        """Convert Anthropic parameters to target parameters"""

class AnthropicResponseTranslator:
    """
    Translates provider responses back to Anthropic format.
    
    OpenAI/Ollama/Gemini → Anthropic format conversion
    """
    
    def translate_completion(self, response: Dict) -> Dict:
        """Convert completion response to Anthropic format"""
        
    def translate_streaming(self, chunk: Dict) -> Dict:
        """Convert streaming chunk to Anthropic SSE format"""
        
    def translate_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Convert tool calls to Anthropic format"""
```

### 4. Context-Aware Router

```python
# Location: src/kailash/channels/anthropic_router.py

class ContextAwareRouter:
    """
    Routes requests to optimal provider based on:
    - Task type (coding, debugging, research, file search)
    - Model preferences (big/small/fast)
    - Provider availability
    - Cost optimization
    """
    
    def __init__(self, routing_config: Dict):
        self.routing_rules = {
            "coding": {"provider": "ollama", "model": "qwen2.5-coder:32b"},
            "debugging": {"provider": "ollama", "model": "qwen2.5-coder:32b"},
            "documentation": {"provider": "ollama", "model": "llama3.1"},
            "fileSearch": {"provider": "ollama", "model": "phi3:mini"},
            "syntaxCheck": {"provider": "ollama", "model": "phi3:mini"},
            "quickRefactor": {"provider": "ollama", "model": "gemma2:9b"}
        }
    
    def route(self, model: str, messages: List[Dict], context: str = None) -> tuple:
        """
        Route request to provider.
        
        Returns: (provider, actual_model)
        """
        # Check for explicit model switching (/model command)
        if model.startswith("ollama/"):
            return "ollama", model.replace("ollama/", "")
            
        # Use context-aware routing
        if context in self.routing_rules:
            rule = self.routing_rules[context]
            return rule["provider"], rule["model"]
            
        # Map Anthropic model tiers to local models
        if "haiku" in model.lower():
            return self.routing_rules["fileSearch"]["provider"], \
                   self.routing_rules["fileSearch"]["model"]
        elif "sonnet" in model.lower():
            return self.routing_rules["coding"]["provider"], \
                   self.routing_rules["coding"]["model"]
        elif "opus" in model.lower():
            return "ollama", "llama3.1:70b"
            
        # Default fallback
        return "ollama", "llama3.1"
```

### 5. Workflow Integration

```python
# Location: src/kailash/channels/anthropic_executor.py

class AnthropicWorkflowExecutor:
    """
    Executes AI requests via Kailash workflows.
    
    Wraps provider calls in Kailash workflow infrastructure
    for monitoring, logging, and enterprise features.
    """
    
    def __init__(self):
        self.runtime = AsyncLocalRuntime()
    
    async def execute_chat(self, provider: str, model: str, 
                          messages: List[Dict], **kwargs) -> Dict:
        """
        Execute chat via Kailash workflow:
        
        1. Build workflow with LLMAgentNode
        2. Configure with provider/model
        3. Execute via AsyncLocalRuntime
        4. Return standardized response
        """
        from kailash.workflow.builder import WorkflowBuilder
        
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "agent", {
            "provider": provider,
            "model": model,
            "messages": messages,
            **kwargs
        })
        
        results = await self.runtime.execute_workflow_async(
            workflow.build(),
            inputs={}
        )
        
        return results.get("agent", {})
```

---

## 🚀 Implementation Plan

### Phase 1: Core Channel Infrastructure (Week 1)

**Goal**: Create basic AnthropicProxyChannel with Ollama support

**Tasks**:
1. Create `anthropic_channel.py` extending `Channel` base class
2. Implement FastAPI server with `/v1/messages` endpoint
3. Add request/response translation for Ollama
4. Integrate with existing `OllamaProvider`
5. Write comprehensive tests

**Files to Create**:
```
src/kailash/channels/
├── anthropic_channel.py         # Main channel implementation
├── anthropic_translator.py      # Request/response translation
├── anthropic_router.py          # Context-aware routing
└── anthropic_executor.py        # Workflow execution

tests/unit/channels/
├── test_anthropic_channel.py
├── test_anthropic_translator.py
└── test_anthropic_router.py
```

**Success Criteria**:
- ✅ Channel starts/stops cleanly
- ✅ Basic `/v1/messages` endpoint works
- ✅ Claude Code can connect and execute simple queries
- ✅ Ollama provider translates correctly
- ✅ 90%+ test coverage

### Phase 2: Multi-Provider Support (Week 2)

**Goal**: Add OpenAI, Gemini, Anthropic direct support

**Tasks**:
1. Implement `ProviderRegistry` with auto-discovery
2. Add translation layers for each provider
3. Create provider-specific parameter mapping
4. Implement provider fallback logic
5. Add comprehensive provider tests

**Files to Modify/Create**:
```
src/kailash/channels/
├── anthropic_channel.py         # Add multi-provider support
├── anthropic_translator.py      # Add provider-specific translators
└── provider_registry.py         # NEW: Provider management

apps/kailash-kaizen/
└── configs/
    └── anthropic_proxy_config.yaml  # NEW: Provider configuration
```

**Success Criteria**:
- ✅ All 4 providers (Ollama, OpenAI, Gemini, Anthropic) work
- ✅ Automatic fallback when provider unavailable
- ✅ Provider-specific features preserved (tools, streaming)

### Phase 3: Advanced Features (Week 3)

**Goal**: Add context-aware routing, streaming, tool calling

**Tasks**:
1. Implement `ContextAwareRouter` with task-based routing
2. Add SSE streaming support
3. Implement tool/function calling translation
4. Add dynamic model switching via `/model` command
5. Create session management

**Files to Modify/Create**:
```
src/kailash/channels/
├── anthropic_router.py          # Context-aware routing
├── anthropic_streaming.py       # NEW: SSE streaming handler
├── anthropic_tools.py           # NEW: Tool calling translation
└── anthropic_session.py         # NEW: Session management

apps/kailash-kaizen/
└── src/kaizen/proxy/
    └── model_switcher.py        # NEW: Dynamic model switching
```

**Success Criteria**:
- ✅ Context routing works (coding → qwen, file search → phi3)
- ✅ Streaming responses work with Claude Code
- ✅ Tool calls translate correctly across providers
- ✅ `/model` command switches providers mid-session

### Phase 4: Enterprise Features (Week 4)

**Goal**: Add rate limiting, monitoring, auth, configuration

**Tasks**:
1. Integrate with existing Nexus auth system
2. Add rate limiting per API key
3. Implement comprehensive monitoring/metrics
4. Create web UI for configuration
5. Add cost tracking and budget alerts

**Files to Create**:
```
src/kailash/channels/
├── anthropic_auth.py            # NEW: Authentication
├── anthropic_ratelimit.py       # NEW: Rate limiting
└── anthropic_monitor.py         # NEW: Monitoring

apps/kailash-kaizen/
└── src/kaizen/proxy/
    ├── dashboard.py             # NEW: Web UI for config
    ├── cost_tracker.py          # NEW: Cost tracking
    └── budget_manager.py        # NEW: Budget management
```

**Success Criteria**:
- ✅ API key authentication works
- ✅ Rate limiting enforced per key
- ✅ Real-time monitoring dashboard
- ✅ Cost tracking for all providers
- ✅ Budget alerts trigger correctly

---

## 🔧 Configuration Design

### User-Facing Configuration (Zero-Config Philosophy)

```python
# Option 1: Pure Python (Zero Config)
from kaizen.proxy import AnthropicProxy

# Zero configuration - auto-discovers Ollama
proxy = AnthropicProxy()
proxy.start()

# Option 2: Basic Configuration
proxy = AnthropicProxy(
    port=8082,
    preferred_provider="ollama",
    ollama_models={
        "big": "qwen2.5-coder:32b",
        "small": "phi3:mini"
    }
)
proxy.start()

# Option 3: Multi-Provider Configuration
proxy = AnthropicProxy(
    providers={
        "ollama": {
            "models": ["qwen2.5-coder:32b", "llama3.1", "phi3:mini"],
            "api_base": "http://localhost:11434"
        },
        "openai": {
            "api_key": "sk-...",
            "models": ["gpt-4o", "gpt-4o-mini"]
        }
    },
    routing={
        "coding": {"provider": "ollama", "model": "qwen2.5-coder:32b"},
        "fileSearch": {"provider": "ollama", "model": "phi3:mini"}
    }
)
proxy.start()
```

### YAML Configuration (Alternative)

```yaml
# ~/.kaizen/anthropic_proxy.yaml
port: 8082
log_level: INFO
timeout_ms: 600000

providers:
  ollama:
    enabled: true
    api_base: http://localhost:11434
    models:
      - qwen2.5-coder:32b
      - llama3.1:70b
      - llama3.1
      - phi3:mini
  
  openai:
    enabled: false
    api_key: ${OPENAI_API_KEY}
    models:
      - gpt-4o
      - gpt-4o-mini
  
  gemini:
    enabled: false
    api_key: ${GEMINI_API_KEY}
    models:
      - gemini-2.5-pro
      - gemini-2.0-flash

routing:
  default:
    provider: ollama
    model: llama3.1
  
  context_rules:
    coding:
      provider: ollama
      model: qwen2.5-coder:32b
    
    debugging:
      provider: ollama
      model: qwen2.5-coder:32b
    
    fileSearch:
      provider: ollama
      model: phi3:mini
    
    syntaxCheck:
      provider: ollama
      model: phi3:mini

model_mapping:
  # Map Anthropic model names to local models
  claude-haiku: phi3:mini
  claude-sonnet: qwen2.5-coder:32b
  claude-opus: llama3.1:70b

enterprise:
  enable_auth: false
  enable_rate_limiting: false
  enable_monitoring: true
  enable_cost_tracking: true
```

### Integration with Nexus

```python
# Nexus automatically includes AnthropicProxy as a channel
from nexus import Nexus

app = Nexus(
    enable_anthropic_proxy=True,
    anthropic_proxy_config={
        "port": 8082,
        "preferred_provider": "ollama"
    }
)

app.start()
# Now starts API, CLI, MCP, AND Anthropic Proxy channels!
```

---

## 🌟 Best Features from Competitors

### From `claude-code-router` (musistudio)
- ✅ Dynamic model switching via `/model` command
- ✅ Context-aware routing (task-based)
- ✅ Web UI for configuration
- ✅ Multiple provider support
- ✅ Custom transformers

### From `claude-code-ollama-proxy` (1rgs)
- ✅ LiteLLM-based architecture
- ✅ Simple environment configuration
- ✅ Docker support
- ✅ Streaming SSE

### From `claude-code-proxy` (fuergaosi233)
- ✅ Function calling support
- ✅ Azure OpenAI support
- ✅ Clean Python FastAPI design

### From `AstroAir/ollama-proxy`
- ✅ Load balancing
- ✅ Automatic failover
- ✅ Model filtering
- ✅ Performance monitoring

### Our Unique Advantages
- ✅ **Built on Kailash SDK** - Leverages proven enterprise infrastructure
- ✅ **Nexus Integration** - Works seamlessly with multi-channel platform
- ✅ **Workflow-based** - All requests execute via monitored workflows
- ✅ **Zero-config** - Just `AnthropicProxy().start()`
- ✅ **Enterprise Ready** - Auth, rate limiting, audit logs built-in
- ✅ **Cost Tracking** - Monitor and optimize API usage
- ✅ **Provider Abstraction** - Reuses existing Kailash AI provider system

---

## 📊 Comparison with Competitors

| Feature | claude-code-router | claude-code-ollama-proxy | Our Implementation |
|---------|-------------------|--------------------------|-------------------|
| **Framework** | Node.js | Python/LiteLLM | Python/Kailash SDK |
| **Multi-Provider** | ✅ 8+ providers | ✅ 3 providers | ✅ Unlimited (extensible) |
| **Model Switching** | ✅ `/model` command | ❌ Static | ✅ `/model` + context routing |
| **Web UI** | ✅ | ❌ | ✅ (Planned Phase 4) |
| **Context Routing** | ✅ | ❌ | ✅ Enhanced |
| **Streaming** | ✅ | ✅ | ✅ |
| **Tool Calling** | ✅ | ✅ | ✅ |
| **Auth** | ❌ | ❌ | ✅ (Nexus auth) |
| **Rate Limiting** | ❌ | ❌ | ✅ (Nexus rate limiting) |
| **Monitoring** | Basic logs | Basic logs | ✅ Enterprise monitoring |
| **Cost Tracking** | ❌ | ❌ | ✅ |
| **Zero Config** | ❌ Complex config | ✅ Simple | ✅ True zero config |
| **Enterprise Features** | ❌ | ❌ | ✅ Full suite |

---

## 🎓 Technical Deep Dive

### Why Nexus Channel is Perfect for This

1. **Already Multi-Channel**: Nexus handles API/CLI/MCP - adding Anthropic is natural
2. **Proven Patterns**: Channel base class provides lifecycle, event handling, sessions
3. **Enterprise Features**: Auth, rate limiting, monitoring already built
4. **Zero-Config**: Matches Nexus philosophy - `AnthropicProxy().start()`
5. **Workflow Integration**: All requests become workflows = full observability

### Request Flow Diagram

```
Claude Code Request
        ↓
[AnthropicProxyChannel]
        ↓
[Request Parser] → Parse /v1/messages
        ↓
[ContextAwareRouter] → Determine provider/model
        ↓
[ProviderRegistry] → Get provider instance
        ↓
[RequestTranslator] → Translate to provider format
        ↓
[AnthropicWorkflowExecutor] → Build & execute workflow
        ↓
[Kailash Runtime] → Execute LLMAgentNode
        ↓
[Provider (Ollama/OpenAI/etc)] → Get AI response
        ↓
[ResponseTranslator] → Translate to Anthropic format
        ↓
[AnthropicProxyChannel] → Return response
        ↓
Claude Code receives response
```

### Streaming Flow

```
Claude Code (SSE Client)
        ↓
[AnthropicProxyChannel] /v1/messages?stream=true
        ↓
[StreamingHandler] → Setup SSE connection
        ↓
[Provider Streaming] → Get chunks from provider
        ↓
[ChunkTranslator] → Convert to Anthropic SSE format
        ↓
[SSE Stream] → Send "data: {...}\n\n" events
        ↓
Claude Code receives incremental response
```

---

## 🧪 Testing Strategy

### Unit Tests (Tier 1)
```python
# tests/unit/channels/test_anthropic_channel.py
def test_channel_initialization()
def test_request_parsing()
def test_response_formatting()
def test_error_handling()

# tests/unit/channels/test_anthropic_translator.py
def test_message_translation_ollama()
def test_message_translation_openai()
def test_tool_translation()
def test_parameter_mapping()

# tests/unit/channels/test_anthropic_router.py
def test_context_routing()
def test_model_mapping()
def test_provider_fallback()
def test_dynamic_switching()
```

### Integration Tests (Tier 2)
```python
# tests/integration/channels/test_anthropic_proxy_integration.py
async def test_ollama_chat_request()
async def test_streaming_response()
async def test_tool_calling()
async def test_multi_provider_routing()
async def test_session_management()
```

### E2E Tests (Tier 3)
```python
# tests/e2e/test_claude_code_integration.py
def test_claude_code_connection()
def test_simple_query()
def test_multi_turn_conversation()
def test_model_switching()
def test_file_operations()
```

---

## 📝 Documentation Plan

### User Guides
1. **Quick Start Guide** - Get running in 5 minutes
2. **Configuration Guide** - All configuration options
3. **Provider Guide** - Setting up each provider
4. **Model Mapping Guide** - Optimal model selection
5. **Troubleshooting Guide** - Common issues and solutions

### Developer Guides
1. **Architecture Overview** - System design
2. **Adding Providers** - Extend with new providers
3. **Custom Routing** - Implement routing strategies
4. **Testing Guide** - Writing tests for proxy features
5. **Contributing Guide** - How to contribute

### API Documentation
1. **Anthropic API Compatibility** - Supported endpoints
2. **Extensions** - Custom features beyond Anthropic API
3. **Configuration API** - Programmatic configuration
4. **Monitoring API** - Metrics and health endpoints

---

## 🚀 Launch Checklist

### MVP (Phase 1)
- [ ] AnthropicProxyChannel implemented
- [ ] Ollama provider integration
- [ ] Basic `/v1/messages` endpoint
- [ ] Request/response translation
- [ ] Unit tests (90%+ coverage)
- [ ] Quick start documentation
- [ ] Claude Code connection verified

### Beta (Phase 2-3)
- [ ] Multi-provider support
- [ ] Context-aware routing
- [ ] Streaming support
- [ ] Tool calling support
- [ ] Dynamic model switching
- [ ] Session management
- [ ] Integration tests
- [ ] Comprehensive documentation

### Production (Phase 4)
- [ ] Enterprise features (auth, rate limiting)
- [ ] Monitoring dashboard
- [ ] Cost tracking
- [ ] Budget management
- [ ] E2E tests
- [ ] Performance optimization
- [ ] Production deployment guide
- [ ] Migration guide from other proxies

---

## 🎯 Success Metrics

### Technical Metrics
- **Response Time**: <500ms for non-streaming requests
- **Streaming Latency**: <100ms time-to-first-token
- **Uptime**: 99.9% availability
- **Test Coverage**: >90% across all components
- **Translation Accuracy**: 100% API compatibility

### User Metrics
- **Setup Time**: <5 minutes from install to first request
- **Provider Support**: 4+ providers at launch
- **Model Support**: 10+ models across providers
- **Documentation**: 100% API coverage

### Enterprise Metrics
- **Auth Success Rate**: 100% valid requests pass
- **Rate Limit Enforcement**: 100% accuracy
- **Cost Tracking Accuracy**: Within 1% of actual costs
- **Monitoring Coverage**: All critical paths instrumented

---

## 🔮 Future Enhancements

### Phase 5: Advanced AI Features
- **Prompt Caching** - Cache common prompts for speed
- **Request Batching** - Batch multiple requests
- **Automatic Retry** - Smart retry with backoff
- **Circuit Breaker** - Prevent cascading failures

### Phase 6: Multi-Model Orchestration
- **Ensemble Routing** - Route to multiple models, merge responses
- **A/B Testing** - Compare model performance
- **Model Fallback Chain** - Try multiple models on failure
- **Quality Scoring** - Rate and route based on response quality

### Phase 7: Advanced Monitoring
- **Trace Visualization** - Full request traces
- **Performance Analytics** - Deep performance insights
- **Cost Optimization** - AI-powered cost reduction
- **Anomaly Detection** - Detect unusual patterns

---

## 💡 Key Insights

### Why This Beats Competitors

1. **Built on Proven Infrastructure**: Kailash SDK is battle-tested with 4000+ tests
2. **True Zero-Config**: Nexus philosophy - just start and it works
3. **Enterprise Ready**: Auth, monitoring, rate limiting built-in
4. **Workflow Integration**: Full observability via Kailash workflows
5. **Provider Abstraction**: Reuses existing AI provider system
6. **Channel Architecture**: Natural fit with Nexus multi-channel design
7. **Extensible**: Add new providers without core changes

### Design Principles

1. **Zero-Config First**: Should work with no configuration
2. **Progressive Enhancement**: Add complexity only when needed
3. **Provider Agnostic**: Any provider can be added
4. **Enterprise Grade**: Security, monitoring, cost tracking built-in
5. **Developer Friendly**: Clear APIs, comprehensive docs
6. **Test Driven**: >90% coverage, comprehensive test suite
7. **Kailash Native**: Uses SDK patterns throughout

---

## 📚 References

### Internal Documentation
- [Nexus Architecture](apps/kailash-nexus/README.md)
- [Channels System](src/kailash/channels/base.py)
- [AI Providers](src/kailash/nodes/ai/ai_providers.py)
- [Workflow Builder](src/kailash/workflow/builder.py)
- [Kaizen Framework](apps/kailash-kaizen/README.md)

### External References
- [claude-code-router](https://github.com/musistudio/claude-code-router)
- [claude-code-ollama-proxy](https://github.com/1rgs/claude-code-openai)
- [claude-code-proxy](https://github.com/fuergaosi233/claude-code-proxy)
- [Anthropic API Docs](https://docs.anthropic.com/en/api)

---

**Next Steps**: Review this design, get feedback, and proceed with Phase 1 implementation.
