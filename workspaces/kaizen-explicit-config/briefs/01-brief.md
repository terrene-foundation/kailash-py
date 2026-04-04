# Brief: Kaizen Explicit Configuration Refactor

## Context

Issues #254-257 revealed that Kaizen-py's Azure integration has accumulated implicit convenience behaviors that create coupling across abstraction boundaries. All 4 bugs trace to the same root pattern: auto-magic that silently fails.

kailash-rs avoids all 4 bugs by using explicit configuration — user provides base_url, separate config fields, explicit structured output config. No auto-detection, no dual-purpose fields, no env var guessing.

## Objective

Move Kaizen-py's provider configuration model from implicit magic toward explicit configuration, aligned with kailash-rs's approach. Users write 2-3 more lines of config, but zero magic means zero bugs in this category.

## Specific Implicit Behaviors to Evaluate

1. **Auto-detection of Azure endpoints** — `AzureBackendDetector` infers backend from URL regex patterns. Breaks on new Azure regions/URL schemes.
2. **Dual-purpose `provider_config`** — Single field serves as both response_format config AND provider-specific settings (api_version, etc). Ambiguous.
3. **Auto-generation of `provider_config`** — `WorkflowGenerator` silently creates `{"type": "json_object"}` for Azure. User doesn't know it happened.
4. **System prompt auto-patching** — `WorkflowGenerator` appends "Respond with JSON" to prompts it didn't generate, working around Azure's requirement.
5. **Env var guessing** — Multiple env var names for the same setting (AZURE_API_VERSION, AZURE_OPENAI_API_VERSION, etc).
6. **Two parallel `_generate_system_prompt()` implementations** — `BaseAgent` and `WorkflowGenerator` both generate prompts, diverging over time.

## Constraints

- EATP D6: Python and Rust SDKs implement independently but semantics MUST match
- Backward compatibility: Existing user code should not break without a migration path
- This is the BUILD repo — we fix the SDK directly, no workarounds

## Non-goals

- Rewriting the entire Kaizen framework
- Changing non-Azure providers (OpenAI, Google, etc) unless they share the same bugs
- Removing all env var support (env vars are fine, just not ambiguous ones)
