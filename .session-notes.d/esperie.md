# CSQ 14 continuation — final promotion gate, 2026-09-26

## Next actions (standing authorization preserved)

1. Finish the final all-files hook gate, publish dev, push PR #2229 once, and merge after exact-head required checks AND every previously failing test job pass. D1 is already approved; advisory type backlog #73 is excluded.
   Revalidate: `gh pr view 2229 --json state,headRefOid,mergeStateStatus`.
2. Land every completed branch in dev and remove its clean worktree immediately. Only the primary checkout remains; there are no completed implementation siblings to retain. No PR or CI trigger for dev.
   Revalidate: `git worktree list --porcelain` and `git for-each-ref refs/heads refs/remotes`.
3. Preserve the five inherited stashes. Never restore/drop them without the user's decision. Rejected recovery was deleted and NEVER merged; the approved stale draft was deleted with its landing receipt.
   Revalidate: `git stash list` (five held entries), and archived disposition below.
4. Continue bounded archive-content adjudication; retain uncertain historical refs and never merge a stale prototype wholesale. Five archive clusters still have partial/unresolved content; no whole-forest completion claim.
   Revalidate: `workspaces/issue-1720-llm-consolidation/04-validate/csq13-ref-adjudication.json` (52 refs, explicit dispositions).
5. Keep the unresolved #2225 design question and paused Express routing/cache findings distinct from completed repairs. Package publishing is a separate release gate, not implied by promotion approval.
   Revalidate: `gh issue view 2225 --comments`; inspect Express callers before resuming that shard.

## Recovered authorization

Exact slot-13 Codex thread: `01a0d7ea-e2a1-74b3-8af2-2a47dc410525`.
Final user decision at 12:53:14 UTC: **"Retain reusable pool identities (recommended)"**.
The next turn ended `usage_limit_exceeded`; that decision is now implemented.
Also approved: #2249 opt-in owned execution, owner-loop HTTP reuse with aggregate cap,
and harmless URL diagnostics. No repeat approval is needed for those repairs.
User reiterated landing all remote/local branches, refs and worktrees, with active WIP drain.
Future promotions retain the 10-landings / 72-hours / immediate-security-or-deploy trigger
and require their own user authorization; #2229's D1 approval is already recorded.

## Integrated source and WIP

Dev includes #2238/PACT `fcf1ec06b`, #2248 `c1b04c8ae`, #2251 `839a039a3`,
#2249 `d3549dee4` (merge `0711ddee9`), Edge `a98075487`, SQLite `fc93ee8ff`,
credential scanner `d02980968`, cache controls `b91e8d177`, async migration `d2d8d1f34`,
coroutine ownership/replay `b31c191f9`, memory/CI `ca15ac555`, warning/Align `849157905`,
network/audio `9eaa4d4ee`, warning instruments `0f126ca02` / `1df572866`, duplicate
pytest configuration cleanup `658d97de4`, watchdog `772f12c64` (merge `03efa7c48`),
and Black assertion formatting `db9565623`.
All implementation worktrees and branches were drained after landing.
Formatter repair is landed as `e30256691`, with two clean correctness/security rounds; remote promotion still
points to `28602f1a0` until a single validated consolidated push. Refresh live refs before acting.

The final formatter repair sets `combine_as_imports` and consistent first-party namespaces
in four active configs. Actual old settings produced five Black/isort two-state cycles and
Kaizen-first batch grouping differed from single/root batches. Candidate fixed-point probes
passed three rounds. Actual all-file Black, isort and Ruff pass; import-order and narrow-pragma
reviews are complete. Three pragma scopes and optional-provider lookup order were preserved
with narrow sort boundaries. No behavioral equality is inferred solely from an import multiset.

## Actual validation (scope matters)

Integrated census at `b796ffe08`: Core units 5368 passed / one watchdog fixture failure;
Core integration 2607 passed; DataFlow infrastructure 27 passed; root infrastructure22 passed.
Kaizen LLM/parity/security1822 passed, expanded units8387 passed, regressions1965 passed,
authorization parity43 passed without skips, agents818 passed. Skips/deselections are excluded.
These are completed runs, superseding older interrupted Kaizen runs. Recovered final Core rerun at709759a38 passed5371 with5skips,3deselections,6xfails,5xpasses; those exclusions are not coverage.
Full configured hooks completed: pytest-check, doc8 and structural hooks passed; formatter/lint
failures are being repaired. The final full hook run, including pytest-check, remains mandatory after the new seed-test commit.

Watchdog repair has13 strict tests, actual delayed/disabled monitor controls, reached threshold
mutations, callback-survival checks, and two independent clean rounds. Warning tests now reject
unexpected categories. Old/new pytest9 controls prove duplicate-config notices removed while
authoritative pytest.ini files stay byte-identical. Focused coroutine37, memory22,
warning/Core118 + fresh Align1, network/audio277, and real SQLite cache6 all passed.
Holistic correctness/security reviews exercised ownership, warning scope, mapped CIDRs,
real localhost transport, and memory cleanup. DNS resolution-to-connect TOCTOU is not claimed fixed.

Final assigned remote runner: fresh workflow environments, strict changed tests, exact Core
Tier1 selection and every configured hook; one trestle mirror owner, no concurrent installs.
Per-commit pytest-check skips are documented and tracked to this final full-hook gate.
Local launcher/cache repair succeeded; older signal11 claims are historical, not current blockers.

## Archive and follow-on evidence

52-ref adjudication and follow-up JSONs are in
`workspaces/issue-1720-llm-consolidation/04-validate/csq13-*.json`.
Exact squash-tree matches are distinct from behavioral conformance. Align's missing fresh-process
regression was recovered with `849157905`. Release v0.9.7 matches its retained tag; this is not a
PyPI publication claim. Old strategy prose and cycle-test markers have explicit historical dispositions.
The parameter-validator prototype retains required/type safety and injection behavior in current
code, but its runtime-wide policy/report API is absent; debugger/optimizer remain unaudited.
Current spec's root-only flat-injection wording differs from actual old/current all-accepting-node
behavior. This is recorded, not treated as an archive-only lost feature.
Two trust files in the large scrap snapshot have landed/superseded receipts and actual controls;
that bounded review does not dispose of the whole mixed snapshot. No archive ref/tag was deleted.

Paused source findings: Express read/list/find_one accept `use_primary` without using it;
replica-routing helpers have no source callers. Warm outer-cache returns precede `_trust_check_read`
and keys scope by tenant without agent/clearance. These are source-level concerns, not
runtime-confirmed security verdicts, and were not closed by TTL-forwarding reviews.

## Standing forest (IDs preserved)

| ID | Obligation | Current disposition |
| --- | --- | --- |
| F21 | Promotion and package release backlog | #2229 D1 approved; final gates/promotion active. Publishing remains separate. |
| F22 | #2238 sites3–4 and restore | Landed `fcf1ec06b`, issue closed, tree drained; owner acceptance not inferred. |
| F23 | #2225 blocklist design/headline reconciliation | Residual A design remains unresolved; headline is capability accuracy. |
| F24 | Rejected recovery branch | Deleted with #2225 comment5830857222 evidence; NEVER merged. |
| F25 | Workstation/stash hygiene | Hook launcher repaired; D5 stale draft deleted; five stashes held. |
| F26 | Open-issue burndown | Active standing obligation, not closed by branch drain. |
| F27 | #2238 clearance parity | Landed with F22; independent union2713 passed,15 skipped. |
| F28 | #2248/#2249 | Both fixed/closed; #2249 merge0711ddee9,220 tests and two clean rounds, tree drained. |
| F29 | Burndown manifest | Landed `d10295cf4`; frozen source/generator counts are not owner acceptance. |
| F30 | Unlabelled issue triage | Labels captured and dispositions proposed; external labeling not done by this lane. |

## Operating hazards

- Use explicit primary `.venv/bin/python`; bare pyenv launchers were unreliable. Pin uv subprocess Python.
- Never edit primary while a commit's auto-stashing hooks run; preserve dirty work with cp backups.
- Offload expensive gates through trestle; 114/116 are no evidence. No concurrent mutation of one mirror venv.
- Assert resolved checkout root before any sibling work; a removed CWD must not silently redirect edits.
- Exact PR head required checks must be read separately from the merge command.
- Do not mistake archive reachability or GitHub issue closure for implementation/owner acceptance.
- `.session-notes.d/esperie.md` remains the existing operator fragment; avoid creating a stale second identity.

## CSQ 14 continuation receipts

Exact recovered slot14 thread: `01a0d8a0-e67b-7dc2-8628-1e1bfbbd3eca`.
Final old gate actually finished: Core and all configured hooks passed; ML alone failed
on a30-second PyTorch Lightning cold import. `seed(torch=False)` intentionally leaves
its independent Lightning flag enabled. Unit fixtures now isolate optional libraries
and assert actual calls/reports, preserving production behavior. Strict original six-file
selection:237passed with warnings as errors and unchanged30-second timeout; reached
source mutations rejected. Correctness and adversarial reviewers each delivered two
clean rounds. Implementation34eca2992, merge6fa357a1b; sibling and branch removed.

Archive evidence landed asf065c42bd, merge6d5e34e35; sibling and branch removed.
All52archive/original ref names checked,30previously recorded tips checked, all52current
tips captured. Five recovered reports distinguish fresh structural evidence from prior
runtime results; no original unresolved disposition was upgraded. See04-validate/csq14-*
and launch-ledger-csq14-resume.md. Only primary checkout remains; five stashes held.

Final all-files hook run is owed once, including pytest-check skipped/documented on the
seed-test checkpoint. PR still has old28602f1a0 pending the consolidated push.
Vault sweep/wrapup pair remains owed before ending this recovery run (CLAUDE.md Directive1).
