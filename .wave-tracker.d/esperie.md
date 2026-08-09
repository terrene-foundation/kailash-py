# Wave tracker — esperie

## Status: WAVE 1 (F10 leak-class closure) IN FLIGHT — 2026-08-09, session J

Branch `fix/issue-1720-forest-drain` @ `b954ed66a`. Session I's clean round **REFUTED**
the branch (verdict preserved below). Wave 1 closes F10, which GATES F7 (PR + `/release`).
Read this BEFORE spawning anything (`orchestration-launch-ledger.md` MUST-2). Match every
completion against the table BEFORE reacting (MUST-3).

### Session-J ground-truth reconciliation (orchestrator, first-hand, BEFORE dispatch)

Every session-I finding was re-verified against the current tree — `wave-loop.md` MUST-7.
Real path is `packages/kaizen-agents/src/kaizen_agents/patterns/patterns/` (session I's
notes said `.../src/patterns/patterns/`, which does not exist — one path segment wrong).

| finding                      | verification command                  | result                                                                                         |
| ---------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------- |
| HIGH(a) 7 `format_exc()`     | `grep -rn format_exc <patterns dir>`  | CONFIRMED 7: blackboard 281,322 · meta_controller 246 · ensemble 264,315 · parallel 148,258    |
| HIGH(a) scrub-beside-leak    | `sed -n 135,160p parallel.py`         | CONFIRMED — `:143` `scrub_remote_error(e)` and `:148` raw `format_exc()` in the SAME dict      |
| HIGH(b) raw `str()` returns  | `sed -n 248,262p` + `sed -n 235,250p` | CONFIRMED — `parallel.py:251` `str(result)`, `meta_controller.py:243` `str(error)`, unscrubbed |
| MED(d) missing key names     | `grep -c 'secret_key\|passphrase'`    | CONFIRMED absent — count **0** in `credential_scrub.py`                                        |
| MED(c) `_SinkScan` blindness | `grep -n _SinkScan`                   | scanner at `kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py:161`         |
| pinned counts                | `:135` comment                        | `53 -> 57 files, 185 -> 191 sites` — these MUST move when the teaching takes                   |

Additional defect the orchestrator found while verifying, NOT in session I's report:
`parallel.py:258` calls `format_exc()` from a loop body that is **not inside an except
handler** (the exception arrives as a `gather(return_exceptions=True)` value). There is no
active exception there, so it returns whatever unrelated exception last propagated, or
`"NoneType: None"` — a wrong-traceback leak, not merely a raw one.

### Launch ledger — Wave 1

Base for all three worktrees: `b954ed66a`. Worktrees are SIBLINGS outside the repo at
`/Users/esperie/repos/kailash/build/.kailash-py-wt/` per `worktree-isolation.md` Rule 1+7.
File partitions are DISJOINT — no two shards touch the same file.

| agent            | shard                                 | worktree / branch             | partition                                                               | status    |
| ---------------- | ------------------------------------- | ----------------------------- | ----------------------------------------------------------------------- | --------- |
| `w1-sinks`       | F10 HIGH(a)+(b) — the 9 leak surfaces | `.kailash-py-wt/f10-sinks`    | `kaizen_agents/patterns/patterns/*.py` + its tests                      | in-flight |
| `w1-scanner`     | F10 MED(c) — teach `_SinkScan`        | `.kailash-py-wt/f10-scanner`  | `kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py` | in-flight |
| `w1-scrubber`    | F10 MED(d)+(e), LOW(f)                | `.kailash-py-wt/f10-scrubber` | `credential_scrub.py`, `claude_code.py`, `kaizen/__init__.py`           | in-flight |
| `w1-correctness` | re-dispatch of session I's LOST lens  | read-only, main checkout      | none (read-only)                                                        | in-flight |

`w1-correctness` re-runs the correctness/closure-parity lens that never returned in session
I, PLUS the two items session I's security lens explicitly marked NOT EXAMINED (it had no
Bash): `bb8a3f966` (monitoring stop) and four of seven retained named fields.

### `w1-scanner` RETURNED — DONE, commit `bf164efc1`. Three corrections to MY brief.

Four shapes taught (`format_exc` module-wide/name-independent; exception-as-VALUE via three
region producers; `%`/`.format()`; exception ATTRIBUTES behind an allowlist so an
unanticipated attribute defaults to FLAGGED). RED established per shape against the
pre-change scanner extracted via `git show HEAD:` — **17/17 fixtures BLIND untaught,
detected taught**. Zero false positives in the real package. Passes union by
`(lineno, col_offset)`, not by line, so overlapping regions cannot double-count the pin.

**CORRECTION 1 — my brief named the WRONG INSTRUMENT, and it would have manufactured a
false negative.** I told the shard to expect the pinned `57/191` to MOVE and to treat a
non-moving count as "the teaching did not take". Wrong: the pin counts **WRAPPED** sinks,
which move when sites are **FIXED**, not when a shape is taught. Teaching moves the **BARE**
count — observed `0 → 10` package-wide. Taken literally, my instruction would have sent the
shard chasing a number that could not move. Recorded because the failure mode is this
wave's own subject: I named a check that could not discriminate the hypothesis.

**CORRECTION 2 — `parallel.py:251` is the `isinstance` guard; `str(result)` is at `:256`.**
My brief was off by five and I passed that to `w1-sinks` too. No harm: it worked from source
rather than my line numbers. Verified first-hand.

**CORRECTION 3 — a TENTH live site, in NO partition.**
`packages/kaizen-agents/src/kaizen_agents/delegate/loop.py:767` —
`logger.error("Unexpected error in parallel tool execution: %s", result)`, where `result` is
a `BaseException` from `gather(return_exceptions=True)`, narrowed at `:763`, logged raw.
**Thirteen lines earlier `:754` scrubs correctly**, under a comment block explaining this
exact defect class. The file already knows the rule, applies it on the `except`-bound path,
drops it on the `gather`-value path — the same scrub-beside-leak shape as `parallel.py`, in
a second file. Verified first-hand. **Routed to `w1-sinks` to fix IN-SHARD**
(`autonomous-execution.md` MUST-4: same bug class, one-line + test, context already warm —
filing it would cost 2–5× to reload).

**PIN HANDLING AT INTEGRATION — do not skip this.** The shard left the pin at `57/191`,
correct for its own tree (sibling fixes absent). Predicted post-fix: **58 files / 201 sites**
(+10 sites; +1 file because `meta_controller.py` currently has ZERO wrapped sinks and joins
the swept set). **RE-DERIVE — do not trust that arithmetic.** Its suite is `344 passed,
5 failed`, and **all 5 failures are the coverage assertion correctly flagging the live
leaks**. They go green when `w1-sinks` lands, at which point
`test_the_sweep_covers_the_measured_surface` REDS until the pin is re-derived. A green
5-failure→0 transition without a pin red means something is wrong.

**~~Owed: a `git.md` hooks-bypass disclosure for `bf164efc1`.~~ WITHDRAWN — nothing was
bypassed.** This row asked for a disclosure of a `core.hooksPath=/dev/null` commit. It is
superseded by § "NO COMMIT IN THIS REPO IS HOOK-CHECKED" below: this repo's `core.hooksPath`
points at a non-existent directory in another repo, so the flag was a **no-op and there was
never a hook to bypass**. The obligation was owed for an event that did not occur.

**Corrected here because it was corrected in ONE place and not this one** — the exact drift
recorded against the F1 receipt earlier in this session (a claim restated in two places gets
fixed in one). Caught by the shard whose work the stale row named.

### `w1-correctness` RETURNED — **REFUTED, a SECOND independent axis.** Pinned `b954ed66a`.

It had Bash and ran the controls the session-I security lens could not. Two of that lens's
NOT PROVENs are now proven; one NOT EXAMINED became a **confirmed live credential leak**.
All headline claims re-verified first-hand by the orchestrator before acting.

**HIGH-1 — a SHIPPING credential leak, proven by EXECUTION, not by reading.**
`packages/kailash-kaizen/src/kaizen/l3/event_hooks.py:118-124` renders a caller-registered
`listener` via `%r` on the same log line where it correctly scrubs the exception. A
`functools.partial` and a callable object each carrying a synthetic key were registered and
the real logger captured: `records emitted : 2  records leaking : 2`.

**The comment above it refutes its own conclusion, in the same paragraph.** It says
_"Listeners are caller-registered"_ and then _"none is exception-derived."_ Both true. But
**"not exception-derived" is the WRONG SAFETY TEST** — the question is whether the value is
CALLER-SUPPLIED, and a caller-registered listener is arbitrary user code that can hold
credentials. `20f507bb0` wrote the premise that refutes it, one sentence apart. Byte-for-byte
the class `d6030aefe` closed one package over IN THIS BRANCH, never swept here.

**HIGH-2 — same class at ≥5 more sites** (`resolver.py:381`, `:552-555` ×2,
`nexus/core.py:2429`, `runtime/distributed.py:1167`, `runtime/scheduler.py:1666`,
`utils/lifespan.py:82`). Mechanism CONFIRMED by execution: a `partial` has neither
`__name__` nor `__qualname__`, a dataclass has no `__qualname__` — so the `getattr` fallback
fires for exactly the objects that carry payloads. Per-site reachability PLAUSIBLE, not
confirmed; `w2-core-repr` owns settling it.

**`distributed.py:1167` + `scheduler.py:1666` ALSO carry `exc_info=True`** — live
counterexamples to `689f9ebd8`'s claim to have closed the exc_info re-leak class. Verified.

**HIGH-3 — a SECOND instrument, blind on a DIFFERENT axis.**
`04-validate/find-unsanitized-provider-errors.py` keys on `except … as <v>` handlers
rendering `<v>`. In HIGH-1 the leaking value is the LISTENER — no binding exists to trace.
Run against the tree just PROVEN to leak: `{"high": [], "high_count": 0}`. So: the security
lens found the scanner marking files SWEPT **while carrying** the defect; this lens found a
defect shape the scanner **cannot express at all**. `20f507bb0`'s "residual sweep returns
exactly the three documented keeps and nothing else" inherits that blindness.

**`bb8a3f966` HOLDS — proven, NOT vacuous.** Driven against the real pre-fix file
(`git show bb8a3f966^:…`): pre-fix returned `{'status':'stopped'}` on a surviving task, so
the test DISCRIMINATES. Session I's NOT EXAMINED is CLOSED.
**MEDIUM-1 — but the false success MOVED one endpoint over.** Retaining the handle (correct
per the commit's own reasoning) makes `start_monitoring`'s `if not self._broadcast_task`
guard read the wedged task as already-running: `api.py:311-316` reports `started` while the
only broadcast task is the one `stop` refused to certify as stopped. Same defect-contract
class, unclosed. `SimpleDashboardAPI.stop_monitoring` (`api.py:747`) checked — NOT a sibling.

**MEDIUM-2** — the cancellation-swallow `bb8a3f966` deliberately avoided is live at
`channels/api_channel.py:236-240` + `channels/cli_channel.py:312-316`.

**TEST TREES — a "green across five trees" claim is UNSUPPORTED.** nexus `2632 passed, 14
skipped` CLEAN; mcp `670 passed, 1 xfailed` CLEAN. **kaizen ABORTED** — `pytest.ini:13` sets
`--maxfail=10` (verified), so its `156 passed` is NOT tree coverage. Core + kaizen-agents
INCOMPLETE (in flight at report time; an in-flight run is ZERO evidence). One kaizen failure
is NOT environmental: `BaseAgent.__init__() got an unexpected keyword argument 'description'`
— pre-existing (`origin/main` carries the identical signature; the branch touched neither
file), already tracked as **#2010**, still owned under `zero-tolerance` Rule 1.

**PROVEN CLEAN — a real regression hypothesis that did NOT hold.** `llm/routing/fallback.py`
classifies on `str(error).lower()` against `"invalid api key"` / `"rate limit"`, so a
scrubbed string would mis-route provider failures. Both call sites (`:399`, `:523`) pass the
RAW exception; only the log/serialization path is sanitized. **No routing regression.**

**Retained named fields — the seven could NOT be recovered.** No committed report enumerates
them and the ledgers name overlapping sets, so the lens derived an acceptance surface
independently (`completion-criterion` MUST-2) rather than guessing. `listener` repr REFUTED
(HIGH-1); callback INDEX holds (an int cannot carry a payload); `event_type`/`agent_id` hold.
Six more PLAUSIBLE-not-probed; `tool_name` is a HIGH-1 sibling IF any tool name is
caller-supplied — **unsettled**. `interpretability/core.py` ×2 + the `__init__.py` exc_info
keeps: **NOT EXAMINED.** That the seven are unrecoverable from the committed record is itself
a finding — a receipt naming a count without naming its members cannot be audited.

### Wave 1b — LAUNCHED (2 shards, base `40ba0518d`)

| agent            | shard                                         | worktree                         | status    |
| ---------------- | --------------------------------------------- | -------------------------------- | --------- |
| `w2-kaizen-repr` | HIGH-1 + the 7 F11 autonomy-hook siblings     | `.kailash-py-wt/f11-kaizen-repr` | in-flight |
| `w2-core-repr`   | HIGH-2 (7 sites) + the 2 live `exc_info=True` | `.kailash-py-wt/f11-core-repr`   | in-flight |

Partitions disjoint from `w1-sinks` / `w1-scrubber`, which are still running. New test files
namespaced `test_f11_*` so concurrent shards cannot collide on a filename.

### MY SCOPE ERROR — teaching `_SinkScan` does NOT make the #2012 claim true

`w1-scanner` refused the corpus I gave it, correctly. Verified first-hand: the scanner
enumerates `PKG = SRC / "kaizen_agents"` (`:86-87`). **All 11 F11 sites live in
`kailash-kaizen`, `src/kailash`, and `nexus` — none under `PKG`.** It detects 0 of 11 and
always will; the enumeration never opens those files. My brief asserted the opposite.

**#2012 therefore needs its OWN scanners for THREE more trees**, and that shard carries a
constraint that would otherwise defeat it silently: **7 of the 11 are not syntactically
expressible.** The `kailash-kaizen` sites bind `repr()` to a local, then log the local —

```python
handler_name = getattr(handler, "name", repr(handler))
logger.info(f"Registered hook ...: {handler_name} ...")
```

— which needs assignment/dataflow tracking, categorically different from every syntactic
pass in the existing file. Measured `repr`-reaching-a-log: kaizen_agents 1, kailash-kaizen
**0**, src/kailash 2, nexus 4.

**A THIRD render form exists that neither shape 8 nor my brief covers:** `%r` in a format
string with the value as a separate positional arg (`"Listener %r ...", listener`) — no
`repr(` token, no `!r`. That is the form of the PROVEN leak (`event_hooks.py:120`) and of
`resolver.py:381/552/554`. The class is `%r` OR `!r` OR `repr()` applied to a caller-supplied
callable-valued argument. Propagated to both repr shards.

### HIGH-4 / HIGH-5 — a SECOND proven leak, and the other scanner is broken BOTH ways

**HIGH-4 — `delegate/mcp.py:116-120`, PROVEN, at INFO.** `logger.info("Starting MCP server
%r: %s", name, " ".join(cmd))` where `cmd = [command] + config.args`. Driving the real
`McpClient.start()` with the canonical MCP config shape (credential as a CLI arg — how
`server-github` / `server-postgres` are actually configured) leaked
`--token ghp_SYNTHETIC…`. **The comment above it reasons explicitly about the config being
untrusted** ("could be project-level `.kz/config.toml` in a cloned repo") **and then logs it
verbatim**; `env` two lines up is correctly withheld. The danger of EXECUTING untrusted
config was reasoned about; the danger of PRINTING it was not. The file is in `689f9ebd8`'s
own file list — open during that sweep, still missed. Routed to `w1-sinks`. **Not the repr
class** — the value is a joined argument list, so it needs a different fix.

**HIGH-5 — `find-unsanitized-provider-errors.py:54` pins `SANITIZER` to ONE name.** Verified:
`SANITIZER = "sanitize_provider_error"`, while the branch standardised onto
`scrub_remote_error` (repo-wide 342 vs 257; two-src-tree scoped 216 vs 130). It flags
already-fixed handlers at ~27%, **including sites `689f9ebd8` itself fixed**
(`a2a.py:2309/2318/2454/2463/2674/2683`, `approval_manager.py:148/160`).
**That scanner is now broken in BOTH directions** — green on defective sites (session-I
finding), red on fixed ones (this). `high_count` can never reach zero by fixing code, so
anyone driving it to zero either never converges or learns to dismiss the instrument.
Looks like a one-line fix (`SANITIZER` → a set). Raised with `w1-scanner`; may want its own shard.

**Site 11 — `patterns/registry.py:711`** `getattr(listener, "__qualname__", repr(listener))`
with `scrub_remote_error(exc)` on the NEXT line. Third scrub-beside-leak instance. Routed to
`w1-sinks`.

### THE REMEDIATION PRECEDENT — scrubbing a repr is NOT a fix (propagated mid-flight)

`journey/manager.py:488` already litigated this and wrote out the threat model:
`type(handler).__name__` is preferred over `scrub_remote_error(repr(handler))` because
**"the scrubber's coverage is porous — a prefix-less 32-39 char key, `token=`, a
%40-encoded `@` all survive it."** The type name cannot carry a payload BY CONSTRUCTION;
the scrub is a porous filter over unbounded input.

**The distinction that must be held:** scrubbing an EXCEPTION is the accepted contract here
(and `w1-sinks`'s `parallel.py` traceback decision stands on it). Scrubbing a CALLER-SUPPLIED
OBJECT's repr is not. Different inputs, different soundness argument. Sent to both repr shards
before either committed a remediation.

**Integration diagnostic:** the correct fix removes a BARE site without adding a WRAPPED one,
so the predicted pin stays **58 files / 201 sites**. **A pin landing on 202 means someone
scrubbed a repr** — a finding, not a rounding difference.

### RETAINED FIELDS — adjudicated; 2 of the ledger's own 4 are DEFECTS

The lens could not recover "the seven" from any committed artifact (no report enumerates
them; three commits list overlapping sets of 6/4/3), so it derived the acceptance surface
independently per `completion-criterion` MUST-2. **That the seven are unrecoverable from the
committed record is itself a finding — a receipt naming a COUNT without naming its MEMBERS
cannot be audited.** Against the ledger's own four:

| field                  | verdict                                                                 |
| ---------------------- | ----------------------------------------------------------------------- |
| server name / command  | **REFUTED — proven leak (HIGH-4)**                                      |
| listener repr          | **REFUTED — proven leak (HIGH-1)**                                      |
| handler name           | REFUTED → already FIXED by `d6030aefe`                                  |
| tool name              | **basis WRONG** (`tc["function"]["name"]` is model/MCP-supplied, not    |
|                        | "registry-supplied"), exploitation implausible — needs a hostile server |
| trigger description    | **HOLDS** — basis honestly stated, caller-authored, comment says so     |
| `execution_id`/`agent` | HOLDS, basis CORRECT — a Python class name cannot carry runtime data    |

**A cheaper review rule than case-by-case judgment, and it is codify-worthy:** every field
that proved defective renders an OBJECT or a JOINED ARGUMENT LIST; every field that holds is
a SCALAR IDENTIFIER. **Retain scalars; never retain a rendering.**

### MY INSTRUMENT ERROR — live diagnostics are not evidence about committed code

I reported three Pyright findings against `w1-scanner`'s work. Only one was real. The
`extend()` bug matched an **intermediate state between two of its edits** — already fixed
before it committed — and the `_args`/`_kwargs` line was pre-existing `_`-convention code
pyright never flagged. I was reading diagnostics from a tree under active edit and reporting
them as findings against committed work. Same class as everything else here: an instrument
that cannot distinguish the state it is measuring. Verify against the COMMITTED file.

### F12 — NEW CLASS, orchestrator-found: 24 raw exceptions into HTTP RESPONSE BODIES

Found while verifying MEDIUM-1's site; **neither lens reported it, because both were
hunting log sinks.** `src/kailash/visualization/api.py:319` sits three lines below MEDIUM-1's
guard:

```python
self.logger.error(f"Failed to start monitoring: {e}")
raise HTTPException(status_code=500, detail=str(e))     # <-- into the RESPONSE BODY
```

24 sites repo-wide (excluding tests/build), verified by grep:

| file                                                  | sites |
| ----------------------------------------------------- | ----- |
| `src/kailash/visualization/api.py`                    | 10    |
| `src/kailash/middleware/communication/api_gateway.py` | 6     |
| `src/kailash/gateway/api.py`                          | 3     |
| `src/kailash/servers/durable_workflow_server.py`      | 1+    |

**This is a MORE exposed surface than any leak found so far.** A log sink is internal; an
HTTP 500 body is returned to whoever made the request, and on a gateway that can be an
unauthenticated caller. The exception at these sites is whatever the workflow/DB/provider
raised — the same class of object that carries DSNs and API keys everywhere else in this
audit.

**The branch ANTICIPATED this class but scoped it elsewhere.** The PR body already states:
_"No systematic sweep of RETURN surfaces exists anywhere — captured as a second lens inside
#2012. Every sweep this session was log-shaped ... not merely un-swept but
un-instrumented."_ That is exactly right, and #2012 is scoped to the 390 `kailash-kaizen`
sinks. **These 24 are in `src/kailash` CORE — outside #2012's stated scope**, so the
existing tracking does NOT cover them.

**NOT auto-fixed, NOT auto-filed — scope decision belongs to the co-owner.** It is a new
class beyond this branch's remit, the wave is already at 4 concurrent editors, and a
24-site sweep across three gateway surfaces is its own shard with its own security review.
Surfaced for a filing/scheduling decision rather than absorbed silently.

### ⚠ CREDENTIAL EXPOSURE — session transcript only. ROTATE THE OpenAI KEY.

`w1-sinks` ran a shell check whose fallback expansion was wrong
(`${VAR:+YES}${VAR:-NO}` — the second expansion prints the VALUE when the var IS set),
printing a live `OPENAI_API_KEY` from the repo `.env` into its session transcript in full.
**It self-reported rather than burying it**, which is the behaviour to reinforce.

**Containment VERIFIED first-hand by the orchestrator, not taken on report:**

| check                                          | result                                 |
| ---------------------------------------------- | -------------------------------------- |
| real-key prefix in tracked files at HEAD       | **absent**                             |
| commits touching that literal (`-S`, `--all`)  | **0**                                  |
| present in any of the 5 worktree working trees | **none**                               |
| `.env` tracked?                                | **no** — gitignored at `.gitignore:75` |

(21 files DO contain `sk-proj-` — every one is a SYNTHETIC scrubber fixture. The
discriminating check is the real prefix, which appears nowhere.)

**Exposure is confined to the session transcript. Rotate anyway.** The prior session's
notes record this key as already invalid (live 401), which is mitigating but NOT a reason
to skip rotation: that note is 15 days old, and "401" is consistent with expired,
rate-limited, or revoked — it does not establish the key is dead.

### ⚠ NO COMMIT IN THIS REPO IS HOOK-CHECKED — every session commit went in unhooked

Found by `w1-scanner` while discharging a `git.md` follow-up I had asked it for, and it
**corrected its own fabricated reason to get there** (see below). Verified first-hand:

```
$ git config --get core.hooksPath
/Users/esperie/repos/loom/kailash-py/.git/hooks     <-- a DIFFERENT repo
$ [ -d that ] -> NO
$ git commit --allow-empty     -> zero hook output, exit 0      (probe reverted)
```

`core.hooksPath` points at a hooks directory **in another repository that does not exist**,
so git runs no hook at all. The setting lives in the COMMON git dir, so it binds the build
checkout **and every worktree of it**. Consequently `-c core.hooksPath=/dev/null` was a
**no-op — there was never a hook to bypass**, and the `git.md` disclosure I demanded was
owed for an event that did not occur.

**Every commit this session — all five shards' and all of mine — is unhooked.** This is
operator-owned repo config, outside any shard's partition. NOT fixed here: repairing another
operator's git config is not this session's to make. Surfaced for the co-owner.

**And running the REAL gate immediately caught a live failure a bare-tool stand-in missed.**
`w1-scanner`'s `305e689a6` claimed "black/ruff/pyright all pass"; bare `ruff check` did pass,
but the repo's CONFIGURED ruff (via pre-commit) failed `UP038` ×4 on code it had just
written. Fixed in `f630851dc`. That is the argument for running the gate rather than a close
substitute, demonstrated on the shard that was auditing instruments.

### `w1-sinks` — F10 CLOSED. 9 sites, RED established, one premise CONFIRMED.

Commit `bcd446068`. RED `11 failed, 4 passed` → GREEN `15 passed`. `__file__` proof under
`$WT` for both packages. **It refused to count the 4 pre-fix passes as evidence** — 3 are
deliberate negative controls, 1 an already-safe path — which is the honest accounting.

**My `parallel.py:258` claim CONFIRMED by measurement:** `format_exc() -> 'NoneType: None\n'`.
It then applied derive-from-object at ALL 9 sites, including the 6 where `format_exc()` was
already correct, because a reader cannot tell the two cases apart by looking and the two that
were broken were broken in exactly that way. Output byte-identical where it was already right.

**`format_exc()` is now EXTINCT in both packages' `src/`** — post-fix sweep, zero non-comment
occurrences. No same-class residue.

**It also predicted, then verified, that the sibling's pin does NOT move** (`319 passed`,
57/191 unchanged) — because that scanner only counts sinks inside `ast.ExceptHandler` keyed
on the bound name, and none of these shapes qualify. Two shards reasoning independently to
the same structural conclusion is worth more than either assertion alone.

**13 full-suite failures are NOT its work** — established with two discriminating checks:
the failure stack contains no `patterns/` frame, and no failing file imports any of the four
classes. Root cause: `.env` is gitignored so it does NOT exist in a worktree, and the root
conftest auto-load has nothing to load. **Any agent running the full suite from a worktree
will hit the same 13 and may misread them as regressions.**

**Adjacent lead, latent not live:** `hooks/security/redaction.py:231` +
`hooks/builtin/logging_hook.py:109` register `structlog.processors.format_exc_info` in a
chain with NO redaction processor — the `689f9ebd8` class one layer up. It grepped for
producers and found none live, so it is latent config that re-opens the class the moment
anyone adds an `exc_info` call. Worth an issue; untouched.

### `w2-kaizen-repr` — F11 kaizen half CLOSED. It corrected my severity in BOTH directions.

Commits `8a4820a26` + `90c5bda79` + `e035ffe17`. RED `18 failed, 4 passed` / 45 sentinel
occurrences → GREEN `24 passed`; no-regression `1138 passed` then `555 passed`, **both runs
completing without hitting `--maxfail=10`**, so those are real totals, not aborts.

**WIDER than I briefed — the leak is NOT conditional.** I framed the `getattr(handler,
"name", repr(handler))` fallback as firing only for objects lacking `.name`. Verified
first-hand why that understates it: `HookHandler` is a bare `@runtime_checkable` **Protocol**
whose only member is `handle` (`protocol.py:13-14`). So `isinstance(handler, HookHandler)` is
a STRUCTURAL check — any caller object with a `handle` method is NOT wrapped in
`FunctionHookAdapter`, keeps its own `__repr__`, and has no `.name`. That is the NORMAL way
to supply a hook, so the fallback is unconditionally reachable at all seven sites.

**And NOT log-only — it is a RETURN-VALUE leak.** Verified: `manager.py:277/284/298` feed
`handler_name` into `_update_stats`, and `get_stats()` (`:340`) returns a dict **keyed by
it**, verbatim, on the public API. `isolation.py:211` puts it into the returned
`HookResult.error`. Same shape as `d6030aefe`'s `JourneyHookResult.error`.

**MY SUB-CLAIM CORRECTED (narrower, in one direction).** I said a `functools.partial` is a
payload-carrying shape that reaches these sites. It cannot reach six of the seven —
`FunctionHookAdapter.__init__` does `func.__name__`, which raises `AttributeError` on a
partial, so registration fails first. It DOES reach `rate_limiting.py:153`, because
`_check_rate_limit` runs BEFORE `super().register()`. Net: wider overall, not narrower.

**It refused the resolution loss I offered to accept.** `type(p).__name__` is the constant
`"partial"` for EVERY partial — on a bus allowing 1000 listeners per key, that destroys the
diagnostic the field exists for. `safe_handler_name` instead unwraps the partial chain
(bounded at 8), prefers `__qualname__` **when it is a string**, else `type(x).__name__`,
prefixing `partial(...)`. **Safety argument verified first-hand rather than accepted:**

```
instance inherits __qualname__ from class? -> False     (dataclass → class name, never a field)
partial has __name__/__qualname__?         -> False/False
unwrapped p.func.__qualname__              -> real_fn   (carries NO bound kwarg)
```

A `__qualname__` is a SOURCE-level identifier fixed at `def`/`class` time, not runtime state
— so unlike `repr` it cannot pick up a bound credential, and it is the SAME trust level as
the `handler.name` these sites already log unscrubbed. Adds no new trust; reuses an accepted one.

**Rule-1 finding it fixed in its own file:** `isolation.py` imported **no credential scrubber
at all** — un-swept for the exception-text half. Three caller-derived surfaces scrubbed
(`:239` — which crosses a PROCESS boundary into both a parent log line and the returned
`HookResult.error` — plus `:307`, `:440`). Deliberately NOT scrubbed: `:126`, whose errors
come from `resource.setrlimit`, an OS surface with no caller data — scrubbing there costs
diagnostics for no protection. That restraint is correct and is the `zero-tolerance` Rule 3
over-correction trap.

Helper placement: `safe_handler_name` in `hooks/manager.py`, with a deliberate private
`_safe_listener_name` twin in `l3/event_hooks.py` (making an L3 governance bus depend on the
autonomy hook manager for naming would be bad layering) — and a test running BOTH over the
same five cases asserting identical output, so they cannot drift. True unification belongs in
`kaizen/utils/`, which is another shard's partition; correctly not touched.

### F14 — NEW, HIGH: hook process isolation NEVER RUNS, and degrades SILENTLY

Found by `w2-kaizen-repr`, out of its scope, **verified first-hand by me**:

```
$ python -c "import multiprocessing as mp; print(mp.get_start_method())"   ->  spawn
isolation.py:217   def _run_hook():                 <-- nested closure
isolation.py:244   multiprocessing.Process(target=_run_hook)
```

Under `spawn` — the DEFAULT on macOS and on Python 3.14 Linux — a nested closure is
unpicklable, so `execute_isolated` raises `AttributeError: Can't get local object`.
`IsolatedHookManager._execute_hook` catches it and **silently degrades to non-isolated
execution**, announcing it only as a log line. So SECURITY FIX #5's process isolation has
never run on any macOS host. `zero-tolerance` Rule 3 (silent fallback) **plus** a real
security-posture failure.

**Same class as #2013** (`enable_auth` inert): a documented security control that installs
nothing. **Correctly NOT fixed in-shard** — the remedy (module-level worker; handler AND
context must become picklable across the spawn boundary) exceeds one shard budget, so
`autonomous-execution` MUST-4's bound makes it a genuine follow-up, not a warm-context
fix-now. Needs filing.

### Wave 3 — LAUNCHED

| agent          | shard                                              | worktree                       | status    |
| -------------- | -------------------------------------------------- | ------------------------------ | --------- |
| `w3-lifecycle` | MEDIUM-1 (start-after-failed-stop) + MEDIUM-2 (×2) | `.kailash-py-wt/f13-lifecycle` | in-flight |

### DECISION — the `!r` guard stays LOGGER-SCOPED. Do not "tighten" it later.

`w2-kaizen-repr` offered to widen its `!r` guard from `logger.*` arguments to every
`FormattedValue`, and honestly flagged that doing so would red on a benign line:
`event_hooks.py:114` `f"event type {key!r}"` — `key` is a **str** (so `!r` adds quotes rather
than rendering an object), it is a bus key not caller object state, and it goes to a
`ValueError` not a sink. Out of class on all three counts.

**Declined, and the reason is the HIGH-5 lesson applied forward.** The provider-error scanner
became wrong in both directions and its count could never reach zero by fixing code; the real
damage was not its false-positive rate but that **an instrument which cannot reach its own
success state teaches its operator to dismiss it.** A guard that reds on a correct
`ValueError` is on that path — the first person it blocks scopes it down or deletes it, and
then neither net exists.

**The gap is RECORDED, not closed badly.** A `!r` bound into a variable and logged later
escapes the logger-scoped guard. That is the SAME structural limitation `w1-scanner` hit on
the seven `kailash-kaizen` sites (`repr()` → local → log): both need assignment/dataflow
tracking, categorically different from syntactic matching. A comment naming the limitation was
requested so the scope reads as a decision, not an oversight.

**Two caller-supplied SCALARS flagged by that shard — both retained, deliberately.**
`rate_limiting`'s `principal_id` IS the audit record (a rate-limit security event that cannot
name the principal is not an audit record). `manager.py`'s `hook_file` is a path under a
caller-supplied `hooks_dir` — a path-disclosure surface, not a credential one. Both pass the
scalar-vs-rendering heuristic, and `hook_file` sits at its EDGE: scalar, but caller-DERIVED
rather than framework-derived. The heuristic is a cheap first filter, not a proof.

### `w2-core-repr` — F11 core/nexus half COMPLETE. Commits `318df97bc` + `a4ac02a17`.

RED `22 failed` → GREEN `27 passed`. Regression: nexus `1991 passed`, core runtime/utils
`1023 passed`, scheduler/utils `331 passed`, extractor/rate-limit/f11 `84 passed`. Pre-commit
passed on both commits — **no bypass** (consistent with hooks being dead repo-wide).

**ALL 8 SITES CONFIRMED BY EXECUTION**, driven through the REAL gateway (TestClient →
middleware → HandlerNode → resolver), asserting on the REAL module logger. Reachability is
now settled, not PLAUSIBLE — which is what the shard was asked to produce.

**THE FINDING THAT MATTERS MOST — the identity fix ALONE would NOT have closed
`resolver.py:550`.** `get_type_hints` refuses a partial with a `TypeError` whose message
**embeds the full repr**, and `_detect_pep563` chains it via `raise ... from exc` — so the
credential arrived as the `__cause__`, entirely independent of the field I flagged. Fixing
only what my brief named would have shipped the site leaking AND reading as closed. Third
time this wave a fix was narrower than the leak; **first time it was caught BEFORE landing.**
Same shape at `nexus/core.py:2429`, which leaked TWICE in one `logger.warning` (`:2429` repr

- `:2433` interpolated `exc` carrying the same repr) — the statement, not the line, is the unit.

**MY SITE LIST CORRECTED (execution-only findings):** `Depends(partial)` does NOT reach
`:381` — `_classify_parameters` raises first because `get_type_hints` refuses a partial, so it
lands at `:554`. A plain `@dataclass` does not reach `:381` either: unhashable, dies at `:329`
(`real in cache` → `TypeError`). `:381` needs a **HASHABLE** callable object (`frozen=True`,
the idiomatic config-object shape). **And there were FOUR `exc_info` sites, not the two I
named** — `resolver.py:550` + `lifespan.py:102` were also live.

**`safe_exception_frames` — the construction argument, reusable.** Keeps
`path:line:function` per frame + each chained exception's TYPE, drops messages, EXCLUDES
source text so a frame cannot echo an interpolated value. Every retained element is a
source-level identifier — the same argument that makes `__qualname__` safe. Dropping the
traceback outright was refused because archived spec §140 pins it as "the operator's only
audit trail". `scrub_remote_error` was correctly NOT reached for: it lives in kaizen, kaizen
depends on kailash, so using it inverts the dependency. One shared helper in
`kailash.utils.secure_logging`, not a per-package copy.

**`TestKnownDownstreamReleak` — the best test design of this wave.** It pins the leaking-logger
set to exactly `{"HandlerNode"}`, so a NEW leak fails it **and fixing `base_async` also fails
it**, forcing the pin to be DELETED rather than left as a stale claim. A self-clearing
tripwire, the property `testing.md` wants from strict-xfail.

**Two stale citations, both verified by me:** `specs/nexus-fastapi-parity.md` does NOT exist
in the live tree (only `workspaces/_archive/nexus-fastapi-parity-py/specs/`), and
`observability.md` contains **zero** occurrences of "Rule 3a" (that string lives in
`zero-tolerance.md` + `worktree-isolation.md`). Re-deriving §140 rather than trusting the
docstring is `zero-tolerance` 3e done right; declining to guess the second citation's intended
target is also right — a wrong citation replaced by a differently-wrong one is worse.

### ⚠ RELEASE-ORDER CONSTRAINT — kailash 2.63.0 MUST publish before nexus's next release

Verified: PyPI `kailash` latest is **2.62.0**; local `pyproject.toml` is **2.63.0,
UNPUBLISHED**. The shard bumped `packages/kailash-nexus/pyproject.toml` to
`kailash>=2.63.0` because nexus imports `safe_callable_name` / `safe_exception_frames` at
module scope — an older kailash makes `import nexus` fail at startup.

**NOT a defect and NOT to be reverted.** A floor that lies about a module-scope import is
worse than a release-ordering constraint, and both alternatives are worse still: duplicating
the helper into nexus guarantees the drift a shared helper exists to prevent, and hosting it
in nexus is impossible because kailash's own `distributed`/`scheduler`/`lifespan` sites cannot
depend on nexus. This repo's standing trap ("bumping to unreleased versions breaks release CI,
which installs from PyPI before the new release publishes") is real and applies — as an
ORDERING requirement, surfaced to the co-owner, not as a reason to weaken the pin.

### Routed back to `w2-core-repr` (offered, warm context, helper already imported)

`nexus/core.py:2535` (`rate_limit_inert`) + `:2861` (`use_middleware` sync-function
`TypeError` rendering a full partial repr) — my earlier "line 2429 ONLY" boundary lifted for
these two specifically. Plus the `base_async.py` downstream re-leak — **the sink is
`src/kailash/nodes/base_async.py:279`** (`self.logger.error(f"Node {self.id} execution
failed: {e}", exc_info=True)`), **NOT `:260`**, which this row said twice and which is
`outputs = await self.async_run(**validated_inputs)` — the HAPPY PATH. Verified: `:277` is
the `except Exception as e:`, `:279` is the sink. `:260` was a traceback FRAME in the
evidence, and I carried a line number out of a report instead of out of the code — the same
class of error as citing a SHA before it existed. `w2-core-repr` flagged it TWICE before it
was corrected here; a brief aimed at `:260` sends the next reader to edit the happy path,
whose closure signal is the `TestKnownDownstreamReleak` pin failing.

### CODIFY-WORTHY — the retain-rule SHARPENED, and a three-instrument lesson

**The rule, corrected.** "Retain scalars, never retain a rendering" was derived from four
defective fields and works as a cheap first filter, but `w2-core-repr` found where it fails:
`safe_exception_frames` is a JOINED LIST — the shape the rule forbids — yet it joins
`path:line:function` + exception TYPEs, every element fixed at `def`/`class` time.

The property that made the four defective fields dangerous was never their ARITY. It was that
they rendered **runtime-derived** state (bound kwargs, dataclass fields, a joined `argv`, an
exception message). The sharper form:

> **Retain SOURCE-LEVEL identifiers; never retain RUNTIME-DERIVED state — regardless of arity.**

A joined list of code locations PASSES. A single scalar that is caller-derived does NOT — which
makes `hook_file` (a path under a caller-supplied dir, flagged by `w2-kaizen-repr`) the CLOSER
call under the sharp rule, not the safer one. Same construction argument as `__qualname__`,
now verified independently by three shards.

**Three instruments, three ways of being wrong about a file that discusses its own subject —
all within one hour, all on the same class:**

| instrument                        | failure                                                           |
| --------------------------------- | ----------------------------------------------------------------- |
| `w1-sinks`' `repr` grep           | too NARROW — required a dunder, missed 7 plain-`"name"` sites     |
| MY verification grep              | too BROAD — matched the fix's own explanatory COMMENTS as defects |
| `w2-core-repr`'s first helper pin | substring scan — failed on its OWN docstrings                     |

The honest form in all three cases is an **AST walk**, which is what `w2-core-repr` shipped
(`TestNoModuleHelperRendersAnObject` walks for a `repr()` Call node, ignoring docstrings).

**SHARPENED by `w1-sinks` — its framing supersedes mine.** I characterised the pair as
narrow-vs-broad. That is DOWNSTREAM of the actual root: **neither grep had a PLANT-CONTROL.**
A regex over source text has TWO independent failure axes — it can miss the real shape, and it
can match prose _about_ the shape — and **one control fired against a deliberately planted
instance discriminates BOTH at once.** Mine acquired a control on the second attempt and became
trustworthy immediately; its own never had one, which is exactly why an empty result read as an
ALL-CLEAR rather than as UNKNOWN.

**And the control must survive the FILTER, not merely the command:** my comment-excluding grep
still left a live false positive inside the helper's own DOCSTRING, because I excluded `#` but
not docstrings. A plant-control catches that too.

> **Operational form: before citing any grep as evidence of ABSENCE, plant one instance of what
> you claim is gone and confirm the command finds it.** Ten seconds, and it converts "returned
> nothing" into an actual measurement.

That is `instrument-discipline` MUST-1 reduced to a reflex a tired operator will actually
perform, and it is the single most reusable output of this wave.

**INTEGRATION FLAG from `w1-sinks`:** `376b7a988` makes its test doubles subclass the REAL
`BaseAgent`, so `run` now passes through `LoggingMixin`'s wrapper and emits an ADDITIONAL log
record during those tests. That is correct — it is what production does — but if any sibling
adds a package-wide assertion over emitted records, that is where the extra records originate.

**Sequel: `safe_exception_message` DELETED, not deprecated.** It filtered exactly `repr(handler)`
out of a retained message — exact, not porous, so not the scrubber failure mode. But it retained
a RENDERING, and **a repr-then-filter helper sitting in a security module is an invitation to the
generalisation that was explicitly forbidden**. The diagnostic turned out to be available as a
SCALAR (`NameError.name` is the bare identifier and survives the re-raise), so nothing is
filtered — it is simply not retained. No scalar was invented for the `TypeError` path, which
genuinely has none.

**New site from the `%r` correction:** `distributed.py:778` — a task-queue backend failure logged
the Redis URL it could not reach, credentials included. Not the caller-repr shape, same
credential-into-logs class. Fixed in-shard.

### STILL UNOWNED — do not let these read as covered

- **MEDIUM-1** (visualization `start` after a failed `stop`) + **MEDIUM-2** (cancellation
  swallow ×2) — no shard; need one.
- **HIGH-3**: `find-unsanitized-provider-errors.py` still cannot express the class. Teaching
  it is what makes any future "residual sweep is clean" claim mean something.
- The six PLAUSIBLE retained fields, `tool_name`, and the NOT EXAMINED
  `interpretability/core.py` ×2 + `__init__.py` exc_info keeps.
- Core + kaizen-agents tree results (logs at `/tmp/w5corr/`) — re-poll for summary lines.
- **#2010** `BaseAgent(description=)` — pre-existing, still owed under `zero-tolerance` R1.

### Ordering coupling — read before integrating

`w1-scanner` and `w1-sinks` are coupled at VERIFICATION, not at implementation.
`w1-scanner` asserts its teaching took by proving the scanner now DETECTS the 9 known
sites (a positive-detection assertion, independent of whether they are fixed). The pinned
`57/191` counts are re-derived by the ORCHESTRATOR at integration, after `w1-sinks` merges.
A count that does not move means the teaching did not take.

### FOREST RECONCILIATION — five ledger rows were STALE (orchestrator, session J)

Done while Wave 1 was in flight (`wave-loop.md` MUST-6: never idle when independent
in-budget work is launchable; MUST-7: reconcile a backlog item against ground truth BEFORE
implementing it). **Result: F1/F2/F3/F5/F6 are NOT queued work. They are this branch's OWN
delivered work, awaiting the PR.** The issues are still OPEN on GitHub only because the PR
has not merged — `open ≠ undone`, exactly the MUST-7 case.

Commit `0066e4fcb` ("drain the #1970-#1981 five-issue forest") plus its follow-up tail IS
this branch. Verified per-row against the TREE, not the commit message (`spec-compliance`:
grep/AST, never file existence, never a commit claim):

| row | issue | verification                                                          | verdict             |
| --- | ----- | --------------------------------------------------------------------- | ------------------- |
| F1  | #1970 | 13 `sanitize_provider_error` call sites in `ai_nodes.py`              | DELIVERED on branch |
| F2  | #1971 | `DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH` in core, imported by DataFlow | DELIVERED on branch |
| F3  | #1972 | `validate_workflow_name` called at `core.py:1919` + `:3777`           | DELIVERED on branch |
| F5  | #1974 | six suites `1974` + `1974b`–`1974f`; scrubbing CONSOLIDATED onto      | DELIVERED on branch |
|     |       | `kaizen.utils.credential_scrub.scrub_credentials` (`c0c99b589`)       |                     |
| F6  | #1981 | `ReasoningDegradedError` — 10 refs `a2a.py`, 7 refs `reasoning.py`    | DELIVERED on branch |

Regression suites present for all five: `test_issue_{1970,1971,1972,1974,1981}`.

**Instrument note (`instrument-discipline` MUST-1).** My first F5 probe grepped
`error_sanitizer.py` for `xox|jwt|JWT` and returned 0. That check could NOT discriminate
"not fixed" from "fixed elsewhere" — it was re-instrumented against the test corpus, which
revealed the fix had been consolidated into a DIFFERENT module. The 0 was a true reading of
a wrong question. Do not resurrect F5 on the strength of that grep.

**Consequence for Wave 2 — the real remaining queue is only F8 + F9:**

- **F8 (#2013)** — CONFIRMED and SHARPENED beyond the issue text. `enable_auth` is not
  wholly inert: `core.py:1542` DOES install `APIKeyAuth`, but only on the **MCP** channel.
  On the **HTTP/API** surface, `transports/http.py:116` assigns `self._enable_auth` and
  **never reads it again** (the only other occurrences at `:48`, `:70`, `:158` are
  docstrings). So `Nexus(enable_auth=True)` secures MCP and leaves the primary API surface
  wide open — worse than uniformly inert, because the MCP half makes it look wired.
  Partition (`kailash-nexus/**`) is DISJOINT from every Wave-1 shard.
- **F9 (#2012)** — 390 un-triaged exception sinks; the issue itself says port the AST sink
  scanner rather than hand-sweep. **Directly enabled by `w1-scanner`** — it MUST NOT launch
  until that shard merges, or it will hand-sweep against an untaught scanner and re-create
  the false-SWEPT defect this whole wave exists to close. Also a file collision.

**F8 was deliberately NOT launched as a fifth concurrent agent.** `wave-loop.md` MUST-6 is
explicitly bounded by capacity + throttle. Four concurrent is this session's observed-safe
ceiling; a session-limit death is account-scoped and kills the WHOLE wave at once, so a
fifth agent risks four agents' in-flight work to save a short wait. Held for Wave 2.

### F11 — NEW ledger row: 11 `repr(handler)` sites the scanner cannot see

Raised by `w5-correctness` (session I's lens, delivered LATE into session J — matched
against session I's ledger before reacting, per `orchestration-launch-ledger.md` MUST-3).
Both its findings re-verified first-hand by the orchestrator before any action.

**C1 (PR body, suite-results basis) — CONFIRMED, FIXED at `34321615c`.** Two nexus test
commits landed after the range the body cited, so the "nothing inside the four packages"
inference was stale. The NUMBERS survive (re-run identical at `b220704b5`); the REASONING
did not. Withdrawn and replaced with the re-run + a required merge-time re-run.

**C2 (F11) — CONFIRMED, OPEN.** `grep repr(handler)` returns 22 hits at HEAD, 11 live
source sites, of which **7 are the same defect class F1 claimed closed**:

```
kailash-kaizen/src/kaizen/core/autonomy/hooks/manager.py:89,184,267
kailash-kaizen/src/kaizen/core/autonomy/hooks/security/isolation.py:211,418
kailash-kaizen/src/kaizen/core/autonomy/hooks/security/rate_limiting.py:118,153
src/kailash/utils/lifespan.py:82 · runtime/distributed.py:1167
runtime/scheduler.py:1666 · nexus/core.py:2429
```

**Why the original receipt read clean — the shape recurs, so note it.** The FIXED file and
the LEAKING file are both named `manager.py`, in different packages. A grep scoped to the
file just fixed returns empty and reads as a package-wide all-clear.

**F11 is F10's class, one surface further out.** `_SinkScan` inspects only the bound
EXCEPTION name inside an `except` block, so a `repr()` of a NON-exception value is
invisible. The lens proved it with a control: `repr(handler)` → `[]`, `repr(e)` → `[4]`.
So the PR body's "390 un-triaged sinks, tracked as #2012" does **not** cover these 11 —
counted as outside-the-surface while carrying the defect, the same false-SWEPT mode as F10.

**Routed, not queued:** shape 5 sent to `w1-scanner` mid-flight (it is already teaching
this exact instrument; a second teaching pass would be waste). The 11 SITES are NOT in any
current partition — they need their own shard, gated behind `w1-scanner` merging.

**Severity is CONDITIONAL and must not be overstated:** `getattr(handler, "name",
repr(handler))` evaluates the default eagerly but only USES it when the attribute is
absent, so the leak fires only for handlers lacking `.name`. Exploitability referred to
security review. The coverage-claim gap is NOT conditional.

### Session-I F10 verdict — PRESERVED, still the governing finding

**The round was NOT clean. 2 of 6 REFUTED.** Convergence is NOT met and the PR MUST NOT
open until F10 closes. Details are in the reconciliation table above (every row re-verified
first-hand this session, so session I's report is no longer the only witness).

**Method caveat from session I's lens — still binding.** It had NO Bash: could not run the
`git show` controls, execute `_SinkScan`, or run the scrubber. It marked NOT PROVEN rather
than HOLDS wherever it could not control a claim. `w1-correctness` carries those items.

## Standing operational notes (carried from session I, all still in force)

**Agents go idle WITHOUT delivering.** Root cause KNOWN: an agent writes its report as
plain assistant text without ever sending it. **The failure is DELIVERY, not execution.**
QUERY, never re-dispatch — every re-ping returned substantial finished work.

**An idle signal is not a completion signal — check the ARTIFACT.** `git log <base>..HEAD`
plus `git diff --stat` over the agent's partition. Both empty ⇒ not started.

**Session-limit death kills every in-flight agent at once** — account-scoped, distinct from
the server-side concurrency throttle (no `not your usage limit` string). The recovery unit
is the WHOLE wave.

**Cold-start ~3 concurrent Opus agents** (`worktree-isolation.md` Rule 4). Session I ran 4
for most of the session with no throttle signal; Wave 1 runs 4 (3 editing + 1 read-only).

**A shard that dies mid-flight may have COMPLETE work on disk** — verify the tree before
assuming a task needs re-running.

**`git status` has no vocabulary for duration.** A clean read is a millisecond observation,
not a standing property. Pin a SHA; re-check the pin holds afterwards.

## Prior waves

Session I's clean round is CLOSED (it returned a REFUTATION, which is a result, not a
non-delivery). Wave 8 (session D) and Wave 7 are CLOSED; reconciliation detail is
superseded by `04-validate/launch-ledger-sessionI.md` and the sweep reports. Redteam
rounds 2–5 are complete.
