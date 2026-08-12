# Launch Ledger — cont-17

Base: main `21deef321` (after #2095 merged). Durable per `orchestration-launch-ledger.md` MUST-1.
Consult BEFORE every spawn (MUST-2); match every completion against it BEFORE reacting (MUST-3).

Worktree parent: `<build-parent>/.kailash-py-wt/` (sibling, outside the repo — `worktree-isolation.md` Rule 7).

## Wave 1 (launched, cold-start cap ~3 per `worktree-isolation.md` Rule 4)

| lane | issue(s)       | branch                               | worktree | status    |
| ---- | -------------- | ------------------------------------ | -------- | --------- |
| w1a  | #2072 (task27) | `fix/2072-fail-closed-require-auth`  | w1a      | in-flight |
| w1b  | #2083, #2092   | `fix/2083-2092-key-generation-class` | w1b      | in-flight |
| w1c  | #2078          | `fix/2078-tier2-resource-exhaustion` | w1c      | in-flight |

## Carried from cont-16 (NOT this session's launch)

| lane | issue | branch                                   | worktree | status                                 |
| ---- | ----- | ---------------------------------------- | -------- | -------------------------------------- |
| w2b  | #2070 | `fix/2070-logging-hook-redaction-defeat` | w2b      | PR #2073 open, CONFLICTING, HELD on D1 |

**Do NOT remove w2b** — its 5 commits are not in main and cannot be recreated (L2 quota).

## Wave 2 (launched)

| lane | issue(s)                     | branch                                   | worktree | status    |
| ---- | ---------------------------- | ---------------------------------------- | -------- | --------- |
| w2c  | #2084 (+ D1 verdict → #2073) | `fix/2084-observability-honesty`         | w2c      | in-flight |
| w2d  | #2047, #2088, #2089, #2040   | `fix/2047-mfa-actor-log-sanitizing`      | w2d      | in-flight |
| w2e  | PR #2031 (D3 approved)       | `docs/codify-specification-verification` | w2e      | in-flight |

6 concurrent Opus-tier lanes. No synchronized-throttle signal observed (the
`worktree-isolation.md` Rule 4 falsifiable signal: ≥2 lanes dying within a
~30–48s window carrying `(not your usage limit)`). Hold at 6 until lanes return.

## Wave 3 (queued, NOT launched — with the reason each is held)

- **w2f — proxy cluster #2085 #2087 #2091.** HELD: collides with w1a on
  `src/kailash/servers/` proxy handlers. Launch after w1a lands.
- **w3a — CI selectors #2074 + #2076.** HELD: may collide with w1c on
  `unified-ci.yml`. Launch after w1c lands.
- **w3b — channel/MCP lifecycle #2018 #2019 #2020 #2021 (+ #2011 #2017).**
  Independent — launchable as soon as a slot frees.
- **w3c — remainder: #2069 #2086 #2052 #2056 #2057 #2000 #2010 #2029 #2067 #2039 #2044.**

## ⚠ QUOTA KILL — all 6 lanes died at 03:05Z. WIP PRESERVED. This was NOT a throttle.

All six lanes returned `idleReason: failed` within a 41-second window with:

    You've hit your session limit · resets 1:30pm (Asia/Singapore)

**Read the string, not the shape.** A synchronized multi-lane death at ~30–48s
LOOKS exactly like the `worktree-isolation.md` Rule 4 concurrency throttle — but
that signal's discriminating text is **`(not your usage limit)` / `Rate limited`**.
This said the OPPOSITE: it IS the usage limit. So per Rule 4 this **MUST NOT
trigger concurrency back-off** — 6 concurrent lanes was not the problem, account
quota was. The operator swapped accounts (`csq swap 10`). Do NOT "learn" a lower
concurrency cap from this event.

**WIP preservation (orchestrator, before any relaunch):**

| lane | uncommitted at death                                       | preserved as |
| ---- | ---------------------------------------------------------- | ------------ |
| w1a  | **36 entries**                                             | `04f8025d7`  |
| w1b  | 12 entries (incl. 2 new fail-first regression tests)       | `f6a2bf25a`  |
| w1c  | 4 entries (incl. `test_issue_2078_address_space_limit.py`) | `0ae88b3e4`  |
| w2c  | 2 entries (a new `audit_trail_hook.py`)                    | `c8d07bea2`  |
| w2d  | 0 — died before writing                                    | —            |
| w2e  | 0 — its 2 commits pre-date this session                    | `ee8274122`  |

Committed with `core.hooksPath=/dev/null` **deliberately and disclosed in each
commit body**: these are ORCHESTRATOR WIP-preservation commits over mid-shard
trees, where the hooks' test/lint gates would fail on deliberately-incomplete
work. Silent `--no-verify` is BLOCKED; this is the documented form. **Every
relaunched lane MUST re-run the full local CI-parity set before pushing.**

Signal worth keeping: w1c's WIP (`memory_limit_guard`, `RLIMIT_AS` edits in
`src/kailash/security.py`, `test_issue_2078_address_space_limit.py`) suggests it
had converged on **address-space limits** as the #2078 thread-exhaustion root
cause. The relaunched lane should resume from that, not re-derive it.

## RELAUNCH (post-quota, account 10) — supersedes the wave-1/wave-2 rows above

All six relaunched with RESUME briefs naming their predecessor's WIP commit, so
each reads and verifies that work instead of redoing it. Every relaunch brief adds
a **commit-at-every-milestone** mandate so a future quota kill costs minutes.

| lane | agent name          | resumes from | scope                                    |
| ---- | ------------------- | ------------ | ---------------------------------------- |
| w1a  | `w1a-2072-auth-r2`  | `04f8025d7`  | #2072 fail-closed auth (CRITICAL)        |
| w1b  | `w1b-keygen-r2`     | `f6a2bf25a`  | #2083 + #2092 + SHAPE sweep              |
| w1c  | `w1c-2078-r2`       | `0ae88b3e4`  | #2078 CI keystone (RLIMIT_AS hypothesis) |
| w2c  | `w2c-2084-r2`       | `c8d07bea2`  | #2084 + the D1 verdict                   |
| w2d  | `w2d-auth-actor-r2` | (clean)      | #2047 #2088 #2089 #2040                  |
| w2e  | `w2e-2031-r2`       | `ee8274122`  | PR #2031 (D3 approved)                   |

**Match every completion notification against THIS table before reacting**
(`orchestration-launch-ledger.md` MUST-3) — the `-r2` names are the live ones;
the pre-quota names are dead and must not be re-dispatched or re-attributed.

## ⛔ ORCHESTRATOR ERROR — I DUPLICATE-SPAWNED ALL SIX LANES. Resolved; record the lesson.

**A `failed` / quota notification is NOT evidence that an agent TERMINATED.**

I read the six `idleReason: failed · You've hit your session limit` notifications
as terminations and spawned `-r2` replacements into the SAME worktrees. After the
operator's `csq swap 10`, the ORIGINALS RESUMED. Two agents then ran concurrently
in every lane, on the same branch, editing the same files.

This is exactly the duplicate-spawn `orchestration-launch-ledger.md` MUST-2
forbids, and the ledger was RIGHT THERE showing every track `in-flight`. The
ledger check does not fail if you consult it and then override it with an
assumption. **The bug was inferring liveness from a notification instead of
measuring it** — `evidence-first-claims.md` MUST-3: an errored/failed result is
zero evidence, never confirmation of a state.

**How it surfaced:** `w1a-2072-auth-r2` refused to push and escalated, with
process-level evidence — a `pytest` it never launched (flags it never used:
`-p no:cacheprovider`, `--continue-on-collection-errors`), an mtime on
`durable_gateway.py` LATER than its own last edit on a file it never opened, and
its own `git add -A` having swept in a sibling's test file. **A lane that halts on
a collision rather than pushing is worth more than one that complies** — this is
the second time that has paid out this session.

**Resolution:** all six pre-quota agents stopped via TaskStop (each returned
success); verified afterwards that ZERO stray pytest processes remain under any
lane worktree (the one surviving process was w2c's own commit in its own tree).
The `-r2` instances survive — they carry the better briefs and, in w1a's case,
committed verified work. Nothing was lost: the killed originals' edits remain
uncommitted on disk for the survivor to absorb with credit.

**Every surviving lane was told: some uncommitted edits in your tree may not be
yours — account for every file before committing, treat anything you did not
write as unreviewed.**

### The correct check, for next time

Before spawning a replacement for a lane reported dead, MEASURE liveness — e.g.
`ps -eo pid,etime,command | grep <worktree-path>` for live processes, and compare
file mtimes against the agent's own last edit. Do not infer it from a
notification. A quota `failed` is recoverable and may resume on account swap;
only an observed absence of the process is evidence of absence.

## #2072 ENFORCEMENT-SURFACE PARITY SWEEP — 2 MORE OPEN SURFACES (w1a; orchestrator-verified)

`POST .../execute` anonymous-execution is NOT one site. Sweep results, each
re-verified by the orchestrator against `origin/main` before ruling (not taken
on lane report — this is a CRITICAL disposition):

| surface                                               | state          | evidence                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/kailash/api/workflow_api.py`                     | **OPEN**       | `@self.app.post("/execute")` at :303; standalone entry `def run()` → `uvicorn.run` at :675; `grep -c require_auth` = **0**. So `WorkflowAPI(wf).run()` is anonymous arbitrary execution WITHOUT touching `WorkflowServer`. Also the sub-app mounted by `WorkflowServer.register_workflow` (~~:823) and `WorkflowAPIGateway` (~~:601) — gating needs `external_auth_reason` threaded from BOTH parents or every mounted workflow double-authenticates. |
| `src/kailash/gateway/api.py::create_gateway_app`      | **OPEN**       | `POST /workflows/{id}/execute` :131 and `/register` :237; every `Depends(...)` on them is `Depends(get_gateway)` — a **gateway-instance injector, not authentication**; `grep -c require_auth` = **0**.                                                                                                                                                                                                                                               |
| `src/kailash/middleware/communication/api_gateway.py` | already CLOSED | `enable_auth: bool = True` :143 + `KAILASH_API_GATEWAY_SECRET` RuntimeError :178 (since #636). Genuinely fail-closed; correctly out of scope. This is the precedent #2072 cites.                                                                                                                                                                                                                                                                      |

**Ruling: w1a EXTENDS the PR to close both (option a).** `autonomous-execution.md`
MUST-4 — same bug class, warm context, in budget → fix now; a follow-up issue
would be the BLOCKED disposition. **`Fixes #2072` is only honest once both close**;
otherwise the PR ships `Refs #2072` — the same standard that made PR #2064
`Refs #2025` rather than `Fixes`. Auto-closing a CRITICAL with a default-reachable
instance still live records it resolved when it is not.

**Budget stop-condition given to the lane:** MUST-4 is doubly bounded — by
category AND by shard budget. If threading `external_auth_reason` through
`WorkflowAPI`'s two parents exceeds one shard (the double-authentication risk is
where that would happen), the lane STOPS and reports; we then ship `Refs #2072`
with the sweep table in the PR body and open a dedicated lane. A gap genuinely
exceeding the budget IS correctly a follow-up.

**Note:** the terminated sibling had already begun surface 2 — `gateway/api.py`
carries uncommitted `install_server_auth_middleware` / `_auth_config` references,
with the helper UNDEFINED at the call site. Unreviewed, non-importing work; the
lane was told to finish or discard it explicitly, not assume it correct.

## ⚠ TRAP — a worktree cannot collect `kailash._kailash` (found by w1a)

`tests/regression/test_classification_fail_closed.py` fails to COLLECT in any
worktree: `ModuleNotFoundError: No module named 'kailash._kailash'`.
`_kailash.cpython-312-darwin.so` is a **gitignored build artifact present only in
the main checkout**, so every run using `-o pythonpath=<worktree>/src` misses it.
Environmental, not a code defect.

**The sharp edge: `--continue-on-collection-errors` SILENTLY SWALLOWS IT** — a run
carrying that flag yields a green that cannot distinguish "collected and passed"
from "never collected." Same non-discriminating-instrument class as `continue-on-error`
(#2038) and green-by-absence (#2074, #2002). **Never use that flag in a final
verification run.** Copying the `.so` into the worktree to iterate is acceptable
(gitignored, cannot reach a commit) but MUST be disclosed when reporting a suite
result, because the tree then differs from what CI sees. w1c was asked to check
whether any CI selector carries the flag — if so it is another green-by-absence surface.

## ✅ D1 RESOLVED — WIRING IS FEASIBLE. #2073's raise is superseded; #2073 will CLOSE.

w2c-2084-r2 returned the verdict with receipts. **All four hook classes already
exist** — in `packages/kailash-kaizen/src/kaizen/core/autonomy/hooks/builtin/`
(`tracing_hook.py:50`, `logging_hook.py:24`, `metrics_hook.py:29`,
`audit_hook.py:16`), NOT in the `observability/` path `smart_defaults` imported
(`grep -rn "^class .*Hook"` there returns **0**). `HookManager.register_hook`
(`hooks/manager.py:155`) is the registration contract and **its own docstring
example is the exact wiring**; `BaseAgent.enable_observability()`
(`core/base_agent.py:915-935`) already does it for tracing.

So the defect is a **wrong module path + wrong registration idiom**, not four
missing subsystems. The six phantom handler methods confirm it — scoped to real
source trees only: `start_trace 0, end_trace 0, record_start 2, record_end 0,
log_start 0, log_end 0`, and both `record_start` hits are unrelated
(`src/kailash/infrastructure/execution_store.py:119,306`).

Baseline re-derived in-process with a resolved-`__file__` receipt: `flags = True
True True True`, `is_observability_enabled() = True`, **hooks registered = 0**.
**The four flags ARE `True`** — the prior brief's "default False" claim stays
refuted; no second false premise found.

**Therefore: wire it (non-breaking AND delivers the feature). The #2073 tri-state
raise and `errors.py::ObservabilityNotImplemented` are no longer needed.**

### ⚠ Orchestrator correction to w2c's split recommendation — VERIFIED

w2c recommended splitting #2073 to save its `#2070` half. **That half already
landed.** #2070 is CLOSED/COMPLETED (2026-08-12T02:07:51Z) by **PR #2094**
(merged 02:07:50Z) — #2094 _was_ that split, performed last session.

Verified by CONTENT, not issue state — all three files byte-identical between
`origin/main` and #2073's branch tip (`git show <ref>:<path> | shasum`):
`_payload.py` (62 lines), `logging_hook.py` (279), `redaction.py` (370).

**The `git diff --stat origin/main...origin/fix/2070-...` delta (+117/+62/+60) is
a MERGE-BASE artifact** — the three-dot form diffs from the merge base, and the
branch was never rebased past #2094. That is also why the PR reads CONFLICTING.
It is NOT unlanded content. Anyone re-reading that diff will reach w2c's
conclusion again unless they compare content hashes; this note is the guard.

**Disposition (orchestrator-held, sequenced):** #2073 stays OPEN until w2c's PR
merges, then closes as SUPERSEDED citing both receipts — #2094 for the logging
half, w2c's PR for the observability half. Closing before the wire lands would
retire the raise while nothing replaces it.

## Housekeeping done (orchestrator)

- Deleted `fix/redteam-high-1-2` — verified fully contained in `origin/main`
  (`git merge-base --is-ancestor` → YES, zero commits ahead, no PR). Nothing lost.
- Classified the remaining stale remote branches; MERGED so far: `docs/w6-redteam-closeout`,
  `feat/issue-604-algorithm-identifier-threading`, `feat/w31-core-ml-nodes-observability`,
  `feat/w31b-dataflow-ml-bridge`, `feat/w31c-nexus-ml-bridge`,
  `feat/w33b-migration-readme-regression`, `worktree-agent-a69473b3`. The classification
  loop TIMED OUT before reaching the other four `worktree-agent-*` branches — **their
  status is UNKNOWN, not merged.** Finish that check before deleting any of them.

## Ground-truth reconciliation of the wave-3 backlog (orchestrator, read-only)

Per `wave-loop.md` MUST-7 — an open issue is not evidence the work is undone.
Reconciled against main `21deef321`. **Brief wave-3 lanes from THIS table, not
from the issue titles.**

| issue     | verdict                                                            | evidence                                                                                                                                                                                                                                                                            |
| --------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **#2039** | **config half ALREADY FIXED — issue retitled, not re-implemented** | `src_paths` present at `packages/kailash-dataflow/pyproject.toml:252` under `[tool.isort]` (§ starts 236). Receipt: commit `2cf40a17b`. Surviving half = the mode disagreement, cause UNKNOWN, 3 hypotheses excluded — do NOT re-run them.                                          |
| #2010     | still real                                                         | `BaseAgent.__init__` at `packages/kailash-kaizen/src/kaizen/core/base_agent.py:69` — AST-derived args carry no `description`, `vararg=None`, `kwarg=None`.                                                                                                                          |
| #2011     | still real, ONE site                                               | `packages/kailash-kaizen/scripts/test_examples_implementation.py:23` — `logging.FileHandler("kaizen_implementation_test.log")`, relative path at module scope.                                                                                                                      |
| #2000     | still real                                                         | `_get_cached_allowed_types` defined `src/kailash/security.py:443`, called `:764`. Heavy imports confirmed live in the same module (`matplotlib.axes`, `matplotlib.figure`, `cv2` at 625–657).                                                                                       |
| #2057     | still real                                                         | `add_permission_rule` appears ONLY as a `getattr` lookup at `src/kailash/middleware/auth/access_control.py:253` — zero definitions of the callee, confirming the dead-guard finding.                                                                                                |
| #2069     | still real                                                         | `_detect_provider_from_model` at `packages/kailash-kaizen/src/kaizen/agent_config.py:309`, called `:307`.                                                                                                                                                                           |
| #2029     | still real                                                         | `test_concurrent_execution_performance` at `tests/unit/nodes/test_async_node_comprehensive.py:357`.                                                                                                                                                                                 |
| #2052     | still real                                                         | `CURRENT_TIMESTAMP` literals at `packages/kailash-dataflow/src/dataflow/database/multi_database.py:236,368,494,590`.                                                                                                                                                                |
| #2067     | **cross-link found**                                               | The red test lives in `packages/kailash-kaizen/tests/regression/` — i.e. inside the 855 tests **#2074** says are in NO pytest invocation. So "red on main" was observed locally; CI never ran it. Brief w3a with this: #2074's baseline run will surface #2067 and likely siblings. |

### New trap for every lane — `build/lib/` shadow trees

SIX stale `build/lib/` package copies exist (`./build/lib`, and under
`packages/{kaizen-agents,kailash-kaizen,kailash-dataflow,kailash-mcp,kailash-nexus}`).
They are **gitignored** (verified: `git ls-files` returns 0 tracked, `git check-ignore`
returns YES) so they cannot be committed — but an unscoped `grep -rn` returns a
DUPLICATE hit from `build/lib/...` for every real `src/...` hit. Scope greps to
`src`/`packages/*/src`, and never count hits without checking for the shadow.
This is a second contributor to the 78,152-file sweep walk recorded in cont-16.

## Decisions taken this session

- **D2 — the six `deferred-quality` items: RE-TRIAGED as ordinary bugs** (co-owner
  approved). Label retired on all six; zero open issues now carry it. Receipt
  comment posted on each. No technical finding withdrawn.
- **D3 — PR #2031: RESOLVE both gating questions and land** (co-owner approved),
  not close. Lane w2e.
- **D1 — #2073 remains HELD** pending w2c's wiring-feasibility verdict.
