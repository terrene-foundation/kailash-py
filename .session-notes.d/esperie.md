---
owner: esperie
last_reconciled_sha: 3120a6ede
migrated_from: .session-notes
---

# Session Notes — 2026-08-05 (session E)

## Where we are

Workspace issue-1720-llm-consolidation, phase 05-codify, branch
`fix/issue-1720-forest-drain` @ `3120a6ede` — **27 commits ahead of the session-D
close (`03795208d`), NOT pushed** (87 ahead of `origin/main`). Tree clean. No
stray worktrees.

**Release is still HELD, and session D's recommendation to release is REFUTED.**

## Read first

1. This file's **THE FINDING OF THIS SESSION** — it changes how you should read
   any "converged" claim on this branch.
2. **Open items** + **Traps** below.
3. `git log --format='%h %s%n%b' 03795208d..HEAD` — every commit body carries its
   own evidence and states what was NOT done.
4. **`workspaces/issue-1720-llm-consolidation/04-validate/sweep-2026-08-05.md`
   — the CURRENT decision report.** Supersedes `sweep-2026-08-04b.md`, whose §1
   completion table and §6 release recommendation are REFUTED (see below) though
   its §3/§4 triage largely carries forward. Carries the PCF triage, the six
   decision points, and the Sweep-N gate owed on #1995.

## THE FINDING OF THIS SESSION

**Session D recommended releasing on "abnormal-termination evidence" — severity
fell monotonically, nothing in the last three rounds changed what the module
leaks. Five more rotated-lens rounds found FIVE CRITICAL/HIGH defects, including
an unconditional auth bypass.** That recommendation would have shipped them.

The reasoning that justified it ("findings are getting smaller") was not wrong
about the trend — it was wrong that the trend was evidence. Each round found
serious defects _on an axis the previous round's lens could not see_.

**Three of the five were regressions introduced BY fixes**, including one of
mine. That is the durable lesson: on this branch a fix is not a reduction in
risk until an independent lens has looked at the fix itself.

| Round | Lens                                                  | Found                                                                                                                                                                                                                                                                                                                                                                  |
| ----- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1    | adversarial security + correctness/instrument         | **CRITICAL** — `completion/complete` was a THIRD tool-schema emitter; anonymous callers got permission-gated tools' full `inputSchema`, and it leaked `disabled` tools too                                                                                                                                                                                             |
| R2    | same-class sibling sweep + consumer/API + adversarial | **CRITICAL** — unconditional auth bypass in the async tool wrapper (send no credentials → tool EXECUTES). **CRITICAL** — falsy-but-not-None `auth_provider` silently disabled authz + rate limiting + the new schema gate while reporting auth ENABLED. **CRITICAL** — release-blocking floor: 51 modules module-scope-importing a symbol absent at the declared floor |
| R3    | runtime/end-to-end + adversarial                      | **HIGH** — credentials written verbatim into Redis key names + debug logs. **HIGH (mine)** — deny-on-advisory-labels erased agents from discovery entirely                                                                                                                                                                                                             |
| R4    | whole-branch behavioural differential + adversarial   | **HIGH** — the R3 cache fix traded the credential leak for CROSS-PRINCIPAL result sharing, and pinned the sharing as an invariant test                                                                                                                                                                                                                                 |
| R5    | narrow verification of the R4 fix                     | fix-introduced red in an out-of-package test; **F4 confirmed by me** (below)                                                                                                                                                                                                                                                                                           |

**My own regression, recorded so it is not repeated.** In wave 3 I instructed an
agent to "fail closed on an unparseable constraint payload." That was right in
general and wrong for that field: `chain.py:350-363` documents
`effective_constraints` as _"reporting-only — read by NO allow/deny gate ...
advisory per #1896"_ and states _"the tightening IS enforced"_ elsewhere via
signed derived capabilities. Denying on it added no safety and removed
availability — agents carrying any constraint label vanished silently from every
user's discovery list, and the only operator lever was disabling the checker.
**Read the field's own contract before hardening on it.** Fixed in `b8d60577e`.

## Executed this session (25 commits)

Security fixes: the third schema emitter + `_public_tool_view` extraction
(`19c8cfb33`), the async auth bypass deletion + falsy-`auth_provider` identity
guards (`14d9d8b31`), credentials-in-cache-keys (`71eb63790`), cross-principal
cache sharing + key hashing (`ee6d5b8bb`), discovery fail-closed + falsy-checker

- denial-shape (`393f33e27`, `784f92462`), the advisory-label revert
  (`b8d60577e`), the scrub local/remote split (`b2d3acce5`), the release-blocking
  floor + gated-schema normalization (`269038fd9`), trust-plane lazy FastMCP for
  #1996 (`45ccac417`), and the `key=value` prose regression (`eee4fa59b`).

Test-only: six security tests that pinned pre-#1912 fixtures rather than the
guards (`9791892fa`), two that pinned the bypass (`2f7d56807`), the cache-key
shape (`d8ecef1f8`).

**`packages/kailash-kaizen/tests/{security,trust}` went 9 failed → 0.** All were
stale tests asserting behaviour production deliberately blocks; **zero product
changes** were needed — greening them by loosening would have re-opened the
#1912 capability-transplant vector and the `_get_key` privatization.

## Verified green (measured this session, not asserted)

- `packages/kailash-mcp/tests/` — 584 passed
- `packages/kailash-kaizen/tests/{security,trust}` — 127 passed, 0 failed
- `packages/kailash-kaizen/tests/regression/` — 1356 passed
- `packages/kaizen-agents/tests/` — 13 failed / 3809 passed; the 13 are live-LLM
  flakes, **discriminated** against a git-extracted `03795208d` tree (identical
  node IDs), not assumed

## Open items — NONE fixed, NONE release-blocking-verified

1. **F3 (MEDIUM, unadjudicated)** — on a non-empty advisory label list,
   `discovery.py` grants `permission_level="execute"` with a bare
   `AccessConstraints()` (the type's own docstring: "the MOST PERMISSIVE value
   this type can hold") while the checker said e.g. `read_only`. The
   "enforced elsewhere" justification is about the trust-chain verification
   path, which `find_agents_for_user`'s return value does not traverse. Two
   lanes flagged it; nobody has ruled on whether `"execute"` is defensible.
2. **F5/F6/F7 (LOW, unadjudicated)** — advisory-warn is once-per-process
   per-label-set with no `user_id` in the record; a `Mapping` whose `__len__`>0
   but `items()` empty falls through to an UNLIMITED grant; the operand-echo
   doctrine enumerates only `float`/`int`/`re.compile`/`Path` (unprobed:
   `Decimal`, `strptime`, `ipaddress`, `b64decode`, `KeyError`).
3. **3 nexus failures — CONSISTENT, not flaky, and UNOWNED.** Every request
   returns 500 on `POST /workflows/process/`. Discriminated: identical with the
   MCP changes fully reverted. Different bug class, outside the packages worked
   this session. **Needs an owner.**
4. **#1998** — production stdio (`run()` → FastMCP) bypasses EVERY gate: a gated
   tool returns its full schema + `Args:` block, a `disable_tool()`'d tool
   EXECUTES with `isError=false`. `run_stdio` — where all the stdio hardening
   landed — has **ZERO production callers**. Pre-existing, architectural,
   deliberately not attempted.
5. **#2000** — eager `torch`/`sklearn` import in `src/kailash/security.py:536,595`
   costs 11.4s on first node execution.
6. **#1996 is FIXED** (`45ccac417`). Session D recorded its premise as FALSE
   after checking `nexus/transports/mcp.py` — **the wrong file**. The issue names
   `src/kailash/trust/plane/mcp_server.py:31`, which was genuinely unguarded.

## Convergence position — state it honestly

**Rounds 1–5 were ALL un-clean. The clean-round counter is at ZERO.**
`commands/redteam.md` requires TWO CONSECUTIVE clean rounds. Round 5's scope A
(the cache fix) verified correct on all five execution checks after `d8ecef1f8`,
but its scope B was never reached, so no round has completed clean end-to-end.

Do not read 25 commits of real fixes as convergence. Do not let a later session
read it that way either. `completion-criterion.md` MUST-4: a cap-stop is
abnormal termination, never "done".

## NOT DONE — and gated on the above, not on code

- **Version anchors** (kaizen 2.46.0, kaizen-agents 0.13.0, dataflow 2.20.0,
  core 2.63.0, ml 2.2.3; nexus already 2.16.0). **TRAP: `kailash-ml` keeps its
  version in `_version.py`, NOT `__init__.py`** — the obvious bump ships a split
  version state (zero-tolerance Rule 5).
- **CHANGELOGs.** NOTHING from this session is in any CHANGELOG yet. A consumer
  lane drafted the required per-package entries with semver bumps — recover them
  from the R2 consumer-lane report if you can; otherwise re-derive. Several are
  **BREAKING** (discovery fail-closed; the falsy-checker enforcement flip, which
  presents to operators as a sudden access-denial wave; the renamed log event
  `discovery.permission_check_failed_open` → `..._failed_closed`, which any
  alerting keys on).
- **PUSH** — 25 commits local. Session D ratified the push; it has not happened
  since.
- **`/release`.**

## Traps

- **`cd` PERSISTS between Bash calls in this harness.** An early `cd
packages/.../src` silently invalidated three later path checks in this session
  — they reported "file does not exist" for files that do exist. **Always use
  absolute paths**; re-`cd` to the repo root if unsure.
- **An idle/empty agent return is ZERO evidence, and you must QUERY not
  re-dispatch.** A round-5 agent returned only "I'll start by reading the
  code" after 27 tool calls; `SendMessage` to its agentId recovered the FULL
  report. Re-dispatching would have discarded it. (Session D hit this with six
  agents; it recurred here.)
- **Sub-agents spawning sub-agents lose work.** One lane's three inventory
  sub-agents were killed by an unrelated cleanup and never reported; the parent
  redid the work directly. **Tell agents not to spawn sub-agents.**
- **A syntactically-broken mutation is INERT, not a passing test.** My first
  attempt to red-test the scrub fix commented out a trailing comma → SyntaxError
  → suite never ran. That reads identically to "the test is vacuous". Always
  `ast.parse` the mutated file before reading the result.
- Disk hit **100%** mid-session (1.8Ti volume). One `Edit` failed `ENOSPC`.
  Clear `__pycache__` between long runs.
- Two agents hit account/session budget limits mid-run and were cut off. Work in
  the tree survived; work in agent context did not.
- `.venv/bin/python -m pytest` ALWAYS. `packages/kailash-kaizen` and
  `packages/kaizen-agents` **cannot** be collected in one invocation.
- `integration/nodes/test_iterative_llm_agent_real_services.py` HANGS.
  `tests/integration/mcp_server/` needs Redis on 6380. Use `--timeout=120` on
  nexus runs — one hung past 45 min without it.
- **Do NOT use a broad `pkill -f pytest`** — it killed another agent's suite.
- New credential-shaped test vectors MUST be assembled at runtime from fragments.

## Pending decisions for the co-owner

1. **Release gate.** Convergence is not met and five rounds say the trend is not
   evidence. Recommend: two clean rounds before `/release`, starting with F3.
   Con, stated honestly: that is more cycles on a branch already 25 commits deep,
   and the remaining items are MEDIUM/LOW, not the CRITICALs that justified
   rounds 1–4.
2. **The 3 nexus 500s** need an owner — outside every package touched here.
3. **Cross-SDK: prior grants EXIST but are action-scoped; this session's two
   classes need a NEW one.** Correcting an over-broad statement I made mid-session
   ("still not authorized", which implied none had ever been granted): this
   workspace holds FIVE `cross-repo-authorization-1720-*.md` receipts against the
   Rust SDK BUILD repo, and two drafts marked FILED. But
   `repo-scope-discipline.md` condition 5 scopes a grant to the NAMED action, and
   none covers this session's classes — the credential-scrubber under-redaction
   family, and the identity-vs-truthiness authz-gate family. Both recur across
   bindings; `cross-sdk-inspection.md` Rule 1 binds. Run `/cross-repo-authorize`
   for each specifically. **Do not put the private sibling's org slug in any
   public-published artifact** (`cross-sdk-inspection.md` Rule 6) — refer to it by
   role; the slug lives in the gitignored resolver + the receipts.
