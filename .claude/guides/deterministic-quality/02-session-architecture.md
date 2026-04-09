# Session Architecture — What Makes a Session "Sharp"

The layered loading model that produces high-throughput, zero-drop sessions. Distilled from first-hand observation of a 12-hour session that shipped 6 workstreams, 15 commits, 6 GitHub issues, and 2 production deploys with nothing falling on the floor.

**Origin**: journal/0052-DISCOVERY-session-productivity-patterns.md §§1-2, journal/0051-DISCOVERY-cc-rule-loading-model.md

## The Four Layers

A sharp session loads context in four layers, each catching what the previous missed:

```
Layer 1: SESSION-START (always loaded, every turn)
  ├── CLAUDE.md absolute directives (3-6 numbered rules)
  ├── Auto-memory index (MEMORY.md)
  ├── Session notes from previous session (.session-notes)
  └── Universal rules (zero-tolerance, communication, git, security)
  │
  │ Cost: 15-30K tokens. Pays every turn. Must be minimal and high-leverage.
  │
Layer 2: PATH-SCOPED (loaded once on first matching file read, sticky)
  ├── Domain rules (observability, schema-migration, dataflow-pool, etc.)
  ├── Framework rules (infrastructure-sql, tenant-isolation, etc.)
  └── Path patterns: **/*.py, **/migrations/**, **/bulk*.py, etc.
  │
  │ Cost: 0 tokens until triggered; then one-time cost per rule. Scales to 25+ rules.
  │
Layer 3: TOOL-SCOPED (loaded on specialist delegation)
  ├── Specialist agents (dataflow, nexus, kaizen, mcp, pact, ml, align)
  ├── Skills (01-core-sdk through 35-kailash-align)
  └── Loaded when framework-specific work is detected
  │
  │ Cost: Only loaded in the subagent's context, never in the parent's.
  │
Layer 4: GATE-SCOPED (loaded at phase boundaries)
  ├── Review agents (reviewer, security-reviewer, gold-standards-validator)
  ├── Triggered at: end of /implement, before /release, after /redteam
  └── Run as background agents (parent context stays clean)
  │
  │ Cost: Separate context per review agent. Parent sees only the verdict.
```

## Layer 1: Session-Start Context

### CLAUDE.md Absolute Directives

The highest-leverage artifact in any project. 3-6 numbered directives loaded into context on every turn. These frame every decision the agent makes.

**What makes a good directive:**

- Phrased as prohibition + imperative, not guideline
- Applies to EVERY decision in the session, not just some
- References a specific rule file for full detail
- Under 3 lines each; the block fits in 20 lines total

**Canonical structure (from impact-verse, validated in 0052):**

```markdown
## Absolute Directives

### 0. Foundation Independence — No Commercial Coupling

[1-2 lines]. See `rules/independence.md`.

### 1. Framework-First

Never write code from scratch before checking the Kailash frameworks.
See specialist delegation table below.

### 2. .env Is the Single Source of Truth

All API keys and model names from .env. Never hardcode.

### 3. Implement, Don't Document

Discover a gap → fix it. Never write "TODO" or "noted for future."

### 4. Zero Tolerance

Pre-existing failures fixed in-session. Stubs BLOCKED. See `rules/zero-tolerance.md`.

### 5. Recommended Reviews

Code review + security review after changes. See `rules/agents.md`.
```

**Where Directive 3 ("Implement, Don't Document") fired in 0052**: The agent discovered empty columns in production. Without Directive 3, the agent would have documented the gap. With Directive 3, it diagnosed the root cause (VALID_SOURCES mismatch), fixed it, and shipped the fix to production in the same cycle.

**Where Directive 4 ("Zero Tolerance") fired**: progress_product TypeError in startup logs. Classic "pre-existing, not this session" excuse. Directive 4 blocked the excuse, agent diagnosed + fixed + filed upstream issue + added regression test.

### Auto-Memory (MEMORY.md)

User preferences and project facts that persist across sessions. The index file is always loaded; individual memory files are read on demand.

**What belongs in memory:**

- User preferences that prevent friction ("no direct Redis connections from local")
- Infrastructure facts that prevent mistakes ("use Azure OpenAI, not direct OpenAI")
- Project state that prevents re-discovery ("unified schema deployed 2026-03-15")

**What does NOT belong in memory:**

- Code patterns (derive from the code)
- Git history (use `git log`)
- Debugging solutions (the fix is in the code)
- Anything in CLAUDE.md (loads every turn anyway)

**Where memory fired in 0052**: "No keywords/regex for matching" was active from turn 1 — the agent didn't ask whether to use embeddings vs dict lookup when designing the ontology. "Azure OpenAI not direct" prevented LLM call drift. "Never connect directly to Azure PG/Redis" routed the agent through `az containerapp exec`.

### Session Notes (.session-notes)

State + intent from the previous session. NOT a recap of what was done (that's in git). The three things nothing else captures:

1. **Priority ordering** — which files to read first
2. **In-flight state** — what's true right now that isn't committed
3. **Traps** — pitfalls the next session will walk into

**Where session notes fired in 0052**: Previous session left W2-T5 in-flight (cells_written=0 mystery). Session notes told the agent exactly where to resume. Without notes: 20-30 minutes of re-reading commits and logs.

**Hard cap**: 50 lines. Overflow means the content belongs in `todos/active/` or `journal/`.

## Layer 2: Path-Scoped Rules

### Loading Model (Verified in 0051)

| Frontmatter   | When loads                       | Token cost                       |
| ------------- | -------------------------------- | -------------------------------- |
| No `paths:`   | Session start, every session     | Full cost in baseline every turn |
| With `paths:` | Once on first matching file read | One-time cost, only if relevant  |

**Critical findings from 0051 subprocess tests:**

- Paths-scoped rules are ABSENT from session-start prompt (Test F vs A: Δ ≈ 0 tokens)
- No-paths rules add their full size to baseline (Test I vs A: Δ +5482 tokens)
- No per-call accumulation (Test E vs D: 5 same-file reads ≈ 5 different-file reads)
- Wide patterns (`**/*.py`) are fine — one-time cost, not per-call

**Practical ceiling**: 25-30 path-scoped rules with 8-10 in active context at any time. The rest are dormant until triggered.

### When to Path-Scope vs Always-Load

| Always-load (no `paths:`) | Path-scope                                             |
| ------------------------- | ------------------------------------------------------ |
| zero-tolerance.md         | observability.md (`**/*.py`, `**/*.rs`, `**/*.ts`)     |
| communication.md          | schema-migration.md (`**/migrations/**`)               |
| git.md                    | dataflow-pool.md (`**/dataflow/**`)                    |
| security.md               | infrastructure-sql.md (`**/*.sql`)                     |
| independence.md           | tenant-isolation.md (`**/tenant*`, `**/multi_tenant*`) |
| autonomous-execution.md   | cross-sdk-inspection.md (`**/src/**`, `**/tests/**`)   |

**Test**: Does the rule apply to every session regardless of what files are touched? If yes, always-load. If no, path-scope.

## Layer 3: Tool-Scoped (Specialist Delegation)

### When Specialists Fire

Specialists fire for **greenfield feature work** inside one framework: "build me a DataFlow model," "set up a Nexus endpoint," "create a Kaizen agent."

Specialists do NOT fire for **maintenance/ops**: deploy, troubleshoot, observability, cross-framework operations. In the 0052 session (12 hours, 6 workstreams), zero specialist delegations occurred — all work was infrastructure, ontology, or cross-framework.

**Implication**: Don't over-invest in specialist routing for maintenance-heavy projects. Invest in Layer 1 (rules + memory + CLAUDE.md) first. Specialists are insurance for greenfield work, not the primary quality mechanism.

### Context Isolation

The critical second-order effect of specialists (and background agents generally): **the parent's context stays clean.** A background agent can explore 180K tokens of SDK internals, file issues, run tests — and the parent only sees the 200-500 word final report.

This is what makes the 10x autonomous execution multiplier achievable:

- Parent thread: narrow context, fast decisions, user-facing
- Background agents: deep context, thorough exploration, invisible to parent
- Result: parallel depth without context pollution

## Layer 4: Gate-Scoped (Phase Boundary Reviews)

### The Gap (0052 §3.3)

Six commits shipped in the 0052 session without a single review agent running. Gate reviews were phrased as "recommended" in `rules/agents.md`, so under time pressure the agent skipped them.

### The Fix

Upgrade specific gates from "recommended" to MUST, and make reviews cheap by running them as background agents:

| Gate                | After phase  | Reviewers                                               | Mode                 |
| ------------------- | ------------ | ------------------------------------------------------- | -------------------- |
| Implementation done | `/implement` | reviewer + security-reviewer                            | **MUST, background** |
| Before release      | `/release`   | reviewer + security-reviewer + gold-standards-validator | **MUST, blocking**   |
| Red team complete   | `/redteam`   | reviewer                                                | RECOMMENDED          |
| Knowledge captured  | `/codify`    | gold-standards-validator                                | RECOMMENDED          |

**Background reviews cost nearly zero parent context.** The review agent reads the diff, produces findings, and the parent sees a 10-line verdict. The review itself (potentially 50K tokens of analysis) never touches the parent's context.

## The Throughput Multiplier

The 0052 session achieved ~5-8x throughput vs the agent's own "no-artifacts" baseline. The mechanisms, mapped to layers:

| Layer             | Mechanism                                       | Multiplier contribution                         |
| ----------------- | ----------------------------------------------- | ----------------------------------------------- |
| 1 (session-start) | Zero-tolerance blocked deferral                 | 2 workstreams saved from "come back later"      |
| 1 (session-start) | Auto-memory eliminated re-stating preferences   | ~10 turns of friction saved                     |
| 1 (session-start) | Session notes eliminated re-discovery           | ~20 minutes saved at session start              |
| 2 (path-scoped)   | Cross-SDK inspection caught kailash-rs finding  | 1 cross-SDK finding that would have been missed |
| 2 (path-scoped)   | Observability rule upgraded DEBUG→WARN twice    | 2 silent-failure patterns fixed                 |
| 3 (tool-scoped)   | Background agents ran 3 workstreams in parallel | 3-5x throughput from parallelism                |
| 3 (tool-scoped)   | Context isolation kept parent thread clean      | Enabled sustained decision-making               |
| —                 | Rich commit bodies                              | 6 months of future review time saved            |

**Net**: Nothing fell on the floor. No zero-tolerance violation, no deferred WARN, no forgotten cross-SDK check, no silent failure, no "I'll come back to that."

## Ablation Table

What breaks if each layer mechanism is removed:

| Removed                        | What breaks                                                        | Cost                       |
| ------------------------------ | ------------------------------------------------------------------ | -------------------------- |
| Zero-tolerance (Layer 1)       | `cells_failed: 10663` shipped silently, TypeError deferred forever | 2-3 future sessions        |
| Cross-SDK inspection (Layer 2) | kailash-rs#273 update never happens, stub remains undocumented     | Silent semantic divergence |
| Autonomous execution (Layer 1) | 3 background workstreams run serially over 3 sessions              | ~6-8 hours wall-clock slip |
| CLAUDE.md directives (Layer 1) | Model hardcoding, framework misuse, stubs slip in                  | Steady quality drift       |
| Path-scoped loading (Layer 2)  | Either all 25 rules in baseline (crowding) or none (drift)         | Unusable rule system       |
| Auto-memory (Layer 1)          | User restates preferences every session                            | +10 turns friction/session |
| Session notes (Layer 1)        | First 20 minutes wasted re-discovering state                       | 20-minute slip/session     |
| Background agents (Layer 3)    | Serial execution, 1 workstream per session                         | 3-5x throughput loss       |

## Replication Protocol

To replicate a sharp session in a new project:

1. **CLAUDE.md**: Write 3-6 absolute directives. Copy the impact-verse structure.
2. **Rules**: Copy Tier 1 rules verbatim (zero-tolerance, cross-sdk-inspection, autonomous-execution, observability, communication, git). Path-scope domain-specific rules.
3. **Memory**: Seed 3-5 user preference memories and 2-3 project fact memories.
4. **/wrapup**: Run at every session end. Hard cap 50 lines.
5. **Workspace structure**: `workspaces/{project}/01-analysis/NN-*.md` for numbered ADRs.
6. **Background agents**: Use `Agent({run_in_background: true})` for independent workstreams. Trust autonomous-execution.md's framing.
7. **Test**: Remove zero-tolerance.md, run the same workstreams, measure whether "nothing fell on the floor" survives. Prediction: it won't.
