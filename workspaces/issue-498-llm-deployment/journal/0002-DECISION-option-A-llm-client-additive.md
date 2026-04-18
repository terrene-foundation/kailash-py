---
type: DECISION
date: 2026-04-18
author: human
project: kailash-py
topic: Option A confirmed — introduce LlmClient additively, keep provider registry as primitive
phase: todos
tags: [cross-sdk, eatp-d6, issue-498, llm-deployment, back-compat]
---

# Option A Confirmed: Additive `LlmClient`, Provider Registry Stays

**Context**: GH #498 is a cross-SDK mirror of kailash-rs#406 (four-axis LLM
deployment abstraction). The issue brief was authored against Rust's
baseline where `LlmClient` already exists. Python has no `LlmClient`
today; 39 consumer files use `kaizen.providers.registry` /
`kaizen.config.providers.autoselect_provider()` directly.

Journal 0001-DISCOVERY surfaced three options:

- **(A)** Introduce `LlmClient` as a new class; keep provider registry
  unchanged as the low-level primitive. `LlmClient.from_deployment()`
  is the deployment-scoped entrypoint.
- **(B)** Route the provider registry THROUGH `LlmClient` under the
  hood. Registry becomes a compatibility shim.
- **(C)** Defer to a new ADR.

## Decision

**Option A** is confirmed as the `/todos` baseline by the human at the
structural approval gate (2026-04-18, session round 4).

## Rationale

1. **Lowest-risk surface change.** Zero churn on the 39 consumer files
   that import the provider registry today. `kailash.LlmClient()` and
   `LlmClient.from_deployment(...)` are additive. The brief's "zero
   breaking changes" criterion is satisfied by preserving the provider
   registry, even though the Rust-shaped language of "preserve
   `kailash.LlmClient()`" doesn't literally apply (no such class today).

2. **EATP D6 "matching semantics" interpretation.** D6 says "semantics
   MUST match while implementation details may differ (Rust idioms vs
   Python idioms)." The cross-SDK match lives at the preset-name +
   env-precedence + observability-shape layer, not at class topology.
   Option A preserves the semantic match without forcing the class
   structure to mirror Rust when the Python baseline differs.

3. **Provider registry as escape hatch.** Users who need pre-4-axis
   provider selection keep `registry.get_provider("openai")`. Users who
   want the deployment-scoped client get `LlmClient.from_deployment(
LlmDeployment.bedrock_claude(...))`. Two entrypoints for two
   complexity levels; no hostile deprecation cycle.

4. **Observability parity is still achievable.** S9 parity test suite
   asserts `deployment_preset` log field byte-identical to Rust; this
   works regardless of whether the Python surface is a single
   `LlmClient` or a dual client + registry shape.

## Alternatives weighed and rejected

- **(B)** would force a rewrite of 39 consumer files that pass
  `provider: "openai"` strings today; scope creep beyond D6.
- **(C)** would delay `/todos` by a full session with no
  architectural upside — the back-compat question is the only real
  question and it's answerable now.

## Consequences

- Plan shards S1–S9 proceed as written in
  `02-plans/01-shard-breakdown.md`. No shard renumbering.
- `LlmClient` lands in S1+S2 as a NEW class; zero-arg
  `LlmClient()` is a stub that composes a sensible default (likely
  `from_env()`-equivalent) — distinct from the Rust back-compat
  promise because Python has no existing `LlmClient()` to preserve.
- The provider registry stays as a primitive. Re-assess at end of S9
  parity suite whether it's still doing meaningful work; do NOT
  deprecate pre-emptively.
- Cross-SDK ticket filed on the atelier/loom side: "cross-SDK issue
  template should verify back-compat targets exist in the receiving
  SDK before using Rust-shaped language in the brief."

## For Discussion

- Counterfactual: if we'd adopted (B), the 39 consumer files would need
  regression tests proving registry-backed paths still work through the
  `LlmClient` shim layer. Is that test coverage implicitly required
  anyway, or is (A)'s additive surface genuinely cheaper?
- The DISCOVERY journal (0001) flags a review point "once S9 parity
  suite lands, re-assess whether the registry is still doing
  meaningful work." What criteria would constitute "no longer
  meaningful"? At least one: if zero new consumer code imports the
  registry after two minor versions, it's a dead primitive.
- Should this decision be reflected in `specs/_index.md` as an explicit
  "Kaizen LLM Deployment" entry pointing to the S9-delivered
  `specs/llm-deployments.md`, even before S9 lands? Per
  `rules/specs-authority.md` MUST 5 (first-instance spec update), the
  answer is yes — but the spec file itself is the S9 deliverable.
  Consensus: add the `_index.md` stub row at S1 time with a "(coming
  in S9)" marker, fill in when S9 ships.

## References

- `workspaces/issue-498-llm-deployment/journal/0001-DISCOVERY-python-no-llm-client-today.md`
- `workspaces/issue-498-llm-deployment/02-plans/01-shard-breakdown.md`
- `workspaces/issue-498-llm-deployment/02-plans/02-adr-0001-llm-deployment-abstraction.md`
- `/Users/esperie/repos/loom/kailash-rs/specs/llm-deployments.md` (authoritative Rust spec)
- GH issue #498; cross-SDK mirror of kailash-rs#406
