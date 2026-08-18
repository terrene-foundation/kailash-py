---
id: "AGENTS"
---

# Agent Orchestration Rules

See `.claude/guides/rule-extracts/agents.md` for full evidence, extended examples, post-mortems, recovery-protocol commands, the gate-review table, and CLI-syntax variants.

## Specialist Delegation (MUST)

When working with Kailash frameworks, MUST consult the relevant specialist (**dataflow** / **nexus** / **kaizen** / **mcp** / **mcp-platform** / **pact** / **ml** / **align**-specialist). The work-domain → specialist binding is `rules/framework-first.md`'s domain table.

**Why:** Specialists encode hard-won patterns generalist agents miss, preventing subtle API misuse.

## Specs Context in Delegation (MUST)

Every specialist delegation prompt MUST include relevant spec content from `specs/` (read `specs/_index.md`, select, inline it). Protocol: `rules/specs-authority.md` MUST Rule 7.

**Why:** Specialists without domain context produce technically correct but intent-misaligned output (e.g. schemas missing tenant_id).

## Analysis Chain (Complex Features)

**analyst** (failure points) → **analyst** (requirements breakdown) → **`decide-framework` skill** (approach) → the domain specialist.

## Parallel Execution

Launch independent operations in parallel via the CLI's delegation primitive, wait for all, aggregate. MUST NOT run sequentially when parallel is possible — the always-on form of the § Triad clause below (under time pressure, parallelization IS the throughput response — `rules/time-pressure-discipline.md`).

### MUST: The Default Execution Mode Is The Triad — Parallelize + /autonomize + /redteam-to-convergence

**The default execution mode for every actionable input is the TRIAD, each DEFAULT-ON** (not only under `/autonomize`, not serial/inline): (1) **parallelize** wherever the input has **≥2 independent sub-parts OR a multi-stage shape**; (2) **/autonomize** — execute autonomously under the permission envelope; (3) **/redteam-to-convergence** — adversarially verify every substantive change to 2 consecutive clean rounds before "done". Drops to serial/inline ONLY for a genuinely-atomic single-item task OR a factual/confirmation/recommendation reply. Executing a decomposable input inline-serially, or idling while independent work is dispatchable, is BLOCKED. The triad FILLS the default posture, NEVER overrides a gate. **Bounding gates, DO/DO-NOT, BLOCKED corpus, Why: `skills/30-claude-code-patterns/parallel-dispatch-default.md`; CLI dispatch syntax → the `examples` slot.**

### MUST: Parallel Brief-Claim Verification When Issue Count ≥ 3

When `/analyze` runs against a brief covering ≥ 3 distinct issues, the orchestrator MUST launch parallel deep-dive verification agents — one per claim cluster — to independently re-verify every factual claim, recording inaccuracies in the workspace journal AND the plan's "Brief corrections" section AS THE GATE before `/todos`. Single-agent analysis on a ≥3-issue brief is BLOCKED. Depth: `skills/30-claude-code-patterns/parallel-dispatch-default.md` § 2.

## Quality Gates (MUST — Gate-Level Review)

Reviews happen at COC phase boundaries, not per-edit. Skip only when explicitly told to. **MUST gates** are `/implement` and `/release`; reviewer + security-reviewer (and gold-standards-validator at `/release`) run as parallel background agents. RECOMMENDED gates: `/analyze`, `/todos`, `/redteam`, `/codify`, post-merge. Full gate table: guide.

**Why:** Skipped gate reviews let gaps propagate downstream where they are far more expensive to fix. (Example 2 = background-dispatch pattern.)

**BLOCKED responses when skipping MUST gates:** full corpus in guide § "Quality Gates — BLOCKED responses".

### MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep

Every gate-level reviewer prompt MUST include explicit mechanical sweeps that verify ABSOLUTE state, not only the diff — LLM-judgment review catches what is wrong with new code; sweeps catch what is MISSING from old code the spec also touched. Prompt shape + BLOCKED corpus: guide.

**Why:** Reviewers are constrained by the diff; the `orphan-detection.md` §1 failure mode is invisible at diff-level. A 4-second `grep -c` catches what LLM judgment misses.

### MUST: Holistic Post-Multi-Wave Redteam Before Plan Close

A plan shipped across ≥3 sharded waves MUST run ONE holistic redteam round across ALL merged shards on main — ≥3 parallel reviewers scoped to the union of merged PRs, not the latest shard's diff — before the plan is declared converged.

**Why:** Per-shard redteams see only their own diff; cross-shard invariant breaks are invisible to each. Evidence + BLOCKED corpus + wiring: guide.

### MUST: Redteam Reviewer Dispatch — Errored/Empty Is Zero Evidence, Never A Clean Round

A throttled parallel fan-out returns errored/empty, which reads as "0 findings". **(1) EVIDENCE GATE** — every dispatched reviewer MUST return a ran/evidence signal; an errored, empty or timed-out return is ZERO evidence, MUST be re-run, and MUST NOT count clean. Convergence is claimable ONLY when EVERY agent genuinely ran. **(2) CONCURRENCY BACK-OFF** — on a throttle signal, reduce concurrency and re-run the throttled reviewers. Depth: `skills/30-claude-code-patterns/redteam-dispatch-evidence-gate.md`.

### MUST: Correctness-Review-Clean Is Not Security-Clean

A correctness / closure-parity reviewer returning CLEAN is NOT evidence a change is SECURITY-clean (tested-path correctness ≠ off-path adversarial defeat). A security-critical change (auth, signing, revocation, tenant-isolation, any fail-closed gate or trust boundary) MUST be redteamed by BOTH a correctness reviewer AND an adversarial security-reviewer prompted to REFUTE, both with a genuine ran-signal, before convergence. Counting a CLEAN correctness verdict AS the security round is BLOCKED.

**Why:** The correctness lens is blind to off-tested-path attacks; in #1842-S3 a CLEAN correctness verdict co-occurred with a CRITICAL revocation bypass the SAME-round security-reviewer caught. Depth: `skills/30-claude-code-patterns/redteam-dispatch-evidence-gate.md`.

## Zero-Tolerance

Pre-existing failures MUST be fixed (`rules/zero-tolerance.md` Rule 1); no workarounds for SDK bugs — fix directly (Rule 4), since a workaround creates a parallel implementation that diverges from the SDK.

## MUST: Verify Specialist Tool Inventory Before Implementation Delegation

When delegating IMPLEMENTATION work (file edits, commits, build/test invocation, version bumps), the orchestrator MUST select a specialist whose declared tool set includes `Edit` AND `Bash`; a read-only specialist MUST NOT be given implementation work. Read-only roster, tool-inventory table, materialization workaround, BLOCKED corpus: guide.

**Why:** Read-only specialists halt mid-instruction at file-edit boundaries; pre-launch tool-inventory verify is O(1), re-launch is O(N) on shard size.

## MUST: Audit/Closure-Parity Verification Specialist Has Bash + Read

When delegating a /redteam round including **closure-parity verification**, the orchestrator MUST select a specialist with `Bash` AND `Read`; a read-only analyst silently FORWARDS verification rows the next round must redo. Extends the tool-inventory MUST above from IMPLEMENTATION to AUDIT delegation. Depth: `skills/30-claude-code-patterns/closure-parity-specialist-discipline.md`.

**Why:** Tool-inventory mismatch costs one full audit round; pre-launch verify is O(1), re-launch O(N) on row count.

## MUST: Worktree Orchestration — The ORCHESTRATOR Creates A SIBLING, Before Dispatch

Parallel/compiling agents MUST run isolated per `skills/30-claude-code-patterns/worktree-orchestration.md` (Rules 1–11) and `rules/worktree-isolation.md`. At SPAWN TIME the ORCHESTRATOR creates the worktree — a SIBLING outside the repo (`<repo-parent>/.<repo-slug>-wt/<name>`) — pins its ABSOLUTE path in the prompt, and mandates a STEP-0 assertion comparing RESOLVED `git rev-parse --show-toplevel` to `pwd -P`, refusing on mismatch. Requesting harness-native isolation (the delegation tool's `isolation: "worktree"` parameter) is BLOCKED: it nests under `.claude/worktrees/`, which the nested-worktree guard refuses, and no setting relocates that base. In a SHARED tree restore ONLY from a `cp` backup; `git checkout --`/`git restore` read the INDEX and are BLOCKED.

**Why:** Each sub-rule converts a silent parallel-work loss into isolation or a loud refusal — and the sibling requirement lived only behind globs a spawn decision never matches, so the guard blocked launches with nothing loaded saying what to do.

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
- **Detection mechanism:** Phase 1 (manual) — cc-architect / reviewer inspect the transcript for a parallel-wave dispatch + convergence receipt. Probes `.claude/test-harness/probes/agents.probes.json` — NOT YET AUTHORED, declared in `phase2-deferrals.json::probe_authorship_deferrals`. Phase 2 (deferred) — advisory Stop detector + fixtures `.claude/audit-fixtures/wave-loop/orchestration-hygiene/` (shared with `wave-loop.md` MUST-6/7) per `rules/cc-artifacts.md` Rule 9.
- **Violation scope:** the § Triad clause ONLY; grandfathered sections exempt until `/codify`-touched.
- **Origin:** `journal/0543` (co-owner-directed); see § Origin below.

### Clause-scoped wiring — Correctness-Review-Clean Is Not Security-Clean (added 2026-07-22)

Applies to the **§ Quality Gates → "Correctness-Review-Clean Is Not Security-Clean"** clause ONLY (added 2026-07-22, `/sync-from-build` Wave-1 placement, loom-sweep-waves-2026-07-22); ships canonical-8-field-compliant. Per `trust-posture.md` MUST-8 grandfather cutoff it lands AT/AFTER the MUST-8 SHA; the pre-existing grandfathered sections + the § Triad clause stay on their own wiring above (clause-scoped precedent: `security.md` § Enforcement-Surface Parity + `git.md` § CI-check/merge).

- **Severity:** `halt-and-report` at `/implement` + `/redteam` + `/codify` gate-review (cc-architect / reviewer confirm any security-critical change was redteamed by BOTH a correctness reviewer AND an adversarial security-reviewer, both with genuine ran-signals, before convergence); `advisory` at the hook layer per `rules/hook-output-discipline.md` MUST-2 (whether a dispatched round included an adversarial security lens is a session-history judgment, no structural tool-call signal).
- **Grace period:** 7 days from clause landing (2026-07-22 → 2026-07-29).
- **Cumulative posture impact:** same-class violations (a security-critical change converged on a correctness-only round, or a CLEAN correctness verdict counted as the security round) route to `rules/trust-posture.md` MUST-4 cumulative math (3× same-rule / 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** a same-class violation within the 7-day grace window routes through the GENERIC `regression_within_grace` emergency trigger per `rules/trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated per-clause trigger key (a two-lens-dispatch property is review-layer + session-history judgment; it does not reuse the § Triad clause's key). Named deviation from the canonical key-per-clause shape, recorded here per `rules/trust-posture.md` Rule 8 — the same no-dedicated-key disposition the § Triad clause + `security.md` § Enforcement-Surface Parity took.
- **Receipt requirement:** SessionStart soft-gate `[ack: agents]` IFF `posture.json::pending_verification` includes `agents` (shared rule_id with the § Triad wiring).
- **Detection mechanism:** Phase 1 (manual, gate-review) — cc-architect / reviewer inspect any session redteaming a security-critical change (auth / crypto-signing / revocation / tenant-isolation / fail-closed-gate / trust-boundary) and confirm the round dispatched BOTH a correctness reviewer AND an adversarial security-reviewer prompted to refute, both returning a genuine ran-signal (§ Redteam Reviewer Dispatch). Phase 2 (deferred) — advisory Stop detector + audit fixtures at `.claude/audit-fixtures/correctness-not-security-clean/` per `rules/cc-artifacts.md` Rule 9.
- **Violation scope:** the § "Correctness-Review-Clean Is Not Security-Clean" clause ONLY (clause-scoped); the § Triad clause + grandfathered sections stay on their own wiring.
- **Origin:** kailash-py #1842-S3 (kailash 2.58.0 signed revocation ledger — correctness CLEAN, adversarial security caught a CRITICAL bypass). Landed at loom via `/sync-from-build` Wave-1 placement (loom-sweep-waves-2026-07-22).

### Clause-scoped wiring — Wave Worktrees Are Orchestrator-Created Siblings (added 2026-08-11)

Applies to the **§ Worktree Orchestration** spawn-time sentences ONLY (orchestrator-creates-the-sibling; harness-native `isolation: "worktree"` BLOCKED; absolute-path pin; STEP-0 resolved-toplevel assertion), added 2026-08-11 via `/sync-from-build` Gate-1 placement; ships canonical-8-field-compliant per `trust-posture.md` MUST-8. The § Triad and Correctness-vs-Security blocks above, and the grandfathered sections, stay on their own wiring.

- **Severity:** `halt-and-report` at gate-review (cc-architect at `/codify` + reviewer at `/implement` confirm every parallel dispatch in the session named an orchestrator-created SIBLING path, absolute, with a STEP-0 assertion in the prompt, and that no dispatch requested harness-native worktree isolation); `block` at the hook layer is ALREADY carried structurally by the nested-worktree guard on the PreToolUse matcher — that guard refuses the nested spawn outright, and this clause exists because the refusal previously arrived with no loaded instruction telling the orchestrator what to do instead.
- **Grace period:** 7 days from clause landing (2026-08-11 → 2026-08-18).
- **Cumulative posture impact:** same-class violations (a dispatch requesting harness-native worktree isolation; a prompt pinning a relative path or a path rooted at the orchestrator's own checkout; a prompt omitting the STEP-0 resolved-toplevel assertion) contribute to `trust-posture.md` MUST-4 cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** DELEGATED — a same-class violation routes to `worktree-isolation.md` Rule 7's existing wiring, which already OWNS the nested-placement violation class; no second trigger is minted here, and the GENERIC `regression_within_grace` trigger per `trust-posture.md` MUST-4 covers the ABSOLUTE-path-pin and STEP-0 halves that Rule 7's "session/operator sibling-placement ONLY" scope does not reach. Named deviation from the canonical key-per-clause shape, recorded here per `trust-posture.md` Rule 8 — same disposition as the § Triad clause.
- **Receipt requirement:** SessionStart soft-gate `[ack: agents]` IFF `posture.json::pending_verification` includes the `agents` rule_id (shared rule_id; one ack covers every clause in this file).
- **Detection mechanism:** structural + review. Structural: the nested-worktree guard registered on the PreToolUse matcher refuses a nested spawn at tool-call time (this clause adds no new detector — it supplies the instruction the existing refusal lacked). Review: cc-architect at `/codify` + reviewer at `/implement` inspect any session that dispatched parallel agents and confirm each prompt carried an absolute sibling path plus the STEP-0 assertion. **No probe suite ships for this clause** — `agents.md` has no `eval-manifest.json` entry and no probe set; stated explicitly rather than naming a phantom path, so the semantic tier is UNCOVERED and is owed at gate-review via `/test-harness-probe`. Phase 2 (deferred) — audit fixtures land WITH any future detector at `.claude/audit-fixtures/wave-loop/orchestration-hygiene/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** the § Worktree Orchestration spawn-time sentences ONLY (clause-scoped); the nested-placement class itself belongs to `worktree-isolation.md` Rule 7.
- **Origin:** 2026-07-28, BUILD stream — a spawn-time REACHABILITY gap. The sibling requirement lived only in `worktree-isolation.md` (priority 10, path-scoped over `.claude/{agents,commands,skills}/**`, `**/*worktree*`, `**/workspaces/**`) and its depth skill; an orchestrator CHOOSING a spawn flag touches none of those globs, so the instruction never loaded at the moment of the decision, while this always-on file carried no prohibition at all. Net effect measured in one session: the nested-worktree guard correctly BLOCKED four parallel spawns and the orchestrator had no loaded instruction telling it what to do instead. Same reachability class as `issue-triage-routing.md`'s own Origin. Two claims the source proposal shipped were FALSIFIED by its own follow-up measurement and are deliberately NOT restated in the clause: that a PreToolUse hook can only refuse a call and never rewrite it (the harness carries an `updatedInput` schema and an implemented fallback path), and that "no configuration avoids the block" (narrowed to the verified claim — no flag, setting or env var RELOCATES the base directory). A reviewer-proposed `cwd`-based remedy was REJECTED as unusable: the delegation tool's exposed input schema strips `cwd`, so an orchestrator cannot pass it. Classified GLOBAL: the contract is CLI-neutral (the ORCHESTRATOR creates the sibling; a harness-native worktree-isolation primitive is BLOCKED); the parameter name is kept literal because spawn-time recognisability is the whole point of the fix.

Origin: sessions 2026-04-19/20/27 (worktree drift, parallel-release PRs #552/#553, W6 closure-parity); slot-partitioned 2026-05-14 (#200); F20 extraction 2026-05-22 (journal/0143); prose trim 2026-06-11 (Gate-1 paired extraction); worktree-cluster extraction to skill Rules 1–10 + Examples 6–10 retired 2026-06-12 (#491, journal/0271); triad default-execution-mode clause + paired extraction to `parallel-dispatch-default.md` 2026-07-18 (co-owner-directed origination, `journal/0543`). Full evidence in guide.

## Examples (CLI-specific delegation syntax)

The MUST clauses in the neutral-body section reference numbered examples by their inline "(Example N = …)" descriptors. The WORKED examples (Examples 1–5) — the concrete CC `Agent(subagent_type=…)` delegation code for each clause — live in `.claude/skills/30-claude-code-patterns/specialist-delegation-syntax.md`. That skill also carries the Codex (`bin/coc` inline-cat injection) and Gemini (`@specialist`) mappings. The examples are reference material loaded on-demand when delegating; the MUST clauses above are the CLI-neutral contract.
