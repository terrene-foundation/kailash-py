---
owner: esperie
last_reconciled_sha: d6c6cbb83
migrated_from: .session-notes
---

# Session Notes — 2026-08-07/08 (session H)

Workspace `issue-1720-llm-consolidation`, phase 05-codify, branch
`fix/issue-1720-forest-drain` @ `d6c6cbb83` — **160 ahead of `origin/main`, 6 behind,
0 UNPUSHED, working tree clean.**

**NOTHING IS AT RISK.** Sessions F and G both closed with work that existed in only one
place. This one does not. Every commit is on the remote; the only untracked file is a
test-generated log left deliberately in place.

## Read first, in order

1. **`04-validate/sweep-2026-08-08.md`** — the CURRENT decision report. PCF-triaged queue,
   3 decision points, ordered next steps. **Start here.**
2. **`04-validate/launch-ledger-sessionH.md`** — this session's verified record: the
   corrections to the inherited numbers, the nexus-hang diagnosis, the #2007 investigation,
   the #1995 refutation, and my own errors. Long; § headers are navigable.
3. This file's **Traps** below before touching anything.

**SUPERSEDED — do not plan from these:** `sweep-2026-08-07.md` and `sweep-2026-08-07b.md`.
The first carries "161 ahead / 93 unpushed" measured against a local `main` seven commits
stale (real: 160 / 0). Both list blockers that are now closed.

## Landed this session

- **THE PUSH.** `03795208d..7b3d9ee77`, then `..d6c6cbb83`. Verified by comparing `rev-parse`
  on both sides, never an exit code.
- **All 3 dependabot PRs merged** — `876a3bf18`, `1be52aafd`, `c11dd4b5d`. Board EMPTY.
  #1990 needed `gh auth refresh -s workflow`. Residual noted honestly: #1988 touched the SAME
  workflow file and merged WITHOUT the scope; I never established why and did NOT guess.
- **#1998 + #2001 CLOSED** with SHA receipts, each confirmed an ancestor of the pushed branch
  BEFORE being cited (`handoff-completion.md` MUST-2).
- **#2007 filed, fixed, documented** — `ca56bf501` (fix) + `d85fa80f6` (changelog). See below.
- **Semver corrected** — `805d68179`.
- **#1995 root-caused; prep landed** — `d6c6cbb83`. See below.
- **All five test trees ESTABLISHED.** No UNESTABLISHED tree remains.

## #2007 — the trusted-proxy resolver was DEAD CODE

`extractors/middleware.py` ran a full RFC-7239 trust walk on every request and stored
`request._nexus_resolved_client_host`. **Repo-wide that attribute had exactly ONE mention —
the write.** Nothing read it. All four rate limiters hand-rolled the raw TCP peer, so
`Nexus(trusted_proxy_cidrs=…)` affected nothing and every caller behind a proxy shared ONE
bucket. Never a spoofing bypass (a peer cannot be forged — the old keying erred fail-SAFE);
an availability defect plus a dead operator-facing control. Pre-existing.

Fixed with ONE owner, `extractors/proxy.py::client_key_for_request`, called by all four sites.
RED→GREEN in two stages: helper absent → ImportError; **helper present but unwired → 3 failed
naming all four sites**; wired → 13 passed. Full tree 2605 passed / 0 failed = 2592 + 13.

**The load-bearing detail:** wiring reddened two PRE-EXISTING tests that asserted the CORRECT
behaviour — they failed only because `MagicMock` fabricates any attribute, so the helper saw a
Mock. **The fix was the CODE, not the tests.** `resolve_client_host` returns `Optional[str]`,
so the helper now requires `isinstance(host, str)`. **Both pre-existing tests pass UNMODIFIED**
(empty `git diff` on that file) — no assertion was moved to meet the implementation.

**#2007 is correctly still OPEN.** `Fixes #2007` auto-closes only at PR-merge to the default
branch; the fix is on this branch, not `main`. Verified. No action.

## Semver — Option A, scoped to the TWO packages where the claim was FALSE

`kailash` 2.63.0 and `kailash-kaizen` 2.46.0 are stable 2.x shipping changes their own entries
label `### Changed (BREAKING)`. Header claim replaced with the real contract (lockstep
versioning; pin exact if you need upgrade safety).

**`kailash-mcp` 0.5.0 and `kaizen-agents` 0.13.0 still claim semver and were LEFT ALONE
DELIBERATELY** — both are 0.x, and semver §4 makes no stability promise below 1.0.0, so a
breaking change in a 0.x minor is permitted and their claims are CORRECT. Do not "fix" them.

## #1995 — the issue's OWN diagnosis is REFUTED. Do not implement it as written.

Measured on `d6c6cbb83`, each run guarded so an invalid invocation cannot read as clean:

| config                                                    | files isort would change |
| --------------------------------------------------------- | ------------------------ |
| current (baseline)                                        | **1396**                 |
| narrow `known_first_party` — **the issue's proposed fix** | **1746 (WORSE)**         |
| `lines_after_imports = 2` — my hypothesis                 | **3962 (much worse)**    |

Classifying what isort actually rewrites over a 120-file sample: **2.5%** is the first-party
boundary the issue blames; 61.7% is blank-line counts with no first-party import involved;
35.8% is ordinary stdlib/third-party ordering.

**There is no config bug.** The config is sane; the code drifted from it because the gate that
would catch it is not run — and it is not run BECAUSE it reports ~1400 spurious modifications.
The drift feeds itself. Corrected diagnosis posted to the issue; the refuted acceptance
criterion is struck there.

**LANDED (`d6c6cbb83`, zero-conflict):** scaffold templates excluded from black+isort at
CONFIG level (not just the pre-commit hook, so a direct `black .` skips them too), plus the
missing `[tool.black]` section. `docs/development/templates/agent_test_template.py` carries
`{Placeholder}` tokens and is not valid Python; ONE unparseable file meant `black --check .`
could never exit 0 regardless of the rest of the tree. Measured: unparseable 1 → 0.

**NOT LANDED, with a concrete trigger:** the repo-wide reformat overlaps **57 files** with this
branch's own 308-file diff — both sides rewrite the same import blocks, the worst conflict
shape. **Trigger: after this branch merges.** Then `isort .` + `black .` in one mechanical
commit, own PR, acceptance = `pre-commit run --all-files` modifies 0.

## Convergence — counter is ZERO, and round 5 is INCOMPLETE

| Lane                                         | Status                                                         |
| -------------------------------------------- | -------------------------------------------------------------- |
| security REFUTE over the round-4 fix surface | A/B/C resolved; **D UNRESOLVED** (finalizer warn-path leakage) |
| test-contract / vacuous-assertion / xfail    | **ran Task 1 of 4** — Tasks 2/3/4 NEVER RAN                    |
| all five test trees                          | ESTABLISHED                                                    |

Also: `completion-criterion.md` MUST-3 — the #2007 fix TOUCHED the nexus surface, so any
clean-round credit that surface held is **void**.

Delegated lanes signal idle WITHOUT delivering; a SECOND explicit request works (that is how
the nexus report was obtained). **Ask again before concluding a lane is dead** — an empty
return is ZERO evidence, never a clean round.

## Test trees — all five ESTABLISHED, and the "UNESTABLISHED" mystery is SOLVED

| tree                             | result                                |
| -------------------------------- | ------------------------------------- |
| root `tests/unit/`               | 4798 passed, 4 skipped                |
| root `tests/regression/`         | 1567 passed, 2 skipped, 22 deselected |
| `packages/kailash-mcp/`          | 649 passed, 1 skipped                 |
| `packages/kailash-nexus/`        | **2605 passed, 14 skipped, 0 failed** |
| `packages/kailash-kaizen/tests/` | 156 passed, 10 failed, 48 skipped     |
| `packages/kaizen-agents/tests/`  | 3943 passed, 13 failed, 89 skipped    |

**All 23 failures are Tier 2/3 infra-dependent — ZERO outside `tests/deployment/`, `e2e/`,
`integration/`.** No LLM key, no Docker, no `config/*.env` here. One "failure" is the SDK
working: its SSRF guard correctly rejected a private-IP ollama endpoint. The single
non-environmental failure (`BaseAgent.__init__(description=…)`) is git-proven pre-existing —
both source and test unchanged vs `origin/main`.

**THE NEXUS SUITE COMPLETES AND THEN NEVER EXITS — 116 live threads, deterministic in BOTH
independent runs.** It prints its full summary in ~5 min, then hangs (`STAT=S`, `%CPU=0.0` —
blocked, not spinning) until killed. **This is why three trees read "UNESTABLISHED" for two
sessions:** every wrapper with a 10-min cap killed a run that had ALREADY finished and
reported. Session G's "contention" diagnosis was WRONG. **Fix before `/release`** — a suite
that succeeds then hangs consumes a CI job's whole budget and is reported as infra flake.
Branch-caused vs pre-existing UNDETERMINED (no `main` baseline; `py-spy` needs root on macOS).

## Root extras floors — PENDING BY DESIGN. Do not "fix" early.

`pyproject.toml` says so inline: floors stay at published versions until the sub-packages
publish, else release CI (which installs from PyPI) breaks. Raise AFTER the publishes, BEFORE
the core tag. **FIVE, not four:** dataflow 2.19.1→2.20.0 · nexus 2.15.0→2.16.0 ·
kaizen 2.45.0→2.46.0 · **kaizen-agents 0.12.0→0.13.0** · ml 2.2.2→2.2.3.

## PR body — MUST NOT be opened as written

`04-validate/pr-body-draft.md` asserts **"Convergence was reached."** FALSE. Also carries stale
counts, a stale "round 3" gate, an incomplete filed-issues list, and mis-classifies #1998 as
carried. Rewrite AFTER convergence; merge `origin/main` (6 behind, no conflict — this branch
touches no workflow file) at the same time.

## Traps

- **`.venv/bin/python -m pytest` ALWAYS**; `--timeout=120`. Bare python dies at conftest with
  `ImportError: Node`.
- Root `tests/` and `packages/kailash-nexus/tests/` **cannot** be collected together (duplicate
  basenames); `kailash-kaizen` and `kaizen-agents` likewise. **Run trees separately.**
- **A tree path is NOT a test path.** `packages/kailash-kaizen/` collects `examples/`, which
  needs a LIVE LLM key. **Scope to `…/tests/`.**
- **Pass `-p no:cacheprovider`** on any fingerprinted run, or pytest writes `.pytest_cache` and
  perturbs the fingerprint being read.
- **A kaizen test writes `kaizen_implementation_test.log` into the REPO ROOT** — breaks the
  fingerprint protocol and dirties a CI checkout. Left in place; deleting untracked files
  without confirmation is BLOCKED.
- Clear `__pycache__` before kaizen runs. Never delete `.git/index.lock`.
- `cd` PERSISTS between Bash calls — use absolute paths.
- **NEVER `git checkout --` / `reset` / `stash` / `clean`** in a shared tree.
- Commit with a PATHSPEC (`git commit -F <msg> -- <paths>`); the index is shared. A pathspec
  commit must still leave HEAD GREEN.
- **`pkill -f pytest` is worse than "kills sibling suites."** This host runs ~10 concurrent
  pytest suites for OTHER operators across four unrelated repos. **Kill by EXACT pid with a
  verified ppid.**
- **GitHub secret-scanning unblock URLs ROTATE on every push attempt**, and the page is a FORM
  (pick a reason, confirm) — visiting does nothing. Ask whether the forms are submitted, THEN
  push; a speculative retry invalidates the links the co-owner is about to use.

## THE DURABLE LESSON — ten non-discriminating instruments this session

Session G recorded eight. Session H hit **ten more**, all caught before reaching a durable
artifact. The rate is NOT falling, which is the datum: this is the dominant failure mode of
the work, not a phase it is passing through.

| #   | Instrument                                    | Why it could not discriminate                                                                                                                                                                                                                                         |
| --- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `^__version__ =` grep                         | silent for BOTH "no anchor" and "anchor via `_version.py` indirection"                                                                                                                                                                                                |
| 2   | `^kailash[\w-]*` over root extras             | reported 4 stale floors; real count **5** — `kaizen-agents` lacks the prefix                                                                                                                                                                                          |
| 3   | `git log origin/main..HEAD` on a stale `main` | 7 commits behind ⇒ "161 ahead". **Fetch before you count.**                                                                                                                                                                                                           |
| 4   | `gh pr view --json merged`                    | not a valid field — ERRORS, and an errored command is zero evidence, not a "no"                                                                                                                                                                                       |
| 5   | unquoted `grep --include=*.py` under zsh      | glob failure returns nothing, indistinguishable from "no matches"                                                                                                                                                                                                     |
| 6   | `git push … \| tail` exit status              | reports `exit=0` on a REJECTED push — the PIPE's code, not git's                                                                                                                                                                                                      |
| 7   | pytest `EXITCODE` on the nexus tree           | `143` on a run that passed 2592 tests — the SIGTERM to the hang                                                                                                                                                                                                       |
| 8   | the IDE/pyright diagnostics feed              | kept reporting a syntax error after the file was fixed and parsing cleanly                                                                                                                                                                                            |
| 9   | `head -28` on an isort diff                   | truncated a 1-hunk answer into a wrong root-cause reading                                                                                                                                                                                                             |
| 10  | **`isort --known-first-party` — the worst**   | **not a real flag.** argparse aborted before scanning; the file-count grep read the empty output as **"0 files — completely fixed"**, which would have justified a wrong 1,397-file change. Caught ONLY because a single-file check contradicted the tree-wide count. |

**Four transferable rules, ordered by how often they bite:**

1. **State the PATTERN, not just the count.** "N sites swept" is a claim about what the pattern
   could MATCH, never about the code. Say what it could not have matched.
2. **An errored or empty command is ZERO evidence, never a negative result** (#4, #5, #6, #10).
3. **Read the ARTIFACT, not the status.** Exit codes, IDE diagnostics, and `--json` fields are
   one indirection away from the thing you care about (#6, #7, #8).
4. **Fetch before you count** (#3). And **never `head` a diff you are diagnosing from** (#9).

**The best reasoning in this record is not mine.** The nexus lane refused to attribute the
post-summary hang to this branch merely because a topically-adjacent test existed —
_"adjacency is not evidence."_ That is the standard.

## Next steps, in order

1. **File the four UNFILED findings** — the nexus hang, the untracked authz fail-open
   (discovery `except Exception` grants access), the kaizen stale-E2E test, the repo-root log
   write. Evidence is freshest now and three took real effort to establish.
2. **Finish round 5** — test-contract lens Tasks 2/3/4 + security hypothesis D — then ONE
   clean round. Counter ZERO; the nexus surface was re-touched.
3. **Fix the nexus post-summary hang** before `/release`; capture a `main` baseline + a thread
   dump (needs root on macOS).
4. **Rewrite the PR body** from re-derived numbers, merge `origin/main`, open the PR.
5. **`/release`** — mcp 0.5.0 → kaizen 2.46.0 → kaizen-agents 0.13.0 → dataflow/nexus/ml →
   kailash 2.63.0 LAST. Raise the FIVE extras floors between sub-package publishes and the tag.
6. **After the branch merges:** the #1995 repo-wide reformat, own PR.
7. BUG queue — **#2006 first**.

**Owed to the co-owner:** nothing outstanding. Both gates from the previous sweep (#1995
disposition, semver policy) were answered this session and are discharged.
