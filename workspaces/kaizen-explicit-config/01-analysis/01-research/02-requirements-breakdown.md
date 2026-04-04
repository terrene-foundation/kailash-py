# Requirements Breakdown: Kaizen Explicit Provider Configuration

## Executive Summary

- **Feature**: Refactor Kaizen-py provider configuration from implicit magic to explicit configuration, aligned with kailash-rs
- **Complexity**: High -- touches config model, workflow generation, provider backends, and system prompt generation
- **Risk Level**: Medium -- backward-incompatible changes to public API surface (BaseAgentConfig.provider_config)
- **Estimated Effort**: 2 sessions (parallel agent execution: config model + backend refactor + tests)

## Source Issues

Issues #254-257 trace to a common root: implicit convenience behaviors in Kaizen-py's Azure integration that create coupling across abstraction boundaries. kailash-rs avoids all four bugs by using explicit configuration.

---

## MUST Requirements (Breaking Changes / Core Fixes)

### R1: Separate response_format from provider_config

**Priority**: MUST
**Breaking**: Yes (field semantics change)

**Current State**:
`BaseAgentConfig.provider_config` (line 50, config.py) is a single `Optional[Dict[str, Any]]` that serves dual purpose:

1. Structured output config (response_format): `{"type": "json_schema", "json_schema": {...}}`
2. Provider-specific settings: `{"api_version": "2024-10-21", "deployment": "my-gpt4"}`

In `llm_agent.py` (lines 756-766), the code guesses which purpose `provider_config` serves by checking `if "type" in provider_config` -- if it has a "type" key, treat it as response_format; otherwise ignore it. This heuristic breaks when provider-specific config legitimately contains a "type" key.

**Target State**:
Two separate fields on `BaseAgentConfig`:

```python
response_format: Optional[Dict[str, Any]] = None   # Structured output config
provider_config: Optional[Dict[str, Any]] = None    # Provider-specific settings only
```

**kailash-rs Reference**:
`LlmRequest` (types.rs, line 451) has no `provider_config` at all. It has explicit typed fields: `model`, `system_prompt`, `tools`, `temperature`, `max_tokens`, `api_key`, `base_url`. No dual-purpose bags of options.

**Implementation Components**:

1. Add `response_format: Optional[Dict[str, Any]] = None` to `BaseAgentConfig`
2. Change `provider_config` semantics to only hold provider-specific settings
3. Update `from_domain_config()` to extract both fields
4. Update `LLMAgentNode` to read `response_format` directly instead of guessing from `provider_config`
5. Update `WorkflowGenerator.generate_signature_workflow()` to set `response_format` instead of `provider_config` when auto-configuring structured output

**Edge Cases**:

- User passes `{"type": "json_schema", ...}` in `provider_config` (old behavior) -- emit deprecation warning, interpret as `response_format`
- User passes both `response_format` and `provider_config` with a `"type"` key -- `response_format` wins, no ambiguity
- User passes `provider_config={"api_version": "2024-10-21"}` -- no change, works as before

**Migration Path**:
Deprecation shim in `BaseAgentConfig.__post_init__`: if `provider_config` contains a `"type"` key and `response_format` is None, move it to `response_format` and emit `DeprecationWarning`.

**SDK Mapping**: `BaseAgentConfig` (config.py), `LLMAgentNode` (llm_agent.py), `WorkflowGenerator` (workflow_generator.py)

---

### R2: Unify system prompt generation

**Priority**: MUST
**Breaking**: No (internal refactor, public extension point preserved)

**Current State**:
Two independent `_generate_system_prompt()` implementations:

1. **BaseAgent.\_generate_system_prompt()** (base_agent.py, line 1580) -- generates from signature + tool registry
2. **WorkflowGenerator.\_generate_system_prompt()** (workflow_generator.py, line 411) -- generates from signature only

These diverge over time. BaseAgent's version includes MCP tool documentation; WorkflowGenerator's does not. The callback pattern (line 345-350) partially bridges this by passing BaseAgent's method as `prompt_generator`, but WorkflowGenerator still has its own fallback.

**Target State**:
Single authoritative implementation. WorkflowGenerator delegates to a shared utility or always uses the callback. The fallback path in WorkflowGenerator either calls the same shared function or is removed.

**Implementation Components**:

1. Extract shared prompt generation logic into a standalone function (e.g., `generate_prompt_from_signature(signature) -> str`)
2. Both `BaseAgent._generate_system_prompt()` and `WorkflowGenerator._generate_system_prompt()` call this shared function
3. BaseAgent augments the base prompt with tool registry docs (its unique addition)
4. WorkflowGenerator's fallback uses the shared function

**Edge Cases**:

- Subclasses that override `_generate_system_prompt()` continue to work (callback pattern unchanged)
- WorkflowGenerator used without an agent (no callback) still produces a reasonable prompt

**SDK Mapping**: `BaseAgent` (base_agent.py), `WorkflowGenerator` (workflow_generator.py), new shared module

---

### R3: Make structured output explicit

**Priority**: MUST
**Breaking**: Yes (behavior change for users relying on auto-generation)

**Current State**:
`WorkflowGenerator.generate_signature_workflow()` (workflow_generator.py, lines 190-208) silently creates structured output config when:

- No `provider_config` is set
- Provider supports structured output (openai, google, gemini, azure)
- A signature exists

It then patches the system prompt (lines 241-253) to append "Respond with a JSON object containing the output fields" for Azure when using json_object or json_schema response_format.

The user never sees this happen. If the auto-generated config is wrong, the error is opaque.

**Target State**:
Structured output configuration is always explicit. Users set `response_format` on their config when they want structured output. The SDK provides a helper to generate the config from a signature, but does not apply it automatically.

**kailash-rs Reference**:
kailash-rs's `OpenAiAdapter.build_chat_request()` (openai.rs) constructs the request body directly from `LlmRequest` fields. No auto-detection of whether structured output should be enabled. If the user wants it, they configure it.

**Implementation Components**:

1. Remove auto-generation of `provider_config` in `WorkflowGenerator.generate_signature_workflow()`
2. Expose `create_structured_output_config()` as a public API users can call explicitly
3. Remove system prompt patching for JSON format (lines 241-253) -- if the user configures response_format, they are responsible for their prompt
4. Add clear documentation showing how to configure structured output

**Migration Path**:
Add a `structured_output_mode` field to `BaseAgentConfig` with values:

- `"auto"` (current behavior, default during deprecation period)
- `"explicit"` (new behavior, no auto-generation)
- `"off"` (never use structured output)

Default to `"auto"` in the first release with a deprecation warning. Switch default to `"explicit"` in the next minor version.

**Edge Cases**:

- Existing code relying on auto-generation gets deprecation warnings but continues working
- Users of non-OpenAI providers who accidentally set response_format get a clear error
- Signature-based agents without response_format still produce valid output (just not schema-enforced)

**SDK Mapping**: `WorkflowGenerator` (workflow_generator.py), `BaseAgentConfig` (config.py), `StructuredOutputGenerator` (structured_output.py)

---

## SHOULD Requirements (Improvements with Backward Compat)

### R4: Simplify Azure env vars

**Priority**: SHOULD
**Breaking**: No (deprecated vars still work)

**Current State**:
Multiple env var names for the same setting, checked in priority order:

- Endpoint: `AZURE_ENDPOINT` > `AZURE_OPENAI_ENDPOINT` > `AZURE_AI_INFERENCE_ENDPOINT`
- API key: `AZURE_API_KEY` > `AZURE_OPENAI_API_KEY` > `AZURE_AI_INFERENCE_API_KEY`
- API version: `AZURE_OPENAI_API_VERSION` > `AZURE_API_VERSION` > hardcoded `"2024-10-21"`

This creates confusion: which env var should the user set? If both are set, which wins? The priority order is undocumented in the user-facing API.

**Target State**:
Canonical env var names with documented deprecation of alternatives:

- `AZURE_ENDPOINT` (canonical)
- `AZURE_API_KEY` (canonical)
- `AZURE_API_VERSION` (canonical, replaces both `AZURE_OPENAI_API_VERSION` and `AZURE_API_VERSION`)

Legacy names emit `DeprecationWarning` on first use.

**kailash-rs Reference**:
kailash-rs has no Azure-specific env var logic at all. Users pass `base_url` explicitly on `LlmRequest`. The SDK resolves env vars only for API keys (`OPENAI_API_KEY`, etc.) with one name per provider.

**Implementation Components**:

1. Define canonical env var names in a constants module
2. Add deprecation warnings when legacy names are used
3. Document the canonical names prominently

**Edge Cases**:

- Both `AZURE_ENDPOINT` and `AZURE_OPENAI_ENDPOINT` set to different values -- canonical wins, warn about conflict
- Only legacy var set -- works with deprecation warning

**SDK Mapping**: `AzureBackendDetector` (azure_detection.py), `AzureOpenAIBackend` (azure_backends.py)

---

### R5: Simplify Azure backend detection

**Priority**: SHOULD
**Breaking**: Potentially (users relying on auto-detection)

**Current State**:
`AzureBackendDetector` (azure_detection.py) uses a multi-layer detection strategy:

1. Explicit `AZURE_BACKEND` env var
2. Regex pattern matching on endpoint URL (7 patterns across 2 backends)
3. Default to Azure OpenAI
4. Error-based correction (detect wrong backend from API error messages, auto-switch)

This is the most complex implicit behavior. The regex patterns break on new Azure regions/URL schemes. The error-based fallback creates a situation where the first API call always fails for incorrectly-detected endpoints.

**Target State**:
Two options (see ADR for decision):

**Option A (Recommended)**: Keep auto-detection but make it advisory. The detector runs, logs what it detected, but the user must confirm or override via `AZURE_BACKEND`. Remove error-based fallback entirely.

**Option B**: Remove auto-detection entirely. User must set `AZURE_BACKEND=openai` or `AZURE_BACKEND=foundry`. Clean error message if not set.

**kailash-rs Reference**:
kailash-rs has no Azure backend detection at all. The user provides `base_url` on `LlmRequest`, and the SDK sends requests to that URL using the OpenAI-compatible API format. No URL parsing, no pattern matching, no fallback.

**Implementation Components**:

1. Remove `handle_error()` method (error-based fallback)
2. Make `AZURE_BACKEND` required when using Azure (Option B) or emit a warning suggesting it be set (Option A)
3. Simplify or remove regex pattern matching
4. Clean error messages when detection fails

**Edge Cases**:

- Custom proxy URLs that don't match any pattern -- currently defaults to Azure OpenAI silently
- Corporate environments with non-standard Azure endpoint URLs
- Users who set `base_url` on `BaseAgentConfig` directly (should bypass detection entirely)

**SDK Mapping**: `AzureBackendDetector` (azure_detection.py), `UnifiedAzureProvider` (unified_azure_provider.py)

---

### R6: EATP D6 alignment (semantic matching with kailash-rs)

**Priority**: SHOULD
**Breaking**: No (additive alignment)

**Current State**:
kailash-py and kailash-rs have semantically different config models:

| Concept         | kailash-rs (LlmRequest)         | kailash-py (BaseAgentConfig)             |
| --------------- | ------------------------------- | ---------------------------------------- |
| Model           | `model: String`                 | `model: Optional[str]`                   |
| Base URL        | `base_url: Option<String>`      | `base_url: Optional[str]` (matches)      |
| API key         | `api_key: Option<String>`       | `api_key: Optional[str]` (matches)       |
| Temperature     | `temperature: Option<f64>`      | `temperature: Optional[float]` (matches) |
| Max tokens      | `max_tokens: Option<u32>`       | `max_tokens: Optional[int]` (matches)    |
| System prompt   | `system_prompt: Option<String>` | Generated, not on config                 |
| Provider config | N/A                             | `provider_config: Optional[Dict]`        |
| Response format | N/A                             | Buried in `provider_config`              |

**Target State**:
After R1 (separate response_format), the Python config aligns closer. Remaining gap is that kailash-rs has no `provider_config` bag at all -- every setting is an explicit field. Full alignment would mean:

- `api_version: Optional[str]` as an explicit field (not buried in dict)
- `deployment: Optional[str]` as an explicit field (not buried in dict)

**Implementation Components**:

1. After R1, evaluate whether `provider_config` still needs to exist or if common settings should be promoted to fields
2. Document the semantic mapping between Python and Rust configs
3. Ensure the two SDKs produce identical API requests given equivalent configuration

**SDK Mapping**: `BaseAgentConfig` (config.py), cross-reference with kailash-rs `AgentConfig` + `LlmRequest` (types.rs)

---

## COULD Requirements (Nice-to-Haves)

### R7: Typed provider config dataclasses

**Priority**: COULD

Replace `provider_config: Optional[Dict[str, Any]]` with typed dataclasses per provider:

```python
@dataclass
class AzureProviderConfig:
    api_version: str = "2024-10-21"
    deployment: Optional[str] = None

@dataclass
class GoogleProviderConfig:
    safety_settings: Optional[Dict] = None
```

This eliminates the Dict bag entirely, providing IDE autocompletion and validation. Deferred because it is a larger API surface change that should be designed carefully.

### R8: Remove hardcoded model default

**Priority**: COULD

`WorkflowGenerator` (line 225) defaults to `model or "gpt-4"`. This violates `rules/env-models.md` which requires all model names come from `.env`. Should default to `os.environ.get("DEFAULT_LLM_MODEL")` or raise an error.

### R9: Consolidate provider client initialization

**Priority**: COULD

Both `AzureOpenAIBackend.__init__()` and `AzureBackendDetector._get_config()` independently read env vars to build client config. Should have a single source of truth for Azure client configuration.

---

## Cross-SDK Inspection (EATP D6)

Per `rules/cross-sdk-inspection.md`, the following must be verified:

- [ ] kailash-rs does NOT have the dual-purpose provider_config bug (confirmed: it has no provider_config at all)
- [ ] kailash-rs does NOT have auto-detection of Azure backends (confirmed: uses explicit base_url)
- [ ] kailash-rs does NOT have auto-generation of structured output config (confirmed: no auto-generation)
- [ ] kailash-rs does NOT have duplicate system prompt generation (confirmed: single path through system_prompt field)

**Conclusion**: kailash-rs is already at the target state. This refactor brings kailash-py into alignment. No cross-SDK issues to file.

---

## Risk Assessment

### High Probability, High Impact (Critical)

1. **Backward compatibility breakage on provider_config**
   - Users who pass `{"type": "json_schema", ...}` in `provider_config` will break when it stops being auto-interpreted as response_format
   - Mitigation: Deprecation shim in `__post_init__` that auto-migrates with warning
   - Prevention: Release as minor version bump with deprecation period

2. **Structured output regression**
   - Removing auto-generation means existing agents that relied on it will produce unstructured output
   - Mitigation: `structured_output_mode="auto"` as transitional default
   - Prevention: Comprehensive test coverage of all signature-based agents

### Medium Risk (Monitor)

1. **Azure env var confusion during transition**
   - Users with both old and new env vars set may get unexpected behavior
   - Mitigation: Log which env var was resolved and warn on conflicts
   - Prevention: Clear deprecation messages with migration instructions

2. **System prompt quality regression**
   - Unifying prompt generation may change prompt content for some agents
   - Mitigation: Snapshot tests on prompt output for known signatures
   - Prevention: Extract-and-compare before replacing

### Low Risk (Accept)

1. **Azure backend detection removal causing failures**
   - Very few users depend on auto-detection without `AZURE_BACKEND` set
   - Mitigation: Clear error message guiding user to set `AZURE_BACKEND`

---

## Implementation Roadmap

### Phase 1: Config Model (1 session)

- Add `response_format` field to `BaseAgentConfig`
- Add deprecation shim for `provider_config` -> `response_format` migration
- Add `structured_output_mode` field
- Update `from_domain_config()` and `from_dict()` methods
- Tests for new fields, deprecation warnings, edge cases

### Phase 2: Workflow + Prompt Refactor (1 session, parallelizable)

- Extract shared prompt generation function
- Unify `BaseAgent._generate_system_prompt()` and `WorkflowGenerator._generate_system_prompt()`
- Update `WorkflowGenerator.generate_signature_workflow()` to respect `structured_output_mode`
- Remove system prompt patching for JSON format
- Update `LLMAgentNode` to read `response_format` directly
- Tests for prompt generation, workflow generation, structured output paths

### Phase 3: Azure Simplification (1 session, parallelizable with Phase 2)

- Define canonical Azure env vars
- Add deprecation warnings for legacy names
- Simplify or remove error-based backend fallback
- Update documentation
- Tests for env var resolution, deprecation warnings

### Success Criteria

- [ ] R1: `response_format` and `provider_config` are separate fields with clear semantics
- [ ] R2: Single authoritative prompt generation path
- [ ] R3: Structured output is explicit, not auto-generated (or opt-in with deprecation warning)
- [ ] R4: Canonical env var names with deprecation on alternatives
- [ ] R5: Azure backend detection simplified, error-based fallback removed
- [ ] R6: Config model semantically matches kailash-rs approach
- [ ] All existing tests pass
- [ ] No new `DeprecationWarning` without documented migration path
