# Workspace: issue-498-llm-deployment

Created: 2026-04-18
Source: GH issue #498 (cross-SDK mirror of kailash-rs#406)

## Goal

Implement the four-axis LLM deployment abstraction in `kailash.kaizen`
mirroring kailash-rs#406 semantics. Preset names, `from_env()` precedence,
observability field names, and security posture MUST match the Rust
implementation per EATP D6 (independent implementation, matching semantics).

## Issue summary (from #498)

`kailash.kaizen.LlmClient` today uses a provider-centric shape that
conflates four independent axes:

1. **Wire protocol** — OpenAI-chat, Anthropic-messages, Gemini
2. **Auth method** — bearer token, AWS SigV4/bearer, GCP OAuth, Azure Entra
3. **Endpoint** — api.openai.com, bedrock-runtime.{region}.amazonaws.com, …
4. **Model grammar** — `gpt-4o`, `anthropic.claude-3-5-sonnet-20241022-v2:0`,
   Azure deployment name, Vertex model ID

Downstream consumers can't express Bedrock-Claude, Vertex-Claude,
Azure-OpenAI, Groq, Together, air-gapped vLLM/TGI/LM Studio.

## Target architecture

```python
from kailash.kaizen import LlmClient, LlmDeployment, AwsBearerToken

client = LlmClient.from_deployment(
    LlmDeployment.bedrock_claude(region="ap-southeast-1", auth=AwsBearerToken.from_env())
)
client = LlmClient.from_deployment(LlmDeployment.openai())
client = LlmClient.from_deployment(
    LlmDeployment.openai_compatible(base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"])
)
```

Providers become presets. Four axes decomposed. Back-compat preserved via
preset-backed implementation.

## Semantic invariants (MUST match Rust per EATP D6)

- Preset names: `openai`, `anthropic`, `bedrock_claude`, `vertex_claude`,
  `azure_openai`, `groq`, `openai_compatible`, `anthropic_compatible`, `mock`
- `from_env()` precedence: `KAILASH_LLM_DEPLOYMENT` URI > `KAILASH_LLM_PROVIDER`
  selector > legacy per-provider env keys
- `AWS_BEARER_TOKEN_BEDROCK` alone activates `bedrock_claude`
- Observability `deployment_preset` log field (NOT credential)
- SSRF guard + DNS-rebinding defense on every preset's HTTP client

## Back-compat constraints (MUST hold)

- `kailash.LlmClient()` today — preserved via preset-backed implementation
- `kailash.Agent(config, client)` — unchanged
- Legacy env-key detection preserved in `from_env()`
- Zero breaking changes for callers that work today

## Shards (from issue #498, mirror of Rust S1–S9)

- **S1** — Foundation types in `kailash/kaizen/llm/deployment.py`
- **S2** — Migrate OpenAI path to preset
- **S3** — Migrate Anthropic + Google
- **S4** — AWS auth + `LlmDeployment.bedrock_claude(...)` + Tier 2 test
- **S5** — GCP auth + Vertex presets
- **S6** — Azure auth + `LlmDeployment.azure_openai(...)`
- **S7** — `from_env()` richer config
- **S8** — N/A (Python IS the binding surface, no PyO3 layer)
- **S9** — Parity test suite vs Rust SDK; docs update

## References (local)

- Rust design spec: `/Users/esperie/repos/loom/kailash-rs/specs/llm-deployments.md`
- Rust ADR: `/Users/esperie/repos/loom/kailash-rs/workspaces/use-feedback-triage/02-plans/02-adrs/ADR-0001-llm-deployment-abstraction.md`
- Rust BUILD issue: `esperie-enterprise/kailash-rs#406`
- Reporter chain: `terrene-foundation/kailash-coc-claude-rs#52`

## Out of scope

- Rust SDK implementation (tracked upstream in kailash-rs#406)
- `LlmProvider` removal (stays through all 2.x minor versions)

## Success criteria (verbatim from #498)

- [ ] Foundation types land in `kailash/kaizen/llm/deployment.py`
- [ ] OpenAI, Anthropic, Google paths migrated to preset-backed impl
- [ ] Bedrock-Claude, Vertex-Claude, Azure OpenAI presets functional with real Tier 2 tests
- [ ] `from_env()` URI parser + legacy fallback
- [ ] Parity test suite vs Rust SDK (preset names, env precedence, observability shape)
- [ ] Existing `LlmClient()` callers continue to work unchanged
