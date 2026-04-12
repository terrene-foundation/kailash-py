# Autonomous Execution Model

COC executes through **autonomous AI agent systems**, not human teams. All deliberation, analysis, recommendations, and effort estimates MUST assume autonomous execution unless the user explicitly states otherwise.

Human defines the operating envelope. AI executes within it. Human-on-the-Loop, not in-the-loop.

## MUST NOT (Deliberation)

- Estimate effort in "human-days" or "developer-weeks"
- Recommend approaches constrained by "team size" or "resource availability"
- Suggest phased rollouts motivated by "team bandwidth" or "hiring"
- Assume sequential execution where parallel autonomous execution is possible
- Frame trade-offs in terms of "developer experience" or "cognitive load on the team"

**Why:** Human-team framing causes the agent to recommend suboptimal approaches (phasing, sequencing, simplifying) that waste autonomous execution capacity.

## MUST (Deliberation)

- Estimate effort in **autonomous execution cycles** (sessions, not days)
- Recommend the **technically optimal approach** unconstrained by human resource limits
- Default to **maximum parallelization** across agent specializations
- Frame trade-offs in terms of **system complexity**, **validation rigor**, and **institutional knowledge capture**

**Why:** Without autonomous framing, effort estimates inflate 10x and plans are artificially sequenced to fit human-team constraints that don't exist.

## 10x Throughput Multiplier

Autonomous AI execution with mature COC institutional knowledge produces ~10x sustained throughput vs equivalent human team.

| Factor                                               | Multiplier |
| ---------------------------------------------------- | ---------- |
| Parallel agent execution                             | 3-5x       |
| Continuous operation (no fatigue, no context-switch) | 2-3x       |
| Knowledge compounding (zero onboarding)              | 1.5-2x     |
| Validation quality overhead                          | 0.7-0.8x   |
| **Net sustained**                                    | **~10x**   |

**Conversion**: "3-5 human-days" → 1 session. "2-3 weeks with 2 devs" → 2-3 sessions. "33-50 human-days" → 3-5 days parallel.

**Does NOT apply to**: Greenfield domains (first session ~2-3x), novel architecture decisions, external dependencies (API access, approvals), human-authority gates (calendar-bound).

## Structural vs Execution Gates

**Structural (human required):** Plan approval (/todos), release authorization (/release), envelope changes.

**Execution (autonomous convergence):** Analysis quality (/analyze), implementation correctness (/implement), validation rigor (/redteam), knowledge capture (/codify). Human observes but does NOT block.

## Per-Session Capacity Budget

Autonomous capacity is high but not infinite. It degrades along multiple axes simultaneously — LOC is only the proxy. Work that exceeds the budget below MUST be sharded at `/todos` time, before implementation begins.

### 1. Shard When Any Threshold Is Exceeded (MUST)

A single shard (one session, one worktree, one implementation pass) MUST stay within ALL of:

- **≤500 LOC of load-bearing logic** — state machines, schedulers, invariant-holding code. Does NOT count CRUD, DTOs, route registration, or generated boilerplate.
- **≤5–10 simultaneous invariants** the implementation must hold (tenant isolation + audit + redaction + cache key shape + error taxonomy = 5).
- **≤3–4 call-graph hops** of cross-file reasoning.
- **≤15k LOC of relevant surface area** in working context for correctness.
- Describable in **3 sentences or fewer**. If it takes more, the shard is too big.

```markdown
# DO — sharded plan with explicit invariant count

- Shard 1: wire TrustExecutor into express.read (invariants: redact, audit, clearance)
- Shard 2: wire into express.list (same 3 invariants, batch path)
- Shard 3: tenant isolation across both paths (cache key, audit rows, metric labels)

# DO NOT — one mega-todo

- Wire TrustExecutor through express, add audit rows, handle tenant isolation,
  update all 14 call sites, add integration tests, migrate legacy callers
```

**Why:** Beyond the budget the model stops tracking cross-file invariants and pattern-matches instead. Errors on line 400 poison everything after and surface only at `/redteam`. Evidence: the Phase 5.11 orphan (2,407 LOC of trust integration code with zero production call sites) was one conceptual change that exceeded the invariant budget — nothing caught it until the audit.

### 2. Size By Complexity, Not LOC Alone (MUST)

Todo sizing MUST distinguish boilerplate from load-bearing logic. Boilerplate scales ~5× further than logic before sharding triggers, because the model holds a single pattern and stamps it out.

```markdown
# DO — differentiated sizing

- Todo: generate 14 CRUD repositories (~2k LOC boilerplate, single shard)
- Todo: rewrite job scheduler (~400 LOC logic, single shard)
- Todo: migrate scheduler across 6 services (6 shards, one per service)

# DO NOT — uniform LOC cap

- Every todo under 500 LOC — fragments CRUD into meaningless shards AND
  overflows the invariant budget on scheduler work
```

**Why:** Uniform LOC caps fail on both ends. Sizing reflects what's held in attention (invariants, call-graph depth), not what's typed (line count).

### 3. Feedback Loops Multiply Capacity (MUST)

Shards with an executable feedback loop (unit tests, `cargo check`, type checker, integration harness that runs during the session) MAY use up to 3–5× the base budget. Shards without a live loop (spec drafting, config editing, refactors in untested modules) MUST use the base budget.

**Why:** Feedback loops convert "write 2000 LOC then discover it's wrong" into "write 200 LOC, test, continue." The multiplier is real but requires the loop to actually fire during the session — "redteam will catch it later" is not a feedback loop.

## MUST NOT (Sharding)

- Size shards by LOC alone, ignoring invariant count and call-graph depth

**Why:** LOC is a proxy that fragments trivial work and overflows complex work.

- Defer sharding decisions to `/implement`

**Why:** Sharding at `/todos` costs a plan rewrite; sharding mid-`/implement` abandons work in progress and leaves partial state the next session must untangle.

**BLOCKED rationalizations:**

- "The 1M context window handles it"
- "Opus can keep track of more than 5 invariants"
- "We'll see how far we get"
- "Splitting is artificial, it's one conceptual change"
- "The test suite will catch any errors that slip through"
- "It's mostly boilerplate" (when it isn't)

**Why:** Context window is not attention. Model capability claims are not evidence for a specific task. "One conceptual change" is exactly how Phase 5.11 shipped 2,407 LOC of orphaned code.

Origin: Session 2026-04-13 — capacity bands discussion (~500 LOC load-bearing, ~5–10 invariants, ~3–4 call-graph hops, "describe in 3 sentences" heuristic), grounded in the Phase 5.11 orphan failure mode documented in `rules/orphan-detection.md`.
