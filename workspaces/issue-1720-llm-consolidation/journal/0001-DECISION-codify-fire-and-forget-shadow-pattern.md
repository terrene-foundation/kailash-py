---
type: DECISION
date: 2026-07-16
topic: Focused /codify — fire-and-forget shadow pattern + Wave-1/2 kaizen traps
---

# DECISION — Focused /codify (fire-and-forget shadow pattern)

## Directive

User: "check if we need to /codify since its been some time since we did that" →
assessment surfaced ONE genuinely-new cross-project pattern + two kaizen-specific
traps → user "approved" the focused codify (the fire-and-forget-shadow pattern +
the 2 kaizen notes).

## Cascade-valuable learning codified (cross-project)

**Shadow / dual-run / canary paths are fire-and-forget.** A validation path that
runs a second implementation alongside the primary (to compare/measure) MUST be
dispatched on a daemon thread the primary never joins — reading a deepcopy
snapshot, bounding its own work, catching BaseException, flag-gated OFF by
default — so a hung/slow/crashing shadow provably cannot add latency to, delay,
or break the primary. Landed as a new MUST section in `.claude/rules/patterns.md`
("Shadow / Dual-Run / Canary Paths Are Fire-And-Forget"), the file's natural home
for the SDK's async/threading disciplines (path-scoped `**/*.py`; NOT baseline, NOT
on the self-referential-codify allowlist, so neither the multi-agent self-ref gate
nor the rule-authoring Rule-10 proximity-band gate fires).

Origin: this session's #1720 Wave-2 dual-run redteam surfaced it as a HIGH — a
four-axis-vs-legacy shadow dispatched synchronously with `future.result(timeout=30s)`
added up to 30s × 5 tool-loop rounds of latency to live LLM responses; fixed by
the fire-and-forget daemon-thread refactor, proven by a hung-shadow live-return
latency test.

## Kaizen-specific traps (recorded here per wave-loop G2 — lightweight, NOT rule edits)

1. **Local verify scope MUST include `tests/cross_sdk_parity/`.** CI caught a
   cross-SDK error-taxonomy failure (`test_no_python_only_errors_leak_public_surface`)
   that the `tests/unit/llm/ tests/regression/` local scope missed — a new public
   error (`InvalidApiKeyOverride`) in `kaizen.llm.errors` not present in the Rust
   taxonomy. When touching kaizen LLM code, run
   `pytest tests/unit/llm/ tests/regression/ tests/cross_sdk_parity/` locally
   before pushing.
2. **Client-layer BYOK-override errors belong in `client.py`, not `errors.py`.**
   The `kaizen.llm.errors` module is the cross-SDK-mirrored error taxonomy (scanned
   by `test_no_python_only_errors_leak_public_surface` for parity with Rust). Client-
   layer guards (`UnsupportedApiKeyOverride`, `InvalidApiKeyOverride`) live in
   `client.py` beside their call sites — subclassing `AuthError`, catchable by
   consumers via the parent — NOT in the mirrored `errors.py` module (which would
   demand a Rust counterpart or a leading-underscore private rename).

## Distribution

`patterns.md` is already manifest-registered (a synced `.claude/rules/` artifact),
so its distribution fate is declared — the pattern cascades to downstream consumers
on the next loom `/sync-from-build` ingest of the rule diff (knowledge-cascade-routing
MUST-2 satisfied). The 2 kaizen traps are workspace-local (kaizen-repo-specific), so
they stay here per wave-loop G2 (journal capture for non-cross-project learnings), not
a rule edit.
