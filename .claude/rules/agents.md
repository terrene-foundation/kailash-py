# Agent Orchestration Rules

See `.claude/guides/rule-extracts/agents.md` for full evidence, extended examples, and post-mortems.

## Specialist Delegation (MUST)

When working with Kailash frameworks, MUST consult the relevant specialist: **dataflow-specialist** (DB/DataFlow), **nexus-specialist** (API/deployment), **kaizen-specialist** (AI agents), **mcp-specialist** (MCP integration), **mcp-platform-specialist** (FastMCP platform), **pact-specialist** (governance), **ml-specialist** (ML lifecycle), **align-specialist** (LLM fine-tuning). See `rules/framework-first.md` for the domain-to-framework binding.

**Why:** Framework specialists encode hard-won patterns and constraints generalist agents miss, leading to subtle misuse of DataFlow, Nexus, or Kaizen APIs.

## Specs Context in Delegation (MUST)

Every specialist delegation prompt MUST include relevant spec file content from `specs/`. Read `specs/_index.md`, select relevant files, include them inline. See `rules/specs-authority.md` MUST Rule 7 for the full protocol.

**Why:** Specialists without domain context produce technically correct but intent-misaligned output (e.g., schemas without tenant_id because multi-tenancy wasn't communicated).

## Analysis Chain (Complex Features)

1. **analyst** → Identify failure points
2. **analyst** → Break down requirements
3. **`decide-framework` skill** → Choose approach
4. Then appropriate specialist

## Parallel Execution

When multiple independent operations are needed, launch agents in parallel via Task tool, wait for all, aggregate results. MUST NOT run sequentially when parallel is possible.

**Why:** Sequential execution of independent operations wastes the autonomous execution multiplier, turning a 1-session task into a multi-session bottleneck.

## Quality Gates (MUST — Gate-Level Review)

Reviews happen at COC phase boundaries, not per-edit. Skip only when explicitly told to.

**Why:** Skipping gate reviews lets analysis gaps, security holes, and naming violations propagate to downstream repos where they are far more expensive to fix.

| Gate                | After Phase  | Enforcement | Review                                                                                                          |
| ------------------- | ------------ | ----------- | --------------------------------------------------------------------------------------------------------------- |
| Analysis complete   | `/analyze`   | RECOMMENDED | **reviewer**: Are findings complete? Gaps?                                                                      |
| Plan approved       | `/todos`     | RECOMMENDED | **reviewer**: Does plan cover requirements?                                                                     |
| Implementation done | `/implement` | **MUST**    | **reviewer** + **security-reviewer**: Parallel background agents.                                               |
| Validation passed   | `/redteam`   | RECOMMENDED | **reviewer**: Are red team findings addressed?                                                                  |
| Knowledge captured  | `/codify`    | RECOMMENDED | **gold-standards-validator**: Naming, licensing compliance.                                                     |
| Before release      | `/release`   | **MUST**    | **reviewer** + **security-reviewer** + **gold-standards-validator**: Blocking.                                  |
| After release       | post-merge   | RECOMMENDED | **reviewer** against MERGED main. Catches drift the pre-release review missed. If CRIT/HIGH, ship as `x.y.z+1`. |

**Background agent pattern for MUST gates** — review costs near-zero parent context:

```
Agent({subagent_type: "reviewer", run_in_background: true, prompt: "Review all changes since last gate..."})
Agent({subagent_type: "security-reviewer", run_in_background: true, prompt: "Security audit all changes..."})
```

**BLOCKED responses when skipping MUST gates:** "Skipping review to save time" / "Reviews will happen in a follow-up session" / "The changes are straightforward, no review needed" / "Already reviewed informally during implementation".

### MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep

Every gate-level reviewer prompt MUST include explicit mechanical sweeps that verify ABSOLUTE state (not only the diff). LLM-judgment review catches what's wrong with new code; mechanical sweeps catch what's missing from OLD code the spec also touched.

```python
# DO — reviewer prompt enumerates mechanical sweeps
Agent(subagent_type="reviewer", prompt="""
... diff context ...
Mechanical sweeps (run BEFORE LLM judgment):
1. Parity grep (`grep -c`) on critical call-site patterns
2. `pytest --collect-only -q` exit 0 across all test dirs
3. Every public symbol in __all__ added by this PR has an eager import
""")

# DO NOT — reviewer prompt only includes diff context
Agent(subagent_type="reviewer", prompt="Review the diff between main and feat/X.")
```

**BLOCKED rationalizations:** "The reviewer is smart enough to spot orphans" / "Mechanical sweeps are /redteam's job" / "Adding sweeps is repetitive".

**Why:** Reviewers are constrained by the diff. The orphan failure mode in `orphan-detection.md` §1 is invisible at diff-level. A 4-second `grep -c` catches what 5 minutes of LLM judgment misses. See guide for full evidence.

Origin: Session 2026-04-19. See `skills/30-claude-code-patterns/worktree-orchestration.md`.

## Zero-Tolerance

Pre-existing failures MUST be fixed (`rules/zero-tolerance.md` Rule 1). No workarounds for SDK bugs — deep-dive and fix directly (Rule 4).

**Why:** Workarounds create parallel implementations that diverge from the SDK, doubling maintenance cost.

## MUST: Worktree Isolation for Compiling Agents

Agents that compile (Rust `cargo`, Python editable installs at scale) MUST use `isolation: "worktree"` to avoid build-directory lock contention.

```
# DO — independent target/ dirs, compile in parallel
Agent(isolation: "worktree", prompt: "implement feature X...")
Agent(isolation: "worktree", prompt: "implement feature Y...")

# DO NOT — multiple agents sharing same target/ (serializes on lock)
Agent(prompt: "implement feature X...")
Agent(prompt: "implement feature Y...")
```

**Why:** Cargo uses an exclusive filesystem lock on `target/`. Worktrees give each agent its own `target/`. See `skills/30-claude-code-patterns/worktree-orchestration.md` for the full 5-layer protocol — `isolation: "worktree"` is necessary but not sufficient.

## MUST: Worktree Prompts Use Relative Paths Only

When prompting an agent with `isolation: "worktree"`, the orchestrator MUST reference files via paths RELATIVE to the repo root — never absolute paths starting with `/Users/` or `/home/`.

```python
# DO — relative paths resolve to the worktree's cwd
Agent(isolation="worktree", prompt="Edit packages/kailash-ml/src/kailash_ml/trainable.py...")

# DO NOT — absolute paths bypass worktree isolation
Agent(isolation="worktree", prompt="Edit /Users/esperie/repos/loom/kailash-py/packages/...")
```

**BLOCKED rationalizations:** "Absolute paths are unambiguous" / "The agent should figure out its own cwd" / "This worked the one time I tested it".

**Why:** `isolation: "worktree"` sets cwd to the worktree; absolute paths point back to the parent checkout, silently defeating isolation. Session 2026-04-19: 2 of 3 parallel shards wrote to MAIN; one lost 300+ LOC when its empty worktree auto-cleaned. See guide + `skills/30-claude-code-patterns/worktree-orchestration.md` § Rule 2 for full post-mortem.

## MUST: Recover Orphan Writes From Zero-Commit Worktree Agents

When an `isolation: "worktree"` agent reports completion but the branch has zero commits AND the worktree has been auto-cleaned, the parent orchestrator MUST inspect the MAIN checkout for orphaned untracked files BEFORE concluding the work was lost. Absolute-path writes from the agent resolve to the MAIN checkout cwd — the files are NOT lost; they are orphaned, uncommitted, and reachable via `git status` on the parent.

```bash
# DO — recovery protocol (detect → recover → PR with recovery/ prefix)
git worktree list | grep <expected-branch>      # empty if cleaned
git log <expected-branch> --oneline | head -5   # zero agent commits confirms truncation
git status --short                              # "??" entries surface the orphans
# → git checkout -b recovery/<original-branch-name> && git add <orphans> && git commit
# → fill missing deliverables (tests, specs, pyproject bumps, CHANGELOG)

# DO NOT — abandon orphans and re-launch the agent
```

**BLOCKED rationalizations:** "The agent said it was done, so the work must be committed somewhere" / "Re-launching is cleaner than recovery" / "If the branch has zero commits, the work is gone" / "The main checkout is clean, nothing to recover" / "recovery/ branches are a workaround; feat/ is more correct".

**Why:** The first three rationalizations lose 1000+ LOC of real work every time an absolute-path agent truncates. The fourth is false because `git status` reveals the orphans. The fifth conflates branch-name aesthetics with provenance traceability — `recovery/` grep surfaces this class of rescue across history; `feat/` does not.

Origin: Session 2026-04-20 Session 3b (issue #567, PR #574 recovered 1129 LOC of `alignment.py`). See guide for full 4-step protocol.

## MUST: Worktree Agents Commit Incremental Progress

Every agent launched with `isolation: "worktree"` MUST receive an explicit instruction in its prompt to `git commit` after each milestone. The orchestrator MUST verify the branch has ≥1 commit before declaring the agent's work landed.

```python
# DO — prompt includes incremental commit discipline
Agent(isolation="worktree", prompt="""...
**Commit discipline (MUST):**
- After each file is complete: `git add <file> && git commit -m "wip(shard-X): <what>"`
- If you exit without committing (budget exhaustion), the worktree auto-cleans and ALL work is lost.
""")

# DO NOT — trust completion commit
Agent(isolation="worktree", prompt="Implement feature X. Report when done.")
```

**BLOCKED rationalizations:** "The agent will commit at the end" / "Splitting adds overhead" / "The parent can recover from the worktree after exit".

**Why:** Worktrees with zero commits are silently deleted. Session 2026-04-19: Shard A wrote 300+ LOC, truncated mid-message, zero commits, work lost. See guide + `skills/30-claude-code-patterns/worktree-orchestration.md` § Rule 3.

## MUST: Verify Agent Deliverables Exist After Exit

When an agent reports completion of a file-writing task, the parent MUST `ls` or `Read` the claimed file before trusting the completion claim.

```python
# DO — verify
result = Agent(prompt="Write src/feature.py with ...")
Read("src/feature.py")  # raises if missing → retry

# DO NOT — trust the completion message (budget-exhaustion truncates writes)
```

**BLOCKED rationalizations:** "The agent said 'done', that's good enough" / "Now let me write the file…" (with no subsequent tool call).

**Why:** Session 2026-04-19 logged 2 occurrences of agents hitting budget mid-message and reporting success with zero files on disk. The `ls` check is O(1) and converts silent no-op into loud retry.

## MUST: Parallel-Worktree Package Ownership Coordination

When launching two or more parallel agents whose worktrees touch the SAME sub-package, the orchestrator MUST designate ONE agent as **version owner** (pyproject.toml + `__init__.py::__version__` + CHANGELOG) AND tell every sibling explicitly: "do NOT edit those files". Integration belongs to the orchestrator.

```python
# DO — explicit ownership in prompts (sibling sees coordination note)
Agent(isolation="worktree", prompt="""... bump package to 0.13.0, CHANGELOG, __version__ ...""")
Agent(isolation="worktree", prompt="""...
COORDINATION NOTE: A parallel agent is bumping this package to 0.13.0.
You MUST NOT edit pyproject.toml / __version__ / CHANGELOG.""")

# DO NOT — both agents bump independently (merge arbitrarily picks one side's CHANGELOG)
```

**BLOCKED rationalizations:** "Both agents are smart enough to see the existing version" / "We'll resolve at merge time" / "Each agent owns a section of the CHANGELOG".

**Why:** Parallel agents see the same base SHA; each independently bumps `version` and writes a top-level CHANGELOG entry. Merge picks one — discarding the other's prose silently. One-sentence exclusion clause prevents O(manual) reconciliation.

Origin: Session 2026-04-20 kailash-ml 0.13.0 + kailash 2.8.10 parallel-release (PRs #552, #553). See guide for full example.

## MUST NOT

- **Framework work without specialist** — misuse violates invariants (pool sharing, session lifecycle, trust boundaries).
- **Sequential when parallel is possible** — wastes the autonomous execution multiplier.
- **Raw SQL / custom API / custom agents / custom governance** — see `rules/framework-first.md` and guide for per-framework rationale. Framework specialists auto-invoke on matching work.
