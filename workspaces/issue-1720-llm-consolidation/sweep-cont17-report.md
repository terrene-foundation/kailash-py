# /sweep — Management Decision Report (cont-17)

main `506c5b9cd` · **16 PRs merged since 2026-08-12** · **39 issues open** · 1 PR open (loom's, not ours)

Every "complete" claim below cites a durable receipt (merge SHA / verified file state), per
`verify-resource-existence.md` MUST-4. No self-attested completion.

---

## 1. Completion status

### The headline: the CI blind spot is closed

**#2038 CLOSED** — receipt: PR **#2124** (`8b96e07a6`). Verified on main, not inferred: the
Tier-2 step carries no `continue-on-error`; the only `continue-on-error: true` left in
`unified-ci.yml` is line 146 (pyright, #73 — always out of scope).

**A green `gh pr checks` now carries information about the integration suite for the first
time in this repo's history.** Until this session it did not, and nobody could have known.

**#2129 CLOSED** — receipt: PR **#2131** (`46c738ad4`). Full tier, run exactly as CI runs it:
**2603 passed, 0 failed, 0 errors** (baseline `13 failed / 10 errors`).

### Landed this session (receipts = merge SHAs)

| PR    | Closes                     | What it bought                                                           |
| ----- | -------------------------- | ------------------------------------------------------------------------ |
| #2124 | **#2038**                  | Tier 2 gates the merge. The masking is gone                              |
| #2131 | **#2129**                  | The 23 tests the masking hid — three security changes' worth             |
| #2100 | **#2072**                  | **A default gateway no longer executes workflows for anonymous callers** |
| #2098 | #2083, #2092               | No component invents its own signing or encryption key                   |
| #2101 | #2084                      | Four observability flags now install the hooks they advertised           |
| #2103 | #2047, #2088, #2089, #2040 | MFA had no actor — every action authorized on a caller-supplied id       |
| #2105 | #2018–#2021, #2011, #2017  | Shutdown status reports what teardown actually established               |
| #2097 | #2078                      | PythonCodeNode was capping the host process's address space              |
| #2125 | (#2099)                    | Two operator-local files were loading as instructions every session      |

### Is the product complete and visible?

**Closer than at cont-16, and the biggest gap is now closed.** #2072 — a default `create_gateway()`
serving anonymous arbitrary workflow execution, proven on a real socket — is fixed.

**But the auth surface is still not uniformly covered.** #2112 reports a **seventh** un-gated HTTP
server (`visualization/api.py` serves runs and tasks with no auth parameter), and **#2108 reports
that `MiddlewareAuthManager.verify_api_key` can never succeed at all** — the underlying node
ignores its arguments and returns no success key. An API-key auth path that cannot authenticate
anyone is the fail-open counterpart of #2072.

### Committed-scope fraction

Of cont-16's prioritized queue, **the top four items all closed** (#2072, #2083, #2092, #2084,
plus #2047 and the CI keystone #2078). Issue count moved 36 → 39: that is discovery, and every
new item carries a measurement.

---

## 2. ETA to completion — in autonomous cycles

**To a complete + visible product: ~7–9 cycles** for the BUG + INVEST-NOW set.

| Bucket                                                                                                      | Items | Est. cycles |
| ----------------------------------------------------------------------------------------------------------- | ----- | ----------- |
| Auth-surface completion (#2108, #2112, #2102, #2114, #2104)                                                 | 5     | 1–1.5       |
| CI verification chain (#2074, #2076, #2133, #2119, #2067)                                                   | 5     | 1–1.5       |
| CI hang chain (#2081 → #2079 → #2002)                                                                       | 3     | 1.5–2       |
| Proxy hardening (#2085, #2087, #2091)                                                                       | 3     | 1           |
| Correctness (#2107, #2069, #2111, #2113, #2109, #2110)                                                      | 6     | 1.5         |
| Gemini 3.x tool loops (#2120, #2121)                                                                        | 2     | 0.5–1       |
| Remainder (#2000 #2010 #2039 #2044 #2052 #2056 #2057 #2075 #2086 #2106 #2116 #2117 #2118 #2127 #2128 #2029) | 16    | 1–1.5       |

Basis: single-shard items at ~0.25 cycle. **#2081 is the long pole** — the root regression suite
hangs on the CI runner and never completes, so it is diagnose-then-fix, not fix. It still blocks
#2002.

---

## 3. Prioritized immediate queue (BUG + INVEST-NOW, value-ranked)

Value-anchor for the queue: the co-owner's standing directive this session — _"burn down the
buckets"_ — plus the explicit approval of #2074/#2076 recorded below. Ranked by user-facing exposure.

1. **#2108 — `MiddlewareAuthManager.verify_api_key` can NEVER succeed.**
   _Implication:_ the API-key authentication path does not authenticate anyone. Either it is
   dead (users think they have auth and do not) or callers fall through to another path. Highest
   exposure open, and the direct sibling of the #2072 class just closed.
2. **#2112 — a seventh un-gated HTTP server.**
   _Implication:_ `visualization/api.py` serves runs and tasks with no auth parameter. #2100
   closed six surfaces; this is the one it did not reach.
3. **#2102 / #2114 / #2104 — auth-surface defects.**
   _Implication:_ a body-supplied `user_id` accepted when auth is on (#2102); a non-ASCII
   `X-API-Key` driving an unauthenticated traceback per request (#2114); an attacker-supplied
   JWT `key_id` interpolated into a log line (#2104).
4. **#2133 — CI never runs on main** _(filed this sweep — see Decision D1)_.
   _Implication:_ nothing verifies what you actually ship from. Same class as #2038.
5. **#2074 / #2076 — CI selectors** _(APPROVED this session)_.
   _Implication:_ 855 kaizen tests are green-by-absence; five jobs run selectors matching zero
   tests and exit 5. Same blind-spot class as #2038, one layer over.
6. **#2081 → #2079 → #2002 — the CI hang chain.**
   _Implication:_ the root regression suite never completes on the runner, so #2002 stays blocked.
7. **#2107 — ten `__del__` finalizers call `close()` inside `try/except Exception: pass`.**
   _Implication:_ this is the documented logging-lock deadlock class (`patterns.md` § Async
   Resource Cleanup) — non-deterministic, surfaces under test load, "works in dev".
8. **#2085 #2087 #2091** proxy hardening · **#2069** provider detection fails open ·
   **#2111** a fifth advertised-but-unimplemented subsystem · **#2120 #2121** Gemini 3.x tool
   loops cannot terminate · remainder.

---

## 4. Deferred-quality backlog

**Empty — and legitimately so.** `gh issue list --label deferred-quality` returns nothing.

The six items flagged INVALID at cont-16 (#2011 #2017 #2018 #2019 #2020 #2021) were re-triaged
as ordinary bugs per the co-owner's D2 decision and **all six closed via #2105**. The label now
has no members, so the Sweep-N "still wanted?" gate has nothing to fire on.

This is the outcome the label is supposed to produce: items either get fixed or get an honest
disposition, rather than decaying under a label nobody revisits.

---

## 5. Decision points for the co-owner

**D1 — #2133: CI never runs on main. Which fix?**
Measured: `unified-ci.yml`'s `push:` branches are `[feat/*, feature/*, fix/*, docs/*, session/*]`
— `main` is absent, and the API confirms no `CI Pipeline` run has ever executed on main.

- _Option 1 — add `main` to `push:`._ **Pro:** every merge verified; detection immediate.
  **Con:** one full matrix (~45 min runner time) per merge, on top of the PR run — and this repo
  has an active CI-spend concern.
- _Option 2 — nightly scheduled main run._ **Pro:** most of the coverage at a fraction of the
  cost. **Con:** up to a day of lag; a broken main can ship in that window.
- _Option 3 — require branch-up-to-date + required status checks._ **Pro:** _prevents_ the
  stale-green merge instead of detecting it. **Con:** changes the admin-merge workflow you
  currently rely on; branch protection today declares no required checks at all.

**Recommendation: Option 2 + Option 3.** 3 prevents the actual failure mode (two independently
green PRs merging into a broken main) at zero recurring cost; 2 catches what slips through for
one matrix run a day rather than one per merge. Option 1 is the most thorough and the least
proportionate to this repo's merge rate.

**D2 — #2119: the LOC invariant is RED on main.**
Verified on disk: `base_agent.py` is **1068 lines against a 1015 limit**. Per
`refactor-invariants.md` the guard exists precisely to catch re-inlining, and it is currently
failing. _Recommendation:_ treat as a BUG (it is a red test on main, not polish) and fix in the
CI-verification wave alongside #2074/#2076 — the same lane, and it is one extraction.

**D3 — the `xfail` marked "flaky" that was swallowing a real error.**
`test_async_execution_no_threading` carries `xfail(reason="Flaky: async event loop pollution")`
but was in fact catching `ServerAuthNotConfiguredError`. It now genuinely passes (XPASS,
non-strict, does not fail CI). _Recommendation:_ remove the marker, but only after a handful of
full-suite runs confirm it is stable across orderings — the stated reason (ordering-dependent
pollution) is exactly the thing a single green run cannot disprove. Low value, low risk; fold
into the CI wave.

---

## 6. Recommendation — next steps, for ratification

1. **#2074 / #2076 — APPROVED, start here.** The blind-spot class this session proved is real
   and expensive. 855 tests green-by-absence is the same lie #2038 was, one layer over. Fold in
   **#2119** (D2) and **#2067** (also red on main) — one CI-verification wave.
2. **The auth-surface completion set (#2108, #2112, #2102, #2114, #2104).** #2108 is the highest
   open exposure: an authentication path that cannot authenticate. #2100 closed the anonymous-
   execution hole; this finishes the surface it started.
3. **D1 (#2133)** — ratify the CI-on-main disposition. Cheap to decide, and it protects
   everything else on this list.
4. **#2081 → #2079 → #2002** — the CI hang chain. Long pole; start it early because it is
   diagnose-then-fix and blocks #2002 regardless of what else lands.
5. **Proxy hardening (#2085, #2087, #2091)** — held twice now. Worth scheduling rather than
   deferring a third time.
