# Launch Ledger — session F (2026-08-05, continuation of session E)

Branch `fix/issue-1720-forest-drain` @ `3a642d188` — 96 ahead of `main`, **28 UNPUSHED**.
Entry state read from `04-validate/sweep-2026-08-05.md` (§6 recommendation) +
`.session-notes.d/esperie.md`. Convergence counter **ZERO** at entry.

## Plan

| Wave | Purpose                                                           | Gate                              |
| ---- | ----------------------------------------------------------------- | --------------------------------- |
| 1    | Close the two open adjudications + prepare the release artifacts  | all 3 lanes report                |
| 2    | G1 redteam round over the union, rotating lenses (clean-round 1)  | every reviewer returns ran-signal |
| 3    | G1 redteam round 2, rotated again (clean-round 2 ⇒ convergence)   | 2 consecutive clean               |
| —    | Push / PR / issue writes / `/release` — HELD for co-owner confirm | structural human gate             |

## Wave 1 — launched 2026-08-05

| track            | agent | scope (DISJOINT — enforced by brief)                                         | branch | status    |
| ---------------- | ----- | ---------------------------------------------------------------------------- | ------ | --------- |
| authz-adjudicate | W1-A  | `packages/kaizen-agents/src/kaizen_agents/patterns/discovery.py` + its tests | (main) | in-flight |
| release-prep     | W1-B  | 6× `pyproject.toml`, `__init__.py`/`_version.py`, 6× `CHANGELOG.md` ONLY     | (main) | in-flight |
| nexus-500        | W1-C  | `packages/kailash-nexus/**` ONLY                                             | (main) | in-flight |

### Worktree-isolation deviation — NAMED, not silent

`worktree-isolation.md` Rule 1 mandates orchestrator-made sibling worktrees for
parallel agents. **Deviation taken: all three lanes run in the MAIN checkout with
strictly disjoint, brief-enforced file scopes.** Reasons, stated so a reviewer can
overrule: (a) the three scopes share ZERO files — the collision class Rule 1 guards
is absent by construction; (b) a Python worktree needs its own `.venv` (`uv sync
--all-extras --dev`), and session E recorded the volume hitting **100% disk with an
`ENOSPC` Edit failure** — two more full checkouts + venvs is a live failure mode, not
a theoretical cost; (c) each brief pins the lane to its OWN package's tests only, so
no two lanes invoke pytest over the same tree. Residual accepted: no branch-level
isolation, so a lane that violates its declared scope is caught at review, not
structurally.

## Wave-1 scope-contract defect — found by lane B, corrected mid-wave

My original contract was self-contradictory: it assigned the version anchors to lane B
while forbidding it the trees those anchors live in
(`packages/kaizen-agents/src/kaizen_agents/__init__.py:17`, and all three nexus release
files). Lane B flagged it instead of guessing — correct behaviour. **Resolved by narrowing
FORBIDDEN from whole trees to the specific files each lane actually holds**, and all three
lanes were re-briefed.

### The omission it exposed: `kailash-mcp` was missing from the release set

Neither my 7-package table (originally 6) **nor the session-E notes' version list**
included `kailash-mcp`. Measured:

- `packages/kailash-mcp/pyproject.toml` = `0.4.3`; anchor `src/kailash_mcp/__init__.py:10` = `0.4.3`
- tag `mcp-v0.4.3` **EXISTS** ⇒ 0.4.3 is released
- **15 changed files** on this branch

kailash-mcp carries the branch's most security-critical work — the third tool-schema
emitter (`19c8cfb33`), credentials in Redis key names (`71eb63790`), cross-principal cache
sharing (`ee6d5b8bb`), the no-credential auth bypass (`14d9d8b31`). **Releasing on the
notes' package list would have shipped every one of those fixes untagged and unannounced.**

### `kailash-nexus` — bumped-but-unreleased, not "already released"

`pyproject.toml` + `src/nexus/__init__.py:120` = `2.16.0`, newest tag = `nexus-v2.15.0`.
Lane B instructed to ESTABLISH whether the branch's 13 nexus changes are already covered by
an existing 2.16.0 entry rather than assume a further bump.

## DELIVERY GAP — the floors ship the fixes without delivering them

Version anchors verified atomic across all 7 packages (re-derived with `tomllib` + regex,
not taken from the lane's report): **0 split-state violations**.

Measured PyPI (live) vs local post-bump:

| package          | PyPI       | local  |
| ---------------- | ---------- | ------ |
| kailash-mcp      | **0.4.3**  | 0.5.0  |
| kailash-kaizen   | **2.45.0** | 2.46.0 |
| kaizen-agents    | **0.12.0** | 0.13.0 |
| kailash-dataflow | **2.19.1** | 2.20.0 |
| kailash-nexus    | **2.15.0** | 2.16.0 |
| kailash-ml       | **2.2.2**  | 2.2.3  |
| kailash          | **2.62.0** | 2.63.0 |

**Every floor pin still names the published, vulnerable version.** A FRESH install resolves
to newest and gets the fix; a user who upgrades `kailash` ALONE keeps `kailash-mcp` 0.4.3,
because `>=0.4.3` is already satisfied — so the auth bypass and the credential leaks stay
live on an install that reports as upgraded.

Worst instance: `packages/kailash-kaizen/pyproject.toml:35` pins `kailash-mcp>=0.2.4`, so
kaizen 2.46.0 can satisfy itself with an mcp carrying every vulnerability fixed here.

This is `conformance-walk.md`'s DELIVERED-family gap exactly: source has the fix, tests pass
against source, the artifact the user installs does not contain it. Floors queued for raise.

**CI caveat, reasoned not assumed:** the session-notes trap ("bumping to unreleased versions
breaks release CI which installs from PyPI") does NOT bind local resolution — `pyproject.toml:316-324`
declares `[tool.uv.sources]` path overrides, and the comment at `:299-310` states they exist
precisely so the root package may pin newer-than-published versions without breaking `uv sync`.
Residual risk is release-CI publish ORDER: mcp → kaizen → kaizen-agents → dataflow/nexus/ml →
kailash last. Lane B tasked to READ `.github/workflows/` and report; editing workflows is BLOCKED.

Secondary (NOT actioned, decision pending): `kailash-ml`, `kailash-pact`, `kailash-align` all
pin `kailash-kaizen>=2.7.5`, permitting a kaizen without the credential-scrub fixes. Those
packages are not in this release.

## MY OWN unverified claim, caught by lane B — recorded, not buried

I wrote into the lane-B delegation brief: _"Nothing from this branch is in ANY changelog yet
(verified: zero CHANGELOG files in the diff)."_ **I never ran that check.** I took the
session-E sweep's _"zero CHANGELOG files touched **this session**"_ and restated it as a
stronger, branch-wide claim in a durable artifact. Measured after the lane challenged it:

```
$ git diff --name-only main..HEAD | grep -i changelog
packages/kailash-dataflow/CHANGELOG.md
packages/kailash-kaizen/CHANGELOG.md
packages/kailash-nexus/CHANGELOG.md
```

Three were already committed from PRIOR sessions. `verify-claims-before-write.md` MUST-1/2
names delegation briefs as durable artifacts and prior-session claims as presumed-false —
this is precisely the violation those clauses block, committed by the orchestrator.

**Consequence had the lane not challenged it:** it would have written duplicate `[Unreleased]`
blocks over three existing entries, including dataflow's BREAKING #1971 entry. The lane
instead ADDED to kaizen's existing block. Correct behaviour; the brief was the defect.

Sub-correction issued: the lane read the pre-existing entries as a _concurrent sibling lane's_
writes. They are prior-session commits. No lane is racing on changelogs.

## CORRECTION to the delivery-gap entry above — the orchestrator was wrong, lane B was right

I instructed lane B to raise the `kailash` extras floors at `pyproject.toml:143-148`. **It
refused, on the artifact's own documented evidence, and it was correct.** I had conflated two
distinct comments:

- `pyproject.toml:299-310` — why **local `uv sync`** tolerates newer-than-published pins
  (`[tool.uv.sources]` path overrides). This is the one I read.
- `pyproject.toml:139-142` — a **different consumer entirely**:
  _"Pins are MINIMUM compatible versions — bumping to unreleased versions breaks release CI
  which installs from PyPI before the new release publishes."_

Release CI installs the extras FROM PyPI, where path overrides do not apply. My instruction
would have red-lit the core release. The extras block stays at pre-release floors **by design**.

**What was correctly closed:** `packages/kailash-kaizen/pyproject.toml:35` `kailash-mcp`
`>=0.2.4` → `>=0.5.0` — a production dep, and the user-facing path to the vulnerable mcp
(kaizen constructs `MCPServer` directly at `core/mcp_mixin.py:732`, the `KaizenMCPServer`
subclass, and `catalog_server`). Root `pyproject.toml:194` was also raised, but that line is
`[dev]`-only — my earlier framing of it as user-facing was wrong.

**New hard constraint this creates.** kaizen 2.46.0 now floors on an UNPUBLISHED mcp 0.5.0, so
tagging `kaizen-v2.46.0` before `mcp-v0.5.0` publishes will fail to resolve. `publish-pypi.yml`
is tag-triggered with `needs:` scoped WITHIN one package's job graph and **zero cross-package
ordering** — the sequence is operator-manual and CI-unenforced. Required order:

> mcp 0.5.0 → kaizen 2.46.0 → kaizen-agents 0.13.0 → dataflow/nexus/ml → kailash 2.63.0 last

**Residual, deliberately deferred:** the extras floors MUST be raised in a follow-up commit
AFTER the sub-packages publish and BEFORE the core `v2.63.0` tag. Without that step an operator
upgrading `kailash` alone keeps a kaizen lacking the credential-scrub fixes. Captured in
`release-order-sessionF.md`, not left in conversation.

## REFINEMENT — the file's own comment is stale too; the lane's mechanism supersedes both

Lane B re-derived the extras-floor question independently rather than trusting either the
orchestrator's instruction OR this ledger's correction. Result: the conclusion holds, both
stated reasons were wrong.

**Verified independently (`grep -rn` over `.github/workflows/`): ZERO matches for any
`kailash[<extra>]` install.** So `pyproject.toml:139-142`'s _"breaks release CI which installs
from PyPI"_ has **no live enforcement point**. I cited that comment as authority; it is stale
as stated.

**The correct mechanism is user-facing and temporal, not CI:** if `kailash` 2.63.0 publishes
before `kailash-kaizen` 2.46.0 is live, `pip install kailash[kaizen]==2.63.0` fails with "no
matching distribution" for every real user until the sub-package lands — true whether or not
any CI job exercises it.

**The load-bearing distinction, which the orchestrator got wrong:** `[tool.uv.sources]` is a
**uv extension**, NOT PEP 621 metadata, **never read by `pip`**, governing only how THIS
repo's checkout resolves locally. A published wheel's `[project.optional-dependencies]` is
what a real `pip install` reads, verbatim. Local-dev resolution and published-metadata
resolution are different systems; conflating them is what produced the bad instruction.

Kept (correctly): `packages/kailash-kaizen/pyproject.toml:46` `kailash-mcp>=0.5.0` — kaizen
ALREADY had a mandatory mcp dependency, so the kaizen-after-mcp publish constraint pre-existed;
raising the floor makes an existing coupling correct rather than introducing a new one.
Reverted (correctly): the root extras block + `all` aggregate.

`uv lock` drift clean: 6 version bumps + 2 floor constraints. `kailash-nexus` absent from the
lock because it is only pulled by the optional `nexus` extra, which nothing in the lock's
resolved scope requests.

## Lane-B extended round — what running the deliverables found

**The verification script was DEAD ON ARRIVAL.** `declare -A` requires bash 4; this machine is
`GNU bash 3.2.57 (arm64-apple-darwin25)` (macOS ships 3.2). First run: `line 8: packages:
unbound variable`, exit 1. **A safety check that cannot execute reports success by not
running** — strictly worse than no check, because it converts an unexamined assumption into a
green tick. Rewritten bash-3.2-portable. Orchestrator re-ran it independently from the note:

```
FAIL: packages/kailash-kaizen/pyproject.toml declares kailash-mcp>=0.5.0, but PyPI live=0.4.3
FAIL: packages/kaizen-agents/pyproject.toml declares kailash-kaizen>=2.46.0, but PyPI live=2.45.0
EXIT: 1
```

Correct, and correct for the two right reasons — it blocks `kaizen-v2.46.0` today. This is
`user-flow-validation.md` MUST-1 paying for itself: the walk, not the review, found it.

**A CHANGELOG entry was on the wrong package.** Core's changelog claimed a
`_detect_database_type` fail-closed fix. Verified: `grep -rln "_detect_database_type"
src/kailash/` → **0 hits**; it lives in `packages/kailash-dataflow/src/dataflow/{core/engine.py,
core/nodes.py,migrations/auto_migration_system.py}`. Documented where it isn't, undocumented
where it is. Moved.

**Credential-scrub entry audited exhaustively — 12/13 exact, 1 corrected.** The correction is
the notable one: the changelog claimed the local `PATTERNS` list is retained "only for
non-credential PII classes". Verified at `core/autonomy/hooks/security/redaction.py` — it also
retains `api_key` = `(sk|pk)[-_][a-zA-Z0-9]{20,}`, `bearer_token` = `Bearer\s+...`, and
`password`. **The source's OWN SCOPE comment also calls these "NON-CREDENTIAL."** The lane read
the regexes rather than either layer of prose. Two layers of documentation wrong in the same
direction; ground truth was one layer below both.

**ORCHESTRATOR instrument failure, recorded.** I grepped the release-order note for `declare -A`
to check the fix, got hits at `:111` and `:133`, and nearly reported the bug unfixed. Those are
the prose EXPLAINING the bug and the comment PROMISING it is unused. **A grep over a document
containing code cannot distinguish code from commentary about code** (`instrument-discipline.md`
MUST-1 — the result was identical under both hypotheses). Executing the script was the
discriminating instrument.

**Pre-existing type errors in `nexus/core.py:2256/2263/2276/2313/3549`** — provably NOT lane C's
(its hunks are `@@ +3797,14` and `@@ +4365,24`; all errors fall outside). Per
`zero-tolerance.md` Rule 1a "same on main" is not a disposition — routed to lane C to adjudicate.
`:2276` (`str < int` in the rate-limit cleanup) is a candidate 500-generator on a rate-limited
endpoint; lane C told to rule it in or out against its own 500 root cause before dismissing it.

## Backlog reconciliation — done by the orchestrator while Wave 1 ran (`wave-loop.md` MUST-7)

10 issues open, unchanged from the session-E sweep: #1970 #1971 #1972 #1974 #1981
#1995 #1996 #1997 #1998 #2000.

### #1996 — FIX VERIFIED with a discriminating instrument (was: asserted from the commit body)

First attempt was **INERT and its result discarded**: the `sys.meta_path` blocker used
`find_module`, which Python **3.12 removed**, so `mcp` stayed importable and BOTH readings
("import OK", "get_server did not raise") were zero evidence (`instrument-discipline.md`
MUST-2b — a non-reddening mutation leaves two hypotheses).

Re-instrumented with `find_spec`, and the instrument was **proved to discriminate first**
(`import mcp.server` → `ImportError: No module named 'mcp'`). Then, with `mcp` genuinely absent:

- `import kailash.trust.plane.mcp_server` → **succeeds** (module-scope import is now
  `TYPE_CHECKING`-only; `src/kailash/trust/plane/mcp_server.py:36-37`)
- `get_server()` → raises the typed, actionable error:
  `Cannot import FastMCP from the third-party 'mcp' package. Install it with: pip install 'mcp[cli]>=1.23.0'`

⇒ `45ccac417` genuinely delivers. Closure with the SHA is HELD for co-owner confirm (issue
writes are shared state).

### #1998 — the session-E framing is IMPRECISE; corrected here before anyone fixes it

Session notes say "`run_stdio` has **ZERO** production callers." **Measured: it has two**
— `server.py:5447` (inside `run_async()`) and `contrib/ai_registry.py:727`.

The accurate statement, from the code's own comment at `server.py:2996-3001`: the **sync
`run()` entrypoint** (`server.py:2949`) dispatches to `self._mcp.run()` at `:3002`, serving
**FastMCP's own registry**, which was never taught `_public_tool_view`. `run_async()` →
`run_stdio()` IS gated.

Also narrower than "bypasses EVERY gate" — the same comment records that **invocation
authorization still holds on both paths** (the enhanced wrapper is what FastMCP registered).
What leaks on `run()` is **disclosure** (gated tools advertise full `inputSchema` + `Args:`)
and **`disable_tool()` enforcement** (disabled tools are listed AND executable).

⇒ The fix is "teach FastMCP registration the public view", not "add a filter to `run_stdio`".
A fix written against the notes' framing would have targeted a path that is already gated.

## Lane A — NEVER REPORTED (2 queries, no reply). Accepted on orchestrator-derived evidence.

All four items verified by the orchestrator from the tree + independent test runs, NOT from a
lane report. Recorded this way so no later reader mistakes derived evidence for a receipt.

**RED ESTABLISHED INDEPENDENTLY.** `cp` backup → `git show HEAD:<path> >` the pre-fix source →
run → restore from backup (`cmp`-verified, 65499 bytes). `git checkout --` deliberately NOT
used (`git.md` — it restores from the INDEX and would have destroyed the lane's unstaged work):

- **pre-fix: 7 failed, 46 passed** — all 7 in `TestF5AdvisoryWarnNamesItsSubjectAndFiresPerUser`
  and `TestF6AMappingThatDisagreesWithItselfFailsClosed`
- **post-fix: 51 passed**

⇒ F5 + F6 tests are NON-VACUOUS. The fixes are real.

**F3 — REFUTED, not fixed, and the refutation's PREMISES are pinned.** Its tests pass against
pre-fix source, which is the correct signature of a refutation (the behaviour was already
right). Verified independently: `src/kailash/trust/chain.py:841-856` — `VerificationResult`
carries `valid`/`level`/`reason`/`capability_used`/`effective_constraints: List[str]`/`violations`
and **NO permission-level field**. So `valid=True` for `action="execute"` IS the verdict;
restating it does not widen it. The labels arrive via `effective_constraints`, documented at
`chain.py:350-363` as read by NO allow/deny gate.

The durable part: `TestF3TheRefutationsPremises` pins the premises themselves
(`test_verification_result_declares_no_permission_level_field`,
`test_the_checker_is_asked_for_the_execute_action`), so an SDK change that adds a
permission-level field REDS the test and re-opens the refutation automatically. A refutation
without its premises pinned decays into folklore the moment the thing it rested on changes.
`TestF3NoneConstraintsCannotReachTheGrant` pins the `None`-guard (the pyright `:1247` finding is
a narrowing limitation, not a runtime bug — `if unrepresentable is not None:` denies first).

**F7 — DONE, and it found the doctrine WRONG ABOUT ITSELF.** Doctrine at
`credential_scrub.py:1084-1160`; 24 probes pass on CPython **3.13.7**, the exact version the
verdicts claim. Empirical verdicts (probed per BRANCH, not sampled):

| type                        | verdict                                                                           |
| --------------------------- | --------------------------------------------------------------------------------- |
| `Decimal(x)`                | **NO echo** — reports the condition class (`ConversionSyntax`), never the operand |
| `base64.b64decode(x)`       | **NO echo** — padding/character complaint with counts only                        |
| `datetime.strptime(x, f)`   | **ECHOES** — on BOTH operands (data, and the format on a bad directive)           |
| `datetime.fromisoformat(x)` | **ECHOES**                                                                        |
| `ipaddress.ip_address(x)`   | **ECHOES**                                                                        |
| `KeyError`                  | **ECHOES** — `str()` IS `repr(key)`, so `f"missing: {exc}"` prints it verbatim    |

**The `re.compile` record is the load-bearing part.** An EARLIER revision of this doctrine
asserted `re.error` is "purely positional" and classified it NO-echo — reached by sampling two
positional branches and generalizing. FALSE on the group-name branches, which interpolate the
name verbatim. **That wrong verdict shipped a real leak:** `delegate/tools/grep_tool` compiles a
model-supplied pattern and was left LOCAL on the strength of it, so a prefix-less credential
inside a group name reached the tool result in full. The doctrine's own prior guess is the
evidence for its "probe every branch, never reason" rule. Note also that the two NO-echo
verdicts (`Decimal`, `b64decode`) are exactly the ones that would have been guessed wrong — both
take a string the caller is parsing, the `float`/`int` shape, and neither quotes it back.

## ORCHESTRATOR methodological lesson — reading a shared tree mid-edit is a SNAPSHOT, not a STATE

Three times I flagged an in-flight defect from the shared working tree. **Two were transient
states, not findings:**

1. `git diff --stat -- src/kailash/api/workflow_api.py` returned EMPTY → I reported "the core
   fix has not landed." The lane had **stashed that exact file** to establish its parity suite's
   RED. Correct behaviour on its part; my read landed inside the window.
2. `"logging" is not defined` in the new WARN tests → I reported three hard errors. The import
   had **already been added** in a separate edit before any test run; the diagnostic I saw was
   from the intermediate state.
3. `"Sequence" is not defined` (lane A) → this one WAS real and worth catching.

**One in three.** The two false positives cost a round-trip each; the one true positive would
have shipped a headline deliverable that could not execute. So the checking was worth it — but
the framing was wrong. A diagnostic or `git diff` against a tree with a LIVE editor is a
**snapshot of a moment**, not a claim about the lane's state. The honest form is "as of this
read, X — confirm whether that is current," not "X is broken."

This is the same `instrument-discipline.md` MUST-1 question one level up: a snapshot of a moving
tree cannot discriminate "the lane never did this" from "the lane is mid-edit." **The
discriminating instrument for a lane's state is asking the lane** — which is exactly why
`wave-loop.md`'s query-don't-re-dispatch rule exists.

Corollary that DID hold: never re-dispatch on silence. Both silent lanes had complete work.

## Wave 1 CLOSED — lane C

**nexus 2366 passed / 14 skipped / 0 failed; parity 7 passed; nexus regression 100 passed.**

- **The 500 root-caused to CORE, not nexus** — `src/kailash/api/workflow_api.py::get_inputs`
  unwrapped the `{"parameters": {...}}` envelope. Same registered workflow: 200 over MCP, 500
  over HTTP AND over Nexus's own CLI (`cli/main.py:59`). Multi-channel parity — the product's
  core promise — broken in the product that exists to provide it, with the docstring at
  `nexus/core.py:1562-1563` asserting the opposite.
- **`rate_limit_config={"default_rate_limit": None}` was a live 500-generator** on every call,
  reachable through a public constructor kwarg — while `core.py:2184` documents
  `None=unlimited`. **The documented behaviour had never been implemented; it crashed.** This
  was one of the "pre-existing, provably not mine" type errors — proof that
  `zero-tolerance.md` Rule 1a ("same on main" is not a disposition) earns its keep.
- **The skip was hiding TWO defects.** Removing `test_request_latency`'s self-skip exposed the
  bodyless-POST 500 (a workflow's own defaults unreachable) AND a `max < 200ms` assertion
  measuring scheduler noise (measured: p95 110ms, ONE 408ms outlier in 100 — changed the
  STATISTIC to p95, not the threshold, per `testing.md`).
- **Two scope-exceeding changes, both flagged and both ACCEPTED**: MCP symmetry
  (`core.py:1574` — without it parity is one-directional, so criterion 4 unmet) and the
  bodyless-POST envelope (same defect at the empty boundary).
- **Rate-limit WARN** landed per ruling — enforcement byte-for-byte unchanged, only the silence
  ends (`zero-tolerance.md` Rule 3c satisfied without the blast radius).
- **Self-flagged vacuous test:** `test_engaged_rate_limit_does_not_warn` passes in BOTH arms —
  a false-alarm guard, not a bug detector. Reported unprompted rather than letting a 3-test
  RED/GREEN table imply three independent proofs. RED arm fails with **`AssertionError` naming
  the captured messages, not `NameError`** — the discriminating shape.
- **Hook false-positive settled with the AST:** `framework-first` matched
  `from fastapi import Request` inside a log-message STRING. Real `ImportFrom` nodes: 2257,
  2332, 2648, 3991 — line 2311 absent. Reworded anyway so the next session does not re-trip it.

## 29 PRE-EXISTING failures — ATTRIBUTED, and the CI gap behind them

Definitive: lane A's two source files reverted to HEAD → **29 failed / 642 passed in BOTH arms**,
identical. Not caused by any lane this session. (Files restored, `cmp`-verified.)

- **9 CI-VISIBLE, RELEASE-BLOCKING** — `tests/unit/mcp_server/`, all `TestMCPServerToolDecorator`:
  `assert ('admin.execute',) == 'admin.execute'`. The registry now stores a TUPLE because the fix
  made `_authorize()` check ALL declared permissions instead of dropping everything after the
  first. **STALE TESTS — PORT them.** Reverting to a bare string re-opens ">1 permissions dropped
  to first," a real authorization bypass. Same trap session E hit with 9 security tests where
  zero product changes were needed. Routed to lane B.
- **20 INVISIBLE TO CI** — `tests/regression/test_provider_registry_backcompat.py` (18) +
  `test_issue_697_pool_leak.py` (2). **`unified-ci.yml:140-143` runs `tests/unit/`,
  `tests/trust/plane/unit/`, `tests/security/` — NOT `tests/regression/`.** The directory holding
  the never-delete regression suite (`testing.md`) has NO CI coverage, and 20 failures have
  accumulated there unseen. Recorded as a follow-up shard; NOT taken (different bug class,
  would delay a security release).

## WAVE 2 / ROUND 1 — **NOT CLEAN.** Clean-round counter remains **ZERO**.

Three FRESH reviewers (deliberately NOT the implementer lanes — `completion-criterion.md` MUST-5:
a critic sharing the generator's context shares its failure distribution). Rotated lenses. All
three returned genuine ran-signals with per-claim coverage statements, so this counts as a real
round that found defects — not as an un-run round.

**Every lens found something the other two did not.** Two findings are defects in fixes made
THIS session.

| Lens                                   | Verdict                                            |
| -------------------------------------- | -------------------------------------------------- |
| Adversarial security (REFUTE-prompted) | 1 HIGH, 3 MEDIUM, 2 LOW                            |
| Consumer / upgrade path                | 2 release-blocking, 1 MEDIUM-HIGH, 1 MEDIUM, 1 LOW |
| Cross-package composition              | 1 HIGH, 1 MEDIUM, 1 LOW                            |

### HIGH-1 — the rate-limit WARN certifies inert endpoints as protected (ORCHESTRATOR-SPECIFIED DEFECT)

Verified in source. Predicate `core.py:2249` accepts any parameter whose ANNOTATION is `Request`,
with no name check. Runtime `core.py:2337` resolves by LITERAL NAME (`if "request" in kwargs`),
then scans `args` — which FastAPI never populates (`dependant.call(**values)`), so that loop is
dead. `kwargs.values()` is never scanned.

⇒ `async def costly(req: Request, payload: dict)` with `rate_limit=10`: predicate True ⇒ **no
WARN**; at request time `request` stays `None` ⇒ **no counting, no 429**, unbounded — while the
registration log prints `rate_limit=10/min`. Naming it `req` is idiomatic.

**I specified this predicate without checking what the runtime does.** The WARN was added so a
silently-inert `rate_limit=` would be announced; it announces nothing for the most common
handler shape. Fix routed as: change the WRAPPER to scan `kwargs.values()` (makes the feature
work for any name, and makes predicate and runtime the same test) — NOT tighten the predicate,
which would only make the WARN honest about a still-broken feature.

### HIGH-2 — the parity fix reaches 3 of 9 entry points, and the parity test cannot red on the other 6

Verified in source. `nexus/transports/mcp.py:168` (`execute_workflow_async(workflow, kwargs)`)
and `transports/websocket.py:706-709` (`inputs = params`) both bind RAW, both are PUBLIC
(`nexus/__init__.py:68,71` + `__all__`), and both serve the SAME registry `Nexus.register()`
writes to. One `nexus.register()` yields a workflow that succeeds on `core.py`'s MCP tool and
**500s on `MCPTransport`'s**. Four more: `core.py:4024`, `src/kailash/channels/{api,cli,mcp}_channel.py`.

**The deeper finding is the test.** `test_issue_workflow_parameters_envelope_parity.py` passes and
is honest about what it drives — but its acceptance surface is THREE channels while its docstring
says "every channel." A denominator smaller than the claim reports 100% BY OMISSION
(`conformance-walk.md` MUST-3). It certified "parity holds" while six channels were broken.
Fix routed as: bind the six, AND make the test's denominator DERIVED so a new un-updated entry
point fails it instead of passing silently.

### RELEASE-BLOCKING — `specs/mcp-server.md:141` still documents the auth bypass as INTENDED

Verified verbatim: _"For async tools, if no credentials are provided and no `mcp_*` kwargs exist,
the call is allowed (development/testing mode)."_

**The spec blesses the CRITICAL vulnerability this branch deleted.** A future session reads the
spec, sees the code disagree, and "restores" the documented behaviour as a REGRESSION FIX — with
the spec as the authority telling them to. Nothing in the suite would object.
`specs-authority.md` Rule 5 required this at first instance; it was missed. **This single line
was worth the whole round.**

### RELEASE-BLOCKING — two changelogs ship release notes under `## [Unreleased]`

Verified: mcp `pyproject=0.5.0` / changelog `## [Unreleased]`; dataflow `pyproject=2.20.0` /
changelog `## [Unreleased]`. The other five are correctly headed, so this is an omission in two.
`mcp-v0.5.0` is FIRST in the publish sequence ⇒ blocks the chain.

### Remaining round-1 findings (routed, not yet fixed)

- **MED** — both len/items guards re-read `len()` a SECOND time; a non-idempotent `__len__`
  Mapping (and a one-shot-`__iter__` Sequence) still reach the UNLIMITED default — verbatim the
  outcome the guard's own comment claims to prevent. Fix: MATERIALIZE ONCE at entry.
- **MED** — the `user_id` memo key moved cardinality from `|label sets|` to `|users|×|label sets|`,
  so the 256 cap saturates in normal operation and post-saturation degrades to the O(users×agents)
  flood the memo exists to prevent. `len(...) < CAP` gates RECORDING, never EMITTING.
- **MED** — rate-limiter `request_counts` is unbounded in the client-IP dimension; the
  "prevent memory leak" comment is true of the inner dict, false of the outer.
- **MED** — `bash_tool.py:65,77-79` interpolate the model-supplied `command` unscrubbed while the
  sibling OSError branch was routed through `scrub_remote_error` by the same sweep.
- **MED-HIGH** — nexus 2.16.0 has three source changes and ONE changelog entry.
- **LOW** — local scrub preset misses `password=<pure-alpha 6-15>`, the shape its own docstring
  names as covered; a comma-bearing value appears to leak on BOTH presets (needs empirical repro).
- **LOW** — `get_inputs` change is in NO changelog; envelope capture by a node id'd `parameters`.

### Corrections to durable artifacts (orchestrator errors)

1. **`discovery.permission_check_failed_open` is NOT a breaking rename.** Proven: it never
   existed on `main` — introduced AND renamed inside this unreleased branch, so no operator
   alerting can key on it. My instruction to lane B calling it BREAKING was wrong; the same
   framing is in `sweep-2026-08-05.md:210` and `.session-notes.d/esperie.md:145`.
2. **`run_stdio` "zero production callers"** — corrected earlier; it has two.

### Deepest OPEN question on the branch (recorded, deliberately not chased)

F3's refutation survived direct attack on all three sub-questions. But its load-bearing premise —
that the advisory tightening IS enforced elsewhere via signed derived capabilities — was
confirmed to EXIST (`_build_signed_derived_caps` / `_derive_enforced_envelope` at
`src/kailash/trust/operations/__init__.py:596,788`, called from `verify()`) but **NOT verified
end-to-end that the labels are actually bound and re-derived there**. Also: `advisory_constraints`
has **NO production consumer anywhere** — the field is write-only, so "nothing is silently
dropped" currently rests on a field nothing reads.

## DISCLOSURE — private org slug in a PUBLIC repo. Pre-existing, ~7 weeks live, USER DECISION.

`gh repo view` → `terrene-foundation/kailash-py  visibility=PUBLIC`. The private sibling's org
slug `esperie-enterprise` is present in **17 tracked files** outside `workspaces/`/`.claude/`
(specs FIXED this session by lane B; the rest untouched):

| area                 | files                                                      |
| -------------------- | ---------------------------------------------------------- |
| root records         | `SWEEP-2026-06-{08,15,25}.md`                              |
| deploy notes         | 4× `deploy/deployments/2026-06-*.md`                       |
| dataflow tests       | 4× cross-SDK parity vectors + regression tests             |
| root tests / vectors | 6× incl. `tests/test-vectors/eatp08-alg-id-canonical.json` |

**On `main` since at least `0539b7d30` (2026-06-16) — ~7 weeks public, and in git HISTORY.**

**How it was found is the transferable part.** Lane B flagged "34 files, identical Rule 6
disclosure class" after grepping `kailash-rs`. Checking BEFORE sizing showed that grep pointed at
the LOW-severity token: the bare repo name says a sibling exists, not where it lives. The
high-severity token is the ORG SLUG, it was in a different (smaller) set of files, and **lane B's
grep could never have found it** — hidden underneath a count 11× larger and less severe.
Generalized rule issued: when flagging a disclosure class, grep the MOST sensitive identifier
(org / tenant / operator / engagement) FIRST; the low-severity token is usually more numerous.

**Disposition: NOT fixed this session, NOT release-blocking, surfaced as a user decision.**
Reasoning: (a) it is pre-existing and unrelated to this branch; (b) it has been public ~7 weeks
AND is in git history, so editing files is PARTIAL mitigation only — the disclosure already
happened and history retains it; (c) the remaining 17 are test vectors, deploy records, and sweep
reports — a coherent separate task, not release-prep; (d) whether an org NAME (not a credential)
is sensitive is the co-owner's call, not the agent's. `zero-tolerance.md` Rule 1a is honored by
recording and surfacing it, not by silently absorbing a repo-wide cleanup into a security release.

## Completion matching (MUST-3)

Every completion notification below is matched against this table BEFORE reacting.
No branch/commit produced by these agents is to be reasoned about as another
session's work.

| agent | reported     | verdict                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| W1-A  | pending      | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| W1-B  | **COMPLETE** | **ACCEPTED** — verified independently, not from the report. 7/7 version anchors atomic (`tomllib`+regex, 0 split-state); `grep "breaks release CI"` → no match (stale line deleted, not relocated); extras comment `:138-164` states ONE mechanism; `tomllib` parses at 2.63.0; `release-order-sessionF.md` 153 lines, 4/4 sections, disclosure-scrub clean, citations `:165`/`:265` resolve exactly. **Note: this lane reported "complete" ONCE while Task A was undone — verify, never accept the report.** |
| W1-C  | pending      | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
