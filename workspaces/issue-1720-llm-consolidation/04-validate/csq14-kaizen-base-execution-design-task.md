# Separate Kaizen base execution design task

Status: proposal awaiting the user's disposition; not an approved deferral.

During the bounded diagnostic review, the inherited implementation of
`KaizenNode._execute_ai_model` was found to construct a canned response instead of
calling a provider. The source labels it `Placeholder implementation for foundation`
and builds `AI Response to: ...`; see
`packages/kailash-kaizen/src/kaizen/nodes/base.py:230-256` at commit
`7814db7a1`. A local execution probe returned
`{"response": "AI Response to: 'base-prompt-person@example.invalid...' using mock-model", "model_used": "mock-model", "prompt_length": 34, "response_length": 72}`.
Evidence: `/tmp/csq14-kaizen-base-probe.py` and `/tmp/csq14-kaizen-base-probe.log`.
The probe establishes the inherited method's behavior; it does not claim that
subclasses overriding `_execute_ai_model` use this implementation.

The current promotion's diagnostic repair can remove private prompt/response data
from automatic logs while preserving public results. Replacing the inherited
execution method changes a separate public API contract, including provider
selection, authentication, synchronous invocation, result shape and compatibility
with subclasses. AGENTS.md Zero-Tolerance Rule 2 forbids production placeholders;
leaving this separate behavior for a design task therefore needs an explicit user
exception, just as the earlier pools decision did.

Proposed separate task acceptance criteria:

- Determine supported direct `KaizenNode` usage and subclass compatibility from
  actual callers and the authoritative Kaizen specs.
- Select the existing Kaizen provider/agent abstraction; do not implement a second
  raw provider client or retain simulated production responses.
- Define explicit provider/model configuration and missing-configuration errors,
  synchronous invocation rules, output shape and any required deprecation path.
- Execute meaningful provider-seam tests and required real-provider integration
  tests without silently converting missing provider configuration into success.
- Preserve automatic diagnostic privacy and document migration behavior.

No change to provider execution, public outputs or model configuration is included
in the current diagnostic patch. The authorized pools design exception does not
itself authorize this separate exception.
