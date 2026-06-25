---
priority: 0
scope: baseline
---

# Agent Orchestration Rules

See `.claude/guides/rule-extracts/agents.md` for full evidence, extended examples, post-mortems, recovery-protocol commands, the gate-review table, and CLI-syntax variants.

<!-- slot:neutral-body -->

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

When multiple independent operations are needed, launch agents in parallel via the CLI's delegation primitive, wait for all, aggregate results. MUST NOT run sequentially when parallel is possible.

**Why:** Sequential execution of independent operations wastes the autonomous execution multiplier, turning a 1-session task into a multi-session bottleneck. (Under time-pressure framings, parallelization IS the throughput response — `rules/time-pressure-discipline.md`.)

### MUST: Decompose Onto The Parallel Primitive By Default When The Work Earns It

When the work surface is **≥3 independent items** OR has a **multi-stage shape**, the orchestrator MUST decompose onto the runtime's parallel orchestration primitive by DEFAULT — not only under `/autonomize`. A genuinely serial single-item task MUST stay serial. Governance per `rules/governed-throughput.md`; throttle-aware per `rules/worktree-isolation.md` Rule 4.

```text
# DO — 3 independent shards → one parallel wave
# DO NOT — 1 serial rewrite → stay serial
```

**BLOCKED rationalizations:** "parallel-by-default needs `/autonomize`" / "serial is simpler, I'll decompose later" / "the ≥3-item trigger is my call each session".

**Why:** Parallel decomposition is the baseline throughput response, not a per-session opt-in; the serial-single-item gate prevents over-decomposing sequential work.

### MUST: Parallel Brief-Claim Verification When Issue Count ≥ 3

When `/analyze` runs against a brief covering ≥ 3 distinct issues, the orchestrator MUST launch parallel deep-dive verification agents — one per claim cluster — to independently re-grep / re-read every factual claim. Inaccuracies MUST be recorded in the workspace journal AND the plan's "Brief corrections" section AS THE GATE before `/todos`. Single-agent analysis on a ≥3-issue brief is BLOCKED. (Example 1 = CLI-specific dispatch syntax.)

**BLOCKED rationalizations:**

- "The brief was authored by the user, it must be accurate"
- "Sequential single-agent analysis catches inaccuracies anyway"
- "Three parallel agents triple the cost for the same conclusion"
- "I'll spot-check a couple of claims, that's good enough"
- "Brief verification is /redteam's job, not /analyze's"
- "The brief's claims are 'mostly correct', the rounding errors don't change the plan"
- "If a claim turns out wrong, /todos can correct it"

**Why:** Briefs reflect the author's mental model, which decays as code evolves; single-agent analysis cannot resist the brief's framing without independent reading. Parallel deep-dive verification is the structural defense — N agents, N claim-clusters, one wall-clock unit.

## Quality Gates (MUST — Gate-Level Review)

Reviews happen at COC phase boundaries, not per-edit. Skip only when explicitly told to. **MUST gates** are `/implement` and `/release`; reviewer + security-reviewer (and gold-standards-validator at `/release`) run as parallel background agents. RECOMMENDED gates: `/analyze`, `/todos`, `/redteam`, `/codify`, post-merge. Full gate table: guide.

**Why:** Skipped gate reviews let gaps propagate downstream where they are far more expensive to fix. (Example 2 = background-dispatch pattern.)

**BLOCKED responses when skipping MUST gates:** "Skipping review to save time" / "Reviews will happen in a follow-up session" / "The changes are straightforward, no review needed" / "Already reviewed informally during implementation".

### MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep

Every gate-level reviewer prompt MUST include explicit mechanical sweeps that verify ABSOLUTE state (not only the diff) — LLM-judgment review catches what's wrong with new code; sweeps catch what's missing from OLD code the spec also touched. (Example 3 = mechanical-sweep prompt.)

**BLOCKED rationalizations:** "The reviewer is smart enough to spot orphans" / "Mechanical sweeps are /redteam's job" / "Adding sweeps is repetitive".

**Why:** Reviewers are constrained by the diff; the `orphan-detection.md` §1 failure mode is invisible at diff-level. A 4-second `grep -c` catches what LLM judgment misses.

### MUST: Holistic Post-Multi-Wave Redteam Before Plan Close

A plan shipped across ≥3 sharded waves MUST run ONE holistic redteam round across ALL merged shards on main — ≥3 parallel reviewers (reviewer + security-reviewer + closure-parity verifier) scoped to the union of merged PRs, not the latest shard's diff — before the plan is declared converged.

**Why:** Per-shard redteams see only their own diff; cross-shard invariant breaks are invisible to each. Evidence + BLOCKED corpus + wiring: guide.

### MUST: Redteam Reviewer Dispatch — Errored/Empty Is Zero Evidence, Never A Clean Round

A `/redteam` round dispatches reviewers in PARALLEL; rate-limiting can throttle the fan-out so an agent returns errored/empty, reading as "0 findings" → false convergence. Two axes: **(1) EVIDENCE GATE** — every dispatched reviewer MUST return a ran/evidence signal; an errored/empty/timed-out return is ZERO evidence (per `rules/evidence-first-claims.md` MUST-3), MUST be re-run, and MUST NOT count clean; convergence is claimable ONLY when EVERY agent genuinely ran. **(2) CONCURRENCY BACK-OFF** — on a throttle signal, reduce dispatch concurrency (per `rules/worktree-isolation.md` Rule 4's adaptive model) and re-run the throttled reviewers. COMPLEMENTS parallel-by-default; does NOT override it. DO/DO-NOT + BLOCKED corpus + Wiring: `skills/30-claude-code-patterns/redteam-dispatch-evidence-gate.md`.

**Why:** An errored agent and a genuinely-clean agent are indistinguishable in a "0 findings" tally yet opposite in meaning; counting the errored return as clean ships an un-reviewed shard under a converged banner.

## Zero-Tolerance

Pre-existing failures MUST be fixed (`rules/zero-tolerance.md` Rule 1). No workarounds for SDK bugs — deep-dive and fix directly (Rule 4).

**Why:** Workarounds create parallel implementations that diverge from the SDK.

## MUST: Verify Specialist Tool Inventory Before Implementation Delegation

When delegating IMPLEMENTATION work (file edits, commits, build/test invocation, version bumps), the orchestrator MUST select a specialist whose declared tool set includes `Edit` AND `Bash`. Read-only specialists (`security-reviewer`, `analyst`, `reviewer`, `gold-standards-validator`, `value-auditor`) MUST NOT be delegated implementation tasks. Tool-inventory table: guide.

**BLOCKED rationalizations:** "security-reviewer is the security domain, so security-relevant edits go there" / "The agent will figure out its tool limitations" / "I'll re-launch with a different specialist if it halts" / "Read-only review IS implementation when the diff is trivial" / "The agent has Write — that's enough for code edits".

**Why:** Read-only specialists halt mid-instruction at file-edit boundaries; pre-launch tool-inventory verify is O(1), re-launch is O(N) on shard size.

## MUST: Audit/Closure-Parity Verification Specialist Has Bash + Read

When delegating a /redteam round including **closure-parity verification** (mapping prior-wave findings to delivered code via `gh pr view`, `pytest --collect-only`, `grep`, `ast.parse()`), the orchestrator MUST select a specialist with `Bash` AND `Read`. Read-only analyst MUST NOT be assigned — its tool set silently FORWARDS verification rows the next round must redo. Extends the tool-inventory MUST above from IMPLEMENTATION to AUDIT delegation. Examples 4+5 (dispatch + delegation-time scan), the BLOCKED corpus, the delegation-time detection signals, and the multi-incident Origin live in `.claude/skills/30-claude-code-patterns/closure-parity-specialist-discipline.md`.

**Why:** Tool-inventory mismatch costs one full audit round; pre-launch verify is O(1), re-launch O(N) on row count.

## MUST: Worktree Orchestration

Parallel/compiling agents MUST run isolated per `skills/30-claude-code-patterns/worktree-orchestration.md` (Rules 1–10 — each a full MUST). The 10 sub-rules: isolate compiling agents + ANY shared-source editor (concurrent readers read committed HEAD via `git show HEAD:<path>`, never the working tree); relative paths only in prompts; commit per milestone + verify ≥1 commit; verify deliverables exist after exit; recover orphan writes onto `recovery/<branch>`; one version owner per sub-package; binding-scoped shard PRs touch only their own package. The depth-file carries each rule's failure-mode evidence, prompt templates, DO/DO-NOT blocks, BLOCKED-rationalization corpus, and Trust Posture Wiring.

**Why:** Each sub-rule converts a silent parallel-work loss (lock serialization, phantom reads, checkout drift, auto-cleanup loss, truncated writes, version clobber, shard conflicts) into clean isolation or a loud refusal.

## MUST NOT

- **Framework work without specialist** — misuse violates invariants (pool sharing, session lifecycle, trust boundaries).
- **Sequential when parallel is possible** — wastes the autonomous execution multiplier.
- **Raw SQL / custom API / custom agents / custom governance** — see `rules/framework-first.md` and guide for per-framework rationale.

Origin: sessions 2026-04-19/20/27 (worktree drift, parallel-release PRs #552/#553, W6 closure-parity); slot-partitioned 2026-05-14 (#200); F20 extraction 2026-05-22 (journal/0143); prose trim 2026-06-11 (Gate-1 paired extraction); worktree-cluster extraction to skill Rules 1–10 + Examples 6–10 retired 2026-06-12 (#491, journal/0271). Full evidence in guide.

<!-- /slot:neutral-body -->

<!-- slot:examples -->

## Examples (CLI-specific delegation syntax)

The MUST clauses in the neutral-body section reference numbered examples here. Each example shows the CC `Agent(subagent_type=...)` delegation primitive; the Codex variant of this rule (`.claude/variants/codex/rules/agents.md`) replaces these with `codex_agent(agent=...)` syntax, and the Gemini variant uses `@specialist` invocation.

### Example 1 — Parallel Brief-Claim Verification (≥3-issue brief)

```python
# DO — parallel deep-dive verification for ≥3-issue brief
# (one agent per claim cluster, run concurrently)
Agent(subagent_type="general-purpose", run_in_background=True, prompt="""
  Verify brief claim #1: 'ExperimentTracker creates _kml_model_versions'.
  Re-grep the source tree; cite file:line. Report TRUE / FALSE / UNCLEAR.""")
Agent(subagent_type="general-purpose", run_in_background=True, prompt="""
  Verify brief claim #2: 'InferenceServer at engines/inference_server.py'.
  Re-grep + re-read the cited path. Report TRUE / FALSE / UNCLEAR.""")
Agent(subagent_type="general-purpose", run_in_background=True, prompt="""
  Verify brief claim #3: '1.1.x kwargs silently dropped in 1.5.x'.
  Re-read the 1.5.x signature; check raise vs silent-drop. Report.""")
# Wait for all three; reconcile findings; record corrections in journal +
# architecture plan BEFORE /todos.

# DO NOT — single-agent analysis on a ≥3-issue brief
Agent(subagent_type="analyst", prompt="Analyze the brief and produce architecture plan.")
# (the analyst inherits whatever framing the brief asserts; brief inaccuracies
# propagate into the plan, the plan into /todos, and three sessions later
# the workstream is solving the wrong problem.)
```

### Example 2 — Background Reviewer Dispatch (Quality Gates)

```
# Background agent pattern for MUST gates — review costs near-zero parent context
Agent({subagent_type: "reviewer", run_in_background: true, prompt: "Review all changes since last gate..."})
Agent({subagent_type: "security-reviewer", run_in_background: true, prompt: "Security audit all changes..."})
```

### Example 3 — Mechanical Sweep in Reviewer Prompt

```python
# DO — reviewer prompt enumerates mechanical sweeps
Agent(subagent_type="reviewer", prompt="""
Mechanical sweeps (run BEFORE LLM judgment):
1. Parity grep (`grep -c`) on critical call-site patterns
2. `pytest --collect-only -q` exit 0 across all test dirs
3. Every public symbol in __all__ added by this PR has an eager import
""")

# DO NOT — reviewer prompt only includes diff context
Agent(subagent_type="reviewer", prompt="Review the diff between main and feat/X.")
```

### Example 4 — Closure-Parity Specialist Dispatch (Bash+Read required)

```python
# DO — pact-specialist or general-purpose for Round-2+ closure-parity verification
Agent(subagent_type="pact-specialist", prompt="""
Verify W5→W6 closure parity. Run gh pr view, gh pr diff, grep, pytest --collect-only,
ast.parse() for __all__ enumeration. Convert FORWARDED rows to VERIFIED with command output.""")

# DO NOT — analyst (Read/Grep/Glob only) — cannot run gh / pytest / ast.parse()
Agent(subagent_type="analyst", prompt="Verify W5→W6 closure parity...")
```

### Example 5 — Delegation-Time Closure-Parity Scan

```python
# DO — orchestrator detects closure-parity markers in draft prompt, picks Bash+Read specialist
draft_prompt = "Verify W5→W6 closure parity. Run gh pr view, ast.parse() for __all__..."
# scan: contains "closure parity" + "gh pr view" + "ast.parse(" → MUST use Bash+Read
Agent(subagent_type="pact-specialist", prompt=draft_prompt)

# DO NOT — orchestrator drafts a closure-parity prompt and delegates to read-only analyst
draft_prompt = "Verify W5→W6 closure parity. Run gh pr view, ast.parse() for __all__..."
Agent(subagent_type="analyst", prompt=draft_prompt)
# (analyst lacks Bash; will FORWARD the gh-pr-view rows; round burned)
```

<!-- /slot:examples -->
