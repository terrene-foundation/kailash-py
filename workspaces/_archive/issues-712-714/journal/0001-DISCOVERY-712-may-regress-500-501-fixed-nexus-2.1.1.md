---
type: DISCOVERY
created: 2026-04-29
issue: 712
phase: 01-analyze
---

# 712 may regress #500/#501 — both fixed in nexus 2.1.1 via PR #533

## Finding

Issue #712 (the downstream consumer: `@nexus.app.on_event("startup")` silently ignored) is the
**third instance of the same FastAPI-lifespan-footgun bug class** in this repo:

| #   | Date       | Bug                                                                     | Fix                      |
| --- | ---------- | ----------------------------------------------------------------------- | ------------------------ |
| 500 | 2026-04-18 | `router.on_startup.append(fn)` silent no-op under custom lifespan       | PR #533 → nexus-v2.1.1   |
| 501 | 2026-04-18 | `_call_startup_hooks` uses `asyncio.run()` → kills bg tasks             | Same PR #533             |
| 531 | 2026-04-19 | Regression: `app.router.startup()` doesn't exist (must be `_startup()`) | PR #533 → nexus-v2.1.1   |
| 538 | 2026-04-19 | #531 fix not shipped to PyPI (kailash core wheel not cut)               | PR #540 → kailash-v2.8.9 |
| 712 | 2026-04-29 | `@nexus.app.on_event("startup")` silently dropped                       | THIS WORKSTREAM          |

`@app.on_event("startup")` is FastAPI's documented decorator that calls
`app.add_event_handler("startup", fn)` → `self.router.add_event_handler(...)`
→ appends to `self.router.on_startup`. So at the FastAPI ABI level, #500's
`router.on_startup.append(fn)` and #712's `@app.on_event("startup")` should
hit the same list — and both should be honored by the #533 fix that drives
`_startup()` / `_shutdown()` from inside the custom lifespan.

## Three possible explanations (verify in /analyze deep-dive)

1. **Regression**: the #533 fix was reverted, removed, or broken between
   nexus-v2.1.1 (the fix-shipping release) and nexus-v2.4.1 (current).
   Pattern would surface as: lifespan no longer calls `_startup()`, OR calls
   it before `on_event` decorators have a chance to register, OR FastAPI
   upstream changed `_startup()` semantics.

2. **Stale consumer**: the downstream consumer is pinned to a pre-2.1.1 nexus, in which
   case #712 is the same bug as #500 surfacing under a slightly different
   API. Fix is "upgrade nexus." The linked the downstream consumer commit `d5b3bd15`
   workaround is the SAME `app.router.lifespan_context` wrapper from impact-verse
   commit `f1186b28` referenced in #500.

3. **Fresh facet**: `@on_event` decoration involves a FastAPI codepath that
   `_startup()` doesn't pick up — possibly because `add_event_handler` writes
   to a different list now, or because FastAPI's deprecation of `on_event`
   (the docs deprecate it in favor of lifespan) introduced a new no-op path.

## Why this matters before /todos

If (2), the fix is documentation/upgrade guidance — no SDK change needed.
If (1) or (3), the fix is a code change in `workflow_server.py` lifespan
AND a regression test that would have caught the failure mode #533 missed.

**The deep-dive agent for #712 will report which.** Decision branch is large
enough that /todos cannot be drafted without ground truth.

## Cross-references

- #500 close comment / PR #533 merge commit: `1e184541b74c813541191e270b0321612b06feed`
- #531 fix-of-fix commit: same PR #533 (kailash 2.8.9, PR #540 hotfix)
- the downstream consumer workaround: `d5b3bd15` (referenced in #712 body)
- impact-verse same-class workaround: `f1186b28` (referenced in #500 body)
- Cross-SDK note: kailash-rs uses axum + tokio, no equivalent custom lifespan
  wrapper, so this bug class does not exist on the Rust side.

## Implication for the analyze plan

The same code area was patched within the same week in April 2026 by three
distinct PRs. That bug-density-per-LOC is the failure-pattern signal —
this code path lacks structural protection (e.g., a Tier 2 test that
exercises lifespan with realistic consumer hook patterns). The
`/codify` step at the end of this workstream MUST add such a test AND a
rule about lifespan-handler registration semantics to prevent the next
session from rediscovering this.
