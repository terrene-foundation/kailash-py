# DISCOVERY — LLM wire-layer dispatch pattern extracted from #498 + #462

**Date:** 2026-04-19
**Workspace:** issue-498-llm-deployment (final session — S9 shipped, extended by #462 in a separate cycle)
**Author:** `/codify` — sessions 2026-04-17 → 2026-04-19

## What

The `#498` four-axis `LlmDeployment` abstraction and `#462` `LlmClient.embed()` together produced a reusable pattern for adding wire-send methods on `LlmClient`. The pattern is now documented in `skills/04-kaizen/kaizen-llm-deployment.md` so future wire-send methods (`complete()`, additional embed providers) can follow it without re-discovering the shape.

## Pattern summary

1. **Typed-enum dispatch table** (e.g. `_EMBED_DISPATCH`) keyed on `WireProtocol` — each entry pairs a wire-protocol shaper module with a path suffix + env-model hint. Adding a provider means adding one entry, not a conditional branch.
2. **Shapers are pure** (`build_request_payload`, `parse_response`) — no I/O, no mocking concerns, typed errors at shape boundaries, sort-by-index for providers that don't guarantee order.
3. **HTTP routes through `LlmHttpClient`** — single constructor site for `httpx.AsyncClient`; direct construction inside wire adapters is BLOCKED (bypasses `SafeDnsResolver`).
4. **Errors use `kaizen.llm.errors`** hierarchy — no new exceptions invented per wire.
5. **Tests mirror the dispatch** — Tier 1 shaper tests (pure-function contract), Tier 2 wiring tests through `LlmClient` facade (real API if creds, always-runs SSRF regression, structural `inspect.iscoroutinefunction`).
6. **Facade file naming** — Tier 2 wiring files MUST be `test_<subject>_wiring.py` (absence grep-able per `rules/facade-manager-detection.md` MUST 2).

## Why extract now

The pattern appeared twice in the same week (#498 S1–S9, then #462 embed). Each future wire-send method will otherwise re-derive it from source reading + specialist dispatch — two sessions of reinvention per method. Capturing as a skill eliminates that tax.

## Authority

- Spec: `specs/kaizen-llm-deployments.md` (#498 S9)
- Implementation: `packages/kailash-kaizen/src/kaizen/llm/client.py:232-437` (embed + dispatch)
- Cross-SDK mirror: `esperie-enterprise/kailash-rs#406` + `#393`
- Codified-to: `skills/04-kaizen/kaizen-llm-deployment.md`

## Next-time checklist

When adding the next wire-send method (e.g. `complete()`):

- [ ] Read `specs/kaizen-llm-deployments.md` — complete() MUST ship end-to-end or not at all
- [ ] Load `skills/04-kaizen/kaizen-llm-deployment.md` first
- [ ] Write shapers following the build/parse contract
- [ ] Add to `_COMPLETE_DISPATCH` (mirrors `_EMBED_DISPATCH`)
- [ ] Tier 2 wiring test through `LlmClient.from_deployment(...)` facade
- [ ] SSRF regression test pointing at `169.254.169.254`
- [ ] Cross-SDK issue on `esperie-enterprise/kailash-rs` if Python ships first
