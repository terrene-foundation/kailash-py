# Launch Ledger — Session I (2026-08-08)

Durable launch record per `orchestration-launch-ledger.md` MUST-1. Consult BEFORE every
spawn (MUST-2); match every completion against it BEFORE reacting (MUST-3).

## Entry state (verified this session, not relayed)

- Branch `fix/issue-1720-forest-drain` @ `7aeb61d5e`.
- `git rev-list --left-right --count origin/main...HEAD` → **6 behind, 161 ahead** (after
  `git fetch origin`). Session-H's "160 ahead" was measured at `d6c6cbb83`, one commit back.
- `gh pr list --state open` → **0 open PRs**.
- `gh issue list --state open` → **14**: #1970 #1971 #1972 #1974 #1981 #1995 #1997 #2000
  #2002 #2003 #2004 #2005 #2006 #2007.
- Working tree: 1 untracked file (`kaizen_implementation_test.log`, test-generated, left in
  place deliberately — deleting untracked files without confirmation is BLOCKED).

## Inherited open work (from `sweep-2026-08-08.md` §7)

Convergence counter is **ZERO**. Round 5 is INCOMPLETE: the test-contract lens ran Task 1
of 4; security hypothesis **D** is unresolved (E was resolved and became #2007).

## Wave 1 (dispatched 2026-08-08)

| track                                         | agent                 | scope                                                               | files it may write                                                    | status     |
| --------------------------------------------- | --------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------- | ---------- |
| round-5 test-contract Tasks 2/3/4             | `w1-rt5-testcontract` | ~37 unaudited test files; vacuous assertions; skip/xfail discipline | report only, NO source edits                                          | dispatched |
| round-5 security hypothesis D + finding-B fix | `w1-rt5-secD`         | finalizer warn-path leakage; uncoerced `HTTPTransport._rate_limit`  | `packages/kailash-nexus/src/nexus/transports/http.py` + its own tests | dispatched |
| nexus post-summary hang (116 threads)         | `w1-nexus-hang`       | root-cause the leaked non-daemon threads; fix                       | nexus runtime/server/fixture files EXCEPT `transports/http.py`        | dispatched |

**Partition rule for this wave:** `w1-rt5-secD` owns `transports/http.py`; `w1-nexus-hang`
owns everything else under `packages/kailash-nexus/`. `w1-rt5-testcontract` writes no source.
The git index is SHARED — every commit MUST use an explicit pathspec; `git add -A` is BLOCKED.

## Wave 2 (NOT yet dispatched — gated on wave 1)

- #2006 dataflow CREATE explicit-NULL (BUG queue rank 1 after the hang).
- One clean redteam round (counter ZERO; the #2007 fix re-touched the nexus surface, so any
  credit that surface held is void per `completion-criterion.md` MUST-3).
- PR body rewrite from re-derived numbers + merge `origin/main`.

## Pending human gate

Four findings remain UNFILED (nexus hang, authz fail-open tracking issue, kaizen stale-E2E,
repo-root log write). `gh issue create` is a shared-state action — surfaced to the co-owner
for a single batch approval; NOT filed unilaterally.

## Orchestrator-verified inline (not delegated, not relayed)

**Branch numbers, re-derived at the moment of writing** (not carried from session H):
`git rev-list --count origin/main..HEAD` → **161**; `git diff --name-only origin/main...HEAD
| wc -l` → **309**; `git diff --shortstat` → **309 files changed, 55866 insertions(+), 2334
deletions(-)**.

**Version anchors — 9/9 self-consistent.** Root `pyproject.toml` 2.63.0 ==
`src/kailash/__init__.py:116` `__version__ = "2.63.0"`. Packages: align 0.7.4 · dataflow
2.20.0 · kaizen 2.46.0 · mcp 0.5.0 · ml 2.2.3 · nexus 2.16.0 · pact 0.18.0 ·
kaizen-agents 0.13.0.

**The `origin/main` merge is CONFLICT-FREE — verified structurally, not assumed.** The 6
commits behind are three dependabot merges + their three bumps, touching exactly TWO files
(`.github/workflows/coc-hook-registration.yml`, `.github/workflows/project-automation.yml`).
`comm -12` of the two changed-file sets returns **EMPTY** — zero overlap with the branch's
309 files. (Falsifying result had it existed: `comm -12` would have printed the shared paths.)

### Issue→branch mapping — SIX issues have branch work but NO closure trailer

Only `Fixes #1996` and `Fixes #2007` appear in any commit body on this branch, yet:

| issue | commits mentioning | `issue_NNNN` test files |
| ----- | ------------------ | ----------------------- |
| #1970 | 5                  | 4                       |
| #1971 | 3                  | 4                       |
| #1972 | 3                  | 2                       |
| #1974 | 4                  | 6                       |
| #1981 | 7                  | 4                       |
| #2007 | 3                  | 1                       |

**This is a LEAD, NOT a closure verdict — and MUST NOT be written into the PR body as one.**
A commit mentioning `#NNNN` and a test file named for it are consistent with a FULL fix, a
PARTIAL fix, and a test that merely pins current behaviour. Per
`verify-claims-before-write.md` MUST-1 a `Fixes #NNNN` line is a durable claim needing
ground-truth verification per issue (read the issue's acceptance criteria, then verify each
against the code + a passing test). **Wave-2 work item: one verification pass per issue
before ANY closure trailer or PR-body claim.** Issues with zero signal (#2000 #2004 #2005
#2006) are untouched by this branch; #1995 #1997 #2002 #2003 have commits but no
`issue_NNNN` test file and need the same verification, not an assumption.

## Completions

_(appended as agents return — match agent id against the table above before reacting)_

- **`w1-rt5-testcontract` — 2026-08-08T12:27Z: signalled IDLE with NO report delivered.**
  Per `agents.md` § Redteam Reviewer Dispatch + `evidence-first-claims.md` MUST-3 that is
  ZERO evidence and MUST NOT be recorded as a clean lane. Session H recorded the identical
  pattern and that a SECOND explicit request extracts the report. Re-requested with an
  explicit per-task "NOT RUN" instruction. Status: **re-pinged, unresolved.**
- **`w1-rt5-testcontract` — DELIVERED on the second request.** All three tasks RAN.
  **10 findings (F1–F10).** The re-ping is what produced them: the idle signal would have
  been recorded as a clean lane and round 5 would have closed on nothing. Session H's
  "ask again before concluding a lane is dead" is now twice-confirmed.

### Round-5 test-contract findings — triage

Category per `product-completion-first.md`; gating per `completion-criterion.md` MUST-2
(BUG + INVEST-NOW converge; INCREMENTAL is budgeted and does NOT gate).

| id  | site                                                        | class                                                                                   | cat               | gates?  |
| --- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------- | ----------------- | ------- |
| F4  | `test_multi_database_e2e.py:508`                            | zero-assertion test logging "PRODUCTION READY", + a PytestWarning                       | **BUG**           | **YES** |
| F9  | `test_tools_list_permission_gated_schema_disclosure.py:396` | `skip` where `testing.md` mandates strict-xfail; ALSO disables the anti-vacuity CONTROL | HIGH / INVEST-NOW | **YES** |
| F1  | `test_key_extraction.py:555`                                | finds a key-extraction path, asserts nothing, records `pass`                            | HIGH / INVEST-NOW | **YES** |
| F5  | `test_mcp_cache.py:496`                                     | vacuous Redis arm + `MagicMock` in a Tier-2 tree                                        | MED / INVEST-NOW  | **YES** |
| F6  | `test_production_scenarios.py:598`                          | `assert True` in an else-branch — passes on 404                                         | MED / INVEST-NOW  | **YES** |
| F2  | `test_key_extraction.py:291`                                | class docstring asserts the opposite of the test                                        | MED / INCREMENTAL | no      |
| F3  | `test_constraint_gaming.py:966`                             | non-discriminating attack vector (probed: impl SAFE today)                              | MED / INCREMENTAL | no      |
| F7  | `test_mcp_cache.py:923`                                     | terminal `assert True`                                                                  | LOW / INCREMENTAL | no      |
| F8  | `test_key_extraction.py:438…504`                            | except-only asserts (probed: NOT live today)                                            | LOW / INCREMENTAL | no      |
| F10 | `test_key_extraction.py:317`                                | skipif marker contradicts its own docstring                                             | LOW / INCREMENTAL | no      |

**Favourable context, recorded so the findings are not over-read:** 3/3 xfails on this branch
are already `strict=True`; the `probe-unavailable:` skip pattern is used correctly; the branch
DELETED a pre-existing infinity/NaN defect-contract and replaced hand-rolled trust fixtures
with the real production path. Every finding clusters in PRE-EXISTING files the branch touched
for other reasons — NONE in the newly-authored regression suites.

## Wave 2 (dispatched 2026-08-08)

| track                                      | agent        | scope                                                                                                             | files it may write                                                                               | status     |
| ------------------------------------------ | ------------ | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------- |
| gating test-hygiene fixes F4/F9/F1/F5(+F7) | `w2-testfix` | delete the fabricated-verdict test; skip→strict-xfail; assert the key bound; de-vacuate + de-mock the cache tests | `packages/kailash-kaizen/tests/`, `packages/kailash-mcp/tests/`, `tests/integration/mcp_server/` | dispatched |

**F6 is EXCLUDED from `w2-testfix`** — it lives under `packages/kailash-nexus/`, owned
concurrently by `w1-nexus-hang`. It gates, so it is queued for dispatch the moment that
partition is released. NOT dropped.

| track                                  | agent                                          | scope                                                                                  | files it may write   | status     |
| -------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------- | ---------- |
| issue-closure verification (10 issues) | `w1-rt5-testcontract` (REUSED, not re-spawned) | per-issue verdict CLOSED / PARTIAL / PINS-ONLY / UNTOUCHED against acceptance criteria | **none — READ-ONLY** | dispatched |

**Second idle signal from `w1-rt5-testcontract` (12:30Z) matched against this ledger BEFORE
reacting** (`orchestration-launch-ledger.md` MUST-3): its track was already COMPLETE, so the
signal means "available", NOT "died". No re-ping, no duplicate spawn — the MUST-2 failure both
prior sessions committed. The agent was REUSED for the read-only verification pass because it
already carries the branch's test surface in context; a fresh spawn would re-derive it.

### `w1-rt5-secD` — DELIVERED. Hypothesis D **CONFIRMED**. Parity fix committed `1df4df166`.

**JOB 2 — CLOSED.** `HTTPTransport.__init__` now routes through the shared
`_coerce_rate_limit` (function-local import; `core.py` imports transports at module scope).
RED→GREEN quoted in the commit body. Full surface enumeration found **NO sixth fail-OPEN
surface** — the token-bucket family (`auth/rate_limit/decorators.py`, `middleware.py` route
overrides) fails CLOSED or loud on non-positive values.

**JOB 1 — hypothesis D SPLITS, and the split is the finding:**

- **(a) finalizer half — REFUTED**, with the enumeration that makes the refutation usable:
  all 6 finalizers on the changed surface checked; none logs at all; none interpolates
  sensitive material (class name / int port only). Zero `atexit`, zero `weakref.finalize`.
- **(b) degraded-WARN half — CONFIRMED. Two classes, 13 sites, 2 proven BEHAVIOURALLY**
  (the real code path was driven; the emitted record was read verbatim; controls run both
  ways). This is a genuine `security.md` § "No secrets in logs" violation, not a theory.

**LEAK 1 — `kaizen/nodes/ai/a2a.py:1940`.** The `a2a.summarize.llm_failed` degraded WARN
passes `"error": str(exc)` RAW. A connection error carrying provider credentials in its URL
reaches the log record intact. The SIBLING branch 20 lines up reads the already-sanitised
result-dict error — only the exception branch is raw. Control: the existing
`scrub_remote_error` / `sanitize_provider_error` helpers redact that exact string correctly,
so the fix is to route through them, not to invent a scrub.

**LEAK 2 — the "scrubbed message, retained traceback" class.** The message is scrubbed and
then `exc_info=True` re-leaks what the scrub removed, via the chained `__cause__` line.
**The branch's OWN comments state this reasoning** (`reasoning.py:1731`, `trace_exporter.py`:
"dropping exc_info is what stops the raw message re-entering via the traceback's final line")
and correctly applied it at **8 sites** — and missed these. That is the
`security.md` § Multi-Site Kwarg Plumbing / Enforcement-Surface Parity shape exactly: the
right fix applied at the primary sites, siblings left on the vulnerable path.

Sites (all were outside secD's original partition, hence the report-then-reassign):
`kaizen_agents/agents/autonomous/base.py:1320` · `runtime_adapters/{claude_code.py:250,
gemini_cli.py:312, kaizen_local.py:509, openai_codex.py:283}` (these four ARE the
provider-dispatch surfaces — highest priority) · `journey/{nexus.py:534, manager.py:481,
manager.py:1040, transitions.py:265}` · raw message AND traceback:
`delegate/print_mode.py:103` (its very next line returns `scrub_remote_error(exc)` — return
scrubbed, log not), `delegate/mcp.py:425`, `nexus/core.py:4178`.
Lower confidence (clean message, user-supplied callee traceback): `nexus/core.py:3389/3419/4748`,
`nexus/transports/websocket.py:678`.
REFUTED as clean: `nexus/sse.py:387` (DEBUG), `kaizen/__init__.py:59`, `fallback.py:391`,
`reasoning.py:618/636`, `_judge.py:667`, `trace_exporter.py:377/439`,
`ai_behavior_analysis.py:308`, `ai_threat_detection.py:328`.

**Reassignment (NOT a new spawn):** `w1-rt5-secD` re-partitioned OFF nexus and ONTO
`packages/kailash-kaizen/src/**` + `packages/kaizen-agents/src/**`, may create NEW files only
under those packages' `tests/regression/`. The nexus sites stay QUEUED behind `w1-nexus-hang`.
Security-critical ⇒ per `agents.md` § "Correctness-Review-Clean Is Not Security-Clean" this
fix needs an ADVERSARIAL security reviewer prompted to REFUTE it before it counts toward
convergence; a correctness-clean verdict does NOT discharge that.

### UNOWNED FLAKE — surfaced, root cause UNRESOLVED, deliberately not guessed

`tests/regression/test_endpoint_rate_limit_semantics.py::test_integral_float_rate_limit_is_accepted_and_enforced`
failed ONCE in a batch run. **Proven NOT caused by the parity fix** — passed with the fix
reverted, passed twice more with it applied, 6/6 isolated. Leading hypothesis is a
minute-window rollover at `nexus/core.py:2583`, explicitly NOT asserted. Owns to
`zero-tolerance.md` Rule 1; queued behind the nexus partition alongside the leak sites.

### ISSUE-CLOSURE VERIFICATION — DELIVERED. The mechanical scan was WRONG by two.

| issue | verdict    | ACs                   | note                                                                                                                                                                                                                                     |
| ----- | ---------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #1970 | **CLOSED** | 3/3                   | issue text is STALE — names `MultiProviderNode` in `nodes/ai/ai_nodes.py`; NEITHER exists. Real owner `KaizenAIModelNode` in `nodes/ai_nodes.py:1574-1600`. Correct this in the closing comment or the next reader is sent to a phantom. |
| #1972 | **CLOSED** | 3/3                   | BREAKING change, documented at `packages/kailash-nexus/CHANGELOG.md:28`. One named test was RENAMED — cite the rename or a reader greps and finds nothing.                                                                               |
| #1974 | **CLOSED** | 3/3 + AC-3 superseded | verified behaviourally; probe would have printed `*** LEAKED ***` on any miss                                                                                                                                                            |
| #2007 | **CLOSED** | 5/5                   | 13 passed                                                                                                                                                                                                                                |
| #1971 | PARTIAL    | 2/3                   | AC-2 needs a live PostgreSQL; all 4 legs skip on `POSTGRES_TEST_URL` unset                                                                                                                                                               |
| #1981 | PARTIAL    | 3/4                   | AC-3 **structurally** unreachable — see the conftest finding below                                                                                                                                                                       |
| #2003 | PARTIAL    | 1/3                   | only the no-regression AC holds; the 2x doubling is INTACT at `input_envelope.py:126` + `tracking/storage/database.py:463`                                                                                                               |
| #1997 | PINS-ONLY  | 0/4                   | strict-xfail present and XFAILing; probe confirms the key STILL LEAKS. The pin is the CORRECT disposition, not a defect.                                                                                                                 |
| #1995 | UNTOUCHED  | 0/4                   | **and MUST stay open** — its own AC-4 requires landing as its own PR. Closing it from this PR would violate the issue's own acceptance criteria.                                                                                         |
| #2002 | UNTOUCHED  | 0/3                   | no CI step added; root `tests/regression/` still named by only `trust-tests.yml:79-80`                                                                                                                                                   |

**THE SAFE `Fixes #` LIST IS FOUR, NOT SIX: #1970, #1972, #1974, #2007.** The mechanical
commit/test-file scan implied #1971 and #1981 were also closed; both are PARTIAL. Writing
their trailers into the PR body would have AUTO-CLOSED two issues with unmet ACs on merge —
the exact `verify-claims-before-write.md` MUST-1 failure the pass existed to prevent.
Non-closing `Refs #1971 #1981 #2003 #1997`; #1995/#2002 get NO reference at all.

**`Fixes #1996` is on the branch already and is UNAUDITED** — outside the verified ten.
Re-dispatched to verify; if it is not CLOSED the trailer is wrong and must be corrected.

**The #1972 shape did NOT recur.** One test's polarity WAS inverted
(`test_special_characters_in_name`: previously asserted register SUCCEEDS, now asserts it
RAISES) but that is AC-1's second disjunct, taken deliberately, with the validator at
`nexus/validation.py:138-201` wired at four call sites. The same diff also REMOVED a genuine
defect-contract that asserted `Nexus(rate_limit=-1)` is "accepted by constructor (no
validation)" — the exact literal from the Task-1 pattern, caught by the hunk's author.

### RETRACTED — "the kaizen tree cannot load `.env`" was WRONG. It is a deliberate COST GUARD.

**This supersedes the section below it, which is left in place as the corrected record.** The
lane that reported it retracted it on scoping, before anything acted on it.

`packages/kailash-kaizen/conftest.py:44` calls
`install_cost_guard(Path(__file__).resolve().parents[2] / ".env")`. `.env` IS loaded; provider
SECRETS are scrubbed on purpose. The module docstring states the intent: kaizen declares its
own rootdir so the repo-root guard never fires, and "a bare run MUST make ZERO billed LLM
calls, so this rootdir MUST withhold/scrub provider secrets."

**The recommended fix would have been HARMFUL.** Adding `load_dotenv` there disarms a working
cost control, and it is the DOCUMENTED anti-pattern:
`src/kailash/testing/env_cost_guard.py:14-24` names "Re-injection … dozens of test modules call
`load_dotenv()` at import scope" as defeat #2, and `install_dotenv_guard()` monkeypatches
`dotenv.load_dotenv` so every call re-scrubs after.

**Instrument lesson (`instrument-discipline.md` MUST-1, textbook case):** `grep -c load_dotenv`
→ 0 was a CORRECT count from a MISLEADING instrument. It answered "does this file call
`load_dotenv`" when the load happens via `install_cost_guard`. The count was real; the
inference was not. The falsifying result was never named before the claim was made.

Verified behaviourally after the correction: 6 secrets ABSENT after a guarded load
(`ANTHROPIC_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`, `AZURE_AI_FOUNDRY_API_KEY`,
`DEEPSEEK_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`), 6 non-secrets PRESENT (model names,
endpoints, API version). Fail-closed by name-shape, pops inherited keys, idempotent.
Every package declares its own rootdir — BY DESIGN, and the design is itself regression-pinned
by a `test_cost_guard_rootdir.py` in all 7 package trees.

**#1981 AC-3 verdict UNCHANGED — still unmet.** Only the CAUSE and the REMEDY change. The
designed opt-in is `KAIZEN_ALLOW_REAL_LLM=1`, which lifts both the scrub and the
`requires_real_llm` marker-skip. Cost if applied tree-wide: up to **142 of 162 skips** begin
executing, every one billable, many `e2e/` multi-agent with >1 call each. Cheapest sufficient
path for AC-3 alone: scope the opt-in to
`test_issue_1981_reasoning_structured_output.py::TestLiveProviderMatrix` — one Anthropic
completion. NOT run; co-owner's call.

### NEW FINDING — 10 kaizen failures are API DRIFT, NOT credential-shaped

Running the 33 env-gated kaizen files (precheck confirmed ZERO provider keys in ambient
`os.environ`, so nothing could authenticate or bill): **13 failed, 69 passed, 162 skipped**.
None of the 13 is credential-shaped. Verbatim:

```
AttributeError: 'SharedMemoryPool' object has no attribute 'add_insight'        [6 tests]
AttributeError: 'BufferMemory' object has no attribute 'clear_session'          [1]
TypeError: BaseAgent.enable_observability() got an unexpected keyword argum...  [1]
assert 'test_histogram_p50' in 'test_counter{operation="test"} 10000.0\ntes...  [1]
Failed: FAILED: execute_workflow_async() was NOT called!                        [1]
AssertionError: assert 0 > 0   (TestOllamaVisionIntegration x2)                 [2]
```

**Labelled as INFERENCE, not fact** (`evidence-first-claims.md` MUST-4): a credential cannot
conjure a missing method, so the 10 missing-attribute / wrong-signature failures would fail
IDENTICALLY with keys present. They read as real API drift. The 2 Ollama ones are genuine
infra (no local server).

**Why this matters beyond the count:** session H triaged 23 failures as "Tier 2/3
infra-dependent" and cleared them as non-blocking. These are a DIFFERENT run and a DIFFERENT
scope — NOT a claim that they are the same 23 — but if any of the 23 carried THIS shape, the
infra-dependent disposition was wrong for it, and a real API regression is sitting behind a
triage that reads as clean. **Dispatched to determine branch-caused vs pre-existing.**

### RESOLVED — all 5 API-drift failures are PRE-EXISTING STALE TESTS. Git-proven. Release NOT gated.

`git diff --quiet origin/main...HEAD` (exit 0 IFF unchanged) run across **9 paths** — the
source defining each symbol AND the test asserting it — returned UNCHANGED on all 9. Falsifying
result available and observed once: one file DID come back CHANGED and was chased (symbol 5).

| symbol                                                 | reality                                                                                                                                                                                                                                                                                                                                                                                                                                                | verdict      |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| `SharedMemoryPool.add_insight` (6 tests)               | renamed → `write_insight` (`shared_memory.py:66`); the rename predates this branch by the `apps/`→`packages/` migration                                                                                                                                                                                                                                                                                                                                | PRE-EXISTING |
| `BufferMemory.clear_session` (1)                       | renamed → `clear(session_id)` (`buffer.py:95`); left in the #75 structural split                                                                                                                                                                                                                                                                                                                                                                       | PRE-EXISTING |
| `BaseAgent.enable_observability(jaeger_endpoint=)` (1) | `jaeger_endpoint` split into `jaeger_host` + `jaeger_port` (`base_agent.py:840`). **4 call sites in the test; only 1 surfaced** — the other 3 skip on the missing key, so expect 3 more with credentials present                                                                                                                                                                                                                                       | PRE-EXISTING |
| `test_histogram_p50` (1)                               | emitter EXISTS and is correct (`metrics.py:295-307`, UNCHANGED); `record_metric` is not populating `_histograms`. **Attribution proven; MECHANISM deliberately left UNDETERMINED rather than asserted**                                                                                                                                                                                                                                                | PRE-EXISTING |
| `execute_workflow_async() NOT called` (1)              | the containing strategy module IS changed on-branch, so `--quiet` did not settle it and the DIFF was read: 2 hunks, both inside one `except`, both message-content only (`sanitize_provider_error`), **no control-flow change**. Real cause forced out with `--log-cli-level=WARNING`: `Missing required output field: answer` — an output-contract mismatch, invisible because the test wraps its own call in `except Exception: pass` (the F8 class) | PRE-EXISTING |

**NO PRODUCTION CALLER IS BROKEN — checked, not assumed.** The single `.add_insight(` call site
in production (`a2a.py:3857`) is on a DIFFERENT class (`A2ATask`, whose `add_insight` is defined
at `a2a.py:683`). Both `clear_session` production callers resolve to real definitions
(`persistence_backend.py:55` → `dataflow_backend.py:381`; `SimpleMemoryStore.clear_session:137`).
All sweeps used `--exclude-dir=build`.

**DISPOSITION: cleanup, NOT a regression. Does NOT gate the release.** Queued shape when taken:
the three renames (11 call sites total), the two genuine investigations (histogram routing; the
`answer` output-contract), and removing the `except Exception: pass` in `test_async_execution.py`
that made this cost a log-capture round to diagnose.

**Second self-correction from this lane, and it strengthens the record:** its earlier "none of
the 13 is credential-shaped" was sound for the four AttributeError/TypeError cases but
UNDER-EVIDENCED for symbol 5, where the swallowed exception hid the cause until the log was
forced. The claim survived; the reasoning behind it did not exist when it was made. Distinguishing
"the conclusion held" from "the evidence held" is the discipline `evidence-first-claims.md` MUST-4
asks for.

### PR-body correction — `Refs #1996`, not `Fixes #1996`

#1996 is CLOSED on the merits (all 4 ACs verified; the absence simulation poisons `sys.modules`
so the guard meets a REAL `ImportError`, not a mock) — but `gh issue view 1996 --json state` →
`CLOSED` ALREADY. A `Fixes` trailer on an already-closed issue is a no-op that reads as a fresh
closure. **Final trailer list: `Fixes #1970, #1972, #1974, #2007` + `Refs #1996`.**

### SUPERSEDED (retained for the record) — the original, incorrect `.env` reading

`grep -c load_dotenv packages/kailash-kaizen/conftest.py` → **0**; root `conftest.py` → **4**;
kaizen runs under `rootdir: packages/kailash-kaizen, configfile: pytest.ini`. So
`ANTHROPIC_API_KEY` — which IS present in `.env` — can never reach a test in that tree, in CI
or locally. #1981's AC-3 live-provider leg is therefore **structurally** unreachable, not
environmentally skipped. Falsifying result, stated: had the kaizen conftest loaded `.env` the
grep count would have been ≥1 and the leg would have run.

**Why this reaches past #1981:** session H triaged 23 failures across trees as
infra-dependent. If a tree cannot load `.env` AT ALL, a "no API key" failure in that tree has
a SECOND possible cause — the harness, not the environment — and the two are indistinguishable
from the failure text alone. NOT asserting that is what happened; scoping whether it COULD
have. Adding `load_dotenv` is NOT a unilateral call: it would start making billable outward
API calls locally. Cost picture first, then the co-owner decides.

### Hygiene — stale `packages/kailash-kaizen/build/lib/` shadows `src/`

`git ls-files packages/kailash-kaizen/build/` → **0 tracked files**, yet it contains a stale
`a2a.py` that a grep-based audit hits BEFORE `src/`. It already mis-answered one query this
session. Untracked ⇒ NOT deleted (deleting untracked files without confirmation is BLOCKED).

### `w2-testfix` — `d13668060` LANDED. "make four green tests actually discriminate"

F4 deleted (and its PytestWarning with it) · F9 split into its own test under
`xfail(strict=True)`, deliberately kept SEPARATE from the suppression assertion so the marker
cannot swallow a real disclosure regression · F1 now asserts the bound `InMemoryKeyManager`'s
OWN docstring states (no `str`/`repr`/`dir`/`pickle` surface carries the key; every holding
attribute is private) WITH an anti-vacuity control that the key is in `__dict__` at all ·
F5 moved `tests/integration → tests/unit` (it mocked Redis with `MagicMock`, which a Tier-2
tree forbids outright, and its own docstring already declared Tier 1).

Commit body states: **"No production code changed. Each new assertion was verified to red
under a mutation proven to reach the code under test."** That is `instrument-discipline.md`
MUST-2 satisfied explicitly — mutation shown to REACH the code, not merely applied.

### NEW PRODUCT DEFECT, surfaced BY the test-hygiene work — `UnifiedCache.clear()` NO-OPS ON REDIS

The F5 fix records it plainly: the Redis arm "called `clear()` with no assertion and passed
**because `clear()` silently no-ops on that path**", and the new test is
`xfail(strict=True)` **against the real no-op rather than pinning the stub as correct.**

That is not a test defect — the test was the only thing hiding it. A cache whose `clear()`
does nothing on its Redis backend serves STALE DATA INDEFINITELY after any invalidation, and
every caller believes the invalidation succeeded. The vacuous assertion is precisely why it
was never observed: the arm asserted only that `clear()` did not raise, and a no-op does not
raise.

**Category: BUG — it GATES convergence** (`completion-criterion.md` MUST-2). The strict-xfail
is the correct INTERIM pin (it self-clears on XPASS the moment `clear()` is implemented), but
a pin is not a fix. QUEUED for dispatch when a lane frees; owner is the `UnifiedCache` Redis
backend, no partition currently held over it.

**Meta-observation worth carrying to `/codify`:** this is the second time this session that
fixing a VACUOUS TEST surfaced a REAL DEFECT the vacuity was concealing (the first: the
removed `rate_limit=-1` "accepted by constructor" defect-contract, which would have BLOCKED
the fail-open fix that later shipped). Vacuous-assertion sweeps are not hygiene — they are
defect discovery with a lagging indicator.

### CREDENTIAL-LEAK FIX LANDED — `689f9ebd8`, 17 files, **18 sinks** (not the 13 scoped)

"scrubbing the message while keeping the traceback protected nothing". Scope grew TWICE, both
correctly and both within partition:

- **a2a.py had FOUR sinks of the proven class, not one** — 1940 (proven) plus the stage1/stage3/
  stage6 pipeline sinks at 2298/2431/2642, each wrapping `super().run(...)` in a broad
  `except Exception` and logging `str(exc)`. Each try-block verified to contain the provider
  dispatch BEFORE editing — not pattern-matched on the `except`.
- **THREE unlisted delegate sites** — `delegate/delegate.py:628`, `delegate/loop.py:748`, `:838`.
  `loop.py::run_turn` is what `print_mode.py` iterates, so **fixing print_mode alone would have
  left the same exception logged raw ONE FRAME EARLIER.** The "fixed the symptom, missed the
  caller" shape this class keeps producing.

**Helper swap, flagged for adversarial check.** `sanitize_provider_error` broke three existing
tests that legitimately pin `record.error` to the exception's own message (it prefixes
`"<surface> error: "`); all four a2a sinks switched to `scrub_remote_error`. The instinct was
right — the contract was right and the first choice wrong. But **if the two helpers do not
redact IDENTICALLY, the swap silently downgraded the fix to satisfy a test.** Independently
verified in the round below; this is precisely the shape a correctness-clean review misses.

**Carve-out pinned as a test, not left as prose:** the narrow `except (JSONDecodeError,
ValueError)` blocks in a2a were deliberately NOT touched (they wrap `json.loads` of the model's
own output, never `super().run()`), and that verdict is pinned so a later sweep cannot
"fix" them on pattern-match.

**Per-site verdicts on the lower-confidence group** (blanket-stripping was BLOCKED and was not
done): `exc_info` stripped at every touched site; diagnostic context retained as NAMED FIELDS
(handler name, tool name, server name, trigger description) rather than as tracebacks — which
preserves debuggability without the vector (`zero-tolerance.md` Rule 3 cuts both ways).

**STATED COVERAGE GAP, unprompted — the most credible thing in the report.** The four runtime
adapters + `mcp.py` + `loop.py` are FIXED but NOT regression-covered (reaching those sinks needs
a live CLI subprocess). The lane also DELETED an earlier adapter test of its own because it
invoked `module.logger.error` directly and **would have passed with the bug present**. A green
that proves nothing is worse than an acknowledged gap.

### ADVERSARIAL SECURITY ROUND DISPATCHED — `w3-secreview`, prompted to REFUTE

Required by `agents.md` § "Correctness-Review-Clean Is Not Security-Clean" before this counts
toward convergence. Diff materialized to `/tmp/leakfix-689f9ebd8.diff` (962 lines) because
`security-reviewer` is read-only with no Bash (`agents.md` § read-only reviewer
materialization). Eight numbered claims to break, notably: helper-equivalence after the swap;
a credential SHAPE the scrub patterns miss; whether the narrow-except carve-out holds; whether
any RETAINED named field is config- or attacker-controlled; and whether the new tests would
FAIL if their fix were reverted.

### WIDER SURFACE — ~30 sites, dispatched as a FRESH shard (NOT a follow-up issue)

The lane correctly declined to relabel it to fit the last shard. `autonomous-execution.md`
MUST-4 is doubly bounded — fix-now holds only while the gap fits ONE shard budget, and this
exceeds it. Disposition: a DEDICATED shard with its own budget NOW, rather than an issue nobody
reloads. Surface spans `kaizen/core/autonomy/**`, `tools/native/**`, `security/audit.py`,
`core/mixins/logging_mixin.py`, `interpretability/core.py`, `orchestration/runtime.py`,
`l3/event_hooks.py`, `mcp/catalog_server/server.py`, `nodes/rag/query_processing.py`.
Flagged as highest-care: the **logging mixin** (a multiplier — every consumer inherits it) and
the **audit sink** (where a redaction bug is least likely to be noticed, most damaging).

### ROOT CAUSE OF THE IDLE PATTERN — agents COMPLETE the work and fail to SEND it

`w3-secreview` volunteered it: _"my earlier round DID run to completion; I failed to send it
(wrote it as plain text instead of calling SendMessage)."_ That explains every
idle-without-delivery this session. **The work was never the problem; the DELIVERY step was.**

Consequences for orchestration, and this is the `/codify` item:

- An idle signal means "turn ended", NOT "nothing was produced" and NOT "work is done".
- Re-pinging is not nagging — it is the RETRIEVAL mechanism for work that already exists.
  Every re-ping this session returned substantial completed work on the first retry.
- Counting silence as a clean round would have discarded a completed 9-finding adversarial
  security review, a 10-finding test-contract report, and a confirmed credential-leak fix.
- Corollary for prompts: state the delivery mechanism explicitly, not just the deliverable.

### ADVERSARIAL SECURITY VERDICT on `689f9ebd8` — 9 findings, 2 HIGH. Convergence NOT yet met.

**The claim I most feared is CLEAN, and examined-clean rather than assumed-clean.** The helper
swap (`sanitize_provider_error` → `scrub_remote_error`) did NOT downgrade redaction: both call
`scrub_credentials(str(x))` against the SAME pattern list, same order, same anchoring, same
placeholder, and `redact_opaque_tokens=True` on BOTH — so the two shape-only rules catching
prefix-less credentials are ON in both. No pattern uses `re.MULTILINE`, so newline handling
cannot differ. The reviewer attacked it four ways (pattern-set, ordering, placeholder,
multiline) and failed. It ALSO independently verified the swap's justification was real:
`test_issue_1973...:518` is an exact equality the prefix genuinely reds.

| id  | finding                                                                                                                                                                                                                                                                                                                                                          | sev      |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| F1  | `manager.py:479` (+`:469`) `getattr(handler,"__name__",repr(handler))` — `handler` is CALLER-SUPPLIED; a `functools.partial` with a credential-bearing URL kwarg, or a dataclass with an `api_key` field, prints it verbatim via `repr`. Unscrubbed into the log AND the returned `.error`. **The commit re-opens its own leak class on the one field it kept.** | **HIGH** |
| F2  | `_SinkScan` advertises catching NEW unscrubbed sinks; it is blind to `exc_info`/`logger.exception` ENTIRELY and to the bare `%s`-arg form. **That blindness is WHY the #1970 sweep left all 11 CLASS-2 sinks.** The fixed class can recur silently.                                                                                                              | **HIGH** |
| F3  | Both sentinels are URL-userinfo shapes, which both presets redact — so a downgrade to `scrub_local_error` leaves all six tests GREEN while re-opening bare-AWS/32-hex shapes. The preset choice is unpinned.                                                                                                                                                     | MED      |
| F4  | Coverage gap is **10 sinks, not 7**, and the "needs a live CLI subprocess" reason is REFUTED — `ClaudeCodeAdapter.execute` reaches its except through one stub-able seam, the same technique already used for `PrintRunner`.                                                                                                                                     | MED      |
| F5  | Message surface still leaks: prefix-less 32–39-char alphanumeric key (no separator ⇒ no key-name rule fires); `token=`/`access_key=` (absent from the vocabulary); `%40`-encoded `@`. Pre-existing scrubber residuals.                                                                                                                                           | MED      |
| F6  | Traceback diagnostic GENUINELY lost at caller-supplied-code sinks; the mitigation `scrub_remote_error("".join(traceback.format_exception(e)))` (keeps frames, scrubs text) was not taken. `zero-tolerance.md` Rule 3 cuts both ways, as instructed.                                                                                                              | MED      |
| F7  | Commit body's "leaves everything else byte-identical" is FALSE — `redact_paths` differs (paths + Azure resource hostname). Fix the SENTENCE via a follow-up commit, never an amend (`git.md`).                                                                                                                                                                   | LOW      |
| F8  | MCP-**server**-supplied tool name unscrubbed into a log record — log injection, not exfiltration.                                                                                                                                                                                                                                                                | LOW      |
| F9  | `journey/errors.py:47` docstring TEACHES `logger.error(f"...{e}")` — the exact pattern the commit removes, in the module's own API docs.                                                                                                                                                                                                                         | LOW      |

**DISPATCHED F1+F2+F3 to `w1-rt5-secD` ahead of the ~30-site surface** — same class, same shard,
and F1 re-opens the leak TODAY (`autonomous-execution.md` MUST-4). F4–F9 are follow-ups.

**Attacks run that FAILED, recorded as examined-clean:** preset weakening on the credential
axis; pattern/ordering/placeholder/multiline divergence; provider exceptions reaching the narrow
JSON handlers; `super().run()` inside a narrow try (verified by line number in all 3 stages);
model-controlled operands echoing via `InsightType`/`Insight`; the unscrubbed sibling branch at
`a2a.py:1926` (premise verified at `llm_agent.py:1271`); IPv6-host DSN evading the URL rules;
vacuous new tests; real credentials in fixtures.

**Reviewer's own stated instrument boundary, honoured:** read-only toolset, NOTHING executed —
so the non-vacuity verdict is a reading of the mechanism, NOT a red-under-revert observation.
It named the falsifying result it would have needed. That boundary is why F3 matters.

### PATTERN — the idle signal is NOT a completion signal. Check the ARTIFACT.

Three idle-without-delivery events across two agents this session (`w1-rt5-testcontract`
12:27Z and 12:30Z, `w1-rt5-secD` 12:38Z), on top of the four session-H recorded. The signal
carries NO information about whether work was done — it fired identically when a full
10-finding report was pending delivery, when the agent was genuinely finished, and when an
assignment had not been started at all.

**The discriminating instrument is the artifact, never the signal** (`instrument-discipline.md`
MUST-1). For a fix assignment:

```bash
git log --oneline <base>..HEAD                 # commits, if any landed
git diff --stat -- <the agent's partition>     # unstaged work, if mid-flight
```

Falsifying result, stated: had the leak-cluster fix been started, ONE of those two would have
been non-empty. Both were EMPTY ⇒ not started ⇒ re-ping, do NOT record as delivered and do NOT
re-spawn (`orchestration-launch-ledger.md` MUST-2/3). Re-pinged with an instruction to commit
INCREMENTALLY so a budget exhaustion cannot lose the whole shard.

**This is the single highest-yield orchestration lesson of sessions G/H/I and belongs in
`/codify`:** an idle notification satisfies neither `agents.md` § Redteam Reviewer Dispatch's
ran-signal requirement nor `evidence-first-claims.md` MUST-3. Treating it as completion would
have silently dropped a confirmed credential-leak fix and a 10-finding report.

**Concurrency note:** this takes the session to 4 concurrent agents, one above the ~3
cold-start cap in `worktree-isolation.md` Rule 4. Deliberate: the falsifiable throttle signal
(≥2 agents dying inside ~30–48s carrying `not your usage limit`) has NOT fired in this session,
and that rule explicitly forbids preemptive over-serialization. The 4th lane is READ-ONLY, so
it holds no partition and a throttle-kill costs only its own re-run. Back off to ≤3 the moment
the signal appears.
