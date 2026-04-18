# Migrating to the LLM Deployment Abstraction (#498)

The four-axis `LlmDeployment` + `LlmClient` API shipped in #498 is **additive**. Your existing `kaizen.providers.registry.get_provider(...)` call sites continue to work unchanged. You can migrate incrementally.

## When to migrate

Migrate if you want any of:

- Cloud-provider routing (AWS Bedrock, GCP Vertex, Azure OpenAI)
- Single config entry point (`LlmClient.from_env()`) across OpenAI / Anthropic / cloud providers
- Cross-SDK portability (kailash-py ↔ kailash-rs deployments are byte-parity)
- Env-driven routing via `KAILASH_LLM_DEPLOYMENT` URI or `KAILASH_LLM_PROVIDER` selector
- Structural SSRF defense (LlmHttpClient + SafeDnsResolver)

## Quick reference

### Before

```python
from kaizen.providers.registry import get_provider

provider = get_provider(
    "openai",
    model="gpt-4o-mini",
    api_key=os.environ["OPENAI_API_KEY"],
)
```

### After (explicit)

```python
from kaizen.llm import LlmClient, LlmDeployment

deployment = LlmDeployment.openai(
    api_key=os.environ["OPENAI_API_KEY"],
    model=os.environ["OPENAI_PROD_MODEL"],
)
client = LlmClient.from_deployment(deployment)
```

### After (env-driven)

Set one of:

```bash
# URI form (highest priority)
export KAILASH_LLM_DEPLOYMENT="bedrock://us-east-1/claude-3-opus"
export AWS_BEARER_TOKEN_BEDROCK="..."

# Selector form
export KAILASH_LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-3-opus"

# Legacy autoselect form (still works)
export OPENAI_API_KEY="sk-..."
export OPENAI_PROD_MODEL="gpt-4o-mini"
```

Then:

```python
from kaizen.llm import LlmClient

client = LlmClient.from_env()
```

## Provider-specific migration

### AWS Bedrock (Claude)

```python
from kaizen.llm import LlmClient, LlmDeployment

deployment = LlmDeployment.bedrock_claude(
    api_key=os.environ["AWS_BEARER_TOKEN_BEDROCK"],
    region="us-east-1",
    model="claude-3-opus",  # short alias, resolves to anthropic.claude-3-opus-20240229-v1:0
)
client = LlmClient.from_deployment(deployment)
```

### GCP Vertex (Claude)

```python
deployment = LlmDeployment.vertex_claude(
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"],  # path to SA key JSON
    project="my-gcp-project-1234",
    region="us-central1",
    model="claude-3-opus",  # resolves to claude-3-opus@20240229
)
client = LlmClient.from_deployment(deployment)
```

### Azure OpenAI

```python
auth = LlmDeployment.azure_entra(api_key=os.environ["AZURE_OPENAI_API_KEY"])
deployment = LlmDeployment.azure_openai(
    "my-openai-resource",      # Azure resource name
    "gpt-4o-prod",              # Deployment name created in Azure portal
    auth,
    api_version="2024-06-01",   # defaults to AZURE_OPENAI_DEFAULT_API_VERSION
)
client = LlmClient.from_deployment(deployment)
```

## Breaking changes from #498

- **`model` is required on every preset** (no hardcoded defaults). Read from `.env` per `rules/env-models.md`. Prior `LlmDeployment.openai(api_key)` calls that relied on the `gpt-4` default now raise `TypeError`.
- None of the legacy `kaizen.providers.registry` surface is affected.

## Gradual migration path

1. Keep existing `get_provider(...)` call sites.
2. For new code, use `LlmClient.from_deployment(LlmDeployment.X(...))`.
3. For environment-driven config, switch to `LlmClient.from_env()`.
4. When the test suite is fully green against the new API, consider removing legacy `get_provider` imports per-file.

## Troubleshooting

- **`TypeError: ... missing 1 required positional argument: 'model'`** — pass `model=os.environ["..."]` explicitly. Per `rules/env-models.md`, model names come from environment.
- **`InvalidUri: bedrock:// URI region failed regex validation`** — AWS regions are `us-east-1`, `eu-central-1`, etc. (no trailing dash before digit sequence).
- **`NoKeysConfigured`** from `from_env()` — no deployment env or legacy key is set. Set one of the tier variables.
- **Log warning `legacy_and_deployment_both_configured`** — you have BOTH `KAILASH_LLM_DEPLOYMENT` (or `KAILASH_LLM_PROVIDER`) AND a legacy per-provider key set. The deployment path wins; clear the legacy key when you're ready.

## References

- Spec: `specs/kaizen-llm-deployments.md`
- Workspace: `workspaces/issue-498-llm-deployment/`
- Cross-SDK: `kailash-rs#406`
