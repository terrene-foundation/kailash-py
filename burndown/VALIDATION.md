# Census validation receipt — 2026-09-25

Source commit: `bb4129bf6`. These checks cover data completeness and generator behavior; they do not certify issue fixes, owner acceptance, code security, or package releases.

- Frozen ISSUE IDs exactly equal the root session baseline ID set. Removing ISSUE-2251 from the expected set makes equality false, establishing the mismatch pole. Current body/comment capture matched that original set; no IDs were silently removed.
- `node .claude/bin/burndown-build.mjs --selftest` exited 0 and printed `SELFTEST OK`: differing fixture inputs produce differing blocks; canonical tokens validate while changed value/denominator/bucket tokens are rejected.
- After committing sources, `--write` exited 0 and `--check` printed `block in burndown/REGISTER.md is current.`
- On this manifest, `--quote 'GitHub issues/Open'` followed by `--verify-quote` exited 0 with `all valid`. Increasing the quoted value while retaining its token caused exit 1 with `INVALID QUOTE` and `surrounding text contradicts token`. This is the real-register negative control, separate from the generator fixtures.
- Receipt ancestry was checked against the frozen dev SHA recorded in REGISTER.md; an absent issue-2238 follow-up commit produced exit 1 under the same instrument. Reachability is not acceptance.

The first attempted quote used the incomplete selector `Open` and was refused with exit 2. No evidence was banked from that invocation; the documentation now gives the required qualified selector.

Normal pre-commit remains unrun because its attempted invocation died of signal 11. The documented bypass and F25 follow-up are in TRIAGE.md and commit bodies. The default interpreter also returned exit 139; system Python ran the source-generation and baseline checks. Node ran the generator checks locally; this short data-validation workload did not require trestle offload. Expensive runtime verification remains for the specialist lanes through `trestle run --`.

Independent manifest/disposition review is still owed. No new runtime conclusions about #2248/#2249, no external issue changes, and no Signed off transitions were made.
