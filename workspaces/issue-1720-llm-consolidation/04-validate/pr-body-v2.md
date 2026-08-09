# fix(forest): credential-leak classes, rate-limit fail-opens, and the silent-degradation family

<!-- Title says "classes", not "sweep", deliberately: the traceback re-leak class is
     closed, the kailash-kaizen package is not. A reader who sees only the subject line
     must not infer a completed package sweep. See Known not fixed. -->

Replaces `pr-body-draft.md`, which **must not be opened as written** — it asserts
"Convergence was reached" (it was not), carries counts from an earlier HEAD, cites a
"round 3" gate that has since been superseded, and lists an incomplete set of filed
issues.

**Every number below was re-derived at the moment of writing**, with the command shown.
Nothing is carried from any prior document. This branch has already paid for two
correction cycles on carried claims (`verify-claims-before-write.md` MUST-1/2).

---

## Status: NOT converged. Do not merge on the strength of this description alone.

**The three gating security findings are CLOSED. The clean round has NOT run.** Those are
different things, and only the second is convergence.

The adversarial round on `689f9ebd8` raised 9 findings, 2 HIGH. Verified in the code at
the time of writing, not taken from a status report:

- **F1** — a caller-supplied `repr()` reaching a log. **Closed AT THE SITE, and the
  original receipt here was OVER-SCOPED — corrected at `b981830df`.** What is true and
  re-verified: `d6030aefe` fixed `kaizen-agents/.../journey/manager.py:469,479`, which now
  use `type(handler).__name__`.
  What was FALSE: the claim that "`grep repr(handler)` returns nothing". It returns **22
  hits at HEAD, of which 11 are live source sites and 7 are the same defect class F1
  named** — a caller-supplied handler `repr` rendered into a log:
  `kailash-kaizen/src/kaizen/core/autonomy/hooks/manager.py:89,184,267`,
  `.../hooks/security/isolation.py:211,418`, `.../hooks/security/rate_limiting.py:118,153`,
  plus `src/kailash/utils/lifespan.py:82`, `src/kailash/runtime/distributed.py:1167`,
  `src/kailash/runtime/scheduler.py:1666`, `nexus/core.py:2429`.
  **How the receipt went wrong is worth stating, because the shape recurs:** the fixed file
  and the leaking file are BOTH named `manager.py`, in different packages. A grep scoped to
  the file just fixed returns empty and reads as a package-wide all-clear.
  These sites are **outside every boundary declared in this PR, and #2012 does NOT cover
  them** — the scanner inspects only the bound EXCEPTION name inside an `except` block, so
  a `repr()` of a non-exception value is invisible to it. Proven with a control:
  `repr(handler)` inside a handler → `[]`; `repr(e)` inside a handler → `[4]` (the
  instrument does fire, so the empty result discriminates). The leak is CONDITIONAL — these
  are `getattr(handler, "name", repr(handler))`, so the `repr` reaches the log only when the
  attribute is absent, which is a property of caller-supplied objects and not decidable at
  scan time. Exploitability is referred to security review; the coverage-claim gap is not
  conditional and is stated here.
- **F2** — the sink scanner blind to `exc_info`/`logger.exception`. Closed; the scanner
  handles `logger.exception` (Shape 3a) and explicit truthy `exc_info` (Shape 3b).
- **F3** — the preset choice unpinned. Closed by `test_remote_preset_claims_prefixless_credentials`
  / `test_local_preset_deliberately_does_not`, which pin the distinction on a
  prefix-less credential rather than a URL-userinfo shape both presets would redact.

F4–F9 remain open follow-ups. **A gate closing does not make a round clean — a clean
round is something that runs, not something that follows.** It has not run. Do not read
the closed gates as convergence.

**Measurement honesty: this branch is under continuous commit by concurrent lanes, and
HEAD moved four times during the verification pass** (`57e277b49` → `b417a83f9` →
`ce96848ae` → `95b142320`). Consequently:

- **Git-derived counts** below were taken at **`95b142320`**.
- **Suite results** were taken at **`b417a83f9`**, and the basis originally stated here —
  "everything between the two pins touches nothing inside the four packages those suites
  cover" — was **true of the range it named and is now STALE**. HEAD moved 11 commits past
  `95b142320`, two of which are nexus test commits (`82480af19` →
  `packages/kailash-nexus/tests/e2e/test_user_flows.py`; `4c5f7c5b2` →
  `packages/kailash-nexus/tests/unit/transports/test_webhook.py`). The
  "nothing inside the four packages" guarantee therefore no longer holds, and the
  inference it supported is **withdrawn**.
  **The numbers themselves survive on a fresh basis, not on that inference.** The suites
  were RE-RUN at **`b220704b5`** by the correctness lens of the clean round: nexus
  **2632 passed, 14 skipped** (exit 0); kaizen regression **1381 passed, 1 skipped,
  22 xfailed** — identical to the values pinned at `b417a83f9`. Provenance: re-run by that
  lens, not independently re-executed by the author of this line.
  **A final re-run at merge time is REQUIRED**, on the same terms as the git counts below —
  a suite result inherited across a moving HEAD is a claim about a tree that no longer
  exists.
- The source tree was clean at both pins. One untracked non-source file is present,
  `kaizen_implementation_test.log` — which is the artifact of **#2011** itself, left in
  place rather than deleted.

**Re-derive the git counts at merge time.** They were accurate when taken and the branch
has almost certainly moved since.

---

## What this branch fixes

Impact first. Each item is a real user-visible or operator-visible defect, not a cleanup.

**Specific classes of credential leak into logs and error messages are closed.** A
provider exception — a bad API key, a rate-limit rejection, a DSN with an embedded
password — could carry the credential itself into a user-facing error field, a WARN log,
or a traceback. Closed here: the `exc_info` / `logger.exception` traceback re-leak class
in kaizen (24 sites — `logging` renders the exception via the traceback's final line,
defeating a scrubber applied only to the message), the enumerated sinks named in the
individual commits, and the kaizen-agents and MCP sites. Pattern coverage is widened for
shapes that previously slipped: non-HTTP connection strings (`postgres://`, `redis://`,
`mongodb://`, `mysql://`), Slack tokens, and bare JWTs. Verified behaviourally, not by
reading the regexes.

**This is class-scoped, not package-scoped.** Read the entry under Known not fixed
before concluding anything about the kailash-kaizen package as a whole.

**Rate limiting works behind a proxy.** `trusted_proxy_cidrs` was accepted, documented,
validated — and had no effect on any of the four rate limiters, which all keyed on the
immediate TCP peer. Behind any load balancer or ingress, every client shared one bucket,
so a single caller could exhaust the limit for everyone. All four sites now derive the
key through one shared helper. Unconfigured deployments are byte-identical to before,
and a client sending `X-Forwarded-For` from an untrusted peer still cannot move itself
into someone else's bucket.

**A negative rate limit no longer silently disables rate limiting.** `Nexus(rate_limit=-1)`
was accepted; the SSE limiter treats anything failing `> 0` as "no limit configured", so
a typo'd minus sign removed the protection entirely rather than tightening it. It now
raises. `rate_limit=0` normalises to "unlimited" consistently across every surface.

**Workflow names are validated where they are registered.** Registration accepted names
that later failed deep inside FastMCP with an opaque pydantic error, leaving a
half-registered workflow; names that survived that check went on to return HTTP 400 from
their own execute route forever. `register()` now rejects them up front and names every
offending character. **This is a breaking change** — see below.

**Cache invalidation actually invalidates.** `UnifiedCache.clear()` did nothing on the
Redis backend while reporting success, so an operator who invalidated a cache got an
explicit confirmation and stale data indefinitely. Clearing now works, scoped to the
cache's own key namespace (never `FLUSHDB`, which would destroy every other consumer's
keys in a shared database). The rest of the sync surface — `get`/`set` — is also
non-functional on Redis and now says so loudly instead of silently returning nothing.

**Metrics are scrapeable.** Histogram percentiles were emitted in a form no Prometheus
scraper reads.

**The monitoring tests can now fail.** Three assertions across two E2E files reported
success when `GET /metrics` returned **404** — the branch fixes the _verification_, not
the product, but it is listed here because it changes what this PR's own green means.
`enable_monitoring()` registers the route unconditionally, so a 404 means monitoring did
not wire up; the genuine unavailability case (the optional `[metrics]` extra absent) is
now an `importorskip`, so a 404 for any other reason fails hard. Before this, the suite
could not distinguish "monitoring works" from "the endpoint does not exist" — the two
outcomes those tests were written to tell apart. A reviewer weighing the Verification
numbers is entitled to know three of them could not previously fail.

**The monitoring stop endpoint no longer reports "stopped" without stopping.**
`POST /api/v1/monitoring/stop` called `task.cancel()`, discarded the return, awaited and
inspected nothing, and returned `{"status": "stopped"}` regardless — `cancel()` only
_requests_ cancellation. This is the same false-success family as the cache `clear()` and
the orphaned subprocess above, but at the worst surface of the three: a `status` field is
a return value an orchestrator acts on, not a log line a human might read.

**Shutdown no longer wedges (#2008).** A pooled-executor path and an `MCPChannel.__del__`
doing cleanup work could deadlock during finalization. Pre-existing and production-side —
see the note under Issues for why it is filed as well as fixed.

**An MCP subprocess can no longer be orphaned while the transport reports "disconnected".**
`EnhancedStdioTransport.disconnect()` swallowed a failed process termination, nulled the
process handle in a `finally` regardless, and then logged success anyway. Three
consequences, the third being the serious one: a status scraper read the transport as
stopped; the child process could still be running — a real OS resource, leaked; and
dropping the handle made it **unrecoverable in-process**, because nothing was left to
retry the kill with. A second lock-out compounded it — `_connected` is cleared _before_
termination is attempted and the method early-returned on that flag, so even a retained
handle would not have been retried. Termination now reports success or failure honestly:
on failure the handle is kept, no success line is emitted, and the error names the
surviving pid so an operator can clean up. The existing `terminate` → wait → `kill`
escalation is preserved, with its second wait bounded — it was unbounded, so a kill that
did not land hung `disconnect()` forever.

**PostgreSQL identifiers stay inside the 63-byte limit.** Long model names generated
identifiers PostgreSQL rejects outright, or — worse — that collide after silent
truncation, so two distinct models could alias onto one physical table.

---

## Breaking changes

**`Nexus.register()` rejects workflow names it previously accepted.** Names containing
characters outside the MCP tool-name charset (SEP-986), names over 128 characters, empty
names, and names containing path separators now raise `ValueError` at registration. This
is deliberate: those names were never addressable — they either failed later with an
opaque error or returned HTTP 400 from their execute route forever. Documented in
`packages/kailash-nexus/CHANGELOG.md`.

**`Nexus(rate_limit=-1)` raises** instead of silently disabling rate limiting.

---

## Issues

```
Fixes #1970
Fixes #1972
Fixes #1974
Fixes #2007
Fixes #2008
Refs  #1996
```

Each `Fixes` was verified against the issue's own acceptance criteria — code cited by
`path:line`, and a test that actually exercises it and would red if the behaviour
regressed. `#1996` is already `STATE: CLOSED`, so it is referenced rather than closed
again.

**On #2008, because it is easy to read backwards:** it was filed even though this branch
fixes it (`a50fb78c6`, with `e13339c02` closing the sibling finalizer defect in the same
file). That is not filing a bug we just wrote. The defect is **pre-existing and
production-side** — every core release from `v0.8.6` (2025-07-22) through `v2.62.0`
carries it, and users on those releases are hitting unclean shutdowns with no public
record. The issue serves the released-version audience; the `Fixes` trailer serves this
branch. Both are correct at once.

**Referenced but NOT closed** — real work landed, acceptance criteria are not fully met:

- `Refs #1971` — identifiers are fixed and 171 regression tests pass, but AC-2 ("`test_multi_database_e2e` passes") needs a live PostgreSQL; those legs skip here.
- `Refs #1981` — structured output is requested, degradation is distinguishable at the API surface, and the all-zero ranking is gone; AC-3's cross-provider matrix has no leg that executes, because its live-provider test is unreachable in the kaizen tree.
- `Refs #2003` — the call-time envelope behaviour is pinned by tests, but the 2× storage defect itself is untouched: `input_envelope.py:126` still self-binds and `database.py:463` still persists it.
- `Refs #1997` — the Mistral key shape is pinned by a strict-xfail and still leaks; the gap is a documented design trade-off, not an oversight.
- `Refs #2009` — the discovery permission-checker error path GRANTS access (authz fail-open). Deliberately unchanged: flipping it means a transient checker outage denies every user, so it is security-reviewed work in its own right. Filed as the tracking receipt that distinguishes a reasoned deferral from a silent dismissal.
- `Refs #2010` — a stale E2E passes `description=` to `BaseAgent.__init__`, which has no such parameter. Git-proven pre-existing; cannot be verified RED→GREEN on a host with no provider.
- `Refs #2011` — a test writes `kaizen_implementation_test.log` into the repo root, dirtying CI checkouts and voiding the run-fingerprint protocol.
- `Refs #2012` — the 390-site un-triaged exception-sink surface in kailash-kaizen; deliberately its own shard, see Known not fixed.

**Deliberately unreferenced:**

- **#1995 must stay open, and referencing it here would violate its own acceptance criteria.** Its AC-4 requires the isort normalisation to land "as its own PR, not folded into a feature or bugfix branch", and its revisit trigger is `after-milestone:forest-release` — explicitly sequenced _after_ this branch ships, because a 2,000-file import shuffle would make this diff unreviewable. Only a scaffold-template exclusion (`#1995 prep`) is present here.
- **#2002** — no CI step for root `tests/regression/` was added; the gap is untouched.

---

## Known not fixed

Stated plainly so a reviewer does not have to discover them.

**Sync tools get no Redis caching, and the fix is architectural.** Measured: with no
event loop running the result is cached; inside a running loop `redis.store` stays empty
and the tool body re-executes every call. That second case is the _normal_ production
path — `_execute_tool:3459` calls `return handler(**arguments)` directly and there is no
`to_thread`/`run_in_executor` anywhere in the file. Closing it means either blocking the
event loop on a cross-thread Redis round-trip or offloading sync tools to a thread, which
changes execution semantics for every existing tool body. Neither ships here. The
degradation is now announced once per cache, naming the remedy available today: declare
the tool `async def` (async tools take a different path and were never affected).

**The kailash-kaizen credential surface is NOT swept — tracked as #2012.**

390 sites across 107 files in `packages/kailash-kaizen/src` where a caught exception's
text reaches a log record or a return value without passing through a credential
scrubber. This is an **un-triaged surface, not a defect count**: every site still needs
the "where can this exception be RAISED" (local vs remote) classification that
`kaizen-agents` already received, and only the remote-raised subset is a credential
channel — the rest are local `OSError`/`ImportError`/`JSONDecodeError` whose path and
module text are the diagnostic and must be preserved.

**28 of those sites sit in 8 files that ALREADY import a scrubber for their other
sinks.** Those 8 are the highest-risk subset and the place to start: a half-swept file's
import reads as evidence the file was handled, so it is where a reviewer is least likely
to look and most likely to be wrong. The remaining 362 sites in 99 files were never
touched by any sweep. **Every gap found in this round's reviews came from the half-swept
category, not the untouched one** — if you take one thing from this entry, take that.

Any commit body on this branch that framed the surface as "closed" was scoped to a
_class_, not to the package: this branch closed the `exc_info`/`logger.exception` class
in kaizen and left the raw-`{e}` class there almost entirely open. The asymmetry has a
structural cause worth knowing, because it predicts where the next gap will be —
kaizen-agents has an AST scanner guarding it and sits at 191 wrapped sites;
kailash-kaizen has none. The scanner is the difference, not the diligence. #2012 carries
the acceptance criteria and prescribes porting the scanner rather than hand-sweeping.

**No systematic sweep of RETURN surfaces exists anywhere — captured as a second lens
inside #2012.** Every sweep this session was log-shaped, and the lens is not merely
un-swept but **un-instrumented**: `_SinkScan` does not distinguish a log sink from a
return surface. It flagged `skill_tool.py`'s three return surfaces only _incidentally_,
because the exception name happened to appear in string context inside the handler.

**A path in a log is a diagnostic; the same path in a tool result is disclosure.** A
`NativeToolResult` reaches the **model** and persists in the transcript — an audience
strictly wider than a framework log, and one nobody rotates. A future shard porting the
scanner must classify sink-vs-return rather than lump them: the two need opposite
verdicts on the same text.

**The credential-sink sweep is mid-flight.** The ~30-site kaizen-agents surface is being
worked in another lane and part of it is still uncommitted; see Status.

**Stale tests against long-renamed APIs.** Five failure clusters in the kaizen tree are
**git-proven pre-existing** — `git diff --quiet origin/main...HEAD` reports UNCHANGED for
both the source defining each symbol and the test asserting it, so they reproduce
identically on `origin/main`. They are `SharedMemoryPool.add_insight` (renamed to
`write_insight`), `BufferMemory.clear_session` (renamed to `clear`),
`enable_observability(jaeger_endpoint=…)` (split into `jaeger_host`/`jaeger_port`), a
histogram-routing gap, and an output-contract mismatch. No production caller is broken:
every candidate call site resolves to a class that does define the method. Cleanup, not
regression — and deliberately not bundled into this branch.

**A zero-assertion E2E test that logs "PRODUCTION READY".** Plus a small set of vacuous
and mis-skipped tests catalogued during validation; the gating ones are fixed, the
remainder are budgeted.

---

## Verification

All commands run at the moment of writing. **Trees are run separately** — root `tests/`
and the package trees cannot be collected together (duplicate conftest basenames), and
`kailash-kaizen` and `kaizen-agents` likewise.

**Git-derived counts, at `95b142320`:**

```
$ git rev-list --left-right --count origin/main...95b142320   # 6 behind, 202 ahead
$ git diff --shortstat origin/main...95b142320
  376 files changed, 62260 insertions(+), 2924 deletions(-)
$ git diff --name-only origin/main...95b142320 -- '*test*' | wc -l      # 122
$ git log origin/main..95b142320 --pretty=%s | grep -oE '^[a-z]+' | sort | uniq -c
  78 fix · 62 docs · 30 test · 21 chore · 4 style · 2 feat · 1 perf · 1 build
```

**Suites executed at `b417a83f9`** (observed results, not collected counts):

```
$ pytest packages/kailash-mcp/tests               -> 670 passed, 1 xfailed
$ pytest packages/kailash-nexus/tests/regression  -> 166 passed
$ pytest packages/kailash-kaizen/tests/regression -> 1381 passed, 1 skipped, 22 xfailed
$ pytest packages/kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py
                                                  -> 319 passed
```

Both pins had a clean source tree.

**These are `tests/regression` SUBSETS (plus one single file), NOT whole package trees — do
not read them as tree coverage.** Whole-tree runs at `b954ed66a` by the clean round's
correctness lens: `packages/kailash-nexus/tests` **2632 passed, 14 skipped** and
`packages/kailash-mcp/tests` **670 passed, 1 xfailed** are genuinely clean and complete.
`packages/kailash-kaizen/tests` is **NOT** — `packages/kailash-kaizen/pytest.ini:13` sets
`--maxfail=10`, so a whole-tree run ABORTS at the tenth failure and its "156 passed" is an
abort count, not coverage. Nine of those ten look infrastructure/live-LLM dependent
(`docker-compose up failed`, `config/dev.env must exist`, `$OPENAI_API_KEY is unset`) —
**that diagnosis was not confirmed per-failure and must not be assumed.** The tenth is NOT
environmental: `test_full_integration_e2e.py::test_enterprise_workflow_integration` fails
`TypeError: BaseAgent.__init__() got an unexpected keyword argument 'description'`, which is
**#2010**, pre-existing (`origin/main` carries the identical signature and this branch
touched neither file) and still owed under `zero-tolerance.md` Rule 1. The core `tests/` and
`packages/kaizen-agents/tests` whole-tree runs were still IN FLIGHT when observed, and an
in-flight run is zero evidence — those two are **NOT EXAMINED**, not passing.

**The earlier "intervening commits touch nothing inside the four packages" justification is
WITHDRAWN here as it is in Status** — HEAD has since moved 11 commits past `95b142320`, two
of them nexus test commits. The numbers above stand on the re-runs cited, not on that
inference, and a merge-time re-run is required.

Collected-only counts, for scale (re-derived at `51a3e4eaa` — HEAD moved again during
this pass, which is the condition, not an anomaly):

```
tests/regression 1593 · tests/unit 4883 · kailash-mcp 671
kaizen regression 1404 · kaizen-agents 4076 · nexus regression 166
```

The 22 `xfailed` in the kaizen regression tree are **strict** xfails pinning documented
residuals (including #1997); each XPASSes and forces its own removal the moment the gap
closes.

**Version anchors — 9/9 self-consistent:**

```
root pyproject.toml 2.63.0 == src/kailash/__init__.py 2.63.0
align 0.7.4 · dataflow 2.20.0 · kaizen 2.46.0 · mcp 0.5.0
ml 2.2.3 · nexus 2.16.0 · pact 0.18.0 · kaizen-agents 0.13.0
```

**Not verified here:** no Redis is reachable on `localhost:6380` or `:6379`, so every
Redis-backed test in this branch runs against a deterministic in-process adapter rather
than a real server. Those tests verify the code against a _model_ of Redis. Likewise the
PostgreSQL-dependent legs of the #1971 suite skip without `POSTGRES_TEST_URL`.

---

## Reviewer guidance

The highest-value things to check, in order:

1. **Re-derive every number after the tree is committed** — all readings here include
   uncommitted concurrent-lane work, and the same command returned three different
   results during drafting for exactly that reason.
2. **The `Nexus.register()` breaking change** — is rejecting previously-accepted names the right call for your consumers?
3. **The four `Fixes` trailers** — each was verified against its issue's acceptance criteria, but they are durable claims and worth a second read.
4. **The sync-tool caching decision** — the measurement is in the commit body of `0523ad633`; the architectural options are named there rather than chosen.
5. **What "credential leak fixed" does and does not cover.** The closed work is
   class-scoped. `packages/kailash-kaizen/src` carries 390 un-triaged sink sites across
   107 files (#2012) — 28 of them in 8 files that already import a scrubber, which is
   where a reviewer is least likely to look — and
   is not swept, and no systematic sweep of RETURN surfaces has been done anywhere —
   every sweep this session was log-shaped, which is why a `NativeToolResult` reaching
   the model went unnoticed until a return-shaped lens was pointed at it.
