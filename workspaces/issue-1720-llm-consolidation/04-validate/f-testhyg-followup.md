# F-TESTHYG follow-up — kaizen-agents test-scratch root writes (DEFERRED)

Wave 1A agent (2026-07-18) hit a session limit mid-investigation. Captured here
so a fresh session starts ahead. **Symptom already mitigated** by the `.gitignore`
band-aid (PR #1808) — this is the real fix behind it.

## Finding (agent investigation, verified)

The kaizen-agents scratch files split into TWO classes:

1. **CWD-relative writes** (`proposal*.txt`, `task_*.txt`, `memory.txt`,
   `session*.txt`, `delegation_plan.txt`, `evaluation_results.json`, …) — computed
   at runtime from task/session/proposal keys, written relative to the current
   working directory. Run from the package root → land beside the source tree.
   **A `monkeypatch.chdir(tmp_path)` autouse fixture catches this class** (below).

2. **Discovered/absolute-root writes** (`consensus_<hash>.json`,
   `detailed_proposal.txt`, `proposal_evaluation.txt`) — these landed at the
   package root **even with the chdir fixture active** (observed in the agent's
   worktree). So some kaizen-agents code DISCOVERS a project root (not CWD) and
   writes there during real-LLM runs. The chdir fixture does NOT catch this class.

## Partial fix (agent-authored, NOT merged — the chdir fixture)

```python
# packages/kaizen-agents/tests/conftest.py
import pytest

@pytest.fixture(autouse=True)
def _isolate_cwd_scratch(tmp_path, monkeypatch):
    """Route CWD-relative scratch writes into an isolated auto-cleaned temp dir."""
    monkeypatch.chdir(tmp_path)
```

Catches class 1 only. Left un-merged: (a) incomplete (class 2 still leaks),
(b) shipping a partial fix adds little over the .gitignore band-aid.

## Real fix (fresh session — src-level)

Locate the root-discovery logic in kaizen-agents that writes class-2 scratch
(`grep -rn "consensus_\|detailed_proposal\|proposal_evaluation\|_find.*root\|project_root" packages/kaizen-agents/src`)
and either (a) route it through an env-var workspace-root knob the tests set to
`tmp_path`, or (b) fix the code to write CWD-relative (then the chdir fixture
covers everything). Touches src → its own redteam + a kaizen-agents release.

## product-completion-first disposition (INCREMENTAL defer, 4 conditions)

- (i) **Blocking-safety:** does NOT touch any shipped/success path; scratch is
  test-run litter, not a runtime defect. `.gitignore` (#1808) prevents commits.
- (ii) **Value-anchor:** test-hygiene per the owner's minor-note ("address the
  scratch litter"); the real fix removes the band-aid dependency.
- (iii) **Acceptance:** after a kaizen-agents test run, `git status` shows ZERO
  new scratch at the package root WITHOUT relying on `.gitignore`.
- (iv) **Revisit trigger:** `after-milestone:1720-wave2` (bundle with the Wave-2
  kaizen-agents release, since both touch kaizen-agents src + release).

## Reconciliation — 2026-07-23 (cont-15, revisit trigger FIRED)

The `after-milestone:1720-wave2` trigger has **passed without bundling**: cont-14 shipped
**kaizen-agents 0.11.7** as #1720's final release (#1927), but F-TESTHYG was NOT bundled in.
The item is now an **orphaned INCREMENTAL deferral** whose original revisit trigger expired.

Re-scoped effort (grep evidence, cont-15): the class-2 write sites are **NOT statically
locatable** — `consensus_<hash>.json` / `detailed_proposal.txt` / `proposal_evaluation.txt`
appear nowhere as literal write sites in `packages/kaizen-agents/src` (dynamically
constructed filenames; observable only under real-LLM runs — where the Wave-1A agent hit
its session limit). The real fix therefore requires real-LLM reproduction to locate the
sites, then a src change + kaizen-agents redteam + a **patch release** — for test-run
scratch litter that is already `.gitignore`-masked (#1808) and has **zero runtime / user
impact**.

The class-1 chdir fixture alone delivers no net value: it does not let us remove the
`.gitignore` band-aid (class-2 still leaks), which is why cont-14's predecessor left it
un-merged.

**Value re-validation (value-prioritization MUST-3):** LOW — anchor is the owner's minor
test-hygiene note; not a shipped/runtime defect. Disposition is a **user gate**
(value-prioritization MUST-4: value-bearing deferred work is not closed nor re-actioned
without owner sign-off). **Re-anchored trigger:** `next kaizen-agents src change OR owner
prioritizes test-hygiene` (removes the expired release-bundle coupling).

## RESOLVED — 2026-07-23 (cont-15, owner-approved "action it now")

The bounded investigation **corrected the premise**: there is NO "class-2 root-discovery src
bug." The `consensus_*.json` / `detailed_proposal.txt` names appear in src only as dict/memory
keys (no disk-write site) — those scratch files were **example-script output**, not shipped
package behavior. The real, confirmed defect was narrower AND user-facing (not test-only):

- **`BaseAutonomousAgent.__init__` created `./checkpoints/` in the caller's cwd on EVERY
  construction** (base.py:222 unconditional `mkdir`) — even for agents that never checkpoint
  (base run loop persists via `state_manager`/DataFlow). Confirmed runtime, not test litter.

**Fix (non-breaking):** dir creation moved to lazy (first checkpoint write in `_save_checkpoint`).
Construct → no folder; checkpoint → identical dir/location on demand. Reads already
`.exists()`-guarded. Verified: runtime walk + 3 behavioral regression tests
(`tests/regression/test_checkpoint_dir_no_cwd_litter.py`) + 44 autonomous unit tests + 3478
collect clean + 0 WARN+. Redteam 2 clean rounds (reviewer + security-reviewer NO FINDINGS;
same-class sweep found no sibling defect). Shipped in **kaizen-agents 0.11.8**.

### Residuals surfaced to owner (NOT actioned — separate decisions)

1. **Running-agent default location.** A _running_ codex/claude_code autonomous agent still
   defaults checkpoints to `./checkpoints` in the user's cwd. Lazy-mkdir fixes construct-time
   litter only; changing the documented default location (→ temp/state dir) is a
   behavior-change / owner call.
2. **Pre-existing checkpoint perms (different bug class).** Checkpoint dir/files use default
   umask (world-readable) and `state` may contain PII (security-reviewer, pre-existing). The
   delegate `SessionManager` is the in-repo secure reference (`chmod 0o700` dir + `_secure_write`
   `0o600` files). Hardening the checkpoint path to match is a separate, owner-gated change.
