# kailash-rs LLM Provider Layer Audit — 2026-04-07

## Scale

- **5,824 LOC across 7 files** in `crates/kailash-kaizen/src/llm/`
- **5 provider adapters**: openai, anthropic, google, azure, mock
- **138 unit tests** across the module

## Module Structure

```
crates/kailash-kaizen/src/llm/
├── mod.rs              (17 lines)   — Module declaration, re-exports
├── client.rs           (2,347 lines) — LlmClient dispatcher + retry logic
├── openai.rs           (528 lines)  — OpenAI adapter
├── anthropic.rs        (875 lines)  — Anthropic Claude adapter
├── google.rs           (869 lines)  — Google Gemini adapter
├── azure.rs            (327 lines)  — Azure OpenAI config wrapper
└── mock.rs             (861 lines)  — Mock provider for testing
```

## Architecture: Adapters (NOT a trait-based interface)

Rust uses `struct`-based adapters that each have methods; the `LlmClient` dispatches by detecting the provider from the model prefix.

### LlmClient (client.rs)

```rust
pub struct LlmClient {
    http: Client,                                    // reqwest HTTP client
    keys: HashMap<LlmProvider, String>,              // API keys per provider
    base_urls: HashMap<LlmProvider, String>,         // override URLs (testing, Azure)
    max_retries: u32,                                // default 3
    retry_base_delay: Duration,                      // exponential backoff
    timeout: Duration,                               // default 60s
    openai_adapter: OpenAiAdapter,
    anthropic_adapter: AnthropicAdapter,
    google_adapter: GoogleAdapter,
    mock_provider: Option<Arc<MockLlmProvider>>,
    streaming_config: StreamingConfig,
    auth_mode: AuthMode,                             // Bearer vs AzureApiKey
    provider_override: Option<LlmProvider>,
}

impl LlmClient {
    // Entry points
    pub async fn complete(&self, request: &LlmRequest) -> Result<LlmResponse, LlmClientError>;
    pub fn stream_completion<'a>(&'a self, request: &'a LlmRequest)
        -> Pin<Box<dyn Stream<Item = Result<String, LlmClientError>> + Send + 'a>>;

    // Construction
    pub fn from_env() -> Result<Self, LlmClientError>;
    pub fn new() -> Self;
    pub fn with_openai_key(mut self, key: String) -> Self;
    pub fn with_anthropic_key(mut self, key: String) -> Self;
    pub fn with_google_key(mut self, key: String) -> Self;
    pub fn with_max_retries(mut self, n: u32) -> Self;
    pub fn with_timeout(mut self, d: Duration) -> Self;
    pub fn with_streaming_config(mut self, c: StreamingConfig) -> Self;
    pub fn with_base_url(mut self, p: LlmProvider, url: String) -> Self;
    pub fn with_auth_mode(mut self, m: AuthMode) -> Self;
    pub fn mock_provider(&self) -> Option<Arc<MockLlmProvider>>;
    pub fn from_mock(mock: Arc<MockLlmProvider>) -> Self;
}
```

**Provider detection**: string matching on model name prefix (`gpt-` → OpenAI, `claude-` → Anthropic, `gemini-` → Google).

### Per-Adapter Interface (Consistent)

Every provider adapter (OpenAI, Anthropic, Google) is a unit struct with these methods:

```rust
pub struct XxxAdapter;  // unit struct, stateless

impl XxxAdapter {
    pub fn build_chat_request(&self, req: &LlmRequest) -> serde_json::Value;
    pub fn parse_chat_response(&self, body: &[u8]) -> Result<LlmResponse, AgentError>;
    pub fn parse_stream_chunk(&self, line: &str) -> Option<String>;
    pub fn chat_endpoint(&self) -> &'static str;
    pub fn auth_header(&self, api_key: &str) -> (String, String);
    // Anthropic-specific
    pub fn auth_headers(&self, api_key: &str) -> Vec<(String, String)>;
    // Google-specific
    pub fn auth_query_param(&self, api_key: &str) -> (String, String);
    pub fn stream_endpoint(&self, model: &str) -> String;
}
```

**Advantage**: each adapter is stateless, testable in isolation, no trait bounds to fight.

## Provider Feature Matrix

| Feature                     | OpenAI    | Anthropic | Google  | Azure     | Mock |
| --------------------------- | --------- | --------- | ------- | --------- | ---- |
| Streaming                   | ✓         | ✓         | ✓       | ✓\*       | ✓    |
| Tool calling                | ✓         | ✓         | ✓       | ✓\*       | ✓    |
| Structured outputs (JSON)   | ✓         | ✓         | ✓       | ✓\*       | ✗    |
| Embeddings                  | ✗         | ✗         | ✗       | ✗         | ✗    |
| Vision                      | ✗\*\*     | ✗\*\*     | ✗\*\*   | ✗\*\*     | ✗    |
| Audio                       | ✗\*\*     | ✗\*\*     | ✗\*\*   | ✗\*\*     | ✗    |
| Cost tracking               | ✗\*\*\*   | ✗\*\*\*   | ✗\*\*\* | ✗\*\*\*   | ✗    |
| Retry/backoff               | ✓         | ✓         | ✓       | ✓         | ✓    |
| BYOK multi-tenant           | ✓         | ✓         | ✓       | ✓         | ✓    |
| Reasoning models (o1/o3/o4) | ✗\*\*\*\* | ✗         | ✗       | ✗\*\*\*\* | ✗    |

- `*` Azure inherits from OpenAI adapter
- `**` Vision/Audio handled in `kaizen-agents/multimodal/` separately
- `***` Cost tracking in `kailash-kaizen/src/cost/` module, not in LLM client
- `****` o1/o3/o4 prefix detected but special parameter handling NOT applied (should use `max_completion_tokens`, disable `temperature`)

## Azure as a Wrapper (Not an Adapter)

`AzureOpenAiConfig` in `azure.rs` is a **pre-configured LlmClient builder**, not a separate adapter:

```rust
pub struct AzureOpenAiConfig { ... }
impl AzureOpenAiConfig {
    pub fn builder() -> AzureOpenAiBuilder;
    pub fn chat_url(&self) -> String;
    pub fn into_client(self) -> LlmClient;  // produces LlmClient with:
                                              // - base_url set to Azure endpoint
                                              // - auth_mode = AzureApiKey
                                              // - provider_override = OpenAI
}
```

Validates: HTTPS required, SSRF blocklist, API version format (YYYY-MM-DD).

## Streaming Architecture

Rust uses `futures::Stream<Item = Result<String, LlmClientError>>`:

```rust
pub fn stream_completion<'a>(
    &'a self,
    request: &'a LlmRequest,
) -> Pin<Box<dyn Stream<Item = Result<String, LlmClientError>> + Send + 'a>>
```

**KEY LIMITATION**: NOT true incremental streaming. Collects full SSE response body first, then yields tokens one-by-one. Code comment (line 819-821):

> "True incremental SSE streaming (yielding tokens as they arrive from the network) requires a `tokio_util::io::StreamReader` or equivalent, which is not available in this crate's dependencies."

Uses `stream::once(async move { ... }).flat_map()` to convert bulk response into token stream.

## Cost Module (Rust Has, Python Lacks)

**Location**: `crates/kailash-kaizen/src/cost/`

```rust
// tracker.rs
pub struct CostTracker {
    config: CostConfig,
    cumulative_cost: Arc<Mutex<f64>>,        // in microdollars (integer precision)
    per_model: Arc<Mutex<HashMap<String, CostRecord>>>,
}

impl CostTracker {
    pub fn new(config: CostConfig) -> Self;
    pub fn record_usage(&self, model: &str, usage: &TokenUsage) -> Result<(), CostError>;
    pub fn total_cost_usd(&self) -> f64;
    pub fn per_model_cost(&self) -> HashMap<String, f64>;
    pub fn reset(&self);
}

// config.rs
pub struct CostConfig {
    pub model_pricing: HashMap<String, ModelPricing>,
    pub budget_limit: Option<f64>,
}

pub struct ModelPricing {
    pub prompt_price_per_token: f64,
    pub completion_price_per_token: f64,
}

// budget.rs
pub struct BudgetTracker {
    limit: f64,
    consumed: Arc<Mutex<f64>>,
}

impl BudgetTracker {
    pub fn check(&self, request_cost: f64) -> Result<(), BudgetExhausted>;
    pub fn remaining(&self) -> f64;
}

// monitored.rs
pub struct MonitoredAgent {
    inner: Arc<dyn BaseAgent>,
    tracker: Arc<CostTracker>,
}

impl BaseAgent for MonitoredAgent {
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError> {
        let result = self.inner.run(input).await?;
        self.tracker.record_usage(&result.model, &result.usage)?;
        Ok(result)
    }
}
```

**This is the composition-wrapper pattern in action**: `MonitoredAgent` wraps any `BaseAgent` and adds cost tracking. Python should port this pattern.

## Security Features

- **SSRF protection**: blocklist for AWS/GCP/Azure/Alibaba metadata endpoints
- **API keys NOT logged**: errors redact them
- **Per-request API key override** (BYOK multi-tenant)
- **Per-request base URL override** with SSRF validation
- **Sensitive data redaction** in Debug impl

## Error Handling

```rust
pub enum LlmClientError {
    Http(reqwest::Error),
    ApiError { provider: LlmProvider, status: StatusCode, message: String },
    MissingApiKey(String),
    UnsupportedProvider(String),
    Deserialization(String),
    NoKeysConfigured,
    SsrfBlocked(String),
    RetriesExhausted { attempts: u32, last_error: Box<LlmClientError> },
}
```

## Cross-Crate LLM Code Search

**Other crates using LLM**: only `kaizen-agents/src/multimodal/` (VisionProcessor, AudioProcessor, MultimodalOrchestrator) and `kailash-nodes/src/ai/` (embedding_node, llm_node, provider detection).

**Verdict**: NO duplicate LLM code. `kailash-kaizen` is the single source of truth.

## Missing Providers (vs Python Monolith)

| Provider          | Python              | Rust                |
| ----------------- | ------------------- | ------------------- |
| OpenAI            | ✓                   | ✓                   |
| Anthropic         | ✓                   | ✓                   |
| Google Gemini     | ✓                   | ✓                   |
| Azure OpenAI      | ✓                   | ✓ (wrapper)         |
| Mock              | ✓                   | ✓                   |
| Ollama            | ✓                   | ✗                   |
| Cohere            | ✓ (embed)           | ✗                   |
| HuggingFace       | ✓ (embed)           | ✗                   |
| Perplexity        | ✓                   | ✗                   |
| DockerModelRunner | ✓                   | ✗                   |
| AzureAIFoundry    | ✓                   | ✗                   |
| Mistral           | (via OpenAI-compat) | (via OpenAI-compat) |

Python has **11 concrete providers**, Rust has **5**. Rust must add: Ollama, Cohere, HuggingFace, Perplexity, Docker, AzureAIFoundry.

## Rust Advantages (to Port to Python)

1. **Modular layout** — 7 focused files vs Python's 5,001-line monolith
2. **Dedicated cost module** — CostTracker + BudgetTracker + MonitoredAgent wrapper
3. **SSRF protection** — metadata endpoint blocklist
4. **BYOK per-request overrides** — api_key + base_url from kwargs
5. **Explicit retry/backoff** — ExponentialBackoffRetry + CircuitBreakerRetry
6. **Type-safe error enum** — provider context preserved
7. **138 unit tests** with wiremock

## Rust Weaknesses (to Fix)

1. **No embeddings** in LLM client — should add `EmbeddingProvider` support
2. **No reasoning model handling** — o1/o3/o4 detected but not filtered
3. **Missing providers** (see table above)
4. **No true incremental streaming** — collects full response first
5. **Vision/Audio outside LLM module** — good separation but requires multi-crate coordination

## Convergence Target

**Python should adopt Rust's modular structure**:

```
packages/kailash-kaizen/src/kaizen/providers/
├── __init__.py
├── base.py           (BaseProvider, LLMProvider, EmbeddingProvider protocols)
├── streaming.py      (StreamingChatAdapter protocol)
├── registry.py       (get_provider() dispatcher)
├── cost.py           (CostTracker, BudgetTracker, ModelPricing) — NEW from Rust
├── config.py         (ProviderConfig dataclass)
├── errors.py         (ProviderError, sanitize_provider_error)
├── llm/
│   ├── openai.py
│   ├── anthropic.py
│   ├── google.py
│   ├── ollama.py
│   ├── azure.py
│   ├── perplexity.py
│   └── docker.py
└── embedding/
    ├── openai.py
    ├── cohere.py
    ├── huggingface.py
    └── ollama.py
```

**Rust should add** (per the audit recommendations):

1. Ollama, Cohere, HuggingFace, Perplexity, Docker adapters
2. Reasoning model parameter filtering (o1/o3/o4 → max_completion_tokens, temperature=1)
3. Embeddings in LLM client (or separate embedding crate)
4. True incremental streaming via tokio_util::io::StreamReader
