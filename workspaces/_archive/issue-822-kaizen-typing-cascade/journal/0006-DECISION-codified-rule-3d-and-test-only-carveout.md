---
type: DECISION
date: 2026-05-05
created_at: 2026-05-05T23:30:00Z
author: agent
session_id: codify-2026-05-05
session_turn: /codify
project: kailash-py / issue-822 + issue-821
topic: codified two rule additions — zero-tolerance Rule 3d + build-repo-release-discipline Rule 1a
phase: codify
tags: [codify, zero-tolerance, build-repo-release-discipline, rule-update]
---

# DECISION — Codified two rule additions from #822 + #821 cycle

**Date:** 2026-05-05
**Phase:** /codify

## What was codified

Two rule clauses added to the kailash-py BUILD repo's `.claude/rules/`:

### 1. `zero-tolerance.md` — new Rule 3d: Dual-Shape Return + Structural Guard = Silent Fallback

A property/method whose return type is a union of structurally-distinct
shapes (e.g., `Union[ConfigWrapper(dict), KaizenConfig(dataclass)]`) MUST
NOT be consumed via a structural existence guard (`hasattr(value, "method")`)
that resolves True for one branch and False for the other. The guard
silently flips False on the branch that lacks the attribute, and the
documented behavior never fires for users on that branch.

**Origin:** Issue #822 silent-fallback discovery (`workspaces/issue-822-kaizen-typing-cascade/journal/0003-DISCOVERY-signature-programming-gate-silent-noop.md`). The `signature_programming_enabled` gate at `agents.py:458` was a silent no-op for `KaizenConfig(...)` users because the dataclass has no `.get()` method — the `hasattr` guard flipped False and the gate never fired. Tests passed because they used dict-shaped config. Fix shipped in kailash-kaizen 2.19.0.

### 2. `build-repo-release-discipline.md` — new Rule 1a: Carve-Out — Test-Only / Docs-Only / Workspace-Only Diffs

A PR whose diff is strictly test-only, docs-only, or workspace-only MAY
merge without `/release` because the diff produces no consumer-visible
artifact change — PyPI version unchanged, wheel content identical,
downstream installs see no change. Allowlist + explicit exclusions
(`CHANGELOG.md`, `pyproject.toml`, `__init__.py::__version__`, `src/**`,
`packages/**/src/**`, `specs/**`, `.github/workflows/**`, `uv.lock`)
prevent rationalization gaps.

**Origin:** Issue #821 session-notes flagged the carve-out for `/codify`. PR #824 (test parity for `kaizen-agents/research_patterns/*`) merged via admin without `/release`; user approved the no-release path because the diff was strictly under `packages/kaizen-agents/tests/unit/`. Without the codified carve-out, the next BUILD-repo session re-derives the same A/B decision.

## Alternatives considered

1. **Add Rule 3d as a separate rule file** — rejected. The pattern is
   structurally a Rule 3 silent-fallback variant; nesting under Rule 3
   keeps related patterns co-located. zero-tolerance.md is already 317
   LOC (above the 200-LOC soft limit) but is a CRIT baseline rule, so
   the size budget is appropriately relaxed.

2. **Add the carve-out as a sub-rule under build-repo-release-discipline
   Rule 1, vs as a separate top-level rule.** — chose sub-rule. The
   carve-out is a refinement of Rule 1's "every code merge MUST proceed
   through release" claim, not an independent obligation. Sub-rule
   placement keeps the two clauses adjacent so readers don't miss the
   carve-out.

3. **Codify the LLM-first violation in `_generate_role_based_traits` (#822 J0004).**
   — rejected for /codify. Already covered by `rules/agent-reasoning.md`
   Rule 1; the discovery is a follow-up issue (#829), not new methodology.
   A rule update would be redundant with existing prose.

4. **Codify the brief under-counts pattern (#822 J0001).** — rejected for
   /codify. Already covered by `rules/agents.md` § Parallel Brief-Claim
   Verification, which fired correctly during /analyze. The discovery
   confirms the rule works as intended; no update needed.

5. **Codify orphan detection across structural splits (#822 J0002).** —
   rejected for /codify. Already covered by `rules/orphan-detection.md`
   - `rules/zero-tolerance.md` Rules 1c, 2 + `rules/cross-sdk-inspection.md`.
     The discovery confirms the existing rules detect the pattern.

## Trust Posture Wiring

Both rule files are grandfathered (predate `rules/trust-posture.md`); per
Phase 1 enforcement policy, no wiring section required for clause
additions to grandfathered rules. Phase 2 enforcement (`/codify`
Trust-Posture Wiring requirement) activates after ≥10 real sessions.

## Cross-SDK consideration

Both rules are language-agnostic and apply identically to kailash-rs:

- **Rule 3d** — Rust's `match` exhaustiveness + `enum` discrimination
  prevents the dual-shape silent-fallback at the type-system level for
  enum returns, but `&dyn Trait` returns + `if let Some(x) = ...` guards
  recreate the pattern. Worth global classification at loom Gate 1.

- **Rule 1a** — `cargo` ships crates, not git trees; same wheel-vs-tree
  argument applies. `tests/`, `docs/`, `workspaces/` translate directly;
  the `pyproject.toml` exclusion translates to `Cargo.toml::[package]
exclude = [...]`.

Recommended loom action: classify both as GLOBAL at Gate 1 with
cross-SDK propagation noted for the next kailash-rs `/sync` cycle.

## Consequences

1. Future agents working on kaizen-style dual-shape config APIs will
   pattern-match Rule 3d at design time and choose discriminator
   dispatch over structural guards.
2. Future BUILD-repo sessions merging test-only PRs will not re-derive
   the carve-out A/B decision; Rule 1a's allowlist + BLOCKED
   rationalizations short-circuit the question.
3. The `release-drift.js` lib (which already correctly returns "no drift"
   for unchanged versions) becomes the executable companion to Rule 1a's
   prose — operators can verify carve-out applicability via the existing
   `node .claude/hooks/lib/release-drift.js` invocation.

## Follow-up actions

- [x] Edit `.claude/rules/zero-tolerance.md` — Rule 3d inserted
- [x] Edit `.claude/rules/build-repo-release-discipline.md` — Rule 1a inserted + ABSOLUTE clause refined
- [x] Archive distributed proposal `.claude/.proposals/latest.yaml` → `.claude/.proposals/archive/2026-05-03-kailash-py-issue-781-todo-cleanup.yaml`
- [x] Create fresh `.claude/.proposals/latest.yaml` for loom Gate 1 review
- [x] Update `.claude/learning/learning-codified.json`
- [x] Run cc-architect red team on both rule edits
- [ ] Loom human classifies both as GLOBAL at next `/sync py` Gate 1
- [ ] Cross-SDK propagation: kailash-rs `/sync rs` cycle picks up loom's distributed version

## For Discussion

1. **Counterfactual:** if Rule 3d had existed before #822, would the
   `signature_programming_enabled` gate have shipped broken? Pyright DID
   flag the call site (`reportAttributeAccessIssue`); the rule would
   have provided the framing for the fix at design time, before pyright
   surfaced the symptom. Is the rule's value preventive (catch at design)
   or detective (frame the fix when pyright catches the symptom)?

2. **Specific data:** Rule 1a's allowlist enumerates 4 carve-out
   directories + 8 explicit exclusions. The 8 exclusions came from
   walking the actual `pyproject.toml::include` and `tool.setuptools.packages`
   shape. Are there BUILD-repo file types not yet enumerated (e.g.,
   `Dockerfile`, `docker-compose.yml`, `scripts/release/`) that should
   be in the exclusion list? What's the cost of an under-enumerated
   list? (Answer: re-derivation per session — exactly the cost the
   carve-out is meant to eliminate.)

3. **Trade-off:** Rule 3d says "either dispatch on a discriminator OR
   collapse the API to a single return shape." The collapse path is
   structurally cleaner but a backwards-incompatible refactor. The
   discriminator path is additive but couples every consumer to the
   union shape. For new APIs, the rule says collapse is preferred.
   Should the rule add an explicit guidance that union return types
   should require a `Why:` justification at design time?

## References

- `workspaces/issue-822-kaizen-typing-cascade/journal/0003-DISCOVERY-signature-programming-gate-silent-noop.md`
- `workspaces/issue-821-kaizen-agents-research-tests/.session-notes` § Open questions
- `.claude/rules/zero-tolerance.md` Rule 3d (newly added)
- `.claude/rules/build-repo-release-discipline.md` Rule 1a (newly added)
- `.claude/.proposals/latest.yaml` (this codify cycle)
- `.claude/.proposals/archive/2026-05-03-kailash-py-issue-781-todo-cleanup.yaml` (archived prior cycle)
