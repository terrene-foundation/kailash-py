# Kaizen Provider Configuration (v2.5.0 — Explicit over Implicit)

Canonical reference for `BaseAgentConfig` fields, structured output, and Azure environment variables. Load when configuring agents with `response_format`, `provider_config`, or Azure env vars.

As of v2.5.0, provider configuration follows an **explicit over implicit** model. Structured output config is separated from provider-specific settings.

## BaseAgentConfig Fields

| Field                    | Purpose                                                                | Example                                      |
| ------------------------ | ---------------------------------------------------------------------- | -------------------------------------------- |
| `response_format`        | Structured output config (json_schema, json_object)                    | `{"type": "json_schema", "json_schema": {}}` |
| `provider_config`        | Provider-specific operational settings only                            | `{"api_version": "2024-10-21"}`              |
| `structured_output_mode` | Controls auto-generation: `"auto"` (deprecated), `"explicit"`, `"off"` | `"explicit"`                                 |

## Quick Pattern

```python
from kaizen.core.config import BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config

# Explicit mode (recommended)
config = BaseAgentConfig(
    llm_provider="openai",
    model=os.environ["LLM_MODEL"],
    response_format=create_structured_output_config(MySignature(), strict=True),
    structured_output_mode="explicit",
)

# Azure with provider-specific settings (separate from response_format)
config = BaseAgentConfig(
    llm_provider="azure",
    model=os.environ["LLM_MODEL"],
    response_format={"type": "json_object"},
    provider_config={"api_version": "2024-10-21"},
    structured_output_mode="explicit",
)
```

## Azure Env Vars (Canonical Names)

| Canonical           | Legacy (deprecated)                                    |
| ------------------- | ------------------------------------------------------ |
| `AZURE_ENDPOINT`    | `AZURE_OPENAI_ENDPOINT`, `AZURE_AI_INFERENCE_ENDPOINT` |
| `AZURE_API_KEY`     | `AZURE_OPENAI_API_KEY`, `AZURE_AI_INFERENCE_API_KEY`   |
| `AZURE_API_VERSION` | `AZURE_OPENAI_API_VERSION`                             |

Legacy vars emit `DeprecationWarning`. Use `resolve_azure_env()` from `kaizen.nodes.ai.azure_detection` for canonical-first resolution.

## Anti-Patterns

- **Never** put structured output config in `provider_config` — use `response_format`
- **Never** rely on auto-generated structured output without understanding it — set `structured_output_mode="explicit"`
- **Never** use multiple env var names for the same Azure setting without deprecation
- **Never** use error-based backend switching — detect the backend upfront or set `AZURE_BACKEND` explicitly

## Prompt Utilities

`kaizen.core.prompt_utils` is the single source of truth for signature-based prompt generation:

- `generate_prompt_from_signature(signature)` — builds system prompt from signature fields
- `json_prompt_suffix(output_fields)` — returns JSON format instructions for Azure `json_object` compatibility

## See Also

- [kaizen-config-patterns](kaizen-config-patterns.md) — Domain configs, auto-extraction, provider-specific patterns
- [kaizen-structured-outputs](kaizen-structured-outputs.md) — Full structured output guide with migration examples
