---
owner: esperie
last_reconciled_sha: 2268a3e14
migrated_from: .session-notes
---

# Session Notes — 2026-08-10 (session L)

## Where we are

Workspace `issue-1720-llm-consolidation`, branch `fix/issue-1720-forest-drain`.
**PR #2016 IS OPEN.** The branch is pushed. Redteam rounds 9, 10 and 11 all ran to completion on
BOTH lenses and are closed. **kailash-mcp 0.5.0 AND 0.5.1 are published to PyPI.**

**CI is 26 SUCCESS / 2 FAILURE**, down from 11 failures. Remaining: `Test DataFlow Unit Suite
(Tier 1)` and `CodeQL`. Neither is diagnosed to completion — see **Unfinished** below. Do NOT
assume they are the same causes already fixed.

## Read first

1. `workspaces/issue-1720-llm-consolidation/04-validate/sweep-2026-08-10.md` — **THE DECISION
   REPORT.** PCF-triaged queue, ETA in cycles, three decision points. Supersedes `-08-09c.md`.
2. `workspaces/issue-1720-llm-consolidation/04-validate/launch-ledger-sessionL.md` — the full
   round-9/10/11 record with every measurement.
3. This file's **Traps** — several are NEW and cost real time this session.

## What the redteam found, and why it took three more rounds

Rounds 6-11 EACH found a real defect in the previous round's fix. The shape, now legible:
**a fix hardened the layer it was looking at, and the next round found the same class one layer
over.** R9 hardened the helper; R10 found 14 sink sites logging the same identifier RAW beside the
sanitized one; R11 found the CRITICAL below.

**R11 CRITICAL (fixed, `160cfc8de`).** `text in _CPYTHON_PSEUDO_IDENTIFIERS` is NOT byte-equality —
it is `__hash__` then `__eq__`, both overridable on a `str` SUBCLASS, and `isinstance` admits one.
The allowlist branch returned BEFORE the charset filter and BEFORE the length bound:

```
class Sneak(str):
    def __hash__(self): return hash("<module>")
    def __eq__(self, other): return True
-> LEN 5043, newline True, " <- " True, "@" True
```

Closed by normalizing to a plain `str` via `str.__str__` BEFORE any predicate. `str(value)` alone
is NOT enough — `__str__` is overridable too, so the result is re-normalized on TYPE IDENTITY.
**The `# noqa: E721` on that line is load-bearing**: Ruff says "use isinstance()", and doing so
reintroduces the CRITICAL verbatim. The reason is inline; do not "fix" it.

**R11 also:** `__suppress_context__` is shadowable by a class attribute that LIES rather than
raises, defeating `raise X from None`. Closed by reading the three walk attributes through
`BaseException`'s OWN descriptors — which defeats a shadow that raises AND one that lies.

## THE METHODOLOGICAL FINDING — this is the one worth carrying

**A mutation matrix perturbs the IMPLEMENTATION while holding the INPUT fixed.** My matrix reported
18/18 red and I read it as convergence. It was not: the CRITICAL's vector is the input's TYPE.

The r11 mutation lens **refuted my "structurally blind" conclusion with a measured counter-example**
and its formulation is better than mine: both matrices applied only **WEAKENING** mutations. A
**HARDENING** mutation on the normalization line (`text = value if isinstance(...) else str(value)`
→ `text = str(value)`) reds nothing AND defeats the CRITICAL. Conventional mutation testing omits
the hardening family by construction.

**Its generative rule, adopted:** _enumerate the dunders a function's control flow consults, and
mutate the point where each is trusted or normalized away._ For `_safe_identifier` that is
`__class__`, `__str__`, `__bool__`/`__len__`, `__hash__` AND `__eq__`, `__len__`, `__getitem__` —
six consulted, one previously probed.

## Unfinished — pick up HERE

1. **CI: 2 failures, NOT fully diagnosed.**
   - `Test DataFlow Unit Suite (Tier 1)` — the run was still in progress, so its log was
     UNAVAILABLE. My greps against it returned empty, which is **zero evidence, not "no errors"**.
     Locally `packages/kailash-dataflow/tests/unit` is **3670 passed**. Re-read the log once the
     run completes before assuming anything.
   - `CodeQL` — open alerts are pre-existing quality findings (`py/unused-import`,
     `py/cyclic-import`, `py/repeated-import`, `py/catch-base-exception`) in nexus / kaizen /
     dataflow / trust, none carrying a security severity. Not chased.
2. **Merge #2016**, then `/release` — kailash 2.63.0 BEFORE both nexus and dataflow.
3. **Decision A (sweep §6): `#2005` is at its FIFTH defer cycle and may be MIS-LABELLED.** A tenant
   key falling open to a shared global namespace is a tenant-isolation shape. Deliberately NOT
   closed alongside `#2003`. Recommend re-triage as BUG.
4. **Decision B: kailash-mcp was published from an UNMERGED branch.** 0.5.0 and 0.5.1 carry code
   not on `main`. Merge promptly, or cut `mcp-v0.5.1` from main after merge so tags match artifacts.
5. **Decision C: residuals P2 and P3 could NOT be filed** — the session-K sweep names them but no
   substantive content survives anywhere. Filing would have meant inventing findings. Re-derive or
   accept the loss.

## Executed this session

- **PR #2016 opened**; 5 residuals filed (`#2017`-`#2021`); `#2003` closed with owner gate and a
  re-open criterion; `#2011` labelled.
- **Four issue-text corrections posted** (`#2013`/`#2014`/`#2015`/`#1997`), each re-verified against
  HEAD first. **`#2013`'s session-K claim was FALSE and I posted the wrong version before catching
  it** — see Traps.
- **kailash-mcp 0.5.0 → PyPI** (auth-bypass + disclosure fixes), **0.5.1 → PyPI** (`mcp<2.0` cap).
- CI repairs: spec-drift cite (`75cabdda6`), DataFlow fixture gap (`829e76e20`), mcp import-patch
  recursion (`532dd8807`), mcp cap (`c2affcf04`), `requests` in `[dev]` (`2268a3e14`).

## Traps — several are NEW and each cost real time

- **`gh run view --log` on an IN-PROGRESS run returns "logs will be available when complete"**, and
  a grep over it returns EMPTY. That empty is zero evidence. Check `.status` first.
- **A green publish job is NOT evidence the package published.** The PyPI workflow reported
  `Publish to PyPI: success` while pypi.org still served the old version — twice. Confirm by
  reading the job log for `Uploading …` + `200 OK`, then by a clean-venv `pip install`. PyPI's
  JSON API and index lag the upload by minutes; a check at +30s can legitimately show the old
  version.
- **`$?` after a pipe reports the LAST command's status, not the one you care about.** Bit me on
  `grep … | head` (printed "confirmed" for a grep that had not matched) and on
  `spec_drift_gate.py … | tail` (printed exit 0 for a gate that failed).
- **`mapfile` is a bash builtin and does NOT exist in zsh.** The CI spec-drift invocation uses it;
  copying that line locally silently passes an empty file list and the script scans `.`.
- **`nohup … &` inside a `run_in_background` Bash call kills the child** when the wrapper returns,
  and reports **exit 0**. It truncated a 1646-test run at ~190 tests and looked like success.
- **A bare `python -c` inside a git worktree resolves `kailash` through the EDITABLE INSTALL to the
  MAIN repo**, not the worktree. A mutation probe run that way silently measures unmutated code.
  **pytest resolves correctly** (root conftest inserts the worktree's `src`). Prove the resolved
  path before reading any result.
- **The venv's editable `kailash-mcp` points at THIS branch**, so a "does it fail on main too?"
  test in a main worktree still imports this branch's 0.5.0. That produced a WRONG "pre-existing"
  verdict this session. Compare against the PUBLISHED wheel instead.
- **`python-use-type-annotations` is a pygrep hook** matching a comment-hash followed by the guarded
  word with no trailing punctuation. It fired on a comment using that phrase in prose — and then
  fired again on the REWORDED comment that explained the trap by quoting the literal.
- **Root `tests/` HANGS, it does not merely run slowly.** 42s CPU in 17 minutes, an asyncio selector
  wait; no tree has an effective pytest timeout. `--timeout=60 --timeout-method=signal` makes it
  complete and attributable; **`--timeout-method=thread` KILLS the process on first hang** and you
  get no summary at all.
- **Tree-wide root `tests/` = 389 failed / 2375 passed / 92 errors, and that is INFRASTRUCTURE.**
  270 integration + 119 e2e, **zero in unit or regression**. All five backing ports probed CLOSED
  (Postgres 5432/5433, Redis 6379/6380, MySQL 3306). Corrects the older note claiming 5432 was up.
- **`pre-commit run --all-files` rewrites 2,022 files (#1995).** Always scope to the branch's
  changed files. isort and Ruff also reorder one kaizen-agents test against each other with a
  net-EMPTY diff — that is #1995's drift, not a defect.
- **`core.hooksPath` points at `/Users/esperie/repos/loom/kailash-py/.git/hooks`, which does NOT
  exist** — so NO commit in this repo is hook-checked, including this session's.
- `.env` `OPENAI_API_KEY` is INVALID (live 401). Anthropic works.

## Corrections I made to my own claims — do not re-derive these the hard way

- **`#2013`:** I posted that `hasattr(gw,"enable_auth")` is True. **WRONG** — `create_gateway`
  returns `EnterpriseWorkflowServer`/`DurableWorkflowServer`/`WorkflowServer`, and `hasattr` is
  **False on all three**. The branch is DEAD CODE. Correction posted as a follow-up comment. What
  survives: `use_plugin("auth")` runs unconditionally, and auth dies because `def set_auth_manager`
  **exists nowhere in the tree**.
- **mcp `RecursionError`:** I reported it pre-existing. **WRONG** — `mask_error_text` appears
  nowhere in the published 0.4.3 wheel and is called inside `_init_mcp` in 0.5.0. My publish
  introduced the trigger; the test was latently broken.
- **Spec-drift gate:** I reported "17 expired baselines = calendar expiry". **WRONG** — those are
  `::warning`; `spec_drift_gate.py:2615` returns non-zero only for a `FAIL` finding. The real cause
  was one bare method cite.
- **A CRLF near-miss:** a scripted rewrite converted `visualization/api.py` from CRLF to LF — 914
  lines of churn inside a security commit where the real change is 7 lines. Caught at `--stat`
  review and amended before push.

## Forest ledger

`F1/F2/F3/F5/F6` (#1970/#1971/#1972/#1974/#1981) are this branch's delivered work — they close on
merge. **Re-implementing them is the `wave-loop.md` MUST-7 trap.**

Genuinely open and issue-backed, value-ranked in the sweep report: **#2013** (own lane, needs a
JWT-secret-source decision), **#2009**, **#1997**, **#2015**, **#2014**, **#2002**, then
#2004/#2006/#2007/#2012/#2008/#2000/#2010.

**Measured this session, so the follow-up starts from a number rather than "subset unknown":** raw
`type(<exc>).__name__` sites outside the 7 swept sink files — `src/kailash` 81, `kailash-kaizen` 60,
`kailash-dataflow` 54, `kailash-nexus` 29, `kaizen-agents` 14. Most are ordinary Python idiom, not
leaks; triaging them for attacker-controlled class names is its own shard.
