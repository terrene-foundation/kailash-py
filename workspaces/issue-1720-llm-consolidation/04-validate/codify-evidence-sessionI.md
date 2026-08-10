# Codify evidence — session I (2026-08-08)

Draft input for a future human-gated `/codify`. **Evidence only.** No proposed
rule text: that is the gate's job.

## Provenance and how to read this

Two grades of claim, marked per row. This distinction is load-bearing — the
whole subject of §1 is instruments that report confidently about things they
cannot see, and a document that laundered relayed reports into first-hand
findings would be an instance of its own topic.

- **[V]** — verified by me in this repo at the cited `path:line` / SHA.
- **[R]** — RELAYED by the orchestrator from another lane, NOT independently
  verified by me. Recorded because the pattern is the point and the sample size
  matters; each still needs its own citation before it is cited as fact.

---

## §0 THE RULE ALREADY EXISTS — read this before §1

Everything in §1 and §2 was written before anyone checked whether the property
being re-derived was already codified. It is. **This changes what the file is
for, so it goes first.**

`.claude/rules/instrument-discipline.md` — `priority: 0`, `scope: baseline`,
`cli_delivery: baseline`. Title: _"A Check That Cannot Discriminate Is Not
Evidence"_. Its governing question, verbatim at `:11`:

> **Would this instrument produce a DIFFERENT result if the proposition were
> false?**

That is the same property §1 arrives at from nine observed failures, stated
first. Its MUST-1 (`:17`) is _"Name The Falsifying Result Before Citing Any
Check As Evidence"_; MUST-2 (`:32`) extends it to green tests and non-reddening
mutations. **[V]** — read from the file, not relayed. The orchestrator supplied
the quote and explicitly flagged it as relayed; I re-read the frontmatter and
body rather than accept it, which is the [R]→[V] transition this file's grading
exists to force.

**The rule is loaded in EVERY session in this repo** (one of 14 baseline-scope
rules). Every agent who committed an instance in §1 had it in context. **[V]**

### And it was not merely loaded — it was CITED, by clause, in the same branch

A first draft of this section said the agents "could have quoted the rule". That
understates it, and the stronger version is measurable. This branch's own prior
session ledgers cite `instrument-discipline.md` by name and by MUST-clause:

| ledger                      | citations | by MUST-clause |
| --------------------------- | --------- | -------------- |
| `launch-ledger-sessionF.md` | 3         | 1              |
| `launch-ledger-sessionG.md` | 2         | 1              |
| `launch-ledger-sessionH.md` | 2         | 2              |
| `launch-ledger-sessionI.md` | 3         | 1              |

Used correctly, as the governing rule, e.g. sessionG: _"the harder direction to
find them and both are `instrument-discipline.md` MUST-1"_; sessionH: _"a fix
whose RED→GREEN could not be established — `instrument-discipline.md` MUST-2"_.
**[V]** — counted with a negative control (`grep -c nonexistent-rule` → 0 in the
same files, confirming the counts are real matches rather than a broken pattern).

**This removes the most comfortable explanation.** The violations are not what
happens when a rule is unknown, unread, or buried. They happened in sessions that
were actively invoking the rule by clause number, in the same documents that
record the violations. Three prior sessions of this branch reasoned with it
explicitly, and it did not prevent the nine instances in §1 — several of which
occurred in those very sessions.

That is the strongest form of the enforcement-gap claim available, and it is
stronger than the version this section originally carried. A rule can be
baseline-priority, loaded, quoted by clause, and correctly understood, and still
not bind — because _understanding a test is not the same as having a second
instrument to run it with_.

### So the finding is not what §1 thought it was

| what §1 reads as           | what it actually is                                                  |
| -------------------------- | -------------------------------------------------------------------- |
| a property worth codifying | a property **already codified at baseline priority**                 |
| a knowledge gap            | an **enforcement gap** — the rule was loaded and violated anyway     |
| ~9 mistakes                | **a violation RATE under an active rule**, and the rate is the datum |

Nine or ten instances, four independent lanes, one session, at least four
committed by agents _actively working on this exact class_. Not one of them was
prevented by a baseline rule that states the test in its first line. **That is
evidence the rule could not previously produce about itself**, and it is the
session's actual contribution.

This file cites the rule **zero** times before this section. Verified with a
positive control first, because a zero from a grep is exactly the shape §1 is
about: `grep -ci instrument` returns **18** (so the grep reads the file),
`grep -ci instrument-discipline` returns **0**, `grep -c '.claude/rules/'`
returns **0**. **[V]**

### The rule's own Detection block says why it did not fire

Quoted verbatim from `:61`:

> **Probes: STAGED, and NOTHING EXECUTES THEM.** [...] the Phase-1 gate-review
> above is this rule's **ONLY ACTIVE coverage**

and, on the deferred half:

> Phase 2 deferred — no hook detector (**a regex detector would itself instance
> this class**)

**[V]**. Two things follow, and the second is the sharper.

1. The rule's only live enforcement is human/agent gate-review at `/codify` and
   `/redteam` — i.e. AFTER the work. Nine in-session violations is direct
   evidence about what that leaves uncovered.
2. **The parenthetical is empirically confirmed by this session.** The rule
   predicted that a regex detector would instance the class; I5 (a `grep`
   defeated by shell word-splitting, returning 0 across 9 packages) and I9 (a
   `grep -E "^1 failed"` defeated by ANSI colour codes) are two independent
   confirmations, in opposite directions. The rule anticipated the failure mode
   of its own missing detector, and this session produced the instances.

### What the session adds that the rule does not carry: the operational form

The rule states the TEST. It does not say how to SATISFY it. Every instance in
§1 is an agent who could have quoted the rule and still shipped a
non-discriminating check, because knowing the question does not tell you what to
build. That gap is where this session's evidence is useful:

| instrument    | what makes it able to discriminate                                                     |
| ------------- | -------------------------------------------------------------------------------------- |
| a **sweep**   | a **positive control** — show it finds the shape before trusting a zero                |
| a **scanner** | **negative controls** — cases that must NOT fire, or "flags everything" passes equally |
| a **test**    | an **outcome-shaped assertion**, not a mechanism-shaped one                            |
| a **claim**   | a **named falsifying result**, stated BEFORE the check runs                            |

Each row is evidenced below: row 1 by the `_SinkScan` receipt (§1), row 2 by
`TestTheScannerSeesEachShape`'s 6-must-red / 7-must-not-fire split (§1), row 3 by
`4772d0c48` (§1, constructive counterpart), row 4 by the I1–I4 failures, each of
which had no falsifying result named before it ran.

**No rule text is proposed here, per the drafting constraint.** The disposition
this file supports is: the rule stands as written; the gap is in enforcement and
in operational guidance, and the gate decides whether either warrants a change.

---

## §1 The non-discriminating instrument

**The class — stated in its general form, because the narrow form is wrong.**

An earlier draft of this section defined the class as _"instruments that produce
falsely reassuring results"_. That definition is too narrow and was corrected by
a later instance that inverts the direction (I9 below — the orchestrator's
seventh by its own tally, the ninth row here). The class is:

> **Instruments that produce results uncorrelated with the thing they claim to
> measure.**

Both directions cost. The **false-clear** direction (a defect passes) is the
more dangerous. The **false-alarm** direction (a correct artifact is reported
broken) costs as much in wasted work and is the case a reader is least likely to
guard against — because a red result _feels like the instrument working_. In I9
the output would have sent an engineer to rewrite a guard that was already
correct.

It is not "a bug in the check". The check runs, exits 0, and prints a plausible
value. The failure is that the result carries no information about the question
while having the grammar of an answer.

**The discriminating question, which is the whole defense in one line:**
_what would this command have printed if the proposition were false?_
If the answer is "the same thing", the result is not evidence — in EITHER
direction.

### Instances

| #   | Instrument                                                                    | What it printed                                                   | Why it could not discriminate                                                                                                                                                                                                                                                                                                                                                                                       | Grade                                                             |
| --- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| I1  | `out=$(isort --check-only ...); echo "isort: CLEAN"`                          | `isort: CLEAN`                                                    | The `echo` was unconditional — it never read `$out`. Printed CLEAN while two files were red. Caught on the next command.                                                                                                                                                                                                                                                                                            | **[V]** mine, this session                                        |
| I2  | `re.findall(r'^\s+\("', block)` to count parametrize cases                    | `4 positive / 6 negative`                                         | Regex counts LINES beginning with `("`; multi-line tuples start with `(` alone. True answer via `ast` + the live run: **6 / 7 / 13 passed**.                                                                                                                                                                                                                                                                        | **[V]** mine, ~10 min before writing this                         |
| I3  | F3 sentinel: bare-hex placed in the INNER exception of a chained pair         | downgrade probe stayed GREEN                                      | The sinks scrub the WRAPPER; `str(wrapper)` never contains the inner message, so the scrubber was never handed the sentinel. The test pinned nothing. Fixed by moving the hex to the outer message; re-proved both ways.                                                                                                                                                                                            | **[V]** mine — `6a6e54541`, then applied correctly in `6a870a702` |
| I4  | `git log --author="$(git config user.name)"` to count my own commits          | 20 commits                                                        | All lanes commit under ONE git identity, so the filter cannot separate agents. Returned siblings' work as mine. I had already reported "14 commits" from memory; the verified count by subject is **12**.                                                                                                                                                                                                           | **[V]** mine, at session close                                    |
| I5  | A scoped `grep` detector, already validated against ground truth              | **0 hits across all 9 packages**                                  | A multi-line shell variable failed to word-split, so the sweep never ran. Zero-hits is byte-identical to a genuinely clean tree.                                                                                                                                                                                                                                                                                    | **[R]**                                                           |
| I6  | `set --` for range vars, two lanes                                            | empty range                                                       | Same shape: an empty range and a range with nothing in it are indistinguishable downstream.                                                                                                                                                                                                                                                                                                                         | **[R]** (×2)                                                      |
| I7  | `grep -c load_dotenv <file>`                                                  | an accurate count                                                 | Accurate answer to a question nobody asked — the file loads `.env` via `install_cost_guard`. The inference drawn from the zero was wrong, and the recommended "fix" would have disarmed a working cost control.                                                                                                                                                                                                     | **[R]**                                                           |
| I8  | A test suite read while the tree was being written                            | `1 failed` / `13 failed` / `319 passed` at ONE HEAD               | Three reads, three answers, no code change between them — a moving tree read as branch state. Nearly shipped as a live RED in the PR body.                                                                                                                                                                                                                                                                          | **[R]**                                                           |
| I9  | `pytest --color=yes ... \| grep -E "^1 failed"` over a mutation-results table | all 8 mutations reported MISSED, incl. one that demonstrably reds | **INVERTED DIRECTION — a false ALARM.** pytest's summary line is ANSI-colorized, so it begins `\x1b[31m\x1b[31m\x1b[1m1 failed`, and an anchored `^1 failed` cannot match. Reproduced: with color the grep counts **0** on a genuinely failing run; ANSI-stripped it counts **1**. Reads as "the new guard is worse than the old" when the guard was correct — would have sent an engineer to rewrite working code. | mechanism **[V]** (reproduced locally); the incident **[R]**      |

| I10 | `grep -nE "<pattern>" "$F" \| head -10; echo "exit: $?"` | `exit: 0`, read as "no match, file clean" | **The pipeline's `$?` is the LAST command's status — `head`, not `grep` — and `head` exits 0 on empty input.** So `exit: 0` was returned identically whether the pattern matched, did not match, or the file did not exist. The zero-lines-of-output WAS sound evidence; the exit code appended to "confirm" it was not, and it is the part a reader would have quoted. Re-run with a positive control (`grep -c instrument` → 18, proving the grep reads the file) before trusting the negative. | **[V]** ORCHESTRATOR's, while checking whether a refuted premise had contaminated this file |

**Note the distribution:** four independent lanes plus the orchestrator, at least
TEN instances, and in I1–I4 and I10 the agent committing the error was the one
actively fixing this class — I10 occurring while checking this very document for
contamination. That is the strongest available argument that this is not a
discipline problem solved by care. I9 additionally shows the class is not
direction-specific: the same root cause (a matcher that cannot see what it claims
to check) produced a false ALARM rather than a false clear, and cost the same.

**I10 is worth separating from I1 despite the surface similarity.** I1 was an
`echo` that never read its input — a missing conditional, visible on inspection.
I10 _did_ read a status; it read the **wrong one**, because a pipeline reports its
last stage. The check looked rigorous, produced a plausible value, and was
uncorrelated with the question. That failure survives code review in a way I1
does not, which makes it the more dangerous of the two and the reason the
operational form below has to be a SECOND INSTRUMENT rather than a more careful
first one.

### The defense that emerged, and its receipt

**Pair every negative sweep with a positive control: demonstrate the instrument
CAN find the thing before trusting its silence.**

Receipt — the defense found a real defect within an hour of adoption:

- Instrument: `_SinkScan`, an AST pass over `kaizen_agents/`
  (`packages/kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py`).
- Before: it recognised only `str(e)` / `repr(e)` / f-string `{e}`. It was blind
  to (a) `exc_info=True` / `logger.exception` entirely and (b) the lazy
  `%s`-argument form `logger.error("...: %s", e)`. Those are exactly the two
  shapes that had just been fixed by hand in `689f9ebd8`.
- The file's own docstring (tier 1) advertised that it reds when a new
  unscrubbed sink is added. For two of three shapes that claim was false.
- After teaching it both shapes (`6a6e54541`), **first run against real source
  found 6 previously-invisible bare sinks in 4 files** — `agents/nodes.py`,
  `agents/register_builtin.py`, `delegate/hooks.py`, `delegate/session.py`.
  Pin moved 53→57 files / 185→191 sites (`test_local_error_sinks_are_scrubbed.py:148-149`).
- Those six had survived TWO prior sweeps of the same package plus a
  `grep exc_info|logger.exception`. All six are the `%s`-arg form, which that
  grep structurally cannot match. **[V]**

**The negative half is not optional.** `TestTheScannerSeesEachShape`
(`:337`) pins **6 shapes that MUST red** and **7 that MUST NOT**
(`type(e).__name__`, `isinstance`, `raise e`, `Result.from_exception(e)`,
`exc_info=False`, and both scrubbed forms). 13 cases, all passing. Without the
negative half the suite passes equally against a scanner that flags
everything — which is a different way of being uninformative, and would have
driven someone to add exclusions until the scanner was decorative. **[V]**

### The constructive counterpart: what makes an instrument able to discriminate

Everything above is negative — instruments that could not discriminate. This is
the positive form, and it is the single most transferable thing in this file.

> **Write the assertion for the property you actually want, not the mechanism
> you plan to change.**

**Why it is not a style preference.** An assertion aimed at the MECHANISM can
only confirm your model of the bug — it passes exactly when the change you
already decided to make is present. An assertion aimed at the OUTCOME can
CONTRADICT that model. Only the second can surface a defect you did not already
know about.

**Evidence — `4772d0c48`, "a failed subprocess termination reported the
transport disconnected".** The orphaned-subprocess fix retained the process
handle so a retry could act on it. The lane then wrote:

    packages/kailash-mcp/tests/regression/
      test_stdio_disconnect_does_not_orphan_the_subprocess.py:119
        async def test_a_second_disconnect_retries_the_termination

...because _"retain the handle so a retry can act"_ IMPLIES a retry that works,
and the cheapest way to check an implication is to assert it.

**The test failed for a reason the lane had not predicted.** Not the handle at
all — an early return on a `_connected` flag that was cleared before termination.
Visible in the diff:

```
-        if not self._connected:
+        if not self._connected and self.process is None:
```

The lane's own line:

> Had I tested "the handle is not None", it would have passed and the orphan
> would have stayed permanent behind a green test.

That mechanism-shaped assertion would have been GREEN, CORRECT about the handle,
and WRONG about the outcome — a non-discriminating instrument authored in good
faith, which is precisely the §1 class arriving through the front door.

**Provenance split, and it matters here.** The ARTIFACT is **[V]** — I verified
the commit `4772d0c48`, the test name at `:119`, and the `_connected` early-return
in its diff. The PROCESS NARRATIVE (that the lane did not reason its way to the
second defect, and that the failure was unpredicted) is **[R]** — that is the
lane's account of its own reasoning and is not recoverable from the artifact.
I record the split because the narrative is the part a `/codify` gate would most
want, and it is the part I cannot stand behind.

**Relation to §1.** This is the anti-vacuity control one level up. The negative
controls in `TestTheScannerSeesEachShape` stop an instrument degrading into
flagging everything; outcome-shaped assertions stop an instrument from only ever
confirming what its author already believed. Same property — the result must be
able to come out the other way — applied to the scanner and to the test
respectively.

---

## §2 The sibling left behind

**The class.** A fix lands where someone was looking. The same defect one call
site, one branch, one surface, or one package over is untouched — not by
judgement, but because the instrument that found the first one could not see the
second.

**The diagnosis, which I want carried verbatim because it names the reason these
survive review:**

> **Half-swept is the worst state to leave a file in, because the import reads
> as evidence the file was handled.**

A reviewer opening `hooks/manager.py` sees `from kaizen.utils.credential_scrub
import scrub_remote_error` at `:18` and a scrubbed sink at `:297`, and stops.
The raw `{e}` at `:420` was ~120 lines below the fold, behind a correct-looking
import.

(Line numbers as they stood AT `90899764a`, the commit that created the
half-swept state. Post-fix at `934d5f8ae` those two sinks are `:434` and `:445`
and are no longer raw. Citing the pre-fix numbers because the claim is about
what the file looked like to a reviewer at that moment.)

### Instances

| #   | The fix that landed                                                                                     | The sibling left                                                                                                        | Mechanism                                                                                             | Grade                                                                       |
| --- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| S1  | `98e83dfbe` coerced 4 rate-limit write surfaces                                                         | the 5th, `HTTPTransport.__init__`, wrote raw; guarded only by an `Optional[int]` ANNOTATION, which does not execute     | the 5th surface is in a different file from the other four                                            | **[V]** fixed `1df4df166`                                                   |
| S2  | the #1970 sweep applied drop-`exc_info` reasoning at 8 sites in `kailash-kaizen`                        | **11** sites in `kaizen-agents`, all with correctly-scrubbed messages                                                   | the scrub made them LOOK done; only the traceback still leaked                                        | **[V]** fixed `689f9ebd8`                                                   |
| S3  | `90899764a` fixed the hook EXECUTION sink in `hooks/manager.py`                                         | hook INSTANTIATION (`:420`) and hook FILE LOADING (`:423`) in the SAME FILE, ~120 lines below (lines as at `90899764a`) | the sweep's grep keyed on `exc_info\|logger.exception`; both are raw `{e}` with neither               | **[V]** fixed `934d5f8ae`                                                   |
| S4  | `20f507bb0` scrubbed the LOG line in `skill_tool.py`'s load-failure handler                             | THREE RETURN surfaces in the same handler: `SkillCompleteEvent`, `SkillResult`, and the `NativeToolResult` message      | every sweep this session was log-shaped; returns were never in scope                                  | **[V]** fixed `934d5f8ae`                                                   |
| S5  | the finalizer-deadlock class (`rules/patterns.md` § Async Resource Cleanup) swept in DataFlow and Nexus | `MCPChannel.__del__` still called `close()` → `runtime.release()` → `logger.debug`                                      | per that commit's own body; I verified the commit and its reasoning, NOT the DataFlow/Nexus precedent | **[V]** commit `e13339c02` exists and states this; the precedent is **[R]** |
| S6  | an `assert True`-on-404 fixed in one file                                                               | its twin one file over                                                                                                  | —                                                                                                     | **[R]**                                                                     |

### The inverse-asymmetry sub-finding (S4), which generalises furthest

S4 is the mirror of the shape found earlier in `delegate/print_mode.py`, where
the RETURN was scrubbed and the LOG was not. Both directions occur, and the S4
direction is worse:

> A `NativeToolResult` reaches the MODEL and enters the transcript — an audience
> strictly wider than a framework log, and one that persists and is not rotated.

Evidence, `934d5f8ae` on `tools/native/skill_tool.py`:

```
+            safe_error = scrub_remote_error(e)
-                error_message=str(e),          → +  error_message=safe_error,   (SkillCompleteEvent)
-                error_message=str(e),          → +  error_message=safe_error,   (SkillResult)
-   f"Failed to load skill '{skill_name}': {e}" → +  f"... {safe_error}"          (NativeToolResult)
```

**`_SinkScan` does not distinguish sink-from-return.** It flagged these three
only incidentally, because the exception name happened to appear in string
context inside the handler. A scanner ported to other packages should classify
the two, because they need different verdicts: a filesystem path in a log is a
diagnostic worth keeping; the same path in a tool result is disclosure. **[V]**

### The structural remediation, demonstrated not proposed

Key on the **shape**, not the **instance**. `_SinkScan` finds any occurrence of
the shape in any file, including files nobody has looked at — which is what
found the 6 in §1. A hand-sweep finds only what the sweeper's query matched, and
each of S1–S4 is a hand-sweep's blind spot.

The measured asymmetry that makes the argument:

| Package          | Has an AST scanner? | Sites                         |
| ---------------- | ------------------- | ----------------------------- |
| `kaizen-agents`  | yes                 | 191 wrapped, **0 bare**       |
| `kailash-kaizen` | no                  | **390 bare across 107 files** |

Every gap the adversarial reviewer and the orchestrator found this round was in
`kailash-kaizen`; none in `kaizen-agents`. **The scanner is the difference, not
the diligence.** **[V]** — measured by running `_SinkScan` over
`packages/kailash-kaizen/src`; filed as **#2012**.

Actionable split for whoever takes #2012: **28 of the 390 sites sit in 8 files
that ALREADY import a scrubber** for their other sinks — the half-swept
category, and by the diagnosis above the highest-risk subset. The other 362 sites
in 99 files were never touched by any sweep. **[V]**

### One caveat on the count, recorded so it is not re-derived

390/107 is an UN-TRIAGED surface, not a defect count. Each site still needs the
where-can-this-exception-be-RAISED (local vs remote) classification that
`kaizen-agents` received; only the remote-raised subset is a credential channel.
The rest are local `OSError`/`ImportError`/`JSONDecodeError` whose path and
module text ARE the diagnostic and must be preserved — a blanket sweep would
trade a leak for a blind spot, which is the failure mode that halted the first
attempt at this in `kaizen-agents` (see that file's docstring, "WHAT LANDED, AND
WHY IT IS NOT THE SWEEP THAT WAS HALTED"). **[V]**

---

## Cross-reference between the two sections

They are the same mechanism at different scopes. §2's siblings survive _because_
of §1's instruments: S3 survived a grep that could not match its shape, S2
survived a sweep keyed on the wrong token, S4 survived because no instrument
looked at return surfaces at all. The remediation is likewise shared — a
shape-keyed detector WITH negative controls, since a detector without them
degrades into flagging everything and is then disabled by exclusions.

The constructive counterpart in §1 closes the loop from the other side. A
shape-keyed detector stops a sibling surviving because nobody LOOKED there;
an outcome-shaped assertion stops one surviving because the person who DID
look wrote a test that could only agree with them. S1 through S4 are the
first failure; `4772d0c48`'s second lock-out — found by a test that failed
for an unpredicted reason — is the second one being avoided.

One property unifies every finding in this file. It is **not** this session's
discovery — see §0: it is `instrument-discipline.md`'s governing question,
baseline priority, loaded in every session here, and every agent in §1 had it
in context while violating it. The session re-derived it the expensive way:
**an instrument is only evidence if its result could have come out the other
way.** Applied to a sweep it means a positive
control; to a scanner, negative controls; to a test, an outcome-shaped
assertion; to a claim, a named falsifying result. Nine instruments in §1
lacked that property in one direction or the other, across four lanes, and
four of them were authored by the agent actively fixing the class — under a
loaded baseline rule that states the test in its first line. **That is the
finding: not that the property is true, but that stating it at baseline
priority did not make it hold.**

---

## §3 Version archaeology — four traps, each producing a confidently wrong release note

**Provenance:** every trap below was hit first-hand by the nexus lane while dating three
findings for release notes and issue bodies. Recorded here by the ORCHESTRATOR from that
lane's reports because the lane hit its session quota before it could write this section
— so the traps and their commands are **[R]** (relayed, not re-run by me), while the
three-namespace outcome at the end is **[V]** (verifiable from the filed issues).

**Why this section exists.** An affected-versions line is one of the few things a project
publishes that a user acts on directly: they check their version against it and conclude
they are safe or exposed. Each trap below yields a plausible, confident, WRONG such line.
None is exotic; all four appeared while dating three findings in one session.

### The four traps

| # | Trap | What it produces | Grade |
| - | ---- | ---------------- | ----- |
| T1 | `git tag --contains <sha>` where a tag namespace is reused across sub-packages | **667 of 697 tags** returned, including a `v0.2.0` pointing at a commit dated **three months AFTER** the defect landed. Reads as "affected since the beginning of the project". | **[R]** |
| T2 | Trusting a commit SUBJECT that names a release | The introducing commit's subject said "Release v0.8.5"; the `v0.8.5` **tag does not contain it**. First shipped in **v0.8.6**. Wrong by one release — and every user on v0.8.5 would have been told they were affected. | **[R]** |
| T3 | `git log --follow -S '<string>'` | Returned `b553104c6`, **the monorepo refactor** — dating a *security* defect to a file move. `--follow` and `-S` do not compose reliably. | **[R]** |
| T4 | Tag-NAME collision | `kailash-v2.1.0` → `d918b5a5c` (2026-03-24, **clean**) and `v2.1.0` → `a76453a94` (2026-03-26, **CONTAINS the defect**) are different commits two days apart. A user asking *"I'm on 2.1.0 — am I affected?"* can land on either and get **opposite answers**. | **[R]** |

### The method that survives all four

1. **Pickaxe the exact string over the owning file** — `git log -S '<exact string>' -- <path>`.
   Expect a **small definite commit set**; the introduction and the fix is the ideal shape,
   because it proves continuity with no gap rather than inferring it.
2. **Where two independent strings exist, run both and require agreement.** Done for the
   finalizer dating; it is why that 136-day figure is trustworthy rather than plausible.
3. **Sort tags by COMMIT DATE, not by version string**, and read the clean→CONTAINS
   boundary. This sidesteps T1 and T4 together.
4. **Resolve T3 by enumerating every path ever bearing the filename** (here: exactly one)
   and reading content at the add, rather than trusting `--follow`.
5. **Publish the DATE and/or the SHA alongside the version**, not the version alone — T4
   means a version string is not by itself an identifier.

### The honest-bound practice

One finding's history begins at the repo's own horizon: the file enters at `b553104c6`
(2026-03-11) with no prior path, and `git ls-tree nexus-v1.4.1` contains no such file at
all. The lane's statement is the model:

> Versions before `nexus-v1.4.3` were built from source this repository never held.
> **I am not claiming they were clean; they cannot be assessed from here.** Exposure is
> ≥140 days and possibly longer.

An affected-versions claim with a stated bound is usable. One that quietly stops at the
repository's horizon and reads as complete is worse than no claim, because a reader cannot
see where the evidence ended.

### The outcome that justifies the whole section — **[V]**

Three findings from one session landed in **three different version namespaces with three
different spans**:

| finding | namespace | first affected | span |
| ------- | --------- | -------------- | ---- |
| #2008 pooled-worker shutdown wedge | core | `v0.8.6` (2025-07-22) | ~382 days |
| #2013 inert `enable_auth` facade | **nexus** | `nexus-v1.4.3` (2026-03-21) | ≥140 days (bounded) |
| `__del__` finalizer (fixed `e13339c02`) | core | `v2.1.0` (2026-03-26) | 136 days |

**Any single affected-versions line covering these would have been wrong about at least
two of them** — and the errors would have been in the dangerous direction for #2013
(understating a security exposure) and in the alarming direction for the finalizer
(overstating it by ~250 days and the entire `v0.8.x`–`v2.0.x` range).

### Relation to §1

These are §1's class applied to `git` rather than to a test or a sweep: **an instrument
returning a confident value uncorrelated with the question asked.** T1 returns tags, not
affected releases. T2 returns a subject line, not a tag's contents. T3 returns a commit,
not an introduction. T4 returns a commit, not *the* commit. The §1 defense transfers
directly — a positive control here means **checking the boundary in both directions**
(a tag that must be clean AND a tag that must contain), which is what the clean→CONTAINS
read above actually is.
