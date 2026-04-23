---
paths:
  - ".claude/agents/**"
  - ".claude/commands/**"
  - "**/agents/**"
---

# Worktree Isolation Rules

Agents launched with `isolation: "worktree"` run in their own git worktree so parallel compile/test jobs do not fight over the same `target/` or `.venv/`. The isolation is only real if the agent actually edits files inside its assigned worktree path. When an agent drifts back to the main checkout — because the system prompt didn't pin cwd, because absolute paths were copied from the orchestrator, because the tool defaulted to `process.cwd()` — the isolation silently breaks: two workers overwrite each other's changes, one commits the other's half-done code, and the "parallel" session produces garbage that only surfaces at `/redteam`.

This rule mandates a self-verification step at agent start AND a pre-flight check in the orchestrator's delegation prompt. The verification is cheap (one `git status`) and the failure mode is expensive (a whole session's worth of parallel work corrupted).

## MUST Rules

### 1. Orchestrator Prompts MUST Pin The Worktree Path

Any delegation that uses `isolation: "worktree"` MUST include the absolute worktree path in the prompt AND MUST instruct the agent to verify `git -C <worktree> status` at the start of its run. Passing the isolation flag without the explicit path is BLOCKED.

```python
# DO — explicit path + verification instruction
worktree = "/Users/me/repos/kailash-py/.claude/worktrees/agent-ml-abc123"
Agent(
    isolation="worktree",
    prompt=f"""
Working directory: {worktree}

STEP 0 — verify isolation before touching any file:
  git -C {worktree} status
If the output shows "not a git repository" OR the branch does not
match the worktree's expected branch, STOP and report "worktree
isolation broken" — do NOT fall back to the main checkout.

All file paths you write MUST be absolute and begin with {worktree}/.
""",
)

# DO NOT — isolation flag without pinned path
Agent(
    isolation="worktree",
    prompt="Implement feature X — use the ml-specialist patterns.",
)
# Agent starts in process.cwd() (main checkout), edits main's tree,
# reports success. Worktree is empty; main has half-done code.
```

**BLOCKED rationalizations:**

- "The isolation flag handles the cwd for me"
- "The tool sets up the worktree automatically"
- "I'll just use relative paths, they're shorter"
- "The agent will figure out the right directory"
- "I tested it once, it worked — should keep working"

**Why:** The `isolation: "worktree"` flag creates the worktree but does not pin every tool call inside it — file-writing tools that accept absolute paths will happily write to the main checkout if the orchestrator's prompt uses a main-checkout path. In this session, ml-specialist, dataflow-specialist, and kaizen-specialist each drifted back to the main tree at least once; the corruption was only caught by `git status` after the fact. One-line verification at agent start converts a silent corruption into a loud refusal.

### 2. Specialist Agents MUST Self-Verify Cwd At Start

Every specialist agent file (`.claude/agents/**/*.md`) that may be launched with `isolation: "worktree"` MUST include a "Working Directory Self-Check" step at the top of its process section. The check prints the resolved cwd and the git branch, and refuses to proceed if either is unexpected.

```markdown
# DO — self-check baked into the agent file

## Step 0: Working Directory Self-Check

Before any file edit, run:

    git rev-parse --show-toplevel
    git rev-parse --abbrev-ref HEAD

If the top-level path does NOT match the worktree path passed in the
prompt, STOP and emit "worktree drift detected — refusing to edit
main checkout". Do NOT fall back to process.cwd().

# DO NOT — assume orchestrator pinned cwd

## Step 1: Read the task

Read the prompt, start editing files…
```

**Why:** The orchestrator's pinned-path instruction can be lost to context compression across long delegation chains; a self-check inside the specialist file is a belt-and-suspenders guarantee that survives prompt truncation. Verified cost: one git call (~30 ms). Verified benefit: prevents the ml-specialist / dataflow-specialist / kaizen-specialist drift that shipped during the 2026-04-19 session.

### 3. Parent MUST Verify Deliverables Exist After Agent Exit

When an agent reports completion of a file-writing task, the parent orchestrator MUST verify the claimed files exist at the worktree path via `ls` or `Read` before trusting the completion claim. Agent completion messages are NOT evidence of file creation.

```python
# DO — verify after agent returns
result = Agent(isolation="worktree", prompt=f"Write {worktree}/src/feature.py...")
assert_file_exists(f"{worktree}/src/feature.py")  # parent checks

# DO NOT — trust "done" and proceed
result = Agent(isolation="worktree", prompt="...")
# Parent commits based on result.completion_message without ls
```

**BLOCKED rationalizations:**

- "The agent said 'done', that's good enough"
- "Verifying every file slows the orchestrator"
- "The agent would have errored if the write failed"
- "Now let me write the file..." followed by no actual write

**Why:** Agents hit their budget mid-message and emit "Now let me write X..." without having written X. This session saw 2 occurrences (kaizen round 6, ml-specialist round 7); both reported success, both produced zero files. An `ls` check is O(1) and converts "silent no-op" into "loud retry".

## MUST NOT

- Launch an agent with `isolation: "worktree"` without passing the absolute worktree path in the prompt

**Why:** The isolation flag alone does not guarantee every tool call stays inside the worktree — the prompt is the only place the agent learns where it belongs.

- Trust an agent's "completion" message when it says "Now let me write…" followed by no tool call

**Why:** Budget exhaustion truncates the write. The completion message is misleading; the filesystem is the source of truth.

- Use `process.cwd()` or relative paths inside specialist agent files that may run in a worktree

**Why:** `process.cwd()` resolves to whatever the Claude Code process was launched with (the main checkout), not the worktree; relative paths inherit the same problem.

### 4. Parallel-Launch Burst Size Limit (Waves of ≤3)

When launching multiple Opus agents with `isolation: "worktree"` in a single orchestration turn, the parent MUST launch them in waves of ≤3, NOT a single burst of 4+. Bursts of 4+ simultaneous Opus agents hit Anthropic server-side rate limiting and ALL fail at 30–45s elapsed with `API Error: Server is temporarily limiting requests for this user`. Rate-limit failures exit the agent before it commits anything — every shard in the failed burst loses its work.

```python
# DO — wave of 3, wait, then next wave
wave1 = [
    Agent(isolation="worktree", prompt="... W31a+d ..."),
    Agent(isolation="worktree", prompt="... W31b ..."),
    Agent(isolation="worktree", prompt="... W31c ..."),
]
# wait for wave1 to complete (or fail) before launching wave2
wave2 = [
    Agent(isolation="worktree", prompt="... W32a ..."),
    Agent(isolation="worktree", prompt="... W32b ..."),
    Agent(isolation="worktree", prompt="... W32c ..."),
]

# DO NOT — burst of 6 simultaneous Opus worktree agents
for shard in [W31a, W31b, W31c, W32a, W32b, W32c]:
    Agent(isolation="worktree", prompt=f"... {shard} ...")
# ↑ all 6 rate-limited at 34-45s, zero commits across all worktrees,
#   every shard's work is lost. Empirical: 2026-04-23 M10 launch.
```

**BLOCKED rationalizations:**

- "The API says we can launch as many as we want"
- "Rate limits only kick in on sustained load"
- "If any fail we'll just retry"
- "Waves of 3 halves my throughput for no reason"
- "The earlier tests with 4 agents worked fine"

**Why:** Anthropic's server-side throttle on simultaneous Opus session starts is not documented as a hard limit, but empirically 4–6 concurrent Opus worktree agents from one parent exceeds it and every agent in the burst dies before committing. Recovery is worse than serialization: the orchestrator MUST re-launch every failed shard, and without commits (see § Rule 5) there is no partial-progress to salvage. Waves of ≤3 complete cleanly; the latency cost of waiting one wave is strictly less than the cost of a full re-launch plus orphan recovery. Evidence: kailash-ml-audit 2026-04-23 M10 launch — 6 Opus worktree agents (`ab9c2f7213c4a82ab`, `ae2f048829aa941a2`, `af15e0f9c3f2d16a3`, `a823d7ed912137852`, `a0e76f0996d1d9a4e`, `ad10591aa614deeae`) launched simultaneously, ALL 6 died at 34–45s with rate-limit error; fallback waves of 3 (`a506217c8640af1c0`, `a0831fc0ca6b9f6ae`, `a1027b84cb7c4f9d2` + `aa7fb6a6`, `a69473b3`, `aaecc695`) all completed and merged successfully.

### 5. Pre-Flight Merge-Base Check Before Worktree Launch

Before launching a worktree agent, the orchestrator MUST create the worktree's branch from the current `HEAD` of the feat/main branch the work will merge back into — NOT from a stale commit the agent happens to pick up. The orchestrator MUST verify `git merge-base <new-branch> <target-branch>` equals the CURRENT tip of `<target-branch>` at launch time. Launching without the merge-base check is BLOCKED.

```bash
# DO — pin the base SHA at launch, verify merge-base matches HEAD
target_branch="feat/kailash-ml-1.0.0-m1-foundations"
target_head=$(git rev-parse "$target_branch")
git worktree add -b "feat/w31-core-ml-nodes" ".claude/worktrees/w31a" "$target_head"
merge_base=$(git merge-base "feat/w31-core-ml-nodes" "$target_branch")
[ "$merge_base" = "$target_head" ] || { echo "base drift — ABORT"; exit 1; }

# DO NOT — let the worktree default to a stale branch tip
git worktree add .claude/worktrees/w31a  # branches from whatever HEAD happens to be
# Agent's branch now forks from an OLD commit; merge silently picks
# either side on conflicts; package overlap = data loss.
```

**BLOCKED rationalizations:**

- "The worktree defaults handle the base SHA"
- "Git will rebase at merge time"
- "The packages don't overlap so stale base is fine"
- "It worked this time, the failure mode is theoretical"

**Why:** `git worktree add` without an explicit base defaults to whatever branch HEAD was last set — which for a long-running session can be a pre-merge commit from hours ago. Worktrees created from a stale base merge cleanly ONLY when the packages they touch don't overlap; the moment two shards touch the same `pyproject.toml`, same `__init__.py`, or same CHANGELOG, the 3-way merge silently discards one shard's edits (see `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination"). The merge-base check converts an invisible drift risk into a loud pre-flight abort. Evidence: kailash-ml-audit 2026-04-23 M10 launch — 5 of 6 worktrees branched from `899ce3e5` (pre-W30-merge), only 1 branched from feat tip `41a217dc`. Worked this time only because packages didn't overlap; failure mode is permanent until structurally prevented.

### 6. Worktree Branch Name MUST Match Prompt's Declared Name

When the orchestrator prompt specifies a branch name (e.g. `feat/w31-core-ml-nodes`), the worktree MUST be created with that exact branch name — NOT the harness default `worktree-agent-<hash>`. The orchestrator MUST pass `-b <branch>` explicitly to `git worktree add`, AND the agent prompt MUST verify `git rev-parse --abbrev-ref HEAD` matches the declared name before committing.

```python
# DO — explicit branch name on worktree creation
worktree = ".claude/worktrees/w31a"
branch = "feat/w31-core-ml-nodes-observability"
subprocess.run(["git", "worktree", "add", "-b", branch, worktree, target_head])
Agent(
    isolation="worktree",
    prompt=f"""Working directory: {worktree}
Branch: {branch}

STEP 0 — verify branch name matches:
  actual=$(git -C {worktree} rev-parse --abbrev-ref HEAD)
  [ "$actual" = "{branch}" ] || {{ echo "branch-name drift"; exit 1; }}
""",
)

# DO NOT — let harness default assign worktree-agent-<hash>
Agent(isolation="worktree", prompt="Implement W31... use feat/w31-core-ml-nodes")
# ↑ 3 of 6 shards in the M10 launch ended up on worktree-agent-<hash>
#   branches because the prompt name-reference didn't force creation.
#   Post-merge grep for feat/w31-* missed those three.
```

**BLOCKED rationalizations:**

- "The branch name is only for bookkeeping"
- "Harness default names are fine, I'll rename at merge"
- "The prompt mentions the name, the agent will set it"
- "Hash-based names are more unique"

**Why:** Branch names are the primary `git log --grep` surface for tracing a shard back to its plan — `feat/w31-core-ml-nodes-observability` instantly surfaces in history; `worktree-agent-aa7fb6a6` surfaces only as a meaningless hash. When half the shards in a release wave use harness-default names, post-merge audits cannot enumerate "did every planned shard land?" via grep — they have to cross-reference the worktree list (which has already been auto-cleaned). Evidence: kailash-ml-audit 2026-04-23 — 3 of 6 M10 shards honored `feat/<shard>` names (`feat/w31-core-ml-nodes-observability`, `feat/w31b-dataflow-ml-bridge`, `feat/w31c-nexus-ml-bridge`, `feat/w33b-migration-readme-regression`) while 3 got `worktree-agent-aa7fb6a6`, `worktree-agent-a69473b3`, `worktree-agent-aaecc695`, `worktree-agent-aa8e8995`, `worktree-agent-af0e8132`. Audit had to pull from the orchestrator's working-memory table.

## Relationship To Other Rules

- `rules/agents.md` § "MUST: Worktree Isolation for Compiling Agents" — companion rule; this file is the verification layer for the isolation directive there.
- `rules/zero-tolerance.md` Rule 2 — a completed-looking file that doesn't exist is a stub under a different name.
- `rules/testing.md` § "Verified Numerical Claims In Session Notes" — same principle, applied to file deliverables.

Origin: Session 2026-04-19 — ml-specialist, dataflow-specialist, and kaizen-specialist each drifted back to the main tree during PRs #502-#508; kaizen round 6 and ml-specialist round 7 reported "Now let me write X..." completions with no actual file writes. The self-verify + parent-verify protocol closed both failure modes. Rules 4–6 added 2026-04-23 from the kailash-ml-audit M10 release wave (6-agent burst rate-limit + 5-of-6 stale-base-SHA + 3-of-6 branch-name-default).
