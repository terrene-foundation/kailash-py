---
priority: 0
scope: baseline
---

# Self-Referential /codify Discipline

A `/codify` execution is **self-referential** when its proposal touches the loom-side artifacts that govern codification itself — commands like `/codify` / `/sync` / `/redteam`, the skills backing them, the rules governing artifact quality and trust posture, the hooks detecting violations, the bin scripts validating output. On those surfaces the agent is authoring rules that constrain its own next behavior, so a single-pass shipment can silently propagate a defect into every future session that loads the rule.

Per posture defaults (`.claude/skills/32-trust-posture/redteam-integration.md`), L5_DELEGATED makes Round 1 OPTIONAL. On a non-self-referential surface that is the right trade-off — the user's blast radius is bounded by the artifact and the next session catches what slipped. On the self-referential surface the same default ships defects into the gate the next session would otherwise use to catch them. The forest-ledger arc (journal/0089–0098) cost 7 redteam rounds + a mid-arc Option A→B redesign before the substring-mask failure class was structurally closed — and per journal/0098 §FD #3: _"7 rounds of evidence say the single-pass L5 default would have shipped the R1 substring-mask silently."_

This rule overrides the posture default for that specific surface, and ONLY that surface, with a positive allowlist that names every file the gate covers.

## MUST Rules

### 1. Self-Referential /codify MUST Carry Multi-Agent Redteam-With-Tests Regardless Of Posture

When a `/codify` proposal touches ANY file matching the self-referential surface allowlist below, the orchestrator MUST dispatch a multi-agent redteam-with-tests round before merging the codify, EVEN AT L5_DELEGATED posture where Round 1 would otherwise be optional. The team MUST include at minimum: a code-review specialist (reviewer agent), a security specialist (security-reviewer), and a structural-validator specialist (cc-architect for artifact-quality surface, gold-standards-validator for naming/licensing surface, analyst for contract-design surface). The round runs in parallel — sequential single-agent review does NOT satisfy the multi-agent requirement.

The dispatched team MUST receive the proposal AND its receipt-journal entry AND the originating evidence (the journal entries the codify cites as motivation). Each team member reports findings independently; cross-agent disagreement on CRIT/HIGH MUST be resolved per `.claude/skills/32-trust-posture/redteam-integration.md` § Round-N — Cross-Agent CRIT/HIGH Disagreement Resolution (resolve by construction, never by averaging severities).

```markdown
# DO — /codify touches a self-referential surface file → multi-agent redteam runs in parallel before merge

Surface touched: .claude/rules/trust-posture.md (allowlist match)
Dispatched team (parallel): reviewer, security-reviewer, cc-architect, analyst
Each receives: proposal + receipt journal + originating evidence
Cross-agent verdicts reconciled by construction against the contract
Merge proceeds only when ≥0 genuine CRIT/HIGH across all four

# DO NOT — surface touched, posture L5, ship single-pass under "Round 1 OPTIONAL"

Surface touched: .claude/rules/cc-artifacts.md (allowlist match)
Posture: L5_DELEGATED → Round 1 OPTIONAL → skip
Merge proceeds with no independent review
(this is exactly the failure mode the rule blocks)
```

**BLOCKED rationalizations:**

- "Posture is L5, the table says Round 1 is OPTIONAL"
- "The codify is small (one bullet, one line), redteam is overkill"
- "The proposal only touches one allowlist file, the surface is narrow"
- "I am the orchestrator, I already reviewed the proposal as I drafted it"
- "The receipt journal documents the rationale, that satisfies independent review"
- "Multi-agent costs ~30–60 min of agent time; the codify ships value now"
- "Cross-agent dispatch was the prior session's rule — this session's posture overrides it"
- "Sequential review by one specialist after another is functionally equivalent"
- "The next session will catch it under its own gate"
- "If anything slips, the regression-within-grace mechanism downgrades us"
- "The rule's own bootstrap-circularity carve-out lets us skip"
  (the carve-out is one-time-per-rule per Rule 2 below, NOT a per-session shortcut)

**Why:** A defect in a self-referential artifact is a load-bearing defect for every session that loads it; the cost of letting one slip is N future sessions paying the substring-mask cost the forest-ledger arc paid. Multi-agent parallel review at one wall-clock unit (per `rules/agents.md` § Parallel Execution) is the structural defense against the failure mode the arc surfaced; sequential or single-agent review re-introduces the same blind spot.

### 2. Self-Referential Surface Is A Positive Allowlist (per `cc-artifacts.md` Rule 10)

The self-referential surface MUST be enumerated as a positive allowlist below. Files NOT in the allowlist are outside the gate. New files added to `.claude/` under categories the allowlist enumerates (a new rule under `.claude/rules/` that governs codify-class behavior, a new hook under `.claude/hooks/lib/` that detects violations) MUST be added to the allowlist in the SAME `/codify` that lands them — undeclared new self-referential files outside the allowlist is BLOCKED.

The allowlist (load-bearing paths only; edge cases at the boundary resolve in favor of the gate firing — Phase-1 false-positive cost is bounded to one extra redteam round):

- **Commands:** `.claude/commands/codify.md`, `.claude/commands/sync.md`, `.claude/commands/sync-to-build.md`, `.claude/commands/redteam.md`, `.claude/commands/sweep.md`, `.claude/commands/wrapup.md`
- **Skills (codify-discipline):** `.claude/skills/spec-compliance/**`, `.claude/skills/command-authoring/**`, `.claude/skills/skill-authoring/**`, `.claude/skills/hook-authoring/**`, `.claude/skills/sweep/**`, `.claude/skills/32-trust-posture/**`
- **Rules (codify-discipline):** `.claude/rules/{trust-posture,cc-artifacts,coc-sync-landing,artifact-flow,recommendation-quality,value-prioritization,autonomous-execution,agents,sweep-completeness,rule-authoring,variant-authoring,cross-cli-parity,specs-authority,spec-accuracy,probe-driven-verification,hook-output-discipline,verify-resource-existence,time-pressure-discipline,repo-scope-discipline,self-referential-codify}.md`
- **Hooks:** `.claude/hooks/lib/{violation-patterns,detect-violations,state-io,state-resolver,template-resolver,workspace-utils}.js`
- **Bin (codify-class):** `.claude/bin/{validate-*,scan-synced-disclosure,emit-cli-artifacts,emit,compose,sync-tier-aware,sync-consumer-dryrun}.mjs`
- **Audit fixtures:** `.claude/audit-fixtures/violation-patterns/**`
- **Management agents:** `.claude/agents/management/{coc-sync,sync-reviewer,repo-ops,settings-manager}.md`

**BLOCKED rationalizations:**

- "The file LOOKS self-referential but is too peripheral — skip the allowlist"
- "The allowlist is overcomprehensive, narrow it later"
- "A denylist is easier to maintain"
- "Adding the new file to the allowlist is the next codify's job"
- "The new rule under `.claude/rules/` doesn't really govern codify, it's adjacent"
- "Edge cases at the boundary should resolve in favor of NOT firing — the gate is too expensive"

**Why:** A denylist scales linearly with brainstormed exceptions and never closes the class (per `cc-artifacts.md` Rule 10). A positive allowlist closes the class on day one and surfaces drift loudly: every new self-referential file is either declared in the allowlist (gate covers it) or undeclared (this rule fires on the codify trying to ship it). Boundary-favoring-the-gate is the Phase-1 fail-closed default; tightening to fail-open requires Phase-2 evidence.

### 3. Bootstrap-Circularity Carve-Out Is One-Time-Per-Rule

The codify that AUTHORS this rule (and any future codify that authors a similar meta-rule about codify discipline) IS itself a self-referential codify under Rule 1's gate. Running the gate on the codify that authors the gate is circular. Per `rules/trust-posture.md` MUST Rule 7 § Two-Phase Rollout: _"A meta-rule and its enforcement should never bootstrap in the same release — the rule is then drafted by an agent operating without it (mitigates red-team H4 bootstrapping circularity)."_

The carve-out: the FIRST codify that lands this rule (or a similar meta-rule about codify discipline) MAY ship as Phase-1 observer under the prevailing posture default (L5_DELEGATED's Round 1 OPTIONAL). The carve-out is one-time-per-rule and MUST be declared in the codify's receipt journal under a "Bootstrap-circularity disposition" section. Phase-2 enforcement (this rule's gate fires on every subsequent self-referential codify, regardless of posture) starts at the NEXT self-referential codify, NOT at the next session.

```markdown
# DO — first codify of this rule ships Phase-1 observer, declared in receipt

journal/NNNN § Bootstrap-circularity disposition:
"F4 IS a self-referential codification. Per trust-posture.md MUST-7
two-phase rollout, this codify ships F4 as Phase-1 observer under
L5_DELEGATED's Round 1 OPTIONAL. Phase-2 enforcement starts at the
NEXT self-referential codify."

# DO NOT — every future self-referential codify cites bootstrap-circularity to skip the gate

journal/NNNN: "this codify is self-referential, citing bootstrap-circularity
carve-out to skip multi-agent redteam-with-tests"
(BLOCKED — the carve-out is one-time-per-rule, not a per-session shortcut)
```

**Why:** Without the one-time-per-rule constraint, "bootstrap circularity" becomes a rubber stamp every self-referential codify cites to skip the gate. The carve-out exists for the genuine chicken-and-egg case (a meta-rule authoring itself); every subsequent invocation has the prior rule already in scope and IS the case the gate exists to govern.

## Trust Posture Wiring

- **Severity:** `halt-and-report` at /codify gate (cc-architect surfaces the violation at proposal-validation); `advisory` at hook layer (Phase 2, when a self-referential-detection hook lands). Per `rules/hook-output-discipline.md` MUST-2: judgment-bearing gates do not carry `block` severity.
- **Grace period:** 7 days from rule landing.
- **Regression-within-grace:** any same-class violation (a self-referential `/codify` that ships without multi-agent redteam-with-tests within 7 days of this rule landing) triggers emergency downgrade L5→L4 per `rules/trust-posture.md` MUST Rule 4. Trigger key `self_referential_codify_without_redteam` added to trust-posture.md emergency-trigger list (1× = drop 1 posture).
- **Receipt requirement:** SessionStart MUST require `[ack: self-referential-codify]` in the agent's first response IF `posture.json::pending_verification` includes this rule_id.
- **Detection (Phase 1 — this codify):** MANUAL. The `/codify` orchestrator reads the allowlist in Rule 2, checks the proposal's file list against it, and dispatches the multi-agent redteam-with-tests team described in Rule 1 when any match. No hook detection in Phase 1.
- **Detection (Phase 2 — deferred):** `.claude/hooks/lib/codify-self-referential.js` (planned). Runs on `/codify` proposal generation; mechanically detects allowlist matches per Rule 2 and emits an advisory finding the orchestrator MUST resolve before merge. Audit fixtures committed at `.claude/audit-fixtures/codify-self-referential/` per `rules/cc-artifacts.md` Rule 9. Phase 2 lands after ≥3 real self-referential `/codify` cycles have exercised Phase 1 (per `rules/trust-posture.md` MUST Rule 7 § Two-Phase Rollout: enforcement bootstraps after real-session-based exercise).

## Distinct From / Cross-References

- **Extends:** `rules/cc-artifacts.md` Rule 6 (every /codify deploys cc-architect) → this rule adds a parallel multi-agent redteam-with-tests requirement on the self-referential subset of `/codify` executions. cc-artifacts.md Rule 6 still applies to every /codify; this rule layers additional gating on the self-referential surface.
- **Pairs with:** `.claude/skills/32-trust-posture/redteam-integration.md` § Patterns From Convergence Arcs (Patterns a, b, c) — those patterns govern WHAT the redteam round checks; this rule governs WHEN the round MUST fire regardless of posture.
- **Distinct from:** `rules/trust-posture.md` MUST Rule 4 (downgrade triggers) — that rule defines posture-downgrade math; this rule's regression-within-grace clause feeds into MUST-4's emergency-trigger list but does NOT replace it. `rules/trust-posture.md` MUST Rule 7 § Two-Phase Rollout — that rule's principle is the foundation Rule 3 above instantiates; the carve-out language is borrowed and constrained to one-time-per-rule.

## Origin

2026-05-18 — journal/0098 §For Discussion #3 surfaced the question; co-owner approval ("approved") on the F4 recommendation in this session, both cons disclosed (bootstrap-circularity + surface-area definition). Receipt-first journal/0100 (this codify's provenance, per `rules/artifact-flow.md` § Co-Owner-Directed Origination). Originating evidence: forest-ledger arc journal/0089–0098, 7 redteam rounds + mid-arc Option A→B redesign, the substring-mask failure class structurally closed only after Option B inflection.
