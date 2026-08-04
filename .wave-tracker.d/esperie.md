# Wave tracker — esperie

## Status: WAVE 8 IN FLIGHT (2026-08-04, session D)

Branch `fix/issue-1720-forest-drain`. Executing the RATIFIED ordering constraint from
`.session-notes.d/esperie.md`: W19 fix → Round-2 redteam → version anchors + MCP pin →
`/release`. Decision C runs independently and blocks nothing.

Read this file BEFORE spawning anything (`rules/orchestration-launch-ledger.md` MUST-2;
`rules/wave-loop.md` MUST-6). Match every completion notification against the table
BEFORE reacting (MUST-3).

### Launch ledger — Wave 8

| track             | scope (EXCLUSIVE file ownership)                 | mode          | status                                                                |
| ----------------- | ------------------------------------------------ | ------------- | --------------------------------------------------------------------- |
| w8-w19-scrub      | `kaizen/utils/credential_scrub.py` + tests       | inline (orch) | **DONE** — `4fdb37fa2` `9eb66d893` `73e86016d`                        |
| w8-w12-authz      | `discovery._check_user_access` fail-open (recon) | read-only     | **DELIVERED after query** — part fixed `942bdef80`; rest PENDING USER |
| w8-w13-route      | `runtime.py::_route_task` (recon)                | read-only     | **DELIVERED after query** — root cause fixed `b9a0a4ed6`              |
| w8-specdrift      | Decision C — spec-drift adjudication (recon)     | read-only     | **DELIVERED after query** — measurement only, no code                 |
| w8-r2-security    | R2 adversarial security lens over the branch     | read-only     | IDLE/NO REPORT → queried, OUTSTANDING                                 |
| w8-r2-correctness | R2 correctness + closure-parity lens             | Bash+Read     | IDLE/NO REPORT → queried, OUTSTANDING                                 |

All three dispatched agents are READ-ONLY and read committed HEAD, so they cannot
collide with the inline W19 edit (`rules/agents.md` § Worktree Orchestration). Session-C's
finding stands: use the SHARED tree with exclusive per-track file ownership, NOT
`isolation: "worktree"`.

**ALL FIVE agents went IDLE without delivering a report** — the documented failure
mode (session B: 6×; session C standing note), now 5-for-5 this session. Resumed
via message per protocol rather than re-dispatched: **3 of 3 queried recon agents
delivered in full on the first query**, and each said the same thing — the work WAS
complete and the report had been written as final assistant text without ever
calling SendMessage. So the failure is DELIVERY, not execution. Query, never
re-dispatch: re-dispatching would have thrown away three complete investigations.
**An idle signal is ZERO evidence and was NOT scored as "no findings."**

**The queried reports were worth far more than the inline re-derivation.** Both
W12 and W13 were re-derived inline while waiting, and BOTH inline conclusions were
WRONG — see § reconciliation below. Do not treat inline re-derivation as a
substitute for the agent's report; treat it as a hedge against never getting one.

One dispatch error worth not repeating: `w8-specdrift` was given the read-only
`analyst` type but its task required running `tools/sweep-redteam.py`. It correctly
refused and asked for the output (`rules/agents.md` § "Verify Specialist Tool
Inventory Before Implementation Delegation" — check for `Bash` BEFORE dispatch).

### Wave 8 reconciliation — do NOT re-derive

**W13 — the backlog row was wrong, AND so was my inline correction of it.**
The row said "SEMANTIC branch dead, picks agent[0]". I read the code, saw
`_score_capability` called with `if score > best_score` driving selection, and
concluded the row was false. WRONG. The loop is there; it never executes.
`_route_task` read `getattr(a2a_card, "capabilities", [])` but `A2AAgentCard`
declares `primary_capabilities` / `secondary_capabilities` /
`emerging_capabilities` and NO `capabilities` — and for the dict shape `getattr`
never sees dict KEYS. Empty for BOTH shapes ⇒ judge invoked ZERO times.
**Reading the code did not settle it; COUNTING JUDGE INVOCATIONS did**
(`_route_task -> 'a1'`, 0 calls vs `route_task -> 'a2'`, 2 calls, same fixtures,
same process). Use that instrument on any "is this branch live?" question.
ROOT CAUSE was two implementations of the same four strategies, each holding the
bug the other fixed — the dead copy had the correct round-robin bounds guard, the
live one had the correct capability lookup. Duplicate DELETED (`b9a0a4ed6`);
`_route_task` is now a thin adapter. Fixed a LIVE production `IndexError` on any
pool shrink in passing.

**W12 — the row hid the worst half, and the in-code deferral premise is REFUTED.**
THREE findings, not one:
(a) checker ABSENT (`permission_checker=None`, the DEFAULT, and the shape the
class's own docstring example uses) ⇒ grant with NO log at all. `security.md`
§ Secure-Default; fixed with the prescribed loud one-time WARN (`942bdef80`).
(b) checker RAISES ⇒ grant. Already loud at ERROR. **PENDING USER DECISION.**
(c) **THE ONE NOBODY SAW:** `TrustOperations.verify()` — the checker type the
docstring names — takes `(agent_id, action, resource=None, level=..., context=None)`.
NO `user_id`, NO `organization_id`, NO `**kwargs`. The call site passes
`user_id=`/`organization_id=` ⇒ `TypeError` on the FIRST agent ⇒ caught by (b) ⇒
**every agent granted to every user, always.** Not a transient window — the steady
state for the DOCUMENTED integration. Verified by `inspect.signature`, not by
reading. This REFUTES the in-code note's premise that flipping (b) fail-closed
would "deny every user during a transient outage": for TrustOperations users there
is no working state to regress from. Every existing test supplies a bespoke
duck-typed checker written to match the call site, which is why nothing caught it.
**(b)+(c) are a live PENDING DECISION — see `.session-notes.d`.**

**W19 — my own first fix was wrong and I caught it by attacking it.**
`4fdb37fa2` excluded `"`, `{`, `}`, `\` reasoning all four are RFC-3986-illegal in
userinfo so excluding them was free. Not free: `{`, `}`, `\` made
`postgresql://u:pa{ss@host/db` and siblings stop matching and LEAK IN FULL. `"`
ALONE fences every compact-JSON case. Narrowed in `9eb66d893`.
**Reusable lesson: RFC-illegal ≠ cannot-occur.** Generated passwords carry those
bytes and lenient drivers accept them, so a scrubber that only redacts well-formed
URLs redacts the wrong set. The test is not "is this byte legal here?" but "does
excluding it buy coverage I cannot get otherwise?"
Accepted residual pinned in `73e86016d`: a URL with a `:` in its path plus a later
`@` in the SAME JSON string value still over-redacts. Left deliberately — that IS
the credential shape and no regex separates it without parsing. **Do NOT close it
by widening the character class; that is the exact error above.**

## Wave 7 — final disposition (CLOSED)

| track            | scope                                                          | outcome                        |
| ---------------- | -------------------------------------------------------------- | ------------------------------ |
| w7-cred-audit    | S4 enumeration, fallback.py, sweep autouse-skip (READ-ONLY)    | DONE — report applied by hand  |
| w7-nexus         | nexus S8 atomicity, `_tools`, 2.16.0 MINOR                     | DONE — `84f08d203`             |
| w7-1981-contract | a2a `run()` contract, runtime state invariant, #1981 consumers | DONE — `2a54f134f`             |
| w7-core-dialect  | NEW-1 + NEW-2 across core / dataflow / kailash-ml              | DONE — `d8b29d038` (recovered) |
| w7-2nd-scrubber  | S1 shared `credential_scrub` module                            | DONE — `c0c99b589` (recovered) |
| w7-nexus-del     | `Nexus.__del__` -> ResourceWarning                             | DONE — `eda71b7d3` (recovered) |
| w7-ollama-deploy | keyless local provider resolution                              | DONE — `5dfa5f225` (recovered) |
| w7-task-handoff  | `_build_workflow_from_agents` task handoff                     | DONE — `7816923f7` (recovered) |

**"Recovered" = the shard died on a session limit mid-flight; its on-disk work was
complete, and the orchestrator verified it by behavioral probe, formatted it, and
committed it.** Five shards died in the same instant. Nothing was lost — because shards
edit the SHARED tree, not `isolation: "worktree"`, which would have left 5 orphan
checkouts. Keep using the shared tree with exclusive per-track file ownership.

## Verified this session — do NOT re-derive

- **S4 is 23 sites, not the ledger's 8.** 9 explicit `raise … from e` + 14 BARE raises
  inside `except` where Python sets `__context__` implicitly. The 14 are invisible to a
  `from e` grep. `packages/kaizen-agents/` has ZERO sites. **This is the only session-B
  finding still open (forest `W10`).**
- **httpx probe (settles which raises leak):** `TimeoutException` / `ConnectTimeout` /
  `ReadTimeout` / `ConnectError` render `'timed out'` only — NOT leaks, no fix owed.
  `HTTPStatusError` **from `raise_for_status()`** renders the full URL including userinfo
  AND query token. All four `raise_for_status()` sites are already on the S4 list, so that
  enumeration is complete and W10's `__cause__` is a real credential, not a hypothetical.
- **Nexus registration touches SEVEN stores** (2 registry + 1 gateway + 4 MCP), not four.
- **`_register_handler_workflow` never existed** — phantom name in the CHANGELOG and a code
  comment. Real surface is `Nexus.register_handler`.
- **`_tools` writes register nothing reachable** — it exists only on the FastMCP fallback
  shim (assigned to `self._mcp`, never to `MCPServer` itself); handlers iterate
  `_tool_registry`.
- **`DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH` challenge — the "RESOLVED" here was an
  OVER-CLAIM; corrected 2026-08-04 (`0e2497b3b`).** What that entry describes DID land
  (`max_length` keyword-only and required; Postgres `upsert()` / `quote_identifier()`
  agreeing on a 100-char identifier), but a SECOND defect in the same constant survived
  it and this row asserted the whole challenge closed.
  The unknown budget is numerically EQUAL to SQLite's (both 128) and the WARN trigger was
  a VALUE comparison, so a correctly-bound **SQLite** caller — the default store here —
  was indistinguishable from an unbound one and warned on every identifier. The
  no-false-positive test covered **Postgres only** (63, numerically distinct), so it
  passed either way: a non-discriminating instrument cited as proof, the THIRD occurrence
  of that shape on this branch (see F1 and the W19 probe-set gap above).
  Now fixed with a real sentinel (`_UnknownBudget`, an `int` subclass) and the trigger
  moved to `isinstance`; the test is parametrized over both dialects with SQLite as the
  discriminating case. **Left visible rather than rewritten** — a row that silently
  changed from RESOLVED to not-resolved would hide that the over-claim happened.

## One unresolved thread (NOT a blocker, but do not re-discover it)

`w7-core-dialect` re-fired after its work was already committed and died again (529
Overloaded). Its last words: _"One test differs (20 vs 19). Let me identify exactly
which:"_ — it was mid-investigation of a test-COUNT delta and never named the test. It
made no further on-disk edits (verified: tree carried only the wrapup files afterwards).

Independently green regardless: 31 core + 67 dataflow targeted tests pass, all six
packages import, and NEW-1 / NEW-2 were confirmed by behavioral probe. But the orchestrator
never ran the FULL core-SDK suite itself — that shard's "4,792 passed" is its own
unverified report. So when W11's full-suite run happens, a count that does not match a
remembered baseline is most likely this same benign delta (tests were added this wave),
not a regression. Confirm rather than assume.

## Concurrency

Cold-start ~3 concurrent Opus agents (`rules/worktree-isolation.md` Rule 4). This session
ran 5 and all 5 died together on a **session limit** (not the server-side throttle — no
`not your usage limit` string). That is a THIRD failure mode distinct from both the
cold-start throttle and single-agent death: it is account-scoped and kills every in-flight
agent simultaneously, so the recovery unit is the whole wave. Run heavy suites SERIALLY;
concurrent suite runs alongside live agents produce `sqlite3 disk I/O error` and
perf-threshold failures that are self-inflicted.

## Standing operational note

Agents go idle WITHOUT delivering a final report (6× in session B). Resume via message
rather than re-dispatch — it recovered 3 of 4. Re-dispatch only after a resume ALSO returns
empty. Never score a silent-idle as a clean round: that manufactures a convergence that
never happened. Corollary from session C: a shard that dies mid-flight may still have
COMPLETE work on disk — verify the tree before assuming the task needs re-running.
