# Launch Ledger — Session L (2026-08-09)

Durable per `rules/orchestration-launch-ledger.md` MUST-1. Consult BEFORE every spawn (MUST-2);
match every completion notification against it BEFORE reacting (MUST-3).

Branch `fix/issue-1720-forest-drain`, 301 commits ahead of `main`, no PR open.
Entry state: session K stopped at the `completion-criterion.md` MUST-4 **circuit breaker** —
8 redteam rounds, consecutive-clean streak **ZERO**, three commits never reviewed by any lens.

## Host constraint (measured this session, gates lane C)

| measurement                            | value                                  |
| -------------------------------------- | -------------------------------------- |
| load average (1m / 5m / 15m)           | 333 / 291 / 249 — **rising**           |
| cores                                  | 16 (≈21x oversubscribed)               |
| stranded root `tests/` run (PID 78292) | **39.93s CPU in 1h42m wall = 0.65%**   |
| `/tmp/treewide_rest.log`               | 48 bytes — header line only, no result |

Load source is ~22 concurrent sessions on this host, NOT this repo. Tree-wide suites are a merge
gate and must be READABLE, not merely finished — deferred, not skipped.

## Wave 1 — dispatched

| track                      | agent            | branch | status                              |
| -------------------------- | ---------------- | ------ | ----------------------------------- |
| redteam r9 correctness     | `r9-correctness` | —      | in-flight                           |
| redteam r9 security        | `r9-security`    | —      | in-flight                           |
| issue-text corrections     | orchestrator     | —      | **DONE** — 4 posted, 1 labelled     |
| `tests/regression/` (1646) | bg `bnor0pnfy`   | —      | in-flight (re-launched — see below) |
| tree-wide suites           | —                | —      | **BLOCKED on host load**            |

### Lane C outcome — the session-K note's own #2013 claim was FALSE

Every claim re-verified against HEAD before any durable write
(`verify-claims-before-write.md` MUST-2: cross-boundary reconstructions presumed false). One did
not survive:

- **#2013 — SUPERSEDED BY MY OWN LATER MEASUREMENT. See Wave 2 § "A durable public claim I got
  wrong".** What I wrote here first, and posted publicly, was: "`hasattr(gw, "enable_auth")` is
  **True** because `APIGateway` assigns `self.enable_auth` as a bool attribute
  (`api_gateway.py:163`), so `gw.enable_auth()` raises `TypeError` into a swallowing `except`."
  **That is WRONG and is left visible here rather than edited away.** `create_gateway` never
  returns `APIGateway`; measured across all three server types, `hasattr` is **False** on every
  path, so the branch is DEAD CODE — no `TypeError`, no error log. The session-K note was RIGHT on
  that point and I was wrong; I inferred the gateway type instead of resolving it.
  **What survives, and is the load-bearing half:** `use_plugin("auth")` runs **unconditionally**
  (so "complete no-op" is still wrong), and `plugins.py:103` guards on `set_auth_manager`, which
  **exists nowhere in the tree** (grep exit 1) — a real `MiddlewareAuthManager` is built and
  attached to nothing. `_auth_enabled`/`_auth_manager` are write-only.
- **#2014 — CONFIRMED.** Logs `SECURITY: Hook isolation failed…` (`isolation.py:468-473`) then
  falls back to `super()._execute_hook` — fail-open, loudly. `test_process_isolation` has exactly
  ONE assertion (`:237 assert isinstance(results, list)`), true on both branches ⇒ not coverage.
- **#2015 — count NOT asserted; ENUMERATED instead.** AST walk over `src/` + `packages/*/src/`:
  **154 sink calls considered, 35 reference an exception, 27 of those bare**. The note's "26" was
  a cross-boundary number with an unstated denominator — replaced with a reproducible method.
- **#1997 — CONFIRMED and WIDER than the note.** Probed both presets: Mistral, Groq and xAI leak
  under **BOTH** (the note said only Mistral); Cohere leaks under local only. Root cause: `grep -ic`
  for each of the four vendors in `credential_scrub.py` returns **0**.

### Two instrument failures of my own, recorded rather than quietly fixed

1. **`$?` after a pipe.** `grep … | head; echo $?` reports `head`'s status, so it printed
   `exit=0` (“confirmed”) for a grep that had **not** matched. Re-run with the grep unpiped.
2. **`nohup … &` inside `run_in_background`.** The launching shell exited immediately with code 0
   and killed pytest at ~190/1646 tests, producing a truncated log and a **false completion
   signal**. `evidence-first-claims.md` MUST-3: that is zero evidence, not a pass. Re-launched
   under harness management (no `&`). **Do not read `/tmp/regression_sessionL.log` as a result.**

### Host reclaim

Stranded session-K root `tests/` run (PID 78292) killed — 39.93s CPU / 1h42m wall, header-only
log, zero progress. Nothing lost; it was competing for a starved scheduler.

Surface under review (materialized at `redteam-round9/unreviewed-surface.diff`, 221 lines):

- `a17c95e76` — `src/kailash/utils/secure_logging.py` (+90/-23), chain-cap eviction fix
- `7d14e0b7e` — committed WITHOUT running the suite; went red on nine files
- `a87890fd6` — narrowed shape 8 after the first cut over-reached

Both lenses dispatched per `agents.md` § "Correctness-Review-Clean Is Not Security-Clean".
Concurrency 2 (cold-start cap ~3 per `worktree-isolation.md` Rule 4).

---

## Wave 2 — round 9 verdict, fix, and round 10

### Round 9: NOT CLEAN (security lens, 6 findings — 1 HIGH)

The correctness lens **returned nothing** — zero evidence per `agents.md` § Redteam Reviewer
Dispatch, NOT a clean round. Re-dispatched as `r10-correctness`.

The security lens had no Bash, so all six findings were INFERENCE with named falsifying probes.
**I ran the probes.** Five reproduced as measured fact; one was refuted as written:

| finding                                | probe result                                                     |
| -------------------------------------- | ---------------------------------------------------------------- |
| F1 `__getattr__` → `__qualname__`      | `'postgres://svc:hunter2@h/db'` emitted **verbatim**             |
| F1 5000-char `__qualname__`            | returned at **full length** — unbounded                          |
| F1 `property` for `__qualname__`       | **REFUTED as written** — `TypeError` at class creation           |
| F2 `__context__` inner-chaining        | `KeyError("REAL_FAILURE")` **evicted**; docstring absolute false |
| F4 newline in class name               | constructible; **1 newline** injected — forged log line          |
| F4 `" <- "` / `<+N ...>` in class name | **forged** the record grammar                                    |
| F5 `_MAX_CHAIN_LINKS = 0`              | **12 links rendered** — N3 class recurs                          |

### The meta-finding that changed the fix shape

Rounds 6/7/8/9 each found a defect in the PRIOR round's fix. All six r9 findings are ONE class:
an attacker-influenceable string reaching a log record unsanitized and unbounded. A sixth point
patch would have been the fifth iteration of that loop. Fixed at a **chokepoint**
(`_safe_identifier`) instead — `613d8a197`.

Contract deliberately NOT secrecy: **bounded** + **structurally inert**. A short caller-chosen
name still reaches the record on purpose; it is often the only diagnostic there is.

Three false claims corrected rather than deleted (module header + `safe_callable_name` still
asserted the proposition N1 measured false; the chain-cap docstring's "always survives
truncation"; the walk's "costs nothing").

### Verification

```
new pins at parent (isolated worktree at HEAD, never git stash):  12 failed, 3 passed
new pins after fix:                                               15 passed
root tests/regression/:                          1649 passed, 12 skipped   74.92s
kaizen-agents sink scanner:                       374 passed                9.03s
```

The 3 pins passing at parent are deliberately non-discriminating honest-contract pins; r10 was
asked to check that claim rather than take it.

### Round 10 — dispatched against MY fix

`r10-security` + `r10-correctness` against `613d8a197`. The fix is the FIFTH in the chain and is
itself unreviewed; base rate of fix-introduces-defect on this surface is 4-for-4.

**Streak is ZERO and the surface MOVED** (`completion-criterion.md` MUST-3 resets on a change to
the surface). Merge gate NOT met.

### A durable public claim I got wrong, and corrected

My first `#2013` comment asserted `hasattr(gw, "enable_auth")` is True because `APIGateway`
assigns it as a bool attribute. **Wrong** — `create_gateway` never returns `APIGateway`.
Measured across all three server types:

```
enterprise  EnterpriseWorkflowServer   hasattr(enable_auth)=False
durable     DurableWorkflowServer      hasattr(enable_auth)=False
basic       WorkflowServer             hasattr(enable_auth)=False
```

The guarded branch is DEAD CODE; there is no `TypeError` and no error log. The session-K note was
right on that point and I was wrong. Correction posted as a follow-up comment rather than an edit,
so the record shows what was claimed and what the measurement returned. The load-bearing finding
(`set_auth_manager` exists nowhere → the auth manager is attached to nothing) is unaffected.

### Round 9 CORRECTNESS lens — also NOT CLEAN (8 findings), delivered late

It self-reported a delivery failure (three reports emitted as plain text, never received). The work
was genuinely run — its RAN-SIGNAL carries real commands and output. **Round 9 is therefore NOT
CLEAN from BOTH lenses.** It explicitly did NOT disagree with the security lens: it also found
defects in `a17c95e76`'s chain-cap code.

**Substantive findings I re-verified myself (all CONFIRMED):**

| # | finding | my measurement |
| - | ------- | -------------- |
| F5 | `__suppress_context__` ignored — `raise X from None` | `__suppress_context__=True`, render still emits `KeyError@…` — **leaks the suppressed context** |
| F1 | chain cap drops the CAUGHT exception's type | `HTTPGatewayError` **absent**; render is `<+23 outer links dropped> <- RuntimeError… <- KeyError` |
| F6 | docstring branch condition wrong | code `cwd != _HOME_DIR` (strictly above) vs docstring "at/above" |

**F2 — a PROVEN-VACUOUS test, and the proof is properly constructed.** The shape-8 block added by
`7d14e0b7e`/`a87890fd6` is entirely unpinned: mutation (remove the block) → 374 passed BOTH ways,
AND reachability shown (`HEAD -> ([4], [])` vs `PARENT -> ([], [])`), so the mutation reaches the
code and changes behaviour yet reds nothing. That satisfies `instrument-discipline.md` MUST-2(b) —
genuinely vacuous, not an inert mutation. The commit's own stated goal ("the day somebody writes
it, the pin must not stay green over a real leak") is unenforced.

Also: F3 duplicate "Shape 8" label (nine cross-references now resolve to two definitions), F7 early
`return` undercounts (contradicts the containing method's own docstring), F8 dead guard
(`value is not None` can never fire on `ast.Dict.values`), F4 the blanket exclusion also spares the
leaky class and `extra=dict(error=e)` was never closed by either commit.

**It also caught a real limit in MY greens:** `test_f11_caller_repr_leak_core.py` uses 2-link
chains, far under the cap, so it never reaches the eviction path — it is green and BLIND to F1.
The tree-wide green is blind the same way. Noted rather than argued.

**Its scope bound, carried:** correctness lens only, NO security scoring — per `agents.md` its
verdict is zero evidence about this trust-bearing surface's security posture. Its F4 residual
(safety of the nine sites resting on `ReasoningDegradedError.error` being pre-sanitised) is
INFERENCE from a docstring, not measured.

### Sequencing decision — holding commits until r10 returns

`r10-security` + `r10-correctness` are mid-review against `613d8a197`. Committing the r9-correctness
fixes now would move the surface under them and make their verdicts stale
(`completion-criterion.md` MUST-3). The fixes are prepared and will land as ONE combined change
after r10 reports, followed by a single fresh round — rather than a sixth point-patch mid-review.
