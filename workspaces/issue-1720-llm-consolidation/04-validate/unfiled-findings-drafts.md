# Findings — ALL FILED 2026-08-08, co-owner approved

**STATUS: FILED. This file is now a drafting record, not a queue.**

| draft                                   | filed as  | disposition                                                                                                                                                                                                                                                      |
| --------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — MCPChannel shutdown wedge           | **#2008** | FIXED on this branch (`a50fb78c6`); filed because it is PRE-EXISTING and production-side — first shipped `v0.8.6` 2025-07-22, every 2.x release through `v2.62.0`. Users on released versions are affected with no public record. PR should carry `Fixes #2008`. |
| 2 — discovery authz fail-open           | **#2009** | NOT fixed, deliberately. Filed as the `zero-tolerance.md` Rule 1b tracking receipt that distinguishes a reasoned deferral from a silent dismissal.                                                                                                               |
| 3 — stale `BaseAgent(description=)` E2E | **#2010** | NOT fixed — git-proven pre-existing; cannot be verified RED→GREEN on a host without a provider.                                                                                                                                                                  |
| 4 — repo-root log write                 | **#2011** | NOT fixed — voids the run-fingerprint protocol and dirties CI checkouts.                                                                                                                                                                                         |
| 5 — 390 un-triaged exception sinks      | **#2012** | NOT fixed, deliberately. The originating lane recommended AGAINST sweeping it on this branch and I accepted; it needs its own budget and per-site local-vs-remote triage.                                                                                        |

**The five-line hold was worth it on #2008.** It was drafted early and deliberately held pending the branch-caused-vs-pre-existing verdict. Had it been filed on the evidence available then, its affected-versions statement would have been a guess. The verdict (production-side, pre-existing, dated by pickaxe to exactly two commits in history) turned it from a changelog note into the most consequential of the five.

**#2012's number moved between drafting and filing — 397/109 → 390/107 — and the delta is the check.** It moved by exactly the 7 sites in 2 files that `934d5f8ae` fixed. A measurement that shifts by precisely what changed is one you can trust; one that had not moved would have meant the scanner could not see its own author's fix.

---

# Original drafts (session I) — retained as the record

Evidence re-derived from `launch-ledger-sessionH.md`; each claim below is quoted from that
record, not reconstructed. Filing is a shared-state action and is HELD for co-owner approval.

**Sequencing note on finding 1:** it is deliberately drafted but held pending
`w1-nexus-hang`'s branch-caused-vs-pre-existing verdict. If the leak is branch-introduced and
fixed in-branch, the fix commit is the receipt and no issue is owed. If it reproduces on
`main`, it MUST be filed so users on the released package learn of it. Filing before that
verdict would either be churn or would mis-state the affected versions.

---

## 1. nexus: pytest suite completes then never exits — 116 leaked non-daemon threads (HELD)

**Affected surface:** `packages/kailash-nexus/` — the runtime/transport layer that spawns
background threads; the test suite is where it is observable, not where it is caused.

**Symptom.** The suite prints its complete summary — `2592 passed, 14 skipped, 14 warnings in
302.34s` — and then does not exit. Log mtime static for 8+ further minutes; `STAT=S`,
`%CPU=0.0` (blocked, not spinning); `ps -M | wc -l` → **116 threads still alive**; the
wrapping shell's `echo EXIT=$?` never fired until SIGTERM at 920s.

**Deterministic, not a contention artifact.** Two independent instruments — different flags
(`-p no:randomly` vs `-p no:cacheprovider`), different processes, 1.8x different wall-clock
(302.34s vs 545.71s) — produced identical counts and both hung. One sat 2103s total against
a 545s test session: ~26 minutes past its own completed summary.

**Impact.** A suite that reports success and then never exits HANGS a CI job rather than
failing it: it burns the job's entire wall-clock budget and is reported as infrastructure
flake rather than as the real defect. It also means any long-running host process using this
surface leaks non-daemon threads. Secondary: the exit code is not a verdict — `EXITCODE=143`
was recorded for a run that passed 2592 tests (143 is the SIGTERM to the hang).

**Retroactive explanation.** This is why three test trees read "UNESTABLISHED" for two
sessions: every wrapper with a 10-minute cap killed a run that had ALREADY finished and
reported. Session G's "lane contention" diagnosis was wrong.

**Severity:** HIGH — blocks trusting the release gate. **Category:** BUG.

**Acceptance criteria**

- [ ] The `packages/kailash-nexus/` suite exits on its own after printing its summary.
- [ ] `threading.enumerate()` at session finish shows no leaked non-daemon threads.
- [ ] A regression test under `packages/kailash-nexus/tests/regression/` asserts it.

---

## 2. kaizen-agents: discovery `except Exception` GRANTS access — authz fail-open needs a tracking issue

**Affected surface:**
`packages/kaizen-agents/src/kaizen_agents/patterns/discovery.py`, class
`UserFilteredAgentDiscovery`.

**The behaviour.** The `except Exception` path **grants access when the permission checker
itself errors** — an authorization fail-open. It is deliberately UNCHANGED on this branch.

**Why this issue exists, and what it is NOT.** The deferral is sound and reasoned, and its
regression suite
(`packages/kaizen-agents/tests/regression/test_silent_authz_and_routing_fallbacks.py`) is
exemplary — it scopes the exclusion explicitly, states the reason (flipping it means a
transient checker outage denies EVERY user), records that the path is already LOUD at ERROR,
notes the in-code deferral to its own security-reviewed change, and closes with _"Nothing
here should be read as having closed it."_

This issue is filed because `zero-tolerance.md` Rule 1b requires a deferral to be
distinguishable from a silent dismissal by a **tracking issue** — an in-code note alone is
weaker than that. **Do NOT flip the behaviour as a drive-by fix**; the outage-denies-everyone
trade-off is real and the change is security-reviewed work in its own right.

**Severity:** MEDIUM (deferred with sound reasoning; needs the tracking receipt).
**Category:** BUG (fail-open authorization), lane = tracked-deferral.

**Acceptance criteria**

- [ ] A decision is recorded on whether the checker-error path denies or grants.
- [ ] If it changes to deny, a degraded-mode path exists so a transient checker outage does
      not deny every user.

---

## 3. kaizen: `BaseAgent(description=...)` stale E2E test — git-proven pre-existing

**Affected API:** `kaizen.core.base_agent.BaseAgent.__init__`.

**Actual signature** accepts `config, signature, strategy, memory, shared_memory, agent_id,
control_protocol, mcp_servers, hook_manager, checkpoint_manager` — **no `description`**.

**Failure.** `packages/kailash-kaizen/tests/e2e/autonomy/test_full_integration_e2e.py::test_enterprise_workflow_integration`
→ `TypeError: BaseAgent.__init__() got an unexpected keyword argument 'description'`.

**Proven pre-existing, not branch-caused.** Discriminating check
`git diff --quiet origin/main...HEAD -- <path>` (exits 0 IFF unchanged; would have exited 1
had either moved):

- `packages/kailash-kaizen/src/kaizen/core/base_agent.py` → UNCHANGED on branch
- `packages/kailash-kaizen/tests/e2e/autonomy/test_full_integration_e2e.py` → UNCHANGED

Both unchanged ⇒ the failure reproduces identically on `origin/main`.

**Why it was not fixed in-branch.** The fix is a stale-test repair in a tree that cannot be
executed on this host (no LLM provider, no Docker, no `config/*.env`), so a fix could not be
verified RED→GREEN here, and `instrument-discipline.md` MUST-2 blocks shipping a fix whose
green cannot be established. Re-run on a provisioned host before `/release`.

**Severity:** LOW — a stale test, not a live product defect. **Category:** INVEST-NOW.

**Acceptance criteria**

- [ ] The test constructs `BaseAgent` with its real signature, or the signature gains
      `description` deliberately.
- [ ] Verified RED→GREEN on a host with a provider configured.

---

## 4. A kaizen test writes `kaizen_implementation_test.log` into the REPOSITORY ROOT

**Affected surface:** a test under `packages/kailash-kaizen/tests/` (the writer is not yet
pinned to a single file — identifying it is part of the fix).

**Symptom.** Running the kaizen tree creates an untracked **`kaizen_implementation_test.log`**
(0 bytes) at the repository root, timestamped mid-run, never tracked in git history.

**Why this is a defect, not housekeeping.** A suite that dirties the working tree (a) breaks
any sibling lane's `git status --porcelain` fingerprint in a shared checkout — this VOIDED an
entire run's numbers by protocol, the first time that guard fired; and (b) leaves a CI
checkout dirty, tripping any "working tree must be clean" release gate.

**Severity:** LOW-MEDIUM. **Category:** INVEST-NOW.

**Acceptance criteria**

- [ ] The writing test uses `tmp_path` (or a configured log dir), not the repo root.
- [ ] `git status --porcelain` is byte-identical before and after the kaizen tree runs.
