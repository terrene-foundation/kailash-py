# Agent Orchestration Rules

## Specialist Delegation (MUST)

When working with Kailash frameworks, MUST consult the relevant specialist:

- **dataflow-specialist**: Database or DataFlow work
- **nexus-specialist**: API or deployment work
- **kaizen-specialist**: AI agent work
- **mcp-specialist**: MCP integration work
- **mcp-platform-specialist**: FastMCP platform server, contributor plugins, security tiers
- **pact-specialist**: Organizational governance work
- **ml-specialist**: ML lifecycle, feature stores, training, drift monitoring, AutoML
- **align-specialist**: LLM fine-tuning, LoRA adapters, alignment methods, model serving

**Applies when**: Creating workflows, modifying DB models, setting up endpoints, building agents, implementing governance, training ML models, fine-tuning LLMs, configuring MCP platform server.

**Why:** Framework specialists encode hard-won patterns and constraints that generalist agents miss, leading to subtle misuse of DataFlow, Nexus, or Kaizen APIs.

## Specs Context in Delegation (MUST)

Every specialist delegation prompt MUST include relevant spec file content from `specs/`. Read `specs/_index.md`, select relevant files, include them inline. See `rules/specs-authority.md` MUST Rule 7 for the full protocol and examples.

**Why:** Specialists without domain context produce technically correct but intent-misaligned output (e.g., schemas without tenant_id because multi-tenancy wasn't communicated).

## Analysis Chain (Complex Features)

1. **analyst** → Identify failure points
2. **analyst** → Break down requirements
3. **`decide-framework` skill** → Choose approach
4. Then appropriate specialist

**Applies when**: Feature spans multiple files, unclear requirements, multiple valid approaches.

## Parallel Execution

When multiple independent operations are needed, launch agents in parallel using Task tool, wait for all, aggregate results. MUST NOT run sequentially when parallel is possible.

**Why:** Sequential execution of independent operations wastes the autonomous execution multiplier, turning a 1-session task into a multi-session bottleneck.

## Quality Gates (MUST — Gate-Level Review)

Reviews happen at COC phase boundaries, not per-edit. Skip only when explicitly told to.

**Why:** Skipping gate reviews lets analysis gaps, security holes, and naming violations propagate to downstream repos where they are far more expensive to fix. Evidence: 0052-DISCOVERY §3.3 — six commits shipped without a single review because gates were phrased as "recommended." Upgrading to MUST + background agents makes reviews nearly free.

| Gate                             | After Phase          | Enforcement | Review                                                                                                                                                                                                                                                                                         |
| -------------------------------- | -------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Analysis complete                | `/analyze`           | RECOMMENDED | **reviewer**: Are findings complete? Gaps?                                                                                                                                                                                                                                                     |
| Plan approved                    | `/todos`             | RECOMMENDED | **reviewer**: Does plan cover requirements?                                                                                                                                                                                                                                                    |
| Implementation done              | `/implement`         | **MUST**    | **reviewer** + **security-reviewer**: Run as parallel background agents.                                                                                                                                                                                                                       |
| Validation passed                | `/redteam`           | RECOMMENDED | **reviewer**: Are red team findings addressed?                                                                                                                                                                                                                                                 |
| Knowledge captured               | `/codify`            | RECOMMENDED | **gold-standards-validator**: Naming, licensing compliance.                                                                                                                                                                                                                                    |
| Before release                   | `/release`           | **MUST**    | **reviewer** + **security-reviewer** + **gold-standards-validator**: Blocking.                                                                                                                                                                                                                 |
| After release (post-merge audit) | `/release` follow-up | RECOMMENDED | **reviewer** run against the MERGED release commit on main. Catches drift that pre-release review missed (e.g., a kwarg plumbing gap in a sibling call site, a keyspace bump with a missed invalidator). If CRIT/HIGH surfaces, open a patch branch in the SAME session and ship as `x.y.z+1`. |

**BLOCKED responses when skipping MUST gates:**

- "Skipping review to save time"
- "Reviews will happen in a follow-up session"
- "The changes are straightforward, no review needed"
- "Already reviewed informally during implementation"

**Background agent pattern for MUST gates** — the review costs nearly zero parent context:

```
# At end of /implement, spawn reviews in background:
Agent({subagent_type: "reviewer", run_in_background: true, prompt: "Review all changes since last gate..."})
Agent({subagent_type: "security-reviewer", run_in_background: true, prompt: "Security audit all changes..."})
# Parent continues; reviews arrive as notifications
```

### MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep, Not Only Diff Review

Every gate-level reviewer prompt MUST include explicit mechanical sweeps that verify ABSOLUTE state (not only the diff). LLM-judgment review of the diff catches what's wrong with the new code; mechanical sweeps catch what's missing from the OLD code that the spec also touched.

```
# DO — reviewer prompt enumerates mechanical sweeps to run
Agent(subagent_type="reviewer", prompt="""
... diff context ...

Mechanical sweeps (run BEFORE LLM judgment):
1. `grep -c "return TrainingResult(" src/...trainable.py` — must equal
   `grep -cE "device=DeviceReport|device=device_report" src/...trainable.py`
2. `pytest --collect-only -q` exit 0 across all test dirs
3. `pip check` — no new conflicts vs main
4. For every public symbol in __all__ added by this PR — verify
   eager import (per orphan-detection §6)
""")

# DO NOT — reviewer prompt only includes diff context
Agent(subagent_type="reviewer", prompt="Review the diff between main and feat/X.")
# ↑ reviewer reads the diff, judges the new code, never runs the sweep.
#   Orphan in untouched lines (TorchTrainable still missing device=) is invisible.
```

**BLOCKED rationalizations:**

- "The reviewer is smart enough to spot orphans"
- "Mechanical sweeps are /redteam's job, not the reviewer's"
- "The diff IS the reviewer's scope"
- "Adding sweeps to every reviewer prompt is repetitive"

**Why:** Gate reviewers are constrained by the diff they're shown. The orphan failure mode of `rules/orphan-detection.md` §1 is invisible at diff-level — the new entries look complete; the OLD entries that were never updated for the new public surface stay invisible. A 4-second `grep -c` sweep catches what 5 minutes of LLM judgment misses. Without the sweep, the reviewer agent's APPROVE verdict is necessary but not sufficient. Evidence: Session 2026-04-19 — code reviewer APPROVED 0.12.0 with one minor finding (missing test); the subsequent `/redteam` mechanical sweep caught TorchTrainable + LightningTrainable missing `device=DeviceReport` (2 of 7 return sites). The reviewer never ran the parity grep.

Origin: Session 2026-04-19 ML GPU-first Phase 1 codify cycle. See `workspaces/kailash-ml-gpu-stack/journal/0004-RISK-torch-lightning-deviceReport-orphan.md` § "Why it slipped past the round-3 reviewer."

## Zero-Tolerance

Pre-existing failures MUST be fixed (see `rules/zero-tolerance.md` Rule 1). No workarounds for SDK bugs — deep dive and fix directly (Rule 4).

**Why:** Workarounds create parallel implementations that diverge from the SDK, doubling maintenance cost and masking the root bug from being fixed (see `rules/zero-tolerance.md` Rule 4).

## MUST: Worktree Isolation for Compiling Agents

When launching agents that will compile Rust code (build, test, implement), MUST use `isolation: "worktree"` to avoid build directory lock contention.

```
# DO: Independent target/ dirs, compile in parallel
Agent(isolation: "worktree", prompt: "implement feature X...")
Agent(isolation: "worktree", prompt: "implement feature Y...")

# DO NOT: Multiple agents sharing same target/ (serializes on lock)
Agent(prompt: "implement feature X...")
Agent(prompt: "implement feature Y...")  # Blocks waiting for X's build lock
```

**Why:** Cargo uses an exclusive filesystem lock on `target/`. Two cargo processes in the same directory serialize completely, turning parallel agents into sequential execution. Worktrees give each agent its own `target/` directory.

**See `rules/worktree-isolation.md`** for the orchestrator pinning contract, the specialist self-check, and the post-agent file-existence verification. The `isolation: "worktree"` flag is necessary but not sufficient — without the verification layer, agents drift back to the main checkout silently.

## MUST: Worktree Prompts Use Relative Paths Only

When prompting an agent with `isolation: "worktree"`, the orchestrator MUST reference files via paths RELATIVE to the repo root (`packages/kailash-ml/src/...`) — never absolute paths starting with `/Users/` or `/home/`. Agents resolve absolute paths against the filesystem root, which bypasses the worktree's copy and writes to the PARENT checkout instead.

```python
# DO — relative paths resolve to the worktree's cwd
Agent(
    isolation="worktree",
    prompt="Edit packages/kailash-ml/src/kailash_ml/trainable.py at line 370..."
)

# DO NOT — absolute paths bypass worktree isolation
Agent(
    isolation="worktree",
    prompt="Edit /Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/trainable.py..."
)
# ↑ writes land in the MAIN checkout; the worktree stays empty; auto-cleanup
#   deletes the empty worktree; agent's work is either silently on main OR lost.
```

**BLOCKED rationalizations:**

- "Absolute paths are unambiguous"
- "The agent should figure out its own cwd"
- "This worked the one time I tested it"
- "I included 'Repo root: /Users/...' at the top; the agent will use that"

**Why:** `isolation: "worktree"` creates a nested git worktree under `.claude/worktrees/agent-XXXX/`, then runs the agent with cwd set to that worktree. Relative paths resolve correctly; absolute paths point back to the parent checkout the orchestrator is using, silently defeating isolation. Session 2026-04-19 logged: 2 of 3 parallel shards wrote to MAIN before self-correcting (Shard B) or losing work entirely (Shard A's 300+ LOC of sklearn array-API impl was lost when its empty worktree auto-cleaned). Only one self-corrected; the failure mode is not agent-detectable by default.

Origin: Session 2026-04-19 ML GPU-first Phase 1 parallel-shard experiment. See `workspaces/kailash-ml-gpu-stack/journal/0004-RISK-torch-lightning-deviceReport-orphan.md` for the full post-mortem of the write-to-main leak AND the subsequent spec-compliance finding it masked.

## MUST: Worktree Agents Commit Incremental Progress

Every agent launched with `isolation: "worktree"` MUST receive an explicit instruction in its prompt to `git commit` after each major milestone (each file written, each test batch passed), NOT only at completion. The orchestrator MUST then verify the branch has ≥1 commit before declaring the agent's work landed.

```python
# DO — prompt includes incremental commit discipline
Agent(
    isolation="worktree",
    prompt="""...
**Commit discipline (MUST):**
- After each file is complete, run `git add <file> && git commit -m "wip(shard-X): <what>"`.
- Do NOT hold all work in the worktree's index until the final report.
- If you exit without committing (budget exhaustion / crash / interruption),
  the worktree is auto-cleaned and ALL work is lost.
""",
)

# DO NOT — trust that the agent commits at completion
Agent(isolation="worktree", prompt="Implement feature X. Report when done.")
# ↑ agent writes 4 files, hits budget on file 5, emits truncated message,
#   never reaches `git commit`, worktree auto-cleaned — all 5 files lost.
```

**BLOCKED rationalizations:**

- "The agent will commit at the end"
- "Splitting into commits adds overhead"
- "The parent can recover from the worktree after the agent exits"
- "Budget exhaustion is rare"

**Why:** Worktree auto-cleanup silently deletes worktrees with zero commits on their branch. An agent that writes perfect code but truncates mid-message before committing loses 100% of its output. Post-hoc file-existence verification (see § Verify Agent Deliverables) catches orphan files in main but CANNOT recover files that were only in a cleaned-up worktree. Evidence: Session 2026-04-19 — Shard A's agent wrote a complete SklearnTrainable Array-API rewrite, then truncated on "Now let me rewrite fit:" with zero commits; worktree auto-deleted; ~300 LOC of load-bearing work had to be recovered serendipitously from Shard B's scope-creeped worktree. Shard C was rescued by an explicit WIP commit from the orchestrator immediately after notification. The only reliable defense is instructing the agent to commit as it goes.

Origin: Session 2026-04-19 ML GPU-first Phase 1 parallel-shard experiment. Three of three parallel agents truncated at 250-370k tokens; two lost work to auto-cleanup; one (Shard B) self-corrected because its prompt happened to emphasize "commit before exit."

## MUST: Verify Agent Deliverables Exist After Exit

When an agent reports completion of a file-writing task, the parent orchestrator MUST `ls` or `Read` the claimed file before trusting the completion claim. Agent "done" messages are NOT evidence of file creation — budget exhaustion mid-message truncates the final write, and the agent emits "Now let me write X..." with no tool call behind it.

```python
# DO — verify
result = Agent(prompt="Write src/feature.py with ...")
# parent's next step:
Read("/abs/path/src/feature.py")  # raises if missing → retry

# DO NOT — trust the completion message
result = Agent(prompt="Write src/feature.py with ...")
# parent moves on; src/feature.py never existed
```

**BLOCKED rationalizations:**

- "The agent said 'done', that's good enough"
- "Verifying every file slows the orchestrator"
- "Now let me write the file…" (with no subsequent tool call)

**Why:** Session 2026-04-19 logged 2 occurrences (kaizen round 6, ml-specialist round 7) where an agent hit its budget mid-message and reported success with zero files on disk. The `ls` check is O(1) and converts silent no-op into loud retry. See `rules/worktree-isolation.md` MUST Rule 3 for the full protocol.

## MUST NOT

- Framework work without specialist

**Why:** Framework misuse without specialist review produces code that looks correct but violates invariants (e.g., pool sharing, session lifecycle, trust boundaries).

- Sequential when parallel is possible

**Why:** See Parallel Execution above — same rule, expressed as MUST NOT.

- Raw SQL when DataFlow exists

**Why:** Raw SQL bypasses DataFlow's access controls, audit logging, and dialect portability, creating ungoverned database access.

- Custom API when Nexus exists

**Why:** Custom API endpoints miss Nexus's built-in session management, rate limiting, and multi-channel deployment, requiring manual reimplementation.

- Custom agents when Kaizen exists

**Why:** Custom agent implementations bypass Kaizen's signature validation, tool safety, and structured reasoning, producing fragile agents.

- Custom governance when PACT exists

**Why:** Custom governance lacks PACT's D/T/R accountability grammar and verification gradient, making audit compliance unverifiable.
