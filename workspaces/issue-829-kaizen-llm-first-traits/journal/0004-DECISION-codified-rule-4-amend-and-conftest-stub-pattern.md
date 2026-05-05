---
type: DECISION
date: 2026-05-06
created_at: 2026-05-06T18:30:00Z
author: agent
session_id: codify-2026-05-06-issue-829
session_turn: post-redteam
project: issue-829-kaizen-llm-first-traits
topic: codified two patterns from the issue-829 release cycle
phase: codify
tags: [autonomous-execution, testing, codify, conftest, security-reviewer]
---

# DECISION — Codified Rule 4 amend + conftest-stub pattern from issue-829 cycle

## What was codified

Two AMEND actions on existing rule files (not new rules) proposed via
`.claude/.proposals/latest.yaml` for loom Gate-1 review:

### Action 1 — `rules/autonomous-execution.md` Rule 4 surface broadening

Today's Rule 4 ("Fix-Immediately When Review Surfaces A Same-Class Gap")
names "code review or self-verification" as the trigger surface. The
2026-05-06 session demonstrated cleanly that the rule generalizes to
**any gate-level review** — specifically, security-reviewer surfacings.

Concrete evidence: PR #836 (kailash-kaizen 2.20.0) was REJECTED by
security-reviewer with 1 HIGH (prompt-injection sanitization missing)
and 2 MEDIUM (raw role logged at WARN, unbounded cache as DoS surface).
All three fit within the shard's remaining capacity (≤30 LOC each, all
within `framework.py:_generate_role_based_traits` + adjacent
`Kaizen.__init__`). All three landed in the same commit `ba476b88`.
Security-reviewer re-approved on the post-fix diff.

Filing follow-up issues for any of the three would have:

- Wasted the still-warm shard context (security analysis + threat-model
  walkthrough + spec invariants all loaded).
- Re-cost the next session 2-5× the marginal time (per Rule 4's
  existing "context-reload" rationale).
- Risked the H1 prompt-injection fix shipping a PyPI release before
  the follow-up landed — exact failure-mode the security-reviewer was
  designed to prevent.

The amendment broadens the rule's first sentence and adds 2026-05-06
evidence to the Origin paragraph.

### Action 2 — `rules/testing.md` new advisory subsection on conftest-scope stubs

When an internal method becomes side-effecting (LLM call, DB lookup,
network fetch) WITHOUT changing its return-shape contract, the
canonical Tier-1 sweep is one autouse fixture in `tests/unit/conftest.py`.
Pytest's conftest-scope rules guarantee the stub does NOT leak to
Tier-2 (`tests/integration/`) or Tier-3 (`tests/e2e/`).

Concrete evidence: the kaizen #829 sweep had 36 NEEDS-FIX call sites
across 8 files. The conftest fixture (44 LOC at
`packages/kailash-kaizen/tests/unit/conftest.py`) collapsed all 36 to
one file. Future test additions in `tests/unit/` pick up the stub for
free.

Marked **advisory**, not MUST — explicit `behavior_traits=[...]` per
call site is also valid. The conftest pattern wins on every dimension
when:

- ≥10 Tier-1 call sites depend on the side-effecting method.
- The actual content of the method's output isn't asserted in Tier-1
  (only the shape).
- Tier-1 must remain offline + fast per the 3-Tier contract.

## Alternatives considered

1. **New top-level rule file for either pattern.** Rejected for both:
   - Action 1 is structurally an extension of an existing rule's
     trigger-surface enumeration. No new authority is being claimed —
     the same rule, slightly broader.
   - Action 2 is an advisory pattern, not a MUST. Rules carry MUST
     weight; advisory patterns belong in the supplementary section
     of an existing rule OR in a skill guide.
2. **Skill addition under `12-testing-strategies/`** for Action 2.
   Rejected because the pattern is short enough to live inline in
   `rules/testing.md` and survives near the 3-Tier section it
   amends. A skill addition would duplicate the prose without adding
   discoverability — `rules/testing.md` is the canonical surface.
3. **No codification — leave as journal evidence only.** Rejected
   because both patterns are reusable across SDKs (autonomous-execution
   surface broadening applies to every gate-level review in any BUILD
   repo; conftest-stub pattern applies wherever pytest runs). The
   institutional value lives in promoting them into rules-tier prose.

## Why this matters

Both amendments encode lessons that future sessions will benefit from:

- **Rule 4 amend**: closes the rationalization gap "security-reviewer
  is a different agent, not in scope for fix-immediately." That
  gap doesn't exist in the rule's current text — but a
  literally-minded read could miss the spirit. The amendment makes
  the spirit explicit.
- **Conftest-stub pattern**: surfaces an optimization that's invisible
  until you've done the 36-edit alternative once. Codifying it
  saves the next agent the comparison.

## Trust Posture Wiring

NOT_REQUIRED — both actions are AMEND of existing rule files, not
NEW rule files. Per `/codify` Step 6b, wiring is per-new-rule-file.
Per `rules/trust-posture.md` Phase 1/2 rollout, `/codify` integration
enforcement is also Phase 2 (deferred). Both checks pass.

## Follow-up actions

- Loom Gate 1 review of `.claude/.proposals/latest.yaml` (next
  loom session running `/sync` from BUILD repos).
- After loom classifies + distributes, the amendments will surface in
  the next downstream `/sync` cycle to `kailash-py` (this repo) AND
  `kailash-rs` (the conftest-stub pattern needs Rust-variant overlay
  if loom decides it earns a sibling rule on the kailash-rs side; the
  Rule 4 amend is naturally cross-language).

## For Discussion

1. **Counterfactual.** If we'd left the security-reviewer findings to
   a follow-up issue, what would the cost have been? My estimate: ~30
   min next session to reload context + re-derive the threat model,
   vs ~10 min same-shard to add the regex + hashlib + OrderedDict.
   The 3× cost ratio matches Rule 4's existing "context-reload"
   rationale. Is this the right magnitude, or am I underestimating
   the security-review re-run cost?

2. **Specific data — when does the conftest pattern become wrong?**
   At 36 call sites the pattern is unambiguously right. At 3 call
   sites explicit args are clearer. Where's the crossover? My read:
   ~5-10 call sites is the gray zone — explicit args still readable,
   conftest stub starts to pay off. The proposed advisory text says
   "≥10" as the lower bound for "use the stub"; should this be
   tighter / looser?

3. **Sibling SDKs.** kailash-rs uses `cargo nextest` which has
   different shared-fixture mechanics than pytest's conftest. If
   loom decides the conftest-stub pattern earns a sibling rule on
   the Rust side, what's the equivalent — `mod common`?
   `#[fixture]` from `rstest`? Should the proposal include
   rs_translation_notes for this, or defer to the loom-side review?
