# Azure Provider Guide

**Last Updated**: 2026-07-21

## Overview

Kaizen serves Azure through the **four-axis `LlmClient`** — there is no
separate "unified Azure provider" class. Two distinct four-axis wires cover
the two Azure LLM surfaces:

| Azure surface                            | Four-axis preset           | Endpoint shape                                        |
| ---------------------------------------- | -------------------------- | ----------------------------------------------------- |
| Azure OpenAI Service                     | `azure_openai`             | `{endpoint}/openai/deployments/{deployment}/...`      |
| Azure AI Foundry (unified model catalog) | `azure_ai_foundry` (#1892) | `{endpoint}/models/chat/completions` (model-agnostic) |

Both wires speak the same on-the-wire OpenAI-compatible chat-completions JSON
and authenticate with a static `api-key: <KEY>` header — they differ only in
URL shape and how the model identifier is carried (Azure OpenAI: a
caller-chosen _deployment name_ in the URL path; Azure AI Foundry: the actual
deployed _model name_ in the JSON body, since one endpoint serves every model
in the project).

## Azure OpenAI Service

### Quick Start

```bash
export AZURE_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_API_KEY="your-api-key"
export AZURE_API_VERSION="2024-06-01"   # optional; this is the pinned default
```

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

config = BaseAgentConfig(
    llm_provider="azure",        # or "azure_openai" -- same four-axis mapping
    model="my-gpt4o-deployment", # the Azure DEPLOYMENT NAME
    temperature=0.7,
)
agent = BaseAgent(config=config)
result = agent.run(prompt="What is the capital of France?")
```

Constructing the deployment directly:

```python
from kaizen.llm import LlmClient, LlmDeployment

auth = LlmDeployment.azure_entra(api_key="your-api-key")
deployment = LlmDeployment.azure_openai(
    "my-resource",             # Azure resource name
    "my-gpt4o-deployment",     # Azure deployment name
    auth,
    api_version="2024-06-01",  # optional
)
client = LlmClient.from_deployment(deployment)
response = await client.complete([{"role": "user", "content": "Say 'hello'"}])
```

### Environment Variables

| Variable                                                                      | Required    | Description                                                    |
| ----------------------------------------------------------------------------- | ----------- | -------------------------------------------------------------- |
| `AZURE_ENDPOINT`                                                              | Yes         | `https://{resource}.openai.azure.com`                          |
| `AZURE_API_KEY`                                                               | Yes         | Azure OpenAI API key                                           |
| `AZURE_API_VERSION`                                                           | No          | Defaults to `2024-06-01`                                       |
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_API_VERSION` | No (legacy) | Deprecated aliases; still resolve, emit a `DeprecationWarning` |

Auth also supports Entra ID workload-identity and managed-identity variants
via `LlmDeployment.azure_entra(workload_identity=True)` /
`LlmDeployment.azure_entra(managed_identity_client_id="...")`.

## Azure AI Foundry (unified model-inference wire, #1892)

Azure AI Foundry serves models from multiple families (OpenAI, Meta Llama,
Mistral, Cohere, and more) through **one unified, model-agnostic
model-inference endpoint** — `POST {endpoint}/models/chat/completions`. The
model identifier travels in the request body's `model` field, not the URL, so
the same endpoint serves every model deployed to the Foundry project.

### Quick Start

```bash
export AZURE_AI_FOUNDRY_ENDPOINT="https://your-foundry-resource.services.ai.azure.com"
export AZURE_AI_FOUNDRY_API_KEY="your-api-key"
export AZURE_AI_FOUNDRY_DEPLOYMENT="gpt-5-nano"   # the deployed model name
export AZURE_AI_FOUNDRY_API_VERSION="2024-05-01-preview"  # optional
```

```python
from kaizen.llm import LlmClient, LlmDeployment

deployment = LlmDeployment.azure_ai_foundry(
    "https://your-foundry-resource.services.ai.azure.com",
    "your-api-key",
    "gpt-5-nano",   # the deployed model name/id
    api_version="2024-05-01-preview",  # optional
)
client = LlmClient.from_deployment(deployment)
response = await client.complete(
    [{"role": "user", "content": "Say 'hello'"}],
    max_tokens=64,
)
print(response["text"])
```

Or through `LLMAgentNode` / `BaseAgent` with `llm_provider="azure_ai_foundry"`
— the endpoint / key / deployment resolve from the `AZURE_AI_FOUNDRY_*` env
vars above, mirroring the `azure` provider's resolution contract (a
per-request `api_key=` / `base_url=` override wins over the env vars; a
missing endpoint or key is a quiet skip, matching every other four-axis
preset's missing-credential behavior).

### Environment Variables

| Variable                       | Required | Description                                                            |
| ------------------------------ | -------- | ---------------------------------------------------------------------- |
| `AZURE_AI_FOUNDRY_ENDPOINT`    | Yes      | The Foundry project's unified inference endpoint                       |
| `AZURE_AI_FOUNDRY_API_KEY`     | Yes      | The Foundry project's inference API key                                |
| `AZURE_AI_FOUNDRY_DEPLOYMENT`  | Yes      | The deployed model name/id (never hardcode -- read from this env var)  |
| `AZURE_AI_FOUNDRY_API_VERSION` | No       | Defaults to the pinned `AZURE_AI_FOUNDRY_DEFAULT_API_VERSION` constant |

### Reasoning Models

Deployed reasoning models (the `gpt-5*` / `o1*` / `o3*` / `o4*` families) are
detected by model-name prefix and automatically get:

- `max_tokens` emitted as `max_completion_tokens` (these models reject the
  legacy `max_tokens` field with a 400).
- `temperature` / `top_p` / `frequency_penalty` / `presence_penalty` filtered
  per the model's documented sampling-parameter restrictions.

Reasoning tokens are drawn from the SAME `max_completion_tokens` budget as
visible output — a small budget (e.g. 16) can be fully consumed by internal
reasoning with **zero** visible text left (`finish_reason="length"`, empty
`text`). Give reasoning models enough budget (e.g. 150+) for both reasoning
and a visible answer.

## Migrating From The Legacy `azure_ai_foundry` Provider

Prior to #1892, `azure_ai_foundry` was served by a legacy provider class
(`AzureAIFoundryProvider`, built on the `azure-ai-inference` SDK) reached
through `kaizen.providers.registry.get_provider("azure_ai_foundry")`. That
class and its registry entry are REMOVED — `azure_ai_foundry` is now served
end-to-end by the four-axis `LlmClient` described above. No code changes are
required for `LLMAgentNode` / `BaseAgent` callers that already set
`llm_provider="azure_ai_foundry"`; only the environment variable names
changed (`AZURE_AI_INFERENCE_ENDPOINT` / `AZURE_AI_INFERENCE_API_KEY` →
`AZURE_AI_FOUNDRY_ENDPOINT` / `AZURE_AI_FOUNDRY_API_KEY` /
`AZURE_AI_FOUNDRY_DEPLOYMENT`).

## See Also

- [Ollama Quickstart](./ollama-quickstart.md) — Local LLM alternative
- [Multi-Agent Coordination](./multi-agent-coordination.md) — Using Azure with agents
