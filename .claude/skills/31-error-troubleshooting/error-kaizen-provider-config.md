# Kaizen Provider Configuration Errors

Common errors from Kaizen provider configuration, especially Azure and structured output settings. All trace to the same root cause: mixing structured output config with provider-specific settings, or using deprecated implicit configuration.

## Error: Azure 400 "messages must contain 'json'"

**Symptom**: Azure returns HTTP 400 with message like `Invalid request: messages must contain the word 'json' in some form`.

**Cause**: Azure's `json_object` response format requires the word "JSON" to appear in the system prompt. When using `response_format: {"type": "json_object"}` without explicit JSON instructions in the prompt, Azure rejects the request.

**Fix** (choose one):

```python
# Option 1: Append json_prompt_suffix() to your system prompt
from kaizen.core.prompt_utils import json_prompt_suffix

class MyAgent(BaseAgent):
    def _generate_system_prompt(self) -> str:
        base = "You are a helpful assistant."
        return base + json_prompt_suffix(self.signature.output_fields)

# Option 2: Use json_schema mode instead of json_object (no prompt requirement)
config = BaseAgentConfig(
    llm_provider="azure",
    model=os.environ["LLM_MODEL"],
    response_format=create_structured_output_config(MySignature(), strict=True),
    structured_output_mode="explicit",
)
```

**Why:** OpenAI's `json_schema` strict mode enforces the schema via constrained sampling (no prompt requirement). Azure's `json_object` mode only tells the model to produce JSON but needs the prompt to specify what shape.

## Error: "Missing required parameter: response_format.type"

**Symptom**: API returns a validation error about `response_format.type` being missing or invalid.

**Cause**: Provider-specific settings (like `api_version`) were placed in `response_format` instead of `provider_config`. The API tries to interpret `api_version` as a response format type and fails.

**Fix**: Separate the two fields:

```python
# WRONG: api_version mixed into response_format
config = BaseAgentConfig(
    response_format={"type": "json_object", "api_version": "2024-10-21"},  # BUG
)

# RIGHT: Each field has one purpose
config = BaseAgentConfig(
    response_format={"type": "json_object"},                  # Structured output only
    provider_config={"api_version": "2024-10-21"},            # Provider settings only
    structured_output_mode="explicit",
)
```

**Why:** `response_format` is sent to the LLM API as the structured output instruction. `provider_config` holds operational settings like API version and deployment name. Mixing them sends garbage keys to the API.

## Error: DeprecationWarning about provider_config

**Symptom**: `DeprecationWarning: provider_config with 'type' key is deprecated for structured output. Use response_format instead.`

**Cause**: Code passes structured output config (containing a `"type"` key) via `provider_config` instead of `response_format`. The deprecation shim in `BaseAgentConfig.__post_init__` auto-migrates it but warns.

**Fix**: Move structured output config to `response_format`:

```python
# BEFORE (deprecated)
config = BaseAgentConfig(
    provider_config=create_structured_output_config(sig, strict=True)
)

# AFTER (correct)
config = BaseAgentConfig(
    response_format=create_structured_output_config(sig, strict=True),
    structured_output_mode="explicit",
)
```

**Migration timeline**:

- v2.5.x: `structured_output_mode="auto"` default + deprecation warnings
- v2.6.0: Default changes to `structured_output_mode="explicit"`
- v3.0.0: Deprecated `provider_config` structured output support removed

## Error: Azure Env Var Deprecation Warnings

**Symptom**: `DeprecationWarning: Environment variable AZURE_OPENAI_ENDPOINT is deprecated. Use AZURE_ENDPOINT instead.`

**Cause**: Using legacy Azure environment variable names. The `resolve_azure_env()` helper checks canonical names first, then falls back to legacy names with warnings.

**Fix**: Update environment variables to canonical names:

| Canonical           | Legacy (deprecated)                                    |
| ------------------- | ------------------------------------------------------ |
| `AZURE_ENDPOINT`    | `AZURE_OPENAI_ENDPOINT`, `AZURE_AI_INFERENCE_ENDPOINT` |
| `AZURE_API_KEY`     | `AZURE_OPENAI_API_KEY`, `AZURE_AI_INFERENCE_API_KEY`   |
| `AZURE_API_VERSION` | `AZURE_OPENAI_API_VERSION`                             |

```bash
# Update .env file
AZURE_ENDPOINT="https://your-endpoint.openai.azure.com"
AZURE_API_KEY="your-key"
AZURE_API_VERSION="2024-10-21"
```

## Error: Azure Backend Auto-Detection Failure

**Symptom**: First API call always fails, then succeeds on retry. Or: opaque error from wrong Azure backend.

**Cause**: Pre-v2.5.0 used error-based backend switching via `AzureBackendDetector.handle_error()`. When URL pattern detection guessed wrong, it made a failing call, parsed the error, and switched backends.

**Fix**: Set `AZURE_BACKEND` explicitly when auto-detection from URL patterns fails:

```bash
# Set explicitly in .env
AZURE_BACKEND=openai    # For Azure OpenAI Service
AZURE_BACKEND=foundry   # For Azure AI Foundry
```

**Why:** Error-based fallback makes every misdetected endpoint pay a round-trip penalty and produces confusing error logs. Explicit backend selection is deterministic and fast.

## Related

- `kaizen/core/config.py` — `BaseAgentConfig` with `response_format` and `structured_output_mode`
- `kaizen/core/prompt_utils.py` — `generate_prompt_from_signature()` and `json_prompt_suffix()`
- `kaizen/nodes/ai/azure_detection.py` — `resolve_azure_env()` canonical-first resolution
- `skills/04-kaizen/kaizen-config-patterns.md` — Full configuration patterns
- `skills/04-kaizen/kaizen-structured-outputs.md` — Structured output guide
