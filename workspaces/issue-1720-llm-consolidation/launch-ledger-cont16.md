# Launch Ledger — cont-16 (parallel burn-down waves)

Durable record of background agents spawned this session
(`orchestration-launch-ledger.md` MUST-1). **Match every completion notification
against this table BEFORE reacting** — a branch listed here is SELF-LAUNCHED, not
another session's work.

Base for every lane: `586062dbccd2aa6e46dfb7b57a6f9327a1eb9bd2` (main after #2061 + #2062 merged).
Worktree parent: `/Users/esperie/repos/kailash/build/.kailash-py-wt/`

## Wave 0 — PR queue cleared (done)

| PR    | Disposition                                    |
| ----- | ---------------------------------------------- |
| #2061 | MERGED (docs/sweep-wrapup; refreshed notes)    |
| #2062 | MERGED (proposals seed-org-token scrub)        |
| #2031 | LEFT DRAFT — two open gating questions (below) |

**#2031 is deliberately not merged.** Its PR comment carries two unresolved
questions: (a) baseline vs path-scoped scope, (b) it ships with no probe set /
eval-manifest entry, which `coc-artifact-eval-coverage.md` MUST-1 requires. Both
are decisions, not work items. Do NOT merge it as part of a burn-down sweep.

## Wave 1 — in flight

| lane | agent            | issue | branch                             | scope (file-disjoint)                       | status    |
| ---- | ---------------- | ----- | ---------------------------------- | ------------------------------------------- | --------- |
| w1a  | nexus-specialist | #2025 | fix/2025-workflow-server-auth-gate | `src/kailash/servers/**`                    | in-flight |
| w1b  | security-review+ | #2041 | fix/2041-secretmanager-ephemeral   | `src/kailash/gateway/security.py`           | in-flight |
| w1c  | pattern-expert   | #2060 | fix/2060-enterprise-auth-async     | `src/kailash/nodes/auth/**`                 | in-flight |
| w1d  | kaizen-spec.     | #2030 | fix/2030-baseagent-io-logging      | `packages/kailash-kaizen/.../base_agent.py` | in-flight |

**Disjointness verified:** four distinct directories, zero shared files. w1c owns
ALL of `nodes/auth/` (including `mfa.py`) so #2047 CANNOT be launched concurrently
— it is wave 2, after w1c lands.

## Wave 2 — in flight

| lane | agent              | issues            | branch                         | scope                  | status    |
| ---- | ------------------ | ----------------- | ------------------------------ | ---------------------- | --------- |
| w2a  | testing-specialist | #2002 #2038 #2023 | fix/2002-2038-2023-ci-coverage | `.github/workflows/**` | in-flight |

### USER-APPROVED decisions for w2a (do NOT re-litigate)

- **#2002 → gate on EVERY PR.** Approved with cost stated (~3-4 min/PR).
- **#2038 → make Tier-2 GATE; quarantine flakes INDIVIDUALLY** with `xfail(strict=True)`.
  Explicitly NOT allowed: widening #2029's threshold, or making the tier unfailable by
  another route.
- Standing policy retained: adding STEPS to existing workflows is approved; creating a
  NEW workflow file still requires asking the user first.

## Orchestrator-held work (done this session, not agent work)

| item                 | disposition                                                         |
| -------------------- | ------------------------------------------------------------------- |
| PR #2071             | MERGED-pending: `safe_http_detail` sweep scoped to first-party      |
| #2023 premise verify | HOLDS — `import kailash_ml` pulls **0** dataflow modules (measured) |

### Measured facts that CORRECT the issue bodies

- Root `tests/regression/`: **1,928 passed / 12 skipped / 0 failed, ~3m15s**.
  **#2002's "roughly 20 of these currently fail" is REFUTED by measurement.**
- Suite has GROWN since #2002 was filed: ~156 files / ~1,941 collected (not 142 / 1,566).
- `test_every_module_calling_the_helper_also_imports_it` took **379s** because it
  AST-parsed 78,152 files, **73,371 (94%) vendored `.venv`/site-packages**. Now 8.27s.

### Trap recorded — a timeout is not an assertion failure

I first read that test's FAILED line as a live regression on main and began hunting a
polluting test. It was neither. The captured traceback said
`Failed: Timeout (>120.0s) from pytest-timeout` — it was killed by the `--timeout=120`
flag **I** passed. Run without it: 20 passed. The lesson is the one this workspace keeps
re-learning: I had truncated the output with `tail -35`, which dropped the traceback and
left only the summary line, and a summary line cannot distinguish a timeout from an
assertion. **Read the FAILURES block, not the short summary, before naming a cause.**

## LIVE STATUS (update before reacting to any completion notification)

| PR    | issue(s)      | head        | CI                           | gate                                 |
| ----- | ------------- | ----------- | ---------------------------- | ------------------------------------ |
| #2063 | #2041         | `18fc196fb` | GREEN 13✓/4skip              | in adversarial + correctness review  |
| #2066 | #2060         | `63f239408` | GREEN 12✓/4skip              | in adversarial + correctness review  |
| #2068 | #2030 #2022   | `5d55d97ff` | GREEN 20✓/10skip             | needs review                         |
| #2071 | (#2015 sweep) | `1de9bf3ce` | GREEN 13✓/8skip              | needs review (orchestrator-authored) |
| #2064 | #2025 (Refs)  | `8a03ceb32` | CodeQL FAIL (deferred #2065) | release-specialist signoff in flight |

Extra lanes NOT spawned by me (spawned by w1d): **L2-kaizen-agents**. Recorded here so a
completion notification from it is not mistaken for an unknown/parallel session.

| lane | agent            | issue | branch                                 | scope              | status    |
| ---- | ---------------- | ----- | -------------------------------------- | ------------------ | --------- |
| w2b  | L2-kaizen-agents | #2070 | fix/2070-logging-hook-redaction-defeat | `hooks/builtin/**` | in-flight |

## USER DECISION — #2025 server-wide auth is FAIL-CLOSED

Approved: `require_auth=True` server-wide, raising at construction with no credential source.
**Sharded deliberately:** #2064 keeps proxy gate + `api/gateway.py` parity + channel plumbing
(`Refs #2025`); the breaking middleware lands as a SEPARATE shard off #2064's merged state
(`Fixes #2025`). Reason: #2064 already exceeds what one review pass holds, and a
"stops every deployment booting" change must not ride under a bugfix PR.

## The finding that reframed #2025

The proxy route was the **least** reachable instance. On a default `create_gateway()`,
`POST /workflows/{name}/execute` is anonymous arbitrary workflow execution. Cause:
`register_workflow` uses `app.mount(...)`, and FastAPI `Depends` does not reach a mounted
sub-application. Measured, discriminating:

    A app-level Depends  -> /direct 401 | mounted execute 200   <-- OPEN
    B middleware         -> /direct 401 | mounted execute 401   <-- closed
    B middleware + creds -> mounted execute 200                 <-- control

Also still open by default: signals, `/mcp/{name}/*`, `/durability/requests` (leaks
`client_ip`), `/ws`, `/metrics`, `/dashboard`.

## Cross-lane traps confirmed THIS session (broadcast to every new lane)

1. **`pytest.ini` sets `pythonpath = src` AHEAD of `PYTHONPATH`.** Comparing against another
   checkout via `PYTHONPATH` silently tests YOUR OWN tree. w1c got a false **20/20 pass**
   this way; the real result was 19-of-20 FAIL. Assert the resolved module `__file__`
   in-process — never trust the flag.
2. **Wiring a dormant audit sink is a DISCLOSURE change, not a logging change.** w1c's sink
   wiring nearly shipped the TOTP seed, `otpauth://` URI, and backup codes to the log in
   plaintext. Caught by adversarial review. Strictly worse than the unwired sink.
3. **`gh issue list --search` / `gh issue view` do NOT see comment threads.** Two agents
   mis-scoped work because the governing analysis lived in a COMMENT. Use `--comments`
   whenever the question is "is X already tracked?".
4. A test can be non-discriminating in BOTH directions: w1c found 3 of its own tests passed
   against the broken tree. Passing pre-fix is a defect in the test, not evidence.

## Follow-ups filed by lanes (do NOT lose)

#2065 (CodeQL deferral tracking) · #2067 (azure test red on main) · #2069 (`agent_config`
provider fail-open — ordering defect: allowlist validates BEFORE auto-detect assigns) ·
#2070 (logging-hook redaction defeat — now w2b's lane).

Unfiled, owed: the durable log-injection fix belongs in `SecurityEventNode.execute`
(`nodes/security/`) so every SDK caller is covered, not just `nodes/auth`. Also the
kaizen `security/encryption.py:16-26` ephemeral AES-256-GCM key on the default path —
same class as #2041 and **entirely silent**.

## Wave 3 — queued (launch as slots free)

| issue(s)              | scope                                       | note                               |
| --------------------- | ------------------------------------------- | ---------------------------------- |
| #2047                 | `nodes/auth/mfa.py`                         | BLOCKED on w1c (same dir)          |
| #2002 + #2038 + #2023 | `.github/workflows/**`                      | one lane — all three are CI config |
| #2018–#2021           | channel / MCP lifecycle                     | four issues, one area, one lane    |
| #2010 + #2011 + #2017 | kaizen small fixes                          | one lane                           |
| #2052 + #2039         | dataflow (defaults-as-SQL-text + isort)     | one lane                           |
| #2000                 | `PythonCodeNode` eager torch/sklearn import | perf                               |
| #2056                 | Nexus MCP FastMCP URI template              |                                    |
| #2057 + #2040 + #2044 | dead guards / log injection / codeql sinks  | one lane                           |
| #2029                 | flaky perf assert — do NOT widen threshold  |                                    |

## Traps carried into every lane brief

1. **Line numbers in issue bodies are STALE** (the #2028 import reorder shifted
   nearly every file). Anchor on grep-stable symbols; re-derive the line.
2. **`pytest -o pythonpath` is WHITESPACE-separated, not colon-separated.** A
   colon-joined value silently resolves the package from the MAIN checkout and
   produces a vacuous pass. Print the resolved `__file__` in-process; never trust
   the flag.
3. **Skipped is not passed** (Trap 9). Group check conclusions explicitly.
4. **Verify on the MERGED tree, not the lane worktree** (Trap 7).
5. An errored / empty test run is ZERO evidence, not a pass and not a failure.

## Concurrency governance

Cold start = 4 concurrent (`worktree-isolation.md` Rule 4 adaptive model). Back off
to waves of ~3 ONLY on the falsifiable throttle signal: ≥2 agents in the same wave
dying within a ~30–48s synchronized window carrying `(not your usage limit)`.
A single agent dying, an OOM, or a timeout is NOT that signal.

## Residue carried from cont-15

- **`lane-1c` worktree still INTACT** on `tmp/reword` with stale `UU` index entries
  from an abandoned reword. Everything in it is MERGED. Safe to remove; left for
  the owner rather than force-removed.
- A predecessor WIP commit still documents its own `--no-verify`. Rewording needs
  an interactive rebase across 15 commits; flagged, not risked.
- kaizen-agents 0.11.8 release staged but NOT cut (F-TESTHYG lazy checkpoint dir).
