# CSQ 14 continuation — 2026-09-26

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
