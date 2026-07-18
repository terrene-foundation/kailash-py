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
