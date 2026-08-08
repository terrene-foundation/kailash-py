# fix(forest): credential-leak sweep, rate-limit fail-opens, and the silent-degradation family

Replaces `pr-body-draft.md`, which **must not be opened as written** — it asserts
"Convergence was reached" (it was not), carries counts from an earlier HEAD, cites a
"round 3" gate that has since been superseded, and lists an incomplete set of filed
issues.

**Every number below was re-derived at the moment of writing**, with the command shown.
Nothing is carried from any prior document. This branch has already paid for two
correction cycles on carried claims (`verify-claims-before-write.md` MUST-1/2).

---

## Status: NOT converged. Do not merge on the strength of this description alone.

**Every test result below was taken against a working tree carrying UNCOMMITTED work
from concurrent lanes.** At the time of writing:

```
$ git status --porcelain packages/kaizen-agents/
 M packages/kaizen_agents/agents/nodes.py
 M packages/kaizen_agents/agents/register_builtin.py
 M packages/kaizen_agents/delegate/hooks.py
 M packages/kaizen_agents/delegate/session.py
 M tests/regression/test_local_error_sinks_are_scrubbed.py
 M tests/regression/test_log_sinks_do_not_releak_via_traceback.py
```

So these numbers describe **the tree, not the committed branch**. The committed-state
result is not established here, and re-deriving it after the tree settles is a
prerequisite to merging — not a formality. During drafting the same command at the same
HEAD returned `1 failed`, then `13 failed`, then `319 passed` across three reads; the
cause was reading a file while another lane was writing it, not a flaky test. It is
stable at `319 passed` over three consecutive runs now.

The adversarial security round on `689f9ebd8` raised 9 findings, 2 HIGH. F1 (a
caller-supplied `repr()` reaching a log) is fixed at `d6030aefe`. F2 (the sink scanner
being blind to `exc_info`/`logger.exception`) and F3 (the preset choice being unpinned)
have code and tests present and passing, but in **uncommitted** form. F4–F9 are open
follow-ups. **Convergence is not claimed, and cannot be until the tree is committed and
re-measured.**

---

## What this branch fixes

Impact first. Each item is a real user-visible or operator-visible defect, not a cleanup.

**Credentials stopped leaking into logs and error messages.** A provider exception —
a bad API key, a rate-limit rejection, a DSN with an embedded password — could carry the
credential itself into a user-facing error field, a WARN log, or a traceback. The sweep
routes provider errors through a scrubber at every surface that renders them, across
kaizen, kaizen-agents and MCP, and adds pattern coverage for shapes that previously
slipped: non-HTTP connection strings (`postgres://`, `redis://`, `mongodb://`, `mysql://`),
Slack tokens, and bare JWTs. Verified behaviourally, not by reading the regexes.

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

**Shutdown no longer wedges.** A pooled-executor path and an `MCPChannel.__del__` doing
cleanup work could deadlock during finalization.

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
Refs  #1996
```

Each `Fixes` was verified against the issue's own acceptance criteria — code cited by
`path:line`, and a test that actually exercises it and would red if the behaviour
regressed. `#1996` is already `STATE: CLOSED`, so it is referenced rather than closed
again.

**Referenced but NOT closed** — real work landed, acceptance criteria are not fully met:

- `Refs #1971` — identifiers are fixed and 171 regression tests pass, but AC-2 ("`test_multi_database_e2e` passes") needs a live PostgreSQL; those legs skip here.
- `Refs #1981` — structured output is requested, degradation is distinguishable at the API surface, and the all-zero ranking is gone; AC-3's cross-provider matrix has no leg that executes, because its live-provider test is unreachable in the kaizen tree.
- `Refs #2003` — the call-time envelope behaviour is pinned by tests, but the 2× storage defect itself is untouched: `input_envelope.py:126` still self-binds and `database.py:463` still persists it.
- `Refs #1997` — the Mistral key shape is pinned by a strict-xfail and still leaks; the gap is a documented design trade-off, not an oversight.

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

**The credential-sink sweep is mid-flight.** The ~30-site surface is being worked in
another lane and part of it is still uncommitted; see Status.

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

```
$ git rev-list --left-right --count origin/main...HEAD     # 6 behind, 180 ahead
$ git diff --shortstat origin/main...HEAD
  359 files changed, 59777 insertions(+), 2845 deletions(-)
$ git diff --name-only origin/main...HEAD -- '*test*' | wc -l          # 117
$ git log origin/main..HEAD --pretty=%s | grep -oE '^[a-z]+' | sort | uniq -c
  75 fix · 52 docs · 25 test · 21 chore · 4 style · 2 feat · 1 build
```

Suites executed (not collected — these are observed results):

```
$ pytest packages/kailash-mcp/tests            -> 663 passed, 1 xfailed
$ pytest packages/kailash-nexus/tests/regression -> 166 passed
$ pytest packages/kailash-kaizen/tests/regression -> 1381 passed, 1 skipped, 22 xfailed
$ pytest packages/kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py
                                                -> 319 passed  (3 consecutive runs)
```

**All four readings include uncommitted concurrent-lane work** (see Status). They are
not a measurement of the committed branch and must be re-derived once the tree settles.

Collected-only counts, for scale:

```
tests/regression 1591 · tests/unit 4883 · kailash-mcp 664 · kaizen regression 1404
kaizen-agents 4055 · dataflow regression 850/873 (23 deselected) · nexus regression 166
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
