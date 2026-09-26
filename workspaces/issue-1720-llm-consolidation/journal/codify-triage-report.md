# /codify triage — 18 pending journal candidates

Date: 2026-09-12. Repo: kailash-py (BUILD), branch `dev`. Lane: read-only triage.
Source dir: `workspaces/issue-1720-llm-consolidation/journal/.pending/`

Every one of the 18 `source_commit` SHAs was confirmed an ancestor of `dev`
(`git merge-base --is-ancestor <sha> dev`, 18/18 ON-DEV). So no candidate describes
unlanded work; the question for each is only whether its *lesson* is already durable
and whether its *framing* is still true.

---

## FLAGGED FIRST — genuinely open items (actionable work, NOT codification material)

### 1. Issue #2084 is STALE-OPEN: the defect is fixed, the issue record is not

Candidate `1789051497620-0-RISK.md` records "#2084 is OPEN despite PR #2101 having
merged — a drain lane reported it closed, and the issue state contradicts that."
**Both halves verified true today, and the correct disposition is `gh issue close`, not a re-fix.**

- Code: `packages/kailash-kaizen/src/kaizen/smart_defaults.py:322-489` —
  `create_observability` now calls `hook_manager.register_hook(...)` 4× (measured:
  `awk 'NR>=322 && NR<=520' … | grep -c 'register_hook\|add_hook'` → `4`). The
  docstring names the defect by number: *"an enabled flag that installs nothing is
  the exact defect #2084 records"*. **Beware**: `packages/kailash-kaizen/build/lib/kaizen/smart_defaults.py`
  is a stale build artifact carrying the same text — read `src/`, not `build/lib/`
  (`instrument-discipline.md` MUST-4: the file you read fixes what question you answered).
- Issue: `gh issue view 2084 --json state,closedAt` → `{"closedAt":null,"state":"OPEN"}`,
  last touched 2026-09-10. Its final comment ("Correction: this reopening checked for
  the wrong artifact") already establishes the fix is real on `dev` and that the
  reopening evidence belonged to an abandoned branch (`refs/archive/2026-08-21/...`).
- **Action:** close #2084 citing `5c3d98558` (PR #2101) per `git.md` § Discipline
  ("issue closure MUST include a commit SHA / PR number"). The residual it spawned,
  #2219, is separately filed.

### 2. #2135 — kailash-align has no GPU-hardware test coverage (OPEN, tracked)

From candidate `1786805625965-0-DECISION.md`: the `test-gpu` job was DELETED rather
than fixed, because `gpu` was registered but applied to zero tests. Verified:
`.github/workflows/test-kailash-align.yml:152` carries the removal note; `gh issue
view 2135` → OPEN. This is a real, deliberately-accepted coverage gap with an owner
issue — not a codification item, but it belongs on the work board, not in a journal.

### 3. Nothing else is live

Every other open-problem framing in the 18 is now **stale** (see per-candidate detail):
the compact-JSON over-redaction BUG is fixed, the third scrubber is routed through the
shared module, the fail-open authorization trade has been ratified fail-CLOSED, the
release-version decision is moot (versions moved), and #2003 / #2005 / #2007 / #2013 /
#2074 / #2076 / #2112 / #2149 / #2152 / #1974 / #1896 are all CLOSED.

---

## Verdict table

| file | type | one-line subject | verdict | evidence |
| --- | --- | --- | --- | --- |
| `1785811104891-0-DECISION.md` | DECISION | 2026-08-04 sweep: release blocked on a version decision; 4 open items | **DELETE** | all 4 items resolved — `credential_scrub.py:951-957` carries the JSON fence; kaizen at `2.46.1`; `pyproject.toml:128` pins `mcp[cli]>=1.23.0,<3.0` |
| `1785824470055-0-DECISION.md` | DECISION | the DOCUMENTED permission checker never worked at all | **FOLD-INTO `.claude/rules/testing.md`** | fix landed (`discovery.py:1302-1313`); fail-open pin since REPLACED by `TestErrorPathFailsClosed`; the *fixture* lesson is uncodified |
| `1785824470056-1-DISCOVERY.md` | DISCOVERY | a THIRD credential scrubber exists, on a logging path | **DELETE** | residual FIXED in `358637785`; all three items now durable as source comments (`redaction.py:40-61`, `credential_scrub.py:88-94`) |
| `1785824470056-2-RISK.md` | RISK | residual list incomplete; placeholder guard predated the fence | **DELETE** | durable at `credential_scrub.py:837-845` + `tests/regression/test_issue_1974e_compact_json_over_redaction.py:501-518` |
| `1785937047916-0-RISK.md` | RISK | session D's release recommendation is refuted, and why | **DELETE** | `completion-criterion.md` MUST-4 + `commands/redteam.md:142` codify it verbatim ("the instrument ROTATES", cap = abnormal termination) |
| `1786237828906-0-DECISION.md` | DECISION | session-I wrapup — ledger reconciled, clean round in flight | **DELETE** | status note; delivery lesson now `agents.md` § Agent-Result-Delivery + `skills/30-claude-code-patterns/agent-result-delivery.md` |
| `1786237828906-1-DECISION.md` | DECISION | session-I decision report — nothing at risk, convergence outstanding | **DELETE** | status note; #2003/#2005 CLOSED; piped-`$?` covered by `guides/rule-extracts/instrument-discipline.md:27,39` |
| `1786256413552-0-DISCOVERY.md` | DISCOVERY | teach the sink scanner the extra-dict shape it could not see | **DELETE** | `verification-gate-integrity.md` MUST-1 + `instrument-bipolarity.md` MUST-1 own the pattern |
| `1786256413565-1-DECISION.md` | DECISION | round 2 — the cleanup fix re-opened the defect it closed | **FOLD-INTO `.claude/rules/patterns.md`** | fix landed (`channels/base.py:401-443`); `patterns.md` has ZERO cancellation/`finally` coverage (grep: 0 hits) |
| `1786256413566-2-DISCOVERY.md` | DISCOVERY | the F11 idiom survived in the fabric nexus adapter | **DELETE** | landed at `dataflow/fabric/nexus_adapter.py:58,122`; both lessons covered (see detail) |
| `1786256413567-3-DISCOVERY.md` | DISCOVERY | three defects the integration round found in its own work | **DELETE** | `secure_logging.py:635-700` carries the full lesson in-source; async half duplicates the FOLD above |
| `1786321079489-0-DECISION.md` | DECISION | session-M sweep + wrapup; CI 3 red → 1; PCF triage of 22 | **DELETE** | status note; its methodological finding is `guides/rule-extracts/security.md:241-263` |
| `1786321079490-1-DISCOVERY.md` | DISCOVERY | correct two claims of mine that a late review refuted | **FOLD-INTO `.claude/rules/verify-claims-before-write.md`** | item 1 (selective omission from a cited run) has no covering clause; item 2 is covered |
| `1786321079491-2-DISCOVERY.md` | DISCOVERY | teach the THIRD scheme classifier the `file:` form | **DELETE** | fix + enumeration test landed (`tests/regression/test_issue_1971_detect_database_type_fail_closed.py:489-551`); mechanism codified in ESP extract |
| `1786805625965-0-DECISION.md` | DECISION | repair five zero-match pytest selectors (#2076) | **DELETE** | `verification-gate-integrity.md` MUST-1/2/3(b) predate it (landed 2026-08-11) |
| `1786805625965-1-DISCOVERY.md` | DISCOVERY | wire kailash-kaizen `tests/regression/` into CI (#2074) | **DELETE** | `verification-gate-integrity.md` MUST-3(b) is the clause, near-verbatim |
| `1786805625966-2-DECISION.md` | DECISION | gate the eighth un-gated HTTP server (#2112) | **FOLD-INTO `.claude/skills/18-security-patterns/`** (low priority) | fix landed (`workflow_connection_pool.py:321-323,1151-1164`); ESP covers it, the transport-class nuance is a worthwhile worked example |
| `1789051497620-0-RISK.md` | RISK | cont-28 — 2.64.0 released, advisory published | **DELETE** (but see FLAG 1) | all three self-corrections are the `verify-claims-before-write.md` MUST-2(b) shape; only #2084 is actionable |

**Counts: PROMOTE 0 · FOLD 4 · DELETE 14 · UNRESOLVED 0.**

---

## Duplicate groups

These candidates are not independent; several stem from one work arc and should be
dispositioned together.

- **Group A — the #1720 / #1974 credential-scrub arc** (candidates 1, 3, 4):
  `1785811104891-0-DECISION`, `1785824470056-1-DISCOVERY`, `1785824470056-2-RISK`.
  One module (`kaizen/utils/credential_scrub.py`), three rotated-lens rounds. Every
  finding from all three has since been either fixed in code or written into the
  module's own comments. Delete as a group.
- **Group B — session status reports** (candidates 6, 7, 12, 18):
  `1786237828906-0`, `1786237828906-1`, `1786321079489-0`, `1789051497620-0`.
  These are `/sweep` + `/wrapup` outputs auto-captured because the commit subject
  matched the journal-worthy pattern. They are *pointer files about pointer files* —
  the wrapup contract (`session-notes-continuity.md`) already owns this content, and
  their decision points (#2003/#2005/#2007/#2013) are all CLOSED. Delete as a group.
- **Group C — the F11/F13 integration round** (candidates 9, 11):
  `1786256413565-1-DECISION`, `1786256413567-3-DISCOVERY`. Same session, same
  `Channel._cleanup` root cause, described twice from two angles. FOLD once (via 9),
  delete 11.
- **Group D — the "Nth independent surface" family** (candidates 3, 13, 14, 17):
  a third scrubber, a third classifier, an eighth HTTP server, and the meta-note
  about why self-chosen consistency checks miss them. They are FOUR INSTANCES OF ONE
  CLASS, and that class is already codified — see "Already covered" below. Only the
  transport-enumeration nuance (17) is worth adding as an example.
- **Group E — CI coverage vacuums** (candidates 15, 16): `1786805625965-0`,
  `1786805625965-1`. Both are instances of `verification-gate-integrity.md` MUST-3(b),
  which landed 2026-08-11 — *four days before* these commits. Delete both.

---

## PROMOTE / FOLD detail

### FOLD 1 → `.claude/rules/testing.md` (highest value)
**Candidate:** `1785824470055-0-DECISION.md` (`ca8aaad74840`)

**Lesson:** When a collaborator is injected by duck-type, every test supplying its own
bespoke stub written to match the *call site* makes the call-shape contract
untestable — code and fixture are consistently wrong together, so a documented
integration can be broken since inception and green forever. At least one test MUST
exercise the REAL declared type (or assert against its `inspect.signature`), not only
a hand-rolled double.

**Evidence it is real and uncovered:**
- The defect: `UserFilteredAgentDiscovery` documented its checker as `TrustOperations`,
  whose real signature takes no `user_id`/`organization_id`; the call site passed both,
  so the documented integration raised `TypeError` on the first agent of every call,
  the `except Exception` handler caught it, and **it became a GRANT** — steady state,
  not a window. Established by `inspect.signature`, not by reading.
- It had **recurred on the same branch** ("the same shape as the routing fixture fixed
  earlier"), which is the pattern-not-incident threshold.
- Nearest existing clause is `rules/testing.md:240` (unit fixtures "construct fixtures
  with exactly the fields THAT primitive needs — they cannot observe a field MISSING
  from the A→B handoff"). That is the *field-shape* sibling; the *call-shape / declared-type*
  half is absent. Greps for `duck-typed`, `fixture agreed`, `inspect.signature` across
  `.claude/{rules,skills,guides}` return zero hits (control: the same grep form returns
  hits for `Enforcement-Surface Parity`).

**Note for the folder:** the candidate's own framing is now STALE in one respect and
must not be carried over — it says the `except Exception` fail-OPEN path was
"DELIBERATELY NOT CHANGED" and pinned by `test_error_path_still_fails_open`. That pin
was deleted and replaced: `packages/kaizen-agents/tests/regression/test_discovery_documented_checker_works.py:221-232`
reads *"The RATIFIED posture flip: a checker that raised has not approved. This class
replaces `test_error_path_still_fails_open` … It was deleted in the commit that made
the flip."* Fold the fixture lesson; drop the open-trade framing.

### FOLD 2 → `.claude/rules/patterns.md`
**Candidates:** `1786256413565-1-DECISION.md` (`c3cf5069c11d`) + the third item of
`1786256413567-3-DISCOVERY.md` (`dcbf1db06c04`)

**Lesson:** `await <task>` inside a `finally` is two defects at once — it never returns
when the task ignores cancellation (stranding the caller), and it RE-RAISES whatever the
task died of, which inside a `finally` REPLACES the propagating `CancelledError` and
demotes it to `__context__`, losing the cancellation silently. Use
`asyncio.wait({task}, timeout=…)`: `cancel()` is synchronous and has already landed, so
only the CONFIRMATION is bounded. Corollary from the same round: a cleanup added to
`stop()` cancels a DIFFERENT task than the one being awaited, so "I fixed the strand"
must name WHICH task.

**Why `patterns.md`:** it is the file that already owns the SDK's async/threading
disciplines (journal `0001` landed the fire-and-forget shadow MUST there), it is
path-scoped `**/*.py` so it costs no baseline budget, and a grep for
`cancel|finally|asyncio.wait|await.*task` in `rules/patterns.md` returns **zero hits** —
there is no cancellation coverage at all today. The shipped fix and its full reasoning
are already in-source at `src/kailash/channels/base.py:401-443` (plus
`cli_channel.py:358-366`, `api_channel.py:311-319`), so the rule clause can be compact
and point at them.

### FOLD 3 → `.claude/rules/verify-claims-before-write.md` (MUST-2 extension)
**Candidate:** `1786321079490-1-DISCOVERY.md` (`58d4b1629abe`), item 1

**Lesson:** Citing a test run by omitting its failures — even when every omitted failure
carries a believed-correct benign attribution — makes a RED run read GREEN in a durable
artifact. Attribution licenses an *explanation*, never a *deletion*: cite the run's full
verdict line, then attribute.

**Evidence it is uncovered:** the commit cited *"Verified … 717 passed, 176 deselected"*
when the actual run was *"2 failed, 717 passed, 1 skipped, 176 deselected"*; the two
failures were a real local-vs-pinned pyright skew and that attribution held — *"the
attribution was right; the presentation was not."* The closest clauses govern
**truncation** (`verify-claims-before-write.md` MUST-2(b): "`tail -N` / `head -N` … over
the line carrying the cited value silently drops the datum") and **over-claiming**
(`git.md` § Discipline, commit bodies describing only what is in the diff). Neither
reaches *deliberate selective omission of a known datum*. Greps for `omitting them`,
`RED run read GREEN`, `partial citation` return zero hits.

Item 2 of the same candidate (the false "restores enforcement-surface parity" claim)
is already covered — see "Already covered" #2 — and needs no fold.

### FOLD 4 → `.claude/skills/18-security-patterns/` (low priority, worked example only)
**Candidate:** `1786805625966-2-DECISION.md` (`242e9dc34cab`)

**Lesson:** When enumerating surfaces for an Enforcement-Surface-Parity sweep, enumerate
by what BINDS A SOCKET, not by what a framework middleware hook reaches.
`ConnectionDashboardNode` was invisible to the #2072/#2100 sweeps purely because it is
aiohttp and not ASGI — `install_server_auth_middleware` calls Starlette's
`add_middleware`, which an aiohttp app does not have. It ranked ABOVE the seventh
surface because two of its routes MUTATE (`POST`/`DELETE /api/alerts`): an anonymous
caller could delete the rule that would have paged an operator.

The rule itself (`security.md` § Enforcement-Surface Parity) already mandates the
behaviour and its extract already carries the "enumerate ALL validators" detection
recipe; this is an *example*, not a new MUST. The fix is landed and self-documenting
(`src/kailash/nodes/data/workflow_connection_pool.py:321-323,1151-1164`;
`src/kailash/visualization/api.py:177-265`). Fold or drop at the codifier's discretion —
it does not block.

---

## DELETE detail — what already covers each

1. **`1785811104891-0-DECISION.md`** — a point-in-time release-gate status report, and
   all four of its items are now closed:
   - *compact-JSON over-redaction in `_URL_WITH_AUTH`* — FIXED. The fence the candidate
     proposed ("exclude JSON structural chars from the userinfo classes") is present:
     `credential_scrub.py:951-957` reads `(?:(?!"[,}\]:])[^\s]){0,256}`. Provenance
     `91e9215b1` / `0fce89856`; issue #1974 CLOSED; pinned by
     `tests/regression/test_issue_1974e_compact_json_over_redaction.py`.
   - *kaizen MINOR-for-breaking at 2.45.0* — moot; `packages/kailash-kaizen/pyproject.toml:7`
     is `2.46.1`, root is `2.65.0`, kaizen-agents `0.13.0`.
   - *MCP stack undeclared* — DECLARED: `pyproject.toml:128` → `mcp = ["mcp[cli]>=1.23.0,<3.0"]`,
     with an in-file comment recording the uncapped-pin incident that pulled mcp 2.0.0.
   - *three session traps* — all covered (see 5, 6, 7 below).
2. **`1785824470056-1-DISCOVERY.md`** — the residual it escalated is FIXED:
   `358637785 fix(kaizen): route the THIRD credential scrubber through the shared module`.
   `core/autonomy/hooks/security/redaction.py:14` now imports `scrub_credentials` and
   runs it FIRST; lines 40-61 record the 9-of-10 vendor-shape drift and the scope split
   verbatim. Item (B) (unbounded quantifiers / deterministic split point) is documented
   at `credential_scrub.py:960-985`. Item (C) (three underscore-prefixed patterns as
   de-facto public API) is documented at `credential_scrub.py:88-94`, recorded-not-renamed
   exactly as proposed. Item "INSTRUMENT #9" (a drift probe that read patterns via
   `vars(module)` and found zero, then measured 10/10 drift from an empty set) is the
   textbook `instrument-discipline.md` MUST-3(a) failure and is in that rule's own
   extract table. Nothing left to promote.
3. **`1785824470056-2-RISK.md`** — both items durable. The residual family is enumerated
   in-source at `credential_scrub.py:837-845` (scheme-less / scheme-relative / `%40`),
   with the same INSIDE-vs-OUTSIDE-coverage adjudication the candidate describes, and
   the `%40` member is pinned in
   `tests/regression/test_issue_1974e_compact_json_over_redaction.py:501-518`. The
   placeholder-guard fix is landed. Its meta-lesson ("fix where a check can be true;
   document where it would have to be false") is a good line but is a restatement of
   `instrument-bipolarity.md` MUST-3 (a check whose poles cannot be built is ADVISORY
   and MUST NOT gate).
4. **`1785937047916-0-RISK.md`** — the headline lesson is codified almost word-for-word.
   `rules/completion-criterion.md` MUST-4: *"A 2–5 round cap is a runaway guard: hitting
   it is ABNORMAL TERMINATION, reported as such, never 'done' … The instrument MUST
   rotate between rounds … repeating one lens draws against the residue that lens
   already filtered."* MUST-5 adds that security/trust-bearing surfaces run the **full
   loop, UNCAPPED**. `commands/redteam.md:142` restates it at the gate. The three harness
   traps are likewise covered: *query-don't-re-dispatch* → `agents.md` § "A Dispatched
   Agent's Result Is Not Received Until It Is DELIVERED" (3) RECOVERY + the depth skill
   `agent-result-delivery.md:89-139`; *a syntactically-broken mutation is inert, not a
   vacuous test* → `instrument-discipline.md` MUST-2(b) and `instrument-bipolarity.md`
   § MUST NOT ("Read a non-reddening mutation as vacuity when it stayed inside the blind
   spot"). Only *"`cd` persists between Bash calls"* has no rule hit — and it is
   CLI-harness trivia already stated in the agent system prompt, not a codifiable pattern.
5. **`1786237828906-0-DECISION.md`** — wrapup pointer. Its one load-bearing finding
   ("agents complete their work and write the report as assistant text without sending
   it — the failure is DELIVERY, not execution, so query, never re-dispatch") is now a
   MUST in `agents.md` with clause-scoped Trust-Posture Wiring and a shipped PreToolUse
   detector (`hooks/lib/dispatch-contract.js::detectNamedDispatchWithoutDelivery`).
   Promoting the candidate would duplicate a rule that already has teeth.
6. **`1786237828906-1-DECISION.md`** — decision report. Decision A/B/C all resolved:
   #2013, #2003, #2005 are CLOSED. The one reusable line — *"a piped push reports the
   pipe's status, which is how a rejected push once read as success here"* — is in
   `guides/rule-extracts/instrument-discipline.md:27` (the `${PIPESTATUS[0]}` row) and
   :39 (§ "The shell reports the LAST stage, not the one you meant", with DO/DO-NOT and
   a BLOCKED corpus).
7. **`1786256413552-0-DISCOVERY.md`** — the "sweep the SCANNER with planted shapes, not
   just the code" discipline is `verification-gate-integrity.md` MUST-1 ("A Gate Ships
   With A Negative Control That Runs Where The Gate Runs") and `instrument-bipolarity.md`
   MUST-1 (executable pole pair, verdicts must DIFFER). The candidate's own
   self-correction — a first predicate that counted any bare name and returned 71 — is
   `instrument-discipline.md` MUST-3(b) (read the hits, not the tally). Four-polarity
   verification is exactly the bipolar-pair shape both rules mandate.
8. **`1786256413566-2-DISCOVERY.md`** — the fix is landed
   (`dataflow/fabric/nexus_adapter.py:58` imports the shared
   `kailash.utils.secure_logging.safe_callable_name`; `:122` uses it), and both lessons
   are covered: *a security helper duplicated per package is guaranteed to drift* →
   `security.md` § Credential Decode Helpers ("MUST live in that SAME module; per-adapter
   copies are BLOCKED") + `skills/18-security-patterns/multi-site-kwarg-plumbing.md`;
   *taking the helper moves the dependency floor because the import is module-scope* →
   journal `0003-DISCOVERY-release-hazards-1779.md` Hazard 1, already committed in this
   same workspace. The record-correction to `8ea48617b` is a `git.md` § Discipline
   follow-up-not-amend instance, correctly executed.
9. **`1786256413567-3-DISCOVERY.md`** — its `safe_callable_name` half is now the most
   thoroughly self-documenting function in the tree: `src/kailash/utils/secure_logging.py:635-700`
   carries the eager-`getattr`-default explanation, the lazy-proxy escape, the
   `Exception`-not-`BaseException` choice, AND a later measured correction of its own
   earlier claim ("An earlier version of item 3 said a class name 'cannot carry a caller
   payload'. That is FALSE and was measured false"). Its `visualization/api.py` half is
   #2112, CLOSED. Its test half — *"asyncio.shield does not make a task ignore
   cancellation … Red for the wrong reason is not evidence"* — is
   `instrument-bipolarity.md` MUST-2 (the red pole names a failure IDENTITY, never a
   quantity) and appears in that rule's extract sub-class table as "A red for the wrong
   reason". Its channel half duplicates FOLD 2.
10. **`1786321079489-0-DECISION.md`** — a `/sweep` + `/wrapup` status report. Its
    methodological headline — *"a consistency check across a set you CHOSE cannot
    discover a member you left out"* — is already the documented state of the art at
    `guides/rule-extracts/security.md:241-263`, § "The clause asks for something a human
    does not reliably do" / § "The mechanism": *"Collapse the surfaces onto ONE shared
    function … then add a test that ENUMERATES the surfaces and fails when a new one
    re-derives the decision locally."* That extract even carries the same
    caught-while-fixing-a-violation-of-this-very-clause evidence.
11. **`1786321079491-2-DISCOVERY.md`** — fix landed AND the structural remedy landed.
    `packages/kailash-dataflow/tests/regression/test_issue_1971_detect_database_type_fail_closed.py:489-551`
    defines `_independent_scheme_classifiers()` and
    `test_every_independent_classifier_maps_the_file_uri_form_to_sqlite`, with the
    comment *"so an independent ladder added later fails here instead of being found by
    review"* — precisely the enumeration test the ESP extract prescribes. The candidate's
    reasoning is also already quoted against `security.md` § Enforcement-Surface Parity
    in its own commit body. Promoting it would be a third copy.
12. **`1786805625965-0-DECISION.md`** — landed (`pyproject.toml:256-257` registers `dl`
    and `cuda`; `test-kailash-ml.yml:247,317`; `test-kailash-align.yml:152`). The lesson
    *"a selector that can only ever match nothing is a stub gate; remove rather than ship
    degraded"* is `verification-gate-integrity.md` MUST-1 + MUST-2 ("Absence Of A Result
    Is Not A Pass") and its § MUST NOT bullet "Silence a chronically-red gate instead of
    fixing or re-scoping it". That rule landed 2026-08-11, four days BEFORE this commit —
    this is an application of it, not a new lesson. `#2076` CLOSED; the one residual
    (`#2135`) is FLAGGED above.
13. **`1786805625965-1-DISCOVERY.md`** — landed (`test-kailash-kaizen.yml:23,78-95`).
    The lesson is `verification-gate-integrity.md` MUST-3(b) near-verbatim: *"every
    verification target that EXISTS MUST be named by an invocation that runs it, checked
    against the authoritative target list — a target no invocation names advertises
    coverage that has never executed once."* The secondary lesson (`grep -c "^def test_"`
    undercounts parametrized cases and nested-class methods; real count 1654 vs the
    issue's 855) is `instrument-discipline.md` MUST-3(b) (read the hits, and know what a
    count COUNTS). #2074, #2152 and #2149 — the residues this work spawned — are all CLOSED.
14. **`1789051497620-0-RISK.md`** — its three self-corrections are one shape, already
    codified: reading 97 lines of a 570-line section; comparing declared versions to PyPI
    which cannot see an unreleased bump; anchoring a diff at the core tag instead of the
    package's own bump. All three are `verify-claims-before-write.md` MUST-2 (truncated
    output and context-boundary reconstructions are "presumed false until re-verified")
    and `instrument-discipline.md` MUST-4 (an instrument is scoped to the question it was
    BUILT for; the version-vs-PyPI comparison is a textbook wrong-question instrument).
    Its ONE non-redundant datum is the #2084 state contradiction — FLAGGED above as work,
    not codification.

---

## Method / instrument notes (per `instrument-discipline.md`)

- **Ancestry:** `git merge-base --is-ancestor <sha> dev` per candidate. This
  discriminates — it returns non-zero for a SHA not on `dev`, which is why the 18/18
  ON-DEV result is readable rather than vacuous.
- **Grep controls:** every "no coverage" claim was preceded by firing the identical
  grep form at a known-answer case (`grep -rni --include='*.md' "Enforcement-Surface
  Parity" rules/` → 3 hits; `grep -rni --include='*.md' "consecutive clean" rules/
  skills/ guides/` → 4 hits). An early run used an unquoted `--include=*.md` under zsh
  and failed with `no matches found` rather than returning empty — that run is NOT
  cited anywhere above, because a shell error and a true negative are indistinguishable
  in effect and opposite in meaning (`evidence-first-claims.md` MUST-3).
- **Hits, not tallies:** every "already covered" claim names a file and quotes the
  covering line, per the task's own bar.
- **One scope error caught mid-audit and corrected:** the first read of
  `create_observability` resolved to `packages/kailash-kaizen/build/lib/...`, a stale
  build artifact, not `src/`. The verdict happened to be the same in both, which is
  exactly why it was worth catching — a plausible answer from the wrong file is
  invisible at read time (`instrument-discipline.md` MUST-4).
- **Not measured:** no test suite was run and no probe dispatched; this is a read-only
  triage. Claims above are about artifact CONTENT and issue STATE, not about whether
  any suite currently passes.
