# ADR-001: Explicit vs Implicit Provider Configuration

## Status

Proposed

## Context

Kaizen-py's provider configuration has accumulated implicit convenience behaviors that create coupling across abstraction boundaries. Issues #254-257 all trace to the same root pattern: auto-magic that silently fails.

The specific implicit behaviors causing bugs are:

1. **Dual-purpose `provider_config` field** -- A single `Dict[str, Any]` serves as both structured output configuration (response_format) and provider-specific settings (api_version, deployment). The code in `LLMAgentNode` guesses which purpose is intended by checking `if "type" in provider_config`. This heuristic is fragile and ambiguous.

2. **Auto-generation of structured output config** -- `WorkflowGenerator` silently creates `{"type": "json_schema", ...}` or `{"type": "json_object"}` when it detects a signature and a compatible provider. The user never sees this configuration. When it produces the wrong config, the error is opaque because the user did not write the config that caused it.

3. **System prompt auto-patching** -- After auto-generating structured output config, `WorkflowGenerator` appends "Respond with a JSON object containing the output fields" to the system prompt. This patches a prompt the user may have carefully crafted, and it patches it after the user's `_generate_system_prompt()` override has already run.

4. **Azure backend auto-detection with error-based fallback** -- `AzureBackendDetector` uses regex patterns to guess the backend from the endpoint URL, defaults to Azure OpenAI when no pattern matches, and then uses API error message analysis to switch backends after a failed call. The first call always fails for misdetected endpoints.

5. **Multiple env var names per setting** -- Three different env var names for the endpoint, three for the API key, two for the API version. Undocumented priority order. Conflicting values produce silent surprises.

6. **Duplicate system prompt generation** -- Both `BaseAgent` and `WorkflowGenerator` have independent `_generate_system_prompt()` implementations that have diverged over time. BaseAgent's version includes MCP tool documentation; WorkflowGenerator's does not.

kailash-rs avoids all six problems by being explicit: the user provides `base_url`, `api_key`, `model`, `temperature`, `max_tokens`, and `system_prompt` as separate typed fields on `LlmRequest`. There is no `provider_config` bag, no auto-detection, no auto-generation, no prompt patching. The Rust SDK has zero bugs in this category.

### Constraints

- **EATP D6**: Python and Rust SDKs implement independently but semantics MUST match.
- **Backward compatibility**: Existing user code must have a migration path, not a hard break.
- **BUILD repo**: We fix the SDK directly. No workarounds.

## Decision

Move Kaizen-py's provider configuration model from implicit magic to explicit configuration, aligned with kailash-rs's approach.

### 1. Separate response_format from provider_config

Add a new `response_format: Optional[Dict[str, Any]]` field to `BaseAgentConfig`, separate from `provider_config`. Each field has one clear purpose:

- `response_format`: Structured output config sent to the LLM API (`{"type": "json_schema", ...}` or `{"type": "json_object"}`)
- `provider_config`: Provider-specific operational settings (`{"api_version": "2024-10-21", "deployment": "my-gpt4"}`)

A deprecation shim in `BaseAgentConfig.__post_init__` detects when `provider_config` contains a `"type"` key (indicating it was being used as response_format under the old convention), moves it to `response_format`, and emits a `DeprecationWarning`.

### 2. Make structured output opt-in with transitional default

Add a `structured_output_mode` field to `BaseAgentConfig` with three values:

- `"auto"`: Current behavior -- auto-generate structured output config from signature (transitional default, emits deprecation warning)
- `"explicit"`: New behavior -- user must set `response_format` themselves if they want structured output
- `"off"`: Never use structured output

The default starts as `"auto"` to avoid breaking existing code. The deprecation warning tells users to set `response_format` explicitly. In the next minor version, the default changes to `"explicit"`.

### 3. Remove system prompt patching

Stop appending JSON format instructions to user-provided system prompts. If the user configures `response_format`, they are responsible for ensuring their prompt is compatible. The SDK provides documentation and a helper function (`generate_json_prompt_suffix()`) that users can call themselves.

### 4. Unify system prompt generation

Extract the shared prompt-from-signature logic into a standalone function that both `BaseAgent` and `WorkflowGenerator` call. BaseAgent's version augments the result with tool registry documentation (its unique contribution). WorkflowGenerator's independent copy is removed.

### 5. Simplify Azure env vars

Define canonical names (`AZURE_ENDPOINT`, `AZURE_API_KEY`, `AZURE_API_VERSION`) and emit deprecation warnings for alternatives. Document one name per setting.

### 6. Remove error-based Azure backend fallback

Remove the `handle_error()` method from `AzureBackendDetector`. When auto-detection from URL patterns fails, emit a clear error message telling the user to set `AZURE_BACKEND=openai` or `AZURE_BACKEND=foundry`. No silent retry with a different backend.

## Consequences

### Positive

- **Zero ambiguity**: Every field has one purpose. `response_format` is structured output. `provider_config` is provider settings. No guessing.
- **User visibility**: No configuration is generated behind the user's back. If structured output is configured, the user wrote that configuration.
- **Debuggability**: When an API call fails, the user can inspect the exact configuration they provided. No hidden auto-generated config to discover.
- **Cross-SDK alignment**: Python config model semantically matches Rust's approach (explicit typed fields, no magic bags).
- **Prompt integrity**: System prompts are never silently modified after the user provides them.
- **Single source of truth**: One prompt generation path, one env var per setting, one purpose per field.

### Negative

- **More configuration required**: Users who relied on auto-generation must now write 2-3 additional lines of config for structured output. The helper function reduces this to one line.
- **Deprecation warnings during transition**: Existing code using `provider_config` for structured output will see warnings until migrated.
- **Breaking change for Azure auto-detection users**: Users who relied on error-based backend switching (a small population) must now set `AZURE_BACKEND` explicitly.
- **Documentation burden**: Must clearly document the new fields, the migration path, and the helper functions.

### Neutral

- **Code complexity**: Net reduction. Removing auto-generation, prompt patching, error-based fallback, and duplicate prompt generation removes more code than the new fields and deprecation shims add.

## Alternatives Considered

### Alternative 1: Keep auto-generation but fix the heuristic

Fix the `if "type" in provider_config` heuristic in `LLMAgentNode` to be more robust (e.g., check for specific known response_format shapes). Keep auto-generation in `WorkflowGenerator` but improve it.

**Pros**: Minimal user-facing change. No deprecation period needed.

**Cons**: Does not fix the root cause. The dual-purpose field remains ambiguous. Auto-generation still creates invisible configuration. The next bug in this category is inevitable because the architecture invites it. Does not align with kailash-rs.

**Why rejected**: This is a patch, not a fix. Issues #254-257 are symptoms of architectural coupling, not individual bugs. Fixing symptoms leaves the architecture that produces them intact.

### Alternative 2: Full kailash-rs alignment (no provider_config at all)

Remove `provider_config` entirely. Promote every provider-specific setting to a typed field on `BaseAgentConfig`: `api_version`, `deployment`, `safety_settings`, etc.

**Pros**: Maximum explicitness. Perfect alignment with kailash-rs. IDE autocompletion for every setting. Compile-time-equivalent validation.

**Cons**: Large API surface change. Every new provider setting requires a new field on the base config class. Providers with many settings (Google, Azure) would bloat the base config. Python's dataclass approach makes this more cumbersome than Rust's struct approach.

**Why rejected**: Over-correction. The `provider_config` dict is a reasonable escape hatch for provider-specific settings that do not warrant top-level fields. The key insight is that `response_format` is NOT provider-specific -- it is a cross-provider concept that deserves its own field. Once response_format is separated, provider_config becomes unambiguous.

### Alternative 3: Configuration validation layer

Keep the current structure but add a validation layer that inspects `provider_config` at config time (not at API call time) and raises clear errors for ambiguous configurations.

**Pros**: No API change. Existing code works. Better error messages.

**Cons**: Validation cannot distinguish between a user who intentionally put response_format in provider_config and one who put provider settings there. The ambiguity is structural, not a validation problem. Does not address auto-generation or prompt patching.

**Why rejected**: You cannot validate away ambiguity. If a field has two purposes, no validation can determine which purpose the user intended without asking them -- which is what separate fields do.

### Alternative 4: Provider-specific config subclasses

Create typed subclasses like `AzureConfig(provider_config)`, `OpenAIConfig(provider_config)` that know their own fields and validation rules.

**Pros**: Type safety within provider boundaries. Self-documenting. Can validate at construction time.

**Cons**: Does not fix the response_format ambiguity (that is a cross-provider concern). Adds significant API surface. Users must know which config class to use before they can configure their agent.

**Why deferred to COULD**: Good idea for a future iteration (see R7 in requirements), but the immediate priority is separating response_format from provider_config. Typed subclasses can be layered on top of that separation later.

## Implementation Plan

### Phase 1: Config Model Foundation (1 session)

1. Add `response_format` field to `BaseAgentConfig`
2. Add `structured_output_mode` field to `BaseAgentConfig`
3. Implement deprecation shim in `__post_init__`
4. Update `from_domain_config()`, `from_dict()`, serialization
5. Write tests for new fields, deprecation path, edge cases

### Phase 2: Workflow and Prompt Refactor (1 session, parallel with Phase 3)

1. Extract shared `generate_prompt_from_signature()` function
2. Refactor `BaseAgent._generate_system_prompt()` to use shared function
3. Replace `WorkflowGenerator._generate_system_prompt()` with shared function
4. Update `WorkflowGenerator.generate_signature_workflow()` to respect `structured_output_mode`
5. Remove system prompt patching
6. Update `LLMAgentNode` to read `response_format` directly
7. Write tests for prompt generation, workflow generation

### Phase 3: Azure Simplification (1 session, parallel with Phase 2)

1. Define canonical env var constants
2. Add deprecation warnings for legacy env var names
3. Remove `AzureBackendDetector.handle_error()` method
4. Require `AZURE_BACKEND` when auto-detection fails (clear error message)
5. Write tests for env var resolution, deprecation, detection
