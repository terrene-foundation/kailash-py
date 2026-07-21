---
id: "AGENTS"
---

# Agent Orchestration Rules

See `.claude/guides/rule-extracts/agents.md` for full evidence, extended examples, post-mortems, recovery-protocol commands, the gate-review table, and CLI-syntax variants.

## Specialist Delegation (MUST)

When working with Kailash frameworks, MUST consult the relevant specialist (**dataflow** / **nexus** / **kaizen** / **mcp** / **mcp-platform** / **pact** / **ml** / **align**-specialist). The work-domain → specialist binding is `rules/framework-first.md`'s domain table.

**Why:** Specialists encode hard-won patterns generalist agents miss, preventing subtle API misuse.

## Specs Context in Delegation (MUST)

Every specialist delegation prompt MUST include relevant spec file content from `specs/` (read `specs/_index.md`, select, include inline). Full protocol: `rules/specs-authority.md` MUST Rule 7.

**Why:** Specialists without domain context produce technically correct but intent-misaligned output (e.g. schemas missing tenant_id).

## Analysis Chain (Complex Features)

1. **analyst** → Identify failure points
2. **analyst** → Break down requirements
3. **`decide-framework` skill** → Choose approach
4. Then appropriate specialist

## Parallel Execution

Launch independent operations in parallel via the CLI's delegation primitive, wait for all, aggregate. MUST NOT run sequentially when parallel is possible — the always-on form of the § Triad clause below (under time-pressure framings, parallelization IS the throughput response — `rules/time-pressure-discipline.md`).

### MUST: The Default Execution Mode Is The Triad — Parallelize + /autonomize + /redteam-to-convergence

**The default execution mode for every actionable input is the TRIAD, each DEFAULT-ON (not only under `/autonomize`, not serial/inline):** (1) **parallelize** — decompose onto the parallel primitive wherever the input has **≥2 independent sub-parts OR a multi-stage shape**; (2) **/autonomize** — execute autonomously under the permission envelope (`commands/autonomize.md`); (3) **/redteam-to-convergence** — adversarially verify every substantive change to 2 consecutive clean rounds before "done" (reinforces § Quality Gates + § Holistic Post-Multi-Wave Redteam + `rules/self-referential-codify.md` Rule 1). Drops to serial/inline ONLY for a genuinely-atomic single-item task OR a factual/confirmation/recommendation reply. Executing a decomposable input inline-serially, or idling while independent work is dispatchable, is BLOCKED. The triad FILLS the default posture, NEVER overrides a gate — BOUNDED by the same gates as `rules/wave-loop.md` MUST-6; `/autonomize` is self-bounding. **DO/DO-NOT, full BLOCKED corpus, bounding-gate enumeration, Why: `skills/30-claude-code-patterns/parallel-dispatch-default.md`; CLI dispatch syntax → the `examples` slot.**

### MUST: Parallel Brief-Claim Verification When Issue Count ≥ 3

When `/analyze` runs against a brief covering ≥ 3 distinct issues, the orchestrator MUST launch parallel deep-dive verification agents — one per claim cluster — to independently re-grep / re-read every factual claim; inaccuracies recorded in the workspace journal AND the plan's "Brief corrections" section AS THE GATE before `/todos`. Single-agent analysis on a ≥3-issue brief is BLOCKED. BLOCKED corpus + Why: `skills/30-claude-code-patterns/parallel-dispatch-default.md` § 2. (Example 1 = dispatch syntax.)

## Quality Gates (MUST — Gate-Level Review)

Reviews happen at COC phase boundaries, not per-edit. Skip only when explicitly told to. **MUST gates** are `/implement` and `/release`; reviewer + security-reviewer (and gold-standards-validator at `/release`) run as parallel background agents. RECOMMENDED gates: `/analyze`, `/todos`, `/redteam`, `/codify`, post-merge. Full gate table: guide.

**Why:** Skipped gate reviews let gaps propagate downstream where they are far more expensive to fix. (Example 2 = background-dispatch pattern.)

**BLOCKED responses when skipping MUST gates:** full corpus in guide § "Quality Gates — BLOCKED responses".

### MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep

Every gate-level reviewer prompt MUST include explicit mechanical sweeps that verify ABSOLUTE state (not only the diff) — LLM-judgment review catches what's wrong with new code; sweeps catch what's missing from OLD code the spec also touched. (Example 3 = mechanical-sweep prompt.)

**BLOCKED rationalizations:** guide § "Reviewer Prompts … — BLOCKED rationalizations".

**Why:** Reviewers are constrained by the diff; the `orphan-detection.md` §1 failure mode is invisible at diff-level. A 4-second `grep -c` catches what LLM judgment misses.

### MUST: Holistic Post-Multi-Wave Redteam Before Plan Close

A plan shipped across ≥3 sharded waves MUST run ONE holistic redteam round across ALL merged shards on main — ≥3 parallel reviewers (reviewer + security-reviewer + closure-parity verifier) scoped to the union of merged PRs, not the latest shard's diff — before the plan is declared converged.

**Why:** Per-shard redteams see only their own diff; cross-shard invariant breaks are invisible to each. Evidence + BLOCKED corpus + wiring: guide.

### MUST: Redteam Reviewer Dispatch — Errored/Empty Is Zero Evidence, Never A Clean Round

A `/redteam` round dispatches reviewers in PARALLEL; a throttled fan-out can return errored/empty, reading as "0 findings" → false convergence. **(1) EVIDENCE GATE** — every dispatched reviewer MUST return a ran/evidence signal; an errored/empty/timed-out return is ZERO evidence (`rules/evidence-first-claims.md` MUST-3), MUST be re-run, MUST NOT count clean; convergence is claimable ONLY when EVERY agent genuinely ran. **(2) CONCURRENCY BACK-OFF** — on a throttle signal, reduce concurrency (`rules/worktree-isolation.md` Rule 4) and re-run the throttled reviewers. Complements parallel-by-default, does not override it. DO/DO-NOT + BLOCKED corpus + Wiring + Why: `skills/30-claude-code-patterns/redteam-dispatch-evidence-gate.md`.

## Zero-Tolerance

Pre-existing failures MUST be fixed (`rules/zero-tolerance.md` Rule 1). No workarounds for SDK bugs — deep-dive and fix directly (Rule 4).

**Why:** Workarounds create parallel implementations that diverge from the SDK.

## MUST: Verify Specialist Tool Inventory Before Implementation Delegation

When delegating IMPLEMENTATION work (file edits, commits, build/test invocation, version bumps), the orchestrator MUST select a specialist whose declared tool set includes `Edit` AND `Bash`. Read-only specialists (`security-reviewer`, `analyst`, `reviewer`, `gold-standards-validator`, `value-auditor`) MUST NOT be delegated implementation tasks. Tool-inventory table: guide.

**BLOCKED rationalizations:** guide § "Verify Specialist Tool Inventory … — BLOCKED rationalizations".

**Why:** Read-only specialists halt mid-instruction at file-edit boundaries; pre-launch tool-inventory verify is O(1), re-launch is O(N) on shard size.

**Read-only reviewer materialization (INCREMENTAL):** `security-reviewer` is read-only (no `Bash`) → materialize the diff/changed files to a scratchpad path and name it in the prompt, so it reviews the change instead of halting for context it cannot fetch.

## MUST: Audit/Closure-Parity Verification Specialist Has Bash + Read

When delegating a /redteam round including **closure-parity verification** (mapping prior-wave findings to delivered code via `gh pr view`, `pytest --collect-only`, `grep`, `ast.parse()`), the orchestrator MUST select a specialist with `Bash` AND `Read`. Read-only analyst MUST NOT be assigned — its tool set silently FORWARDS verification rows the next round must redo. Extends the tool-inventory MUST above from IMPLEMENTATION to AUDIT delegation. Examples 4+5 (dispatch + delegation-time scan), the BLOCKED corpus, the delegation-time detection signals, and the multi-incident Origin live in `.claude/skills/30-claude-code-patterns/closure-parity-specialist-discipline.md`.

**Why:** Tool-inventory mismatch costs one full audit round; pre-launch verify is O(1), re-launch O(N) on row count.

## MUST: Worktree Orchestration

Parallel/compiling agents MUST run isolated per `skills/30-claude-code-patterns/worktree-orchestration.md` (Rules 1–10 — each a full MUST): isolate compiling agents + any shared-source editor (concurrent readers read committed HEAD via `git show HEAD:<path>`); relative paths in prompts; commit per milestone + verify ≥1 commit; verify deliverables after exit; recover orphan writes onto `recovery/<branch>`; one version owner per sub-package; binding-scoped shard PRs. The skill carries each rule's evidence, prompt templates, DO/DO-NOT, BLOCKED corpus, and Wiring.

**Why:** Each sub-rule converts a silent parallel-work loss (lock serialization, phantom reads, checkout drift, auto-cleanup loss, truncated writes, version clobber, shard conflicts) into clean isolation or a loud refusal.

## MUST NOT

- **Framework work without specialist** — misuse violates invariants (pool sharing, session lifecycle, trust boundaries).
- **Sequential when parallel is possible** — wastes the autonomous execution multiplier.
- **Raw SQL / custom API / custom agents / custom governance** — see `rules/framework-first.md` and guide for per-framework rationale.

## Trust Posture Wiring

Applies to the **§ Triad** clause ONLY (added 2026-07-18, `journal/0543`); ships canonical-8-field-compliant. Pre-existing grandfathered sections of this baseline rule stay exempt until each is itself `/codify`-touched (precedent: `security.md` § Enforcement-Surface Parity + `git.md` § CI-check/merge).

- **Severity:** `halt-and-report` at `/codify` + `/redteam` gate-review (confirm a decomposable input went onto a parallel wave + substantive changes redteamed to convergence, not self-attested); `advisory` at the hook layer per `rules/hook-output-discipline.md` MUST-2 (session-history judgment).
- **Grace period:** 7 days (2026-07-18 → 2026-07-25).
- **Cumulative posture impact:** same-class violations (decomposable input run inline-serially; a change called "done" without redteam-to-convergence) route to `rules/trust-posture.md` MUST-4 cumulative math (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** GENERIC `regression_within_grace` trigger per `rules/trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated key; named deviation from key-per-clause per Rule 8 (same disposition as `wave-loop.md` MUST-6/7).
- **Receipt requirement:** SessionStart soft-gate `[ack: agents]` IFF `posture.json::pending_verification` includes `agents`.
- **Detection mechanism:** Phase 1 (manual) — cc-architect / reviewer inspect the transcript for a parallel-wave dispatch + convergence receipt. Phase 2 (deferred) — advisory Stop detector + fixtures `.claude/audit-fixtures/wave-loop/orchestration-hygiene/` (shared with `wave-loop.md` MUST-6/7) per `rules/cc-artifacts.md` Rule 9.
- **Violation scope:** the § Triad clause ONLY; grandfathered sections exempt until `/codify`-touched.
- **Origin:** `journal/0543` (co-owner-directed); see § Origin below.

Origin: sessions 2026-04-19/20/27 (worktree drift, parallel-release PRs #552/#553, W6 closure-parity); slot-partitioned 2026-05-14 (#200); F20 extraction 2026-05-22 (journal/0143); prose trim 2026-06-11 (Gate-1 paired extraction); worktree-cluster extraction to skill Rules 1–10 + Examples 6–10 retired 2026-06-12 (#491, journal/0271); triad default-execution-mode clause + paired extraction to `parallel-dispatch-default.md` 2026-07-18 (co-owner-directed origination, `journal/0543`). Full evidence in guide.

## Examples (CLI-specific delegation syntax)

The MUST clauses in the neutral-body section reference numbered examples by their inline "(Example N = …)" descriptors. The WORKED examples (Examples 1–5) — the concrete CC `Agent(subagent_type=…)` delegation code for each clause — live in `.claude/skills/30-claude-code-patterns/specialist-delegation-syntax.md`. That skill also carries the Codex (`bin/coc` inline-cat injection) and Gemini (`@specialist`) mappings. The examples are reference material loaded on-demand when delegating; the MUST clauses above are the CLI-neutral contract.
