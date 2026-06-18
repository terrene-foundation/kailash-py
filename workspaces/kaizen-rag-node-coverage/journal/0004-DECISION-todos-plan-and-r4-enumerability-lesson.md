# DECISION + RISK — /todos plan shape; R4 enumerability lesson

Date: 2026-05-19
Phase: 02 /todos (F8) — plan red-team round-2 convergence

## DECISION — plan shape (awaiting human approval)

Milestone A (prerequisite): A0 (mechanical R4 AST pre-flight) · A1 (38
`super().__init__(name)` sites, 13 modules) · A1-core (2 kailash-core MCP
sites + remove `# type: ignore`) · A2 (13 `super().__init__(name,
self._create_workflow())` sites, 9 modules) · A3 (R3+R4 disposition over
A0's enumerated set) · A-S2 (implement the `create_hybrid_rag_workflow`
placeholder). Milestone B: B1..B10 behavioral coverage, value-ordered by the
user's explicitly-named capabilities (ColBERT→Graph→Agentic→Multimodal→
Federated→HyDE→pipelines→query→privacy/safety→generic). Release: R1.

## DECISION — A2 simplified vs analyst's framing

analyst `02-risk-analysis.md` claimed "≥3 distinct WorkflowNode super-call
conventions." `grep -oE 'super\(\).__init__\([^)]*\)'` over all rag proves
EXACTLY 2 forms: `super().__init__(name)` ×38 + `super().__init__(name,
self._create_workflow())` ×13. A2 STEP-1 enumeration is therefore done at
plan time, not deferred — A2 is a single uniform 13-site fix, not a
multi-convention investigation. Plan corrected.

## RISK / institutional lesson — a contested count is resolved by an

## enumerator shard, never another estimate

R4/CLASS4's surface was mischaracterised THREE times across rounds:

1. Round-1 analysis red-team: "`code=f\"\"\"` in 10 Shape-W modules" —
   overcount, wrong pattern.
2. This orchestrator (reconciled-findings + plan draft): `grep code=f\"\"\"`
   = 0 → "blast radius unknown until measured" — UNDERcount; the source form
   is `"code": f"""` (dict-key), not `code=f"""`. Same wrong pattern,
   opposite error. Repeated the imprecision class twice.
3. Plan red-team round-2: "3 confirmed genuine leaks" — closer, but still an
   approximation (privacy.py:221 is likely a benign loop var).

Ground truth (this session, correct pattern + AST): `"code": f"""` = 29
sites/12 modules; AST = 30 code-template f-strings/13 modules; genuine-LEAK
count requires per-site adjudication. **Resolution: Shard A0 — a mechanical
AST enumerator that emits a deterministic LEAK|BENIGN table.** The lesson:
when a quantitative claim is contested across ≥2 review rounds, the correct
disposition is a mechanical-enumerator shard (deterministic, reproducible),
NOT a 4th estimate and NOT a vague "investigate later" bullet. This is the
`verify-resource-existence.md` MUST-2 principle (cite the endpoint/AST, not
the documentation/estimate) applied to an internal count.

## Plan red-team round-2 disposition

Verdict BLOCK (1 CRIT + 2 HIGH) — all dispositioned in `todos/active/
00-plan.md`: CRIT-A (R4 enumerable → A0 added, correct pattern cited);
HIGH-A (A1 exact 38-site/13-module breakdown); HIGH-B (A2 = 1 convention/13
sites/9 modules); MED (16 code modules, `_index.md` row obligation, R1≈39
nuance). Red-team verified SOUND (no change): dependency graph (empirically
simulated A1+A2, ran `_create_workflow()` ×17 — CLASS4 only privacy/B9a, R3
only strategies/B7+optimized/B9c; B1–B6/B8/B10 clean), build/wire fusion
argument, all-shard capacity-budget compliance, B9a/b/c split. Convergence:
structural questions settled empirically; remaining surface is low-risk
precision now fixed — human gate is the next checkpoint (not another
red-team round; spiraling past empirically-settled structure is the
perfection-spiral `value-prioritization.md` warns against).
