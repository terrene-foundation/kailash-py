# Worktree Orchestration Reference

Detailed evidence and post-mortems backing the 5 worktree rules in `rules/agents.md`. The rules contain the load-bearing MUST clauses + DO/DO NOT; this file holds the institutional memory (failure stories, counterfactuals, prompt templates).

## Rule 1 — Worktree Isolation For Compiling Agents

**Rule:** `rules/agents.md` § "MUST: Worktree Isolation for Compiling Agents".

**Why it exists:** Cargo uses an exclusive filesystem lock on `target/`. Two cargo processes in the same directory serialize completely, turning parallel agents into sequential execution. Worktrees give each agent its own `target/` directory.

**Cross-language applicability:** Rust (cargo `target/` lock) is the clearest case. Python does NOT have the same compiler lock, but worktree isolation still prevents agents from stepping on each other's file edits and produces cleanly-merge-able commit branches — both significant benefits. JavaScript/TypeScript also benefit because `node_modules/` can be contention-sensitive during install.

**Full protocol:** `isolation: "worktree"` is necessary but not sufficient. Combine with:

1. Relative paths only in the agent prompt (Rule 2 below)
2. Explicit commit-as-you-go discipline (Rule 3 below)
3. Post-exit file existence verification (Rule 4 below)
4. Cross-agent package ownership declared (Rule 5 below)

Without all 5 layers, agents drift back to the main checkout silently, lose work to auto-cleanup, or race on version-bump files.

## Rule 2 — Worktree Prompts Use Relative Paths Only

**Rule:** `rules/agents.md` § "MUST: Worktree Prompts Use Relative Paths Only".

### Failure mode evidence

Session 2026-04-19 logged: 2 of 3 parallel shards wrote to MAIN before self-correcting (Shard B) or losing work entirely (Shard A's 300+ LOC of sklearn array-API impl was lost when its empty worktree auto-cleaned). Only one self-corrected; the failure mode is not agent-detectable by default.

Post-mortem: `workspaces/kailash-ml-gpu-stack/journal/0004-RISK-torch-lightning-deviceReport-orphan.md` — full post-mortem of the write-to-main leak AND the subsequent spec-compliance finding it masked.

### Why relative paths are load-bearing

`isolation: "worktree"` creates a nested git worktree under `.claude/worktrees/agent-XXXX/`, then runs the agent with cwd set to that worktree. Relative paths resolve correctly; absolute paths point back to the parent checkout the orchestrator is using, silently defeating isolation.

### Prompt template (safe)

```python
Agent(
    isolation="worktree",
    prompt="""
    Resolve <issue>.

    Files you may edit (relative paths only; NEVER absolute):
    - packages/kailash-ml/src/kailash_ml/foo.py
    - packages/kailash-ml/tests/integration/test_foo.py

    ...
    """,
)
```

## Rule 3 — Worktree Agents Commit Incremental Progress

**Rule:** `rules/agents.md` § "MUST: Worktree Agents Commit Incremental Progress".

### Failure mode evidence

Session 2026-04-19 ML GPU-first Phase 1 parallel-shard experiment:

- Shard A's agent wrote a complete SklearnTrainable Array-API rewrite, then truncated on "Now let me rewrite fit:" with zero commits. Worktree auto-deleted. ~300 LOC of load-bearing work had to be recovered serendipitously from Shard B's scope-creeped worktree.
- Shard C was rescued by an explicit WIP commit from the orchestrator immediately after notification.
- Only Shard B self-corrected — because its prompt happened to emphasize "commit before exit" as a byproduct.

Three of three parallel agents truncated at 250-370k tokens; two lost work to auto-cleanup.

### Why incremental commits are load-bearing

Worktree auto-cleanup silently deletes worktrees with zero commits on their branch. An agent that writes perfect code but truncates mid-message before committing loses 100% of its output. Post-hoc file-existence verification (Rule 4 below) catches orphan files in main but CANNOT recover files that were only in a cleaned-up worktree.

### Prompt template

```python
Agent(
    isolation="worktree",
    prompt="""
    ...

    **Commit discipline (MUST):**
    - After each file is complete, run `git add <file> && git commit -m "wip(shard-X): <what>"`.
    - Do NOT hold all work in the worktree's index until the final report.
    - If you exit without committing (budget exhaustion / crash / interruption),
      the worktree is auto-cleaned and ALL work is lost.
    """,
)
```

## Rule 4 — Verify Agent Deliverables Exist After Exit

**Rule:** `rules/agents.md` § "MUST: Verify Agent Deliverables Exist After Exit".

### Failure mode evidence

Session 2026-04-19 logged 2 occurrences (kaizen round 6, ml-specialist round 7) where an agent hit its budget mid-message and reported success with zero files on disk. The agent emitted "Now let me write X..." with no tool call behind it.

The `ls` check is O(1) and converts silent no-op into loud retry.

### Combined protocol

- Rule 3 (commit discipline) protects against worktree auto-cleanup
- Rule 4 (post-exit verify) protects against the main checkout
- Both are needed: Rule 3 alone misses truncated-in-main cases; Rule 4 alone misses truncated-worktree cases

## Rule 5 — Parallel-Worktree Package Ownership Coordination

**Rule:** `rules/agents.md` § "MUST: Parallel-Worktree Package Ownership Coordination".

### Positive evidence (coordination succeeded)

Session 2026-04-20 kailash-ml 0.13.0 + kailash 2.8.10 parallel-release cycle (PRs #552, #553). Three parallel worktree agents resolved issues #546 (ONNX matrix), #547+#548 (km.doctor + km.track), and #550 (quote_identifier). Clean integration because:

- **Agent 1** designated version-owner for kailash-ml pyproject.toml + CHANGELOG
- **Agent 2** prompt included the verbatim exclusion: "COORDINATION NOTE: A parallel agent is resolving #546 (ONNX bridge matrix) in another worktree and will ALSO bump version to 0.13.0 + write CHANGELOG. To avoid merge conflicts, you (this agent) MUST NOT edit packages/kailash-ml/pyproject.toml, packages/kailash-ml/src/kailash_ml/**init**.py::**version**, or packages/kailash-ml/CHANGELOG.md."
- **Agent 3** worked on a different package (core kailash/, 2.8.10) — no overlap

Result: merge integration was mechanical. One trivial CHANGELOG conflict on the root file, zero conflicts on package pyproject.toml or package CHANGELOG. Integration step (owned by orchestrator) added `km-doctor` console script + expanded CHANGELOG (which Agent 1 correctly seeded with ONNX entries only) to cover all three issues.

### Counterfactual

Without the exclusion clause, Agent 2 would have independently bumped 0.12.1 → 0.13.0 and written its own top-level `## [0.13.0]` CHANGELOG entry. At merge time git would have picked one agent's version field (arbitrary) and one agent's CHANGELOG header (arbitrary), silently dropping the other's prose. The cost of the exclusion clause is one sentence per sibling prompt; the cost of the collision is manual CHANGELOG reconciliation plus risk of dropped coverage notes.

### Integration step belongs to orchestrator

The post-merge fixup (adding cross-agent artifacts that neither agent owned) is the orchestrator's responsibility, not an agent's:

- `km-doctor` console script entry in `pyproject.toml [project.scripts]` — spans agents 1 and 2's work
- Expanded CHANGELOG entries covering all 3 issues — agent 1 wrote the ONNX section; orchestrator added km.track + km.doctor sections
- Cross-package version floor updates (sibling package bumps, lockstep coordination)

Agents MUST NOT attempt integration work because they cannot see each other's worktrees until the merge lands.

## Reviewer Prompts — Mechanical AST/Grep Sweep

**Rule:** `rules/agents.md` § "MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep".

### Failure mode evidence

Session 2026-04-19 ML GPU-first Phase 1 codify cycle — code reviewer APPROVED 0.12.0 with one minor finding (missing test); the subsequent `/redteam` mechanical sweep caught TorchTrainable + LightningTrainable missing `device=DeviceReport` (2 of 7 return sites). The reviewer never ran the parity grep.

See `workspaces/kailash-ml-gpu-stack/journal/0004-RISK-torch-lightning-deviceReport-orphan.md` § "Why it slipped past the round-3 reviewer" for the full analysis.

### Why mechanical sweeps are load-bearing

Gate reviewers are constrained by the diff they're shown. The orphan failure mode of `rules/orphan-detection.md` §1 is invisible at diff-level — the new entries look complete; the OLD entries that were never updated for the new public surface stay invisible. A 4-second `grep -c` sweep catches what 5 minutes of LLM judgment misses. Without the sweep, the reviewer agent's APPROVE verdict is necessary but not sufficient.

### Reviewer prompt template (with sweeps)

```python
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
```

## Related rules & skills

- `rules/agents.md` — the load-bearing MUST clauses for all 5 worktree rules
- `rules/orphan-detection.md` — §1 (facade call site) and §6 (`__all__` eager import) are what the mechanical sweep verifies
- `skills/30-claude-code-patterns/parallel-merge-workflow.md` — merge-step patterns for collecting worktree branches into an integration branch
- `guides/deterministic-quality/02-session-architecture.md` — session-level architecture for multi-agent orchestration
