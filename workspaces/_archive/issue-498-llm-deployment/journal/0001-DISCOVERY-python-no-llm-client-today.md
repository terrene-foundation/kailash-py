---
type: DISCOVERY
date: 2026-04-18
author: agent
project: kailash-py
topic: Python SDK has no LlmClient class today — back-compat target is provider registry
phase: analyze
tags: [cross-sdk, eatp-d6, issue-498, llm-deployment, divergence]
---

# Python Has No `LlmClient` Today — Back-Compat Target Shifts

**Finding**: GH #498 is a cross-SDK mirror of kailash-rs#406 (four-axis
LLM deployment abstraction). The issue's "Back-compat" section is
written against the Rust shape:

> - `kailash.LlmClient()` today preserved via preset-backed implementation.
> - `kailash.Agent(config, client)` unchanged.
> - Legacy env-key detection preserved in `from_env()`.
> - Zero breaking changes for callers that work today.

**Reality in Python**: No `LlmClient` class exists. LLM work flows through:

1. `kaizen.providers.registry.get_provider(name)` — lookup by provider name
2. `kaizen.config.providers.autoselect_provider()` — env-driven selection
3. Concrete per-provider classes: `kaizen.providers.openai.OpenAIProvider`,
   `kaizen.providers.anthropic.AnthropicProvider`,
   `kaizen.providers.google.GoogleProvider`

39 consumer files import and use this registry/provider surface.

**Reinterpretation of brief criterion**: "Zero breaking changes for
callers that work today" maps to preserving the **provider registry**
surface, NOT an `LlmClient` class. The Python implementation introduces
`LlmClient.from_deployment(...)` as a NEW symbol — additive, not a
back-compat target.

**Divergence from Rust shape** (EATP D6 "matching semantics"):

- Rust already has `LlmClient` as a builder; introducing
  `from_deployment()` is additive on an existing class.
- Python introduces `LlmClient` for the first time alongside the
  provider registry. The provider registry remains the low-level
  primitive; `LlmClient` is the high-level preset-scoped client.

**Semantic match preserved**: preset names, `from_env()` precedence,
observability field names, SSRF guard — all four identical to Rust.
Only the class-surface shape differs because Python starts from a
different baseline.

**Action at `/todos` gate**: Surface this divergence to the user.
Options:

- **(A)** Introduce `LlmClient` as new class + keep provider registry
  unchanged. `LlmClient.from_deployment()` is the deployment-scoped
  entrypoint; `registry.get_provider()` remains for low-level use.
  **(Recommended)**
- **(B)** Route the provider registry THROUGH `LlmClient` under the
  hood. Registry becomes a compatibility shim. Larger blast radius,
  possible test churn across 39 files.
- **(C)** Treat this as an architectural decision in a new ADR and
  defer implementation choice to the user.

The analyst recommends (A). Rationale: additive surface is lowest-risk,
zero churn on existing 39 consumer files, and mirrors Rust's "one
client class, preset-configured" design at the high-level layer. The
provider registry stays as a valid escape hatch for users who need
pre-4-axis semantics.

## For Discussion

- Counterfactual: if we'd implemented Rust's exact shape, we'd be
  replacing the registry API for 39 callers. That's explicit scope
  creep beyond the EATP D6 mandate. Does (A) still count as "matching
  Rust semantics" when the class structure differs? Yes — D6 says
  "semantics MUST match while implementation details may differ (Rust
  idioms vs Python idioms)." The public preset names + env precedence
  - observability shape are where the match happens, not the class
    topology.
- The issue body's "Zero breaking changes for callers that work
  today" is authored by someone presuming Python has Rust's surface.
  Should the cross-SDK issue template include a "verify back-compat
  targets exist in the receiving SDK" check before filing? File an
  atelier/loom-side enhancement.
- When does the provider registry get deprecated, if ever? The
  analyst says it doesn't — it's the primitive under `LlmClient`.
  Future review point: once S9 parity suite lands, re-assess whether
  the registry is still doing meaningful work or has become a
  redundant second entrypoint.

## References

- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-498-llm-deployment/01-analysis/02-kailash-py-current-state.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-498-llm-deployment/02-plans/02-adr-0001-llm-deployment-abstraction.md`
- `/Users/esperie/repos/loom/kailash-rs/specs/llm-deployments.md` (authoritative Rust spec)
