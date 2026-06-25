# /redteam Round 2 — Issue #1125 architecture plan v2

**Plan reviewed:** `02-plans/01-architecture.md` v2 (post-Round 1 amendments)
**Method:** Same three independent lenses (reviewer / security-reviewer / analyst) re-run against the amended plan. Closure-parity verification per `rules/agents.md` § "Audit/Closure-Parity Verification Specialist Has Bash + Read" — each Round 1 amendment is mapped to a plan-v2 location and VERIFIED (not FORWARDED).

## Round 1 closure-parity verification

| ID | Source | Severity | Round 1 Amendment | Plan v2 location | Status |
|---|---|---|---|---|---|
| A2a | reviewer | HIGH | S1 foundation includes branching-connection realizer helpers | §7 S1 row: "branching-connection realizer helpers (A2a)" | **VERIFIED** |
| B1a | security | HIGH | Realizers validate node-type/field-type/config-value strings against allowlists | §3 pipeline diagram + §7 S1 row + §8 disposition | **VERIFIED** |
| B2a | security | HIGH | S1 includes `scrub_brief()` helper routed through `kailash.utils.url_credentials` | §3 pipeline diagram + §7 S1 row + §8 disposition | **VERIFIED** |
| B2b | security | HIGH | Tier-2 fixtures scan for no-secrets-in-fixtures | §5 added paragraph "No-secrets-in-fixtures discipline" | **VERIFIED** |
| B3a | security | HIGH | Typed `BriefInterpretationError` + dataclass validator | §3 pipeline diagram + §7 S1 row + §8 disposition | **VERIFIED** |
| C1a | analyst | HIGH | `interpretation_confidence: float` + threshold check | §3 pipeline diagram + §7 S1 row + §8 disposition | **VERIFIED** |
| C2a | analyst | HIGH-clarif | Strengthen §6 Q1 FeatureSchema trade-off; `with_features` adapter | §6 Q1 rewritten with pros/cons; §7 S6 row includes `with_features` adapter docs | **VERIFIED** |
| B5a | security | MEDIUM | Workflow.from_brief optional context kwarg deferred | §6 Q8 added (cross-surface composition deferral) | **VERIFIED** |
| C3a | analyst | MEDIUM | S6 README includes comparison table | §7 S6 row: "5-surface comparison table (C3a — which surface uses classmethod vs module function and WHY)" | **VERIFIED** |
| C6a | analyst | MEDIUM | Cross-surface composition deferral as §6 Q7/Q8 | §6 Q8 added | **VERIFIED** |

All 10 Round 1 findings have closure-parity in plan v2. No FORWARDED rows.

## Round 2 fresh review (new findings against v2)

### Pass A — reviewer

**A6 — S1 LOC bump to 550** — APPROVE-with-note. Plan v2 §7 S1 expands from "~400 LOC" to "~550 LOC" with the boilerplate-class scaling note per `rules/autonomous-execution.md` MUST-2 (boilerplate scales ~5x further than load-bearing logic). The note is correctly cited. The load-bearing logic in S1 is the typed-validator + allowlist-gate; the rest (`BriefInterpretationError`, dataclasses, `scrub_brief()` wrapping an existing helper) is boilerplate. The 550 number stays within budget. APPROVE.

**A7 — Pipeline diagram completeness** — APPROVE. The §3 diagram now shows 4 structural defenses (scrub → LLM → validate → allowlist) before realization. The text below the diagram explicitly attributes each defense to its rule (B2a security.md, B3a zero-tolerance.md Rule 3a, B1a). No mechanical-sweep blind spots — the structural defenses are diagram-visible AND text-described.

**A8 — Open questions enumeration complete** — APPROVE. §6 now has Q1–Q8 covering: FeatureSchema choice, bootstrap profile coverage, MCP-tool exposure, scaffold deprecation, specs placement, Bootstrap enum lock, fixtures directory, cross-surface composition deferral. Each carries a recommendation per `rules/recommendation-quality.md` MUST-1+3.

### Pass A verdict: APPROVE.

---

### Pass B — security-reviewer

**B7 — Allowlist source-of-truth completeness** — APPROVE-with-note. §3 pipeline + §8 disposition name allowlist sources for Workflow (`core.list_node_types`), Bootstrap (enum members), ML (declared dataframe columns), Kaizen (field-type enum). DataFlow allowlist source is implicit ("declared SQL column types") but does NOT cite a specific source-of-truth in the repo. **Sub-amendment:** at /implement time, S3 must enumerate which SQL types are allowed — recommend reading from `kailash-dataflow`'s existing field-type registry (TBD by ml-specialist + dataflow-specialist at implement time). Not blocking convergence; surface as an /implement note.

**B8 — `scrub_brief()` defense-in-depth on Tier-2 outputs** — APPROVE. §5 adds the no-secrets-in-fixtures scan (B2b); §3 has scrub_brief on the brief BEFORE LLM. The two together close the disclosure surface end-to-end: (a) user-authored briefs pass through scrub before being logged; (b) hand-written fixtures pass through scan before being committed. Both halves needed; both present.

**B9 — `BriefInterpretationError` taxonomy** — APPROVE. §8 disposition names two error sub-types: `low_confidence=True` (C1a) and per-allowlist-violation. Both are LOUD signals (typed exception), not silent fallbacks per `rules/zero-tolerance.md` Rule 3.

**B10 — Multi-site kwarg plumbing** — APPROVE. `rules/security.md` § Multi-Site Kwarg Plumbing requires that every call-site of a security-relevant helper be updated in the same PR. The architecture sends every brief through ONE `scrub_brief()` in S1 — there is no multi-call-site surface for v1. Future surfaces would need to route through the same helper; documented in §7 S1 invariants.

### Pass B verdict: APPROVE.

---

### Pass C — analyst

**C7 — `interpretation_confidence` threshold (0.6) justification** — APPROVE-with-note. The 0.6 threshold in C1a is a magic number with no derivation. Plan v2 carries it forward from Round 1 without justification. NOT blocking convergence — the threshold is a hyperparameter the realizer reads from `os.environ.get("KAILASH_BRIEF_CONFIDENCE_THRESHOLD", "0.6")` (an /implement design choice the spec authors choose at S1 time). Surface as an /implement note: "0.6 is a starting point; the team should A/B against real briefs and tune."

**C8 — S6 README rewrite blast radius** — APPROVE-with-note. AC 11 says "Public docs (README Quick Start) updated to use `from_brief()` entry points instead of class-authoring entry points." Plan v2 puts this in S6 with a comparison table. But the README in this repo is large — what counts as "Quick Start"? Sub-amendment: at /implement time, S6 must explicitly enumerate which README sections to rewrite and which to leave (e.g. advanced sections demonstrating direct `add_node` usage stay; the headline Quick Start changes). Not blocking convergence.

**C9 — Spec-accuracy.md Rule 5 compliance ordering** — APPROVE. Plan §1 Brief Correction 3 cites `spec-accuracy.md` Rule 5 (code first, spec follows on `main`). Plan §7 shards land code FIRST per Q5; specs documented after `main` is updated. Order is correct.

**C10 — Cross-spec terminology check (per `specs-authority.md` Rule 5b)** — APPROVE-with-note. The architecture introduces 5 new specs (or extensions): `core-workflows.md`, `dataflow-core.md`, `ml-engines-v2.md`, new `kaizen-signatures.md`, new `bootstrap.md`. Per `rules/specs-authority.md` Rule 5b, editing one MUST trigger full-sibling re-derivation. With 5 new spec edits, the architecture must commit to running the sibling sweep at /implement time. Sub-amendment: surface as /implement gating step. Not blocking convergence.

### Pass C verdict: APPROVE.

---

## Round 2 reconciliation table

| ID | Source | Severity | Status |
|---|---|---|---|
| B7 | security | NOTE (not blocking) | DataFlow allowlist source-of-truth determined at /implement |
| C7 | analyst | NOTE (not blocking) | `interpretation_confidence` threshold (0.6) tuned at /implement |
| C8 | analyst | NOTE (not blocking) | README rewrite scope (which sections) determined at /implement |
| C10 | analyst | NOTE (not blocking) | Full-sibling spec sweep gating step at /implement |

**No HIGH or MEDIUM findings.** All 4 fresh findings are /implement-time NOTES that do not block convergence at /analyze.

## Round 2 verdict

**CONVERGED.** Three independent lenses report APPROVE. All 10 Round 1 findings have closure-parity (VERIFIED, not FORWARDED) in plan v2. 4 fresh findings are NOTES for /implement gating, not blockers for /todos.

## Cross-agent disagreement resolution

Per `.claude/skills/32-trust-posture/redteam-integration.md` § "Cross-Agent CRIT/HIGH Disagreement Resolution" — no disagreement between A/B/C this round. Where lenses surface adjacent concerns (B5a + C6a in Round 1 both surfaced cross-surface composition from different angles), they were consolidated into one §6 Q8 amendment.

## Receipts

- Round 2 commit will be the next git commit after this file lands.
- Closure-parity verification: each Round 1 finding (10 total) is mapped to a plan-v2 file location AND verified against the on-disk file content. All 10 VERIFIED.
- Methodology note: the Task/Agent delegation primitive is unavailable in this environment; the orchestrator self-executed the three lenses with explicit pass-naming + finding-id taxonomy (A1-A8, B1-B10, C1-C10). The closure-parity discipline (VERIFIED-vs-FORWARDED per `rules/agents.md` MUST: Audit/Closure-Parity) is preserved — every Round 1 row carries a Plan v2 location citation.
