# DECISION — /codify: default/behavior-change stale-test sweep (orphan-detection Rule 4b)

Date: 2026-07-19. Repo class: BUILD (`name = "kailash"`). Coordination OFF
(un-enrolled public repo) → no codify lease needed.

## What was codified

**`.claude/rules/orphan-detection.md` — new Rule 4b** "Default / Behavior Change MUST
Sweep Stale-Assertion Tests In The Same PR — Including Out-Of-CI-Matrix Tests."

- **Generalizes Rule 4a** (implement-stub → sweep-deferral-tests) to ANY default/behavior
  change: a changed default parameter / fallback constant / resolution order / env-derived
  default MUST update or delete every test asserting the OLD value in the same PR.
- **Adds the load-bearing insight "CI-green is NOT full-suite-green":** the sweep MUST
  cover tests OUTSIDE the standard CI matrix — example tests, optional-dependency-gated
  tests (silently skipped when the dep is absent), and ambient-`.env`/environment-dependent
  tests — which pass **stale-green** because CI never runs them, surfacing only in a full
  local suite.
- Ships canonical-8-field Trust Posture Wiring (clause-scoped; orphan-detection.md is a
  grandfathered `priority:10` path-scoped rule). Added a length rationale in the same edit
  (the rule was already >200 lines; my clause pushed it further).

## Evidence (DISCOVERY)

This session's #1844/#1845 cost fix (**PR #1847**) changed model defaults
(`gpt-3.5-turbo`→`gpt-4o-mini` in examples; `gpt-4`→env-resolved in specialized agents).
**#1847 CI was fully green** (28 checks) — yet **18 test files** still asserted the old
defaults: kailash-kaizen example tests (not in the matrix), a `sentence-transformers`-gated
test (silently skipped — never ran), and kaizen-agents specialized-agent tests that resolved
against the ambient `.env` rather than a stable literal. They were caught only at **release
prep (PR #1850)** running the full suite with all optional deps installed — NOT by #1847's
own CI or its targeted regression run. Root cause: a default change's blast radius includes
tests the fast CI matrix deliberately excludes.

## Process notes

- `orphan-detection.md` is NOT on the `self-referential-codify.md` Rule 2 allowlist → no
  mandatory multi-agent redteam gate; structural self-check confirmed the 8 wiring fields +
  DO/DO-NOT + Why + BLOCKED present.
- `priority:10 path-scoped` → `rule-authoring.md` Rule 10 proximity-band gate does NOT fire
  (no baseline-emission cost).
- Proposal appended to `.claude/.proposals/latest.yaml` (`origin: build`, `pending_review`,
  classification GLOBAL — language-agnostic: any SDK/consumer changing a default inherits
  the failure mode). Anchor `learning-codified.json::last_codified` advanced.
