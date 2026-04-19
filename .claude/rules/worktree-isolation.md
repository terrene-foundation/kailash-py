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

## Relationship To Other Rules

- `rules/agents.md` § "MUST: Worktree Isolation for Compiling Agents" — companion rule; this file is the verification layer for the isolation directive there.
- `rules/zero-tolerance.md` Rule 2 — a completed-looking file that doesn't exist is a stub under a different name.
- `rules/testing.md` § "Verified Numerical Claims In Session Notes" — same principle, applied to file deliverables.

Origin: Session 2026-04-19 — ml-specialist, dataflow-specialist, and kaizen-specialist each drifted back to the main tree during PRs #502-#508; kaizen round 6 and ml-specialist round 7 reported "Now let me write X..." completions with no actual file writes. The self-verify + parent-verify protocol closed both failure modes.
