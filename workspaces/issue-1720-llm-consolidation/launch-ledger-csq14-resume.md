# CSQ 14 continuation — 2026-09-26

## Live repair checkpoint — supersedes earlier statuses

Final source candidate is `15960d9478e327389413e3765e4284801b16fa8b`. Runtime controls/timer ownership,
constructor/runtime-input separation, real DataFlow transactions/cache handling,
gateway per-app authentication/resource ownership and canonical path checks are landed.
Automatic Core/DataFlow, MFA and Python exception diagnostics omit payload values;
public exception/result contracts and explicit caller-authored logging are preserved.
All substantive repair shards have two delivered scoped review rounds, reached
negative controls and retained test evidence. The latest selections include 281
runtime, 381 configuration, 403 MFA, 110 security/path and 42 Python cases. These
overlap and must not be added as a unique coverage total. Ten macOS resource-limit
skips do not cover those Linux paths. No filesystem race prevention or Windows
runtime claim is made. Completed implementation siblings are drained.

Three final reviewers will assess the full promotion union and repair interfaces
at this source; final root/DataFlow suites and every configured all-files hook,
including pytest-check, remain OPEN. Historical greens do not cover this candidate.
D1 promotion approval persists. PR #2229 remains at `ce4c9de67` until those gates pass.
Nine proposed CodeQL dismissals await explicit approval; none was executed.
Exact-head required checks and previously failing jobs must succeed before a
separate merge operation. Three post-main union/tree-parity reviews remain due.
Five stashes and 52 uncertain historical refs remain held. Package publishing,
owner acceptance and whole-forest completion are not authorized or claimed.


## Current continuation checkpoint — supersedes historical gate states

Primary dev: `51fcd96c003587ce6ca16ba56cde799e135850b4`. Content failure, DataFlow utility/options,
gateway sibling ownership and safe logging are now landed. Individual review
receipts, frozen hashes and validation scope are retained in
`04-validate/csq14-active-repair-checkpoint.json`.

A bounded follow-on shard repairs the actual compatibility-wrapper option drop:
`fix/csq14-runtime-option-forwarding`, sibling `csq14-runtime-forwarding`, owner
`archive_checkpoint`. The orchestrator created it at e7c1085 before dispatch;
the prompt mandates resolved-root/branch assertions and concrete report-back.
Supported canonical options must be forwarded; non-None unsupported controls
must fail before execution. No new runtime engine is authorized by this shard.

The nine CodeQL dispositions remain proposals pending explicit approval. D1
promotion approval persists; package publishing remains unauthorized. The final
all-files hook obligation is OPEN, including pytest-check; individual commit
skips do not discharge it. Final whole-union reviews and exact-head successful
remote checks are also OPEN. Five stashes and uncertain historical refs remain
held. No forest-completion or owner-acceptance claim is made.

Recovered parent thread: `01a0d8a0-e67b-7dc2-8628-1e1bfbbd3eca`.
Source checkpoint: `709759a385ae5950fdeab2eda739718dddfb75e3`.
Prior user approval for D1 and the advisory-type exception was read from
thread `01a0d7ea-e2a1-74b3-8af2-2a47dc410525`; it remains in force.

| Lane | Branch | Task set | Agent roster | Status |
| --- | --- | --- | --- | --- |
| ML gate | `fix/csq14-ml-seed` | Diagnose failed seed unit test; preserve independent opt-outs; bounded ML gate and controls | `/root/ml_gate_recovery`: committing; `/root/ml_correctness_review`: two clean rounds; `/root/archive_checkpoint`: two clean adversarial rounds | Landed `6fa357a1b`; branch and sibling removed |
| Archive evidence | `docs/csq14-archive-recovery` | Recover five temporary reports; verify historical receipts and 52-ref inventory; retain unresolved scope | `/root/archive_checkpoint`: delivered; `/root/ml_correctness_review`: independent verification | Landed `6d5e34e35`; branch and sibling removed |
| Integration | `dev` | Recover completed gate result; exact-head promotion checks; land and drain completed lanes | `/root`: coordinating | All implementation lanes drained; full configured hooks passed; promotion checks next |

Sibling root: `/Users/esperie/repos/kailash/build/.kailash-py-wt/`.
Both dispatched lanes received a mandatory resolved-root/branch assertion.
No lane may push, merge, delete archive refs, or modify the five held stashes.

## Recovered gate outcome

`/tmp/kailash-csq13-final-delta-gate.log` ended with
`[trestle-remote-run] exit=1 command wall=404.3s host=esperie-ai`.
The earlier handoff's pending Core and hook checks actually completed:
`FINAL_DELTA_STEP core_tier1_exact exit=0` and
`FINAL_DELTA_STEP full_hooks exit=0`. Core reported
`5371 passed, 5 skipped, 3 deselected, 6 xfailed, 5 xpassed`.
Those exclusions do not certify their paths.

The remaining failure was
`test_torch_deterministic_false_when_torch_opted_out`, with
`Failed: Timeout (>30.0s)` while importing `pytorch_lightning`.
The bounded ML selection reported `1 failed, 235 passed`.
This is recovered evidence, not a newly executed test run.

## Live inventory at recovery

After fetching origin: `dev` and `origin/dev` both at `709759a38`;
`main` and `origin/main` at `50f98afe4`; PR #2229 still open at
`28602f1a0` on `promote/2026-09-11-cont30`.
Before dispatch, only the primary checkout remained. The two sibling trees
above were created by this continuation and must be drained after completion.
Five stashes remain held. No historical archive ref was deleted.

Required main checks read from branch protection: `CodeQL`, `Analyze Python`,
and `test-with-infrastructure`. All previously failing test jobs must also
succeed on the final promotion head. Read evidence and merge remain separate
operations. Package publication is outside D1.

## Final gate obligation

The ML lane may skip only `pytest-check` on its local commit, documenting the
bypass and this follow-up in the commit body. The orchestrator must run the
complete configured all-files hooks, including `pytest-check`, before the
consolidated promotion push. This preserves the existing final-gate obligation
without repeating the Core suite at every lane checkpoint. No skipped hook is
represented as having passed.

Obligation discharged: full configured all-files hooks including `pytest-check` passed
at `fe791935c`; `git diff --exit-code` passed. See `04-validate/csq14-final-hooks-receipt.json`.
Only evidence/continuity documents changed after that gate.

## New repair dispatch after refreshed CI

 (head ce4c9de67)

DataFlow unit job: 3 failed, 3469 passed, 31 skipped, 56 warnings.
Root regression job: 3 failed, 3000 passed, 4 skipped, 24 deselected, 64 warnings.
Other completed workflows pass; CodeQL still pending at observation. No merge yet.

| Active lane | Agent | Branch / sibling suffix | Scope |
| --- | --- | --- | --- |
| D1 | ml_gate_recovery | fix/csq14-dataflow-gate / csq14-dataflow-gate | Constructor fixture, configuration, expected warnings |
| D2 | archive_checkpoint | test/csq14-dataflow-lifecycle / csq14-dataflow-lifecycle | Coroutine rejection cleanup, lifecycle fixtures |
| R1 | ml_correctness_review | fix/csq14-root-regression / csq14-root-regression | Capability producer inventory and proxy assertion contracts |

All siblings under /Users/esperie/repos/kailash/build/.kailash-py-wt/.
Root owns test dependency declaration and remaining root-regression warning triage.
Every new repair needs negative controls, reviews, local parity, then a consolidated push.

R2 active: ml_gate_recovery now also owns frozen-D1-independent six-file root warning repair in sibling csq14-root-warning-contracts, branch test/csq14-root-warning-contracts. R1 additionally owns compatible aiohttp typed request-key migration across all three success paths. Four active siblings; three agents. CodeQL passed; two test jobs remain blockers.

Final-hook obligation reopened for refreshed CI repairs. Per-commit pytest-check may be skipped only with explicit body receipt; rerun complete all-files hooks including pytest-check before nextpromotionpush. D3 regression fixture cleanup active in sibling csq14-dataflow-regression-cleanup, branch test/csq14-dataflow-regression-cleanup, ml_correctness_review owns; original CI DataFlow regression812passed,6skipped,181deselected, but stricter warning run exposed caller-ownedruntime leaks now underrepair.

## Final source freeze and holistic dispatch

Allfive CI-repair implementationlanes landed through13687209e and drained.
Three detachedsiblingscsq14-holistic-correctness/security/coverage created byroot
at13687209e beforedispatch; eachprompt requiresresolvedSTEP0 andsourcepin.
Agents respectivelyml_gate_recovery/archive_checkpoint/ml_correctness_review.
Each reviews thewhole ce4c9de67...13687209e union with absoluteAST/grepsweeps
and boundedactualnegativecontrols; no latestshardonlyreview. Parent final
CIselections running; all-filehookobligation remainsopen beforepush.

## Final corrections landed; CodeQL investigation

The source import scanner now prunes vendor descendants relative to each source root,
then uses a Unicode-aware candidate filter before semantic AST checks. The independent
reference covered the same 4,866 files; scan time decreased from 26.306s to 4.286s.
Commit 7c85f6a2e, merge 78b3a35fb; two clean review rounds and five reached mutations.

The optional aiohttp import guard names `pip install 'kailash[server]'` and chains the
missing-module cause. Commit a1ba6c826; 13 strict tests, source-origin opposite control,
and two independent clean rounds. No scanner allowlist changed.

The bridge deadline rejects non-finite, non-positive, unrepresentable, or unsupported
bounds before runtime resources are acquired. Supported int/float values normalize once
to float; None remains unbounded. Commit c8b2377fb, merge 8f77625056e37ffd993d803a3cddd473408e0a08.
23 strict tests, five reached admission mutations, actual public-path timeout forwarding
mutation, and two independent correctness/security rounds passed.

Integrated gate at 13687209e: DataFlow 3,484 unit passes / 31 skips; 812 regression
passes / 6 skips / 181 deselections. Root: 3,017 passes, two failures, 3 skips,
24 deselections; the import scan timeout and optional import failure are repaired above.
These skips and deselections are not coverage. Full root rerun is active at 8f77625056e37ffd993d803a3cddd473408e0a08.

CodeQL check 108304848821 failed on ce4c9de67 with "265 new alerts including 10 high
severity security vulnerabilities". This is the scanner's report, not a confirmed exploit
count. Current analysis 1842994026 has 2,253 results; previous 1838845444 has three.
Exact membership and dispositions are being independently verified. No new alert dismissal
is authorized. The prior scoped approvals cover 11587, 11588, and 11594 only.

All-files hooks, including pytest-check, remain required before the next push. The attempted
`mac-mini` runner was rejected before execution; the corrected declared host is
`esperie-mac-mini`. Never count the rejected launch as a gate run.
