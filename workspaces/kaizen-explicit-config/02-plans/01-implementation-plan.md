# Implementation Plan: Kaizen Explicit Provider Configuration

## Objective

Move Kaizen-py's provider configuration from implicit magic to explicit configuration, eliminating the class of bugs demonstrated by #254-257. Aligned with kailash-rs's explicit model (EATP D6).

## Architecture Decision

**ADR-001**: Separate, don't remove. See `01-analysis/01-research/03-adr-explicit-config.md`.

- Split `provider_config` into `response_format` (structured output) and `provider_config` (provider settings)
- Make structured output opt-in with transitional `structured_output_mode` field
- Unify system prompt generation into single source
- Simplify Azure env vars with deprecation warnings
- Remove error-based Azure backend fallback

## Phases

### Phase 1: Config Model Refactor (MUST — do first)

**Goal**: Eliminate dual-purpose `provider_config` and make structured output explicit.

**Changes**:

1. **BaseAgentConfig** (`config.py`):
   - Add `response_format: Optional[Dict[str, Any]] = None`
   - Add `structured_output_mode: str = "auto"` (values: "auto", "explicit", "off")
   - Keep `provider_config` for provider-specific settings only
   - Add `__post_init__` deprecation shim: if `provider_config` has "type" key and `response_format` is None, migrate it

2. **WorkflowGenerator** (`workflow_generator.py`):
   - Read `response_format` from config instead of `provider_config` for structured output
   - When `structured_output_mode == "auto"`: current behavior (auto-generate) + deprecation warning
   - When `structured_output_mode == "explicit"`: only use user-provided `response_format`
   - When `structured_output_mode == "off"`: never set response_format
   - Remove the JSON prompt patching (line 241-253) — replace with helper function users call explicitly

3. **LLMAgentNode** (`llm_agent.py`):
   - Read `response_format` directly from config (no more "type" key guessing from provider_config)
   - `provider_config` passthrough for provider-specific settings (api_version, deployment)

4. **SingleShotStrategy** + **AsyncSingleShotStrategy**:
   - Read `response_format` instead of `provider_config` for JSON instruction injection

5. **SchemaFactory** (`schema_factory.py`):
   - Update to read `response_format` instead of `provider_config.response_format`

**Tests**: Update all 12+ test files referencing `provider_config` for structured output. Regression tests from #254-255 updated.

**Blast radius**: High (14+ source files, 40+ tests). Must be atomic.

---

### Phase 2: Azure Simplification (SHOULD — can parallel with Phase 3)

**Goal**: Standardize Azure env vars, remove error-based fallback.

**Changes**:

1. **AzureBackendDetector** (`azure_detection.py`):
   - Canonical env vars: `AZURE_ENDPOINT`, `AZURE_API_KEY`, `AZURE_API_VERSION`
   - Legacy vars (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`, `AZURE_AI_INFERENCE_*`): read with `DeprecationWarning`
   - Remove `handle_error()` — when pattern detection fails, raise clear error instead of silent retry

2. **AzureOpenAIBackend** (`azure_backends.py`):
   - Read from canonical env vars only (with deprecation for legacy)
   - Single `_api_version` resolution path

3. **Documentation**: Update all Azure setup docs with canonical var names.

---

### Phase 3: System Prompt Unification (SHOULD — can parallel with Phase 2)

**Goal**: Single authoritative prompt generation path.

**Changes**:

1. Extract `generate_prompt_from_signature(signature) -> str` into `kaizen/core/prompt_utils.py`
2. `BaseAgent._generate_system_prompt()`: calls shared function + augments with MCP tool docs
3. `WorkflowGenerator._generate_system_prompt()`: calls shared function only (no independent copy)
4. Remove JSON prompt suffix from WorkflowGenerator — provide `json_prompt_suffix()` as explicit utility

---

### Phase 4: Structured Output Helper (COULD — nice-to-have)

**Goal**: Make structured output easy even in explicit mode.

**Changes**:

1. Add `StructuredOutput` helper class:

   ```python
   from kaizen.core.structured_output import StructuredOutput

   config = BaseAgentConfig(
       response_format=StructuredOutput.from_signature(MySig).for_provider("azure"),
       structured_output_mode="explicit",
   )
   ```

2. `from_signature()` generates JSON schema from signature fields
3. `for_provider()` translates to provider-specific format (json_schema for OpenAI, json_object for Azure)
4. `prompt_hint()` returns "Respond with a JSON object..." for Azure compatibility

---

## Effort Estimate

| Phase     | Sessions                       | Parallelizable?    |
| --------- | ------------------------------ | ------------------ |
| Phase 1   | 1                              | No (must go first) |
| Phase 2   | 0.5                            | Yes (with Phase 3) |
| Phase 3   | 0.5                            | Yes (with Phase 2) |
| Phase 4   | 0.5                            | After Phase 1      |
| **Total** | **2 sessions** (critical path) |                    |

## Migration Path

1. **v2.5.x** (next patch): Phase 1 with `structured_output_mode="auto"` default + deprecation warnings
2. **v2.6.0** (next minor): Default changes to `structured_output_mode="explicit"`, Phases 2-4 complete
3. **v3.0.0** (major): Remove deprecated `provider_config` structured output support, remove legacy Azure env vars

## Files Affected

**Phase 1 (14 source + 40+ test files)**:

- `packages/kailash-kaizen/src/kaizen/core/config.py`
- `packages/kailash-kaizen/src/kaizen/core/workflow_generator.py`
- `packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py`
- `packages/kailash-kaizen/src/kaizen/core/schema_factory.py`
- `packages/kailash-kaizen/src/kaizen/strategies/single_shot.py`
- `packages/kailash-kaizen/src/kaizen/core/structured_output.py`
- `packages/kailash-kaizen/src/kaizen/core/base_agent.py`

**Phase 2 (3 source files)**:

- `packages/kailash-kaizen/src/kaizen/nodes/ai/azure_detection.py`
- `packages/kailash-kaizen/src/kaizen/nodes/ai/azure_backends.py`
- `packages/kailash-kaizen/src/kaizen/nodes/ai/unified_azure_provider.py`

**Phase 3 (3 source files)**:

- `packages/kailash-kaizen/src/kaizen/core/base_agent.py`
- `packages/kailash-kaizen/src/kaizen/core/workflow_generator.py`
- New: `packages/kailash-kaizen/src/kaizen/core/prompt_utils.py`
