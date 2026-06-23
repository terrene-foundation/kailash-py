# Kaizen LLM Deployment Abstraction (#498) + Embed (#462)

`kaizen.llm.LlmClient` is the low-level wire surface for LLM deployments — separate from the `kaizen_agents.Delegate` high-level agent API. Use this skill when working with the deployment-target abstraction, preset factories, or the wire-send methods (`embed()` today, `complete()` when it lands).

For Delegate / multi-agent / signatures, see `SKILL.md` + `kaizen-multi-provider.md`. This file is the **wire layer** beneath those abstractions.

**Load first** when touching: `LlmDeployment`, `LlmClient`, `kaizen.llm.wire_protocols.*`, `from_deployment` / `from_env`, `embed()`, or adding a new wire-send method.

Authority spec: `specs/kaizen-llm-deployments.md` (domain truth for parity + env precedence).

## Four-Axis Deployment (#498)

`LlmDeployment` decomposes an LLM provider into four independent axes so one shape expresses Bedrock-Claude, Vertex-Claude, Azure-OpenAI, Groq, air-gapped vLLM, etc.:

```
LlmDeployment(
    wire:     WireProtocol,    # on-the-wire schema (OpenAiChat, AnthropicMessages, ...)
    endpoint: Endpoint,        # base_url + path_prefix + required_headers
    auth:     AuthStrategy,    # Bearer, AwsSigV4, AwsBearerToken, GcpOauth, AzureEntra, StaticNone
    default_model: str,        # model name (MUST come from env per rules/env-models.md)
)
```

**Providers are presets over the four axes.** 24 preset factories ship as classmethods on `LlmDeployment`:

```python
from kaizen.llm import LlmDeployment, LlmClient
import os

# Direct provider (15 presets)
deployment = LlmDeployment.openai(
    api_key=os.environ["OPENAI_API_KEY"],
    model=os.environ["OPENAI_PROD_MODEL"],
)
# anthropic, google, cohere, mistral, perplexity, huggingface, ollama,
# docker_model_runner, groq, together, fireworks, openrouter, deepseek,
# lm_studio, llama_cpp — same shape.

# Cloud providers (9 presets)
deployment = LlmDeployment.bedrock_claude(
    region="ap-southeast-1",
    model=os.environ["BEDROCK_MODEL_ID"],
    auth=AwsBearerToken.from_env(),
)
# bedrock_llama, bedrock_titan, bedrock_mistral, bedrock_cohere,
# vertex_claude, vertex_gemini, azure_openai.

client = LlmClient.from_deployment(deployment)
```

## from_env() precedence (#498 S7)

Three-tier resolution; first tier present wins. Deployment-tier signals coexisting with legacy keys emit a WARN (the deployment path still wins):

| Tier | Signal | Grammar |
| ---- | ------ | ------- |
| 1 | `KAILASH_LLM_DEPLOYMENT` URI | `bedrock://region/model`, `vertex://project/location/model`, `azure://resource/deployment`, `openai-compat://base_url` |
| 2 | `KAILASH_LLM_PROVIDER` selector | `openai` / `anthropic` / `bedrock_claude` / `vertex_claude` / `azure_openai` / `groq` / `openai_compatible` / `anthropic_compatible` / `mock` |
| 3 | Legacy per-provider keys | `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → `GOOGLE_API_KEY` → Azure → Bedrock (bearer token alone activates `bedrock_claude`) |

```python
client = LlmClient.from_env()  # returns a usable client or raises ConfigError
```

Sync variant exists for API symmetry: `LlmClient.from_deployment_sync(d)` — construction does no I/O, the method simply signals intent to use sync wire-send methods.

## Wire-send dispatch pattern (#462 embed)

`LlmClient.embed()` is the first wire-send method. It dispatches on `WireProtocol` enum keyed against a `_EMBED_DISPATCH: dict` table:

```python
_EMBED_DISPATCH = {
    WireProtocol.OpenAiChat: {
        "path": "/embeddings",
        "shaper": openai_embeddings,
        "env_model_hint": "OPENAI_EMBEDDING_MODEL",
    },
    WireProtocol.OllamaNative: {
        "path": "/api/embed",
        "shaper": ollama_embeddings,
        "env_model_hint": "OLLAMA_EMBEDDING_MODEL",
    },
}
```

**This is permitted deterministic logic** per `rules/agent-reasoning.md`: dispatching on a typed configuration enum is structural routing, NOT keyword-matching on user input.

**When adding a new wire (e.g. Mistral embeddings, Bedrock embeddings):**

1. Create `kaizen/llm/wire_protocols/<provider>_<op>.py` with two pure functions:

   ```python
   def build_request_payload(texts: list[str], model: str, options: EmbedOptions | None) -> dict: ...
   def parse_response(payload: dict) -> {"vectors": list[list[float]], "model": str, "usage": dict}: ...
   ```

   - Reject empty input at shaper boundary (typed error before HTTP)
   - Reject non-str elements (so `[b"bytes"]` doesn't make it into wire)
   - Return vectors in request order — if the provider reorders (OpenAI returns by `index`), sort explicitly; docs do not guarantee order
   - Reject `bool` as an embedding value (`isinstance(v, (int, float)) and not isinstance(v, bool)`)

2. Add an entry to `_EMBED_DISPATCH` in `client.py`. No conditional branches — one entry, one shaper.

3. Add `export` in `kaizen/llm/wire_protocols/__init__.py`.

4. Write Tier 1 shaper tests + Tier 2 wiring test through `LlmClient.from_deployment()` facade per `rules/facade-manager-detection.md` and `rules/orphan-detection.md`.

**`complete()` is BLOCKED until wired end-to-end.** `client.py:23-34` deliberately has NO `complete()` method — per `rules/zero-tolerance.md` Rule 2 and `rules/orphan-detection.md` Rule 3, shipping a `NotImplementedError` stub on a public API is blocked. Redteam HIGH removed the stub in commit `8dbb6e1c`. When `complete()` lands, it follows the same dispatch pattern as `embed()`.

## HTTP layer contract

**Every outbound HTTP call MUST route through `LlmHttpClient`** (SSRF-safe via `SafeDnsResolver`). Direct `httpx.AsyncClient(...)` construction inside a wire adapter is BLOCKED — the single constructor site is `LlmHttpClient.__init__`.

```python
# DO — the wire adapter is pure (shapes), the send is through LlmHttpClient
http_client = LlmHttpClient(deployment_preset=wire.name, timeout=60.0)
resp = await http_client.post(url, headers=..., json=payload, auth_strategy_kind=...)

# DO NOT — bypasses SafeDnsResolver, SSRF defense gone
client = httpx.AsyncClient(timeout=60)
resp = await client.post(url, json=payload)
```

SSRF regression tests MUST exist for each new wire-send method — assert `EndpointError` (the common base of `InvalidEndpoint` / `Unreachable`) is raised when `base_url` points at the AWS metadata IP (`169.254.169.254`). The test runs always (no external infra) and catches rejection at either construction time or connect time.

## Cross-SDK parity (#498 S9)

`specs/kaizen-llm-deployments.md` is the domain-truth. Per `rules/cross-sdk-inspection.md` EATP D6:

- **Semantics match**: preset names IDENTICAL across Python + Rust (`openai`, `bedrock_claude`, `vertex_claude`, …)
- **`from_env()` precedence IDENTICAL**: URI > selector > legacy
- **Wire shapers are byte-identical** for fixed input (stricter than the general "semantics match" rule — the JSON body sent to the provider must be the same bytes from both SDKs)
- Implementation idioms may differ (Pydantic classmethods on Python, typed constructors on Rust)


## Error taxonomy

All errors route through `kaizen.llm.errors` (see `errors.py`):

```
LlmClientError
├── LlmError
│   ├── Timeout                 # configured deadline exceeded
│   ├── RateLimited             # 429 + retry_after hint
│   ├── ProviderError           # 4xx/5xx with credential-scrubbed body snippet (256 chars)
│   └── InvalidResponse         # non-JSON / schema violation
├── AuthError
│   ├── Invalid                 # credential rejected, 8-char fingerprint only (no raw)
│   ├── Expired                 # access token past expiry
│   └── MissingCredential       # envelope not found (source_hint is const, not user input)
├── EndpointError
│   ├── InvalidEndpoint         # reason from allowlist (scheme, private_ipv4, metadata_service, ...)
│   └── Unreachable             # resolved but TCP failed
├── ModelGrammarError
│   ├── ModelGrammarInvalid     # malformed deployment grammar
│   └── ModelRequired           # preset constructed without required model string
└── ConfigError
    ├── NoKeysConfigured        # from_env() found nothing
    ├── InvalidUri              # KAILASH_LLM_DEPLOYMENT URI failed per-scheme regex
    └── InvalidPresetName       # register_preset() name failed regex gate
```

Never invent new exceptions. `ProviderError.body_snippet` is auto-scrubbed for known credential patterns (OpenAI `sk-proj-*` / `sk-ant-*` / `sk-*`, Google `AIza*`, AWS `AKIA*`/`ASIA*`, generic `Bearer`, JWT, Azure SAS `sig=`) BEFORE truncation to 256 chars.

## Classification policy pass-through (§6.5)

`LlmClient(deployment, classification_policy=policy, caller_clearance=clearance)` — optional. When installed, `redact_request_messages()` routes outbound messages through `redact_messages()` before wire serialization, applying DataFlow-compatible masking to classified fields in prompt payloads. The policy is duck-typed on `apply_masking_to_record(model_name, record, caller_clearance)` — any producer works, though `dataflow.ClassificationPolicy` is canonical.

## Testing layout (cross-reference)

| Tier | Location | Purpose |
| ---- | -------- | ------- |
| 1 | `tests/unit/llm/test_*.py` | Shaper pure-function contract, preset construction, URI grammar |
| 2 | `tests/integration/llm/test_<subject>_wiring.py` | Real provider if creds in env, structural + SSRF regression always |
| Cross-SDK | `tests/integration/llm/test_cross_sdk_parity.py` | Byte-identical payload-builder comparison with Rust fixtures |

File naming convention enforced: Tier 2 files are `test_<lowercase_subject>_wiring.py` so absence is grep-able per `rules/facade-manager-detection.md` §2.

## Origin

- `specs/kaizen-llm-deployments.md` — authoritative spec
- four-axis abstraction + 24 presets + from_env + CHANGELOG + migration guide
- `embed()` wire-send method for OpenAI + Ollama (precedent for `complete()`)
