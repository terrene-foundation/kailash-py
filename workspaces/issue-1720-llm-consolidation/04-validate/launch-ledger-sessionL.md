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

---

## Wave 3 — round 10: NOT CLEAN, and the defect was in MY fix

`r10-security` delivered (after the same message-delivery failure `r9-correctness` had — it
needed an explicit "you MUST call SendMessage" prompt). No Bash, so all findings were inference
with named probes. **I ran every probe.**

| finding | probe result |
| ------- | ------------ |
| **F1 (HIGH)** raw sibling `type(exc).__name__` at 9 sinks | **CONFIRMED** — newline reached the record through the raw field while the helper's field rendered sanitized, 4 chars apart; 5000-char name unbounded |
| **F3** no totality guard on `safe_exception_frames` | **CONFIRMED** — shadowed `__cause__` property raised straight through the caller's `except` |
| **F5** CPython pseudo-identifiers mangled + `?`-form forgeable | **CONFIRMED** — `!listcomp!` → `?listcomp?` |
| **F6** walked-back claim live at 4 caller sites | **CONFIRMED** — grep returned all four |
| **F2** lying `__len__` str subclass defeats the bound | **REFUTED** — `re.sub` returns a plain `str` copy for a subclass; bound held at 131 |
| **F4** the `__getattr__` pin is satisfiable without the payload | route DOES fire; assertions rewritten to key on the payload's own bytes |

**F1 is mine.** Round 9 hardened the HELPER; nine call sites logged the same identifier RAW as a
sibling `%s` in the SAME log call. BOUNDED and STRUCTURALLY INERT were both defeated *in the record
the fix hardened*. Fifth consecutive round where a fix carried the class it was written to close —
and the pattern is now legible: each fix hardened the layer it was looking at, and the next round
found the same class one layer over.

**A correction the lens made on itself, worth keeping:** it first recommended DELETING the raw type
field as redundant, then withdrew that after the r9-correctness finding — the chain keeps the
INNERMOST links, so on a chain longer than the cap the caught exception's type is evicted and that
field is the only place it appears. Sanitize in place, never delete.

**F3 is worse than reported.** Writing its pin took pytest itself down with an `INTERNALERROR`:
`TracebackException` re-reads `__cause__` while formatting the failure, re-entering the shadowed
property and aborting the session. The pin now reduces the outcome to a string before any assert.

Landed `deac19f1b`: `safe_type_name()` at 14 sites across 7 modules, a totality wrapper, an
exact-match CPython pseudo-identifier passthrough, and the 4 corrected claims.
Verified: 33 pins, **1667** root regression, 379 scanner. Fail-first at `2448f4ec2`: 10 failed / 5
passed (the 5 are deliberately non-discriminating guards).

### A third instrument failure of my own — caught at commit review

The scripted sink rewrite used `read_text()`/`write_text()`, which silently converted
`visualization/api.py` from **CRLF to LF** — 914 lines of unrelated whitespace churn buried inside
a security commit, where the real change is 7 insertions / 5 deletions. Caught by reading the
`--stat` (1830 lines for a file I touched once), diagnosed with `--ignore-cr-at-eol`, restored, and
amended before push. A 914-line whitespace diff inside a security fix is exactly what makes review
unreliable.

### Status

**Merge gate NOT met.** Streak zero; the surface moved again at `deac19f1b`. A round 11 against
that SHA is owed. Scoped out with reasons: `base_async.py:304` (exception message embedding `{e}` —
runtime-hot-path shard), F7 (truncation keeps prefix), F8 (per-identifier bound ≠ per-record bound,
~52 KB worst case), F1-of-r9c (render does not name the caught type — design call, deferred).

---

## Wave 4 — round 10 CORRECTNESS lens (delivered late, same delivery bug)

**Independently NOT CLEAN, and it converged on the SAME HIGH from a different route** (it drove the
`lifespan` sink end-to-end; the security lens read the sinks statically). Already closed by
`deac19f1b` before its report arrived. It also **verified my fail-first claim** (12 failed / 3
passed) and found the 3 parent-passing pins each red under a mutation in their own subject area —
so none is vacuous.

**Its one apparent disagreement is not one.** It found NO vacuous pin in the round-9 file and
questioned `2153aca5b`'s "proven-vacuous pin". Both are correct: that claim is about the
**kaizen-agents SCANNER** file, a different file. Recorded so nobody re-litigates it.

### What was still open, and is now closed (`bd2f610c8`)

- **MED — a gap in MY OWN pins.** Only the class-name sanitization site was pinned; de-sanitizing
  `frame.name` or `_relative_frame_path(frame.filename)` left the suite GREEN. **I re-ran both
  against my 33-pin suite with the reach check confirming the wrapper was removed: 33 passed,
  twice.** I had pinned one site and assumed the siblings rode along. Both now pinned, each
  verified to red under its own mutation and only its own.
- **LOW — negative-cap `dropped` over-counted** (12-link chain announced 13). Third instance of one
  arithmetic bug in this function.

### REFUTED, recorded so it is not re-investigated

Its **P4** (`__context__` set to a non-exception) is a **probe artifact**: CPython rejects the
assignment itself (`exception context must be None or derive from BaseException`), so the helper
never sees it. P1–P3 were real and are closed by `deac19f1b`'s totality wrapper — re-measured, all
three now return `<frames-unavailable>`.

### The cross-package surface — MEASURED, and deliberately NOT fixed here

The lens is right that the real surface is wider than the 8 sinks in my brief. Measured
(production `src` only, `build/lib` excluded):

| package | raw `type(<exc>).__name__` sites |
| ------- | -------------------------------: |
| `src/kailash` (tree-wide, 47 files) | 81 |
| `packages/kailash-kaizen/src` | 60 |
| `packages/kailash-dataflow/src` | 54 |
| `packages/kailash-nexus/src` | 29 |
| `packages/kaizen-agents/src` | 14 |

**The 7 helper-sink files this fix scoped to now have exactly ONE residual** —
`base_async.py:304`, the documented exception-message exclusion.

**NOT scope creep into the rest, deliberately.** `type(e).__name__` is the ordinary Python idiom
and is only a channel where an attacker controls the exception CLASS NAME (a class minted via
`type(f"...{data}", ...)`). Triaging ~240 sites across four more packages for that property is its
own shard, well past a single shard budget, and this branch is already 311 commits with a known
"ONE TREE OF FOUR swept" framing. The number is recorded here so the follow-up starts from a
measurement rather than "subset unknown" — which is the gap the sweep report has carried for
several sessions.

### Status

**Merge gate NOT met.** Streak zero; surface moved again at `bd2f610c8`.
Tree-wide root `tests/` is ALIVE but starved — 46s CPU in 50min wall (~1.5%), output still
header-only. Both tree-wide task outputs are EMPTY (30 and 5 bytes): **zero evidence, not a pass.**

---

## Wave 5 — ROUND 11, mutation-first (user-approved)

| track | agent | status |
| ----- | ----- | ------ |
| r11 mutation-first correctness | `r11-mutation` | in-flight |
| r11 adversarial security | `r11-security` | in-flight |
| orchestrator mutation matrix | me | **DONE** |

### The orchestrator matrix — 18 behaviours enumerated, each mutated independently

First complete matrix over this surface in eleven rounds. **17 red on the first pass; ONE did not.**

```
pseudo_allowlist_widened          36 passed     <- REDS NOTHING
```

Widening the CPython pseudo-identifier membership test from exact-match to
`text.startswith("<") and text.endswith(">")` — the most natural "simplification" of that branch —
passed the ENTIRE suite.

**Proven a real pin gap under `instrument-discipline.md` MUST-2(b), not assumed.** The mutated file
was loaded DIRECTLY BY PATH (no ambiguity about which module ran), the mutation confirmed present in
the loaded source, and behaviour measurably changed:

```
'<+9999 outer links dropped, cap reached>'  -> PASSES THROUGH INTACT
'<truncated>'                               -> PASSES THROUGH INTACT
'<evil <- FORGED@a.py:1:f>'                 -> PASSES THROUGH INTACT
```

That is the module's load-bearing claim — *"a `<...>` marker in a record is always OURS"* — silently
defeated. The allowlist re-admits `<` and `>`, so EXACT membership is the only thing holding it, and
nothing tested that. `test_a_near_miss_does_not_survive` could not catch it (`!listcomp!` does not
start with `<`, so it satisfies a widened predicate too).

Closed in `2931bc4ca`. **Matrix re-run with the pin in place: 18 of 18 RED, none reds nothing.**

### A fourth instrument failure of mine, caught mid-probe

A bare `python -c` inside a worktree resolves `kailash` through the EDITABLE INSTALL to the **MAIN
repo**, not the worktree — so a mutation probe run that way silently measures UNMUTATED code. My
first reachability probe did exactly that and printed "sanitized" for all three payloads, which
would have dismissed a real finding. Caught by printing the resolved path. **pytest resolves
correctly** (the root conftest inserts the worktree's `src`), which is why every fail-first run this
session was sound. Every probe now proves its resolution before reading a result.

### Verified

```
42 pins · 1676 root regression (12 skipped) · 379 scanner
mutation matrix: 18/18 red
```

Merge gate still pending the two r11 agent verdicts.

### Round 11 SECURITY lens — NOT CLEAN, 1 CRITICAL. All seven probes CONFIRMED.

| finding | measured |
| ------- | -------- |
| **C1 CRITICAL** str subclass with lying `__eq__`/`__hash__` | `LEN 5043`, newline ✓, `" <- "` ✓, `@` ✓ — **whole chokepoint bypassed** |
| C1 reachability via `type.__name__` | `ROUNDTRIP-SUBCLASS: True` — the lens expected possibly-unreachable; it IS reachable |
| **H1 HIGH** lying `__suppress_context__` | `LEAKED: True` — `raise X from None` suppression defeated |
| **H2 HIGH** sink sweep cannot fail for the right reason | rewrite found **2 more live sinks** (`scheduler.py:1378/1409`) |
| M1 allowlist scope-creep | class named `<module>` rendered `<module>` |
| M3 Windows paths | `svc?db?connect.py` |
| L2 lying `__len__` | real diagnostic suppressed to `<empty>` |

All closed in `160cfc8de`. The root fix is **normalize to a plain `str` via `str.__str__` BEFORE any
predicate runs** — `str(value)` alone is insufficient because `__str__` is overridable too, so the
result is re-normalized on TYPE IDENTITY. H1 closed by reading the three walk attributes through
`BaseException`'s own descriptors, which defeats a shadow that RAISES and one that LIES in one move.

### TWO defects I introduced while fixing these — both caught by driving, not review

1. **The M2 telemetry called a module-level `logger` that did not exist** — a `NameError` inside the
   very handler whose contract is that it never raises. Found by driving the wrapper pre-commit.
2. **The M1 gating silently DISARMED my own round-11 marker-forgery pin.** Gating the allowlist
   behind `allow_pseudo` moved that pin onto the DEFAULT path where the branch never runs, so it
   passed under a widened allowlist. A fix that disarms its own pin is exactly the class this file
   exists to catch. Re-armed; the mutation now reds 6.

### The methodological finding — this is the one worth codifying

**My round-11 matrix reported 18/18 red and I read it as strong convergence. It was not.** A mutation
matrix perturbs the IMPLEMENTATION while holding the INPUT fixed, so it is structurally blind to a
defect whose vector is the TYPE of the input. The CRITICAL was found by READING.

Mutation testing and adversarial reading are **not substitutes**: the matrix proves pins
discriminate; reading finds the axis the matrix never varies. I recommended a mutation-first round
on the grounds that reading had been less productive — that recommendation was wrong, and the
evidence is that the worst finding of eleven rounds came from the instrument I deprioritized.

Also recorded: my matrix classified a syntactically-broken mutation's **NO OUTPUT** as GREEN. Zero
evidence is not a pass — the fourth instance of that trap this session, this time inside my own
harness.

### Verified

```
59 pins · 1693 root regression (12 skipped) · 379 scanner · 821 runtime/channels unit
fail-first at 00a74b5cc: 11/11 round-11 pins red
mutation matrix: 18 behaviours, all red (after re-arming the pin the M1 fix disarmed)
```

`r11-mutation` still in flight.
