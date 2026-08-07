# Launch Ledger — Session H (2026-08-07)

Durable per `orchestration-launch-ledger.md` MUST-1. Consult BEFORE every spawn;
match EVERY completion notification against a row before reacting.

## Entry state (verified, not relayed)

- branch `fix/issue-1720-forest-drain`; **94 unpushed** vs `origin/fix/issue-1720-forest-drain`
  (03795208d); 155 ahead of `origin/main`; working tree CLEAN (`git status --porcelain` empty).
- Push BLOCKED on GitHub secret-scanning allowlist — co-owner action, not agent-executable.
- Convergence counter ZERO (round 4 NOT clean; 2 branch-caused regressions fixed).
- 3 test trees UNESTABLISHED: nexus, kaizen-agents, kaizen regression.

## Wave 1 (dispatched 2026-08-07)

| track | agent | branch | status |
| ----- | ----- | ------ | ------ |
| nexus suite re-establish | w1-tests-nexus | (none — read-only, shared tree) | in-flight |
| kaizen + kaizen-agents suites | w1-tests-kaizen | (none — read-only, shared tree) | in-flight |
| issue/PR ground-truth recon | w1-recon | (none — read-only) | in-flight |

Read-only lanes: NO worktree (worktree-isolation Rule 1 targets editing/compiling agents).
Every lane is FORBIDDEN to mutate any tracked file and MUST run the fingerprint protocol.

## Wave 2 — redteam Round 5 (dispatched 2026-08-07)

Lens ROTATION is mandatory (`completion-criterion.md` MUST-4). Rounds 2–4 ran
correctness / parity / instrument lenses. Round 5's two lenses are NEW:

| track | agent | lens | status |
| ----- | ----- | ---- | ------ |
| adversarial security REFUTE over round-4 fix surface | w2-rt5-security | security (mandated: `agents.md` § Correctness-Review-Clean Is Not Security-Clean — the rate limiter is a fail-closed gate) | in-flight |
| test-suite-as-defect-contract + vacuous-assertion + xfail discipline | w2-rt5-testcontract | test-contract (NEW; motivated by `98e83dfbe` having to update a test that pinned the fail-open as intended) | in-flight |

## Orchestrator-verified inline (not delegated, not relayed)

- **Version anchors: all 9 packages CONSISTENT.** kailash 2.63.0 · dataflow 2.20.0 ·
  kaizen 2.46.0 · mcp 0.5.0 · nexus 2.16.0 · pact 0.18.0 · kaizen-agents 0.13.0 ·
  ml 2.2.3 · align 0.7.4 — each `pyproject::project.version` equals the imported
  `<pkg>.__version__`. `zero-tolerance.md` Rule 5 satisfied.
  - **Instrument note (recorded because it is the session's own lesson):** the FIRST
    check — a literal `^__version__\s*=` grep over `src/*/__init__.py` — reported
    ml and align as missing an anchor. That was a NON-DISCRIMINATING instrument: both
    packages re-export from a `_version.py` (`kailash_ml/__init__.py::__version__`,
    `kailash_align/__init__.py::__version__`), so the grep's silence was consistent with
    BOTH "no anchor" and "anchor via indirection". The API-surface check
    (`import <pkg>; print(<pkg>.__version__)`) discriminates, and it says OK.
    The grep finding was withdrawn before it reached any durable artifact.

## Root extras floors — VERIFIED PENDING, deliberately, NOT a defect

`pyproject.toml` lines above the pin block state the intent verbatim: *"these floors
stay at currently-published versions in this release-prep commit; raise in the
follow-up commit after dataflow/nexus/kaizen/kaizen-agents/ml publish, before the
kailash core tag."* Raising them NOW would break release CI, which installs from
PyPI before the new versions publish. **Do not "fix" these before the publishes.**

Exact post-publish raise list (local version is the target floor):

| dep | current floor | raise to | sites |
| --- | ------------- | -------- | ----- |
| kailash-dataflow | >=2.19.1 | >=2.20.0 | `[dataflow]`, `[all]` |
| kailash-nexus | >=2.15.0 | >=2.16.0 | `[nexus]`, `[all]` |
| kailash-kaizen | >=2.45.0 | >=2.46.0 | `[kaizen]`, `[all]` |
| **kaizen-agents** | **>=0.12.0** | **>=0.13.0** | `[all]` |
| kailash-ml | >=2.2.2 | >=2.2.3 | `[ml]`, `[all]` |

Already current, no action: kailash-align 0.7.4 · kailash-pact 0.18.0 · kailash-mcp 0.5.0.

**Instrument note — a second non-discriminating pattern, caught before it shipped.**
The first sweep used `^kailash[\w-]*` and returned a 4-row answer. `kaizen-agents`
does NOT carry the `kailash-` prefix, so the pattern could not match it and its stale
floor was INVISIBLE — the sweep would have reported "4 floors to raise" and the release
would have shipped `[all]` pinning `kaizen-agents>=0.12.0` against a published 0.13.0.
The real count is FIVE. Stated per the session's own rule: *"N sites swept" is a claim
about the PATTERN, not the code* — the pattern here could not match a sibling package
whose name does not share the prefix.

## CHANGELOG release-readiness — VERIFIED, all 7 releasing packages

Each releasing package's CHANGELOG carries a heading for the version its
`pyproject.toml` declares: mcp 0.5.0 · kaizen 2.46.0 · kaizen-agents 0.13.0 ·
dataflow 2.20.0 · nexus 2.16.0 · ml 2.2.3 · kailash 2.63.0.

**STALE NOTE RETIRED — the kaizen CHANGELOG anomaly no longer exists.** The
2026-07-25 session notes flagged `packages/kailash-kaizen/CHANGELOG.md` as carrying
a SECOND Keep-a-Changelog preamble plus a stranded EMPTY `## [Unreleased]` heading
mid-history (~line 1550), and deliberately left it for a dedicated pass. Re-derived
against the current tree: the file is 2810 lines, with exactly **ONE** `Keep a
Changelog` preamble (line 5) and exactly **ONE** `## [Unreleased]` heading (line 8).
It was repaired somewhere in sessions D–G. **Do not schedule the restructuring pass.**
Recorded per `wave-loop.md` MUST-7 — an open note is not an undone item, and acting
on this one would have burned a shard chasing a defect that is not there.

## Branch position — CORRECTED. Every session-G artifact says "161 ahead"; the true figure is 155.

Post-`git fetch --prune`, re-derived:

| Quantity | Verified value |
| -------- | -------------- |
| `origin/main` tip | `26a4509b4` (unchanged by the fetch) |
| ahead of `origin/main` | **155** |
| BEHIND `origin/main` | **0** — nothing to rebase; `merge-base == origin/main` tip |
| unpushed vs `origin/fix/issue-1720-forest-drain` | **94** |
| files changed vs `origin/main` | 301 |

**Root cause of the 161.** Local `main` is **7 commits behind** `origin/main`
(`git rev-list --left-right --count main...origin/main` → `0  7`), and the remote-tracking
ref had not been fetched since 2026-08-03. Counting against the LOCAL `main` yields 162;
against the real remote base, 155. Session G's `.session-notes.d/esperie.md`, its
`sweep-2026-08-07.md` header, and its §7 process-hygiene row all carry the inflated figure.
The PR body MUST cite 155 — the count a reviewer reproduces is the one against `origin/main`.

## PR body draft — MUST NOT be opened as written

`04-validate/pr-body-draft.md` carries claims that are FALSE as of now. Opening the PR with
this body would put an unverified durable claim on a public surface
(`verify-claims-before-write.md` MUST-1).

| Draft claim | Status |
| ----------- | ------ |
| "**Convergence was reached** by rotated-lens redteam rounds" (§ Verification) | **FALSE.** Round 4 was NOT clean — 2 branch-caused regressions. Counter is ZERO. `completion-criterion.md` MUST-4: a cap-stop is abnormal termination, never done. |
| "round 3 rotated to cross-lane composition" — implies 3 rounds total | **STALE.** Rounds 4 and 5 exist; round 5 is in flight. |
| Header gate: "do not open until round 3 reaches convergence" | **STALE** — the gate is now round 5 + one clean round. |
| root `tests/regression/` "1566 passed, 2 skipped, 22 infra deselected" | **STALE by one.** Re-derived collection = **1591**, which reconciles exactly with the sweep's `1567 + 2 + 22`. The draft's 1566 does not reconcile. |
| "`kailash-mcp` regression 515 passed, 1 skipped" | **SCOPE-AMBIGUOUS, not necessarily wrong.** Whole-package collection re-derived = **650**, reconciling with the sweep's `649 + 1`. The draft's 515 names a *regression subset*, a different denominator — it must be re-derived or re-scoped, NOT silently replaced with 649. |
| "#2002 — 1,564 of 1,566 tests never run" | **STALE denominator** (1591 collected). Re-derive before citing. |
| "Filed during this work: #2001, #2002" | **INCOMPLETE.** Session G also filed #2003 #2004 #2005. |
| "Closes #1996 (delivered by `45ccac417`)" | #1996 is confirmed CLOSED — re-verify the SHA still resolves before citing publicly. |

**Disposition: rewrite the body AFTER round 5 + one clean round, and after the three
UNESTABLISHED trees report.** Not before — every number above moves.

## Round 5 — orchestrator lane: hunted a 7th enforcement-surface-parity instance. NOT FOUND. Surface is correctly guarded.

Reported in full including the dead end, because a suspected finding that dissolves
under verification is the outcome this branch has most often got WRONG in the other
direction (four wrong orchestrator fix-recommendations in session G).

**The hunt.** `_public_tool_view`'s docstring names THREE surfaces that must route
through it. An AST-independent sweep of `_tool_registry` enumerations found FOUR in
`server.py` plus one in `discovery/registry_integration.py` — apparently two unaccounted.

**Every one is already dispositioned.** `packages/kailash-mcp/tests/regression/test_gated_tool_invocation_requires_credentials.py::test_every_registry_enumerator_is_accounted_for`
re-derives the enumerator set **from the AST at PACKAGE scope** (`root.rglob("*.py")`),
NOT a hand-list, and pins each with a disposition:

| site | disposition |
| ---- | ----------- |
| `server.py::_handle_list_tools` / `::_handle_completion_complete` / `::run_stdio` | caller-facing → route through `_public_tool_view` (verified: all three call it) |
| `discovery/registry_integration.py` | caller-facing, names-only → filters `disabled` (correct: `_public_tool_view` also preserves name+description for a GATED tool; it returns `None` only for DISABLED) |
| `server.py::get_tool_stats` | operator/in-process; no JSON-RPC method dispatches to it (grep: `get_tool_stats` is referenced only by `get_server_stats`, never registered as a tool nor reachable over a transport) |

Companion `::test_public_tool_view_is_the_only_projection_builder` forbids any hand-written
`inputSchema` dict. **Both tests PASS** (`2 passed, 49 deselected`). This is precisely the
machine-derived denominator `conformance-walk.md` MUST-3 requires — the prior session got
this right.

**Non-dict fail-open: UNREACHABLE.** `registry_integration.py`'s
`not (isinstance(info, dict) and info.get("disabled", False))` emits the name when `info`
is not a dict. There is exactly ONE writer to `_tool_registry` (`server.py:2177`,
`self._tool_registry[tool_name] = {`), always a dict literal — so the branch is dead today.
Latent only.

### The one real residual — LOW, LATENT: the guard's AST pattern has four named blind spots

The guard matches `<attr>._tool_registry.<items|keys|values>()`. It requires the receiver to
be an `ast.Attribute`, so it CANNOT match a fifth enumerator written as:

| form | why the pattern misses it |
| ---- | ------------------------- |
| `for name in self._tool_registry:` | bare iteration — no `.items/.keys/.values` Call node |
| `self._tool_registry.copy().items()` | receiver is a `Call`, not an `Attribute` |
| `reg = self._tool_registry; reg.items()` | receiver is a `Name` local alias, not an `Attribute` |
| `dict(self._tool_registry)` / `list(...)` then enumerate | no attribute access on the mapping at the enumeration site |

**Verified NONE of the four exists in the package today** (four greps, each reported above,
all empty) — so this is a LATENT gap, not a live bypass, and it does NOT reset the
convergence counter. Stated per the session's own rule: *"N sites swept" is a claim about
the PATTERN, not the code* — here the guard's own pattern is the claim, and these are the
inputs it could not have matched.

Recommended disposition: **INCREMENTAL / deferred-quality**, not a blocker. Widening the
matcher to include `ast.Name` and `ast.Call` receivers plus bare `ast.For` iteration is a
~10-line change to a test, and it belongs in the same shard as any future MCP discovery
work rather than in a 155-commit release branch.

## Round 5 — SECURITY lens, run by the orchestrator after all four delegated lanes returned nothing

Four lanes (2 suites + 2 round-5 lenses) signalled idle WITHOUT delivering, across three
rounds of pings. Per `agents.md` § Redteam Reviewer Dispatch + `evidence-first-claims.md`
MUST-3 that is ZERO evidence, never a clean round. Instrument switched: run it directly.

### A — surviving fail-OPEN input to `_rate_limit`: **REFUTED**

`nexus/core.py::_coerce_rate_limit` fails CLOSED on every unexpected shape. Enumerated:

| input | path | outcome |
| ----- | ---- | ------- |
| `None` | early return | None = unlimited (documented) |
| `True` / `False` | `isinstance(value, bool)` | **raises** — and this matters because `isinstance(True, int)` is True in Python, so an uncoerced `True` WOULD read as 1 req/min at the consumer |
| `float('nan')`, `float('inf')` | `isinstance(float)` → `.is_integer()` is False for both | **raises** |
| `50.0` | integral float | accepted → `int()` (deliberate: JSON/YAML/env configs deliver `50.0`) |
| `0.5` | non-integral float | **raises** (`int(0.5) == 0` would have been unlimited) |
| `Decimal`, `str`, numpy scalar | `not isinstance(value, int)` | **raises** |
| `-5`, `-0.0`→`0` | `value < 0` / `value or None` | raises / unlimited-as-documented |

Consumer `nexus/sse.py::_rate_limit_exceeded` guards `not isinstance(rate_limit, int) or
rate_limit <= 0 → return False` (no limit). That is fail-OPEN by construction, which is
exactly why the coercion must hold at every write — and it does.

### B — "four write surfaces": a **FIFTH exists and is UNCOERCED**. Latent, NOT live.

`nexus/transports/http.py::HTTPTransport.__init__` writes **`self._rate_limit = rate_limit`
RAW** from an `Optional[int] = 100` kwarg — no `_coerce_rate_limit`. It is the same attribute
NAME the enforced path reads.

**Why it is not exploitable today** (each verified, not assumed):
1. `HTTPTransport._rate_limit` is **write-only** — `grep -n "_rate_limit"` over that file
   returns the single assignment and no read.
2. The only duck-typed reader is `sse.py::_rate_limit_exceeded`'s
   `getattr(nexus, "_rate_limit", None)`, and its owning `sse.py::register_sse` is typed
   `nexus: "Nexus"`. Both internal callers pass a Nexus: `core.py::Nexus.register_sse`
   passes `self`, and `sse.py::register_sse_endpoint` is itself typed `nexus: "Nexus"`.
   No internal path routes an `HTTPTransport` there.

**Why it is still worth recording (LOW / INCREMENTAL):** the attribute is uncoerced, carries
the SAME name as the enforced one, and the sole reader reaches it by `getattr` duck-typing
rather than by type. `register_sse` is in `sse.py::__all__`, so the composition
`register_sse(<an HTTPTransport>, ...)` is expressible by a caller; the guard against it is
a type ANNOTATION, which does not execute. A negative on that path yields `-5 <= 0 → return
False` — silently unlimited: the precise fail-OPEN shape `98e83dfbe` set out to eliminate.

Recommended disposition: route the `HTTPTransport.__init__` write through
`_coerce_rate_limit` (one line, same fix as the other four), OR delete the dead attribute.
Do NOT ship it as-is on the reasoning "it is never read" — that is a reachability argument,
and the enforcement-surface-parity class on this branch has now been the SIXTH-most-repeated
defect precisely because reachability arguments went stale.

**C** — post-coercion mutation: `plugins.py` coerces at the WRITE (not in `__init__`),
which correctly closes the public-mutable `requests_per_minute` path. A direct
`nexus._rate_limit = -5` remains possible but is a private attribute; not a defect.

**D / E** (finalizer warn-path leakage; rate-limit KEYING per-principal vs IP-spoofable)
— **NOT INVESTIGATED. Explicitly UNRESOLVED**, not clean. E is the more valuable of the two:
the limiter keys on `request.client.host`, so a proxied deployment without a trusted
X-Forwarded-For chain shares one bucket across all clients. Carry to the next round.

**ROUND 5 IS NOT COMPLETE.** One lens (test-contract) never ran at all; D and E are open.
Convergence counter remains ZERO.

## nexus tree — ESTABLISHED (lane `w1-tests-nexus`, fingerprint-verified)

```
2592 passed, 14 skipped, 14 warnings in 302.34s (0:05:02)
```
Zero failures, zero errors, zero collection errors. `grep -cE "FAILED|ERROR|^E "` → 0.
BEFORE/AFTER `git status --porcelain` fingerprint IDENTICAL (sha256
`854f1ad8…`), captured at three checkpoints; `-p no:cacheprovider` was passed so pytest
could not write `.pytest_cache` and perturb it. **VALID** — supersedes UNESTABLISHED.

**Count reconciliation (the lane did this rather than hand-waving the delta):** collection
reported 2605; the summary sums to 2606. Per-test progress characters are 2592 `.` + 13 `s`
= 2605, matching collection exactly; the extra summary row is ONE collection-level skip
(module-level `pytest.skip(allow_module_level=True)`), which pytest counts but which emits
no progress char. **Nothing is unaccounted for — no failure hides in the delta.**

### NEW FINDING — the nexus suite NEVER EXITS after it finishes. 116 live threads.

The pytest process printed its complete summary at 302s and then **did not exit**: log mtime
static for 8 further minutes, `STAT=S`, `%CPU=0.0` (blocked, not spinning), `ps -M | wc -l`
→ **116 threads** still alive, and the wrapping shell's `echo EXIT=$?` never fired until
SIGTERM at 920s. 116 live non-daemon threads at interpreter shutdown is the signature of
leaked threads holding the process open.

**This RETROACTIVELY EXPLAINS the "UNESTABLISHED" trees.** They were never slow and never
failing — the suite completes in ~5 minutes and then hangs forever, so every wrapper with a
10-minute cap killed a run that had ALREADY finished and reported. Session G recorded the
cause as "10-min cap under lane contention"; the real cause is a post-summary hang. The
orchestrator reproduced the same 10-min SIGTERM (exit 143) this session before the lane
identified it.

**Release-relevant:** a suite that reports success and then never exits will HANG CI, not
fail it — a job that burns its wall-clock budget and gets cancelled, read as flake. This
belongs on the pre-`/release` list.

**Branch-caused vs pre-existing: UNDETERMINED, and deliberately not guessed.** No `main`
baseline exists for this tree and establishing one needs a checkout in a shared tree. The
lane noted the tree contains `packages/kailash-nexus/tests/regression/test_issue_1285_close_cascades_runtime.py::TestIssue1285CloseCascadesRuntime::test_close_releases_all_runtime_refs`
(topically adjacent — runtime-ref release) but correctly refused to cite adjacency as
evidence. A Python stack could not be captured: `py-spy` needs root on macOS and was not
escalated to. **Follow-up: get a baseline + a thread dump.**

## ORCHESTRATOR ERROR — duplicate track spawned (`orchestration-launch-ledger.md` MUST-2)

I launched a detached three-tree runner (`/tmp/run_trees.sh`, pid 47901) while the two suite
lanes were STILL ALIVE, because they had gone silent and I judged them dead. They were not:
`w1-tests-nexus` completed and delivered a better report than my own run would have, and
`w1-tests-kaizen` is still running kaizen-agents (pid 72886, 36+ min). **The ledger tracked
my SPAWNS but I reacted to an idle SIGNAL instead of to the ledger** — the same class session
G recorded as its duplicate-lane spawn. Correct move was to consult the ledger and treat
silence as unresolved, not as death. My runner's nexus pass is now redundant work.

**MACHINE-STATE WARNING for the next session.** `ps` shows ~10 concurrent pytest runs from
OTHER repos and other operators' sessions (tpc_backend, aegis, kailash-rs, CoE-global-aegis)
on this host. Two consequences: (1) wall-clock here is contention-bound, so a slow suite is
not evidence of a slow suite; (2) **`pkill -f pytest` would destroy other operators' work
across four repos.** The existing trap said "kills sibling suites" — it is worse than that.
Kill by EXACT pid with a verified ppid, never by pattern.

## nexus — INDEPENDENTLY REPLICATED, and the hang reproduces deterministically

The orchestrator's detached run (`-p no:randomly`, no `no:cacheprovider`) and the lane's run
(`-p no:cacheprovider`, no `no:randomly`) are INDEPENDENT instruments — different flags,
different process, different wall-clock — and agree EXACTLY:

| run | summary | duration |
| --- | ------- | -------- |
| lane `w1-tests-nexus` | `2592 passed, 14 skipped, 14 warnings` | 302.34s |
| orchestrator detached | `2592 passed, 14 skipped, 14 warnings` | 545.71s |

Same counts under a 1.8x wall-clock spread, so the duration delta is host contention (~10
concurrent unrelated pytest suites) and the COUNTS are contention-independent. **nexus is
VALID at 2592 passed / 14 skipped / 0 failed.**

**The post-summary hang reproduced in BOTH runs**, so it is deterministic and NOT a
contention artifact. The orchestrator's process sat 2103s total against a 545s test session
— **~26 minutes hung past its own completed summary** — until killed by exact pid.

**TRAP FOR THE NEXT SESSION — the nexus suite's EXIT CODE IS NOT A VERDICT.** My runner
recorded `EXITCODE=143` for a run that PASSED 2592 tests: 143 is the SIGTERM sent to the
hang, not a failure. Any CI job, script, or wrapper that reads this tree's exit status will
read a fully green run as a failure (or as a cancelled/flaky job). **Read the summary LINE,
not the exit code, for this tree** — and fix the leaked threads before `/release`, because
a hang consumes a CI job's entire wall-clock budget and is reported as infrastructure flake
rather than as the real defect it is.

## Round 5 — TEST-CONTRACT lens (Task 1 only), run by the orchestrator after the lane died

The delegated lane NEVER RAN. Orchestrator ran **Task 1 of 4** (defect-as-contract sweep).
Tasks 2 (the ~37 unaudited files), 3 (vacuous assertions) and 4 (skip/xfail discipline)
are **NOT RUN** — round 5 remains INCOMPLETE.

**PATTERN** (stated so the reader sees its blind spots): case-insensitive literals
`no validation|not validated|accepted by constructor|fail.?open|by design|known limitation|
intentionally (allow|permit|unvalidated)|currently (allow|accept|permit)|for now`, over the
**97 test files** changed vs `origin/main`. **It CANNOT match**: a defect pinned with none of
those words; a defect encoded purely in an assertion VALUE (`assert limit == -5`) with no
prose; non-English phrasing; or any defect-contract in a test file the branch did NOT touch.

**RESULT: no defect-contracts found.** All 30 hits fall in two legitimate classes —
(a) tests asserting AGAINST a fail-open (e.g.
`packages/kailash-nexus/tests/regression/test_endpoint_rate_limit_semantics.py` — "A negative
limit MUST raise, not fail OPEN"; `packages/kailash-dataflow/tests/regression/test_issue_1971_detect_database_type_fail_closed.py::FAIL_OPEN_DSNS`
is a list of inputs that USED to fail open, asserted now-closed), and (b) honestly-scoped
deferrals. The one prior defect-contract — `test_core_comprehensive.py`'s "accepted by
constructor (no validation)" — is already corrected in place by `98e83dfbe`.

### Residual surfaced (NOT a new finding — documented, deliberate, still LIVE)

`packages/kaizen-agents/src/kaizen_agents/patterns/discovery.py`, in
`UserFilteredAgentDiscovery`: the `except Exception` path **GRANTS access when the permission
checker itself errors** — an authorization fail-open that is deliberately UNCHANGED.

Its regression suite
(`packages/kaizen-agents/tests/regression/test_silent_authz_and_routing_fallbacks.py`) is
**exemplary and should be the template**, not a finding: it scopes the exclusion explicitly,
gives the reason (flipping it means a transient checker outage denies EVERY user), records
that the path is already LOUD at ERROR, notes the in-code deferral to its own
security-reviewed change, and closes with *"Nothing here should be read as having closed it."*
That final sentence is the anti-over-claim discipline this branch has repeatedly needed.

**Disposition: confirm it carries a tracking issue.** The deferral is sound and reasoned, but
`zero-tolerance.md` Rule 1b wants a deferral to be distinguishable from a silent dismissal by
a tracking issue, and an in-code note alone is weaker than that. If no issue exists, file one
— do NOT flip the behaviour in this branch.

## TWO NEW TRAPS — both caught by the fingerprint protocol, both would have produced a false number

### 1. A kaizen test WRITES INTO THE REPO ROOT — the fingerprint protocol earns its keep

Running `packages/kailash-kaizen/` created an untracked **`kaizen_implementation_test.log`**
(0 bytes) at the repository root, timestamped mid-run and never tracked in git history.
`git status --porcelain` BEFORE ≠ AFTER, so **every number from that run is VOID by protocol**
— exactly the rule the protocol exists to enforce, firing for the first time this session.

Consequences beyond the void result: a suite that dirties the working tree (a) breaks any
sibling lane's fingerprint in a shared checkout, and (b) leaves a CI checkout dirty, which
trips any "working tree must be clean" release gate. **File this; it is a real defect, not
housekeeping.** The file was LEFT IN PLACE — deleting untracked files without confirmation
is BLOCKED (`git.md` § Destructive Working-Tree Ops).

### 2. SCOPE the kaizen run to `tests/` — `packages/kailash-kaizen/` pulls in `examples/`

The bare package path collects `packages/kailash-kaizen/examples/1-single-agent/chain-of-thought/test_chain_of_thought.py`,
which needs a LIVE LLM provider. `.env`'s `OPENAI_API_KEY` is INVALID (carried trap, live 401),
so those tests fail for an ENVIRONMENTAL reason and a naive reader records a red kaizen tree.
Nine `F`s were produced before the run was stopped — **none of them evidence of a code defect.**

Correct invocation, now in `/tmp/run_trees2.sh`:
```
.venv/bin/python -m pytest packages/kailash-kaizen/tests/ --timeout=120 -q \
    -p no:randomly -p no:cacheprovider
```
`-p no:cacheprovider` is REQUIRED, not optional: without it pytest writes `.pytest_cache`
and perturbs the very fingerprint the protocol reads (the nexus lane established this).

**Generalises to a rule for this repo: a tree path is not a test path.** Verify what a path
COLLECTS before trusting what it REPORTS.

## kaizen + kaizen-agents — ESTABLISHED. All three trees now have VALID numbers.

Both runs scoped to `tests/` only, `-p no:cacheprovider`, **FINGERPRINT=MATCH** on both.

| tree | result | duration |
| ---- | ------ | -------- |
| `packages/kailash-kaizen/tests/` | **156 passed, 10 failed, 48 skipped, 1 xfailed** | 339s |
| `packages/kaizen-agents/tests/` | **3943 passed, 13 failed, 89 skipped** | 2234s (37m) |

**EXITCODE=1 on both — again NOT the verdict.** Read the summary line.

### The 23 failures triaged. NOT a release blocker; NOT clean either.

**Every one of the 23 lives under `tests/deployment/`, `tests/e2e/`, or `tests/integration/`
— Tier 2/3, which `testing.md` defines as requiring REAL infrastructure. Zero failures
outside those tiers.** This host has no LLM key, no Docker daemon, and no `config/*.env`.

| class | count | evidence (quoted, not inferred) |
| ----- | ----- | ------------------------------- |
| No LLM provider | 3 kaizen e2e + 3 kaizen-agents `test_openai_*` | `Provider openai is not available: no API key for openai: $OPENAI_API_KEY is unset or empty` |
| Ollama endpoint blocked | (within above) | `ollama error (InvalidEndpoint): reason=private_ipv4` — the SDK's own SSRF guard firing correctly |
| Docker absent | 1 | `test_dockerfile.py::TestDockerfile::test_docker_compose_up` — `docker-compose up failed` |
| Missing env config | 4 | `test_production_configs.py::TestEnvironmentConfigs::*` — `config/dev.env must exist`, `FileNotFoundError` |
| Registry/runtime infra | 10 kaizen-agents | `test_agent_registry_e2e.py`, `test_agent_registry_integration.py`, `test_async_runtime_integration.py` |
| **Stale test vs API — PRE-EXISTING** | 1 | `test_full_integration_e2e.py::test_enterprise_workflow_integration` — `TypeError: BaseAgent.__init__() got an unexpected keyword argument 'description'` |
| Threshold assertion | 1 | `test_multi_agent_research_pipeline` — `Expected at least 3/6 systems engaged, got 2/6` (downstream of the missing provider) |

### The one non-environmental failure is PROVEN pre-existing — not branch-caused

`BaseAgent.__init__` accepts `config, signature, strategy, memory, shared_memory, agent_id,
control_protocol, mcp_servers, hook_manager, checkpoint_manager` — **no `description`**.

**Discriminating check** (`git diff --quiet origin/main...HEAD -- <path>`, which exits 0 IFF
unchanged — it would have exited 1 had either moved):
- `packages/kailash-kaizen/src/kaizen/core/base_agent.py` → **UNCHANGED on branch**
- `packages/kailash-kaizen/tests/e2e/autonomy/test_full_integration_e2e.py` → **UNCHANGED on branch**

Both unchanged ⇒ the failure reproduces identically on `origin/main`. `zero-tolerance.md`
Rule 1c is SATISFIED here — this is not an unfalsifiable "pre-existing" claim across a context
boundary, it is a git-provable one.

**Disposition — NOT fixed in this branch, and the reason is stated rather than assumed.**
Rule 1 says found-it-own-it, but the fix is a stale-E2E-test repair in a tree that CANNOT be
executed on this host (no provider, no Docker, no env config), so a "fix" could not be
verified RED→GREEN here — and `instrument-discipline.md` MUST-2 blocks shipping a fix whose
green cannot be established. **File it with the evidence above.** Re-run these trees on a
provisioned host before `/release`; that run, not this one, is the gate.

**What this DOES establish:** no failure anywhere outside the infra-dependent tiers, on
either tree, with fingerprints intact. Combined with nexus (2592/0) and session G's VALID
root `tests/unit/` (4798/0) + `tests/regression/` (1567/0) + mcp (649/0), the non-infra
surface of this branch is green across all five trees.

## Round 5 — security hypothesis E RESOLVED. A REAL FINDING: the trusted-proxy resolver is DEAD CODE.

Hypothesis E ("is the rate-limit KEY sound, or bypassable/shared?") was left UNRESOLVED
earlier this session. Now resolved, and it is a genuine defect.

### The finding

`nexus/extractors/proxy.py::resolve_client_host` is a well-built trusted-proxy resolver —
RFC 7239 `Forwarded`, `X-Forwarded-For` right-most-untrusted walk, `X-Real-IP`, CIDR trust
gating, fail-closed on mixed IP version. `Nexus.__init__` accepts an operator-facing
`trusted_proxy_cidrs` kwarg, validates it fail-fast (`core.py::Nexus.__init__` →
`validate_trusted_proxy_cidrs`), and `extractors/middleware.py` calls the resolver on EVERY
request and stores the answer as `request._nexus_resolved_client_host`.

**Nothing ever reads it.** Repo-wide — `src/`, every `packages/*/src/`, and every test —
`grep -rn "_nexus_resolved_client_host"` returns **exactly ONE line: the WRITE**
(`extractors/middleware.py:77`). Zero readers. The resolver's only caller is that middleware;
its output is computed per-request and discarded.

Meanwhile ALL FOUR rate-limit key derivations independently hand-roll the RAW TCP peer:

| site | line |
| ---- | ---- |
| `nexus/sse.py::_rate_limit_exceeded` | `client_ip = request.client.host if request.client else "unknown"` |
| `nexus/core.py` (endpoint `rate_limited_func`) | same |
| `nexus/auth/rate_limit/middleware.py` | same, then `f"ip:{client_ip}"` |
| `nexus/auth/rate_limit/decorators.py` | same, then `f"ip:{client_ip}"` |

(By contrast `nexus/auth/audit/middleware.py::_get_client_ip` DOES consult proxy headers under
a trust flag — so the codebase disagrees with ITSELF about client-identity derivation.)

### Severity — stated precisely, NOT inflated

- **NOT a spoofing bypass.** The raw TCP peer cannot be forged, so rate limiting is not
  defeatable by sending `X-Forwarded-For`. The keying errs in the FAIL-SAFE direction.
  `auth/rate_limit/backends/memory.py` even notes the forged-XFF concern explicitly.
- **IS a real availability defect in the standard production topology.** Behind ANY reverse
  proxy / load balancer / ingress, every client presents the SAME peer IP, so all clients
  share ONE bucket and a single caller exhausts the limit for everyone.
- **IS a dead operator-facing security control.** `trusted_proxy_cidrs` is accepted,
  documented, and validated — and affects nothing. Adjacent to `zero-tolerance.md` Rule 3c;
  it satisfies the LETTER (the kwarg IS forwarded to a callee) while the callee discards the
  result, so the user-visible effect is identical to a silent drop.
- **Zero contract coverage.** No test reads the attribute; the one proxy test
  (`tests/integration/nexus/test_trusted_proxy_mixed_version.py`) exercises the RESOLVER
  FUNCTION directly, never its wiring — so nothing would red if the write were deleted.

### PRE-EXISTING — git-proven, not branch-caused

`git diff --quiet origin/main...HEAD` exits 0 for `extractors/middleware.py`,
`extractors/proxy.py`, and `sse.py` — all UNCHANGED on this branch — and `origin/main`
already carries the write-only attribute (1 occurrence). This branch did not introduce it.

### Disposition: FILE IT. Do NOT fix in this branch. Human gate.

The fix is small and **behaviour-preserving by default**: `resolve_client_host` returns
`peer_ip` whenever the peer is not in `trusted_proxy_cidrs`, and the default is `[]`
(nothing trusted) — so routing the four sites through it changes NOTHING for operators who
configured no CIDRs, and only activates for those who did, which is the documented intent.

Not fixed here anyway, for three stated reasons: (1) it is pre-existing, so not a regression
this branch owes; (2) changing rate-limit KEYING is a security-behaviour change that needs
its own adversarial round, and this branch's convergence counter is already ZERO; (3) the
nexus tree cannot be cheaply re-verified on this host (5-min run plus the post-summary hang),
so a fix's RED→GREEN could not be established — `instrument-discipline.md` MUST-2.

Per `completion-criterion.md` MUST-6 this is a RESIDUAL requiring a NAMED human acceptor.

## #2007 FILED AND FIXED (co-owner directed the fix; my "file, don't fix" recommendation was overridden)

**Issue:** https://github.com/terrene-foundation/kailash-py/issues/2007

**Fix shape — ONE owner, four callers.** `nexus/extractors/proxy.py::client_key_for_request`
is now the single owner of the rate-limit caller identity; all four sites CALL it:
`sse.py::_rate_limit_exceeded`, `core.py`'s endpoint `rate_limited_func`,
`auth/rate_limit/middleware.py::RateLimitMiddleware._default_identifier_extractor`, and
`auth/rate_limit/decorators.py::rate_limit._default_identifier`. Same single-owner shape as
`kailash-mcp`'s `_public_tool_view` — chosen because four hand-rolled copies is exactly how
the trusted-proxy posture came to apply to none of them.

**RED → GREEN, established in two stages rather than asserted:**

| stage | result |
| ----- | ------ |
| test written, helper absent | collection ImportError — proves the symbol did not exist |
| helper added, sites UNWIRED | **3 failed / 10 passed** — the two callable key-functions keyed on the peer, and the structural guard named all FOUR sites |
| sites wired | **13 passed** |

The middle stage is the real RED: it failed on the DEFECT, not on a missing import.

**A pre-existing test failure that was NOT a stale assertion — and the fix was the CODE.**
Wiring the sites reddened two pre-existing tests
(`tests/unit/auth/rate_limit/test_middleware.py::TestIdentifierExtraction::test_falls_back_to_ip`
and `::test_unknown_when_no_client`). They were asserting the CORRECT production behaviour.
They failed because `request = MagicMock()` FABRICATES any attribute on access, so
`getattr(request, "_nexus_resolved_client_host", None)` returned a truthy Mock and the key
became `ip:<MagicMock name='mock._nexus_resolved_client_host' id='4502007360'>`.

**Weakening those assertions would have been the wrong fix.** `resolve_client_host` returns
`Optional[str]`, so a non-`str` means the value did NOT come from the middleware. The helper
now requires `isinstance(host, str)` and falls through to the peer otherwise — type-correct,
fail-safe, and immune to mock contamination. **Both pre-existing tests now pass UNMODIFIED**
(`git diff` on that test file is empty), which is the strongest available evidence the change
is behaviour-preserving: no assertion was moved to meet the code.

Runtime proof on the three paths:
`resolved wins → 203.0.113.7` · `peer fallback → 198.51.100.4` · `MagicMock → 192.168.1.1`.

**Coverage pinned (13 tests):** resolved-wins · peer-fallback · `"unknown"` sentinel ·
empty-resolved-does-not-shadow-peer · **unconfigured deployment byte-identical to the peer** ·
**untrusted peer sending XFF cannot move its own bucket** (the anti-spoofing property the old
code got right, now pinned) · trusted peer forwards the origin · two clients behind one proxy
get SEPARATE buckets (the availability defect itself) · both callable key-functions ·
`__all__` export · a structural guard failing if ANY site re-derives the peer · and an
AST read/write census that fails if `_nexus_resolved_client_host` is EVER write-only again.

**Two authoring errors of mine, recorded:**
1. I placed the `isinstance` rationale AFTER the docstring's closing `"""`, making prose into
   code — an em-dash `SyntaxError`. Caught by `ast.parse`, fixed; the function now has
   exactly 2 terminators.
2. **The pyright diagnostics feed was STALE** — it kept reporting the broken intermediate
   state after the file was fixed and parsing cleanly. `ast.parse` + an actual import +
   the passing suite are the discriminating instruments; the IDE diagnostic was not.

**Scope honesty:** this closes hypothesis E. Hypothesis D (finalizer warn-path leakage) is
still UNRESOLVED, and round 5's test-contract lens ran only Task 1 of 4. Convergence counter
remains ZERO — and per `completion-criterion.md` MUST-3 this fix TOUCHES the nexus surface,
so any clean-round credit that surface had is void.
